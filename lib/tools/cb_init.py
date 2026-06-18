"""cb_init.py — one-command bootstrap for canvas-toolbox.

Sprint 2 of the productional-alignment work (inspired by kenn-io/roborev's
`roborev init` pattern, 2026-06-18 research). Closes the "what do I do
AFTER I clone?" friction every adopter (and every fresh contributor agent)
currently hits.

WHAT IT DOES — 8 idempotent steps

  1. Install uv (Astral's official installer, curl-pipe) if not on PATH
  2. Install Python 3.14 via uv (uv-managed; never touches system Python)
  3. Write a .env stub in cwd with the required fields commented; STOP
     here on first run so the operator can fill in CANVAS_API_TOKEN /
     CANVAS_BASE_URL / CANVAS_COURSE_ID manually
  4. `uv sync --group dev` from the canvas-toolbox repo root (pulls all
     deps + dev group: pytest, ruff, pre-commit)
  5. `uv run playwright install chromium` (~92 MB; used by
     grader_follow_share_url for ChatGPT/Gemini share URLs)
  6. `uv run pre-commit install` (ruff + actionlint on every commit)
  7. Canvas API smoke test — `GET /api/v1/users/self` (read-only;
     confirms the token works + reports the authenticated user's name)
  8. Surface AGENTS.md + the bug-intake one-liner

Every step is idempotent: re-running cb-init after the first complete
pass is a fast no-op that prints "✓ already done — skipping" for each
step.

SMART PROMPTS (decision G)
  When a step has work to do, cb-init prompts y/n. When it doesn't
  (already-installed / already-done), it silently skips. Use `--yes`
  to accept all prompts (CI / Codespaces / scripted runs).

MAINTAINER vs ADOPTER (decision A)
  Default mode is `adopter` (the dominant case). Pass `--mode maintainer`
  to suppress adopter-facing hints (e.g., the `cb-report-bug` reminder).
  Auto-detection from `git remote get-url origin` surfaces a suggestion
  but doesn't override the default; the flag is the explicit toggle.

WHERE THE .env LANDS
  cb-init writes the stub to the CURRENT WORKING DIRECTORY. This lets
  the user control placement by where they invoke from:
    - Maintainer / adopter-standalone (cd canvas-toolbox && cb-init)
      → .env at canvas-toolbox/.env
    - Adopter-vendored (cd consumer-repo && uv run python
      canvas-toolbox/lib/tools/cb_init.py) → .env at consumer-repo/.env
  Both are valid; `_env_loader.py` walks up from script location to find
  the nearest .env.

WHAT IT DOES NOT DO
  - No Canvas WRITES. Step 7 hits `/users/self` (read-only) only.
  - No `gh` / GitHub CLI requirements. Bug intake goes through the
    Cloudflare Worker (cb_report_bug.py).
  - No grader config.json scaffold. Use `grader_scaffold.py` (#54-A)
    when starting a new grading workflow.
  - No system-Python or system-anything install. Everything is
    uv-managed and contained to the project's venv.

USAGE
  uv run python lib/tools/cb_init.py                     # interactive
  uv run python lib/tools/cb_init.py --yes               # non-interactive
  uv run python lib/tools/cb_init.py --check             # dry-run; no writes
  uv run python lib/tools/cb_init.py --mode maintainer   # explicit mode
  uv run python lib/tools/cb_init.py --skip-playwright   # skip the 92 MB

EXIT CODES
  0  setup complete (every step that needed to run, ran successfully)
  1  setup stopped (user declined a step, or a step failed); message
     above will name the issue. Re-run to continue.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# cb_init.py lives in lib/tools/, so the repo root is two parents up.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TARGET_PYTHON = "3.14"
UV_INSTALL_URL = "https://astral.sh/uv/install.sh"

# The canonical .env stub. Two fields are REQUIRED for any tool to run
# (TOKEN + BASE_URL); COURSE_ID + SANDBOX_ID are usually passed via CLI
# flags per-command (e.g. `--course-id 12345`) but adopters who work on
# one course can drop it in env to save typing.
ENV_STUB = """# canvas-toolbox configuration
# Fill in the REQUIRED values below, then re-run cb-init to continue from step 4.
# See AGENTS.md for the full setup guide.

# REQUIRED — your Canvas personal access token.
# Canvas → Account → Settings → New Access Token (set a 90-day expiry).
CANVAS_API_TOKEN=

# REQUIRED — your institution's Canvas base URL (no trailing slash).
# e.g. https://institution.instructure.com
CANVAS_BASE_URL=

# OPTIONAL — the course ID you usually work with. Tools also accept
# `--course-id <id>` so you can leave this blank and pass it per-command.
# CANVAS_COURSE_ID=

# OPTIONAL — a sandbox course ID safe for write operations during testing.
# CANVAS_SANDBOX_ID=
"""


# ---------------------------------------------------------------------------
# Pure-logic helpers (no subprocess / no filesystem — unit-testable)
# ---------------------------------------------------------------------------

def detect_mode_from_remote(remote_url: str) -> str:
    """Return 'maintainer' iff remote_url points at chaz-clark/canvas-toolbox,
    else 'adopter'. Empty/unknown → 'adopter' (the safe default per decision A)."""
    if not remote_url:
        return "adopter"
    return "maintainer" if "chaz-clark/canvas-toolbox" in remote_url else "adopter"


def env_stub_content() -> str:
    """Return the .env stub written when no .env exists. Pure function so
    tests can assert content without filesystem touches."""
    return ENV_STUB


def parse_canvas_self_name(payload) -> str:  # noqa: ANN001 — accept anything
    """Extract the display name from a /api/v1/users/self response payload.
    Returns '(no name)' for any missing/malformed input; never raises."""
    if not isinstance(payload, dict):
        return "(no name)"
    return str(payload.get("name") or payload.get("short_name") or "(no name)")


def stub_is_filled(env_text: str) -> bool:
    """True iff env_text has the two REQUIRED fields (CANVAS_API_TOKEN +
    CANVAS_BASE_URL) populated with non-empty values. CANVAS_COURSE_ID
    is OPTIONAL — most tools accept `--course-id` so an operator working
    across multiple courses leaves it blank. Comments + blank lines are
    ignored. Surrounding quotes are stripped."""
    required = {"CANVAS_API_TOKEN", "CANVAS_BASE_URL"}
    found_with_value: set[str] = set()
    for line in env_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in required:
            continue
        value = value.strip().strip('"').strip("'")
        if value:
            found_with_value.add(key)
    return required.issubset(found_with_value)


# ---------------------------------------------------------------------------
# State detection (filesystem + subprocess; harder to test cleanly — kept
# narrow so the pure helpers above carry the test surface)
# ---------------------------------------------------------------------------

def get_git_remote_origin() -> str:
    """Return the URL of the 'origin' remote, or '' if not a git repo /
    no origin / git is missing."""
    try:
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def is_uv_installed() -> bool:
    return shutil.which("uv") is not None


def uv_has_python(target: str) -> bool:
    """Run `uv python list --only-installed` and check for cpython-<target>.
    Returns False on any error — caller will attempt the install."""
    if not is_uv_installed():
        return False
    try:
        r = subprocess.run(
            ["uv", "python", "list", "--only-installed"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0 and f"cpython-{target}" in r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def playwright_chromium_cache_dir() -> Path:
    """Per-platform Playwright cache directory. Used for the
    "is Chromium installed" check without invoking Playwright itself."""
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    if platform.system() == "Windows":
        return Path.home() / "AppData" / "Local" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def is_playwright_chromium_installed() -> bool:
    cache = playwright_chromium_cache_dir()
    if not cache.exists():
        return False
    try:
        return any(p.name.startswith("chromium") for p in cache.iterdir())
    except OSError:
        return False


def is_pre_commit_installed() -> bool:
    """True if REPO_ROOT/.git/hooks/pre-commit exists AND looks like a
    pre-commit-framework hook (contains the framework's marker)."""
    hook = REPO_ROOT / ".git" / "hooks" / "pre-commit"
    if not hook.exists():
        return False
    try:
        return "pre-commit" in hook.read_text(encoding="utf-8").lower()
    except OSError:
        return False


def smoke_test_canvas(token: str, base_url: str) -> tuple[bool, str]:
    """Hit GET /api/v1/users/self. Return (success, name-or-error). The
    `requests` import is lazy because step 4 (uv sync) installs it — and
    step 7 (smoke test) only runs AFTER step 4. Bootstrapping protected."""
    try:
        import requests  # noqa: PLC0415 — intentional lazy import
    except ImportError:
        return False, "requests not installed (uv sync didn't run yet?)"
    try:
        r = requests.get(
            f"{base_url.rstrip('/')}/api/v1/users/self",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        try:
            return True, parse_canvas_self_name(r.json())
        except json.JSONDecodeError:
            return False, "response not JSON"
    except Exception as e:  # noqa: BLE001 — surface any network error
        return False, f"network error: {e}"


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------

def prompt_y_n(prompt: str, default_yes: bool = True, auto_yes: bool = False) -> bool:
    if auto_yes:
        print(f"{prompt} [auto-yes]")
        return True
    suffix = "[Y/n]" if default_yes else "[y/N]"
    try:
        answer = input(f"{prompt} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return default_yes if not answer else answer in ("y", "yes")


def run_subprocess(args: list[str], *, cwd: Path | None = None, timeout: int = 120) -> bool:
    """Run a subprocess inheriting stdout/stderr. Return True on success."""
    try:
        r = subprocess.run(args, cwd=str(cwd) if cwd else None, timeout=timeout)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"  ✗ {' '.join(args)}: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Step runners — return True if cb-init should continue
# ---------------------------------------------------------------------------

def step_1_install_uv(*, auto_yes: bool, check_only: bool) -> bool:
    if is_uv_installed():
        print("Step 1/8: ✓ uv already installed — skipping.")
        return True
    if check_only:
        print("Step 1/8: would install uv via Astral's official installer.")
        return False
    if platform.system() == "Windows":
        print("Step 1/8: uv not on PATH. On Windows, install manually:")
        print("           irm https://astral.sh/uv/install.ps1 | iex")
        print("         Then re-run cb-init.")
        return False
    if not prompt_y_n(
        "Step 1/8: uv not on PATH. Install via Astral's official installer (curl-pipe)?",
        auto_yes=auto_yes,
    ):
        print("  ⚠ Skipped. cb-init can't proceed without uv.")
        return False
    print("  Installing uv...")
    if not run_subprocess(["sh", "-c", f"curl -LsSf {UV_INSTALL_URL} | sh"], timeout=120):
        return False
    if not is_uv_installed():
        # The installer adds uv to PATH via shell-rc; this process doesn't pick it up.
        print("  ✓ uv installed but not yet on this shell's PATH.")
        print("    Open a new terminal (or `source ~/.zshrc` / `~/.bashrc`),")
        print("    then re-run cb-init.")
        return False
    print("  ✓ uv installed.")
    return True


def step_2_install_python(*, auto_yes: bool, check_only: bool) -> bool:
    if uv_has_python(TARGET_PYTHON):
        print(f"Step 2/8: ✓ Python {TARGET_PYTHON} (uv-managed) already installed — skipping.")
        return True
    if check_only:
        print(f"Step 2/8: would run `uv python install {TARGET_PYTHON}`.")
        return False
    if not prompt_y_n(
        f"Step 2/8: Python {TARGET_PYTHON} not managed by uv. Install (uv-only; "
        f"won't touch system Python)?",
        auto_yes=auto_yes,
    ):
        print("  ⚠ Skipped.")
        return False
    print(f"  Installing Python {TARGET_PYTHON}...")
    if not run_subprocess(["uv", "python", "install", TARGET_PYTHON], timeout=180):
        return False
    print(f"  ✓ Python {TARGET_PYTHON} ready.")
    return True


def step_3_env_stub(*, cwd: Path, auto_yes: bool, check_only: bool) -> bool:
    env_path = cwd / ".env"
    if env_path.exists():
        if stub_is_filled(env_path.read_text(encoding="utf-8")):
            print("Step 3/8: ✓ .env present + required fields filled — skipping.")
            return True
        print(f"Step 3/8: ⚠ .env exists at {env_path} but required fields are blank.")
        print("  Fill in CANVAS_API_TOKEN + CANVAS_BASE_URL, then re-run cb-init.")
        return False
    if check_only:
        print(f"Step 3/8: would write a .env stub to {env_path}.")
        return False
    if not prompt_y_n(
        f"Step 3/8: .env not found. Write a stub at {env_path}?",
        auto_yes=auto_yes,
    ):
        print("  ⚠ Skipped.")
        return False
    env_path.write_text(env_stub_content(), encoding="utf-8")
    print(f"  ✓ Wrote stub to {env_path}.")
    print("    Now: edit it (any editor — VS Code / vim / nano / etc.),")
    print("    fill in CANVAS_API_TOKEN + CANVAS_BASE_URL + CANVAS_COURSE_ID,")
    print("    then re-run cb-init to continue from step 4.")
    return False  # halt — operator needs to fill in values manually per decision


def step_4_uv_sync(*, auto_yes: bool, check_only: bool) -> bool:
    if check_only:
        print("Step 4/8: would run `uv sync --group dev` from the repo root.")
        return True  # check-only: skip the work but keep going
    print("Step 4/8: running `uv sync --group dev` (idempotent — verifies + installs deps).")
    if not run_subprocess(["uv", "sync", "--group", "dev"], cwd=REPO_ROOT, timeout=180):
        return False
    print("  ✓ Deps synced.")
    return True


def step_5_playwright(*, auto_yes: bool, check_only: bool, skip: bool) -> bool:
    if skip:
        print("Step 5/8: ⏭ skipped via --skip-playwright.")
        return True
    if is_playwright_chromium_installed():
        print("Step 5/8: ✓ Playwright Chromium already installed — skipping.")
        return True
    if check_only:
        print("Step 5/8: would run `uv run playwright install chromium` (~92 MB).")
        return True
    if not prompt_y_n(
        "Step 5/8: Playwright Chromium not detected. Install (~92 MB)? Required by "
        "grader_follow_share_url for ChatGPT/Gemini share URL parsing.",
        auto_yes=auto_yes,
    ):
        print("  ⚠ Skipped. Share-URL parsing won't work until installed.")
        return True  # non-fatal
    print("  Installing Chromium...")
    if not run_subprocess(["uv", "run", "playwright", "install", "chromium"],
                          cwd=REPO_ROOT, timeout=300):
        return False
    print("  ✓ Chromium installed.")
    return True


def step_6_pre_commit(*, auto_yes: bool, check_only: bool) -> bool:
    if is_pre_commit_installed():
        print("Step 6/8: ✓ pre-commit hook already installed — skipping.")
        return True
    if check_only:
        print("Step 6/8: would run `uv run pre-commit install` from the repo root.")
        return True
    if not prompt_y_n(
        "Step 6/8: pre-commit hook not installed. Install it (ruff + actionlint "
        "run on every commit)?",
        auto_yes=auto_yes,
    ):
        print("  ⚠ Skipped.")
        return True  # non-fatal
    if not run_subprocess(["uv", "run", "pre-commit", "install"],
                          cwd=REPO_ROOT, timeout=60):
        return False
    print("  ✓ pre-commit hook installed.")
    return True


def step_7_canvas_smoke(*, cwd: Path, check_only: bool) -> bool:
    env_path = cwd / ".env"
    if not env_path.exists():
        print("Step 7/8: ⚠ No .env at " + str(env_path) + " — cannot smoke-test. Skipping.")
        return True
    env_vars: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env_vars[k.strip()] = v.strip().strip('"').strip("'")
    token = env_vars.get("CANVAS_API_TOKEN", "")
    base_url = env_vars.get("CANVAS_BASE_URL", "")
    if not token or not base_url:
        print("Step 7/8: ⚠ CANVAS_API_TOKEN or CANVAS_BASE_URL blank — cannot smoke-test.")
        return True
    if not base_url.startswith("http"):
        base_url = "https://" + base_url
    if check_only:
        print("Step 7/8: would hit GET " + base_url.rstrip('/') + "/api/v1/users/self (read-only).")
        return True
    print("Step 7/8: smoke-testing Canvas API...")
    ok, msg = smoke_test_canvas(token, base_url)
    if not ok:
        print("  ✗ Smoke test failed: " + msg)
        print("    Check CANVAS_API_TOKEN + CANVAS_BASE_URL in " + str(env_path))
        return False
    print("  ✓ Authenticated as " + msg + ".")
    return True


def step_8_surface_docs(*, mode: str) -> bool:
    print("Step 8/8: setup complete.")
    print()
    print("Next:")
    print("  • Read " + str(REPO_ROOT) + "/AGENTS.md — Active Context tells you what's where")
    print("  • Tools under lib/tools/ — try `uv run python lib/tools/course_audit.py --help`")
    print("  • For grading workflows, see grading_readme.md + lib/agents/canvas_grader.md")
    if mode == "adopter":
        print("  • Hit a bug or want a feature? Run `uv run python lib/tools/cb_report_bug.py`")
        print("    (zero-config; routes through the Cloudflare bug-intake worker)")
    else:
        print("  • [maintainer mode] cb-report-bug hint suppressed; you ARE the maintainer.")
    print()
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "One-command bootstrap for canvas-toolbox. Detects state, "
            "installs uv + Python + deps + Playwright + pre-commit hooks, "
            "smoke-tests your Canvas API token, surfaces the docs."
        ),
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    parser.add_argument(
        "--mode", choices=["maintainer", "adopter"], default="adopter",
        help=("Default: adopter. Pass `--mode maintainer` to suppress "
              "adopter-facing hints (e.g. the cb-report-bug reminder). "
              "Auto-detection from `git remote get-url origin` surfaces a "
              "suggestion but doesn't override the default — the flag is "
              "the explicit toggle."),
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip all prompts; accept defaults. For CI / Codespaces / scripted runs.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Show what each step WOULD do, without writing anything.",
    )
    parser.add_argument(
        "--skip-playwright", action="store_true",
        help="Skip the Playwright Chromium download (~92 MB). Use in CI or "
             "when share-URL parsing isn't needed.",
    )
    args = parser.parse_args()

    cwd = Path.cwd()
    print()
    print("=== canvas-toolbox cb-init v" + __version__ + " ===")
    print("    cwd:       " + str(cwd))
    print("    repo root: " + str(REPO_ROOT))

    # Mode resolution — flag wins; auto-detection is a hint.
    detected = detect_mode_from_remote(get_git_remote_origin())
    mode = args.mode
    if detected != mode:
        print("    mode:      " + mode + " (auto-detected: " + detected + ")")
    else:
        print("    mode:      " + mode)
    if args.check:
        print("    --check:   no writes will occur")
    print()

    step_funcs = [
        lambda: step_1_install_uv(auto_yes=args.yes, check_only=args.check),
        lambda: step_2_install_python(auto_yes=args.yes, check_only=args.check),
        lambda: step_3_env_stub(cwd=cwd, auto_yes=args.yes, check_only=args.check),
        lambda: step_4_uv_sync(auto_yes=args.yes, check_only=args.check),
        lambda: step_5_playwright(
            auto_yes=args.yes, check_only=args.check, skip=args.skip_playwright,
        ),
        lambda: step_6_pre_commit(auto_yes=args.yes, check_only=args.check),
        lambda: step_7_canvas_smoke(cwd=cwd, check_only=args.check),
        lambda: step_8_surface_docs(mode=mode),
    ]

    for fn in step_funcs:
        ok = fn()
        if not ok and not args.check:
            # Normal-mode failure: stop. In --check mode, continue so the
            # operator sees the full plan.
            print()
            print("cb-init stopped. Address the message above + re-run.")
            return 1

    print()
    print("✓ cb-init complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

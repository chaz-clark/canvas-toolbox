"""cb_init.py — one-command bootstrap for canvas-toolbox.

Sprint 2 of the productional-alignment work (inspired by kenn-io/roborev's
`roborev init` pattern, 2026-06-18 research). Closes the "what do I do
AFTER I clone?" friction every adopter (and every fresh contributor agent)
currently hits.

v1.6 ARCHITECTURE (course-centric layout)
  Detects subdirectory context automatically. When run from DS460/canvas-toolbox/,
  creates course files at DS460/ (course root), not inside canvas-toolbox/.

  Course root layout:
    DS460/                      # Work from here
    ├── canvas-toolbox/         # Tools only (gitignored)
    │   └── AGENTS.md          # Toolkit knowledge
    ├── .env                   # Course config
    ├── .gitignore             # Course gitignore
    ├── AGENTS.md              # Course context (HERMES learning)
    ├── course/                # Canvas mirror (from canvas-sync)
    ├── grading/               # Grading workflows
    └── handoffs/              # Session notes (opt-in via --with-handoffs)

WHAT IT DOES — 14 idempotent steps

  1. Install uv (Astral's official installer, curl-pipe) if not on PATH
  2. Install Python 3.14 via uv (uv-managed; never touches system Python)
  3. Write a .env stub at course root with required fields; STOP here on
     first run so operator can fill in CANVAS_API_TOKEN / CANVAS_BASE_URL /
     CANVAS_COURSE_ID manually
  4. `uv sync --group dev` from canvas-toolbox repo root (pulls all deps +
     dev group: pytest, ruff, pre-commit)
  5. Install Rust (optional in v1.5.x; opt-in via --with-rust; will become
     required in v2.x; provides 10-100x speedup for large courses)
  6. `uv run playwright install chromium` (~92 MB; used by
     grader_follow_share_url for ChatGPT/Gemini share URLs)
  7. `uv run pre-commit install` (ruff + actionlint on every commit)
  8. Canvas API smoke test — `GET /api/v1/users/self` (read-only; confirms
     token works + reports authenticated user's name)
  9. Surface AGENTS.md + bug-intake one-liner
 10. Create .gitignore at course root (subdirectory mode only)
 11. Run canvas-sync --pull to populate course/ (subdirectory mode only)
 12. Generate course-specific AGENTS.md stub (subdirectory mode only)
 13. Create handoffs/ directory (opt-in via --with-handoffs; dev feature)
 14. Copy slash commands to .claude/commands/ (always; makes tools discoverable)

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

WHERE THE .env LANDS (v1.6+)
  Automatic detection:
    - Subdirectory mode (DS460/canvas-toolbox/) → .env at DS460/
    - Standalone mode (canvas-toolbox/) → .env at canvas-toolbox/
  Both are valid; `_env_loader.py` walks up from script location to find
  the nearest .env.

WHAT IT DOES NOT DO
  - No Canvas WRITES. Step 8 hits `/users/self` (read-only) only.
    Step 11 runs canvas-sync --pull (read-only sync from Canvas).
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
  uv run python lib/tools/cb_init.py --with-handoffs     # create handoffs/ (dev)

EXIT CODES
  0  setup complete (every step that needed to run, ran successfully)
  1  setup stopped (user declined a step, or a step failed); message
     above will name the issue. Re-run to continue.
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from _env_loader import force_utf8_console
except ImportError:
    # Fallback for pre-sync environments (cb-init runs before uv sync)
    def force_utf8_console() -> None:
        if sys.platform != "win32":
            return
        import io
        if sys.stdout is not None:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
        if sys.stderr is not None:
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

try:
    # Single source of truth for the HG-5 grading-protocol pointer (#207), shared
    # with sync_grading_protocol.py so a freshly-init'd repo and a retrofitted one
    # carry the identical, sentinel-marked block.
    from sync_grading_protocol import POINTER_BLOCK as GRADING_POINTER_BLOCK
except ImportError:
    # Fallback for pre-sync / partial vendored environments. Keeps the same
    # sentinel marker so sync_grading_protocol stays idempotent against it.
    GRADING_POINTER_BLOCK = (
        "<!-- canvas-toolbox:grading-protocol-pointer -->\n\n"
        "## ⚠️ Grading — HG-5: the instructor decides\n\n"
        "AI-assisted grading is decision support, not autonomy. Never push AI-drafted "
        "grades without human review. Full protocol: canvas-toolbox/AGENTS.md → "
        '"AI Grading Protocol — HG-5".\n\n'
        "<!-- /canvas-toolbox:grading-protocol-pointer -->"
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# cb_init.py lives in lib/tools/, so the repo root is two parents up.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TARGET_PYTHON = "3.14"
UV_INSTALL_URL = "https://astral.sh/uv/install.sh"


# ---------------------------------------------------------------------------
# v1.6 Architecture: Course Root Detection
# ---------------------------------------------------------------------------

def detect_course_context() -> tuple[Path, bool]:
    """
    Detect if running from canvas-toolbox subdirectory (v1.6+ architecture).

    Returns: (course_root, is_subdirectory)
    - If in canvas-toolbox/ subdirectory: (parent, True)  # DS460/canvas-toolbox/
    - If standalone: (REPO_ROOT, False)                    # canvas-toolbox/

    v1.6 architecture: all course files (.env, course/, grading/, AGENTS.md,
    handoffs/) live at course root, not inside canvas-toolbox/.
    """
    if REPO_ROOT.name != "canvas-toolbox":
        # Renamed or non-standard layout
        return REPO_ROOT, False

    # Common development folder names where standalone canvas-toolbox lives
    dev_folders = {"GitHub", "github", "repos", "repositories", "projects", "src", "code", "dev", "Documents"}

    parent = REPO_ROOT.parent
    if parent.name in dev_folders:
        # Standalone mode: ~/GitHub/canvas-toolbox or ~/Documents/GitHub/canvas-toolbox
        return REPO_ROOT, False

    # Subdirectory mode: DS460/canvas-toolbox, itm327/canvas-toolbox, etc.
    return parent, True

COURSE_ROOT, IS_SUBDIRECTORY = detect_course_context()

# The canonical .env stub. Two fields are REQUIRED for any tool to run
# (TOKEN + BASE_URL); COURSE_ID + SANDBOX_ID are usually passed via CLI
# flags per-command (e.g. `--course-id 12345`) but adopters who work on
# one course can drop it in env to save typing.
ENV_STUB = """# Canvas course configuration
# This file lives at the course root (not inside canvas-toolbox/).
# Fill in the REQUIRED values below, then re-run cb-init to continue.
# See canvas-toolbox/AGENTS.md for the full setup guide.

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


def is_uv_synced() -> bool:
    """True if REPO_ROOT/.venv exists. `uv sync` is idempotent, so this
    is only a heuristic to keep the cb-init output honest: when uv has
    already synced (often because `uv run` auto-sync'd on invocation),
    step 4 prints '✓ skipping' instead of 'would run'."""
    return (REPO_ROOT / ".venv").exists()


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
        print("Step 1/14: ✓ uv already installed — skipping.")
        return True
    if check_only:
        print("Step 1/14: would install uv via Astral's official installer.")
        return False
    if platform.system() == "Windows":
        print("Step 1/14: uv not on PATH. On Windows, install manually:")
        print("           irm https://astral.sh/uv/install.ps1 | iex")
        print("         Then re-run cb-init.")
        return False
    if not prompt_y_n(
        "Step 1/14: uv not on PATH. Install via Astral's official installer (curl-pipe)?",
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
        print(f"Step 2/14: ✓ Python {TARGET_PYTHON} (uv-managed) already installed — skipping.")
        return True
    if check_only:
        print(f"Step 2/14: would run `uv python install {TARGET_PYTHON}`.")
        return False
    if not prompt_y_n(
        f"Step 2/14: Python {TARGET_PYTHON} not managed by uv. Install (uv-only; "
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


def step_3_env_stub(*, course_root: Path, auto_yes: bool, check_only: bool) -> bool:
    env_path = course_root / ".env"
    old_env_path = REPO_ROOT / ".env"  # v1.5 location

    # v1.6 migration: check for .env in old location (canvas-toolbox/.env)
    if IS_SUBDIRECTORY and not env_path.exists() and old_env_path.exists():
        print(f"Step 3/14: detected .env at old v1.5 location: {old_env_path}")
        print(f"          v1.6 moves .env to course root: {env_path}")
        if check_only:
            print(f"          would offer to migrate .env to {env_path}")
            return False
        if prompt_y_n(
            f"Step 3/14: migrate .env from {old_env_path} to {env_path}?",
            auto_yes=auto_yes,
        ):
            import shutil
            shutil.move(str(old_env_path), str(env_path))
            print(f"  ✓ Migrated .env to {env_path}")
            # Check if migrated .env is filled
            if stub_is_filled(env_path.read_text(encoding="utf-8")):
                print("    .env is filled — continuing setup.")
                return True
            print("    .env migrated but required fields are blank.")
            print("    Fill in CANVAS_API_TOKEN + CANVAS_BASE_URL, then re-run cb-init.")
            return False
        print("  ⚠ Migration declined — creating new .env stub instead.")

    if env_path.exists():
        if stub_is_filled(env_path.read_text(encoding="utf-8")):
            print("Step 3/14: ✓ .env present + required fields filled — skipping.")
            return True
        print(f"Step 3/14: ⚠ .env exists at {env_path} but required fields are blank.")
        print("  Fill in CANVAS_API_TOKEN + CANVAS_BASE_URL, then re-run cb-init.")
        return False
    if check_only:
        print(f"Step 3/14: would write a .env stub to {env_path}.")
        return False
    if not prompt_y_n(
        f"Step 3/14: .env not found. Write a stub at {env_path}?",
        auto_yes=auto_yes,
    ):
        print("  ⚠ Skipped.")
        return False
    env_path.write_text(env_stub_content(), encoding="utf-8")
    print(f"  ✓ Wrote stub to {env_path}.")
    print("    Now: edit it (any editor — VS Code / vim / nano / etc.),")
    print("    fill in CANVAS_API_TOKEN + CANVAS_BASE_URL (CANVAS_COURSE_ID is optional),")
    print("    then re-run cb-init to continue from step 4.")
    return False  # halt — operator needs to fill in values manually per decision


def step_4_uv_sync(*, auto_yes: bool, check_only: bool) -> bool:
    # Honest message either way — uv sync is idempotent, but a fresh
    # invocation via `uv run` already auto-syncs, so we only PROMPT for a
    # fresh install. When .venv exists we just verify (no prompt).
    venv_exists = is_uv_synced()
    if check_only:
        if venv_exists:
            print("Step 4/14: ✓ .venv exists — would verify with `uv sync --group dev`.")
        else:
            print("Step 4/14: would run `uv sync --group dev` (creates .venv + installs deps).")
        return True
    if venv_exists:
        print("Step 4/14: ✓ .venv exists — verifying deps with `uv sync --group dev`...")
    else:
        print("Step 4/14: running `uv sync --group dev` (creates .venv + installs deps)...")
    if not run_subprocess(["uv", "sync", "--group", "dev"], cwd=REPO_ROOT, timeout=180):
        return False
    print("  ✓ Deps synced.")
    return True


def step_5_rust_optional(*, check_only: bool, with_rust: bool) -> bool:
    """Install Rust (OPTIONAL in v1.5.x - opt-in via --with-rust flag)."""
    if not with_rust:
        print("Step 5/14: ⏭  Rust installation skipped (optional in v1.5.x).")
        print("          For 10-100x speedup on large courses: cb-init --with-rust")
        print("          Rust will become required in v2.x.")
        return True

    # If --with-rust provided, show message that manual install is needed for v1.5.0
    # Auto-install will be added in v1.5.1
    if check_only:
        print("Step 5/14: Rust installation requested via --with-rust")
        print("          (v1.5.0: manual install required; auto-install in v1.5.1)")
        return True

    print("Step 5/14: Rust installation requested via --with-rust")
    print()
    print("  v1.5.0 requires manual Rust installation:")
    print("    1. Install Rust via rustup:")
    print("       curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
    print()
    print("    2. Activate Rust in your shell:")
    print("       source ~/.cargo/env")
    print()
    print("    3. Build canvas-toolbox Rust binaries:")
    print(f"       cd {REPO_ROOT / 'lib' / 'tools' / 'fix_override_recalc_rs'}")
    print("       cargo build --release")
    print()
    print("  Auto-install will be added in v1.5.1")
    print()
    return True


def step_6_playwright(*, auto_yes: bool, check_only: bool, skip: bool) -> bool:
    if skip:
        print("Step 6/14: ⏭ skipped via --skip-playwright.")
        return True
    if is_playwright_chromium_installed():
        print("Step 6/14: ✓ Playwright Chromium already installed — skipping.")
        return True
    if check_only:
        print("Step 6/14: would run `uv run playwright install chromium` (~92 MB).")
        return True
    if not prompt_y_n(
        "Step 6/14: Playwright Chromium not detected. Install (~92 MB)? Required by "
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


def step_7_pre_commit(*, auto_yes: bool, check_only: bool) -> bool:
    if is_pre_commit_installed():
        print("Step 7/14: ✓ pre-commit hook already installed — skipping.")
        return True
    if check_only:
        print("Step 7/14: would run `uv run pre-commit install` from the repo root.")
        return True
    if not prompt_y_n(
        "Step 7/14: pre-commit hook not installed. Install it (ruff + actionlint "
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


def step_8_canvas_smoke(*, cwd: Path, check_only: bool) -> bool:
    env_path = cwd / ".env"
    if not env_path.exists():
        print("Step 8/14: ⚠ No .env at " + str(env_path) + " — cannot smoke-test. Skipping.")
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
        print("Step 8/14: ⚠ CANVAS_API_TOKEN or CANVAS_BASE_URL blank — cannot smoke-test.")
        return True
    if not base_url.startswith("http"):
        base_url = "https://" + base_url
    if check_only:
        print("Step 8/14: would hit GET " + base_url.rstrip('/') + "/api/v1/users/self (read-only).")
        return True
    print("Step 8/14: smoke-testing Canvas API...")
    ok, msg = smoke_test_canvas(token, base_url)
    if not ok:
        print("  ✗ Smoke test failed: " + msg)
        print("    Check CANVAS_API_TOKEN + CANVAS_BASE_URL in " + str(env_path))
        return False
    print("  ✓ Authenticated as " + msg + ".")
    return True


def step_9_surface_docs(*, mode: str) -> bool:
    print("Step 9/14: setup complete.")
    print()
    print("Next:")
    print("  • Read " + str(REPO_ROOT) + "/AGENTS.md — Active Context tells you what's where")
    print("  • Tools under lib/tools/ — try `uv run python lib/tools/course_audit.py --help`")
    print("  • For grading workflows, see docs/grading_readme.md + lib/agents/canvas_grader.md")
    if mode == "adopter":
        print("  • Share back — three zero-friction paths (no GitHub account needed):")
        print("      ./bin/cb-report-bug    bug: <description>          # toolkit broke")
        print("      ./bin/cb-report-bug    enhancement: <description>  # want a feature")
        print("      ./bin/cb-share         share: <description>        # built something to contribute")
        print("    See README → 'How can you share back?' or .github/CONTRIBUTING.md for the full shape.")
    else:
        print("  • [maintainer mode] share-back hints suppressed; you ARE the maintainer.")
    print()
    return True


def step_10_gitignore(*, course_root: Path, is_subdir: bool, check_only: bool) -> bool:
    """Create .gitignore at course root (v1.6+ subdirectory mode only)."""
    if not is_subdir:
        print("Step 10/14: ⏭  Standalone mode — .gitignore not needed.")
        return True

    gitignore_path = course_root / ".gitignore"
    gitignore_content = """.env
canvas-toolbox/
handoffs/
course/
course_ref/
course_src/
.canvas/
grading/
quality_report.md
"""

    if gitignore_path.exists():
        print(f"Step 10/14: ✓ .gitignore exists at {gitignore_path} — skipping.")
        return True

    if check_only:
        print(f"Step 10/14: would create .gitignore at {gitignore_path}")
        return True

    gitignore_path.write_text(gitignore_content, encoding="utf-8")
    print(f"  ✓ Created .gitignore at {gitignore_path}")
    return True


def step_11_canvas_sync(*, course_root: Path, is_subdir: bool, check_only: bool) -> bool:
    """Run canvas-sync --pull to populate course/ directory (v1.6+ subdirectory mode only)."""
    if not is_subdir:
        print("Step 11/14: ⏭  Standalone mode — canvas-sync skipped.")
        print("          Run manually: uv run python lib/tools/canvas_sync.py --pull")
        return True

    if check_only:
        print("Step 11/14: would run canvas-sync --pull from course root")
        return True

    print("Step 11/14: Running canvas-sync --pull to fetch course data...")
    sync_tool = REPO_ROOT / "lib" / "tools" / "canvas_sync.py"

    if not run_subprocess(
        ["uv", "run", "python", str(sync_tool), "--pull"],
        cwd=course_root,
        timeout=300
    ):
        print("  ⚠ canvas-sync failed (check .env has CANVAS_COURSE_ID)")
        return False

    print("  ✓ Course data synced to course/")
    return True


def step_12_generate_agents_md(*, course_root: Path, is_subdir: bool, check_only: bool) -> bool:
    """Generate course-specific AGENTS.md stub (v1.6+ subdirectory mode only)."""
    if not is_subdir:
        print("Step 12/14: ⏭  Standalone mode — AGENTS.md generation skipped.")
        return True

    agents_md_path = course_root / "AGENTS.md"

    if agents_md_path.exists():
        print(f"Step 12/14: ✓ AGENTS.md exists at {agents_md_path} — skipping.")
        return True

    if check_only:
        print("Step 12/14: would generate course-specific AGENTS.md")
        return True

    # Create stub that references canvas-toolbox/AGENTS.md
    stub_content = f"""---
name: {course_root.name}-context
description: Course-specific context for {course_root.name}
---

# {course_root.name}

This course uses canvas-toolbox for Canvas course management.

## Toolkit Documentation

See [canvas-toolbox/AGENTS.md](canvas-toolbox/AGENTS.md) for:
- Available tools and CLI commands
- Agent knowledge and workflows
- Canvas API patterns

Run all tools from this directory (course root):
```bash
uv run python canvas-toolbox/lib/tools/course_audit.py --help
```

---

## Quality Discipline (Toyota Production System)

AI agents working on this course follow three core quality principles:

### 1. Genchi Gembutsu (現地現物) - Go and See

**Don't assume, verify with real data:**
- Test with REAL course data, not synthetic fixtures
- When uncertain about format, examine actual files
- Verify in Canvas sandbox, don't trust docs alone
- Read actual code before claiming understanding

**Behavioral trigger**: When you catch yourself saying "probably" or "should" → STOP and verify

### 2. Jidoka (自働化) - Built-in Quality / Stop on Defect

**Build quality in, stop when defect detected:**
- Write tests WITH code, not after
- Red tests block progress - fix immediately, don't defer
- Validation runs automatically (not manual step)
- Can't push to Canvas with errors (blocked by design)

**Behavioral trigger**: When you want to say "we'll fix this later" → STOP and fix now

### 3. Poka-yoke (ポカヨケ) - Mistake-Proofing

**Design so mistakes can't happen:**
- Automate validation (no manual steps)
- Use pre-commit hooks to catch errors
- Type hints catch errors at write-time
- Block operations that would create defects

**Behavioral trigger**: When manual verification required → Design it out

**Quality Loop**: Prevent (Poka-yoke) → Detect (Jidoka) → Verify (Genchi Gembutsu)

When you find a defect:
1. **Fix it** (Jidoka - stop and correct)
2. **Verify the fix** (Genchi Gembutsu - test with real data)
3. **Prevent recurrence** (Poka-yoke - add automated check)

---

{GRADING_POINTER_BLOCK}

---

## Course Context

[Add course-specific context here as you work]

**HERMES Learning:** This section grows as you chat with Claude about your course.
- Teaching approach
- Grading workflows
- Course-specific Canvas patterns
- Student cohort notes
"""

    agents_md_path.write_text(stub_content, encoding="utf-8")
    print(f"  ✓ Created AGENTS.md stub at {agents_md_path}")
    print("    This file will grow with HERMES learning as you work with Claude.")
    return True


def step_13_handoffs(*, course_root: Path, is_subdir: bool, with_handoffs: bool, check_only: bool) -> bool:
    """Create handoffs/ directory (opt-in via --with-handoffs, dev/power-user feature)."""
    if not with_handoffs:
        print("Step 13/14: ⏭  --with-handoffs not provided — skipping handoffs/ creation.")
        print("          This is a dev/power-user feature for AI session tracking.")
        return True

    if not is_subdir:
        print("Step 13/14: ⚠  --with-handoffs requires subdirectory mode (course root context).")
        return True

    handoffs_dir = course_root / "handoffs"

    if handoffs_dir.exists():
        print(f"Step 13/14: ✓ handoffs/ exists at {handoffs_dir} — skipping.")
        return True

    if check_only:
        print(f"Step 13/14: would create handoffs/ at {handoffs_dir}")
        return True

    handoffs_dir.mkdir(exist_ok=True)
    readme = handoffs_dir / "README.md"
    readme.write_text("""# Handoffs

AI agent session handoff notes (GITIGNORED).

Each session creates a timestamped markdown file documenting:
- What was accomplished
- Decisions made
- Context for next session

These files are for human review and cross-session continuity.
""", encoding="utf-8")

    print(f"  ✓ Created handoffs/ at {handoffs_dir}")
    return True


def step_14_slash_commands(*, course_root: Path, check_only: bool) -> bool:
    """Copy slash commands from scaffold/.claude/commands/ to course .claude/commands/."""
    target_dir = course_root / ".claude" / "commands"
    scaffold_dir = REPO_ROOT / "scaffold" / ".claude" / "commands"

    # Check if target has expected files (idempotent check)
    expected_files = ["sync.md", "audit.md", "quality-check.md", "blueprint-sync.md",
                      "validate-blueprint.md", "module-settings.md", "tools.md"]

    if target_dir.exists() and all((target_dir / f).exists() for f in expected_files):
        print(f"Step 14/14: ✓ Slash commands exist at {target_dir} — skipping.")
        return True

    if check_only:
        print(f"Step 14/14: would copy slash commands from {scaffold_dir} to {target_dir}")
        return True

    # Create target directory if needed
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy all command files from scaffold
    copied_count = 0
    for cmd_file in scaffold_dir.glob("*.md"):
        shutil.copy2(cmd_file, target_dir / cmd_file.name)
        copied_count += 1

    print(f"  ✓ Copied {copied_count} slash commands to {target_dir}")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash on glyph output

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
    parser.add_argument(
        "--with-rust", action="store_true",
        help="Install Rust toolchain and build high-performance binaries. "
             "Optional in v1.5.x (provides 10-100x speedup for large courses). "
             "Will become required in v2.x.",
    )
    parser.add_argument(
        "--with-handoffs", action="store_true",
        help="Create handoffs/ directory and course-level AGENTS.md for AI session tracking. "
             "Optional: most users don't need this (dev/power-user feature).",
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
        lambda: step_3_env_stub(course_root=COURSE_ROOT, auto_yes=args.yes, check_only=args.check),
        lambda: step_4_uv_sync(auto_yes=args.yes, check_only=args.check),
        lambda: step_5_rust_optional(check_only=args.check, with_rust=args.with_rust),
        lambda: step_6_playwright(
            auto_yes=args.yes, check_only=args.check, skip=args.skip_playwright,
        ),
        lambda: step_7_pre_commit(auto_yes=args.yes, check_only=args.check),
        lambda: step_8_canvas_smoke(cwd=COURSE_ROOT, check_only=args.check),
        lambda: step_9_surface_docs(mode=mode),
        lambda: step_10_gitignore(course_root=COURSE_ROOT, is_subdir=IS_SUBDIRECTORY, check_only=args.check),
        lambda: step_11_canvas_sync(course_root=COURSE_ROOT, is_subdir=IS_SUBDIRECTORY, check_only=args.check),
        lambda: step_12_generate_agents_md(course_root=COURSE_ROOT, is_subdir=IS_SUBDIRECTORY, check_only=args.check),
        lambda: step_13_handoffs(course_root=COURSE_ROOT, is_subdir=IS_SUBDIRECTORY, with_handoffs=args.with_handoffs, check_only=args.check),
        lambda: step_14_slash_commands(course_root=COURSE_ROOT, check_only=args.check),
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

"""Tier 1 unit tests — cb_init pure-logic helpers + ONE tmp-repo integration test.

Source: lib/tools/cb_init.py (Sprint 2 — one-command bootstrap).

Coverage strategy per decision E (a+c):
  - Pure-logic helpers (detect_mode_from_remote, env_stub_content,
    parse_canvas_self_name, stub_is_filled) are unit-tested deterministically.
  - ONE end-to-end integration test runs `cb_init.py --check` against a
    fresh tmp git repo, asserting the full 8-step dry-run prints all
    steps without writing anything.

The subprocess-touching helpers (is_uv_installed, uv_has_python,
is_playwright_chromium_installed, is_pre_commit_installed,
smoke_test_canvas) are deliberately NOT unit-tested — they're thin
wrappers around `shutil.which` / `subprocess.run` / a network call; the
integration test exercises the wiring.
"""
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import cb_init  # noqa: E402
from cb_init import (  # noqa: E402
    detect_mode_from_remote,
    env_stub_content,
    parse_canvas_self_name,
    step_10_gitignore,
    step_11_canvas_sync,
    step_12_generate_agents_md,
    stub_is_filled,
    _install_guardian_hook,
)


# ---------------------------------------------------------------------------
# _install_guardian_hook — must NOT install a hook whose script isn't there
# ---------------------------------------------------------------------------

def test_guardian_hook_skipped_when_no_vendored_toolkit(tmp_path, capsys):
    """Standalone / non-course layout: no `canvas-toolbox/lib/tools/grade_guardian.py`
    under the root, so the hook must be SKIPPED — installing it there is what bricked
    the session (path pointed at a missing script)."""
    _install_guardian_hook(course_root=tmp_path, check_only=False)
    assert not (tmp_path / ".claude" / "settings.json").exists()  # nothing written
    assert "skipped" in capsys.readouterr().out.lower()


def test_guardian_hook_installed_when_vendored_toolkit_present(tmp_path):
    """Course layout: the vendored guardian exists → the hook IS wired in."""
    g = tmp_path / "canvas-toolbox" / "lib" / "tools" / "grade_guardian.py"
    g.parent.mkdir(parents=True)
    g.write_text("# vendored guardian\n", encoding="utf-8")
    _install_guardian_hook(course_root=tmp_path, check_only=False)
    settings = tmp_path / ".claude" / "settings.json"
    assert settings.exists()
    assert "grade_guardian" in settings.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# detect_mode_from_remote
# ---------------------------------------------------------------------------

def test_detect_maintainer_ssh_remote():
    assert detect_mode_from_remote("git@github.com:chaz-clark/canvas-toolbox.git") == "maintainer"


def test_detect_maintainer_https_remote():
    assert detect_mode_from_remote("https://github.com/chaz-clark/canvas-toolbox.git") == "maintainer"


def test_detect_maintainer_no_dot_git_suffix():
    """Some clones don't include the .git suffix on the origin URL."""
    assert detect_mode_from_remote("https://github.com/chaz-clark/canvas-toolbox") == "maintainer"


def test_detect_adopter_when_origin_differs():
    assert detect_mode_from_remote("git@github.com:smithu/ds250-master.git") == "adopter"


def test_detect_adopter_when_remote_empty():
    """No git repo / no origin / git missing → safe default of adopter."""
    assert detect_mode_from_remote("") == "adopter"


def test_detect_adopter_when_fork_uses_different_owner():
    """A fork that's NOT under chaz-clark should be adopter, even though
    the repo name matches."""
    assert detect_mode_from_remote("https://github.com/other-uni/canvas-toolbox.git") == "adopter"


# ---------------------------------------------------------------------------
# env_stub_content + stub_is_filled
# ---------------------------------------------------------------------------

def test_env_stub_lists_required_fields():
    """The stub MUST surface the two required fields by name."""
    stub = env_stub_content()
    assert "CANVAS_API_TOKEN=" in stub
    assert "CANVAS_BASE_URL=" in stub


@pytest.mark.parametrize("key", [
    "CANVAS_TIMEZONE",       # DST-correct .imscc date shifting
    "CANVAS_MODE",           # online/offline — the no-token path
    "MASTER_COURSE_ID",      # blueprint_sync needs it
    "BLUEPRINT_COURSE_ID",
    "PROTECTED_COURSE_IDS",  # course ids the toolkit must never write to
])
def test_env_stub_carries_keys_the_hardcoded_copy_had_lost(key):
    """cb_init used to write its own hardcoded stub, four keys behind
    .env.example. An operator never saw these, so never set them — and a
    missing CANVAS_TIMEZONE silently shifts due dates across a DST boundary.
    Reading the template at write-time is what keeps them from drifting."""
    assert key in env_stub_content()


def test_env_stub_reads_the_injected_template(tmp_path):
    t = tmp_path / ".env.example"
    t.write_text("CANVAS_API_TOKEN=\nSENTINEL_KEY=\n", encoding="utf-8")
    assert "SENTINEL_KEY=" in env_stub_content(t)


def test_env_stub_falls_back_when_template_is_missing(tmp_path):
    """A partial vendored checkout must still yield a usable .env — halting
    for two required values beats crashing during setup."""
    stub = env_stub_content(tmp_path / "does-not-exist.example")
    assert "CANVAS_API_TOKEN=" in stub
    assert "CANVAS_BASE_URL=" in stub


def test_env_stub_falls_back_when_template_is_empty(tmp_path):
    t = tmp_path / ".env.example"
    t.write_text("   \n\n", encoding="utf-8")
    assert "CANVAS_API_TOKEN=" in env_stub_content(t)


def test_scaffold_template_is_the_same_file_not_a_copy():
    """Two .env.example files drifted apart once already — scaffold's had
    PROTECTED_COURSE_IDS, root's had CANVAS_TIMEZONE/CANVAS_MODE, and cb_init
    shipped a third version thinner than both. One file, two names."""
    root = Path(__file__).resolve().parent.parent.parent
    a = (root / ".env.example").read_text(encoding="utf-8")
    b = (root / "scaffold" / ".env.example").read_text(encoding="utf-8")
    assert a == b


def test_stub_is_filled_false_for_fresh_stub():
    """A freshly-written stub has both required values blank → NOT filled."""
    assert stub_is_filled(env_stub_content()) is False


def test_stub_is_filled_true_when_both_required_set():
    """Only TOKEN + BASE_URL are required (COURSE_ID is optional —
    tools accept --course-id per-command)."""
    text = (
        "CANVAS_API_TOKEN=abc123\n"
        "CANVAS_BASE_URL=https://institution.instructure.com\n"
    )
    assert stub_is_filled(text) is True


def test_stub_is_filled_false_when_base_url_missing():
    text = "CANVAS_API_TOKEN=abc123\n"
    assert stub_is_filled(text) is False


def test_stub_is_filled_false_when_token_missing():
    text = "CANVAS_BASE_URL=https://institution.instructure.com\n"
    assert stub_is_filled(text) is False


def test_stub_is_filled_true_even_without_course_id():
    """The real-world case: an adopter who works across multiple courses
    has TOKEN + BASE_URL + SANDBOX_ID set but leaves COURSE_ID blank,
    passing it per-command via --course-id."""
    text = (
        "CANVAS_API_TOKEN=abc123\n"
        "CANVAS_BASE_URL=https://institution.instructure.com\n"
        "CANVAS_SANDBOX_ID=999\n"
    )
    assert stub_is_filled(text) is True


def test_stub_is_filled_ignores_comment_lines():
    """Lines starting with # should not be treated as set values, even if
    they're a commented-out version of the key."""
    text = (
        "# CANVAS_API_TOKEN=fake-from-comment\n"
        "CANVAS_API_TOKEN=\n"
        "CANVAS_BASE_URL=https://...\n"
    )
    # Actual CANVAS_API_TOKEN is blank, so not filled.
    assert stub_is_filled(text) is False


def test_stub_is_filled_strips_surrounding_quotes():
    text = (
        'CANVAS_API_TOKEN="abc"\n'
        "CANVAS_BASE_URL='https://...'\n"
    )
    assert stub_is_filled(text) is True


def test_stub_is_filled_ignores_unrelated_keys():
    """Other keys (FOO=bar, CANVAS_SANDBOX_ID, GH_TOKEN) don't affect the check."""
    text = (
        "FOO=bar\n"
        "GH_TOKEN=ghp_xxx\n"
        "CANVAS_SANDBOX_ID=999\n"
        "CANVAS_API_TOKEN=token\n"
        "CANVAS_BASE_URL=url\n"
    )
    assert stub_is_filled(text) is True


# ---------------------------------------------------------------------------
# parse_canvas_self_name
# ---------------------------------------------------------------------------

def test_parse_canvas_self_returns_name():
    assert parse_canvas_self_name({"name": "Alice Smith"}) == "Alice Smith"


def test_parse_canvas_self_falls_back_to_short_name():
    """When `name` is absent, fall back to `short_name`."""
    assert parse_canvas_self_name({"short_name": "Alice"}) == "Alice"


def test_parse_canvas_self_handles_missing_fields():
    assert parse_canvas_self_name({}) == "(no name)"


def test_parse_canvas_self_handles_non_dict():
    """Defensive: pass garbage and don't crash."""
    assert parse_canvas_self_name(None) == "(no name)"
    assert parse_canvas_self_name([]) == "(no name)"
    assert parse_canvas_self_name("string") == "(no name)"


# ---------------------------------------------------------------------------
# Integration test — --check mode against a fresh tmp git repo
# ---------------------------------------------------------------------------

def test_check_mode_against_tmp_repo(tmp_path):
    """End-to-end smoke: cb_init.py --check --mode adopter --skip-playwright
    against a fresh git repo. Asserts ALL 13 step labels print + no .env
    is written. Catches "I forgot to wire step X into the dispatch."

    --check mode is designed to continue past failures so the operator
    sees the full plan; the dispatch loop honors that. This test relies
    on that behavior.
    """
    # Set up a fresh git repo (no origin, no commits).
    r = subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"git init failed: {r.stderr}"

    cb_init_path = _TOOLS_DIR / "cb_init.py"
    result = subprocess.run(
        [sys.executable, str(cb_init_path),
         "--check", "--mode", "adopter", "--skip-playwright", "--yes"],
        cwd=tmp_path,
        capture_output=True, text=True, timeout=30,
    )
    out = result.stdout + result.stderr

    # Every step label must appear (catches the dispatch-wiring class of bugs).
    # Derive the total from the output rather than hardcoding it, so adding a
    # cb-init step never silently breaks this test again (it went 13→14 in
    # v1.6.1 and this assertion wasn't updated).
    import re
    totals = set(re.findall(r"Step \d+/(\d+):", out))
    assert len(totals) == 1, f"inconsistent step totals {totals} in output:\n{out}"
    total = int(totals.pop())
    for i in range(1, total + 1):
        assert f"Step {i}/{total}:" in out, (
            f"step {i} missing from --check output. Full output:\n{out}"
        )

    # In --check mode, no .env should be written
    assert not (tmp_path / ".env").exists(), (
        ".env was written despite --check mode"
    )

    # --check should print the mode + the cwd
    assert "adopter" in out
    assert "--check" in out

    # Exit code: 0 since --check keeps going past would-do-work steps
    assert result.returncode == 0, (
        f"cb-init --check should exit 0; got {result.returncode}\n{out}"
    )


# ---------------------------------------------------------------------------
# Credentials: don't stop a setup to ask for something the machine already has,
# and never address the halt message to a human at a terminal.
# ---------------------------------------------------------------------------

def test_credentials_resolve_when_both_present(monkeypatch):
    monkeypatch.setenv("CANVAS_API_TOKEN", "tok")
    monkeypatch.setenv("CANVAS_BASE_URL", "https://x.instructure.com")
    resolved, where = cb_init.credentials_already_resolve()
    assert resolved is True
    assert where


def test_credentials_do_not_resolve_when_token_missing(monkeypatch, tmp_path):
    """GLOBAL_CONFIG is repointed at an empty path — without that this reads the
    DEVELOPER's real ~/.canvas/config and passes for the wrong reason (the same
    hazard test_env_loader.py documents)."""
    import _env_loader
    monkeypatch.setattr(_env_loader, "GLOBAL_CONFIG", tmp_path / "nope")
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    monkeypatch.setenv("CANVAS_BASE_URL", "https://x.instructure.com")
    assert cb_init.credentials_already_resolve()[0] is False


def test_step3_is_a_noop_when_credentials_already_resolve(tmp_path, monkeypatch, capsys):
    """#288 put the token in ~/.canvas/config so it's set ONCE for N courses.
    Setting up a SECOND course must not halt to demand it again."""
    monkeypatch.setenv("CANVAS_API_TOKEN", "tok")
    monkeypatch.setenv("CANVAS_BASE_URL", "https://x.instructure.com")
    assert cb_init.step_3_env_stub(
        course_root=tmp_path, auto_yes=True, check_only=False) is True
    assert not (tmp_path / ".env").exists()          # nothing written
    assert "no .env needed" in capsys.readouterr().out


def test_credential_next_step_is_addressed_to_the_agent(capsys):
    """AGENTS.md: never hand an instructor a terminal command, an editor, or a
    file to fill in. cb_init is run BY an agent on their behalf, so the halt
    message has to tell the AGENT what to do — it used to say 'edit it —
    VS Code / vim / nano', which the agent relayed verbatim."""
    cb_init._print_credential_next_step()
    out = capsys.readouterr().out
    assert "FOR THE AGENT" in out
    assert "ASK the instructor IN CHAT" in out
    assert "WRITE those values into the .env yourself" in out
    for banned in ("vim", "nano", "open a terminal", "copy-paste"):
        assert banned not in out.lower(), f"still tells the human to {banned!r}"


@pytest.mark.parametrize("banned", ["vim", "nano", "copy-paste", "copy and paste"])
def test_no_cb_init_message_sends_the_instructor_to_a_terminal(banned):
    """Guard against the whole class: a reviewer adding a friendly 'just run
    this in your terminal' line reintroduces the No-Go the audience rule bans."""
    src = (Path(__file__).resolve().parent.parent / "tools" / "cb_init.py").read_text(
        encoding="utf-8")
    printed = "\n".join(ln for ln in src.splitlines() if "print(" in ln)
    assert banned not in printed.lower(), f"cb_init prints {banned!r} at the operator"


# ---------------------------------------------------------------------------
# steps 10/11/12 — mode-based gating (#317 follow-up)
#
# WHY THIS EXISTS: these used to gate on `is_subdir` alone, which meant a v2
# FLAT adopter ("not nested" but a real course) was treated exactly like the
# maintainer's own standalone toolkit dev repo — silently getting no course
# .gitignore, no Canvas sync, no course AGENTS.md content at all. `mode`
# (from detect_mode_from_remote) is the actual signal for "is this the
# maintainer's own repo"; these three steps now gate on that instead.
# ---------------------------------------------------------------------------

def test_step_10_skips_for_maintainer_regardless_of_is_subdir(tmp_path, capsys):
    for is_subdir in (True, False):
        ok = step_10_gitignore(course_root=tmp_path, is_subdir=is_subdir,
                               mode="maintainer", check_only=False)
        assert ok and not (tmp_path / ".gitignore").exists()
        assert "Maintainer mode" in capsys.readouterr().out


def test_step_10_runs_for_flat_adopter_not_just_nested(tmp_path):
    """The bug: flat ("not nested") used to be treated as standalone/skip."""
    ok = step_10_gitignore(course_root=tmp_path, is_subdir=False, mode="adopter",
                           check_only=False)
    assert ok
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "course/" in content and "grading/" in content
    assert "canvas-toolbox/" not in content  # no such folder in flat layout


def test_step_10_nested_adopter_still_ignores_the_nested_folder(tmp_path):
    ok = step_10_gitignore(course_root=tmp_path, is_subdir=True, mode="adopter",
                           check_only=False)
    assert ok
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "canvas-toolbox/" in content


def test_step_11_skips_for_maintainer_only(capsys):
    ok = step_11_canvas_sync(course_root=Path("/nonexistent"), is_subdir=False,
                             mode="maintainer", check_only=False)
    assert ok
    assert "Maintainer mode" in capsys.readouterr().out


def test_step_12_skips_for_maintainer(tmp_path, capsys):
    ok = step_12_generate_agents_md(course_root=tmp_path, is_subdir=False,
                                    mode="maintainer", check_only=False)
    assert ok and not (tmp_path / "AGENTS.md").exists()
    assert "Maintainer mode" in capsys.readouterr().out


def test_step_12_flat_adopter_confirms_cb_flatten_already_wrote_it(tmp_path, capsys):
    """Flat: cb_flatten.py owns AGENTS.md (constitution + course content merged
    together). step_12 must not try to write a second, competing stub."""
    (tmp_path / "AGENTS.md").write_text("constitution + course half", encoding="utf-8")
    ok = step_12_generate_agents_md(course_root=tmp_path, is_subdir=False,
                                    mode="adopter", check_only=False)
    assert ok
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "constitution + course half"
    assert "written by cb_flatten.py" in capsys.readouterr().out


def test_step_12_flat_adopter_missing_agents_md_tells_operator_to_run_cb_flatten(tmp_path, capsys):
    ok = step_12_generate_agents_md(course_root=tmp_path, is_subdir=False,
                                    mode="adopter", check_only=False)
    assert not ok
    assert "cb_flatten.py" in capsys.readouterr().out


def test_step_12_nested_adopter_writes_a_stub_with_the_shared_course_content(tmp_path):
    ok = step_12_generate_agents_md(course_root=tmp_path, is_subdir=True,
                                    mode="adopter", check_only=False)
    assert ok
    stub = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Toyota Production System" in stub
    assert "HERMES Learning" in stub
    assert "canvas-toolbox/AGENTS.md" in stub  # nested still points at the toolkit's own


# ---------------------------------------------------------------------------
# main() mode resolution — auto-detection must be authoritative by default
# (regression caught in code review, #345)
#
# Steps 10-12 now gate real writes on `mode` (fixing the is_subdir
# conflation bug — see step_10's docstring), but `mode` was still resolving
# to args.mode's old hardcoded default ("adopter") whenever no --mode flag
# was passed. Auto-detection was computed correctly; it just was never made
# authoritative. Running cb_init.py with no flags in canvas-toolbox's OWN
# checkout silently ran adopter steps (Canvas sync, course AGENTS.md, course
# .gitignore) against the toolkit's own repo.
# ---------------------------------------------------------------------------

def _run_cb_init_check(tmp_path, origin: str | None, extra: list[str] | None = None):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    if origin:
        subprocess.run(["git", "remote", "add", "origin", origin], cwd=tmp_path, check=True)
    cb_init_path = _TOOLS_DIR / "cb_init.py"
    result = subprocess.run(
        [sys.executable, str(cb_init_path), "--check", "--skip-playwright", "--yes",
         *(extra or [])],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    return result.stdout + result.stderr


def test_no_mode_flag_in_maintainer_checkout_stays_maintainer(tmp_path):
    """The exact regression: no --mode flag, origin is chaz-clark/canvas-toolbox
    -> must resolve to maintainer and skip the adopter-only steps, not silently
    run Canvas sync / course AGENTS.md generation against the toolkit's own repo."""
    out = _run_cb_init_check(tmp_path, "https://github.com/chaz-clark/canvas-toolbox.git")
    assert "mode:      maintainer (auto-detected)" in out
    assert "Maintainer mode" in out
    assert "canvas-sync --pull" not in out.lower() or "would run" not in out.lower()


def test_no_mode_flag_in_adopter_checkout_stays_adopter(tmp_path):
    out = _run_cb_init_check(tmp_path, "https://github.com/smithu/ds250-master.git")
    assert "mode:      adopter (auto-detected)" in out


def test_explicit_mode_flag_overrides_detection(tmp_path):
    """An explicit --mode still wins over auto-detection — e.g. testing
    adopter-facing behavior from a maintainer checkout on purpose."""
    out = _run_cb_init_check(
        tmp_path, "https://github.com/chaz-clark/canvas-toolbox.git",
        extra=["--mode", "adopter"],
    )
    assert "mode:      adopter (override — auto-detected: maintainer)" in out

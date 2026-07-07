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

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from cb_init import (  # noqa: E402
    detect_mode_from_remote,
    env_stub_content,
    parse_canvas_self_name,
    stub_is_filled,
)


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
    """The stub MUST surface the two required fields by name. COURSE_ID
    + SANDBOX_ID are mentioned but commented out (optional)."""
    stub = env_stub_content()
    assert "CANVAS_API_TOKEN=" in stub
    assert "CANVAS_BASE_URL=" in stub
    # Optional fields should be commented (start with #)
    assert "# CANVAS_COURSE_ID=" in stub
    assert "# CANVAS_SANDBOX_ID=" in stub


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
    against a fresh git repo. Asserts ALL 8 step labels print + no .env
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

    # All 9 step labels must appear (catches the dispatch-wiring class of bugs)
    for i in range(1, 10):
        assert f"Step {i}/9:" in out, (
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

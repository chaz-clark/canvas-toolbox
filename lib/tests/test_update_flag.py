"""Tests — `--update` is the write flag; `--push` is its old spelling until 3.0.0 (#493).

The two spellings must be indistinguishable to the tools (one argparse option,
dest="push", so every gate reading `args.push` sees the same value) and to the
guardian (the review gate must ask on `--update` exactly as on `--push`). A gap
in either is a write that skips a gate.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _update_flag import NOTE, add_update_flag, note_old_flag  # noqa: E402
from grade_guardian import _grader_push_checkpoint, _redirect, ask_reason  # noqa: E402

# Every tool with a Canvas write flag. A new one must use add_update_flag too.
WRITERS = ["blueprint_sync", "canvas_quiz_questions", "canvas_sync", "course_mirror",
           "grader_correct", "grader_letter_comments", "grader_push",
           "grader_push_comments", "grader_standing"]
GP = "uv run python lib/tools/grader_push.py --challenge-dir grading/kc3"


# --- the flag ----------------------------------------------------------------

@pytest.mark.parametrize("kwargs, argv, expected", [
    ({"action": "store_true"}, [], False),
    ({"action": "store_true"}, ["X"], True),
    ({"nargs": "?", "const": "", "metavar": "MODULE"}, ["X"], ""),            # canvas_sync
    ({"nargs": "?", "const": "", "metavar": "MODULE"}, ["X", "sprint-1"], "sprint-1"),
    ({"metavar": "FILE"}, ["X", "q.json"], "q.json"),                         # canvas_quiz_questions
])
def test_both_spellings_give_the_same_value(kwargs, argv, expected):
    for spelling in ("--update", "--push"):
        p = argparse.ArgumentParser()
        add_update_flag(p, **kwargs)
        args = p.parse_args([spelling if a == "X" else a for a in argv])
        assert args.push == expected, spelling
        assert not hasattr(args, "update")


def test_the_old_spelling_prints_one_note(capsys):
    assert note_old_flag(["--push"]) is True
    assert note_old_flag(["--challenge-dir", "d", "--push=sprint-1"]) is True
    assert capsys.readouterr().err == f"{NOTE}\n{NOTE}\n"
    assert NOTE == "`--push` is now `--update`; `--push` will be removed in 3.0.0."


def test_the_new_spelling_prints_nothing(capsys):
    assert note_old_flag(["--update"]) is False
    assert note_old_flag(["--update", "push"]) is False      # a module named "push"
    assert note_old_flag([]) is False
    assert capsys.readouterr().err == ""


# --- every writer uses it ----------------------------------------------------

@pytest.mark.parametrize("tool", WRITERS)
def test_every_writer_uses_the_shared_flag(tool):
    src = (_TOOLS_DIR / f"{tool}.py").read_text(encoding="utf-8")
    assert not re.search(r"""add_argument\(\s*["']--push["']""", src), \
        f"{tool}.py defines --push itself; use add_update_flag"
    assert "add_update_flag(" in src
    assert re.search(r"args = \w+\.parse_args\(\)\n    note_old_flag\(\)\n", src), \
        f"{tool}.py must call note_old_flag() right after parse_args()"


def test_no_other_tool_defines_a_push_flag():
    for path in sorted(_TOOLS_DIR.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"""add_argument\(\s*["']--push["']""", src), path.name


@pytest.mark.parametrize("tool", WRITERS)
def test_help_shows_update_first(tool):
    r = subprocess.run([sys.executable, str(_TOOLS_DIR / f"{tool}.py"), "--help"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert re.search(r"--update(?: \[?\w+\]?)?, --push", r.stdout), r.stdout


# --- the guardian ------------------------------------------------------------

@pytest.mark.parametrize("flag", ["--update", "--push"])
def test_guardian_asks_on_both_spellings(flag):
    for cmd, kind in [
        (f"{GP} {flag}", "push"),
        (f"{GP} --comments-only {flag}", "push"),
        (f"{GP} --roster-csv ns.csv --assignment-id 5 {flag}", "push"),
        (f"{GP} --mark-reviewed {flag}", "push"),
        (f"uv run python lib/tools/grader_correct.py --assignment-id 5 {flag}", "correct"),
    ]:
        assert _grader_push_checkpoint(cmd) == kind, cmd
        assert ask_reason("Bash", {"command": cmd}) is not None, cmd


@pytest.mark.parametrize("flag", ["--update", "--push"])
def test_guardian_skips_the_same_non_ai_paths_on_both_spellings(flag):
    for extra in ("--grade-only", "--test-user 1234", "--retract"):
        assert ask_reason("Bash", {"command": f"{GP} {flag} {extra}"}) is None, extra
    assert _grader_push_checkpoint("uv run python lib/tools/grader_correct.py") is None


def test_guardian_ignores_update_outside_the_grading_writers():
    assert ask_reason("Bash", {"command": "uv run python lib/tools/canvas_sync.py --update"}) is None
    assert ask_reason("Bash", {"command": "uv run python lib/tools/cb_update.py --pull --apply"}) is None


def test_hook_asks_on_update_end_to_end():
    r = subprocess.run([sys.executable, str(_TOOLS_DIR / "grade_guardian.py")],
                       input=json.dumps({"tool_name": "Bash",
                                         "tool_input": {"command": f"{GP} --update"}}),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_the_redirect_teaches_the_new_spelling():
    msg = _redirect("a hand-written Canvas write")
    assert "--update" in msg and "--push" not in msg

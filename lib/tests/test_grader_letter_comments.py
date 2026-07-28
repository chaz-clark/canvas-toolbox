"""Unit tests — grader_letter_comments (sanctioned End-Letter comment-only push).

The safety-critical logic: never comment on the wrong (or no) student, never post an
empty comment, never touch a grade. These pin the resolution + row loading.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_letter_comments import load_comment_rows, plan_comments  # noqa: E402

INDEX = {"1001": 1001, "1002": 1002, "dup": None}


def test_load_reads_key_and_comment_skips_blank_comment(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("user_id,comment\n1001,Final grade B+. Nice work.\n1002,\n",
                 encoding="utf-8")
    rows, key_col, com_col = load_comment_rows(str(p), None, None)
    assert key_col == "user_id" and com_col == "comment"
    assert rows == [("1001", "Final grade B+. Nice work.")]  # blank-comment row dropped


def test_plan_resolves_and_hard_fails_on_unmatched():
    plan, problems = plan_comments([("9999", "x")], INDEX)
    assert plan == [] and problems and "no enrolled student" in problems[0]


def test_plan_hard_fails_on_ambiguous_key():
    plan, problems = plan_comments([("dup", "x")], INDEX)
    assert plan == [] and "more than one" in problems[0]


def test_plan_resolves_valid_rows():
    plan, problems = plan_comments([("1001", "hi"), ("1002", "yo")], INDEX)
    assert problems == []
    assert [(p["uid"], p["comment"]) for p in plan] == [(1001, "hi"), (1002, "yo")]


def test_missing_comment_column_is_fatal(tmp_path):
    import pytest
    p = tmp_path / "c.csv"
    p.write_text("user_id,grade\n1001,B\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_comment_rows(str(p), None, None)

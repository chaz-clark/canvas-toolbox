"""Unit tests — grader_standing planning/resolution (issue #242).

This tool writes to a column that is often weighted 100% of the grade, so the
guards that must never silently fail are the ones under test: a CSV key that
matches no student (or two), a grade out of bounds, and a big score drop (the
symptom of a shifted CSV) must all be caught BEFORE any write.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_standing import (  # noqa: E402
    _pick_column,
    load_standing_rows,
    plan_writes,
)


# --- _pick_column: auto-detect, override, case-insensitivity ---------------

def test_pick_column_autodetects_first_candidate():
    assert _pick_column(["name", "user_id", "grade"], ("user_id", "id"), None) == "user_id"


def test_pick_column_is_case_insensitive():
    assert _pick_column(["User_ID", "Grade"], ("user_id",), None) == "User_ID"


def test_pick_column_honors_override():
    assert _pick_column(["a", "b"], ("a",), "b") == "b"


def test_pick_column_override_missing_is_fatal():
    import pytest
    with pytest.raises(SystemExit):
        _pick_column(["a", "b"], ("a",), "zzz")


def test_pick_column_returns_none_when_absent():
    assert _pick_column(["foo", "bar"], ("user_id",), None) is None


# --- load_standing_rows: reads the two columns, skips blank lines -----------

def test_load_standing_rows_reads_key_and_grade(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("student_id,your_grade,note\n1001,A,ok\n1002,B,\n\n", encoding="utf-8")
    rows, key_col, grade_col = load_standing_rows(str(p), None, None)
    assert key_col == "student_id" and grade_col == "your_grade"
    assert rows == [("1001", "A"), ("1002", "B")]


# --- plan_writes: the safety gates -----------------------------------------

INDEX = {"1001": 1001, "1002": 1002, "dup": None, "l99": 1003}
ACTIVE = {1001, 1002, 1003}


def test_plan_flags_unmatched_key_as_fatal():
    plan, problems = plan_writes([("9999", "90")], INDEX, ACTIVE, {}, 100, 20)
    assert plan == []
    assert any(kind == "unmatched" for kind, _ in problems)


def test_plan_flags_ambiguous_key_as_fatal():
    plan, problems = plan_writes([("dup", "90")], INDEX, ACTIVE, {}, 100, 20)
    assert plan == []
    assert any(kind == "ambiguous" for kind, _ in problems)


def test_plan_flags_out_of_bounds_as_fatal():
    plan, problems = plan_writes([("1001", "150")], INDEX, ACTIVE, {}, 100, 20)
    assert plan == []
    assert any(kind == "out-of-bounds" for kind, _ in problems)


def test_plan_flags_negative_grade_as_fatal():
    _, problems = plan_writes([("1001", "-5")], INDEX, ACTIVE, {}, 100, 20)
    assert any(kind == "out-of-bounds" for kind, _ in problems)


def test_plan_flags_big_drop_as_warning_but_still_plans_write():
    current = {1001: {"grade": "95", "score": 95.0}}
    plan, problems = plan_writes([("1001", "40")], INDEX, ACTIVE, current, 100, 20)
    assert any(kind == "big-drop" for kind, _ in problems)
    assert plan and plan[0]["status"] == "write"  # planned, but caller must gate on the warning


def test_plan_small_change_is_not_a_big_drop():
    current = {1001: {"grade": "95", "score": 95.0}}
    _, problems = plan_writes([("1001", "90")], INDEX, ACTIVE, current, 100, 20)
    assert not any(kind == "big-drop" for kind, _ in problems)


def test_plan_unchanged_value_is_a_noop():
    current = {1001: {"grade": "A", "score": None}}
    plan, problems = plan_writes([("1001", "A")], INDEX, ACTIVE, current, None, 20)
    assert problems == []
    assert plan[0]["status"] == "same"


def test_plan_normal_write_resolves_and_marks_write():
    plan, problems = plan_writes([("l99", "B")], INDEX, ACTIVE, {}, None, 20)
    assert problems == []
    assert plan[0]["uid"] == 1003 and plan[0]["status"] == "write"


def test_plan_marks_inactive_students():
    plan, _ = plan_writes([("1001", "A")], INDEX, {1002}, {}, None, 20)
    assert plan[0]["inactive"] is True  # 1001 not in the active set


# --- integration: main() dry-run, Canvas stubbed, writes NOTHING -----------

import grader_standing as _GS  # noqa: E402


class _Resp:
    def __init__(self, payload, status=200, link=""):
        self._payload = payload
        self.status_code = status
        self.headers = {"Link": link}
        self.text = ""

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_main_dry_run_resolves_sis_keys_and_writes_nothing(tmp_path, monkeypatch, capsys):
    """Drive the whole path: a CSV keyed by SIS/login resolves against the roster,
    the diff renders FERPA-safe (user_id only), and dry-run writes NOTHING —
    requests.put is monkeypatched to explode so any write would fail the test."""
    csv_path = tmp_path / "standing.csv"
    csv_path.write_text("login_id,your_grade\nalice@x.edu,88\nbob@x.edu,92\n", encoding="utf-8")

    monkeypatch.setattr(_GS, "_env_canvas", lambda: ("tok", "407908", "https://x.instructure.com"))

    def fake_get(url, **kw):
        if "/users" in url:
            return _Resp([
                {"id": 501, "login_id": "alice@x.edu", "enrollments": [{"enrollment_state": "active"}]},
                {"id": 502, "login_id": "bob@x.edu", "enrollments": [{"enrollment_state": "active"}]},
            ])
        if url.rstrip("/").endswith(f"/assignments/16958677"):
            return _Resp({"name": "Your Grade", "points_possible": 100})
        return _Resp({})
    monkeypatch.setattr(_GS.requests, "get", fake_get)
    monkeypatch.setattr(_GS, "fetch_submissions", lambda *a, **k: [
        {"user_id": 501, "grade": "80", "score": 80.0},
        {"user_id": 502, "grade": "92", "score": 92.0},
    ])

    def _no_write(*a, **k):
        raise AssertionError("requests.put called during a DRY RUN")
    monkeypatch.setattr(_GS.requests, "put", _no_write)

    rc = _GS.main.__wrapped__ if hasattr(_GS.main, "__wrapped__") else _GS.main
    monkeypatch.setattr(sys, "argv",
                        ["grader_standing.py", "--csv", str(csv_path),
                         "--assignment-id", "16958677", "--course-id", "407908"])
    code = rc()
    out = capsys.readouterr().out
    assert code == 0
    assert "Dry run — nothing written." in out
    assert "user 501: 80 -> 88" in out          # alice: real change shown
    assert "[same ] user 502" in out            # bob: 92 == 92, a no-op
    assert "alice@x.edu" not in out             # FERPA: the login key is never echoed

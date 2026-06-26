"""Tier 1 unit tests — student_late_accommodation pure-logic helpers.

Source: lib/tools/student_late_accommodation.py
  - resolve_user_id_from_master  (CSV lookup, PII-aware)
  - build_override_payload       (override POST body construction)
  - filter_my_overrides          (per-student override filter)

No Canvas API calls. The CSV lookup uses tmp_path fixtures.
"""
import csv
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from student_late_accommodation import (  # noqa: E402
    build_override_payload,
    cutoff_from_days_ago,
    filter_assignments_by_due_from,
    filter_my_overrides,
    resolve_user_id_from_master,
)


# ---------------------------------------------------------------------------
# resolve_user_id_from_master — CSV lookup
# ---------------------------------------------------------------------------

def _write_master(tmp_path: Path, rows: list[dict]) -> Path:
    """Helper to write a small deid master CSV for testing."""
    p = tmp_path / ".deid_master.csv"
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["deid_code", "user_id",
                                            "sortable_name", "withdrawn"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return p


def test_resolve_basic(tmp_path):
    p = _write_master(tmp_path, [
        {"deid_code": "S-95DBB6", "user_id": "173819",
         "sortable_name": "Ahlstrom, Sydney", "withdrawn": "0"},
    ])
    assert resolve_user_id_from_master(p, "S-95DBB6") == 173819


def test_resolve_case_insensitive(tmp_path):
    """Operator can type s-95dbb6 or S-95DBB6 — both work."""
    p = _write_master(tmp_path, [
        {"deid_code": "S-95DBB6", "user_id": "173819",
         "sortable_name": "Ahlstrom, Sydney", "withdrawn": "0"},
    ])
    assert resolve_user_id_from_master(p, "s-95dbb6") == 173819
    assert resolve_user_id_from_master(p, "S-95dbb6") == 173819


def test_resolve_strips_whitespace(tmp_path):
    """Tolerate trailing/leading whitespace from copy-paste."""
    p = _write_master(tmp_path, [
        {"deid_code": "S-95DBB6", "user_id": "173819",
         "sortable_name": "Ahlstrom, Sydney", "withdrawn": "0"},
    ])
    assert resolve_user_id_from_master(p, "  S-95DBB6  ") == 173819


def test_resolve_missing_code_raises_keyerror(tmp_path):
    p = _write_master(tmp_path, [
        {"deid_code": "S-95DBB6", "user_id": "173819",
         "sortable_name": "Ahlstrom, Sydney", "withdrawn": "0"},
    ])
    with pytest.raises(KeyError):
        resolve_user_id_from_master(p, "S-DOESNOTEXIST")


def test_resolve_missing_master_raises_filenotfound(tmp_path):
    """The error must point the operator at build_deid_master.py."""
    nope = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError) as exc_info:
        resolve_user_id_from_master(nope, "S-95DBB6")
    assert "build_deid_master" in str(exc_info.value)


def test_resolve_returns_int_not_str(tmp_path):
    """user_id must be returned as int — Canvas API takes int."""
    p = _write_master(tmp_path, [
        {"deid_code": "S-AAA", "user_id": "42",
         "sortable_name": "Test", "withdrawn": "0"},
    ])
    uid = resolve_user_id_from_master(p, "S-AAA")
    assert isinstance(uid, int)
    assert uid == 42


# ---------------------------------------------------------------------------
# build_override_payload — the POST body builder
# ---------------------------------------------------------------------------

def test_payload_includes_student_id():
    assignment = {"due_at": "2026-04-15T23:59:00Z",
                  "unlock_at": "2026-04-01T00:00:00Z"}
    payload = build_override_payload(assignment, user_id=173819)
    assert payload["assignment_override[student_ids][]"] == 173819


def test_payload_includes_title():
    """The title makes the override identifiable in Canvas's UI."""
    payload = build_override_payload({}, user_id=1)
    assert "Late-work accommodation" in payload["assignment_override[title]"]


def test_payload_keeps_due_at():
    """Critical: the original due_at is preserved → student still sees
    the original deadline in their student-view."""
    assignment = {"due_at": "2026-04-15T23:59:00Z"}
    payload = build_override_payload(assignment, user_id=1)
    assert payload["assignment_override[due_at]"] == "2026-04-15T23:59:00Z"


def test_payload_keeps_unlock_at():
    """The original open date is preserved (student can't start early)."""
    assignment = {"unlock_at": "2026-04-01T00:00:00Z"}
    payload = build_override_payload(assignment, user_id=1)
    assert payload["assignment_override[unlock_at]"] == "2026-04-01T00:00:00Z"


def test_payload_omits_lock_at():
    """THE CORE INVARIANT — lock_at MUST NOT appear in the payload.
    Canvas interprets a missing lock_at as null (no close date), which
    is exactly the accommodation. If lock_at ever bleeds into the payload
    here, students lose late-submission access."""
    assignment = {
        "due_at": "2026-04-15T23:59:00Z",
        "unlock_at": "2026-04-01T00:00:00Z",
        "lock_at": "2026-05-01T23:59:00Z",  # SHOULD be ignored
    }
    payload = build_override_payload(assignment, user_id=1)
    assert "assignment_override[lock_at]" not in payload


def test_payload_handles_missing_due_at():
    """Assignments without due dates (e.g. ungraded surveys) still
    accept the override — payload just omits the due_at field."""
    payload = build_override_payload({}, user_id=1)
    assert "assignment_override[due_at]" not in payload
    assert "assignment_override[unlock_at]" not in payload


def test_payload_handles_null_due_at():
    """Canvas returns null for missing due dates (not absent key).
    Defensive: null due_at → don't include it in the payload."""
    payload = build_override_payload({"due_at": None, "unlock_at": None},
                                     user_id=1)
    assert "assignment_override[due_at]" not in payload


def test_payload_custom_title():
    payload = build_override_payload({}, user_id=1, title="Custom title")
    assert payload["assignment_override[title]"] == "Custom title"


# ---------------------------------------------------------------------------
# filter_my_overrides — per-student override filter
# ---------------------------------------------------------------------------

def test_filter_returns_only_target_user_overrides():
    overrides = [
        {"id": 1, "student_ids": [100, 200]},
        {"id": 2, "student_ids": [100]},
        {"id": 3, "student_ids": [300]},
    ]
    mine = filter_my_overrides(overrides, user_id=100)
    assert sorted(o["id"] for o in mine) == [1, 2]


def test_filter_empty_list_returns_empty():
    assert filter_my_overrides([], user_id=100) == []


def test_filter_none_returns_empty():
    """Defensive: Canvas API can return None for empty override lists."""
    assert filter_my_overrides(None, user_id=100) == []


def test_filter_no_student_ids_key():
    """Section overrides have no student_ids — filter should ignore them."""
    overrides = [
        {"id": 1, "course_section_id": 999},  # section override
        {"id": 2, "student_ids": [100]},
    ]
    mine = filter_my_overrides(overrides, user_id=100)
    assert len(mine) == 1
    assert mine[0]["id"] == 2


def test_filter_null_student_ids():
    """Defensive: student_ids: null."""
    overrides = [
        {"id": 1, "student_ids": None},
        {"id": 2, "student_ids": [100]},
    ]
    mine = filter_my_overrides(overrides, user_id=100)
    assert len(mine) == 1


# ---------------------------------------------------------------------------
# cutoff_from_days_ago — rolling-window scope helper
# ---------------------------------------------------------------------------

def test_cutoff_zero_days_returns_today():
    from datetime import date
    today = date(2026, 6, 26)
    assert cutoff_from_days_ago(0, today=today) == "2026-06-26"


def test_cutoff_14_days_ago():
    from datetime import date
    today = date(2026, 6, 26)
    assert cutoff_from_days_ago(14, today=today) == "2026-06-12"


def test_cutoff_crosses_month_boundary():
    from datetime import date
    today = date(2026, 4, 5)
    # 14 days before April 5 is March 22
    assert cutoff_from_days_ago(14, today=today) == "2026-03-22"


def test_cutoff_returns_iso_format():
    """Must be YYYY-MM-DD for the string-prefix comparison to work."""
    from datetime import date
    out = cutoff_from_days_ago(7, today=date(2026, 6, 26))
    assert len(out) == 10
    assert out[4] == "-" and out[7] == "-"


# ---------------------------------------------------------------------------
# filter_assignments_by_due_from — date-scoped filtering
# ---------------------------------------------------------------------------

def _a(aid: int, due: str | None) -> dict:
    return {"id": aid, "due_at": due}


def test_filter_includes_assignment_on_cutoff_date():
    """An assignment due ON the cutoff date is INCLUDED (>=)."""
    assignments = [_a(1, "2026-04-15T23:59:00Z")]
    out = filter_assignments_by_due_from(assignments, "2026-04-15")
    assert len(out) == 1


def test_filter_includes_assignment_after_cutoff():
    assignments = [_a(1, "2026-04-20T23:59:00Z")]
    out = filter_assignments_by_due_from(assignments, "2026-04-15")
    assert len(out) == 1


def test_filter_excludes_assignment_before_cutoff():
    assignments = [_a(1, "2026-04-10T23:59:00Z")]
    out = filter_assignments_by_due_from(assignments, "2026-04-15")
    assert out == []


def test_filter_excludes_null_due_at():
    """Undated assignments aren't part of a date-scoped accommodation."""
    assignments = [_a(1, None), _a(2, "2026-04-20T23:59:00Z")]
    out = filter_assignments_by_due_from(assignments, "2026-04-15")
    assert len(out) == 1
    assert out[0]["id"] == 2


def test_filter_excludes_missing_due_at_key():
    """Defensive: due_at key absent entirely."""
    assignments = [{"id": 1}, _a(2, "2026-04-20T23:59:00Z")]
    out = filter_assignments_by_due_from(assignments, "2026-04-15")
    assert len(out) == 1
    assert out[0]["id"] == 2


def test_filter_mixed_pre_and_post_cutoff():
    """Realistic scenario: 5 assignments spanning the cutoff."""
    assignments = [
        _a(1, "2026-04-01T23:59:00Z"),  # before
        _a(2, "2026-04-10T23:59:00Z"),  # before
        _a(3, "2026-04-15T23:59:00Z"),  # ON (included)
        _a(4, "2026-04-20T23:59:00Z"),  # after
        _a(5, None),                      # null (excluded)
    ]
    out = filter_assignments_by_due_from(assignments, "2026-04-15")
    assert [a["id"] for a in out] == [3, 4]

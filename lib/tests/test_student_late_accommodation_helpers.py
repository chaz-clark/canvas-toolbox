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
    build_shift_payload,
    cutoff_from_days_ago,
    filter_assignments_by_due_from,
    filter_my_overrides,
    skip_reason,
    build_repair_payload,
    existing_override_action,
    resolve_user_id_from_master,
    shift_iso_timestamp,
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
        {"deid_code": "S-68BC40", "user_id": "900001",
         "sortable_name": "Anon, Ada", "withdrawn": "0"},
    ])
    assert resolve_user_id_from_master(p, "S-68BC40") == 900001


def test_resolve_case_insensitive(tmp_path):
    """Operator can type s-68bc40 or S-68BC40 — both work."""
    p = _write_master(tmp_path, [
        {"deid_code": "S-68BC40", "user_id": "900001",
         "sortable_name": "Anon, Ada", "withdrawn": "0"},
    ])
    assert resolve_user_id_from_master(p, "s-68bc40") == 900001
    assert resolve_user_id_from_master(p, "S-68bc40") == 900001


def test_resolve_strips_whitespace(tmp_path):
    """Tolerate trailing/leading whitespace from copy-paste."""
    p = _write_master(tmp_path, [
        {"deid_code": "S-68BC40", "user_id": "900001",
         "sortable_name": "Anon, Ada", "withdrawn": "0"},
    ])
    assert resolve_user_id_from_master(p, "  S-68BC40  ") == 900001


def test_resolve_missing_code_raises_keyerror(tmp_path):
    p = _write_master(tmp_path, [
        {"deid_code": "S-68BC40", "user_id": "900001",
         "sortable_name": "Anon, Ada", "withdrawn": "0"},
    ])
    with pytest.raises(KeyError):
        resolve_user_id_from_master(p, "S-DOESNOTEXIST")


def test_resolve_missing_master_raises_filenotfound(tmp_path):
    """The error must point the operator at build_deid_master.py."""
    nope = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError) as exc_info:
        resolve_user_id_from_master(nope, "S-68BC40")
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
    payload = build_override_payload(assignment, user_id=900001)
    assert payload["assignment_override[student_ids][]"] == 900001


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


def test_payload_sets_until_explicitly_empty():
    """THE CORE INVARIANT (#505) — the Until date (lock_at) is sent, and empty.
    Canvas does NOT read a missing lock_at as "no Until date": a field the
    override leaves out isn't overridden, so the assignment's own Until date
    still locks the student out. Seen with a real student account, 2026-11-26;
    sending it empty is what removes it. The assignment's own Until date must
    never bleed into the payload either."""
    assignment = {
        "due_at": "2026-04-15T23:59:00Z",
        "unlock_at": "2026-04-01T00:00:00Z",
        "lock_at": "2026-05-01T23:59:00Z",  # must NOT be copied
    }
    payload = build_override_payload(assignment, user_id=1)
    assert payload["assignment_override[lock_at]"] == ""
    assert build_override_payload({}, user_id=1)["assignment_override[lock_at]"] == ""


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
# skip_reason — what --remove may delete (#510)
# ---------------------------------------------------------------------------

def test_remove_takes_the_tools_own_late_grace_override():
    assert skip_reason({"id": 1, "title": "Late-work accommodation (no close date)",
                        "student_ids": [100]}, user_id=100) is None


def test_remove_takes_the_tools_own_reschedule_override():
    assert skip_reason({"id": 1, "title": "Test reschedule (date-shifted)",
                        "student_ids": [100]}, user_id=100) is None


def test_remove_skips_an_override_shared_with_other_students():
    """Deleting it would take the dates away from the other students too."""
    why = skip_reason({"id": 1, "title": "Late-work accommodation (no close date)",
                       "student_ids": [100, 200, 300]}, user_id=100)
    assert why and "2 other student" in why


def test_remove_skips_an_override_the_tool_didnt_make():
    """Made by hand in Assign To (or renamed there): the instructor's, not ours."""
    for title in ("1 student", "Extended for Sarah (fake name)", None):
        why = skip_reason({"id": 1, "title": title, "student_ids": [100]}, user_id=100)
        assert why and "not made by this tool" in why


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


# ---------------------------------------------------------------------------
# shift_iso_timestamp — date-shift helper for test_reschedule
# ---------------------------------------------------------------------------

def test_shift_basic_forward():
    """Shift 2026-04-15T23:59:00Z forward 7 days → 2026-04-22T23:59:00Z.
    Time-of-day and Z suffix preserved."""
    assert shift_iso_timestamp("2026-04-15T23:59:00Z", 7) == "2026-04-22T23:59:00Z"


def test_shift_crosses_month_boundary():
    """Shift Apr 28 forward 7 → May 5."""
    assert shift_iso_timestamp("2026-04-28T12:00:00Z", 7) == "2026-05-05T12:00:00Z"


def test_shift_crosses_year_boundary():
    """Shift Dec 30 forward 5 → Jan 4 (next year)."""
    assert shift_iso_timestamp("2026-12-30T09:00:00Z", 5) == "2027-01-04T09:00:00Z"


def test_shift_preserves_timezone_suffix():
    """Shift must preserve whatever timezone Canvas sent (e.g. -06:00)."""
    out = shift_iso_timestamp("2026-04-15T23:59:00-06:00", 3)
    assert out == "2026-04-18T23:59:00-06:00"


def test_shift_none_returns_none():
    """Null timestamps pass through unchanged so callers can chain."""
    assert shift_iso_timestamp(None, 7) is None
    assert shift_iso_timestamp("", 7) is None


def test_shift_zero_days_returns_same():
    """Zero days = no shift."""
    assert shift_iso_timestamp("2026-04-15T23:59:00Z", 0) == "2026-04-15T23:59:00Z"


def test_shift_negative_days_goes_backward():
    """Negative days = move backward. Defensive: not the primary use
    case but the helper shouldn't crash."""
    assert shift_iso_timestamp("2026-04-15T23:59:00Z", -2) == "2026-04-13T23:59:00Z"


# ---------------------------------------------------------------------------
# build_shift_payload — POST body for date-shifted overrides
# ---------------------------------------------------------------------------

def test_shift_payload_includes_lock_at_unlike_default():
    """KEY DIFFERENCE from build_override_payload: this payload INCLUDES
    lock_at (shifted). The default override sends lock_at empty (#505)."""
    assignment = {
        "unlock_at": "2026-04-01T00:00:00Z",
        "due_at": "2026-04-15T23:59:00Z",
        "lock_at": "2026-04-22T23:59:00Z",
    }
    payload = build_shift_payload(assignment, user_id=1, days=7)
    assert "assignment_override[lock_at]" in payload
    assert payload["assignment_override[lock_at]"] == "2026-04-29T23:59:00Z"


def test_shift_payload_shifts_all_three_dates():
    assignment = {
        "unlock_at": "2026-04-01T00:00:00Z",
        "due_at": "2026-04-15T23:59:00Z",
        "lock_at": "2026-04-22T23:59:00Z",
    }
    payload = build_shift_payload(assignment, user_id=1, days=7)
    assert payload["assignment_override[unlock_at]"] == "2026-04-08T00:00:00Z"
    assert payload["assignment_override[due_at]"] == "2026-04-22T23:59:00Z"
    assert payload["assignment_override[lock_at]"] == "2026-04-29T23:59:00Z"


def test_shift_payload_includes_student_id_and_title():
    payload = build_shift_payload({}, user_id=900001, days=7)
    assert payload["assignment_override[student_ids][]"] == 900001
    assert "reschedule" in payload["assignment_override[title]"].lower()


def test_shift_payload_omits_missing_dates():
    """If due_at is null, the payload just omits it — doesn't crash."""
    assignment = {"due_at": None, "unlock_at": None, "lock_at": None}
    payload = build_shift_payload(assignment, user_id=1, days=7)
    assert "assignment_override[due_at]" not in payload
    assert "assignment_override[unlock_at]" not in payload
    assert "assignment_override[lock_at]" not in payload


def test_shift_payload_custom_title():
    payload = build_shift_payload({}, user_id=1, days=7,
                                  title="Bereavement reschedule")
    assert payload["assignment_override[title]"] == "Bereavement reschedule"


# ---------------------------------------------------------------------------
# --remove end to end (#510): main() deletes only the tool's own override
# ---------------------------------------------------------------------------

def test_remove_apply_deletes_only_the_tools_own_override(monkeypatch, capsys):
    import student_late_accommodation as sla
    overrides = [
        {"id": 1, "title": "Late-work accommodation (no close date)", "student_ids": [100]},
        {"id": 2, "title": "Late-work accommodation (no close date)", "student_ids": [100, 200]},
        {"id": 3, "title": "Extended for Sarah (fake name)", "student_ids": [100]},
        {"id": 4, "title": "Late-work accommodation (no close date)", "student_ids": [200]},
    ]
    deleted = []
    monkeypatch.setattr(sla, "list_overrides", lambda *a, **k: overrides)
    monkeypatch.setattr(sla, "delete_override", lambda base, cid, aid, oid, tok: deleted.append(oid) or 200)
    monkeypatch.setattr(sla, "_course_guard", lambda *a, **k: None)
    for k, v in {"CANVAS_BASE_URL": "http://127.0.0.1:9", "CANVAS_COURSE_ID": "1",
                 "CANVAS_API_TOKEN": "x"}.items():
        monkeypatch.setenv(k, v)
    argv = ["student_late_accommodation.py", "--user-id", "100", "--assignment-id", "5", "--remove"]
    # Preview first: names what it would remove, sends nothing.
    monkeypatch.setattr(sys, "argv", argv)
    assert sla.main() == 0
    assert deleted == []
    out = capsys.readouterr().out
    assert "would remove override 1 'Late-work accommodation (no close date)' (1 student(s))" in out
    assert "Would remove 1; skipped 2, left in Canvas." in out
    # Then for real.
    monkeypatch.setattr(sys, "argv", argv + ["--apply"])
    assert sla.main() == 0
    assert deleted == [1]
    out = capsys.readouterr().out
    assert "override 2" in out and "1 other student" in out
    assert "override 3" in out and "not made by this tool" in out
    assert "override 4" not in out  # not this student's at all
    assert "Removed 1; skipped 2, left in Canvas." in out


# ---------------------------------------------------------------------------
# #511: repairing late grace given before 2.13.4
# ---------------------------------------------------------------------------

_OLD_LATE = {"id": 7, "title": "Late-work accommodation (no close date)", "student_ids": [100],
             "due_at": "2026-04-15T23:59:00Z", "unlock_at": "2026-04-01T00:00:00Z"}
_OLD_SHIFT = {"id": 8, "title": "Test reschedule (date-shifted)", "student_ids": [100],
              "due_at": "2026-04-22T23:59:00Z", "lock_at": "2026-04-23T23:59:00Z"}


def test_repair_payload_keeps_the_overrides_own_dates_and_empties_until():
    """Canvas drops any overridden date a PUT leaves out, so send them all back."""
    p = build_repair_payload(_OLD_LATE, user_id=100)
    assert p["assignment_override[student_ids][]"] == 100
    assert p["assignment_override[title]"] == "Late-work accommodation (no close date)"
    assert p["assignment_override[due_at]"] == "2026-04-15T23:59:00Z"
    assert p["assignment_override[unlock_at]"] == "2026-04-01T00:00:00Z"
    assert p["assignment_override[lock_at]"] == ""


def test_repair_payload_sends_no_date_the_override_doesnt_have():
    p = build_repair_payload({**_OLD_LATE, "unlock_at": None}, user_id=100)
    assert "assignment_override[unlock_at]" not in p


def test_existing_late_grace_is_repaired_by_late_grace():
    assert existing_override_action(_OLD_LATE, 100, shifting=False) == ("repair", None)


def test_existing_overrides_that_are_skipped():
    cases = [
        (_OLD_LATE, True, "replace"),                                     # reschedule over late grace
        (_OLD_SHIFT, False, "replace"),                                   # late grace over a reschedule
        (_OLD_SHIFT, True, "twice"),                                      # reschedule again
        ({**_OLD_LATE, "student_ids": [100, 200]}, False, "other student"),  # shared
        ({**_OLD_LATE, "title": "1 student"}, False, "not made by this tool"),  # hand-made
    ]
    for override, shifting, words in cases:
        action, why = existing_override_action(override, 100, shifting=shifting)
        assert action == "skip" and words in why, (override["title"], shifting, why)


def _run_add(monkeypatch, capsys, existing, extra=()):
    import student_late_accommodation as sla
    sent = []
    monkeypatch.setattr(sla, "_course_guard", lambda *a, **k: None)
    monkeypatch.setattr(sla, "fetch_assignment", lambda *a, **k: {"id": 5, "due_at": "2026-04-15T23:59:00Z"})
    monkeypatch.setattr(sla, "post_override", lambda *a, **k: (400, {"errors": {"assignment_override_students": "taken"}}))
    monkeypatch.setattr(sla, "list_overrides", lambda *a, **k: existing)
    monkeypatch.setattr(sla, "put_override", lambda base, cid, aid, oid, payload, tok: sent.append((oid, payload)) or (200, {"id": oid}))
    for k, v in {"CANVAS_BASE_URL": "http://127.0.0.1:9", "CANVAS_COURSE_ID": "1", "CANVAS_API_TOKEN": "x"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "argv", ["student_late_accommodation.py", "--user-id", "100",
                                      "--assignment-id", "5", "--apply", *extra])
    code = sla.main()
    captured = capsys.readouterr()
    return code, sent, captured.out, captured.err


def test_apply_repairs_the_tools_old_late_grace(monkeypatch, capsys):
    code, sent, out, err = _run_add(monkeypatch, capsys, [_OLD_LATE])
    assert code == 0 and [oid for oid, _ in sent] == [7]
    assert sent[0][1]["assignment_override[lock_at]"] == ""
    assert "Until date removed" in out and "Re-run" not in err


def test_apply_leaves_a_shared_override_alone(monkeypatch, capsys):
    code, sent, out, err = _run_add(monkeypatch, capsys, [{**_OLD_LATE, "student_ids": [100, 200]}])
    assert code == 0 and sent == []
    assert "[SKIP]" in out and "Nothing sent" in out and "Re-run" not in err


def test_apply_does_not_reschedule_twice(monkeypatch, capsys):
    code, sent, out, err = _run_add(monkeypatch, capsys, [_OLD_SHIFT], extra=("--shift-by-days", "7"))
    assert code == 0 and sent == [] and "twice" in out


def test_apply_with_no_existing_override_still_fails(monkeypatch, capsys):
    code, sent, out, err = _run_add(monkeypatch, capsys, [])
    assert code == 1 and sent == [] and "failed" in err

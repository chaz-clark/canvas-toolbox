"""Tests — warn when the student's module will still lock them out (#508).

A module that opens later wins over a student's earlier Available from, and a
module whose prerequisites the student hasn't finished stays locked, whatever
the assignment's override says (lesson L37). Canvas has no per-student dates on
a module: a module override takes only who, never when. So the tool can only
say so, before it writes.

Module shapes are from GET /courses/:id/modules?student_id=…&include[]=items on
a hosted sandbox (2026-11-26), with ids replaced by fake ones. A Classic Quiz
sits in its module as type "Quiz" with its quiz id, not its assignment id.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import student_late_accommodation as sla  # noqa: E402
from student_late_accommodation import module_blocks  # noqa: E402

NOW = "2026-11-26T12:00:00Z"
OPENS_LATER = {"id": 3, "name": "Week 14: Coding Challenge", "state": "locked",
               "unlock_at": "2026-12-05T07:00:00Z", "prerequisite_module_ids": [2],
               "items": [{"type": "Assignment", "content_id": 501},
                         {"type": "Quiz", "content_id": 801}]}
NEEDS_PREREQ = {"id": 2, "name": "Week 13: Portfolio", "state": "locked",
                "unlock_at": "2026-11-20T07:00:00Z", "prerequisite_module_ids": [1],
                "items": [{"type": "Assignment", "content_id": 502}]}
DONE = {"id": 1, "name": "Week 12: Joins", "state": "completed", "unlock_at": None,
        "prerequisite_module_ids": [], "items": [{"type": "Assignment", "content_id": 503}]}
MODULES = [DONE, NEEDS_PREREQ, OPENS_LATER]


def test_earlier_available_from_than_the_module_is_flagged():
    why = module_blocks(MODULES, {"id": 501}, new_available_from="2026-11-25T07:00:00Z", now=NOW)
    assert len(why) == 1 and "Week 14: Coding Challenge" in why[0] and "2026-12-05" in why[0]


def test_a_classic_quiz_is_found_by_its_quiz_id():
    why = module_blocks(MODULES, {"id": 999, "quiz_id": 801}, new_available_from="2026-11-25T07:00:00Z", now=NOW)
    assert len(why) == 1 and "Week 14" in why[0]


def test_a_module_that_opens_first_is_not_flagged():
    """Rescheduled later than the module opens: nothing blocks the change."""
    assert module_blocks(MODULES, {"id": 501}, new_available_from="2026-12-10T07:00:00Z", now=NOW) == []


def test_late_grace_isnt_flagged_for_a_module_that_simply_opens_later():
    """Every future week is locked; late grace there takes effect when it opens."""
    assert module_blocks(MODULES, {"id": 501}, new_available_from=None, now=NOW) == []


def test_unfinished_prerequisites_are_flagged_for_any_change():
    why = module_blocks(MODULES, {"id": 502}, new_available_from=None, now=NOW)
    assert len(why) == 1 and "Week 13: Portfolio" in why[0] and "Week 12: Joins" in why[0]


def test_open_or_finished_modules_and_other_items_are_not_flagged():
    assert module_blocks(MODULES, {"id": 503}, new_available_from=None, now=NOW) == []
    assert module_blocks(MODULES, {"id": 777}, new_available_from="2026-11-25T07:00:00Z", now=NOW) == []


def _run(monkeypatch, capsys, argv, modules, assignment):
    monkeypatch.setattr(sla, "_course_guard", lambda *a, **k: None)
    monkeypatch.setattr(sla, "fetch_assignment", lambda *a, **k: assignment)
    monkeypatch.setattr(sla, "fetch_student_modules", lambda *a, **k: modules)
    posted = []
    monkeypatch.setattr(sla, "post_override", lambda *a, **k: posted.append(a[2]) or (201, {"id": 1}))
    for k, v in {"CANVAS_BASE_URL": "http://127.0.0.1:9", "CANVAS_COURSE_ID": "1", "CANVAS_API_TOKEN": "x"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "argv", ["student_late_accommodation.py", "--user-id", "100", *argv])
    code = sla.main()
    return code, posted, capsys.readouterr().out


def test_preview_warns_and_apply_still_writes(monkeypatch, capsys):
    asg = {"id": 501, "unlock_at": "2026-12-05T07:00:00Z", "due_at": "2026-12-17T06:59:00Z",
           "lock_at": "2026-12-17T06:59:00Z"}
    code, posted, out = _run(monkeypatch, capsys, ["--assignment-id", "501", "--shift-by-days", "-10"],
                             MODULES, asg)
    assert code == 0 and posted == [] and "[WARN] 1 assignment(s) (501)" in out and "Lock until" in out
    code, posted, out = _run(monkeypatch, capsys, ["--assignment-id", "501", "--shift-by-days", "-10", "--apply"],
                             MODULES, asg)
    assert code == 0 and posted == [501] and "[WARN] 1 assignment(s) (501)" in out


def test_a_module_read_failure_doesnt_stop_the_change(monkeypatch, capsys):
    import requests

    def boom(*a, **k):
        raise requests.HTTPError("403 Forbidden")
    code, posted, out = _run(monkeypatch, capsys, ["--assignment-id", "501", "--apply"], [], {"id": 501})
    monkeypatch.setattr(sla, "fetch_student_modules", boom)
    monkeypatch.setattr(sys, "argv", ["student_late_accommodation.py", "--user-id", "100",
                                      "--assignment-id", "501", "--apply"])
    assert sla.main() == 0
    assert "couldn't check the student's modules" in capsys.readouterr().out


def test_a_chain_of_locked_modules_is_one_line_each_and_names_what_to_finish(monkeypatch, capsys):
    """A student behind on Week 12 has Week 13 locked; every assignment there shares one line."""
    week13 = {**NEEDS_PREREQ, "prerequisite_module_ids": [1],
              "items": [{"type": "Assignment", "content_id": x} for x in (502, 504, 505)]}
    started = {**DONE, "state": "started"}
    import student_late_accommodation as sla2
    monkeypatch.setattr(sla2, "fetch_published_assignments",
                        lambda *a, **k: [{"id": x, "published": True} for x in (502, 504, 505)])
    code, posted, out = _run(monkeypatch, capsys, ["--all"], [started, week13], {"id": 502})
    assert out.count("  [WARN] ") == 1 and "[WARN] 3 assignment(s) (502, 504, 505)" in out
    assert "needs to finish 'Week 12: Joins' first" in out

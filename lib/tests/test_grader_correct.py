"""Unit tests — grader_correct planning/classification (issue #434).

The guards that must never silently fail: an unmatched/duplicate/Test-Student/
inactive row, an invalid grade, and an overwrite (up OR down) that was not explicitly
allowed must all be caught BEFORE any write.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grade_guardian import ask_reason  # noqa: E402
from grader_correct import (  # noqa: E402
    classify_change,
    comparable_current,
    landed,
    not_landed,
    ledger_key,
    load_correction_rows,
    needs_allow_change,
    plan_corrections,
)

INDEX = {"1": 1, "2": 2, "3": 3, "4": 4, "9": 9, "dup": None}
ACTIVE = {1, 2, 3, 4}
CUR = {1: {"grade": "80"}, 2: {"grade": "50"}, 3: {"grade": None}, 4: {"grade": "90"},
       9: {"grade": "10"}}


def _plan(rows, gtype="points", pp=100):
    return plan_corrections(rows, INDEX, ACTIVE, 9, CUR, gtype, pp)


def test_classify_directions():
    assert classify_change("80", "90") == "up"
    assert classify_change("80", "0") == "down"
    assert classify_change("80", "80.0") == "same"
    assert classify_change(None, "5") == "first"
    assert classify_change("B", "85") == "changed"   # cross-type: can't direction-check


def test_plan_classifies_and_flags_overwrites():
    plan, fatal = _plan([("1", "90", ""), ("2", "0", "n"), ("3", "70", ""), ("4", "90", "")])
    assert fatal == []
    assert [p["change"] for p in plan] == ["up", "down", "first", "same"]
    assert {p["uid"] for p in needs_allow_change(plan)} == {1, 2}   # first/same exempt


def test_fatal_unmatched_ambiguous_duplicate_test_student_inactive_nosub():
    plan, fatal = _plan([("nope", "1", ""), ("dup", "1", ""), ("1", "1", ""),
                         ("1", "2", ""), ("9", "1", ""), ("5", "1", "")])
    # "5" is not in INDEX -> unmatched; add an inactive + no-submission case explicitly
    idx = dict(INDEX, **{"7": 7, "8": 8})
    p2, f2 = plan_corrections([("7", "1", ""), ("8", "1", "")], idx, ACTIVE | {8}, 9,
                              CUR, "points", 100)
    assert any("no enrolled student" in m for m in fatal)
    assert any("more than one" in m for m in fatal)
    assert any("more than once" in m for m in fatal)
    assert any("Test Student" in m for m in fatal)
    assert any("not active" in m for m in f2)
    assert any("no submission record" in m for m in f2)


def test_invalid_grades_refused():
    _, fatal = _plan([("1", "abc", ""), ("2", "101", ""), ("3", "-1", ""), ("4", "", "")])
    assert len(fatal) == 4
    _, fatal = _plan([("1", "B+", "")], gtype="letter_grade")
    assert fatal == []


def test_load_rows_prefers_new_grade_and_reads_comment(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("user_id,current_grade,new_grade,note\n1,80,90,hello\n", encoding="utf-8")
    rows, kc, gc, cc = load_correction_rows(str(f), None, None, None)
    assert rows == [("1", "90", "hello")] and (kc, gc, cc) == ("user_id", "new_grade", "note")


def test_load_rows_no_comment_column(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("user_id,new_grade\n1,90\n", encoding="utf-8")
    rows, _, _, cc = load_correction_rows(str(f), None, None, None)
    assert rows == [("1", "90", "")] and cc is None


def test_ledger_key_is_whitespace_free():
    assert ledger_key(12) == "user-12" and " " not in ledger_key(12)


def test_guardian_asks_on_correct_push_only():
    push = "uv run python lib/tools/grader_correct.py --csv x.csv --assignment-id 5 --push"
    dry = "uv run python lib/tools/grader_correct.py --csv x.csv --assignment-id 5"
    assert ask_reason("Bash", {"command": push}) is not None
    assert ask_reason("Bash", {"command": dry}) is None


def test_test_student_only_with_explicit_allow():
    cur = dict(CUR)
    plan, fatal = plan_corrections([("9", "20", "")], INDEX, ACTIVE, 9, cur, "points", 100,
                                   allow_test=True)
    assert fatal == [] and plan[0]["uid"] == 9 and plan[0]["change"] == "up"
    _, fatal = plan_corrections([("9", "20", "")], INDEX, ACTIVE, 9, cur, "points", 100)
    assert any("Test Student" in m for m in fatal)


# --- Letter-scheme assignments (2026-11-18): Canvas keeps an entered number as `score`
# and shows `grade` in the assignment's own scheme, so 3.0 comes back as grade "Strong". ---
LETTER_SUB = {"grade": "Strong", "score": 3.0}


def test_readback_on_a_letter_scheme_is_not_a_false_mismatch():
    assert landed(LETTER_SUB, "3.0")            # was reported as MISMATCH ("3.0" vs "Strong")
    assert landed(LETTER_SUB, "3")
    assert not landed({"grade": "Solid", "score": 2.75}, "3.0")   # a write that did not land still fails


def test_readback_unchanged_for_points_percent_and_complete():
    assert landed({"grade": "8", "score": 8.0}, "8")
    assert not landed({"grade": "7", "score": 7.0}, "8")
    assert landed({"grade": "92%", "score": 9.2}, "92%")          # percent: compared with grade, not the points score
    assert landed({"grade": "complete", "score": 1.0}, "complete")


def test_plan_on_a_letter_scheme_shows_the_direction():
    cur = {1: {"grade": "Solid", "score": 2.75}, 2: {"grade": "Strong", "score": 3.0}}
    plan, fatal = plan_corrections([("1", "3.0", ""), ("2", "2.0", "")],
                                   {"1": 1, "2": 2}, {1, 2}, 9, cur, "letter_grade", 4)
    assert not fatal, fatal
    by = {p["uid"]: p for p in plan}
    assert by[1]["change"] == "up" and by[2]["change"] == "down"   # was "changed" for both: a lowering went unlabelled
    assert {p["uid"] for p in needs_allow_change(plan)} == {1, 2}  # an overwrite still needs --allow-change


def test_comparable_current_falls_back_to_grade():
    assert comparable_current({"grade": "B", "score": None}, "3.0") == "B"
    assert comparable_current({"grade": "Strong", "score": 3.0}, "Strong") == "Strong"
    assert comparable_current(None, "3.0") is None


def test_the_readback_after_a_push_names_only_real_mismatches():
    writes = [{"uid": 41, "grade": "3.0"}, {"uid": 42, "grade": "3.0"}, {"uid": 43, "grade": "9"}]
    after = {41: {"grade": "Strong", "score": 3.0}, 42: {"grade": "Solid", "score": 2.75}, 43: {"grade": "9", "score": 9.0}}
    assert not_landed(after, writes, {41, 42, 43}) == [42]


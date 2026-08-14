"""Unit tests — course rebinding (#294).

The dangerous failure here is not "didn't match" — it's "matched the WRONG thing".
A bad remap silently aims every future push, and any grade sync, at a different
assignment, and nothing surfaces until someone spots marks on the wrong item. So the
refusal cases carry as much weight as the success cases.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _course_rebind import (  # noqa: E402
    apply_rebind,
    index_target,
    normalize_title,
    plan_rebind,
    summarize,
)


def _target(*items):
    return index_target(list(items))


def A(title, cid):          # assignment in the target course
    return {"type": "Assignment", "title": title, "canvas_id": cid}


def P(slug, cid, title="P"):  # page in the target course
    return {"type": "Page", "title": title, "page_url": slug, "canvas_id": cid}


# --- matching ---------------------------------------------------------------

def test_assignments_match_on_exact_title():
    tgt = _target(A("Week 1 Lab", 900), A("Week 2 Lab", 901))
    local = {"a1.json": {"type": "Assignment", "title": "Week 1 Lab", "canvas_id": 11}}
    plan = plan_rebind(local, tgt)
    assert plan["matched"] == {"a1.json": (11, 900, "title")}


def test_case_and_whitespace_differences_still_match():
    """A Canvas copy can normalize whitespace; that shouldn't strand an item."""
    tgt = _target(A("Week 1  Lab", 900))
    local = {"a1.json": {"type": "Assignment", "title": "week 1 lab", "canvas_id": 11}}
    assert plan_rebind(local, tgt)["matched"]["a1.json"][2] == "normalized"


def test_pages_match_on_slug_not_title():
    """Pages are addressed by URL slug in Canvas — a real identity, unlike a title."""
    tgt = _target(P("syllabus", 700, title="Course Syllabus"))
    local = {"p.html": {"type": "Page", "title": "RENAMED", "page_url": "syllabus",
                        "canvas_id": 5}}
    assert plan_rebind(local, tgt)["matched"]["p.html"] == (5, 700, "slug")


def test_punctuation_is_not_normalized_away():
    """"Quiz 1" and "Quiz 1 (Retake)" are different assessments. Over-eager
    normalization here would silently merge them."""
    assert normalize_title("Quiz 1") != normalize_title("Quiz 1 (Retake)")
    tgt = _target(A("Quiz 1 (Retake)", 900))
    local = {"q.json": {"type": "Assignment", "title": "Quiz 1", "canvas_id": 11}}
    plan = plan_rebind(local, tgt)
    assert plan["matched"] == {} and plan["unmatched"] == ["q.json"]


def test_type_is_part_of_the_key():
    """An Assignment and a Quiz can share a title and are not the same object."""
    tgt = _target({"type": "Quiz", "title": "Midterm", "canvas_id": 800})
    local = {"a.json": {"type": "Assignment", "title": "Midterm", "canvas_id": 11}}
    assert plan_rebind(local, tgt)["unmatched"] == ["a.json"]


# --- refusals (the ones that matter most) -----------------------------------

def test_duplicate_title_in_TARGET_is_refused():
    """Two assignments named the same in the new course: there is no way to tell
    which one this local file is. Guessing sends grades to the wrong item."""
    tgt = _target(A("Lab", 900), A("Lab", 901))
    local = {"a.json": {"type": "Assignment", "title": "Lab", "canvas_id": 11}}
    plan = plan_rebind(local, tgt)
    assert plan["ambiguous"] == ["a.json"] and plan["matched"] == {}


def test_duplicate_title_LOCALLY_is_refused():
    """Two local files with the same title can't both take the one target id — and
    picking either is a coin flip."""
    tgt = _target(A("Lab", 900))
    local = {"a.json": {"type": "Assignment", "title": "Lab", "canvas_id": 11},
             "b.json": {"type": "Assignment", "title": "LAB", "canvas_id": 12}}
    plan = plan_rebind(local, tgt)
    assert sorted(plan["ambiguous"]) == ["a.json", "b.json"]
    assert plan["matched"] == {}


def test_unmatched_items_are_reported_not_dropped():
    """The empty-course case: nothing to match against yet. Every item must be
    accounted for, because a silent drop looks like success."""
    tgt = _target()
    local = {f"a{i}.json": {"type": "Assignment", "title": f"T{i}", "canvas_id": i}
             for i in range(5)}
    plan = plan_rebind(local, tgt)
    assert len(plan["unmatched"]) == 5 and plan["matched"] == {}
    assert "copy the content there first" in summarize(plan)


def test_entries_without_identity_are_skipped_not_guessed():
    tgt = _target(A("Lab", 900))
    local = {"x.json": {"type": "Assignment", "title": "", "canvas_id": 11},
             "y.html": {"type": "Page", "canvas_id": 12}}
    plan = plan_rebind(local, tgt)
    assert sorted(plan["skipped"]) == ["x.json", "y.html"]


# --- applying ---------------------------------------------------------------

def test_apply_repoints_ids_and_course_and_clears_stale_module_ids():
    """Stale module ids belong to the OLD course. Carrying them over is worse than
    dropping them, because a wrong id looks valid."""
    index = {"course_id": "407908", "files": {
        "a.json": {"type": "Assignment", "title": "Lab", "canvas_id": 11,
                   "module_item_id": 555, "module_canvas_id": 777, "hash": "abc"}}}
    plan = plan_rebind(index["files"], _target(A("Lab", 900)))
    out = apply_rebind(index, plan, "422850")
    e = out["files"]["a.json"]
    assert out["course_id"] == "422850"
    assert e["canvas_id"] == 900
    assert "module_item_id" not in e and "module_canvas_id" not in e
    assert e["hash"] == "abc"                       # unrelated fields preserved


def test_apply_does_not_mutate_the_input_index():
    index = {"course_id": "1", "files": {
        "a.json": {"type": "Assignment", "title": "Lab", "canvas_id": 11}}}
    plan = plan_rebind(index["files"], _target(A("Lab", 900)))
    apply_rebind(index, plan, "2")
    assert index["course_id"] == "1"
    assert index["files"]["a.json"]["canvas_id"] == 11


def test_apply_leaves_unmatched_and_ambiguous_entries_untouched():
    index = {"course_id": "1", "files": {
        "ok.json":   {"type": "Assignment", "title": "Lab", "canvas_id": 11},
        "miss.json": {"type": "Assignment", "title": "Gone", "canvas_id": 12}}}
    plan = plan_rebind(index["files"], _target(A("Lab", 900)))
    out = apply_rebind(index, plan, "2")
    assert out["files"]["ok.json"]["canvas_id"] == 900
    assert out["files"]["miss.json"]["canvas_id"] == 12   # untouched, still stale


def test_summary_calls_out_ambiguity_loudly():
    tgt = _target(A("Lab", 900), A("Lab", 901))
    local = {"a.json": {"type": "Assignment", "title": "Lab", "canvas_id": 11}}
    s = summarize(plan_rebind(local, tgt))
    assert "AMBIGUOUS" in s and "refused rather than guessed" in s

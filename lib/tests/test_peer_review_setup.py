"""Unit tests — peer review setup (#331).

The dangerous failures are quiet ones: a rubric whose points do not match its ratings
(Canvas then renders "No details" — seen in the sandbox, L24), a peer rubric that
grades by accident, an assignment created published, and a re-run that duplicates or
edits a live assignment. So payload shape and idempotency carry the weight.
"""
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import peer_review_setup as prs  # noqa: E402
from peer_review_setup import (  # noqa: E402
    build_assignment_form,
    build_rubric_form,
    diff_existing,
    parse_criteria,
)

_SPEC = "Practiced?:yesno;Effort:1-5;Evidence:none|some|strong"


# --- criteria parsing -------------------------------------------------------

def test_yesno_is_one_point_or_zero():
    c = parse_criteria("Prepared?:yesno")[0]
    assert c["ratings"] == [("Yes", 1), ("No", 0)] and c["points"] == 1


def test_numeric_range_runs_high_to_low_with_points_equal_to_value():
    c = parse_criteria("Effort:1-5")[0]
    assert c["ratings"] == [("5", 5), ("4", 4), ("3", 3), ("2", 2), ("1", 1)]
    assert c["points"] == 5


def test_label_list_scores_from_zero_and_lists_best_first():
    c = parse_criteria("Evidence:none|some|strong")[0]
    assert c["ratings"] == [("strong", 2), ("some", 1), ("none", 0)]
    assert c["points"] == 2


def test_criterion_name_may_contain_a_colon():
    assert parse_criteria("Discussion: readings:1-4")[0]["description"] == "Discussion: readings"


def test_criterion_points_always_equal_the_top_rating():
    """A mismatch renders as 'No details' in Canvas (L24)."""
    for c in parse_criteria(_SPEC):
        assert c["points"] == max(p for _, p in c["ratings"])


@pytest.mark.parametrize("bad", [
    "", "  ;  ", "no-type-here", ":yesno", "X:maybe", "X:5-1", "X:3-3",
    "X:1-40", "X:only", "X:a||b", "X:a|a", "A:yesno;A:1-5",
])
def test_bad_specs_are_refused(bad):
    with pytest.raises(ValueError):
        parse_criteria(bad)


# --- payloads ---------------------------------------------------------------

def _assign(**over):
    kw = dict(title="Prep", submission_type="online_text_entry", points=0.0,
              description="", anonymous=True, auto_count=None,
              group_category_id=None, intra_group=False, due_at=None)
    kw.update(over)
    return build_assignment_form(**kw)


def test_assignment_is_created_unpublished_with_peer_review_on():
    f = _assign()
    assert f["assignment[published]"] == "false"
    assert f["assignment[peer_reviews]"] == "true"
    assert f["assignment[anonymous_peer_reviews]"] == "true"
    assert f["assignment[automatic_peer_reviews]"] == "false"
    assert "assignment[peer_review_count]" not in f


def test_auto_mode_sends_the_count():
    f = _assign(auto_count=2)
    assert f["assignment[automatic_peer_reviews]"] == "true"
    assert f["assignment[peer_review_count]"] == "2"


def test_group_fields_only_sent_with_a_group_set():
    assert "assignment[group_category_id]" not in _assign()
    assert "assignment[intra_group_peer_reviews]" not in _assign()
    f = _assign(group_category_id=99, intra_group=True)
    assert f["assignment[group_category_id]"] == "99"
    assert f["assignment[intra_group_peer_reviews]"] == "true"


def test_rubric_never_grades():
    f = build_rubric_form(7, "Prep", parse_criteria(_SPEC))
    assert f["rubric_association[use_for_grading]"] == "false"
    assert f["rubric_association[association_id]"] == "7"
    assert f["rubric[title]"] == "Prep (peer rubric)"
    assert f["rubric[criteria][1][ratings][0][points]"] == "5"
    assert f["rubric[criteria][2][ratings][2][description]"] == "none"


# --- idempotency / existing assignments ------------------------------------

def _existing(**over):
    a = {"id": 1, "peer_reviews": True, "anonymous_peer_reviews": True,
         "automatic_peer_reviews": False, "peer_review_count": None,
         "group_category_id": None,
         "rubric": [{"description": c["description"]} for c in parse_criteria(_SPEC)]}
    a.update(over)
    return a


def _diff(a, **over):
    kw = dict(anonymous=True, auto_count=None, group_category_id=None,
              criteria=parse_criteria(_SPEC))
    kw.update(over)
    return diff_existing(a, **kw)


def test_matching_assignment_is_already_set_up():
    assert _diff(_existing()) == []


def test_each_owned_setting_difference_is_reported():
    assert _diff(_existing(peer_reviews=False))
    assert _diff(_existing(anonymous_peer_reviews=False))
    assert _diff(_existing(automatic_peer_reviews=True))
    assert _diff(_existing(group_category_id=5))
    assert _diff(_existing(rubric=[{"description": "Something else"}]))
    assert _diff(_existing(automatic_peer_reviews=True, peer_review_count=1), auto_count=2)


def test_assignment_without_a_rubric_is_not_a_difference():
    """The repair path: assignment exists, rubric missing -> attach, don't fail."""
    a = _existing(rubric=None)
    assert _diff(a) == [] and not prs.has_rubric(a)


def test_find_existing_matches_title_exactly(monkeypatch):
    monkeypatch.setattr(prs, "_get", lambda *a, **k: [
        {"id": 1, "name": "Prep ratings extra"}, {"id": 2, "name": " Prep ratings "}])
    assert prs.find_existing("1", "Prep ratings")["id"] == 2
    monkeypatch.setattr(prs, "_get", lambda *a, **k: [{"id": 1, "name": "Other"}])
    assert prs.find_existing("1", "Prep ratings") is None


def test_enhanced_peer_review_detection(monkeypatch):
    monkeypatch.setattr(prs, "_get", lambda *a, **k: ["enhanced_rubrics", prs.ENHANCED_FLAG])
    assert prs.enhanced_peer_review_on("1") is True
    monkeypatch.setattr(prs, "_get", lambda *a, **k: ["enhanced_rubrics"])
    assert prs.enhanced_peer_review_on("1") is False
    monkeypatch.setattr(prs, "_get", lambda *a, **k: None)
    assert prs.enhanced_peer_review_on("1") is None


# --- main(): dry run writes nothing, apply is idempotent --------------------

def _run(monkeypatch, argv, existing=None, posts=None):
    posts = posts if posts is not None else []
    monkeypatch.setattr(prs, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(prs, "CANVAS_BASE_URL", "https://x")
    monkeypatch.setattr(prs.guard, "enforce", lambda **k: None)
    monkeypatch.setattr(prs, "enhanced_peer_review_on", lambda cid: False)
    monkeypatch.setattr(prs, "find_existing", lambda cid, t: existing)
    monkeypatch.setattr(prs, "_post", lambda ep, form: (posts.append(ep) or ({"id": 9, "published": False,
                        "peer_reviews": True, "anonymous_peer_reviews": True,
                        "automatic_peer_reviews": False}, "")))
    monkeypatch.setattr(prs, "attach_rubric", lambda *a, **k: (posts.append("rubric") or True, ""))
    monkeypatch.setattr(sys, "argv", ["peer_review_setup.py", "--course-id", "1",
                                      "--title", "Prep", "--criteria", _SPEC, *argv])
    return prs.main(), posts


def test_dry_run_writes_nothing(monkeypatch):
    rc, posts = _run(monkeypatch, [])
    assert rc == 0 and posts == []


def test_apply_creates_assignment_then_rubric(monkeypatch):
    rc, posts = _run(monkeypatch, ["--apply"])
    assert rc == 0 and posts == ["/courses/1/assignments", "rubric"]


def test_rerun_on_a_finished_setup_writes_nothing(monkeypatch):
    rc, posts = _run(monkeypatch, ["--apply"], existing=_existing())
    assert rc == 0 and posts == []


def test_rerun_on_missing_rubric_only_attaches_it(monkeypatch):
    rc, posts = _run(monkeypatch, ["--apply"], existing=_existing(rubric=None))
    assert rc == 0 and posts == ["rubric"]


def test_existing_with_different_settings_is_never_edited(monkeypatch):
    rc, posts = _run(monkeypatch, ["--apply"], existing=_existing(anonymous_peer_reviews=False))
    assert rc == 1 and posts == []


def test_bad_criteria_exit_2_before_any_call(monkeypatch):
    monkeypatch.setattr(prs, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(prs, "CANVAS_BASE_URL", "https://x")
    monkeypatch.setattr(sys, "argv", ["p", "--course-id", "1", "--title", "T",
                                      "--criteria", "X:maybe"])
    assert prs.main() == 2

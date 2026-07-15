"""Tier 1 unit tests — syllabus_audit.py.

Institution profile (compute_verdict + default_institution): the BYUI profile
REQUIRES a generative-AI policy for a 'complete' verdict; other institutions
treat it as advisory (reported but not verdict-driving). Institution is inferred
from the Canvas host, overridable by CANVAS_INSTITUTION / --institution.

Phrasing coverage (detect_sections + count_images): a "Grading Schemes" heading
(not "grading scale") over an image-only grade table, and late-work phrased as
"late assignments" / "an assignment is late" — real phrasings the original
pattern list missed.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import syllabus_audit as S  # noqa: E402
from syllabus_audit import (  # noqa: E402
    count_images,
    detect_sections,
    html_to_text,
)


# ---------------------------------------------------------------------------
# institution profile — compute_verdict + default_institution
# ---------------------------------------------------------------------------

def _all_detected():
    return [{"label": s["label"], "detected": True} for s in S.REQUIRED_SECTIONS]


def test_byui_profile_requires_ai_policy():
    v, missing = S.compute_verdict(_all_detected(), {"present": False}, 2000,
                                   ai_policy_required=True)
    assert v == "incomplete"
    assert any("AI Policy" in m for m in missing)


def test_generic_profile_treats_ai_policy_as_advisory():
    v, missing = S.compute_verdict(_all_detected(), {"present": False}, 2000,
                                   ai_policy_required=False)
    assert v == "complete"
    assert not any("AI Policy" in m for m in missing)


def test_missing_section_fails_regardless_of_profile():
    secs = _all_detected()
    secs[0]["detected"] = False
    for req in (True, False):
        v, _ = S.compute_verdict(secs, {"present": True}, 2000, ai_policy_required=req)
        assert v == "incomplete"


def test_institution_inferred_from_host(monkeypatch):
    monkeypatch.delenv("CANVAS_INSTITUTION", raising=False)
    monkeypatch.setattr(S, "CANVAS_BASE_URL", "https://byui.instructure.com")
    assert S.default_institution() == "byui"
    monkeypatch.setattr(S, "CANVAS_BASE_URL", "https://someschool.instructure.com")
    assert S.default_institution() == "generic"


def test_env_overrides_inference(monkeypatch):
    monkeypatch.setenv("CANVAS_INSTITUTION", "acme")
    monkeypatch.setattr(S, "CANVAS_BASE_URL", "https://byui.instructure.com")
    assert S.default_institution() == "acme"


# ---------------------------------------------------------------------------
# grading section — phrasing variants that previously false-negatived
# ---------------------------------------------------------------------------

def _grading_detected(text: str) -> bool:
    sections = detect_sections(text)
    return next(s["detected"] for s in sections if s["key"] == "grading")


def test_grading_scheme_heading_detected():
    """"Grading Schemes" (not "grading scale") must now match."""
    assert _grading_detected("see the grading schemes section below")


def test_late_assignments_phrasing_detected():
    """"Late assignments" / "an assignment is late" must now match
    ("late work" / "late policy" alone missed this real phrasing)."""
    assert _grading_detected("late assignments: 10% is deducted "
                             "for every day an assignment is late")


def test_original_grading_patterns_still_detected():
    """Regression guard — the original pattern set must keep working."""
    assert _grading_detected("see the grading scale for letter grades")
    assert _grading_detected("our late policy allows one free extension")


def test_grading_not_detected_when_absent():
    assert not _grading_detected("this syllabus discusses the course overview only")


# ---------------------------------------------------------------------------
# count_images — advisory signal for image-only policy content
# ---------------------------------------------------------------------------

def test_count_images_zero_for_text_only_body():
    assert count_images("<p>No images here, just text.</p>") == 0


def test_count_images_counts_multiple():
    body = '<img src="a.png"><p>text</p><img src="b.png">'
    assert count_images(body) == 2


def test_count_images_empty_body():
    assert count_images("") == 0
    assert count_images(None) == 0  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# html_to_text — sanity check the real-world case end-to-end
# ---------------------------------------------------------------------------

def test_grading_scheme_image_only_html_flagged_by_advisory_not_text():
    """The exact shape from the real syllabus: a "Grading Schemes" heading
    over an <img> with no textual grade cutoffs. Section detection passes
    on the heading; count_images flags the image so the advisory can warn
    that the actual scale is unreadable to both this audit and a screen
    reader."""
    body = (
        "<h2>Grading Schemes</h2>"
        '<img src="grading-scheme.png" alt="Grading Scheme.png">'
        "<h2>Late assignments</h2>"
        "<p>Every day an assignment is late, 10% is deducted.</p>"
    )
    text = html_to_text(body)
    assert _grading_detected(text)
    assert count_images(body) == 1


# ---------------------------------------------------------------------------
# clarity advisory — call out non-standard phrasing (student cognitive load)
# ---------------------------------------------------------------------------

def _grading(text):
    return next(s for s in detect_sections(text) if s["key"] == "grading")


def test_points_possible_no_longer_marks_grading_present():
    """Dropped as too generic — an assignment point value is not a grading policy."""
    assert not _grading("quiz 1 is worth 10 points possible")["detected"]


def test_comprehensive_late_vocabulary_detected():
    """Real faculty + Canvas vocabulary all detect the grading/late section
    (no false-negatives) — grounded in 32 live syllabi + Canvas's Late Policy UI."""
    for phrase in ("late work policy", "late assignments lose 10%",
                   "late submission deduction", "work submitted late",
                   "a grace period after the due date", "make-up work is allowed"):
        assert _grading(phrase)["detected"], phrase


def test_has_text_grade_scale():
    assert S.has_text_grade_scale("A = 93, B = 83")            # letter = number
    assert S.has_text_grade_scale("90-100% = A, 80-89% = B")   # percent range = letter
    # a lone percentage is a late penalty, NOT a grade scale — must not count
    assert not S.has_text_grade_scale("10% off per day an assignment is late")
    assert not S.has_text_grade_scale("final grades are posted in Canvas")


def _render_output(sections, advisory):
    return "\n".join(S._render(
        "1", "Course", S.COMPLETE, [], sections,
        {"present": True, "frameworks": []}, advisory, False, "ts"))


_BASE_ADVISORY = {"word_count": 500, "bloat": False, "outcomes_present": True,
                  "learning_model_present": False, "embedded_images": 0,
                  "grade_scale_in_text": True}


def test_render_image_warning_only_when_grade_scale_missing():
    secs = detect_sections("grading scale: refer to the chart")  # grading present
    warn = _render_output(secs, {**_BASE_ADVISORY, "embedded_images": 2,
                                 "grade_scale_in_text": False})
    assert "invisible to screen readers" in warn          # image-only risk -> warn
    ok = _render_output(secs, {**_BASE_ADVISORY, "embedded_images": 2,
                               "grade_scale_in_text": True})
    assert "invisible to screen readers" not in ok        # text scale present -> quiet


# ---------------------------------------------------------------------------
# late-policy mismatch check (#185) — detection, guards, and the three render
# states. Online-only; masters/sandboxes (no enrolled students) are skipped.
# ---------------------------------------------------------------------------

def test_mentions_late_policy_only_penalty_language():
    # penalty-grade / auto-deduction language -> True
    assert S.mentions_late_policy("10% is deducted per day late")
    assert S.mentions_late_policy("a penalty applies for late work")
    assert S.mentions_late_policy("your grade is reduced by 5% per day")
    # soft timeliness mentions -> False (the naive false-positive #185 fixed)
    assert not S.mentions_late_policy("late work as a sign of professionalism; "
                                      "complete your work on time")
    assert not S.mentions_late_policy("please submit assignments by the due date")


def test_late_policy_enabled():
    assert S.late_policy_enabled({"late_submission_deduction_enabled": True})
    assert S.late_policy_enabled({"missing_submission_deduction_enabled": True})
    assert not S.late_policy_enabled({"late_submission_deduction_enabled": False,
                                      "missing_submission_deduction_enabled": False})
    assert not S.late_policy_enabled(None)  # course has no late policy configured


def test_fetch_late_policy_unwraps_api_nesting(monkeypatch):
    monkeypatch.setattr(S, "_get", lambda ep, params=None:
                        {"late_policy": {"late_submission_deduction_enabled": True}})
    assert S.fetch_late_policy("1") == {"late_submission_deduction_enabled": True}
    monkeypatch.setattr(S, "_get", lambda ep, params=None: None)
    assert S.fetch_late_policy("1") is None


def test_course_has_enrolled_students(monkeypatch):
    monkeypatch.setattr(S, "_get", lambda ep, params=None: {"total_students": 30})
    assert S.course_has_enrolled_students("1")
    monkeypatch.setattr(S, "_get", lambda ep, params=None: {"total_students": 0})
    assert not S.course_has_enrolled_students("1")   # master/sandbox -> skip the check
    monkeypatch.setattr(S, "_get", lambda ep, params=None: None)
    assert not S.course_has_enrolled_students("1")   # fetch failed -> skip, don't crash


def test_detect_advisory_includes_late_policy_keys():
    adv = S.detect_advisory("10% is deducted per day late", "<p>x</p>")
    assert adv["syllabus_states_late_policy"] is True
    assert adv["late_policy_configured"] is None      # set only online + enrolled
    adv2 = S.detect_advisory("welcome to the course", "<p>x</p>")
    assert adv2["syllabus_states_late_policy"] is False


def test_render_flags_late_policy_mismatch():
    """Syllabus states an auto-deduction but Canvas's Late Policy is off -> warn."""
    secs = detect_sections("10% is deducted per day late")
    out = _render_output(secs, {**_BASE_ADVISORY, "syllabus_states_late_policy": True,
                                "late_policy_configured": False})
    assert "Gradebook Late Policy" in out and "OFF" in out


def test_render_confirms_when_policy_on():
    secs = detect_sections("10% is deducted per day late")
    out = _render_output(secs, {**_BASE_ADVISORY, "syllabus_states_late_policy": True,
                                "late_policy_configured": True})
    assert "on to enforce it" in out
    assert "OFF, so Canvas" not in out


def test_render_silent_when_late_policy_not_checked():
    """None = skipped (offline or non-enrolled master) -> NO late-policy line at all."""
    secs = detect_sections("10% is deducted per day late")
    out = _render_output(secs, {**_BASE_ADVISORY, "syllabus_states_late_policy": True,
                                "late_policy_configured": None})
    assert "Late-work policy" not in out

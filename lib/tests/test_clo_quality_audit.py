"""
test_clo_quality_audit.py

Unit tests for clo_quality_audit.py CLO scoring logic.

Tests focus on per-CLO scoring flags (measurable, single_barreled, process_not_outcome)
and the course-level verdict logic, NOT on Canvas API integration.
"""

import sys
from pathlib import Path

# Allow imports from lib/tools/
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from clo_quality_audit import score_clo


def test_process_not_outcome_rubric_criterion():
    """Issue #122 — rubric criterion language flagged as process, not outcome."""
    # The false positive from issue #122
    text = "Skills Practice: ... — This criterion uses the assignment total score to assess mastery"
    result = score_clo(text)

    assert "process_not_outcome" in result["hard_flags"], \
        f"Expected 'process_not_outcome' flag for rubric criterion text, got: {result['hard_flags']}"
    assert result["verdict"] in ("partial", "needs_revision"), \
        f"Expected verdict partial/needs_revision, got: {result['verdict']}"


def test_process_not_outcome_instructor_focused():
    """Instructor-focused outcome flagged per Process vs. Outcome anti-pattern."""
    text = "The instructor will describe types of fire extinguishers"
    result = score_clo(text)

    assert "process_not_outcome" in result["hard_flags"], \
        f"Expected 'process_not_outcome' flag for instructor-focused text, got: {result['hard_flags']}"


def test_valid_clo_not_flagged_as_process():
    """Well-formed CLO should NOT be flagged as process."""
    # Valid observable-verb outcome
    text = "Students will evaluate the ecological impact of deforestation using the criteria discussed in class"
    result = score_clo(text)

    assert "process_not_outcome" not in result["hard_flags"], \
        f"Valid CLO should not be flagged as process, got: {result['hard_flags']}"


def test_measurable_flag():
    """Non-observable verb (understand) should be flagged as not_measurable."""
    text = "Students will understand the water cycle"
    result = score_clo(text)

    assert "not_measurable" in result["hard_flags"], \
        f"Expected 'not_measurable' flag for 'understand' verb, got: {result['hard_flags']}"


def test_double_barreled_flag():
    """Two distinct goals in one outcome should be flagged as double_barreled."""
    text = "Students will design and evaluate a mobile application"
    result = score_clo(text)

    assert "double_barreled" in result["hard_flags"], \
        f"Expected 'double_barreled' flag for 'design and evaluate', got: {result['hard_flags']}"


def test_means_clause_not_double_barreled():
    """Means clause ('to produce') should NOT be flagged as double-barreled."""
    text = "Students will use Python to produce visualizations"
    result = score_clo(text)

    assert "double_barreled" not in result["hard_flags"], \
        f"Means clause should not be flagged as double-barreled, got: {result['hard_flags']}"


def test_clean_clo_meets_criteria():
    """Well-formed CLO with observable verb should meet criteria."""
    text = "Students will explain the water cycle and its phases"
    result = score_clo(text)

    assert result["verdict"] == "meets_criteria", \
        f"Clean CLO should meet criteria, got verdict: {result['verdict']}, flags: {result['hard_flags']}"
    assert len(result["hard_flags"]) == 0, \
        f"Clean CLO should have no hard flags, got: {result['hard_flags']}"


def test_multiple_flags_needs_revision():
    """CLO with 2+ hard flags should get needs_revision verdict."""
    # Instructor-focused + double-barreled
    text = "The instructor will design and evaluate learning activities"
    result = score_clo(text)

    assert result["verdict"] == "needs_revision", \
        f"Expected needs_revision for 2+ flags, got: {result['verdict']}"
    assert len(result["hard_flags"]) >= 2, \
        f"Expected at least 2 hard flags, got: {result['hard_flags']}"

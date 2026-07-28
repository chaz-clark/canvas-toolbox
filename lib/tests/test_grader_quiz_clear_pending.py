"""Unit tests — grader_quiz_clear_pending safety filters.

The whole tool rests on one invariant: it only ever posts a score to a MANUAL
question worth ZERO points, so it can never change a grade. These tests pin that
filter (and the pending-submission selector) hard.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_quiz_clear_pending import zero_point_manual_qids, pending_submissions  # noqa: E402


def test_selects_zero_point_essay_and_file_upload():
    qs = [
        {"id": 1, "question_type": "essay_question", "points_possible": 0},
        {"id": 2, "question_type": "file_upload_question", "points_possible": 0},
    ]
    assert zero_point_manual_qids(qs) == [1, 2]


def test_never_touches_a_scored_manual_question():
    """The safety invariant: a manual question worth > 0 is REAL grading — excluded."""
    qs = [
        {"id": 1, "question_type": "essay_question", "points_possible": 5},   # scored → skip
        {"id": 2, "question_type": "essay_question", "points_possible": 0},   # 0-pt → target
    ]
    assert zero_point_manual_qids(qs) == [2]


def test_ignores_auto_gradable_questions_even_at_zero_points():
    """Only manual types cause pending_review; a 0-point multiple-choice is not ours."""
    qs = [
        {"id": 1, "question_type": "multiple_choice_question", "points_possible": 0},
        {"id": 2, "question_type": "true_false_question", "points_possible": 0},
    ]
    assert zero_point_manual_qids(qs) == []


def test_handles_missing_or_bad_points_field():
    qs = [
        {"id": 1, "question_type": "essay_question"},                 # no points → treated 0
        {"id": 2, "question_type": "essay_question", "points_possible": "x"},  # junk → 0
        {"id": 3, "question_type": "essay_question", "points_possible": None},
    ]
    assert zero_point_manual_qids(qs) == [1, 2, 3]


def test_pending_submissions_selects_only_pending_review():
    subs = [
        {"id": 10, "user_id": 501, "workflow_state": "graded"},
        {"id": 11, "user_id": 502, "workflow_state": "pending_review"},
        {"id": 12, "user_id": 503, "workflow_state": "complete"},
    ]
    assert [s["user_id"] for s in pending_submissions(subs)] == [502]

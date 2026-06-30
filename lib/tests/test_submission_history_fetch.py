"""
Unit tests for submission_history_fetch.py

Tests the submission history tracking logic (Feature 4 - NGAI Integration).
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from submission_history_fetch import is_actual_submission, build_submission_record


def test_is_actual_submission_valid():
    """Submitted submissions should be recognized as actual"""
    sub = {
        "workflow_state": "submitted",
        "submitted_at": "2026-06-29T10:30:00Z"
    }
    assert is_actual_submission(sub)


def test_is_actual_submission_graded():
    """Graded submissions should be recognized as actual"""
    sub = {
        "workflow_state": "graded",
        "submitted_at": "2026-06-29T10:30:00Z"
    }
    assert is_actual_submission(sub)


def test_is_actual_submission_unsubmitted():
    """Unsubmitted should NOT be recognized as actual"""
    sub = {
        "workflow_state": "unsubmitted",
        "submitted_at": None
    }
    assert not is_actual_submission(sub)


def test_is_actual_submission_no_submitted_at():
    """Submissions without submitted_at should NOT be actual"""
    sub = {
        "workflow_state": "submitted",
        "submitted_at": None
    }
    assert not is_actual_submission(sub)


def test_build_submission_record_basic():
    """Build basic submission record with FERPA-safe fields"""
    sub = {
        "user_id": 12345,
        "attempt": 1,
        "submitted_at": "2026-06-29T10:30:00Z",
        "score": 85.0,
        "grade": "85",
        "workflow_state": "graded",
        "late": False,
        "excused": False,
        "missing": False,
        "submission_type": "online_upload",
        "submission_history": [],
        "user": {
            "display_name": "Real Student"
        }
    }

    record = build_submission_record(sub)

    assert record is not None
    assert record["user_id"] == 12345
    assert record["attempt"] == 1
    assert record["score"] == 85.0
    assert record["workflow_state"] == "graded"
    assert record["submission_history"] == []
    assert not record["is_test_student"]
    # FERPA: ensure no name in record
    assert "display_name" not in record
    assert "name" not in record


def test_build_submission_record_with_history():
    """Build submission record with multiple attempts in history"""
    sub = {
        "user_id": 67890,
        "attempt": 3,
        "submitted_at": "2026-06-29T12:00:00Z",
        "score": 95.0,
        "grade": "95",
        "workflow_state": "graded",
        "late": False,
        "excused": False,
        "missing": False,
        "submission_type": "online_text_entry",
        "submission_history": [
            {
                "attempt": 1,
                "submitted_at": "2026-06-29T10:00:00Z",
                "score": 70.0,
                "grade": "70",
                "workflow_state": "graded",
                "late": False
            },
            {
                "attempt": 2,
                "submitted_at": "2026-06-29T11:00:00Z",
                "score": 85.0,
                "grade": "85",
                "workflow_state": "graded",
                "late": False
            },
            {
                "attempt": 3,
                "submitted_at": "2026-06-29T12:00:00Z",
                "score": 95.0,
                "grade": "95",
                "workflow_state": "graded",
                "late": False
            }
        ],
        "user": {
            "display_name": "Persistent Student"
        }
    }

    record = build_submission_record(sub)

    assert record is not None
    assert record["user_id"] == 67890
    assert record["attempt"] == 3
    assert record["score"] == 95.0
    assert len(record["submission_history"]) == 3
    assert record["submission_history"][0]["attempt"] == 1
    assert record["submission_history"][0]["score"] == 70.0
    assert record["submission_history"][1]["attempt"] == 2
    assert record["submission_history"][1]["score"] == 85.0
    assert record["submission_history"][2]["attempt"] == 3
    assert record["submission_history"][2]["score"] == 95.0


def test_build_submission_record_test_student():
    """Test Student should be flagged in record"""
    sub = {
        "user_id": 11111,
        "attempt": 1,
        "submitted_at": "2026-06-29T10:30:00Z",
        "score": 100.0,
        "grade": "100",
        "workflow_state": "graded",
        "late": False,
        "excused": False,
        "missing": False,
        "submission_type": "online_quiz",
        "submission_history": [],
        "user": {
            "display_name": "Test Student"
        }
    }

    record = build_submission_record(sub)

    assert record is not None
    assert record["user_id"] == 11111
    assert record["is_test_student"]


def test_build_submission_record_test_student_only_filter():
    """test_student_only mode should filter out non-Test-Student"""
    real_student = {
        "user_id": 22222,
        "attempt": 1,
        "submitted_at": "2026-06-29T10:30:00Z",
        "score": 90.0,
        "grade": "90",
        "workflow_state": "graded",
        "late": False,
        "excused": False,
        "missing": False,
        "submission_type": "online_upload",
        "submission_history": [],
        "user": {
            "display_name": "Real Student"
        }
    }

    test_student = {
        "user_id": 33333,
        "attempt": 1,
        "submitted_at": "2026-06-29T10:30:00Z",
        "score": 100.0,
        "grade": "100",
        "workflow_state": "graded",
        "late": False,
        "excused": False,
        "missing": False,
        "submission_type": "online_quiz",
        "submission_history": [],
        "user": {
            "display_name": "Test Student"
        }
    }

    # With test_student_only=True, real student should be None
    real_record = build_submission_record(real_student, test_student_only=True)
    assert real_record is None

    # Test Student should still be included
    test_record = build_submission_record(test_student, test_student_only=True)
    assert test_record is not None
    assert test_record["user_id"] == 33333
    assert test_record["is_test_student"]


def test_build_submission_record_no_user_id():
    """Submission without user_id should return None"""
    sub = {
        "attempt": 1,
        "submitted_at": "2026-06-29T10:30:00Z",
        "score": 85.0,
        "submission_history": []
    }

    record = build_submission_record(sub)
    assert record is None


def test_build_submission_record_late_submission():
    """Late submission flag should be preserved"""
    sub = {
        "user_id": 44444,
        "attempt": 1,
        "submitted_at": "2026-06-29T23:59:00Z",
        "score": 80.0,
        "grade": "80",
        "workflow_state": "graded",
        "late": True,
        "excused": False,
        "missing": False,
        "submission_type": "online_text_entry",
        "submission_history": [],
        "user": {
            "display_name": "Late Student"
        }
    }

    record = build_submission_record(sub)

    assert record is not None
    assert record["late"]


def test_build_submission_record_excused():
    """Excused submission should be flagged"""
    sub = {
        "user_id": 55555,
        "attempt": None,
        "submitted_at": None,
        "score": None,
        "grade": None,
        "workflow_state": "graded",
        "late": False,
        "excused": True,
        "missing": False,
        "submission_type": None,
        "submission_history": [],
        "user": {
            "display_name": "Excused Student"
        }
    }

    record = build_submission_record(sub)

    assert record is not None
    assert record["excused"]


if __name__ == "__main__":
    # Run tests
    test_is_actual_submission_valid()
    test_is_actual_submission_graded()
    test_is_actual_submission_unsubmitted()
    test_is_actual_submission_no_submitted_at()
    test_build_submission_record_basic()
    test_build_submission_record_with_history()
    test_build_submission_record_test_student()
    test_build_submission_record_test_student_only_filter()
    test_build_submission_record_no_user_id()
    test_build_submission_record_late_submission()
    test_build_submission_record_excused()
    print("✅ All Feature 4 unit tests passed")

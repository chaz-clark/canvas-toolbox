"""Unit tests — grader_audit_workflow stuck-state detection (issue #226).

The audit's whole correctness rests on which submissions count as "stuck": a grade
posted but workflow_state still 'submitted'. It must NOT sweep in ungraded,
moderated (pending_review), or already-graded submissions — re-posting those would
be wrong.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_audit_workflow import find_stuck_submissions  # noqa: E402


def _s(uid, grade, state):
    return {"user_id": uid, "grade": grade, "workflow_state": state}


def test_graded_but_still_submitted_is_stuck():
    subs = [_s(1, "A", "submitted")]
    assert [s["user_id"] for s in find_stuck_submissions(subs)] == [1]


def test_properly_graded_is_not_stuck():
    assert find_stuck_submissions([_s(1, "A", "graded")]) == []


def test_ungraded_submitted_is_not_stuck():
    assert find_stuck_submissions([_s(1, None, "submitted")]) == []
    assert find_stuck_submissions([_s(2, "", "submitted")]) == []


def test_pending_review_is_left_alone():
    """Moderated grading queue — a re-post must not disturb it."""
    assert find_stuck_submissions([_s(1, "A", "pending_review")]) == []


def test_unsubmitted_is_not_stuck():
    assert find_stuck_submissions([_s(1, None, "unsubmitted")]) == []


def test_mixed_batch_returns_only_stuck():
    subs = [_s(1, "A", "submitted"),     # stuck
            _s(2, "B", "graded"),        # fine
            _s(3, None, "submitted"),    # ungraded
            _s(4, "C", "submitted"),     # stuck
            _s(5, "D", "pending_review")]  # moderated
    assert sorted(s["user_id"] for s in find_stuck_submissions(subs)) == [1, 4]

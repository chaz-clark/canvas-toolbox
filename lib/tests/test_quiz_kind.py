"""Tier 1 unit tests — _quiz_kind::classify_assignment_shape.

Source: lib/tools/_quiz_kind.py (#86 — classify an assignment as New
Quiz / Classic Quiz / not-a-quiz + recommend the data-access path).

Tests cover the pure classifier; the API-touching `detect_quiz_kind`
wrapper is exercised separately via integration smoke.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _quiz_kind import classify_assignment_shape  # noqa: E402


# ---------------------------------------------------------------------------
# Classic Quiz signals
# ---------------------------------------------------------------------------

def test_classic_quiz_via_quiz_id():
    """The strongest classic signal: an explicit quiz_id on the assignment."""
    assn = {"submission_types": ["online_quiz"], "quiz_id": 12345}
    kind, path = classify_assignment_shape(assn)
    assert kind == "classic_quiz"
    assert path == "submission_data"


def test_classic_quiz_via_submission_type_alone():
    """`online_quiz` submission_type confirms classic even without
    quiz_id surfaced (some payloads omit it)."""
    assn = {"submission_types": ["online_quiz"]}
    kind, path = classify_assignment_shape(assn)
    assert kind == "classic_quiz"
    assert path == "submission_data"


def test_classic_quiz_via_quiz_id_with_other_types():
    """A non-zero quiz_id wins even if submission_types is weird —
    Canvas sometimes ships assignments with mixed shapes."""
    assn = {"submission_types": ["none"], "quiz_id": 12345}
    kind, _ = classify_assignment_shape(assn)
    assert kind == "classic_quiz"


# ---------------------------------------------------------------------------
# New Quiz signals
# ---------------------------------------------------------------------------

def test_new_quiz_via_quiz_lti_url():
    """The modern NQ launcher URL fragment."""
    assn = {
        "submission_types": ["external_tool"],
        "external_tool_tag_attributes": {
            "url": "https://quiz-lti-iad-prod.instructure.com/lti/launch?some=param",
        },
    }
    kind, path = classify_assignment_shape(assn)
    assert kind == "new_quiz"
    assert path == "reporting_api"


def test_new_quiz_via_quizzes_next_url():
    """Legacy 'quizzes.next' marker."""
    assn = {
        "submission_types": ["external_tool"],
        "external_tool_tag_attributes": {
            "url": "https://quizzes.next.instructure.com/foo",
        },
    }
    kind, _ = classify_assignment_shape(assn)
    assert kind == "new_quiz"


def test_new_quiz_url_underscore_variant():
    assn = {
        "submission_types": ["external_tool"],
        "external_tool_tag_attributes": {"url": "https://example.com/quiz_lti/launch"},
    }
    kind, _ = classify_assignment_shape(assn)
    assert kind == "new_quiz"


# ---------------------------------------------------------------------------
# Negative cases — external_tool alone doesn't mean NQ
# ---------------------------------------------------------------------------

def test_external_tool_without_nq_url_is_not_a_quiz():
    """A non-NQ LTI tool (e.g., textbook publisher) has external_tool
    submission_type but is NOT a quiz."""
    assn = {
        "submission_types": ["external_tool"],
        "external_tool_tag_attributes": {
            "url": "https://example-publisher.com/launch",
        },
    }
    kind, path = classify_assignment_shape(assn)
    assert kind == "not_a_quiz"
    assert path == "none"


def test_external_tool_without_tag_attributes_is_not_a_quiz():
    """No external_tool_tag_attributes payload → can't confirm NQ."""
    assn = {"submission_types": ["external_tool"]}
    kind, _ = classify_assignment_shape(assn)
    assert kind == "not_a_quiz"


def test_online_upload_assignment_is_not_a_quiz():
    """The most common non-quiz case."""
    assn = {"submission_types": ["online_upload"]}
    kind, path = classify_assignment_shape(assn)
    assert kind == "not_a_quiz"
    assert path == "none"


def test_empty_assignment_payload_is_not_a_quiz():
    assert classify_assignment_shape({}) == ("not_a_quiz", "none")


def test_quiz_id_zero_treated_as_unset():
    """Canvas sometimes serializes a missing quiz_id as 0/null. quiz_id
    is None means no, but quiz_id=0 historically meant the same — we
    accept null-only here; classic_quiz signal also requires online_quiz
    fallback."""
    # quiz_id=None + no online_quiz → not_a_quiz
    assn = {"submission_types": ["online_upload"], "quiz_id": None}
    kind, _ = classify_assignment_shape(assn)
    assert kind == "not_a_quiz"

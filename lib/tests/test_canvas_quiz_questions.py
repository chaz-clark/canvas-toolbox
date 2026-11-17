"""
Unit tests for canvas_quiz_questions.py

Tests the student_view filtering logic (Feature 2 - NGAI Integration).
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from canvas_quiz_questions import _filter_student_view


def test_filter_student_view_strips_weights():
    """Student view should strip answer weights (correct answer indicators)"""
    questions = [
        {
            "id": 1,
            "question_name": "Q1",
            "question_text": "What is 2+2?",
            "question_type": "multiple_choice_question",
            "points_possible": 1,
            "answers": [
                {"id": 101, "text": "4", "weight": 100, "answer_text": "4"},
                {"id": 102, "text": "3", "weight": 0, "answer_text": "3"},
                {"id": 103, "text": "5", "weight": 0, "answer_text": "5"},
            ]
        }
    ]

    filtered = _filter_student_view(questions)

    assert len(filtered) == 1
    assert filtered[0]["id"] == 1
    assert filtered[0]["question_name"] == "Q1"
    assert len(filtered[0]["answers"]) == 3

    # Verify weights are stripped
    for ans in filtered[0]["answers"]:
        assert "weight" not in ans
        assert "answer_weight" not in ans
        assert "text" in ans


def test_filter_student_view_strips_answer_comments():
    """Student view should strip correct/incorrect/neutral comments"""
    questions = [
        {
            "id": 2,
            "question_name": "Q2",
            "question_text": "True or false?",
            "question_type": "true_false_question",
            "points_possible": 1,
            "correct_comments": "Great job!",
            "correct_comments_html": "<p>Great job!</p>",
            "incorrect_comments": "Try again",
            "incorrect_comments_html": "<p>Try again</p>",
            "neutral_comments": "OK",
            "neutral_comments_html": "<p>OK</p>",
            "answers": [
                {"id": 201, "text": "True", "weight": 100},
                {"id": 202, "text": "False", "weight": 0},
            ]
        }
    ]

    filtered = _filter_student_view(questions)

    assert len(filtered) == 1
    assert "correct_comments" not in filtered[0]
    assert "correct_comments_html" not in filtered[0]
    assert "incorrect_comments" not in filtered[0]
    assert "incorrect_comments_html" not in filtered[0]
    assert "neutral_comments" not in filtered[0]
    assert "neutral_comments_html" not in filtered[0]


def test_filter_student_view_preserves_question_structure():
    """Student view should preserve question structure and text"""
    questions = [
        {
            "id": 3,
            "question_name": "Essay Question",
            "question_text": "Explain your reasoning.",
            "question_type": "essay_question",
            "points_possible": 10,
            "answers": []
        }
    ]

    filtered = _filter_student_view(questions)

    assert len(filtered) == 1
    assert filtered[0]["id"] == 3
    assert filtered[0]["question_name"] == "Essay Question"
    assert filtered[0]["question_text"] == "Explain your reasoning."
    assert filtered[0]["question_type"] == "essay_question"
    assert filtered[0]["points_possible"] == 10
    assert filtered[0]["answers"] == []


def test_filter_student_view_handles_multiple_questions():
    """Student view should handle multiple questions correctly"""
    questions = [
        {
            "id": 4,
            "question_name": "Q1",
            "question_text": "First question",
            "answers": [
                {"id": 401, "text": "A", "weight": 100},
                {"id": 402, "text": "B", "weight": 0},
            ]
        },
        {
            "id": 5,
            "question_name": "Q2",
            "question_text": "Second question",
            "answers": [
                {"id": 501, "text": "X", "weight": 0},
                {"id": 502, "text": "Y", "weight": 100},
            ]
        }
    ]

    filtered = _filter_student_view(questions)

    assert len(filtered) == 2
    assert filtered[0]["id"] == 4
    assert filtered[1]["id"] == 5

    # Verify both questions have weights stripped
    for q in filtered:
        for ans in q.get("answers", []):
            assert "weight" not in ans


def test_filter_student_view_empty_list():
    """Student view should handle empty question list"""
    questions = []
    filtered = _filter_student_view(questions)
    assert filtered == []


def test_filter_student_view_no_mutation():
    """Student view filter should not mutate original questions"""
    questions = [
        {
            "id": 6,
            "question_name": "Q6",
            "answers": [
                {"id": 601, "text": "Answer", "weight": 100},
            ]
        }
    ]

    original_weight = questions[0]["answers"][0]["weight"]
    filtered = _filter_student_view(questions)

    # Original should still have weight
    assert questions[0]["answers"][0]["weight"] == original_weight
    # Filtered should not have weight
    assert "weight" not in filtered[0]["answers"][0]


if __name__ == "__main__":
    # Run tests
    test_filter_student_view_strips_weights()
    test_filter_student_view_strips_answer_comments()
    test_filter_student_view_preserves_question_structure()
    test_filter_student_view_handles_multiple_questions()
    test_filter_student_view_empty_list()
    test_filter_student_view_no_mutation()
    print("✅ All Feature 2 unit tests passed")


# --- formatted (HTML) comments -------------------------------------------------
# Canvas renders the plain *_comments fields escaped, so formatted feedback must
# travel in the *_html fields or bullets/italics show as literal tags.

import canvas_quiz_questions as cqq  # noqa: E402


class _Resp:
    status_code = 200

    def json(self):
        return {"id": 1}


def _capture_create(monkeypatch, q):
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent["payload"] = json
        return _Resp()

    monkeypatch.setattr(cqq.requests, "post", fake_post)
    cqq._create_question("1", 2, q)
    return sent["payload"]["question"]


def test_html_comments_are_sent(monkeypatch):
    q = _capture_create(monkeypatch, {
        "question_name": "Q", "question_text": "<p>x</p>",
        "question_type": "multiple_choice_question",
        "answers": [{"answer_text": "A", "answer_weight": 100}],
        "incorrect_comments_html": "<p>Why</p><ul><li><em>b:</em> no</li></ul>",
    })
    assert q["incorrect_comments_html"].startswith("<p>Why</p>")
    assert "incorrect_comments" not in q


def test_essay_neutral_html_comment_sent_without_answers(monkeypatch):
    q = _capture_create(monkeypatch, {
        "question_name": "E", "question_text": "<p>Explain</p>",
        "question_type": "essay_question", "answers": [],
        "neutral_comments_html": "<p>Notes</p>",
    })
    assert q["neutral_comments_html"] == "<p>Notes</p>"
    assert "answers" not in q


def test_plain_comments_still_supported(monkeypatch):
    q = _capture_create(monkeypatch, {
        "question_name": "Q", "question_type": "multiple_choice_question",
        "answers": [{"answer_text": "A", "answer_weight": 100}],
        "correct_comments": "Nice",
    })
    assert q["correct_comments"] == "Nice"


def test_answer_comments_html_passed_per_answer(monkeypatch):
    q = _capture_create(monkeypatch, {
        "question_name": "Q", "question_type": "multiple_choice_question",
        "answers": [{"answer_text": "A", "answer_weight": 0, "answer_comments_html": "<em>no</em>"},
                    {"answer_text": "B", "answer_weight": 100}],
    })
    assert q["answers"][0]["answer_comments_html"] == "<em>no</em>"
    assert "answer_comments_html" not in q["answers"][1]

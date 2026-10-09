"""#359 — an essay-only quiz reports question_count 0 but has questions; only a quiz
whose real /questions list is empty is an empty shell."""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import course_quality_check as cqc  # noqa: E402


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def _patch_questions(monkeypatch, status, body):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        return _Resp(status, body)

    monkeypatch.setattr(cqc.requests, "get", fake_get)
    return calls


def test_quiz_with_essay_questions_is_not_empty(monkeypatch):
    _patch_questions(monkeypatch, 200, [{"id": 1, "question_type": "essay_question"}])
    assert cqc._quiz_has_no_questions("https://x", "1", 9) is False


def test_quiz_with_no_questions_is_empty(monkeypatch):
    calls = _patch_questions(monkeypatch, 200, [])
    assert cqc._quiz_has_no_questions("https://x", "1", 9) is True
    assert calls == ["https://x/api/v1/courses/1/quizzes/9/questions"]


def test_unverifiable_quiz_keeps_the_old_flag(monkeypatch):
    """A failed fetch must not silently hide a real empty shell."""
    _patch_questions(monkeypatch, 500, {})
    assert cqc._quiz_has_no_questions("https://x", "1", 9) is True


def _audit_with_quizzes(monkeypatch, quizzes, questions_by_quiz):
    """Run the real _audit_course with only the network seams stubbed."""
    monkeypatch.setattr(cqc, "_get_course_window", lambda cid: (None, None))
    monkeypatch.setattr(cqc, "_get_all",
                        lambda url, params=None: quizzes if url.endswith("/quizzes") else [])

    def fake_get(url, **kw):
        qid = int(url.split("/quizzes/")[1].split("/")[0])
        return _Resp(200, questions_by_quiz[qid])

    monkeypatch.setattr(cqc.requests, "get", fake_get)
    report = cqc._audit_course("1")
    return [m["canvas_id"] for m in report["manual_review"] if m["type"] == "empty_quiz"]


def test_audit_flags_only_the_truly_empty_quiz(monkeypatch):
    quizzes = [
        {"id": 1, "title": "Essay reflection", "quiz_type": "graded_survey", "question_count": 0},
        {"id": 2, "title": "Empty shell", "quiz_type": "assignment", "question_count": 0},
        {"id": 3, "title": "Really empty", "quiz_type": "practice_quiz", "question_count": 0},
        {"id": 4, "title": "Normal", "quiz_type": "assignment", "question_count": 5},
    ]
    flagged = _audit_with_quizzes(monkeypatch, quizzes, {1: [{"id": 7}], 3: []})
    assert flagged == [3]

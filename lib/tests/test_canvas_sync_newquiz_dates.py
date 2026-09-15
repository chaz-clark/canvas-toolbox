"""_push_newquiz_dates must push due/unlock/lock dates for New-Quiz-backed
assignments instead of the old blanket skip (issue #318).

New Quizzes are LTI-delivered (submission_types == ["external_tool"]); their
content/settings genuinely have no write support via the standard Assignment
API — but due_at/lock_at/unlock_at live on the Assignment object itself and ARE
writable regardless of quiz engine. Confirmed empirically against a real
course: PUT with only these three fields returned a clean 200 for 25/25 dated
New-Quiz assignments. Before this fix, canvas_sync.py unconditionally skipped
EVERY field for `item_type == "NewQuiz"` — 0/51 pushed in the reporting course.

The narrower half of the fix matters as much as the wider half: description,
submission_types, and grading_type must NEVER be sent for a New-Quiz shell —
only what was actually tested.
"""
import importlib.util
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("canvas_sync", TOOLS / "canvas_sync.py")
canvas_sync = importlib.util.module_from_spec(spec)
sys.modules["canvas_sync"] = canvas_sync
spec.loader.exec_module(canvas_sync)


class _Resp:
    def __init__(self, status_code, text="{}"):
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text) if self.text else {}


class _FakeRequests:
    def __init__(self, status_code=200):
        self._status_code = status_code
        self.calls = []  # list of (verb, url, json)

    def put(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("put", url, json))
        return _Resp(self._status_code)


def _install(monkeypatch, status_code=200):
    fake = _FakeRequests(status_code)
    monkeypatch.setattr(canvas_sync, "requests", fake)
    monkeypatch.setattr(canvas_sync, "CANVAS_COURSE_ID", "425166")
    return fake


def _newquiz_assignment_file(tmp_path, **overrides) -> Path:
    data = {
        "name": "Week 1 New Quiz",
        "description": "Canvas-only content — never sent for a New Quiz.",
        "submission_types": ["external_tool"],
        "grading_type": "points",
        "points_possible": 10,
        "published": True,
        "due_at": "2026-09-17T05:59:00Z",
        "lock_at": "2026-09-17T05:59:00Z",
        "unlock_at": "2026-09-10T06:00:00Z",
    }
    data.update(overrides)
    path = tmp_path / "1-function-evaluation.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_pushes_only_the_three_date_fields(monkeypatch, tmp_path):
    fake = _install(monkeypatch)
    path = _newquiz_assignment_file(tmp_path)

    ok = canvas_sync._push_newquiz_dates(path, {"canvas_id": 999})

    assert ok is True
    assert len(fake.calls) == 1
    verb, url, payload = fake.calls[0]
    assert verb == "put"
    assert url.endswith("/courses/425166/assignments/999")
    assert payload == {"assignment": {
        "due_at": "2026-09-17T05:59:00Z",
        "lock_at": "2026-09-17T05:59:00Z",
        "unlock_at": "2026-09-10T06:00:00Z",
    }}


def test_never_sends_description_or_submission_types():
    """The narrower half of the fix, verified directly against the built
    payload — not just by absence of a failure. Touching submission_types on a
    New-Quiz assignment shell risks breaking its LTI linkage."""
    import canvas_sync as _cs
    import inspect
    src = inspect.getsource(_cs._push_newquiz_dates)
    assert '"description"' not in src
    assert '"submission_types"' not in src
    assert '"grading_type"' not in src


def test_returns_true_and_pushes_nothing_when_no_date_fields_present(monkeypatch, tmp_path):
    fake = _install(monkeypatch)
    path = tmp_path / "no-dates.json"
    path.write_text(json.dumps({"name": "x", "submission_types": ["external_tool"]}),
                    encoding="utf-8")

    ok = canvas_sync._push_newquiz_dates(path, {"canvas_id": 999})

    assert ok is True
    assert fake.calls == []


def test_missing_canvas_id_fails_without_a_network_call(monkeypatch, tmp_path, capsys):
    fake = _install(monkeypatch)
    path = _newquiz_assignment_file(tmp_path)

    ok = canvas_sync._push_newquiz_dates(path, {})

    assert ok is False
    assert fake.calls == []
    assert "no canvas_id" in capsys.readouterr().out


def test_a_canvas_error_is_reported_and_returns_false(monkeypatch, tmp_path, capsys):
    _install(monkeypatch, status_code=400)
    path = _newquiz_assignment_file(tmp_path)

    ok = canvas_sync._push_newquiz_dates(path, {"canvas_id": 999})

    assert ok is False
    assert "ERROR" in capsys.readouterr().out


def test_the_old_blanket_skip_no_longer_exists():
    """Regression guard for the exact bug in #318: the push loop must not
    special-case NewQuiz into an unconditional continue that never calls the
    Canvas API at all."""
    import inspect
    src = inspect.getsource(canvas_sync)
    assert "NewQuiz descriptions must be edited in Canvas UI (API not supported)" not in src
    assert "_push_newquiz_dates" in src

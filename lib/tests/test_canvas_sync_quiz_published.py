"""Classic quiz `published` must reach Canvas on push (#411).

`_push_quiz` built its payload without `published`, so toggling it in the quiz
JSON printed OK and left Canvas unchanged. Canvas also refuses to unpublish a
quiz that has student submissions; that refusal is named distinctly.
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
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text) if self.text else {}


class _FakeRequests:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or _Resp(200)

    def put(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, json))
        return self.response


def _push(monkeypatch, tmp_path, data, response=None):
    fake = _FakeRequests(response)
    monkeypatch.setattr(canvas_sync, "requests", fake)
    monkeypatch.setattr(canvas_sync, "CANVAS_COURSE_ID", "1")
    monkeypatch.setattr(canvas_sync, "CANVAS_BASE_URL", "https://example.instructure.com")
    f = tmp_path / "quiz.json"
    f.write_text(json.dumps(data))
    return canvas_sync._push_quiz(f, {"canvas_id": 7}), fake


def test_published_true_is_sent(monkeypatch, tmp_path):
    ok, fake = _push(monkeypatch, tmp_path, {"title": "Q", "published": True})
    assert ok is True
    assert fake.calls[0][1]["quiz"]["published"] is True


def test_published_absent_is_not_sent(monkeypatch, tmp_path):
    _, fake = _push(monkeypatch, tmp_path, {"title": "Q"})
    assert "published" not in fake.calls[0][1]["quiz"]


def test_unpublish_refusal_is_named(monkeypatch, tmp_path, capsys):
    resp = _Resp(400, "Can't unpublish if there are student submissions")
    ok, _ = _push(monkeypatch, tmp_path, {"title": "Q", "published": False}, resp)
    assert ok is False
    assert "ERROR (unpublish)" in capsys.readouterr().out

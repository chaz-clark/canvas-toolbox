"""Page todo_date silently no-ops unless student_todo_at is sent in the same PUT.

Confirmed on live course 425166 (2026-09-15, M119 Fall date migration, #L21 in
canvas_api_lessons_learned.md): wiki_page[todo_date] alone returns 200 but
Canvas does not persist it. wiki_page[todo_date] + wiki_page[student_todo_at]
together does. _push_page_todo_date must always send both fields.

Also confirmed the same day: clearing an existing todo_date requires an empty
string, not a JSON null — a null PUT returns 200 but leaves the stale date in
place (caught only by re-GET after a batch run, since the field's own response
echoed as if it worked).
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
    def __init__(self):
        self.calls = []  # list of (verb, url, json)

    def put(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("put", url, json))
        return _Resp(200)


def _install(monkeypatch):
    fake = _FakeRequests()
    monkeypatch.setattr(canvas_sync, "requests", fake)
    monkeypatch.setattr(canvas_sync, "CANVAS_COURSE_ID", "425166")
    monkeypatch.setattr(canvas_sync, "CANVAS_BASE_URL", "https://example.instructure.com")
    return fake


def test_sets_both_fields_together(monkeypatch):
    fake = _install(monkeypatch)

    ok = canvas_sync._push_page_todo_date("w01-monday-class-prep-reminder", "2026-09-14T06:00:00Z")

    assert ok is True
    assert len(fake.calls) == 1
    verb, url, payload = fake.calls[0]
    assert verb == "put"
    assert "/pages/w01-monday-class-prep-reminder" in url
    assert payload == {
        "wiki_page": {
            "todo_date": "2026-09-14T06:00:00Z",
            "student_todo_at": "2026-09-14T06:00:00Z",
        }
    }


def test_clears_with_empty_string_not_null(monkeypatch):
    """A JSON null PUT returns 200 but Canvas leaves the stale date in place —
    only an empty string actually clears it (confirmed live, 2026-09-15)."""
    fake = _install(monkeypatch)

    ok = canvas_sync._push_page_todo_date("w14-thursday-class-prep-reminder", None)

    assert ok is True
    payload = fake.calls[0][2]
    assert payload == {"wiki_page": {"todo_date": "", "student_todo_at": ""}}


def test_cmd_set_todo_dates_batches_a_mapping_file(monkeypatch, tmp_path):
    fake = _install(monkeypatch)
    mapping_file = tmp_path / "todo_dates.json"
    mapping_file.write_text(json.dumps({
        "w01-monday-class-prep-reminder": "2026-09-14T06:00:00Z",
        "w14-thursday-class-prep-reminder": None,
    }))

    canvas_sync.cmd_set_todo_dates(str(mapping_file))

    assert len(fake.calls) == 2
    urls = [c[1] for c in fake.calls]
    assert any("w01-monday-class-prep-reminder" in u for u in urls)
    assert any("w14-thursday-class-prep-reminder" in u for u in urls)

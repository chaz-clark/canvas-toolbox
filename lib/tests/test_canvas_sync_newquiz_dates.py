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


def test_newquiz_item_payload_strips_read_only_response_fields():
    source = {
        "id": "9001",
        "position": 1,
        "points_possible": 2,
        "entry_type": "Item",
        "entry_editable": True,
        "status": "mutable",
        "created_at": "2026-09-23T00:00:00Z",
        "entry": {
            "id": "entry-1",
            "title": "Probe question",
            "item_body": "<p>Is this a test?</p>",
            "interaction_type_slug": "true-false",
            "interaction_data": {"true_choice": "True", "false_choice": "False"},
            "scoring_data": {"value": True},
            "scoring_algorithm": "Equivalence",
            "updated_at": "2026-09-23T00:00:00Z",
        },
    }

    payload = canvas_sync._newquiz_item_payload(source)
    assert payload["item"]["points_possible"] == 2
    assert payload["item"]["entry"]["title"] == "Probe question"
    assert "id" not in payload["item"]["entry"]
    assert "updated_at" not in payload["item"]["entry"]
    assert "entry_editable" not in payload["item"]
    assert "status" not in payload["item"]


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


# ---------------------------------------------------------------------------
# _push_newquiz_content — opt-in gate + matching/create/update/delete logic
#
# Content writes are sandbox-CRUD-verified but not production-sync-validated
# (8 of 12 documented writable item types have no fixture coverage). The gate
# mirrors the existing CANVAS_SYNC_ALLOW_NEWQUIZ_DELETE precedent, extended to
# the create/update path it was inconsistently missing from.
# ---------------------------------------------------------------------------

def _sidecar_file(tmp_path, settings=None, items=None) -> Path:
    """Default settings deliberately has NO push-whitelisted keys (only "id",
    which is used for quiz_id fallback but never sent) — item-focused tests
    must not accidentally trigger the settings PATCH against a real network
    call just because a monkeypatch was missed."""
    sidecar = {
        "quiz_engine": "new_quiz",
        "settings": settings if settings is not None else {"id": 999},
        "items": items if items is not None else [],
    }
    path = tmp_path / "quiz.newquiz.json"
    path.write_text(json.dumps(sidecar), encoding="utf-8")
    return path


class _BlockRealPatch:
    """Defense in depth: item-focused tests below rely on an empty settings
    payload to skip the PATCH call, but a real `requests.patch` reaching the
    live sandbox with a fake quiz_id must fail LOUDLY in a test, never
    silently succeed or silently no-op against production Canvas."""
    def patch(self, *a, **k):
        raise AssertionError("test must not reach a real requests.patch() call")


def test_content_push_skipped_by_default(monkeypatch, tmp_path, capsys):
    """The core fix: without the opt-in flag, no network call happens at all —
    not the settings PATCH, not a single item read or write."""
    monkeypatch.delenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", raising=False)
    calls = []
    monkeypatch.setattr(canvas_sync, "requests",
                        type("R", (), {"patch": staticmethod(lambda *a, **k: calls.append(1))}))
    monkeypatch.setattr(canvas_sync, "_get_new_quiz", lambda *a: calls.append(1))
    sidecar = _sidecar_file(tmp_path, items=[{"entry_type": "Item", "entry": {"title": "X"}}])

    ok = canvas_sync._push_newquiz_content(
        tmp_path / "assignment.json", {"canvas_id": 999, "settings_path": str(sidecar)})

    assert ok is True
    assert calls == []
    assert "CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE=true" in capsys.readouterr().out


def test_content_push_runs_when_flag_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", "true")
    monkeypatch.setattr(canvas_sync, "CANVAS_COURSE_ID", "425166")
    monkeypatch.setattr(canvas_sync, "requests", _BlockRealPatch())
    monkeypatch.setattr(canvas_sync, "_get_new_quiz", lambda ep: [])
    sidecar = _sidecar_file(tmp_path, settings={"id": 999})  # no settings_payload fields

    ok = canvas_sync._push_newquiz_content(
        tmp_path / "assignment.json", {"canvas_id": 999, "settings_path": str(sidecar)})

    assert ok is True


def test_content_push_creates_new_item_when_no_match(monkeypatch, tmp_path):
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", "true")
    monkeypatch.setattr(canvas_sync, "CANVAS_COURSE_ID", "425166")
    monkeypatch.setattr(canvas_sync, "requests", _BlockRealPatch())
    monkeypatch.setattr(canvas_sync, "_get_new_quiz", lambda ep: [])  # nothing exists yet
    writes = []
    monkeypatch.setattr(canvas_sync, "_newquiz_write", lambda method, path, payload:
                        writes.append((method, path)) or {"id": 42})
    sidecar = _sidecar_file(tmp_path, items=[
        {"entry_type": "Item", "entry": {"title": "New question"}}])

    ok = canvas_sync._push_newquiz_content(
        tmp_path / "assignment.json", {"canvas_id": 999, "settings_path": str(sidecar)})

    assert ok is True
    assert writes == [("POST", "/courses/425166/quizzes/999/items")]


def test_content_push_updates_item_matched_by_id(monkeypatch, tmp_path):
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", "true")
    monkeypatch.setattr(canvas_sync, "CANVAS_COURSE_ID", "425166")
    monkeypatch.setattr(canvas_sync, "requests", _BlockRealPatch())
    monkeypatch.setattr(canvas_sync, "_get_new_quiz", lambda ep: [
        {"id": 7, "entry_type": "Item", "entry": {"title": "Old title"}}])
    writes = []
    monkeypatch.setattr(canvas_sync, "_newquiz_write", lambda method, path, payload:
                        writes.append((method, path)) or {"id": 7})
    sidecar = _sidecar_file(tmp_path, items=[
        {"id": 7, "entry_type": "Item", "entry": {"title": "New title"}}])

    ok = canvas_sync._push_newquiz_content(
        tmp_path / "assignment.json", {"canvas_id": 999, "settings_path": str(sidecar)})

    assert ok is True
    assert writes == [("PATCH", "/courses/425166/quizzes/999/items/7")]


def test_content_push_matches_by_title_when_id_differs(monkeypatch, tmp_path):
    """A re-bound/copied course gives the item a NEW Canvas id — title match
    is the fallback so it updates instead of duplicating."""
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", "true")
    monkeypatch.setattr(canvas_sync, "CANVAS_COURSE_ID", "425166")
    monkeypatch.setattr(canvas_sync, "requests", _BlockRealPatch())
    monkeypatch.setattr(canvas_sync, "_get_new_quiz", lambda ep: [
        {"id": 555, "entry_type": "Item", "entry": {"title": "Same title"}}])
    writes = []
    monkeypatch.setattr(canvas_sync, "_newquiz_write", lambda method, path, payload:
                        writes.append((method, path)) or {"id": 555})
    sidecar = _sidecar_file(tmp_path, items=[
        {"id": 111, "entry_type": "Item", "entry": {"title": "Same title"}}])  # id 111 in source

    ok = canvas_sync._push_newquiz_content(
        tmp_path / "assignment.json", {"canvas_id": 999, "settings_path": str(sidecar)})

    assert ok is True
    assert writes == [("PATCH", "/courses/425166/quizzes/999/items/555")]  # target's real id


def test_content_push_skips_read_only_entry_types(monkeypatch, tmp_path):
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", "true")
    monkeypatch.setattr(canvas_sync, "CANVAS_COURSE_ID", "425166")
    monkeypatch.setattr(canvas_sync, "requests", _BlockRealPatch())
    monkeypatch.setattr(canvas_sync, "_get_new_quiz", lambda ep: [])
    writes = []
    monkeypatch.setattr(canvas_sync, "_newquiz_write", lambda method, path, payload:
                        writes.append((method, path)) or {"id": 1})
    sidecar = _sidecar_file(tmp_path, items=[
        {"entry_type": "StimulusItem", "entry": {"title": "reading passage"}}])

    ok = canvas_sync._push_newquiz_content(
        tmp_path / "assignment.json", {"canvas_id": 999, "settings_path": str(sidecar)})

    assert ok is True
    assert writes == []


def test_content_push_never_deletes_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("CANVAS_SYNC_ALLOW_NEWQUIZ_DELETE", raising=False)
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", "true")
    monkeypatch.setattr(canvas_sync, "CANVAS_COURSE_ID", "425166")
    monkeypatch.setattr(canvas_sync, "requests", _BlockRealPatch())
    monkeypatch.setattr(canvas_sync, "_get_new_quiz", lambda ep: [
        {"id": 7, "entry_type": "Item", "entry": {"title": "orphaned locally"}}])
    writes = []
    monkeypatch.setattr(canvas_sync, "_newquiz_write", lambda method, path, payload:
                        writes.append((method, path)) or {"id": 7})
    sidecar = _sidecar_file(tmp_path, items=[])  # source no longer has item 7

    ok = canvas_sync._push_newquiz_content(
        tmp_path / "assignment.json", {"canvas_id": 999, "settings_path": str(sidecar)})

    assert ok is True
    assert writes == []  # additive/update-only — nothing deleted


def test_content_push_deletes_when_both_flags_set(monkeypatch, tmp_path):
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", "true")
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_DELETE", "true")
    monkeypatch.setattr(canvas_sync, "CANVAS_COURSE_ID", "425166")
    monkeypatch.setattr(canvas_sync, "requests", _BlockRealPatch())
    monkeypatch.setattr(canvas_sync, "_get_new_quiz", lambda ep: [
        {"id": 7, "entry_type": "Item", "entry": {"title": "orphaned locally"}}])
    writes = []
    monkeypatch.setattr(canvas_sync, "_newquiz_write", lambda method, path, payload:
                        writes.append((method, path)) or {"id": 7})
    sidecar = _sidecar_file(tmp_path, items=[])

    ok = canvas_sync._push_newquiz_content(
        tmp_path / "assignment.json", {"canvas_id": 999, "settings_path": str(sidecar)})

    assert ok is True
    assert writes == [("DELETE", "/courses/425166/quizzes/999/items/7")]


def test_content_push_missing_sidecar_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", "true")

    ok = canvas_sync._push_newquiz_content(
        tmp_path / "assignment.json",
        {"canvas_id": 999, "settings_path": str(tmp_path / "missing.json")})

    assert ok is False


def test_content_push_item_write_error_returns_false(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", "true")
    monkeypatch.setattr(canvas_sync, "CANVAS_COURSE_ID", "425166")
    monkeypatch.setattr(canvas_sync, "requests", _BlockRealPatch())
    monkeypatch.setattr(canvas_sync, "_get_new_quiz", lambda ep: [])
    monkeypatch.setattr(canvas_sync, "_newquiz_write",
                        lambda method, path, payload: {"error": "HTTP 422"})
    sidecar = _sidecar_file(tmp_path, items=[{"entry_type": "Item", "entry": {"title": "X"}}])

    ok = canvas_sync._push_newquiz_content(
        tmp_path / "assignment.json", {"canvas_id": 999, "settings_path": str(sidecar)})

    assert ok is False
    assert "ERROR" in capsys.readouterr().out

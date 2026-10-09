"""Regression test — sync_to_new.py's assignment-group create payload (#351).

Caught by chance while sandbox-testing an unrelated tool (canvas_shell_create.py):
create_assignment_group() wrapped its payload in an "assignment_group" key, matching
the convention every other creation function in this file uses (modules, pages,
assignments). Canvas's Assignment Groups API is the one endpoint that doesn't accept
that shape — a wrapped POST returns 200 but silently creates a group named
"Assignments" with group_weight 0, ignoring every field sent. Untested until now.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import sync_to_new as stn  # noqa: E402


def test_create_assignment_group_sends_flat_payload_not_wrapped(monkeypatch):
    seen = {}

    def fake_post(url, payload, token):
        seen["payload"] = payload
        return {"success": True, "data": {"id": 1, **payload}}

    monkeypatch.setattr(stn, "_post", fake_post)
    group_data = {"name": "Homework", "group_weight": 40.0, "position": 1}
    stn.create_assignment_group("https://x", "1", group_data, "tok")

    assert seen["payload"] == group_data
    assert "assignment_group" not in seen["payload"]


# --- course guard + .env loading actually wired (regression) -------------------

def test_load_env_and_course_guard_are_the_real_ones_not_import_fallbacks():
    """sync_to_new imported two names canvas_course_guard never had, and the except
    ImportError fallback silently swapped in a no-op load_env and a no-op guard — so
    .env was never loaded and the course-safety guard never ran."""
    import _env_loader
    import canvas_course_guard
    assert stn.load_env is _env_loader.load_env
    assert stn._course_guard is canvas_course_guard.enforce


def test_main_runs_the_guard_in_read_mode_for_preview_and_write_mode_for_apply(monkeypatch):
    calls = []
    monkeypatch.setattr(stn, "_load_config", lambda: ("https://x", "9", "tok"))
    monkeypatch.setattr(stn, "_course_guard",
                        lambda base, headers, cid, mode: calls.append((cid, mode)))
    monkeypatch.setattr(stn, "load_course_content", lambda *a, **k: {})   # main stops here
    for argv, mode in ((["sync_to_new.py"], "read"), (["sync_to_new.py", "--apply"], "write")):
        monkeypatch.setattr(sys, "argv", argv)
        assert stn.main() == 1
        assert calls[-1] == ("9", mode)


def test_main_does_not_ask_a_human_to_type_yes(monkeypatch):
    """The old stub made every target 'PRODUCTION' and blocked on input()."""
    monkeypatch.setattr(stn, "_load_config", lambda: ("https://x", "9", "tok"))
    monkeypatch.setattr(stn, "_course_guard", lambda *a, **k: None)
    monkeypatch.setattr(stn, "load_course_content", lambda *a, **k: {})
    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(AssertionError("prompted")))
    monkeypatch.setattr(sys, "argv", ["sync_to_new.py"])
    assert stn.main() == 1

# --- New Quizzes (#367) -------------------------------------------------------

import json  # noqa: E402


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body if body is not None else {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


def _newquiz_fixture(tmp_path, items):
    sidecar = tmp_path / "quiz.settings.json"
    sidecar.write_text(json.dumps({
        "quiz_engine": "new_quiz",
        "settings": {"title": "Quiz 1", "points_possible": 10, "assignment_group_id": 77,
                     "quiz_settings": {"shuffle_answers": False}},
        "items": items,
    }), encoding="utf-8")
    return {"m1/quiz.json": {"type": "NewQuiz", "title": "Quiz 1", "module_slug": "m1",
                             "settings_path": str(sidecar)}}


def _item(item_id, title, entry_type="Item"):
    return {"id": item_id, "entry_type": entry_type, "position": 1, "points_possible": 2,
            "entry": {"title": title, "item_body": "<p>q</p>", "id": "read-only"}}


def test_newquizzes_skipped_without_the_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", raising=False)
    monkeypatch.setattr(stn.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no write")))
    files = _newquiz_fixture(tmp_path, [_item(1, "Q1")])
    assert stn.create_newquizzes_in_modules("https://x", "9", files, {"m1": 5}, {}, "tok") == {}


def test_newquiz_created_with_mapped_group_items_and_module_link(tmp_path, monkeypatch):
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", "true")
    posts = []

    def fake_post(url, **kw):
        posts.append((url, kw))
        return _Resp(200, {"id": 555} if url.endswith("/quizzes") else {"id": 1})

    linked = []
    monkeypatch.setattr(stn.requests, "post", fake_post)
    monkeypatch.setattr(stn, "create_module_item",
                        lambda base, cid, mid, data, tok: linked.append((mid, data)) or {"id": 1})
    files = _newquiz_fixture(tmp_path, [_item(1, "Q1"), _item(2, "Stim", "Stimulus")])

    mapping = stn.create_newquizzes_in_modules("https://x", "9", files, {"m1": 5}, {77: 900}, "tok")

    assert mapping == {"m1/quiz.json": 555}
    quiz_url, quiz_kw = posts[0]
    assert quiz_url == "https://x/api/quiz/v1/courses/9/quizzes"
    assert quiz_kw["data"]["quiz[assignment_group_id]"] == 900          # old id remapped
    assert quiz_kw["data"]["quiz[quiz_settings][shuffle_answers]"] == "false"  # not "False"
    item_posts = [p for p in posts if p[0].endswith("/555/items")]
    assert len(item_posts) == 1                                          # Stimulus not created
    assert "id" not in item_posts[0][1]["json"]["item"]["entry"]         # read-only fields stripped
    assert linked == [(5, {"title": "Quiz 1", "type": "Assignment", "content_id": 555,
                           "position": 1, "indent": 0})]


def test_newquiz_group_without_a_mapping_is_dropped_not_sent_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", "true")
    seen = {}
    monkeypatch.setattr(stn.requests, "post",
                        lambda url, **kw: seen.setdefault("data", kw.get("data")) and _Resp(200, {"id": 1}))
    monkeypatch.setattr(stn, "create_module_item", lambda *a, **k: None)
    stn.create_newquizzes_in_modules("https://x", "9", _newquiz_fixture(tmp_path, []), {}, {}, "tok")
    assert "quiz[assignment_group_id]" not in seen["data"]


def test_failed_quiz_create_is_not_mapped_or_linked(tmp_path, monkeypatch):
    monkeypatch.setenv("CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE", "true")
    monkeypatch.setattr(stn.requests, "post", lambda *a, **k: _Resp(422, {"error": "bad"}))
    monkeypatch.setattr(stn, "create_module_item", lambda *a, **k: pytest_fail())
    files = _newquiz_fixture(tmp_path, [_item(1, "Q1")])
    assert stn.create_newquizzes_in_modules("https://x", "9", files, {"m1": 5}, {}, "tok") == {}


def pytest_fail():
    raise AssertionError("must not link a quiz that was never created")

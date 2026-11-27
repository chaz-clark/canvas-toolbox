"""Tests — --migrate-from refuses a target course that isn't empty (#456).

Canvas's content migration can't overwrite: copying into a course that already
has content silently makes a second copy of everything. So before the copy the
tool counts what the target holds, and refuses unless it's empty. A failed read
refuses too: an error must never look like an empty course.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import canvas_sync as cs  # noqa: E402


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._b, self.links = status, body, {}
        self.text = "x"

    def json(self):
        return self._b


def _canvas(monkeypatch, have=None, broken=(), copied_from=()):
    """GET returns `have[kind]` items for a kind (none if absent); the import history
    lists completed copies from `copied_from`; POSTs recorded."""
    posts = []

    def http(method, url, **kw):
        if method == "POST":
            posts.append(url)
            return _Resp(200, {"id": 77})
        kind = url.rsplit("/", 1)[-1]
        if kind == "content_migrations" and "content_migrations" not in broken:
            return _Resp(200, [{"migration_type": "course_copy_importer", "workflow_state": "completed",
                                "settings": {"source_course_id": src}} for src in copied_from])
        if kind in broken:
            return _Resp(401, {"errors": [{"message": "unauthorized"}]})
        return _Resp(200, [{"id": i} for i in range((have or {}).get(kind, 0))])
    monkeypatch.setattr(cs, "_http", http)
    monkeypatch.setattr(cs, "_post", lambda ep, payload: posts.append(ep) or {"id": 77})
    monkeypatch.setattr(cs, "cmd_rebind", lambda *a, **k: 0)
    monkeypatch.setattr(cs, "_get", lambda ep, *a, **k: {"workflow_state": "completed"})
    monkeypatch.setattr(cs.time, "sleep", lambda s: None)
    return posts


def test_a_target_with_content_is_refused_before_anything_is_sent(monkeypatch, capsys):
    posts = _canvas(monkeypatch, have={"modules": 3, "pages": 2})
    assert cs.cmd_migrate_from("100", "200", apply=True) == 2
    out = capsys.readouterr().out
    assert posts == [] and "isn't empty" in out and "3 module(s)" in out and "2 page(s)" in out


def test_an_empty_target_is_copied(monkeypatch):
    posts = _canvas(monkeypatch)
    assert cs.cmd_migrate_from("100", "200", apply=True) == 0
    assert posts == ["/courses/200/content_migrations"]


def test_a_failed_read_is_never_taken_for_empty(monkeypatch, capsys):
    posts = _canvas(monkeypatch, broken=("files",))
    assert cs.cmd_migrate_from("100", "200", apply=True) == 2
    assert posts == [] and "couldn't check" in capsys.readouterr().out


def test_the_preview_says_what_the_target_holds(monkeypatch, capsys):
    posts = _canvas(monkeypatch, have={"assignments": 4})
    assert cs.cmd_migrate_from("100", "200", apply=False) == 0
    out = capsys.readouterr().out
    assert posts == [] and "4 assignment(s)" in out and "would refuse" in out


def test_the_default_assignment_group_doesnt_count(monkeypatch):
    posts = _canvas(monkeypatch, have={"assignment_groups": 1})
    assert cs.cmd_migrate_from("100", "200", apply=True) == 0 and len(posts) == 1


def test_copying_the_same_course_again_is_allowed(monkeypatch, capsys):
    """Canvas updates what it copied before (checked on a local Canvas)."""
    posts = _canvas(monkeypatch, have={"modules": 2}, copied_from=("100",))
    assert cs.cmd_migrate_from("100", "200", apply=True) == 0 and len(posts) == 1
    assert "already holds a copy of course 100" in capsys.readouterr().out


def test_a_target_copied_from_another_course_is_refused(monkeypatch):
    posts = _canvas(monkeypatch, have={"modules": 2}, copied_from=("555",))
    assert cs.cmd_migrate_from("100", "200", apply=True) == 2 and posts == []


def test_an_unreadable_import_history_refuses(monkeypatch, capsys):
    posts = _canvas(monkeypatch, have={"modules": 2}, broken=("content_migrations",))
    assert cs.cmd_migrate_from("100", "200", apply=True) == 2 and posts == []
    assert "import history" in capsys.readouterr().out

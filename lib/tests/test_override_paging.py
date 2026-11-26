"""Tests — paging the overrides list ends (#506).

Canvas's GET /assignments/:id/overrides ignores ?page=: on a hosted sandbox,
pages 1, 2, 3, 50 and 500 all returned the same override with no `Link: next`
(lesson L36). A loop that counts pages until one comes back empty therefore
never ended once an assignment had an override; student_quiz_time_extension's
force-recalc hung for 15+ minutes that way.

Every fake endpoint here behaves like that one: the same items for any page,
and a next link only where the test gives one. The fakes refuse after a few
calls, so a regression fails instead of hanging the suite.
"""
import sys
from pathlib import Path


_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import _override_recalc_helper as helper  # noqa: E402
import student_late_accommodation as sla  # noqa: E402
from _fix_group_override_recalc_python import CanvasClient  # noqa: E402

OVERRIDE = {"id": 7, "title": "Late-work accommodation (no close date)", "student_ids": [100]}


class _Resp:
    def __init__(self, items, next_url=None):
        self._items, self.ok, self.status_code = items, True, 200
        self.links = {"next": {"url": next_url}} if next_url else {}

    def json(self):
        return list(self._items)

    def raise_for_status(self):
        pass


def _ignores_page(items, pages=None, limit=5):
    """A fake GET: `pages` maps a URL to (items, next_url); anything else gets
    `items` with no next link, whatever ?page= says. Refuses past `limit` calls."""
    calls = []

    def get(*args, **kwargs):
        url = kwargs.get("url") or next(a for a in args if isinstance(a, str) and a.startswith("http"))
        calls.append((url, kwargs.get("params")))
        if len(calls) > limit:
            raise AssertionError(f"still paging after {limit} requests: {calls[-1]}")
        if pages and url in pages:
            return _Resp(*pages[url])
        return _Resp(items)
    return get, calls


def test_get_all_stops_when_there_is_no_next_link(monkeypatch):
    get, calls = _ignores_page([OVERRIDE])
    monkeypatch.setattr(helper, "_request_with_backoff", lambda m, url, **k: get(url, **k))
    assert helper._get_all("http://x/api/v1/courses/1/assignments/5/overrides", {}, 10) == [OVERRIDE]
    assert len(calls) == 1


def test_get_all_follows_next_links(monkeypatch):
    first, second = "http://x/a?page=1", "http://x/a?page=2&per_page=100"
    get, calls = _ignores_page([], pages={first: ([{"id": 1}], second), second: ([{"id": 2}], None)})
    monkeypatch.setattr(helper, "_request_with_backoff", lambda m, url, **k: get(url, **k))
    assert [o["id"] for o in helper._get_all(first, {}, 10)] == [1, 2]
    assert calls[1] == (second, None)  # the next link carries its own query string


def test_force_recalc_for_student_ends_with_an_override_present(monkeypatch):
    """The hang itself: one assignment, one override for the student."""
    get, calls = _ignores_page([OVERRIDE])
    monkeypatch.setattr(helper, "_request_with_backoff", lambda m, url, **k: get(url, **k))
    touched = []
    monkeypatch.setattr(helper, "touch_override", lambda *a, **k: touched.append(a[3]))
    n = helper.force_recalc_for_student("http://x", {}, 1, 100, assignment_id=5, quiet=True)
    assert n == 1 and touched == [5]


def test_force_recalc_for_group_ends_with_an_override_present(monkeypatch):
    group_override = {"id": 8, "group_id": 42}
    get, calls = _ignores_page([group_override])
    monkeypatch.setattr(helper, "_request_with_backoff", lambda m, url, **k: get(url, **k))
    monkeypatch.setattr(helper, "touch_override", lambda *a, **k: None)
    assert helper.force_recalc_for_group("http://x", {}, 1, 42, assignment_id=5, quiet=True) == 1


def test_late_accommodation_list_overrides_ends_and_reads_every_page(monkeypatch):
    first = "http://x/api/v1/courses/1/assignments/5/overrides"
    second = first + "?page=2&per_page=100"
    get, calls = _ignores_page([], pages={first: ([{"id": 1}], second), second: ([OVERRIDE], None)})
    monkeypatch.setattr(sla.requests, "get", get)
    assert [o["id"] for o in sla.list_overrides("http://x", "1", 5, "t")] == [1, 7]


def test_group_recalc_tool_paging_ends(monkeypatch):
    api = CanvasClient("http://x", "t")
    get, calls = _ignores_page([OVERRIDE])
    monkeypatch.setattr(api.session, "get", get)
    assert api.get_overrides(1, 5) == [OVERRIDE]
    assert len(calls) == 1


# --- the touch re-sends the override exactly as it is (#506) --------------------

from _override_recalc_helper import build_touch_payload  # noqa: E402


def test_touch_keeps_every_student_on_a_shared_override():
    """One key per id kept only the last student; the PUT dropped the others."""
    fields = build_touch_payload({"id": 1, "title": "3 students", "student_ids": [100, 200, 300]})
    assert [v for k, v in fields if k == "assignment_override[student_ids][]"] == [100, 200, 300]


def test_touch_keeps_a_late_grace_with_no_until_date():
    """lock_at overridden as null must go back empty, or the assignment's Until date returns."""
    fields = dict(build_touch_payload({"id": 1, "title": "Late-work accommodation (no close date)",
                                       "due_at": "2026-04-15T23:59:00Z", "lock_at": None,
                                       "student_ids": [100]}))
    assert fields["assignment_override[lock_at]"] == ""
    assert fields["assignment_override[due_at]"] == "2026-04-15T23:59:00Z"
    assert "assignment_override[unlock_at]" not in fields  # not overridden: not sent


def test_group_tool_touch_keeps_a_null_until_date(monkeypatch):
    api = CanvasClient("http://x", "t")
    sent = {}

    class Ok:
        ok = True
    monkeypatch.setattr(api.session, "put", lambda url, data, timeout: sent.update(data) or Ok())
    api.touch_override(1, 5, {"id": 9, "title": "g", "group_id": 42, "lock_at": None, "due_at": "d"})
    assert sent["assignment_override[lock_at]"] == "" and sent["assignment_override[due_at]"] == "d"


def test_get_all_stops_on_a_next_link_it_has_already_read(monkeypatch):
    loop = "http://x/a?page=1"
    get, calls = _ignores_page([], pages={loop: ([{"id": 1}], loop)})
    monkeypatch.setattr(helper, "_request_with_backoff", lambda m, url, **k: get(url, **k))
    assert helper._get_all(loop, {}, 10) == [{"id": 1}] and len(calls) == 1


def test_group_recalc_tool_uses_the_python_version(monkeypatch):
    """The Rust binary still has the paging and touch bugs (#518): never run it."""
    import fix_group_override_recalc as fg
    import _fix_group_override_recalc_python as py
    called = {}
    monkeypatch.setattr(py, "run_python_fallback", lambda **k: called.update(k) or 0)
    monkeypatch.setattr(fg.subprocess if hasattr(fg, "subprocess") else py, "run",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran a subprocess")), raising=False)
    for k, v in {"CANVAS_BASE_URL": "http://127.0.0.1:9", "CANVAS_API_TOKEN": "x"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "argv", ["fix_group_override_recalc.py", "--course-id", "1",
                                      "--group-id", "42", "--dry-run"])
    assert fg.main() == 0 and called["group_id"] == 42

"""Tests — paging the overrides list ends (#506).

Canvas's GET /assignments/:id/overrides ignores ?page=: on a hosted sandbox,
pages 1, 2, 3 and 50 all returned the same override with no `Link: next`
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

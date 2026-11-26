"""exempt_by_date: the excuse write key, response verification, --assignment-ids."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import exempt_by_date as ebd  # noqa: E402


class _Resp:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def json(self):
        return self._body


def _capture_put(monkeypatch, body):
    sent = {}

    def fake_put(url, headers, json, timeout):
        sent["json"] = json
        return _Resp(body)

    monkeypatch.setattr(ebd.requests, "put", fake_put)
    return sent


def test_excuse_sends_excuse_key(monkeypatch):
    # Canvas's write key is `excuse`; `excused` is silently ignored with a 200.
    sent = _capture_put(monkeypatch, {"excused": True})
    assert ebd.excuse_submission("https://x", "1", 2, 3, "t") is True
    assert sent["json"] == {"submission": {"excuse": True}}


def test_excuse_fails_when_canvas_ignores_it(monkeypatch):
    _capture_put(monkeypatch, {"excused": False})
    assert ebd.excuse_submission("https://x", "1", 2, 3, "t") is False


def test_unexcuse_sends_excuse_false_and_verifies(monkeypatch):
    sent = _capture_put(monkeypatch, {"excused": False})
    assert ebd.unexcuse_submission("https://x", "1", 2, 3, "t") is True
    assert sent["json"] == {"submission": {"excuse": False}}
    _capture_put(monkeypatch, {"excused": True})
    assert ebd.unexcuse_submission("https://x", "1", 2, 3, "t") is False


ASSIGNMENTS = [
    {"id": 10, "name": "M4", "due_at": "2026-11-15T06:59:00Z", "points_possible": 100},
    {"id": 11, "name": "M5", "due_at": "2026-11-22T06:59:00Z", "points_possible": 100},
    {"id": 12, "name": "M6", "due_at": "2026-11-29T06:59:00Z", "points_possible": 100},
]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("CANVAS_API_TOKEN", "t")
    monkeypatch.setenv("CANVAS_BASE_URL", "https://x")
    monkeypatch.setenv("CANVAS_COURSE_ID", "1")
    monkeypatch.setattr(ebd, "load_env", lambda: None)
    monkeypatch.setattr(ebd, "fetch_published_assignments", lambda *a: ASSIGNMENTS)
    excused = []
    monkeypatch.setattr(
        ebd, "excuse_submission",
        lambda base, cid, aid, uid, tok: excused.append(aid) or True)
    return excused


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["exempt_by_date.py", *argv])
    return ebd.main()


def test_assignment_ids_excuses_only_those(monkeypatch, env):
    assert _run(monkeypatch, "--user-id", "5", "--assignment-ids", "11,12",
                "--apply") == 0
    assert sorted(env) == [11, 12]


def test_assignment_ids_dry_run_writes_nothing(monkeypatch, env):
    assert _run(monkeypatch, "--user-id", "5", "--assignment-ids", "11") == 0
    assert env == []


def test_assignment_ids_unknown_id_refuses_before_writing(monkeypatch, env):
    assert _run(monkeypatch, "--user-id", "5", "--assignment-ids", "11,999",
                "--apply") == 1
    assert env == []


def test_assignment_ids_rejects_non_integer(monkeypatch, env):
    assert _run(monkeypatch, "--user-id", "5", "--assignment-ids", "11,abc") == 1


@pytest.mark.parametrize("ids", ["", ","])
def test_assignment_ids_empty_list_refused(monkeypatch, env, ids):
    assert _run(monkeypatch, "--user-id", "5", "--assignment-ids", ids,
                "--apply") == 1
    assert env == []


def test_failed_excuse_exits_nonzero(monkeypatch, env):
    monkeypatch.setattr(ebd, "excuse_submission", lambda *a: False)
    assert _run(monkeypatch, "--user-id", "5", "--assignment-ids", "11",
                "--apply") == 1


def test_non_json_200_counts_as_not_excused(monkeypatch):
    class _BadJson(_Resp):
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(ebd.requests, "put", lambda *a, **k: _BadJson(None))
    assert ebd.excuse_submission("https://x", "1", 2, 3, "t") is False
    assert ebd.unexcuse_submission("https://x", "1", 2, 3, "t") is False


def test_before_date_still_works(monkeypatch, env):
    assert _run(monkeypatch, "--user-id", "5", "--before-date", "2026-11-20",
                "--apply") == 0
    assert env == [10]


# --- #523: assignments are picked by THIS student's Due date ------------------

def test_assignments_are_read_as_the_student_sees_them(monkeypatch):
    """In the Teacher role, a course read applies other students' overrides
    (lesson L39); the student's own view gives their own Due dates."""
    calls = []

    class R:
        def __init__(self, body, nxt=None):
            self._b, self.links = body, ({"next": {"url": nxt}} if nxt else {})
        def raise_for_status(self):
            pass
        def json(self):
            return self._b
    first = "http://x/api/v1/users/900001/courses/1/assignments"
    pages = {first: R([{"id": 1, "published": True, "due_at": "2026-02-01T06:59:00Z"}], first + "?page=2"),
             first + "?page=2": R([{"id": 2, "published": True, "due_at": None},
                                   {"id": 3, "published": False, "due_at": "2026-02-01T06:59:00Z"}])}

    def get(url, headers=None, params=None, timeout=None):
        calls.append(url)
        # The student's own dates are the point: never the assignment's own instead.
        assert "override_assignment_dates" not in (params or {})
        return pages[url]
    monkeypatch.setattr(ebd.requests, "get", get)
    out = ebd.fetch_published_assignments("http://x", "1", "t", 900001)
    assert [a["id"] for a in out] == [1]  # published and dated only
    assert calls == [first, first + "?page=2"]  # the student's view, every page by the Link header


def test_the_students_own_due_date_decides(monkeypatch, env):
    """A student rescheduled past the cutoff still has that work to do."""
    mine = [{"id": 10, "published": True, "due_at": "2026-02-20T06:59:00Z", "name": "moved for me"},
            {"id": 11, "published": True, "due_at": "2026-02-01T06:59:00Z", "name": "due before"}]
    monkeypatch.setattr(ebd, "fetch_published_assignments",
                        lambda base, cid, tok, uid: mine if uid == 900001 else [])
    assert _run(monkeypatch, "--user-id", "900001", "--before-date", "2026-02-15", "--apply") == 0
    assert env == [11]


def test_paging_stops_on_a_next_link_already_read(monkeypatch):
    loop = "http://x/api/v1/users/900001/courses/1/assignments"

    class R:
        links = {"next": {"url": loop}}
        def raise_for_status(self):
            pass
        def json(self):
            return [{"id": 1, "published": True, "due_at": "2026-02-01T06:59:00Z"}]
    calls = []
    monkeypatch.setattr(ebd.requests, "get", lambda url, **k: calls.append(url) or R())
    assert [a["id"] for a in ebd.fetch_published_assignments("http://x", "1", "t", 900001)] == [1]
    assert len(calls) == 1

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

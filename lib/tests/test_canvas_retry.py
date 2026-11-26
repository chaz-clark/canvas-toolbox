"""Tests — Canvas calls survive a dropped connection without duplicating (#445).

Instructors report the Canvas connection dropping during long tasks. A read or
an update (GET/PUT/DELETE) is safe to send again, so it's retried with a pause.
A create (POST) that may already have reached Canvas is NOT sent again: that is
how announcements and assignments got duplicated. It raises UnsureWrite so the
caller can say "check before running it again". Sleeps are recorded, not taken.
"""
import sys
from pathlib import Path

import pytest
import requests

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import _canvas_retry as cr  # noqa: E402


class _Resp:
    def __init__(self, status, headers=None):
        self.status_code, self.headers, self.text = status, headers or {}, ""


def _fake(monkeypatch, outcomes):
    """requests.request returns/raises each outcome in turn; records calls."""
    calls = []

    def make(method):
        def call(url, **kwargs):
            calls.append(method)
            o = outcomes[len(calls) - 1]
            if isinstance(o, Exception):
                raise o
            return o
        return call
    for m in ("get", "put", "post", "patch", "delete"):
        monkeypatch.setattr(cr.requests, m, make(m.upper()))
    return calls


def _refused():
    """What requests raises when the connection was never made."""
    return requests.exceptions.ConnectionError(
        "HTTPSConnectionPool: Max retries exceeded (Caused by NewConnectionError("
        "'Failed to establish a new connection: [Errno 61] Connection refused'))")


def test_an_update_is_retried_through_a_dropped_connection(monkeypatch):
    calls = _fake(monkeypatch, [requests.exceptions.ConnectionError("Connection aborted."),
                                requests.exceptions.ReadTimeout("read timed out"), _Resp(200)])
    waits = []
    r = cr.request("PUT", "https://x/api/v1/courses/1/pages/a", sleep=waits.append)
    assert r.status_code == 200 and calls == ["PUT"] * 3 and waits == [2, 5]


def test_slow_down_and_busy_responses_are_retried_and_retry_after_is_honoured(monkeypatch):
    calls = _fake(monkeypatch, [_Resp(429, {"Retry-After": "7"}), _Resp(503), _Resp(200)])
    waits = []
    assert cr.request("GET", "https://x", sleep=waits.append).status_code == 200
    assert waits == [7, 5] and len(calls) == 3


def test_it_gives_up_after_four_attempts(monkeypatch):
    calls = _fake(monkeypatch, [requests.exceptions.ConnectionError("reset")] * 4)
    with pytest.raises(requests.exceptions.ConnectionError):
        cr.request("GET", "https://x", sleep=lambda s: None)
    assert len(calls) == 4


def test_a_create_that_may_have_landed_is_never_sent_twice(monkeypatch):
    """The issue's test: Canvas created it, then the reply was lost."""
    calls = _fake(monkeypatch, [requests.exceptions.ReadTimeout("read timed out"), _Resp(201)])
    with pytest.raises(cr.UnsureWrite) as e:
        cr.request("POST", "https://x/api/v1/courses/1/discussion_topics", sleep=lambda s: None)
    assert calls == ["POST"]  # one attempt only: no duplicate
    assert "check" in str(e.value).lower()


def test_a_create_that_never_reached_canvas_is_retried(monkeypatch):
    calls = _fake(monkeypatch, [_refused(), _Resp(429), _Resp(201)])
    assert cr.request("POST", "https://x", sleep=lambda s: None).status_code == 201
    assert len(calls) == 3


def test_a_create_answered_by_a_gateway_error_is_unsure(monkeypatch):
    """A 502/504 may come after Canvas has done the work."""
    calls = _fake(monkeypatch, [_Resp(504), _Resp(201)])
    with pytest.raises(cr.UnsureWrite):
        cr.request("POST", "https://x", sleep=lambda s: None)
    assert calls == ["POST"]


def test_a_post_marked_safe_to_repeat_is_retried(monkeypatch):
    calls = _fake(monkeypatch, [requests.exceptions.ReadTimeout("t"), _Resp(200)])
    assert cr.request("POST", "https://x", safe_to_repeat=True, sleep=lambda s: None).status_code == 200
    assert len(calls) == 2


def test_errors_that_arent_about_the_connection_are_returned_at_once(monkeypatch):
    calls = _fake(monkeypatch, [_Resp(404)])
    assert cr.request("PUT", "https://x", sleep=lambda s: None).status_code == 404
    assert len(calls) == 1


# --- canvas_sync uses it --------------------------------------------------------

def test_canvas_sync_update_reports_a_connection_failure_instead_of_crashing(monkeypatch):
    import canvas_sync as cs
    _fake(monkeypatch, [requests.exceptions.ConnectionError("reset")] * 4)
    monkeypatch.setattr(cr.time, "sleep", lambda s: None)
    out = cs._put("/courses/1/pages/a", {"wiki_page": {"body": "x"}})
    assert out.get("error") and "Canvas didn't answer" in out["error"]


def test_canvas_sync_create_that_may_have_landed_is_marked_unsure(monkeypatch):
    import canvas_sync as cs
    _fake(monkeypatch, [requests.exceptions.ReadTimeout("t"), _Resp(201)])
    out = cs._post("/courses/1/content_migrations", {"migration_type": "x"})
    assert out.get("unsure") is True and out.get("error")


def test_the_retry_line_names_the_next_attempt(monkeypatch, capsys):
    _fake(monkeypatch, [requests.exceptions.ConnectionError("reset"), _Resp(200)])
    cr.request("GET", "https://x", sleep=lambda s: None)
    assert "trying again in 2 s (attempt 2 of 4)" in capsys.readouterr().err

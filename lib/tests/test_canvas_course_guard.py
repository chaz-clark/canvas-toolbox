"""Tier 1 unit tests — canvas_course_guard (#27).

Source: lib/tools/canvas_course_guard.py
  - check_course_safety   (verdict from total_students + blueprint_subscriptions + workflow_state)
  - enforce               (block write / advise / proceed)

The guard is safety-critical and had zero coverage. The property under test:
a write to a LIVE enrolled course hard-stops (exit 2) unless overridden, but an
enrolled course that is still UNPUBLISHED — students can't see it, e.g. a section
built before term start — proceeds with an advisory and no override needed.
A Blueprint child still hard-stops regardless of publish state.

No network. requests.get is monkeypatched.
"""
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import canvas_course_guard as guard  # noqa: E402
from canvas_course_guard import (  # noqa: E402
    BLUEPRINT_CHILD,
    ENROLLED,
    ENROLLED_AND_BLUEPRINT_CHILD,
    ENROLLED_UNPUBLISHED,
    ERROR,
    SAFE,
    check_course_safety,
    enforce,
)

_BASE = "https://x.instructure.com"
_HEADERS = {"Authorization": "Bearer t"}
_CID = "423164"


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    @property
    def content(self):
        return b"x" if self._payload is not None else b""

    def json(self):
        return self._payload


def _mock(monkeypatch, *, total_students=0, workflow_state="available",
          subs=None, course_status=200, subs_status=200):
    """Wire requests.get for the two calls the guard makes."""
    def fake_get(url, **kw):
        if url.endswith("/blueprint_subscriptions"):
            return _Resp(subs if subs is not None else [], status=subs_status)
        return _Resp(
            {"name": "Test Course", "total_students": total_students,
             "workflow_state": workflow_state},
            status=course_status,
        )
    monkeypatch.setattr(guard.requests, "get", fake_get)


# ---------------------------------------------------------------------------
# check_course_safety — verdict classification
# ---------------------------------------------------------------------------

def test_no_enrollment_no_blueprint_is_safe(monkeypatch):
    _mock(monkeypatch, total_students=0)
    verdict, _reasons, name = check_course_safety(_BASE, _HEADERS, _CID)
    assert verdict == SAFE
    assert name == "Test Course"


def test_enrolled_and_published_is_enrolled(monkeypatch):
    _mock(monkeypatch, total_students=25, workflow_state="available")
    verdict, reasons, _ = check_course_safety(_BASE, _HEADERS, _CID)
    assert verdict == ENROLLED
    assert "25 enrolled students" in reasons


@pytest.mark.parametrize("state", ["unpublished", "created", "claimed"])
def test_enrolled_but_prepublish_is_enrolled_unpublished(monkeypatch, state):
    _mock(monkeypatch, total_students=25, workflow_state=state)
    verdict, reasons, _ = check_course_safety(_BASE, _HEADERS, _CID)
    assert verdict == ENROLLED_UNPUBLISHED
    assert any("cannot see it yet" in r for r in reasons)


def test_blueprint_child_beats_unpublished(monkeypatch):
    """A Blueprint child hard-stops even when unpublished — the risk there is
    content propagation, not student exposure."""
    _mock(monkeypatch, total_students=25, workflow_state="unpublished",
          subs=[{"id": 1}])
    verdict, _reasons, _ = check_course_safety(_BASE, _HEADERS, _CID)
    assert verdict == ENROLLED_AND_BLUEPRINT_CHILD


def test_blueprint_child_no_enrollment(monkeypatch):
    _mock(monkeypatch, total_students=0, subs=[{"id": 1}])
    verdict, _reasons, _ = check_course_safety(_BASE, _HEADERS, _CID)
    assert verdict == BLUEPRINT_CHILD


def test_course_fetch_4xx_is_error(monkeypatch):
    _mock(monkeypatch, course_status=500)
    verdict, _reasons, _ = check_course_safety(_BASE, _HEADERS, _CID)
    assert verdict == ERROR


def test_subs_endpoint_403_does_not_downgrade_verdict(monkeypatch):
    """Many courses 4xx on blueprint_subscriptions; the course-object call
    already told us what we needed."""
    _mock(monkeypatch, total_students=25, workflow_state="available",
          subs_status=403)
    verdict, _reasons, _ = check_course_safety(_BASE, _HEADERS, _CID)
    assert verdict == ENROLLED


# ---------------------------------------------------------------------------
# enforce — block / advise / proceed
# ---------------------------------------------------------------------------

def test_enforce_safe_write_is_silent(monkeypatch, capsys):
    _mock(monkeypatch, total_students=0)
    enforce(_BASE, _HEADERS, _CID, mode="write")
    assert capsys.readouterr().err == ""


def test_enforce_live_enrolled_write_exits_2(monkeypatch):
    _mock(monkeypatch, total_students=25, workflow_state="available")
    with pytest.raises(SystemExit) as exc:
        enforce(_BASE, _HEADERS, _CID, mode="write")
    assert exc.value.code == 2


def test_enforce_live_enrolled_write_proceeds_with_override(monkeypatch, capsys):
    _mock(monkeypatch, total_students=25, workflow_state="available")
    enforce(_BASE, _HEADERS, _CID, mode="write", allow_override=True)
    assert "proceeding with write despite" in capsys.readouterr().err


def test_enforce_unpublished_enrolled_write_proceeds_without_override(monkeypatch, capsys):
    """The case the guard was over-blocking: enrolled section, term not started."""
    _mock(monkeypatch, total_students=25, workflow_state="unpublished")
    enforce(_BASE, _HEADERS, _CID, mode="write")  # no allow_override
    err = capsys.readouterr().err
    assert "cannot see this course yet; proceeding" in err


def test_enforce_unpublished_but_blueprint_child_still_exits_2(monkeypatch):
    _mock(monkeypatch, total_students=25, workflow_state="unpublished",
          subs=[{"id": 1}])
    with pytest.raises(SystemExit) as exc:
        enforce(_BASE, _HEADERS, _CID, mode="write")
    assert exc.value.code == 2


def test_enforce_read_mode_is_advisory_never_blocks(monkeypatch, capsys):
    _mock(monkeypatch, total_students=25, workflow_state="available")
    enforce(_BASE, _HEADERS, _CID, mode="read")
    assert "advisory" in capsys.readouterr().err.lower()


def test_enforce_guard_error_never_blocks(monkeypatch, capsys):
    _mock(monkeypatch, course_status=500)
    enforce(_BASE, _HEADERS, _CID, mode="write")
    assert "Proceeding without the check" in capsys.readouterr().err


def test_enforce_rejects_bad_mode(monkeypatch):
    _mock(monkeypatch, total_students=0)
    with pytest.raises(ValueError):
        enforce(_BASE, _HEADERS, _CID, mode="delete")

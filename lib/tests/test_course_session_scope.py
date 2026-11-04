"""Session scope lock (#444): writes outside the folder's declared courses are refused."""
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import canvas_course_guard as g  # noqa: E402


@pytest.fixture(autouse=True)
def env(monkeypatch):
    import os
    for k in list(os.environ):
        if k.endswith("COURSE_ID") or k == "CB_COURSE_SWITCH":
            monkeypatch.delenv(k)
    monkeypatch.setenv("MASTER_COURSE_ID", "111")
    monkeypatch.setenv("S1_COURSE_ID", "222")


def test_declared_courses_pass():
    g.check_session_scope("111", "write")
    g.check_session_scope(222, "write")


def test_write_to_other_course_is_refused(capsys):
    with pytest.raises(SystemExit) as e:
        g.check_session_scope("999", "write", "grade target")
    assert e.value.code == 2
    assert "REFUSING WRITE" in capsys.readouterr().err


def test_read_of_other_course_only_warns(capsys):
    g.check_session_scope("999", "read")
    assert "Read-only" in capsys.readouterr().err


def test_explicit_switch_is_per_id(monkeypatch):
    monkeypatch.setenv("CB_COURSE_SWITCH", "999")
    g.check_session_scope("999", "write")
    with pytest.raises(SystemExit):
        g.check_session_scope("888", "write")


def test_no_declared_scope_means_no_lock(monkeypatch):
    monkeypatch.delenv("MASTER_COURSE_ID")
    monkeypatch.delenv("S1_COURSE_ID")
    g.check_session_scope("999", "write")


def test_enforce_applies_the_lock_before_any_api_call(monkeypatch):
    monkeypatch.setattr(g, "check_course_safety",
                        lambda *a: pytest.fail("API called before scope check"))
    with pytest.raises(SystemExit):
        g.enforce("https://x", {}, "999", mode="write")

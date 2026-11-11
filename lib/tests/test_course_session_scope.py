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


def test_parent_folder_with_several_courses_is_detected(tmp_path):
    for n in ("course1", "course2", "course3"):
        (tmp_path / n).mkdir()
        (tmp_path / n / ".env").write_text("CANVAS_COURSE_ID=1\n")
    assert g.opened_above_courses(tmp_path)
    assert not g.opened_above_courses(tmp_path / "course1")      # inside a course: fine


def test_single_child_or_course_root_is_not_flagged(tmp_path):
    (tmp_path / "only").mkdir()
    (tmp_path / "only" / "AGENTS.md").write_text("x")
    assert not g.opened_above_courses(tmp_path)                  # one course: not ambiguous
    (tmp_path / "AGENTS.md").write_text("x")
    assert not g.opened_above_courses(tmp_path)                  # the folder is itself a course


def test_enforce_refuses_write_from_parent_folder(tmp_path, monkeypatch, capsys):
    for n in ("a", "b"):
        (tmp_path / n).mkdir()
        (tmp_path / n / ".env").write_text("X=1\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(g, "check_course_safety", lambda *a: pytest.fail("API called"))
    with pytest.raises(SystemExit) as e:
        g.enforce("https://x", {}, "111", mode="write")
    assert e.value.code == 2
    assert "one course folder per VS Code Window" in capsys.readouterr().err


# ── The guard must be recoverable: every refusal has a fix that actually unblocks ──
# A guard that blocks and then stays blocked (sticky state, cached verdict) would be
# worse than none. It is stateless, so these prove each documented fix works in the
# SAME process right after a refusal.

def test_scope_refusal_clears_when_course_is_added_to_env(monkeypatch):
    with pytest.raises(SystemExit):
        g.check_session_scope("999", "write")
    monkeypatch.setenv("S2_COURSE_ID", "999")        # the instructor fixes their .env
    g.check_session_scope("999", "write")            # no exit now


def test_scope_refusal_clears_with_the_explicit_switch_then_returns(monkeypatch):
    with pytest.raises(SystemExit):
        g.check_session_scope("999", "write")
    monkeypatch.setenv("CB_COURSE_SWITCH", "999")
    g.check_session_scope("999", "write")            # allowed for this command
    monkeypatch.delenv("CB_COURSE_SWITCH")
    with pytest.raises(SystemExit):                  # and not sticky: blocked again
        g.check_session_scope("999", "write")


def test_parent_folder_refusal_clears_after_opening_a_course_folder(tmp_path, monkeypatch):
    for n in ("a", "b"):
        (tmp_path / n).mkdir()
        (tmp_path / n / ".env").write_text("X=1\n")
    monkeypatch.setattr(g, "check_course_safety", lambda *a: (g.SAFE, [], "c"))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        g.enforce("https://x", {}, "111", mode="write")      # opened too high
    monkeypatch.chdir(tmp_path / "a")                        # the fix: open one course
    monkeypatch.setenv("CANVAS_COURSE_ID", "111")
    g.enforce("https://x", {}, "111", mode="write")          # proceeds

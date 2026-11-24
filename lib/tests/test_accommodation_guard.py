"""Tests — the accommodation tools run the course guard, in its per-student mode (#475).

P-LL4: every write tool calls canvas_course_guard.enforce() before it changes
anything. The four one-student tools never did. Their normal target is a live
course (a student's own section, often a Blueprint child), so the guard's
per_student mode names that course in an advisory instead of refusing it. What
still refuses: a folder opened above several courses, and a course outside the
folder's declared scope (CB_COURSE_SWITCH aside).

No network. The guard's own tests stub requests.get; the end-to-end runs point
Canvas at a dead local address and expect the refusal before any call matters.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import canvas_course_guard as guard  # noqa: E402
from canvas_course_guard import enforce  # noqa: E402

_BASE, _HEADERS, _CID = "https://x.instructure.com", {"Authorization": "Bearer t"}, "423164"

# tool -> the smallest argv that reaches a write with --apply, by --user-id only
TOOLS = {
    "exempt_by_date": ["--user-id", "900001", "--assignment-ids", "5"],
    "student_late_accommodation": ["--user-id", "900001", "--assignment-id", "5"],
    "student_quiz_time_extension": ["--user-id", "900001", "--quiz-id", "5",
                                    "--multiplier", "1.5"],
    "submit_on_behalf": ["--user-id", "900001", "--assignment-id", "5",
                         "--file", "essay.txt"],
}


class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code, self.text = payload, status, str(payload)

    @property
    def content(self):
        return b"x"

    def json(self):
        return self._payload


def _course(monkeypatch, *, total_students=30, subs=()):
    def fake_get(url, **kw):
        if url.endswith("/blueprint_subscriptions"):
            return _Resp(list(subs))
        return _Resp({"name": "Live Section", "total_students": total_students,
                      "workflow_state": "available"})
    monkeypatch.setattr(guard.requests, "get", fake_get)


@pytest.fixture
def one_course(monkeypatch, tmp_path):
    """A course folder whose .env declares _CID, opened on its own."""
    for k in list(os.environ):
        if k.endswith("COURSE_ID") or k == "CB_COURSE_SWITCH":
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CANVAS_COURSE_ID", _CID)
    monkeypatch.chdir(tmp_path)


# --- the guard's per-student mode -------------------------------------------

def test_a_live_course_is_allowed_with_an_advisory(monkeypatch, capsys, one_course):
    _course(monkeypatch, total_students=30)
    enforce(_BASE, _HEADERS, _CID, mode="write", per_student=True)   # no SystemExit
    err = capsys.readouterr().err
    assert "Live Section" in err and "30 enrolled students" in err and "proceeding" in err


def test_a_blueprint_child_section_is_allowed_with_an_advisory(monkeypatch, capsys, one_course):
    _course(monkeypatch, total_students=30, subs=[{"id": 1}])
    enforce(_BASE, _HEADERS, _CID, mode="write", per_student=True)
    assert "Blueprint child" in capsys.readouterr().err


def test_without_per_student_a_live_course_is_still_refused(monkeypatch, one_course):
    """The other writers keep the 2.7.2 behaviour."""
    _course(monkeypatch, total_students=30)
    with pytest.raises(SystemExit) as exc:
        enforce(_BASE, _HEADERS, _CID, mode="write")
    assert exc.value.code == 2


def test_a_course_outside_the_folder_is_refused(monkeypatch, capsys, one_course):
    _course(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        enforce(_BASE, _HEADERS, "999999", mode="write", per_student=True)
    assert exc.value.code == 2
    assert "not one of this folder's courses" in capsys.readouterr().err


def test_a_folder_above_several_courses_is_refused(monkeypatch, tmp_path, one_course):
    for name in ("course-a", "course-b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / ".env").write_text("CANVAS_COURSE_ID=1\n", encoding="utf-8")
    _course(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        enforce(_BASE, _HEADERS, _CID, mode="write", per_student=True)
    assert exc.value.code == 2


def test_a_dry_run_never_refuses(monkeypatch, one_course):
    _course(monkeypatch)
    enforce(_BASE, _HEADERS, "999999", mode="read", per_student=True)  # advisory only


# --- every one-student tool calls it, before any write -----------------------

@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_each_tool_calls_the_guard_in_per_student_mode(tool):
    src = (_TOOLS_DIR / f"{tool}.py").read_text(encoding="utf-8")
    calls = re.findall(r"_course_guard\((.*?)\)\n", src, re.S)
    assert len(calls) == 1, f"{tool}.py should call the course guard once"
    assert "per_student=True" in calls[0]
    assert 'mode="write" if args.apply else "read"' in calls[0]
    first_write = min(src.find(f"requests.{verb}(") for verb in ("put", "post", "delete")
                      if f"requests.{verb}(" in src)
    main_at = src.find("def main(")
    assert first_write < main_at < src.find("_course_guard(base_url"), \
        "the guard call belongs in main(), after the helpers that write"


@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_each_tool_refuses_from_a_folder_above_several_courses(tool, tmp_path):
    """End to end: --apply from the wrong folder stops before anything is sent."""
    for name in ("course-a", "course-b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / ".env").write_text("CANVAS_COURSE_ID=1\n", encoding="utf-8")
    (tmp_path / "essay.txt").write_text("x\n", encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path),
           "CANVAS_API_TOKEN": "x", "CANVAS_BASE_URL": "http://127.0.0.1:9",
           "CANVAS_COURSE_ID": _CID}
    r = subprocess.run([sys.executable, str(_TOOLS_DIR / f"{tool}.py"), *TOOLS[tool], "--apply"],
                       capture_output=True, text=True, timeout=60, cwd=tmp_path, env=env)
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "REFUSING WRITE" in r.stderr

"""Tests — fix_group_override_recalc runs the course guard (#502).

#475 gave the four one-student tools the course guard, set for an intervention.
This tool was left out, and it's the one where the out-of-folder check matters
most: it takes --course-id on the command line instead of reading
CANVAS_COURSE_ID. The guard runs in the wrapper, before the Rust version or the
Python one starts. The runs here point Canvas at a dead local address; the
refusals come before any call matters.
"""
import os
import subprocess
import sys
from pathlib import Path

_TOOL = Path(__file__).resolve().parent.parent / "tools" / "fix_group_override_recalc.py"


def _run(tmp_path, *args, extra_env=None, cwd=None):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path),
           "CANVAS_API_TOKEN": "x", "CANVAS_BASE_URL": "http://127.0.0.1:9",
           "CANVAS_COURSE_ID": "423164", **(extra_env or {})}
    return subprocess.run([sys.executable, str(_TOOL), *args], capture_output=True, text=True,
                          timeout=120, cwd=cwd or tmp_path, env=env)


def test_a_course_outside_the_folder_is_refused(tmp_path):
    r = _run(tmp_path, "--course-id", "999999", "--student-id", "900001")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "REFUSING WRITE" in r.stderr and "999999 is not one of this folder's courses" in r.stderr


def test_cb_course_switch_allows_that_course(tmp_path):
    r = _run(tmp_path, "--course-id", "999999", "--student-id", "900001",
             extra_env={"CB_COURSE_SWITCH": "999999"})
    assert "REFUSING WRITE" not in r.stderr, r.stderr
    assert "CB_COURSE_SWITCH allows it" in r.stderr


def test_a_folder_above_several_courses_is_refused(tmp_path):
    for name in ("course-a", "course-b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / ".env").write_text("CANVAS_COURSE_ID=1\n", encoding="utf-8")
    r = _run(tmp_path, "--course-id", "423164", "--group-id", "42")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "REFUSING WRITE" in r.stderr


def test_a_preview_of_another_course_only_warns(tmp_path):
    r = _run(tmp_path, "--course-id", "999999", "--student-id", "900001", "--dry-run")
    assert "REFUSING WRITE" not in r.stderr
    assert "Read-only; proceeding" in r.stderr


def test_the_guard_runs_before_either_version_starts():
    src = _TOOL.read_text(encoding="utf-8")
    main_at = src.index("def main(")
    guard_at = src.index("_course_guard(", main_at)
    assert guard_at < src.index("rust_binary_ok(rust_bin)", main_at)
    assert guard_at < src.index("run_python_fallback(", main_at)
    assert 'per_student=True' in src[guard_at:guard_at + 300]

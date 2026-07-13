"""cmd_status must report every file cmd_push writes.

cmd_status diffed only index["files"]. But cmd_push ALSO writes the homepage,
the syllabus, and _course.json (late_policy) — each tracked under its own index
key, each hash-gated independently, and all three BEFORE the "Nothing to push"
guard.

So on a live course: edit syllabus.html, run --status, get "Everything up to
date. Nothing to push." — then --push overwrites the live syllabus for enrolled
students. --status is the documented pre-push safety check, so under-reporting
is the dangerous direction to be wrong in.
"""
import importlib.util
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("canvas_sync", TOOLS / "canvas_sync.py")
canvas_sync = importlib.util.module_from_spec(spec)
sys.modules["canvas_sync"] = canvas_sync
spec.loader.exec_module(canvas_sync)


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return canvas_sync._file_hash(path)


def test_no_changes_on_a_freshly_pulled_mirror(tmp_path):
    home = tmp_path / "homepage.html"
    syl = tmp_path / "syllabus.html"
    course = tmp_path / "_course.json"
    index = {
        "homepage": {"filepath": str(home), "hash": _write(home, "<p>home</p>")},
        "syllabus": {"filepath": str(syl), "hash": _write(syl, "<p>syllabus</p>")},
        "course_hash": _write(course, json.dumps({"late_policy": {}})),
    }
    assert canvas_sync._special_file_changes(index, course_path=course) == []


def test_detects_edited_syllabus(tmp_path):
    """The live-course trap: syllabus edited, status must not stay silent."""
    syl = tmp_path / "syllabus.html"
    index = {"syllabus": {"filepath": str(syl), "hash": _write(syl, "<p>original</p>")}}
    syl.write_text("<p>EDITED</p>", encoding="utf-8")

    changes = canvas_sync._special_file_changes(index, course_path=tmp_path / "_course.json")

    assert [label for label, _ in changes] == ["Syllabus"]


def test_detects_edited_homepage_and_course(tmp_path):
    home = tmp_path / "homepage.html"
    course = tmp_path / "_course.json"
    index = {
        "homepage": {"filepath": str(home), "hash": _write(home, "<p>home</p>")},
        "course_hash": _write(course, json.dumps({"late_policy": {"late_percent": 10}})),
    }
    home.write_text("<p>EDITED</p>", encoding="utf-8")
    course.write_text(json.dumps({"late_policy": {"late_percent": 50}}), encoding="utf-8")

    labels = [label for label, _ in canvas_sync._special_file_changes(index, course_path=course)]

    assert labels == ["Homepage", "Course"]


def test_absent_files_are_not_reported(tmp_path):
    """A mirror with no homepage/syllabus must not report phantom changes."""
    index = {"homepage": {"filepath": str(tmp_path / "gone.html"), "hash": "abc"}}
    assert canvas_sync._special_file_changes(index, course_path=tmp_path / "_course.json") == []


def test_empty_index_reports_nothing(tmp_path):
    assert canvas_sync._special_file_changes({}, course_path=tmp_path / "_course.json") == []

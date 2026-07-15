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


def _write_course(path: Path, late_policy: dict, **fields) -> str:
    """Write a realistic _course.json (late_policy + course-level fields) and
    return its late_policy-ONLY hash — what --status/--push actually compare (#182)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"late_policy": late_policy, **fields}), encoding="utf-8")
    return canvas_sync._course_late_policy_hash(path)


def test_no_changes_on_a_freshly_pulled_mirror(tmp_path):
    home = tmp_path / "homepage.html"
    syl = tmp_path / "syllabus.html"
    course = tmp_path / "_course.json"
    index = {
        "homepage": {"filepath": str(home), "hash": _write(home, "<p>home</p>")},
        "syllabus": {"filepath": str(syl), "hash": _write(syl, "<p>syllabus</p>")},
        "course_hash": _write_course(course, {}),
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
        "course_hash": _write_course(course, {"late_percent": 10}),
    }
    home.write_text("<p>EDITED</p>", encoding="utf-8")
    course.write_text(json.dumps({"late_policy": {"late_percent": 50}}), encoding="utf-8")

    labels = [label for label, _ in canvas_sync._special_file_changes(index, course_path=course)]

    assert labels == ["Homepage", "Course"]


def test_name_edit_alone_is_not_flagged(tmp_path):
    """#182: editing a non-pushable field (name) must NOT show as `[Course]`.
    --push only round-trips late_policy, so surfacing a name edit as pending would
    imply a sync that then gets silently dropped."""
    course = tmp_path / "_course.json"
    index = {"course_hash": _write_course(course, {"late_percent": 10}, name="BIO 101")}
    # change ONLY the name; late_policy untouched
    course.write_text(
        json.dumps({"late_policy": {"late_percent": 10}, "name": "BIO 101 - Fall"}),
        encoding="utf-8")

    assert canvas_sync._special_file_changes(index, course_path=course) == []


def test_late_policy_edit_is_flagged_even_with_other_fields(tmp_path):
    """The flip side of #182: a real late_policy change IS flagged, even when the
    file also carries name/dates that never push."""
    course = tmp_path / "_course.json"
    index = {"course_hash": _write_course(course, {"late_percent": 10}, name="BIO 101")}
    course.write_text(
        json.dumps({"late_policy": {"late_percent": 50}, "name": "BIO 101"}),
        encoding="utf-8")

    labels = [label for label, _ in canvas_sync._special_file_changes(index, course_path=course)]

    assert labels == ["Course"]


def test_absent_files_are_not_reported(tmp_path):
    """A mirror with no homepage/syllabus must not report phantom changes."""
    index = {"homepage": {"filepath": str(tmp_path / "gone.html"), "hash": "abc"}}
    assert canvas_sync._special_file_changes(index, course_path=tmp_path / "_course.json") == []


def test_empty_index_reports_nothing(tmp_path):
    assert canvas_sync._special_file_changes({}, course_path=tmp_path / "_course.json") == []


# --- integration: cmd_status() itself must surface the course-level edit ---
#
# The tests above exercise the helper in isolation. This one drives cmd_status()
# end-to-end so the WIRING is covered: a refactor that dropped the
# `_special_file_changes(index)` call would leave every unit test above green
# while silently reintroducing the "Everything up to date" false-negative.


def test_cmd_status_surfaces_a_course_level_edit(tmp_path, monkeypatch, capsys):
    # a regular tracked file that is UP TO DATE -> the only change is course-level
    tracked = tmp_path / "week-1" / "page.html"
    tracked_hash = _write(tracked, "<p>page</p>")
    syl = tmp_path / "syllabus.html"
    index = {
        "files": {str(tracked): {"hash": tracked_hash, "type": "Page"}},
        "syllabus": {"filepath": str(syl), "hash": _write(syl, "<p>original</p>")},
    }
    syl.write_text("<p>EDITED</p>", encoding="utf-8")  # edited since the index hash
    monkeypatch.setattr(canvas_sync, "_load_index", lambda: index)
    monkeypatch.setattr(canvas_sync, "COURSE_DIR", tmp_path)  # for the _course.json default

    canvas_sync.cmd_status()
    out = capsys.readouterr().out

    assert "course-level" in out                 # the special block fired
    assert str(syl) in out                       # the edited syllabus is named
    assert "Everything up to date" not in out    # NOT the dangerous false-negative


# --- the same blind spot, on the way out ----------------------------------
#
# cmd_push's summary also only counted index["files"], so a run that pushed the
# syllabus still ended with "Nothing to push — all files match Canvas.":
#
#     [Syllabus] course/syllabus.html
#         OK
#     Nothing to push — all files match Canvas.
#
# Cosmetic, but it makes an operator doubt a write that landed — or re-run the
# push to "make sure", which is what happened during live verification.


def test_push_summary_reports_a_course_level_push():
    assert canvas_sync._push_summary(["Syllabus"]) == "Pushed 1 course-level file(s): Syllabus"


def test_push_summary_lists_every_file_pushed():
    out = canvas_sync._push_summary(["Homepage", "Course", "Syllabus"])
    assert out == "Pushed 3 course-level file(s): Homepage, Course, Syllabus"


def test_push_summary_still_says_nothing_to_push_when_nothing_was():
    assert canvas_sync._push_summary([]) == "Nothing to push — all files match Canvas."

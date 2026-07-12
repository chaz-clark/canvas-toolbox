"""Tier 1 unit tests — offline_import (.imscc -> course/) (Sprint 6).

Source: lib/tools/offline_import.py

Builds a minimal synthetic .imscc and asserts the produced course/ matches the
API-shaped model the loader expects (assignments with list submission_types,
quizzes shaped as assignments, pages as .html). Gated integration imports the
real DS 250 / DS 460 / ITM 327 / M 119 exports and confirms the loader reads them.
"""
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from offline_import import import_imscc, slugify, assignment_from_xml, quiz_from_xml  # noqa: E402
from _course_loader import load_course  # noqa: E402
import _file_finder  # noqa: E402


def _make_imscc(path: Path):
    files = {
        "imsmanifest.xml":
            '<manifest><resources>'
            '<resource identifier="gCCC" type="webcontent"><file href="wiki_content/overview.html"/></resource>'
            '</resources></manifest>',
        "course_settings/course_settings.xml":
            "<course><title>Sample Course</title><course_code>S 101</course_code>"
            "<start_at>2026-09-01T06:00:00</start_at></course>",
        "course_settings/context.xml": "<context_info><course_id>4242</course_id></context_info>",
        "course_settings/module_meta.xml":
            '<modules><module identifier="m1"><title>Week 1</title>'
            "<workflow_state>active</workflow_state><position>1</position><items>"
            '<item identifier="i1"><content_type>Assignment</content_type>'
            "<workflow_state>active</workflow_state><title>HW 1</title>"
            "<identifierref>gAAA</identifierref></item>"
            '<item identifier="i2"><content_type>Quizzes::Quiz</content_type>'
            "<title>Quiz 1</title><identifierref>gBBB</identifierref></item>"
            '<item identifier="i3"><content_type>WikiPage</content_type>'
            "<title>Overview</title><identifierref>gCCC</identifierref></item>"
            "</items></module></modules>",
        "gAAA/assignment_settings.xml":
            "<assignment><title>HW 1</title><workflow_state>published</workflow_state>"
            "<points_possible>100.0</points_possible><due_at>2026-09-05T05:59:00</due_at>"
            "<submission_types>online_upload,online_text_entry</submission_types>"
            "<assignment_group_identifierref>gGRP1</assignment_group_identifierref>"
            "<grading_type>points</grading_type></assignment>",
        "gAAA/hw-1.html": "<p>Read chapter 1 and submit.</p>",     # assignment description body
        "course_settings/syllabus.html": "<h1>Syllabus</h1><p>Grading policy...</p>",
        "course_settings/assignment_groups.xml":
            '<assignmentGroups><assignmentGroup identifier="gGRP1">'
            "<title>Homework</title><position>1</position><group_weight>100.0</group_weight>"
            "</assignmentGroup></assignmentGroups>",
        "gBBB/assessment_meta.xml":
            "<quiz><title>Quiz 1</title><points_possible>10.0</points_possible>"
            "<due_at>2026-09-12T05:59:00</due_at><quiz_type>assignment</quiz_type></quiz>",
        "wiki_content/overview.html": "<p>hi</p>",
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return path


# --- field mapping ---------------------------------------------------------

def test_assignment_mapping():
    xml = ("<a><title>HW</title><workflow_state>published</workflow_state>"
           "<points_possible>50.0</points_possible><due_at>2026-09-05T05:59:00</due_at>"
           "<submission_types>online_upload,online_text_entry</submission_types></a>")
    d = assignment_from_xml(xml, None)
    assert d["name"] == "HW"
    assert d["published"] is True
    assert d["points_possible"] == 50.0
    assert d["submission_types"] == ["online_upload", "online_text_entry"]  # list, not string
    assert d["due_at"] == "2026-09-05T05:59:00"


def test_quiz_mapping_is_assignment_shaped():
    d = quiz_from_xml("<q><title>Q</title><points_possible>10.0</points_possible></q>", True)
    assert d["name"] == "Q"
    assert d["submission_types"] == ["online_quiz"]
    assert d["points_possible"] == 10.0


def test_slugify():
    assert slugify("W02 U0: Core Task 1 — Setup") == "w02-u0-core-task-1-setup"
    assert slugify("") == "item"


# --- full import -> course/ ------------------------------------------------

def test_import_produces_loadable_course(tmp_path):
    src = _make_imscc(tmp_path / "c.imscc")
    out = tmp_path / "course"
    counts = import_imscc(src, out)
    assert counts == {"modules": 1, "assignments": 1, "quizzes": 1, "pages": 1}

    # _course.json
    meta = json.loads((out / "_course.json").read_text())
    assert meta["name"] == "Sample Course"
    assert meta["canvas_id"] == "4242"

    # module dir + files
    mod = out / "week-1"
    assert (mod / "_module.json").is_file()
    assert (mod / "hw-1.json").is_file()
    assert (mod / "quiz-1.json").is_file()
    assert (mod / "overview.html").read_text() == "<p>hi</p>"

    # the loader reads it into API-shaped assignments
    c = load_course(out)
    assert c.name == "Sample Course"
    names = {a["name"] for a in c.assignments}
    assert names == {"HW 1", "Quiz 1"}
    hw = next(a for a in c.assignments if a["name"] == "HW 1")
    assert hw["submission_types"] == ["online_upload", "online_text_entry"]
    assert hw["points_possible"] == 100.0
    assert "Read chapter 1" in hw["description"]        # description body captured

    # syllabus captured at course/syllabus.html
    assert (out / "syllabus.html").is_file()
    assert "Grading policy" in c.syllabus()


# --- integration: real exports (gated, cross-course) -----------------------

def test_import_real_exports_if_present(tmp_path):
    reals = _file_finder.list_imscc(name_hint="export")
    if not reals:
        pytest.skip("no real *_export.imscc in ~/Downloads — integration skipped")
    for real in reals:
        out = tmp_path / real.stem
        counts = import_imscc(real, out)
        assert counts["modules"] > 0
        assert counts["assignments"] + counts["quizzes"] > 0
        c = load_course(out)                       # loader reads what import wrote
        assert len(c.assignments) > 0
        assert all("name" in a for a in c.assignments)


def test_syllabus_audit_local_runs_without_api(tmp_path):
    """The converted syllabus_audit reads the imported course/ syllabus offline."""
    import_imscc(_make_imscc(tmp_path / "c.imscc"), tmp_path / "course")
    env = {**os.environ, "CANVAS_API_TOKEN": "bogus", "CANVAS_BASE_URL": "https://x"}
    r = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / "syllabus_audit.py"),
         "--course-dir", str(tmp_path / "course"), "--json"],
        capture_output=True, text=True, env=env,
    )
    # 0/1/2 are audit verdicts (complete/incomplete/near-empty), not crashes.
    assert r.stdout.strip(), f"no output; stderr={r.stderr}"
    payload = json.loads(r.stdout)      # ran offline (bogus token) and produced valid JSON
    assert isinstance(payload, dict) and payload


def _run_local_audit(tmp_path, tool, flag):
    import_imscc(_make_imscc(tmp_path / "c.imscc"), tmp_path / "course")
    env = {**os.environ, "CANVAS_API_TOKEN": "bogus", "CANVAS_BASE_URL": "https://x"}
    return subprocess.run(
        [sys.executable, str(_TOOLS_DIR / tool), "--course-dir", str(tmp_path / "course"), flag],
        capture_output=True, text=True, env=env,
    )


def test_content_representation_audit_local_runs(tmp_path):
    r = _run_local_audit(tmp_path, "content_representation_audit.py", "--json")
    assert r.stdout.strip(), r.stderr
    assert isinstance(json.loads(r.stdout), dict)   # ran offline, zero API calls


def test_accessibility_audit_local_runs(tmp_path):
    r = _run_local_audit(tmp_path, "accessibility_audit.py", "--emit-json")
    assert r.stdout.strip(), r.stderr
    assert isinstance(json.loads(r.stdout), dict)   # ran offline, zero API calls


def test_import_captures_assignment_groups(tmp_path):
    import_imscc(_make_imscc(tmp_path / "c.imscc"), tmp_path / "course")
    from _course_loader import load_course
    groups = load_course(tmp_path / "course").assignment_groups()
    assert any(
        g["name"] == "Homework" and any(a["name"] == "HW 1" for a in g["assignments"])
        for g in groups
    )


def test_grading_structure_audit_local_runs(tmp_path):
    r = _run_local_audit(tmp_path, "grading_structure_audit.py", "--emit-json")
    assert r.stdout.strip(), r.stderr
    assert isinstance(json.loads(r.stdout), dict)   # groups joined, ran offline


def test_full_pipeline_cross_validation_if_present(tmp_path):
    """Cross-validate the WHOLE offline path — import .imscc -> load -> audit —
    across every real course, fully offline (bogus token = zero API calls)."""
    reals = _file_finder.list_imscc(name_hint="export")
    if not reals:
        pytest.skip("no real *_export.imscc in ~/Downloads — integration skipped")
    workload_tool = _TOOLS_DIR / "workload_audit.py"
    env = {**os.environ, "CANVAS_API_TOKEN": "bogus", "CANVAS_BASE_URL": "https://x"}
    for real in reals:
        out = tmp_path / real.stem
        counts = import_imscc(real, out)
        r = subprocess.run(
            [sys.executable, str(workload_tool), "--course-dir", str(out), "--json"],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode in (0, 1), f"{real.name}: {r.stderr}"
        payload = json.loads(r.stdout)
        assert payload["tool"] == "workload_audit"
        assert isinstance(payload.get("verdict"), str) and payload["verdict"], f"{real.name}"
        assert len(payload.get("week_distribution", [])) > 0, f"{real.name} produced no weeks"
        # the audit saw the imported assignments+quizzes
        assert counts["assignments"] + counts["quizzes"] > 0

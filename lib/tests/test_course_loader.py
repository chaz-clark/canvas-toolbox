"""Tier 1 unit tests — local course/ loader + pilot audit local path (Sprint 5).

Source: lib/tools/_course_loader.py (+ workload_audit.py --local)

Proves the source-agnostic pattern: the loader reads course/ into API-shaped
dicts, and workload_audit runs off them with ZERO API calls (verified with a
bogus token). Gated integration loads the real course/ in this repo.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _course_loader import load_course, Course, CourseNotFound  # noqa: E402

WORKLOAD_TOOL = _TOOLS_DIR / "workload_audit.py"


def _make_course(root: Path):
    """Write a minimal but realistic course/ tree (API-shaped item dicts)."""
    (root / "_course.json").write_text(
        json.dumps({"canvas_id": 999, "name": "Test Course", "course_code": "T 101"}),
        encoding="utf-8",
    )
    m = root / "week-1"
    m.mkdir()
    (m / "_module.json").write_text(
        json.dumps({"canvas_id": 1, "title": "Week 1", "position": 1, "published": True, "items": []}),
        encoding="utf-8",
    )
    (m / "hw1.json").write_text(json.dumps({
        "canvas_id": 11, "name": "HW 1", "points_possible": 100.0,
        "due_at": "2026-09-05T05:59:00Z", "submission_types": ["online_upload"],
        "assignment_group_identifierref": "gGRP1",
    }), encoding="utf-8")
    (m / "hw2.json").write_text(json.dumps({
        "canvas_id": 12, "name": "HW 2", "points_possible": 50.0,
        "due_at": "2026-09-12T05:59:00Z", "submission_types": ["online_text_entry"],
        "assignment_group_identifierref": "gGRP1",
    }), encoding="utf-8")
    (m / "overview.html").write_text("<p>Welcome</p>", encoding="utf-8")
    # a non-gradeable item (external tool) — must NOT count as an assignment
    (m / "tool.json").write_text(json.dumps({"canvas_id": 13, "name": "LTI", "type": "ExternalTool"}), encoding="utf-8")
    (root / "syllabus.html").write_text("<p>Course syllabus here</p>", encoding="utf-8")
    (root / "_assignment_groups.json").write_text(json.dumps([
        {"identifier": "gGRP1", "name": "Homework", "group_weight": 100.0, "position": 1},
    ]), encoding="utf-8")
    return root


# --- loader ----------------------------------------------------------------

def test_loads_metadata_modules_items(tmp_path):
    c = load_course(_make_course(tmp_path))
    assert isinstance(c, Course)
    assert c.name == "Test Course"
    assert c.canvas_id == 999
    assert len(c.modules) == 1
    assert c.modules[0].title == "Week 1"
    assert len(c.items) == 3          # hw1, hw2, tool (excludes _module.json + .html)


def test_assignments_are_gradeable_only(tmp_path):
    c = load_course(_make_course(tmp_path))
    names = {a["name"] for a in c.assignments}
    assert names == {"HW 1", "HW 2"}   # ExternalTool excluded (no points/submission_types)


def test_page_paths(tmp_path):
    c = load_course(_make_course(tmp_path))
    pages = c.page_paths()
    assert len(pages) == 1 and pages[0].name == "overview.html"


def test_syllabus_and_pages_bodies(tmp_path):
    c = load_course(_make_course(tmp_path))
    assert "Course syllabus here" in c.syllabus()
    pages = c.pages()
    assert any(p["title"] == "overview" and "Welcome" in p["body"] for p in pages)


def test_assignment_groups_join(tmp_path):
    c = load_course(_make_course(tmp_path))
    groups = c.assignment_groups()
    assert len(groups) == 1
    g = groups[0]
    assert g["name"] == "Homework" and g["group_weight"] == 100.0
    assert {a["name"] for a in g["assignments"]} == {"HW 1", "HW 2"}   # joined by ref
    assert c.apply_assignment_group_weights() is True


def test_missing_course_raises(tmp_path):
    with pytest.raises(CourseNotFound):
        load_course(tmp_path / "empty")


def test_real_course_loads_if_present():
    if not Path("course/_course.json").is_file():
        pytest.skip("no populated course/ in repo — integration skipped")
    c = load_course("course")
    assert c.canvas_id is not None
    assert len(c.assignments) > 0
    assert all("name" in a for a in c.assignments)


# --- pilot audit local path (end-to-end, offline-safe) ---------------------

def test_workload_audit_local_runs_without_api(tmp_path):
    _make_course(tmp_path)
    env = {**os.environ, "CANVAS_API_TOKEN": "bogus", "CANVAS_BASE_URL": "https://x"}
    r = subprocess.run(
        [sys.executable, str(WORKLOAD_TOOL), "--course-dir", str(tmp_path), "--json"],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode in (0, 1), r.stderr   # 0 balanced / 1 clustered — both are success
    payload = json.loads(r.stdout)
    assert payload["tool"] == "workload_audit"
    assert "verdict" in payload                # produced a real audit from local files, no API

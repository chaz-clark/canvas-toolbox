"""
test_course_audit_artifact.py

Tests for course_audit.py artifact writing (iterative improvement tracking).

Tests the .canvas/audit/<course_id>.json artifact that enables progress tracking
across audit iterations (e.g., missing rubrics: 32 → 22 → 12 over semesters).
"""

import json
import sys
import tempfile
from pathlib import Path

# Allow imports from lib/tools/
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from course_audit import _write_artifact, _COMBINED


def test_artifact_written_to_correct_location():
    """Artifact should be written to .canvas/audit/<course_id>.json"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        original_cwd = Path.cwd()

        try:
            # Change to temp dir so artifact is written there
            import os
            os.chdir(tmp_path)

            # Call _write_artifact with minimal data
            course_id = "415492"
            course_name = "Test Course"
            tier = "quick"
            ts = "2026-06-30 17:10 UTC"
            combined = 1  # NEEDS_ATTENTION
            rows = []
            raw = {}

            _write_artifact(course_id, course_name, tier, ts, combined, rows, raw)

            # Verify artifact exists
            artifact_path = tmp_path / ".canvas" / "audit" / f"{course_id}.json"
            assert artifact_path.exists(), f"Artifact not found at {artifact_path}"

        finally:
            os.chdir(original_cwd)


def test_artifact_schema_matches_spec():
    """Artifact JSON should match documented schema"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        original_cwd = Path.cwd()

        try:
            import os
            os.chdir(tmp_path)

            course_id = "415492"
            course_name = "Intro to Statistics"
            tier = "full"
            ts = "2026-06-30 17:10 UTC"
            combined = 1  # NEEDS_ATTENTION

            # Mock specialist data
            rows = [
                {
                    "key": "rubric_coverage",
                    "headline": "Needs Attention",
                    "fixes": ["32 assignments missing rubrics"],
                },
                {
                    "key": "clo_quality",
                    "headline": "Meets Criteria",
                    "fixes": [],
                },
            ]

            raw = {
                "rubric_coverage": {
                    "missing_rubrics": 32,
                    "decorative_rubrics": 1,
                    "coverage_ok": 7,
                    "total_assignments": 40,
                },
                "clo_quality": {
                    "clo_count": 4,
                    "scope_note": "ideal",
                },
            }

            _write_artifact(course_id, course_name, tier, ts, combined, rows, raw)

            # Read and validate artifact
            artifact_path = tmp_path / ".canvas" / "audit" / f"{course_id}.json"
            artifact = json.loads(artifact_path.read_text())

            # Validate schema
            assert artifact["schema_version"] == 1
            assert artifact["course_id"] == course_id
            assert artifact["course_name"] == course_name
            assert artifact["run_at"] == ts
            assert artifact["tier"] == tier
            assert artifact["verdict"] == _COMBINED[combined]
            assert "areas" in artifact
            assert "top_fixes" in artifact

            # Validate areas structure
            assert "rubric_coverage" in artifact["areas"]
            assert artifact["areas"]["rubric_coverage"]["missing"] == 32
            assert "clo_quality" in artifact["areas"]
            assert artifact["areas"]["clo_quality"]["clos"] == 4

        finally:
            os.chdir(original_cwd)


def test_per_course_keying():
    """Multiple courses should have separate artifacts (no clobbering)"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        original_cwd = Path.cwd()

        try:
            import os
            os.chdir(tmp_path)

            # Write artifact for course A
            course_a_id = "415492"
            _write_artifact(course_a_id, "Course A", "quick", "2026-06-30 10:00 UTC", 0, [], {})

            # Write artifact for course B
            course_b_id = "415194"
            _write_artifact(course_b_id, "Course B", "full", "2026-06-30 11:00 UTC", 1, [], {})

            # Both artifacts should exist
            artifact_a_path = tmp_path / ".canvas" / "audit" / f"{course_a_id}.json"
            artifact_b_path = tmp_path / ".canvas" / "audit" / f"{course_b_id}.json"

            assert artifact_a_path.exists(), "Course A artifact missing"
            assert artifact_b_path.exists(), "Course B artifact missing"

            # Verify they have different data
            artifact_a = json.loads(artifact_a_path.read_text())
            artifact_b = json.loads(artifact_b_path.read_text())

            assert artifact_a["course_id"] == course_a_id
            assert artifact_b["course_id"] == course_b_id
            assert artifact_a["course_name"] == "Course A"
            assert artifact_b["course_name"] == "Course B"

        finally:
            os.chdir(original_cwd)


def test_progress_tracking_use_case():
    """Successive audits should allow comparing findings (iteration tracking)"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        original_cwd = Path.cwd()

        try:
            import os
            os.chdir(tmp_path)

            course_id = "415492"

            # Fall 2026 audit — 32 missing rubrics
            rows_fall = [{
                "key": "rubric_coverage",
                "headline": "Needs Attention",
                "fixes": ["32 assignments missing rubrics"],
            }]
            raw_fall = {
                "rubric_coverage": {
                    "missing_rubrics": 32,
                    "decorative_rubrics": 1,
                    "coverage_ok": 7,
                    "total_assignments": 40,
                },
            }
            _write_artifact(course_id, "Stats", "quick", "2026-09-15 10:00 UTC", 1, rows_fall, raw_fall)

            artifact_path = tmp_path / ".canvas" / "audit" / f"{course_id}.json"
            audit_fall = json.loads(artifact_path.read_text())

            assert audit_fall["areas"]["rubric_coverage"]["missing"] == 32

            # Spring 2027 audit — fixed 10 rubrics, now 22 missing
            rows_spring = [{
                "key": "rubric_coverage",
                "headline": "Needs Attention",
                "fixes": ["22 assignments missing rubrics"],
            }]
            raw_spring = {
                "rubric_coverage": {
                    "missing_rubrics": 22,
                    "decorative_rubrics": 1,
                    "coverage_ok": 17,
                    "total_assignments": 40,
                },
            }
            _write_artifact(course_id, "Stats", "quick", "2027-01-20 10:00 UTC", 1, rows_spring, raw_spring)

            audit_spring = json.loads(artifact_path.read_text())

            assert audit_spring["areas"]["rubric_coverage"]["missing"] == 22
            assert audit_spring["areas"]["rubric_coverage"]["ok"] == 17

            # Demonstrates progress: 32 → 22 missing rubrics
            assert audit_fall["areas"]["rubric_coverage"]["missing"] > audit_spring["areas"]["rubric_coverage"]["missing"]

        finally:
            os.chdir(original_cwd)


def test_top_fixes_collected():
    """Top fixes should be extracted from specialist data"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        original_cwd = Path.cwd()

        try:
            import os
            os.chdir(tmp_path)

            rows = [
                {
                    "key": "rubric_coverage",
                    "headline": "Needs Attention",
                    "fixes": ["32 assignments missing rubrics", "1 decorative rubric found"],
                },
                {
                    "key": "workload",
                    "headline": "Back Loaded",
                    "fixes": ["18.5 hours in week 14"],
                },
            ]

            _write_artifact("415492", "Test", "full", "2026-06-30 10:00 UTC", 1, rows, {})

            artifact_path = tmp_path / ".canvas" / "audit" / "415492.json"
            artifact = json.loads(artifact_path.read_text())

            assert "top_fixes" in artifact
            assert len(artifact["top_fixes"]) > 0
            assert "32 assignments missing rubrics" in artifact["top_fixes"]

        finally:
            os.chdir(original_cwd)

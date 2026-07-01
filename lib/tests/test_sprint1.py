"""
Sprint 1 regression tests — Trust the Mirror
Covers issues: #1, #2, #3, #5
"""
import json
import subprocess
import sys
from pathlib import Path

from conftest import canvas_get, CANVAS_SANDBOX_ID


# ---------------------------------------------------------------------------
# #1 — Homepage false positive: homepage must not appear in orphaned_pages
# ---------------------------------------------------------------------------

def test_homepage_not_in_orphaned_pages(sandbox_pull):
    """#1: homepage page_url must never appear in orphaned_pages list."""
    index = sandbox_pull
    homepage = index.get("homepage", {})
    homepage_url = homepage.get("page_url")

    assert homepage_url, "No homepage found in index — sandbox missing a front page"

    orphan_urls = [o.get("page_url") for o in index.get("orphaned_pages", [])]
    assert homepage_url not in orphan_urls, (
        f"REGRESSION #1: homepage '{homepage_url}' still appears in orphaned_pages"
    )


# ---------------------------------------------------------------------------
# #3 + #5 — Classic quiz title and points_possible round-trip
# ---------------------------------------------------------------------------

def test_quiz_title_and_points_push(sandbox_env):
    """#3 + #5: pushing a local quiz must update title and points_possible in Canvas."""
    index = json.loads(Path(".canvas/index.json").read_text())

    # Find a classic quiz in the sandbox index
    quiz_entry = next(
        (
            (fp, meta)
            for fp, meta in index.get("files", {}).items()
            if meta.get("type") == "Quiz"
        ),
        None,
    )
    assert quiz_entry, "No classic Quiz found in sandbox index — cannot run #3/#5 test"

    filepath, meta = quiz_entry
    canvas_id = meta["canvas_id"]
    original = json.loads(Path(filepath).read_text())

    test_title = "QC Regression Test Quiz Title"
    test_points = 99.0

    try:
        # Write test values locally
        patched = {**original, "title": test_title, "points_possible": test_points}
        Path(filepath).write_text(json.dumps(patched, indent=2))

        result = subprocess.run(
            [sys.executable, "lib/tools/canvas_sync.py", "--push"],
            env={**sandbox_env, "CANVAS_SYNC_NO_PROMPT": "regression test"},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Push failed:\n{result.stderr}\n{result.stdout}"

        # Verify Canvas reflects the changes
        canvas_quiz = canvas_get(f"/courses/{CANVAS_SANDBOX_ID}/quizzes/{canvas_id}")
        assert canvas_quiz["title"] == test_title, (
            f"REGRESSION #3: quiz title not updated. Canvas has: '{canvas_quiz['title']}'"
        )
        assert float(canvas_quiz["points_possible"]) == test_points, (
            f"REGRESSION #5: points_possible not updated. Canvas has: {canvas_quiz['points_possible']}"
        )

    finally:
        # Always restore original values
        Path(filepath).write_text(json.dumps(original, indent=2))
        subprocess.run(
            [sys.executable, "lib/tools/canvas_sync.py", "--push"],
            env={**sandbox_env, "CANVAS_SYNC_NO_PROMPT": "regression test"},
            capture_output=True,
            text=True,
        )


# ---------------------------------------------------------------------------
# #2 — Assignment grading_type + submission_types round-trip
# ---------------------------------------------------------------------------

def test_assignment_grading_type_and_submission_types_push(sandbox_env):
    """#2: pushing grading_type and submission_types must update Canvas assignment."""
    index = json.loads(Path(".canvas/index.json").read_text())

    # Find a plain assignment (not NewQuiz)
    assignment_entry = next(
        (
            (fp, meta)
            for fp, meta in index.get("files", {}).items()
            if meta.get("type") == "Assignment"
        ),
        None,
    )
    assert assignment_entry, "No Assignment found in sandbox index"

    filepath, meta = assignment_entry
    canvas_id = meta["canvas_id"]
    original = json.loads(Path(filepath).read_text())

    try:
        patched = {
            **original,
            "grading_type": "pass_fail",
            "submission_types": ["online_upload", "online_text_entry"],
        }
        Path(filepath).write_text(json.dumps(patched, indent=2))

        result = subprocess.run(
            [sys.executable, "lib/tools/canvas_sync.py", "--push"],
            env={**sandbox_env, "CANVAS_SYNC_NO_PROMPT": "regression test"},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Push failed:\n{result.stderr}"

        canvas_assignment = canvas_get(
            f"/courses/{CANVAS_SANDBOX_ID}/assignments/{canvas_id}"
        )
        assert canvas_assignment["grading_type"] == "pass_fail", (
            f"REGRESSION #2: grading_type not updated. Canvas has: '{canvas_assignment['grading_type']}'"
        )
        assert set(canvas_assignment["submission_types"]) == {"online_upload", "online_text_entry"}, (
            f"REGRESSION #2: submission_types not updated. Canvas has: {canvas_assignment['submission_types']}"
        )

    finally:
        Path(filepath).write_text(json.dumps(original, indent=2))
        subprocess.run(
            [sys.executable, "lib/tools/canvas_sync.py", "--push"],
            env={**sandbox_env, "CANVAS_SYNC_NO_PROMPT": "regression test"},
            capture_output=True,
            text=True,
        )


def test_grading_type_pull_roundtrip(sandbox_pull):
    """#2: grading_type must be present in pulled assignment JSON files."""
    index = sandbox_pull
    assignment_files = [
        fp for fp, meta in index.get("files", {}).items()
        if meta.get("type") == "Assignment"
    ]
    assert assignment_files, "No assignment files found after pull"

    for fp in assignment_files[:3]:  # spot-check first three
        data = json.loads(Path(fp).read_text())
        assert "grading_type" in data, (
            f"REGRESSION #2: grading_type missing from pulled assignment {fp}"
        )


def test_index_no_stale_entries(sandbox_pull):
    """#2: every path in index['files'] must exist on disk after a full pull."""
    index = sandbox_pull
    missing = [fp for fp in index.get("files", {}) if not Path(fp).exists()]
    assert not missing, (
        f"REGRESSION #2: stale index entries after pull — {len(missing)} missing files: {missing[:5]}"
    )

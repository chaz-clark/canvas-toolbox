"""Tier 1 unit tests — grader_consensus pure-logic helpers.

Source: lib/tools/grader_consensus.py
  - detect_calibration_anchor (#101 — uncalibrated-cohort warning)

These tests do NOT exercise the full consensus aggregation; they hit the
calibration-detection helper directly so the file-system patterns are
validated without spinning up the CLI.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_consensus import detect_calibration_anchor  # noqa: E402


# ---------------------------------------------------------------------------
# detect_calibration_anchor — issue #101
# ---------------------------------------------------------------------------

def test_detect_calibration_anchor_no_files(tmp_path):
    """Empty challenge dir + empty feedback dir → not calibrated."""
    feedback = tmp_path / "feedback"
    feedback.mkdir()
    is_cal, evidence = detect_calibration_anchor(tmp_path, feedback)
    assert is_cal is False
    assert "no" in evidence.lower() or "not" in evidence.lower()


def test_detect_calibration_anchor_ta_grades_json(tmp_path):
    """ta_grades_*.json in challenge dir is a calibration anchor."""
    feedback = tmp_path / "feedback"
    feedback.mkdir()
    (tmp_path / "ta_grades_2026spring.json").write_text("{}", encoding="utf-8")
    is_cal, evidence = detect_calibration_anchor(tmp_path, feedback)
    assert is_cal is True
    assert "ta_grades" in evidence


def test_detect_calibration_anchor_ta_grades_csv(tmp_path):
    """ta_grades_*.csv works too — different format, same anchor role."""
    feedback = tmp_path / "feedback"
    feedback.mkdir()
    (tmp_path / "ta_grades_round2.csv").write_text("key,score\n", encoding="utf-8")
    is_cal, _ = detect_calibration_anchor(tmp_path, feedback)
    assert is_cal is True


def test_detect_calibration_anchor_groundtruth_json(tmp_path):
    """_groundtruth.json is the explicit ground-truth pattern."""
    feedback = tmp_path / "feedback"
    feedback.mkdir()
    (tmp_path / "_groundtruth.json").write_text("{}", encoding="utf-8")
    is_cal, evidence = detect_calibration_anchor(tmp_path, feedback)
    assert is_cal is True
    assert "_groundtruth" in evidence


def test_detect_calibration_anchor_in_feedback_dir(tmp_path):
    """Anchor file in feedback/ counts too — some workflows drop it there."""
    feedback = tmp_path / "feedback"
    feedback.mkdir()
    (feedback / "_groundtruth.csv").write_text("key,score\n", encoding="utf-8")
    is_cal, _ = detect_calibration_anchor(tmp_path, feedback)
    assert is_cal is True


def test_detect_calibration_anchor_none_challenge_dir(tmp_path):
    """When called from a feedback-dir-only invocation (no challenge_dir),
    the helper still scans the feedback dir."""
    feedback = tmp_path / "feedback"
    feedback.mkdir()
    (feedback / "ta_grades.json").write_text("{}", encoding="utf-8")
    is_cal, _ = detect_calibration_anchor(None, feedback)
    assert is_cal is True


def test_detect_calibration_anchor_unrelated_files_ignored(tmp_path):
    """Files that aren't on the anchor pattern list don't count."""
    feedback = tmp_path / "feedback"
    feedback.mkdir()
    (tmp_path / "rubric.md").write_text("# rubric", encoding="utf-8")
    (tmp_path / "answer_key.py").write_text("# solution", encoding="utf-8")
    (feedback / "_grader1.csv").write_text("key,score\n", encoding="utf-8")
    is_cal, _ = detect_calibration_anchor(tmp_path, feedback)
    assert is_cal is False


def test_detect_calibration_anchor_multiple_files(tmp_path):
    """Multiple anchors: evidence string reports first 3 + count."""
    feedback = tmp_path / "feedback"
    feedback.mkdir()
    (tmp_path / "ta_grades_a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ta_grades_b.json").write_text("{}", encoding="utf-8")
    (tmp_path / "_groundtruth.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ta_grades_c.csv").write_text("key,score\n", encoding="utf-8")
    is_cal, evidence = detect_calibration_anchor(tmp_path, feedback)
    assert is_cal is True
    # First three named in the evidence; +1 more indicated
    assert "more" in evidence


def test_detect_calibration_anchor_nonexistent_dirs_safe(tmp_path):
    """Pointing at directories that don't exist → returns False cleanly,
    no exception."""
    fake_cd = tmp_path / "does_not_exist"
    fake_fb = tmp_path / "also_missing"
    is_cal, _ = detect_calibration_anchor(fake_cd, fake_fb)
    assert is_cal is False

"""Pure scheduling tests for the advanced GitHub Actions peer-review runner."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
import sys

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import peer_review_schedule as prs  # noqa: E402


def _config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "schedule.yml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_schedule_and_due_time_are_dst_aware(tmp_path):
    path = _config(tmp_path, """
timezone: America/Denver
window:
  start_date: 2026-03-01
  end_date: 2026-03-31
  lock_at: "18:00"
assignment:
  title: Prep ratings
  group_set_id: 123
""")
    schedule = prs.load_schedule(path)
    due, reason = prs.is_due(schedule, datetime(2026, 3, 9, 1, 0, tzinfo=timezone.utc))
    assert due is True
    assert "inside" in reason


def test_before_lock_is_a_noop(tmp_path):
    schedule = prs.load_schedule(_config(tmp_path, """
timezone: America/Denver
window:
  start_date: 2026-10-01
  end_date: 2026-10-31
  lock_at: "18:00"
assignment:
  id: 123
  group_set_id: 456
"""))
    due, reason = prs.is_due(schedule, datetime(2026, 10, 2, 23, 59, tzinfo=timezone.utc))
    assert due is False
    assert reason == "before configured lock time"


def test_assignment_id_and_title_are_mutually_exclusive(tmp_path):
    with pytest.raises(ValueError, match="id or title"):
        prs.load_schedule(_config(tmp_path, """
timezone: America/Denver
window:
  start_date: 2026-10-01
  end_date: 2026-10-31
  lock_at: "18:00"
assignment:
  id: 123
  title: Prep ratings
  group_set_id: 456
"""))


def test_schedule_command_preserves_explicit_live_course_opt_in(tmp_path):
    schedule = prs.load_schedule(_config(tmp_path, """
timezone: America/Denver
allow_enrolled: true
window:
  start_date: 2026-10-01
  end_date: 2026-10-31
  lock_at: "18:00"
assignment:
  title: Prep ratings
  group_set_id: 456
"""))
    command = prs._command(schedule, apply=True)
    assert "--apply" in command
    assert "--allow-enrolled" in command

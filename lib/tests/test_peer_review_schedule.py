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


# --- main(): the paths a scheduled job actually takes (#354) --------------------

def _cfg(tmp_path):
    path = tmp_path / "s.yml"
    path.write_text(
        "timezone: America/Denver\n"
        "window: {start_date: 2026-10-01, end_date: 2026-12-15, lock_at: '18:00'}\n"
        "assignment: {title: Prep ratings, group_set_id: 5}\n",
        encoding="utf-8",
    )
    return path


def _main(monkeypatch, argv, course_id="9"):
    ran = []
    monkeypatch.setattr(sys, "argv", ["peer_review_schedule.py", *argv])
    if course_id:
        monkeypatch.setenv("CANVAS_COURSE_ID", course_id)
    else:
        monkeypatch.delenv("CANVAS_COURSE_ID", raising=False)
    monkeypatch.setattr(prs.subprocess, "run",
                        lambda cmd, **kw: ran.append(cmd) or type("R", (), {"returncode": 0})())
    return prs.main(), ran


def test_outside_the_window_is_a_clean_noop_that_never_calls_canvas(tmp_path, monkeypatch):
    rc, ran = _main(monkeypatch, ["--config", str(_cfg(tmp_path)), "--now", "2026-09-01T18:00:00+00:00"])
    assert rc == 0 and ran == []


def test_inside_the_window_delegates_as_a_dry_run_by_default(tmp_path, monkeypatch):
    rc, ran = _main(monkeypatch, ["--config", str(_cfg(tmp_path)), "--now", "2026-10-10T02:00:00+00:00"])
    assert rc == 0 and len(ran) == 1 and "--apply" not in ran[0]


def test_apply_is_passed_through_only_when_asked(tmp_path, monkeypatch):
    rc, ran = _main(monkeypatch, ["--config", str(_cfg(tmp_path)), "--apply",
                                  "--now", "2026-10-10T02:00:00+00:00"])
    assert rc == 0 and "--apply" in ran[0]


def test_a_failing_delegate_fails_the_job(tmp_path, monkeypatch):
    """A non-zero peer_review_assign result must surface, not become a silent success."""
    monkeypatch.setattr(sys, "argv", ["peer_review_schedule.py", "--config", str(_cfg(tmp_path)),
                                      "--now", "2026-10-10T02:00:00+00:00"])
    monkeypatch.setenv("CANVAS_COURSE_ID", "9")
    monkeypatch.setattr(prs.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 2})())
    assert prs.main() == 2


def test_missing_course_id_inside_the_window_is_an_error_not_a_noop(tmp_path, monkeypatch):
    rc, ran = _main(monkeypatch, ["--config", str(_cfg(tmp_path)), "--now", "2026-10-10T02:00:00+00:00"],
                    course_id=None)
    assert rc == 2 and ran == []


def test_bad_config_exits_2(tmp_path, monkeypatch):
    bad = tmp_path / "bad.yml"
    bad.write_text("timezone: Not/AZone\n", encoding="utf-8")
    rc, ran = _main(monkeypatch, ["--config", str(bad)])
    assert rc == 2 and ran == []

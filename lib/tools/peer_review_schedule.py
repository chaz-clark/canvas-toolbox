#!/usr/bin/env python3
"""
peer_review_schedule.py — gate a scheduled peer-review pairing run (#354).

This is the scheduling layer around the deterministic, idempotent
peer_review_assign.py tool. It validates a course-owned YAML schedule in the
configured timezone, refuses runs outside the configured term/window, and
delegates the actual Canvas read/write to peer_review_assign.py.

Default mode is a read-only preview. `--apply` is intended for an explicitly
configured GitHub Actions job or a technically capable instructor's local
cron job. `allow_enrolled: true` in the config is an explicit course-owner
choice because it permits unattended writes to a live course.

Example:
  uv run python lib/tools/peer_review_schedule.py \
      --config .canvas/peer-review-schedule.yml
  uv run python lib/tools/peer_review_schedule.py \
      --config .canvas/peer-review-schedule.yml --apply
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

from __toolbox_version__ import __version__


@dataclass(frozen=True)
class Schedule:
    timezone: str
    start_date: datetime.date
    end_date: datetime.date
    lock_at: time
    assignment_id: int | None
    assignment_title: str | None
    group_set_id: int
    include_unsubmitted: bool
    allow_enrolled: bool
    course_id_env: str


def _required(data: dict, key: str):
    value = data.get(key)
    if value in (None, ""):
        raise ValueError(f"missing required config key: {key}")
    return value


def _date(value: object, key: str):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{key} must be YYYY-MM-DD") from exc


def _time(value: object, key: str) -> time:
    try:
        return time.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{key} must be HH:MM or HH:MM:SS") from exc


def load_schedule(path: Path) -> Schedule:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ValueError(f"cannot read config: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("config root must be a mapping")

    window = data.get("window") or {}
    if not isinstance(window, dict):
        raise ValueError("window must be a mapping")
    assignment = data.get("assignment") or {}
    if not isinstance(assignment, dict):
        raise ValueError("assignment must be a mapping")

    assignment_id = assignment.get("id")
    title = assignment.get("title")
    if assignment_id is None and not title:
        raise ValueError("assignment requires either id or title")
    if assignment_id is not None:
        try:
            assignment_id = int(assignment_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("assignment.id must be an integer") from exc
    if title and assignment_id is not None:
        raise ValueError("assignment must specify id or title, not both")

    try:
        ZoneInfo(str(_required(data, "timezone")))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {data.get('timezone')}") from exc

    group_set_id = _required(assignment, "group_set_id")
    try:
        group_set_id = int(group_set_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("assignment.group_set_id must be an integer") from exc

    start_date = _date(_required(window, "start_date"), "window.start_date")
    end_date = _date(_required(window, "end_date"), "window.end_date")
    if end_date < start_date:
        raise ValueError("window.end_date must not precede window.start_date")

    return Schedule(
        timezone=str(data["timezone"]),
        start_date=start_date,
        end_date=end_date,
        lock_at=_time(_required(window, "lock_at"), "window.lock_at"),
        assignment_id=assignment_id,
        assignment_title=str(title) if title else None,
        group_set_id=group_set_id,
        include_unsubmitted=bool(data.get("include_unsubmitted", False)),
        allow_enrolled=bool(data.get("allow_enrolled", False)),
        course_id_env=str(data.get("course_id_env", "CANVAS_COURSE_ID")),
    )


def is_due(schedule: Schedule, now: datetime) -> tuple[bool, str]:
    local = now.astimezone(ZoneInfo(schedule.timezone))
    if local.date() < schedule.start_date:
        return False, "before configured window"
    if local.date() > schedule.end_date:
        return False, "after configured window"
    if local.time() < schedule.lock_at:
        return False, "before configured lock time"
    return True, "inside configured window and after lock time"


def _command(schedule: Schedule, apply: bool) -> list[str]:
    tool = Path(__file__).with_name("peer_review_assign.py")
    command = [sys.executable, str(tool)]
    if schedule.assignment_id is not None:
        command += ["--assignment-id", str(schedule.assignment_id)]
    else:
        command += ["--title", schedule.assignment_title or ""]
    command += ["--group-set-id", str(schedule.group_set_id)]
    if schedule.include_unsubmitted:
        command.append("--include-unsubmitted")
    if apply:
        command.append("--apply")
    if schedule.allow_enrolled:
        command.append("--allow-enrolled")
    return command


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description="Run scheduled peer-review pairing safely.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--apply", action="store_true", help="Delegate the Canvas write.")
    ap.add_argument("--now", help="Testing only: ISO datetime, interpreted as UTC if naive.")
    args = ap.parse_args()

    try:
        schedule = load_schedule(args.config)
        now = datetime.fromisoformat(args.now) if args.now else datetime.now().astimezone()
        if now.tzinfo is None:
            now = now.replace(tzinfo=ZoneInfo("UTC"))
        due, reason = is_due(schedule, now)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    course_id = os.environ.get(schedule.course_id_env, "").strip()
    print(f"schedule: {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"window: {reason}")
    print(f"course id configured: {'yes' if course_id else 'no'}")
    if not due:
        print("nothing to run")
        return 0
    if not course_id:
        print(f"ERROR: course ID not found in ${schedule.course_id_env}", file=sys.stderr)
        return 2

    command = _command(schedule, args.apply)
    print("delegating to peer_review_assign.py")
    return subprocess.run(command, env=os.environ.copy(), check=False).returncode


if __name__ == "__main__":
    sys.exit(main())

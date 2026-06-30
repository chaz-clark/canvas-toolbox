#!/usr/bin/env python3
"""
submission_history_fetch.py — Feature 4: Multi-Submission Tracker for NGAI

Fetches submission metadata including submission_history for Canvas assignments.
Designed for n8n Execute Command node integration.

Returns structured JSON with submission attempts, timestamps, and scores - useful
for NGAI QC agents to track student progress across multiple submission attempts.

Usage:
    uv run python lib/tools/submission_history_fetch.py \\
        --assignment-id 12345 \\
        --course-id 67890 \\
        --json

    uv run python lib/tools/submission_history_fetch.py \\
        --assignment-id 12345 \\
        --output submissions.json

FERPA Discipline:
    - Outputs user_id only (Canvas internal ID, not SIS ID)
    - NO student names in JSON output
    - Honors --test-student-only for validation runs
    - Safe for AI agent consumption

Exit codes:
    0 = success
    1 = no submissions found
    2 = configuration error

NGAI Integration (Feature 4):
    Part of Sprint 1 Phase 1 MVP. QC agents use submission_history to detect
    multi-attempt patterns, track improvement trajectories, and adjust feedback
    strategies for students who resubmit.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests

try:
    from _env_loader import load_env, force_utf8_console
    load_env()
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available

from __toolbox_version__ import __version__

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
CANVAS_BASE_URL = ("https://" + _raw) if _raw and not _raw.startswith("http") else _raw
DEFAULT_COURSE_ID = os.environ.get("CANVAS_COURSE_ID", "")

_TEST_STUDENT_NAME = "Test Student"


def _headers():
    return {
        "Authorization": f"Bearer {CANVAS_API_TOKEN}",
        "Accept": "application/json+canvas-string-ids"
    }


def _check_env():
    if not CANVAS_API_TOKEN or not CANVAS_BASE_URL:
        print("ERROR: CANVAS_API_TOKEN and CANVAS_BASE_URL required in .env", file=sys.stderr)
        sys.exit(2)


def fetch_submissions(course_id: str, assignment_id: str) -> list[dict]:
    """
    Fetch all submissions for an assignment including submission_history.

    Returns list of submission objects with:
    - user_id
    - attempt
    - submitted_at
    - score
    - workflow_state
    - submission_history (array of prior attempts)
    - user.display_name (for filtering, not included in JSON output)
    """
    url = f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions"
    params = {
        "include[]": ["user", "submission_history"],
        "per_page": 100
    }

    submissions = []
    page = 1

    while True:
        params["page"] = page
        r = requests.get(url, headers=_headers(), params=params, timeout=30)
        if r.status_code >= 400:
            print(f"ERROR: HTTP {r.status_code} fetching submissions: {r.text[:200]}", file=sys.stderr)
            sys.exit(2)

        batch = r.json()
        if not batch:
            break

        submissions.extend(batch)
        page += 1

    return submissions


def is_actual_submission(sub: dict) -> bool:
    """Check if this is an actual submission (not just enrolled but no submission)."""
    workflow = sub.get("workflow_state", "")
    submitted_at = sub.get("submitted_at")
    return workflow != "unsubmitted" and submitted_at is not None


def build_submission_record(sub: dict, test_student_only: bool = False) -> Optional[dict]:
    """
    Build FERPA-safe submission record for JSON output.

    Returns None if submission should be filtered out.
    """
    user_id = sub.get("user_id")
    if not user_id:
        return None

    user = sub.get("user") or {}
    display_name = user.get("display_name", "").strip()
    is_test_student = display_name == _TEST_STUDENT_NAME

    # Filter: if test_student_only mode, skip non-Test-Student submissions
    if test_student_only and not is_test_student:
        return None

    # Build submission_history array
    history = []
    raw_history = sub.get("submission_history") or []
    for h in raw_history:
        history.append({
            "attempt": h.get("attempt"),
            "submitted_at": h.get("submitted_at"),
            "score": h.get("score"),
            "workflow_state": h.get("workflow_state"),
            "grade": h.get("grade"),
            "late": h.get("late", False)
        })

    record = {
        "user_id": int(user_id),
        "attempt": sub.get("attempt"),
        "submitted_at": sub.get("submitted_at"),
        "score": sub.get("score"),
        "grade": sub.get("grade"),
        "workflow_state": sub.get("workflow_state"),
        "late": sub.get("late", False),
        "excused": sub.get("excused", False),
        "missing": sub.get("missing", False),
        "submission_type": sub.get("submission_type"),
        "submission_history": history,
        "is_test_student": is_test_student
    }

    return record


def main():
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Fetch submission history for Canvas assignments (NGAI Feature 4: Multi-Submission Tracker)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch submission history for assignment (JSON to stdout)
  uv run python lib/tools/submission_history_fetch.py --assignment-id 12345 --course-id 67890

  # Save to file
  uv run python lib/tools/submission_history_fetch.py --assignment-id 12345 --output history.json

  # Test with Test Student only (FERPA discipline)
  uv run python lib/tools/submission_history_fetch.py --assignment-id 12345 --test-student-only

Exit codes:
  0 = success
  1 = no submissions found
  2 = configuration error

FERPA Discipline:
  - Outputs user_id only (no names)
  - --test-student-only validates on Test Student before real cohort fetch
  - JSON is safe for AI agent consumption
"""
    )

    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--assignment-id", required=True,
                   help="Canvas assignment ID to fetch submissions for")
    ap.add_argument("--course-id", default=None,
                   help="Canvas course ID (default: env CANVAS_COURSE_ID)")
    ap.add_argument("--output", default=None, metavar="PATH",
                   help="Write JSON to file instead of stdout")
    ap.add_argument("--test-student-only", action="store_true",
                   help="FERPA-discipline: only include Test Student submissions (validation run)")

    args = ap.parse_args()

    _check_env()

    course_id = args.course_id or DEFAULT_COURSE_ID
    if not course_id:
        print("ERROR: --course-id required or set CANVAS_COURSE_ID in .env", file=sys.stderr)
        sys.exit(2)

    assignment_id = args.assignment_id

    # Fetch submissions
    print(f"Fetching submissions for assignment {assignment_id} in course {course_id}...",
          file=sys.stderr)
    submissions = fetch_submissions(course_id, assignment_id)

    # Filter to actual submissions and build records
    records = []
    for sub in submissions:
        if not is_actual_submission(sub):
            continue

        record = build_submission_record(sub, test_student_only=args.test_student_only)
        if record:
            records.append(record)

    if not records:
        print(f"No submissions found for assignment {assignment_id}", file=sys.stderr)
        sys.exit(1)

    # Build output
    output = {
        "tool": "submission_history_fetch",
        "tool_version": __version__,
        "assignment_id": int(assignment_id),
        "course_id": int(course_id),
        "submission_count": len(records),
        "test_student_only": args.test_student_only,
        "submissions": records
    }

    body = json.dumps(output, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(body, encoding="utf-8")
        print(f"✅ {len(records)} submission(s) written to {args.output}", file=sys.stderr)
    else:
        print(body)

    return 0


if __name__ == "__main__":
    sys.exit(main())

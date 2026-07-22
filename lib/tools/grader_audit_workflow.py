#!/usr/bin/env python3
"""Post-push workflow-state audit + idempotent repair (issue #226).

THE GAP
  After a grade is posted, Canvas usually flips a submission from
  workflow_state "submitted" to "graded". But when a student RESUBMITS after being
  graded, the state resets to "submitted", and re-applying the grade doesn't always
  transition it back — so the grade is posted but the instructor's To-Do still shows
  "needs grading". (2026-07-22: 31 submissions stuck across 6 assignments.)

WHAT THIS DOES
  --check  scan assignment(s) and report submissions that have a grade but are still
           workflow_state "submitted" (FERPA-safe: user_id + assignment, no names).
  --fix    idempotently RE-POST the grade Canvas already has, which forces the
           "submitted" → "graded" transition.

THE HG-5 GUARDRAIL (issue #213)
  --fix ONLY re-posts the grade a submission ALREADY carries — it never sets a new
  or changed grade. So it is a workflow-STATE repair, not a grading path: it stays
  outside the --mark-reviewed review gate (there is no new/AI-drafted grade to
  review) without becoming a backdoor around it. Being a sanctioned lib/tools/ tool,
  its re-post is the path the grade_guardian hook expects — never a custom script.
  Live-course writes still pass canvas_course_guard (--allow-enrolled).

Usage:
    uv run python lib/tools/grader_audit_workflow.py --assignment-id 123 --check
    uv run python lib/tools/grader_audit_workflow.py --all-assignments --fix --allow-enrolled
"""
from __future__ import annotations

import argparse
import os
import sys

import requests

try:
    from _env_loader import force_utf8_console, load_env
except ImportError:
    def force_utf8_console() -> None:
        pass

    def load_env() -> None:
        pass

try:
    from canvas_course_guard import enforce as guard_enforce
except ImportError:
    guard_enforce = None

_TIMEOUT = 20


def find_stuck_submissions(submissions: list) -> list:
    """Submissions that carry a grade but are still workflow_state 'submitted' (#226).

    Pure. `pending_review` (moderated) and `unsubmitted` are intentionally NOT stuck —
    a re-post must not disturb a moderation queue or an ungraded submission.
    """
    return [s for s in submissions
            if s.get("grade") not in (None, "")
            and s.get("workflow_state") == "submitted"]


def _canvas_env(course_override: str | None) -> tuple:
    load_env()
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    cid = course_override or os.environ.get("CANVAS_COURSE_ID", "")
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return tok, cid, base


def _get_paginated(url: str, headers: dict, params: dict | None = None) -> list:
    out: list = []
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        out.extend(body if isinstance(body, list) else [body])
        url = resp.links.get("next", {}).get("url")
        params = None  # the next link carries its own query
    return out


def fetch_assignment_ids(base: str, cid: str, headers: dict) -> list:
    items = _get_paginated(f"{base}/api/v1/courses/{cid}/assignments",
                           headers, {"per_page": 100})
    return [a["id"] for a in items if "id" in a]


def fetch_submissions(base: str, cid: str, headers: dict, aid) -> list:
    return _get_paginated(f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions",
                          headers, {"per_page": 100})


def repost_grade(base: str, cid: str, headers: dict, aid, uid, grade: str) -> bool:
    """Idempotently re-post the EXISTING grade to force the state transition."""
    resp = requests.put(
        f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions/{uid}",
        headers=headers, data={"submission[posted_grade]": grade}, timeout=_TIMEOUT)
    return resp.status_code < 400


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(
        description="Audit + idempotently repair stuck submission workflow_state (#226).")
    ap.add_argument("--course-id", default=None, help="Override CANVAS_COURSE_ID.")
    ap.add_argument("--assignment-id", action="append", type=int, default=None,
                    help="Assignment id to scan (repeatable).")
    ap.add_argument("--all-assignments", action="store_true",
                    help="Scan every assignment in the course.")
    ap.add_argument("--fix", action="store_true",
                    help="Re-post the EXISTING grade to force 'submitted' -> 'graded'. "
                         "Default is --check (report only).")
    ap.add_argument("--yes", "-y", action="store_true", help="Skip the fix confirmation.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="canvas_course_guard override for the live-course re-post.")
    args = ap.parse_args()

    tok, cid, base = _canvas_env(args.course_id)
    for var, val in (("CANVAS_API_TOKEN", tok), ("CANVAS_BASE_URL", base), ("course id", cid)):
        if not val:
            print(f"Missing {var}.", file=sys.stderr)
            return 1
    headers = {"Authorization": f"Bearer {tok}"}

    if not args.assignment_id and not args.all_assignments:
        print("Pass --assignment-id <id> (repeatable) or --all-assignments.", file=sys.stderr)
        return 1

    if args.fix and guard_enforce:
        guard_enforce(base, headers, cid, mode="write", allow_override=args.allow_enrolled)

    aids = args.assignment_id or fetch_assignment_ids(base, cid, headers)
    stuck: list = []  # (aid, uid, grade)
    for aid in aids:
        for s in find_stuck_submissions(fetch_submissions(base, cid, headers, aid)):
            stuck.append((aid, s["user_id"], s.get("grade")))

    if not stuck:
        print(f"No stuck submissions across {len(aids)} assignment(s) — every graded "
              "submission is workflow_state 'graded'.")
        return 0

    print(f"⚠️  {len(stuck)} stuck submission(s) (grade posted but workflow_state "
          f"'submitted') across {len({a for a, _, _ in stuck})} assignment(s):")
    for aid, uid, grade in stuck:
        print(f"    assignment {aid}  user_id {uid}  grade={grade}")

    if not args.fix:
        print("\n--check only. Re-run with --fix (--allow-enrolled) to idempotently re-post "
              "the existing grades and force the transition.")
        return 0

    if not args.yes:
        print(f"\nThis re-posts {len(stuck)} EXISTING grade(s) to the LIVE course {cid} "
              "(no grade values change).")
        if input("Type 'fix' to proceed: ").strip().lower() != "fix":
            print("Aborted.")
            return 1

    fixed = failed = 0
    for aid, uid, grade in stuck:
        if repost_grade(base, cid, headers, aid, uid, grade):
            fixed += 1
        else:
            failed += 1
            print(f"    FAILED to re-post assignment {aid} user_id {uid}", file=sys.stderr)
    print(f"\n✓ Re-posted {fixed} grade(s) to force the transition"
          + (f"; {failed} failed." if failed else "."))
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())

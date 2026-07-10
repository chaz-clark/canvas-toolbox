#!/usr/bin/env python3
"""
exempt_late_enrollment.py — Bulk excuse assignments for late-enrolling students.

PROBLEM
  Student joins Week 5 of a 14-week course. Faculty needs to excuse them from
  all assignments due in Weeks 1-4 so those assignments don't count toward
  their grade. Manually clicking "EX" for 20+ assignments in the gradebook
  is tedious and error-prone.

SOLUTION
  One command excuses the student from all assignments with due dates before
  their enrollment date (or before a specific week). Canvas marks each
  assignment as "EX" (excused) in the gradebook — the assignment doesn't
  count toward their grade, and the maximum total points adjust accordingly.

CANVAS BEHAVIOR
  "Excused" (shown as "EX" in gradebook) means:
    - Assignment doesn't count toward grade calculation
    - Maximum total points reduced by that assignment's point value
    - Canvas treats it like the assignment doesn't exist for that student
    - Student cannot submit to excused assignments

  Note: "Excused" and "exempt" are the same thing in Canvas — just different
  terminology for the same status. There's only one Canvas behavior.

HOW IT WORKS
  1. Fetch all published assignments (assignments, quizzes, discussions)
  2. Filter to assignments with due_at before cutoff date
  3. For each assignment, mark the student's submission as excused via Canvas
     Submissions API (PUT submission with excused: true)
  4. Dry-run by default — shows what would be excused without making changes

PII-FREE LOOKUP
  Resolve target student with EITHER:
    --user-id 123456        Canvas user_id (numeric)
    --deid-code S-95DBB6    Code from grading/.deid_master.csv
                            (built by build_deid_master.py)

  The deid_code lookup reads ONLY the user_id column — student's name is
  never read, printed, or sent to the agent.

SCOPE — pick ONE (mutually exclusive)
  --before-date YYYY-MM-DD    Excuse all assignments due before this date
  --before-week N             Excuse all assignments due before week N
                              (calculates date from course start in .env)

USAGE — dry-run by default (use --apply to actually write)
  # Preview what would be excused (dry-run)
  uv run python lib/tools/exempt_late_enrollment.py \\
    --user-id 123456 --before-date 2026-02-15

  # Apply: excuse student from assignments before date
  uv run python lib/tools/exempt_late_enrollment.py \\
    --user-id 123456 --before-date 2026-02-15 --apply

  # Excuse by week number (before Week 5 = Weeks 1-4)
  uv run python lib/tools/exempt_late_enrollment.py \\
    --deid-code S-95DBB6 --before-week 5 --apply

  # Undo: remove excused status (set excused: false)
  uv run python lib/tools/exempt_late_enrollment.py \\
    --user-id 123456 --undo --apply

REQUIRES in .env:
  CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID
  COURSE_START_DATE (for --before-week; format: YYYY-MM-DD)

REQUIRES (only if using --deid-code):
  grading/.deid_master.csv (built by build_deid_master.py)

Implements roadmap Phase 2 #10 — Global student exemption for late enrollment.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: uv sync", file=sys.stderr)
    raise SystemExit(1) from None

try:
    from _env_loader import force_utf8_console, load_env
except ImportError:
    def force_utf8_console() -> None:
        pass
    def load_env() -> None:
        pass

_TIMEOUT = 60


# ---------------------------------------------------------------------------
# User lookup (FERPA-safe)
# ---------------------------------------------------------------------------

def resolve_user_id_from_deid(deid_code: str, deid_master_path: Path) -> int | None:
    """Look up Canvas user_id from deid-code in .deid_master.csv.

    Reads ONLY the deid_code and user_id columns. Student name is never
    accessed. Returns None if code not found.
    """
    if not deid_master_path.exists():
        print(f"ERROR: {deid_master_path} not found.", file=sys.stderr)
        print("Run: uv run python lib/tools/build_deid_master.py", file=sys.stderr)
        return None

    with deid_master_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("deid_code") == deid_code:
                return int(row["user_id"])
    return None


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def parse_iso_date(date_str: str) -> datetime:
    """Parse YYYY-MM-DD to datetime (naive)."""
    return datetime.fromisoformat(date_str)


def week_number_to_cutoff_date(week: int, course_start_str: str) -> str:
    """Convert week number to cutoff date (first day of that week).

    Example: --before-week 5 with course starting 2026-01-13 returns
    "2026-02-10" (start of week 5). Assignments due before this date
    get excused.
    """
    start = parse_iso_date(course_start_str)
    # Week N starts on day (N-1)*7 after course start
    # Week 1 = days 0-6, Week 2 = days 7-13, Week 5 = days 28-34
    cutoff = start + timedelta(days=(week - 1) * 7)
    return cutoff.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Canvas API
# ---------------------------------------------------------------------------

def fetch_published_assignments(base_url: str, course_id: str,
                                token: str) -> list[dict]:
    """Fetch all published assignments (assignments, quizzes, discussions).

    Returns list of assignment dicts with id, name, due_at, points_possible.
    Only includes assignments that are published and have due dates.
    """
    headers = {"Authorization": f"Bearer {token}"}
    out: list[dict] = []
    page = 1

    while True:
        r = requests.get(
            f"{base_url}/api/v1/courses/{course_id}/assignments",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break

        for a in batch:
            # Only include published assignments with due dates
            if a.get("published") and a.get("due_at"):
                out.append(a)
        page += 1

    return out


def filter_assignments_before_date(assignments: list[dict],
                                   cutoff_date_str: str) -> list[dict]:
    """Return assignments with due_at < cutoff_date_str (YYYY-MM-DD).

    Compares date prefix (first 10 chars) for simplicity — timezone
    precision isn't critical for enrollment-date scoping.
    """
    return [a for a in assignments if a["due_at"][:10] < cutoff_date_str]


def excuse_submission(base_url: str, course_id: str, assignment_id: int,
                     user_id: int, token: str) -> bool:
    """Mark submission as excused via Canvas Submissions API.

    PUT /api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id
    with excused: true.

    Returns True on success, False on error.
    """
    headers = {"Authorization": f"Bearer {token}"}
    url = (f"{base_url}/api/v1/courses/{course_id}/assignments/"
           f"{assignment_id}/submissions/{user_id}")

    payload = {"submission": {"excused": True}}

    r = requests.put(url, headers=headers, json=payload, timeout=_TIMEOUT)
    if r.status_code in (200, 201):
        return True

    print(f"  ✗ Failed to excuse assignment {assignment_id}: "
          f"HTTP {r.status_code}", file=sys.stderr)
    return False


def unexcuse_submission(base_url: str, course_id: str, assignment_id: int,
                       user_id: int, token: str) -> bool:
    """Remove excused status (set excused: false).

    Used by --undo to revert bulk exemptions.
    """
    headers = {"Authorization": f"Bearer {token}"}
    url = (f"{base_url}/api/v1/courses/{course_id}/assignments/"
           f"{assignment_id}/submissions/{user_id}")

    payload = {"submission": {"excused": False}}

    r = requests.put(url, headers=headers, json=payload, timeout=_TIMEOUT)
    if r.status_code in (200, 201):
        return True

    print(f"  ✗ Failed to unexcuse assignment {assignment_id}: "
          f"HTTP {r.status_code}", file=sys.stderr)
    return False


def fetch_excused_assignments(base_url: str, course_id: str, user_id: int,
                              token: str) -> list[int]:
    """Fetch list of assignment IDs that are currently excused for user.

    Used by --undo to know which assignments to unexcuse.
    """
    headers = {"Authorization": f"Bearer {token}"}
    excused_ids: list[int] = []
    page = 1

    while True:
        r = requests.get(
            f"{base_url}/api/v1/courses/{course_id}/students/submissions",
            headers=headers,
            params={"student_ids[]": user_id, "per_page": 100, "page": page},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break

        for sub in batch:
            if sub.get("excused"):
                excused_ids.append(sub["assignment_id"])
        page += 1

    return excused_ids


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()

    parser = argparse.ArgumentParser(
        description="Bulk excuse assignments for late-enrolling students.",
    )
    parser.add_argument("--user-id", type=int,
                       help="Canvas user_id (numeric)")
    parser.add_argument("--deid-code",
                       help="Deid code from grading/.deid_master.csv")

    # Scope: mutually exclusive
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--before-date",
                      help="Excuse assignments due before YYYY-MM-DD")
    scope.add_argument("--before-week", type=int,
                      help="Excuse assignments due before week N")
    scope.add_argument("--undo", action="store_true",
                      help="Remove excused status (undo previous exemptions)")

    parser.add_argument("--apply", action="store_true",
                       help="Actually write changes (default is dry-run)")

    args = parser.parse_args()

    # Validate user lookup
    if not args.user_id and not args.deid_code:
        print("ERROR: Must provide --user-id or --deid-code", file=sys.stderr)
        return 1

    if args.user_id and args.deid_code:
        print("ERROR: Provide only ONE of --user-id or --deid-code",
              file=sys.stderr)
        return 1

    # Load environment
    load_env()
    token = os.environ.get("CANVAS_API_TOKEN")
    base_url = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    course_id = os.environ.get("CANVAS_COURSE_ID")
    course_start = os.environ.get("COURSE_START_DATE")

    if base_url and not base_url.startswith("http"):
        base_url = "https://" + base_url

    if not token or not base_url or not course_id:
        print("ERROR: Missing required .env: CANVAS_API_TOKEN, "
              "CANVAS_BASE_URL, CANVAS_COURSE_ID", file=sys.stderr)
        return 1

    if args.before_week and not course_start:
        print("ERROR: --before-week requires COURSE_START_DATE in .env",
              file=sys.stderr)
        return 1

    # Resolve user_id
    if args.deid_code:
        deid_master = Path("grading/.deid_master.csv")
        user_id = resolve_user_id_from_deid(args.deid_code, deid_master)
        if not user_id:
            print(f"ERROR: deid_code '{args.deid_code}' not found in "
                  f"{deid_master}", file=sys.stderr)
            return 1
        print(f"Resolved {args.deid_code} → user_id {user_id}")
    else:
        user_id = args.user_id
        print(f"Using user_id {user_id}")

    # Handle --undo
    if args.undo:
        print("\n--undo mode: removing excused status from all assignments")
        print("Fetching currently excused assignments...")
        excused_ids = fetch_excused_assignments(base_url, course_id, user_id, token)

        if not excused_ids:
            print("No excused assignments found for this student.")
            return 0

        print(f"Found {len(excused_ids)} excused assignments")

        if not args.apply:
            print("\nDRY-RUN: Would unexcuse these assignment IDs:")
            for aid in excused_ids:
                print(f"  - {aid}")
            print("\nRe-run with --apply to actually remove excused status.")
            return 0

        print("\nRemoving excused status...")
        success_count = 0
        for aid in excused_ids:
            if unexcuse_submission(base_url, course_id, aid, user_id, token):
                success_count += 1
                print(f"  ✓ Unexcused assignment {aid}")

        print(f"\n✓ Unexcused {success_count}/{len(excused_ids)} assignments")
        return 0

    # Determine cutoff date
    if args.before_week:
        cutoff_date = week_number_to_cutoff_date(args.before_week, course_start)
        print(f"Excusing assignments before Week {args.before_week} "
              f"(before {cutoff_date})")
    else:
        cutoff_date = args.before_date
        print(f"Excusing assignments before {cutoff_date}")

    # Fetch and filter assignments
    print("\nFetching published assignments...")
    all_assignments = fetch_published_assignments(base_url, course_id, token)
    print(f"Found {len(all_assignments)} published assignments with due dates")

    target_assignments = filter_assignments_before_date(all_assignments, cutoff_date)
    print(f"Found {len(target_assignments)} assignments due before {cutoff_date}")

    if not target_assignments:
        print("\nNo assignments to excuse.")
        return 0

    # Display what will be excused
    print("\nAssignments to excuse:")
    for a in target_assignments:
        due_date = a["due_at"][:10]
        points = a.get("points_possible", 0)
        print(f"  - [{a['id']}] {a['name']} (due {due_date}, {points} pts)")

    if not args.apply:
        print("\nDRY-RUN: No changes made.")
        print("Re-run with --apply to actually excuse these assignments.")
        return 0

    # Apply excused status
    print("\nExcusing assignments...")
    success_count = 0
    for a in target_assignments:
        if excuse_submission(base_url, course_id, a["id"], user_id, token):
            success_count += 1
            print(f"  ✓ Excused: {a['name']}")

    print(f"\n✓ Excused {success_count}/{len(target_assignments)} assignments")
    print(f"Student {user_id} is now exempt from assignments before {cutoff_date}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

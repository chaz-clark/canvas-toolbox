#!/usr/bin/env python3
"""
student_late_accommodation.py — Per-student "submit anything late"
accommodation via Canvas assignment overrides.

A routine faculty accommodation: ONE student gets permission to submit
late on some (or all) assignments. The class is unaffected.

HOW THE OVERRIDE IS BUILT
  For each target assignment, write a per-student assignment override that:
    - keeps the assignment's normal `unlock_at` (open date)
    - keeps the assignment's normal `due_at`    (due date)
    - omits `lock_at` (no close date) → student can submit after the due
      date; submission shows up marked "late" but is still accepted

The student STILL sees the original due date in their student-view (no
artificial deadline extension shown); they just don't get locked out
when the due date passes.

PII-FREE LOOKUP
  Resolve the target student with EITHER:
    --user-id 123456        the bare Canvas user_id
    --deid-code S-95DBB6    looked up in grading/.deid_master.csv
                            (built by build_deid_master.py)
  The deid_code lookup reads ONLY the user_id column of the master —
  the student's name is never read, printed, or sent to the agent.

CAVEAT WE LEARNED (DS 460 pilot, 2026-06-26)
  Canvas's GET /assignments/:id/overrides endpoint can hang / be very
  slow on some courses. The --apply path therefore POSTs the override
  directly (after fetching ONE assignment's dates) and does NOT pre-list
  existing overrides. Only the --remove path needs to read overrides,
  and that's an explicit operator choice.

SCOPE — pick ONE of these (mutually exclusive)
  --assignment-id <id>      ONE specific assignment
  --all                     ALL published assignments (whole semester,
                            backdated — students get override on past-due
                            items too)
  --from YYYY-MM-DD         Assignments with due_at >= YYYY-MM-DD (rest
                            of semester from a specific date forward)
  --from-days-ago N         Assignments with due_at >= today - N days
                            (rolling window; e.g. --from-days-ago 14
                            covers the last two weeks through the end
                            of the term — the recommended default for
                            "give them grace from when they hit the
                            wall through the end of the semester")

USAGE — dry-run by default (use --apply to actually write)
  # Preview adding accommodation to ONE assignment
  uv run python lib/tools/student_late_accommodation.py \\
    --deid-code S-95DBB6 --assignment-id 123

  # Apply to ONE assignment
  uv run python lib/tools/student_late_accommodation.py \\
    --user-id 173819 --assignment-id 123 --apply

  # Apply across ALL published assignments (whole semester, backdated)
  uv run python lib/tools/student_late_accommodation.py \\
    --deid-code S-95DBB6 --all --apply

  # From a specific date forward (rest of semester)
  uv run python lib/tools/student_late_accommodation.py \\
    --deid-code S-95DBB6 --from 2026-04-01 --apply

  # Rolling window: last 2 weeks through end of semester
  uv run python lib/tools/student_late_accommodation.py \\
    --deid-code S-95DBB6 --from-days-ago 14 --apply

  # SAS test_reschedule: shift dates forward 7 days (vs the default
  # "drop lock_at" mode used for occasional_extensions)
  uv run python lib/tools/student_late_accommodation.py \\
    --deid-code S-95DBB6 --assignment-id 123 --shift-by-days 7 --apply

  # Remove the accommodation (cleanly undo) — scope flags work for
  # remove too, so you can undo across the same window you applied
  uv run python lib/tools/student_late_accommodation.py \\
    --deid-code S-95DBB6 --all --remove --apply

REQUIRES in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID
REQUIRES: a deid master built by lib/tools/build_deid_master.py (only
if you use --deid-code; --user-id works without it).

Resolves issue #109 — course-wide de-id master + per-student
accommodation primitives. Lifted from the DS 460 pilot and generalized.
"""
from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

try:
    from _override_recalc_helper import force_recalc_for_student
except ImportError:
    # If helper not available, define a no-op
    def force_recalc_for_student(*args, **kwargs) -> int:
        return 0  # No-op if _env_loader not available
import csv
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


_DEFAULT_MASTER = Path("grading/.deid_master.csv")
_OVERRIDE_TITLE = "Late-work accommodation (no close date)"
_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Pure helpers (no I/O — easy to unit-test)
# ---------------------------------------------------------------------------

def resolve_user_id_from_master(master_path: Path, deid_code: str) -> int:
    """Look up a deid_code in the master CSV and return the user_id.

    Reads ONLY the user_id column (the sortable_name column is never read
    or printed). Raises FileNotFoundError if the master doesn't exist;
    raises KeyError if the deid_code isn't present.
    """
    if not master_path.exists():
        raise FileNotFoundError(
            f"deid master not found at {master_path}. "
            f"Build it first with: "
            f"uv run python lib/tools/build_deid_master.py"
        )
    target = deid_code.strip().upper()
    with master_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["deid_code"].strip().upper() == target:
                return int(row["user_id"])
    raise KeyError(
        f"deid_code {deid_code!r} not found in {master_path}. "
        f"Did you rebuild the master after a roster change?"
    )


def build_override_payload(assignment: dict, user_id: int,
                           title: str = _OVERRIDE_TITLE) -> dict:
    """Build the POST body for a late-work accommodation override.

    Keeps `unlock_at` + `due_at` from the assignment; omits `lock_at`
    so Canvas treats it as null (no close date). Returns form-encoded
    field/value pairs (the Canvas API quirk: array fields use [] suffix).
    """
    data: dict[str, str | int] = {
        "assignment_override[student_ids][]": user_id,
        "assignment_override[title]": title,
    }
    if assignment.get("due_at"):
        data["assignment_override[due_at]"] = assignment["due_at"]
    if assignment.get("unlock_at"):
        data["assignment_override[unlock_at]"] = assignment["unlock_at"]
    # lock_at intentionally OMITTED → null → no close date
    return data


def filter_my_overrides(overrides: list[dict], user_id: int) -> list[dict]:
    """From the assignment's overrides list, return only the ones
    targeted at this specific user_id."""
    return [o for o in (overrides or [])
            if user_id in (o.get("student_ids") or [])]


def cutoff_from_days_ago(days: int, today: date | None = None) -> str:
    """Return YYYY-MM-DD for (today - days). The `today` parameter
    exists for testability — defaults to actual today."""
    if today is None:
        today = date.today()
    return (today - timedelta(days=int(days))).isoformat()


def shift_iso_timestamp(ts: str | None, days: int) -> str | None:
    """Shift an ISO 8601 timestamp forward by N days, preserving the
    time-of-day and timezone suffix. Returns None if `ts` is None (so
    callers can pass through null dates).

    Canvas's due_at / unlock_at / lock_at are ISO strings like
    '2026-04-15T23:59:00Z'. We split at 'T', advance the date part by N
    days using date.fromisoformat + timedelta, and re-join. This avoids
    pulling in a full timezone-aware parser for what's a simple offset.
    """
    if not ts:
        return None
    date_part = ts[:10]   # YYYY-MM-DD
    rest = ts[10:]        # T..HH:MM:SSZ (or whatever suffix Canvas sent)
    shifted = (date.fromisoformat(date_part) + timedelta(days=int(days))).isoformat()
    return shifted + rest


def build_shift_payload(assignment: dict, user_id: int, days: int,
                        title: str = "Test reschedule (date-shifted)") -> dict:
    """Build the POST body for a date-shift override (test_reschedule).

    Different from build_override_payload: instead of dropping lock_at,
    this SHIFTS all three dates (unlock_at, due_at, lock_at) forward by
    N days. The student gets a moved availability window — they still
    have a hard close, just N days later.

    Used for SAS `test_reschedule` (catalog key). Different intent from
    `occasional_extensions` (which uses build_override_payload to drop
    lock_at). Faculty picks per accommodation letter.
    """
    data: dict[str, str | int] = {
        "assignment_override[student_ids][]": user_id,
        "assignment_override[title]": title,
    }
    unlock = shift_iso_timestamp(assignment.get("unlock_at"), days)
    due = shift_iso_timestamp(assignment.get("due_at"), days)
    lock = shift_iso_timestamp(assignment.get("lock_at"), days)
    if unlock:
        data["assignment_override[unlock_at]"] = unlock
    if due:
        data["assignment_override[due_at]"] = due
    if lock:
        data["assignment_override[lock_at]"] = lock
    return data


def filter_assignments_by_due_from(assignments: list[dict],
                                   cutoff_date_str: str) -> list[dict]:
    """Return assignments whose due_at >= cutoff_date_str (YYYY-MM-DD).

    Compares the date-prefix of due_at (first 10 chars) against the cutoff,
    which lets us avoid timezone parsing — close enough for accommodation
    scoping (the operator picking "from April 1" doesn't care whether
    an assignment due at 1am UTC on April 1 counts).

    Assignments with null/missing due_at are EXCLUDED — undated
    assignments aren't typically what "from a date" means.
    """
    out = []
    for a in assignments:
        due_at = a.get("due_at")
        if not due_at:
            continue
        if due_at[:10] >= cutoff_date_str:
            out.append(a)
    return out


# ---------------------------------------------------------------------------
# Canvas API
# ---------------------------------------------------------------------------

def fetch_published_assignments(base_url: str, course_id: str,
                                token: str) -> list[dict]:
    """GET /courses/:id/assignments and return ONLY the published ones
    as full dicts (so callers can filter by due_at).

    Paginates over all pages.
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
            if a.get("published"):
                out.append(a)
        page += 1
    return out


def fetch_assignment(base_url: str, course_id: str, assignment_id: int,
                     token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"{base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}",
        headers=headers, timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def post_override(base_url: str, course_id: str, assignment_id: int,
                  payload: dict, token: str) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides",
        headers=headers, data=payload, timeout=_TIMEOUT,
    )
    try:
        body = r.json()
    except ValueError:
        body = {}
    return r.status_code, body


def list_overrides(base_url: str, course_id: str, assignment_id: int,
                   token: str) -> list[dict]:
    """SLOW on some courses — only used by the --remove path."""
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"{base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides",
        headers=headers, params={"per_page": 100}, timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json() or []


def delete_override(base_url: str, course_id: str, assignment_id: int,
                    override_id: int, token: str) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.delete(
        f"{base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides/{override_id}",
        headers=headers, timeout=_TIMEOUT,
    )
    return r.status_code


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--user-id", help="bare Canvas user_id (no PII surface)")
    who.add_argument("--deid-code", help="deid_code from grading/.deid_master.csv")
    scope = ap.add_mutually_exclusive_group(required=True)
    scope.add_argument("--assignment-id", type=int, help="ONE assignment id")
    scope.add_argument("--all", action="store_true",
                       help="ALL published assignments (whole semester, "
                            "backdated)")
    scope.add_argument("--from", dest="from_date", metavar="YYYY-MM-DD",
                       help="published assignments with due_at >= this date "
                            "(rest of semester from a specific date forward)")
    scope.add_argument("--from-days-ago", type=int, metavar="N",
                       help="published assignments due in the last N days "
                            "and onward (e.g. --from-days-ago 14 covers "
                            "the last two weeks through end of term)")
    ap.add_argument("--master", type=Path, default=_DEFAULT_MASTER,
                    help=f"deid master path (default {str(_DEFAULT_MASTER)!r})")
    ap.add_argument("--shift-by-days", type=int, metavar="N",
                    help="(SAS test_reschedule) shift unlock_at + due_at + "
                         "lock_at forward by N days for this student, "
                         "instead of dropping lock_at (the default behavior). "
                         "Use for accommodations that say 'reschedule the "
                         "exam' rather than 'allow late submission'.")
    ap.add_argument("--remove", action="store_true",
                    help="undo: delete this student's accommodation overrides")
    ap.add_argument("--apply", action="store_true",
                    help="actually write the change (without this, dry-run)")
    ap.add_argument("--force-recalc", dest="force_recalc", action="store_true",
                    default=False,
                    help="force Canvas to recalculate overrides after applying (slow on large courses)")
    ap.add_argument("--no-force-recalc", dest="force_recalc", action="store_false",
                    help="skip forcing recalculation (default: overrides usually take effect automatically)")
    args = ap.parse_args()

    base_url = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base_url and not base_url.startswith("http"):
        base_url = "https://" + base_url
    course_id = os.environ.get("CANVAS_COURSE_ID", "")
    token = os.environ.get("CANVAS_API_TOKEN", "")
    if not (base_url and course_id and token):
        print("ERROR: CANVAS_BASE_URL / CANVAS_COURSE_ID / CANVAS_API_TOKEN "
              "must be set in .env or the environment.", file=sys.stderr)
        return 2

    if args.user_id:
        uid = int(args.user_id)
    else:
        try:
            uid = resolve_user_id_from_master(args.master, args.deid_code)
        except (FileNotFoundError, KeyError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    if args.assignment_id:
        assignment_ids = [args.assignment_id]
        scope_label = f"assignment {args.assignment_id}"
    elif args.all:
        assignments = fetch_published_assignments(base_url, course_id, token)
        assignment_ids = [a["id"] for a in assignments]
        scope_label = f"ALL {len(assignment_ids)} published"
    elif args.from_date:
        assignments = fetch_published_assignments(base_url, course_id, token)
        filtered = filter_assignments_by_due_from(assignments, args.from_date)
        assignment_ids = [a["id"] for a in filtered]
        scope_label = f"{len(assignment_ids)} due on/after {args.from_date}"
    else:  # --from-days-ago
        cutoff = cutoff_from_days_ago(args.from_days_ago)
        assignments = fetch_published_assignments(base_url, course_id, token)
        filtered = filter_assignments_by_due_from(assignments, cutoff)
        assignment_ids = [a["id"] for a in filtered]
        scope_label = (f"{len(assignment_ids)} due in the last "
                       f"{args.from_days_ago} days + future (cutoff {cutoff})")

    mode = "REMOVE" if args.remove else "ADD"
    apply_ = "APPLY" if args.apply else "DRY-RUN"
    print(f"student user_id={uid} | scope: {scope_label} "
          f"| {mode} accommodation | {apply_}")

    if not assignment_ids:
        print("No assignments matched the scope. Nothing to do.")
        return 0

    fails = 0
    for aid in assignment_ids:
        if args.remove:
            overrides = list_overrides(base_url, course_id, aid, token)
            mine = filter_my_overrides(overrides, uid)
            if not args.apply:
                print(f"  [DRY] {aid}: would remove {len(mine)} override(s)")
                continue
            for o in mine:
                code = delete_override(base_url, course_id, aid, o["id"], token)
                ok = "OK " if code == 200 else "FAIL"
                if code != 200:
                    fails += 1
                print(f"  [{ok}] {aid}: removed override {o['id']} (HTTP {code})")
        else:
            if not args.apply:
                print(f"  [DRY] {aid}: would add override — keep open/due, "
                      "remove close (lock=null)")
                continue
            assignment = fetch_assignment(base_url, course_id, aid, token)
            if args.shift_by_days:
                payload = build_shift_payload(assignment, uid, args.shift_by_days)
            else:
                payload = build_override_payload(assignment, uid)
            code, body = post_override(base_url, course_id, aid, payload, token)
            ok = "OK " if code in (200, 201) else "FAIL"
            if code not in (200, 201):
                fails += 1
            print(f"  [{ok}] {aid}: override id={body.get('id')} "
                  f"due={body.get('due_at')} unlock={body.get('unlock_at')} "
                  f"lock={body.get('lock_at')}")

    # Force recalculation if we applied overrides (not if we removed them)
    if not args.remove and args.apply and args.force_recalc and assignment_ids:
        print(f"\nForcing Canvas override recalculation...")
        try:
            headers = {"Authorization": f"Bearer {token}"}
            touched = 0
            # Only recalc the specific assignments we just modified (not all assignments!)
            for aid in assignment_ids:
                touched += force_recalc_for_student(
                    base=base_url,
                    headers=headers,
                    course_id=int(course_id),
                    student_id=uid,
                    assignment_id=aid,  # ← Pass the specific assignment
                    quiet=True
                )
            if touched > 0:
                print(f"  [recalc] ✓ Recalculated {touched} assignment override(s)")
            else:
                print(f"  [recalc] No overrides found to recalculate (unexpected)")
        except Exception as e:
            print(f"  [recalc] Warning: recalculation failed: {e}", file=sys.stderr)
            print(f"  [recalc] Overrides were created, but may not take effect immediately.",
                  file=sys.stderr)
            print(f"  [recalc] Run: fix_group_override_recalc.py --course-id {course_id} "
                  f"--student-id {uid}", file=sys.stderr)

    if fails:
        print(f"\n{fails} operation(s) failed. Re-run to retry.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

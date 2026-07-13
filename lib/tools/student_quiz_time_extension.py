#!/usr/bin/env python3
"""
student_quiz_time_extension.py — Per-student "extra time on timed quizzes"
accommodation via Canvas quiz extensions.

A routine BYUI Accessibility Services accommodation: ONE student gets a
time multiplier on all timed quizzes/exams (1.5x = 50% extra; 2.0x =
double time). The class is unaffected.

The catalog (handoffs/2026-06-26-accessibility-accommodations-catalog.md)
identifies extra-time as the dominant SAS ask. Two flavors observed:
  extra_time_1.5x — "Please allow 50% extra time on all timed exams
                    and quizzes."
  extra_time_2.0x — "Please allow 100% extra time (double time) on
                    all exams and quizzes."

HOW THE EXTENSION IS BUILT
  For each target timed quiz, POST to
    /api/v1/courses/:cid/quizzes/:qid/extensions
  with `quiz_extensions[][user_id]` + `quiz_extensions[][extra_time]`
  (in MINUTES). extra_time = ceil(quiz.time_limit * (multiplier - 1)).

WHAT'S IN SCOPE
  Classic Canvas quizzes only. New Quizzes (LTI-based) use a separate
  API and are NOT covered by this tool — they're listed as a follow-up
  in lib/agents/knowledge/deid_master_knowledge.md.

PII-FREE LOOKUP
  --user-id 123456        bare Canvas user_id
  --deid-code S-95DBB6    looked up in grading/.deid_master.csv
                          (built by build_deid_master.py; tool reads
                          only the user_id column)

USAGE — dry-run by default (use --apply to actually write)
  # Preview: 1.5x on every timed classic quiz in the course
  uv run python lib/tools/student_quiz_time_extension.py \\
    --deid-code S-95DBB6 --multiplier 1.5 --all-timed

  # Apply 2.0x (double time) across all timed quizzes
  uv run python lib/tools/student_quiz_time_extension.py \\
    --deid-code S-95DBB6 --multiplier 2.0 --all-timed --apply

  # ONE specific quiz
  uv run python lib/tools/student_quiz_time_extension.py \\
    --deid-code S-95DBB6 --multiplier 1.5 --quiz-id 12345 --apply

  # Custom multiplier (e.g. 1.25x for 25% extra time)
  uv run python lib/tools/student_quiz_time_extension.py \\
    --user-id 173819 --multiplier 1.25 --all-timed --apply

REQUIRES in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID

Resolves SAS catalog keys: extra_time_1.5x, extra_time_2.0x
(see handoffs/2026-06-26-accessibility-accommodations-catalog.md)
"""
from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available

try:
    from _override_recalc_helper import force_recalc_for_student
except ImportError:
    # If helper not available, define a no-op
    def force_recalc_for_student(*args, **kwargs) -> int:
        return 0

import csv
import math
import os
import sys
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


_DEFAULT_MASTER = Path("grading/.deid_master.csv")
_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Pure helpers (no I/O — easy to unit-test)
# ---------------------------------------------------------------------------

def compute_extra_minutes(time_limit_minutes: int | None,
                          multiplier: float) -> int | None:
    """Compute extra minutes to add for a given multiplier.

    Returns None if the quiz is untimed (no time_limit) — the caller
    should skip the quiz silently (no need for an extension when there's
    no time limit to extend).

    Multiplier semantics:
      1.5 → 50% extra time → extra = ceil(time_limit * 0.5)
      2.0 → 100% extra time (double time) → extra = ceil(time_limit * 1.0)
      1.25 → 25% extra time → extra = ceil(time_limit * 0.25)

    Uses math.ceil so partial minutes round UP (giving the student the
    full benefit of the multiplier — never less time than promised).
    """
    if time_limit_minutes is None or time_limit_minutes <= 0:
        return None
    if multiplier <= 1.0:
        return 0  # 1.0x or less = no extension; caller may skip
    return math.ceil(time_limit_minutes * (multiplier - 1.0))


def filter_timed_quizzes(quizzes: list[dict]) -> list[dict]:
    """Return only quizzes that have a non-null, positive time_limit.

    Quizzes without a time limit don't need an extension — the student
    already has unlimited time. Filtering them here means the operator
    doesn't have to think about it.
    """
    out = []
    for q in quizzes:
        tl = q.get("time_limit")
        if tl is None:
            continue
        if isinstance(tl, (int, float)) and tl > 0:
            out.append(q)
    return out


def resolve_user_id_from_master(master_path: Path, deid_code: str) -> int:
    """Look up a deid_code in the master CSV and return the user_id.

    Identical signature + behavior to the helper in
    student_late_accommodation.py — duplicated here so each tool stays
    standalone (no cross-tool import dependency).

    Reads ONLY the user_id column (sortable_name is never read).
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


def build_extension_payload(user_id: int, extra_time_minutes: int) -> dict:
    """Build the POST body for a quiz extension.

    Canvas quirk: extensions are submitted as an array of objects, so
    the form-encoded keys use [] suffix.
    """
    return {
        "quiz_extensions[][user_id]": user_id,
        "quiz_extensions[][extra_time]": extra_time_minutes,
    }


# ---------------------------------------------------------------------------
# Canvas API
# ---------------------------------------------------------------------------

def fetch_timed_quizzes(base_url: str, course_id: str, token: str) -> list[dict]:
    """GET /courses/:id/quizzes (classic quizzes) and return only
    the ones with a time_limit set.

    Note: this endpoint returns CLASSIC quizzes only. New Quizzes (LTI)
    aren't returned here.
    """
    headers = {"Authorization": f"Bearer {token}"}
    out: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{base_url}/api/v1/courses/{course_id}/quizzes",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        page += 1
    return filter_timed_quizzes(out)


def fetch_quiz(base_url: str, course_id: str, quiz_id: int,
               token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"{base_url}/api/v1/courses/{course_id}/quizzes/{quiz_id}",
        headers=headers, timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def post_extension(base_url: str, course_id: str, quiz_id: int,
                   payload: dict, token: str) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{base_url}/api/v1/courses/{course_id}/quizzes/{quiz_id}/extensions",
        headers=headers, data=payload, timeout=_TIMEOUT,
    )
    try:
        body = r.json()
    except ValueError:
        body = {}
    return r.status_code, body


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
    scope.add_argument("--quiz-id", type=int, help="ONE specific quiz id")
    scope.add_argument("--all-timed", action="store_true",
                       help="ALL classic quizzes that have a time limit")
    ap.add_argument("--multiplier", type=float, required=True,
                    help="time multiplier — 1.5 for 50%% extra time, "
                         "2.0 for double time, 1.25 for 25%% extra, etc.")
    ap.add_argument("--master", type=Path, default=_DEFAULT_MASTER,
                    help=f"deid master path (default {str(_DEFAULT_MASTER)!r})")
    ap.add_argument("--apply", action="store_true",
                    help="actually write the change (without this, dry-run)")
    ap.add_argument("--force-recalc", dest="force_recalc", action="store_true",
                    default=True,
                    help="force Canvas to recalculate overrides after applying (default: True)")
    ap.add_argument("--no-force-recalc", dest="force_recalc", action="store_false",
                    help="skip forcing recalculation (faster, but extensions may not take effect)")
    args = ap.parse_args()

    if args.multiplier <= 1.0:
        print(f"ERROR: --multiplier must be > 1.0 (got {args.multiplier}). "
              f"1.0 means no extension; use 1.5 or 2.0 for typical SAS asks.",
              file=sys.stderr)
        return 2

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

    if args.all_timed:
        quizzes = fetch_timed_quizzes(base_url, course_id, token)
    else:
        one = fetch_quiz(base_url, course_id, args.quiz_id, token)
        quizzes = filter_timed_quizzes([one])

    apply_ = "APPLY" if args.apply else "DRY-RUN"
    print(f"student user_id={uid} | {len(quizzes)} timed quiz(zes) "
          f"| multiplier {args.multiplier}x | {apply_}")

    if not quizzes:
        print("No timed quizzes matched. Nothing to do.")
        return 0

    fails = 0
    assignment_ids = []  # Track assignment IDs from graded quizzes
    for q in quizzes:
        qid = q["id"]
        tl = q.get("time_limit")
        extra = compute_extra_minutes(tl, args.multiplier)
        if extra is None or extra <= 0:
            print(f"  [SKIP] quiz {qid}: no time_limit or multiplier <= 1.0")
            continue
        title = q.get("title", "")[:40]
        if not args.apply:
            print(f"  [DRY] quiz {qid} ({title}): "
                  f"would add {extra} min (base {tl} min × {args.multiplier})")
            continue
        payload = build_extension_payload(uid, extra)
        code, body = post_extension(base_url, course_id, qid, payload, token)
        ok = "OK " if code in (200, 201) else "FAIL"
        if code not in (200, 201):
            fails += 1
        print(f"  [{ok}] quiz {qid} ({title}): +{extra} min (HTTP {code})")

        # Track assignment_id for graded quizzes (needed for recalc)
        if code in (200, 201) and q.get("assignment_id"):
            assignment_ids.append(q["assignment_id"])

    # Force recalculation if we applied extensions to graded quizzes
    # (practice quizzes/surveys don't have assignment_ids, so nothing to recalc)
    if args.apply and args.force_recalc and assignment_ids:
        print(f"\nForcing Canvas override recalculation for graded quizzes...")
        try:
            headers = {"Authorization": f"Bearer {token}"}
            touched = 0
            # Only recalc the specific assignments for the quizzes we just modified
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
                print(f"  [recalc] ✓ Recalculated {touched} assignment(s)")
            else:
                print(f"  [recalc] No assignment overrides found (quiz extensions use different mechanism)")
        except Exception as e:
            print(f"  [recalc] Warning: recalculation failed: {e}", file=sys.stderr)
            print(f"  [recalc] Extensions were created, but may not take effect immediately.",
                  file=sys.stderr)
            print(f"  [recalc] Fallback: Run fix_group_override_recalc.py --course-id {course_id} "
                  f"--student-id {uid}", file=sys.stderr)

    if fails:
        print(f"\n{fails} operation(s) failed. Re-run to retry.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

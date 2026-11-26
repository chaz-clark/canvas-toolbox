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

NEW QUIZZES (#513)
  New Quizzes take time extensions and attempts through a separate API:
    POST /api/quiz/v1/courses/:cid/quizzes/:assignment_id/accommodations
  with a JSON array [{"user_id", "extra_time" (MINUTES), "extra_attempts"}].
  --all-timed covers timed Classic Quizzes AND timed New Quizzes; --new-quiz-id
  targets one New Quiz by its assignment id. The response lists `successful`
  and `failed`, and a 200 can still list the student as failed, so only
  "successful and not failed" counts. Canvas offers no way to read an
  accommodation back: confirm in the quiz's Moderate page or in Student View.
  extra_attempts is the TOTAL of extra attempts, not an addition: sending 1
  again to a student who already had 1 gives them nothing new. Extra time
  shows only to a student with an attempt left.
  --manually-unlock and --extend-from-end-at are Classic Quizzes only.
  Per quiz, not course-level: the multiplier needs each quiz's own time
  limit, the course-level call can't give attempts, and how the two levels
  combine is undocumented, so this tool never uses the course-level call.
  A course without New Quizzes answers the listing with 404: that means none,
  and Classic Quizzes go ahead.

PII-FREE LOOKUP
  --user-id 123456        bare Canvas user_id
  --deid-code S-68BC40    looked up in grading/.deid_master.csv
                          (built by build_deid_master.py; tool reads
                          only the user_id column)

USAGE — dry-run by default (use --apply to actually write)
  # Preview: 1.5x on every timed quiz in the course (Classic Quizzes and New Quizzes)
  uv run python lib/tools/student_quiz_time_extension.py \\
    --deid-code S-68BC40 --multiplier 1.5 --all-timed

  # Apply 2.0x (double time) across all timed quizzes
  uv run python lib/tools/student_quiz_time_extension.py \\
    --deid-code S-68BC40 --multiplier 2.0 --all-timed --apply

  # ONE specific quiz
  uv run python lib/tools/student_quiz_time_extension.py \\
    --deid-code S-68BC40 --multiplier 1.5 --quiz-id 12345 --apply

  # ONE New Quiz (its assignment id), with one extra attempt
  uv run python lib/tools/student_quiz_time_extension.py \\
    --deid-code S-68BC40 --multiplier 1.5 --new-quiz-id 67890 --extra-attempts 1 --apply

  # Custom multiplier (e.g. 1.25x for 25% extra time)
  uv run python lib/tools/student_quiz_time_extension.py \\
    --user-id 900001 --multiplier 1.25 --all-timed --apply

  # ONE extra attempt on ONE quiz (no multiplier needed; works on untimed
  # quizzes too). Canvas cannot delete a classic submission, so this is the
  # only route. The quiz's score-keeping policy (highest vs latest) decides
  # whether the old attempt still counts.
  uv run python lib/tools/student_quiz_time_extension.py \\
    --deid-code S-68BC40 --quiz-id 12345 --extra-attempts 1 --apply

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

from canvas_course_guard import enforce as _course_guard  # set for an intervention (#475)

try:
    from dotenv import load_dotenv
    # ~/.canvas/config holds the shared, rotating token and ONLY _env_loader
    # reads it (#293). A bare load_dotenv() sees .env alone, so a repo whose
    # .env carries no token resolves to an empty bearer and 401s as though the
    # token were revoked.
    try:
        from _env_loader import load_env
        load_env()
    except ImportError:
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


def timed_new_quizzes(quizzes: list[dict]) -> list[dict]:
    """Timed New Quizzes from GET /api/quiz/v1/courses/:id/quizzes, as
    {"id": assignment_id, "title", "time_limit": minutes, "new_quiz": True}."""
    out = []
    for q in quizzes or []:
        st = q.get("quiz_settings") or {}
        secs = st.get("session_time_limit_in_seconds") or 0
        if st.get("has_time_limit") and secs > 0:
            out.append({"id": int(q["id"]), "title": q.get("title", ""),
                        "time_limit": secs / 60, "new_quiz": True})
    return out


def accommodation_result(code: int, body: dict, user_id: int) -> tuple[bool, str]:
    """(done, reason) for a New Quizzes accommodations response. A 200 can still
    list the student under `failed`, so only "successful and not failed" counts."""
    body = body if isinstance(body, dict) else {}
    for f in body.get("failed") or []:
        if f.get("user_id") == user_id:
            return False, str(f.get("error") or "listed as failed")
    if code not in (200, 201):
        return False, str(body.get("message") or body.get("errors") or f"HTTP {code}")
    if any(x.get("user_id") == user_id for x in body.get("successful") or []):
        return True, ""
    return False, "the student isn't listed as successful"


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


def build_extension_payload(user_id: int,
                            extra_time_minutes: int | None = None,
                            extra_attempts: int | None = None,
                            manually_unlocked: bool = False,
                            extend_from_end_at: int | None = None) -> dict:
    """Build the POST body for a quiz extension.

    Canvas quirk: extensions are submitted as an array of objects, so
    the form-encoded keys use [] suffix. Only fields that were asked for
    are sent.
    """
    payload: dict = {"quiz_extensions[][user_id]": user_id}
    if extra_time_minutes is not None:
        payload["quiz_extensions[][extra_time]"] = extra_time_minutes
    if extra_attempts is not None:
        payload["quiz_extensions[][extra_attempts]"] = extra_attempts
    if manually_unlocked:
        payload["quiz_extensions[][manually_unlocked]"] = "true"
    if extend_from_end_at is not None:
        payload["quiz_extensions[][extend_from_end_at]"] = extend_from_end_at
    return payload


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


def fetch_new_quizzes(base_url: str, course_id: str, token: str) -> list[dict]:
    """GET /api/quiz/v1/courses/:id/quizzes, following the Link header."""
    headers = {"Authorization": f"Bearer {token}"}
    out: list[dict] = []
    url = f"{base_url}/api/quiz/v1/courses/{course_id}/quizzes"
    params = {"per_page": 100}
    while url:
        r = requests.get(url, headers=headers, params=params, timeout=_TIMEOUT)
        if r.status_code == 404 and not out:
            return []  # New Quizzes isn't available in this course: none to extend
        r.raise_for_status()
        out.extend(r.json())
        url, params = r.links.get("next", {}).get("url"), None
    return out


def fetch_new_quiz(base_url: str, course_id: str, assignment_id: int,
                   token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"{base_url}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}",
        headers=headers, timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def post_new_quiz_accommodation(base_url: str, course_id: str, assignment_id: int,
                                body: list[dict], token: str) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{base_url}/api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/accommodations",
        headers=headers, json=body, timeout=_TIMEOUT,
    )
    try:
        out = r.json()
    except ValueError:
        out = {}
    return r.status_code, out


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
    scope.add_argument("--quiz-id", type=int, help="ONE specific Classic Quiz id")
    scope.add_argument("--new-quiz-id", type=int, metavar="ASSIGNMENT_ID",
                       help="ONE specific New Quiz, by its assignment id (#513)")
    scope.add_argument("--all-timed", action="store_true",
                       help="ALL quizzes with a time limit: Classic Quizzes and New Quizzes")
    ap.add_argument("--multiplier", type=float,
                    help="time multiplier — 1.5 for 50%% extra time, "
                         "2.0 for double time, 1.25 for 25%% extra, etc.")
    ap.add_argument("--extra-attempts", type=int, metavar="N",
                    help="grant N extra attempts (requires --quiz-id or --new-quiz-id). "
                         "For a New Quiz, N is the TOTAL of extra attempts: it replaces "
                         "an earlier number, it doesn't add to it (#513)")
    ap.add_argument("--manually-unlock", action="store_true",
                    help="manually unlock the quiz for this student "
                         "(requires --quiz-id)")
    ap.add_argument("--extend-from-end-at", type=int, metavar="MINUTES",
                    help="extend the student's time MINUTES past the quiz "
                         "end date (requires --quiz-id)")
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

    attempt_opts = (args.extra_attempts is not None or args.manually_unlock
                    or args.extend_from_end_at is not None)
    if args.multiplier is None and not attempt_opts:
        print("ERROR: give --multiplier and/or one of --extra-attempts, "
              "--manually-unlock, --extend-from-end-at.", file=sys.stderr)
        return 2
    if attempt_opts and not (args.quiz_id or args.new_quiz_id):
        print("ERROR: --extra-attempts / --manually-unlock / "
              "--extend-from-end-at need --quiz-id or --new-quiz-id (never course-wide).",
              file=sys.stderr)
        return 2
    if args.new_quiz_id and (args.manually_unlock or args.extend_from_end_at is not None):
        print("ERROR: --manually-unlock and --extend-from-end-at are for Classic Quizzes only; "
              "New Quizzes take a time extension (--multiplier) and --extra-attempts.", file=sys.stderr)
        return 2
    if args.extra_attempts is not None and args.extra_attempts < 1:
        print("ERROR: --extra-attempts must be >= 1.", file=sys.stderr)
        return 2
    if args.multiplier is not None and args.multiplier <= 1.0:
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

    # The course guard, set for an intervention (#475): a course with students
    # enrolled is the normal target; a folder above several courses still refuses.
    _course_guard(base_url, {"Authorization": f"Bearer {token}"}, course_id,
                  mode="write" if args.apply else "read", per_student=True)

    if args.user_id:
        uid = int(args.user_id)
    else:
        try:
            uid = resolve_user_id_from_master(args.master, args.deid_code)
        except (FileNotFoundError, KeyError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    listing_failed = ""
    if args.all_timed:
        quizzes = fetch_timed_quizzes(base_url, course_id, token)
        try:
            quizzes += timed_new_quizzes(fetch_new_quizzes(base_url, course_id, token))
        except (requests.RequestException, ValueError) as exc:
            # Classic Quizzes still go ahead; the run is reported as failed.
            listing_failed = f"couldn't list New Quizzes ({exc})"
            print(f"  [FAIL] {listing_failed}; Classic Quizzes only")
    elif args.new_quiz_id:
        nq = fetch_new_quiz(base_url, course_id, args.new_quiz_id, token)
        timed = timed_new_quizzes([nq])
        # Attempt grants apply to untimed quizzes too.
        quizzes = timed or ([{"id": args.new_quiz_id, "title": nq.get("title", ""),
                              "time_limit": None, "new_quiz": True}] if attempt_opts else [])
        if not quizzes:
            print(f"New Quiz {args.new_quiz_id} has no time limit, so extra time changes "
                  f"nothing. Nothing to do.")
            return 0
    else:
        one = fetch_quiz(base_url, course_id, args.quiz_id, token)
        # Attempt grants apply to untimed quizzes too.
        quizzes = [one] if attempt_opts else filter_timed_quizzes([one])

    apply_ = "APPLY" if args.apply else "DRY-RUN"
    mult = f"multiplier {args.multiplier}x" if args.multiplier else "no time change"
    print(f"student user_id={uid} | {len(quizzes)} quiz(zes) "
          f"| {mult} | {apply_}")

    if not quizzes and not listing_failed:
        print("No timed quizzes matched. Nothing to do.")
        return 0

    fails = 1 if listing_failed else 0
    reasons = [listing_failed] if listing_failed else []
    new_quizzes_done = 0
    assignment_ids = []  # Track assignment IDs from graded quizzes
    for q in quizzes:
        qid = q["id"]
        kind = "New Quiz" if q.get("new_quiz") else "quiz"
        tl = q.get("time_limit")
        extra = None
        if args.multiplier is not None:
            extra = compute_extra_minutes(tl, args.multiplier)
            if (extra is None or extra <= 0) and not attempt_opts:
                print(f"  [SKIP] {kind} {qid}: no time_limit or multiplier <= 1.0")
                continue
            if extra is not None and extra <= 0:
                extra = None
        title = q.get("title", "")[:40]
        parts = []
        if extra:
            parts.append(f"+{extra} min")
        if args.extra_attempts is not None:
            parts.append(f"+{args.extra_attempts} attempt(s)")
        if args.manually_unlock:
            parts.append("manually unlocked")
        if args.extend_from_end_at is not None:
            parts.append(f"{args.extend_from_end_at} min from end_at")
        what = ", ".join(parts) or "nothing"
        if not args.apply:
            print(f"  [DRY] {kind} {qid} ({title}): would grant {what}")
            continue
        if q.get("new_quiz"):
            acc = {"user_id": uid}
            if extra:
                acc["extra_time"] = extra
            if args.extra_attempts is not None:
                acc["extra_attempts"] = args.extra_attempts
            try:
                code, body = post_new_quiz_accommodation(base_url, course_id, qid, [acc], token)
                done, reason = accommodation_result(code, body, uid)
            except requests.RequestException as exc:
                code, done, reason = 0, False, f"no answer from Canvas ({exc})"
            if done:
                new_quizzes_done += 1
                print(f"  [OK ] New Quiz {qid} ({title}): {what} (HTTP {code})")
            else:
                fails += 1
                reasons.append(f"New Quiz {qid}: {reason[:120]}")
                print(f"  [FAIL] New Quiz {qid} ({title}): {what}: {reason[:200]}")
            continue
        payload = build_extension_payload(
            uid, extra, args.extra_attempts, args.manually_unlock,
            args.extend_from_end_at)
        code, body = post_extension(base_url, course_id, qid, payload, token)
        ok = "OK " if code in (200, 201) else "FAIL"
        if code not in (200, 201):
            fails += 1
            reasons.append(f"quiz {qid}: HTTP {code}")
        print(f"  [{ok}] quiz {qid} ({title}): {what} (HTTP {code})")

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

    if any(q.get("new_quiz") for q in quizzes):
        lead = (f"{new_quizzes_done} New Quiz change(s) accepted. " if args.apply
                else "After --apply: ")
        print(f"\n{lead}Canvas can't be asked whether a New Quiz change applied: "
              f"check the quiz's Moderate page, or open it in Student View, once the "
              f"student has an attempt available.")

    if fails:
        print(f"\n{fails} operation(s) failed: {'; '.join(reasons)}. "
              f"A re-run helps only if that reason was temporary.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

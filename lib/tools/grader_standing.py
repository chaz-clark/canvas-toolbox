#!/usr/bin/env python3
"""Push instructor-computed STANDING grades to a No-Submission column (#242).

WHY THIS EXISTS
  Canvas's automatic-zero / missing policy makes a course's running total
  misleading (0s sit on not-yet-graded work), and grader_push's `regrade_gate`
  deliberately REFUSES to overwrite an already-graded submission with no new
  resubmission — it guards against stacked COMMENTS. Neither is wrong, but together
  they block a legitimate instructor workflow: a single "your grade" No-Submission
  column, computed from a syllabus table, that the instructor wants to refresh
  weekly so students always see an accurate standing.

  Standing is a different shape from feedback:
    - roster-keyed (by Canvas user_id), not submission-file-keyed
    - value-only: no comments, no disclosure tag, no de-identification — the
      instructor OWNS the number; it is not AI-drafted feedback
    - INTENTIONALLY overwritten every run
  So it gets its own sanctioned writer rather than bending grader_push's
  submission/feedback machinery (the M119 "split logic from transport" lesson).

  It REUSES grader_push's env/auth, canvas_course_guard, submission fetch, and
  manual-post release, plus the TTY-safe confirmation. The value-only write is the
  only new code — so the two writers can't drift on the parts that matter (which
  course is safe, how to authenticate, how to release manually-posted grades).

SAFETY — this column is often weighted 100%, so a bad CSV row corrupts a whole
grade. Guards, in order:
  - Roster resolution HARD-FAILS on any unmatched or ambiguous key: for a
    100%-weight write, never silently skip a student or grade the wrong one.
  - Dry-run by DEFAULT: prints a FERPA-safe diff (user_id: current -> new, no
    names) and writes NOTHING until you pass --push.
  - Out-of-bounds is a HARD FAIL: a numeric grade < 0 or > points_possible is a
    bug, always — it aborts --push.
  - Big-drop guard: a fall larger than --swing-threshold (the classic symptom of
    a shifted/misaligned CSV) is flagged; --push aborts unless --allow-swings.
  - canvas_course_guard: refuses a live enrolled-course write unless --allow-enrolled.
  - --yes is ALLOWED here (deterministic, instructor-computed, value-only) so the
    weekly run can be automated — this is on the safe side of the HG-5 line, unlike
    grader_push's commented pushes. Without --yes, confirmation demands a TTY
    (shared with grader_push, #241), so a piped 'push' can't stand in for you.

INPUT CONTRACT
  A CSV your syllabus-table script emits. Two columns matter (auto-detected, or
  name them with --key-column / --grade-column):
    key   : one of user_id / canvas_user_id / id / sis_user_id / login_id /
            student_id / email  (whatever your script has; it's resolved to a
            Canvas user_id against the course roster)
    grade : one of grade / final_grade / standing / points / score
            (a number OR a letter — whatever the assignment's grading type takes)
  Everything else in the CSV is ignored.
"""
from __future__ import annotations

import argparse
import csv
import sys

try:
    from _env_loader import force_utf8_console, load_env
    load_env()
except ImportError:
    def force_utf8_console() -> None:
        pass

import requests

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

try:
    from canvas_course_guard import enforce as guard_enforce
except ImportError:
    guard_enforce = None

# Reuse grader_push's env, roster/submission fetch, post-policy release, and the
# TTY-safe confirmation — one source of truth for the parts that must not drift.
from grader_push import (
    _env_canvas,
    fetch_submissions,
    assignment_posts_manually,
    post_assignment_grades,
    require_typed_confirmation,
)

_TIMEOUT = 30
_KEY_COLS = ("user_id", "canvas_user_id", "id", "sis_user_id", "sis_id",
             "login_id", "login", "student_id", "sis_login_id", "email")
_GRADE_COLS = ("grade", "final_grade", "standing", "your_grade", "points", "score")


def _pick_column(fieldnames, candidates, override):
    """Return the CSV column to use, preferring an explicit --override, else the
    first candidate present (case-insensitive)."""
    lower = {f.lower(): f for f in (fieldnames or [])}
    if override:
        if override in (fieldnames or []):
            return override
        if override.lower() in lower:
            return lower[override.lower()]
        raise SystemExit(f"⛔ column {override!r} not in CSV header: {fieldnames}")
    for c in candidates:
        if c in lower:
            return lower[c]
    return None


def fetch_roster_index(base, cid, headers):
    """Map every student identifier -> Canvas user_id, and the set of active ids.

    Returns (index, active_ids). `index` maps str(user_id), sis_user_id, login_id,
    and email (all lowercased) to a numeric user_id. A string that maps to two
    different users is recorded as ambiguous (value None) so resolution HARD-FAILS
    on it rather than guessing.
    """
    index: dict[str, int | None] = {}
    active: set[int] = set()

    def _add(token, uid):
        if token is None:
            return
        k = str(token).strip().lower()
        if not k:
            return
        if k in index and index[k] != uid:
            index[k] = None  # ambiguous — two users share this identifier
        else:
            index.setdefault(k, uid)

    url = (f"{base}/api/v1/courses/{cid}/users?enrollment_type[]=student"
           "&per_page=100&include[]=enrollments&include[]=email")
    while url:
        r = requests.get(url, headers=headers, timeout=_TIMEOUT)
        r.raise_for_status()
        for u in r.json() or []:
            uid = u.get("id")
            if uid is None:
                continue
            uid = int(uid)
            _add(uid, uid)
            _add(u.get("sis_user_id"), uid)
            _add(u.get("login_id"), uid)
            _add(u.get("email"), uid)
            for e in u.get("enrollments") or []:
                if (e.get("enrollment_state") or "").lower() in ("active", "invited"):
                    active.add(uid)
        import re
        m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link", ""))
        url = m.group(1) if m else None
    return index, active


def load_standing_rows(path, key_override, grade_override):
    """Read (raw_key, grade_str) pairs from the CSV. Fails loudly if the key or
    grade column can't be found — better than silently pushing nothing."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        key_col = _pick_column(reader.fieldnames, _KEY_COLS, key_override)
        grade_col = _pick_column(reader.fieldnames, _GRADE_COLS, grade_override)
        if not key_col:
            raise SystemExit(f"⛔ no key column found. Have {reader.fieldnames}; "
                             f"expected one of {_KEY_COLS} or pass --key-column.")
        if not grade_col:
            raise SystemExit(f"⛔ no grade column found. Have {reader.fieldnames}; "
                             f"expected one of {_GRADE_COLS} or pass --grade-column.")
        rows = []
        for line in reader:
            raw_key = (line.get(key_col) or "").strip()
            grade = (line.get(grade_col) or "").strip()
            if raw_key or grade:
                rows.append((raw_key, grade))
    return rows, key_col, grade_col


def _as_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def plan_writes(rows, index, active, current_by_uid, points_possible, swing_threshold):
    """Resolve every row to a user_id and classify it. Returns (plan, problems).

    plan: list of dicts {uid, grade, current, new_score, status}. Statuses:
      write / same (no-op) — safe to proceed.
    problems: fatal issues (unmatched/ambiguous key, out-of-bounds) that must
      abort --push; and 'big-drop' warnings that abort unless --allow-swings.
    """
    plan, problems = [], []
    for raw_key, grade in rows:
        uid = index.get(raw_key.lower())
        if raw_key.lower() not in index:
            problems.append(("unmatched", f"key {raw_key!r} matches no enrolled student"))
            continue
        if uid is None:
            problems.append(("ambiguous", f"key {raw_key!r} matches more than one student"))
            continue
        new_score = _as_float(grade)
        if new_score is not None and points_possible is not None and (
                new_score < 0 or new_score > points_possible):
            problems.append(("out-of-bounds",
                             f"user {uid}: grade {grade} outside [0, {points_possible}]"))
            continue
        cur = current_by_uid.get(uid, {})
        cur_grade, cur_score = cur.get("grade"), cur.get("score")
        status = "same" if str(cur_grade or "").strip() == grade else "write"
        if status == "write" and cur_score is not None and new_score is not None \
                and (cur_score - new_score) > swing_threshold:
            problems.append(("big-drop",
                             f"user {uid}: {cur_score} -> {new_score} "
                             f"(drop > {swing_threshold})"))
        plan.append({"uid": uid, "grade": grade, "current": cur_grade,
                     "new_score": new_score, "status": status,
                     "inactive": uid not in active})
    return plan, problems


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(
        description="Push instructor-computed standing grades to a No-Submission "
                    "column (value-only, dry-run by default, gated).")
    ap.add_argument("--csv", required=True, help="standing CSV your script emits")
    ap.add_argument("--assignment-id", required=True, help="the 'your grade' assignment id")
    ap.add_argument("--course-id", default=None, help="defaults to $CANVAS_COURSE_ID")
    ap.add_argument("--key-column", default=None, help="override auto-detected key column")
    ap.add_argument("--grade-column", default=None, help="override auto-detected grade column")
    ap.add_argument("--swing-threshold", type=float, default=20.0,
                    help="flag a score drop larger than this (default 20)")
    ap.add_argument("--allow-swings", action="store_true",
                    help="proceed despite big-drop warnings (out-of-bounds still aborts)")
    ap.add_argument("--push", action="store_true", help="actually write (else dry-run)")
    ap.add_argument("--yes", action="store_true",
                    help="skip the typed confirmation — for automated weekly runs")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="bypass canvas_course_guard for your own enrolled course")
    ap.add_argument("--post", action="store_true",
                    help="release grades after push if the assignment posts manually")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    args = ap.parse_args()

    tok, env_cid, base = _env_canvas()
    cid = args.course_id or env_cid
    if not (tok and base and cid):
        print("⛔ set CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID (or --course-id).",
              file=sys.stderr)
        return 1
    headers = {"Authorization": f"Bearer {tok}"}
    aid = args.assignment_id

    # Assignment meta — name, points_possible (bounds), posting policy.
    meta = {}
    try:
        rm = requests.get(f"{base}/api/v1/courses/{cid}/assignments/{aid}",
                          headers=headers, timeout=_TIMEOUT)
        if rm.status_code < 400:
            meta = rm.json() or {}
    except requests.RequestException:
        pass
    points_possible = meta.get("points_possible")
    print(f"Standing push -> assignment {aid} "
          f"({meta.get('name', '?')}; points_possible={points_possible}) on course {cid}")

    rows, key_col, grade_col = load_standing_rows(args.csv, args.key_column, args.grade_column)
    print(f"  read {len(rows)} row(s) from {args.csv} "
          f"(key='{key_col}', grade='{grade_col}')")

    index, active = fetch_roster_index(base, cid, headers)
    current = {s["user_id"]: s for s in fetch_submissions(base, cid, headers, aid)}
    plan, problems = plan_writes(rows, index, active, current,
                                 points_possible, args.swing_threshold)

    # FERPA-safe diff — user_id + old -> new only, never names.
    writes = [p for p in plan if p["status"] == "write"]
    for p in plan:
        tag = "  [inactive]" if p["inactive"] else ""
        mark = "WRITE" if p["status"] == "write" else "same "
        print(f"  [{mark}] user {p['uid']}: {p['current'] or '—'} -> {p['grade']}{tag}")

    fatal = [m for kind, m in problems if kind in ("unmatched", "ambiguous", "out-of-bounds")]
    drops = [m for kind, m in problems if kind == "big-drop"]
    for m in fatal:
        print(f"  ⛔ {m}", file=sys.stderr)
    for m in drops:
        print(f"  ⚠️  big drop: {m}", file=sys.stderr)

    print(f"\n{len(writes)} to write, {len(plan) - len(writes)} unchanged, "
          f"{len(fatal)} fatal, {len(drops)} big-drop warning(s).")

    if fatal:
        print("⛔ Fatal problems above — nothing written. Fix the CSV/roster and re-run.",
              file=sys.stderr)
        return 1
    if drops and not args.allow_swings:
        print("⛔ Big-drop warning(s) — nothing written. Review, then re-run with "
              "--allow-swings if intended.", file=sys.stderr)
        return 1
    if not args.push:
        print("\nDry run — nothing written. Add --push to write.")
        return 0
    if not writes:
        print("Nothing to write (all values already current).")
        return 0

    # canvas_course_guard: refuse a live enrolled-course write unless --allow-enrolled.
    if guard_enforce:
        guard_enforce(base, headers, cid, mode="write", allow_override=args.allow_enrolled)

    if not args.yes:
        print(f"\nThis writes {len(writes)} standing grade(s) to the LIVE course {cid}.")
        if not require_typed_confirmation("Type 'push' to confirm: ", "push"):
            print("Aborted.")
            return 1

    pushed, failed = 0, 0
    for p in writes:
        resp = requests.put(
            f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions/{p['uid']}",
            headers=headers, data={"submission[posted_grade]": p["grade"]}, timeout=_TIMEOUT)
        if resp.status_code < 400:
            print(f"  pushed user {p['uid']}: {p['current'] or '—'} -> {p['grade']}")
            pushed += 1
        else:
            print(f"  ⛔ user {p['uid']}: HTTP {resp.status_code} {resp.text[:120]}",
                  file=sys.stderr)
            failed += 1
    print(f"\nPushed {pushed}, failed {failed}.")

    if args.post and pushed and assignment_posts_manually(base, cid, headers, aid):
        ok, detail = post_assignment_grades(base, cid, headers, aid)
        print(f"  {'released' if ok else '⛔ release failed'}: {detail}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

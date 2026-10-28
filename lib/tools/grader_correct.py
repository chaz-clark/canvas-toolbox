#!/usr/bin/env python3
"""Instructor-directed grade CORRECTION for already-graded work (#434).

WHY THIS EXISTS
  `grader_push --regrade` is resubmission-only: for a graded submission nobody has
  resubmitted it refuses ("already graded, no new submission"). `grader_standing`
  only fits a No-Submission "your grade" column. So when the instructor (teacher of
  record) finds a grader/TA entered wrong grades, no sanctioned writer could fix
  them and the instructor had to edit every cell by hand. This is that writer.

  It is NOT a way around grader_push's gates: the instructor supplies the EXACT
  per-student value (and optionally the note the student sees). Nothing is inferred,
  there is no "all students" mode, and no AI judgment is in the grade.

INPUT CONTRACT
  A CSV with one row per student to correct:
    key     : user_id / canvas_user_id / id / sis_user_id / login_id / email
    grade   : new_grade (preferred) / corrected_grade / grade   — the NEW value
    comment : (optional) comment / note / text / message — instructor-supplied text
              shown to the student. Rows with no comment change the grade only.
  Other columns (current grade, etc.) are ignored. Name the columns with
  --key-column / --grade-column / --comment-column if the header differs.

GUARDS, in order
  - Unmatched or ambiguous key, duplicate student, Test Student, inactive
    enrollment, no submission record, or a grade invalid for the assignment's
    grading_type / out of [0, points_possible]  -> HARD FAIL, nothing written.
  - Dry-run by DEFAULT: prints a FERPA-safe old -> new preview (user_id only).
  - Overwriting an existing, different grade (up OR down) needs --allow-change.
    Filling an empty grade does not. Unchanged rows are skipped.
  - canvas_course_guard: refuses a live enrolled-course write unless --allow-enrolled.
  - The grade_guardian hook asks the instructor to click before --push runs.
  - Comments are SUPERSEDE-SAFE: the new comment is posted, then this tool's prior
    correction comment for that student (from the ledger) is deleted, so re-runs never
    stack. Only comment ids this tool logged are ever deleted.
  - Every write is logged (old and new value, comment id) to the ledger, so a
    correction is auditable and reversible. The ledger lives under grading/, which is
    gitignored. After the writes, the grades are re-read from Canvas and verified.

--yes is allowed (instructor-supplied values, not AI-drafted); the grade_guardian
click is the approval. Never hand-write these edits as a custom script.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

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

# One source of truth for the parts that must not drift: env/auth, roster
# resolution, the --yes/TTY decision, grade classification, the comment ledger,
# disclosure tags, Test-Student/inactive filtering, and manual-post release.
from grader_push import (
    _env_canvas,
    _read_comment_ledger,
    append_disclosure_tag,
    assignment_posts_manually,
    comments_to_supersede,
    DISCLOSURE_TAGS,
    fetch_active_filter,
    fetch_submissions,
    normalize_grade,
    post_assignment_grades,
    regression_check,
    resolve_disclosure_kind,
    validate_grade_for_grading_type,
)
from grader_standing import _pick_column, fetch_roster_index, standing_push_decision

_TIMEOUT = 30
DEFAULT_LOG = Path("grading/.grade_corrections.md")
_KEY_COLS = ("user_id", "canvas_user_id", "id", "sis_user_id", "sis_id",
             "login_id", "login", "student_id", "email")
_GRADE_COLS = ("new_grade", "corrected_grade", "correct_grade", "grade")
_COMMENT_COLS = ("comment", "note", "text", "message", "feedback")


def load_correction_rows(path, key_override, grade_override, comment_override):
    """Read (raw_key, grade, comment) rows. Fails loudly on a missing key/grade
    column. A row with a key but a blank grade is an error (never a silent skip)."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        key_col = _pick_column(reader.fieldnames, _KEY_COLS, key_override)
        grade_col = _pick_column(reader.fieldnames, _GRADE_COLS, grade_override)
        com_col = _pick_column(reader.fieldnames, _COMMENT_COLS, comment_override) \
            if comment_override or any(c.lower() in _COMMENT_COLS
                                       for c in (reader.fieldnames or [])) else None
        if not key_col:
            raise SystemExit(f"⛔ no key column. Have {reader.fieldnames}; expected one "
                             f"of {_KEY_COLS} or pass --key-column.")
        if not grade_col:
            raise SystemExit(f"⛔ no grade column. Have {reader.fieldnames}; expected "
                             f"one of {_GRADE_COLS} or pass --grade-column.")
        rows = []
        for line in reader:
            key = (line.get(key_col) or "").strip()
            grade = (line.get(grade_col) or "").strip()
            comment = (line.get(com_col) or "").strip() if com_col else ""
            if key or grade or comment:
                rows.append((key, grade, comment))
    return rows, key_col, grade_col, com_col


def _same_grade(current, new) -> bool:
    cc, cr = normalize_grade(current)
    nc, nr = normalize_grade(new)
    if cc == "empty" or nc == "empty":
        return cc == nc
    return cc == nc and cr == nr


def classify_change(current, new) -> str:
    """'same' | 'first' | 'up' | 'down' | 'changed' (cross-type: letter<->number)."""
    if _same_grade(current, new):
        return "same"
    verdict = regression_check(current, new)
    return {"first_fill": "first", "ok": "up", "regression": "down"}.get(verdict, "changed")


def plan_corrections(rows, index, active, test_id, current_by_uid, grading_type,
                     points_possible, allow_test=False):
    """Resolve and classify every row. Returns (plan, fatal) where each plan item is
    {uid, grade, comment, current, change}. Anything in `fatal` aborts the run.
    `allow_test` (operator-explicit --test-user) lifts the Test Student refusal."""
    plan, fatal, seen = [], [], set()
    for raw_key, grade, comment in rows:
        k = raw_key.lower()
        if not raw_key or k not in index:
            fatal.append(f"key {raw_key!r} matches no enrolled student")
            continue
        uid = index[k]
        if uid is None:
            fatal.append(f"key {raw_key!r} matches more than one student")
            continue
        if uid in seen:
            fatal.append(f"user {uid}: appears more than once in the CSV")
            continue
        seen.add(uid)
        if test_id is not None and uid == test_id and not allow_test:
            fatal.append(f"user {uid}: is the Test Student — refused")
            continue
        if uid not in active and not (allow_test and uid == test_id):
            fatal.append(f"user {uid}: enrollment is not active — refused")
            continue
        if uid not in current_by_uid:
            fatal.append(f"user {uid}: no submission record on this assignment")
            continue
        status, why = validate_grade_for_grading_type(grade, grading_type)
        if status in ("sentinel", "invalid", "not_graded"):
            fatal.append(f"user {uid}: grade {grade!r} refused — {why}")
            continue
        kind, val = normalize_grade(grade)
        if (grading_type or "").lower() == "points" and kind == "numeric" \
                and points_possible is not None and not (0 <= val <= points_possible):
            fatal.append(f"user {uid}: grade {grade} outside [0, {points_possible}]")
            continue
        current = current_by_uid[uid].get("grade")
        plan.append({"uid": uid, "grade": grade, "comment": comment,
                     "current": current, "change": classify_change(current, grade)})
    return plan, fatal


def needs_allow_change(plan) -> list:
    """Rows that overwrite an existing, different grade (any direction)."""
    return [p for p in plan if p["change"] in ("up", "down", "changed")]


def ledger_key(uid) -> str:
    return f"user-{uid}"


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(
        description="Correct already-graded work to exact instructor-supplied values "
                    "(dry-run by default; overwriting a grade needs --allow-change).")
    ap.add_argument("--csv", required=True, help="CSV of user_id + new grade (+ optional comment)")
    ap.add_argument("--assignment-id", required=True)
    ap.add_argument("--course-id", default=None, help="defaults to $CANVAS_COURSE_ID")
    ap.add_argument("--key-column", default=None)
    ap.add_argument("--grade-column", default=None)
    ap.add_argument("--comment-column", default=None)
    ap.add_argument("--test-user", type=int, default=None,
                    help="operator-explicit: write to the course's Test Student (must be "
                         "its real id). Refuses any other row — for sandbox validation.")
    ap.add_argument("--disclosure", default=None, choices=sorted(DISCLOSURE_TAGS),
                    help="provenance tag appended to comments (default: "
                         "$CANVAS_DISCLOSURE_DEFAULT, else 'ai'). 'script' = a script "
                         "computed the grade and the note is the instructor's own text.")
    ap.add_argument("--allow-change", action="store_true",
                    help="permit overwriting an existing, different grade — up OR down")
    ap.add_argument("--push", action="store_true", help="actually write (else dry-run)")
    ap.add_argument("--yes", action="store_true",
                    help="skip the terminal prompt once the instructor approved the preview")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="bypass canvas_course_guard for your own enrolled course")
    ap.add_argument("--post", action="store_true",
                    help="release grades after push if the assignment posts manually")
    ap.add_argument("--log", default=str(DEFAULT_LOG),
                    help=f"correction ledger (default {DEFAULT_LOG}; keep it gitignored)")
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
    disclosure_kind = resolve_disclosure_kind(args.disclosure)

    rm = requests.get(f"{base}/api/v1/courses/{cid}/assignments/{aid}",
                      headers=headers, timeout=_TIMEOUT)
    rm.raise_for_status()
    meta = rm.json() or {}
    gtype, pposs = meta.get("grading_type"), meta.get("points_possible")
    print(f"Grade correction -> assignment {aid} ({meta.get('name', '?')}; "
          f"grading_type={gtype}; points_possible={pposs}) on course {cid}")

    rows, key_col, grade_col, com_col = load_correction_rows(
        args.csv, args.key_column, args.grade_column, args.comment_column)
    print(f"  read {len(rows)} row(s) from {args.csv} (key='{key_col}', "
          f"grade='{grade_col}', comment={com_col!r})")

    index, _ = fetch_roster_index(base, cid, headers)
    active, _inactive, test_id = fetch_active_filter(base, cid, headers)
    current = {s["user_id"]: s for s in fetch_submissions(base, cid, headers, aid)}
    if args.test_user is not None:
        if test_id is None or args.test_user != test_id:
            print(f"⛔ --test-user {args.test_user} is not this course's Test Student.",
                  file=sys.stderr)
            return 1
        index[str(test_id)] = test_id
    plan, fatal = plan_corrections(rows, index, active, test_id, current, gtype, pposs,
                                   allow_test=args.test_user is not None)
    if args.test_user is not None:
        fatal += [f"user {p['uid']}: --test-user allows only the Test Student"
                  for p in plan if p["uid"] != test_id]

    for p in plan:
        mark = {"same": "same ", "first": "FIRST", "up": "UP   ",
                "down": "DOWN ", "changed": "CHG  "}[p["change"]]
        note = "  +comment" if p["comment"] and p["change"] != "same" else ""
        print(f"  [{mark}] user {p['uid']}: {p['current'] or '—'} -> {p['grade']}{note}")
    for m in fatal:
        print(f"  ⛔ {m}", file=sys.stderr)

    writes = [p for p in plan if p["change"] != "same"]
    overwrites = needs_allow_change(plan)
    print(f"\n{len(writes)} to write ({len(overwrites)} overwrite an existing grade), "
          f"{len(plan) - len(writes)} unchanged, {len(fatal)} fatal.")
    if any(p["comment"] for p in writes):
        print(f"Disclosure tag on comments: {DISCLOSURE_TAGS[disclosure_kind]!r} "
              f"(--disclosure {disclosure_kind}).")

    if fatal:
        print("⛔ Fatal problems above — nothing written. Fix the CSV/roster and re-run.",
              file=sys.stderr)
        return 1
    if not args.push:
        flag = "" if not overwrites else " (overwrites need --allow-change)"
        print(f"\nDry run — nothing written. Add --push to write{flag}.")
        return 0
    if overwrites and not args.allow_change:
        print(f"⛔ {len(overwrites)} row(s) overwrite an existing grade — nothing written. "
              "Re-run with --allow-change if the instructor approved these exact "
              "changes.", file=sys.stderr)
        return 1
    if not writes:
        print("Nothing to write (all values already current).")
        return 0

    if guard_enforce:
        guard_enforce(base, headers, cid, mode="write", allow_override=args.allow_enrolled)

    decision = standing_push_decision(args.yes, sys.stdin.isatty())
    if decision == "needs-yes":
        print(f"\nThis would correct {len(writes)} grade(s) on the LIVE course {cid}.")
        print("\nⓘ Non-interactive run. These are instructor-supplied values (not "
              "AI-drafted), so --yes IS allowed once the instructor has approved the "
              "preview above. Do NOT send them to a terminal.", file=sys.stderr)
        print("Aborted — re-run with --yes once the instructor confirms the preview.")
        return 1
    if decision == "prompt":
        print(f"\nThis corrects {len(writes)} grade(s) on the LIVE course {cid}.")
        if input("Type 'push' to confirm: ").strip().lower() != "push":
            print("Aborted.")
            return 1

    log = Path(args.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    prior = _read_comment_ledger(log, str(aid))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pushed, failed = 0, 0
    pushed_uids: set = set()
    with log.open("a", encoding="utf-8") as lg:
        for p in writes:
            uid = p["uid"]
            key = ledger_key(uid)
            url = f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions/{uid}"
            data = {"submission[posted_grade]": p["grade"]}
            if p["comment"]:
                data["comment[text_comment]"] = append_disclosure_tag(
                    p["comment"], disclosure_kind)
            resp = requests.put(url, headers=headers, data=data, timeout=_TIMEOUT)
            if resp.status_code >= 400:
                print(f"  ⛔ user {uid}: HTTP {resp.status_code} {resp.text[:120]}",
                      file=sys.stderr)
                failed += 1
                if 400 <= resp.status_code < 500:
                    print("\n⛔ 4xx — STOP (P-003). Investigate before re-running.",
                          file=sys.stderr)
                    break
                continue
            lg.write(f"- {key}: grade correction {p['current'] or '—'} → {p['grade']} "
                     f"({p['change']}) on assignment {aid} at {stamp}\n")
            print(f"  corrected user {uid}: {p['current'] or '—'} -> {p['grade']}")
            pushed += 1
            pushed_uids.add(uid)
            if not p["comment"]:
                continue
            try:
                sc = (resp.json() or {}).get("submission_comments") or []
                new_id = (sc[-1] if sc else {}).get("id")
            except (ValueError, TypeError):
                new_id = None
            if new_id is None:
                continue
            lg.write(f"- {key}: comment {new_id} pushed to assignment {aid}\n")
            # Supersede: delete this tool's earlier correction comment(s) for the same
            # student only after the new one landed, so a failed post never leaves
            # the student with nothing.
            for s_key, s_id in comments_to_supersede(prior, {key}):
                if s_id == new_id:
                    continue
                d = requests.delete(f"{url}/comments/{s_id}", headers=headers,
                                    timeout=_TIMEOUT)
                if d.status_code < 400 or d.status_code == 404:
                    lg.write(f"- {key}: comment {s_id} retracted from assignment {aid} "
                             "(superseded by correction)\n")
                    print(f"    superseded prior correction comment {s_id}")
                else:
                    print(f"    (supersede note: comment {s_id} not deleted — "
                          f"{d.status_code})", file=sys.stderr)
    print(f"\nCorrected {pushed}, failed {failed}. Ledger: {log}")

    # Genchi Gembutsu: re-read from Canvas and confirm each value landed.
    after = {s["user_id"]: s for s in fetch_submissions(base, cid, headers, aid)}
    bad = [u for u in pushed_uids
           if u in after and not _same_grade(
               after[u].get("grade"), next(p["grade"] for p in writes if p["uid"] == u))]
    print(f"Verified {len(pushed_uids) - len(bad)}/{pushed} against Canvas"
          + (f"; MISMATCH for user(s) {bad}" if bad else "."))

    if args.post and pushed and assignment_posts_manually(base, cid, headers, aid):
        ok, detail = post_assignment_grades(base, cid, headers, aid)
        print(f"  {'released' if ok else '⛔ release failed'}: {detail}")

    return 1 if (failed or bad) else 0


if __name__ == "__main__":
    sys.exit(main())

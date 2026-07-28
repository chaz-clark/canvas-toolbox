#!/usr/bin/env python3
"""grader_letter_comments.py — push INSTRUCTOR-authored, comment-only notes to a
specific Canvas assignment, roster-keyed (the "End Letter" / final-grade-comment step).

WHY THIS EXISTS
  Final-letter grading has two writes: the GRADE (a value → the Course Grade column —
  handled by grader_standing) and a COMMENT-ONLY note → an "End Letter" assignment,
  preserving whatever grade is already there (e.g. a TA's complete/incomplete).
  Courses hand-wrote a fix_push.py for the comment step; grade_guardian correctly
  blocks that. This is the sanctioned replacement — a roster CSV (key, comment) →
  `comment[text_comment]` writes, with NO grade change.

SCOPE — INSTRUCTOR-AUTHORED comments only (the HG-5 line)
  The comments here are the instructor's own — a final-grade explanation from their
  script/template — NOT AI-drafted per-student feedback. That's why `--yes` is allowed
  (like grader_standing): the instructor reviews the previews and consents, no terminal
  for non-technical faculty. **AI-drafted feedback does NOT belong here** — it goes
  through grader_push.py, which enforces the HG-5 review gate (#207). Using this tool
  to push AI-written comments would be a false disclosure and an HG-5 breach.

GUARDS
  - Comment-ONLY write (never sends posted_grade) → a grade is never changed.
  - Test Student excluded (#61); unmatched/ambiguous key hard-fails (never comment on
    the wrong student); dry-run by default; --push to write; --allow-enrolled for your
    own course (canvas_course_guard).
  - Prints each comment preview so the instructor reviews the actual TEXT before --yes.
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

# Reuse the sibling standing tool's env, roster resolution, column picker, and the
# --yes/TTY decision — one source of truth for the parts that must not drift.
from grader_standing import (
    _env_canvas,
    fetch_roster_index,
    _pick_column,
    standing_push_decision,
)

_TIMEOUT = 30
_KEY_COLS = ("user_id", "canvas_user_id", "id", "sis_user_id", "sis_id",
             "login_id", "login", "student_id", "email")
_COMMENT_COLS = ("comment", "text", "note", "end_letter", "feedback", "message")


def load_comment_rows(path, key_override, comment_override):
    """Read (raw_key, comment) pairs. Fails loudly if either column is missing."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        key_col = _pick_column(reader.fieldnames, _KEY_COLS, key_override)
        com_col = _pick_column(reader.fieldnames, _COMMENT_COLS, comment_override)
        if not key_col:
            raise SystemExit(f"⛔ no key column. Have {reader.fieldnames}; expected one "
                             f"of {_KEY_COLS} or pass --key-column.")
        if not com_col:
            raise SystemExit(f"⛔ no comment column. Have {reader.fieldnames}; expected "
                             f"one of {_COMMENT_COLS} or pass --comment-column.")
        rows = []
        for line in reader:
            key = (line.get(key_col) or "").strip()
            comment = (line.get(com_col) or "").strip()
            if key and comment:            # skip blank-comment rows — never post empty
                rows.append((key, comment))
    return rows, key_col, com_col


def plan_comments(rows, index):
    """Resolve each row to a user_id. Returns (plan, problems). Hard-fails on any
    unmatched/ambiguous key — never comment on the wrong (or no) student."""
    plan, problems = [], []
    for raw_key, comment in rows:
        k = raw_key.lower()
        if k not in index:
            problems.append(f"key {raw_key!r} matches no enrolled student")
            continue
        uid = index[k]
        if uid is None:
            problems.append(f"key {raw_key!r} matches more than one student")
            continue
        plan.append({"uid": uid, "comment": comment})
    return plan, problems


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(
        description="Push instructor-authored comment-only notes to an assignment "
                    "(no grade change). For AI-drafted feedback use grader_push.")
    ap.add_argument("--csv", required=True, help="roster CSV: a key column + a comment column")
    ap.add_argument("--assignment-id", required=True, help="the assignment to comment on")
    ap.add_argument("--course-id", default=None, help="defaults to $CANVAS_COURSE_ID")
    ap.add_argument("--key-column", default=None)
    ap.add_argument("--comment-column", default=None)
    ap.add_argument("--push", action="store_true", help="actually write (else dry-run)")
    ap.add_argument("--yes", action="store_true",
                    help="post without the interactive prompt. Allowed here (comments "
                         "are instructor-authored, not AI-drafted): use once the "
                         "instructor has reviewed the previews and consents. NO terminal.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="bypass canvas_course_guard for your own enrolled course")
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

    print("ⓘ This posts INSTRUCTOR-authored comments (no grade change). AI-drafted "
          "feedback must go through grader_push.py (HG-5 review gate) — not here.\n")

    rows, key_col, com_col = load_comment_rows(args.csv, args.key_column, args.comment_column)
    index, active = fetch_roster_index(base, cid, headers)
    plan, problems = plan_comments(rows, index)

    for p in plan:
        preview = p["comment"].replace("\n", " ")[:70]
        tag = "  [inactive]" if p["uid"] not in active else ""
        print(f"  user {p['uid']}: \"{preview}…\"{tag}")
    for m in problems:
        print(f"  ⛔ {m}", file=sys.stderr)

    print(f"\n{len(plan)} comment(s) to post, {len(problems)} unmatched.")
    if problems:
        print("⛔ Unmatched keys — nothing written. Fix the CSV/roster and re-run.",
              file=sys.stderr)
        return 1
    if not args.push:
        print("\nDry run — nothing written. Add --push to post.")
        return 0
    if not plan:
        print("Nothing to post.")
        return 0

    decision = standing_push_decision(args.yes, sys.stdin.isatty())
    if decision == "needs-yes":
        print(f"\nThis would post {len(plan)} instructor comment(s) to the LIVE course {cid}.")
        print(
            "\nⓘ Non-interactive run. These are INSTRUCTOR-authored comments (not "
            "AI-drafted), so --yes IS allowed. If the instructor has reviewed the "
            "previews above and consents, re-run with --yes. Do NOT send them to a "
            "terminal — our audience is non-technical faculty.",
            file=sys.stderr,
        )
        print("Aborted — re-run with --yes once the instructor confirms the comments.")
        return 1

    if guard_enforce:
        guard_enforce(base, headers, cid, mode="write", allow_override=args.allow_enrolled)

    if decision == "prompt":
        print(f"\nThis posts {len(plan)} instructor comment(s) to the LIVE course {cid}.")
        if input("Type 'push' to confirm: ").strip().lower() != "push":
            print("Aborted.")
            return 1

    posted, failed = 0, 0
    for p in plan:
        resp = requests.put(
            f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions/{p['uid']}",
            headers=headers, data={"comment[text_comment]": p["comment"]}, timeout=_TIMEOUT)
        if resp.status_code < 400:
            print(f"  commented user {p['uid']}")
            posted += 1
        else:
            print(f"  ⛔ user {p['uid']}: HTTP {resp.status_code} {resp.text[:120]}",
                  file=sys.stderr)
            failed += 1
    print(f"\nPosted {posted} comment(s), failed {failed}. Grades unchanged.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

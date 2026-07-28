#!/usr/bin/env python3
"""grader_quiz_clear_pending.py — clear the "needs grading" flag on auto-scored
classic quizzes stuck on a ZERO-POINT manual-review question.

THE PROBLEM
  A classic quiz with an essay / file-upload question auto-scores on submission
  (workflow_state 'graded', graded_at set), but Canvas still lists it in the
  instructor's To-Do because the manual question is 'pending_review'. When that
  question is worth 0 points there is nothing to actually grade — the instructor
  just needs the flag cleared. grader_push can't help (regrade_gate correctly
  refuses an already-graded submission; this isn't a grade push), and
  grader_audit_workflow deliberately won't touch a moderation queue.

WHAT IT DOES
  Finds classic-quiz submissions in 'pending_review' and posts a score of 0 to the
  ZERO-POINT manual questions holding them there — which marks them graded and clears
  the To-Do. Dry-run by default; --apply to write; --allow-enrolled for your own
  live course.

SAFETY INVARIANT — it can NEVER change a grade
  It only ever touches a question whose points_possible == 0. Posting 0 to a 0-point
  question cannot alter a student's score; it only clears the needs-grading flag.
  Any question worth > 0 points is real grading and belongs in the review -> push
  flow, not here — this tool refuses to touch it. Classic quizzes only (New Quizzes
  can't be graded via this API).
"""
from __future__ import annotations

import argparse
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

from grader_push import _env_canvas

_TIMEOUT = 30
# Classic-quiz question types that require MANUAL grading (auto-gradable types never
# cause pending_review). A 0-point one of these is the target.
_MANUAL_TYPES = {"essay_question", "file_upload_question"}


def zero_point_manual_qids(questions: list[dict]) -> list[int]:
    """Question ids that are manual-review AND worth 0 points — the ONLY questions
    this tool may post a score to. A manual question worth > 0 is real grading and is
    intentionally excluded (the safety invariant lives here)."""
    out = []
    for q in questions:
        try:
            pts = float(q.get("points_possible") or 0)
        except (TypeError, ValueError):
            pts = 0.0
        if q.get("question_type") in _MANUAL_TYPES and pts == 0.0 and q.get("id") is not None:
            out.append(int(q["id"]))
    return out


def pending_submissions(submissions: list[dict]) -> list[dict]:
    """Quiz submissions awaiting manual review (the ones cluttering the To-Do)."""
    return [s for s in submissions
            if (s.get("workflow_state") or "").lower() == "pending_review"]


def _get(base, cid, headers, path, key=None):
    r = requests.get(f"{base}/api/v1/courses/{cid}{path}", headers=headers,
                     params={"per_page": 100}, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return (data or {}).get(key, []) if key else (data or [])


def resolve_quiz_id(base, cid, headers, assignment_id, quiz_id):
    if quiz_id:
        return int(quiz_id)
    a = requests.get(f"{base}/api/v1/courses/{cid}/assignments/{assignment_id}",
                     headers=headers, timeout=_TIMEOUT)
    a.raise_for_status()
    qid = (a.json() or {}).get("quiz_id")
    if not qid:
        print(f"⛔ assignment {assignment_id} is not a classic quiz (no quiz_id). "
              "New Quizzes can't be graded via this API.", file=sys.stderr)
        return None
    return int(qid)


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(
        description="Clear the needs-grading flag on classic quizzes stuck on a "
                    "0-point manual question (posts 0 — cannot change a grade).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--assignment-id", help="the quiz's assignment id")
    g.add_argument("--quiz-id", help="the classic quiz id directly")
    ap.add_argument("--course-id", default=None, help="defaults to $CANVAS_COURSE_ID")
    ap.add_argument("--apply", action="store_true", help="actually post the 0s (else dry-run)")
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

    qid = resolve_quiz_id(base, cid, headers, args.assignment_id, args.quiz_id)
    if qid is None:
        return 1

    questions = _get(base, cid, headers, f"/quizzes/{qid}/questions")
    zero_qids = zero_point_manual_qids(questions)
    if not zero_qids:
        print(f"No 0-point manual questions on quiz {qid}. Any pending review here is "
              "REAL grading — not this tool's job. Nothing to do.")
        return 0

    subs = _get(base, cid, headers, f"/quizzes/{qid}/submissions", key="quiz_submissions")
    pending = pending_submissions(subs)
    print(f"Quiz {qid}: {len(zero_qids)} zero-point manual question(s) "
          f"{zero_qids}; {len(pending)} submission(s) pending review.")
    for s in pending:
        print(f"  [{'apply' if args.apply else 'dry '}] user {s.get('user_id')}: "
              f"post 0 to question(s) {zero_qids} (attempt {s.get('attempt')})")

    if not pending:
        print("Nothing pending — To-Do is clear.")
        return 0
    if not args.apply:
        print("\nDry run — nothing written. Add --apply to clear the flag.")
        return 0

    if guard_enforce:
        guard_enforce(base, headers, cid, mode="write", allow_override=args.allow_enrolled)

    cleared, failed = 0, 0
    for s in pending:
        body = {"quiz_submissions": [{"attempt": s.get("attempt"),
                                      "questions": {str(q): {"score": 0} for q in zero_qids}}]}
        r = requests.put(f"{base}/api/v1/courses/{cid}/quizzes/{qid}/submissions/{s.get('id')}",
                         headers=headers, json=body, timeout=_TIMEOUT)
        if r.status_code < 400:
            print(f"  cleared user {s.get('user_id')}")
            cleared += 1
        else:
            print(f"  ⛔ user {s.get('user_id')}: HTTP {r.status_code} {r.text[:120]}",
                  file=sys.stderr)
            failed += 1
    print(f"\nCleared {cleared}, failed {failed}. Re-check your Canvas To-Do.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
grader_post_policy.py — hold graded work hidden for review, then release it.

THE PROBLEM
  An instructor wants AI-drafted scores and comments in SpeedGrader for review
  BEFORE students see anything. Canvas does this with a MANUAL posting policy:
  grades and comments written through the API are entered but stay hidden until
  they are posted. But an assignment on the default AUTOMATIC policy makes every
  grade and comment student-visible the instant `grader_push` writes it. Nothing
  in the toolkit could change the policy, and nothing warned the operator.

WHAT THIS DOES (it writes no grades and no comments)
  --status    Read-only. Show the assignment's posting policy, any recorded hold,
              and how many graded submissions are currently hidden from students.
  --hold      Switch the assignment to MANUAL posting and remember what it was.
              Run this BEFORE `grader_push`.
  --release   Post the graded submissions to students (the same action as the
              Gradebook "Post grades" button), then restore the policy recorded
              by --hold. This is the moment students can see grades + comments.
  --restore   Put the policy back WITHOUT posting (abandon the draft). Hidden
              grades stay hidden; Canvas does not post them on a policy change.

  The intended flow:
      grader_post_policy.py --assignment-id N --hold    --apply
      grader_push.py ... --mark-reviewed ... --push      # hidden from students
      (review in SpeedGrader)
      grader_post_policy.py --assignment-id N --release --apply

SAFETY
  * Dry-run by default; --apply writes. Reads and verifies after every write
    (a 200 from the GraphQL mutation is not proof it landed).
  * canvas_course_guard runs before any write (--allow-enrolled for an enrolled
    course, same as the other writers).
  * --release is the only student-visible action. If posting fails the policy is
    NOT restored, so the work stays hidden and the hold stays recorded.
  * Prints counts only. No student names, ids or grades ever reach the console,
    and the state file holds only the course id, assignment id, and a boolean.
  * The posting-policy change uses Canvas's GraphQL `setAssignmentPostPolicy`
    mutation (there is no REST endpoint); posting uses `postAssignmentGrades`.

STATE
  <state-dir>/post_policy_<course>_<assignment>.json  (default state-dir: .canvas)
  {"course_id", "assignment_id", "previous_post_manually", "held_at"}

EXIT CODES
  0 ok / nothing to do   1 Canvas call failed or read-back mismatch
  2 refused (no recorded hold, bad input)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available

import requests
from dotenv import load_dotenv

import canvas_course_guard as guard
from __toolbox_version__ import __version__

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url

_TIMEOUT = 30
_POLL_SECONDS = 2
_POLL_TRIES = 15


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


# ---------------------------------------------------------------------------
# Canvas calls
# ---------------------------------------------------------------------------

def get_post_manually(base: str, cid: str, headers: dict, aid) -> bool | None:
    """The assignment's posting policy: True = MANUAL, False = AUTOMATIC,
    None = unknown (call failed). Unknown is never treated as automatic."""
    try:
        r = requests.get(f"{base}/api/v1/courses/{cid}/assignments/{aid}",
                         headers=headers, timeout=_TIMEOUT)
        if r.status_code >= 400:
            return None
        value = r.json().get("post_manually")
    except Exception:
        return None
    return None if value is None else bool(value)


def set_post_manually(base: str, headers: dict, aid, manual: bool) -> tuple[bool, str]:
    """Set the posting policy via GraphQL `setAssignmentPostPolicy`."""
    query = ("mutation ($a: ID!, $m: Boolean!) { setAssignmentPostPolicy("
             "input: {assignmentId: $a, postManually: $m}) "
             "{ postPolicy { postManually } errors { message } } }")
    try:
        r = requests.post(f"{base}/api/graphql", headers=headers,
                          json={"query": query,
                                "variables": {"a": str(aid), "m": bool(manual)}},
                          timeout=_TIMEOUT)
        body = r.json() or {}
    except Exception as e:
        return False, str(e)
    payload = (body.get("data") or {}).get("setAssignmentPostPolicy") or {}
    errs = payload.get("errors") or body.get("errors")
    if r.status_code >= 400 or errs:
        return False, f"HTTP {r.status_code}: {errs or r.text[:120]}"
    return True, ""


def post_graded(base: str, headers: dict, aid) -> tuple[bool, str]:
    """Release graded submissions via GraphQL `postAssignmentGrades` (the
    Gradebook 'Post grades' action; Canvas has no REST endpoint for it)."""
    query = ("mutation ($a: ID!, $go: Boolean) { postAssignmentGrades("
             "input: {assignmentId: $a, gradedOnly: $go}) "
             "{ progress { _id state } errors { message } } }")
    try:
        r = requests.post(f"{base}/api/graphql", headers=headers,
                          json={"query": query,
                                "variables": {"a": str(aid), "go": True}},
                          timeout=_TIMEOUT)
        body = r.json() or {}
    except Exception as e:
        return False, str(e)
    payload = (body.get("data") or {}).get("postAssignmentGrades") or {}
    errs = payload.get("errors") or body.get("errors")
    if r.status_code >= 400 or errs:
        return False, f"HTTP {r.status_code}: {errs or r.text[:120]}"
    return True, ""


def count_hidden_graded(base: str, cid: str, headers: dict, aid) -> int | None:
    """Graded submissions not yet posted to students. Counts only; None on error."""
    url = f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions"
    params: dict | None = {"per_page": 100}
    hidden = 0
    try:
        while url:
            r = requests.get(url, headers=headers, params=params, timeout=_TIMEOUT)
            if r.status_code >= 400:
                return None
            for s in r.json():
                if s.get("workflow_state") == "graded" and not s.get("posted_at"):
                    hidden += 1
            url = r.links.get("next", {}).get("url")
            params = None
    except Exception:
        return None
    return hidden


# ---------------------------------------------------------------------------
# State (ids and a boolean only)
# ---------------------------------------------------------------------------

def state_path(state_dir: Path, cid, aid) -> Path:
    return Path(state_dir) / f"post_policy_{cid}_{aid}.json"


def read_state(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_state(path: Path, cid, aid, previous_manual: bool) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "course_id": str(cid), "assignment_id": str(aid),
        "previous_post_manually": bool(previous_manual),
        "held_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2) + "\n", encoding="utf-8")


def _name(manual: bool | None) -> str:
    return {True: "MANUAL", False: "AUTOMATIC", None: "unknown"}[manual]


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _set_and_verify(base, cid, headers, aid, manual: bool) -> tuple[bool, str]:
    ok, err = set_post_manually(base, headers, aid, manual)
    if not ok:
        return False, err
    back = get_post_manually(base, cid, headers, aid)
    if back is not manual:
        return False, (f"Canvas reported success but the policy reads back as "
                       f"{_name(back)}. Check Gradebook -> Grade Posting Policy.")
    return True, ""


def do_status(base, cid, headers, aid, spath) -> int:
    current = get_post_manually(base, cid, headers, aid)
    hidden = count_hidden_graded(base, cid, headers, aid)
    state = read_state(spath)
    print(f"Posting policy: {_name(current)}")
    print(f"Graded but hidden from students: {hidden if hidden is not None else 'unknown'}")
    if state:
        print(f"Recorded hold: yes (previous policy: "
              f"{_name(state.get('previous_post_manually'))}, since {state.get('held_at')})")
    else:
        print("Recorded hold: none")
    if current is False:
        print("\nNOTE: AUTOMATIC posting — anything grader_push writes is "
              "student-visible immediately. Run --hold first for a review draft.")
    return 0 if current is not None else 1


def do_hold(base, cid, headers, aid, spath, apply: bool) -> int:
    current = get_post_manually(base, cid, headers, aid)
    if current is None:
        print("ERROR: could not read the posting policy; nothing changed.")
        return 1
    state = read_state(spath)
    if current is True and state:
        print("Already held (MANUAL, hold recorded). Nothing to do.")
        return 0
    if current is True:
        print("Already MANUAL with no recorded hold: it was manual before this run. "
              "Recording that, so --release leaves it manual.")
        if apply:
            write_state(spath, cid, aid, True)
        else:
            print("\nDry run — re-run with --apply to record it.")
        return 0
    print(f"Posting policy is AUTOMATIC. Hold would switch assignment {aid} to MANUAL "
          "and record AUTOMATIC as the policy to restore.")
    if not apply:
        print("\nDry run — re-run with --apply to write.")
        return 0
    ok, err = _set_and_verify(base, cid, headers, aid, True)
    if not ok:
        print(f"ERROR: {err}")
        return 1
    write_state(spath, cid, aid, False)
    print("✓ Now MANUAL (verified). Grades and comments written from here stay "
          "hidden until --release.")
    return 0


def do_release(base, cid, headers, aid, spath, apply: bool) -> int:
    state = read_state(spath)
    if not state:
        print("REFUSED: no recorded hold for this assignment, so there is nothing "
              "safe to restore. Run --status; to post without a hold use the "
              "Gradebook 'Post grades' action or grader_push --post.")
        return 2
    previous = bool(state.get("previous_post_manually"))
    hidden = count_hidden_graded(base, cid, headers, aid)
    print(f"Release would POST {hidden if hidden is not None else '?'} graded "
          f"submission(s) to students (grades AND comments become visible), "
          f"then restore the policy to {_name(previous)}.")
    if not apply:
        print("\nDry run — re-run with --apply to release.")
        return 0
    ok, err = post_graded(base, headers, aid)
    if not ok:
        print(f"ERROR posting grades: {err}\nPolicy NOT restored; work stays "
              "hidden and the hold stays recorded.")
        return 1
    remaining = hidden
    for _ in range(_POLL_TRIES):
        time.sleep(_POLL_SECONDS)
        remaining = count_hidden_graded(base, cid, headers, aid)
        if remaining == 0:
            break
    if remaining != 0:
        print(f"WARNING: {remaining if remaining is not None else 'unknown'} graded "
              "submission(s) still read as hidden after waiting. Policy NOT "
              "restored; check the Gradebook, then re-run --release.")
        return 1
    print("✓ Posted to students (verified: 0 graded submissions hidden).")
    if previous is False:
        ok, err = _set_and_verify(base, cid, headers, aid, False)
        if not ok:
            print(f"ERROR restoring policy: {err}\nGrades are posted; set the policy "
                  "back by hand if you want AUTOMATIC.")
            return 1
        print("✓ Policy restored to AUTOMATIC (verified).")
    else:
        print("Policy left MANUAL (it was manual before the hold).")
    Path(spath).unlink(missing_ok=True)
    return 0


def do_restore(base, cid, headers, aid, spath, apply: bool) -> int:
    state = read_state(spath)
    if not state:
        print("REFUSED: no recorded hold for this assignment; nothing to restore.")
        return 2
    previous = bool(state.get("previous_post_manually"))
    hidden = count_hidden_graded(base, cid, headers, aid)
    print(f"Restore would set the policy back to {_name(previous)} WITHOUT posting. "
          f"{hidden if hidden is not None else '?'} graded submission(s) would stay "
          "hidden from students (Canvas does not post them on a policy change).")
    if not apply:
        print("\nDry run — re-run with --apply to restore.")
        return 0
    ok, err = _set_and_verify(base, cid, headers, aid, previous)
    if not ok:
        print(f"ERROR: {err}")
        return 1
    Path(spath).unlink(missing_ok=True)
    print(f"✓ Policy restored to {_name(previous)} (verified).")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(
        description="Hold graded work hidden for review, then release it "
                    "(Canvas posting policy). Writes no grades or comments.")
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    ap.add_argument("--assignment-id", required=True, type=int)
    ap.add_argument("--course-id", help="Literal course id; overrides --target")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Env var holding the course id (default CANVAS_COURSE_ID)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="Read-only (default)")
    mode.add_argument("--hold", action="store_true",
                      help="Switch to MANUAL posting and remember the old policy")
    mode.add_argument("--release", action="store_true",
                      help="Post graded work to students, then restore the policy")
    mode.add_argument("--restore", action="store_true",
                      help="Restore the policy WITHOUT posting")
    ap.add_argument("--apply", action="store_true",
                    help="Write to Canvas. Without this the run is a dry run.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Proceed even if the course has enrolled students")
    ap.add_argument("--state-dir", default=".canvas",
                    help="Where the hold record is kept (default .canvas)")
    args = ap.parse_args(argv)

    cid = args.course_id or os.environ.get(args.target, "")
    if not (CANVAS_API_TOKEN and CANVAS_BASE_URL and cid):
        print("ERROR: need CANVAS_API_TOKEN, CANVAS_BASE_URL and a course id.")
        return 2
    headers = _headers()
    aid = args.assignment_id
    spath = state_path(Path(args.state_dir), cid, aid)
    writing = args.apply and (args.hold or args.release or args.restore)

    guard.enforce(base_url=CANVAS_BASE_URL, headers=headers, course_id=cid,
                  mode="write" if writing else "read",
                  allow_override=args.allow_enrolled, label="post-policy target")

    if args.hold:
        return do_hold(CANVAS_BASE_URL, cid, headers, aid, spath, args.apply)
    if args.release:
        return do_release(CANVAS_BASE_URL, cid, headers, aid, spath, args.apply)
    if args.restore:
        return do_restore(CANVAS_BASE_URL, cid, headers, aid, spath, args.apply)
    return do_status(CANVAS_BASE_URL, cid, headers, aid, spath)


if __name__ == "__main__":
    sys.exit(main())

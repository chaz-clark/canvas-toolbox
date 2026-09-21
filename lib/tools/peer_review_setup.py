#!/usr/bin/env python3
"""
peer_review_setup.py — create a peer-reviewed assignment with a rating rubric (#331).

WHY THIS EXISTS
  `canvas_sync` assignment JSON has no peer-review fields, and `rubric_recommender
  --apply` only attaches rubrics to assignments that already exist. So "students rate
  each other's preparation" — a peer-review assignment plus a structured rubric — had
  to be hand-built in the Canvas UI. This creates ONE assignment (unpublished) with
  peer review switched on and a peer rubric attached. Who reviews whom is a separate
  step (`peer_review_assign.py`).

WHAT IT DELIBERATELY DOES NOT DO
  - Publish. The assignment is created unpublished; publishing is student-facing.
  - Edit an existing assignment. A same-titled assignment is reported, never changed
    (Canvas peer-review settings interact with existing submissions and reviews).
  - Grade with the peer rubric. `use_for_grading` is always false.

LIVE COURSES (students enrolled)
  Instructors adjust running courses, so this works there — behind a gate. With
  students enrolled `canvas_course_guard` refuses the write until the instructor
  explicitly asks for `--allow-enrolled`; a dry run always works. What keeps a live run
  low-risk: the assignment is created UNPUBLISHED (students see nothing until you
  publish), an existing assignment is never edited, and each write is read back.

WHAT IS AND ISN'T VERIFIED (see canvas_api_lessons_learned.md L22-L25)
  Verified on a sandbox: the create payloads below round-trip, `use_for_grading=false`
  is honoured, peer assessments are read from the rubric, not the submission.
  Taken from Canvas documentation only, NOT tested: whether reviewees see peer rubric
  scores, what anonymity hides on the rubric view, real group pairing. Say "per Canvas
  documentation" if you repeat any of that to students.

WHY ONLY TEXT / UPLOAD SUBMISSIONS
  Canvas documents that quizzes, discussions, external tools and on-paper items cannot
  be peer reviewed, but its API stores `peer_reviews=true` on three of those four anyway
  (L22). An echoed flag is not proof it works, so the tool only creates assignments
  Canvas actually peer reviews.

CRITERIA SPEC   (--criteria, criteria separated by ';')
  Prepared for class?:yesno            -> Yes (1) / No (0)
  Effort:1-5                           -> 5 ... 1, points equal the number
  Evidence:none|some|strong            -> strong (2), some (1), none (0)

Usage:
  # dry run (default) — validates and shows the plan, writes nothing
  uv run python lib/tools/peer_review_setup.py --title "Prep ratings" \\
      --criteria "Practiced?:yesno;Effort:1-5;Evidence:none|some|strong"

  # write it (unpublished)
  uv run python lib/tools/peer_review_setup.py --title ... --criteria ... --apply

Requires in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, and the env var named by
--target (default CANVAS_COURSE_ID).

Exit codes:
  0  created (or already set up) and verified, or dry run
  1  Canvas did not apply the write, read-back disagreed, or a same-titled assignment
     exists with different settings
  2  configuration / validation error
"""

from __future__ import annotations

import argparse
import os
import re
import sys

import requests
from dotenv import load_dotenv

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available

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
ENHANCED_FLAG = "peer_review_allocation_and_grading"
# Canvas documents that the other submission types cannot be peer reviewed (L22).
SUBMISSION_TYPES = ("online_text_entry", "online_upload")


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(endpoint: str, params: dict | None = None) -> list | dict | None:
    try:
        resp = requests.get(f"{CANVAS_BASE_URL}/api/v1{endpoint}", headers=_headers(),
                            params={"per_page": 100, **(params or {})}, timeout=_TIMEOUT)
    except Exception:
        return None
    if resp.status_code >= 400:
        return None
    try:
        return resp.json()
    except Exception:
        return None


def _post(endpoint: str, form: dict) -> tuple[dict | None, str]:
    """Form-encoded (P-LL1): nested `a[b][c]` keys are what these endpoints take."""
    try:
        resp = requests.post(f"{CANVAS_BASE_URL}/api/v1{endpoint}", headers=_headers(),
                             data=form, timeout=_TIMEOUT)
    except Exception as e:
        return None, str(e)
    if resp.status_code >= 400:
        return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
    try:
        return resp.json(), ""
    except Exception:
        return None, "response was not JSON"


# ---------------------------------------------------------------------------
# Criteria parsing + validation
# ---------------------------------------------------------------------------

def parse_criteria(spec: str) -> list[dict]:
    """Parse "Name:yesno;Name:1-5;Name:a|b|c". PURE — raises ValueError, writes nothing.

    Each criterion becomes {"description", "points", "ratings": [(label, points), ...]}
    with ratings ordered high to low, as Canvas renders them."""
    criteria: list[dict] = []
    for chunk in (spec or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError(f"expected NAME:TYPE, got {chunk!r}")
        name, _, kind = chunk.rpartition(":")
        name, kind = name.strip(), kind.strip()
        if not name:
            raise ValueError(f"missing criterion name in {chunk!r}")

        if kind.lower() == "yesno":
            ratings = [("Yes", 1), ("No", 0)]
        elif (m := re.fullmatch(r"(\d+)\s*-\s*(\d+)", kind)):
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo >= hi:
                raise ValueError(f"{name}: scale {kind!r} must run low-high, e.g. 1-5")
            if hi - lo > 19:
                raise ValueError(f"{name}: scale {kind!r} has more than 20 levels")
            ratings = [(str(v), v) for v in range(hi, lo - 1, -1)]
        elif "|" in kind:
            labels = [x.strip() for x in kind.split("|")]
            if any(not x for x in labels) or len(labels) < 2:
                raise ValueError(f"{name}: level list {kind!r} needs 2+ non-empty labels")
            if len(set(labels)) != len(labels):
                raise ValueError(f"{name}: duplicate level labels in {kind!r}")
            ratings = [(lab, i) for i, lab in reversed(list(enumerate(labels)))]
        else:
            raise ValueError(
                f"{name}: type {kind!r} is not yesno, a range like 1-5, or a list a|b|c")
        criteria.append({"description": name, "points": ratings[0][1], "ratings": ratings})

    if not criteria:
        raise ValueError("no criteria given")
    names = [c["description"] for c in criteria]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ValueError(f"duplicate criterion name(s): {', '.join(sorted(dupes))}")
    return criteria


# ---------------------------------------------------------------------------
# Payload builders (PURE)
# ---------------------------------------------------------------------------

def rubric_title(title: str) -> str:
    return f"{title} (peer rubric)"


def build_assignment_form(*, title: str, submission_type: str, points: float,
                          description: str, anonymous: bool, auto_count: int | None,
                          group_category_id: int | None, intra_group: bool,
                          due_at: str | None) -> dict:
    form: dict = {
        "assignment[name]": title,
        "assignment[submission_types][]": [submission_type],
        "assignment[points_possible]": f"{points:g}",
        "assignment[published]": "false",
        "assignment[peer_reviews]": "true",
        "assignment[anonymous_peer_reviews]": "true" if anonymous else "false",
        "assignment[automatic_peer_reviews]": "true" if auto_count else "false",
    }
    if auto_count:
        form["assignment[peer_review_count]"] = str(auto_count)
    if description:
        form["assignment[description]"] = description
    if group_category_id:
        form["assignment[group_category_id]"] = str(group_category_id)
        form["assignment[intra_group_peer_reviews]"] = "true" if intra_group else "false"
    if due_at:
        form["assignment[due_at]"] = due_at
    return form


def build_rubric_form(assignment_id: int, title: str, criteria: list[dict]) -> dict:
    form: dict = {
        "rubric_association[association_id]": str(assignment_id),
        "rubric_association[association_type]": "Assignment",
        "rubric_association[purpose]": "grading",
        "rubric_association[use_for_grading]": "false",
        "rubric[title]": rubric_title(title),
    }
    for i, c in enumerate(criteria):
        p = f"rubric[criteria][{i}]"
        form[f"{p}[description]"] = c["description"]
        form[f"{p}[points]"] = str(c["points"])
        for j, (label, pts) in enumerate(c["ratings"]):
            form[f"{p}[ratings][{j}][description]"] = label
            form[f"{p}[ratings][{j}][points]"] = str(pts)
    return form


# ---------------------------------------------------------------------------
# Existing-assignment comparison (PURE)
# ---------------------------------------------------------------------------

def find_existing(course_id: str, title: str) -> dict | None:
    """The assignment already carrying this exact title, if any."""
    for a in _get(f"/courses/{course_id}/assignments",
                  {"search_term": title}) or []:
        if isinstance(a, dict) and (a.get("name") or "").strip() == title.strip():
            return a
    return None


def diff_existing(assignment: dict, *, anonymous: bool, auto_count: int | None,
                  group_category_id: int | None, criteria: list[dict]) -> list[str]:
    """What differs between an existing assignment and what was asked for. Empty
    list = already set up. Only settings this tool owns are compared."""
    diffs: list[str] = []
    if not assignment.get("peer_reviews"):
        diffs.append("peer reviews are off")
    if bool(assignment.get("anonymous_peer_reviews")) != anonymous:
        diffs.append(f"anonymous_peer_reviews is {bool(assignment.get('anonymous_peer_reviews'))}, "
                     f"asked {anonymous}")
    if bool(assignment.get("automatic_peer_reviews")) != bool(auto_count):
        diffs.append("automatic vs manual peer-review assignment differs")
    elif auto_count and assignment.get("peer_review_count") != auto_count:
        diffs.append(f"peer_review_count is {assignment.get('peer_review_count')}, "
                     f"asked {auto_count}")
    if (assignment.get("group_category_id") or None) != (group_category_id or None):
        diffs.append(f"group_category_id is {assignment.get('group_category_id')}, "
                     f"asked {group_category_id}")
    have = [(c.get("description") or "").strip() for c in assignment.get("rubric") or []]
    if have and have != [c["description"] for c in criteria]:
        diffs.append("attached rubric criteria differ from --criteria")
    return diffs


def has_rubric(assignment: dict) -> bool:
    return bool(assignment.get("rubric"))


def enhanced_peer_review_on(course_id: str) -> bool | None:
    """True/False from the enabled-features list; None if it could not be read."""
    enabled = _get(f"/courses/{course_id}/features/enabled")
    if not isinstance(enabled, list):
        return None
    return ENHANCED_FLAG in enabled


# ---------------------------------------------------------------------------
# Writes (each read back — a 200 is not proof it landed, #182)
# ---------------------------------------------------------------------------

def attach_rubric(course_id: str, assignment_id: int, title: str,
                  criteria: list[dict]) -> tuple[bool, str]:
    created, err = _post(f"/courses/{course_id}/rubrics",
                         build_rubric_form(assignment_id, title, criteria))
    if not created:
        return False, err
    back = _get(f"/courses/{course_id}/assignments/{assignment_id}") or {}
    got = [(c.get("description") or "").strip() for c in back.get("rubric") or []]
    if got != [c["description"] for c in criteria]:
        return False, ("Canvas reported success but the assignment does not show the "
                       "rubric. Check the assignment in Canvas before re-running.")
    return True, ""


def main() -> int:
    force_utf8_console()  # #123

    ap = argparse.ArgumentParser(
        description="Create an unpublished peer-review assignment with a peer rubric.")
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    ap.add_argument("--title", required=True, help="Assignment name (also the idempotency key)")
    ap.add_argument("--criteria", required=True, metavar="SPEC",
                    help='e.g. "Practiced?:yesno;Effort:1-5;Evidence:none|some|strong"')
    ap.add_argument("--description-file", default=None,
                    help="File whose contents become the assignment description")
    ap.add_argument("--submission-type", choices=SUBMISSION_TYPES, default="online_text_entry")
    ap.add_argument("--points", type=float, default=0.0,
                    help="Points the assignment itself is worth (default 0; the peer "
                         "rubric never grades)")
    ap.add_argument("--due-at", default=None, help="ISO 8601, e.g. 2026-10-01T05:59:00Z")
    ap.add_argument("--not-anonymous", action="store_true",
                    help="Reviewers and authors see each other (default: anonymous)")
    ap.add_argument("--auto-count", type=int, default=None, metavar="N",
                    help="Let Canvas assign N reviews each (default: manual pairing, "
                         "e.g. via peer_review_assign.py)")
    ap.add_argument("--group-category-id", type=int, default=None,
                    help="Make it a group assignment on this group set")
    ap.add_argument("--intra-group", action="store_true",
                    help="With --group-category-id: allow reviewing one's own group")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Env var holding the course id (default CANVAS_COURSE_ID)")
    ap.add_argument("--course-id", default=None, help="Literal course id; overrides --target")
    ap.add_argument("--apply", action="store_true",
                    help="Write to Canvas. Without this the run is a dry run.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Proceed even if the course has enrolled students")
    args = ap.parse_args()

    if not CANVAS_API_TOKEN or not CANVAS_BASE_URL:
        print("ERROR: CANVAS_API_TOKEN and CANVAS_BASE_URL must be set.")
        return 2
    course_id = (args.course_id or os.environ.get(args.target, "")).strip()
    if not course_id:
        source = "--course-id" if args.course_id else f"${args.target}"
        print(f"ERROR: course ID not found via {source}.")
        print("       Set the env var, or pass --course-id <id> directly.")
        return 2

    try:
        criteria = parse_criteria(args.criteria)
        if args.auto_count is not None and args.auto_count < 1:
            raise ValueError("--auto-count must be 1 or more")
        if args.intra_group and not args.group_category_id:
            raise ValueError("--intra-group needs --group-category-id")
        description = ""
        if args.description_file:
            with open(args.description_file, encoding="utf-8") as fh:
                description = fh.read()
    except (ValueError, OSError) as e:
        print(f"ERROR: {e}")
        return 2
    anonymous = not args.not_anonymous

    print(f"Peer review: {args.title}"
          f"   ({'APPLYING' if args.apply else 'DRY RUN — pass --apply to write'})")
    print(f"  submission     {args.submission_type}, {args.points:g} pts, unpublished")
    print(f"  reviews        {'anonymous' if anonymous else 'named'}, "
          + (f"Canvas assigns {args.auto_count} each" if args.auto_count
             else "manual pairing"))
    if args.group_category_id:
        print(f"  group set      {args.group_category_id}"
              f"{' (intra-group reviews allowed)' if args.intra_group else ''}")
    print(f"  peer rubric    {rubric_title(args.title)!r}, not used for grading")
    for c in criteria:
        print(f"    - {c['description']:<28} "
              + " / ".join(f"{lab}={pts}" for lab, pts in c["ratings"]))
    if anonymous:
        print("  note: anonymity is easy to guess in small groups (3-4 people) — say so "
              "in the student instructions.")

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="write" if args.apply else "read",
                  allow_override=args.allow_enrolled, label="peer review target")

    enhanced = enhanced_peer_review_on(course_id)
    if enhanced:
        print("\n  ⚠ Enhanced Peer Review (Peer Review Allocation and Grading) is ON for "
              "this course. This tool sets the classic peer-review fields; how they "
              "interact with the new mode is untested (L22-L25). Check the result in "
              "SpeedGrader before publishing.")
    elif enhanced is None:
        print("\n  (could not read the Enhanced Peer Review feature state)")

    existing = find_existing(course_id, args.title)
    if existing:
        aid = existing["id"]
        diffs = diff_existing(existing, anonymous=anonymous, auto_count=args.auto_count,
                              group_category_id=args.group_category_id, criteria=criteria)
        if diffs:
            print(f"\n  an assignment titled {args.title!r} already exists (id {aid}) "
                  f"and differs:")
            for d in diffs:
                print(f"    - {d}")
            print("  This tool never edits an existing assignment. Change it in Canvas "
                  "or use a different --title.")
            return 1
        if has_rubric(existing):
            print(f"\n  already set up (id {aid}) — nothing to do")
            return 0
        print(f"\n  assignment exists (id {aid}) but has no rubric")
        if not args.apply:
            print("  Re-run with --apply to attach the peer rubric.")
            return 0
        ok, err = attach_rubric(course_id, aid, args.title, criteria)
        print("  ✓ peer rubric attached and verified" if ok else f"\nERROR: {err}")
        return 0 if ok else 1

    if not args.apply:
        print("\nRe-run with --apply to create it.")
        return 0

    created, err = _post(f"/courses/{course_id}/assignments", build_assignment_form(
        title=args.title, submission_type=args.submission_type, points=args.points,
        description=description, anonymous=anonymous, auto_count=args.auto_count,
        group_category_id=args.group_category_id, intra_group=args.intra_group,
        due_at=args.due_at))
    if not created:
        print(f"\nERROR creating assignment: {err}")
        return 1
    aid = created["id"]
    problems = diff_existing(created, anonymous=anonymous, auto_count=args.auto_count,
                             group_category_id=args.group_category_id, criteria=[])
    if problems or created.get("published"):
        print(f"\nCanvas created assignment {aid} but it did not come back as asked: "
              f"{'; '.join(problems) or 'it is published'}. Check it in Canvas.")
        return 1
    print(f"\n  ✓ assignment created and verified (id {aid}, unpublished)")

    ok, err = attach_rubric(course_id, aid, args.title, criteria)
    if not ok:
        print(f"\nERROR attaching rubric: {err}")
        print(f"The assignment exists (id {aid}). Re-run the same command to attach the "
              f"rubric — it is idempotent by title.")
        return 1
    print("  ✓ peer rubric attached and verified")
    print("\nNext: publish in Canvas when ready, then pair reviewers "
          "(peer_review_assign.py).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

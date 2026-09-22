#!/usr/bin/env python3
"""
peer_review_assign.py — make every member of each group a peer reviewer of their
groupmates, on an individual assignment (#331).

WHY THIS EXISTS
  Canvas cannot scope reviewers to a group for an INDIVIDUAL assignment:
  `intra_group_peer_reviews` exists only on group assignments and makes pairing random
  rather than group-limited, and automatic mode pairs across groups by default (D8 in
  canvas_api_knowledge.md). The only way to keep reviewers inside their group is to
  create the pairings explicitly. This does that, from a group set — self-signup or
  teacher-assigned, the API reads both the same way.

WHAT IT DOES
  For each group, for each ordered pair of members (reviewer != reviewee), it creates a
  peer review unless that pair already exists — so it is safe to re-run after students
  submit late or the groups change. Members who are not active students (Test Student,
  dropped) are left out. Reviewees who have not submitted yet are skipped by default
  (Canvas documents that manual pairing happens after submissions exist);
  `--include-unsubmitted` tries them anyway.

WHAT IT DOES NOT DO
  - Delete pairs. Pairs left over from students who changed groups are counted and left
    for you to remove in Canvas.
  - Group ASSIGNMENTS (`group_category_id` on the assignment). There every member shares
    one submission, so "review your groupmates" would mean reviewing your own group's
    work; that case is refused rather than guessed at.

FERPA
  Output is COUNTS ONLY. The group and enrollment endpoints return student names; this
  keeps only numeric ids in memory and prints neither names nor ids.

LIVE COURSES
  This is meant for courses with students in them. Without `--apply` nothing is written.
  With students enrolled `canvas_course_guard` refuses the write until the instructor
  explicitly asks for `--allow-enrolled`.

Usage:
  # dry run (default) — counts only
  uv run python lib/tools/peer_review_assign.py --title "Prep ratings" --group-set-id 123

  # write the pairings
  uv run python lib/tools/peer_review_assign.py --title ... --group-set-id 123 --apply

Requires in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, and the env var named by
--target (default CANVAS_COURSE_ID).

Exit codes:
  0  dry run, nothing to do, or every pairing created and verified
  1  some pairings failed or did not read back
  2  configuration / validation error
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter

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


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get_all(endpoint: str, params: dict | None = None) -> list | dict | None:
    """GET, following `Link: rel="next"`. Returns None on any failure so a partial
    read is never mistaken for a complete one (a short member list would silently
    plan too few pairings)."""
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    query: dict | None = {"per_page": 100, **(params or {})}
    items: list = []
    while url:
        try:
            resp = requests.get(url, headers=_headers(), params=query, timeout=_TIMEOUT)
        except Exception:
            return None
        if resp.status_code >= 400:
            return None
        try:
            body = resp.json()
        except Exception:
            return None
        if not isinstance(body, list):
            return body
        items.extend(body)
        m = re.search(r'<([^>]+)>;\s*rel="next"', resp.headers.get("Link", ""))
        url, query = (m.group(1) if m else None), None
    return items


def _post(endpoint: str, form: dict) -> tuple[bool, str]:
    try:
        resp = requests.post(f"{CANVAS_BASE_URL}/api/v1{endpoint}", headers=_headers(),
                             data=form, timeout=_TIMEOUT)
    except Exception as e:
        return False, type(e).__name__
    if resp.status_code >= 400:
        return False, f"HTTP {resp.status_code}"
    return True, ""


# ---------------------------------------------------------------------------
# Planning (PURE) — ids only, never names
# ---------------------------------------------------------------------------

def plan_pairs(groups: dict[int, list[int]], eligible: set[int],
               submissions: dict[int, dict], existing: set[tuple[int, int]],
               include_unsubmitted: bool = False) -> dict:
    """Decide which (reviewer, reviewee) pairs to create.

    groups       group id -> member user ids
    eligible     active student user ids; other members are left out
    submissions  user id -> {"id": submission id, "workflow_state": str}
    existing     (reviewer id, reviewee id) pairs Canvas already has

    Returns {"create": [(reviewer, reviewee, submission_id)], "counts": {...}}."""
    create: list[tuple[int, int, int]] = []
    wanted: set[tuple[int, int]] = set()
    c: Counter = Counter()
    c["groups"] = len(groups)

    for members in groups.values():
        kept = sorted({m for m in members if m in eligible})
        c["members_left_out"] += len(set(members)) - len(kept)
        c["members"] += len(kept)
        if len(kept) < 2:
            c["groups_too_small"] += 1
            continue
        for reviewee in kept:
            sub = submissions.get(reviewee)
            if not sub or not sub.get("id"):
                c["reviewees_without_submission_record"] += 1
                continue
            if sub.get("workflow_state") == "unsubmitted" and not include_unsubmitted:
                c["reviewees_not_submitted_yet"] += 1
                continue
            for reviewer in kept:
                if reviewer == reviewee:
                    continue
                wanted.add((reviewer, reviewee))
                if (reviewer, reviewee) in existing:
                    c["already_paired"] += 1
                else:
                    create.append((reviewer, reviewee, sub["id"]))
    c["to_create"] = len(create)
    c["existing_outside_groups"] = len(existing - wanted)
    return {"create": create, "counts": dict(c)}


def existing_pairs(reviews: list) -> set[tuple[int, int]]:
    """(reviewer, reviewee) from a peer_reviews listing: assessor_id reviews user_id."""
    return {(r["assessor_id"], r["user_id"]) for r in reviews
            if isinstance(r, dict) and r.get("assessor_id") and r.get("user_id")}


_LABELS = (
    ("groups", "groups in the set"),
    ("members", "eligible members"),
    ("members_left_out", "members left out (not active students)"),
    ("groups_too_small", "groups skipped (fewer than 2 eligible members)"),
    ("reviewees_not_submitted_yet", "reviewees skipped (not submitted yet)"),
    ("reviewees_without_submission_record", "reviewees skipped (no submission record)"),
    ("already_paired", "pairs already in Canvas"),
    ("existing_outside_groups", "existing pairs not in the current groups (left as is)"),
    ("to_create", "pairs to create"),
)


def print_counts(counts: dict) -> None:
    for key, label in _LABELS:
        if key in ("groups", "members", "to_create") or counts.get(key):
            print(f"  {counts.get(key, 0):>5}  {label}")


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def find_assignment(course_id: str, title: str) -> dict | None:
    for a in _get_all(f"/courses/{course_id}/assignments", {"search_term": title}) or []:
        if isinstance(a, dict) and (a.get("name") or "").strip() == title.strip():
            return a
    return None


def main() -> int:
    force_utf8_console()  # #123

    ap = argparse.ArgumentParser(
        description="Pair every group member as a peer reviewer of their groupmates.")
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--assignment-id", type=int, help="The peer-review assignment")
    which.add_argument("--title", help="Its exact title")
    ap.add_argument("--group-set-id", type=int, required=True,
                    help="Group set whose groups define who reviews whom")
    ap.add_argument("--include-unsubmitted", action="store_true",
                    help="Also pair reviewees who have not submitted (Canvas documents "
                         "pairing after submission; behavior before that is untested)")
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

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="write" if args.apply else "read",
                  allow_override=args.allow_enrolled, label="peer review target")

    if args.assignment_id:
        assignment = _get_all(f"/courses/{course_id}/assignments/{args.assignment_id}")
    else:
        assignment = find_assignment(course_id, args.title)
    if not isinstance(assignment, dict) or not assignment.get("id"):
        print("ERROR: assignment not found in this course.")
        return 2
    aid = assignment["id"]
    if not assignment.get("peer_reviews"):
        print(f"ERROR: {assignment.get('name')!r} does not have peer reviews turned on. "
              "Create it with peer_review_setup.py or turn them on in Canvas.")
        return 2
    if assignment.get("group_category_id"):
        print(f"ERROR: {assignment.get('name')!r} is a GROUP assignment. Its members share "
              "one submission, so 'review your groupmates' would mean reviewing your own "
              "group's work. This tool pairs individual assignments only.")
        return 2

    cat = _get_all(f"/group_categories/{args.group_set_id}")
    group_list = _get_all(f"/group_categories/{args.group_set_id}/groups")
    enrolled = _get_all(f"/courses/{course_id}/enrollments",
                        {"type[]": "StudentEnrollment", "state[]": "active"})
    subs = _get_all(f"/courses/{course_id}/assignments/{aid}/submissions")
    reviews = _get_all(f"/courses/{course_id}/assignments/{aid}/peer_reviews")
    if not isinstance(cat, dict) or any(
            x is None for x in (group_list, enrolled, subs, reviews)):
        print("ERROR: could not read the group set, enrollments, submissions or existing "
              "peer reviews from Canvas. Nothing was changed.")
        return 1

    groups: dict[int, list[int]] = {}
    for g in group_list:
        members = _get_all(f"/groups/{g['id']}/users")
        if members is None:
            print("ERROR: could not read a group's members. Nothing was changed.")
            return 1
        groups[g["id"]] = [m["id"] for m in members if isinstance(m, dict) and m.get("id")]
        del members                      # drop the names with the response

    eligible = {e["user_id"] for e in enrolled if isinstance(e, dict) and e.get("user_id")}
    submissions = {s["user_id"]: {"id": s.get("id"), "workflow_state": s.get("workflow_state")}
                   for s in subs if isinstance(s, dict) and s.get("user_id")}
    plan = plan_pairs(groups, eligible, submissions, existing_pairs(reviews),
                      args.include_unsubmitted)
    counts = plan["counts"]

    print(f"Peer review pairing: {assignment.get('name')}"
          f"   ({'APPLYING' if args.apply else 'DRY RUN — pass --apply to write'})")
    print(f"  group set: {cat.get('name')}"
          f" ({'self sign-up' if cat.get('self_signup') else 'instructor-assigned'})")
    print_counts(counts)
    if assignment.get("automatic_peer_reviews"):
        print("  note: this assignment also has automatic peer reviews on; Canvas may "
              "add its own pairings on top of these.")

    if not plan["create"]:
        print("\nNothing to create.")
        return 0
    if not args.apply:
        print("\nRe-run with --apply to create these pairings.")
        return 0

    failures: Counter = Counter()
    for reviewer, _reviewee, sid in plan["create"]:
        ok, why = _post(f"/courses/{course_id}/assignments/{aid}/submissions/{sid}"
                        f"/peer_reviews", {"user_id": str(reviewer)})
        if not ok:
            failures[why] += 1

    back = _get_all(f"/courses/{course_id}/assignments/{aid}/peer_reviews")
    have = existing_pairs(back) if isinstance(back, list) else set()
    missing = sum(1 for r, e, _ in plan["create"] if (r, e) not in have)
    created = len(plan["create"]) - sum(failures.values())
    print(f"\n  ✓ requested {len(plan['create'])}, accepted {created}")
    if failures:
        print("  failed: " + ", ".join(f"{n} × {why}" for why, n in failures.items()))
    if missing:
        print(f"  {missing} requested pairing(s) did not read back from Canvas. Re-running "
              "is safe — pairs that exist are skipped.")
    return 1 if failures or missing else 0


if __name__ == "__main__":
    sys.exit(main())

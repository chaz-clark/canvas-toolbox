#!/usr/bin/env python3
"""
peer_review_summary.py — per-student peer rating averages from a peer rubric (#331).

READ-ONLY. It never writes to Canvas.

WHY THIS EXISTS
  The peer-review list endpoint carries no scores (D7), and a submission's
  `rubric_assessment` / `full_rubric_assessment` includes return only the GRADING
  assessment — peer assessments are invisible there (L24). They come from the rubric:
  `GET /courses/:cid/rubrics/:rid?include[]=peer_assessments&style=full`. This reads
  them, joins each to its reviewee through the submission id, and reports averages.

WHAT IT REPORTS  (per reviewee, keyed by user_id only)
  - how many peer assessments they received
  - the mean points per criterion, and one overall figure (mean of each criterion as a
    share of its maximum, so a yes/no and a 1-5 scale weigh equally)
  - "self" figures if an assessment exists whose assessor IS the reviewee. Canvas
    refuses a self peer review (L23), so this is usually empty; a student's own
    self-report lives in their submission text, which is prose and is not parsed.

FERPA
  Output is keyed by numeric user_id and prints no name. Rubric assessments carry free-
  text comments and assessor names/ids; this reads points only and reports aggregates,
  never who rated whom. With fewer than 3 assessments a reviewee's average is close to
  one person's rating, so those rows are flagged.

Usage:
  uv run python lib/tools/peer_review_summary.py --title "Prep ratings"
  uv run python lib/tools/peer_review_summary.py --assignment-id 123 --csv out.csv

Requires in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, and the env var named by
--target (default CANVAS_COURSE_ID).

Exit codes:
  0  report printed (including "no peer assessments yet")
  1  Canvas could not be read
  2  configuration / validation error
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import defaultdict

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
LOW_N = 3


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get_all(endpoint: str, params: dict | list | None = None) -> list | dict | None:
    """GET following `Link: rel="next"`; None on any failure so a partial read is never
    reported as a complete one."""
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    if isinstance(params, list):
        query: dict | list | None = [("per_page", "100"), *params]
    else:
        query = {"per_page": 100, **(params or {})}
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


# ---------------------------------------------------------------------------
# Aggregation (PURE)
# ---------------------------------------------------------------------------

def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def summarize(assessments: list, criteria: list[dict],
              submission_to_user: dict[int, int]) -> dict[int, dict]:
    """user_id -> {"n_peer", "peer": {criterion_id: mean points}, "peer_pct",
                   "n_self", "self_pct"}.

    Only `assessment_type == "peer_review"` counts. Points only: comments and assessor
    names are never read. A criterion with no rating (points None) is skipped, not
    counted as zero."""
    maxes = {c["id"]: float(c.get("points") or 0) for c in criteria}
    peer_pts: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    self_pts: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    n_peer: dict[int, int] = defaultdict(int)
    n_self: dict[int, int] = defaultdict(int)

    for a in assessments:
        if not isinstance(a, dict) or a.get("assessment_type") != "peer_review":
            continue
        user = submission_to_user.get(a.get("artifact_id"))
        if user is None:
            continue
        is_self = a.get("assessor_id") == user
        (n_self if is_self else n_peer)[user] += 1
        bucket = self_pts if is_self else peer_pts
        for d in a.get("data") or []:
            cid, pts = d.get("criterion_id"), d.get("points")
            if cid in maxes and pts is not None:
                bucket[user][cid].append(float(pts))

    def pct(per_crit: dict[str, list[float]]) -> float | None:
        shares = [(_mean(v) or 0) / maxes[c] for c, v in per_crit.items() if maxes[c] > 0]
        return _mean(shares)

    out: dict[int, dict] = {}
    for user in set(n_peer) | set(n_self):
        out[user] = {
            "n_peer": n_peer.get(user, 0),
            "peer": {c: _mean(v) for c, v in peer_pts.get(user, {}).items()},
            "peer_pct": pct(peer_pts.get(user, {})),
            "n_self": n_self.get(user, 0),
            "self_pct": pct(self_pts.get(user, {})),
        }
    return out


def _fmt(x: float | None, pct: bool = False) -> str:
    if x is None:
        return "—"
    return f"{x * 100:.0f}%" if pct else f"{x:.2f}"


def print_table(rows: dict[int, dict], criteria: list[dict]) -> None:
    head = ["user_id", "n_peer", "peer_overall"] + [c["description"][:14] for c in criteria] \
        + ["self_overall"]
    print("  " + "  ".join(f"{h:<14}" for h in head))
    for user in sorted(rows):
        r = rows[user]
        cells = [str(user), f"{r['n_peer']}{' *' if r['n_peer'] < LOW_N else ''}",
                 _fmt(r["peer_pct"], pct=True)]
        cells += [_fmt(r["peer"].get(c["id"])) for c in criteria]
        cells.append(_fmt(r["self_pct"], pct=True))
        print("  " + "  ".join(f"{c:<14}" for c in cells))


def write_csv(path: str, rows: dict[int, dict], criteria: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["user_id", "n_peer", "peer_overall_pct"]
                   + [c["description"] for c in criteria] + ["n_self", "self_overall_pct"])
        for user in sorted(rows):
            r = rows[user]
            w.writerow([user, r["n_peer"], r["peer_pct"]]
                       + [r["peer"].get(c["id"]) for c in criteria]
                       + [r["n_self"], r["self_pct"]])


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
        description="Per-student peer rating averages from a peer rubric (read-only).")
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--assignment-id", type=int, help="The peer-review assignment")
    which.add_argument("--title", help="Its exact title")
    ap.add_argument("--csv", default=None, metavar="PATH",
                    help="Also write the table to a CSV (user_id-keyed, no names)")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Env var holding the course id (default CANVAS_COURSE_ID)")
    ap.add_argument("--course-id", default=None, help="Literal course id; overrides --target")
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
                  mode="read", label="peer review target")

    if args.assignment_id:
        assignment = _get_all(f"/courses/{course_id}/assignments/{args.assignment_id}")
    else:
        assignment = find_assignment(course_id, args.title)
    if not isinstance(assignment, dict) or not assignment.get("id"):
        print("ERROR: assignment not found in this course.")
        return 2
    rubric_id = (assignment.get("rubric_settings") or {}).get("id")
    if not rubric_id:
        print(f"ERROR: {assignment.get('name')!r} has no rubric attached, so there are no "
              "peer ratings to read. Create it with peer_review_setup.py.")
        return 2

    rubric = _get_all(f"/courses/{course_id}/rubrics/{rubric_id}",
                      [("include[]", "peer_assessments"), ("style", "full")])
    subs = _get_all(f"/courses/{course_id}/assignments/{assignment['id']}/submissions")
    if not isinstance(rubric, dict) or subs is None:
        print("ERROR: could not read the rubric or submissions from Canvas.")
        return 1

    criteria = [{"id": c["id"], "description": c.get("description") or c["id"],
                 "points": c.get("points")} for c in rubric.get("data") or []]
    sub_to_user = {s["id"]: s["user_id"] for s in subs
                   if isinstance(s, dict) and s.get("id") and s.get("user_id")}
    rows = summarize(rubric.get("assessments") or [], criteria, sub_to_user)

    print(f"Peer ratings: {assignment.get('name')}")
    if not rows:
        print("  no peer assessments yet.")
        return 0
    print_table(rows, criteria)
    if any(r["n_peer"] < LOW_N for r in rows.values()):
        print(f"\n  * fewer than {LOW_N} peer assessments — the average is close to one "
              "person's rating; treat it as such.")
    if args.csv:
        write_csv(args.csv, rows, criteria)
        print(f"\n  wrote {args.csv} (user_id-keyed, no names)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

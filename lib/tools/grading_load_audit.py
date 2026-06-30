#!/usr/bin/env python3
"""
grading_load_audit.py — read-only audit: does grading consume ≤75% of instructor time?

Closes BYUI Course Design Standard 7.3 ("Grading load does not consume more than
75% of instructors' time on average each week"). Complements workload_audit.py
which checks total student/instructor load (BYUI 3hr/credit/wk); this tool zeroes
in on the GRADING portion specifically.

WHAT IT CHECKS

  - Estimate grading hours per week for the course as configured
  - Compare to the facilitator-load cap (course_credits × 3hr × 0.75)
  - Per-assignment-type breakdown so the operator sees where the time goes
  - Surface specific over-load contributors

ESTIMATION MODEL (deterministic)

  For each published assignment with points_possible > 0 and at least one
  submission expected:

    estimated_grader_minutes_per_submission =
      lookup(assignment.submission_types[], --time-defaults-json)

  Defaults (overridable via --time-defaults-json):

    submission_type       | minutes per submission
    ----------------------|------------------------
    online_quiz           |  1 (auto-graded by default)
    on_paper              |  6
    discussion_topic      |  4
    online_upload         | 10 (file submission, rubric-graded)
    online_text_entry     |  8
    media_recording       | 15 (must watch/listen)
    external_tool         |  5 (LTI; varies — conservative default)
    none                  |  0 (non-submittable)

    Bumps applied:
      +5 min if has_rubric and uses rubric for grading (more careful score)
      +5 min if peer_review_count > 0 (instructor also reviews peer reviews)
      +50% if submission_type=='online_upload' AND assignment.name contains
        any of: 'essay', 'paper', 'report', 'writeup', 'analysis', 'reflection'
        (prose-heavy uploads take longer than code/spreadsheet uploads)

  Per-assignment total grading time:
    minutes_per_assignment = estimated_grader_minutes * (--students × --submission-rate)

  Per-week distribution:
    Bucketed by due_at week. Course's grading load per week = sum of all
    assignments' minutes due that week / 60 → hours.

CAP

  facilitator_grading_cap_hours_per_week = course_credits × 3.0 × 0.75
    (3 hr/credit/wk allocation × 75% spent on grading)

  Default course_credits resolved from Canvas course object's `course_code`
  number if discoverable, OR fall back to --credits (default 3).

FLAGS

  OVER_CAP_WEEKS    Any week's estimated grading exceeds the cap → list the
                    weeks + the high-contribution assignments.
  CAP_OVERAGE_MEAN  Average weekly grading load > cap → systemic overload.

NO LIVE-RUN ASSUMPTIONS. The model is a deterministic estimate, NOT an
empirical measurement. Numbers are reasonable defaults; the operator can
override --time-defaults-json with their own per-assignment-type table
calibrated from a real grading cycle.

ENDPOINTS (all GET, read-only):
  GET /courses/:id                                          (course name, code, total_students)
  GET /courses/:id/assignments                              (incl. submission_types, due_at, peer_review_count, rubric_settings)
  GET /courses/:id/blueprint_subscriptions                  (safety guard, advisory)

EXIT CODES
  0  under cap
  1  any week over cap OR mean over cap
  2  configuration error

USAGE
  uv run python canvas_toolbox/lib/tools/grading_load_audit.py --course-id 402262
  uv run python canvas_toolbox/lib/tools/grading_load_audit.py --course-id 402262 \\
    --credits 3 --students 30 --submission-rate 0.95 \\
    --report /tmp/itm327_grading_load.md

ANCHORS
  - course_design_standards_knowledge.md standard 7.3
  - workload_audit.py (the 3hr/credit/wk facilitator-load math)

PAIRS WITH
  - workload_audit.py        (total facilitator load — this tool's cap derives from it)
  - grading_structure_audit.py (different concern: weight/balance, not time)
"""
from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

import canvas_course_guard as guard
from __toolbox_version__ import __version__

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url
_TIMEOUT = 30

DEFAULT_TIME_DEFAULTS = {
    "online_quiz": 1,
    "on_paper": 6,
    "discussion_topic": 4,
    "online_upload": 10,
    "online_text_entry": 8,
    "media_recording": 15,
    "external_tool": 5,
    "none": 0,
}

PROSE_NAME_PATTERNS = re.compile(r"\b(essay|paper|report|writeup|analysis|reflection)\b", re.I)


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(path: str, params: dict | None = None) -> object:
    url = f"{CANVAS_BASE_URL}/api/v1{path}"
    try:
        r = requests.get(url, headers=_headers(), params=params or {}, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"WARN: GET {path} failed ({type(e).__name__}): {e}", file=sys.stderr)
        return None


def _get_paged(path: str, params: dict | None = None) -> list:
    out: list = []
    url = f"{CANVAS_BASE_URL}/api/v1{path}"
    base_params = {**(params or {}), "per_page": 100}
    while url:
        try:
            r = requests.get(url, headers=_headers(),
                             params=base_params if "?" not in url else None,
                             timeout=_TIMEOUT)
            r.raise_for_status()
            page = r.json()
            if isinstance(page, list):
                out.extend(page)
            else:
                return [page]
            link_hdr = r.headers.get("Link", "")
            m = re.search(r'<([^>]+)>;\s*rel="next"', link_hdr)
            url = m.group(1) if m else None
            base_params = None
        except Exception as e:
            print(f"WARN: GET {path} paged failed ({type(e).__name__}): {e}", file=sys.stderr)
            break
    return out


def _parse_due_at(due_at: str | None) -> datetime | None:
    if not due_at:
        return None
    try:
        return datetime.fromisoformat(due_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def estimate_minutes_per_submission(a: dict, time_defaults: dict) -> int:
    """Estimate grader minutes per single submission, applying bumps."""
    types = a.get("submission_types") or ["none"]
    # Pick the highest-cost type listed (assignments may list multiple — instructor grades whatever the student picks)
    base = max((time_defaults.get(t, 5) for t in types), default=0)
    # Rubric bump
    rs = a.get("rubric_settings") or {}
    if rs.get("use_rubric_for_grading"):
        base += 5
    # Peer-review bump (instructor reviews the peer reviews too)
    if (a.get("peer_review_count") or 0) > 0:
        base += 5
    # Prose-name bump for online_upload
    if "online_upload" in types and PROSE_NAME_PATTERNS.search(a.get("name", "")):
        base = int(base * 1.5)
    return base


def estimate_course_credits(course: dict, default: int) -> int:
    """Try to extract course credit count from course_code (e.g. 'ITM 327' → 3).
    Falls back to --credits default. Catalog data isn't exposed by the
    Canvas API, so we always return the operator-supplied default."""
    return default


def audit_grading_load(
    course: dict, assignments: list[dict],
    students: int, submission_rate: float, credits: int,
    time_defaults: dict,
) -> dict:
    """Run the grading-load estimation + cap check."""
    cap_per_week = credits * 3.0 * 0.75  # hours

    # Per-assignment estimates
    records: list[dict] = []
    for a in assignments:
        if a.get("workflow_state") != "published":
            continue
        pts = float(a.get("points_possible") or 0)
        if pts == 0:
            # Ungraded — no grading load. (Auto-grade quizzes still get 1 min for
            # gradebook touch, but workflow_state=published + 0 pts is "not graded.")
            continue
        mins_per = estimate_minutes_per_submission(a, time_defaults)
        expected_submissions = students * submission_rate
        total_minutes = mins_per * expected_submissions
        records.append({
            "id": a.get("id"),
            "name": a.get("name", ""),
            "submission_types": a.get("submission_types") or [],
            "due_at": a.get("due_at"),
            "minutes_per_submission": mins_per,
            "expected_submissions": expected_submissions,
            "total_minutes": total_minutes,
            "total_hours": total_minutes / 60.0,
            "points_possible": pts,
        })

    # Week buckets — ISO week of due_at
    weekly_minutes: dict[str, float] = defaultdict(float)
    weekly_assignments: dict[str, list[dict]] = defaultdict(list)
    undated_minutes = 0.0
    undated_assignments: list[dict] = []
    for r in records:
        d = _parse_due_at(r["due_at"])
        if not d:
            undated_minutes += r["total_minutes"]
            undated_assignments.append(r)
            continue
        # ISO week label: YYYY-Www
        iso_year, iso_week, _ = d.isocalendar()
        wk_label = f"{iso_year}-W{iso_week:02d}"
        weekly_minutes[wk_label] += r["total_minutes"]
        weekly_assignments[wk_label].append(r)

    weeks_sorted = sorted(weekly_minutes.keys())
    week_rows: list[dict] = []
    over_cap_weeks: list[dict] = []
    for wk in weeks_sorted:
        hours = weekly_minutes[wk] / 60.0
        rec = {
            "week": wk,
            "total_hours": hours,
            "over_cap": hours > cap_per_week,
            "assignments": [{"name": a["name"], "total_hours": a["total_hours"]}
                            for a in weekly_assignments[wk]],
        }
        week_rows.append(rec)
        if hours > cap_per_week:
            over_cap_weeks.append(rec)

    mean_weekly_hours = (
        sum(weekly_minutes.values()) / 60.0 / len(weeks_sorted) if weeks_sorted else 0.0
    )

    # Verdict
    flags_count = sum([
        bool(over_cap_weeks),
        bool(mean_weekly_hours > cap_per_week),
    ])
    return {
        "course_name": course.get("name", "<unknown>"),
        "course_id": course.get("id"),
        "course_code": course.get("course_code", ""),
        "credits_used": credits,
        "students_used": students,
        "submission_rate_used": submission_rate,
        "cap_per_week_hours": cap_per_week,
        "mean_weekly_hours": mean_weekly_hours,
        "mean_over_cap": mean_weekly_hours > cap_per_week,
        "weeks": week_rows,
        "over_cap_weeks": over_cap_weeks,
        "undated_minutes": undated_minutes,
        "undated_assignments": undated_assignments,
        "graded_assignment_count": len(records),
        "flags_count": flags_count,
        "verdict": "under_cap" if flags_count == 0 else "over_cap",
        "time_defaults": time_defaults,
        "assignments": records,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_markdown(res: dict, ts: str) -> list[str]:
    L: list[str] = []
    L.append(f"# Grading Load Audit — {res['course_name']}")
    L.append("")
    L.append(f"**Course ID:** {res['course_id']} ({res['course_code']})")
    L.append(f"**Generated:** {ts}")
    L.append(f"**Tool:** grading_load_audit.py (canvas-toolbox {__version__})")
    L.append(f"**Standard:** BYUI Course Design Standard 7.3 — "
             "grading ≤ 75% of facilitator allocation")
    L.append("")
    L.append("**Verdict:** " + ("✅ **under cap**" if res["verdict"] == "under_cap"
                                else f"⚠ **over cap** ({res['flags_count']} flag(s))"))
    L.append("")
    L.append("## Parameters")
    L.append("")
    L.append(f"- Course credits: **{res['credits_used']}** (override via `--credits`)")
    L.append(f"- Students: **{res['students_used']}**")
    L.append(f"- Submission rate: **{res['submission_rate_used']:.0%}**")
    L.append(f"- Cap per week (credits × 3 hr × 0.75): **{res['cap_per_week_hours']:.2f} hr**")
    L.append(f"- Graded assignments (published, > 0 pts): **{res['graded_assignment_count']}**")
    L.append(f"- Mean weekly grading load (across weeks with due items): "
             f"**{res['mean_weekly_hours']:.2f} hr**")
    L.append("")

    # Mean-over-cap flag
    if res["mean_over_cap"]:
        L.append("## ⛔ CAP_OVERAGE_MEAN — average weekly grading exceeds the cap")
        L.append("")
        L.append(f"Average grading load: **{res['mean_weekly_hours']:.2f} hr/wk** "
                 f"vs. cap **{res['cap_per_week_hours']:.2f} hr/wk**.")
        L.append("")
        L.append("This is structural — even an evenly distributed schedule exceeds the "
                 "facilitator allocation. Either reduce graded volume, simplify rubrics, "
                 "automate where possible (auto-graded quizzes, peer review with light "
                 "instructor verification), or increase the credit count.")
        L.append("")

    # Per-week table
    L.append("## Per-week grading load")
    L.append("")
    L.append("| Week | Total hr | Over cap? | Assignments |")
    L.append("|---|---:|---|---|")
    for w in res["weeks"]:
        ax = ", ".join(f"{a['name']} ({a['total_hours']:.1f}h)" for a in w["assignments"])
        flag = "⚠ YES" if w["over_cap"] else ""
        L.append(f"| {w['week']} | {w['total_hours']:.2f} | {flag} | {ax} |")
    L.append("")

    # Over-cap weeks detail
    if res["over_cap_weeks"]:
        L.append("## ⚠ OVER_CAP_WEEKS — individual weeks above the cap")
        L.append("")
        L.append("These weeks' estimated grading load exceeds the facilitator allocation. "
                 "Even if the term mean is fine, the instructor faces a load spike — "
                 "consider redistributing major assessments to neighboring weeks or "
                 "extending grading windows.")
        L.append("")
        L.append(f"| Week | Total hr | Cap | Overage | Top contributor |")
        L.append("|---|---:|---:|---:|---|")
        for w in res["over_cap_weeks"]:
            top = max(w["assignments"], key=lambda a: a["total_hours"], default=None)
            top_str = (f"{top['name']} ({top['total_hours']:.1f}h)" if top else "")
            L.append(f"| {w['week']} | {w['total_hours']:.2f} | {res['cap_per_week_hours']:.2f} | "
                     f"{w['total_hours'] - res['cap_per_week_hours']:.2f} | {top_str} |")
        L.append("")

    # Undated assignments (informational)
    if res["undated_assignments"]:
        undated_hrs = res["undated_minutes"] / 60.0
        L.append("## ℹ Undated assignments")
        L.append("")
        L.append(f"**{len(res['undated_assignments'])}** graded assignments have no `due_at` "
                 f"(estimated **{undated_hrs:.1f} hr** of grading total). Set due dates to get "
                 "an accurate per-week distribution. Names (capped at 10):")
        L.append("")
        for a in res["undated_assignments"][:10]:
            L.append(f"- {a['name']} ({a['total_hours']:.1f}h)")
        L.append("")

    # Time defaults reference
    L.append("---")
    L.append("")
    L.append("## Time defaults used (minutes per submission)")
    L.append("")
    L.append("| Submission type | Minutes |")
    L.append("|---|---:|")
    for k, v in res["time_defaults"].items():
        L.append(f"| {k} | {v} |")
    L.append("")
    L.append("Bumps applied: +5 min if rubric used for grading; +5 min if peer review > 0; "
             "+50% if `online_upload` AND name matches "
             "essay/paper/report/writeup/analysis/reflection. Override the whole table "
             "via `--time-defaults-json <path.json>` with your own per-type table "
             "(calibrated from a real grading cycle).")
    L.append("")

    # Audit tag
    L.append("## Audit tag")
    L.append("")
    tag_flags = []
    if res["over_cap_weeks"]:
        tag_flags.append(f"over_cap_weeks={len(res['over_cap_weeks'])}")
    if res["mean_over_cap"]:
        tag_flags.append("mean_over_cap")
    L.append(f"`grading_load`: **{res['verdict']}** "
             f"({', '.join(tag_flags) if tag_flags else 'all clear'})")
    return L


def _render_json(res: dict, ts: str) -> dict:
    return {
        "tool": "grading_load_audit",
        "version": __version__,
        "generated": ts,
        "course_id": res["course_id"],
        "course_name": res["course_name"],
        "course_code": res["course_code"],
        "standard": "BYUI Course Design Standard 7.3 — grading load ≤ 75% of facilitator allocation",
        "verdict": res["verdict"],
        "grading_load": res["verdict"],
        "parameters": {
            "credits_used": res["credits_used"],
            "students_used": res["students_used"],
            "submission_rate_used": res["submission_rate_used"],
            "cap_per_week_hours": res["cap_per_week_hours"],
        },
        "mean_weekly_hours": res["mean_weekly_hours"],
        "graded_assignment_count": res["graded_assignment_count"],
        "weeks": res["weeks"],
        "flags": {
            "mean_over_cap": res["mean_over_cap"],
            "over_cap_weeks": res["over_cap_weeks"],
        },
        "undated_minutes": res["undated_minutes"],
        "undated_assignments": [{"name": a["name"], "total_hours": a["total_hours"]}
                                for a in res["undated_assignments"]],
        "time_defaults": res["time_defaults"],
    }


def _write_report(path: Path, body: str) -> None:
    path.write_text(body + "\n", encoding="utf-8")
    print(f"\nReport written to {path}", file=sys.stderr)
    if path.suffix.lower() in (".md", ".markdown"):
        try:
            from _md_to_pdf import render_pair
            render_pair(path)
        except ImportError:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Audit grading-load against the 75% facilitator-allocation cap (BYUI Standard 7.3).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--course-id", help="Canvas course id.")
    grp.add_argument("--target", default="CANVAS_COURSE_ID",
                     help="Env var to read the course id from. Default CANVAS_COURSE_ID.")
    ap.add_argument("--report", help=".md path to write the report (with .pdf sibling if Chrome).")
    ap.add_argument("--emit-json", action="store_true",
                    help="Emit JSON to stdout instead of human-readable markdown.")
    ap.add_argument("--credits", type=int, default=3,
                    help="Course credits (used to compute the facilitator cap). Default 3.")
    ap.add_argument("--students", type=int, default=None,
                    help="Number of students (default: course.total_students if available, else 25).")
    ap.add_argument("--submission-rate", type=float, default=0.95,
                    help="Fraction of students expected to submit each assignment. Default 0.95.")
    ap.add_argument("--time-defaults-json", default=None,
                    help="Path to JSON overriding the per-submission-type minute defaults.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Bypass canvas_course_guard advisory for enrolled-course reads.")
    args = ap.parse_args()

    if not CANVAS_API_TOKEN or not CANVAS_BASE_URL:
        print("ERROR: CANVAS_API_TOKEN and CANVAS_BASE_URL must be set in .env.", file=sys.stderr)
        return 2
    course_id = args.course_id or os.environ.get(args.target, "")
    if not course_id:
        print(f"ERROR: course ID not found. Pass --course-id <id> or set {args.target}.",
              file=sys.stderr)
        return 2

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="read", allow_override=args.allow_enrolled, label="audit target")

    # Time defaults — load overrides if given
    time_defaults = dict(DEFAULT_TIME_DEFAULTS)
    if args.time_defaults_json:
        try:
            with open(args.time_defaults_json, encoding="utf-8") as f:
                time_defaults.update(json.load(f))
        except Exception as e:
            print(f"ERROR: couldn't load --time-defaults-json: {e}", file=sys.stderr)
            return 2

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    course = _get(f"/courses/{course_id}", params={"include[]": "total_students"}) or {}
    if not isinstance(course, dict):
        print(f"ERROR: couldn't load course {course_id}.", file=sys.stderr)
        return 2

    # Resolve students
    students = args.students
    if students is None:
        students = course.get("total_students") or 25

    assignments = _get_paged(
        f"/courses/{course_id}/assignments",
        params={"include[]": ["rubric", "rubric_settings"]},
    )
    if not assignments:
        print(f"ERROR: no assignments for course {course_id}.", file=sys.stderr)
        return 2

    res = audit_grading_load(
        course, assignments,
        students=students,
        submission_rate=args.submission_rate,
        credits=args.credits,
        time_defaults=time_defaults,
    )

    if args.emit_json:
        body = json.dumps(_render_json(res, ts), indent=2, ensure_ascii=False)
        print(body)
        if args.report:
            _write_report(Path(args.report), body)
    else:
        lines = _render_markdown(res, ts)
        print("\n".join(lines))
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    return 0 if res["verdict"] == "under_cap" else 1


if __name__ == "__main__":
    sys.exit(main())

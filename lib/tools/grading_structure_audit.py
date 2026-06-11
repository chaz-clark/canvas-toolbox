#!/usr/bin/env python3
"""
grading_structure_audit.py — read-only audit of a course's grading-structure arithmetic.

Closes the parking-lot entry "Grading-structure audit tool" (handoffs/parkinglot.md).
Faculty currently solve this by printing the Assignments page to PDF and uploading
it to ChatGPT with a structured prompt — that's a tool-gap signal (per the meta-
heuristic in the parking lot). The arithmetic doesn't need AI; we have the canonical
structured data from the Canvas API.

WHAT IT CHECKS (six gap signals, all arithmetic):

  1. SUM_NOT_100      Assignment-group weights don't sum to 100 (when the course is
                      set to apply group weights to the final grade).
  2. WEIGHT_MISMATCH  A category's declared weight is significantly off from its
                      actual point contribution proportion (when group weights are
                      OFF but groups have weights — typically a config drift).
  3. OVER_INFLUENCE   A single assignment is worth more than X% of the final grade
                      (default: 25%). Over-influential assignments amplify the
                      consequence of a single bad day.
  4. TOO_SMALL        Assignments worth less than Y% of the final grade (default:
                      1%). Below the threshold, the assignment doesn't materially
                      affect a student's grade — it's busywork from the student's
                      perspective.
  5. CATEGORY_CARRY   A single assignment is worth more than Z% of its own category
                      (default: 60%). Defeats the category structure — students
                      can't make up that assignment elsewhere in the category.
  6. TEMPORAL_STACK   More than W% of the term's points are due in the last 2 weeks
                      (default: 40%). End-loaded grading punishes students who
                      stumble late and rewards crammers.

NO AI REQUIRED — all six checks are deterministic arithmetic against the Canvas
API's assignment_groups + assignments resources. Faculty get the exact numbers
they were printing to PDF and approximating with ChatGPT.

OUTPUT
  --report PATH    structured markdown report (with PDF sibling via _md_to_pdf if
                   Chrome is available)
  --emit-json      structured JSON for downstream consumers
  default          human-readable markdown to stdout

EXIT CODES
  0  no flags
  1  at least one flag fired
  2  configuration error

ENDPOINTS (all GET, read-only):
  GET /courses/:id                                         (course name + weight setting)
  GET /courses/:id?include[]=total_students                (safety guard, advisory)
  GET /courses/:id/blueprint_subscriptions                 (safety guard, advisory)
  GET /courses/:id/assignment_groups?include[]=assignments (the main data)

USAGE
  uv run python canvas_toolbox/lib/tools/grading_structure_audit.py --course-id 402262
  uv run python canvas_toolbox/lib/tools/grading_structure_audit.py --target CANVAS_SANDBOX_ID
  uv run python canvas_toolbox/lib/tools/grading_structure_audit.py --course-id 402262 \\
    --over-influence 30 --too-small 0.5 --temporal-stack 50 \\
    --report /tmp/itm327_grading_structure.md

ANCHORS
  - Parking-lot entry (handoffs/parkinglot.md line 26): "Grading-structure audit tool"
  - Meta-heuristic: "Print-to-AI workflows are tool-gap signals" — this audit
    eliminates the print-to-AI step for grading-structure arithmetic.

PAIRS WITH
  - workload_audit.py     (student/instructor load — different concern)
  - course_audit.py       (umbrella audit)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
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


# ---------------------------------------------------------------------------
# The audit
# ---------------------------------------------------------------------------

def _parse_due_at(due_at: str | None) -> datetime | None:
    if not due_at:
        return None
    try:
        # Canvas uses ISO 8601 with 'Z' suffix
        return datetime.fromisoformat(due_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def audit_structure(
    course: dict,
    groups: list[dict],
    over_influence_pct: float,
    too_small_pct: float,
    category_carry_pct: float,
    temporal_stack_pct: float,
) -> dict:
    """Run all six arithmetic checks. Returns a structured report."""
    apply_weights = bool(course.get("apply_assignment_group_weights"))
    course_name = course.get("name") or "<unknown course>"

    # Compute total points across all assignments (in published state — Canvas
    # convention: assignments with workflow_state='published' count toward grade)
    all_assignments: list[dict] = []
    for g in groups:
        for a in g.get("assignments") or []:
            if a.get("workflow_state") == "published":
                all_assignments.append({**a, "_group_id": g.get("id"), "_group_name": g.get("name")})
    total_points = sum(float(a.get("points_possible") or 0) for a in all_assignments) or 1.0

    # ------ Flag 1: SUM_NOT_100 (weights-on courses only) ------
    sum_not_100 = None
    if apply_weights:
        total_weight = sum(float(g.get("group_weight") or 0) for g in groups)
        sum_not_100 = {
            "active": apply_weights,
            "total_weight": total_weight,
            "delta_from_100": total_weight - 100.0,
            "flag": abs(total_weight - 100.0) > 0.5,
        }

    # ------ Per-category breakdown + Flag 2: WEIGHT_MISMATCH ------
    category_records: list[dict] = []
    weight_mismatches: list[dict] = []
    for g in groups:
        assignments_in_g = [a for a in all_assignments if a["_group_id"] == g.get("id")]
        cat_points = sum(float(a.get("points_possible") or 0) for a in assignments_in_g)
        actual_pct_of_total = (cat_points / total_points * 100.0) if total_points else 0.0
        declared_weight = float(g.get("group_weight") or 0)
        rec = {
            "id": g.get("id"),
            "name": g.get("name", ""),
            "assignment_count": len(assignments_in_g),
            "category_points": cat_points,
            "actual_pct_of_total": actual_pct_of_total,
            "declared_weight": declared_weight,
            "weight_used_for_grade": apply_weights,
        }
        category_records.append(rec)
        # WEIGHT_MISMATCH fires when course is NOT using weights but groups still have them
        # AND the actual-vs-declared delta is big. This is the most common config drift.
        if not apply_weights and declared_weight > 0 and abs(actual_pct_of_total - declared_weight) > 5:
            weight_mismatches.append({
                "category": g.get("name", ""),
                "declared_weight": declared_weight,
                "actual_pct_of_total": actual_pct_of_total,
                "delta": actual_pct_of_total - declared_weight,
            })

    # ------ Flag 3: OVER_INFLUENCE (single assignment > X% of grade) ------
    over_influence: list[dict] = []
    for a in all_assignments:
        pts = float(a.get("points_possible") or 0)
        if apply_weights:
            # weighted % = (pts / category_points) * (declared_weight)
            grp = next((g for g in groups if g.get("id") == a["_group_id"]), {})
            cat_pts = sum(float(x.get("points_possible") or 0) for x in (grp.get("assignments") or [])
                          if x.get("workflow_state") == "published") or 1.0
            grade_pct = (pts / cat_pts) * float(grp.get("group_weight") or 0)
        else:
            grade_pct = (pts / total_points) * 100.0
        if grade_pct >= over_influence_pct:
            over_influence.append({
                "name": a.get("name", ""),
                "category": a["_group_name"],
                "points_possible": pts,
                "pct_of_final_grade": grade_pct,
            })

    # ------ Flag 4: TOO_SMALL (single assignment < Y% of grade) ------
    too_small: list[dict] = []
    for a in all_assignments:
        pts = float(a.get("points_possible") or 0)
        if pts == 0:
            continue  # 0-point assignments are non-gradable, not "too small"
        if apply_weights:
            grp = next((g for g in groups if g.get("id") == a["_group_id"]), {})
            cat_pts = sum(float(x.get("points_possible") or 0) for x in (grp.get("assignments") or [])
                          if x.get("workflow_state") == "published") or 1.0
            grade_pct = (pts / cat_pts) * float(grp.get("group_weight") or 0)
        else:
            grade_pct = (pts / total_points) * 100.0
        if grade_pct < too_small_pct:
            too_small.append({
                "name": a.get("name", ""),
                "category": a["_group_name"],
                "points_possible": pts,
                "pct_of_final_grade": grade_pct,
            })

    # ------ Flag 5: CATEGORY_CARRY (one assignment > Z% of its category) ------
    category_carry: list[dict] = []
    for g in groups:
        assignments_in_g = [a for a in all_assignments if a["_group_id"] == g.get("id")]
        if len(assignments_in_g) < 2:
            continue  # Singleton categories trivially "carry"; not a smell
        cat_pts = sum(float(a.get("points_possible") or 0) for a in assignments_in_g) or 1.0
        for a in assignments_in_g:
            pts = float(a.get("points_possible") or 0)
            pct_of_cat = (pts / cat_pts) * 100.0
            if pct_of_cat >= category_carry_pct:
                category_carry.append({
                    "name": a.get("name", ""),
                    "category": g.get("name", ""),
                    "points_possible": pts,
                    "category_total_points": cat_pts,
                    "pct_of_category": pct_of_cat,
                })

    # ------ Flag 6: TEMPORAL_STACK (last 2 weeks of term > W% of points) ------
    # Discover term window from the course's start_at + end_at; fall back to
    # min/max of assignment due_at if unset.
    course_start = _parse_due_at(course.get("start_at"))
    course_end = _parse_due_at(course.get("end_at"))
    if not (course_start and course_end):
        due_dates = [_parse_due_at(a.get("due_at")) for a in all_assignments]
        due_dates = [d for d in due_dates if d]
        if due_dates:
            course_start = course_start or min(due_dates)
            course_end = course_end or max(due_dates)

    temporal_stack: dict | None = None
    if course_start and course_end:
        last_2_weeks_start = course_end - timedelta(days=14)
        points_last_2_weeks = 0.0
        points_dated = 0.0
        for a in all_assignments:
            d = _parse_due_at(a.get("due_at"))
            pts = float(a.get("points_possible") or 0)
            if not d:
                continue
            points_dated += pts
            if d >= last_2_weeks_start:
                points_last_2_weeks += pts
        if points_dated > 0:
            pct_in_last_2 = (points_last_2_weeks / points_dated) * 100.0
            temporal_stack = {
                "course_start": course_start.isoformat(),
                "course_end": course_end.isoformat(),
                "last_2_weeks_start": last_2_weeks_start.isoformat(),
                "points_last_2_weeks": points_last_2_weeks,
                "points_dated": points_dated,
                "pct_in_last_2_weeks": pct_in_last_2,
                "flag": pct_in_last_2 >= temporal_stack_pct,
            }

    # Verdict
    flag_count = sum([
        bool(sum_not_100 and sum_not_100["flag"]),
        bool(weight_mismatches),
        bool(over_influence),
        bool(too_small),
        bool(category_carry),
        bool(temporal_stack and temporal_stack["flag"]),
    ])

    return {
        "course_name": course_name,
        "course_id": course.get("id"),
        "apply_weights": apply_weights,
        "total_points": total_points,
        "published_assignment_count": len(all_assignments),
        "categories": category_records,
        "sum_not_100": sum_not_100,
        "weight_mismatches": weight_mismatches,
        "over_influence": over_influence,
        "too_small": too_small,
        "category_carry": category_carry,
        "temporal_stack": temporal_stack,
        "flag_count": flag_count,
        "verdict": "no_flags" if flag_count == 0 else "flags_present",
        "thresholds": {
            "over_influence_pct": over_influence_pct,
            "too_small_pct": too_small_pct,
            "category_carry_pct": category_carry_pct,
            "temporal_stack_pct": temporal_stack_pct,
        },
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_markdown(res: dict, ts: str) -> list[str]:
    L: list[str] = []
    L.append(f"# Grading Structure Audit — {res['course_name']}")
    L.append("")
    L.append(f"**Course ID:** {res['course_id']}")
    L.append(f"**Generated:** {ts}")
    L.append(f"**Tool:** grading_structure_audit.py (canvas-toolbox {__version__})")
    L.append("")
    L.append("**Verdict:** " + ("✅ **no flags**" if res["verdict"] == "no_flags"
                                else f"⚠ **{res['flag_count']} flag(s)**"))
    L.append("")
    L.append("## Course summary")
    L.append("")
    L.append(f"- Published assignments: **{res['published_assignment_count']}**")
    L.append(f"- Total points (across all categories): **{res['total_points']:.0f}**")
    L.append(f"- Grade computed by: " +
             ("**weighted assignment groups**" if res["apply_weights"]
              else "**raw points** (groups carry no weight)"))
    L.append("")
    thr = res["thresholds"]
    L.append(f"_Thresholds: over-influence ≥ {thr['over_influence_pct']:.1f}%, "
             f"too-small < {thr['too_small_pct']:.1f}%, "
             f"category-carry ≥ {thr['category_carry_pct']:.1f}%, "
             f"temporal-stack ≥ {thr['temporal_stack_pct']:.1f}% of points in last 2 weeks._")
    L.append("")

    # Categories table
    L.append("## Categories (assignment groups)")
    L.append("")
    L.append("| Category | # Assignments | Points | % of total | Declared weight |")
    L.append("|---|---:|---:|---:|---:|")
    for c in res["categories"]:
        wt = f"{c['declared_weight']:.1f}%" if c["declared_weight"] else "—"
        L.append(f"| {c['name']} | {c['assignment_count']} | "
                 f"{c['category_points']:.0f} | {c['actual_pct_of_total']:.1f}% | {wt} |")
    L.append("")

    # Flag 1: SUM_NOT_100
    if res["sum_not_100"] and res["sum_not_100"]["flag"]:
        s = res["sum_not_100"]
        L.append("## ⚠ SUM_NOT_100 — assignment-group weights don't sum to 100%")
        L.append("")
        L.append(f"Course is set to **weight grades by assignment groups**, but the weights "
                 f"sum to **{s['total_weight']:.1f}%** (off by {s['delta_from_100']:+.1f}%).")
        L.append("")
        L.append("Fix: edit assignment-group weights so they sum to exactly 100.")
        L.append("")

    # Flag 2: WEIGHT_MISMATCH
    if res["weight_mismatches"]:
        L.append("## ⚠ WEIGHT_MISMATCH — categories have weights but they aren't being used")
        L.append("")
        L.append("Course is NOT set to weight grades by assignment groups (raw points drive "
                 "the final grade), but groups still carry weight values that diverge from "
                 "their actual point share. Either turn on weight-based grading or zero the "
                 "weights out — leaving stale weight values is misleading to faculty + students.")
        L.append("")
        L.append("| Category | Declared weight | Actual % of points | Delta |")
        L.append("|---|---:|---:|---:|")
        for w in res["weight_mismatches"]:
            L.append(f"| {w['category']} | {w['declared_weight']:.1f}% | "
                     f"{w['actual_pct_of_total']:.1f}% | {w['delta']:+.1f}% |")
        L.append("")

    # Flag 3: OVER_INFLUENCE
    if res["over_influence"]:
        L.append(f"## ⚠ OVER_INFLUENCE — single assignment ≥ {thr['over_influence_pct']:.0f}% of final grade")
        L.append("")
        L.append("Over-influential assignments amplify the consequence of one bad day. "
                 "Consider splitting into 2-3 smaller checkpoints OR adding a make-up path.")
        L.append("")
        L.append("| Assignment | Category | Points | % of grade |")
        L.append("|---|---|---:|---:|")
        for a in sorted(res["over_influence"], key=lambda x: -x["pct_of_final_grade"]):
            L.append(f"| {a['name']} | {a['category']} | "
                     f"{a['points_possible']:.0f} | **{a['pct_of_final_grade']:.1f}%** |")
        L.append("")

    # Flag 4: TOO_SMALL
    if res["too_small"]:
        L.append(f"## ⚠ TOO_SMALL — single assignment < {thr['too_small_pct']:.1f}% of final grade")
        L.append("")
        L.append("Below the threshold, the assignment doesn't materially affect a student's "
                 "grade. Either raise its weight, combine it with siblings, or convert it to "
                 "ungraded practice. Many small assignments = grading-load burden without "
                 "proportional learning signal.")
        L.append("")
        L.append("| Assignment | Category | Points | % of grade |")
        L.append("|---|---|---:|---:|")
        for a in sorted(res["too_small"], key=lambda x: x["pct_of_final_grade"]):
            L.append(f"| {a['name']} | {a['category']} | "
                     f"{a['points_possible']:.1f} | {a['pct_of_final_grade']:.2f}% |")
        L.append("")
        L.append(f"_Total flagged: {len(res['too_small'])} assignments._")
        L.append("")

    # Flag 5: CATEGORY_CARRY
    if res["category_carry"]:
        L.append(f"## ⚠ CATEGORY_CARRY — single assignment ≥ {thr['category_carry_pct']:.0f}% of its category")
        L.append("")
        L.append("When one assignment carries most of its category, the category structure "
                 "doesn't actually protect students who stumble on it. Consider splitting or "
                 "adding companion assignments within the same category.")
        L.append("")
        L.append("| Assignment | Category | Points | % of category |")
        L.append("|---|---|---:|---:|")
        for a in sorted(res["category_carry"], key=lambda x: -x["pct_of_category"]):
            L.append(f"| {a['name']} | {a['category']} | "
                     f"{a['points_possible']:.0f} | **{a['pct_of_category']:.1f}%** |")
        L.append("")

    # Flag 6: TEMPORAL_STACK
    if res["temporal_stack"]:
        t = res["temporal_stack"]
        if t["flag"]:
            L.append(f"## ⚠ TEMPORAL_STACK — {t['pct_in_last_2_weeks']:.1f}% of points "
                     f"due in the last 2 weeks")
            L.append("")
            L.append("End-loaded grading punishes students who stumble late and disproportionately "
                     "rewards crammers. Consider redistributing major assessments through the term.")
            L.append("")
            L.append(f"- Term window: {t['course_start'][:10]} → {t['course_end'][:10]}")
            L.append(f"- Last 2 weeks: {t['last_2_weeks_start'][:10]} → {t['course_end'][:10]}")
            L.append(f"- Points due in last 2 weeks: **{t['points_last_2_weeks']:.0f}** "
                     f"of **{t['points_dated']:.0f}** dated points "
                     f"({t['pct_in_last_2_weeks']:.1f}%)")
            L.append("")
        else:
            L.append(f"### Temporal distribution")
            L.append("")
            L.append(f"Last 2 weeks of term carry {t['pct_in_last_2_weeks']:.1f}% of dated points "
                     f"(threshold: {thr['temporal_stack_pct']:.0f}%). No flag.")
            L.append("")

    # Audit tag
    L.append("---")
    L.append("")
    L.append("## Audit tag")
    L.append("")
    flags = []
    if res["sum_not_100"] and res["sum_not_100"]["flag"]:
        flags.append("sum_not_100")
    if res["weight_mismatches"]:
        flags.append(f"weight_mismatches={len(res['weight_mismatches'])}")
    if res["over_influence"]:
        flags.append(f"over_influence={len(res['over_influence'])}")
    if res["too_small"]:
        flags.append(f"too_small={len(res['too_small'])}")
    if res["category_carry"]:
        flags.append(f"category_carry={len(res['category_carry'])}")
    if res["temporal_stack"] and res["temporal_stack"]["flag"]:
        flags.append("temporal_stack")
    L.append(f"`grading_structure`: **{res['verdict']}** "
             f"({', '.join(flags) if flags else 'all clear'})")
    return L


def _render_json(res: dict, ts: str) -> dict:
    return {
        "tool": "grading_structure_audit",
        "version": __version__,
        "generated": ts,
        "course_id": res["course_id"],
        "course_name": res["course_name"],
        "verdict": res["verdict"],
        "grading_structure": res["verdict"],
        "summary": {
            "apply_weights": res["apply_weights"],
            "total_points": res["total_points"],
            "published_assignment_count": res["published_assignment_count"],
            "flag_count": res["flag_count"],
        },
        "thresholds": res["thresholds"],
        "categories": res["categories"],
        "flags": {
            "sum_not_100": res["sum_not_100"],
            "weight_mismatches": res["weight_mismatches"],
            "over_influence": res["over_influence"],
            "too_small": res["too_small"],
            "category_carry": res["category_carry"],
            "temporal_stack": res["temporal_stack"],
        },
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
    ap = argparse.ArgumentParser(description="Read-only grading-structure audit (arithmetic only).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--course-id", help="Canvas course id.")
    grp.add_argument("--target", default="CANVAS_COURSE_ID",
                     help="Env var to read the course id from. Default CANVAS_COURSE_ID.")
    ap.add_argument("--report", help=".md path to write the report (with .pdf sibling if Chrome).")
    ap.add_argument("--emit-json", action="store_true",
                    help="Emit JSON to stdout instead of human-readable markdown.")
    ap.add_argument("--over-influence", type=float, default=25.0,
                    help="Single-assignment-as-%%-of-grade threshold. Default 25.0.")
    ap.add_argument("--too-small", type=float, default=1.0,
                    help="Single-assignment-as-%%-of-grade lower bound. Default 1.0.")
    ap.add_argument("--category-carry", type=float, default=60.0,
                    help="Single-assignment-as-%%-of-its-category threshold. Default 60.0.")
    ap.add_argument("--temporal-stack", type=float, default=40.0,
                    help="%%-of-points-due-in-last-2-weeks threshold. Default 40.0.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Bypass canvas_course_guard advisory for enrolled-course reads.")
    args = ap.parse_args()

    if not CANVAS_API_TOKEN:
        print("ERROR: CANVAS_API_TOKEN missing from .env.", file=sys.stderr)
        return 2
    if not CANVAS_BASE_URL:
        print("ERROR: CANVAS_BASE_URL missing from .env.", file=sys.stderr)
        return 2

    course_id = args.course_id or os.environ.get(args.target, "")
    if not course_id:
        print(f"ERROR: course ID not found. Pass --course-id <id> or set "
              f"{args.target} in .env.", file=sys.stderr)
        return 2

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="read", allow_override=args.allow_enrolled, label="audit target")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    course = _get(f"/courses/{course_id}") or {}
    if not isinstance(course, dict):
        print(f"ERROR: couldn't load course {course_id}.", file=sys.stderr)
        return 2

    groups = _get_paged(f"/courses/{course_id}/assignment_groups",
                        params={"include[]": "assignments"})
    if not groups:
        print(f"ERROR: no assignment groups for course {course_id}.", file=sys.stderr)
        return 2

    res = audit_structure(
        course, groups,
        over_influence_pct=args.over_influence,
        too_small_pct=args.too_small,
        category_carry_pct=args.category_carry,
        temporal_stack_pct=args.temporal_stack,
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

    return 0 if res["verdict"] == "no_flags" else 1


if __name__ == "__main__":
    sys.exit(main())

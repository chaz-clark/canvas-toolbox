#!/usr/bin/env python3
"""
formative_variety_audit.py — read-only audit of formative-vs-summative assignment distribution.

Closes BYUI Course Design Standard 3.3 ("A variety of formative, low-stakes, and
self-evaluation activities are used to support outcome achievement.") The standard
demands variety + distribution; this audit checks both, deterministically.

WHAT IT CHECKS

  1. PRESENCE     Are there formative-shaped (low-weight) items at all?
                  A course where every graded item is high-stakes summative is
                  structurally fragile — no in-flight check, no place to fail
                  cheaply.

  2. PER-CATEGORY How many formative-shaped items per assignment-group? A category
                  with ONLY summative items signals there's no practice path
                  toward its outcomes.

  3. PRECEDENCE   Is every high-stakes assessment preceded by formative practice
                  in the same category within the preceding N weeks (default 3)?
                  Practice should precede performance.

  4. DISTRIBUTION Are formative items distributed across the term, or stacked at
                  the start / end? Stacked-at-the-end = post-mortem; stacked-at-
                  the-start = no maintenance.

CLASSIFICATION HEURISTIC (low-stakes vs. high-stakes)

  Each published assignment is classified by its share of the final grade:
    - LOW_WEIGHT   (formative-shaped)   <  --low-weight-pct of grade (default 3%)
    - MEDIUM       (between)            in [low, high)
    - HIGH_WEIGHT  (summative-shaped)   >= --high-weight-pct of grade (default 10%)

  Zero-point assignments are treated as formative (ungraded practice) IF
  workflow_state == published. Surveys + ungraded discussions land here too.

  This is a HEURISTIC — instructor naming intent can override (e.g. a 25%
  midterm called "Practice Midterm" is summative by weight regardless of name).
  The audit reports the weight-based classification + surfaces names so the
  operator can spot-check. NEVER auto-fails on classification.

  COMPANION KNOWLEDGE: assessments_knowledge.md (formative vs. summative
  pedagogy — the source of the seven principles for formative practice).

ENDPOINTS (all GET, read-only):
  GET /courses/:id                                         (course name + dates)
  GET /courses/:id?include[]=total_students                (safety guard, advisory)
  GET /courses/:id/blueprint_subscriptions                 (safety guard, advisory)
  GET /courses/:id/assignment_groups?include[]=assignments (the main data)

EXIT CODES
  0  no flags
  1  at least one flag fired
  2  configuration error

USAGE
  uv run python canvas_toolbox/lib/tools/formative_variety_audit.py --course-id 402262
  uv run python canvas_toolbox/lib/tools/formative_variety_audit.py --target CANVAS_SANDBOX_ID
  uv run python canvas_toolbox/lib/tools/formative_variety_audit.py --course-id 402262 \\
    --low-weight-pct 5 --high-weight-pct 15 --precedence-weeks 2 \\
    --report /tmp/itm327_formative_variety.md

ANCHORS
  - course_design_standards_knowledge.md standard 3.3 (the institutional anchor)
  - assessments_knowledge.md (formative vs summative pedagogy; precedes this audit)
  - hattie_3phase_knowledge.md (Surface → Deep → Transfer; formative anchors Surface)

PAIRS WITH
  - workload_audit.py     (student load — orthogonal concern)
  - grading_structure_audit.py (the weighting math; this tool reads the
                                 weights and infers formative vs summative)
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


def _parse_due_at(due_at: str | None) -> datetime | None:
    if not due_at:
        return None
    try:
        return datetime.fromisoformat(due_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Classification + audit
# ---------------------------------------------------------------------------

def classify_assignments(course: dict, groups: list[dict],
                         low_weight_pct: float, high_weight_pct: float) -> list[dict]:
    """For each published assignment, compute its share of the final grade and tag it."""
    apply_weights = bool(course.get("apply_assignment_group_weights"))
    all_assignments: list[dict] = []
    for g in groups:
        for a in g.get("assignments") or []:
            if a.get("workflow_state") == "published":
                all_assignments.append({**a, "_group_id": g.get("id"), "_group_name": g.get("name", "")})
    total_points = sum(float(a.get("points_possible") or 0) for a in all_assignments) or 1.0

    records = []
    for a in all_assignments:
        pts = float(a.get("points_possible") or 0)
        if apply_weights:
            grp = next((g for g in groups if g.get("id") == a["_group_id"]), {})
            cat_pts = sum(float(x.get("points_possible") or 0) for x in (grp.get("assignments") or [])
                          if x.get("workflow_state") == "published") or 1.0
            grade_pct = (pts / cat_pts) * float(grp.get("group_weight") or 0)
        else:
            grade_pct = (pts / total_points) * 100.0
        # Classification
        if pts == 0:
            tag = "low_weight"  # zero-point = ungraded practice (formative)
        elif grade_pct < low_weight_pct:
            tag = "low_weight"
        elif grade_pct >= high_weight_pct:
            tag = "high_weight"
        else:
            tag = "medium_weight"
        records.append({
            "id": a.get("id"),
            "name": a.get("name", ""),
            "category": a["_group_name"],
            "category_id": a["_group_id"],
            "points_possible": pts,
            "pct_of_grade": grade_pct,
            "weight_tag": tag,
            "due_at": a.get("due_at"),
        })
    return records


def audit_variety(course: dict, records: list[dict],
                  low_weight_pct: float, high_weight_pct: float,
                  precedence_weeks: int) -> dict:
    """Run all four checks against the classified records."""

    # ------ Check 1: PRESENCE (any formative-shaped items at all?) ------
    low_count = sum(1 for r in records if r["weight_tag"] == "low_weight")
    high_count = sum(1 for r in records if r["weight_tag"] == "high_weight")
    medium_count = sum(1 for r in records if r["weight_tag"] == "medium_weight")
    presence_flag = (low_count == 0 and high_count > 0)

    # ------ Check 2: PER-CATEGORY (categories with NO formative items) ------
    cats_by_id: dict = {}
    for r in records:
        cats_by_id.setdefault(r["category_id"], {
            "name": r["category"],
            "low": 0, "medium": 0, "high": 0,
        })
        cats_by_id[r["category_id"]][{
            "low_weight": "low", "medium_weight": "medium", "high_weight": "high"
        }[r["weight_tag"]]] += 1

    summative_only_categories = [
        c for c in cats_by_id.values()
        if c["high"] > 0 and c["low"] == 0
    ]

    # ------ Check 3: PRECEDENCE (every high-stakes preceded by formative in same category) ------
    # Pull due dates; for each high-weight item, check if any low-weight item in the
    # same category is due within the preceding `precedence_weeks` weeks.
    high_assignments = [r for r in records if r["weight_tag"] == "high_weight"]
    no_precedence: list[dict] = []
    for h in high_assignments:
        h_due = _parse_due_at(h["due_at"])
        if not h_due:
            continue  # can't check precedence without a date
        window_start = h_due - timedelta(weeks=precedence_weeks)
        formative_in_window = []
        for r in records:
            if r["weight_tag"] != "low_weight":
                continue
            if r["category_id"] != h["category_id"]:
                continue
            r_due = _parse_due_at(r["due_at"])
            if not r_due:
                continue
            if window_start <= r_due < h_due:
                formative_in_window.append(r)
        if not formative_in_window:
            no_precedence.append({
                "high_assignment": h["name"],
                "high_pct_of_grade": h["pct_of_grade"],
                "category": h["category"],
                "due_at": h["due_at"],
                "window_weeks": precedence_weeks,
            })

    # ------ Check 4: DISTRIBUTION (are formative items distributed across the term?) ------
    course_start = _parse_due_at(course.get("start_at"))
    course_end = _parse_due_at(course.get("end_at"))
    if not (course_start and course_end):
        due_dates = [_parse_due_at(r["due_at"]) for r in records if r["due_at"]]
        due_dates = [d for d in due_dates if d]
        if due_dates:
            course_start = course_start or min(due_dates)
            course_end = course_end or max(due_dates)

    distribution: dict | None = None
    if course_start and course_end:
        term_days = max((course_end - course_start).days, 1)
        first_third_end = course_start + timedelta(days=term_days // 3)
        second_third_end = course_start + timedelta(days=2 * term_days // 3)
        thirds = {"first_third": 0, "second_third": 0, "last_third": 0}
        for r in records:
            if r["weight_tag"] != "low_weight":
                continue
            d = _parse_due_at(r["due_at"])
            if not d:
                continue
            if d < first_third_end:
                thirds["first_third"] += 1
            elif d < second_third_end:
                thirds["second_third"] += 1
            else:
                thirds["last_third"] += 1
        dated_low = sum(thirds.values())
        # Flag: any third has < 15% of the formative items (skewed distribution)
        skewed_thirds = []
        if dated_low > 0:
            for label, count in thirds.items():
                pct = count / dated_low * 100.0
                if pct < 15:
                    skewed_thirds.append({"third": label, "count": count, "pct": pct})
        distribution = {
            "course_start": course_start.isoformat(),
            "course_end": course_end.isoformat(),
            "first_third_end": first_third_end.isoformat(),
            "second_third_end": second_third_end.isoformat(),
            "thirds": thirds,
            "dated_low_count": dated_low,
            "skewed_thirds": skewed_thirds,
            "flag": bool(skewed_thirds and dated_low >= 3),
            # Don't flag distribution if there are <3 formative items total — there's nothing to distribute.
        }

    # Verdict
    flags_count = sum([
        bool(presence_flag),
        bool(summative_only_categories),
        bool(no_precedence),
        bool(distribution and distribution["flag"]),
    ])

    return {
        "course_name": course.get("name", "<unknown>"),
        "course_id": course.get("id"),
        "counts": {
            "low_weight": low_count,
            "medium_weight": medium_count,
            "high_weight": high_count,
            "total_published": len(records),
        },
        "categories": list(cats_by_id.values()),
        "presence_flag": presence_flag,
        "summative_only_categories": summative_only_categories,
        "no_precedence": no_precedence,
        "distribution": distribution,
        "flags_count": flags_count,
        "verdict": "no_flags" if flags_count == 0 else "flags_present",
        "thresholds": {
            "low_weight_pct": low_weight_pct,
            "high_weight_pct": high_weight_pct,
            "precedence_weeks": precedence_weeks,
        },
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_markdown(res: dict, ts: str) -> list[str]:
    L: list[str] = []
    L.append(f"# Formative Variety Audit — {res['course_name']}")
    L.append("")
    L.append(f"**Course ID:** {res['course_id']}")
    L.append(f"**Generated:** {ts}")
    L.append(f"**Tool:** formative_variety_audit.py (canvas-toolbox {__version__})")
    L.append(f"**Standard:** BYUI Course Design Standard 3.3 — "
             f"variety of formative, low-stakes, self-evaluation activities")
    L.append("")
    L.append("**Verdict:** " + ("✅ **no flags**" if res["verdict"] == "no_flags"
                                else f"⚠ **{res['flags_count']} flag(s)**"))
    L.append("")
    L.append("## Counts")
    L.append("")
    c = res["counts"]
    L.append(f"- Published assignments: **{c['total_published']}**")
    L.append(f"- Low-weight (formative-shaped): **{c['low_weight']}**")
    L.append(f"- Medium-weight: **{c['medium_weight']}**")
    L.append(f"- High-weight (summative-shaped): **{c['high_weight']}**")
    L.append("")
    thr = res["thresholds"]
    L.append(f"_Thresholds: low-weight < {thr['low_weight_pct']:.1f}%, high-weight ≥ "
             f"{thr['high_weight_pct']:.1f}%, precedence window {thr['precedence_weeks']} weeks._")
    L.append("")

    # Per-category breakdown
    L.append("## Per-category breakdown")
    L.append("")
    L.append("| Category | Low | Medium | High | Mix |")
    L.append("|---|---:|---:|---:|---|")
    for cat in res["categories"]:
        mix = "—"
        if cat["high"] > 0 and cat["low"] == 0:
            mix = "⚠ summative-only"
        elif cat["low"] > 0 and cat["high"] == 0:
            mix = "formative-only (typical for practice categories)"
        elif cat["low"] > 0 and cat["high"] > 0:
            mix = "balanced"
        L.append(f"| {cat['name']} | {cat['low']} | {cat['medium']} | {cat['high']} | {mix} |")
    L.append("")

    # Flag 1: PRESENCE
    if res["presence_flag"]:
        L.append("## ⛔ PRESENCE — no formative-shaped items in the entire course")
        L.append("")
        L.append("Every graded item is high-stakes (≥ "
                 f"{thr['high_weight_pct']:.0f}% of grade or medium-weight). There's no "
                 "low-stakes path for students to practice, get feedback, and recover "
                 "before high-consequence assessments. This is the most fragile possible "
                 "design — one bad day = unrecoverable.")
        L.append("")
        L.append("**Fix:** add low-weight practice items (quizzes, drafts, peer reviews, "
                 "discussions, self-checks) in each major category. See "
                 "[`assessments_knowledge.md`](../../agents/knowledge/assessments_knowledge.md) "
                 "for the seven principles of formative assessment design.")
        L.append("")

    # Flag 2: SUMMATIVE_ONLY_CATEGORIES
    if res["summative_only_categories"]:
        L.append("## ⚠ SUMMATIVE_ONLY_CATEGORIES — no formative items in some categories")
        L.append("")
        L.append("These categories have at least one high-weight assessment but ZERO "
                 "formative-shaped items. Students have no in-category practice path:")
        L.append("")
        for cat in res["summative_only_categories"]:
            L.append(f"- **{cat['name']}**: {cat['high']} high-weight, {cat['medium']} medium, "
                     "**0** low-weight")
        L.append("")

    # Flag 3: PRECEDENCE
    if res["no_precedence"]:
        L.append(f"## ⚠ PRECEDENCE — high-stakes items without formative practice in the preceding "
                 f"{thr['precedence_weeks']} week(s)")
        L.append("")
        L.append("Each of these high-weight assessments has NO low-weight item in the same "
                 "category within the preceding window. Practice should precede performance.")
        L.append("")
        L.append("| High-stakes assignment | Category | % of grade | Due |")
        L.append("|---|---|---:|---|")
        for h in res["no_precedence"]:
            due_str = h["due_at"][:10] if h.get("due_at") else "(no date)"
            L.append(f"| {h['high_assignment']} | {h['category']} | "
                     f"{h['high_pct_of_grade']:.1f}% | {due_str} |")
        L.append("")

    # Flag 4: DISTRIBUTION
    if res["distribution"] and res["distribution"]["flag"]:
        d = res["distribution"]
        L.append("## ⚠ DISTRIBUTION — formative items are not evenly distributed across the term")
        L.append("")
        L.append(f"Term split into thirds. A third with <15% of formative items signals "
                 f"stacking. (Total dated formative items: **{d['dated_low_count']}**.)")
        L.append("")
        L.append(f"- First third ({d['course_start'][:10]} → {d['first_third_end'][:10]}): "
                 f"**{d['thirds']['first_third']}**")
        L.append(f"- Middle third ({d['first_third_end'][:10]} → {d['second_third_end'][:10]}): "
                 f"**{d['thirds']['second_third']}**")
        L.append(f"- Last third ({d['second_third_end'][:10]} → {d['course_end'][:10]}): "
                 f"**{d['thirds']['last_third']}**")
        L.append("")
        for sk in d["skewed_thirds"]:
            L.append(f"- ⚠ **{sk['third']}** carries only {sk['count']} formative items "
                     f"({sk['pct']:.1f}% of total — below the 15% threshold)")
        L.append("")
    elif res["distribution"]:
        d = res["distribution"]
        L.append("### Distribution across the term")
        L.append("")
        L.append(f"Formative items by term-third: first={d['thirds']['first_third']}, "
                 f"middle={d['thirds']['second_third']}, last={d['thirds']['last_third']}. "
                 "No skew flag.")
        L.append("")

    # Audit tag
    L.append("---")
    L.append("")
    L.append("## Audit tag")
    L.append("")
    tag_flags = []
    if res["presence_flag"]:
        tag_flags.append("no_formative")
    if res["summative_only_categories"]:
        tag_flags.append(f"summative_only_categories={len(res['summative_only_categories'])}")
    if res["no_precedence"]:
        tag_flags.append(f"no_precedence={len(res['no_precedence'])}")
    if res["distribution"] and res["distribution"]["flag"]:
        tag_flags.append("skewed_distribution")
    L.append(f"`formative_variety`: **{res['verdict']}** "
             f"({', '.join(tag_flags) if tag_flags else 'all clear'})")
    return L


def _render_json(res: dict, ts: str) -> dict:
    return {
        "tool": "formative_variety_audit",
        "version": __version__,
        "generated": ts,
        "course_id": res["course_id"],
        "course_name": res["course_name"],
        "standard": "BYUI Course Design Standard 3.3 — variety of formative, low-stakes, self-evaluation activities",
        "verdict": res["verdict"],
        "formative_variety": res["verdict"],
        "thresholds": res["thresholds"],
        "counts": res["counts"],
        "categories": res["categories"],
        "flags": {
            "presence_flag": res["presence_flag"],
            "summative_only_categories": res["summative_only_categories"],
            "no_precedence": res["no_precedence"],
            "distribution": res["distribution"],
        },
        "flags_count": res["flags_count"],
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
        description="Audit formative-vs-summative assignment distribution (BYUI Standard 3.3).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--course-id", help="Canvas course id.")
    grp.add_argument("--target", default="CANVAS_COURSE_ID",
                     help="Env var to read the course id from. Default CANVAS_COURSE_ID.")
    ap.add_argument("--report", help=".md path to write the report (with .pdf sibling if Chrome).")
    ap.add_argument("--emit-json", action="store_true",
                    help="Emit JSON to stdout instead of human-readable markdown.")
    ap.add_argument("--low-weight-pct", type=float, default=3.0,
                    help="An assignment with < this %% of grade is classified low-weight (formative-shaped). Default 3.0.")
    ap.add_argument("--high-weight-pct", type=float, default=10.0,
                    help="An assignment with >= this %% of grade is classified high-weight (summative-shaped). Default 10.0.")
    ap.add_argument("--precedence-weeks", type=int, default=3,
                    help="Number of weeks before a high-weight item to look for formative practice. Default 3.")
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

    records = classify_assignments(course, groups,
                                   low_weight_pct=args.low_weight_pct,
                                   high_weight_pct=args.high_weight_pct)
    res = audit_variety(course, records,
                        low_weight_pct=args.low_weight_pct,
                        high_weight_pct=args.high_weight_pct,
                        precedence_weeks=args.precedence_weeks)

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

#!/usr/bin/env python3
"""
workload_audit.py — read-only student-workload distribution audit.

Where cognitive_load looks at per-task mental load, this looks at the AGGREGATE:
how much gradable work a course asks of students and — most reliably — how it's
DISTRIBUTED across the term. Clustering ("three deliverables in week 7, nothing in
week 8") is a workload defect even when the total is reasonable.

Honest scope (workload_calibration_knowledge.md): the API exposes assignment counts,
points, types, and DUE DATES — so distribution/density is computed confidently.
Reading HOURS are not reliably knowable (readings are links/files), so volume is only
a rough sanity note (assignment count vs a credits-scaled expectation), never a precise
hour budget. Same evidence-based stance as the other audits.

Endpoint (GET, read-only):
  GET /courses/:id/assignments        (due_at, points_possible, submission_types)
  GET /courses/:id                    (name, start_at/end_at for term span)

Verdict `workload` ∈ {balanced, uneven, sparse, unscheduled}.

Exit codes: 0 balanced · 1 uneven/sparse/unscheduled (review) · 2 config / no assignments.

Usage:
  uv run python canvas_toolbox/lib/tools/workload_audit.py --target CANVAS_SANDBOX_ID
  uv run python canvas_toolbox/lib/tools/workload_audit.py --course-id 402262 --credits 3 --detailed
  uv run python canvas_toolbox/lib/tools/workload_audit.py --course-id 402262 --json

Reads: knowledge/workload_calibration_knowledge.md (Carnegie credit-hour norm; the
distribution-vs-volume split; audit signals).
"""

from __future__ import annotations

import argparse
import json
import os
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

# Non-gradable / non-work submission types don't count toward student workload.
_NON_WORK = ({"none"}, {"not_graded"}, set())


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(endpoint: str, params: dict | None = None) -> list | dict | None:
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    results: list = []
    p: dict = {**(params or {}), "per_page": 100}
    while url:
        try:
            resp = requests.get(url, headers=_headers(), params=p, timeout=_TIMEOUT)
        except Exception:
            return results or None
        if resp.status_code >= 400:
            return results or None
        try:
            data = resp.json()
        except Exception:
            return results or None
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url = None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        p = {}
    return results


def _parse_dt(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _is_work(a: dict) -> bool:
    """Counts as student workload: gradable/submittable, not a 0-point non-task."""
    sub = set(a.get("submission_types") or [])
    if sub in _NON_WORK:
        return False
    return True


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def audit_workload(assignments: list[dict], credits: int | None) -> dict:
    work = [a for a in assignments if _is_work(a)]
    n = len(work)
    scheduled = [(a, _parse_dt(a.get("due_at"))) for a in work]
    dated = [(a, d) for a, d in scheduled if d is not None]
    undated = n - len(dated)

    # Week buckets (ISO year-week) from due dates.
    by_week: dict[tuple[int, int], dict] = defaultdict(lambda: {"count": 0, "points": 0.0})
    for a, d in dated:
        key = (d.isocalendar().year, d.isocalendar().week)
        by_week[key]["count"] += 1
        try:
            by_week[key]["points"] += float(a.get("points_possible") or 0)
        except (TypeError, ValueError):
            pass

    weeks_sorted = sorted(by_week)
    week_counts = [by_week[w]["count"] for w in weeks_sorted]
    n_weeks = len(weeks_sorted)
    avg = (sum(week_counts) / n_weeks) if n_weeks else 0
    heaviest = max(week_counts) if week_counts else 0
    heaviest_wk = weeks_sorted[week_counts.index(heaviest)] if week_counts else None

    flags: list[str] = []
    # Distribution (the reliable signal): a week carrying >=2x the average AND >=3 items.
    uneven = bool(n_weeks >= 3 and heaviest >= max(3, 2 * avg))
    if uneven:
        flags.append("uneven_distribution")
    # Front/back-loading: compare first third vs last third of active weeks.
    if n_weeks >= 6:
        third = n_weeks // 3
        front = sum(week_counts[:third])
        back = sum(week_counts[-third:])
        if front >= 2 * max(1, back):
            flags.append("front_loaded")
        elif back >= 2 * max(1, front):
            flags.append("back_loaded")
    # Unscheduled: most work has no due date → distribution unknowable.
    mostly_unscheduled = n > 0 and undated > n / 2
    if mostly_unscheduled:
        flags.append("mostly_unscheduled")
    # Volume sanity (rough, only with --credits). NOT an hour budget.
    volume_note = None
    if credits:
        # crude expectation band: ~1-3 gradable items per credit across a ~14-wk term
        lo, hi = credits * 6, credits * 18
        if n < lo:
            volume_note = f"low ({n} gradable items vs ~{lo}-{hi} typical for {credits} credits)"
            flags.append("low_volume")
        elif n > hi:
            volume_note = f"high ({n} gradable items vs ~{lo}-{hi} typical for {credits} credits)"
            flags.append("high_volume")
        else:
            volume_note = f"in range ({n} items; ~{lo}-{hi} typical for {credits} credits)"

    # Verdict
    if n < 4:
        verdict = "sparse"
    elif mostly_unscheduled:
        verdict = "unscheduled"
    elif uneven or "front_loaded" in flags or "back_loaded" in flags:
        verdict = "uneven"
    else:
        verdict = "balanced"

    return {
        "verdict": verdict,
        "gradable_items": n,
        "scheduled": len(dated),
        "unscheduled": undated,
        "active_weeks": n_weeks,
        "avg_per_week": round(avg, 1),
        "heaviest_week_count": heaviest,
        "heaviest_week": (f"{heaviest_wk[0]}-W{heaviest_wk[1]:02d}" if heaviest_wk else None),
        "flags": flags,
        "volume_note": volume_note,
        "week_distribution": [
            {"week": f"{w[0]}-W{w[1]:02d}", "count": by_week[w]["count"],
             "points": round(by_week[w]["points"], 1)}
            for w in weeks_sorted
        ],
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_GLYPH = {"balanced": "✅", "uneven": "🔴", "sparse": "🟡", "unscheduled": "🟡"}


def _render(course_id: str, course_name: str, r: dict, ts: str, detailed: bool) -> list[str]:
    v = r["verdict"]
    lines = [
        "# Workload Distribution Audit",
        "",
        f"Course:  {course_name} ({course_id})",
        f"Run at:  {ts}",
        "",
        "=" * 62,
        "",
        f"Verdict: {_GLYPH[v]} {v.upper()}",
        f"Gradable items: {r['gradable_items']}  "
        f"({r['scheduled']} scheduled, {r['unscheduled']} without a due date)",
        f"Active weeks: {r['active_weeks']}  ·  avg {r['avg_per_week']} items/week  ·  "
        f"heaviest {r['heaviest_week_count']}"
        + (f" (week {r['heaviest_week']})" if r['heaviest_week'] else ""),
    ]
    if r["volume_note"]:
        lines.append(f"Volume (rough, vs credits): {r['volume_note']}")
    if r["flags"]:
        lines += ["", "Flags: " + ", ".join(r["flags"])]
    lines += ["", "─" * 62,
              "Reliable signal = DISTRIBUTION (clustering/crunch weeks). Reading HOURS",
              "are not measured (readings are links/files the API can't see) — volume is",
              "only a rough sanity note. Add due dates to any unscheduled work to audit it."]
    if detailed and r["week_distribution"]:
        lines += ["", "Per-week distribution:"]
        for w in r["week_distribution"]:
            bar = "█" * min(w["count"], 30)
            lines.append(f"  {w['week']}: {w['count']:2d}  {bar}  ({w['points']} pts)")
    return lines


def _write_report(path: Path, body: str) -> None:
    path.write_text(body + "\n", encoding="utf-8")
    print(f"\nReport written to {path}", file=sys.stderr)


def _resolve_course_id(target_env: str, literal: str | None) -> tuple[str, str]:
    if literal:
        return literal.strip(), f"--course-id {literal}"
    val = os.environ.get(target_env, "").strip()
    return val, f"${target_env}"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Read-only student-workload distribution audit (clustering/density; "
                    "rough volume sanity with --credits).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Env var holding the course ID (repo .env ships CANVAS_SANDBOX_ID)")
    ap.add_argument("--course-id", default=None, help="Literal course ID; overrides --target")
    ap.add_argument("--credits", type=int, default=None,
                    help="Course credit hours — enables a rough volume sanity note")
    ap.add_argument("--detailed", action="store_true", help="Show the per-week distribution bars")
    ap.add_argument("--report", default=None, metavar="PATH", help="Write output to PATH")
    ap.add_argument("--json", action="store_true", dest="emit_json", help="Machine-readable JSON")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="(Read-only; advisory guard. Accepted for symmetry.)")
    args = ap.parse_args()

    if not CANVAS_BASE_URL or CANVAS_BASE_URL == "https://" or not CANVAS_API_TOKEN:
        print("ERROR: set CANVAS_BASE_URL and CANVAS_API_TOKEN in .env.")
        sys.exit(2)
    course_id, source = _resolve_course_id(args.target, args.course_id)
    if not course_id:
        print(f"ERROR: course ID not found via {source}. Pass --course-id <id>.")
        sys.exit(2)

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="read", allow_override=args.allow_enrolled, label="audit target")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    course = _get(f"/courses/{course_id}") or {}
    course_name = (course.get("name") if isinstance(course, dict) else None) or "<unknown course>"
    assignments = _get(f"/courses/{course_id}/assignments")
    if not isinstance(assignments, list) or not assignments:
        print(f"\nNo assignments returned for course {course_id}.", file=sys.stderr)
        sys.exit(2)

    r = audit_workload(assignments, args.credits)

    if args.emit_json:
        payload = {"tool": "workload_audit", "tool_version": __version__, "run_at": ts,
                   "course": {"id": course_id, "name": course_name}, **r}
        out = json.dumps(payload, indent=2, ensure_ascii=False)
        print(out)
        if args.report:
            _write_report(Path(args.report), out)
    else:
        lines = _render(course_id, course_name, r, ts, args.detailed)
        print("\n".join(lines))
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    sys.exit(0 if r["verdict"] == "balanced" else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
rubric_coverage_audit.py — Stage 4 of the rubrics workstream.

READ-ONLY audit: for every assignment in a target Canvas course, classify
whether it carries a rubric, and surface gaps. This is the smallest-useful
deliverable in the rubric audit chain — it does not score rubric *quality*
(that is Stage 5 / rubric_quality_audit.py). It answers a single question:

  "Which graded assignments in this course lack a rubric, and which carry
   one that is decorative (use_rubric_for_grading=false)?"

Classifications per assignment:
  - missing_rubric      — no rubric attached AND points_possible > 0 (gap)
  - decorative_rubric   — rubric attached BUT use_rubric_for_grading=false
                          (canvas_api_lessons_learned.md L9 audit indicator)
  - non_gradable        — no rubric AND points_possible == 0 (informational)
  - lti_external_tool   — submission_types == ['external_tool']; LTI-backed
                          (NewQuiz OR any other external tool — indistinguishable
                          via submission_types); content managed in Canvas UI
                          not REST (L8)
  - non_submittable     — submission_types ∈ {[], ['none'], ['on_paper']}
                          (rubric optional; surfaced for review)
  - has_rubric          — assignment carries a graded rubric (no gap)

Endpoints used (all GET, read-only):
  GET /courses/:id?include[]=total_students    (safety guard, advisory)
  GET /courses/:id/blueprint_subscriptions     (safety guard, advisory)
  GET /courses/:id/assignments
      ?include[]=rubric                        (criteria — L9 workaround,
                                                 student-token-safe)
      &include[]=rubric_settings               (settings incl. use_rubric_for_grading)
      &include[]=submission                    (skipped — not needed here)
  GET /courses/:id/modules?include[]=items     (optional, for module location)

Exit codes:
  0  no missing_rubric findings
  1  at least one missing_rubric (or decorative_rubric) finding
  2  configuration error / cannot run

Usage:
  uv run python canvas_toolbox/lib/tools/rubric_coverage_audit.py
  uv run python canvas_toolbox/lib/tools/rubric_coverage_audit.py --target MASTER_COURSE_ID
  uv run python canvas_toolbox/lib/tools/rubric_coverage_audit.py --course-id 12345
  uv run python canvas_toolbox/lib/tools/rubric_coverage_audit.py --detailed
  uv run python canvas_toolbox/lib/tools/rubric_coverage_audit.py --report rubric_coverage.md

Requires in .env:
  CANVAS_API_TOKEN, CANVAS_BASE_URL, and the env var named by --target
  (default CANVAS_COURSE_ID).

Reads:
  knowledge/canvas_api_knowledge.md (D1 three-resource pattern; U4 include[])
  knowledge/canvas_api_lessons_learned.md (L9 assignment-include workaround;
                                          P-LL4 advisory guard on reads;
                                          P-LL7 pagination)
  knowledge/rubrics_knowledge.md (rubric_quality tag emission for gaps)

Verification note (honest): no live course in this repo. Static + argparse
verification only when developed here. Promotion to v1.0 (and any wiring
into canvas_course_expert) gated on real-course exercise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

import canvas_course_guard as guard
from __toolbox_version__ import __version__

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
# Normalize the base URL: the .env convention is scheme-less (e.g.
# "byui.instructure.com"), but requests needs a scheme. Match canvas_sync.py.
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL  = _raw_url

_TIMEOUT = 30


# ---------------------------------------------------------------------------
# API helpers (style matches blueprint_orphan_pages / canvas_pages)
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(endpoint: str, params: dict | None = None) -> list | dict | None:
    """Paginated GET. Returns list (concatenated pages) or dict (single object)
    or None on any error (HTTP 4xx/5xx OR network exception). Follows Link
    rel="next" per P-LL7 / U1. Network errors degrade silently to None —
    callers are expected to handle the empty-result case (matches the guard's
    'never block on its own failure' discipline)."""
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    results: list = []
    p: dict = {**(params or {}), "per_page": 100}
    while url:
        try:
            resp = requests.get(url, headers=_headers(), params=p, timeout=_TIMEOUT)
        except Exception:
            return None
        if resp.status_code >= 400:
            return None
        try:
            data = resp.json()
        except Exception:
            return None
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


def list_assignments(course_id: str) -> list[dict]:
    """All assignments in course, including rubric criteria + rubric_settings.

    Uses the L9 workaround: GET /assignments?include[]=rubric returns the
    rubric criteria inline and works for student tokens too. include[]=
    rubric_settings adds use_rubric_for_grading + hide_score_total.
    """
    return _get(
        f"/courses/{course_id}/assignments",
        {"include[]": "rubric"},  # type: ignore[arg-type]
    ) or []


def list_assignments_with_settings(course_id: str) -> list[dict]:
    """Same as list_assignments but with rubric_settings include too.
    Canvas's include[] is repeatable; requests' params dict needs a list value
    for repeating a key. Network errors return whatever was collected so far
    (or [] if the first page failed)."""
    url = f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/assignments"
    p = {"include[]": ["rubric", "rubric_settings"], "per_page": 100}
    out: list = []
    while url:
        try:
            resp = requests.get(url, headers=_headers(), params=p, timeout=_TIMEOUT)
        except Exception:
            return out
        if resp.status_code >= 400:
            return out
        try:
            data = resp.json()
        except Exception:
            return out
        if isinstance(data, list):
            out.extend(data)
        else:
            return [data]
        url = None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        p = {}
    return out


def get_module_location_index(course_id: str) -> dict[int, str]:
    """Map content_id -> 'Module Name' for every Page/Assignment/Quiz/Discussion
    module item. Best-effort — returns empty dict on fetch failure (the
    audit still runs, location columns are blank)."""
    out: dict[int, str] = {}
    mods = _get(f"/courses/{course_id}/modules", {"include[]": "items"}) or []
    if not isinstance(mods, list):
        return out
    for m in mods:
        mod_name = (m.get("name") or "").strip() or "<unnamed module>"
        for it in m.get("items") or []:
            cid = it.get("content_id")
            if isinstance(cid, int) and cid > 0:
                # First module wins on duplicate (rare; module items can repeat)
                out.setdefault(cid, mod_name)
    return out


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

# Classification constants
HAS_RUBRIC          = "has_rubric"
DECORATIVE_RUBRIC   = "decorative_rubric"
MISSING_RUBRIC      = "missing_rubric"
NON_GRADABLE        = "non_gradable"
LTI_EXTERNAL_TOOL   = "lti_external_tool"   # was newquiz_externaltool — renamed:
                                            # submission_types can't distinguish a
                                            # NewQuiz from any other LTI tool, so the
                                            # old name overclaimed (ITM327 4d).
NON_SUBMITTABLE     = "non_submittable"

_NON_SUBMITTABLE_SETS = ({"none"}, {"on_paper"}, set())


def classify(assignment: dict) -> str:
    """Return one of the classification constants per the spec at top-of-file."""
    rubric = assignment.get("rubric") or []
    has_criteria = isinstance(rubric, list) and len(rubric) > 0

    # Distinguish "explicitly worth 0 points" (genuinely non-gradable, no rubric
    # expected) from "points_possible is None" (points simply not set — some
    # grading models derive the grade elsewhere). A None-points submittable
    # assignment with no rubric is still a real GAP, not a non-gradable item.
    raw_points = assignment.get("points_possible")
    explicit_zero = False
    if raw_points is not None:
        try:
            explicit_zero = float(raw_points) <= 0
        except (TypeError, ValueError):
            explicit_zero = False

    sub_types = assignment.get("submission_types") or []
    sub_set = set(sub_types)

    if has_criteria:
        # use_rubric_for_grading is documented on the Assignment object when
        # include[]=rubric_settings is requested. May be absent on older
        # Canvas instances or if the include didn't return it; treat missing
        # as None (unknown) — flag only when EXPLICITLY false.
        use_for_grading = assignment.get("use_rubric_for_grading")
        if use_for_grading is False:
            return DECORATIVE_RUBRIC
        return HAS_RUBRIC

    # No rubric attached.
    if sub_set == {"external_tool"}:
        # LTI-backed (NewQuiz OR any other external tool — submission_types
        # can't tell them apart). L8: content managed in Canvas UI, not REST.
        return LTI_EXTERNAL_TOOL

    if sub_set in _NON_SUBMITTABLE_SETS:
        # 'none', 'on_paper', or empty — rubric is optional / instructor-choice
        return NON_SUBMITTABLE

    if explicit_zero:
        # Worth exactly 0 points — no rubric expected.
        return NON_GRADABLE

    # Submittable, has points (or points unset) and no rubric → real gap.
    return MISSING_RUBRIC


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _summary_lines(buckets: dict[str, list[dict]]) -> list[str]:
    total = sum(len(v) for v in buckets.values())
    out = [
        f"Total assignments scanned: {total}",
        "",
        "Classification:",
        f"  has_rubric          : {len(buckets[HAS_RUBRIC]):4d}  ✅ rubric attached and graded",
        f"  decorative_rubric   : {len(buckets[DECORATIVE_RUBRIC]):4d}  ⚠️  rubric attached but use_rubric_for_grading=false (L9 indicator)",
        f"  missing_rubric      : {len(buckets[MISSING_RUBRIC]):4d}  🔴 graded assignment with no rubric (the gap)",
        f"  lti_external_tool   : {len(buckets[LTI_EXTERNAL_TOOL]):4d}  📝 LTI-backed (NewQuiz or other tool); rubric not REST-auditable (L8)",
        f"  non_submittable     : {len(buckets[NON_SUBMITTABLE]):4d}  📝 no submission required (rubric optional)",
        f"  non_gradable        : {len(buckets[NON_GRADABLE]):4d}  📝 zero-point assignment (no rubric expected)",
    ]
    return out


def _bucket_lines(
    title: str, bucket: list[dict], mod_idx: dict[int, str],
    detailed: bool,
) -> list[str]:
    if not bucket:
        return []
    out = ["", f"### {title} ({len(bucket)})"]
    if not detailed:
        for a in bucket[:10]:
            name = a.get("name") or "<untitled>"
            pts = a.get("points_possible")
            out.append(f"  • {name}  ({pts} pts)")
        if len(bucket) > 10:
            out.append(f"  … and {len(bucket) - 10} more (use --detailed to see all)")
        return out
    # detailed: full dump with module location
    for a in bucket:
        name = a.get("name") or "<untitled>"
        pts = a.get("points_possible")
        sub_types = ",".join(a.get("submission_types") or []) or "<none>"
        loc = mod_idx.get(a.get("id"), "<not in any module>")
        out.append(f"  • {name}")
        out.append(f"      id={a.get('id')}  points={pts}  submission_types=[{sub_types}]")
        out.append(f"      module: {loc}")
        rs = a.get("rubric_settings") or {}
        if rs:
            out.append(f"      rubric_settings: id={rs.get('id')}  "
                       f"hide_score_total={rs.get('hide_score_total')}  "
                       f"use_rubric_for_grading={a.get('use_rubric_for_grading')}")
    return out


def _render(
    course_id: str, course_name: str,
    buckets: dict[str, list[dict]], mod_idx: dict[int, str],
    detailed: bool, ts: str,
) -> list[str]:
    lines: list[str] = [
        "# Rubric Coverage Audit",
        "",
        f"Course:   {course_name} ({course_id})",
        f"Run at:   {ts}",
        f"Detailed: {'yes' if detailed else 'no'}",
        "",
        "=" * 62,
        "",
    ]
    lines.extend(_summary_lines(buckets))
    lines.append("")
    lines.append("=" * 62)

    # Show gaps first (loudest)
    lines.extend(_bucket_lines(
        "🔴 missing_rubric — graded assignments with no rubric (FIX THESE)",
        buckets[MISSING_RUBRIC], mod_idx, detailed,
    ))
    lines.extend(_bucket_lines(
        "⚠️  decorative_rubric — rubric attached but not used for grading",
        buckets[DECORATIVE_RUBRIC], mod_idx, detailed,
    ))
    lines.extend(_bucket_lines(
        "📝 lti_external_tool — LTI-backed (NewQuiz or other tool); rubric not REST-auditable",
        buckets[LTI_EXTERNAL_TOOL], mod_idx, detailed,
    ))
    lines.extend(_bucket_lines(
        "📝 non_submittable — no submission required (rubric optional)",
        buckets[NON_SUBMITTABLE], mod_idx, detailed,
    ))
    lines.extend(_bucket_lines(
        "📝 non_gradable — zero-point assignment (no rubric expected)",
        buckets[NON_GRADABLE], mod_idx, detailed,
    ))
    if detailed:
        lines.extend(_bucket_lines(
            "✅ has_rubric — rubric attached and used for grading",
            buckets[HAS_RUBRIC], mod_idx, detailed,
        ))

    return lines


def _render_json(
    course_id: str, course_name: str,
    buckets: dict[str, list[dict]], mod_idx: dict[int, str],
    ts: str,
) -> dict:
    """Machine-readable form of the audit output. Stable schema for piping
    into downstream tools or aggregating across runs/courses."""
    def _slim(a: dict) -> dict:
        return {
            "id": a.get("id"),
            "name": a.get("name") or "<untitled>",
            "points_possible": a.get("points_possible"),
            "submission_types": a.get("submission_types") or [],
            "module_location": mod_idx.get(a.get("id")),
            "use_rubric_for_grading": a.get("use_rubric_for_grading"),
            "rubric_id": (a.get("rubric_settings") or {}).get("id"),
        }
    return {
        "tool": "rubric_coverage_audit",
        "tool_version": __version__,
        "run_at": ts,
        "course": {"id": course_id, "name": course_name},
        "summary": {
            "total": sum(len(v) for v in buckets.values()),
            HAS_RUBRIC:        len(buckets[HAS_RUBRIC]),
            DECORATIVE_RUBRIC: len(buckets[DECORATIVE_RUBRIC]),
            MISSING_RUBRIC:    len(buckets[MISSING_RUBRIC]),
            LTI_EXTERNAL_TOOL: len(buckets[LTI_EXTERNAL_TOOL]),
            NON_SUBMITTABLE:   len(buckets[NON_SUBMITTABLE]),
            NON_GRADABLE:      len(buckets[NON_GRADABLE]),
        },
        "buckets": {k: [_slim(a) for a in v] for k, v in buckets.items()},
    }


def _write_report(path: Path, body: str) -> None:
    path.write_text(body + "\n", encoding="utf-8")
    print(f"\nReport written to {path}", file=sys.stderr)
    # v0.32 — default-on PDF pair when output is markdown (faculty default).
    # Graceful-degrade: if Chrome isn't installed, prints a note and leaves
    # just the .md. Operators can ask the agent to explain the report instead.
    if path.suffix.lower() in (".md", ".markdown"):
        try:
            from _md_to_pdf import render_pair
            render_pair(path)
        except ImportError:
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _resolve_course_id(target_env: str, literal: str | None) -> tuple[str, str]:
    """Return (course_id, source_label) — either the literal --course-id value
    or the env var lookup. Empty course_id signals 'not configured'."""
    if literal:
        return literal.strip(), f"--course-id {literal}"
    val = os.environ.get(target_env, "").strip()
    return val, f"${target_env}"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Read-only Canvas audit: which assignments have rubrics, "
                    "which don't, which are decorative (Stage 4)."
    )
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Name of the env var holding the course ID "
                         "(default: CANVAS_COURSE_ID; also accepts "
                         "MASTER_COURSE_ID, BLUEPRINT_COURSE_ID, S1_COURSE_ID, …)")
    ap.add_argument("--course-id", default=None,
                    help="Literal course ID; overrides --target if set")
    ap.add_argument("--detailed", action="store_true",
                    help="Show every assignment per bucket with module location "
                         "(default: top 10 names per bucket)")
    ap.add_argument("--report", default=None, metavar="PATH",
                    help="Write the audit output to PATH (markdown unless "
                         "--json is also set, in which case JSON)")
    ap.add_argument("--json", action="store_true", dest="emit_json",
                    help="Emit machine-readable JSON to stdout (replaces prose). "
                         "When combined with --report, writes JSON to file.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="(Read-only tool; safety guard is advisory only. "
                         "Flag accepted for symmetry with write tools.)")
    args = ap.parse_args()

    # env check
    missing: list[str] = []
    if not CANVAS_BASE_URL or CANVAS_BASE_URL == "https://":
        missing.append("CANVAS_BASE_URL")
    if not CANVAS_API_TOKEN:
        missing.append("CANVAS_API_TOKEN")
    if missing:
        print("ERROR: Missing required configuration:")
        for m in missing:
            print(f"  {m}")
        print("\nSet these in your .env file.")
        sys.exit(2)

    course_id, source = _resolve_course_id(args.target, args.course_id)
    if not course_id:
        print(f"ERROR: course ID not found via {source}.")
        print("       Set the env var, or pass --course-id <id> directly.")
        sys.exit(2)

    # Advisory safety guard (P-LL4 — read-only mode, never blocks)
    guard.enforce(
        base_url=CANVAS_BASE_URL,
        headers=_headers(),
        course_id=course_id,
        mode="read",
        allow_override=args.allow_enrolled,
        label="audit target",
    )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Fetch course name for the report header
    course_obj = _get(f"/courses/{course_id}") or {}
    course_name = (course_obj.get("name") if isinstance(course_obj, dict)
                   else None) or "<unknown course>"

    # Fetch assignments (with rubric + rubric_settings includes)
    assignments = list_assignments_with_settings(course_id)
    if not assignments:
        # Always to stderr — stdout reserved for the audit payload (prose or JSON)
        print(f"\nNo assignments returned for course {course_id} "
              f"('{course_name}') — or the fetch failed.",
              file=sys.stderr)
        sys.exit(2)

    # Classify
    buckets: dict[str, list[dict]] = {
        HAS_RUBRIC: [], DECORATIVE_RUBRIC: [], MISSING_RUBRIC: [],
        LTI_EXTERNAL_TOOL: [], NON_SUBMITTABLE: [], NON_GRADABLE: [],
    }
    for a in assignments:
        buckets[classify(a)].append(a)

    # Module location index (best-effort). Always fetch for JSON output
    # (downstream consumers may want it); for prose only fetch when --detailed.
    mod_idx = (get_module_location_index(course_id)
               if (args.detailed or args.emit_json) else {})

    if args.emit_json:
        payload = _render_json(course_id, course_name, buckets, mod_idx, ts)
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        print(body)
        if args.report:
            _write_report(Path(args.report), body)
    else:
        lines = _render(course_id, course_name, buckets, mod_idx, args.detailed, ts)
        for line in lines:
            print(line)
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    # Exit code: 1 if any gap (missing or decorative); 0 otherwise
    findings = len(buckets[MISSING_RUBRIC]) + len(buckets[DECORATIVE_RUBRIC])
    sys.exit(1 if findings > 0 else 0)


if __name__ == "__main__":
    main()

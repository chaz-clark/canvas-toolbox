#!/usr/bin/env python3
"""
rubric_quality_audit.py — Stage 5 of the rubrics workstream.

READ-ONLY per-rubric quality audit. Where Stage 4 (rubric_coverage_audit.py)
answered "which assignments have rubrics?", Stage 5 answers "for rubrics
that exist, are they well-formed?"

Scoring framework: the 4-criterion backbone meta-rubric from
`lib/agents/knowledge/rubrics_knowledge.md` (sourced from the
"Rubric for Evaluating a Rubric" PDF):

  Criterion 1 — Criteria Alignment   (rubric criteria trace to CLOs?)
  Criterion 2 — Rating Levels        (observable/discriminable, not subjective)
  Criterion 3 — Process-Oriented     (scores process + output, not just output)
  Criterion 4 — Points & Weights     (no point ranges per cell; weights match)

Each criterion fires HEURISTIC flags only — text-based detection has false
positives. Treat output as a starting point for instructor review, NOT an
authoritative judgment. Mirror of the discipline in
`course_quality_check.py --alignment` (heuristic, flag for review).

Tags emitted per rubric (per rubrics_knowledge.md):
  rubric_quality       ∈ {meets_criteria | meets_criteria_unverified |
                          partial | needs_revision | absent}
  rubric_criteria_flags ⊆ {criteria_alignment, rating_levels,
                           process_oriented, points_and_weights}
  criterion_unverified ⊆ {criteria_alignment}  (a check that could NOT run —
                          NOT a failure; currently only Criterion 1 when CLOs
                          are unfetchable)
  rubric_typology      ∈ {analytic | holistic | single_point | developmental | unknown}
  validity_flag        boolean (true ONLY when Criterion 1 explicitly fails —
                          NOT when unverified — BYUI vocabulary)
  reliability_flag     boolean (true when Criterion 2 fails — BYUI vocabulary)

Verdict mapping:
  0 flags + 0 unverified  → meets_criteria
  0 flags + ≥1 unverified → meets_criteria_unverified (passed every check that
                            could run; Criterion 1 skipped for lack of CLOs —
                            exits 0, not flagged as a finding)
  1-2 flags               → partial
  3+ flags                → needs_revision

Exemption rules from rubrics_knowledge.md:
  - rubric_typology=single_point → suppress rating_levels flag (Criterion 2)
  - rubric_typology=developmental → default Criterion 3 to passing

Endpoints used (all GET, read-only):
  GET /courses/:id?include[]=total_students      (safety guard, advisory)
  GET /courses/:id/blueprint_subscriptions       (safety guard, advisory)
  GET /courses/:id/assignments
       ?include[]=rubric&include[]=rubric_settings
                                                 (criteria + use_rubric_for_grading)
  GET /courses/:id?include[]=syllabus_body       (optional, for CLO extraction)

Exit codes:
  0  all rubrics meet_criteria (or no rubrics present)
  1  at least one rubric is partial or needs_revision
  2  configuration error / cannot run

Usage:
  uv run python canvas_toolbox/lib/tools/rubric_quality_audit.py
  uv run python canvas_toolbox/lib/tools/rubric_quality_audit.py --target MASTER_COURSE_ID
  uv run python canvas_toolbox/lib/tools/rubric_quality_audit.py --course-id 12345
  uv run python canvas_toolbox/lib/tools/rubric_quality_audit.py --detailed
  uv run python canvas_toolbox/lib/tools/rubric_quality_audit.py --report rubric_quality.md

Requires in .env:
  CANVAS_API_TOKEN, CANVAS_BASE_URL, and the env var named by --target.

Reads (knowledge files informing the heuristics):
  knowledge/rubrics_knowledge.md (4-criterion backbone; typology;
                                   single-point/developmental exemptions)
  knowledge/canvas_api_knowledge.md (D1 three-resource pattern; U4 include[])
  knowledge/canvas_api_lessons_learned.md (L9 student-token workaround;
                                          P-LL4 advisory guard; P-LL7 pagination)

Verification limit (honest): no live course in this repo. Static + argparse
+ classifier unit tests only. Heuristics are calibrated against the corpus
in lib/agents/pre_knowledge/rubrics/ but have not been exercised against
real Canvas rubrics. Promotion to v1.0 and any wiring into
canvas_course_expert is gated on real-course exercise.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

import canvas_course_guard as guard
from __toolbox_version__ import __version__

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
CANVAS_BASE_URL  = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")

_TIMEOUT = 30


# ---------------------------------------------------------------------------
# API helpers (style matches rubric_coverage_audit / blueprint_orphan_pages)
# ---------------------------------------------------------------------------

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


def list_assignments_with_rubrics(course_id: str) -> list[dict]:
    """Assignments with rubric + rubric_settings inline. Repeats the
    include[] key (requests' list-value pattern). Network errors return what
    was collected so far."""
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


# ---------------------------------------------------------------------------
# Heuristic detectors (P-LL5 spirit: every flag is reviewable)
# ---------------------------------------------------------------------------

# Criterion 2 — subjective rating-level language.
# Words/phrases that mark a rating descriptor as subjective/non-observable.
_SUBJECTIVE_TERMS = [
    r"\bgood\b", r"\bfair\b", r"\bpoor\b", r"\bexcellent\b",
    r"\baverage\b", r"\babove average\b", r"\bbelow average\b",
    r"\bsatisfactory\b", r"\bunsatisfactory\b",
    r"\bshows good\b", r"\bshows strong\b", r"\bshows understanding\b",
    r"\bdemonstrates good\b", r"\bdemonstrates strong\b",
    r"\bmostly\b", r"\bsomewhat\b", r"\bpartially\b",
    r"\bminor errors?\b", r"\bfew errors?\b", r"\bseveral errors?\b", r"\bmany errors?\b",
    r"\b(very|quite|rather)\s+(good|strong|weak|poor|clear)\b",
    r"\beffort\b",  # "shows effort" is the canonical subjective
]
_SUBJECTIVE_RE = re.compile("|".join(_SUBJECTIVE_TERMS), re.IGNORECASE)

# Criterion 3 — output-only signals on criterion descriptions.
# Hits suggest the criterion measures completion/format, not learning process.
_OUTPUT_ONLY_TERMS = [
    r"\bsubmitted\b", r"\bsubmission\b",
    r"\bcompleted? (the )?(assignment|task)\b",
    r"\bon time\b", r"\bturn(ed)? in\b",
    r"\bmla\b", r"\bapa\b", r"\bchicago style\b",
    r"\bcorrect format\b", r"\bproper format\b",
    r"\bword count\b", r"\bpage count\b",
    r"\bspelling and grammar\b",  # boundary — could be either
]
_OUTPUT_ONLY_RE = re.compile("|".join(_OUTPUT_ONLY_TERMS), re.IGNORECASE)

# Process-positive signals (the opposite — presence indicates process scoring).
_PROCESS_TERMS = [
    r"\breflect(s|ion|ions|ing)?\b",
    r"\bdraft(s|ing)?\b", r"\brevisions?\b", r"\biteration(s)?\b",
    r"\breasoning\b", r"\bthinking\b", r"\bmetacognit",
    r"\bself[- ]assess",
    r"\bexplain(s|ed|ing|ation)?\b",
    r"\bjustify\b|\bjustifies\b|\bjustification\b",
    r"\bprocess\b",
]
_PROCESS_RE = re.compile("|".join(_PROCESS_TERMS), re.IGNORECASE)

# Accountability-criterion signals — descriptions that mark a criterion as
# accountability (format/on-time/length) rather than content/learning.
# Used for Criterion 4 (weighted equal-or-more than content criteria = flag).
_ACCOUNTABILITY_TERMS = [
    r"\bon time\b", r"\bdeadline\b", r"\blate submission\b",
    r"\bword count\b", r"\bpage count\b", r"\blength\b",
    r"\bformat(ting)?\b", r"\bmla\b", r"\bapa\b",
    r"\bname on (the )?paper\b",
    r"\bfile (type|format|name)\b",
]
_ACCOUNTABILITY_RE = re.compile("|".join(_ACCOUNTABILITY_TERMS), re.IGNORECASE)


def _criterion_text(c: dict) -> str:
    """Concatenated description + long_description (the cell text the auditor
    reads). Lower-cased only inside the regex paths (regex flags handle it)."""
    return f"{c.get('description') or ''}  {c.get('long_description') or ''}".strip()


def _rating_text(r: dict) -> str:
    return f"{r.get('description') or ''}  {r.get('long_description') or ''}".strip()


def classify_typology(rubric: list[dict]) -> str:
    """Heuristic typology classifier per rubrics_knowledge.md typology comparison.
    Returns one of: analytic | holistic | single_point | developmental | unknown.

    Heuristics:
      - 0 criteria: unknown
      - All criteria have exactly 1 rating: single_point (target-only form)
      - All criteria have exactly 3 ratings AND descriptions mention
        'concerns'/'advanced' (or rating[0] description != 'F'/'1'/etc):
        single_point (Gonzalez 2017 three-column variation, heuristic)
      - Rating descriptions are process-skill-style (start with verb phrases
        like 'integrates...', 'evaluates...') AND no level numbering:
        developmental (heuristic — false-positives expected)
      - Otherwise (multi-criterion, multi-rating with level structure):
        analytic
      - Single criterion with multiple ratings: holistic (rare in Canvas)
    """
    if not rubric:
        return "unknown"

    rating_counts = [len(c.get("ratings") or []) for c in rubric]
    if all(rc == 1 for rc in rating_counts):
        return "single_point"

    # Three-column single-point heuristic
    if all(rc == 3 for rc in rating_counts):
        # Look for the Gonzalez-2017 column labels somewhere across criteria
        all_rating_text = " ".join(
            _rating_text(r).lower()
            for c in rubric for r in (c.get("ratings") or [])
        )
        if ("concern" in all_rating_text or "advanced" in all_rating_text) \
                and "expectation" in all_rating_text:
            return "single_point"

    if len(rubric) == 1 and rating_counts[0] >= 3:
        return "holistic"

    # Default to analytic — the dominant Canvas form
    return "analytic"


def score_criterion_1_alignment(
    rubric: list[dict], course_outcomes: list[str],
) -> tuple[bool | None, list[str]]:
    """Criterion 1 — do rubric criteria trace to CLOs?

    Heuristic: tokenize each criterion's description + long_description;
    tokenize each course outcome. A criterion 'aligns' if it shares >= 2
    non-stopword tokens with at least one outcome.

    Returns a THREE-state status:
      True  — all criteria match at least one CLO (heuristic pass)
      False — at least one orphan criterion (heuristic fail)
      None  — course outcomes could not be fetched; Criterion 1 is UNVERIFIED
              (NOT a failure — the caller routes None into criterion_unverified,
              never into rubric_criteria_flags, and does not raise validity_flag)
    """
    if not course_outcomes:
        return None, ["course outcomes not available — Criterion 1 UNVERIFIED "
                      "(not a failure; CLOs unfetchable via Outcomes API + "
                      "syllabus extraction)"]

    notes: list[str] = []
    stop = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "or",
            "is", "are", "with", "by", "from", "as", "at", "that", "this",
            "be", "will", "have", "has", "their", "its", "it", "they"}

    def tokens(s: str) -> set[str]:
        return {t for t in re.findall(r"[a-z]+", s.lower()) if len(t) >= 4 and t not in stop}

    outcome_tokens = [tokens(o) for o in course_outcomes]
    orphan_criteria: list[str] = []
    for c in rubric:
        ctoks = tokens(_criterion_text(c))
        if not ctoks:
            orphan_criteria.append(c.get("description") or "<unnamed>")
            continue
        if not any(len(ctoks & o) >= 2 for o in outcome_tokens):
            orphan_criteria.append(c.get("description") or "<unnamed>")

    if orphan_criteria:
        notes.append(
            f"{len(orphan_criteria)} of {len(rubric)} criteria do not "
            f"match any CLO (heuristic token overlap): "
            + ", ".join(repr(c) for c in orphan_criteria[:3])
            + (" …" if len(orphan_criteria) > 3 else "")
        )
        return False, notes
    return True, [f"all {len(rubric)} criteria match at least one CLO (heuristic)"]


def score_criterion_2_rating_levels(rubric: list[dict]) -> tuple[bool, list[str]]:
    """Criterion 2 — observable/discriminable rating-level language?

    Heuristic: scan every rating's description+long_description for
    subjective terms. If any criterion has any rating with subjective
    language, fail.
    """
    notes: list[str] = []
    flagged_by_criterion: dict[str, list[str]] = {}
    for c in rubric:
        cname = c.get("description") or "<unnamed>"
        for r in c.get("ratings") or []:
            text = _rating_text(r)
            if _SUBJECTIVE_RE.search(text):
                # Capture a short excerpt around the match
                m = _SUBJECTIVE_RE.search(text)
                start = max(0, m.start() - 15) if m else 0
                end = min(len(text), m.end() + 15) if m else 60
                snippet = text[start:end].strip()
                flagged_by_criterion.setdefault(cname, []).append(snippet)
    if flagged_by_criterion:
        notes.append(
            f"{len(flagged_by_criterion)} criteria have rating-level "
            "language flagged as subjective:"
        )
        for cname, snippets in list(flagged_by_criterion.items())[:5]:
            notes.append(f"  • {cname}: '{snippets[0]}'")
        if len(flagged_by_criterion) > 5:
            notes.append(f"  • … and {len(flagged_by_criterion) - 5} more criteria flagged")
        return False, notes
    return True, ["no subjective rating-level language detected (heuristic)"]


def score_criterion_3_process_oriented(rubric: list[dict]) -> tuple[bool, list[str]]:
    """Criterion 3 — does the rubric score process + output, not just output?

    Heuristic: scan every criterion description for process-positive vs.
    output-only signals. If ZERO criteria have process signals AND at least
    one criterion has output-only signals, fail. Otherwise pass.
    """
    process_hits = 0
    output_only_hits = 0
    for c in rubric:
        text = _criterion_text(c)
        if _PROCESS_RE.search(text):
            process_hits += 1
        if _OUTPUT_ONLY_RE.search(text):
            output_only_hits += 1

    if process_hits == 0 and output_only_hits > 0:
        return False, [
            f"{output_only_hits} of {len(rubric)} criteria signal output-only "
            "scoring; 0 signal process. Backbone Criterion 3 likely fails."
        ]
    if process_hits == 0:
        return False, [
            "no process-positive language detected in any criterion. "
            "Backbone Criterion 3 likely fails (heuristic — may be a "
            "legitimate output-only assessment)."
        ]
    return True, [
        f"{process_hits} of {len(rubric)} criteria contain process-positive "
        "language (heuristic — reflection, draft, reasoning, etc.)"
    ]


def score_criterion_4_points_weights(rubric: list[dict]) -> tuple[bool, list[str]]:
    """Criterion 4 — point ranges per cell? Accountability-criterion weighting?

    Two heuristics:
      (a) `criterion_use_range == true` on any criterion → direct API signal
          per rubrics_knowledge.md v0.2 api_signal_criterion_use_range.
      (b) Any criterion's description matches accountability terms (on-time,
          format, length, name-on-paper) AND its points are >= the median
          content-criterion points → flag as weighting violation.
    """
    notes: list[str] = []
    failed = False

    range_hits = [c for c in rubric if c.get("criterion_use_range") is True]
    if range_hits:
        notes.append(
            f"{len(range_hits)} criteria have criterion_use_range=true "
            "(point ranges per cell — backbone Criterion 4 anti-pattern). "
            "API-grounded signal."
        )
        failed = True

    accountability_criteria = []
    content_points: list[float] = []
    for c in rubric:
        text = _criterion_text(c)
        pts = c.get("points")
        try:
            pts_f = float(pts) if pts is not None else 0.0
        except (TypeError, ValueError):
            pts_f = 0.0
        if _ACCOUNTABILITY_RE.search(text):
            accountability_criteria.append((c.get("description") or "<unnamed>", pts_f))
        else:
            content_points.append(pts_f)

    if accountability_criteria and content_points:
        # median content points
        content_sorted = sorted(content_points)
        mid = len(content_sorted) // 2
        if len(content_sorted) % 2 == 1:
            median = content_sorted[mid]
        else:
            median = (content_sorted[mid - 1] + content_sorted[mid]) / 2.0
        for cname, cpts in accountability_criteria:
            if cpts >= median and median > 0:
                notes.append(
                    f"  • accountability criterion '{cname}' is weighted "
                    f"{cpts:g} pts (median content criterion: {median:g} pts)"
                )
                failed = True

    if not failed:
        notes.append("no point ranges; accountability criteria are weighted "
                     "below median content criterion (or none present)")
        return True, notes
    return False, notes


# ---------------------------------------------------------------------------
# Overall rubric scoring
# ---------------------------------------------------------------------------

def score_rubric(
    rubric: list[dict], typology: str, course_outcomes: list[str],
) -> dict:
    """Run all 4 backbone criteria + apply exemption rules. Returns a verdict
    dict with rubric_quality tag, rubric_criteria_flags list, and per-criterion
    pass/fail + notes."""
    if not rubric:
        return {
            "rubric_quality": "absent",
            "rubric_criteria_flags": [],
            "criterion_unverified": [],
            "validity_flag": False,
            "reliability_flag": False,
            "per_criterion": {},
        }

    c1_pass, c1_notes = score_criterion_1_alignment(rubric, course_outcomes)

    # Single-point exemption: suppress Criterion 2 flag
    if typology == "single_point":
        c2_pass, c2_notes = True, [
            "Criterion 2 (rating_levels) exempted — single-point rubric "
            "has no per-level descriptors to evaluate (rubrics_knowledge "
            "exemption rule)."
        ]
    else:
        c2_pass, c2_notes = score_criterion_2_rating_levels(rubric)

    # Developmental exemption: default Criterion 3 to passing
    if typology == "developmental":
        c3_pass, c3_notes = True, [
            "Criterion 3 (process_oriented) default-passed — developmental "
            "rubric is process-oriented by design (rubrics_knowledge exemption "
            "rule)."
        ]
    else:
        c3_pass, c3_notes = score_criterion_3_process_oriented(rubric)

    c4_pass, c4_notes = score_criterion_4_points_weights(rubric)

    # c1_pass is THREE-state (True / False / None). c2/c3/c4 are two-state.
    # None means "unverified" — routes to criterion_unverified, NOT to flags,
    # and does NOT raise validity_flag (you can't fail a check you didn't run).
    flags: list[str] = []
    unverified: list[str] = []
    if c1_pass is None:
        unverified.append("criteria_alignment")
    elif c1_pass is False:
        flags.append("criteria_alignment")
    if not c2_pass: flags.append("rating_levels")
    if not c3_pass: flags.append("process_oriented")
    if not c4_pass: flags.append("points_and_weights")

    if not flags and not unverified:
        verdict = "meets_criteria"
    elif not flags and unverified:
        verdict = "meets_criteria_unverified"
    elif len(flags) >= 3:
        verdict = "needs_revision"
    else:
        verdict = "partial"

    return {
        "rubric_quality": verdict,
        "rubric_criteria_flags": flags,
        "criterion_unverified": unverified,
        "validity_flag": (c1_pass is False),  # BYUI vocab — only when EXPLICITLY failed
        "reliability_flag": (not c2_pass),    # BYUI vocabulary
        "per_criterion": {
            "criteria_alignment":  {"pass": c1_pass, "notes": c1_notes},
            "rating_levels":       {"pass": c2_pass, "notes": c2_notes},
            "process_oriented":    {"pass": c3_pass, "notes": c3_notes},
            "points_and_weights":  {"pass": c4_pass, "notes": c4_notes},
        },
    }


# ---------------------------------------------------------------------------
# Course-outcomes extraction (best-effort; same approach as
# course_quality_check.py --alignment but lighter)
# ---------------------------------------------------------------------------

_OUTCOME_LINE_RE = re.compile(r"(?:•|<li>|-|\d+\.|\*)\s*(.{20,400})", re.IGNORECASE)


def fetch_course_outcomes(course_id: str) -> list[str]:
    """Best-effort: try the Outcomes endpoint first; fall back to extracting
    bullet-list lines from the syllabus body. Empty list if neither yields
    anything (Criterion 1 then runs as 'unverified' rather than false-flagging).
    """
    out: list[str] = []

    # Try Outcomes endpoint
    outcomes = _get(f"/courses/{course_id}/outcomes")
    if isinstance(outcomes, list):
        for o in outcomes:
            txt = (o.get("title") or "") + "  " + (o.get("description") or "")
            txt = re.sub(r"<[^>]+>", " ", txt).strip()
            if len(txt) >= 20:
                out.append(txt)

    if out:
        return out

    # Fall back to syllabus extraction
    course = _get(f"/courses/{course_id}", {"include[]": "syllabus_body"})
    if isinstance(course, dict):
        syll = course.get("syllabus_body") or ""
        # Strip HTML tags
        plain = re.sub(r"<[^>]+>", "\n", syll)
        for line in plain.splitlines():
            m = _OUTCOME_LINE_RE.search(line.strip())
            if m:
                out.append(m.group(1).strip())

    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _verdict_emoji(verdict: str) -> str:
    return {
        "meets_criteria": "✅",
        "meets_criteria_unverified": "✅",
        "partial": "⚠️",
        "needs_revision": "🔴",
        "absent": "⭕",
    }.get(verdict, "?")


def _render(
    course_id: str, course_name: str,
    findings: list[dict],
    n_outcomes: int,
    detailed: bool, ts: str,
) -> list[str]:
    lines: list[str] = [
        "# Rubric Quality Audit (per-rubric backbone meta-rubric scoring)",
        "",
        f"Course:           {course_name} ({course_id})",
        f"Run at:           {ts}",
        f"CLOs available:   {n_outcomes} (Criterion 1 runs in heuristic mode)" if n_outcomes
        else f"CLOs available:   none found — Criterion 1 will be UNVERIFIED",
        f"Detailed mode:    {'yes' if detailed else 'no'}",
        "",
        "Heuristic flag: every finding is reviewable — text-based detection",
        "has false positives. Treat output as a starting point.",
        "",
        "=" * 62,
        "",
    ]
    # Summary
    by_verdict: dict[str, list[dict]] = {
        "meets_criteria": [], "meets_criteria_unverified": [], "partial": [],
        "needs_revision": [], "absent": [],
    }
    for f in findings:
        v = f["verdict"]["rubric_quality"]
        by_verdict.setdefault(v, []).append(f)

    total = len(findings)
    lines.append(f"Total rubric-carrying assignments scanned: {total}")
    lines.append("")
    lines.append("Verdict distribution:")
    lines.append(f"  ✅ meets_criteria             : {len(by_verdict['meets_criteria']):4d}")
    lines.append(f"  ✅ meets_criteria_unverified  : {len(by_verdict['meets_criteria_unverified']):4d}  (passed all run checks; Criterion 1 could not run — no CLOs)")
    lines.append(f"  ⚠️  partial                   : {len(by_verdict['partial']):4d}")
    lines.append(f"  🔴 needs_revision            : {len(by_verdict['needs_revision']):4d}")
    if by_verdict["absent"]:
        lines.append(f"  ⭕ absent (no criteria — should not be here): {len(by_verdict['absent'])}")
    lines.append("")
    lines.append("=" * 62)

    # Per-assignment details, ordered by verdict (loudest first)
    for verdict_key in ("needs_revision", "partial", "meets_criteria_unverified",
                        "meets_criteria", "absent"):
        bucket = by_verdict[verdict_key]
        if not bucket:
            continue
        lines.append("")
        lines.append(f"### {_verdict_emoji(verdict_key)} {verdict_key} ({len(bucket)})")
        for f in bucket:
            v = f["verdict"]
            lines.append("")
            lines.append(f"  {_verdict_emoji(verdict_key)} {f['assignment_name']}  "
                         f"[{v['rubric_quality']}]")
            lines.append(f"      assignment_id={f['assignment_id']}  "
                         f"typology={f['typology']}  criteria={f['criteria_count']}")
            if v["rubric_criteria_flags"]:
                lines.append(f"      flags: {', '.join(v['rubric_criteria_flags'])}")
            if v.get("criterion_unverified"):
                lines.append(f"      unverified (could not run): {', '.join(v['criterion_unverified'])}")
            if v["validity_flag"]:
                lines.append("      validity_flag: TRUE (Criterion 1 failed — BYUI vocabulary)")
            if v["reliability_flag"]:
                lines.append("      reliability_flag: TRUE (Criterion 2 failed — BYUI vocabulary)")
            if detailed:
                for crit, result in v["per_criterion"].items():
                    sym = "✓" if result["pass"] else "✗"
                    lines.append(f"      {sym} Criterion {crit}:")
                    for n in result["notes"]:
                        lines.append(f"          {n}")

    return lines


def _render_json(
    course_id: str, course_name: str,
    findings: list[dict],
    n_outcomes: int,
    ts: str,
) -> dict:
    """Machine-readable form of the audit output. Stable schema for piping
    downstream or aggregating across runs/courses."""
    summary: dict[str, int] = {
        "total_rubrics_scored": len(findings),
        "meets_criteria": 0,
        "meets_criteria_unverified": 0,
        "partial": 0,
        "needs_revision": 0,
        "absent": 0,
    }
    for f in findings:
        summary[f["verdict"]["rubric_quality"]] = (
            summary.get(f["verdict"]["rubric_quality"], 0) + 1
        )
    return {
        "tool": "rubric_quality_audit",
        "tool_version": __version__,
        "run_at": ts,
        "course": {"id": course_id, "name": course_name},
        "outcomes_available": n_outcomes,
        "criterion_1_mode": "heuristic" if n_outcomes else "unverified_no_outcomes",
        "summary": summary,
        "findings": findings,
    }


def _write_report(path: Path, body: str) -> None:
    path.write_text(body + "\n", encoding="utf-8")
    print(f"\nReport written to {path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _resolve_course_id(target_env: str, literal: str | None) -> tuple[str, str]:
    if literal:
        return literal.strip(), f"--course-id {literal}"
    val = os.environ.get(target_env, "").strip()
    return val, f"${target_env}"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Read-only per-rubric quality audit. Scores each rubric "
                    "against the 4-criterion backbone meta-rubric "
                    "(rubrics_knowledge.md). Stage 5."
    )
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Name of env var holding the course ID (default: CANVAS_COURSE_ID)")
    ap.add_argument("--course-id", default=None,
                    help="Literal course ID; overrides --target if set")
    ap.add_argument("--detailed", action="store_true",
                    help="Show per-criterion pass/fail + notes for every rubric")
    ap.add_argument("--report", default=None, metavar="PATH",
                    help="Write the audit output to PATH (markdown unless "
                         "--json is also set, in which case JSON)")
    ap.add_argument("--json", action="store_true", dest="emit_json",
                    help="Emit machine-readable JSON to stdout (replaces prose). "
                         "When combined with --report, writes JSON to file.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="(Read-only tool; guard is advisory only. Accepted for symmetry.)")
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

    # Advisory safety guard (read-only)
    guard.enforce(
        base_url=CANVAS_BASE_URL,
        headers=_headers(),
        course_id=course_id,
        mode="read",
        allow_override=args.allow_enrolled,
        label="audit target",
    )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Course meta
    course_obj = _get(f"/courses/{course_id}") or {}
    course_name = (course_obj.get("name") if isinstance(course_obj, dict)
                   else None) or "<unknown course>"

    # Outcomes (best-effort; empty list means Criterion 1 stays unverified)
    outcomes = fetch_course_outcomes(course_id)

    # Assignments + rubrics
    assignments = list_assignments_with_rubrics(course_id)
    if not assignments:
        # stderr — stdout reserved for the audit payload (prose or JSON)
        print(f"\nNo assignments returned for course {course_id} "
              f"('{course_name}') — or the fetch failed.",
              file=sys.stderr)
        sys.exit(2)

    # Score every assignment that carries a non-empty rubric
    findings: list[dict] = []
    for a in assignments:
        rubric = a.get("rubric") or []
        if not isinstance(rubric, list) or not rubric:
            continue
        typology = classify_typology(rubric)
        verdict = score_rubric(rubric, typology, outcomes)
        findings.append({
            "assignment_id": a.get("id"),
            "assignment_name": a.get("name") or "<untitled>",
            "typology": typology,
            "criteria_count": len(rubric),
            "verdict": verdict,
        })

    if not findings:
        if args.emit_json:
            empty_payload = _render_json(course_id, course_name, [], len(outcomes), ts)
            print(json.dumps(empty_payload, indent=2, ensure_ascii=False))
        else:
            print(f"\nNo rubric-carrying assignments found in {course_name} ({course_id}).")
            print("Run rubric_coverage_audit.py to see coverage gaps.")
        sys.exit(0)

    if args.emit_json:
        payload = _render_json(course_id, course_name, findings, len(outcomes), ts)
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        print(body)
        if args.report:
            _write_report(Path(args.report), body)
    else:
        lines = _render(course_id, course_name, findings, len(outcomes), args.detailed, ts)
        for line in lines:
            print(line)
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    # Exit code: 1 if any rubric is partial or needs_revision; 0 otherwise
    bad = sum(1 for f in findings
              if f["verdict"]["rubric_quality"] in ("partial", "needs_revision"))
    sys.exit(1 if bad > 0 else 0)


if __name__ == "__main__":
    main()

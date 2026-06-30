#!/usr/bin/env python3
"""
clo_quality_audit.py — read-only Course Learning Outcome (CLO) quality audit.

The third leg of the audit suite (after rubric_coverage_audit + rubric_quality_audit):
where rubric_quality checks the *rubric* and syllabus_audit checks the *syllabus*,
this checks whether the course's *learning outcomes* are well-formed — BEFORE
anyone audits whether they're aligned. Alignment to a broken outcome is meaningless.

CLO discovery uses the shared path (Canvas Outcomes API first, then the DOM-aware
syllabus parser) — the same fetch_course_outcomes the rubric tools use, so all
tools agree on what the course's CLOs are (#31).

Scoring is the AoL CLO quality rubric (outcomes_quality_knowledge.md). Like
rubric_quality_audit's evidence-based stance, the verdict is driven only by the
machine-checkable criteria; the human-judgment ones are surfaced as review signals,
never auto-failed:

  PER-CLO, machine-checkable (drive the per-CLO verdict):
    - measurable     — has an observable action verb; primary verb is NOT one of
                       the AoL non-observable flags (understand/know/appreciate/…).
    - single_barreled — one goal: not two distinct Bloom-level verbs / "X and Y" goals.
  PER-CLO advisory (reported, does NOT drive the verdict):
    - vague_language — subjective/comparative terms (appropriate/effective/better…).
  COURSE-LEVEL signals (reported; feed the course verdict):
    - scope          — CLO count (3-6 ideal, 3-8 acceptable, else flag).
    - rigor          — Bloom-level spread (all-clustered or all-low → flag for review).
  COURSE-LEVEL review (human judgment — surfaced, never flagged):
    - relevance, recency — does each CLO fit the course / reflect current practice.

Per-CLO verdict: meets_criteria (0 flags) / partial (1) / needs_revision (2).
Course tag `clo_quality` ∈ {meets_criteria, partial, needs_revision, unverified}
(+ clo_criteria_flags). `unverified` = no CLOs discovered (can't audit; not a fail).

Detection is heuristic on outcome text — treat flags as review prompts, not proof
(same posture as rubric_quality Criterion 1).

Endpoints (all GET, read-only, via fetch_course_outcomes):
  GET /courses/:id/outcome_group_links?outcome_style=full   (Canvas Outcomes)
  GET /courses/:id?include[]=syllabus_body                  (syllabus fallback)
  GET /courses/:id                                          (course name)

Exit codes:
  0  meets_criteria
  1  partial / needs_revision
  2  config error / no CLOs discovered (unverified)

Usage:
  uv run python canvas_toolbox/lib/tools/clo_quality_audit.py --target CANVAS_SANDBOX_ID
  uv run python canvas_toolbox/lib/tools/clo_quality_audit.py --course-id 402262 --detailed
  uv run python canvas_toolbox/lib/tools/clo_quality_audit.py --course-id 402262 --json

Reads (knowledge grounding):
  knowledge/outcomes_quality_knowledge.md (the AoL 6-criteria rubric, hierarchy, verbs)
  bloom_verbs.py (shared Bloom verb→level data + non-observable flags)
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
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

import canvas_course_guard as guard
from __toolbox_version__ import __version__
from rubric_quality_audit import fetch_course_outcomes
from bloom_verbs import detect_bloom, all_bloom_levels, leading_nonobservable, BLOOM_RANK

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url
_TIMEOUT = 30

# Subjective / comparative language (AoL "clarity"). Conservative list — kept as
# an ADVISORY signal, not a hard flag, to avoid the over-fire seen with hedge
# words in rubric_quality C2.
_VAGUE_TERMS = [
    "appropriate", "appropriately", "effective", "effectively", "adequate",
    "adequately", "sufficient", "sufficiently", "proper", "properly",
    "reasonable", "reasonably", "better", "improved", "high-quality",
    "good ", "well ", "as needed",
]

# Scope thresholds (AoL): 3-6 ideal, 3-8 acceptable.
_SCOPE_IDEAL = range(3, 7)
_SCOPE_OK = range(3, 9)


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(endpoint: str, params: dict | None = None) -> list | dict | None:
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    try:
        resp = requests.get(url, headers=_headers(), params={**(params or {})}, timeout=_TIMEOUT)
    except Exception:
        return None
    if resp.status_code >= 400:
        return None
    try:
        return resp.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Per-CLO scoring
# ---------------------------------------------------------------------------

def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


_STEM_STRIP = re.compile(
    r"^.*?\b(?:will\s+be\s+able\s+to|will|able\s+to)\b\s*", re.IGNORECASE)
# A leading clause has a SECOND goal only if the conjunction is NOT introducing a
# means clause ("…to produce…"), a relative clause ("…that uses…"), or a gerund
# means ("…using…"). Those carry an incidental verb, not a second learning goal.
_MEANS_GUARD = re.compile(r"\b(to|that|which|using|in\s+order\s+to|so\s+as\s+to)\b",
                          re.IGNORECASE)


def _is_double_barreled(text: str) -> bool:
    """Conservative: flag only when a conjunction DIRECTLY conjoins two distinct
    goal verbs ('Design AND evaluate …'). Requires (a) a Bloom verb in the leading
    region, and (b) an 'and/or' immediately followed by a DISTINCT-level Bloom verb,
    with no intervening means/relative clause. This avoids the false positives:
    'use X to produce Y' (means clause), 'develop an app that uses data' (relative
    clause), and 'programming constructs' (a verb-word used as a NOUN — the noun
    never sits right after 'and <verb>')."""
    t = _STEM_STRIP.sub("", _plain(text)).strip().lower().lstrip("•-–*0123456789.): ")
    clause = re.split(r"[.;]", t, maxsplit=1)[0]
    # Collect verbs in GOAL position: the leading verb + any verb sitting directly
    # after a conjunction (and/or/comma) that is NOT inside a means/relative clause.
    # A noun like "programming constructs" never sits right after "and <word>", and
    # a means verb ("…to produce…") is guarded out — so only real goal verbs land here.
    goal_levels: set[str] = set(all_bloom_levels(" ".join(clause.split()[:3])))
    for m in re.finditer(r"(?:\band\b|\bor\b|,)\s+([a-z]+)", clause):
        if _MEANS_GUARD.search(clause[:m.start()]):
            continue
        goal_levels |= all_bloom_levels(m.group(1))
    return len(goal_levels) >= 2


def score_clo(clo: str) -> dict:
    """Score a single CLO. Returns flags + per-CLO verdict + bloom level.

    Conservative by design (false positives erode trust — the rubric_quality
    calibration lesson). The ONLY hard flag from verb analysis is an explicit
    non-observable primary verb; a verb merely absent from the finite Bloom list
    is NOT flagged (real observable verbs like 'communicate'/'load'/'collaborate'
    aren't penalized). Double-barrel uses the conservative leading-clause rule;
    vague language is advisory."""
    text = _plain(clo)
    hard_flags: list[str] = []
    advisory: list[str] = []

    bloom_level, bloom_rank = detect_bloom(text)

    # measurable — flag ONLY an explicit non-observable primary verb (AoL flag list).
    if leading_nonobservable(text) is not None:
        hard_flags.append("not_measurable")

    # single_barreled — conservative leading-clause conjunction of two goals.
    if _is_double_barreled(text):
        hard_flags.append("double_barreled")

    # vague_language — advisory only (AoL clarity; kept soft to avoid over-fire).
    low = text.lower()
    if any(t in low for t in _VAGUE_TERMS):
        advisory.append("vague_language")
    # no recognized observable verb (and not explicitly non-observable) → advisory
    if bloom_level is None and "not_measurable" not in hard_flags:
        advisory.append("no_recognized_action_verb")

    n = len(hard_flags)
    verdict = "meets_criteria" if n == 0 else ("partial" if n == 1 else "needs_revision")
    return {
        "text": text,
        "bloom_level": bloom_level,
        "bloom_rank": bloom_rank,
        "hard_flags": hard_flags,
        "advisory": advisory,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Course-level audit
# ---------------------------------------------------------------------------

def audit_clos(clos: list[str]) -> dict:
    scored = [score_clo(c) for c in clos]
    n = len(scored)

    course_flags: list[str] = []

    # scope
    if n not in _SCOPE_OK:
        course_flags.append("scope")
    scope_note = ("ideal" if n in _SCOPE_IDEAL
                  else "acceptable" if n in _SCOPE_OK
                  else ("too few (<3)" if n < 3 else "too many (>8)"))

    # rigor — Bloom-level spread across the CLO set
    levels_present = {s["bloom_level"] for s in scored if s["bloom_level"]}
    max_rank = max((s["bloom_rank"] for s in scored), default=0)
    rigor_note = ""
    if n >= 2 and len(levels_present) <= 1:
        course_flags.append("rigor")
        rigor_note = "all CLOs cluster at one Bloom level (no rigor spread)"
    elif max_rank and max_rank <= BLOOM_RANK["understand"]:
        course_flags.append("rigor")
        rigor_note = "all CLOs are low-level (remember/understand only) — no higher-order outcomes"
    else:
        rigor_note = (f"spread across {len(levels_present)} Bloom levels "
                      f"(top: {max((s['bloom_level'] for s in scored if s['bloom_level']), key=lambda l: BLOOM_RANK[l], default='n/a')})")

    # Course verdict (#34). needs_revision is driven ONLY by per-CLO failures —
    # an outcome that is unmeasurable / double-barreled. The course-level signals
    # (scope count, rigor spread) are ADVISORY review prompts, never a red on their
    # own: a course where every CLO passes but has 9 outcomes is "review the count",
    # not "revise". This matches the evidence-based stance of the rest of the suite.
    n_needs = sum(1 for s in scored if s["verdict"] == "needs_revision")
    n_partial = sum(1 for s in scored if s["verdict"] == "partial")
    if n == 0:
        verdict = "unverified"
    elif n_needs > 0 or (n_partial + n_needs) > n / 2:
        verdict = "needs_revision"
    elif n_partial > 0 or course_flags:   # per-CLO partials OR advisory scope/rigor → review
        verdict = "partial"
    else:
        verdict = "meets_criteria"

    return {
        "verdict": verdict,
        "clo_count": n,
        "scope_note": scope_note,
        "rigor_note": rigor_note,
        "course_flags": course_flags,
        "clos": scored,
        "n_needs_revision": n_needs,
        "n_partial": n_partial,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_GLYPH = {"meets_criteria": "✅", "partial": "🟡", "needs_revision": "🔴", "unverified": "⚪"}
_FLAG_HELP = {
    "not_measurable": "no observable action verb (or leads with understand/know/appreciate…)",
    "double_barreled": "two distinct goals in one outcome (split into separate CLOs)",
}


def _render(course_id: str, course_name: str, res: dict, detailed: bool, ts: str) -> list[str]:
    v = res["verdict"]
    lines = [
        "# CLO Quality Audit",
        "",
        f"Course:  {course_name} ({course_id})",
        f"Run at:  {ts}",
        "",
        "=" * 62,
        "",
        f"Verdict: {_GLYPH[v]} {v.upper()}",
        f"CLOs discovered: {res['clo_count']}  (scope: {res['scope_note']})",
    ]
    if v == "unverified":
        lines += ["",
                  "No course outcomes discovered — no Canvas Outcomes and no Learning",
                  "Outcomes section in the syllabus. Define outcomes (or add a syllabus",
                  "Learning Outcomes section), then re-run. Nothing to audit.",
                  "",
                  "Tip: syllabus_audit.py reports whether an outcomes section is present."]
        return lines

    lines.append(f"Rigor: {res['rigor_note']}")
    if res["course_flags"]:
        lines.append(f"Course-level flags: {', '.join(res['course_flags'])}")
    lines.append("")
    lines.append(f"Per-CLO: ✅ {sum(1 for c in res['clos'] if c['verdict']=='meets_criteria')} meet"
                 f"  ·  🟡 {res['n_partial']} partial  ·  🔴 {res['n_needs_revision']} needs revision")
    lines.append("")
    lines.append("Outcomes (heuristic — flags are review prompts, not proof):")
    for i, c in enumerate(res["clos"], 1):
        g = _GLYPH[c["verdict"]]
        lvl = c["bloom_level"] or "no-bloom-verb"
        lines.append(f"  {g} CLO {i} [{lvl}]: {c['text'][:100]}")
        for f in c["hard_flags"]:
            lines.append(f"        🔴 {f} — {_FLAG_HELP.get(f, f)}")
        if detailed:
            for a in c["advisory"]:
                lines.append(f"        · advisory: {a}")
    lines.append("")
    lines.append("─" * 62)
    lines.append("Human-judgment criteria (NOT auto-checked — review yourself):")
    lines.append("  • Relevance — does each CLO logically fit this course?")
    lines.append("  • Recency — do the CLOs reflect current industry/research practice?")
    lines.append("  • Rigor appropriateness — is the Bloom spread right for THIS course level?")
    return lines


def _render_json(course_id: str, course_name: str, res: dict, ts: str) -> dict:
    return {
        "tool": "clo_quality_audit",
        "tool_version": __version__,
        "run_at": ts,
        "course": {"id": course_id, "name": course_name},
        "clo_quality": res["verdict"],
        "clo_count": res["clo_count"],
        "scope_note": res["scope_note"],
        "rigor_note": res["rigor_note"],
        "clo_criteria_flags": res["course_flags"],
        "clos": [
            {"text": c["text"], "bloom_level": c["bloom_level"],
             "verdict": c["verdict"], "flags": c["hard_flags"], "advisory": c["advisory"]}
            for c in res["clos"]
        ],
        "review_signals": ["relevance", "recency", "rigor_appropriateness"],
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
    if literal:
        return literal.strip(), f"--course-id {literal}"
    val = os.environ.get(target_env, "").strip()
    return val, f"${target_env}"


def main() -> None:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Read-only CLO quality audit against the AoL 6-criteria rubric.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Env var holding the course ID (default CANVAS_COURSE_ID; "
                         "repo .env ships CANVAS_SANDBOX_ID)")
    ap.add_argument("--course-id", default=None, help="Literal course ID; overrides --target")
    ap.add_argument("--detailed", action="store_true", help="Show per-CLO advisory notes")
    ap.add_argument("--report", default=None, metavar="PATH", help="Write output to PATH")
    ap.add_argument("--json", action="store_true", dest="emit_json", help="Machine-readable JSON")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="(Read-only; safety guard is advisory. Accepted for symmetry.)")
    args = ap.parse_args()

    missing = []
    if not CANVAS_BASE_URL or CANVAS_BASE_URL == "https://":
        missing.append("CANVAS_BASE_URL")
    if not CANVAS_API_TOKEN:
        missing.append("CANVAS_API_TOKEN")
    if missing:
        print("ERROR: Missing required configuration:")
        for m in missing:
            print(f"  {m}")
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

    clos = fetch_course_outcomes(course_id)
    res = audit_clos(clos)

    if args.emit_json:
        out = json.dumps(_render_json(course_id, course_name, res, ts), indent=2, ensure_ascii=False)
        print(out)
        if args.report:
            _write_report(Path(args.report), out)
    else:
        lines = _render(course_id, course_name, res, args.detailed, ts)
        print("\n".join(lines))
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    sys.exit(0 if res["verdict"] == "meets_criteria"
             else (2 if res["verdict"] == "unverified" else 1))


if __name__ == "__main__":
    main()

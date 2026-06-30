#!/usr/bin/env python3
"""
course_alignment_audit.py — read-only audit of the outcomes ↔ rubric criteria ↔ activity chain.

Closes the open gap surfaced in `course_design_standards_knowledge.md` standard 2.3:
"Outcomes, department-approved key assessments, activities, and instructional
content align." The existing audits cover each link in isolation (clo_quality for
outcomes, rubric_coverage for assignment→rubric, rubric_quality for rubric quality)
but no tool produces the full chain. This is that chain.

ALIGNMENT CHAIN (per BYUI Course Design Standards + backwards_design_knowledge):

  Course Outcome  →  Rubric Criterion  →  Assignment  →  Module Activity
  (the WHAT)         (the MEASURE)        (the EVIDENCE)   (the TEACHING)

A broken link anywhere = a latent alignment gap. Specifically:

  - **Orphan outcome**:   no rubric criterion is linked to it
                           → "the course CLAIMS to teach X but never assesses X"
  - **Orphan criterion**: no `learning_outcome_id` on the criterion
                           → "this assignment measures something not tied to a CLO"
  - **Untaught outcome**: no module overview page mentions the outcome's verbs/nouns
                           → "the course assesses X but doesn't visibly teach X"
                           (soft signal — text-match heuristic; surface as review prompt)

WHAT'S DETERMINISTIC vs. SOFT

  DETERMINISTIC (drives the verdict):
    - outcome→criterion linkage via Canvas's `learning_outcome_id` field on rubric criteria
    - criterion→assignment linkage via the rubric→assignment relationship

  SOFT (advisory, never drives the verdict):
    - module-overview text overlap with outcome verbs/nouns (heuristic; same
      stance as rubric_quality C1 — "not detected ≠ proven absent")

ENDPOINTS (all GET, read-only):
  GET /courses/:id                                        (course name)
  GET /courses/:id?include[]=total_students               (safety guard, advisory)
  GET /courses/:id/blueprint_subscriptions                (safety guard, advisory)
  GET /courses/:id/outcome_group_links?outcome_style=full (CLOs — shared helper)
  GET /courses/:id/assignments
      ?include[]=rubric                                   (criteria w/ learning_outcome_id)
      &include[]=rubric_settings                          (use_rubric_for_grading)
  GET /courses/:id/modules?include[]=items                (module structure)
  GET /courses/:id/pages/:url                             (module overview text)

EXIT CODES
  0  complete (no orphans of either type)
  1  partial (orphan outcomes OR orphan criteria present)
  2  configuration error / no CLOs discovered

USAGE
  uv run python canvas_toolbox/lib/tools/course_alignment_audit.py --course-id 402262
  uv run python canvas_toolbox/lib/tools/course_alignment_audit.py --target CANVAS_SANDBOX_ID --detailed
  uv run python canvas_toolbox/lib/tools/course_alignment_audit.py --course-id 402262 \\
    --report /tmp/itm327_alignment.md

ANCHORS
  - lib/agents/knowledge/course_design_standards_knowledge.md (standard 2.3 — the
    institutional anchor; this tool closes the named OPEN gap)
  - lib/agents/knowledge/backwards_design_knowledge.md (UbD 3-stage — the design
    framework this audit operationalizes)
  - lib/agents/knowledge/outcomes_quality_knowledge.md (outcome well-formedness
    must pass before alignment is meaningful)
  - lib/agents/knowledge/rubrics_knowledge.md (rubric quality framework)

PAIRS WITH
  - clo_quality_audit.py  (outcomes are well-formed — precedes alignment)
  - rubric_coverage_audit.py (every assignment HAS a rubric — precedes alignment)
  - rubric_quality_audit.py (rubrics are well-formed — precedes alignment)
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
    """Single-page GET helper. Returns JSON body or None on error."""
    url = f"{CANVAS_BASE_URL}/api/v1{path}"
    try:
        r = requests.get(url, headers=_headers(), params=params or {}, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"WARN: GET {path} failed ({type(e).__name__}): {e}", file=sys.stderr)
        return None


def _get_paged(path: str, params: dict | None = None) -> list:
    """Paged GET — follows Link rel=next per Canvas API. Returns concatenated list."""
    out: list = []
    url = f"{CANVAS_BASE_URL}/api/v1{path}"
    base_params = {**(params or {}), "per_page": 100}
    while url:
        try:
            r = requests.get(url, headers=_headers(), params=base_params if "?" not in url else None,
                             timeout=_TIMEOUT)
            r.raise_for_status()
            page = r.json()
            if isinstance(page, list):
                out.extend(page)
            else:
                return [page]
            # parse next link
            link_hdr = r.headers.get("Link", "")
            m = re.search(r'<([^>]+)>;\s*rel="next"', link_hdr)
            url = m.group(1) if m else None
            base_params = None
        except Exception as e:
            print(f"WARN: GET {path} paged failed ({type(e).__name__}): {e}", file=sys.stderr)
            break
    return out


# ---------------------------------------------------------------------------
# Outcome → criterion link extraction (the deterministic backbone)
# ---------------------------------------------------------------------------

def extract_criterion_outcome_id(criterion: dict) -> int | None:
    """Pull the Canvas outcome ID from a rubric criterion, if linked.

    Canvas exposes the outcome link as `learning_outcome_id` on the criterion when
    the criterion is bound to a Learning Outcome (the canonical alignment signal).
    Older API responses may use `outcome_id` — fall back to that.
    """
    for key in ("learning_outcome_id", "outcome_id"):
        v = criterion.get(key)
        if v:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    return None


def pull_assignments_with_rubrics(course_id: str) -> list[dict]:
    """All assignments with their rubric criteria + settings. Read-only."""
    return _get_paged(
        f"/courses/{course_id}/assignments",
        params={"include[]": ["rubric", "rubric_settings"]},
    )


# ---------------------------------------------------------------------------
# Module overview text (the soft-match layer)
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "your", "you",
    "are", "will", "can", "use", "have", "has", "but", "not", "all", "any",
    "course", "module", "week", "assignment", "students", "student", "should",
    "their", "what", "when", "where", "which", "while", "would", "could",
}


def _significant_tokens(text: str, min_len: int = 4) -> set[str]:
    """Lowercased significant tokens for soft text matching."""
    clean = _HTML_TAG_RE.sub(" ", text or "")
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", clean.lower())
    return {w for w in words if len(w) >= min_len and w not in _STOPWORDS}


def pull_module_overviews(course_id: str) -> list[dict]:
    """Pull each module's overview page text (if discoverable from module items).

    Convention: the overview is the first Page item in a module, typically titled
    "Overview", "Module N — Title", or similar. We pull every Page item per module
    and merge the text — broader than just "the overview" but cheaper than guessing.
    """
    modules = _get_paged(f"/courses/{course_id}/modules", params={"include[]": "items"})
    out: list[dict] = []
    for m in modules:
        page_items = [i for i in m.get("items") or [] if i.get("type") == "Page"]
        text_parts: list[str] = []
        for it in page_items:
            page_url = it.get("page_url")
            if not page_url:
                continue
            page = _get(f"/courses/{course_id}/pages/{page_url}") or {}
            body = page.get("body") or ""
            if body:
                text_parts.append(body)
        out.append({
            "id": m.get("id"),
            "name": m.get("name", ""),
            "position": m.get("position", 0),
            "text": "\n".join(text_parts),
            "tokens": _significant_tokens("\n".join(text_parts)),
        })
    return out


# ---------------------------------------------------------------------------
# The audit
# ---------------------------------------------------------------------------

def audit_alignment(
    clos: list[dict],
    assignments: list[dict],
    modules: list[dict],
) -> dict:
    """Run the full alignment chain audit.

    Returns:
      {
        "outcomes": [{id, text, linked_criteria: [...], plausible_modules: [...], status}],
        "criteria": [{assignment_id, assignment_name, criterion_id, description, outcome_id, status}],
        "orphan_outcome_count": N,
        "orphan_criterion_count": M,
        "untaught_outcome_count": K,
        "verdict": "complete" | "partial" | "unverified",
      }
    """
    # Build outcome lookup
    outcomes_by_id: dict[int, dict] = {}
    for clo in clos:
        oid = clo.get("id")
        if oid is None:
            continue
        outcomes_by_id[int(oid)] = {
            "id": int(oid),
            "text": clo.get("description") or clo.get("display_name") or "",
            "short_description": clo.get("title") or clo.get("short_description") or "",
            "linked_criteria": [],
            "plausible_modules": [],
        }

    if not outcomes_by_id:
        return {
            "outcomes": [],
            "criteria": [],
            "orphan_outcome_count": 0,
            "orphan_criterion_count": 0,
            "untaught_outcome_count": 0,
            "verdict": "unverified",
            "reason": "no course outcomes discovered (precondition for alignment audit)",
        }

    # Walk assignments → rubrics → criteria; build the link table
    criterion_records: list[dict] = []
    for a in assignments:
        rubric = a.get("rubric") or []  # list of criterion dicts
        if not isinstance(rubric, list):
            continue
        for crit in rubric:
            oid = extract_criterion_outcome_id(crit)
            rec = {
                "assignment_id": a.get("id"),
                "assignment_name": a.get("name", ""),
                "criterion_id": crit.get("id"),
                "description": crit.get("description") or "",
                "outcome_id": oid,
                "status": "linked" if oid and oid in outcomes_by_id else "orphan_criterion",
            }
            criterion_records.append(rec)
            if oid and oid in outcomes_by_id:
                outcomes_by_id[oid]["linked_criteria"].append({
                    "assignment_id": a.get("id"),
                    "assignment_name": a.get("name", ""),
                    "criterion_description": crit.get("description") or "",
                })

    # Soft module-overview match: for each outcome, find modules whose token set
    # overlaps the outcome's significant tokens (≥3 tokens shared = "plausible coverage").
    for oid, oc in outcomes_by_id.items():
        ot = _significant_tokens(oc["text"])
        for m in modules:
            overlap = ot & m["tokens"]
            if len(overlap) >= 3:
                oc["plausible_modules"].append({
                    "module_id": m["id"],
                    "module_name": m["name"],
                    "shared_tokens": sorted(overlap)[:5],
                })

    # Tag per-outcome status
    for oc in outcomes_by_id.values():
        if not oc["linked_criteria"]:
            oc["status"] = "orphan_outcome"  # no assessment evidence
        elif not oc["plausible_modules"]:
            oc["status"] = "untaught_outcome"  # assessed but no module-level teaching signal
        else:
            oc["status"] = "covered"

    orphan_outcomes = [o for o in outcomes_by_id.values() if o["status"] == "orphan_outcome"]
    untaught_outcomes = [o for o in outcomes_by_id.values() if o["status"] == "untaught_outcome"]
    orphan_criteria = [c for c in criterion_records if c["status"] == "orphan_criterion"]

    # Verdict — deterministic only (orphan outcomes + orphan criteria drive it;
    # untaught is advisory, doesn't move the bar)
    if not orphan_outcomes and not orphan_criteria:
        verdict = "complete"
    else:
        verdict = "partial"

    return {
        "outcomes": list(outcomes_by_id.values()),
        "criteria": criterion_records,
        "orphan_outcome_count": len(orphan_outcomes),
        "orphan_criterion_count": len(orphan_criteria),
        "untaught_outcome_count": len(untaught_outcomes),
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_markdown(course_id: str, course_name: str, res: dict, detailed: bool, ts: str) -> list[str]:
    L: list[str] = []
    L.append(f"# Course Alignment Audit — {course_name}")
    L.append("")
    L.append(f"**Course ID:** {course_id}")
    L.append(f"**Generated:** {ts}")
    L.append(f"**Tool:** course_alignment_audit.py (canvas-toolbox {__version__})")
    L.append(f"**Standard:** NWCCU 2.3 — Outcomes ↔ assessments ↔ activities alignment "
             f"(`course_design_standards_knowledge.md`)")
    L.append("")
    if res["verdict"] == "unverified":
        L.append("**Verdict:** ⚠ unverified — " + res.get("reason", ""))
        return L
    icon = {"complete": "✅", "partial": "⚠"}.get(res["verdict"], "⚠")
    L.append(f"**Verdict:** {icon} **{res['verdict']}**")
    L.append("")
    L.append("## Summary")
    L.append("")
    L.append(f"- **{len(res['outcomes'])}** course outcomes")
    L.append(f"- **{len(res['criteria'])}** rubric criteria (across all assignments)")
    linked = sum(1 for c in res["criteria"] if c["status"] == "linked")
    L.append(f"- **{linked}** of {len(res['criteria'])} criteria linked to a course outcome")
    L.append(f"- **{res['orphan_outcome_count']}** orphan outcomes "
             "(no rubric criterion linked — assessment gap)")
    L.append(f"- **{res['orphan_criterion_count']}** orphan criteria "
             "(no `learning_outcome_id` — outcome gap)")
    L.append(f"- **{res['untaught_outcome_count']}** outcomes with no module-level "
             "coverage signal *(soft / advisory)*")
    L.append("")
    L.append("> **Note on the soft signal:** module-overview text matching is a "
             "heuristic. *Not detected* means **review**, not proven absent — same "
             "evidence-based stance as `rubric_quality_audit` Criterion 1.")
    L.append("")

    # Orphan outcomes (highest priority — assessment gap)
    orphans = [o for o in res["outcomes"] if o["status"] == "orphan_outcome"]
    if orphans:
        L.append("## ⛔ Orphan outcomes — assessed by no rubric criterion")
        L.append("")
        L.append("These course outcomes have **no rubric criterion** linked to them. "
                 "The course claims to teach X but has no measure for X.")
        L.append("")
        for o in orphans:
            L.append(f"### {o['short_description'] or '(unnamed)'} (id={o['id']})")
            L.append("")
            if o["text"]:
                L.append(f"> {o['text']}")
                L.append("")
            if o["plausible_modules"]:
                L.append(f"_Plausibly covered by modules:_ " +
                         ", ".join(m["module_name"] for m in o["plausible_modules"][:3]) +
                         " — but **no assessment**.")
            else:
                L.append("_No module-level teaching signal either._ Outcome may be vestigial.")
            L.append("")

    # Orphan criteria (outcome gap — assignment measures something not tied to a CLO)
    orphan_crits = [c for c in res["criteria"] if c["status"] == "orphan_criterion"]
    if orphan_crits:
        L.append("## ⛔ Orphan criteria — measure something with no upstream outcome")
        L.append("")
        L.append("These rubric criteria have no `learning_outcome_id`. They measure "
                 "*something*, but that something isn't tied to a declared course outcome.")
        L.append("")
        # Group by assignment for readability
        by_a: dict[str, list[dict]] = {}
        for c in orphan_crits:
            by_a.setdefault(c["assignment_name"] or f"(assignment {c['assignment_id']})", []).append(c)
        for a_name, items in sorted(by_a.items()):
            L.append(f"### {a_name}")
            L.append("")
            for c in items:
                L.append(f"- {c['description'] or '(no description)'}")
            L.append("")

    # Untaught outcomes (soft signal — instructor should review)
    untaught = [o for o in res["outcomes"] if o["status"] == "untaught_outcome"]
    if untaught:
        L.append("## ⚠ Untaught outcomes (soft signal — review)")
        L.append("")
        L.append("These outcomes ARE assessed (rubric criteria linked) but no module "
                 "overview text overlaps the outcome's significant tokens. This is a "
                 "heuristic — the outcome may be taught implicitly or via materials "
                 "this audit doesn't read.")
        L.append("")
        for o in untaught:
            assess_count = len(o["linked_criteria"])
            L.append(f"- **{o['short_description'] or '(unnamed)'}** "
                     f"({assess_count} criterion link(s); no module-overview overlap)")
        L.append("")

    # Covered outcomes (per-outcome chain — detailed mode)
    if detailed:
        covered = [o for o in res["outcomes"] if o["status"] == "covered"]
        if covered:
            L.append("## ✅ Covered outcomes (per-outcome chain — detailed)")
            L.append("")
            for o in covered:
                L.append(f"### {o['short_description'] or '(unnamed)'} (id={o['id']})")
                if o["text"]:
                    L.append("")
                    L.append(f"> {o['text']}")
                L.append("")
                L.append(f"**Rubric criteria linked:** {len(o['linked_criteria'])}")
                for c in o["linked_criteria"]:
                    L.append(f"- _{c['assignment_name']}:_ {c['criterion_description']}")
                L.append("")
                L.append(f"**Plausibly taught in modules:** "
                         + ", ".join(m["module_name"] for m in o["plausible_modules"][:5]))
                L.append("")

    # Audit tag for downstream consumers
    L.append("---")
    L.append("")
    L.append("## Audit tag")
    L.append("")
    L.append(f"`alignment_chain`: **{res['verdict']}** "
             f"(orphan_outcomes={res['orphan_outcome_count']}, "
             f"orphan_criteria={res['orphan_criterion_count']}, "
             f"untaught_outcomes={res['untaught_outcome_count']} [soft])")
    L.append("")
    return L


def _render_json(course_id: str, course_name: str, res: dict, ts: str) -> dict:
    return {
        "course_id": course_id,
        "course_name": course_name,
        "generated": ts,
        "tool": "course_alignment_audit",
        "version": __version__,
        "standard": "NWCCU 2.3 — outcomes ↔ assessments ↔ activities alignment",
        "verdict": res["verdict"],
        "alignment_chain": res["verdict"],
        "summary": {
            "outcome_count": len(res["outcomes"]),
            "criterion_count": len(res["criteria"]),
            "linked_criteria_count": sum(1 for c in res["criteria"] if c["status"] == "linked"),
            "orphan_outcomes": res["orphan_outcome_count"],
            "orphan_criteria": res["orphan_criterion_count"],
            "untaught_outcomes_soft": res["untaught_outcome_count"],
        },
        "outcomes": res["outcomes"],
        "criteria": res["criteria"],
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
        description="Outcomes ↔ rubric criteria ↔ activities alignment audit (NWCCU 2.3).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    course_grp = ap.add_mutually_exclusive_group()
    course_grp.add_argument("--course-id", help="Canvas course id (overrides --target).")
    course_grp.add_argument("--target", default="CANVAS_COURSE_ID",
                            help="Env var to read the course id from. Default CANVAS_COURSE_ID.")
    ap.add_argument("--report", help="Write the audit to this .md path (with .pdf sibling if Chrome available).")
    ap.add_argument("--emit-json", action="store_true",
                    help="Emit JSON to stdout instead of human-readable markdown.")
    ap.add_argument("--detailed", action="store_true",
                    help="Include the full per-outcome chain table for covered outcomes.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Bypass canvas_course_guard advisory for enrolled-course reads (read is "
                         "advisory anyway; this flag silences the verdict echo).")
    args = ap.parse_args()

    if not CANVAS_API_TOKEN:
        print("ERROR: CANVAS_API_TOKEN missing from .env.", file=sys.stderr)
        return 2
    if not CANVAS_BASE_URL:
        print("ERROR: CANVAS_BASE_URL missing from .env.", file=sys.stderr)
        return 2

    course_id = args.course_id
    source = "--course-id"
    if not course_id:
        course_id = os.environ.get(args.target, "")
        source = f"env {args.target}"
    if not course_id:
        print(f"ERROR: course ID not found via {source}. Pass --course-id <id>.", file=sys.stderr)
        return 2

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="read", allow_override=args.allow_enrolled, label="audit target")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    course = _get(f"/courses/{course_id}") or {}
    course_name = (course.get("name") if isinstance(course, dict) else None) or "<unknown course>"

    print(f"[1/3] Fetching course outcomes for {course_id}...", file=sys.stderr)
    clos = fetch_course_outcomes(course_id)
    print(f"[2/3] Fetching assignments + rubrics...", file=sys.stderr)
    assignments = pull_assignments_with_rubrics(course_id)
    print(f"[3/3] Fetching module overviews (soft-match)...", file=sys.stderr)
    modules = pull_module_overviews(course_id)

    res = audit_alignment(clos, assignments, modules)

    if args.emit_json:
        out = json.dumps(_render_json(course_id, course_name, res, ts), indent=2, ensure_ascii=False)
        print(out)
        if args.report:
            _write_report(Path(args.report), out)
    else:
        lines = _render_markdown(course_id, course_name, res, args.detailed, ts)
        print("\n".join(lines))
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    # Exit codes per the docstring
    if res["verdict"] == "unverified":
        return 2
    if res["verdict"] == "partial":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

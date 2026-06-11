#!/usr/bin/env python3
"""
learning_model_audit.py — read-only audit: does each module exercise the configured pedagogical phases?

Closes BYUI Course Design Standard 3.1 ("The Learning Model is integrated into each
module"). Generalized: default ships BYUI's three-phase Learning Model (Prepare /
Teach One Another / Ponder-Prove), but the phase markers are configurable so any
institution with a multi-phase pedagogical framework can plug in their own.

Why generalized: per the canvas-toolbox open-source philosophy + the operator's
direction (2026-06-10): "BYUI should be a leading uni in student teaching with our
student focus" — open the tool to other universities by default, with BYUI as the
default preset rather than the only mode.

WHAT IT CHECKS

  For each module:
    1. Fetch the module's overview page(s) — Canvas Page items in the module
    2. For each configured phase, scan the overview text for phase-keyword
       markers
    3. Tag the module as `complete` (all phases present), `partial` (some
       missing), or `missing` (no phases detected)
  Cohort-wide aggregate: per-phase coverage + per-module status table.

PRESETS

  --preset byui (default)
    Three phases:
    - Prepare              keywords: prepare, before class, readings, pre-class, review, study guide
    - Teach One Another    keywords: teach one another, discuss, peer, group, share, collaborate, explain to
    - Ponder-Prove         keywords: ponder, prove, reflect, apply, demonstrate, performance, assess

  --preset kolb
    Four phases (Kolb's experiential learning cycle):
    - Concrete Experience  keywords: experience, encounter, observe directly, hands-on
    - Reflective Observation keywords: reflect, observe, think about, journal
    - Abstract Conceptualization keywords: conceptualize, theorize, model, framework
    - Active Experimentation keywords: experiment, apply, try, test, practice

  --preset bloom-3
    Three phases (Hattie 3-phase mapped to Bloom levels):
    - Surface (remember/understand) keywords: define, list, identify, recall, understand
    - Deep (apply/analyze)          keywords: analyze, compare, apply, examine, interpret
    - Transfer (evaluate/create)    keywords: evaluate, create, design, defend, synthesize

  --phases-config <path>
    JSON config that overrides the preset entirely. Shape:
      {"phases": [{"name": "...", "keywords": ["...", "..."]}, ...]}

ENDPOINTS (all GET, read-only):
  GET /courses/:id                                         (course name)
  GET /courses/:id?include[]=total_students                (safety guard, advisory)
  GET /courses/:id/blueprint_subscriptions                 (safety guard, advisory)
  GET /courses/:id/modules?include[]=items                 (modules + items)
  GET /courses/:id/pages/:url                              (per-page content)

EXIT CODES
  0  all modules complete (every phase present in every module)
  1  partial coverage (some modules missing phases)
  2  configuration error

USAGE
  uv run python canvas_toolbox/lib/tools/learning_model_audit.py --course-id 402262
  uv run python canvas_toolbox/lib/tools/learning_model_audit.py --course-id 12345 --preset kolb
  uv run python canvas_toolbox/lib/tools/learning_model_audit.py --course-id 12345 \\
    --phases-config /path/to/my_university_phases.json --report /tmp/audit.md

ANCHORS
  - course_design_standards_knowledge.md standard 3.1 (the institutional anchor)
  - hattie_3phase_knowledge.md (Surface → Deep → Transfer — the bloom-3 preset)
  - experiential_learning_knowledge.md (Kolb cycle — the kolb preset)

PAIRS WITH
  - course_audit.py (umbrella — could surface this audit's per-module status)
  - module_structure_diff.py (consistency across modules — different concern)
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
from bs4 import BeautifulSoup

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url
_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Phase presets — each maps a pedagogical framework to keyword markers
# ---------------------------------------------------------------------------

PRESETS = {
    "byui": {
        "name": "BYU-Idaho Learning Model",
        "phases": [
            {
                "name": "Prepare",
                "keywords": [
                    "prepare", "preparation", "before class", "pre-class", "pre class",
                    "readings", "reading assignment", "review", "study guide",
                    "background reading", "preview", "to be ready",
                ],
            },
            {
                "name": "Teach One Another",
                "keywords": [
                    "teach one another", "discuss", "discussion", "peer", "peers",
                    "group work", "groupwork", "collaborate", "collaboration",
                    "share", "share with", "explain to", "explain it",
                    "in class", "during class", "small group",
                ],
            },
            {
                "name": "Ponder-Prove",
                "keywords": [
                    "ponder", "prove", "reflect", "reflection", "apply",
                    "demonstrate", "demonstration", "performance", "assessment",
                    "self-assess", "assignment due", "deliverable",
                ],
            },
        ],
    },
    "kolb": {
        "name": "Kolb Experiential Learning Cycle",
        "phases": [
            {
                "name": "Concrete Experience",
                "keywords": ["experience", "encounter", "observe directly", "hands-on",
                             "hands on", "lab", "field", "first-hand"],
            },
            {
                "name": "Reflective Observation",
                "keywords": ["reflect", "observe", "think about", "journal",
                             "reflective", "consider what happened", "notice"],
            },
            {
                "name": "Abstract Conceptualization",
                "keywords": ["conceptualize", "theorize", "model", "framework",
                             "principle", "abstract", "generalize", "theory"],
            },
            {
                "name": "Active Experimentation",
                "keywords": ["experiment", "apply", "try", "test", "practice",
                             "implement", "use it"],
            },
        ],
    },
    "bloom-3": {
        "name": "Hattie 3-Phase (Surface / Deep / Transfer)",
        "phases": [
            {
                "name": "Surface",
                "keywords": ["define", "list", "identify", "recall", "understand",
                             "describe", "name", "recognize", "explain in your words"],
            },
            {
                "name": "Deep",
                "keywords": ["analyze", "compare", "apply", "examine", "interpret",
                             "classify", "distinguish", "differentiate", "investigate"],
            },
            {
                "name": "Transfer",
                "keywords": ["evaluate", "create", "design", "defend", "synthesize",
                             "judge", "critique", "produce", "construct", "develop"],
            },
        ],
    },
}


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


def load_phases_config(args: argparse.Namespace) -> dict:
    if args.phases_config:
        with open(args.phases_config, encoding="utf-8") as f:
            cfg = json.load(f)
        # Sanity check
        if "phases" not in cfg or not isinstance(cfg["phases"], list):
            print(f"ERROR: --phases-config must contain a 'phases' array.", file=sys.stderr)
            sys.exit(2)
        return cfg
    preset = PRESETS.get(args.preset)
    if not preset:
        print(f"ERROR: unknown --preset '{args.preset}'. Available: {list(PRESETS.keys())}",
              file=sys.stderr)
        sys.exit(2)
    return preset


# ---------------------------------------------------------------------------
# The audit (per-module phase detection)
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html_to_text(html: str) -> str:
    """Return plain text from HTML, lowercased for keyword matching."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ").lower()


def detect_phase_in_text(text: str, phase: dict) -> dict:
    """Detect a phase's presence in text. Returns {found: bool, matched_keywords: [...]}."""
    matched = []
    for kw in phase["keywords"]:
        # Word-boundary match (avoid partial-word false positives like "applying" matching "apply"
        # — actually we DO want stem-y matches; use substring for now)
        if kw.lower() in text:
            matched.append(kw)
    return {"found": bool(matched), "matched_keywords": matched[:5]}  # cap displayed keywords


def audit_modules(course_id: str, phases: list[dict]) -> list[dict]:
    """For each module: pull overview page text, detect each phase, return module records."""
    modules = _get_paged(f"/courses/{course_id}/modules", params={"include[]": "items"})
    out: list[dict] = []
    for m in modules:
        # Collect page items in the module — overview text comes from these
        page_items = [i for i in m.get("items") or [] if i.get("type") == "Page"]
        text_parts: list[str] = []
        for it in page_items:
            page_url = it.get("page_url")
            if not page_url:
                continue
            page = _get(f"/courses/{course_id}/pages/{page_url}") or {}
            body = page.get("body") or ""
            if body:
                text_parts.append(_strip_html_to_text(body))
        full_text = " ".join(text_parts)
        # Per-phase detection
        phase_results = []
        for ph in phases:
            phase_results.append({
                "phase": ph["name"],
                **detect_phase_in_text(full_text, ph),
            })
        present_count = sum(1 for p in phase_results if p["found"])
        if present_count == len(phases):
            status = "complete"
        elif present_count > 0:
            status = "partial"
        else:
            status = "missing"
        out.append({
            "module_id": m.get("id"),
            "module_name": m.get("name", ""),
            "position": m.get("position", 0),
            "page_item_count": len(page_items),
            "phase_results": phase_results,
            "phases_present": present_count,
            "phases_total": len(phases),
            "status": status,
        })
    return out


def aggregate(modules: list[dict], phases: list[dict]) -> dict:
    by_status = {"complete": 0, "partial": 0, "missing": 0}
    by_phase_coverage: dict[str, int] = {ph["name"]: 0 for ph in phases}
    for m in modules:
        by_status[m["status"]] += 1
        for p in m["phase_results"]:
            if p["found"]:
                by_phase_coverage[p["phase"]] += 1
    total = len(modules) or 1
    return {
        "total_modules": len(modules),
        "by_status": by_status,
        "by_phase_coverage": by_phase_coverage,
        "by_phase_coverage_pct": {
            name: (count / total * 100.0) for name, count in by_phase_coverage.items()
        },
    }


def overall_verdict(agg: dict) -> str:
    s = agg["by_status"]
    if s["missing"] == 0 and s["partial"] == 0:
        return "complete"
    if s["missing"] == agg["total_modules"]:
        return "unverified"  # 0 modules detected anything — config or course doesn't apply
    return "partial"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_markdown(course_name: str, course_id: str, framework_name: str,
                     phases: list[dict], modules: list[dict], agg: dict,
                     verdict: str, ts: str) -> list[str]:
    L: list[str] = []
    L.append(f"# Learning Model Audit — {course_name}")
    L.append("")
    L.append(f"**Course ID:** {course_id}")
    L.append(f"**Generated:** {ts}")
    L.append(f"**Tool:** learning_model_audit.py (canvas-toolbox {__version__})")
    L.append(f"**Framework:** {framework_name}")
    L.append(f"**Standard:** BYUI Course Design Standard 3.1 — Learning Model in each module")
    L.append("")
    icon = {"complete": "✅", "partial": "⚠", "unverified": "⛔"}[verdict]
    L.append(f"**Verdict:** {icon} **{verdict}**")
    L.append("")
    if verdict == "unverified":
        L.append("> No phase markers detected in ANY module's overview pages. This usually "
                 "means one of: (a) the course doesn't follow this pedagogical framework "
                 "(try a different --preset); (b) modules have no overview Page items "
                 "(framework can't be detected); (c) overview pages use very different "
                 "vocabulary from the configured keywords (override via --phases-config "
                 "with course-specific keywords).")
        return L

    L.append("## Summary")
    L.append("")
    s = agg["by_status"]
    L.append(f"- Modules audited: **{agg['total_modules']}**")
    L.append(f"- Complete (all phases present): **{s['complete']}**")
    L.append(f"- Partial (some phases missing): **{s['partial']}**")
    L.append(f"- Missing (no phases detected): **{s['missing']}**")
    L.append("")
    L.append("### Per-phase coverage across modules")
    L.append("")
    L.append("| Phase | Coverage |")
    L.append("|---|---:|")
    for name, pct in agg["by_phase_coverage_pct"].items():
        count = agg["by_phase_coverage"][name]
        L.append(f"| {name} | {count} / {agg['total_modules']} ({pct:.0f}%) |")
    L.append("")

    # Per-module table
    L.append("## Per-module status")
    L.append("")
    header = "| # | Module | " + " | ".join(ph["name"] for ph in phases) + " | Status |"
    sep = "|---|---|" + "|".join(["---"] * len(phases)) + "|---|"
    L.append(header)
    L.append(sep)
    sorted_modules = sorted(modules, key=lambda m: m["position"])
    for m in sorted_modules:
        cells = []
        for pr in m["phase_results"]:
            cells.append("✅" if pr["found"] else "⛔")
        status_icon = {"complete": "✅", "partial": "⚠", "missing": "⛔"}[m["status"]]
        L.append(f"| {m['position']} | {m['module_name']} | {' | '.join(cells)} | "
                 f"{status_icon} {m['status']} |")
    L.append("")

    # Per-module detail for the non-complete ones
    non_complete = [m for m in sorted_modules if m["status"] != "complete"]
    if non_complete:
        L.append("## Modules needing attention")
        L.append("")
        for m in non_complete:
            L.append(f"### {m['position']}. {m['module_name']} — {m['status']}")
            L.append("")
            L.append(f"- Page items in module: {m['page_item_count']}")
            for pr in m["phase_results"]:
                icon = "✅" if pr["found"] else "⛔"
                kw = (", ".join(f"`{k}`" for k in pr["matched_keywords"])
                      if pr["matched_keywords"] else "(none)")
                L.append(f"- {icon} **{pr['phase']}** — matched keywords: {kw}")
            L.append("")

    # Audit tag
    L.append("---")
    L.append("")
    L.append("## Audit tag")
    L.append("")
    L.append(f"`learning_model_integration`: **{verdict}** "
             f"(complete={s['complete']}, partial={s['partial']}, missing={s['missing']}; "
             f"framework={framework_name})")
    L.append("")
    L.append("**Caveat — heuristic check.** This audit looks for keyword markers in module "
             "overview pages; phase presence is a SOFT signal (the module may exercise the "
             "phase through activities the overview doesn't describe with these specific words). "
             "Treat findings as review prompts, not proven absences. Same evidence-based stance "
             "as the other canvas-toolbox audits.")
    return L


def _render_json(course_name: str, course_id: str, framework_name: str,
                 modules: list[dict], agg: dict, verdict: str, ts: str) -> dict:
    return {
        "tool": "learning_model_audit",
        "version": __version__,
        "generated": ts,
        "course_id": course_id,
        "course_name": course_name,
        "framework": framework_name,
        "standard": "BYUI Course Design Standard 3.1 — Learning Model in each module",
        "verdict": verdict,
        "learning_model_integration": verdict,
        "summary": agg,
        "modules": modules,
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
    ap = argparse.ArgumentParser(
        description="Read-only Learning Model audit (NWCCU 3.1 — generalizable across institutions).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--course-id", help="Canvas course id.")
    grp.add_argument("--target", default="CANVAS_COURSE_ID",
                     help="Env var to read the course id from. Default CANVAS_COURSE_ID.")
    ap.add_argument("--report", help=".md path to write the report (with .pdf sibling if Chrome).")
    ap.add_argument("--emit-json", action="store_true",
                    help="Emit JSON to stdout instead of human-readable markdown.")
    ap.add_argument("--preset", default="byui", choices=list(PRESETS.keys()),
                    help=f"Pedagogical framework preset. Default: byui. "
                         f"Options: {list(PRESETS.keys())}")
    ap.add_argument("--phases-config", default=None,
                    help="Path to a custom phases JSON config that overrides --preset entirely. "
                         "Shape: {'phases': [{'name': '...', 'keywords': ['...', ...]}, ...]}")
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

    framework_cfg = load_phases_config(args)
    phases = framework_cfg["phases"]
    framework_name = framework_cfg.get("name", args.preset)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    course = _get(f"/courses/{course_id}") or {}
    if not isinstance(course, dict):
        print(f"ERROR: couldn't load course {course_id}.", file=sys.stderr)
        return 2
    course_name = course.get("name", "<unknown course>")

    print(f"Auditing {course_id} against {framework_name}...", file=sys.stderr)
    modules = audit_modules(course_id, phases)
    if not modules:
        print(f"ERROR: no modules found for course {course_id}.", file=sys.stderr)
        return 2

    agg = aggregate(modules, phases)
    verdict = overall_verdict(agg)

    if args.emit_json:
        body = json.dumps(_render_json(course_name, course_id, framework_name,
                                       modules, agg, verdict, ts), indent=2, ensure_ascii=False)
        print(body)
        if args.report:
            _write_report(Path(args.report), body)
    else:
        lines = _render_markdown(course_name, course_id, framework_name,
                                 phases, modules, agg, verdict, ts)
        print("\n".join(lines))
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    return 0 if verdict == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())

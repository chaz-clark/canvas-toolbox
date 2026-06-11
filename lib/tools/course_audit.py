#!/usr/bin/env python3
"""
course_audit.py — one-command course health audit (read-only orchestrator).

TWO TIERS:
  QUICK (default) — composes the four core read-only audit tools into a fast
                     pre-authoring health check:
    - rubric_coverage_audit  — which assignments lack/have/decorative rubrics
    - rubric_quality_audit   — are the rubrics well-formed (backbone meta-rubric)
    - syllabus_audit         — is the syllabus complete (+ required AI policy)
    - clo_quality_audit      — are the course outcomes well-written (AoL rubric)

  FULL (--full) — adds the standards-gap audits (NWCCU + BYUI Course Design
                  Standards). Slower; intended pre-publish / pre-semester:
    - course_alignment_audit  — outcomes ↔ rubric ↔ activity chain (NWCCU 2.3)
    - learning_model_audit    — pedagogy-phase coverage (BYUI 3.1; presets
                                byui/kolb/bloom-3/merrill)
    - formative_variety_audit — formative presence + precedence + distribution (3.3)
    - grading_structure_audit — weight balance + over-influence + temporal stacking (7.x)
    - grading_load_audit      — grader hours per week vs. credit-based cap (7.3)
    - accessibility_audit     — WCAG 2.1 AA + cognitive layer (6.3) — legal disclaimer
                                applies; this aids review, does not certify compliance
    - workload_audit          — gradable-work distribution + crunch-week detection

This is a TOOL-SIDE orchestrator. It follows the `make_orchestrator_agent` skill's
core principles at the tool layer (see make-ai-agents/make_orchestrator_agent.md):
  - **Specialists are decoupled, referenced by path.** Each audit is invoked as a
    sealed subprocess via its own JSON contract — never reimplemented or inlined.
    Every specialist stays fully usable standalone. The orchestrator handles
    flag-name differences between specialists (`--json` vs. `--emit-json`).
  - **Composition is visible.** Each specialist's verdict is surfaced and rolled up
    into one health summary + a single "top things to fix" list; no hidden logic.
The agent-LAYER orchestrator is `canvas_course_expert` (which reasons over these same
knowledge files); this tool is the deterministic, scriptable composition of the audits.

Combined verdict (rollup of all specialists run):
  HEALTHY        — every specialist clean
  REVIEW         — at least one specialist raised a soft/advisory signal (🟡)
  NEEDS_ATTENTION — at least one specialist raised a hard finding (🔴)

Exit codes:
  0  HEALTHY
  1  REVIEW or NEEDS_ATTENTION (findings exist)
  2  could not run any specialist (config error / bad course id)

Usage:
  uv run python canvas_toolbox/lib/tools/course_audit.py --target CANVAS_SANDBOX_ID
  uv run python canvas_toolbox/lib/tools/course_audit.py --course-id 402262 --detailed
  uv run python canvas_toolbox/lib/tools/course_audit.py --course-id 402262 --full
  uv run python canvas_toolbox/lib/tools/course_audit.py --course-id 402262 --json --report health.md

Requires in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL (+ the env var named by --target).
The specialists read .env themselves; this orchestrator only resolves the course id and
forwards it, then composes their JSON. All read-only — nothing is written to Canvas.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from __toolbox_version__ import __version__

load_dotenv()

_TOOLS_DIR = Path(__file__).resolve().parent
# Specialist roster: (key, tool filename, human label, json-flag).
# Referenced by PATH — decoupled. `json_flag` is the CLI arg each tool uses to
# emit machine-readable JSON: most tools use `--json`, the newer
# standards-gap audits use `--emit-json` — the orchestrator handles either.
QUICK_SPECIALISTS = [
    ("rubric_coverage", "rubric_coverage_audit.py", "Rubric coverage", "--json"),
    ("rubric_quality",  "rubric_quality_audit.py",  "Rubric quality",  "--json"),
    ("syllabus",        "syllabus_audit.py",        "Syllabus",        "--json"),
    ("clo_quality",     "clo_quality_audit.py",     "CLO quality",     "--json"),
]

# Added by --full. The standards-gap audits (NWCCU + BYUI Course Design Standards)
# and workload audit. Each is independently usable; the orchestrator just composes.
FULL_EXTRA_SPECIALISTS = [
    ("course_alignment",  "course_alignment_audit.py",  "Alignment chain",   "--emit-json"),
    ("learning_model",    "learning_model_audit.py",    "Learning model",    "--emit-json"),
    ("formative_variety", "formative_variety_audit.py", "Formative variety", "--emit-json"),
    ("grading_structure", "grading_structure_audit.py", "Grading structure", "--emit-json"),
    ("grading_load",      "grading_load_audit.py",      "Grading load",      "--emit-json"),
    ("accessibility",     "accessibility_audit.py",     "Accessibility",     "--emit-json"),
    ("workload",          "workload_audit.py",          "Workload",          "--json"),
]


# ---------------------------------------------------------------------------
# Specialist invocation (the "delegate_to_*" analog — sealed JSON subprocess)
# ---------------------------------------------------------------------------

def run_specialist(tool_file: str, course_id: str, allow_enrolled: bool,
                   json_flag: str = "--json") -> dict | None:
    """Invoke one audit tool with --course-id + its JSON flag and return parsed JSON.
    Returns None if the specialist produced no parseable JSON. The audit tools
    exit non-zero when they HAVE findings (1) or can't run (2) — that's expected,
    so we parse stdout regardless of exit code."""
    cmd = [sys.executable, str(_TOOLS_DIR / tool_file),
           "--course-id", course_id, json_flag]
    if allow_enrolled:
        cmd.append("--allow-enrolled")
    try:
        # Full sweep can take longer (accessibility walks every page) — give 5 min.
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception:
        return None
    out = (proc.stdout or "").strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Per-specialist headline extraction (defensive — each tool's own JSON shape)
# ---------------------------------------------------------------------------

# severity: 2 = 🔴 hard finding, 1 = 🟡 review/soft, 0 = ✅ clean, -1 = ⚪ could not run
_GLYPH = {2: "🔴", 1: "🟡", 0: "✅", -1: "⚪"}


def _headline(key: str, d: dict | None) -> tuple[int, str, list[str]]:
    """Return (severity, one-line headline, fixes[]) for a specialist's JSON."""
    if d is None:
        return -1, "could not run (no parseable output)", []

    if key == "rubric_coverage":
        s = d.get("summary", {})
        miss, dec, has = s.get("missing_rubric", 0), s.get("decorative_rubric", 0), s.get("has_rubric", 0)
        sev = 2 if miss else (1 if dec else 0)
        fixes = ([f"{miss} graded assignment(s) missing a rubric"] if miss else []) + \
                ([f"{dec} decorative rubric(s) (attached but not used for grading)"] if dec else [])
        return sev, f"{miss} missing · {dec} decorative · {has} ok", fixes

    if key == "rubric_quality":
        s = d.get("summary", {})
        needs, part = s.get("needs_revision", 0), s.get("partial", 0)
        meets = s.get("meets_criteria", 0) + s.get("meets_criteria_unverified", 0)
        sev = 2 if needs else (1 if part else 0)
        fixes = ([f"{needs} rubric(s) need revision"] if needs else []) + \
                ([f"{part} rubric(s) partially meet the backbone"] if part else [])
        return sev, f"{meets} meet · {part} partial · {needs} need revision", fixes

    if key == "syllabus":
        v = d.get("verdict", "?")
        det, tot = d.get("required_detected", "?"), d.get("required_total", "?")
        ai = (d.get("ai_policy") or {}).get("present")
        sev = {"complete": 0, "incomplete": 2, "no_syllabus": 1}.get(v, 1)
        fixes = []
        if v == "incomplete":
            for m in d.get("missing", []):
                fixes.append(f"syllabus: add {m}")
        elif v == "no_syllabus":
            fixes.append("syllabus body empty/near-empty — likely a linked page/file the audit can't see")
        return sev, f"{v} ({det}/{tot} sections; AI policy: {'yes' if ai else 'no'})", fixes

    if key == "clo_quality":
        v = d.get("clo_quality", "?")
        n = d.get("clo_count", "?")
        flags = d.get("clo_criteria_flags", [])
        sev = {"meets_criteria": 0, "partial": 1, "needs_revision": 2, "unverified": 1}.get(v, 1)
        fixes = []
        if v in ("partial", "needs_revision"):
            nbad = sum(1 for c in d.get("clos", []) if c.get("flags"))
            if nbad:
                fixes.append(f"{nbad} CLO(s) flagged (measurable / single-barreled)")
            if flags:
                fixes.append(f"course-level CLO issue: {', '.join(flags)}")
        elif v == "unverified":
            fixes.append("no course outcomes discovered (define Canvas Outcomes or a syllabus Learning Outcomes section)")
        return sev, f"{v} ({n} CLOs)", fixes

    # ----- --full additions (NWCCU + BYUI Course Design Standards audits) -----

    if key == "course_alignment":
        v = d.get("alignment_chain") or d.get("verdict", "?")
        s = d.get("summary", {})
        orph_out = s.get("orphan_outcomes", 0)
        orph_crit = s.get("orphan_criteria", 0)
        sev = {"complete": 0, "partial": 2, "unverified": 1}.get(v, 1)
        fixes = []
        if orph_out:
            fixes.append(f"{orph_out} outcome(s) with no assessment evidence")
        if orph_crit:
            fixes.append(f"{orph_crit} rubric criterion(s) with no upstream outcome")
        return sev, f"{v} (outcomes: {orph_out} orphan · criteria: {orph_crit} orphan)", fixes

    if key == "learning_model":
        v = d.get("learning_model_integration") or d.get("verdict", "?")
        s = d.get("summary", {})
        preset = d.get("preset") or s.get("preset") or "?"
        complete = s.get("modules_complete", 0)
        partial_ct = s.get("modules_partial", 0)
        missing = s.get("modules_missing", 0)
        sev = {"complete": 0, "partial": 1, "unverified": 1}.get(v, 1)
        fixes = []
        if missing:
            fixes.append(f"learning model ({preset}): {missing} module(s) missing all phase markers")
        if partial_ct:
            fixes.append(f"learning model ({preset}): {partial_ct} module(s) with partial phase coverage")
        return sev, f"{v} · preset={preset} ({complete} complete / {partial_ct} partial / {missing} missing)", fixes

    if key == "formative_variety":
        v = d.get("formative_variety") or d.get("verdict", "?")
        s = d.get("summary", {})
        flagged = s.get("flag_count", 0)
        sev = 2 if v == "flags_present" else 0
        fixes = []
        for flag_key, label in (("no_formative_items", "no formative items in the whole course"),
                                ("summative_only_categories", "categories with only summative items"),
                                ("precedence_failures", "summative items lack preceding formative practice"),
                                ("distribution_skew", "formative items skewed across the term")):
            if (d.get("flags") or {}).get(flag_key):
                fixes.append(f"formative variety: {label}")
        return sev, f"{v} ({flagged} flag(s))", fixes

    if key == "grading_structure":
        v = d.get("grading_structure") or d.get("verdict", "?")
        s = d.get("summary", {})
        flagged = s.get("flag_count", 0)
        sev = 2 if v == "flags_present" else 0
        fixes = []
        f = d.get("flags") or {}
        if f.get("sum_not_100"):
            fixes.append("grading weights don't sum to 100%")
        if f.get("weight_mismatches"):
            fixes.append(f"{len(f['weight_mismatches'])} category weight/point mismatch(es)")
        if f.get("over_influence"):
            fixes.append(f"{len(f['over_influence'])} assignment(s) carrying outsized weight")
        if f.get("too_small"):
            fixes.append(f"{len(f['too_small'])} assignment(s) too small to matter")
        if f.get("category_carry"):
            fixes.append(f"{len(f['category_carry'])} category carried by a single assignment")
        if (f.get("temporal_stack") or {}).get("flag"):
            fixes.append("≥40% of points stacked in the last 2 weeks")
        return sev, f"{v} ({flagged} flag(s))", fixes

    if key == "grading_load":
        v = d.get("grading_load") or d.get("verdict", "?")
        s = d.get("summary", {})
        sev = 2 if v == "over_cap" else 0
        fixes = []
        f = d.get("flags") or {}
        over_weeks = f.get("over_cap_weeks") or []
        if over_weeks:
            fixes.append(f"grading load: {len(over_weeks)} week(s) over cap")
        if f.get("cap_overage_mean"):
            fixes.append("grading load: cohort mean exceeds cap (structural overload)")
        return sev, f"{v} (cap={s.get('cap_minutes_per_week', '?')} min/wk)", fixes

    if key == "accessibility":
        v = d.get("accessibility") or d.get("verdict", "?")
        s = d.get("summary", {})
        crit = s.get("critical_count", 0)
        high = s.get("high_count", 0)
        review = s.get("review_count", 0)
        sev_map = {"compliant": 0, "compliant_with_review": 1,
                   "partial_compliant": 2, "non_compliant": 2}
        sev = sev_map.get(v, 1)
        fixes = []
        if crit:
            fixes.append(f"accessibility: {crit} CRITICAL finding(s) (aids WCAG review — see disclaimer)")
        if high:
            fixes.append(f"accessibility: {high} HIGH finding(s)")
        return sev, f"{v} ({crit} crit · {high} high · {review} review)", fixes

    if key == "workload":
        v = d.get("workload") or d.get("verdict", "?")
        s = d.get("summary", {})
        flags = d.get("flags") or []
        sev_map = {"balanced": 0, "sparse": 1, "uneven": 2, "unscheduled": 1}
        sev = sev_map.get(v, 1)
        fixes = []
        if "uneven_distribution" in flags:
            fixes.append("workload: uneven distribution / crunch week(s)")
        if "front_loaded" in flags:
            fixes.append("workload: front-loaded")
        if "back_loaded" in flags:
            fixes.append("workload: back-loaded")
        if "mostly_unscheduled" in flags:
            fixes.append("workload: most items have no due date")
        return sev, f"{v} ({s.get('weeks_with_work', '?')} weeks active)", fixes

    return -1, "unknown specialist", []


_COMBINED = {2: "NEEDS_ATTENTION", 1: "REVIEW", 0: "HEALTHY", -1: "INCOMPLETE"}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render(course_id: str, course_name: str, rows: list[dict], combined: int, ts: str,
            detailed: bool, tier: str) -> list[str]:
    if tier == "full":
        composed = ("Composed (read-only): rubric coverage · rubric quality · syllabus · "
                    "CLO quality · alignment chain · learning model · formative variety · "
                    "grading structure · grading load · accessibility · workload")
    else:
        composed = ("Composed (read-only): rubric coverage · rubric quality · syllabus · "
                    "CLO quality  (run with --full for standards-gap audits + workload)")
    lines = [
        "# Course Health Audit",
        "",
        f"Course:  {course_name} ({course_id})",
        f"Run at:  {ts}",
        f"Tier:    {tier.upper()}",
        composed,
        "",
        "=" * 62,
        "",
        f"Overall: {_GLYPH[combined]} {_COMBINED[combined]}",
        "",
        "Health summary:",
    ]
    for r in rows:
        lines.append(f"  {_GLYPH[r['severity']]} {r['label']:<16} {r['headline']}")
    fixes = [f for r in rows for f in r["fixes"]]
    if fixes:
        lines += ["", "─" * 62, "Top things to fix:"]
        lines += [f"  → {f}" for f in fixes]
    else:
        n = len(rows)
        lines += ["", f"No findings across the {n} audit(s) — course looks healthy."]
    if tier == "full":
        lines += ["",
                  "Note: accessibility audit AIDS WCAG 2.1 AA review; it does NOT certify",
                  "compliance, does NOT guarantee every violation is flagged, and does NOT",
                  "replace assistive-technology testing. Operators retain responsibility."]
    if detailed:
        # Layout-agnostic hint (#35): derive the path from how this tool was actually
        # invoked (relative to cwd), so it copy-pastes correctly whether the repo is a
        # standalone clone (lib/tools/...) or vendored as a subtree (canvas_toolbox/lib/tools/...).
        rel = os.path.relpath(_TOOLS_DIR / "syllabus_audit.py")
        lines += ["", "─" * 62,
                  "Run any specialist directly for full detail, e.g.:",
                  f"  uv run python {rel} --course-id {course_id} --detailed"]
    return lines


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
    ap = argparse.ArgumentParser(
        description="One-command read-only course health audit. QUICK tier (default) "
                    "runs the four core audits; --full adds the standards-gap audits + "
                    "workload (slower; pre-publish / pre-semester).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Env var holding the course ID (default CANVAS_COURSE_ID; "
                         "repo .env ships CANVAS_SANDBOX_ID)")
    ap.add_argument("--course-id", default=None, help="Literal course ID; overrides --target")
    ap.add_argument("--full", action="store_true",
                    help="Run the full sweep: QUICK + alignment chain + learning model + "
                         "formative variety + grading structure + grading load + "
                         "accessibility + workload. Slower; pre-publish health check.")
    ap.add_argument("--detailed", action="store_true", help="Append per-specialist run hints")
    ap.add_argument("--report", default=None, metavar="PATH", help="Write output to PATH")
    ap.add_argument("--json", action="store_true", dest="emit_json", help="Machine-readable JSON")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Forwarded to each specialist (read-only; advisory guard).")
    args = ap.parse_args()

    course_id, source = _resolve_course_id(args.target, args.course_id)
    if not course_id:
        print(f"ERROR: course ID not found via {source}. Pass --course-id <id>.")
        sys.exit(2)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tier = "full" if args.full else "quick"
    roster = QUICK_SPECIALISTS + (FULL_EXTRA_SPECIALISTS if args.full else [])

    raw: dict[str, dict | None] = {}
    rows: list[dict] = []
    course_name = "<unknown course>"
    for key, tool_file, label, json_flag in roster:
        d = run_specialist(tool_file, course_id, args.allow_enrolled, json_flag)
        raw[key] = d
        # Two course-name shapes in the wild: nested {course: {name}} (older
        # audits) and flat course_name (newer standards-gap audits).
        if d:
            cobj = d.get("course")
            if isinstance(cobj, dict) and cobj.get("name"):
                course_name = cobj["name"]
            elif d.get("course_name"):
                course_name = d["course_name"]
        sev, headline, fixes = _headline(key, d)
        rows.append({"key": key, "label": label, "severity": sev,
                     "headline": headline, "fixes": fixes})

    if all(r["severity"] == -1 for r in rows):
        print(f"\nNo specialist could run for course {course_id} — check "
              "CANVAS_API_TOKEN / CANVAS_BASE_URL and the course id.", file=sys.stderr)
        sys.exit(2)

    combined = max((r["severity"] for r in rows if r["severity"] >= 0), default=-1)

    if args.emit_json:
        payload = {
            "tool": "course_audit", "tool_version": __version__, "run_at": ts,
            "tier": tier,
            "course": {"id": course_id, "name": course_name},
            "overall": _COMBINED[combined],
            "specialists": {
                r["key"]: {"severity": _GLYPH[r["severity"]], "headline": r["headline"],
                           "fixes": r["fixes"], "raw": raw[r["key"]]}
                for r in rows
            },
        }
        out = json.dumps(payload, indent=2, ensure_ascii=False)
        print(out)
        if args.report:
            _write_report(Path(args.report), out)
    else:
        lines = _render(course_id, course_name, rows, combined, ts, args.detailed, tier)
        print("\n".join(lines))
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    sys.exit(0 if combined == 0 else 1)


if __name__ == "__main__":
    main()

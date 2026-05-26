#!/usr/bin/env python3
"""
course_audit.py — one-command course health audit (read-only orchestrator).

Composes the four read-only audit tools into a single pre-semester health check:
  - rubric_coverage_audit  — which assignments lack/has/decorative rubrics
  - rubric_quality_audit   — are the rubrics well-formed (backbone meta-rubric)
  - syllabus_audit         — is the syllabus complete (+ required AI policy)
  - clo_quality_audit      — are the course outcomes well-written (AoL rubric)

This is a TOOL-SIDE orchestrator. It follows the `make_orchestrator_agent` skill's
core principles at the tool layer (see make-ai-agents/make_orchestrator_agent.md):
  - **Specialists are decoupled, referenced by path.** Each audit is invoked as a
    sealed subprocess via its own `--json` contract — never reimplemented or inlined.
    Every specialist stays fully usable standalone.
  - **Composition is visible.** Each specialist's verdict is surfaced and rolled up
    into one health summary + a single "top things to fix" list; no hidden logic.
The agent-LAYER orchestrator is `canvas_course_expert` (which reasons over these same
knowledge files); this tool is the deterministic, scriptable composition of the audits.

Combined verdict (rollup of the four):
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
# Specialist roster: (key, tool filename, human label). Referenced by PATH — decoupled.
SPECIALISTS = [
    ("rubric_coverage", "rubric_coverage_audit.py", "Rubric coverage"),
    ("rubric_quality",  "rubric_quality_audit.py",  "Rubric quality"),
    ("syllabus",        "syllabus_audit.py",        "Syllabus"),
    ("clo_quality",     "clo_quality_audit.py",     "CLO quality"),
]


# ---------------------------------------------------------------------------
# Specialist invocation (the "delegate_to_*" analog — sealed --json subprocess)
# ---------------------------------------------------------------------------

def run_specialist(tool_file: str, course_id: str, allow_enrolled: bool) -> dict | None:
    """Invoke one audit tool with --course-id --json and return its parsed JSON.
    Returns None if the specialist produced no parseable JSON. The audit tools
    exit non-zero when they HAVE findings (1) or can't run (2) — that's expected,
    so we parse stdout regardless of exit code."""
    cmd = [sys.executable, str(_TOOLS_DIR / tool_file),
           "--course-id", course_id, "--json"]
    if allow_enrolled:
        cmd.append("--allow-enrolled")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
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

    return -1, "unknown specialist", []


_COMBINED = {2: "NEEDS_ATTENTION", 1: "REVIEW", 0: "HEALTHY", -1: "INCOMPLETE"}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render(course_id: str, course_name: str, rows: list[dict], combined: int, ts: str,
            detailed: bool) -> list[str]:
    lines = [
        "# Course Health Audit",
        "",
        f"Course:  {course_name} ({course_id})",
        f"Run at:  {ts}",
        "Composed (read-only): rubric coverage · rubric quality · syllabus · CLO quality",
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
        lines += ["", "No findings across the four audits — course looks healthy."]
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
        description="One-command read-only course health audit (orchestrates the four "
                    "audit tools into a single report).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Env var holding the course ID (default CANVAS_COURSE_ID; "
                         "repo .env ships CANVAS_SANDBOX_ID)")
    ap.add_argument("--course-id", default=None, help="Literal course ID; overrides --target")
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

    raw: dict[str, dict | None] = {}
    rows: list[dict] = []
    course_name = "<unknown course>"
    for key, tool_file, label in SPECIALISTS:
        d = run_specialist(tool_file, course_id, args.allow_enrolled)
        raw[key] = d
        if d and isinstance(d.get("course"), dict) and d["course"].get("name"):
            course_name = d["course"]["name"]
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
        lines = _render(course_id, course_name, rows, combined, ts, args.detailed)
        print("\n".join(lines))
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    sys.exit(0 if combined == 0 else 1)


if __name__ == "__main__":
    main()

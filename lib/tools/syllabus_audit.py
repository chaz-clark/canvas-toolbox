#!/usr/bin/env python3
"""
syllabus_audit.py — read-only syllabus completeness audit.

Fetches a Canvas course's syllabus body and audits it for completeness against
the BYU-Idaho syllabus template (the harvested standard), plus the now-required
generative-AI policy. READ-ONLY: never writes to Canvas.

It answers: "Does this syllabus contain the sections a student needs, and does
it state an AI policy?" It does NOT judge prose quality — tone, clarity, and
'is each outcome actually assessed' are human judgments, surfaced as advisory
data (see ADVISORY below), never as a pass/fail.

Detection is keyword-heuristic on the syllabus HTML (stripped to text). A
section can legitimately exist under a heading we didn't anticipate, so a
"not detected" result means *review*, not proven-absent. Findings are framed
that way on purpose (evidence-based stance, matching rubric_quality_audit.py).

REQUIRED sections (BYU-Idaho template → byui_syllabus_guidance.md). Each
umbrella section is detected via an OR over its subsection keywords:
  1. Instructor Contact Information
  2. Overview               (Description / Outcomes / Vision)
  3. Requirements           (Prerequisites / Materials / Technology / AI Policy)
  4. Structure              (Learning Model / Key Assessments)   [BYUI-flavored]
  5. Expectations           (Feedback / Workload)
  6. Grading                (Grading Scale / Late Work)
  7. Students with Disabilities
  8. University Policies
  9. Disclaimers

REQUIRED GATE (separate first-class check):
  - AI Policy present — BYUI now REQUIRES every syllabus to state a generative-AI
    policy ("every course syllabus must include a statement about generative AI
    use" — byui_ai_hub.md / byui.edu/ai/academics/ai-in-the-syllabus). Detected
    independently of the Requirements umbrella so it can drive the verdict.

ADVISORY signals (reported as data, do NOT affect the verdict):
  - ai_framework      — which AI framework the policy uses, if detectable
                        (Stoplight RED/YELLOW/GREEN; AI Assessment Scale levels)
  - outcomes_present  — are course outcomes stated in the syllabus text
  - learning_model    — is the BYU-I Learning Model introduced (BYUI-specific)
  - word_count / bloat — very long syllabi risk "syllabus bloat" (pitfall #1);
                         very short bodies may mean the real syllabus is a linked
                         page/file the API can't see here.

Verdict (driven only by the deterministic, defensible checks):
  - complete    — all 9 required sections detected AND an AI policy detected
  - incomplete  — one or more required sections (or the AI policy) not detected
  - no_syllabus — syllabus_body empty/near-empty (nothing to audit; likely a
                  linked page/file instead)

Endpoint used (GET, read-only):
  GET /courses/:id?include[]=syllabus_body   (the syllabus HTML lives here)

Exit codes:
  0  complete
  1  incomplete (something required not detected)
  2  configuration error / no syllabus body to audit

Usage:
  uv run python canvas_toolbox/lib/tools/syllabus_audit.py --target CANVAS_SANDBOX_ID
  uv run python canvas_toolbox/lib/tools/syllabus_audit.py --course-id 12345
  uv run python canvas_toolbox/lib/tools/syllabus_audit.py --course-id 12345 --detailed
  uv run python canvas_toolbox/lib/tools/syllabus_audit.py --course-id 12345 --json
  uv run python canvas_toolbox/lib/tools/syllabus_audit.py --course-id 12345 --report syllabus.md

Requires in .env:
  CANVAS_API_TOKEN, CANVAS_BASE_URL, and the env var named by --target
  (default CANVAS_COURSE_ID; .env here ships CANVAS_SANDBOX_ID).

Reads (knowledge grounding):
  pre_knowledge/byui_learning_teaching/byui_syllabus_guidance.md (9 required sections)
  pre_knowledge/byui_learning_teaching/byui_ai_hub.md            (AI policy = required)
  knowledge/canvas_api_lessons_learned.md (P-LL4 advisory guard on reads)

Institutional neutrality (AGENTS.md rule): the section checklist is the BYU-Idaho
template profile. The Learning-Model and Vision signals are BYUI-specific and are
flagged as such; the rest (instructor contact, outcomes, materials, grading, late
work, disability/accessibility, university policies, AI policy) are broadly general.
"""

from __future__ import annotations

import argparse
import html
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
# Normalize the base URL: the .env convention is scheme-less (e.g.
# "byui.instructure.com"), but requests needs a scheme. Match canvas_sync.py.
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url

_TIMEOUT = 30
# Below this many words of real syllabus text we treat the body as effectively
# empty — the real syllabus is almost certainly a linked page/file we can't see.
_MIN_BODY_WORDS = 25


# ---------------------------------------------------------------------------
# API helpers (style matches rubric_coverage_audit / canvas_pages)
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(endpoint: str, params: dict | None = None) -> list | dict | None:
    """Single GET (no pagination needed for a course object). Returns parsed
    JSON or None on any HTTP 4xx/5xx or network error."""
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    try:
        resp = requests.get(url, headers=_headers(),
                            params={**(params or {})}, timeout=_TIMEOUT)
    except Exception:
        return None
    if resp.status_code >= 400:
        return None
    try:
        return resp.json()
    except Exception:
        return None


def fetch_syllabus(course_id: str) -> tuple[str, str | None]:
    """Return (course_name, syllabus_body_html). syllabus_body is None if the
    course fetch failed; '' (empty string) if the course exists but has no body."""
    course = _get(f"/courses/{course_id}", {"include[]": "syllabus_body"})
    if not isinstance(course, dict):
        return "<unknown course>", None
    name = (course.get("name") or "").strip() or "<unknown course>"
    body = course.get("syllabus_body")
    return name, ("" if body is None else str(body))


# ---------------------------------------------------------------------------
# HTML → text
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def html_to_text(body: str) -> str:
    """Strip tags + unescape entities + collapse whitespace, lowercased.
    Good enough for keyword detection; not a parser."""
    if not body:
        return ""
    # Drop script/style blocks wholesale before stripping tags.
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body,
                  flags=re.IGNORECASE | re.DOTALL)
    text = _TAG_RE.sub(" ", body)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    return text.lower().strip()


def word_count(text: str) -> int:
    return len(text.split()) if text else 0


# ---------------------------------------------------------------------------
# Section + signal detection
# ---------------------------------------------------------------------------

# Each required umbrella section: key, human label, detection patterns (any
# match => detected), and whether it's BYUI-specific in flavor.
# Patterns are lowercase substrings tested against the stripped syllabus text.
REQUIRED_SECTIONS: list[dict] = [
    {"key": "instructor_contact", "label": "Instructor Contact Information",
     "patterns": ["office hour", "contact information", "instructor contact",
                  "instructor information", "instructor:", "email:", "e-mail:",
                  "office location"], "byui": False},
    {"key": "overview", "label": "Overview (Description / Outcomes / Vision)",
     "patterns": ["course description", "catalog description", "course overview",
                  "learning outcome", "course outcome", "course objective",
                  "learning objective"], "byui": False},
    {"key": "requirements", "label": "Requirements (Materials / Prereqs / Tech / AI)",
     "patterns": ["required text", "textbook", "course materials",
                  "required materials", "required reading", "isbn",
                  "prerequisite", "technology requirement"], "byui": False},
    {"key": "structure", "label": "Structure (Learning Model / Key Assessments)",
     "patterns": ["learning model", "key assessment", "major assignment",
                  "course structure", "weekly pattern", "how the course"],
     "byui": True},
    {"key": "expectations", "label": "Expectations (Feedback / Workload)",
     "patterns": ["feedback", "workload", "time commitment", "hours per week",
                  "expect to spend", "expectations"], "byui": False},
    {"key": "grading", "label": "Grading (Grading Scale / Late Work)",
     "patterns": ["grading scale", "grade scale", "grading policy",
                  "grade breakdown", "letter grade", "late work", "late policy",
                  "points possible"], "byui": False},
    {"key": "disabilities", "label": "Students with Disabilities",
     "patterns": ["disabilit", "accommodation", "accessibility", "section 504",
                  "ada ", "americans with disabilities"], "byui": False},
    {"key": "university_policies", "label": "University Policies",
     "patterns": ["university policies", "university policy", "academic honesty",
                  "academic integrity", "honor code", "title ix",
                  "student honor"], "byui": False},
    {"key": "disclaimers", "label": "Disclaimers",
     "patterns": ["disclaimer", "subject to change", "syllabus is subject",
                  "reserve the right", "may be modified", "subject to revision"],
     "byui": False},
]

# AI policy — the required gate (detected independently of Requirements).
_AI_POLICY_PATTERNS = [
    "artificial intelligence", "generative ai", "gen ai", "genai",
    "chatgpt", "copilot", "ai tool", "ai use", "ai policy", "use of ai",
    "ai-generated", "ai generated", "large language model", "llm",
]

# AI framework signals (advisory). Stoplight = R/Y/G posture; AI Assessment
# Scale = the 5-level gradient. Best-effort.
_AI_FRAMEWORK_SIGNALS: list[tuple[str, list[str]]] = [
    ("Stoplight Framework", ["stoplight", "red light", "green light",
                              "yellow light", "red/yellow/green"]),
    ("AI Assessment Scale", ["ai for ideas", "ai for feedback", "ai for content",
                              "ai-led", "ai led", "assessment scale"]),
]

# Outcomes / Learning-Model signals (advisory data).
_OUTCOMES_PATTERNS = ["learning outcome", "course outcome", "student learning outcome",
                      "course objective", "learning objective"]
_LEARNING_MODEL_PATTERNS = ["learning model", "prepare, teach", "teach one another",
                            "ponder and prove", "byu-i learning model",
                            "byui learning model", "prepare-teach"]

# Syllabus-bloat advisory threshold (pitfall #1). Not a failure — a flag.
_BLOAT_WORDS = 4000


def _any(text: str, patterns: list[str]) -> bool:
    return any(p in text for p in patterns)


def detect_sections(text: str) -> list[dict]:
    """Return each required section with a `detected` bool."""
    out = []
    for spec in REQUIRED_SECTIONS:
        out.append({
            "key": spec["key"],
            "label": spec["label"],
            "byui": spec["byui"],
            "detected": _any(text, spec["patterns"]),
        })
    return out


def detect_ai_policy(text: str) -> dict:
    """The required AI-policy gate + advisory framework detection."""
    present = _any(text, _AI_POLICY_PATTERNS)
    frameworks = [name for name, pats in _AI_FRAMEWORK_SIGNALS if _any(text, pats)]
    return {"present": present, "frameworks": frameworks}


def detect_advisory(text: str) -> dict:
    wc = word_count(text)
    return {
        "word_count": wc,
        "bloat": wc > _BLOAT_WORDS,
        "outcomes_present": _any(text, _OUTCOMES_PATTERNS),
        "learning_model_present": _any(text, _LEARNING_MODEL_PATTERNS),
    }


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

COMPLETE = "complete"
INCOMPLETE = "incomplete"
NO_SYLLABUS = "no_syllabus"


def compute_verdict(sections: list[dict], ai_policy: dict,
                    body_words: int) -> tuple[str, list[str]]:
    """Verdict + the list of human-readable missing items driving it."""
    if body_words < _MIN_BODY_WORDS:
        return NO_SYLLABUS, [
            "Syllabus body is empty or near-empty — the real syllabus is likely "
            "a linked Canvas page or file the syllabus_body field doesn't contain."
        ]
    missing = [s["label"] for s in sections if not s["detected"]]
    if not ai_policy["present"]:
        missing.append("AI Policy (REQUIRED — no generative-AI statement detected)")
    return (COMPLETE if not missing else INCOMPLETE), missing


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_VERDICT_GLYPH = {COMPLETE: "✅", INCOMPLETE: "🔴", NO_SYLLABUS: "⚪"}


def _render(course_id: str, course_name: str, verdict: str, missing: list[str],
            sections: list[dict], ai_policy: dict, advisory: dict,
            detailed: bool, ts: str) -> list[str]:
    detected_n = sum(1 for s in sections if s["detected"])
    lines = [
        "# Syllabus Audit",
        "",
        f"Course:  {course_name} ({course_id})",
        f"Run at:  {ts}",
        "",
        "=" * 62,
        "",
        f"Verdict: {_VERDICT_GLYPH[verdict]} {verdict.upper()}",
        f"Required sections detected: {detected_n}/{len(sections)}",
        f"AI policy detected: {'yes' if ai_policy['present'] else 'NO (required)'}",
        "",
    ]

    if verdict == NO_SYLLABUS:
        lines.append(missing[0])
        lines.append("")
        lines.append("Heuristic note: this audit only sees the course's "
                     "syllabus_body field. If your syllabus is a Page or an "
                     "uploaded file, point students there — but the completeness "
                     "checks below can't run on it.")
        return lines

    lines.append("Required sections (keyword-detected — 'not detected' means "
                 "review, not proven-absent):")
    for s in sections:
        glyph = "✅" if s["detected"] else "🔴"
        tag = "  [BYUI]" if s["byui"] else ""
        lines.append(f"  {glyph} {s['label']}{tag}")
    lines.append("")

    # AI policy block (the required gate)
    lines.append("AI policy (REQUIRED — byui.edu/ai: every syllabus must state one):")
    if ai_policy["present"]:
        fw = (", ".join(ai_policy["frameworks"])
              if ai_policy["frameworks"] else "framework not identified")
        lines.append(f"  ✅ AI statement detected ({fw})")
    else:
        lines.append("  🔴 No generative-AI statement detected — this is a "
                     "required element. Add one (Stoplight or AI Assessment "
                     "Scale framework recommended).")
    lines.append("")

    # Advisory block (does NOT affect verdict)
    lines.append("Advisory signals (data only — not part of the verdict):")
    lines.append(f"  • Word count: {advisory['word_count']}"
                 + ("  ⚠️ possible syllabus bloat (pitfall #1)"
                    if advisory["bloat"] else ""))
    lines.append(f"  • Course outcomes stated: "
                 f"{'yes' if advisory['outcomes_present'] else 'not detected'}")
    lines.append(f"  • BYU-I Learning Model introduced: "
                 f"{'yes' if advisory['learning_model_present'] else 'not detected'}"
                 "  [BYUI]")
    lines.append("")

    if missing:
        lines.append("─" * 62)
        lines.append("To reach COMPLETE, add / make detectable:")
        for m in missing:
            lines.append(f"  → {m}")

    if detailed:
        lines.append("")
        lines.append("─" * 62)
        lines.append("Detection is substring-keyword on the stripped syllabus "
                     "text. If a section IS present under a heading we didn't "
                     "match, treat the flag as a false negative and move on.")
    return lines


def _render_json(course_id: str, course_name: str, verdict: str,
                 missing: list[str], sections: list[dict], ai_policy: dict,
                 advisory: dict, ts: str) -> dict:
    return {
        "tool": "syllabus_audit",
        "tool_version": __version__,
        "run_at": ts,
        "course": {"id": course_id, "name": course_name},
        "verdict": verdict,
        "required_sections": sections,
        "required_detected": sum(1 for s in sections if s["detected"]),
        "required_total": len(sections),
        "ai_policy": ai_policy,
        "advisory": advisory,
        "missing": missing,
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
        description="Read-only Canvas syllabus completeness audit (BYU-Idaho "
                    "template + required AI policy)."
    )
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Env var holding the course ID (default CANVAS_COURSE_ID; "
                         "this repo's .env ships CANVAS_SANDBOX_ID)")
    ap.add_argument("--course-id", default=None,
                    help="Literal course ID; overrides --target if set")
    ap.add_argument("--detailed", action="store_true",
                    help="Append the detection-method caveat to the report")
    ap.add_argument("--report", default=None, metavar="PATH",
                    help="Write output to PATH (markdown unless --json)")
    ap.add_argument("--json", action="store_true", dest="emit_json",
                    help="Emit machine-readable JSON to stdout (and to --report "
                         "if set)")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="(Read-only tool; safety guard is advisory only. "
                         "Accepted for symmetry with write tools.)")
    args = ap.parse_args()

    missing_cfg: list[str] = []
    if not CANVAS_BASE_URL or CANVAS_BASE_URL == "https://":
        missing_cfg.append("CANVAS_BASE_URL")
    if not CANVAS_API_TOKEN:
        missing_cfg.append("CANVAS_API_TOKEN")
    if missing_cfg:
        print("ERROR: Missing required configuration:")
        for m in missing_cfg:
            print(f"  {m}")
        print("\nSet these in your .env file.")
        sys.exit(2)

    course_id, source = _resolve_course_id(args.target, args.course_id)
    if not course_id:
        print(f"ERROR: course ID not found via {source}.")
        print("       Set the env var, or pass --course-id <id> directly.")
        sys.exit(2)

    guard.enforce(
        base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
        mode="read", allow_override=args.allow_enrolled, label="audit target",
    )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    course_name, body = fetch_syllabus(course_id)
    if body is None:
        print(f"\nCould not fetch course {course_id} (or the request failed).",
              file=sys.stderr)
        sys.exit(2)

    text = html_to_text(body)
    body_words = word_count(text)
    sections = detect_sections(text)
    ai_policy = detect_ai_policy(text)
    advisory = detect_advisory(text)
    verdict, missing = compute_verdict(sections, ai_policy, body_words)

    if args.emit_json:
        payload = _render_json(course_id, course_name, verdict, missing,
                               sections, ai_policy, advisory, ts)
        out = json.dumps(payload, indent=2, ensure_ascii=False)
        print(out)
        if args.report:
            _write_report(Path(args.report), out)
    else:
        lines = _render(course_id, course_name, verdict, missing, sections,
                        ai_policy, advisory, args.detailed, ts)
        for line in lines:
            print(line)
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    sys.exit(0 if verdict == COMPLETE else
             (2 if verdict == NO_SYLLABUS else 1))


if __name__ == "__main__":
    main()

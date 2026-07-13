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

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
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
from syllabus_outcomes import detect_outcomes_section

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
# Normalize the base URL: the .env convention is scheme-less (e.g.
# "byui.instructure.com"), but requests needs a scheme. Match canvas_sync.py.
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url


def default_institution() -> str:
    """Institution profile (keeps the audit college-agnostic). CANVAS_INSTITUTION
    wins; else infer from the Canvas host (byui.instructure.com -> 'byui'); else
    'generic'. Only the BYUI profile REQUIRES a generative-AI policy for a
    'complete' verdict — other institutions treat it as advisory."""
    inst = os.environ.get("CANVAS_INSTITUTION", "").strip().lower()
    if inst:
        return inst
    return "byui" if "byui" in (CANVAS_BASE_URL or "").lower() else "generic"


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

# Outcomes presence is detected DOM-aware via the shared syllabus_outcomes
# parser (issue #31 — one parser, all tools agree). Learning-Model is a simple
# keyword signal (BYUI-specific advisory).
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


# ---------------------------------------------------------------------------
# 25-item Syllabus Completeness Rubric (v0.31 — knowledge file v0.2)
# ---------------------------------------------------------------------------
# Source: BYU-I Academic Office Syllabus Completeness Rubric (2026), transcribed
# at lib/agents/templates/syllabus_completeness_rubric.md.
#
# Each item has detection patterns. Some items ALSO check link-presence
# (`url_patterns`) — a syllabus that says "see the FERPA page" without a link
# scores lower than one that includes the URL.
#
# Honest limit: detection scores 0 vs ≥1 reliably. The rubric's 1-vs-2
# distinction ("thin/uneven" vs "complete and clear") is a human-judgment
# call this audit does NOT auto-assign — operator scores final 0/1/2.

RUBRIC_ITEMS: list[dict] = [
    # Course Information (5)
    {"cat": "Course Information", "key": "title",
     "label": "Course Title is present",
     "patterns": ["course title", "course:"]},
    {"cat": "Course Information", "key": "code",
     "label": "Course Code is present",
     "patterns": [r"\b[a-z]{2,4}\s*\d{3}\b", "course code", "course id"]},
    {"cat": "Course Information", "key": "credits",
     "label": "Course Credits is present",
     "patterns": [r"\b\d+\s*credit", "credit hour", "credits:", r"credits\s*=\s*\d"]},
    {"cat": "Course Information", "key": "semester_year",
     "label": "Specific semester/year (if on-campus) is present",
     "patterns": [r"(spring|summer|fall|winter)\s+20\d\d", "semester:", "term:"]},
    {"cat": "Course Information", "key": "prerequisites",
     "label": "Prerequisites is present or none are noted",
     "patterns": ["prerequisit", "prereq", "no prerequisite"]},
    # Course Description (1)
    {"cat": "Course Description", "key": "description",
     "label": "Course description matches what is in the catalog",
     "patterns": ["course description", "catalog description", "description:"]},
    # Course Outcomes (1)
    {"cat": "Course Outcomes", "key": "outcomes",
     "label": "Course Outcomes match what is in the catalog",
     "patterns": ["learning outcome", "course outcome", "by the end of",
                  "course objective"]},
    # Materials (1)
    {"cat": "Materials", "key": "materials",
     "label": "Required/recommended textbooks, software, or equipment are identified",
     "patterns": ["textbook", "required materials", "required reading", "software",
                  "equipment", "isbn"]},
    # Grading and Assessments (4)
    {"cat": "Grading and Assessments", "key": "weighting",
     "label": "Weighting of assignments is present (if applicable)",
     "patterns": ["weighting", "% of grade", "percent of grade", "grade breakdown",
                  "points toward", "weight:"]},
    {"cat": "Grading and Assessments", "key": "grading_scale",
     "label": "Grading scale is present (if applicable)",
     "patterns": ["grading scale", "grade scale", "letter grade", r"a\s*=\s*9",
                  "grade thresh"]},
    {"cat": "Grading and Assessments", "key": "exams",
     "label": "Exams is present (if applicable)",
     "patterns": ["exam", "midterm", "final exam"]},
    {"cat": "Grading and Assessments", "key": "projects",
     "label": "Projects is present (if applicable)",
     "patterns": ["project", "capstone", "presentation"]},
    # Main Course Assignments (1)
    {"cat": "Main Course Assignments", "key": "main_assignments",
     "label": "Topics covered, major experiences, or how-students-will-achieve descriptions are present",
     "patterns": ["topics covered", "main assignment", "major assignment",
                  "course experience", "how students will", "reading assignment"]},
    # Expectations (2)
    {"cat": "Expectations", "key": "workload",
     "label": "Workload is clarified",
     "patterns": ["workload", "hours per week", "expect to spend", "time commitment",
                  "estimated time"]},
    {"cat": "Expectations", "key": "attendance",
     "label": "Attendance policy is present",
     "patterns": ["attendance", "absent", "absence policy"]},
    # AI Usage (1 — but composite: policy + right-to-modify + tips)
    {"cat": "AI Usage", "key": "ai_usage",
     "label": "AI policy + 'right to modify' clause + tips for success",
     "patterns": ["ai policy", "ai tool", "ai use", "generative ai",
                  "artificial intelligence", "use of ai"]},
    # Additional Information (1)
    {"cat": "Additional Information", "key": "addl_info",
     "label": "Link to a page with additional information is present, if applicable",
     "patterns": ["additional information", "addendum", "additional resource",
                  "more information"]},
    # University Statements & Policies (9)
    {"cat": "University Statements & Policies", "key": "personal_challenges",
     "label": "Personal Challenges statement is present",
     "patterns": ["personal challenges", "dean of students office",
                  "988 hotline", "9-8-8", "counseling center",
                  "if you experience a crisis"]},
    {"cat": "University Statements & Policies", "key": "disabilities",
     "label": "Accommodations for Students with Disabilities statement is present",
     "patterns": ["accommodations", "accessibility services", "qualified persons with disabilities",
                  "disability"]},
    {"cat": "University Statements & Policies", "key": "sexual_harassment",
     "label": "Sexual Harassment statement is present",
     "patterns": ["sexual harassment", "title ix coordinator", "titleix@byui.edu",
                  "title ix"]},
    {"cat": "University Statements & Policies", "key": "grievance_link",
     "label": "Link to Student Grievance page is present",
     "patterns": ["student grievance", "grievance"],
     "url_patterns": ["byui.edu/student-records/grievance", "grievance"]},
    {"cat": "University Statements & Policies", "key": "honor_code_link",
     "label": "Link to CES Honor Code page is present",
     "patterns": ["ces honor code", "honor code", "church education system"],
     "url_patterns": ["churchofjesuschrist.org", "byui.edu/honor"]},
    {"cat": "University Statements & Policies", "key": "academic_honesty_link",
     "label": "Link to Academic Honesty page is present",
     "patterns": ["academic honesty", "academic integrity"],
     "url_patterns": ["byui.edu/student-honor-office/academic-integrity",
                       "byui.edu/academic"]},
    {"cat": "University Statements & Policies", "key": "ferpa_link",
     "label": "Link to FERPA page is present",
     "patterns": ["ferpa", "family educational rights"],
     "url_patterns": ["byui.edu/student-records/ferpa", "ferpa"]},
    {"cat": "University Statements & Policies", "key": "policy_library_link",
     "label": "Link to Policy Library is present",
     "patterns": ["policy library", "byu-idaho policy library"],
     "url_patterns": ["byui.edu/policies", "policies"]},
    {"cat": "University Statements & Policies", "key": "copyright",
     "label": "Copyright disclaimer is present",
     "patterns": ["copyright", "title 17", "u.s. copyright law",
                  "byui.edu/copyright"]},
]


def _has_link(raw_html: str, url_patterns: list[str]) -> bool:
    """Check whether the raw HTML contains an <a href=...> matching any URL pattern."""
    if not raw_html or not url_patterns:
        return False
    # Find all href values
    hrefs = re.findall(r'href\s*=\s*["\']([^"\']+)["\']', raw_html, re.IGNORECASE)
    if not hrefs:
        return False
    for href in hrefs:
        href_l = href.lower()
        for pat in url_patterns:
            if pat.lower() in href_l:
                return True
    return False


def detect_rubric_items(text: str, raw_html: str) -> list[dict]:
    """Score each of the 25 rubric items.

    For each item:
      - `detected` = True if any keyword pattern fires in the stripped text
      - `link_present` = True if the item has url_patterns AND an <a href=> matches
      - `score_signal` = 0 (not detected), 1 (detected, no link or N/A), 2 (detected + link)

    Honest limit: the 1-vs-2 distinction the rubric makes ("thin" vs "complete")
    is partially captured by link_present for link items. For prose items
    (statements, descriptions), the audit only scores 0 vs ≥1 — the operator
    refines 1 vs 2 by hand.
    """
    out = []
    for item in RUBRIC_ITEMS:
        detected_count = 0
        for pat in item["patterns"]:
            try:
                # Try regex first; if it fails, fall back to substring
                if any(c in pat for c in r"\^$*+?{}[]|()"):
                    detected_count += len(re.findall(pat, text, re.IGNORECASE))
                else:
                    detected_count += text.count(pat)
            except re.error:
                detected_count += text.count(pat)
        url_patterns = item.get("url_patterns")
        link_present = _has_link(raw_html, url_patterns) if url_patterns else None

        # Heuristic score signal:
        #   0 = not detected
        #   1 = detected once (possibly thin) OR detected w/o link when link is required
        #   2 = detected ≥2 times (likely complete) OR detected + link for link items
        if detected_count == 0:
            signal = 0
        elif url_patterns:
            # Link item: needs both keyword AND href
            signal = 2 if link_present else 1
        else:
            # Prose item: 1+ mention = at least present
            signal = 2 if detected_count >= 2 else 1

        out.append({
            "category": item["cat"],
            "key": item["key"],
            "label": item["label"],
            "detected_count": detected_count,
            "link_present": link_present,
            "score_signal": signal,
        })
    return out


def _render_rubric(course_id: str, course_name: str, items: list[dict],
                   ts: str) -> list[str]:
    """Rubric-style output: per-item score signal + category totals + reflection prompts."""
    lines = [
        "# Syllabus Completeness Rubric — Audit",
        "",
        f"Course:  {course_name} ({course_id})",
        f"Run at:  {ts}",
        "",
        "Scoring signal (heuristic — operator refines):",
        "  ✅ 2  — detected + (link present for link items, or multiple mentions)",
        "  ⚠️ 1  — detected once OR detected without link for link items",
        "  🔴 0  — not detected",
        "",
        "Honest limit: a keyword detector cannot reliably distinguish 1 (thin) from",
        "2 (complete and clear). The signal below is detection-based; operator",
        "judgment refines 1 vs 2 by reading the actual text.",
        "",
        "=" * 62,
        "",
    ]

    # Group by category, render table
    by_cat: dict[str, list[dict]] = {}
    for it in items:
        by_cat.setdefault(it["category"], []).append(it)

    total_score = 0
    total_max = 0
    glyph_for = {0: "🔴 0", 1: "⚠️ 1", 2: "✅ 2"}

    for cat, cat_items in by_cat.items():
        lines.append(f"## {cat}")
        lines.append("")
        lines.append("| Item | Score | Detected | Link |")
        lines.append("|---|---|---|---|")
        for it in cat_items:
            score = it["score_signal"]
            total_score += score
            total_max += 2
            link_str = ("✓ link" if it["link_present"] else "no link") if it["link_present"] is not None else "—"
            det_str = str(it["detected_count"]) if it["detected_count"] > 0 else "0"
            lines.append(f"| {it['label']} | {glyph_for[score]} | {det_str} mention(s) | {link_str} |")
        lines.append("")

    lines.append("=" * 62)
    pct = (100 * total_score / total_max) if total_max else 0
    lines.append(f"**TOTAL signal: {total_score} / {total_max}  ({pct:.0f}%)**")
    lines.append("")
    lines.append("(Maximum is 50 if all 25 items are applicable. Use N/A in operator")
    lines.append("review for items that don't apply, then recompute.)")
    lines.append("")
    lines.append("─" * 62)
    lines.append("Reflection prompts (rubric):")
    lines.append("  1. Which 2–3 sections of your syllabus need the most attention?")
    lines.append("  2. Which items could be improved quickly?")
    lines.append("  3. What updates will make the syllabus more helpful and clear for students?")
    lines.append("")
    return lines


def detect_ai_policy(text: str) -> dict:
    """The required AI-policy gate + advisory framework detection."""
    present = _any(text, _AI_POLICY_PATTERNS)
    frameworks = [name for name, pats in _AI_FRAMEWORK_SIGNALS if _any(text, pats)]
    return {"present": present, "frameworks": frameworks}


def detect_advisory(text: str, body: str) -> dict:
    wc = word_count(text)
    return {
        "word_count": wc,
        "bloat": wc > _BLOAT_WORDS,
        # DOM-aware, shared with rubric_quality_audit / rubric_recommender (#31):
        # detects the outcomes SECTION (heading/stem), not a bare keyword hit.
        "outcomes_present": detect_outcomes_section(body) is not None,
        "learning_model_present": _any(text, _LEARNING_MODEL_PATTERNS),
    }


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

COMPLETE = "complete"
INCOMPLETE = "incomplete"
NO_SYLLABUS = "no_syllabus"


def compute_verdict(sections: list[dict], ai_policy: dict,
                    body_words: int, ai_policy_required: bool = True) -> tuple[str, list[str]]:
    """Verdict + the list of human-readable missing items driving it.

    ai_policy_required is a per-institution profile knob: the BYUI profile
    REQUIRES a generative-AI statement (drives the verdict); other institutions
    treat it as advisory (reported but not verdict-driving)."""
    if body_words < _MIN_BODY_WORDS:
        return NO_SYLLABUS, [
            "Syllabus body is empty or near-empty — the real syllabus is likely "
            "a linked Canvas page or file the syllabus_body field doesn't contain."
        ]
    missing = [s["label"] for s in sections if not s["detected"]]
    if ai_policy_required and not ai_policy["present"]:
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


try:
    from _canvas_mode import is_offline_mode as _is_offline
except ImportError:
    def _is_offline() -> bool:
        return False


def main() -> None:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

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
    ap.add_argument("--rubric", action="store_true",
                    help="Emit the 25-item Syllabus Completeness Rubric score "
                         "instead of (or in addition to) the 9-section summary. "
                         "Scores 0/1/2 per item with link-presence detection. "
                         "Use with --detailed to keep the umbrella audit too.")
    ap.add_argument("--local", action="store_true",
                    help="Read the local course/ folder (canvas_sync --pull / offline_import) "
                         "instead of the Canvas API. Auto-on when CANVAS_MODE=offline.")
    ap.add_argument("--course-dir", default=None,
                    help="Local course/ directory to read (implies --local). Default: course")
    ap.add_argument("--institution", default=None,
                    help="Institution profile: 'byui' REQUIRES an AI policy for a complete "
                         "verdict; anything else treats it as advisory. Default: CANVAS_INSTITUTION "
                         "env, else inferred from the Canvas host, else 'generic'.")
    args = ap.parse_args()

    use_local = args.local or bool(args.course_dir) or _is_offline()
    institution = (args.institution or default_institution()).strip().lower()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if use_local:
        from _course_loader import load_course, CourseNotFound
        try:
            c = load_course(args.course_dir or "course")
        except CourseNotFound as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(2)
        course_id = str(c.canvas_id or "local")
        course_name = c.name
        body = c.syllabus()          # mirrors course.syllabus_body
    else:
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

        course_name, body = fetch_syllabus(course_id)
        if body is None:
            print(f"\nCould not fetch course {course_id} (or the request failed).",
                  file=sys.stderr)
            sys.exit(2)

    text = html_to_text(body)
    body_words = word_count(text)
    sections = detect_sections(text)
    ai_policy = detect_ai_policy(text)
    advisory = detect_advisory(text, body)
    verdict, missing = compute_verdict(sections, ai_policy, body_words,
                                       ai_policy_required=(institution == "byui"))

    # v0.31 — 25-item rubric (run alongside umbrella audit; surfaced when --rubric set)
    rubric_items = detect_rubric_items(text, body)

    if args.emit_json:
        payload = _render_json(course_id, course_name, verdict, missing,
                               sections, ai_policy, advisory, ts)
        payload["rubric"] = {
            "items": rubric_items,
            "score_signal_total": sum(it["score_signal"] for it in rubric_items),
            "score_signal_max": 2 * len(rubric_items),
        }
        out = json.dumps(payload, indent=2, ensure_ascii=False)
        print(out)
        if args.report:
            _write_report(Path(args.report), out)
    elif args.rubric:
        # Rubric-only output (use --detailed to also print the 9-section audit)
        lines = _render_rubric(course_id, course_name, rubric_items, ts)
        if args.detailed:
            lines.append("")
            lines.append("=" * 62)
            lines.append("")
            lines.append("Also showing the 9-section umbrella audit:")
            lines.append("")
            lines.extend(_render(course_id, course_name, verdict, missing, sections,
                                ai_policy, advisory, False, ts))
        for line in lines:
            print(line)
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))
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

#!/usr/bin/env python3
"""
course_map_build.py — generate a BYU-I Architects-of-Learning "Course Map & Schedule"
artifact for any Canvas course (read-only Canvas pull + Markdown emission).

Two modes:
  --emit-blank     Write the blank Markdown template to --output-md. Matches
                   lib/agents/templates/course_map_blank.md exactly.
  (default)        Pull Canvas data for the course identified by MASTER_COURSE_ID
                   (or --course), fill the template with Canvas-derivable sections,
                   leave write-in placeholders for prose (Architect's Analysis,
                   Pacing Reflection, AI Opp/Vuln, Lesson Topics), and surface a
                   Gap Report listing what came from Canvas vs. what's write-in.

What this tool produces:
  1.1 Course Learning Outcomes — pulled from syllabus_body via heuristic LO block
  1.2 Architect's Analysis     — write-in placeholder
  1.3 Key Assessments          — Canvas ≥50pt published, heuristic Type / CLO /
                                 Domain·Level; AI Opp/Vuln write-in
  1.4 Assessment Strategy      — write-in placeholder
  1.5 Assessment Design Pt 1   — optional, write-in
  2   At-a-Glance              — Canvas modules + assignments-by-week; Lesson
                                 Topics column is write-in
  3   Per-module Details       — CLO Coverage Matrix + MLOs heuristic-extracted
                                 from overview pages + Learning Experiences grouped
                                 by pedagogy vocabulary + Bloom Scaffolding Ladder
  4   Semester Schedule        — class cadence detected from due-date modal day
                                 (override with CLASS_DAYS env or --class-days);
                                 items classified Prepare / In-Class / Assignment
                                 from name heuristics; holiday line write-in
  5   Pacing Reflection        — heavy-week ranking; reflection prose write-in
  6   Appendix                 — Bloom Reference + Gap Report + Methodology

What this tool does NOT do:
  - Draft course-specific prose. Architect's Analysis, Pacing Reflection prose,
    AI Opportunities/Vulnerabilities text, and Lesson Topics column are write-in
    by design. Agent layer (canvas_course_expert or similar) can draft those by
    reading this tool's output + the course context.
  - Pull Program Learning Outcomes (PLOs). Catalog harvest is non-standard.

Companion files:
  Template:  lib/agents/templates/course_map_blank.md
  Lessons:   lib/agents/knowledge/learned/2026-06-05_course-map-from-canvas-pass-1-lessons.md

Required env (or CLI flags):
  CANVAS_API_TOKEN, CANVAS_BASE_URL, MASTER_COURSE_ID (overridable via --course)

Optional env:
  CLASS_DAYS — comma-separated day codes ("Mon,Wed" or "Tue,Thu,Sun") to override
               the auto-detected modal due-day cadence in §4.

Usage:
  uv run python canvas_toolbox/lib/tools/course_map_build.py --emit-blank --output-md blank.md
  uv run python canvas_toolbox/lib/tools/course_map_build.py --course 402262
  uv run python canvas_toolbox/lib/tools/course_map_build.py --output-md ./map.md

Exit codes:
  0  success
  1  Canvas API error or missing required env
  2  invalid CLI flags
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests
from dotenv import load_dotenv

from __toolbox_version__ import __version__


# ---------------------------------------------------------------------------
# Bloom + Domain classifiers
# ---------------------------------------------------------------------------

BLOOM = [
    ("Remember",   ["define", "list", "recall", "identify", "name", "recognize", "describe", "state", "label"]),
    ("Understand", ["explain", "summarize", "classify", "compare", "interpret", "discuss", "illustrate", "predict"]),
    ("Apply",      ["apply", "implement", "execute", "use", "demonstrate", "solve", "build", "operate", "perform"]),
    ("Analyze",    ["analyze", "differentiate", "examine", "investigate", "deconstruct", "diagram"]),
    ("Evaluate",   ["evaluate", "assess", "critique", "judge", "justify", "validate", "test", "defend"]),
    ("Create",     ["create", "design", "develop", "construct", "produce", "compose", "formulate", "generate", "integrate"]),
]
LEVEL_ORDER = {l: i for i, (l, _) in enumerate(BLOOM)}

_AFFECTIVE_RE = re.compile(
    r"\b(defend|value|respect|appreciate|accept|adopt|embrace|justify|commit|advocate)\b", re.I)
_PSYCHOMOTOR_RE = re.compile(
    r"\b(perform|execute|operate|manipulate|fabricate|assemble)\b", re.I)


def classify_bloom(text: str) -> str:
    t = (text or "").lower()
    hits = []
    for level, verbs in BLOOM:
        for v in verbs:
            m = re.search(rf"\b{v}", t)
            if m:
                hits.append((m.start(), level))
                break
    return max(hits, key=lambda h: LEVEL_ORDER[h[1]])[1] if hits else "—"


def classify_domain(text: str) -> str:
    if _AFFECTIVE_RE.search(text or ""):
        return "Affective"
    if _PSYCHOMOTOR_RE.search(text or ""):
        return "Psychomotor (or Cognitive — verify)"
    return "Cognitive"


def classify_type(canvas_type: str, points: int = 0, name: str = "") -> str:
    """Pedagogy vocabulary, not Canvas widget names."""
    n = (name or "").lower()
    if "peer review" in n or "peer audit" in n: return "Peer Review"
    if "presentation" in n or "defense" in n:   return "Performance"
    if "demo" in n:                              return "Demo"
    if re.search(r"\b(video|watch)\b", n):       return "Video"
    if "stand up" in n or "standup" in n:        return "Discussion"
    if re.search(r"\b(read|reading)\b", n):      return "Reading"
    if "workshop" in n:                          return "Practice"
    if "final" in n or "exam" in n:              return "Summative Assessment"
    if "milestone" in n or "project" in n or "estimate" in n: return "Performance"
    if "lab" in n:                               return "Performance"
    if "quiz" in n or "check" in n:              return "Formative Assessment"
    if canvas_type == "Page":        return "Reading"
    if canvas_type == "ExternalUrl": return "External Resource"
    if canvas_type == "Discussion":  return "Discussion"
    if canvas_type == "Quiz":
        return "Summative Assessment" if (points or 0) >= 50 else "Formative Assessment"
    if canvas_type == "Assignment":
        return "Performance" if (points or 0) >= 50 else "Practice"
    if canvas_type == "SubHeader":   return "Section Header"
    return canvas_type


# ---------------------------------------------------------------------------
# HTML → text + LO/MLO extraction
# ---------------------------------------------------------------------------

class _StripHtml(HTMLParser):
    def __init__(self): super().__init__(); self.out = []
    def handle_data(self, d): self.out.append(d)
    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "li", "div"): self.out.append("\n")


def html2text(html: str) -> str:
    p = _StripHtml(); p.feed(html or ""); p.close()
    return re.sub(r"\n{3,}", "\n\n", "".join(p.out)).strip()


_MLO_HINT_RE = re.compile(
    r"(?:learning outcomes?|by the end|students? will|you will)", re.IGNORECASE)


def extract_mlos(body_html: str) -> list[str]:
    """v0.2 Lesson 17: cap at 3 (quality > quantity)."""
    text = html2text(body_html)
    if not text:
        return []
    out, capture = [], False
    for block in re.split(r"\n{2,}", text):
        if _MLO_HINT_RE.search(block):
            capture = True
            continue
        if not capture:
            continue
        for ln in block.split("\n"):
            ln = ln.strip().lstrip("•-*").strip()
            if 8 < len(ln) < 220 and re.match(r"^[A-Z][a-z]+", ln):
                out.append(ln)
        if out:
            break
    return out[:3]


def extract_syllabus_los(syllabus_html: str) -> list[str]:
    if not syllabus_html:
        return []
    text = html2text(syllabus_html)
    lines = text.split("\n")
    out, capture, n_after = [], False, 0
    for ln in lines:
        ls = ln.strip()
        if not capture and re.search(r"learning\s+outcomes?", ls, re.I):
            capture = True
            continue
        if capture:
            n_after += 1
            if re.match(r"^(required\s+resources|textbook|grading|policies|assessment|schedule)", ls, re.I):
                break
            if not ls or re.match(r"^(by the end|students will|you will be able)", ls, re.I):
                continue
            if 8 < len(ls) < 350 and re.match(r"^[A-Z][a-z]+", ls):
                out.append(ls)
            if n_after > 60:
                break
    return out[:15]


# ---------------------------------------------------------------------------
# Week + cadence helpers
# ---------------------------------------------------------------------------

_WK_NAME_RE = re.compile(r"^W(\d{1,2})\b", re.IGNORECASE)


def week_of(a: dict, start_dt) -> int | None:
    """v0.1 Lesson 4: prefer W## prefix; fall back to date math."""
    m = _WK_NAME_RE.match((a.get("name") or "").strip())
    if m:
        wk = int(m.group(1))
        if 1 <= wk <= 14:
            return wk
    if not start_dt:
        return None
    due = a.get("due_at")
    if not due:
        return None
    try:
        d = datetime.fromisoformat(due.replace("Z", "+00:00"))
    except Exception:
        return None
    return (d - start_dt).days // 7 + 1


def detect_class_cadence(assignments: list[dict],
                          override: list[str] | None = None) -> list[str]:
    """v0.2 Lesson 20: detect modal class days from due-date day-of-week."""
    if override:
        return override
    DAY_LETTER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dow_count = Counter()
    for a in assignments:
        if not a.get("published"):
            continue
        due = a.get("due_at")
        if not due:
            continue
        try:
            d = datetime.fromisoformat(due.replace("Z", "+00:00"))
            dow_count[d.weekday()] += 1
        except Exception:
            continue
    if not dow_count:
        return ["Tue", "Thu", "Sun"]
    top = sorted(dow_count.items(), key=lambda x: -x[1])[:3]
    return [DAY_LETTER[dow] for dow, _ in sorted(top, key=lambda x: x[0])]


def _classify_schedule_bucket(name: str) -> str | None:
    n = (name or "").lower()
    if re.search(r"\b(reading\s+quiz|reading:|sign[- ]up|contract|syllabus\s+quiz|pre[- ]?class)\b", n):
        return "prepare"
    if re.search(r"\b(lab\s+\d|dw\s+lab|in[- ]?class|demo|presentation|stand\s*up|workshop)\b", n):
        return "in_class"
    if re.search(r"\b(milestone|peer\s+audit|self[- ]?assessment|project|capstone|final)\b", n):
        return "assignment"
    return None


# ---------------------------------------------------------------------------
# CLO link heuristic
# ---------------------------------------------------------------------------

_CLO_STOPWORDS = {"with", "from", "that", "this", "their", "these", "those",
                  "have", "they", "your", "into", "than", "also", "such",
                  "data", "course", "students", "learning", "outcomes"}


def clo_keywords_from_clos(clos: list[str]) -> dict[int, list[str]]:
    """Per-CLO keyword list for heuristic alignment matching."""
    out = {}
    for i, clo in enumerate(clos, 1):
        words = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", clo)]
        filtered = [w for w in words if w not in _CLO_STOPWORDS]
        out[i] = list(dict.fromkeys(filtered))[:6]
    return out


def clo_hits(blob: str, clo_keys: dict[int, list[str]]) -> list[int]:
    bl = (blob or "").lower()
    return [n for n, kws in clo_keys.items() if any(k in bl for k in kws)]


def clo_link_str(blob: str, clo_keys: dict[int, list[str]]) -> str:
    h = clo_hits(blob, clo_keys)
    return ", ".join(str(n) for n in h) if h else "—"


# ---------------------------------------------------------------------------
# Canvas pull
# ---------------------------------------------------------------------------

def pull_canvas_data(course_id: str, base_url: str, headers: dict) -> dict:
    def GET(path, params=None):
        url, p, out = f"{base_url}/api/v1{path}", {"per_page": 100, **(params or {})}, []
        while url:
            r = requests.get(url, headers=headers, params=p, timeout=30)
            if r.status_code >= 400:
                return None
            d = r.json()
            if isinstance(d, list):
                out.extend(d)
            else:
                return d
            url = None
            for part in r.headers.get("Link", "").split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
            p = {}
        return out

    print(f"Pulling Canvas course {course_id}...", file=sys.stderr)
    course = GET(f"/courses/{course_id}", {"include[]": "syllabus_body"}) or {}

    _EXCLUDE_MODULE = ("do not publish", "teaching notes", "textbook information",
                       "student resources", "instructor resources")
    modules = [m for m in (GET(f"/courses/{course_id}/modules", {"include[]": "items"}) or [])
               if m.get("published", True)
               and not any(pat in (m.get("name") or "").lower() for pat in _EXCLUDE_MODULE)]

    assignments = GET(f"/courses/{course_id}/assignments") or []
    pages_meta = GET(f"/courses/{course_id}/pages") or []
    overview_bodies = {}
    EXCLUDE_PAGE = ("do not publish", "teaching notes", "textbook information")
    for p in pages_meta:
        title = (p.get("title") or "").lower()
        if not p.get("published", True):
            continue
        if any(pat in title for pat in EXCLUDE_PAGE):
            continue
        if "overview" in title:
            full = GET(f"/courses/{course_id}/pages/{p['url']}")
            if isinstance(full, dict):
                overview_bodies[p["title"]] = full.get("body") or ""

    syllabus_los = extract_syllabus_los(course.get("syllabus_body", ""))
    print(f"  modules={len(modules)} assignments={len(assignments)} "
          f"overview-bodies={len(overview_bodies)} syllabus_los={len(syllabus_los)}",
          file=sys.stderr)

    return {
        "course": course, "modules": modules, "assignments": assignments,
        "overview_bodies": overview_bodies, "course_id": course_id,
        "syllabus_los": syllabus_los,
    }


def derive_start(data: dict):
    course = data.get("course", {}) or {}
    sa = course.get("start_at")
    if sa:
        return datetime.fromisoformat(sa.replace("Z", "+00:00"))
    pub_due = []
    for a in data.get("assignments", []):
        if a.get("published") and a.get("due_at"):
            try:
                pub_due.append(datetime.fromisoformat(a["due_at"].replace("Z", "+00:00")))
            except Exception:
                pass
    if pub_due:
        earliest = min(pub_due)
        return earliest - timedelta(days=earliest.weekday())
    return None


def group_assignments_by_week(assignments: list[dict], start_dt) -> dict[int, list[dict]]:
    out = defaultdict(list)
    for a in assignments:
        if not a.get("published"):
            continue
        wk = week_of(a, start_dt)
        if wk and 1 <= wk <= 14:
            out[wk].append(a)
    return dict(out)


# ===========================================================================
# REPORT EMITTER
# ===========================================================================

def emit_report(data: dict | None = None) -> tuple[str, list[dict]]:
    """data=None → blank template. data=dict → Canvas-filled. Returns (md, gaps)."""
    BLANK = data is None
    L = []
    def w(s=""): L.append(s)
    gaps = []

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ---- Title ----
    if BLANK:
        w("# [Course Code] — Course Map & Schedule")
        w()
        w("**[Course Name]** · *Mode: [Mode]* · *Generated [timestamp]*")
        w()
        w("> **Template (blank)** — Markdown form of the *Architects of Learning* Course Map "
          "workbook (5–7 sheets depending on cohort). Every workbook section has a home below. "
          "Fill placeholders (`_[…]_`) from your Canvas course + your write-ins. University-agnostic "
          "— works for any institution running an AoL-style course-design track. Use the companion "
          "filler tool (`course_map_build.py`) to populate Canvas-derivable fields automatically.")
    else:
        course = data["course"]
        course_name = course.get("name", "Course")
        course_code = course.get("course_code", "[Course Code]")
        w(f"# {course_code} — {course_name} · Course Map & Schedule")
        w()
        w(f"**Mode:** *[fill in]* · *Generated {now_iso}* · *Canvas course `{data['course_id']}`*")
        w()
        w("> Canvas-derivable sections are filled; **prose sections are write-in by design** "
          "(Architect's Analysis, Pacing Reflection, AI Opportunities/Vulnerabilities, Lesson Topics). "
          "The Gap Report at the end (§6.2) lists each section's source.")
    w()
    w("---")
    w()

    # ============================================================
    # 1 — Course Outcomes & Assessment Strategy
    # ============================================================
    w("## 1 — Course Outcomes & Assessment Strategy")
    w()
    w("#### 1.1 Course Learning Outcomes")
    w()
    w("| # | Course Learning Outcome | Domain | Bloom Level |")
    w("|---|---|---|---|")
    if BLANK:
        for i in range(1, 6):
            w(f"| {i} | _[CLO text]_ | _[Cognitive / Affective / Psychomotor]_ | _[Bloom level]_ |")
        w("| *(add more rows as needed)* | | | |")
    else:
        syl = data.get("syllabus_los") or []
        if syl:
            for i, lo in enumerate(syl, 1):
                w(f"| {i} | {lo} | {classify_domain(lo)} | {classify_bloom(lo)} |")
            gaps.append({"sheet": "1.1", "item": "CLO source",
                         "status": f"✓ syllabus_body ({len(syl)} LOs)",
                         "note": "Bloom + Domain heuristic. Operators with a condensed CLO set should replace + explain in §1.2."})
        else:
            for i in range(1, 6):
                w(f"| {i} | _[CLO text — no syllabus LO block detected]_ | _[Domain]_ | _[Bloom]_ |")
            gaps.append({"sheet": "1.1", "item": "CLO source", "status": "⊘ no LO block",
                         "note": "Author from external syllabus or course catalog."})
    w()

    # 1.2
    w("#### 1.2 Architect's Analysis")
    w()
    w("> *Prompts:*")
    w("> - *Where were the existing outcomes strong?*")
    w("> - *Where could they use improvement?*")
    w("> - *What challenges did you have as you revised outcomes where necessary?*")
    w("> - *How do these revised course outcomes align with the broader program / instructional design goals?*")
    w()
    w("**Response:**")
    w()
    w("> _[write-in]_")
    w()
    if not BLANK:
        gaps.append({"sheet": "1.2", "item": "Architect's Analysis prose",
                     "status": "⊘ write-in", "note": "Faculty authorship required (rubric-scored)."})

    # 1.3
    w("#### 1.3 Key Assessments")
    w()
    w("| Key Assessment | Type | CLOs | Domain / Level | AI Opportunities | AI Vulnerabilities |")
    w("|---|---|---|---|---|---|")
    if BLANK:
        for i in range(5):
            w(f"| _[name]_ | _[Performance / Summative / Recall / Formative]_ | _[CLOs e.g. 1,3]_ | _[e.g. Cognitive/Create]_ | _[paragraph: 2–3 sentences on AI co-pilot patterns]_ | _[paragraph: 2–3 sentences on ghost-writer risks]_ |")
    else:
        clo_keys = clo_keywords_from_clos(data.get("syllabus_los") or [])
        key_assess_raw = [a for a in data["assignments"]
                          if (a.get("points_possible") or 0) >= 50 and a.get("published")]
        family_groups = defaultdict(list)
        for a in key_assess_raw:
            name = a.get("name") or "?"
            base = re.sub(r"^W\d{1,2}\s+", "", name)
            base = re.sub(r"[:\-]?\s*\d+\s*$", "", base).strip()
            base = re.sub(r":\s*Chapter\s+\d+.*$", "", base, flags=re.I).strip()
            if not base:
                base = name
            family_groups[base].append(a)

        sorted_families = sorted(family_groups.items(),
                                 key=lambda kv: -max((x.get("points_possible") or 0) for x in kv[1]))
        for base, items in sorted_families[:15]:
            name = base if len(items) == 1 else f"{base} ({len(items)}×)"
            pts = max((x.get("points_possible") or 0) for x in items)
            nm_low = name.lower()
            if "final" in nm_low or "exam" in nm_low or "capstone" in nm_low:
                atype = "Summative"
            elif "presentation" in nm_low or "milestone" in nm_low or "lab" in nm_low or "project" in nm_low or "estimate" in nm_low:
                atype = "Performance"
            elif "quiz" in nm_low and re.search(r"(masterformat|uniformat|vocab|terminology)", nm_low):
                atype = "Recall"
            elif "quiz" in nm_low or "check" in nm_low:
                atype = "Formative"
            else:
                atype = "Formative"
            blob = " ".join((x.get("name", "") + " " + html2text(x.get("description") or ""))
                           for x in items)
            clo_str = clo_link_str(blob, clo_keys)
            bloom = classify_bloom(blob)
            domain_level = f"Cognitive/{bloom}" if bloom != "—" else "_[verify]_"
            w(f"| {name} *({int(pts)}pt)* | {atype} *(heuristic)* | {clo_str} *(heuristic)* | {domain_level} *(heuristic)* | _[write-in: paragraph]_ | _[write-in: paragraph]_ |")
        gaps.append({"sheet": "1.3", "item": "Key Assessments rollup",
                     "status": "⚠ heuristic family-grouping",
                     "note": f"Grouped {len(key_assess_raw)} ≥50pt assignments into {len(family_groups)} families by name-stem."})
        gaps.append({"sheet": "1.3", "item": "AI Opp / Vuln columns",
                     "status": "⊘ write-in (Canvas has no field)",
                     "note": "Author 2–3 sentence paragraphs per family explaining AI co-pilot opportunities and ghost-writer risks."})
    w()

    # 1.4
    w("#### 1.4 Assessment Strategy Reflection")
    w()
    w("> *Prompts:*")
    w("> - *How do the assessment approaches selected align with the needed level of mastery defined by the course outcomes?*")
    w("> - *How can AI use potentially short-circuit AND extend learning outcomes and the level of mastery required?*")
    w()
    w("**Response:**")
    w()
    w("> _[write-in]_")
    w()
    if not BLANK:
        gaps.append({"sheet": "1.4", "item": "Assessment Strategy Reflection prose",
                     "status": "⊘ write-in", "note": "Faculty authorship required (rubric-scored)."})
    w("---")
    w()

    # 1.5 — Assessment Design Deep-Dive (optional)
    w("## 1.5 — Assessment Design Deep-Dive *(optional)*")
    w()
    w("*Pick **one** existing assessment to redesign as an exemplar of evidence-centered "
      "assessment design. Detail the redesigned format, instructions, and a 3×3 rubric matrix.*")
    w()
    w("### Original assessment")
    w()
    w("_[name from your Key Assessments above]_")
    w()
    w("### Redesigned assessment")
    w()
    w("**Name:** _[new name]_  ")
    w("**Format:** _[in-class case study / take-home project / scenario-based exam / portfolio / etc.]_  ")
    w("**Estimated time:** _[N hours]_")
    w()
    w("**Instructions:**")
    w()
    w("> _[detailed instructions — what students do, materials, output, AI use guidance]_")
    w()
    w("**Tasks:**")
    w()
    w("1. _[Task 1]_")
    w("2. _[Task 2]_")
    w("3. _[Task 3]_")
    w()
    w("### Rubric")
    w()
    w("| Criteria | Excellent (Mastery) | Competent (Proficient) | Needs Improvement (Developing) |")
    w("|---|---|---|---|")
    w("| _[criterion 1 + points]_ | _[mastery descriptor]_ | _[proficient descriptor]_ | _[developing descriptor]_ |")
    w("| _[criterion 2 + points]_ | _[mastery descriptor]_ | _[proficient descriptor]_ | _[developing descriptor]_ |")
    w("| _[criterion 3 + points]_ | _[mastery descriptor]_ | _[proficient descriptor]_ | _[developing descriptor]_ |")
    w()
    if not BLANK:
        gaps.append({"sheet": "1.5", "item": "Assessment Design Deep-Dive",
                     "status": "⊘ optional write-in",
                     "note": "Skip if not required. Otherwise pick one assessment to redesign deeply."})
    w("---")
    w()

    # ============================================================
    # 2 — Course Map At a Glance
    # ============================================================
    w("## 2 — Course Map · At a Glance")
    w()
    w("| Week | Module Concept/Title | Lesson Topics | Minor Activities/Assignments | Key Assessments |")
    w("|---|---|---|---|---|")
    if BLANK:
        for wk in range(1, 15):
            w(f"| {wk} | _[Module / Sprint name]_ | _[verb-led: 'Apply X. Calculate Y.']_ | _[minor items]_ | _[key assessments]_ |")
    else:
        start_dt = derive_start(data)
        assigns_by_week = group_assignments_by_week(data["assignments"], start_dt)
        modules = data["modules"]
        module_week_map = {}
        for i, m in enumerate(modules):
            name = m.get("name") or ""
            mw = re.search(r"\bW(\d+)|\bWeek\s*(\d+)|\bSprint\s*(\d+)", name)
            if mw:
                module_week_map[int(next(g for g in mw.groups() if g))] = name
            else:
                module_week_map[i + 1] = name
        for wk in range(1, 15):
            mod_label = module_week_map.get(wk, "—")
            canvas_items = assigns_by_week.get(wk, [])
            canvas_major = [a.get("name", "?")[:40] for a in canvas_items if (a.get("points_possible") or 0) >= 50]
            canvas_minor = [a.get("name", "?")[:40] for a in canvas_items if (a.get("points_possible") or 0) < 50]
            minor_str = "; ".join(canvas_minor[:3]) + (f" (+{len(canvas_minor)-3})" if len(canvas_minor) > 3 else "") if canvas_minor else "—"
            key_str = "; ".join(canvas_major) if canvas_major else "—"
            w(f"| {wk} | {mod_label[:40]} | _[write-in: verb-led]_ | {minor_str} | {key_str} |")
        gaps.append({"sheet": "2", "item": "Lesson Topics column",
                     "status": "⊘ write-in",
                     "note": "Author as action-verb sentences (e.g., 'Apply X. Calculate Y.'), NOT topic nouns."})
    w()
    w("---")
    w()

    # ============================================================
    # 3 — Per-module Details
    # ============================================================
    w("## 3 — Course Map · Details (per-module)")
    w()
    if BLANK:
        for i in (1, 2):
            w(f"### Module {i}: _[Module Title]_")
            w()
            w("**Module Learning Outcomes** *(high-level — what students walk away with; 2–3 MLOs per module is the sweet spot)*")
            w()
            w("| # | Module Learning Outcome | Bloom Level | CLO(s) |")
            w("|---|---|---|---|")
            for j in range(1, 4):
                w(f"| {j} | _[MLO text]_ | _[Bloom]_ | _[CLOs]_ |")
            w()
            w("**Learning Experiences** *(grouped summary — pedagogy vocab not Canvas widget names)*")
            w()
            w("| Category | Summary | Type of Experience | Notes |")
            w("|---|---|---|---|")
            w("| Materials | _[reading list]_ | Reading | _[N items]_ |")
            w("| Activities | _[activity names]_ | Practice | _[N items, X pts total]_ |")
            w("| Major Assessment | _[name + pts]_ | Performance | _[summative for this module]_ |")
            w("| Discussions | _[if any]_ | Discussion | _[peer / instructor interaction]_ |")
            w("| Quizzes / Checks | _[if any]_ | Formative Assessment | _[check-for-understanding]_ |")
            w()
        w("> **[REPEAT BLOCK FOR EACH MODULE]**")
        w()
        w("### Bloom Scaffolding Ladder (across all modules)")
        w()
        w("| Module | Remember | Understand | Apply | Analyze | Evaluate | Create | Highest |")
        w("|---|---|---|---|---|---|---|---|")
        w("| M1: _[title]_ | _[✓ if MLO at this level]_ | | | | | | _[highest]_ |")
        w("| *(repeat per module)* | | | | | | | |")
        w()
    else:
        modules = data["modules"]
        syl_los = data.get("syllabus_los") or []
        clo_keys = clo_keywords_from_clos(syl_los)
        clo_count = max(len(syl_los), 5) if syl_los else 5

        w("### CLO Coverage Across Modules")
        w()
        w("*Which CLOs each module supports (via its MLOs). Heuristic keyword match — empty cells may "
          "indicate vocabulary mismatch rather than a real gap.*")
        w()
        w("| Module | " + " | ".join(f"CLO {n}" for n in range(1, clo_count + 1)) + " |")
        w("|" + "---|" * (clo_count + 1))

        coverage = [0] * clo_count
        module_data = []
        for i, m in enumerate(modules, 1):
            mname = m.get("name") or f"Module {i}"
            items = m.get("items") or []
            overview_title = next(
                (it.get("title") for it in items
                 if it.get("type") == "Page" and "overview" in (it.get("title") or "").lower()),
                None)
            mlos = extract_mlos(data["overview_bodies"].get(overview_title, "")) if overview_title else []
            clos_for_module = set()
            for mlo in mlos:
                for n in clo_hits(mlo, clo_keys):
                    if n <= clo_count:
                        clos_for_module.add(n)
                        coverage[n - 1] += 1
            module_data.append((i, mname, clos_for_module, mlos, items))
            row = ["✓" if n in clos_for_module else "" for n in range(1, clo_count + 1)]
            w(f"| M{i}: {mname[:30]} | " + " | ".join(row) + " |")
        w(f"| **Modules touching CLO** | " + " | ".join(str(c) for c in coverage) + " |")
        w()
        gap_clos = [f"CLO {n+1}" for n, c in enumerate(coverage) if c == 0]
        if gap_clos:
            w(f"> ⚠ **Possible alignment gaps:** {', '.join(gap_clos)} — no module MLO keyword-matched. Verify vocabulary or fill the gap.")
        else:
            w(f"> ✓ Every CLO is supported by at least one module's MLOs (heuristic — verify wording).")
        w()
        w("---")
        w()

        assign_by_id = {a["id"]: a for a in data["assignments"]}
        module_bloom_levels = []
        EXCLUDE = ("do not publish", "teaching notes", "textbook information")
        for i, mname, _clos, mlos, items in module_data:
            w(f"### Module {i}: {mname}")
            w()
            w("**Module Learning Outcomes** *(high-level outcomes — what students walk away with)*")
            w()
            w("| # | Module Learning Outcome | Bloom Level | CLO(s) |")
            w("|---|---|---|---|")
            blooms = set()
            if mlos:
                for j, mlo in enumerate(mlos, 1):
                    b = classify_bloom(mlo)
                    if b != "—":
                        blooms.add(b)
                    w(f"| {j} | {mlo[:200]} | {b} | {clo_link_str(mlo, clo_keys)} |")
            else:
                w("| — | ⚠ _gap: no MLOs detected in overview page. Add to overview or write-in._ | | |")
            w()

            materials, activities, major, discussions, quizzes = [], [], [], [], []
            for it in items:
                itype = it.get("type", "?")
                title = it.get("title") or ""
                tl = title.lower()
                if any(pat in tl for pat in EXCLUDE) or itype == "SubHeader":
                    continue
                if itype == "Page":
                    materials.append(title)
                elif itype == "Assignment":
                    aid = it.get("content_id"); a = assign_by_id.get(aid, {})
                    pts = int(a.get("points_possible") or 0)
                    ped = classify_type(itype, pts, title)
                    if ped in ("Performance", "Summative Assessment"):
                        major.append((title, pts, ped))
                    else:
                        activities.append((title, pts, ped))
                elif itype == "Discussion":
                    discussions.append(title)
                elif itype == "Quiz":
                    quizzes.append(title)

            w("**Learning Experiences** *(grouped summary — supports the MLOs above)*")
            w()
            w("| Category | Summary | Type of Experience | Notes |")
            w("|---|---|---|---|")
            if materials:
                names = "; ".join(materials[:4]) + (f" (+{len(materials)-4})" if len(materials) > 4 else "")
                w(f"| Materials | {names} | Reading | {len(materials)} item(s) |")
            if activities:
                names = "; ".join(f"{n} ({p}pt)" for n, p, _ in activities[:4])
                total = sum(p for _n, p, _t in activities)
                ptypes = Counter(t for _n, _p, t in activities).most_common(1)[0][0]
                w(f"| Activities | {names} | {ptypes} | {len(activities)} item(s), {total} pts |")
            if major:
                names = "; ".join(f"{n} ({p}pt)" for n, p, _ in major[:4])
                ptypes = Counter(t for _n, _p, t in major).most_common(1)[0][0]
                w(f"| Major Assessment | {names} | {ptypes} | Summative for module |")
            if discussions:
                w(f"| Discussions | {'; '.join(discussions[:3])} | Discussion | Peer / instructor interaction |")
            if quizzes:
                w(f"| Quizzes / Checks | {'; '.join(quizzes[:3])} | Formative Assessment | Check-for-understanding |")
            if not any([materials, activities, major, discussions, quizzes]):
                w(f"| — | _no published learning experiences detected_ | — | — |")
            w()
            module_bloom_levels.append((i, mname, sorted(blooms, key=lambda b: LEVEL_ORDER.get(b, 99))))

        w("### Bloom Scaffolding Ladder (across all modules)")
        w()
        levels = [l for l, _ in BLOOM]
        w("| Module | " + " | ".join(levels) + " | Highest |")
        w("|" + "---|" * (len(levels) + 2))
        for i, mname, blooms in module_bloom_levels:
            row = ["✓" if l in blooms else "" for l in levels]
            highest = blooms[-1] if blooms else "—"
            w(f"| M{i}: {mname[:35]} | " + " | ".join(row) + f" | **{highest}** |")
        w()

        gaps.append({"sheet": "3", "item": "MLO extraction",
                     "status": "⚠ heuristic",
                     "note": "MLOs scraped from module overview pages. Some modules may need write-in."})
    w("---")
    w()

    # ============================================================
    # 4 — Semester Schedule
    # ============================================================
    w("## 4 — Semester Schedule")
    w()
    if BLANK:
        w("*Per-week table. Default 3 day-rows (Tue/Thu/Sun); filler detects modal class days or honors `CLASS_DAYS`.*")
        w()
        for wk in range(1, 15):
            w(f"### Week {wk}")
            w()
            w("| Date | Day | Prepare | In-Class | Assignment |")
            w("|---|---|---|---|---|")
            for d in ["Tue", "Thu", "Sun"]:
                w(f"| _[date]_ | {d} | _[Prepare items due this day]_ | _[In-Class items]_ | _[Outside-class deliverables]_ |")
            w()
            w("> *Holiday / special note this week:* _[write-in if any]_")
            w()
    else:
        start_dt = derive_start(data)
        assigns_by_week = group_assignments_by_week(data["assignments"], start_dt)
        cadence_override = os.environ.get("CLASS_DAYS", "").strip()
        cadence_override_list = [s.strip() for s in cadence_override.split(",") if s.strip()] if cadence_override else None
        DAYS = detect_class_cadence(data["assignments"], cadence_override_list)
        DAY_IDX = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

        def row_for_dow(dow_int):
            if not DAYS:
                return "Sun"
            target_dow = {d: DAY_IDX[d] for d in DAYS}
            return min(DAYS, key=lambda d: abs(target_dow[d] - dow_int))

        loads_for_calendar = []
        for wk in range(1, 15):
            items = assigns_by_week.get(wk, [])
            pts = sum((a.get("points_possible") or 0) for a in items)
            mj = sum(1 for a in items if (a.get("points_possible") or 0) >= 50)
            loads_for_calendar.append((wk, pts, mj))
        sorted_loads = sorted(loads_for_calendar, key=lambda x: -(x[1] + 2 * x[2]))
        heavy = {wk for wk, _, _ in sorted_loads[:4]}

        for wk in range(1, 15):
            if start_dt:
                ws = start_dt + timedelta(days=(wk - 1) * 7)
                label = ws.strftime("%b %d, %Y")
            else:
                ws = None
                label = "—"
            flag = " ⚠️ *heavy*" if wk in heavy else ""
            w(f"### Week {wk} — week of {label}{flag}")
            w()
            w("| Date | Day | Prepare | In-Class | Assignment |")
            w("|---|---|---|---|---|")

            wk_items = assigns_by_week.get(wk, [])
            row_buckets = {d: {"prepare": [], "in_class": [], "assignment": [], "date": None}
                          for d in DAYS}
            for a in wk_items:
                name = a.get("name", "?")
                pts = int(a.get("points_possible") or 0)
                due_iso = a.get("due_at")
                dow = None
                date_label = "—"
                if due_iso:
                    try:
                        d = datetime.fromisoformat(due_iso.replace("Z", "+00:00"))
                        dow = d.weekday()
                        date_label = d.strftime("%b %d")
                    except Exception:
                        pass
                row_key = row_for_dow(dow) if dow is not None else (DAYS[-1] if DAYS else "Sun")
                bucket = _classify_schedule_bucket(name)
                label_str = f"{name[:48]} *({pts}pt)*"
                if bucket == "prepare":
                    row_buckets[row_key]["prepare"].append(label_str)
                elif bucket == "in_class":
                    row_buckets[row_key]["in_class"].append(label_str)
                elif bucket == "assignment":
                    row_buckets[row_key]["assignment"].append(label_str)
                if row_buckets[row_key]["date"] is None and date_label != "—":
                    row_buckets[row_key]["date"] = date_label

            for day_name in DAYS:
                rb = row_buckets[day_name]
                date_str = rb["date"] or "—"
                w(f"| {date_str} | {day_name} | {'; '.join(rb['prepare'])} | {'; '.join(rb['in_class'])} | {'; '.join(rb['assignment'])} |")
            w()
            w("> *Holiday / special note this week:* _[write-in if any]_")

            unclassified = [a for a in wk_items if _classify_schedule_bucket(a.get("name", "")) is None]
            if unclassified:
                w()
                w(f"**Unclassified W{wk:02d} items** *(name doesn't match prepare / in-class / assignment patterns):*")
                for a in unclassified:
                    nm = a.get("name", "?"); pt = int(a.get("points_possible") or 0)
                    dt = (a.get("due_at") or "")[:10] or "no due"
                    w(f"- {nm} *({pt}pt, due {dt})*")
            w()

        gaps.append({"sheet": "4", "item": "Prepare / In-Class / Assignment classification",
                     "status": "⚠ heuristic by name pattern",
                     "note": "Unclassified items listed separately. Override class meeting days via CLASS_DAYS env var or --class-days."})
        gaps.append({"sheet": "4", "item": "Holiday markers",
                     "status": "⊘ write-in",
                     "note": "Per-week holiday/special notes are operator write-ins."})
    w("---")
    w()

    # ============================================================
    # 5 — Pacing Reflection
    # ============================================================
    w("## 5 — Pacing Reflection")
    w()
    if BLANK:
        w("### Heavy-Week Analysis")
        w()
        w("_[The filler tool produces a heavy-week ranking by `points + 2 × major_count`. ")
        w("Top 4 weeks are flagged ⚠️. Use this as the data backbone for your reflection prose.]_")
        w()
    else:
        start_dt = derive_start(data)
        assigns_by_week = group_assignments_by_week(data["assignments"], start_dt)
        max_pts = max((sum((a.get("points_possible") or 0) for a in assigns_by_week.get(wk, []))
                      for wk in range(1, 15)), default=1) or 1
        loads = sorted([(wk, sum((a.get('points_possible') or 0) for a in assigns_by_week.get(wk, [])),
                        sum(1 for a in assigns_by_week.get(wk, []) if (a.get('points_possible') or 0) >= 50))
                       for wk in range(1, 15)], key=lambda x: -(x[1] + 2 * x[2]))
        heavy_set = {wk for wk, _, _ in loads[:4]}
        w("### Workload by Week (Canvas-derived)")
        w()
        w("| Wk | Items due | Pts | Major (≥50pt) | Density |")
        w("|---|---|---|---|---|")
        for wk in range(1, 15):
            items = assigns_by_week.get(wk, [])
            pts = sum((a.get("points_possible") or 0) for a in items)
            mj = sum(1 for a in items if (a.get("points_possible") or 0) >= 50)
            n = int(round((pts / max_pts) * 20)) if max_pts else 0
            bar = "█" * n + "·" * (20 - n)
            hflag = " ⚠️" if wk in heavy_set else ""
            w(f"| {wk}{hflag} | {len(items)} | {int(pts)} | {mj} | `{bar}` |")
        w()
        w("### Heavy-Week Ranking")
        w()
        w("| Rank | Week | # items | Pts | Major | What's due |")
        w("|---|---|---|---|---|---|")
        for r, (wk, pts, mj) in enumerate(loads[:8], 1):
            items = assigns_by_week.get(wk, [])
            big = [a.get("name", "?")[:40] for a in items if (a.get("points_possible") or 0) >= 50]
            big_str = "; ".join(big) if big else "minor items only"
            w(f"| {r} | {wk} | {len(items)} | {int(pts)} | {mj} | {big_str} |")
        w()

    w("### Reflection")
    w()
    w("> *Prompts:*")
    w("> - *Which specific weeks look heavy?*")
    w("> - *Why might those weeks be demanding?*")
    w("> - *What evidence will you monitor to decide whether students are overwhelmed?*")
    w("> - *Architect's Reflection: \"Could an outside inspector see exactly why students are doing every activity?\" "
      "\"Does your schedule allow breathing room?\"*")
    w()
    w("**Response:**")
    w()
    w("> _[write-in]_")
    w()
    if not BLANK:
        gaps.append({"sheet": "5", "item": "Pacing Reflection prose",
                     "status": "⊘ write-in",
                     "note": "Heavy-week data above is your ground truth. Author the reflection."})
    w("---")
    w()

    # ============================================================
    # 6 — Appendix
    # ============================================================
    w("## 6 — Appendix")
    w()
    w("### 6.1 Bloom's Taxonomy Reference")
    w()
    w("| Domain | Level (low → high) | Sample verbs |")
    w("|---|---|---|")
    w("| **Cognitive** | Remember → Understand → Apply → Analyze → Evaluate → Create | define, explain, apply, analyze, evaluate, create |")
    w("| **Affective** | Receiving → Responding → Valuing → Organizing → Characterizing | attend, comply, accept, integrate, embody |")
    w("| **Psychomotor** | Reflex → Fundamental → Perceptual → Physical → Skilled → Non-discursive | react, walk, perceive, endure, execute, gesture |")
    w()

    if not BLANK:
        w("### 6.2 Gap Report")
        w()
        w("*Each row says where the data came from and whether it needs verification or write-in.*")
        w()
        w("| Section | Item | Status | Note |")
        w("|---|---|---|---|")
        for g in gaps:
            w(f"| {g['sheet']} | {g['item']} | {g['status']} | {g['note']} |")
        w()
        w("### 6.3 Methodology")
        w()
        w(f"- **Data source:** Canvas REST API against course `{data['course_id']}`.")
        w(f"- **Week mapping:** prefers `W##` prefix in assignment name; falls back to due-date relative to derived start (course `start_at` if set, else earliest published due-date walked back to Monday).")
        w(f"- **Bloom classification:** verb-matched, highest match wins (heuristic — verify).")
        w(f"- **CLO link heuristic:** keyword match against CLO terms (heuristic — verify).")
        w(f"- **Class cadence:** detected from due-date modal day-of-week, or overridden via `CLASS_DAYS` env / `--class-days`.")
        w(f"- **Excluded:** Page/module titles matching 'do not publish' / 'teaching notes' / 'textbook information' / 'student resources' / 'instructor resources' are filtered out.")
        w(f"- **What's NOT auto-filled:** Architect's Analysis, Assessment Strategy Reflection, Pacing Reflection prose, AI Opp/Vuln paragraphs, Lesson Topics, Holiday markers. See §6.2.")
        w()
    w(f"*{'BLANK TEMPLATE' if BLANK else 'Filled from Canvas'} · generated {now_iso} · canvas-toolbox `course_map_build.py` v{__version__}*")
    w()

    return "\n".join(L), gaps


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    ap = argparse.ArgumentParser(
        description="Generate a Course Map & Schedule artifact from Canvas data (or emit blank template).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--emit-blank", action="store_true",
                    help="Emit the blank template only; skip Canvas pull.")
    ap.add_argument("--course", metavar="ID",
                    help="Canvas course id to pull (default: $MASTER_COURSE_ID).")
    ap.add_argument("--class-days", metavar="DAYS",
                    help="Comma-separated class meeting days, e.g. 'Mon,Wed' or "
                         "'Tue,Thu,Sun'. Default: auto-detect modal due-day.")
    ap.add_argument("--output-md", metavar="PATH", default="course_map.md",
                    help="Output Markdown path (default: ./course_map.md).")
    args = ap.parse_args()

    if args.class_days:
        os.environ["CLASS_DAYS"] = args.class_days

    load_dotenv()

    if args.emit_blank:
        md, _ = emit_report(data=None)
        out_path = Path(args.output_md)
        out_path.write_text(md, encoding="utf-8")
        print(f"✓ blank template → {out_path}", file=sys.stderr)
        # v0.32: default-on PDF pair
        if out_path.suffix.lower() in (".md", ".markdown"):
            try:
                from _md_to_pdf import render_pair
                render_pair(out_path, title=f"Course Map Template (blank)")
            except ImportError:
                pass
        return 0

    token = os.environ.get("CANVAS_API_TOKEN")
    base_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
    if base_url and not base_url.startswith("http"):
        base_url = "https://" + base_url
    course_id = args.course or os.environ.get("MASTER_COURSE_ID") or os.environ.get("CANVAS_COURSE_ID")

    missing = []
    if not token:     missing.append("CANVAS_API_TOKEN")
    if not base_url:  missing.append("CANVAS_BASE_URL")
    if not course_id: missing.append("MASTER_COURSE_ID (or --course)")
    if missing:
        print("ERROR: Missing required configuration:", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {token}"}
    try:
        data = pull_canvas_data(course_id, base_url, headers)
    except Exception as e:
        print(f"ERROR: Canvas pull failed: {e}", file=sys.stderr)
        return 1

    md, gaps = emit_report(data=data)
    out_path = Path(args.output_md)
    out_path.write_text(md, encoding="utf-8")
    print(f"✓ course map → {out_path} ({len(md)} bytes, {len(gaps)} gap(s))", file=sys.stderr)
    # v0.32: default-on PDF pair
    if out_path.suffix.lower() in (".md", ".markdown"):
        try:
            from _md_to_pdf import render_pair
            render_pair(out_path, title=f"Course Map · {data.get('course', {}).get('name', 'Course')}")
        except ImportError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

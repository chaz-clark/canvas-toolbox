#!/usr/bin/env python3
"""
content_representation_audit.py — EXPERIMENTAL, UNWIRED (v0.1).

Read-only content-source inventory: scans a course's text content (syllabus,
page bodies, assignment descriptions) and surfaces the NAMED SOURCES it can detect
(citation/attribution patterns) as a deduplicated, counted list — so an instructor
can review *whose* voices their content draws on.

It SURFACES data; it does NOT score representation, and it deliberately does NOT
infer anyone's demographics (gender/ethnicity/etc.) — automated demographic
inference is error-prone and inappropriate. The list is a starting point for a
human review (see content_representation_knowledge.md, the evidence-based stance).

NOT wired into course_audit or canvas_course_expert — built ahead of an explicit
decision to wire it. Run it directly to evaluate whether the surface is useful.

Detection (heuristic on stripped HTML — "not detected" ≠ "not present"):
  - Author (Year)        e.g. "Sweller (1988)", "Walton & Cohen (2007)", "Ambrose et al. (2010)"
  - by <Name Surname>    e.g. "a framework by Grant Wiggins"
  - — <Name Surname>     quoted-attribution em-dash

Cannot see: authors inside linked PDFs/files, video creators, publisher metadata,
or names only in external links. A course delivering readings as attachments will
surface little — a limitation, not a finding.

Endpoints (all GET, read-only):
  GET /courses/:id?include[]=syllabus_body
  GET /courses/:id/pages         then per-page GET /courses/:id/pages/:url  (body)
  GET /courses/:id/assignments   (descriptions inline)

Exit codes: 0 inventory produced · 2 config error / no content fetched.

Usage:
  uv run python canvas_toolbox/lib/tools/content_representation_audit.py --target CANVAS_SANDBOX_ID
  uv run python canvas_toolbox/lib/tools/content_representation_audit.py --course-id 402262 --json
  uv run python canvas_toolbox/lib/tools/content_representation_audit.py --course-id 402262 --max-pages 40

Reads: knowledge/content_representation_knowledge.md (the framework + evidence-based stance).
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

import canvas_course_guard as guard
from __toolbox_version__ import __version__

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url
_TIMEOUT = 30

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Detection patterns. Author(Year) is the high-precision primary signal.
_AUTHOR_YEAR = re.compile(
    r"\b([A-Z][A-Za-z.'’-]+(?:,?\s+(?:&|and)\s+[A-Z][A-Za-z.'’-]+)*"
    r"(?:\s+et\s+al\.?)?)\s*\(\s*(\d{4})[a-z]?\s*\)")
_BY_NAME = re.compile(r"\bby\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)")
_DASH_NAME = re.compile(r"[—–-]\s*([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*$")

# Words that look like names after "by"/dash but aren't (reduce noise).
_NOT_NAMES = {"the", "this", "that", "clicking", "default", "friday", "monday",
              "tuesday", "wednesday", "thursday", "saturday", "sunday", "week",
              "completing", "following", "submitting", "using", "creating",
              "due", "date", "click", "please", "note", "example", "figure",
              "table", "chapter", "section", "part", "module", "unit", "day",
              "assignment", "quiz", "exam", "page", "step", "lesson", "group"}


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
            return results or None
        if resp.status_code >= 400:
            return results or None
        try:
            data = resp.json()
        except Exception:
            return results or None
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


def _text(htmlstr: str) -> str:
    if not htmlstr:
        return ""
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", htmlstr,
                  flags=re.IGNORECASE | re.DOTALL)
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", body))).strip()


def _norm(name: str) -> str:
    return _WS_RE.sub(" ", name).strip(" .,").strip()


def extract_sources(text: str) -> set[str]:
    """Named sources detected in one content item's text. Conservative."""
    found: set[str] = set()
    for m in _AUTHOR_YEAR.finditer(text):
        nm = _norm(m.group(1))
        if len(nm) >= 2:
            found.add(f"{nm} ({m.group(2)})")
    for rx in (_BY_NAME, _DASH_NAME):
        for m in rx.finditer(text):
            nm = _norm(m.group(1))
            if nm and nm.split()[0].lower() not in _NOT_NAMES and len(nm) >= 4:
                found.add(nm)
    return found


# ---------------------------------------------------------------------------
# Content collection
# ---------------------------------------------------------------------------

def collect_items(course_id: str, max_pages: int) -> tuple[str, list[tuple[str, str]]]:
    """Return (course_name, [(item_label, text), ...]) for syllabus + pages + assignments."""
    items: list[tuple[str, str]] = []

    course = _get(f"/courses/{course_id}", {"include[]": "syllabus_body"})
    course_name = "<unknown course>"
    if isinstance(course, dict):
        course_name = (course.get("name") or "").strip() or course_name
        syll = _text(course.get("syllabus_body") or "")
        if syll:
            items.append(("syllabus", syll))

    pages = _get(f"/courses/{course_id}/pages") or []
    if isinstance(pages, list):
        for p in pages[:max_pages]:
            url = p.get("url")
            if not url:
                continue
            full = _get(f"/courses/{course_id}/pages/{url}")
            body = _text(full.get("body") or "") if isinstance(full, dict) else ""
            if body:
                items.append((f"page:{p.get('title') or url}", body))

    assigns = _get(f"/courses/{course_id}/assignments") or []
    if isinstance(assigns, list):
        for a in assigns:
            body = _text(a.get("description") or "")
            if body:
                items.append((f"assignment:{a.get('name') or a.get('id')}", body))

    return course_name, items


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _inventory(items: list[tuple[str, str]]) -> dict[str, dict]:
    """source -> {count, items:set[label]}."""
    inv: dict[str, dict] = defaultdict(lambda: {"count": 0, "items": set()})
    for label, text in items:
        for src in extract_sources(text):
            inv[src]["count"] += 1
            inv[src]["items"].add(label)
    return inv


def _render(course_id: str, course_name: str, n_items: int, inv: dict[str, dict],
            ts: str, detailed: bool) -> list[str]:
    ranked = sorted(inv.items(), key=lambda kv: (-kv[1]["count"], kv[0].lower()))
    lines = [
        "# Content Representation — Source Inventory  (EXPERIMENTAL, UNWIRED)",
        "",
        f"Course:  {course_name} ({course_id})",
        f"Run at:  {ts}",
        f"Scanned: {n_items} content item(s) (syllabus + pages + assignment descriptions)",
        "",
        "=" * 62,
        "",
        f"Distinct named sources detected: {len(ranked)}",
        "",
        "⚠️  This is REVIEW DATA, not a score. Detection is heuristic (inline",
        "    citations/attributions only); it does NOT infer anyone's demographics.",
        "    'Not detected' ≠ 'not present' — authors in linked files/videos aren't seen.",
        "",
    ]
    if not ranked:
        lines.append("No inline named sources detected. Common when readings are delivered")
        lines.append("as file attachments or external links (the audit can't see inside those).")
        return lines
    lines.append("Named sources (review the mix yourself):")
    for src, d in ranked:
        where = ("  [" + ", ".join(sorted(d["items"])[:3]) +
                 (f", +{len(d['items'])-3} more" if len(d["items"]) > 3 else "") + "]") if detailed else ""
        lines.append(f"  • {src}  —  {d['count']} mention(s){where}")
    return lines


def _render_json(course_id: str, course_name: str, n_items: int,
                 inv: dict[str, dict], ts: str) -> dict:
    return {
        "tool": "content_representation_audit",
        "tool_version": __version__,
        "status": "experimental_unwired",
        "run_at": ts,
        "course": {"id": course_id, "name": course_name},
        "content_items_scanned": n_items,
        "distinct_sources": len(inv),
        "sources": [
            {"source": s, "mentions": d["count"], "items": sorted(d["items"])}
            for s, d in sorted(inv.items(), key=lambda kv: (-kv[1]["count"], kv[0].lower()))
        ],
        "note": "Review data only — representation is a human judgment; demographics are NOT inferred.",
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


def _resolve_course_id(target_env: str, literal: str | None) -> tuple[str, str]:
    if literal:
        return literal.strip(), f"--course-id {literal}"
    val = os.environ.get(target_env, "").strip()
    return val, f"${target_env}"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="EXPERIMENTAL read-only content-source inventory (surfaces named "
                    "sources in course content for human representation review; not a score).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Env var holding the course ID (repo .env ships CANVAS_SANDBOX_ID)")
    ap.add_argument("--course-id", default=None, help="Literal course ID; overrides --target")
    ap.add_argument("--max-pages", type=int, default=80,
                    help="Cap page bodies fetched (N+1 requests; default 80)")
    ap.add_argument("--detailed", action="store_true", help="Show which items each source appears in")
    ap.add_argument("--report", default=None, metavar="PATH", help="Write output to PATH")
    ap.add_argument("--json", action="store_true", dest="emit_json", help="Machine-readable JSON")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="(Read-only; advisory guard. Accepted for symmetry.)")
    args = ap.parse_args()

    if not CANVAS_BASE_URL or CANVAS_BASE_URL == "https://" or not CANVAS_API_TOKEN:
        print("ERROR: set CANVAS_BASE_URL and CANVAS_API_TOKEN in .env.")
        sys.exit(2)

    course_id, source = _resolve_course_id(args.target, args.course_id)
    if not course_id:
        print(f"ERROR: course ID not found via {source}. Pass --course-id <id>.")
        sys.exit(2)

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="read", allow_override=args.allow_enrolled, label="audit target")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    course_name, items = collect_items(course_id, args.max_pages)
    if not items:
        print(f"\nNo readable content fetched for course {course_id}.", file=sys.stderr)
        sys.exit(2)

    inv = _inventory(items)

    if args.emit_json:
        out = json.dumps(_render_json(course_id, course_name, len(items), inv, ts),
                         indent=2, ensure_ascii=False)
        print(out)
        if args.report:
            _write_report(Path(args.report), out)
    else:
        lines = _render(course_id, course_name, len(items), inv, ts, args.detailed)
        print("\n".join(lines))
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    sys.exit(0)


if __name__ == "__main__":
    main()

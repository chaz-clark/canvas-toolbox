"""
course_quality_check.py

Checks a Canvas course for common quality issues and writes a structured
quality report to .canvas/quality_report_{course_id}.json.

Checks performed:
  - Duplicate assignment groups
  - Duplicate assignments / quizzes
  - Duplicate module items (same title in same module)
  - Due / lock / unlock dates outside the course date window

Report output separates issues into two buckets:
  "auto_fixable"  — issues a tool or agent can resolve without human input
  "manual_review" — issues that require human judgment or Canvas UI action

Usage:
    uv run python tools/course_quality_check.py                    # source course (CANVAS_COURSE_ID)
    uv run python tools/course_quality_check.py --master           # MASTER_COURSE_ID
    uv run python tools/course_quality_check.py --blueprint        # BLUEPRINT_COURSE_ID
    uv run python tools/course_quality_check.py --all              # all three
    uv run python tools/course_quality_check.py --course 415322    # specific ID
    uv run python tools/course_quality_check.py --fix              # auto-fix fixable issues (source)
    uv run python tools/course_quality_check.py --fix --master     # auto-fix on master
    uv run python tools/course_quality_check.py --validate-dates   # date audit (read-only)
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from canvas_course_guard import enforce as _course_guard

try:
    from dotenv import load_dotenv
    _env = Path(__file__).parent.parent / ".env"
    if _env.exists():
        load_dotenv(_env)
except ImportError:
    pass

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
CANVAS_BASE_URL = ("https://" + _raw) if _raw and not _raw.startswith("http") else _raw
SOURCE_ID    = os.environ.get("CANVAS_COURSE_ID", "")
MASTER_ID    = os.environ.get("MASTER_COURSE_ID", "")
BLUEPRINT_ID = os.environ.get("BLUEPRINT_COURSE_ID", "")
REPORT_DIR   = Path(".canvas")


def _h():
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get_all(url: str, params: dict = None) -> list:
    results, p = [], {"per_page": 100, **(params or {})}
    while url:
        r = requests.get(url, headers=_h(), params=p, timeout=30)
        if r.status_code >= 400:
            print(f"  WARNING: {r.status_code} fetching {url}")
            return results
        results.extend(r.json())
        url, p = None, {}
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
    return results


def _parse_dt(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.rstrip("Z")).replace(tzinfo=timezone.utc)
    except Exception:
        return None


# Issue #41 — orphan-slug detection. The L13 orphan pattern is specifically:
#   parent_slug present in dup set  AND  same dup set contains parent_slug + "-N"
# A naive "ends in -<digit>" check would over-fire on legitimate week-suffixed
# slugs like `sprint-1-...-w01-w02`. The parent-slug-in-set test filters those
# out — there's no `sprint-1-...-w01` sibling to anchor on.
_ORPHAN_SLUG_SUFFIX_RE = re.compile(r"-(\d+)$")


def _classify_orphan_slug_dup(course_id: str, dups: list) -> dict | None:
    """Detect the L13 orphan-slug pattern in a same-title module-item dup set
    and pull each Page's body to report whether the copies hold identical or
    diverging content.

    Returns None if this is NOT an orphan-slug case. Otherwise returns a dict:
        {"slugs": [...], "bodies_match": bool, "stale_parent": bool,
         "body_summary": {slug: short_hash_or_marker, ...}}
    The caller routes orphan-slug findings to `manual_review` rather than
    auto-deleting, since `--fix`'s lowest-position heuristic can keep stale
    copies and delete canonical ones (issue #41).
    """
    page_dups = [d for d in dups if d.get("type") == "Page" and d.get("page_url")]
    if len(page_dups) < 2:
        return None

    slugs = {d["page_url"] for d in page_dups}
    parent_slug = None
    for slug in slugs:
        m = _ORPHAN_SLUG_SUFFIX_RE.search(slug)
        if m and slug[:m.start()] in slugs:
            parent_slug = slug[:m.start()]
            break
    if parent_slug is None:
        return None

    # Pull each page body and hash a short prefix so we can compare without
    # putting the full HTML in the report. A hash collision on short prefix is
    # acceptable here — the user always re-reads in Canvas before acting.
    import hashlib
    body_summary = {}
    parent_hash = None
    for slug in sorted(slugs):
        try:
            r = requests.get(
                f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/pages/{slug}",
                headers=_h(), timeout=20,
            )
            if r.status_code >= 400:
                body_summary[slug] = f"ERR:{r.status_code}"
                continue
            body = (r.json() or {}).get("body") or ""
            h = hashlib.sha256(body.encode("utf-8")).hexdigest()[:10]
            body_summary[slug] = h
            if slug == parent_slug:
                parent_hash = h
        except Exception as exc:
            body_summary[slug] = f"ERR:{type(exc).__name__}"

    distinct = {h for h in body_summary.values() if not h.startswith("ERR:")}
    bodies_match = len(distinct) <= 1
    # stale_parent: parent slug body hash differs from at least one suffixed copy
    stale_parent = False
    if parent_hash:
        suffixed_hashes = {
            h for slug, h in body_summary.items()
            if slug != parent_slug and not h.startswith("ERR:")
        }
        # Parent is stale if every suffixed copy disagrees with it
        if suffixed_hashes and parent_hash not in suffixed_hashes:
            stale_parent = True

    return {
        "slugs": sorted(slugs),
        "parent_slug": parent_slug,
        "bodies_match": bodies_match,
        "stale_parent": stale_parent,
        "body_summary": body_summary,
    }


def _get_course_window(course_id: str) -> tuple:
    """Return (start_at, end_at) as datetime objects."""
    idx_path = Path(".canvas/index.json")
    if str(course_id) == str(SOURCE_ID) and idx_path.exists():
        idx = json.loads(idx_path.read_text())
        c = idx.get("course", {})
        s = _parse_dt(c.get("start_at"))
        e = _parse_dt(c.get("end_at"))
        if s and e:
            return s, e

    r = requests.get(f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}", headers=_h(), timeout=20)
    if r.ok:
        d = r.json()
        return _parse_dt(d.get("start_at")), _parse_dt(d.get("end_at"))
    return None, None


_WEEK_RE   = re.compile(r'\bWeek\s+(\d+)\b', re.IGNORECASE)
_SPRINT_RE = re.compile(r'\bS\s*(\d+)\b')   # uppercase S only — avoids false positives on "s" words


def _week_of_course(dt: datetime, start_at: datetime) -> int | None:
    delta = (dt.date() - start_at.date()).days
    return delta // 7 + 1 if delta >= 0 else None


def _sprint_of_course(dt: datetime, start_at: datetime, sprint_weeks: int = 2) -> int | None:
    delta = (dt.date() - start_at.date()).days
    return delta // (sprint_weeks * 7) + 1 if delta >= 0 else None


def _audit_course(course_id: str) -> dict:
    """
    Run all checks. Returns a dict with:
        course_id, label, start_at, end_at,
        auto_fixable: [...],   # can be resolved programmatically
        manual_review: [...]   # require human judgment
    """
    base = CANVAS_BASE_URL
    auto_fixable = []
    manual_review = []

    start_at, end_at = _get_course_window(course_id)

    # ── Assignment groups ──────────────────────────────────────
    groups = _get_all(f"{base}/api/v1/courses/{course_id}/assignment_groups")
    group_counts = Counter(g["name"] for g in groups)
    for name, count in group_counts.items():
        if count > 1:
            dups = [g for g in groups if g["name"] == name][1:]  # keep first, delete rest
            for g in dups:
                auto_fixable.append({
                    "type": "duplicate_assignment_group",
                    "title": name,
                    "canvas_id": g["id"],
                    "action": f"DELETE /api/v1/courses/{course_id}/assignment_groups/{g['id']}",
                    "note": f"Duplicate assignment group '{name}' (id={g['id']})"
                })

    # ── Assignments ────────────────────────────────────────────
    assignments = _get_all(f"{base}/api/v1/courses/{course_id}/assignments")
    by_name = defaultdict(list)
    for a in assignments:
        by_name[a["name"]].append(a)

    for name, items in by_name.items():
        if len(items) > 1:
            # Sort by id ascending — lowest id is oldest (original)
            items_sorted = sorted(items, key=lambda x: x["id"])
            # Blueprint-locked copy is canonical — newer, higher ID. "Keep oldest" is wrong here.
            bp_locked = [a for a in items_sorted if a.get("locked_by_master_course")]
            if bp_locked:
                keep_id = bp_locked[0]["id"]
                copies = [
                    {
                        "canvas_id": a["id"],
                        "due_at": a.get("due_at"),
                        "allowed_extensions": a.get("allowed_extensions", []),
                        "blueprint_locked": bool(a.get("locked_by_master_course")),
                    }
                    for a in items_sorted
                ]
                manual_review.append({
                    "type": "duplicate_assignment",
                    "title": name,
                    "copies": copies,
                    "note": (
                        f"Duplicate assignment '{name}' — Blueprint-locked copy (id={keep_id}) is canonical; "
                        "delete non-locked copies manually. "
                        "Likely cause: direct push overlapping a Blueprint sync."
                    ),
                    "action": f"Canvas UI → Assignments — delete copies other than id={keep_id}",
                })
            else:
                for dup in items_sorted[1:]:
                    auto_fixable.append({
                        "type": "duplicate_assignment",
                        "title": name,
                        "canvas_id": dup["id"],
                        "action": f"DELETE /api/v1/courses/{course_id}/assignments/{dup['id']}",
                        "note": f"Duplicate assignment '{name}' (id={dup['id']})"
                    })

    # Date checks — assignments
    if start_at and end_at:
        for a in assignments:
            name = a["name"]
            published = a.get("published", True)
            for field in ("due_at", "lock_at", "unlock_at"):
                dt = _parse_dt(a.get(field))
                if dt and not (start_at <= dt <= end_at):
                    entry = {
                        "type": "date_out_of_window",
                        "item_type": "assignment",
                        "published": published,
                        "title": name,
                        "canvas_id": a["id"],
                        "field": field,
                        "value": a.get(field),
                        "course_window": f"{start_at.date()} → {end_at.date()}",
                        "action": f"PUT /api/v1/courses/{course_id}/assignments/{a['id']} — update {field}",
                        "note": f"{'[UNPUBLISHED] ' if not published else ''}Assignment '{name}' {field}={a.get(field)[:10]} is outside course window"
                    }
                    if published:
                        auto_fixable.append(entry)
                    else:
                        manual_review.append(entry)

    # ── Quizzes ────────────────────────────────────────────────
    quizzes = _get_all(f"{base}/api/v1/courses/{course_id}/quizzes")
    qby_name = defaultdict(list)
    for q in quizzes:
        qby_name[q["title"]].append(q)

    for title, items in qby_name.items():
        if len(items) > 1:
            items_sorted = sorted(items, key=lambda x: x["id"])
            bp_locked = [q for q in items_sorted if q.get("locked_by_master_course")]
            if bp_locked:
                keep_id = bp_locked[0]["id"]
                copies = [
                    {
                        "canvas_id": q["id"],
                        "due_at": q.get("due_at"),
                        "blueprint_locked": bool(q.get("locked_by_master_course")),
                    }
                    for q in items_sorted
                ]
                manual_review.append({
                    "type": "duplicate_quiz",
                    "title": title,
                    "copies": copies,
                    "note": (
                        f"Duplicate quiz '{title}' — Blueprint-locked copy (id={keep_id}) is canonical; "
                        "delete non-locked copies manually. "
                        "Likely cause: direct push overlapping a Blueprint sync."
                    ),
                    "action": f"Canvas UI → Quizzes — delete copies other than id={keep_id}",
                })
            else:
                for dup in items_sorted[1:]:
                    auto_fixable.append({
                        "type": "duplicate_quiz",
                        "title": title,
                        "canvas_id": dup["id"],
                        "action": f"DELETE /api/v1/courses/{course_id}/quizzes/{dup['id']}",
                        "note": f"Duplicate quiz '{title}' (id={dup['id']})"
                    })

    if start_at and end_at:
        for q in quizzes:
            published = q.get("published", True)
            for field in ("due_at", "lock_at", "unlock_at"):
                dt = _parse_dt(q.get(field))
                if dt and not (start_at <= dt <= end_at):
                    entry = {
                        "type": "date_out_of_window",
                        "item_type": "quiz",
                        "published": published,
                        "title": q["title"],
                        "canvas_id": q["id"],
                        "field": field,
                        "value": q.get(field),
                        "course_window": f"{start_at.date()} → {end_at.date()}",
                        "action": f"PUT /api/v1/courses/{course_id}/quizzes/{q['id']} — update {field}",
                        "note": f"{'[UNPUBLISHED] ' if not published else ''}Quiz '{q['title']}' {field}={q.get(field)[:10]} is outside course window"
                    }
                    if published:
                        auto_fixable.append(entry)
                    else:
                        manual_review.append(entry)

    # ── Module items ───────────────────────────────────────────
    # Build a set of content IDs AND titles that appear in any module
    # Canvas module item types: "Assignment", "Quiz", "Discussion", "Page", etc.
    modules = _get_all(f"{base}/api/v1/courses/{course_id}/modules", {"include[]": ["items"]})
    module_content_ids: dict[str, set] = defaultdict(set)  # type → set of content_ids
    module_item_titles: set = set()  # all titles present in any module (lowercase for fuzzy-safe exact match)
    for mod in modules:
        items = mod.get("items") or _get_all(
            f"{base}/api/v1/courses/{course_id}/modules/{mod['id']}/items"
        )
        title_map = defaultdict(list)
        for it in items:
            title_map[it.get("title", "")].append(it)
            ctype = it.get("type", "")
            cid_val = it.get("content_id")
            if cid_val:
                module_content_ids[ctype].add(cid_val)
            if it.get("title"):
                module_item_titles.add(it["title"].strip().lower())

        for title, dups in title_map.items():
            if len(dups) > 1 and title:
                # Issue #41 — orphan-slug pattern (L13): when same-title Page
                # dups include parent_slug AND parent_slug+"-N", the lowest-
                # position-keep heuristic can keep stale copies and delete
                # canonical ones. Route those to manual_review with a content
                # comparison instead of auto-deleting.
                orphan_info = _classify_orphan_slug_dup(course_id, dups)
                if orphan_info is not None:
                    severity = "URGENT" if orphan_info["stale_parent"] else "review"
                    content_note = (
                        "bodies match across all copies"
                        if orphan_info["bodies_match"]
                        else "BODIES DIFFER — content not identical across copies"
                    )
                    if orphan_info["stale_parent"]:
                        content_note += (
                            f" — parent slug '{orphan_info['parent_slug']}' "
                            f"is STALE vs. its suffixed copies (--fix would have "
                            f"deleted the canonical copies)"
                        )
                    manual_review.append({
                        "type": "orphan_slug_duplicate",
                        "module": mod["name"],
                        "title": title,
                        "parent_slug": orphan_info["parent_slug"],
                        "slugs": orphan_info["slugs"],
                        "bodies_match": orphan_info["bodies_match"],
                        "stale_parent": orphan_info["stale_parent"],
                        "body_summary": orphan_info["body_summary"],
                        "severity": severity,
                        "action": "Run blueprint_orphan_pages.py for content-aware cleanup (see #40 Phase 2).",
                        "note": (
                            f"[{severity}] Orphan-slug dup in '{mod['name']}': "
                            f"'{title}' — slugs {orphan_info['slugs']} share parent "
                            f"'{orphan_info['parent_slug']}'; {content_note}. "
                            f"--fix CANNOT safely resolve this (issue #41, L13)."
                        ),
                    })
                    continue  # do NOT add to auto_fixable
                # Keep lowest position (first in module), remove rest
                dups_sorted = sorted(dups, key=lambda x: x.get("position", 999))
                for dup in dups_sorted[1:]:
                    auto_fixable.append({
                        "type": "duplicate_module_item",
                        "module": mod["name"],
                        "title": title,
                        "canvas_id": dup["id"],
                        "position": dup.get("position"),
                        "action": f"DELETE /api/v1/courses/{course_id}/modules/{mod['id']}/items/{dup['id']}",
                        "note": f"Duplicate module item in '{mod['name']}': '{title}' (item_id={dup['id']}, pos={dup.get('position')})"
                    })

    # ── Published content not linked in any module ─────────────
    # Canvas classic quizzes have TWO IDs: quiz_id (in /quizzes) and an underlying
    # assignment_id (in /assignments with submission_types=['online_quiz']).
    # Module items for quizzes store the quiz_id, not the assignment_id.
    # Build a lookup: assignment_id → quiz_id so we can cross-check correctly.
    quiz_assignment_id_to_quiz_id = {q.get("assignment_id"): q["id"]
                                     for q in quizzes if q.get("assignment_id")}

    for a in assignments:
        if not a.get("published", False):
            continue
        # If this assignment is the shell for a classic quiz, check the quiz_id in Quiz bucket
        quiz_id_for_assignment = quiz_assignment_id_to_quiz_id.get(a["id"])
        if quiz_id_for_assignment:
            in_module = quiz_id_for_assignment in module_content_ids["Quiz"]
        else:
            in_module = a["id"] in module_content_ids["Assignment"]
        if not in_module:
            name = a["name"]
            # If same title is already in a module under a different ID, it's an orphan duplicate
            same_name_in_module = name.strip().lower() in module_item_titles
            if same_name_in_module:
                auto_fixable.append({
                    "type": "orphaned_duplicate",
                    "item_type": "assignment",
                    "title": name,
                    "canvas_id": a["id"],
                    "note": f"Orphaned assignment '{name}' (id={a['id']}) — same title already in a module under a different ID, this copy is unreachable",
                    "action": f"DELETE /api/v1/courses/{course_id}/assignments/{a['id']}"
                })
            else:
                manual_review.append({
                    "type": "published_not_in_module",
                    "item_type": "assignment",
                    "title": name,
                    "canvas_id": a["id"],
                    "note": f"Published assignment '{name}' (id={a['id']}) is not linked in any module — students cannot find it",
                    "action": f"Add to the appropriate module via Canvas UI or POST /api/v1/courses/{course_id}/modules/:module_id/items"
                })

    # Discussions
    discussions = _get_all(f"{base}/api/v1/courses/{course_id}/discussion_topics")
    for d in discussions:
        if not d.get("published", False):
            continue
        in_module = d["id"] in module_content_ids["Discussion"]
        if not in_module:
            title = d["title"]
            same_name_in_module = title.strip().lower() in module_item_titles
            if same_name_in_module:
                auto_fixable.append({
                    "type": "orphaned_duplicate",
                    "item_type": "discussion",
                    "title": title,
                    "canvas_id": d["id"],
                    "note": f"Orphaned discussion '{title}' (id={d['id']}) — same title already in a module under a different ID",
                    "action": f"DELETE /api/v1/courses/{course_id}/discussion_topics/{d['id']}"
                })
            else:
                manual_review.append({
                    "type": "published_not_in_module",
                    "item_type": "discussion",
                    "title": title,
                    "canvas_id": d["id"],
                    "note": f"Published discussion '{title}' (id={d['id']}) is not linked in any module — students cannot find it",
                    "action": f"Add to the appropriate module via Canvas UI or POST /api/v1/courses/{course_id}/modules/:module_id/items"
                })

    # ── Empty modules ──────────────────────────────────────────
    for mod in modules:
        items = mod.get("items") or []
        if len(items) == 0:
            manual_review.append({
                "type": "empty_module",
                "title": mod["name"],
                "canvas_id": mod["id"],
                "note": f"Module '{mod['name']}' (id={mod['id']}) has no items — may be a sync artifact",
                "action": "Delete via Canvas UI or DELETE /api/v1/courses/{}/modules/{}".format(course_id, mod["id"])
            })

    # ── Course-level manual review items ───────────────────────
    if not start_at or not end_at:
        # Master/template courses intentionally have no dates — only flag for non-master courses
        if str(course_id) != str(MASTER_ID):
            manual_review.append({
                "type": "missing_course_dates",
                "note": "Course has no start_at or end_at set — date window checks were skipped.",
                "action": "Set course start and end dates in Canvas Settings > Course Details"
            })

    # Quiz questions — if a classic quiz has 0 questions it's an empty shell
    for q in quizzes:
        if q.get("quiz_type") != "assignment" and q.get("question_count", 1) == 0:
            manual_review.append({
                "type": "empty_quiz",
                "title": q["title"],
                "canvas_id": q["id"],
                "note": f"Quiz '{q['title']}' has 0 questions.",
                "action": "Use canvas_quiz_questions.py --push <questions-file.json> to add questions"
            })

    return {
        "course_id": course_id,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "course_window": {
            "start_at": start_at.isoformat() if start_at else None,
            "end_at": end_at.isoformat() if end_at else None,
        },
        "auto_fixable": auto_fixable,
        "manual_review": manual_review,
        "summary": {
            "auto_fixable": len(auto_fixable),
            "manual_review": len(manual_review),
            "total_issues": len(auto_fixable) + len(manual_review),
        }
    }


def _print_report(report: dict, label: str):
    cid = report["course_id"]
    w = report["course_window"]
    af = report["auto_fixable"]
    mr = report["manual_review"]

    print(f"\n{'='*62}")
    print(f"  {label} — Course {cid}")
    if w["start_at"] and w["end_at"]:
        print(f"  Window: {w['start_at'][:10]} → {w['end_at'][:10]}")
    else:
        print(f"  Window: NOT SET")
    print(f"{'='*62}")

    if not af and not mr:
        print("  All checks passed — no issues found.")
        return

    if af:
        print(f"\n  AUTO-FIXABLE ({len(af)}) — tools/agents can resolve:")
        by_type = defaultdict(list)
        for item in af:
            by_type[item["type"]].append(item)
        for t, items in by_type.items():
            print(f"    [{t}] x{len(items)}")
            for it in items:
                print(f"      • {it['note']}")

    if mr:
        print(f"\n  MANUAL REVIEW ({len(mr)}) — requires human action:")
        for it in mr:
            print(f"    • {it['note']}")
            print(f"      → {it['action']}")


# ---------------------------------------------------------------------------
# Alignment-chain audit (issue #18, read-only)
# ---------------------------------------------------------------------------

_ALIGNMENT_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "for", "on", "with", "by",
    "is", "are", "be", "will", "shall", "can", "may", "should", "would", "could",
    "this", "that", "these", "those", "it", "its", "as", "at", "from", "into",
    "students", "student", "you", "your", "their", "they", "them", "we", "our", "us",
    "have", "has", "had", "do", "does", "did", "been", "being", "having",
    "course", "module", "week", "weekly", "assignment", "outcome", "outcomes", "objective", "objectives",
    "able", "demonstrate", "complete", "completed", "show", "include", "includes",
}


def _alignment_tokens(text: str) -> set:
    """Tokenize for alignment matching: lowercase, strip punctuation, drop short/stop words."""
    if not text:
        return set()
    # Strip HTML tags first
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.lower()
    # Replace punctuation with spaces
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = {t for t in text.split() if len(t) >= 4 and t not in _ALIGNMENT_STOPWORDS}
    return tokens


def _extract_outcomes_from_html(html: str) -> list:
    """Heuristic: find an Outcomes/Objectives section, return its list items as outcome strings.

    Looks for a heading containing 'outcome' or 'objective' and extracts the next <ul>/<ol>
    block. Falls back to numbered-paragraph patterns if no list is found.
    """
    if not html:
        return []
    outcomes: list = []

    # Pattern: header containing "outcomes" or "objectives", followed by list items
    # Match <h\d>...outcomes...</h\d>...<ul/ol>...</ul/ol>
    section_pattern = re.compile(
        r"<h[1-6][^>]*>[^<]*(?:outcome|objective|goal)s?[^<]*</h[1-6]>(.*?)(?=<h[1-6]|$)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in section_pattern.finditer(html):
        section = m.group(1)
        # Extract <li> items
        for li in re.findall(r"<li[^>]*>(.*?)</li>", section, re.IGNORECASE | re.DOTALL):
            text = re.sub(r"<[^>]+>", " ", li).strip()
            text = re.sub(r"\s+", " ", text)
            if text and len(text) >= 10:
                outcomes.append(text)
        # Or numbered paragraphs like "<p>1. Students will..."
        if not outcomes:
            for p in re.findall(r"<p[^>]*>\s*\d+[\.\)]\s*(.*?)</p>", section, re.IGNORECASE | re.DOTALL):
                text = re.sub(r"<[^>]+>", " ", p).strip()
                text = re.sub(r"\s+", " ", text)
                if text and len(text) >= 10:
                    outcomes.append(text)

    return outcomes


def _audit_alignment(course_id: str, label: str = "") -> dict:
    """Alignment-chain audit (issue #18, read-only).

    Walks the chain: Course Outcome → Module Outcome → Rubric Criterion → Activity.
    Flags breaks at each link. Heuristic text-based matching — false positives
    expected; treat as a starting point for instructor review.

    Returns:
      summary: counts of outcomes / criteria / breaks
      course_outcomes: extracted from syllabus.html with token sets
      module_outcomes: per-module extracted outcomes
      rubric_criteria: per-assignment rubric criteria
      breaks:
        course_outcomes_no_rubric: course outcomes with no matching rubric criterion
        rubric_criteria_no_outcome: criteria with no matching upstream outcome
        module_outcomes_no_rubric: module outcomes with no matching rubric criterion
    """
    course_outcomes_text: list = []
    module_outcomes_text: list = []  # [{module_slug, outcome_text}]
    rubric_criteria: list = []  # [{assignment_id, assignment_name, criterion_description, criterion_long_description}]

    # 1. Course outcomes from local syllabus.html (or fall back to API)
    syllabus_path = Path("course/syllabus.html")
    if syllabus_path.exists():
        syllabus_html = syllabus_path.read_text(encoding="utf-8")
        course_outcomes_text = _extract_outcomes_from_html(syllabus_html)
    else:
        # Fall back: fetch syllabus body via API
        course_meta = _get_all(f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}",
                               params={"include[]": "syllabus_body"})
        body = ""
        if isinstance(course_meta, list) and course_meta:
            body = course_meta[0].get("syllabus_body", "")
        elif isinstance(course_meta, dict):
            body = course_meta.get("syllabus_body", "")
        course_outcomes_text = _extract_outcomes_from_html(body)

    # 2. Module outcomes from each module's overview page (heuristic — first .html in each module dir)
    course_dir = Path("course")
    if course_dir.exists():
        for module_dir in sorted(course_dir.iterdir()):
            if not module_dir.is_dir():
                continue
            slug = module_dir.name
            # Look for an overview-like file: contains "overview" or "intro" in name
            overview_files = sorted(module_dir.glob("*overview*.html")) + sorted(module_dir.glob("*intro*.html"))
            if not overview_files:
                # Fall back to the first .html file in the module
                html_files = sorted(module_dir.glob("*.html"))
                overview_files = html_files[:1]
            for f in overview_files:
                try:
                    html = f.read_text(encoding="utf-8")
                    for outcome in _extract_outcomes_from_html(html):
                        module_outcomes_text.append({"module_slug": slug, "source": str(f), "outcome": outcome})
                except Exception:
                    pass

    # 3. Rubric criteria — fetch each assignment with include[]=rubric
    assignments = _get_all(f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/assignments",
                           params={"per_page": 100, "include[]": "rubric"})
    for a in assignments:
        rubric = a.get("rubric") or []
        for criterion in rubric:
            rubric_criteria.append({
                "assignment_id": a.get("id"),
                "assignment_name": a.get("name"),
                "criterion_description": criterion.get("description", ""),
                "criterion_long_description": criterion.get("long_description", ""),
            })

    # 4. Compute token overlaps
    co_tokens = [(t, _alignment_tokens(t)) for t in course_outcomes_text]
    mo_tokens = [(m, _alignment_tokens(m["outcome"])) for m in module_outcomes_text]
    rc_tokens = [(c, _alignment_tokens(c["criterion_description"] + " " + (c.get("criterion_long_description") or ""))) for c in rubric_criteria]

    def _overlaps(toks_a: set, toks_b: set, threshold: int = 2) -> bool:
        return len(toks_a & toks_b) >= threshold

    # 5. Find breaks
    course_outcomes_no_rubric = []
    for outcome_text, toks in co_tokens:
        matches = [c.get("criterion_description") for c, ctoks in rc_tokens if _overlaps(toks, ctoks)]
        if not matches:
            course_outcomes_no_rubric.append({"outcome": outcome_text, "matched_criteria": []})

    rubric_criteria_no_outcome = []
    for criterion, ctoks in rc_tokens:
        matched_co = [t for t, ttoks in co_tokens if _overlaps(ctoks, ttoks)]
        matched_mo = [m["outcome"] for m, mtoks in mo_tokens if _overlaps(ctoks, mtoks)]
        if not matched_co and not matched_mo:
            rubric_criteria_no_outcome.append({
                "assignment_name": criterion.get("assignment_name"),
                "criterion_description": criterion.get("criterion_description"),
            })

    module_outcomes_no_rubric = []
    for m, toks in mo_tokens:
        matched = [c.get("criterion_description") for c, ctoks in rc_tokens if _overlaps(toks, ctoks)]
        if not matched:
            module_outcomes_no_rubric.append({"module_slug": m["module_slug"], "outcome": m["outcome"]})

    summary = {
        "course_id": course_id,
        "label": label,
        "course_outcomes_count": len(course_outcomes_text),
        "module_outcomes_count": len(module_outcomes_text),
        "rubric_criteria_count": len(rubric_criteria),
        "assignments_with_rubric": sum(1 for a in assignments if a.get("rubric")),
        "assignments_without_rubric": sum(1 for a in assignments if not a.get("rubric")),
        "breaks": {
            "course_outcomes_no_rubric": len(course_outcomes_no_rubric),
            "rubric_criteria_no_outcome": len(rubric_criteria_no_outcome),
            "module_outcomes_no_rubric": len(module_outcomes_no_rubric),
        },
    }

    return {
        "summary": summary,
        "course_outcomes": course_outcomes_text,
        "module_outcomes": module_outcomes_text,
        "rubric_criteria_sample": rubric_criteria[:20],
        "breaks": {
            "course_outcomes_no_rubric": course_outcomes_no_rubric,
            "rubric_criteria_no_outcome": rubric_criteria_no_outcome,
            "module_outcomes_no_rubric": module_outcomes_no_rubric,
        },
    }


def _print_alignment_report(report: dict, label: str):
    s = report["summary"]
    print(f"\n{'='*62}\n  Alignment Audit — {label}\n{'='*62}")
    print(f"  Course outcomes (syllabus):   {s['course_outcomes_count']}")
    print(f"  Module outcomes (extracted):  {s['module_outcomes_count']}")
    print(f"  Rubric criteria total:        {s['rubric_criteria_count']}")
    print(f"  Assignments with rubric:      {s['assignments_with_rubric']}")
    print(f"  Assignments without rubric:   {s['assignments_without_rubric']}")

    b = s["breaks"]
    print(f"\n  Alignment breaks:")
    print(f"    Course outcomes with no matching rubric criterion: {b['course_outcomes_no_rubric']}")
    print(f"    Rubric criteria with no matching outcome:          {b['rubric_criteria_no_outcome']}")
    print(f"    Module outcomes with no matching rubric criterion: {b['module_outcomes_no_rubric']}")

    if s["course_outcomes_count"] == 0:
        print(f"\n  ⚠  No course outcomes extracted from syllabus.html.")
        print(f"     The syllabus may not use a recognizable outcomes/objectives section.")
        print(f"     Heuristic looks for a heading containing 'outcome' or 'objective' followed by a list.")

    breaks = report["breaks"]
    if breaks["course_outcomes_no_rubric"]:
        print(f"\n  Course outcomes with no matching rubric criterion (top 5):")
        for b in breaks["course_outcomes_no_rubric"][:5]:
            print(f"    • {b['outcome'][:90]}{'…' if len(b['outcome']) > 90 else ''}")

    if breaks["rubric_criteria_no_outcome"]:
        print(f"\n  Rubric criteria with no matching outcome (top 5):")
        for b in breaks["rubric_criteria_no_outcome"][:5]:
            print(f"    • {b['assignment_name']} → \"{b['criterion_description'][:60]}\"")

    print(f"\n  ⚠  Heuristic text-matching produces false positives — review before acting.")


def _write_alignment_md_report(reports: list[dict], labels: dict, path: Path):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Canvas Course Alignment Audit",
        f"Generated: {now}",
        "",
        "Read-only audit of the alignment chain: Course Outcome → Module Outcome → Rubric Criterion → Activity.",
        "Heuristic text-matching — false positives expected; treat as starting point for instructor review.",
        "",
    ]
    for r in reports:
        s = r["summary"]
        b = s["breaks"]
        label = s.get("label") or s["course_id"]
        lines += [
            f"## {label}",
            "",
            f"- **Course outcomes** (extracted from syllabus.html): {s['course_outcomes_count']}",
            f"- **Module outcomes** (extracted from module pages): {s['module_outcomes_count']}",
            f"- **Rubric criteria** (across all assignments): {s['rubric_criteria_count']}",
            f"- **Assignments with rubric**: {s['assignments_with_rubric']}",
            f"- **Assignments without rubric**: {s['assignments_without_rubric']}",
            "",
            "### Alignment breaks",
            "",
            f"- Course outcomes with no matching rubric criterion: **{b['course_outcomes_no_rubric']}**",
            f"- Rubric criteria with no matching outcome: **{b['rubric_criteria_no_outcome']}**",
            f"- Module outcomes with no matching rubric criterion: **{b['module_outcomes_no_rubric']}**",
            "",
        ]
        breaks = r["breaks"]
        if breaks["course_outcomes_no_rubric"]:
            lines += ["#### Course outcomes with no rubric coverage", ""]
            for entry in breaks["course_outcomes_no_rubric"]:
                lines.append(f"- {entry['outcome']}")
            lines.append("")
        if breaks["rubric_criteria_no_outcome"]:
            lines += ["#### Rubric criteria with no upstream outcome", "",
                      "| Assignment | Criterion |", "|---|---|"]
            for entry in breaks["rubric_criteria_no_outcome"]:
                lines.append(f"| {entry['assignment_name']} | {entry['criterion_description']} |")
            lines.append("")
        if breaks["module_outcomes_no_rubric"]:
            lines += ["#### Module outcomes with no rubric coverage", "",
                      "| Module | Outcome |", "|---|---|"]
            for entry in breaks["module_outcomes_no_rubric"]:
                lines.append(f"| {entry['module_slug']} | {entry['outcome']} |")
            lines.append("")
    path.write_text("\n".join(lines))


def _audit_files(course_id: str, label: str = "") -> dict:
    """Files audit: orphans, broken references, likely duplicates (issue #17, read-only).

    Reads index["linked_files"] from .canvas/index.json (built by canvas_sync.py
    via /courses/X/files/N reference scanning) and cross-references with the
    full Canvas Files inventory at GET /courses/:id/files.

    Returns a dict with:
      summary: counts and sizes
      orphans: files in Canvas but not referenced from any content
      broken_references: file IDs referenced from content but missing from Canvas
      duplicates: files with same display_name but different IDs
    """
    # Read linked_files reverse map from canvas_sync's index
    index_path = Path(".canvas/index.json")
    linked_files = {}
    if index_path.exists():
        try:
            idx = json.loads(index_path.read_text())
            linked_files = idx.get("linked_files", {})
        except Exception:
            pass

    # Fetch full Canvas Files inventory
    inventory = _get_all(f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/files",
                         params={"per_page": 100})
    inventory_by_id = {f["id"]: f for f in inventory}
    inventory_ids = set(inventory_by_id.keys())
    linked_ids = {int(fid) for fid in linked_files.keys()}

    # Orphans: in Canvas but not referenced
    orphan_ids = inventory_ids - linked_ids
    orphans = []
    orphan_size = 0
    for fid in orphan_ids:
        f = inventory_by_id[fid]
        size = f.get("size") or 0
        orphan_size += size
        orphans.append({
            "canvas_file_id": fid,
            "filename": f.get("filename"),
            "display_name": f.get("display_name"),
            "size": size,
            "uploaded_at": f.get("created_at") or f.get("updated_at"),
            "folder_id": f.get("folder_id"),
            "url": f.get("url"),
        })
    orphans.sort(key=lambda x: -(x["size"] or 0))

    # Broken references: referenced from content but file deleted from Canvas
    broken_ids = linked_ids - inventory_ids
    broken_references = []
    for fid in broken_ids:
        entry = linked_files.get(str(fid), {})
        broken_references.append({
            "missing_file_id": fid,
            "referenced_by": entry.get("referenced_by", []),
        })

    # Duplicates: same display_name, different IDs
    by_name: dict = {}
    for f in inventory:
        name = (f.get("display_name") or f.get("filename") or "?").strip()
        by_name.setdefault(name, []).append(f)
    duplicates = []
    for name, instances in by_name.items():
        if len(instances) > 1:
            duplicates.append({
                "display_name": name,
                "instances": [{
                    "canvas_file_id": f["id"],
                    "size": f.get("size", 0),
                    "uploaded_at": f.get("created_at") or f.get("updated_at"),
                    "referenced": f["id"] in linked_ids,
                } for f in instances],
            })

    total_size = sum((f.get("size") or 0) for f in inventory)
    summary = {
        "course_id": course_id,
        "label": label,
        "total_files": len(inventory),
        "referenced_count": len(inventory_ids & linked_ids),
        "orphan_count": len(orphans),
        "broken_reference_count": len(broken_references),
        "duplicate_groups": len(duplicates),
        "total_size_bytes": total_size,
        "orphan_size_bytes": orphan_size,
        "linked_files_data_available": bool(linked_files),
    }

    return {
        "summary": summary,
        "orphans": orphans,
        "broken_references": broken_references,
        "duplicates": duplicates,
    }


def _format_size_bytes(size_bytes: int) -> str:
    """Human-readable byte count."""
    if size_bytes is None:
        return "?"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} PB"


def _print_files_report(report: dict, label: str):
    """Pretty-print a files audit to stdout."""
    s = report["summary"]
    print(f"\n{'='*62}\n  Files Audit — {label}\n{'='*62}")
    print(f"  Total files in Canvas:    {s['total_files']}")
    print(f"  Referenced by content:    {s['referenced_count']}"
          + (f"  ({100*s['referenced_count']//max(s['total_files'],1)}%)" if s["total_files"] else ""))
    print(f"  Orphans (unreferenced):   {s['orphan_count']}")
    print(f"  Broken references:        {s['broken_reference_count']}")
    print(f"  Duplicate-name groups:    {s['duplicate_groups']}")
    print(f"  Total storage:            {_format_size_bytes(s['total_size_bytes'])}")
    print(f"  Orphan storage:           {_format_size_bytes(s['orphan_size_bytes'])}  ← cleanup candidate")

    if not s["linked_files_data_available"]:
        print(f"\n  ⚠  No linked_files data — orphan/broken-reference accuracy degraded.")
        print(f"     Run: uv run python tools/canvas_sync.py --pull")
        print(f"     (canvas_sync scans content for /courses/X/files/N references and")
        print(f"      writes the reverse map this audit consumes.)")

    if report["orphans"]:
        top = report["orphans"][:10]
        print(f"\n  Top {len(top)} orphans by size:")
        for o in top:
            name = (o["display_name"] or o["filename"] or "?")[:50]
            print(f"    {_format_size_bytes(o['size']):>10}  {name:<50}  id={o['canvas_file_id']}")

    if report["broken_references"]:
        print(f"\n  Broken references ({len(report['broken_references'])}):")
        for br in report["broken_references"][:10]:
            print(f"    file_id={br['missing_file_id']} referenced by:")
            for src in br["referenced_by"][:3]:
                print(f"      - {src}")
            if len(br["referenced_by"]) > 3:
                print(f"      + {len(br['referenced_by']) - 3} more")

    if report["duplicates"]:
        print(f"\n  Likely duplicates ({len(report['duplicates'])} groups):")
        for d in report["duplicates"][:5]:
            unrefs = sum(1 for i in d["instances"] if not i["referenced"])
            print(f"    \"{d['display_name']}\" — {len(d['instances'])} copies, {unrefs} unreferenced")


def _write_files_md_report(reports: list[dict], labels: dict, path: Path):
    """Append/overwrite the files audit section in quality_report.md."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Canvas Course Files Audit",
        f"Generated: {now}",
        "",
        "Read-only audit of file storage and references. Run via:",
        "`uv run python tools/course_quality_check.py --files`",
        "",
    ]
    for r in reports:
        s = r["summary"]
        label = s.get("label") or s["course_id"]
        lines += [
            f"## {label}",
            "",
            f"- **Total files in Canvas**: {s['total_files']}",
            f"- **Referenced by content**: {s['referenced_count']}",
            f"- **Orphans (unreferenced)**: {s['orphan_count']}",
            f"- **Broken references**: {s['broken_reference_count']}",
            f"- **Duplicate-name groups**: {s['duplicate_groups']}",
            f"- **Total storage**: {_format_size_bytes(s['total_size_bytes'])}",
            f"- **Orphan storage**: {_format_size_bytes(s['orphan_size_bytes'])} (cleanup candidate)",
            "",
        ]
        if not s["linked_files_data_available"]:
            lines += [
                "> ⚠ No `linked_files` data found in `.canvas/index.json`. Run `canvas_sync.py --pull` first.",
                "",
            ]
        if r["orphans"]:
            lines += ["### Top orphans by size", "", "| Size | Display name | Filename | ID |", "|---|---|---|---|"]
            for o in r["orphans"][:20]:
                lines.append(
                    f"| {_format_size_bytes(o['size'])} | {o.get('display_name') or '—'} | "
                    f"{o.get('filename') or '—'} | {o['canvas_file_id']} |"
                )
            lines.append("")
        if r["broken_references"]:
            lines += ["### Broken references", "",
                      "| Missing file ID | Referenced from |", "|---|---|"]
            for br in r["broken_references"]:
                refs = "<br>".join(br["referenced_by"][:3])
                if len(br["referenced_by"]) > 3:
                    refs += f"<br>+ {len(br['referenced_by']) - 3} more"
                lines.append(f"| {br['missing_file_id']} | {refs or '—'} |")
            lines.append("")
        if r["duplicates"]:
            lines += ["### Likely duplicates (same display name)", "",
                      "| Display name | Copies | Unreferenced |", "|---|---|---|"]
            for d in r["duplicates"]:
                unrefs = sum(1 for i in d["instances"] if not i["referenced"])
                lines.append(f"| {d['display_name']} | {len(d['instances'])} | {unrefs} |")
            lines.append("")
    path.write_text("\n".join(lines))


def _write_md_report(reports: list[dict], labels: dict, path: Path):
    """Write a combined markdown quality report for all audited courses."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Canvas Course Quality Report",
        f"Generated: {now}",
        "",
    ]

    # Overall summary table
    lines += ["## Summary", ""]
    lines += ["| Course | Window | Auto-Fixable | Manual Review | Status |"]
    lines += ["|--------|--------|:------------:|:-------------:|--------|"]
    for r in reports:
        cid = r["course_id"]
        label = labels.get(cid, f"Course {cid}")
        w = r["course_window"]
        window = (f"{w['start_at'][:10]} → {w['end_at'][:10]}"
                  if w.get("start_at") and w.get("end_at") else "NOT SET")
        af = r["summary"]["auto_fixable"]
        mr = r["summary"]["manual_review"]
        status = "✅ Clean" if r["summary"]["total_issues"] == 0 else ("⚠️ Issues" if af == 0 else "🔴 Action needed")
        lines.append(f"| {label} | {window} | {af} | {mr} | {status} |")
    lines.append("")

    for r in reports:
        cid = r["course_id"]
        label = labels.get(cid, f"Course {cid}")
        w = r["course_window"]
        af = r["auto_fixable"]
        mr = r["manual_review"]

        lines += [f"---", f"## {label}", ""]
        window = (f"{w['start_at'][:10]} → {w['end_at'][:10]}"
                  if w.get("start_at") and w.get("end_at") else "NOT SET")
        lines += [f"**Course window:** {window}", ""]

        if not af and not mr:
            lines += ["All checks passed — no issues found.", ""]
            continue

        if af:
            lines += [
                f"### 🔴 Auto-Fixable ({len(af)})",
                "_These can be resolved by running `course_quality_check.py --fix` or via agent._",
                "",
            ]
            by_type = defaultdict(list)
            for item in af:
                by_type[item["type"]].append(item)

            type_labels = {
                "duplicate_assignment_group": "Duplicate Assignment Groups",
                "duplicate_assignment":       "Duplicate Assignments",
                "duplicate_quiz":             "Duplicate Quizzes",
                "duplicate_module_item":      "Duplicate Module Items",
                "date_out_of_window":         "Dates Outside Course Window",
                "orphaned_duplicate":         "Orphaned Duplicates (same title in module under different ID)",
            }
            for t, items in by_type.items():
                lines.append(f"**{type_labels.get(t, t)}**")
                for it in items:
                    fix = it.get("action", "")
                    lines.append(f"- {it['note']}")
                    if fix:
                        lines.append(f"  - Fix: `{fix}`")
                lines.append("")

        if mr:
            lines += [
                f"### ⚠️ Manual Review ({len(mr)})",
                "_These require human judgment or Canvas UI action._",
                "",
            ]
            by_type = defaultdict(list)
            for item in mr:
                by_type[item["type"]].append(item)

            type_labels = {
                "missing_course_dates":    "Missing Course Dates",
                "empty_quiz":              "Empty Quizzes (no questions)",
                "empty_module":            "Empty Modules (no items — possible sync artifact)",
                "date_out_of_window":      "Dates Outside Window (Unpublished Items)",
                "published_not_in_module": "Published Content Not Linked in Any Module",
                "duplicate_assignment":    "Duplicate Assignments (Blueprint-lock conflict — manual resolution required)",
                "duplicate_quiz":          "Duplicate Quizzes (Blueprint-lock conflict — manual resolution required)",
                "orphan_slug_duplicate":   "Orphan-Slug Page Duplicates (#41 — needs blueprint_orphan_pages.py content-aware cleanup)",
                "stale_link_metadata":     "Stale data-api-endpoint / data-api-returntype Metadata (#42 — href no longer matches enrichment target)",
            }
            for t, items in by_type.items():
                lines.append(f"**{type_labels.get(t, t)}**")
                for it in items:
                    lines.append(f"- {it['note']}")
                    action = it.get("action", "")
                    if action:
                        lines.append(f"  - Action: {action}")
                lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _audit_link_metadata(course_id: str, label: str = "") -> dict:
    """Opt-in audit (#42). Read-only. Walks all description-bearing content
    in the course — Pages, Assignments, Quizzes, Discussion Topics — and
    flags `<a>` tags whose `data-api-endpoint` no longer points at the
    link's current `href` target.

    Canvas auto-injects `data-api-endpoint` / `data-api-returntype` on
    Canvas-internal links inside descriptions. When the `href` is later
    swapped (to a different Canvas resource or an external URL), Canvas does
    NOT update or strip those attributes. The link clicks correctly, but
    hovercards, preview-fetchers, and audit tools reading `data-api-endpoint`
    misreport where the link points.

    Each finding identifies one anchor tag and lists the actual `href` vs.
    the stale `data-api-endpoint`. Does not modify anything — surfacing
    findings is the contract. Pair with the shared writer-side normalizer
    (see `_link_metadata.strip_stale_link_metadata`) to prevent recurrence.
    """
    from _link_metadata import find_stale_link_metadata

    base = CANVAS_BASE_URL
    findings = []

    pages_list = _get_all(f"{base}/api/v1/courses/{course_id}/pages")
    for p in pages_list:
        slug = p.get("url") or p.get("page_url")
        if not slug:
            continue
        try:
            r = requests.get(
                f"{base}/api/v1/courses/{course_id}/pages/{slug}",
                headers=_h(), timeout=20,
            )
            if r.status_code >= 400:
                continue
            body = (r.json() or {}).get("body") or ""
        except Exception:
            continue
        for f in find_stale_link_metadata(body):
            findings.append({
                "container_type": "Page",
                "container_id": slug,
                "container_title": p.get("title", ""),
                "href": f["href"],
                "data_api_endpoint": f["data_api_endpoint"],
                "data_api_returntype": f["data_api_returntype"],
            })

    for endpoint, ctype, body_field in (
        ("assignments", "Assignment", "description"),
        ("quizzes", "Quiz", "description"),
        ("discussion_topics", "Discussion", "message"),
    ):
        items = _get_all(f"{base}/api/v1/courses/{course_id}/{endpoint}")
        for it in items:
            body = it.get(body_field) or ""
            for f in find_stale_link_metadata(body):
                findings.append({
                    "container_type": ctype,
                    "container_id": it.get("id"),
                    "container_title": it.get("name") or it.get("title") or "",
                    "href": f["href"],
                    "data_api_endpoint": f["data_api_endpoint"],
                    "data_api_returntype": f["data_api_returntype"],
                })

    return {
        "course_id": course_id,
        "label": label,
        "findings_count": len(findings),
        "findings": findings,
    }


def _print_link_metadata_report(report: dict, label: str = "") -> None:
    """Print a concise console summary of stale-link-metadata findings."""
    print(f"\n  Stale link-metadata audit — {label or report.get('course_id')}")
    print(f"  ─────────────────────────────────────────────────")
    n = report["findings_count"]
    if n == 0:
        print("  ✓ No stale data-api-endpoint / data-api-returntype attributes found.")
        return
    print(f"  ⚠ {n} stale anchor{'s' if n != 1 else ''} found:")
    by_container = defaultdict(list)
    for f in report["findings"]:
        by_container[(f["container_type"], f["container_title"], f["container_id"])].append(f)
    for (ctype, title, cid), fs in list(by_container.items())[:20]:
        print(f"  • {ctype} '{title}' ({cid}) — {len(fs)} stale anchor(s)")
        for f in fs[:3]:
            print(f"      href → {f['href'][:70]}")
            print(f"      stale data-api-endpoint → {f['data_api_endpoint'][:70]}")


def _write_link_metadata_md_report(reports: list, labels_by_id: dict, path: Path) -> None:
    """Markdown report writer mirroring _write_files_md_report shape."""
    lines = [
        "# Canvas — Stale Link Metadata Audit",
        "",
        "_Read-only audit. Lists `<a>` tags whose `data-api-endpoint` no longer matches their `href` target (issue #42)._",
        "",
    ]
    for r in reports:
        label = labels_by_id.get(r["course_id"], r["course_id"])
        lines.append(f"## {label} ({r['course_id']}) — {r['findings_count']} stale anchor(s)")
        lines.append("")
        if not r["findings"]:
            lines.append("_No stale anchors found._")
            lines.append("")
            continue
        by_container = defaultdict(list)
        for f in r["findings"]:
            by_container[(f["container_type"], f["container_title"], f["container_id"])].append(f)
        for (ctype, title, cid), fs in by_container.items():
            lines.append(f"### {ctype} — {title} ({cid})")
            for f in fs:
                lines.append(f"- `href` → {f['href']}")
                lines.append(f"  - stale `data-api-endpoint` → {f['data_api_endpoint']}")
                if f["data_api_returntype"]:
                    lines.append(f"  - stale `data-api-returntype` → {f['data_api_returntype']}")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _audit_dates(course_id: str, label: str = "") -> dict:
    """Date-specific audit (issue #20, read-only). Four checks:
    1. Out-of-window: due_at/lock_at/unlock_at outside course start_at..end_at
    2. Timestamp ordering: lock_at before due_at, or unlock_at after due_at
    3. Duplicate due dates within the same assignment group (same UTC calendar day)
    4. Label-vs-week drift: 'Week N' or 'SN' items due outside expected course week/sprint
    All timestamps compared in UTC — findings within 24h of a boundary may be timezone artifacts.
    """
    base = CANVAS_BASE_URL
    findings = []

    start_at, end_at = _get_course_window(course_id)
    if not start_at or not end_at:
        return {
            "course_id": course_id,
            "label": label,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "course_window": {"start_at": None, "end_at": None},
            "findings": [],
            "error": "No course start_at/end_at — date checks skipped. Set course dates in Canvas Settings.",
            "summary": {"total": 0},
        }

    assignments  = _get_all(f"{base}/api/v1/courses/{course_id}/assignments")
    quizzes      = _get_all(f"{base}/api/v1/courses/{course_id}/quizzes")
    discussions  = _get_all(f"{base}/api/v1/courses/{course_id}/discussion_topics")
    groups       = _get_all(f"{base}/api/v1/courses/{course_id}/assignment_groups")
    group_names  = {g["id"]: g["name"] for g in groups}

    window_str = f"{start_at.date()} → {end_at.date()}"

    # ── 1. Out-of-window ──────────────────────────────────────
    def _check_window(item_type, name, canvas_id, fields: dict):
        for field, value in fields.items():
            dt = _parse_dt(value)
            if dt and not (start_at <= dt <= end_at):
                findings.append({
                    "check": "out_of_window",
                    "item_type": item_type,
                    "title": name,
                    "canvas_id": canvas_id,
                    "field": field,
                    "value": value[:10],
                    "note": f"{item_type.title()} '{name}' {field}={value[:10]} is outside course window {window_str}",
                    "fix": f"Update {field} to a date within {window_str}",
                })

    for a in assignments:
        _check_window("assignment", a["name"], a["id"],
                      {f: a.get(f) for f in ("due_at", "lock_at", "unlock_at") if a.get(f)})
    for q in quizzes:
        _check_window("quiz", q["title"], q["id"],
                      {f: q.get(f) for f in ("due_at", "lock_at", "unlock_at") if q.get(f)})
    for d in discussions:
        if d.get("todo_date"):
            _check_window("discussion", d["title"], d["id"], {"todo_date": d["todo_date"]})

    # ── 2. Timestamp ordering sanity ──────────────────────────
    def _check_ordering(item_type, name, canvas_id, due_val, lock_val, unlock_val):
        due    = _parse_dt(due_val)
        lock   = _parse_dt(lock_val)
        unlock = _parse_dt(unlock_val)
        if due and lock and lock < due:
            findings.append({
                "check": "lock_before_due",
                "item_type": item_type,
                "title": name,
                "canvas_id": canvas_id,
                "due_at": due_val[:10],
                "lock_at": lock_val[:10],
                "note": f"{item_type.title()} '{name}': lock_at ({lock_val[:10]}) is before due_at ({due_val[:10]}) — students lose access before the deadline",
                "fix": "Set lock_at on or after due_at",
            })
        if due and unlock and unlock > due:
            findings.append({
                "check": "unlock_after_due",
                "item_type": item_type,
                "title": name,
                "canvas_id": canvas_id,
                "due_at": due_val[:10],
                "unlock_at": unlock_val[:10],
                "note": f"{item_type.title()} '{name}': unlock_at ({unlock_val[:10]}) is after due_at ({due_val[:10]}) — item unlocks after it's already due",
                "fix": "Set unlock_at on or before due_at",
            })

    for a in assignments:
        _check_ordering("assignment", a["name"], a["id"],
                        a.get("due_at"), a.get("lock_at"), a.get("unlock_at"))
    for q in quizzes:
        _check_ordering("quiz", q["title"], q["id"],
                        q.get("due_at"), q.get("lock_at"), q.get("unlock_at"))

    # ── 3. Duplicate due dates within an assignment group ─────
    by_group_day: dict = defaultdict(list)
    for a in assignments:
        gid = a.get("assignment_group_id")
        due = _parse_dt(a.get("due_at"))
        if gid and due:
            by_group_day[(gid, due.date())].append(a)

    for (gid, day), items in by_group_day.items():
        if len(items) > 1:
            group_name = group_names.get(gid, f"group {gid}")
            titles = [i["name"] for i in items]
            findings.append({
                "check": "duplicate_due_date_in_group",
                "assignment_group": group_name,
                "due_date": str(day),
                "titles": titles,
                "canvas_ids": [i["id"] for i in items],
                "note": f"Group '{group_name}': {len(items)} items share due date {day} — {', '.join(repr(t) for t in titles)}",
                "fix": "Spread items across different due dates, or confirm this is intentional",
            })

    # ── 4. Label-vs-week/sprint drift ────────────────────────
    all_dated = (
        [("assignment", a["name"], a["id"], a.get("due_at")) for a in assignments] +
        [("quiz",       q["title"], q["id"], q.get("due_at")) for q in quizzes] +
        [("discussion", d["title"], d["id"], d.get("todo_date")) for d in discussions]
    )
    for item_type, name, canvas_id, date_val in all_dated:
        dt = _parse_dt(date_val)
        if not dt or not date_val:
            continue
        wm = _WEEK_RE.search(name)
        if wm:
            labeled = int(wm.group(1))
            actual  = _week_of_course(dt, start_at)
            if actual is not None and actual != labeled:
                exp_start = (start_at + timedelta(weeks=labeled - 1)).date()
                exp_end   = (start_at + timedelta(weeks=labeled)).date()
                findings.append({
                    "check": "label_week_drift",
                    "item_type": item_type,
                    "title": name,
                    "canvas_id": canvas_id,
                    "labeled_week": labeled,
                    "actual_week": actual,
                    "due_date": date_val[:10],
                    "note": f"{item_type.title()} '{name}': label says Week {labeled} but due {date_val[:10]} falls in Week {actual} of the course",
                    "fix": f"Rename to 'Week {actual}' OR move due date into Week {labeled} window ({exp_start} → {exp_end})",
                })
            continue  # don't also check sprint pattern on the same item
        sm = _SPRINT_RE.search(name)
        if sm:
            labeled = int(sm.group(1))
            actual  = _sprint_of_course(dt, start_at)
            if actual is not None and actual != labeled:
                exp_start = (start_at + timedelta(weeks=(labeled - 1) * 2)).date()
                exp_end   = (start_at + timedelta(weeks=labeled * 2)).date()
                findings.append({
                    "check": "label_sprint_drift",
                    "item_type": item_type,
                    "title": name,
                    "canvas_id": canvas_id,
                    "labeled_sprint": labeled,
                    "actual_sprint": actual,
                    "due_date": date_val[:10],
                    "note": f"{item_type.title()} '{name}': label says Sprint {labeled} but due {date_val[:10]} falls in Sprint {actual} (2-week sprints assumed)",
                    "fix": f"Rename to 'S{actual}' OR move due date into Sprint {labeled} window ({exp_start} → {exp_end})",
                })

    return {
        "course_id": course_id,
        "label": label,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "course_window": {
            "start_at": start_at.isoformat(),
            "end_at":   end_at.isoformat(),
        },
        "findings": findings,
        "summary": {"total": len(findings)},
    }


def _print_dates_report(report: dict, label: str):
    w = report["course_window"]
    findings = report.get("findings", [])
    total = report["summary"]["total"]

    print(f"\n{'='*62}\n  Date Validation — {label}\n{'='*62}")
    if report.get("error"):
        print(f"  {report['error']}")
        return

    print(f"  Course window: {w['start_at'][:10] if w['start_at'] else 'n/a'} → {w['end_at'][:10] if w['end_at'] else 'n/a'}")
    print(f"  Findings: {total}")

    by_check: dict = defaultdict(list)
    for f in findings:
        by_check[f["check"]].append(f)

    check_labels = {
        "out_of_window":              "Out-of-window dates",
        "lock_before_due":            "Lock before due",
        "unlock_after_due":           "Unlock after due",
        "duplicate_due_date_in_group":"Duplicate due dates in group",
        "label_week_drift":           "Label-vs-week drift",
        "label_sprint_drift":         "Label-vs-sprint drift",
    }
    for check, items in by_check.items():
        print(f"\n  {check_labels.get(check, check)} ({len(items)})")
        for f in items:
            print(f"    • {f['note']}")
            print(f"      Fix: {f['fix']}")

    if total == 0:
        print("  All date checks passed.")


def _write_dates_md_report(reports: list[dict], labels: dict, path: Path):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    check_labels = {
        "out_of_window":               "Out-of-window dates",
        "lock_before_due":             "Lock before due",
        "unlock_after_due":            "Unlock after due",
        "duplicate_due_date_in_group": "Duplicate due dates in assignment group",
        "label_week_drift":            "Label-vs-week drift",
        "label_sprint_drift":          "Label-vs-sprint drift",
    }
    lines = [
        "# Canvas Date Validation Report",
        f"Generated: {now}",
        "",
        "Read-only. All timestamps compared in UTC — findings within 24 h of a boundary may be timezone artifacts.",
        "Sprint drift assumes 2-week sprints.",
        "",
    ]
    for r in reports:
        label = r.get("label") or r["course_id"]
        w = r["course_window"]
        findings = r.get("findings", [])
        total = r["summary"]["total"]
        lines += [
            f"## {label}",
            "",
            f"- **Course window**: {w['start_at'][:10] if w['start_at'] else 'n/a'} → {w['end_at'][:10] if w['end_at'] else 'n/a'}",
            f"- **Total findings**: {total}",
            "",
        ]
        if r.get("error"):
            lines += [f"> {r['error']}", ""]
            continue
        if not findings:
            lines += ["All date checks passed.", ""]
            continue
        by_check: dict = defaultdict(list)
        for f in findings:
            by_check[f["check"]].append(f)
        for check, items in by_check.items():
            lines += [f"### {check_labels.get(check, check)} ({len(items)})", ""]
            for f in items:
                lines.append(f"- {f['note']}")
                lines.append(f"  - Fix: {f['fix']}")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _apply_fixes(course_id: str, report: dict, dry_run: bool = False):
    """Delete duplicate items and report date issues (date fixes need human confirmation)."""
    base = CANVAS_BASE_URL
    af = report["auto_fixable"]

    deletable_types = {"duplicate_assignment_group", "duplicate_assignment",
                       "duplicate_quiz", "duplicate_module_item"}
    date_types = {"date_out_of_window"}

    fixed, skipped = 0, 0
    for item in af:
        if item["type"] in deletable_types:
            action = item["action"]  # "DELETE /api/v1/..."
            path = action.split(" ", 1)[1]
            url = f"{base}{path}"
            if dry_run:
                print(f"  [dry-run] DELETE {path}")
            else:
                r = requests.delete(url, headers=_h(), timeout=20)
                ok = r.status_code in (200, 204)
                print(f"  {'OK' if ok else 'FAILED'} DELETE — {item['note']}")
                if ok:
                    fixed += 1
                else:
                    skipped += 1
        elif item["type"] in date_types:
            print(f"  SKIP (date fix needs human decision): {item['note']}")
            skipped += 1

    print(f"\n  Fixed: {fixed}  |  Skipped: {skipped}")


def main():
    parser = argparse.ArgumentParser(
        description="Canvas course quality check: duplicates, date windows, empty quizzes"
    )
    parser.add_argument("--master",    action="store_true", help="Check MASTER_COURSE_ID")
    parser.add_argument("--blueprint", action="store_true", help="Check BLUEPRINT_COURSE_ID")
    parser.add_argument("--all",       action="store_true", help="Check all three courses")
    parser.add_argument("--course",    metavar="ID",        help="Check a specific course ID")
    parser.add_argument("--fix",       action="store_true", help="Auto-fix duplicate issues (deletes extras)")
    parser.add_argument("--dry-run",   action="store_true", help="Show what --fix would do without changing Canvas")
    parser.add_argument("--files",     action="store_true",
                        help="Files audit: orphans, broken references, duplicates "
                             "(read-only; consumes index['linked_files'] from canvas_sync) — issue #17")
    parser.add_argument("--alignment", action="store_true",
                        help="Alignment-chain audit: Course Outcome → Module Outcome → "
                             "Rubric Criterion → Activity. Heuristic text-based matching, "
                             "read-only — issue #18")
    parser.add_argument("--validate-dates", action="store_true",
                        help="Date validation: out-of-window, timestamp ordering, "
                             "duplicate due dates per group, label-vs-week/sprint drift. "
                             "Read-only — issue #20")
    parser.add_argument("--link-metadata", action="store_true",
                        help="Stale link-metadata audit: <a> tags whose "
                             "data-api-endpoint no longer points at the link's "
                             "current href target. Opt-in, read-only — issue #42")
    args = parser.parse_args()

    if not CANVAS_API_TOKEN or not CANVAS_BASE_URL:
        print("ERROR: CANVAS_API_TOKEN and CANVAS_BASE_URL required in .env")
        sys.exit(1)

    targets = []
    if args.course:
        targets.append((args.course, f"Course {args.course}"))
    elif args.all:
        targets = [
            (SOURCE_ID,    f"Source (CANVAS_COURSE_ID={SOURCE_ID})"),
            (MASTER_ID,    f"Master (MASTER_COURSE_ID={MASTER_ID})"),
            (BLUEPRINT_ID, f"Blueprint (BLUEPRINT_COURSE_ID={BLUEPRINT_ID})"),
        ]
    elif args.master:
        targets.append((MASTER_ID, f"Master (MASTER_COURSE_ID={MASTER_ID})"))
    elif args.blueprint:
        targets.append((BLUEPRINT_ID, f"Blueprint (BLUEPRINT_COURSE_ID={BLUEPRINT_ID})"))
    else:
        targets.append((SOURCE_ID, f"Source (CANVAS_COURSE_ID={SOURCE_ID})"))

    targets = [(cid, label) for cid, label in targets if cid]
    if not targets:
        print("ERROR: No course IDs configured.")
        sys.exit(1)

    # Startup safety guard (#27): advisory only — course_quality_check is
    # read-only, so the guard warns but never blocks.
    for cid, label in targets:
        _course_guard(CANVAS_BASE_URL, _h(), cid, "read",
                      allow_override=False, label=label)

    REPORT_DIR.mkdir(exist_ok=True)

    # Date validation (issue #20) — separate, read-only audit.
    if args.validate_dates:
        date_reports = []
        labels_by_id: dict = {}
        for course_id, label in targets:
            print(f"  Validating dates for {label}...")
            r = _audit_dates(course_id, label=label)
            _print_dates_report(r, label)
            date_reports.append(r)
            labels_by_id[course_id] = label
            audit_path = REPORT_DIR / f"date_audit_{course_id}.json"
            audit_path.write_text(json.dumps(r, indent=2, default=str))

        md_path = Path("quality_report.md")
        _write_dates_md_report(date_reports, labels_by_id, md_path)
        total = sum(r["summary"]["total"] for r in date_reports)
        print(f"\n  Date validation → {md_path} + .canvas/date_audit_*.json")
        sys.exit(1 if total > 0 else 0)

    # Alignment audit (issue #18) — separate, read-only audit. Doesn't run alongside
    # the default audit; --alignment switches modes entirely.
    if args.alignment:
        align_reports = []
        labels_by_id: dict = {}
        for course_id, label in targets:
            print(f"  Auditing alignment for {label}...")
            r = _audit_alignment(course_id, label=label)
            _print_alignment_report(r, label)
            align_reports.append(r)
            labels_by_id[course_id] = label
            audit_path = REPORT_DIR / f"alignment_audit_{course_id}.json"
            audit_path.write_text(json.dumps(r, indent=2, default=str))

        md_path = Path("quality_report.md")
        _write_alignment_md_report(align_reports, labels_by_id, md_path)
        print(f"\n  Alignment audit → {md_path} + .canvas/alignment_audit_*.json")
        sys.exit(0)

    # Link-metadata audit (issue #42) — opt-in, read-only. Switches modes
    # entirely. Does NOT run alongside the default audit; pair with the
    # writer-side normalizer (when shipped) to prevent recurrence.
    if args.link_metadata:
        lm_reports = []
        labels_by_id: dict = {}
        for course_id, label in targets:
            print(f"  Auditing link metadata for {label}...")
            r = _audit_link_metadata(course_id, label=label)
            _print_link_metadata_report(r, label)
            lm_reports.append(r)
            labels_by_id[course_id] = label
            audit_path = REPORT_DIR / f"link_metadata_audit_{course_id}.json"
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_path.write_text(json.dumps(r, indent=2, default=str))
        md_path = Path("link_metadata_report.md")
        _write_link_metadata_md_report(lm_reports, labels_by_id, md_path)
        print(f"\n  Link-metadata audit → {md_path} + .canvas/link_metadata_audit_*.json")
        sys.exit(0)

    # Files audit (issue #17) — separate, read-only audit. Doesn't run alongside the
    # default duplicate-and-window audit; --files switches modes entirely.
    if args.files:
        files_reports = []
        labels_by_id: dict = {}
        for course_id, label in targets:
            print(f"  Auditing files for {label}...")
            r = _audit_files(course_id, label=label)
            _print_files_report(r, label)
            files_reports.append(r)
            labels_by_id[course_id] = label
            audit_path = REPORT_DIR / f"file_audit_{course_id}.json"
            audit_path.write_text(json.dumps(r, indent=2, default=str))

        md_path = Path("quality_report.md")
        _write_files_md_report(files_reports, labels_by_id, md_path)
        print(f"\n  Files audit → {md_path} + .canvas/file_audit_*.json")
        sys.exit(0)

    all_clean = True
    all_reports = []
    label_map = {}

    for course_id, label in targets:
        print(f"  Checking {label}...")
        report = _audit_course(course_id)
        _print_report(report, label)
        all_reports.append(report)
        label_map[course_id] = label

        # Write JSON report (machine-readable, gitignored)
        report_path = REPORT_DIR / f"quality_report_{course_id}.json"
        report_path.write_text(json.dumps(report, indent=2))

        if args.fix or args.dry_run:
            print(f"\n  {'[DRY RUN] ' if args.dry_run else ''}Applying auto-fixes...")
            _apply_fixes(course_id, report, dry_run=args.dry_run)

        if report["summary"]["total_issues"] > 0:
            all_clean = False

    # Write combined markdown report at repo root
    md_path = Path("quality_report.md")
    _write_md_report(all_reports, label_map, md_path)

    print(f"\n{'='*62}")
    if all_clean:
        print("  All courses clean.")
    else:
        print("  Issues found — review quality_report.md")
        if not args.fix and not args.dry_run:
            print("  Run with --fix to auto-resolve duplicates.")
    print(f"  Report → quality_report.md")
    print(f"{'='*62}\n")

    sys.exit(0 if all_clean else 1)


if __name__ == "__main__":
    main()

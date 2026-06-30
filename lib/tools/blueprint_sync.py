"""
blueprint_sync.py

One-way sync: master course (MASTER_COURSE_ID) → Blueprint course (BLUEPRINT_COURSE_ID).
Master course/ is always the source of truth. Blueprint is overwritten — never read for content.
No analysis, no LLM, no context loading. Pure mechanical rclone-style copy + push.

Setup:
    Add BLUEPRINT_COURSE_ID to .env

Commands:
    uv run python tools/blueprint_sync.py --pull        # Full init of blueprint_course/ + build ID mapping
    uv run python tools/blueprint_sync.py --push        # Sync master → blueprint (content + dates)
    uv run python tools/blueprint_sync.py --status      # Show mapping coverage + last sync

Folder layout:
    blueprint_course/       Mirror of blueprint structure (like course/ for master). Never edit.
    .canvas/blueprint_index.json    master_filepath → blueprint canvas_id + date mapping
    .canvas/blueprint_log.md        Append-only audit trail (gitignored)

What --pull does:
    Full init mirroring canvas_sync.py --init:
    - Fetches all modules + items from Blueprint
    - Pulls full content for each item (assignments with dates, pages, quizzes, discussions)
    - Writes to blueprint_course/<module-slug>/<filename>
    - Title-matches blueprint items to master items to build ID mapping
    - Stores blueprint canvas IDs + dates in blueprint_index.json

What --push syncs:
    - Course settings: grading_standard_id, show_announcements_on_home_page
    - Homepage (front_page)
    - Syllabus body
    - Pages, Assignments, Discussions, classic Quizzes:
        content (description/body) + published state + dates (due_at, lock_at, unlock_at)
    - Unmapped master Pages: created new in Blueprint + added to correct module

What is NOT synced (Canvas API limitation or by design):
    - NewQuiz content (LTI-based, no standard API)
    - late_policy (requires Canvas admin token — instructor token returns 403)
    - Module structure / item order
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from canvas_pages import page_in_module, upsert_page
from __toolbox_version__ import __version__
from canvas_course_guard import enforce as _course_guard

# Load .env via the shared helper (issue #43)
try:
    from _env_loader import load_env, force_utf8_console
    load_env()
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url

MASTER_COURSE_ID = os.environ.get("MASTER_COURSE_ID", "")
BLUEPRINT_COURSE_ID = os.environ.get("BLUEPRINT_COURSE_ID", "")

MASTER_DIR = Path("course")
BLUEPRINT_DIR = Path("blueprint_course")
MASTER_INDEX = Path(".canvas/index.json")
BLUEPRINT_INDEX = Path(".canvas/blueprint_index.json")
BLUEPRINT_LOG = Path(".canvas/blueprint_log.md")

# Types that cannot be pushed via the standard REST API
NO_PUSH_TYPES = {"NewQuiz", "ExternalTool", "ExternalUrl", "ContextModuleSubHeader", "SubHeader"}

# Types with no editable body — store as metadata-only JSON (same as canvas_sync.py)
METADATA_ONLY_TYPES = {"ExternalTool", "ExternalUrl", "ContextModuleSubHeader"}


# ---------------------------------------------------------------------------
# Env check
# ---------------------------------------------------------------------------

def _check_env():
    missing = []
    if not CANVAS_BASE_URL or CANVAS_BASE_URL == "https://":
        missing.append("CANVAS_BASE_URL")
    if not CANVAS_API_TOKEN:
        missing.append("CANVAS_API_TOKEN")
    if not MASTER_COURSE_ID:
        missing.append("MASTER_COURSE_ID")
    if not BLUEPRINT_COURSE_ID:
        missing.append("BLUEPRINT_COURSE_ID")
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        print("Add them to .env and re-run.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}", "Content-Type": "application/json"}


def _get(endpoint: str, params: dict = None):
    """GET with pagination."""
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    results = []
    while url:
        resp = requests.get(url, headers=_headers(), params=params, timeout=20)
        if resp.status_code >= 400:
            return None
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url = None
        link = resp.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        params = None
    return results


def _put(endpoint: str, payload: dict) -> dict:
    resp = requests.put(f"{CANVAS_BASE_URL}/api/v1{endpoint}",
                        headers=_headers(), json=payload, timeout=20)
    if resp.status_code >= 400:
        return {"error": resp.text[:300]}
    try:
        return resp.json() or {"ok": True}
    except Exception:
        return {"ok": True}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _slug(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:80]


def _confirm_module_match(master_title: str, candidates: list, context: str = "") -> Optional[dict]:
    """
    Exact-match-first module resolver with user confirmation for ambiguous cases.

    - Exactly one exact slug match → return silently.
    - Multiple exact matches (duplicate module names) → show options, require user to pick.
    - No exact match → SKIP, never auto-apply fuzzy match.
    """
    master_slug = _slug(master_title)
    exact = [m for m in candidates if _slug(m.get("name", "")) == master_slug]

    if len(exact) == 1:
        return exact[0]

    if len(exact) > 1:
        print(f"\n  WARNING: {len(exact)} modules share the same slug for '{master_title}':")
        for i, m in enumerate(exact):
            print(f"    [{i}] id={m['id']}  name={repr(m['name'])}")
        if context:
            print(f"  {context}")
        try:
            choice = input(f"  Enter index to use (or ENTER to skip): ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = ""
        if choice.isdigit() and int(choice) < len(exact):
            return exact[int(choice)]
        print(f"  SKIPPED: '{master_title}' (ambiguous, no selection made)")
        return None

    # No exact match — never silently fuzzy-match
    print(f"  SKIP module '{master_title}': no exact match in blueprint (slug='{master_slug}')")
    return None


def _log(message: str, files: list):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    BLUEPRINT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with BLUEPRINT_LOG.open("a", encoding="utf-8") as f:
        f.write(f"\n## {message}\n_{ts}_\n\n")
        for item in files:
            f.write(f"- {item}\n")
        f.write("\n")


# ---------------------------------------------------------------------------
# Pull: full init of blueprint_course/ + build master → blueprint mapping
# ---------------------------------------------------------------------------

def _pull_assignment(course_id: str, assignment_id: int) -> Optional[dict]:
    data = _get(f"/courses/{course_id}/assignments/{assignment_id}")
    if not data or isinstance(data, list):
        return None
    return {
        "canvas_id": data.get("id"),
        "name": data.get("name"),
        "description": data.get("description", ""),
        "points_possible": data.get("points_possible"),
        "due_at": data.get("due_at"),
        "lock_at": data.get("lock_at"),
        "unlock_at": data.get("unlock_at"),
        "submission_types": data.get("submission_types", []),
        "published": data.get("published", False),
    }


def _pull_discussion(course_id: str, topic_id: int) -> Optional[dict]:
    data = _get(f"/courses/{course_id}/discussion_topics/{topic_id}")
    if not data or isinstance(data, list):
        return None
    assignment = data.get("assignment") or {}
    return {
        "canvas_id": data.get("id"),
        "title": data.get("title"),
        "message": data.get("message", ""),
        "due_at": assignment.get("due_at"),
        "lock_at": assignment.get("lock_at"),
        "unlock_at": assignment.get("unlock_at"),
        "published": data.get("published", False),
    }


def _pull_quiz(course_id: str, quiz_id: int) -> Optional[dict]:
    data = _get(f"/courses/{course_id}/quizzes/{quiz_id}")
    if not data or isinstance(data, list):
        return None
    return {
        "canvas_id": data.get("id"),
        "title": data.get("title"),
        "description": data.get("description", ""),
        "points_possible": data.get("points_possible"),
        "quiz_type": data.get("quiz_type"),
        "due_at": data.get("due_at"),
        "lock_at": data.get("lock_at"),
        "unlock_at": data.get("unlock_at"),
        "published": data.get("published", False),
    }


def _pull_page(course_id: str, page_url: str) -> Optional[str]:
    data = _get(f"/courses/{course_id}/pages/{page_url}")
    if not data or isinstance(data, list):
        return None
    return data.get("body", "")


def cmd_pull():
    """Full init of blueprint_course/ + build master→blueprint ID mapping."""
    _check_env()
    bp_id = BLUEPRINT_COURSE_ID

    master_index = _load_json(MASTER_INDEX)
    if not master_index.get("files"):
        print("ERROR: Master index empty. Run 'canvas_sync.py --pull' first.")
        sys.exit(1)

    print(f"Pulling blueprint course {bp_id} from {CANVAS_BASE_URL}...\n")

    BLUEPRINT_DIR.mkdir(exist_ok=True)

    # Build title → (master_filepath, master_meta) lookup for matching
    master_by_title = {}
    for fp, meta in master_index.get("files", {}).items():
        title = (meta.get("title") or "").strip().lower()
        if title:
            master_by_title[title] = (fp, meta)

    blueprint_index = {
        "blueprint_course_id": bp_id,
        "master_course_id": MASTER_COURSE_ID,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "homepage": None,
        "mappings": {},
        "unmapped_master": [],
        "unmapped_blueprint": [],
    }

    # -----------------------------------------------------------------------
    # Homepage
    # -----------------------------------------------------------------------
    homepage = _get(f"/courses/{bp_id}/front_page")
    if homepage and not homepage.get("errors"):
        blueprint_index["homepage"] = {
            "page_url": homepage.get("url", "front-page"),
            "title": homepage.get("title", ""),
        }
        print(f"  [homepage] {homepage.get('url', 'front-page')}")

    # -----------------------------------------------------------------------
    # Modules + items — full init into blueprint_course/
    # -----------------------------------------------------------------------
    modules = _get(f"/courses/{bp_id}/modules", params={"per_page": 50, "include[]": "items"})
    if not modules:
        print("ERROR: Could not fetch blueprint modules. Check BLUEPRINT_COURSE_ID and token.")
        sys.exit(1)

    print(f"  {len(modules)} modules")
    total_items = sum(len(m.get("items", [])) for m in modules)
    print(f"  {total_items} module items\n")

    # Warn if blueprint has duplicate module names — push will skip ambiguous ones
    from collections import Counter
    mod_name_counts = Counter(_slug(m.get("name", "")) for m in modules)
    dup_mods = [slug for slug, count in mod_name_counts.items() if count > 1]
    if dup_mods:
        print(f"  WARNING: Blueprint has {len(dup_mods)} duplicate module name(s):")
        for slug in dup_mods:
            print(f"    '{slug}' appears {mod_name_counts[slug]}x")
        print(f"  Clean up duplicate modules in Canvas before running --push.\n")

    matched = 0
    for mod in modules:
        mod_name = mod.get("name", "")
        mod_slug = _slug(mod_name)
        mod_dir = BLUEPRINT_DIR / mod_slug
        mod_dir.mkdir(exist_ok=True)

        mod_meta = {
            "canvas_id": mod.get("id"),
            "title": mod_name,
            "position": mod.get("position"),
            "published": mod.get("workflow_state") != "unpublished",
            "items": [],
        }

        for item in mod.get("items", []):
            item_type = item.get("type")
            item_title = item.get("title", "")
            content_id = item.get("content_id")
            page_url = item.get("page_url")
            item_id = item.get("id")

            # Generate filename (same logic as canvas_sync.py)
            title_slug = _slug(item_title)
            if item_type == "Page":
                filename = f"{title_slug}.html"
            else:
                filename = f"{title_slug}.json"

            filepath = mod_dir / filename
            item_record = {
                "module_item_id": item_id,
                "content_id": content_id,
                "type": item_type,
                "title": item_title,
                "position": item.get("position"),
                "published": item.get("published", False),
                "filename": filename,
            }
            if page_url:
                item_record["page_url"] = page_url

            # Fetch full content and write to blueprint_course/
            content_data = None
            if item_type == "Page" and page_url:
                body = _pull_page(bp_id, page_url)
                if body is not None:
                    filepath.write_text(body, encoding="utf-8")
                    content_data = {"body_hash": _file_hash(filepath)}

            elif item_type == "Assignment" and content_id:
                data = _pull_assignment(bp_id, content_id)
                if data:
                    filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    content_data = data

            elif item_type == "Discussion" and content_id:
                data = _pull_discussion(bp_id, content_id)
                if data:
                    filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    content_data = data

            elif item_type == "Quiz" and content_id:
                data = _pull_quiz(bp_id, content_id)
                if data:
                    filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    content_data = data

            else:
                # Metadata-only (ExternalTool, ExternalUrl, SubHeader, NewQuiz)
                meta_only = {
                    "canvas_id": content_id,
                    "title": item_title,
                    "type": item_type,
                    "module_item_id": item_id,
                }
                filepath.write_text(json.dumps(meta_only, indent=2), encoding="utf-8")

            mod_meta["items"].append(item_record)

            # Title-match to master
            key = item_title.strip().lower()
            master_match = master_by_title.get(key)
            if master_match:
                master_fp, master_meta = master_match
                mapping_entry = {
                    "blueprint_canvas_id": content_id,
                    "blueprint_page_url": page_url,
                    "blueprint_filepath": str(filepath),
                    "blueprint_module_id": mod.get("id"),
                    "type": master_meta.get("type", item_type),
                    "title": item_title,
                    "module": mod_name,
                }
                # Store current blueprint dates for comparison
                if content_data and isinstance(content_data, dict):
                    mapping_entry["blueprint_due_at"] = content_data.get("due_at")
                    mapping_entry["blueprint_lock_at"] = content_data.get("lock_at")
                    mapping_entry["blueprint_unlock_at"] = content_data.get("unlock_at")
                blueprint_index["mappings"][master_fp] = mapping_entry
                matched += 1
            else:
                blueprint_index["unmapped_blueprint"].append(item_title)

        # Write module metadata
        _save_json(mod_dir / "_module.json", mod_meta)

    # Master items with no blueprint counterpart
    for fp in master_index.get("files", {}):
        if fp not in blueprint_index["mappings"]:
            blueprint_index["unmapped_master"].append(fp)

    _save_json(BLUEPRINT_INDEX, blueprint_index)

    print(f"Blueprint pull complete.")
    print(f"  {matched} master items mapped to blueprint canvas IDs")
    if blueprint_index["unmapped_blueprint"]:
        print(f"  {len(blueprint_index['unmapped_blueprint'])} blueprint items not matched to master")
    if blueprint_index["unmapped_master"]:
        unmapped_non_nq = [fp for fp in blueprint_index["unmapped_master"]
                           if master_index["files"].get(fp, {}).get("type") not in NO_PUSH_TYPES
                           and master_index["files"].get(fp, {}).get("type") != "NewQuiz"]
        if unmapped_non_nq:
            unmapped_pages = [fp for fp in unmapped_non_nq
                              if master_index["files"].get(fp, {}).get("type") == "Page"]
            unmapped_manual = [fp for fp in unmapped_non_nq
                               if master_index["files"].get(fp, {}).get("type") in ("Assignment", "Discussion", "Quiz")]
            if unmapped_pages:
                print(f"  {len(unmapped_pages)} new Pages will be created in blueprint on --push:")
                for fp in unmapped_pages[:10]:
                    print(f"    [Page] {fp}")
            if unmapped_manual:
                print(f"  {len(unmapped_manual)} new items must be added manually in Blueprint UI (--push will warn):")
                for fp in unmapped_manual[:10]:
                    t = master_index["files"].get(fp, {}).get("type", "?")
                    print(f"    [{t}] {fp}")
    print(f"\n  Blueprint mirror → {BLUEPRINT_DIR}/")
    print(f"  Mapping saved    → {BLUEPRINT_INDEX}")
    print(f"  Run --status to review coverage, then --push to sync.")


# ---------------------------------------------------------------------------
# Push: overwrite blueprint with master content + dates
# ---------------------------------------------------------------------------

def cmd_push():
    """Sync all master course content (+ dates) to the blueprint course. Full overwrite."""
    _check_env()

    master_index = _load_json(MASTER_INDEX)
    blueprint_index = _load_json(BLUEPRINT_INDEX)

    if not master_index.get("files"):
        print("ERROR: Master index empty. Run 'canvas_sync.py --pull' first.")
        sys.exit(1)
    if not blueprint_index.get("mappings"):
        print("ERROR: Blueprint mapping empty. Run 'blueprint_sync.py --pull' first.")
        sys.exit(1)

    bp_id = BLUEPRINT_COURSE_ID
    mappings = blueprint_index["mappings"]
    pushed_files = []
    pushed = skipped = failed = 0

    print(f"Syncing master → blueprint course {bp_id}...\n")

    # -----------------------------------------------------------------------
    # 1. Course-level settings
    # -----------------------------------------------------------------------
    master_course = _load_json(MASTER_DIR / "_course.json")
    if master_course:
        # Grading standard
        gs_id = master_course.get("grading_standard_id")
        if gs_id:
            print("  [Settings] grading_standard")
            r = _put(f"/courses/{bp_id}", {"course": {"grading_standard_id": gs_id}})
            if r.get("error"):
                print(f"    FAILED: {r['error']}")
                failed += 1
            else:
                print(f"    OK")
                pushed_files.append("settings/grading_standard")

        # Disable announcements on home page
        print("  [Settings] show_announcements_on_home_page → false")
        resp = requests.put(
            f"{CANVAS_BASE_URL}/api/v1/courses/{bp_id}",
            headers=_headers(),
            json={"course": {"show_announcements_on_home_page": False}},
            timeout=20,
        )
        if resp.status_code < 400:
            print(f"    OK")
            pushed_files.append("settings/announcements")
        else:
            print(f"    FAILED: {resp.text[:200]}")
            failed += 1

        # Note: late_policy requires Canvas admin token (instructor token returns 403)
        # Set late_policy manually in Blueprint Settings or ask Canvas admin.

    # -----------------------------------------------------------------------
    # 2. Homepage
    # -----------------------------------------------------------------------
    master_hp = master_index.get("homepage")
    bp_hp = blueprint_index.get("homepage")
    if master_hp and bp_hp:
        hp_path = Path(master_hp["filepath"])
        if hp_path.exists():
            print(f"  [Homepage] {hp_path.name}")
            body = hp_path.read_text(encoding="utf-8")
            page_url = bp_hp.get("page_url", "front-page")
            resp = requests.put(
                f"{CANVAS_BASE_URL}/api/v1/courses/{bp_id}/pages/{page_url}",
                headers=_headers(),
                json={"wiki_page": {"body": body}},
                timeout=20,
            )
            if resp.status_code < 400:
                print(f"    OK")
                pushed += 1
                pushed_files.append("homepage.html")
            else:
                print(f"    FAILED: {resp.text[:200]}")
                failed += 1

    # -----------------------------------------------------------------------
    # 3. Syllabus
    # -----------------------------------------------------------------------
    master_syl = master_index.get("syllabus")
    if master_syl:
        syl_path = Path(master_syl["filepath"])
        if syl_path.exists():
            print(f"  [Syllabus] syllabus.html")
            body = syl_path.read_text(encoding="utf-8")
            resp = requests.put(
                f"{CANVAS_BASE_URL}/api/v1/courses/{bp_id}",
                headers=_headers(),
                json={"course": {"syllabus_body": body}},
                timeout=20,
            )
            if resp.status_code < 400:
                print(f"    OK")
                pushed += 1
                pushed_files.append("syllabus.html")
            else:
                print(f"    FAILED: {resp.text[:200]}")
                failed += 1

    # -----------------------------------------------------------------------
    # 4. Module items
    # -----------------------------------------------------------------------
    # Pull blueprint module IDs (for new page creation)
    bp_modules_resp = _get(f"/courses/{bp_id}/modules", params={"per_page": 50})
    bp_modules_by_slug = {}
    if bp_modules_resp:
        for m in bp_modules_resp:
            slug = _slug(m.get("name", ""))
            bp_modules_by_slug[slug] = m.get("id")

    for master_fp, master_meta in master_index.get("files", {}).items():
        bp_meta = mappings.get(master_fp)
        master_path = Path(master_fp)
        if not master_path.exists():
            skipped += 1
            continue

        item_type = master_meta.get("type")

        # Unmapped — create new in blueprint if it's a pushable Page
        if not bp_meta:
            if item_type in NO_PUSH_TYPES or item_type == "NewQuiz":
                skipped += 1
                continue
            if item_type in ("Assignment", "Discussion", "Quiz"):
                title = master_meta.get("title", Path(master_fp).stem)
                print(f"  [{item_type}] NEW — add manually in Blueprint UI, then re-run --pull: {title}")
                skipped += 1
                continue
            if item_type == "Page":
                title = master_meta.get("title") or master_path.stem.replace("-", " ").title()
                mod_slug = master_meta.get("module_slug", "")
                # Exact match only — no fuzzy
                bp_mod_id = bp_modules_by_slug.get(mod_slug)
                if not bp_mod_id:
                    print(f"  [Page] NEW {master_fp}")
                    print(f"    SKIP: no exact blueprint module match for slug '{mod_slug}'")
                    skipped += 1
                    continue
                print(f"  [Page] NEW {master_fp}")
                body = master_path.read_text(encoding="utf-8")
                published = master_meta.get("published", True)
                # Idempotent upsert (issue #26): reuse an existing same-title
                # blueprint page instead of POSTing a duplicate every run.
                page_url, action = upsert_page(
                    CANVAS_BASE_URL, _headers(), bp_id, title, body, published
                )
                if action == "ambiguous":
                    print(f"    SKIP: >1 blueprint page already titled '{title}' — "
                          f"manual review (corrupted state; see #23/#26)")
                    skipped += 1
                    continue
                if action.startswith("error"):
                    print(f"    FAILED upsert: {action[6:]}")
                    failed += 1
                    continue
                # Module-item guard (#26): don't re-link a page already in the module.
                if page_in_module(CANVAS_BASE_URL, _headers(), bp_id, bp_mod_id, page_url):
                    print(f"    {action.upper()} → {page_url} (already in module; not re-added)")
                    pushed += 1
                    pushed_files.append(master_fp)
                    continue
                r2 = requests.post(
                    f"{CANVAS_BASE_URL}/api/v1/courses/{bp_id}/modules/{bp_mod_id}/items",
                    headers=_headers(),
                    json={"module_item": {"type": "Page", "page_url": page_url, "position": 1}},
                    timeout=20,
                )
                if r2.status_code < 400:
                    print(f"    {action.upper()} → {page_url} (linked to module)")
                    pushed += 1
                    pushed_files.append(master_fp)
                else:
                    print(f"    {action} page but failed to add to module: {r2.text[:100]}")
                    pushed += 1
                    pushed_files.append(master_fp)
            else:
                skipped += 1
            continue

        bp_canvas_id = bp_meta.get("blueprint_canvas_id")
        bp_page_url = bp_meta.get("blueprint_page_url")

        if item_type in NO_PUSH_TYPES:
            skipped += 1
            continue

        print(f"  [{item_type}] {master_fp}")
        ok = False

        if item_type == "Page" and bp_page_url:
            body = master_path.read_text(encoding="utf-8")
            r = _put(f"/courses/{bp_id}/pages/{bp_page_url}", {
                "wiki_page": {
                    "body": body,
                    "published": master_meta.get("published", True),
                }
            })
            ok = not r.get("error")
            if not ok:
                print(f"    FAILED: {r.get('error')}")

        elif item_type == "Assignment" and bp_canvas_id:
            data = json.loads(master_path.read_text(encoding="utf-8"))
            payload = {
                "assignment": {
                    "description": data.get("description", ""),
                    "points_possible": data.get("points_possible"),
                    "published": data.get("published", True),
                    "due_at": data.get("due_at"),
                    "lock_at": data.get("lock_at"),
                    "unlock_at": data.get("unlock_at"),
                }
            }
            r = _put(f"/courses/{bp_id}/assignments/{bp_canvas_id}", payload)
            ok = not r.get("error")
            if not ok:
                print(f"    FAILED: {r.get('error')}")

        elif item_type == "Discussion" and bp_canvas_id:
            data = json.loads(master_path.read_text(encoding="utf-8"))
            payload = {
                "title": data.get("title", ""),
                "message": data.get("message", data.get("description", "")),
                "published": data.get("published", True),
                "delayed_post_at": data.get("unlock_at"),
                "lock_at": data.get("lock_at"),
            }
            r = _put(f"/courses/{bp_id}/discussion_topics/{bp_canvas_id}", payload)
            ok = not r.get("error")
            if not ok:
                print(f"    FAILED: {r.get('error')}")

        elif item_type == "Quiz" and bp_canvas_id:
            data = json.loads(master_path.read_text(encoding="utf-8"))
            payload = {
                "quiz": {
                    "description": data.get("description", ""),
                    "due_at": data.get("due_at"),
                    "lock_at": data.get("lock_at"),
                    "unlock_at": data.get("unlock_at"),
                }
            }
            r = _put(f"/courses/{bp_id}/quizzes/{bp_canvas_id}", payload)
            ok = not r.get("error")
            if not ok:
                print(f"    FAILED: {r.get('error')}")

        else:
            print(f"    SKIP: {item_type} (no canvas_id or unsupported)")
            skipped += 1
            continue

        if ok:
            print(f"    OK")
            pushed += 1
            pushed_files.append(master_fp)
        else:
            failed += 1

    # -----------------------------------------------------------------------
    # 5. Module structure: published state, prerequisites, item order + published
    # -----------------------------------------------------------------------
    print(f"\n  [Modules] syncing structure...")

    # Load master module metadata from course/_module.json files
    master_modules = []
    for mod_dir in sorted(MASTER_DIR.iterdir()):
        mf = mod_dir / "_module.json"
        if mf.exists():
            data = _load_json(mf)
            data["_dir_slug"] = mod_dir.name
            master_modules.append(data)
    master_modules.sort(key=lambda m: m.get("position", 999))

    # Load blueprint module metadata from blueprint_course/_module.json files
    # Build both a slug→data dict AND a flat list for _confirm_module_match
    bp_modules_by_slug = {}
    bp_modules_list = []  # flat list used for duplicate detection
    for mod_dir in sorted(BLUEPRINT_DIR.iterdir()):
        mf = mod_dir / "_module.json"
        if mf.exists():
            data = _load_json(mf)
            slug = _slug(data.get("title", mod_dir.name))
            bp_modules_by_slug[slug] = data
            bp_modules_list.append(data)

    # Walk master modules in position order, exact match only
    sprint_bp_mod_ids = []  # collect sprint module IDs for prerequisite chaining
    for master_mod in master_modules:
        master_title = master_mod.get("title", "")
        bp_mod = bp_modules_by_slug.get(_slug(master_title))
        if not bp_mod:
            print(f"    SKIP module (no exact match): {master_title}")
            continue

        bp_mod_id = bp_mod.get("canvas_id")
        master_published = master_mod.get("published", True)

        # Warn if all master module items are non-pushable (module will be empty in blueprint)
        master_items = master_mod.get("items", [])
        pushable_items = [it for it in master_items
                          if it.get("type") not in NO_PUSH_TYPES
                          and it.get("type") not in ("NewQuiz",)]
        if master_items and not pushable_items:
            print(f"    WARNING: '{master_title}' has {len(master_items)} item(s) but none are pushable "
                  f"(all NewQuiz/ExternalTool) — module will be empty in blueprint")

        # Set module published state
        state = "active" if master_published else "unpublished"
        r = requests.put(
            f"{CANVAS_BASE_URL}/api/v1/courses/{bp_id}/modules/{bp_mod_id}",
            headers={k: v for k, v in _headers().items() if k != "Content-Type"},
            data={"module[workflow_state]": state},
            timeout=20,
        )
        ok = r.status_code < 400
        print(f"    {master_title}: published={master_published} → {'OK' if ok else 'FAILED'}")
        if ok:
            pushed_files.append(f"module/{master_title}/published")
        else:
            failed += 1

        # Track sprint modules for prerequisite chaining
        if "sprint" in _slug(master_title) or "project" in _slug(master_title):
            sprint_bp_mod_ids.append(bp_mod_id)

        # Sync module item published state + position by title-matching
        bp_items_by_title = {
            _slug(item.get("title", "")): item
            for item in bp_mod.get("items", [])
        }
        for master_item in master_mod.get("items", []):
            item_title = master_item.get("title", "")
            item_slug = _slug(item_title)
            bp_item = bp_items_by_title.get(item_slug)
            if not bp_item:
                continue
            bp_item_id = bp_item.get("module_item_id")
            master_item_published = master_item.get("published", True)
            master_position = master_item.get("position")
            payload = {}
            if master_item_published != bp_item.get("published"):
                payload["module_item[published]"] = str(master_item_published).lower()
            if master_position and master_position != bp_item.get("position"):
                payload["module_item[position]"] = master_position
            if payload:
                r2 = requests.put(
                    f"{CANVAS_BASE_URL}/api/v1/courses/{bp_id}/modules/{bp_mod_id}/items/{bp_item_id}",
                    headers={k: v for k, v in _headers().items() if k != "Content-Type"},
                    data=payload,
                    timeout=20,
                )
                if r2.status_code >= 400:
                    print(f"      item '{item_title}': FAILED {r2.text[:80]}")
                    failed += 1

    # Wire prerequisite chain for sprint modules (Sprint N requires Sprint N-1)
    if len(sprint_bp_mod_ids) > 1:
        print(f"    Prerequisites: chaining {len(sprint_bp_mod_ids)} sprint modules...")
        for i in range(1, len(sprint_bp_mod_ids)):
            r = requests.put(
                f"{CANVAS_BASE_URL}/api/v1/courses/{bp_id}/modules/{sprint_bp_mod_ids[i]}",
                headers={k: v for k, v in _headers().items() if k != "Content-Type"},
                data={"module[prerequisite_module_ids][]": sprint_bp_mod_ids[i - 1]},
                timeout=20,
            )
            if r.status_code >= 400:
                print(f"      prereq chain {i}: FAILED {r.text[:80]}")
                failed += 1
        print(f"    Prerequisites: OK")
        pushed_files.append("modules/prerequisites")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\nSync complete.")
    print(f"  {pushed} pushed, {skipped} skipped (unmapped/no-API), {failed} failed")
    if failed:
        print(f"  NOTE: late_policy requires Canvas admin token — set manually in Blueprint Settings.")
    _log(f"[BLUEPRINT PUSH] {pushed} pushed, {skipped} skipped, {failed} failed", pushed_files)
    print(f"  Logged → {BLUEPRINT_LOG}")


# ---------------------------------------------------------------------------
# Status: show mapping coverage
# ---------------------------------------------------------------------------

def cmd_status():
    """Show what would be synced from master to blueprint."""
    master_index = _load_json(MASTER_INDEX)
    blueprint_index = _load_json(BLUEPRINT_INDEX)

    if not master_index.get("files"):
        print("Master index not found. Run 'canvas_sync.py --pull' first.")
        return
    if not blueprint_index.get("mappings"):
        print("Blueprint mapping not found. Run 'blueprint_sync.py --pull' first.")
        return

    mappings = blueprint_index["mappings"]
    total = len(master_index["files"])
    mapped = sum(1 for fp in master_index["files"] if fp in mappings)

    pushable_types = {"Page", "Assignment", "Discussion", "Quiz"}
    pushable = sum(
        1 for fp, meta in master_index["files"].items()
        if fp in mappings and meta.get("type") in pushable_types
    )

    # Date coverage: how many mapped assignments have due_at in master
    dated = sum(
        1 for fp, meta in master_index["files"].items()
        if fp in mappings and meta.get("type") in ("Assignment", "Quiz", "Discussion")
        and Path(fp).exists()
        and json.loads(Path(fp).read_text()).get("due_at")
    )

    print(f"Blueprint sync status")
    print(f"  Blueprint course:  {blueprint_index.get('blueprint_course_id')}")
    print(f"  Blueprint mirror:  {BLUEPRINT_DIR}/")
    print(f"  Last pull:         {blueprint_index.get('pulled_at', 'never')}")
    print(f"  Master items:      {total}")
    print(f"  Mapped:            {mapped}")
    print(f"  Will push:         {pushable} (Page/Assignment/Discussion/Quiz, with dates)")
    print(f"  Skipped (no API):  {mapped - pushable} (NewQuiz/ExternalTool/etc.)")
    print(f"  Unmapped:          {total - mapped} (not found in blueprint)")
    print(f"  Items with due_at: {dated}")

    if blueprint_index.get("unmapped_master"):
        pushable_unmapped = [fp for fp in blueprint_index["unmapped_master"]
                             if master_index["files"].get(fp, {}).get("type") not in NO_PUSH_TYPES
                             and master_index["files"].get(fp, {}).get("type") != "NewQuiz"]
        if pushable_unmapped:
            print(f"\n  Unmapped pushable master items (will be created as new):")
            for fp in pushable_unmapped:
                t = master_index["files"].get(fp, {}).get("type", "?")
                print(f"    [{t}] {fp}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    parser = argparse.ArgumentParser(
        description="Sync master Canvas course → Blueprint course (one-way overwrite)"
    )
    parser.add_argument("--version", action="version",
                        version=f"canvas-toolbox {__version__}")
    parser.add_argument("--pull", action="store_true",
                        help="Full init: pull blueprint into blueprint_course/ + build ID mapping")
    parser.add_argument("--push", action="store_true",
                        help="Sync master content + dates → blueprint (full overwrite)")
    parser.add_argument("--status", action="store_true",
                        help="Show mapping coverage and what would be synced")
    parser.add_argument("--allow-enrolled", action="store_true",
                        help="bypass the startup safety guard (#27)")
    args = parser.parse_args()

    # Startup safety guard (#27): source = MASTER_COURSE_ID (read on every
    # mode), target = BLUEPRINT_COURSE_ID (write on --push).
    if args.pull or args.push or args.status:
        _course_guard(CANVAS_BASE_URL, _headers(), MASTER_COURSE_ID, "read",
                      allow_override=args.allow_enrolled,
                      label="source (MASTER_COURSE_ID)")
    if args.push:
        _course_guard(CANVAS_BASE_URL, _headers(), BLUEPRINT_COURSE_ID, "write",
                      allow_override=args.allow_enrolled,
                      label="target (BLUEPRINT_COURSE_ID)")

    if args.pull:
        cmd_pull()
    elif args.push:
        cmd_push()
    elif args.status:
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

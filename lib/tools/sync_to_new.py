#!/usr/bin/env python3
"""
sync_to_new.py — Deploy local course content to new Canvas course

PROBLEM
  Campus deletes old Canvas courses, breaking instructor's ability to copy
  course content to new sections. Even if old course exists, Canvas course
  copy can be unreliable (misses content, breaks module structure).

SOLUTION
  Deploy locally-stored course content (pulled via canvas_sync.py) into a
  NEW Canvas course with different course ID. Git becomes source of truth.

HOW IT WORKS
  1. Read course structure from .canvas/index.json
  2. Read content files from course/ directory
  3. Create modules in target course (in order)
  4. Create pages and link to modules
  5. (Phase 2+: assignments, quizzes, discussions)

APPROACH
  Reverse sync (API-by-API recreation), NOT Canvas import API + IMSCC.

  Why: Reuses 80% of existing canvas_sync infrastructure, provides selective
  restore, transparent errors, preview mode, and incremental rollback.

PHASE 1 MVP SCOPE (current)
  - Module creation
  - Page creation and linking
  - Dry-run preview mode
  - Basic progress reporting

USAGE
  # Preview what would be created (dry-run, default)
  uv run python lib/tools/sync_to_new.py

  # Apply: create modules and pages in target course
  uv run python lib/tools/sync_to_new.py --apply

  # A run stopped partway (e.g. a dropped connection): continue it. Items already
  # in the course with the same title are reused, not created again (#445).
  uv run python lib/tools/sync_to_new.py --apply --resume

REQUIRES in .env
  CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID (target course)

REQUIRES local content
  .canvas/index.json (course structure metadata)
  course/ directory (HTML files, JSON files)

Implementation plan: docs/implementation/sync_to_new.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: uv sync", file=sys.stderr)
    raise SystemExit(1) from None

try:
    from _env_loader import load_env
except ImportError:
    def load_env() -> None:
        pass

from canvas_course_guard import enforce as _course_guard
import _canvas_retry as _cr  # retry through a dropped connection; never re-send an unsure create (#445)
import time

_TIMEOUT = 60


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _load_config() -> tuple[str, str, str]:
    """Load Canvas config from environment.

    Returns:
        (base_url, course_id, token)
    """
    load_env()

    token = os.environ.get("CANVAS_API_TOKEN", "")
    base_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
    course_id = os.environ.get("CANVAS_COURSE_ID", "")

    if base_url and not base_url.startswith("http"):
        base_url = "https://" + base_url

    if not token or not base_url or not course_id:
        print("ERROR: Missing required .env variables:", file=sys.stderr)
        print("  CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID", file=sys.stderr)
        return ("", "", "")

    return (base_url, course_id, token)


# ---------------------------------------------------------------------------
# Canvas API helpers
# ---------------------------------------------------------------------------

def _headers(token: str) -> dict:
    """Return Canvas API headers with authorization."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


class _Target:
    """What the target course already has, by list URL and title (#445).

    A create's URL is also the URL that lists that kind of thing (POST
    /courses/:id/modules creates, GET lists). Each existing object can be claimed
    once, so two local items with the same title match two existing ones, not one.
    Re-running after a dropped connection then reuses what the first run made
    instead of making it again."""

    def __init__(self, token: str, reuse: bool = False):
        # reuse=True (--resume): claim a same-titled item before every create, so
        # a re-run continues. Without it only an unsure create is settled by title.
        self.token, self.reuse, self._lists, self._claimed = token, reuse, {}, set()

    @staticmethod
    def _title(obj: dict):
        return obj.get("title") if "title" in obj else obj.get("name")

    def _fetch(self, url: str) -> list:
        out, params, seen = [], {"per_page": 100}, set()
        while url and url not in seen:
            seen.add(url)
            r = _cr.request("GET", url, headers=_headers(self.token), params=params,
                            timeout=_TIMEOUT, client=requests)
            r.raise_for_status()
            out += r.json() or []
            url, params = r.links.get("next", {}).get("url"), None
        return out

    def claim(self, url: str, title: str, refresh: bool = False):
        if refresh or url not in self._lists:
            self._lists[url] = self._fetch(url)
        plain_assignments = url.endswith("/assignments")
        for obj in self._lists[url]:
            key = (url, obj.get("id"))
            if plain_assignments and _is_quiz_or_discussion(obj):
                continue  # a quiz's or a discussion's assignment is never a plain assignment
            if self._title(obj) == title and key not in self._claimed:
                self._claimed.add(key)
                return obj
        return None

    def mark(self, url: str, obj: dict) -> None:
        self._claimed.add((url, obj.get("id")))


def _is_quiz_or_discussion(obj: dict) -> bool:
    kinds = set(obj.get("submission_types") or [])
    return bool(obj.get("is_quiz_assignment") or obj.get("quiz_id")
                or obj.get("discussion_topic") or kinds & {"online_quiz", "external_tool",
                                                           "discussion_topic"})


_TARGET: Optional[_Target] = None   # set by main() for --apply


def _done(obj: dict) -> str:
    """"Reused" for an object that was already in the course, else "Created"."""
    return "Reused" if (obj or {}).get("_reused") else "Created"


# What this run did, for the closing report (#445): done / not done / unsure.
RESULTS: dict = {"created": [], "reused": [], "updated": [], "not_done": [], "unsure": []}


def _post(url: str, payload: dict, token: str, title: Optional[str] = None,
          form: bool = False, update_reused: bool = False,
          label: Optional[str] = None) -> dict:
    """POST (create) to Canvas, safely across a dropped connection (#445).

    With a `title` and a target record (--apply): an object already there with
    that title, not yet claimed, is reused instead of created again (and, with
    update_reused, updated with this payload). A create that may have reached
    Canvas is never blindly sent again: the target is read again after a pause,
    and the create counts as done if it's there, is sent once more if it isn't,
    and is reported as unsure if that can't be told.

    Returns:
        {"success": True, "data": {...}} on success
        {"success": False, "error": "...", "status_code": 400} on error
        ("unsure": True when a create may or may not have happened)
    """
    label = label or title or url
    body = {"data": payload} if form else {"json": payload}
    headers = ({**_headers(token), "Content-Type": "application/x-www-form-urlencoded"}
               if form else _headers(token))
    if _TARGET is not None and title and (_TARGET.reuse or update_reused):
        try:
            existing = _TARGET.claim(url, title)
        except requests.RequestException as exc:
            existing = None
            print(f"  ⚠ couldn't check what's already in the course ({type(exc).__name__}); "
                  f"creating '{title}'", file=sys.stderr)
        if existing:
            print(f"    (already in the course: reused '{title}')")
            # Updated ones have this run's settings; plain reuse keeps Canvas's copy.
            RESULTS["updated" if update_reused else "reused"].append(label)
            existing = {**existing, "_reused": True}
            if update_reused and existing.get("id"):
                # Bring the reused item's settings in line with this one's (e.g. a
                # group's weight); checked and reported like any other write.
                try:
                    put = _cr.request("PUT", f"{url}/{existing['id']}", headers=headers,
                                      timeout=_TIMEOUT, client=requests, **body)
                    failed = put.status_code >= 400
                    why = put.text[:200] if failed else ""
                except requests.RequestException as exc:
                    failed, why = True, f"Canvas didn't answer ({type(exc).__name__})"
                if failed:
                    print(f"    ⚠ couldn't apply the settings to '{title}': {why}", file=sys.stderr)
                    RESULTS["not_done"].append(f"{label} (settings)")
            return {"success": True, "data": existing, "status_code": 200, "reused": True}

    for attempt in (1, 2):
        try:
            resp = _cr.request("POST", url, headers=headers, timeout=_TIMEOUT,
                               client=requests, **body)
        except _cr.UnsureWrite as exc:
            if _TARGET is not None and title:
                # Canvas may still be finishing a create it received: look twice,
                # after 5 s and after another 20 s, before deciding it didn't land.
                landed = None
                for wait in (5, 20):
                    time.sleep(wait)
                    try:
                        landed = _TARGET.claim(url, title, refresh=True)
                    except requests.RequestException:
                        landed, attempt = None, 2  # couldn't look: don't risk sending it again
                        break
                    if landed:
                        break
                if landed:
                    print(f"    (the connection dropped, but '{title}' is in Canvas: it was created)")
                    RESULTS["created"].append(label)
                    return {"success": True, "data": landed, "status_code": 200}
                if attempt == 1:
                    print(f"    (the connection dropped and '{title}' isn't in Canvas: sending it once more)")
                    continue
            RESULTS["unsure"].append(label)
            return {"success": False, "error": str(exc), "status_code": 0, "unsure": True}
        except requests.RequestException as e:
            RESULTS["not_done"].append(label)
            return {"success": False, "error": f"Canvas didn't answer ({type(e).__name__}): {e}",
                    "status_code": 0}

        if resp.status_code >= 400:
            RESULTS["not_done"].append(label)
            return {
                "success": False,
                "error": resp.text[:300],
                "status_code": resp.status_code
            }

        data = resp.json() if resp.text else {}
        if _TARGET is not None:
            _TARGET.mark(url, data)
        RESULTS["created"].append(label)
        return {"success": True, "data": data, "status_code": resp.status_code}
    return {"success": False, "error": "not sent", "status_code": 0}  # pragma: no cover


# ---------------------------------------------------------------------------
# Course content loading
# ---------------------------------------------------------------------------

def load_course_content(canvas_dir: Path = Path(".canvas")) -> dict:
    """Load course structure from .canvas/index.json.

    Returns:
        {
            "course_id": "145706",
            "base_url": "https://...",
            "modules": [...],
            "files": {...}
        }
    """
    index_path = canvas_dir / "index.json"

    if not index_path.exists():
        print(f"ERROR: {index_path} not found", file=sys.stderr)
        print("\nThis tool requires a fully downloaded course. Follow these steps:\n", file=sys.stderr)
        print("  1. Download source course:", file=sys.stderr)
        print("     CANVAS_COURSE_ID=<source> uv run python lib/tools/canvas_sync.py --pull-all", file=sys.stderr)
        print("\n  2. Adjust dates/content in JSON files if needed (optional)", file=sys.stderr)
        print("\n  3. Restore to new course:", file=sys.stderr)
        print("     CANVAS_COURSE_ID=<target> uv run python lib/tools/sync_to_new.py --apply", file=sys.stderr)
        return {}

    with open(index_path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Module creation
# ---------------------------------------------------------------------------

def create_module(base_url: str, course_id: str, module_data: dict, token: str) -> Optional[dict]:
    """Create single module in target course.

    Args:
        module_data: {
            "title": "Module Title",
            "position": 1,
            "published": False,
            "unlock_at": "2026-01-13T00:00:00Z"  # optional
        }

    Returns:
        Canvas module object with new canvas_id, or None on error
    """
    url = f"{base_url}/api/v1/courses/{course_id}/modules"
    payload = {"module": module_data}

    result = _post(url, payload, token, title=module_data.get("name"))

    if not result["success"]:
        print(f"  ✗ Failed to create module '{module_data.get('name')}': {result['error']}", file=sys.stderr)
        return None

    return result["data"]


def create_modules(base_url: str, course_id: str, modules: list, token: str) -> dict:
    """Create all modules in target course.

    Returns:
        Mapping of module slug → new Canvas module_id
    """
    slug_to_id = {}

    # Sort by position to maintain order
    for module in sorted(modules, key=lambda m: m.get('position', 999)):
        module_payload = {
            "name": module["title"],
            "position": module.get("position", 1),
            "published": module.get("published", False),
        }

        # Add optional fields if present
        if module.get("unlock_at"):
            module_payload["unlock_at"] = module["unlock_at"]
        if module.get("require_sequential_progress"):
            module_payload["require_sequential_progress"] = module["require_sequential_progress"]

        new_module = create_module(base_url, course_id, module_payload, token)

        if new_module:
            slug_to_id[module["slug"]] = new_module["id"]
            print(f"  ✓ {_done(new_module)} module: {module['title']} (id: {new_module['id']})")
        else:
            print(f"  ✗ Skipped module: {module['title']} (creation failed)")

    return slug_to_id


# ---------------------------------------------------------------------------
# Page creation
# ---------------------------------------------------------------------------

def create_page(base_url: str, course_id: str, page_data: dict, html_content: str, token: str) -> Optional[dict]:
    """Create single wiki page in target course.

    Args:
        page_data: {
            "title": "Page Title",
            "published": False
        }
        html_content: Raw HTML body

    Returns:
        Canvas page object with page_id, or None on error
    """
    url = f"{base_url}/api/v1/courses/{course_id}/pages"
    payload = {
        "wiki_page": {
            "title": page_data["title"],
            "body": html_content,
            "published": page_data.get("published", False),
        }
    }

    result = _post(url, payload, token, title=page_data["title"])

    if not result["success"]:
        print(f"  ✗ Failed to create page '{page_data['title']}': {result['error']}", file=sys.stderr)
        return None

    return result["data"]


# ---------------------------------------------------------------------------
# Module item linking
# ---------------------------------------------------------------------------

def create_module_item(base_url: str, course_id: str, module_id: int, item_data: dict, token: str) -> Optional[dict]:
    """Link content item to module.

    Args:
        item_data: {
            "title": "Item Title",
            "type": "Page",
            "page_url": "page-slug",  # for Pages
            "position": 1,
            "indent": 0
        }

    Returns:
        Canvas module item object, or None on error
    """
    url = f"{base_url}/api/v1/courses/{course_id}/modules/{module_id}/items"
    payload = {"module_item": item_data}

    result = _post(url, payload, token, title=item_data.get("title"),
                   label=f"module link: {item_data.get('title')}")

    if not result["success"]:
        print(f"  ✗ Failed to link item '{item_data['title']}' to module: {result['error']}", file=sys.stderr)
        return None

    return result["data"]


# ---------------------------------------------------------------------------
# Page orchestration
# ---------------------------------------------------------------------------

def create_pages_in_modules(
    base_url: str,
    course_id: str,
    files: dict,
    module_mapping: dict,
    token: str,
    file_mapping: dict = None,
    source_course_id: str = None
) -> dict:
    """Create all pages and link them to modules.

    Args:
        file_mapping: Optional old_file_id → new_file_id mapping
        source_course_id: Optional source course ID for URL rewriting

    Returns:
        Mapping of local page path → new Canvas page_url
    """
    page_mapping = {}

    # Filter for pages only
    pages = {path: meta for path, meta in files.items() if meta.get("type") == "Page"}

    if not pages:
        print("  No pages found to create")
        return page_mapping

    for page_path, page_meta in pages.items():
        # Read HTML content
        local_path = Path(page_path)
        if not local_path.exists():
            print(f"  ⚠ Skipped page '{page_meta['title']}': file not found at {page_path}")
            continue

        html_content = local_path.read_text(encoding="utf-8")

        # Rewrite file URLs if mapping provided
        if file_mapping and source_course_id:
            html_content = rewrite_file_urls(html_content, source_course_id, course_id, file_mapping)

        # Create page
        new_page = create_page(
            base_url,
            course_id,
            page_meta,
            html_content,
            token
        )

        if not new_page:
            continue

        page_mapping[page_path] = new_page["url"]
        print(f"  ✓ {_done(new_page)} page: {page_meta['title']}")

        # Link to module
        module_slug = page_meta.get("module_slug")
        if module_slug and module_slug in module_mapping:
            item_payload = {
                "title": page_meta["title"],
                "type": "Page",
                "page_url": new_page["url"],
                "position": page_meta.get("module_item_position", 1),
                "indent": page_meta.get("indent", 0)
            }

            module_item = create_module_item(
                base_url,
                course_id,
                module_mapping[module_slug],
                item_payload,
                token
            )

            if module_item:
                print(f"    → Linked to module: {module_slug}")

    return page_mapping


# ---------------------------------------------------------------------------
# Assignment group creation
# ---------------------------------------------------------------------------

def create_assignment_group(base_url: str, course_id: str, group_data: dict, token: str) -> Optional[dict]:
    """Create single assignment group in target course.

    Args:
        group_data: {
            "name": "Homework",
            "group_weight": 40.0,
            "position": 1
        }

    Returns:
        Canvas assignment group object with new canvas_id, or None on error
    """
    url = f"{base_url}/api/v1/courses/{course_id}/assignment_groups"
    # FLAT, not wrapped in "assignment_group" — unlike modules/assignments/quizzes.
    # Caught on a sandbox (#351): a wrapped POST returns 200 but silently creates a
    # group named "Assignments" with group_weight 0, ignoring every field sent.
    payload = group_data

    # update_reused: a new course already has a default "Assignments" group; reuse
    # it with this group's settings instead of making a second one (#445).
    result = _post(url, payload, token, title=group_data.get("name"), update_reused=True)

    if not result["success"]:
        print(f"  ✗ Failed to create assignment group '{group_data['name']}': {result['error']}", file=sys.stderr)
        return None

    return result["data"]


def create_assignment_groups(base_url: str, course_id: str, groups: list, token: str) -> dict:
    """Create all assignment groups in target course.

    Returns:
        Mapping of old assignment_group canvas_id → new canvas_id
    """
    group_mapping = {}

    if not groups:
        return group_mapping

    for group in groups:
        group_payload = {
            "name": group["name"],
            "group_weight": group.get("group_weight", 0.0),
        }

        new_group = create_assignment_group(base_url, course_id, group_payload, token)

        if new_group:
            old_id = group["canvas_id"]
            new_id = new_group["id"]
            group_mapping[old_id] = new_id
            print(f"  ✓ {_done(new_group)} assignment group: {group['name']} (id: {new_id})")
        else:
            print(f"  ✗ Skipped assignment group: {group['name']} (creation failed)")

    return group_mapping


# ---------------------------------------------------------------------------
# Assignment creation
# ---------------------------------------------------------------------------

def create_assignment(base_url: str, course_id: str, assignment_data: dict, description: str, token: str) -> Optional[dict]:
    """Create single assignment in target course.

    Args:
        assignment_data: {
            "name": "Assignment Name",
            "points_possible": 100,
            "grading_type": "points",
            "submission_types": ["online_text_entry"],
            "due_at": "2026-01-13T23:59:59Z",
            "assignment_group_id": 123456,
            "published": false
        }
        description: HTML description/instructions

    Returns:
        Canvas assignment object with new canvas_id, or None on error
    """
    url = f"{base_url}/api/v1/courses/{course_id}/assignments"

    # Build payload with required and optional fields
    payload = {
        "assignment": {
            "name": assignment_data["name"],
            "description": description,
            "points_possible": assignment_data.get("points_possible", 0),
            "grading_type": assignment_data.get("grading_type", "points"),
            "submission_types": assignment_data.get("submission_types", ["none"]),
            "published": assignment_data.get("published", False),
        }
    }

    # Add optional fields if present
    if assignment_data.get("due_at"):
        payload["assignment"]["due_at"] = assignment_data["due_at"]
    if assignment_data.get("unlock_at"):
        payload["assignment"]["unlock_at"] = assignment_data["unlock_at"]
    if assignment_data.get("lock_at"):
        payload["assignment"]["lock_at"] = assignment_data["lock_at"]
    if assignment_data.get("assignment_group_id"):
        payload["assignment"]["assignment_group_id"] = assignment_data["assignment_group_id"]

    result = _post(url, payload, token, title=assignment_data["name"])

    if not result["success"]:
        print(f"  ✗ Failed to create assignment '{assignment_data['name']}': {result['error']}", file=sys.stderr)
        return None

    return result["data"]


def create_assignments_in_modules(
    base_url: str,
    course_id: str,
    files: dict,
    module_mapping: dict,
    group_mapping: dict,
    token: str,
    file_mapping: dict = None,
    source_course_id: str = None
) -> dict:
    """Create all assignments and link them to modules.

    Args:
        file_mapping: Optional old_file_id → new_file_id mapping
        source_course_id: Optional source course ID for URL rewriting

    Returns:
        Mapping of local assignment path → new Canvas assignment_id
    """
    assignment_mapping = {}

    # Filter for assignments only
    assignments = {path: meta for path, meta in files.items() if meta.get("type") == "Assignment"}

    if not assignments:
        print("  No assignments found to create")
        return assignment_mapping

    for assignment_path, assignment_meta in assignments.items():
        # Read assignment JSON
        local_path = Path(assignment_path)
        if not local_path.exists():
            print(f"  ⚠ Skipped assignment '{assignment_meta['title']}': file not found at {assignment_path}")
            continue

        assignment_data = json.load(local_path.open(encoding="utf-8"))
        description = assignment_data.get("description", "")

        # Rewrite file URLs if mapping provided
        if file_mapping and source_course_id:
            description = rewrite_file_urls(description, source_course_id, course_id, file_mapping)

        # Map old assignment_group_id to new one
        old_group_id = assignment_data.get("assignment_group_id")
        if old_group_id and old_group_id in group_mapping:
            assignment_data["assignment_group_id"] = group_mapping[old_group_id]
        else:
            assignment_data.pop("assignment_group_id", None)  # Remove if no mapping

        # Create assignment
        new_assignment = create_assignment(
            base_url,
            course_id,
            assignment_data,
            description,
            token
        )

        if not new_assignment:
            continue

        assignment_mapping[assignment_path] = new_assignment["id"]
        print(f"  ✓ {_done(new_assignment)} assignment: {assignment_meta['title']}")

        # Link to module
        module_slug = assignment_meta.get("module_slug")
        if module_slug and module_slug in module_mapping:
            item_payload = {
                "title": assignment_meta["title"],
                "type": "Assignment",
                "content_id": new_assignment["id"],
                "position": assignment_meta.get("module_item_position", 1),
                "indent": assignment_meta.get("indent", 0)
            }

            module_item = create_module_item(
                base_url,
                course_id,
                module_mapping[module_slug],
                item_payload,
                token
            )

            if module_item:
                print(f"    → Linked to module: {module_slug}")

    return assignment_mapping


def create_newquizzes_in_modules(
    base_url: str,
    course_id: str,
    files: dict,
    module_mapping: dict,
    group_mapping: dict,
    token: str,
) -> dict:
    """Create New Quizzes (settings + question items) in the new course and link them
    to modules. On by default; opt out with `CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE=false`, the same gate as
    `canvas_sync.py --update`. A quiz already in the course with the same title (from a
    run that stopped partway) is reused, and its questions aren't added again (#445).

    The create/item payload helpers are canvas_sync's, so a New Quiz is written the
    same way whichever tool does it. Stimulus/Bank/BankEntry items are read-only to
    the API and are reported, not created. Quizzes are created unpublished.

    Returns: mapping of local sidecar path -> new New Quiz (assignment) id."""
    newquizzes = {path: meta for path, meta in files.items() if meta.get("type") == "NewQuiz"}
    mapping: dict = {}
    if not newquizzes:
        return mapping
    import canvas_sync as cs
    if not cs.newquiz_write_enabled():
        print(f"  ⚠ Skipped {len(newquizzes)} New Quiz(zes): disabled by "
              "CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE=false")
        return mapping


    quiz_url = f"{base_url}/api/quiz/v1/courses/{course_id}/quizzes"
    for path, meta in newquizzes.items():
        title = meta.get("title", path)
        sidecar_path = Path(meta.get("settings_path") or "")
        if not sidecar_path.is_file():
            print(f"  ⚠ Skipped New Quiz '{title}': sidecar not found at {sidecar_path}")
            continue
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        settings = dict(sidecar.get("settings") or {})
        old_group_id = settings.pop("assignment_group_id", None)
        payload = cs._newquiz_settings_payload(settings)
        try:        # the New Quiz API returns ids as strings; the mapping is keyed by int
            new_group_id = group_mapping.get(int(old_group_id))
        except (TypeError, ValueError):
            new_group_id = None

        result = _post(quiz_url, payload, token, title=title, form=True)
        if not result["success"] or not (result.get("data") or {}).get("id"):
            print(f"  ✗ Failed to create New Quiz '{title}': {str(result.get('error'))[:200]}",
                  file=sys.stderr)
            continue
        new_id = result["data"]["id"]
        mapping[path] = new_id
        reused = bool(result.get("reused"))
        if reused:
            # Already in the course, e.g. from a run that stopped partway: its questions can't be
            # matched reliably, so they aren't added again (#445). Its group and module
            # link still are, so a re-run finishes what the first run didn't.
            print(f"    ⚠ '{title}' already existed: its questions weren't added again. "
                  f"Check them in Canvas.")
            RESULTS["unsure"].append(f"{title} (questions)")
        if new_group_id:
            # Canvas ignores quiz[assignment_group_id] on create (sandbox-confirmed,
            # canvas_api_lessons_learned.md L32) — it only takes on a PATCH.
            gr = _cr.request(
                "PATCH",
                f"{quiz_url}/{new_id}",
                client=requests,
                headers={**_headers(token), "Content-Type": "application/x-www-form-urlencoded"},
                data={"quiz[assignment_group_id]": new_group_id}, timeout=30)
            if gr.status_code >= 400:
                print(f"    ⚠ could not set assignment group: {gr.text[:200]}", file=sys.stderr)
                RESULTS["not_done"].append(f"{title} (assignment group)")

        created = failed = 0
        for item in ([] if reused else sidecar.get("items") or []):
            if item.get("entry_type", "Item") != "Item":
                print(f"    SKIP read-only New Quiz item type: {item.get('entry_type')}")
                continue
            try:
                r = _cr.request("POST", f"{quiz_url}/{new_id}/items", headers=_headers(token),
                                json=cs._newquiz_item_payload(item), timeout=30, client=requests)
            except _cr.UnsureWrite:
                failed += 1
                RESULTS["unsure"].append(f"{title}: question {(item.get('entry') or {}).get('title', '<untitled>')!r}")
                print("    ? a question may or may not have been added (connection dropped)",
                      file=sys.stderr)
                continue
            except requests.RequestException as exc:
                failed += 1
                RESULTS["not_done"].append(f"{title}: a question")
                print(f"    ✗ a question wasn't added: Canvas didn't answer ({type(exc).__name__})",
                      file=sys.stderr)
                continue
            if r.status_code >= 400:
                failed += 1
                RESULTS["not_done"].append(f"{title}: a question")
                print(f"    ✗ item {(item.get('entry') or {}).get('title', '<untitled>')!r}: "
                      f"{r.text[:200]}", file=sys.stderr)
            else:
                created += 1
        note = f", {failed} item(s) FAILED" if failed else ""
        print(f"  ✓ {_done(result['data'])} New Quiz: {title} ({created} item(s){note})")

        module_slug = meta.get("module_slug")
        if module_slug and module_slug in module_mapping:
            module_item = create_module_item(
                base_url, course_id, module_mapping[module_slug],
                {"title": title, "type": "Assignment", "content_id": new_id,
                 "position": meta.get("module_item_position", 1),
                 "indent": meta.get("indent", 0)},
                token)
            if module_item:
                print(f"    → Linked to module: {module_slug}")
    return mapping


# ---------------------------------------------------------------------------
# File copying and URL rewriting
# ---------------------------------------------------------------------------

def check_source_course_accessible(base_url: str, course_id: str, token: str) -> bool:
    """Check if source course is accessible for server-side file copying."""
    try:
        resp = _cr.request(
            "GET", client=requests, url=f"{base_url}/api/v1/courses/{course_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT
        )
        return resp.status_code < 400
    except Exception:
        return False


def get_root_folder(base_url: str, course_id: str, token: str) -> Optional[int]:
    """Get root folder ID for target course."""
    try:
        resp = _cr.request(
            "GET", client=requests, url=f"{base_url}/api/v1/courses/{course_id}/folders/root",
            headers=_headers(token),
            timeout=_TIMEOUT
        )
        if resp.status_code < 400:
            folder = resp.json()
            return folder.get("id")
    except Exception:
        pass
    return None


def copy_file_server_side(base_url: str, dest_folder_id: int, source_file_id: str, token: str) -> Optional[dict]:
    """Copy file using Canvas server-side copy endpoint.

    Args:
        dest_folder_id: Target course folder ID
        source_file_id: Source file canvas_id (from linked_files)

    Returns:
        New file object with new file_id, or None on error
    """
    url = f"{base_url}/api/v1/folders/{dest_folder_id}/copy_file"
    payload = {
        "source_file_id": source_file_id,
        "on_duplicate": "overwrite"
    }

    # Canvas copy_file endpoint requires form-urlencoded (not JSON)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        resp = _cr.request("POST", url, headers=headers, data=payload, timeout=_TIMEOUT,
                           safe_to_repeat=True, client=requests)  # on_duplicate=overwrite
        if resp.status_code in (200, 201):
            return resp.json()
    except Exception:
        pass

    return None


def upload_file_local(base_url: str, course_id: str, local_path: Path, filename: str, token: str) -> Optional[dict]:
    """Upload file from local storage (two-step Canvas upload).

    Returns:
        New file object with new file_id, or None on error
    """
    import mimetypes

    if not local_path.exists():
        return None

    file_size = local_path.stat().st_size
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # Step 1: Request upload token
    token_url = f"{base_url}/api/v1/courses/{course_id}/files"
    token_payload = {
        "name": filename,
        "size": file_size,
        "content_type": content_type,
        "parent_folder_path": "/uploaded_media",
        "on_duplicate": "overwrite"
    }

    try:
        token_resp = _cr.request(  # asks for an upload slot; creates no file
            "POST", token_url, safe_to_repeat=True, client=requests,
            headers=_headers(token),
            json=token_payload,
            timeout=_TIMEOUT
        )
        if token_resp.status_code >= 400:
            return None

        token_data = token_resp.json()
        upload_url = token_data["upload_url"]
        upload_params = token_data.get("upload_params", {})

        # Step 2: Upload file
        with local_path.open("rb") as fh:
            upload_resp = requests.post(
                upload_url,
                data=upload_params,
                files={"file": (filename, fh, content_type)},
                allow_redirects=True,
                timeout=60
            )

        if upload_resp.status_code not in (200, 201, 301, 302):
            return None

        # Get file object
        file_obj = upload_resp.json() if upload_resp.text else {}

        # If redirect, follow it
        if "id" not in file_obj and upload_resp.history:
            confirm_resp = _cr.request(
                "GET", client=requests, url=upload_resp.url,
                headers=_headers(token),
                timeout=_TIMEOUT
            )
            file_obj = confirm_resp.json() if confirm_resp.text else {}

        return file_obj if "id" in file_obj else None

    except Exception:
        return None


def copy_files(
    base_url: str,
    source_course_id: str,
    target_course_id: str,
    linked_files: dict,
    token: str
) -> dict:
    """Copy all course files (server-side if possible, local fallback).

    Args:
        linked_files: From index["linked_files"] - maps file_id → file metadata

    Returns:
        Mapping of old_file_id → new_file_id
    """
    file_mapping = {}

    if not linked_files:
        return file_mapping

    # Check if source course accessible for server-side copy
    source_accessible = check_source_course_accessible(base_url, source_course_id, token)

    if source_accessible:
        print("  Source course accessible - using server-side file copy")
        dest_folder_id = get_root_folder(base_url, target_course_id, token)

        if not dest_folder_id:
            print("  ✗ Could not get target folder ID")
            source_accessible = False  # Fall back to local

    # Server-side copy
    if source_accessible and dest_folder_id:
        for old_file_id, file_meta in linked_files.items():
            new_file = copy_file_server_side(base_url, dest_folder_id, old_file_id, token)

            if new_file:
                file_mapping[old_file_id] = str(new_file["id"])
                filename = new_file.get("filename", old_file_id)
                print(f"  ✓ Copied file {old_file_id} → {new_file['id']} ({filename})")
            else:
                print(f"  ✗ Failed to copy file {old_file_id}")

    # Local upload fallback
    else:
        print("  Source course not accessible - using local file upload")
        files_dir = Path("course/_files")

        if not files_dir.exists():
            print("  ✗ No local files directory found")
            return file_mapping

        for old_file_id, file_meta in linked_files.items():
            filename = file_meta.get("filename", "unknown")
            local_path_str = file_meta.get("local_path")

            if not local_path_str:
                print(f"  ⚠ Skipped {filename} (no local path)")
                continue

            local_path = Path(local_path_str)
            new_file = upload_file_local(base_url, target_course_id, local_path, filename, token)

            if new_file:
                file_mapping[old_file_id] = str(new_file["id"])
                print(f"  ✓ Uploaded {filename} (local)")
            else:
                print(f"  ✗ Failed to upload {filename}")

    return file_mapping


def rewrite_file_urls(content: str, old_course_id: str, new_course_id: str, file_mapping: dict) -> str:
    """Rewrite Canvas file URLs in HTML/JSON content.

    Args:
        content: HTML or JSON string
        old_course_id: Source course ID (unused - rewrites ANY course ID)
        new_course_id: Target course ID
        file_mapping: old_file_id → new_file_id

    Returns:
        Content with updated file URLs

    Note: Rewrites /courses/{ANY_ID}/files/{file_id} patterns to handle cases
          where HTML was synced from a different course than index.json indicates
          (e.g., after manual course copies or migrations).
    """
    import re

    # Pattern: /courses/{any_course_id}/files/{file_id}
    # Match ANY course ID (not just old_course_id) to handle course migrations
    pattern = r'/courses/\d+/files/(\d+)'

    def replace_url(match):
        old_file_id = match.group(1)
        new_file_id = file_mapping.get(old_file_id)

        if new_file_id:
            return f'/courses/{new_course_id}/files/{new_file_id}'
        else:
            # File not in mapping - leave unchanged (will be broken link)
            return match.group(0)

    return re.sub(pattern, replace_url, content)


# ---------------------------------------------------------------------------
# Preview mode
# ---------------------------------------------------------------------------

def preview_restoration(course_content: dict) -> None:
    """Show what would be created without making changes."""
    print("\n" + "="*60)
    print("PREVIEW: What will be created")
    print("="*60 + "\n")

    modules = course_content.get("modules", [])
    print(f"Modules ({len(modules)}):")
    for module in sorted(modules, key=lambda m: m.get('position', 999)):
        status = "published" if module.get("published") else "unpublished"
        print(f"  {module.get('position', '?')}. {module['title']} ({status})")

    files = course_content.get("files", {})
    pages = [f for f in files.values() if f.get("type") == "Page"]
    print(f"\nPages ({len(pages)}):")

    # Group pages by module
    pages_by_module = {}
    for page in pages:
        module_slug = page.get("module_slug", "no-module")
        if module_slug not in pages_by_module:
            pages_by_module[module_slug] = []
        pages_by_module[module_slug].append(page)

    # Show first 20 pages
    count = 0
    for module_slug in sorted(pages_by_module.keys()):
        module_pages = pages_by_module[module_slug]
        for page in module_pages[:5]:  # Max 5 per module in preview
            count += 1
            if count > 20:
                break
            status = "✓" if page.get("published") else "○"
            print(f"  {status} {page['title']} → {module_slug}")
        if count > 20:
            break

    if len(pages) > 20:
        print(f"  ... and {len(pages) - 20} more pages")

    # Assignment groups
    groups = course_content.get("assignment_groups", [])
    if groups:
        print(f"\nAssignment Groups ({len(groups)}):")
        for group in groups[:10]:  # Show first 10
            weight = group.get("group_weight", 0.0)
            print(f"  - {group['name']} (weight: {weight}%)")
        if len(groups) > 10:
            print(f"  ... and {len(groups) - 10} more groups")

    # Assignments
    assignments = [f for f in files.values() if f.get("type") == "Assignment"]
    if assignments:
        print(f"\nAssignments ({len(assignments)}):")
        for assignment in assignments[:10]:  # Show first 10
            status = "✓" if assignment.get("published") else "○"
            print(f"  {status} {assignment['title']}")
        if len(assignments) > 10:
            print(f"  ... and {len(assignments) - 10} more assignments")

    # NewQuizzes (warn about skipping)
    newquizzes = [f for f in files.values() if f.get("type") == "NewQuiz"]
    if newquizzes:
        import canvas_sync as cs
        if cs.newquiz_write_enabled():
            print(f"\nNewQuizzes ({len(newquizzes)}) - will be created (unpublished):")
            for nq in newquizzes:
                print(f"  ○ {nq['title']}")
        else:
            print(f"\n⚠ NewQuizzes ({len(newquizzes)}) - will be SKIPPED "
                  "(disabled by CANVAS_SYNC_ALLOW_NEWQUIZ_WRITE=false):")
            for nq in newquizzes:
                print(f"  ○ {nq['title']}")

    print("\n" + "="*60)
    print("Re-run with --apply to create these items")
    print("="*60 + "\n")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy local course content to new Canvas course (Phase 4: modules + pages + assignments + files)",
    )
    parser.add_argument("--apply", action="store_true",
                       help="Actually create content (default is dry-run preview)")
    parser.add_argument("--resume", action="store_true",
                       help="Continue a run that stopped partway: reuse items already in the "
                            "course with the same title instead of creating them again. Local "
                            "changes to those items aren't applied (#445)")

    args = parser.parse_args()

    # Load configuration
    base_url, course_id, token = _load_config()
    if not base_url or not course_id or not token:
        return 1

    # Safety check — refuses a write into an enrolled or Blueprint-child course
    _course_guard(base_url, _headers(token), course_id,
                  mode="write" if args.apply else "read")

    # Workflow reminder
    print("\n" + "="*70)
    print("WORKFLOW: Restoring course to new Canvas course")
    print("="*70)
    print("Prerequisites:")
    print("  1. Source course fully downloaded (canvas_sync.py --pull-all)")
    print("  2. Dates/content adjusted locally if needed (optional)")
    print("  3. Target course ID set: CANVAS_COURSE_ID=" + course_id)
    print("="*70 + "\n")

    # Load course content
    print(f"Loading course content from .canvas/index.json...")
    course_content = load_course_content()

    if not course_content:
        return 1

    source_course_id = course_content.get("course_id", "unknown")
    module_count = len(course_content.get("modules", []))
    files = course_content.get("files", {})
    page_count = len([f for f in files.values() if f.get("type") == "Page"])
    assignment_count = len([f for f in files.values() if f.get("type") == "Assignment"])
    group_count = len(course_content.get("assignment_groups", []))

    print(f"✓ Loaded {module_count} modules, {page_count} pages, {group_count} assignment groups, {assignment_count} assignments from course {source_course_id}")

    # Validate content
    if module_count == 0 and page_count == 0 and assignment_count == 0:
        print("\n⚠ WARNING: Course content appears empty (no modules, pages, or assignments)", file=sys.stderr)
        print("  This might indicate an incomplete sync. Consider running:", file=sys.stderr)
        print(f"    CANVAS_COURSE_ID={source_course_id} uv run python lib/tools/canvas_sync.py --pull-all", file=sys.stderr)
        confirm = input("\nContinue with empty course? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return 0

    # Check for file references
    linked_files = course_content.get("linked_files", {})
    files_dir = Path("course/_files")

    if linked_files:
        # Count how many files are actually downloaded
        downloaded_count = 0
        if files_dir.exists():
            for file_id, file_meta in linked_files.items():
                local_path = file_meta.get("local_path")
                if local_path and Path(local_path).exists():
                    downloaded_count += 1

        if downloaded_count == 0 and len(linked_files) > 0:
            print(f"\n⚠ WARNING: Course references {len(linked_files)} files (images/PDFs), but none are downloaded locally.")
            print(f"  Embedded images and file links will be BROKEN in the new course.")
            print(f"\n  To fix this, run from the SOURCE course directory:")
            print(f"    CANVAS_COURSE_ID={source_course_id} uv run python lib/tools/canvas_sync.py --pull-files")
            print(f"\n  Then re-run this tool to restore with files.")

            if not args.apply:
                print(f"\n  (Continuing with preview mode...)")
            else:
                confirm = input("\n  Continue restore WITHOUT files? [y/N]: ").strip().lower()
                if confirm != "y":
                    print("Aborted. Please download files first.")
                    return 0
        elif downloaded_count < len(linked_files):
            print(f"\n⚠ Note: {downloaded_count}/{len(linked_files)} referenced files downloaded.")
            print(f"  Some file links may be broken. Run --pull-files to download all.")
        else:
            print(f"✓ All {downloaded_count} referenced files downloaded to course/_files/")
            print(f"  (Phase 3: File upload and link rewriting not yet implemented)")
    else:
        print(f"✓ No file references detected (text-only course)")

    # Preview mode (dry-run)
    if not args.apply:
        preview_restoration(course_content)
        return 0

    # Apply mode
    print(f"\nDeploying to course {course_id}...\n")
    # What the course already has, so a re-run after a dropped connection reuses
    # what the first run made instead of making it twice (#445).
    global _TARGET
    _TARGET = _Target(token, reuse=args.resume)
    if not args.resume:
        # A new course only: never merge into one that already has content (#445).
        try:
            have = {kind: len(_TARGET._fetch(f"{base_url}/api/v1/courses/{course_id}/{kind}"))
                    for kind in ("modules", "pages", "assignments")}
        except requests.RequestException as exc:
            print(f"ERROR: couldn't check that course {course_id} is empty "
                  f"({type(exc).__name__}). Nothing was created.", file=sys.stderr)
            return 1
        if any(have.values()):
            print(f"STOPPED: course {course_id} already has {have['modules']} module(s), "
                  f"{have['pages']} page(s) and {have['assignments']} assignment(s). Nothing was "
                  f"created.\n  If a run into it stopped partway, run again with --resume to "
                  f"continue (items already there are reused). Otherwise use an empty course.",
                  file=sys.stderr)
            return 1

    # Step 1: Create assignment groups
    groups = course_content.get("assignment_groups", [])
    group_mapping = {}
    if groups:
        print("Step 1/5: Creating assignment groups...")
        group_mapping = create_assignment_groups(base_url, course_id, groups, token)
        print(f"✓ {len(group_mapping)} assignment groups ready (created or reused)\n")
    else:
        print("Step 1/5: No assignment groups to create\n")

    # Step 2: Create modules
    print("Step 2/5: Creating modules...")
    modules = course_content.get("modules", [])
    module_mapping = create_modules(base_url, course_id, modules, token)

    if not module_mapping:
        print("\nERROR: No modules created. Aborting.", file=sys.stderr)
        return 1

    print(f"✓ {len(module_mapping)} modules ready (created or reused)\n")

    # Step 3: Copy files (if any)
    linked_files = course_content.get("linked_files", {})
    file_mapping = {}
    if linked_files:
        print(f"Step 3/5: Copying {len(linked_files)} files...")
        file_mapping = copy_files(
            base_url,
            source_course_id,
            course_id,
            linked_files,
            token
        )
        print(f"✓ Copied {len(file_mapping)} files\n")
    else:
        print("Step 3/5: No files to copy\n")

    # Step 4: Create pages (with URL rewriting)
    print("Step 4/5: Creating pages and linking to modules...")
    page_mapping = create_pages_in_modules(
        base_url,
        course_id,
        files,
        module_mapping,
        token,
        file_mapping=file_mapping,
        source_course_id=source_course_id
    )
    print(f"✓ {len(page_mapping)} pages ready (created or reused)\n")

    # Step 5: Create assignments (with URL rewriting)
    print("Step 5/5: Creating assignments and New Quizzes and linking to modules...")
    assignment_mapping = create_assignments_in_modules(
        base_url,
        course_id,
        files,
        module_mapping,
        group_mapping,
        token,
        file_mapping=file_mapping,
        source_course_id=source_course_id
    )

    newquiz_mapping = create_newquizzes_in_modules(
        base_url, course_id, files, module_mapping, group_mapping, token
    )

    print(f"\n{'='*60}")
    problems = RESULTS["not_done"] or RESULTS["unsure"]
    print("✓ Restoration complete!" if not problems else "Restoration finished, with items to check:")
    print(f"{'='*60}")
    print(f"  • {len(group_mapping)} assignment groups")
    print(f"  • {len(module_mapping)} modules")
    print(f"  • {len(file_mapping)} files copied")
    print(f"  • {len(page_mapping)} pages")
    print(f"  • {len(assignment_mapping)} assignments")
    print(f"  • {len(newquiz_mapping)} New Quizzes")
    # Done / not done / unsure (#445).
    reused_total = len(RESULTS["reused"]) + len(RESULTS["updated"])
    print(f"\n  Created {len(RESULTS['created'])}; reused {reused_total} already there"
          + (f" ({len(RESULTS['updated'])} updated with this run's settings)" if RESULTS["updated"] else "")
          + ".")
    if RESULTS["reused"]:
        print("  Reused (already in the course; local changes to these weren't applied):")
        for x in RESULTS["reused"][:10]:
            print(f"    - {x}")
    if RESULTS["not_done"]:
        print(f"  Not done: {len(RESULTS['not_done'])}. Running it again creates only these "
              f"(what's already there is reused):")
        for x in RESULTS["not_done"][:10]:
            print(f"    - {x}")
    if RESULTS["unsure"]:
        print(f"  Unsure: {len(RESULTS['unsure'])}. Canvas may have these already. Check "
              f"them in Canvas before running it again:")
        for x in RESULTS["unsure"][:10]:
            print(f"    - {x}")
    print(f"\nView in Canvas: {base_url}/courses/{course_id}")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

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
    from canvas_course_guard import verify_course_access, is_sandbox_course
except ImportError:
    def load_env() -> None:
        pass
    def verify_course_access(course_id: str, token: str) -> None:
        pass
    def is_sandbox_course(course_id: str) -> bool:
        return False

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


def _post(url: str, payload: dict, token: str) -> dict:
    """POST to Canvas API with error handling.

    Returns:
        {"success": True, "data": {...}} on success
        {"success": False, "error": "...", "status_code": 400} on error
    """
    try:
        resp = requests.post(url, headers=_headers(token), json=payload, timeout=_TIMEOUT)

        if resp.status_code >= 400:
            return {
                "success": False,
                "error": resp.text[:300],
                "status_code": resp.status_code
            }

        data = resp.json() if resp.text else {}
        return {"success": True, "data": data, "status_code": resp.status_code}

    except requests.RequestException as e:
        return {"success": False, "error": str(e), "status_code": 0}


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
        print("Run canvas_sync.py --pull first to download course content", file=sys.stderr)
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

    result = _post(url, payload, token)

    if not result["success"]:
        print(f"  ✗ Failed to create module '{module_data['title']}': {result['error']}", file=sys.stderr)
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
            print(f"  ✓ Created module: {module['title']} (id: {new_module['id']})")
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

    result = _post(url, payload, token)

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

    result = _post(url, payload, token)

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
    token: str
) -> dict:
    """Create all pages and link them to modules.

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
        print(f"  ✓ Created page: {page_meta['title']}")

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

    print("\n" + "="*60)
    print("Re-run with --apply to create these items")
    print("="*60 + "\n")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy local course content to new Canvas course (Phase 1 MVP: modules + pages)",
    )
    parser.add_argument("--apply", action="store_true",
                       help="Actually create content (default is dry-run preview)")

    args = parser.parse_args()

    # Load configuration
    base_url, course_id, token = _load_config()
    if not base_url or not course_id or not token:
        return 1

    # Safety check
    try:
        verify_course_access(course_id, token)
    except Exception as e:
        print(f"ERROR: Cannot access course {course_id}: {e}", file=sys.stderr)
        return 1

    # Warn if production course
    if not is_sandbox_course(course_id):
        print(f"\n⚠ WARNING: Target is PRODUCTION course {course_id}")
        confirm = input("Continue? Type 'yes' to proceed: ")
        if confirm.lower() != "yes":
            print("Aborted.")
            return 0

    # Load course content
    print(f"Loading course content from .canvas/index.json...")
    course_content = load_course_content()

    if not course_content:
        return 1

    source_course_id = course_content.get("course_id", "unknown")
    module_count = len(course_content.get("modules", []))
    files = course_content.get("files", {})
    page_count = len([f for f in files.values() if f.get("type") == "Page"])

    print(f"✓ Loaded {module_count} modules, {page_count} pages from course {source_course_id}")

    # Preview mode (dry-run)
    if not args.apply:
        preview_restoration(course_content)
        return 0

    # Apply mode
    print(f"\nDeploying to course {course_id}...\n")

    # Phase 1: Create modules
    print("Step 1/2: Creating modules...")
    modules = course_content.get("modules", [])
    module_mapping = create_modules(base_url, course_id, modules, token)

    if not module_mapping:
        print("\nERROR: No modules created. Aborting.", file=sys.stderr)
        return 1

    print(f"✓ Created {len(module_mapping)} modules\n")

    # Phase 2: Create pages
    print("Step 2/2: Creating pages and linking to modules...")
    page_mapping = create_pages_in_modules(
        base_url,
        course_id,
        files,
        module_mapping,
        token
    )

    print(f"\n{'='*60}")
    print("✓ Restoration complete!")
    print(f"{'='*60}")
    print(f"  • {len(module_mapping)} modules created")
    print(f"  • {len(page_mapping)} pages created")
    print(f"\nView in Canvas: {base_url}/courses/{course_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

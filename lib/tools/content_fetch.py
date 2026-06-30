#!/usr/bin/env python3
"""
content_fetch.py — Feature 1: Differential Content Access for NGAI

Fetches course content (pages, modules) with optional solution filtering for
student-view mode. Designed for NGAI peer agent workflows where answer keys
must be excluded.

Usage:
    uv run python lib/tools/content_fetch.py \\
        --page-url my-page \\
        --course-id 12345 \\
        --access-mode student_view \\
        --json

    uv run python lib/tools/content_fetch.py \\
        --module-id 67890 \\
        --course-id 12345 \\
        --access-mode instructor_view \\
        --output content.json

Access Modes:
    instructor_view (default) — Full content including solutions/answer keys
    student_view             — Filters out solution markers and answer keys

Solution Filtering Heuristics (student_view only):
    1. HTML comments: <!-- SOLUTION -->...</

--SOLUTION -->
    2. Data attributes: <div data-solution="true">...</div>
    3. CSS classes: <div class="solution">...</div>
    4. Heading markers: Content after "## Solution" or "## Answer Key" headings

Exit codes:
    0 = success
    1 = content not found
    2 = configuration error

NGAI Integration (Feature 1):
    Part of Sprint 1 Phase 1 MVP. Peer agents fetch course content in student_view
    mode to ensure they don't see answer keys when providing peer feedback.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    pass

from __toolbox_version__ import __version__

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
CANVAS_BASE_URL = ("https://" + _raw) if _raw and not _raw.startswith("http") else _raw
DEFAULT_COURSE_ID = os.environ.get("CANVAS_COURSE_ID", "")


def _headers():
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _check_env():
    if not CANVAS_API_TOKEN or not CANVAS_BASE_URL:
        print("ERROR: CANVAS_API_TOKEN and CANVAS_BASE_URL required in .env", file=sys.stderr)
        sys.exit(2)


def fetch_page(course_id: str, page_url: str) -> Optional[dict]:
    """
    Fetch a Canvas page by URL.

    Returns dict with:
    - title
    - body (HTML)
    - url
    - page_id
    - published
    """
    url = f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/pages/{page_url}"
    r = requests.get(url, headers=_headers(), timeout=30)

    if r.status_code >= 400:
        print(f"ERROR: HTTP {r.status_code} fetching page {page_url}: {r.text[:200]}", file=sys.stderr)
        return None

    return r.json()


def fetch_module(course_id: str, module_id: str) -> Optional[dict]:
    """
    Fetch a Canvas module with its items.

    Returns dict with:
    - name
    - position
    - published
    - items (list of module items with content)
    """
    url = f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/modules/{module_id}"
    r = requests.get(url, headers=_headers(), params={"include[]": "items"}, timeout=30)

    if r.status_code >= 400:
        print(f"ERROR: HTTP {r.status_code} fetching module {module_id}: {r.text[:200]}", file=sys.stderr)
        return None

    module = r.json()

    # For each Page item, fetch its body
    for item in module.get("items", []):
        if item.get("type") == "Page" and item.get("page_url"):
            page_data = fetch_page(course_id, item["page_url"])
            if page_data:
                item["page_content"] = {
                    "title": page_data.get("title"),
                    "body": page_data.get("body"),
                    "url": page_data.get("url")
                }

    return module


def filter_solution_markers(html: str) -> tuple[str, list[str]]:
    """
    Remove solution content from HTML using heuristic markers.

    Returns: (filtered_html, list_of_removed_sections)

    Heuristics:
    1. HTML comments: <!-- SOLUTION -->...<!-- /SOLUTION -->
    2. Data attributes: <div data-solution="true">...</div>
    3. CSS classes: <div class="solution">...</div> or <section class="answer-key">...</section>
    4. Heading-delimited: Content after <h2>Solution</h2> or <h2>Answer Key</h2>
    """
    if not html or not html.strip():
        return html, []

    soup = BeautifulSoup(html, "html.parser")
    removed_sections = []

    # 1. Remove HTML comment blocks: <!-- SOLUTION -->...<!-- /SOLUTION -->
    solution_pattern = re.compile(r'<!-- *SOLUTION *-->.*?<!-- */SOLUTION *-->', re.DOTALL | re.IGNORECASE)
    matches = solution_pattern.findall(str(soup))
    if matches:
        removed_sections.extend([f"HTML comment block ({len(m)} chars)" for m in matches])
        html = solution_pattern.sub('', str(soup))
        soup = BeautifulSoup(html, "html.parser")

    # 2. Remove elements with data-solution attribute
    solution_elements = soup.find_all(attrs={"data-solution": True})
    for elem in solution_elements:
        removed_sections.append(f"data-solution element: <{elem.name}>")
        elem.decompose()

    # 3. Remove elements with solution/answer-key classes
    solution_classes = soup.find_all(class_=lambda c: c and any(
        marker in str(c).lower() for marker in ["solution", "answer-key", "answerkey", "answer_key"]
    ))
    for elem in solution_classes:
        removed_sections.append(f"solution class element: <{elem.name} class='{elem.get('class')}'>")
        elem.decompose()

    # 4. Remove content after "Solution" or "Answer Key" headings
    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        # Skip if heading was already removed as part of another section
        if not heading.parent:
            continue

        text = heading.get_text().strip().lower()
        if any(marker in text for marker in ["solution", "answer key", "answer", "answers"]):
            # Remove this heading and all following siblings until next heading of same/higher level
            removed_sections.append(f"heading-delimited section: {heading.get_text().strip()}")
            # Save heading level before decomposing
            heading_level = int(heading.name[1])

            # Collect siblings to remove
            to_remove = [heading]
            current = heading.find_next_sibling()
            while current:
                # Stop if we hit another heading of same or higher level
                if current.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    next_level = int(current.name[1])
                    if next_level <= heading_level:
                        break
                to_remove.append(current)
                current = current.find_next_sibling()

            # Now remove all collected elements
            for elem in to_remove:
                elem.decompose()

    return str(soup), removed_sections


def main():
    ap = argparse.ArgumentParser(
        description="Fetch Canvas course content with optional solution filtering (NGAI Feature 1)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch page in instructor view (full content)
  uv run python lib/tools/content_fetch.py --page-url my-page --course-id 12345 --access-mode instructor_view

  # Fetch page in student view (solutions filtered)
  uv run python lib/tools/content_fetch.py --page-url my-page --course-id 12345 --access-mode student_view --json

  # Fetch module with all page content (student view)
  uv run python lib/tools/content_fetch.py --module-id 67890 --course-id 12345 --access-mode student_view --json

Exit codes:
  0 = success
  1 = content not found
  2 = configuration error

Access Modes:
  instructor_view — Full content (default)
  student_view    — Filters solution markers for NGAI peer agents
"""
    )

    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--page-url", default=None,
                   help="Canvas page URL to fetch (e.g., 'my-page-slug')")
    ap.add_argument("--module-id", default=None,
                   help="Canvas module ID to fetch with all page content")
    ap.add_argument("--course-id", default=None,
                   help="Canvas course ID (default: env CANVAS_COURSE_ID)")
    ap.add_argument("--access-mode", choices=["student_view", "instructor_view"],
                   default="instructor_view",
                   help="Access mode: student_view (filters solutions) or instructor_view (full content)")
    ap.add_argument("--json", action="store_true", dest="emit_json",
                   help="Output structured JSON")
    ap.add_argument("--output", default=None, metavar="PATH",
                   help="Write output to file instead of stdout")

    args = ap.parse_args()

    _check_env()

    course_id = args.course_id or DEFAULT_COURSE_ID
    if not course_id:
        print("ERROR: --course-id required or set CANVAS_COURSE_ID in .env", file=sys.stderr)
        sys.exit(2)

    if not args.page_url and not args.module_id:
        print("ERROR: --page-url or --module-id required", file=sys.stderr)
        sys.exit(2)

    if args.page_url and args.module_id:
        print("ERROR: specify only one of --page-url or --module-id", file=sys.stderr)
        sys.exit(2)

    # Fetch content
    if args.page_url:
        content = fetch_page(course_id, args.page_url)
        content_type = "page"
    else:
        content = fetch_module(course_id, args.module_id)
        content_type = "module"

    if not content:
        print(f"Content not found: {args.page_url or args.module_id}", file=sys.stderr)
        sys.exit(1)

    # Apply solution filtering in student_view mode
    removed_sections = []
    if args.access_mode == "student_view":
        if content_type == "page":
            if content.get("body"):
                filtered_body, removed = filter_solution_markers(content["body"])
                content["body"] = filtered_body
                content["filtered"] = True
                content["removed_sections"] = removed
                removed_sections = removed
        elif content_type == "module":
            for item in content.get("items", []):
                if "page_content" in item and item["page_content"].get("body"):
                    filtered_body, removed = filter_solution_markers(item["page_content"]["body"])
                    item["page_content"]["body"] = filtered_body
                    item["page_content"]["filtered"] = True
                    item["page_content"]["removed_sections"] = removed
                    removed_sections.extend(removed)

    # Build output
    output = {
        "tool": "content_fetch",
        "tool_version": __version__,
        "course_id": int(course_id),
        "content_type": content_type,
        "access_mode": args.access_mode,
        "content": content
    }

    if args.access_mode == "student_view":
        output["solution_filtering"] = {
            "enabled": True,
            "sections_removed": len(removed_sections),
            "details": removed_sections[:10]  # Cap at 10 for readability
        }

    if args.emit_json:
        body = json.dumps(output, indent=2, ensure_ascii=False)
    else:
        # Human-readable output
        if content_type == "page":
            body = f"Page: {content.get('title')}\n"
            body += f"URL: {content.get('url')}\n"
            body += f"Access mode: {args.access_mode}\n"
            if args.access_mode == "student_view":
                body += f"Filtered sections: {len(removed_sections)}\n"
            body += f"\nContent:\n{content.get('body', '')}"
        else:
            body = f"Module: {content.get('name')}\n"
            body += f"Items: {len(content.get('items', []))}\n"
            body += f"Access mode: {args.access_mode}\n"
            if args.access_mode == "student_view":
                body += f"Filtered sections: {len(removed_sections)}\n"
            body += "\n" + json.dumps(content, indent=2)

    if args.output:
        Path(args.output).write_text(body, encoding="utf-8")
        print(f"✅ Content written to {args.output}", file=sys.stderr)
    else:
        print(body)

    return 0


if __name__ == "__main__":
    sys.exit(main())

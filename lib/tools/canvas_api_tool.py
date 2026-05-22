"""
canvas_api_tool.py

Local tool implementations for the Canvas Course Expert Agent.
Canvas API operations are handled by the MCP server (see docker-compose.yml).

Local tools:
  - parse_course_export   — extracts and parses the Canvas IMSCC ZIP
  - analyze_cognitive_load — audits course structure against CL rules
  - read_local_file        — reads extracted course files
  - write_local_file       — writes/backups extracted course files
  - fetch_byui_resources   — scrapes teach.byui.edu or returns embedded standards
  - request_confirmation   — interactive confirmation gate before Canvas MCP writes

Usage:
    python canvas_api_tool.py --audit /path/to/export.imscc
    python canvas_api_tool.py --test
"""

import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import anthropic
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:3000/mcp")
CANVAS_COURSE_ID = os.environ.get("CANVAS_COURSE_ID", "")
CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
# Normalize the base URL: the .env convention is scheme-less; requests needs a
# scheme. Matches canvas_sync.py (see ITM327 2026-05-21 scheme bug).
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url


# ---------------------------------------------------------------------------
# Tool: parse_course_export
# ---------------------------------------------------------------------------

def parse_course_export(zip_path: str, extract_dir: Optional[str] = None) -> dict:
    """
    Extracts and parses a Canvas IMSCC course export ZIP.
    Returns a structured course_data dict.
    """
    zip_path = Path(zip_path)
    if not zip_path.exists():
        return {"error": f"File not found: {zip_path}"}

    if extract_dir is None:
        extract_dir = tempfile.mkdtemp(prefix="canvas_extract_")
    else:
        Path(extract_dir).mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    manifest_path = Path(extract_dir) / "imsmanifest.xml"
    if not manifest_path.exists():
        return {
            "error": "format_error",
            "message": (
                "imsmanifest.xml not found. This appears to be a Canvas-native export, "
                "not an IMSCC Common Cartridge. Re-export via: "
                "Course Settings → Export Course Content → Common Cartridge."
            )
        }

    modules = _parse_modules(extract_dir)
    pages = _parse_pages(extract_dir)
    assignments = _parse_assignments(extract_dir)
    quizzes = _parse_quizzes(extract_dir)
    discussions = _parse_discussions(extract_dir)
    settings = _parse_course_settings(extract_dir)

    return {
        "extract_dir": str(extract_dir),
        "modules": modules,
        "pages": pages,
        "assignments": assignments,
        "quizzes": quizzes,
        "discussions": discussions,
        "settings": settings,
        "stats": {
            "module_count": len(modules),
            "page_count": len(pages),
            "assignment_count": len(assignments),
            "quiz_count": len(quizzes),
            "discussion_count": len(discussions),
        }
    }


def _parse_modules(extract_dir: str) -> list[dict]:
    module_meta = Path(extract_dir) / "course_settings" / "module_meta.xml"
    if not module_meta.exists():
        return []
    tree = ET.parse(module_meta)
    root = tree.getroot()
    # Canvas XML uses a namespace — extract it so findall works
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    modules = []
    for mod in root.findall(f"{ns}module"):
        items = []
        for item in mod.findall(f".//{ns}item"):
            items.append({
                "id": item.get("identifier", ""),
                "identifierref": item.findtext(f"{ns}identifierref", ""),
                "title": item.findtext(f"{ns}title", ""),
                "type": item.findtext(f"{ns}content_type", ""),
                "indent": int(item.findtext(f"{ns}indent", "0")),
                "published": item.findtext(f"{ns}workflow_state", "") not in ("unpublished", "deleted"),
            })
        modules.append({
            "id": mod.get("identifier", ""),
            "title": mod.findtext(f"{ns}title", ""),
            "position": int(mod.findtext(f"{ns}position", "0")),
            "published": mod.findtext(f"{ns}workflow_state", "") not in ("unpublished", "deleted"),
            "items": items,
            "item_count": len(items),
        })
    return sorted(modules, key=lambda m: m["position"])


def _parse_pages(extract_dir: str) -> list[dict]:
    pages = []
    wiki_dir = Path(extract_dir) / "wiki_content"
    if not wiki_dir.exists():
        return pages
    for html_file in wiki_dir.glob("*.html"):
        content = html_file.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "lxml")
        title = soup.find("title")
        body_text = soup.get_text(separator=" ", strip=True)
        pages.append({
            "path": str(html_file),
            "filename": html_file.name,
            "title": title.get_text() if title else html_file.stem,
            "word_count": len(body_text.split()),
            "content_preview": body_text[:200],
        })
    return pages


def _parse_assignments(extract_dir: str) -> list[dict]:
    assignments = []
    for xml_file in Path(extract_dir).rglob("*/assignment.xml"):
        tree = ET.parse(xml_file)
        root = tree.getroot()
        assignments.append({
            "path": str(xml_file),
            "title": root.findtext("title", ""),
            "description_length": len(root.findtext("body", "") or ""),
            "points": root.findtext("points_possible", ""),
            "due_at": root.findtext("due_at", ""),
        })
    return assignments


def _parse_quizzes(extract_dir: str) -> list[dict]:
    quizzes = []
    for xml_file in Path(extract_dir).rglob("*/assessment_meta.xml"):
        tree = ET.parse(xml_file)
        root = tree.getroot()
        quizzes.append({
            "path": str(xml_file),
            "title": root.findtext("title", ""),
            "quiz_type": root.findtext("quiz_type", ""),
            "points": root.findtext("points_possible", ""),
            "due_at": root.findtext("due_at", ""),
        })
    return quizzes


def _parse_discussions(extract_dir: str) -> list[dict]:
    discussions = []
    for xml_file in Path(extract_dir).rglob("*/topic.xml"):
        tree = ET.parse(xml_file)
        root = tree.getroot()
        discussions.append({
            "path": str(xml_file),
            "title": root.findtext("title", ""),
            "type": root.findtext("discussion_type", ""),
        })
    return discussions


def _parse_course_settings(extract_dir: str) -> dict:
    settings_path = Path(extract_dir) / "course_settings" / "course_settings.xml"
    if not settings_path.exists():
        return {}
    tree = ET.parse(settings_path)
    root = tree.getroot()
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    return {
        "title": root.findtext(f"{ns}title", ""),
        "course_code": root.findtext(f"{ns}course_code", ""),
        "start_at": root.findtext(f"{ns}start_at", ""),
        "conclude_at": root.findtext(f"{ns}conclude_at", ""),
    }


# ---------------------------------------------------------------------------
# Tool: request_confirmation
# ---------------------------------------------------------------------------

def request_confirmation(
    operation_summary: str,
    resource_type: str,
    before: str,
    after: str,
) -> dict:
    """
    Interactive confirmation gate. Prints a before/after preview and
    waits for instructor input before any Canvas MCP write proceeds.
    Returns {approved: bool}.
    """
    print("\n" + "─" * 60)
    print("PROPOSED CANVAS CHANGE")
    print(f"  Operation : {operation_summary}")
    print(f"  Resource  : {resource_type}")
    print(f"  Before    : {before}")
    print(f"  After     : {after}")
    print("─" * 60)
    answer = input("Approve this change? (yes/no): ").strip().lower()
    approved = answer in ("yes", "y")
    if not approved:
        print("  → Change rejected.")
    return {"approved": approved}


# ---------------------------------------------------------------------------
# Tool: read_local_file
# ---------------------------------------------------------------------------

def read_local_file(file_path: str) -> str:
    """Reads a file from the extracted course directory."""
    path = Path(file_path)
    if not path.exists():
        return f"ERROR: File not found: {file_path}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tool: write_local_file
# ---------------------------------------------------------------------------

def write_local_file(file_path: str, content: str) -> dict:
    """
    Writes content to a local file, creating a .bak backup first.
    Always call this before the corresponding Canvas MCP write tool.
    """
    path = Path(file_path)
    backup_path = path.with_suffix(path.suffix + ".bak")

    if path.exists():
        shutil.copy2(path, backup_path)

    path.write_text(content, encoding="utf-8")
    return {
        "success": True,
        "path": str(path),
        "backup": str(backup_path) if backup_path.exists() else None,
        "bytes_written": len(content.encode("utf-8")),
    }


# ---------------------------------------------------------------------------
# Persistent Canvas index (.canvas/index.json)
# ---------------------------------------------------------------------------

_INDEX_PATH = Path(".canvas/index.json")

def _load_index() -> dict:
    """Load the persistent Canvas resource index for this course."""
    if _INDEX_PATH.exists():
        return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    return {
        "course_id": CANVAS_COURSE_ID or None,
        "base_url": os.environ.get("CANVAS_BASE_URL", ""),
        "last_audit": None,
        "last_audit_score": None,
        "modules": {},
        "pages": {},
        "assignments": {},
        "change_ledger": {},
    }


def _save_index(index: dict) -> None:
    """Persist the Canvas resource index."""
    _INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INDEX_PATH.write_text(json.dumps(index, indent=2, default=str), encoding="utf-8")


def update_index_after_audit(course_data: dict, audit_score: int) -> dict:
    """
    Update the persistent index with module structure from a fresh audit.
    Call after parse_course_export + analyze_cognitive_load.
    Preserves existing Canvas IDs — only updates structural metadata.
    """
    from datetime import datetime, timezone
    index = _load_index()
    index["last_audit"] = datetime.now(timezone.utc).isoformat()
    index["last_audit_score"] = audit_score

    for mod in course_data.get("modules", []):
        title = mod["title"]
        existing = index["modules"].get(title, {})
        index["modules"][title] = {
            "canvas_id": existing.get("canvas_id"),  # preserve if known
            "position": mod["position"],
            "published": mod["published"],
            "item_count": mod["item_count"],
        }

    _save_index(index)
    return {"updated": True, "index_path": str(_INDEX_PATH), "score": audit_score}


def record_canvas_write(
    change_id: str,
    rule_id: str,
    resource_type: str,
    canvas_id: int,
    local_backup: Optional[str],
    status: str = "applied",
) -> dict:
    """
    Record a completed Canvas write in the persistent index.
    Call after every successful canvas_api write operation.
    """
    from datetime import datetime, timezone
    index = _load_index()
    index["change_ledger"][change_id] = {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "rule_id": rule_id,
        "resource_type": resource_type,
        "canvas_id": canvas_id,
        "local_backup": local_backup,
        "status": status,
    }
    _save_index(index)
    return {"recorded": True, "change_id": change_id, "status": status}


def cache_page_slug(title: str, canvas_id: int, slug: str, published: bool) -> dict:
    """
    Store a page slug in the index after create_page returns.
    The slug is required for module item insertion (type=Page uses page_url, not content_id).
    """
    index = _load_index()
    index["pages"][slug] = {
        "canvas_id": canvas_id,
        "title": title,
        "published": published,
    }
    _save_index(index)
    return {"cached": True, "slug": slug, "canvas_id": canvas_id}


def cache_module_id(title: str, canvas_id: int) -> dict:
    """Store a Canvas module ID after it is fetched or created."""
    index = _load_index()
    if title not in index["modules"]:
        index["modules"][title] = {}
    index["modules"][title]["canvas_id"] = canvas_id
    _save_index(index)
    return {"cached": True, "title": title, "canvas_id": canvas_id}


# ---------------------------------------------------------------------------
# Canvas API — Python-direct mode (requires CANVAS_API_TOKEN + CANVAS_BASE_URL)
# ---------------------------------------------------------------------------
#
# Decision rule:
#   - If CANVAS_API_TOKEN is set → use these functions for reads AND writes
#   - If not → MCP handles reads; writes are blocked until token is provided
#
# All write functions return only {success, canvas_id/slug/module_item_id, status_code}
# — never the full Canvas response body, to protect context window budget.
# All read functions return minimal fields; full response bodies are discarded.

def canvas_available() -> dict:
    """Check whether Python-direct Canvas API mode is available."""
    missing = [v for v in ("CANVAS_API_TOKEN", "CANVAS_BASE_URL", "CANVAS_COURSE_ID") if not os.environ.get(v)]
    if missing:
        return {
            "available": False,
            "reason": f"Missing .env variables: {', '.join(missing)}",
            "recommendation": "Copy .env.example to .env and fill in CANVAS_API_TOKEN, CANVAS_BASE_URL, and CANVAS_COURSE_ID.",
        }
    return {"available": True, "course_id": CANVAS_COURSE_ID, "base_url": CANVAS_BASE_URL}


def _canvas_headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}", "Content-Type": "application/json"}


def _canvas_request(method: str, endpoint: str, payload: Optional[dict] = None) -> dict:
    """
    Generic Canvas API request. Endpoint is relative (e.g. '/courses/123/pages').
    Returns full JSON for GET, compact summary for POST/PUT/DELETE.
    Raises on network errors; returns {error, status_code} on API errors.
    """
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    resp = requests.request(method, url, headers=_canvas_headers(), json=payload, timeout=20)
    if resp.status_code >= 400:
        return {"error": resp.text[:300], "status_code": resp.status_code}
    if method.upper() == "GET":
        return resp.json()
    # For writes: return only what the agent needs — discard the rest
    body = resp.json() if resp.text else {}
    compact = {"success": True, "status_code": resp.status_code}
    for field in ("id", "url", "page_id", "module_item_id", "slug"):
        if field in body:
            compact[field] = body[field]
    # Normalize: Canvas returns page slug in 'url' field; numeric id maps to canvas_id
    if "url" in compact and "slug" not in compact:
        compact["slug"] = compact.pop("url")
    if "id" in compact and "canvas_id" not in compact:
        compact["canvas_id"] = compact.pop("id")
    return compact


def fetch_modules() -> dict:
    """
    Fetch all modules for the course. Caches canvas_id for each module in the index.
    Returns minimal list — title, canvas_id, published, item_count only.
    """
    if not CANVAS_API_TOKEN:
        return {"error": "CANVAS_API_TOKEN not set — use MCP or add token to .env"}
    raw = _canvas_request("GET", f"/courses/{CANVAS_COURSE_ID}/modules?per_page=50&include[]=items")
    if "error" in raw:
        return raw
    index = _load_index()
    modules = []
    for m in raw:
        title = m.get("name", "")
        canvas_id = m.get("id")
        existing = index["modules"].get(title, {})
        index["modules"][title] = {**existing, "canvas_id": canvas_id, "published": m.get("published", False)}
        modules.append({
            "title": title,
            "canvas_id": canvas_id,
            "published": m.get("published", False),
            "item_count": m.get("items_count", 0),
        })
    _save_index(index)
    return {"modules": modules, "count": len(modules), "cached": True}


def fetch_module_items(module_id: int) -> dict:
    """
    Fetch items for a single module. Returns minimal list — title, type, canvas_id, position, published.
    Use this for targeted lookups; avoid calling for all modules in one session.
    """
    if not CANVAS_API_TOKEN:
        return {"error": "CANVAS_API_TOKEN not set"}
    raw = _canvas_request("GET", f"/courses/{CANVAS_COURSE_ID}/modules/{module_id}/items?per_page=50")
    if "error" in raw:
        return raw
    items = [
        {
            "title": i.get("title"),
            "type": i.get("type"),
            "canvas_id": i.get("id"),
            "position": i.get("position"),
            "published": i.get("published", False),
        }
        for i in raw
        if i.get("type") != "ContextModuleSubHeader"
    ]
    return {"items": items, "module_id": module_id, "count": len(items)}


def create_page(title: str, body_html: str, published: bool = False) -> dict:
    """
    Create a new Canvas wiki page. Returns {success, canvas_id, slug, status_code}.
    Always call cache_page_slug() with the returned slug before insert_module_item().
    """
    if not CANVAS_API_TOKEN:
        return {"error": "CANVAS_API_TOKEN not set"}
    result = _canvas_request("POST", f"/courses/{CANVAS_COURSE_ID}/pages", {
        "wiki_page": {"title": title, "body": body_html, "published": published}
    })
    if "error" in result:
        return result
    # Auto-cache the slug so insert_module_item() can use it immediately
    if result.get("slug") and result.get("id"):
        cache_page_slug(title, result["id"], result["slug"], published)
    return {**result, "canvas_id": result.get("id")}


def update_page(slug: str, title: str, body_html: str, published: bool = True) -> dict:
    """
    Update an existing Canvas wiki page by slug.
    Returns {success, slug, status_code}.
    """
    if not CANVAS_API_TOKEN:
        return {"error": "CANVAS_API_TOKEN not set"}
    return _canvas_request("PUT", f"/courses/{CANVAS_COURSE_ID}/pages/{slug}", {
        "wiki_page": {"title": title, "body": body_html, "published": published}
    })


def insert_module_item(
    module_id: int,
    title: str,
    page_url: str,
    position: int = 1,
    published: bool = True,
) -> dict:
    """
    Insert a wiki page as a module item. Requires page_url (slug), NOT the numeric page_id.
    Returns {success, module_item_id, status_code}.
    """
    if not CANVAS_API_TOKEN:
        return {"error": "CANVAS_API_TOKEN not set"}
    result = _canvas_request("POST", f"/courses/{CANVAS_COURSE_ID}/modules/{module_id}/items", {
        "module_item": {
            "title": title,
            "type": "Page",
            "page_url": page_url,
            "position": position,
            "published": published,
        }
    })
    if result.get("success") and result.get("id"):
        result["module_item_id"] = result.pop("id", None)
    return result


def update_module_item(module_id: int, item_id: int, title: str, published: Optional[bool] = None) -> dict:
    """
    Update a module item's title and/or published state.
    Required for renames — Canvas does not cascade page title changes to module items.
    Returns {success, status_code}.
    """
    if not CANVAS_API_TOKEN:
        return {"error": "CANVAS_API_TOKEN not set"}
    payload: dict = {"module_item": {"title": title}}
    if published is not None:
        payload["module_item"]["published"] = published
    return _canvas_request("PUT", f"/courses/{CANVAS_COURSE_ID}/modules/{module_id}/items/{item_id}", payload)


# ---------------------------------------------------------------------------
# Tool: analyze_cognitive_load
# ---------------------------------------------------------------------------

def analyze_cognitive_load(
    course_data: dict,
    rules_override: Optional[list[str]] = None,
) -> dict:
    """
    Runs the cognitive load audit rules against parsed course_data.
    Returns a scored report with prioritized issues.
    """
    config_path = Path(__file__).parent.parent / "agents" / "canvas_course_expert.json"
    with open(config_path) as f:
        config = json.load(f)

    rules = config["primary_data"]["audit_rules"]
    skip_rules = set(rules_override or [])
    issues = []

    modules = course_data.get("modules", [])
    pages = course_data.get("pages", [])

    # Build set of page titles linked from any module item
    linked_page_titles: set[str] = set()
    for mod in modules:
        for item in mod.get("items", []):
            linked_page_titles.add(item.get("title", "").strip().lower())

    # Student-facing modules only: unpublished modules are instructor-only
    # and should not be audited for CL-002, CL-007, CL-008
    student_modules = [m for m in modules if m.get("published", False)]

    for rule in rules:
        rule_id = rule["rule_id"]
        if rule_id in skip_rules:
            continue

        if rule_id == "CL-001":
            # Flag all modules (instructor modules can still have too many items)
            for mod in modules:
                if mod["item_count"] > rule["threshold"]:
                    issues.append(_issue(rule, mod["title"], None,
                        f"Module '{mod['title']}' has {mod['item_count']} items (threshold: {rule['threshold']})"))

        elif rule_id == "CL-002":
            # Only student-facing modules need overview pages
            for mod in student_modules:
                if not mod["items"]:
                    continue
                first = mod["items"][0]
                title_lower = first.get("title", "").lower()
                if not any(kw in title_lower for kw in ("overview", "intro", "welcome", "start here")):
                    issues.append(_issue(rule, mod["title"], first.get("title"),
                        f"Module '{mod['title']}' first item is '{first.get('title')}', not an overview/intro page"))

        elif rule_id == "CL-003":
            patterns = [
                re.compile(r"^week\s*\d+", re.IGNORECASE),
                re.compile(r"^unit\s*\d+", re.IGNORECASE),
                re.compile(r"^module\s*\d+", re.IGNORECASE),
                re.compile(r"^sprint\s*\d+", re.IGNORECASE),
                re.compile(r"^\d+[\.\-:]"),
            ]
            named = [m for m in student_modules if m["title"] and not m["title"].lower().startswith("import")]
            if len(named) > 1:
                matched_pattern = None
                inconsistent = []
                for mod in named:
                    match = any(p.match(mod["title"]) for p in patterns)
                    if matched_pattern is None:
                        matched_pattern = match
                    elif match != matched_pattern:
                        inconsistent.append(mod["title"])
                if inconsistent:
                    issues.append(_issue(rule, None, None,
                        f"Inconsistent module naming. Examples: {inconsistent[:3]}"))

        elif rule_id == "CL-005":
            for page in pages:
                if page["title"].strip().lower() not in linked_page_titles:
                    issues.append(_issue(rule, None, page["title"],
                        f"Page '{page['title']}' ({page['filename']}) is not linked in any module"))

        elif rule_id == "CL-007":
            # Only student-facing modules need Prove It assessments
            for mod in student_modules:
                item_types = [i.get("type", "") for i in mod.get("items", [])]
                has_assessment = any(
                    t in item_types for t in ("Assignment", "Quiz", "Quizzes::Quiz")
                )
                if not has_assessment:
                    issues.append(_issue(rule, mod["title"], None,
                        f"Module '{mod['title']}' has no assignment or quiz (Prove It missing)"))

        elif rule_id == "CL-008":
            # Only student-facing modules need Teach One Another discussions
            for mod in student_modules:
                item_types = [i.get("type", "") for i in mod.get("items", [])]
                if "DiscussionTopic" not in item_types and "Discussion" not in item_types:
                    issues.append(_issue(rule, mod["title"], None,
                        f"Module '{mod['title']}' has no discussion (Teach One Another missing)"))

        elif rule_id == "CL-009":
            for page in pages:
                if page["word_count"] > 1500:
                    issues.append(_issue(rule, None, page["title"],
                        f"Page '{page['title']}' has {page['word_count']} words (threshold: 1500)"))

        elif rule_id == "CL-010":
            # Published modules with unpublished items create broken navigation for students
            for mod in student_modules:
                unpublished_items = [
                    i for i in mod.get("items", [])
                    if not i.get("published", True)
                    and i.get("type") not in ("ContextModuleSubHeader",)
                ]
                for item in unpublished_items:
                    issues.append(_issue(rule, mod["title"], item.get("title"),
                        f"Published module '{mod['title']}' contains unpublished item '{item.get('title')}' — students will see a broken link"))

    deductions = {"critical": 15, "warning": 7, "info": 2}
    score = max(0, 100 - sum(deductions.get(i["severity"], 0) for i in issues))

    load_order = {"extraneous": 0, "intrinsic": 1, "germane": 2}
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda x: (severity_order.get(x["severity"], 9), load_order.get(x["load_type"], 9)))

    critical = [i for i in issues if i["severity"] == "critical"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    infos    = [i for i in issues if i["severity"] == "info"]

    return {
        "score": score,
        "grade": "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F",
        "issues": issues,
        "summary": (
            f"Course scored {score}/100. "
            f"{len(critical)} critical, {len(warnings)} warnings, {len(infos)} info. "
            f"{'Immediate attention needed.' if critical else 'No critical issues.'}"
        ),
        "critical_count": len(critical),
        "warning_count": len(warnings),
        "info_count": len(infos),
    }


def _issue(rule: dict, module: Optional[str], item: Optional[str], description: str) -> dict:
    return {
        "rule_id": rule["rule_id"],
        "load_type": rule["load_type"],
        "hattie_phase": rule.get("hattie_phase", "surface"),
        "severity": rule["severity"],
        "module": module,
        "item": item,
        "description": description,
        "recommendation": rule["recommendation"],
    }


# ---------------------------------------------------------------------------
# Tool: fetch_byui_resources
# ---------------------------------------------------------------------------

def fetch_byui_resources(topic: str) -> str:
    """
    Fetches relevant content from teach.byui.edu.
    Falls back to embedded byui_standards if the page requires login.
    """
    topic_url_map = {
        "module structure": "https://teach.byui.edu/course-design/module-structure",
        "teach one another": "https://teach.byui.edu/teach-one-another",
        "prove it": "https://teach.byui.edu/prove-it-assessments",
        "cognitive load": "https://teach.byui.edu/reducing-cognitive-load",
        "course navigation": "https://teach.byui.edu/canvas/course-navigation",
        "competency alignment": "https://teach.byui.edu/competency-based-learning",
    }

    url = None
    topic_lower = topic.lower()
    for key, mapped_url in topic_url_map.items():
        if any(word in topic_lower for word in key.split()):
            url = mapped_url
            break

    if url:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                for tag in soup(["nav", "footer", "script", "style", "header"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                return f"[Source: {url}]\n\n{text[:3000]}"
        except Exception:
            pass

    config_path = Path(__file__).parent.parent / "agents" / "canvas_course_expert.json"
    with open(config_path) as f:
        config = json.load(f)

    standards = config["primary_data"]["byui_standards"]
    matching = [
        s for s in standards
        if any(word in s["key"] for word in topic_lower.replace(" ", "_").split("_"))
    ] or standards

    result = "[Source: Embedded BYUI Knowledge Base (teach.byui.edu unavailable or login required)]\n\n"
    for s in matching:
        result += f"**{s['key']}** ({s['source']})\n{s['standard']}\n\n"
    return result.strip()


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

# Canvas MCP write tool prefixes — any tool starting with these requires
# request_confirmation to have been called first.
_WRITE_PREFIXES = ("create_", "update_", "delete_", "publish_", "unpublish_")

def run_agent(zip_path: str, dry_run: bool = False):
    """
    Main agent loop using the Anthropic API with the Canvas MCP server.
    """
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    config_path = Path(__file__).parent.parent / "agents" / "canvas_course_expert.json"
    with open(config_path) as f:
        config = json.load(f)

    llm_cfg = config["implementation"]["llm_agent"]
    system_prompt = llm_cfg["system_prompt"]

    # Determine operating mode: Python-direct or MCP-fallback
    creds = canvas_available()
    if creds["available"]:
        system_prompt += (
            f"\n\nCANVAS MODE: Python-direct. CANVAS_API_TOKEN is set."
            f" Course ID: {CANVAS_COURSE_ID}. Base URL: {CANVAS_BASE_URL}."
            f"\nFor all Canvas reads, call fetch_modules() or fetch_module_items() — do NOT use MCP for reads."
            f"\nFor all Canvas writes, call create_page(), update_page(), insert_module_item(), or update_module_item()."
            f"\nMCP is available as a fallback only if a Python function returns an error."
        )
    elif CANVAS_COURSE_ID:
        system_prompt += (
            f"\n\nCANVAS MODE: MCP-only (CANVAS_API_TOKEN not set)."
            f" Course ID: {CANVAS_COURSE_ID}."
            f"\nUse MCP tools for Canvas reads. Canvas writes are blocked until CANVAS_API_TOKEN is added to .env."
        )
    else:
        system_prompt += "\n\nNOTE: CANVAS_COURSE_ID is not set. Ask the instructor for the course ID before any Canvas operations."

    if dry_run:
        system_prompt += "\n\nDRY RUN MODE: Do not call request_confirmation or any write tools. Audit and propose only."

    # Local tools (handled in this process)
    local_tool_map = {
        "parse_course_export":    parse_course_export,
        "analyze_cognitive_load": analyze_cognitive_load,
        "read_local_file":        read_local_file,
        "write_local_file":       write_local_file,
        "fetch_byui_resources":   fetch_byui_resources,
        "request_confirmation":   request_confirmation,
        "canvas_available":       canvas_available,
        "fetch_modules":          fetch_modules,
        "fetch_module_items":     lambda module_id, **_: fetch_module_items(int(module_id)),
        "create_page":            create_page,
        "update_page":            update_page,
        "insert_module_item":     lambda **kw: insert_module_item(**{k: int(v) if k in ("module_id", "position") else v for k, v in kw.items()}),
        "update_module_item":     lambda **kw: update_module_item(**{k: int(v) if k in ("module_id", "item_id") else v for k, v in kw.items()}),
        "cache_page_slug":        cache_page_slug,
        "cache_module_id":        cache_module_id,
    }
    tools = [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in llm_cfg["tools"]
    ]

    # MCP server config
    mcp_servers = llm_cfg.get("mcp_servers", [])
    # Strip internal _notes field before passing to API
    mcp_servers_api = [
        {k: v for k, v in s.items() if not k.startswith("_")}
        for s in mcp_servers
    ]

    messages = [
        {
            "role": "user",
            "content": (
                f"Please audit the Canvas course export at: {zip_path}\n"
                "Parse the export, run the cognitive load audit, then present "
                "a prioritized change plan with before/after previews."
            )
        }
    ]

    print(f"\nCanvas Course Expert starting...\nCourse: {zip_path}\n{'='*60}\n")

    # Track whether request_confirmation was called before the current write
    _confirmed_this_turn = False

    max_turns = 20
    for turn in range(max_turns):
        create_kwargs = dict(
            model=llm_cfg["model"],
            max_tokens=llm_cfg["parameters"]["max_tokens"],
            temperature=llm_cfg["parameters"]["temperature"],
            system=system_prompt,
            tools=tools,
            messages=messages,
        )
        if mcp_servers_api:
            create_kwargs["mcp_servers"] = mcp_servers_api
            create_kwargs["betas"] = ["mcp-client-2025-04-04"]

        response = (
            client.beta.messages.create(**create_kwargs)
            if mcp_servers_api
            else client.messages.create(**create_kwargs)
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(block.text)
            break

        if response.stop_reason in ("tool_use", "mcp_tool_use"):
            tool_results = []
            _confirmed_this_turn = False

            for block in response.content:
                if hasattr(block, "text"):
                    print(block.text)

                if not hasattr(block, "type") or block.type not in ("tool_use", "mcp_tool_use"):
                    continue

                tool_name = block.name
                tool_input = block.input
                print(f"\n[Tool: {tool_name}]")

                # Guard: Canvas MCP write tools require prior confirmation
                if block.type == "mcp_tool_use" and any(tool_name.startswith(p) for p in _WRITE_PREFIXES):
                    if not _confirmed_this_turn:
                        result = {
                            "error": "confirmation_required",
                            "message": "Call request_confirmation() first with a before/after preview, then retry this tool."
                        }
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                        continue
                    if dry_run:
                        result = {"error": "write_blocked_dry_run"}
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                        continue
                    # MCP tools are forwarded automatically by the SDK — no local handling needed
                    _confirmed_this_turn = False  # Reset after each write
                    continue

                # Local tool dispatch
                if block.type == "tool_use":
                    func = local_tool_map.get(tool_name)
                    if func:
                        result = func(**tool_input)
                        if tool_name == "request_confirmation":
                            _confirmed_this_turn = result.get("approved", False)
                    else:
                        result = {"error": f"Unknown local tool: {tool_name}"}

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })

            if tool_results:
                messages.append({"role": "user", "content": tool_results})

        if response.stop_reason == "pause_turn":
            messages.append({
                "role": "user",
                "content": [{"type": "text", "text": "Please continue."}]
            })

    print("\n" + "=" * 60 + "\nCanvas Course Expert complete.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _run_tests():
    """Smoke tests — no Canvas API or MCP required."""
    print("Running smoke tests...\n")

    # Test 1: parse with missing file
    result = parse_course_export("/nonexistent/path.imscc")
    assert "error" in result, "Test 1 failed: expected error for missing file"
    print("✓ Test 1: Missing file returns error")

    # Test 2: cognitive load audit with synthetic data
    course_data = {
        "modules": [
            {
                "id": "mod1", "title": "Statistics Intro", "position": 1, "published": True,
                "items": [
                    {"id": "i1", "title": "Assignment 1", "type": "Assignment"},
                    {"id": "i2", "title": "Reading 1", "type": "Page"},
                    {"id": "i3", "title": "Reading 2", "type": "Page"},
                    {"id": "i4", "title": "Reading 3", "type": "Page"},
                    {"id": "i5", "title": "Reading 4", "type": "Page"},
                    {"id": "i6", "title": "Reading 5", "type": "Page"},
                    {"id": "i7", "title": "Reading 6", "type": "Page"},
                    {"id": "i8", "title": "Reading 7", "type": "Page"},
                ],
                "item_count": 8,
            }
        ],
        "pages": [
            {"path": "/tmp/orphan.html", "filename": "orphan.html",
             "title": "Orphaned Page", "word_count": 200, "content_preview": ""},
        ],
        "assignments": [], "quizzes": [], "discussions": [], "settings": {},
    }
    report = analyze_cognitive_load(course_data)
    assert any(i["rule_id"] == "CL-001" for i in report["issues"]), "Test 2a failed: CL-001 should fire"
    assert any(i["rule_id"] == "CL-002" for i in report["issues"]), "Test 2b failed: CL-002 should fire"
    assert not any(i["rule_id"] == "CL-007" for i in report["issues"]), "Test 2c failed: CL-007 should not fire"
    print(f"✓ Test 2: Cognitive load audit — score {report['score']}/100, {len(report['issues'])} issues")

    # Test 3: fetch_byui_resources returns content
    result = fetch_byui_resources("module structure")
    assert len(result) > 50, "Test 3 failed: should return content"
    print("✓ Test 3: fetch_byui_resources returns content")

    # Test 4: write_local_file creates backup
    import tempfile as _tmp
    with _tmp.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
        f.write("<p>original</p>")
        tmp_path = f.name
    result = write_local_file(tmp_path, "<p>updated</p>")
    assert result["success"], "Test 4 failed: write should succeed"
    assert Path(tmp_path + ".bak").exists(), "Test 4 failed: backup not created"
    print("✓ Test 4: write_local_file creates .bak backup")

    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Canvas Course Expert — Python tool functions and audit engine.",
        epilog="Use canvas_sync.py for course mirroring. Use canvas_api_tool.py --test for smoke tests."
    )
    parser.add_argument("--test", action="store_true", help="Run smoke tests")
    # Deprecated — kept to surface a helpful error if someone tries it
    parser.add_argument("--audit", metavar="EXPORT_PATH", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.test:
        _run_tests()
    elif args.audit:
        print(
            "ERROR: --audit (imscc export mode) is deprecated.\n"
            "Use canvas_sync.py --init to pull the live course into course/, "
            "then analyze_cognitive_load() against that data.\n"
            "See README.md for the current workflow."
        )
    else:
        parser.print_help()

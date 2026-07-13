"""
canvas_sync.py

Local mirror of a Canvas course. Pulls instructor-authored content into a
folder structure, tracks content hashes, and pushes changes back to Canvas.

Source of truth: local files. Canvas is the delivery target.
Conflict rule: local always wins. If Canvas was edited directly, use --pull
(no path) to re-sync the full course, or --pull <path> for a single file.

Usage:
    uv run python canvas_sync.py --pull               # full course pull (alias for --init)
    uv run python canvas_sync.py --pull <path>        # re-pull one file from Canvas
    uv run python canvas_sync.py --push               # push all local changes to Canvas
    uv run python canvas_sync.py --push "sprint-1"    # push one module
    uv run python canvas_sync.py --status             # show local changes not yet pushed
    uv run python canvas_sync.py --init               # same as --pull (full course pull)

    Add --quiet to any command to suppress per-file output lines.

Folder structure:
    course/
      _course.json
      sprint-1-setup-dag-demo/
        _module.json          # module metadata: position, published, canvas_id, item order
        sprint-1-overview.html
        w01-reading-quiz-ch1.json
        w01-standup-report.json
      sprint-2-api-dag/
        _module.json
        ...
    .canvas/index.json        # canvas_ids, slugs, hashes — sync state

Item types pulled:
    Page        → .html  (body only, metadata in _module.json items list)
    Assignment  → .json  (name, description, points, due_at, submission_types, allowed_extensions, omit_from_final_grade)
    Discussion  → .json  (title, message, todo_date, published)
    Quiz        → .json  (title, description, points_possible, time_limit, allowed_attempts, shuffle_answers, due_at via assignment_id)
    ExternalTool, SubHeader, ExternalUrl → .json (metadata only, no editable body)

Items NOT pulled (Canvas-generated, not instructor-authored):
    Gradebook, submissions, enrollments, analytics, student data
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import requests

from __toolbox_version__ import __version__
from canvas_course_guard import enforce as _course_guard

# Load .env via the shared helper — finds .env regardless of where the tool
# is invoked from (issue #43). Walks up from CWD, then __file__ as fallback.
try:
    from _env_loader import load_env
    load_env()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url
CANVAS_COURSE_ID = os.environ.get("CANVAS_COURSE_ID", "")

QUIET = False  # set to True via --quiet flag; suppresses per-file output lines
PUSH_LOG = Path(".canvas/push_log.md")


def _vprint(*args, **kwargs):
    """Print only when not in quiet mode."""
    if not QUIET:
        print(*args, **kwargs)


def _log_push(summary: str, comment: str, files_pushed: list[str], direction: str = "push") -> None:
    """Append a commit-style entry to .canvas/push_log.md."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    PUSH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PUSH_LOG.open("a", encoding="utf-8") as f:
        f.write(f"\n## [{direction.upper()}] {summary}\n")
        f.write(f"_{ts}_\n\n")
        if comment:
            f.write(f"{comment}\n\n")
        for fp in files_pushed:
            f.write(f"- {fp}\n")
        f.write("\n")

COURSE_DIR = Path("course")
COURSE_SRC_DIR = Path("course_src")
INDEX_PATH = Path(".canvas/index.json")

# Item types with no editable body — store as metadata-only JSON
METADATA_ONLY_TYPES = {"ExternalTool", "ExternalUrl", "ContextModuleSubHeader"}


# ---------------------------------------------------------------------------
# Canvas API helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}", "Content-Type": "application/json"}


def _get(endpoint: str, params: Optional[dict] = None) -> list | dict:
    """GET with automatic pagination."""
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    results = []
    while url:
        resp = requests.get(url, headers=_headers(), params=params, timeout=20)
        if resp.status_code >= 400:
            print(f"  ERROR {resp.status_code}: {resp.text[:200]}")
            return []
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data  # single object
        # Follow Canvas pagination
        url = None
        link = resp.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        params = None  # params already in URL after first page
    return results


def _put(endpoint: str, payload: dict) -> dict:
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    resp = requests.put(url, headers=_headers(), json=payload, timeout=20)
    if resp.status_code >= 400:
        return {"error": resp.text[:300], "status_code": resp.status_code}
    body = resp.json() if resp.text else {}
    return {"success": True, "status_code": resp.status_code, "id": body.get("id"), "url": body.get("url")}


def _post(endpoint: str, payload: dict) -> dict:
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    resp = requests.post(url, headers=_headers(), json=payload, timeout=20)
    if resp.status_code >= 400:
        return {"error": resp.text[:300], "status_code": resp.status_code}
    body = resp.json() if resp.text else {}
    return {"success": True, "status_code": resp.status_code, "id": body.get("id"), "url": body.get("url")}


# ---------------------------------------------------------------------------
# Index helpers
# ---------------------------------------------------------------------------

def _load_index() -> dict:
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text())
    return {"course_id": CANVAS_COURSE_ID, "base_url": CANVAS_BASE_URL, "files": {}, "modules": []}


def _save_index(index: dict) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, indent=2, default=str))


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _slug(text: str) -> str:
    """Convert a title to a filesystem-safe slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:80]


# ---------------------------------------------------------------------------
# File reference helpers (issue #16 — file-aware pulling)
# ---------------------------------------------------------------------------

LINKED_FILES_DIR = Path("course/_files")
_FILE_REF_PATTERN = re.compile(r"/courses/\d+/files/(\d+)")


def _extract_file_refs(text: Optional[str]) -> set:
    """Find /courses/X/files/N references. Returns set of canvas_file_ids (int)."""
    if not text:
        return set()
    return {int(m) for m in _FILE_REF_PATTERN.findall(text)}


def _format_size(size_bytes: Optional[int]) -> str:
    """Human-readable byte count. Returns '?' if size_bytes is None."""
    if size_bytes is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _parse_size(size_str: Optional[str]) -> Optional[int]:
    """Parse '50mb', '1.5gb', '500kb' → bytes. Returns None for None/invalid."""
    if not size_str:
        return None
    s = size_str.strip().lower()
    multipliers = {"kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4, "b": 1}
    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if s.endswith(suffix):
            try:
                return int(float(s[: -len(suffix)]) * mult)
            except ValueError:
                return None
    try:
        return int(s)  # bare number = bytes
    except ValueError:
        return None


def _get_file_metadata(course_id: str, file_id: int) -> Optional[dict]:
    """GET /courses/:id/files/:file_id — returns dict or None on error/missing."""
    data = _get(f"/courses/{course_id}/files/{file_id}")
    if isinstance(data, list) or not data or data.get("error"):
        return None
    return data


def _search_files(course_id: str, pattern: str) -> list:
    """GET /courses/:id/files?search_term=<pattern> — fuzzy search by filename/display_name."""
    data = _get(f"/courses/{course_id}/files", params={"search_term": pattern, "per_page": 50})
    return data if isinstance(data, list) else []


def _download_file(file_meta: dict, local_path: Path) -> bool:
    """Download a file via its pre-signed URL. Returns True on success."""
    url = file_meta.get("url")
    if not url:
        return False
    try:
        resp = requests.get(url, timeout=120, stream=True)
        if resp.status_code >= 400:
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with local_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        return True
    except Exception:
        return False


def _prompt_file_download(file_inventory: dict, total_size: int) -> bool:
    """Show summary, prompt user. Returns True to proceed, False to skip.

    Thresholds:
      < 50 MB    → silent (auto-proceed, return True)
      50 MB-1 GB → prompt with summary + top-N largest
      > 1 GB     → prompt with full list before proceeding
    """
    if os.getenv("CANVAS_SYNC_NO_PROMPT"):
        return True

    size_mb = total_size / (1024 * 1024)
    if size_mb < 50:
        return True

    n = len(file_inventory)
    sorted_files = sorted(file_inventory.values(), key=lambda f: -(f.get("size") or 0))
    top_count = n if size_mb > 1024 else min(5, n)

    print(f"\nFound {n} referenced file(s)")
    print(f"  Total: {_format_size(total_size)}")
    if top_count > 0:
        print(f"  {'Full list' if size_mb > 1024 else f'Largest {top_count}'}:")
        for f in sorted_files[:top_count]:
            name = f.get("display_name") or f.get("filename", "?")
            print(f"    - {name:<50} {_format_size(f.get('size'))}")
        if size_mb <= 1024 and n > top_count:
            print(f"    + {n - top_count} smaller files")

    try:
        ans = input(f"\nDownload {n} file(s)? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans in ("", "y", "yes")


def _local_path_for_file(file_meta: dict, folder_paths: dict) -> Path:
    """Resolve the local path under course/_files/ for a file based on its Canvas folder."""
    folder_id = file_meta.get("folder_id")
    folder_full_name = folder_paths.get(folder_id, "")
    # Strip leading "course files/" prefix from Canvas folder paths
    rel_folder = folder_full_name.removeprefix("course files/").removeprefix("course files").lstrip("/")
    filename = file_meta.get("filename") or file_meta.get("display_name", f"file_{file_meta['id']}")
    if rel_folder:
        return LINKED_FILES_DIR / rel_folder / filename
    return LINKED_FILES_DIR / filename


# ---------------------------------------------------------------------------
# New Quizzes API helpers (separate base path: /api/quiz/v1/)
# ---------------------------------------------------------------------------

def _get_new_quiz(path: str) -> any:
    """GET from the New Quizzes engine API (/api/quiz/v1/). Returns parsed JSON or None on error."""
    url = f"{CANVAS_BASE_URL}/api/quiz/v1{path}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=20)
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            return {"error": resp.text[:200], "status_code": resp.status_code}
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def _pull_new_quiz_sidecar(course_id: str, quiz_id: int) -> Optional[dict]:
    """Pull New Quiz settings and items. Returns combined dict or None if inaccessible."""
    settings = _get_new_quiz(f"/courses/{course_id}/quizzes/{quiz_id}")
    if not settings or isinstance(settings, dict) and settings.get("error"):
        return None
    items = _get_new_quiz(f"/courses/{course_id}/quizzes/{quiz_id}/items?per_page=100")
    return {
        "quiz_engine": "new_quiz",
        "settings": settings,
        "items": items if isinstance(items, list) else [],
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Markdown conversion helpers
# ---------------------------------------------------------------------------

def _html_to_md(html: str, title: str = "", canvas_id: int = 0, page_url: str = "") -> str:
    """Convert Canvas page HTML to markdown with YAML frontmatter."""
    import markdownify
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("script"):
        tag.decompose()
    # Unwrap outermost byui div if present — it's canvas/CSS scaffolding, not content
    outer = soup.find("div", class_=lambda c: c and "byui" in c.split())
    inner_html = str(outer) if outer else str(soup.body or soup)

    md_body = markdownify.markdownify(inner_html, heading_style="ATX", strip=["div"]).strip()

    frontmatter = "---\n"
    if title:
        frontmatter += f"title: {title}\n"
    if canvas_id:
        frontmatter += f"canvas_id: {canvas_id}\n"
    if page_url:
        frontmatter += f"page_url: {page_url}\n"
    frontmatter += "---\n\n"
    return frontmatter + md_body


def _md_to_html(md_text: str) -> str:
    """Convert markdown (with optional YAML frontmatter) to Canvas-ready HTML."""
    import markdown as md_lib

    # Strip YAML frontmatter block if present
    body = md_text
    if md_text.startswith("---"):
        end = md_text.find("---", 3)
        if end != -1:
            body = md_text[end + 3:].lstrip("\n")

    return md_lib.markdown(body, extensions=["tables", "fenced_code"])


def _assignment_json_to_md(assignment: dict) -> str:
    """Convert Canvas assignment JSON to markdown with YAML frontmatter."""
    from bs4 import BeautifulSoup
    import markdownify

    # Extract description HTML and convert to markdown
    description_html = assignment.get("description", "")
    body_md = ""
    if description_html:
        soup = BeautifulSoup(description_html, "lxml")
        # Remove script tags
        for tag in soup.find_all("script"):
            tag.decompose()
        body_md = markdownify.markdownify(
            str(soup),
            heading_style="ATX",
            strip=["div"]
        ).strip()

    # Build YAML frontmatter
    frontmatter = "---\n"
    frontmatter += f"title: {assignment.get('name', 'Untitled')}\n"
    frontmatter += "type: assignment\n"
    frontmatter += f"canvas_id: {assignment.get('canvas_id', 0)}\n"
    if assignment.get("points_possible") is not None:
        frontmatter += f"points: {assignment['points_possible']}\n"
    if assignment.get("due_at"):
        frontmatter += f"due_at: {assignment['due_at']}\n"
    if assignment.get("grading_type"):
        frontmatter += f"grading_type: {assignment['grading_type']}\n"
    if assignment.get("submission_types"):
        frontmatter += f"submission_types: {', '.join(assignment['submission_types'])}\n"
    frontmatter += "---\n\n"

    return frontmatter + body_md


def _quiz_json_to_md(quiz: dict) -> str:
    """Convert Canvas quiz JSON to markdown with YAML frontmatter."""
    from bs4 import BeautifulSoup
    import markdownify

    # Extract description HTML and convert to markdown
    description_html = quiz.get("description", "")
    body_md = ""
    if description_html:
        soup = BeautifulSoup(description_html, "lxml")
        for tag in soup.find_all("script"):
            tag.decompose()
        body_md = markdownify.markdownify(
            str(soup),
            heading_style="ATX",
            strip=["div"]
        ).strip()

    # Build YAML frontmatter
    frontmatter = "---\n"
    frontmatter += f"title: {quiz.get('title', 'Untitled')}\n"
    frontmatter += "type: quiz\n"
    frontmatter += f"canvas_id: {quiz.get('canvas_id', 0)}\n"
    if quiz.get("points_possible") is not None:
        frontmatter += f"points: {quiz['points_possible']}\n"
    if quiz.get("quiz_type"):
        frontmatter += f"quiz_type: {quiz['quiz_type']}\n"
    if quiz.get("time_limit") is not None:
        frontmatter += f"time_limit: {quiz['time_limit']}\n"
    if quiz.get("allowed_attempts") is not None:
        frontmatter += f"allowed_attempts: {quiz['allowed_attempts']}\n"
    if quiz.get("due_at"):
        frontmatter += f"due_at: {quiz['due_at']}\n"
    frontmatter += "---\n\n"

    return frontmatter + body_md


def _discussion_json_to_md(discussion: dict) -> str:
    """Convert Canvas discussion JSON to markdown with YAML frontmatter."""
    from bs4 import BeautifulSoup
    import markdownify

    # Extract message HTML and convert to markdown
    message_html = discussion.get("message", "")
    body_md = ""
    if message_html:
        soup = BeautifulSoup(message_html, "lxml")
        for tag in soup.find_all("script"):
            tag.decompose()
        body_md = markdownify.markdownify(
            str(soup),
            heading_style="ATX",
            strip=["div"]
        ).strip()

    # Build YAML frontmatter
    frontmatter = "---\n"
    frontmatter += f"title: {discussion.get('title', 'Untitled')}\n"
    frontmatter += "type: discussion\n"
    frontmatter += f"canvas_id: {discussion.get('canvas_id', 0)}\n"
    if discussion.get("todo_date"):
        frontmatter += f"todo_date: {discussion['todo_date']}\n"
    frontmatter += "---\n\n"

    return frontmatter + body_md


# ---------------------------------------------------------------------------
# Pull: Canvas → local files
# ---------------------------------------------------------------------------

def _pull_page(course_id: str, page_url: str) -> Optional[str]:
    """Fetch page body HTML. Returns None on error."""
    data = _get(f"/courses/{course_id}/pages/{page_url}")
    if isinstance(data, list) or "body" not in data:
        return None
    return data.get("body", "")


def _pull_assignment(course_id: str, assignment_id: int) -> Optional[dict]:
    data = _get(f"/courses/{course_id}/assignments/{assignment_id}")
    if isinstance(data, list):
        return None
    return {
        "canvas_id": data.get("id"),
        "name": data.get("name"),
        "description": data.get("description", ""),
        "points_possible": data.get("points_possible"),
        "grading_type": data.get("grading_type"),
        "due_at": data.get("due_at"),
        "lock_at": data.get("lock_at"),
        "unlock_at": data.get("unlock_at"),
        "submission_types": data.get("submission_types", []),
        "allowed_extensions": data.get("allowed_extensions", []),
        "omit_from_final_grade": data.get("omit_from_final_grade", False),
        "published": data.get("published", False),
    }


def _pull_discussion(course_id: str, topic_id: int) -> Optional[dict]:
    data = _get(f"/courses/{course_id}/discussion_topics/{topic_id}")
    if isinstance(data, list):
        return None
    return {
        "canvas_id": data.get("id"),
        "title": data.get("title"),
        "message": data.get("message", ""),
        "todo_date": data.get("todo_date"),
        "published": data.get("published", False),
    }


def _pull_quiz(course_id: str, quiz_id: int) -> Optional[dict]:
    data = _get(f"/courses/{course_id}/quizzes/{quiz_id}")
    if isinstance(data, list):
        return None
    return {
        "canvas_id": data.get("id"),
        "assignment_id": data.get("assignment_id"),
        "title": data.get("title"),
        "description": data.get("description", ""),
        "points_possible": data.get("points_possible"),
        "quiz_type": data.get("quiz_type"),
        "time_limit": data.get("time_limit"),
        "allowed_attempts": data.get("allowed_attempts"),
        "shuffle_answers": data.get("shuffle_answers", False),
        "due_at": data.get("due_at"),
        "lock_at": data.get("lock_at"),
        "unlock_at": data.get("unlock_at"),
        "published": data.get("published", False),
    }


def _check_env():
    """Fail fast if required env vars are missing."""
    missing = [v for v in ("CANVAS_API_TOKEN", "CANVAS_BASE_URL", "CANVAS_COURSE_ID") if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing required .env variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in all three values.")
        sys.exit(1)


def cmd_init():
    """Pull the full course down into course/ folder."""
    _check_env()

    course_id = CANVAS_COURSE_ID

    # Warn if there are unsaved local changes — pull will overwrite them
    index_check = _load_index()
    _unsaved = []
    for fp, meta in index_check.get("files", {}).items():
        p = Path(fp)
        if p.exists() and _file_hash(p) != meta.get("hash"):
            _unsaved.append(fp)
    for key in ("homepage", "syllabus"):
        m = index_check.get(key)
        if m:
            p = Path(m["filepath"])
            if p.exists() and _file_hash(p) != m.get("hash"):
                _unsaved.append(m["filepath"])
    if _unsaved:
        print(f"WARNING: {len(_unsaved)} local file(s) have unpushed changes that will be overwritten:")
        for fp in _unsaved:
            print(f"  M  {fp}")
        print("\n  If YOUR local edits should win → abort and run --push first, then --pull.")
        print("  If CANVAS edits should win (you made changes in Canvas UI) → continue.")
        try:
            confirm = input("\nContinue pull and overwrite local changes? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            confirm = "n"
        if confirm != "y":
            print("Pull aborted. Run --push first, then re-run --pull.")
            return

    print(f"Initializing course {course_id} from {CANVAS_BASE_URL}...\n")

    index = _load_index()
    # Snapshot existing hashes before overwriting — used to detect Canvas-side changes
    prior_hashes = {fp: meta.get("hash") for fp, meta in index.get("files", {}).items()}
    # Include homepage and syllabus in prior snapshot
    if index.get("homepage"):
        prior_hashes[index["homepage"]["filepath"]] = index["homepage"].get("hash")
    if index.get("syllabus"):
        prior_hashes[index["syllabus"]["filepath"]] = index["syllabus"].get("hash")
    index["files"] = {}  # rebuild from scratch — removes stale entries from renames/deletes
    index["modules"] = []  # rebuilt fresh each init
    # METADATA_ONLY_TYPES sidecars written this run. Canvas-backed but not
    # pushable (L8), so they stay out of index["files"] — and must therefore be
    # named here, or the stale sweep deletes what this pull just wrote.
    meta_paths: set = set()

    # Issue #16 — reverse map of canvas_file_id → list of source content files that reference it.
    # Built as a side effect of pulling content; consumed by --pull-files (this script) and
    # course_quality_check.py --files (orphan/broken-reference audit, issue #17).
    index["linked_files"] = {}
    referenced_by: dict = {}  # {canvas_file_id: [content_filepath, ...]}

    # Course metadata + Syllabus
    course = _get(f"/courses/{course_id}?include[]=syllabus_body")
    COURSE_DIR.mkdir(exist_ok=True)
    COURSE_SRC_DIR.mkdir(exist_ok=True)
    Path("course_ref").mkdir(exist_ok=True)

    # Late policy
    late_policy_resp = _get(f"/courses/{course_id}/late_policy")
    late_policy = late_policy_resp.get("late_policy", {}) if late_policy_resp else {}

    course_meta = {
        "canvas_id": course.get("id"),
        "name": course.get("name"),
        "course_code": course.get("course_code"),
        "workflow_state": course.get("workflow_state"),
        "grading_standard_id": course.get("grading_standard_id"),
        "start_at": course.get("start_at"),
        "end_at": course.get("end_at"),
        "late_policy": {
            "late_submission_deduction_enabled": late_policy.get("late_submission_deduction_enabled", False),
            "late_submission_deduction": late_policy.get("late_submission_deduction", 0.0),
            "late_submission_interval": late_policy.get("late_submission_interval", "day"),
            "late_submission_minimum_percent_enabled": late_policy.get("late_submission_minimum_percent_enabled", False),
            "late_submission_minimum_percent": late_policy.get("late_submission_minimum_percent", 0.0),
            "missing_submission_deduction_enabled": late_policy.get("missing_submission_deduction_enabled", False),
            "missing_submission_deduction": late_policy.get("missing_submission_deduction", 0.0),
        },
    }
    course_path = COURSE_DIR / "_course.json"
    course_path.write_text(json.dumps(course_meta, indent=2))
    index["course"] = course_meta  # summary in index for agent lookup
    index["course_hash"] = _file_hash(course_path)
    print(f"Course: {course.get('name')}")

    # Homepage (Canvas front_page — not a module item)
    homepage = _get(f"/courses/{course_id}/front_page")
    if homepage and not homepage.get("errors"):
        homepage_body = homepage.get("body", "")
        homepage_url = homepage.get("url", "front-page")
        homepage_path = COURSE_DIR / "homepage.html"
        homepage_path.write_text(homepage_body, encoding="utf-8")
        h_hp = _file_hash(homepage_path)
        index["homepage"] = {
            "filepath": str(homepage_path),
            "page_url": homepage_url,
            "title": homepage.get("title", ""),
            "hash": h_hp,
        }
        for fid in _extract_file_refs(homepage_body):
            referenced_by.setdefault(fid, []).append(str(homepage_path))
        _vprint(f"  [homepage] homepage.html ({len(homepage_body)} chars)")

    # Syllabus (Canvas left-sidebar Syllabus tab — not a module item)
    syllabus_body = course.get("syllabus_body", "")
    syllabus_path = COURSE_DIR / "syllabus.html"
    syllabus_path.write_text(syllabus_body, encoding="utf-8")
    for fid in _extract_file_refs(syllabus_body):
        referenced_by.setdefault(fid, []).append(str(syllabus_path))
    h = _file_hash(syllabus_path)
    index["syllabus"] = {
        "type": "Syllabus",
        "filepath": str(syllabus_path),
        "hash": h,
        "note": "Push via PUT /courses/:id with course[syllabus_body]. Not a module item.",
    }
    _vprint(f"  [syllabus] syllabus.html ({len(syllabus_body)} chars)")

    # Outcomes (course-linked) -> course/_outcomes.json. Lets audits that read
    # course/ locally (rubric_quality, clo_quality) use outcomes without
    # re-hitting the API. A .imscc export has NO outcomes (account-level), so a
    # canvas_sync pull is the only local source — offline stays "unverified".
    outcome_links = _get(f"/courses/{course_id}/outcome_group_links",
                         params={"outcome_style": "full", "per_page": 100})
    outcomes = []
    if isinstance(outcome_links, list):
        for ln in outcome_links:
            o = ln.get("outcome") or {}
            if o.get("id"):
                outcomes.append({
                    "id": o.get("id"),
                    "title": o.get("title") or "",
                    "description": o.get("description") or "",
                    "display_name": o.get("display_name") or "",
                })
    if outcomes:
        (COURSE_DIR / "_outcomes.json").write_text(json.dumps(outcomes, indent=2), encoding="utf-8")
        _vprint(f"  [outcomes] _outcomes.json ({len(outcomes)} outcomes)")

    # Modules
    modules = _get(f"/courses/{course_id}/modules", params={"per_page": 50, "include[]": "items"})
    print(f"Pulling {len(modules)} modules...")

    for mod in modules:
        mod_title = mod.get("name", f"module-{mod['id']}")
        mod_slug = _slug(mod_title)
        mod_dir = COURSE_DIR / mod_slug
        mod_dir.mkdir(exist_ok=True)

        _vprint(f"  [{'+' if mod.get('published') else ' '}] {mod_title}")

        # Index entry for this module (structured view for agent)
        mod_index_entry = {
            "canvas_id": mod.get("id"),
            "title": mod_title,
            "slug": mod_slug,
            "position": mod.get("position"),
            "published": mod.get("published", False),
            "items": [],
        }

        items_meta = []
        for item in mod.get("items", []):
            item_type = item.get("type", "")
            item_title = item.get("title", "unknown")
            item_canvas_id = item.get("id")  # module item id
            content_id = item.get("content_id")
            page_url = item.get("page_url")
            item_slug = _slug(item_title)
            published = item.get("published", False)

            item_record = {
                "module_item_id": item_canvas_id,
                "content_id": content_id,
                "type": item_type,
                "title": item_title,
                "position": item.get("position"),
                "published": published,
                "filename": None,
            }

            filepath = None  # resolved below per type
            _item_dates = {}  # due_at, lock_at, unlock_at — populated per type below

            if item_type == "Page" and page_url:
                filename = f"{item_slug}.html"
                filepath = mod_dir / filename
                body = _pull_page(course_id, page_url)
                if body is not None:
                    filepath.write_text(body, encoding="utf-8")
                    for fid in _extract_file_refs(body):
                        referenced_by.setdefault(fid, []).append(str(filepath))
                    item_record["filename"] = filename
                    item_record["page_url"] = page_url
                    h = _file_hash(filepath)

                    # Write markdown mirror to course_src/
                    src_mod_dir = COURSE_SRC_DIR / mod_slug
                    src_mod_dir.mkdir(parents=True, exist_ok=True)
                    md_path = src_mod_dir / f"{item_slug}.md"
                    md_path.write_text(
                        _html_to_md(body, title=item_title, canvas_id=content_id, page_url=page_url),
                        encoding="utf-8",
                    )

                    index["files"][str(filepath)] = {
                        "canvas_id": content_id,
                        "type": "Page",
                        "title": item_title,
                        "page_url": page_url,
                        "module_item_id": item_canvas_id,
                        "module_slug": mod_slug,
                        "module_canvas_id": mod.get("id"),
                        "hash": h,
                        "published": published,
                        "markdown_path": str(md_path),
                    }
                    _vprint(f"      [page] {filename}")

            elif item_type == "Assignment" and content_id:
                filename = f"{item_slug}.json"
                filepath = mod_dir / filename
                data = _pull_assignment(course_id, content_id)
                if data:
                    filepath.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
                    for fid in _extract_file_refs(data.get("description", "")):
                        referenced_by.setdefault(fid, []).append(str(filepath))
                    item_record["filename"] = filename
                    h = _file_hash(filepath)
                    # Distinguish New Quizzes (external_tool) from plain assignments
                    sub_types = data.get("submission_types", [])
                    entry_type = "NewQuiz" if sub_types == ["external_tool"] else "Assignment"
                    _item_dates = {
                        "due_at": data.get("due_at"),
                        "lock_at": data.get("lock_at"),
                        "unlock_at": data.get("unlock_at"),
                    }
                    index_entry = {
                        "canvas_id": content_id,
                        "type": entry_type,
                        "title": item_title,
                        "module_item_id": item_canvas_id,
                        "module_slug": mod_slug,
                        "module_canvas_id": mod.get("id"),
                        "hash": h,
                        "published": published,
                    }

                    # Write markdown mirror to course_src/ (for LLM consumption)
                    if entry_type == "Assignment":
                        src_mod_dir = COURSE_SRC_DIR / mod_slug
                        src_mod_dir.mkdir(parents=True, exist_ok=True)
                        md_path = src_mod_dir / f"{item_slug}.md"
                        md_path.write_text(
                            _assignment_json_to_md(data),
                            encoding="utf-8",
                        )
                        index_entry["markdown_path"] = str(md_path)

                    # Pull New Quiz sidecar (settings + items) via /api/quiz/v1/
                    if entry_type == "NewQuiz":
                        sidecar = _pull_new_quiz_sidecar(course_id, content_id)
                        if sidecar:
                            sidecar_path = mod_dir / f"{item_slug}.newquiz.json"
                            sidecar_path.write_text(json.dumps(sidecar, indent=2, default=str), encoding="utf-8")
                            index_entry["quiz_engine"] = "new_quiz"
                            index_entry["settings_path"] = str(sidecar_path)
                            _vprint(f"      [newquiz sidecar] {sidecar_path.name}")
                        else:
                            _vprint(f"      [newquiz sidecar] skipped — API inaccessible for {item_title}")

                    index["files"][str(filepath)] = index_entry
                    _vprint(f"      [{entry_type.lower()}] {filename}")

            elif item_type == "Discussion" and content_id:
                filename = f"{item_slug}.json"
                filepath = mod_dir / filename
                data = _pull_discussion(course_id, content_id)
                if data:
                    filepath.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
                    for fid in _extract_file_refs(data.get("message", "")):
                        referenced_by.setdefault(fid, []).append(str(filepath))
                    item_record["filename"] = filename
                    h = _file_hash(filepath)
                    _item_dates = {
                        "due_at": data.get("assignment", {}).get("due_at") if isinstance(data.get("assignment"), dict) else None,
                        "lock_at": data.get("assignment", {}).get("lock_at") if isinstance(data.get("assignment"), dict) else None,
                        "unlock_at": data.get("assignment", {}).get("unlock_at") if isinstance(data.get("assignment"), dict) else None,
                    }
                    # Write markdown mirror to course_src/ (for LLM consumption)
                    src_mod_dir = COURSE_SRC_DIR / mod_slug
                    src_mod_dir.mkdir(parents=True, exist_ok=True)
                    md_path = src_mod_dir / f"{item_slug}.md"
                    md_path.write_text(
                        _discussion_json_to_md(data),
                        encoding="utf-8",
                    )

                    index["files"][str(filepath)] = {
                        "canvas_id": content_id,
                        "type": "Discussion",
                        "title": item_title,
                        "module_item_id": item_canvas_id,
                        "module_slug": mod_slug,
                        "module_canvas_id": mod.get("id"),
                        "hash": h,
                        "published": published,
                        "markdown_path": str(md_path),
                    }
                    _vprint(f"      [discussion] {filename}")

            elif item_type == "Quiz" and content_id:
                filename = f"{item_slug}.json"
                filepath = mod_dir / filename
                data = _pull_quiz(course_id, content_id)
                if data:
                    filepath.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
                    for fid in _extract_file_refs(data.get("description", "")):
                        referenced_by.setdefault(fid, []).append(str(filepath))
                    item_record["filename"] = filename
                    h = _file_hash(filepath)
                    _item_dates = {
                        "due_at": data.get("due_at"),
                        "lock_at": data.get("lock_at"),
                        "unlock_at": data.get("unlock_at"),
                    }

                    # Write markdown mirror to course_src/ (for LLM consumption)
                    src_mod_dir = COURSE_SRC_DIR / mod_slug
                    src_mod_dir.mkdir(parents=True, exist_ok=True)
                    md_path = src_mod_dir / f"{item_slug}.md"
                    md_path.write_text(
                        _quiz_json_to_md(data),
                        encoding="utf-8",
                    )

                    index["files"][str(filepath)] = {
                        "canvas_id": content_id,
                        "type": "Quiz",
                        "title": item_title,
                        "module_item_id": item_canvas_id,
                        "module_slug": mod_slug,
                        "module_canvas_id": mod.get("id"),
                        "hash": h,
                        "published": published,
                        "markdown_path": str(md_path),
                    }
                    _vprint(f"      [quiz] {filename}")

            elif item_type in METADATA_ONLY_TYPES:
                filename = f"{item_slug}.json"
                filepath = mod_dir / filename
                meta = {
                    "canvas_id": item_canvas_id,
                    "type": item_type,
                    "title": item_title,
                    "external_url": item.get("external_url"),
                    "published": published,
                }
                filepath.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                meta_paths.add(str(filepath))
                item_record["filename"] = filename
                _vprint(f"      [meta] {filename}")

            items_meta.append(item_record)

            # Add to structured module index for agent lookup
            mod_index_entry["items"].append({
                "module_item_id": item_canvas_id,
                "canvas_id": content_id,
                "type": item_type,
                "title": item_title,
                "position": item.get("position"),
                "published": published,
                "filepath": str(mod_dir / item_record["filename"]) if item_record.get("filename") else None,
                **_item_dates,
            })

        # Write _module.json
        module_json = {
            "canvas_id": mod.get("id"),
            "title": mod_title,
            "position": mod.get("position"),
            "published": mod.get("published", False),
            "items": items_meta,
        }
        (mod_dir / "_module.json").write_text(json.dumps(module_json, indent=2), encoding="utf-8")
        index["modules"].append(mod_index_entry)

    # Remove local files that no longer exist in Canvas (renames, deletes)
    stale = set(prior_hashes) - set(index["files"]) - {
        index.get("homepage", {}).get("filepath", ""),
        index.get("syllabus", {}).get("filepath", ""),
    }
    stale.discard("")
    for fp in stale:
        p = Path(fp)
        if p.exists():
            p.unlink()
            _vprint(f"  [removed] {fp} (no longer in Canvas)")

    # -----------------------------------------------------------------------
    # Assignment Groups (grading weight structure)
    # -----------------------------------------------------------------------
    print("\nPulling assignment groups...")
    ag_data = _get(f"/courses/{course_id}/assignment_groups", params={"include[]": ["assignments"]})
    index["assignment_groups"] = [
        {
            "canvas_id": ag.get("id"),
            "name": ag.get("name"),
            "group_weight": ag.get("group_weight"),
            "assignments": [
                {
                    "canvas_id": a.get("id"),
                    "name": a.get("name"),
                    "points_possible": a.get("points_possible"),
                    "published": a.get("published"),
                    "due_at": a.get("due_at"),
                }
                for a in ag.get("assignments", [])
            ],
        }
        for ag in ag_data
    ]
    print(f"  {len(index['assignment_groups'])} assignment groups")

    # -----------------------------------------------------------------------
    # Course settings (homepage, nav)
    # -----------------------------------------------------------------------
    print("Pulling course settings...")
    settings = _get(f"/courses/{course_id}/settings")
    nav_tabs = _get(f"/courses/{course_id}/tabs")
    index["course"]["default_view"] = course.get("default_view")
    index["course"]["settings"] = settings if isinstance(settings, dict) else {}
    index["course"]["nav_tabs"] = [
        {"id": t.get("id"), "label": t.get("label"), "hidden": t.get("hidden", False)}
        for t in (nav_tabs if isinstance(nav_tabs, list) else [])
    ]
    print(f"  {len(index['course'].get('nav_tabs', []))} nav tabs")

    # -----------------------------------------------------------------------
    # Orphaned pages (published to course but not in any module)
    # -----------------------------------------------------------------------
    print("Pulling all pages to find orphans...")
    all_pages = _get(f"/courses/{course_id}/pages", params={"per_page": 50})
    linked_page_urls = {
        meta.get("page_url")
        for meta in index["files"].values()
        if meta.get("type") == "Page" and meta.get("page_url")
    }
    homepage_url = index.get("homepage", {}).get("page_url")
    orphans = [
        {
            "canvas_id": p.get("page_id") or p.get("url"),
            "title": p.get("title"),
            "page_url": p.get("url"),
            "published": p.get("published", False),
            "updated_at": p.get("updated_at"),
        }
        for p in (all_pages if isinstance(all_pages, list) else [])
        if p.get("url") not in linked_page_urls
        and p.get("url") != homepage_url
    ]
    index["orphaned_pages"] = orphans
    print(f"  {len(orphans)} orphaned pages (not linked in any module)")

    # -----------------------------------------------------------------------
    # Announcements
    # -----------------------------------------------------------------------
    print("Pulling announcements...")
    announcements = _get(f"/courses/{course_id}/discussion_topics", params={"only_announcements": True, "per_page": 50})
    index["announcements"] = [
        {
            "canvas_id": a.get("id"),
            "title": a.get("title"),
            "posted_at": a.get("posted_at"),
            "published": a.get("published", False),
            "message_preview": (a.get("message") or "")[:200],
        }
        for a in (announcements if isinstance(announcements, list) else [])
    ]
    print(f"  {len(index['announcements'])} announcements")

    # -----------------------------------------------------------------------
    # Gradebook columns (custom columns only — not assignment-based columns)
    # -----------------------------------------------------------------------
    print("Pulling gradebook custom columns...")
    gb_columns = _get(f"/courses/{course_id}/custom_gradebook_columns", params={"per_page": 50})
    index["gradebook_columns"] = [
        {
            "canvas_id": col.get("id"),
            "title": col.get("title"),
            "position": col.get("position"),
            "hidden": col.get("hidden", False),
            "teacher_notes": col.get("teacher_notes", False),
        }
        for col in (gb_columns if isinstance(gb_columns, list) else [])
    ]
    print(f"  {len(index['gradebook_columns'])} custom gradebook columns")

    # -----------------------------------------------------------------------
    # Groups / Group Sets
    # -----------------------------------------------------------------------
    print("Pulling group categories (group sets)...")
    group_categories = _get(f"/courses/{course_id}/group_categories", params={"per_page": 50})
    group_sets = []
    for cat in (group_categories if isinstance(group_categories, list) else []):
        cat_id = cat.get("id")
        groups = _get(f"/group_categories/{cat_id}/groups", params={"per_page": 50})
        group_sets.append({
            "canvas_id": cat_id,
            "name": cat.get("name"),
            "self_signup": cat.get("self_signup"),
            "group_limit": cat.get("group_limit"),
            "groups": [
                {
                    "canvas_id": g.get("id"),
                    "name": g.get("name"),
                    "members_count": g.get("members_count", 0),
                }
                for g in (groups if isinstance(groups, list) else [])
            ],
        })
    index["group_sets"] = group_sets
    print(f"  {len(group_sets)} group sets")

    # -----------------------------------------------------------------------
    # Calendar Events (office hours, TA labs, review sessions, etc.)
    # -----------------------------------------------------------------------
    print("Pulling calendar events...")
    cal_events = _get(f"/calendar_events", params={
        "context_codes[]": f"course_{course_id}",
        "per_page": 50,
        "all_events": True,
    })
    index["calendar_events"] = [
        {
            "canvas_id": e.get("id"),
            "title": e.get("title"),
            "start_at": e.get("start_at"),
            "end_at": e.get("end_at"),
            "location_name": e.get("location_name"),
            "description_preview": (e.get("description") or "")[:200],
            "workflow_state": e.get("workflow_state"),
        }
        for e in (cal_events if isinstance(cal_events, list) else [])
    ]
    print(f"  {len(index['calendar_events'])} calendar events")

    # -----------------------------------------------------------------------
    # Consolidate file-reference scan into index["linked_files"] (issue #16)
    # -----------------------------------------------------------------------
    for fid, sources in referenced_by.items():
        index["linked_files"][str(fid)] = {
            "canvas_file_id": fid,
            "referenced_by": sorted(set(sources)),
            # filename, size, folder, url, local_path are populated only when
            # the user explicitly runs --pull-files (which fetches metadata + downloads).
        }
    if referenced_by:
        print(f"  {len(referenced_by)} file reference(s) discovered across content")

    _save_index(index)
    total = len(index["files"])

    # -----------------------------------------------------------------------
    # Stale index entry pruning — remove index entries whose files don't exist
    # (happens when Canvas items are renamed and get new slugs/filenames)
    # -----------------------------------------------------------------------
    missing_from_disk = [fp for fp in list(index["files"].keys()) if not Path(fp).exists()]
    for fp in missing_from_disk:
        del index["files"][fp]
    if missing_from_disk:
        _vprint(f"  Pruned {len(missing_from_disk)} stale index entries (files renamed/removed)")

    # -----------------------------------------------------------------------
    # Stale file cleanup — delete any tracked-extension files not in new index
    # -----------------------------------------------------------------------
    tracked_paths = set(index["files"].keys())
    # Also protect homepage, syllabus, and _course.json — tracked separately, not in index["files"]
    if index.get("homepage"):
        tracked_paths.add(index["homepage"]["filepath"])
    if index.get("syllabus"):
        tracked_paths.add(index["syllabus"]["filepath"])
    tracked_paths.add(str(COURSE_DIR / "_course.json"))
    deleted = _cleanup_stale_files(COURSE_DIR, tracked_paths, meta_paths)

    # -----------------------------------------------------------------------
    # Auto-log: record what changed vs prior index (undocumented Canvas edits)
    # -----------------------------------------------------------------------
    # Build full hash map of new state (files + homepage + syllabus)
    new_hashes = {fp: meta.get("hash") for fp, meta in index["files"].items()}
    if index.get("homepage"):
        new_hashes[index["homepage"]["filepath"]] = index["homepage"].get("hash")
    if index.get("syllabus"):
        new_hashes[index["syllabus"]["filepath"]] = index["syllabus"].get("hash")

    changed_from_canvas = [
        fp for fp, h in new_hashes.items()
        if fp in prior_hashes and prior_hashes[fp] != h
    ]
    new_files = [fp for fp in new_hashes if fp not in prior_hashes]
    log_entries = changed_from_canvas + new_files + deleted

    if log_entries:
        summary = f"Full pull — {len(changed_from_canvas)} changed, {len(new_files)} new, {len(deleted)} deleted"
        _log_push(summary, "(automatic — canvas-side changes pulled, no manual summary)", log_entries, direction="pull")
        print(f"  Changes logged to {PUSH_LOG}")

    print(f"\nPull complete. {total} files tracked in .canvas/index.json")
    print(f"  {len(index['modules'])} modules, {total} content files")
    if deleted:
        print(f"  {len(deleted)} stale file(s) removed")
    print(f"Course folder: {COURSE_DIR.resolve()}")


# ---------------------------------------------------------------------------
# Status: diff local vs index
# ---------------------------------------------------------------------------

def _cleanup_stale_files(course_dir: Path, tracked_paths: set, meta_paths: set) -> list:
    """Delete Canvas-backed files under course_dir that Canvas no longer has.

    meta_paths are the METADATA_ONLY_TYPES sidecars (ExternalUrl / ExternalTool)
    this pull just wrote. They are deliberately kept OUT of index["files"] —
    those item types cannot be content-pushed (canvas_api_lessons_learned L8),
    and an entry in index["files"] would make cmd_push try. But that also meant
    this sweep saw them as untracked and deleted them in the same run that
    created them, so the mirror silently omitted every ExternalUrl/ExternalTool
    item. They are Canvas-backed, not stale: protect them here, and let a pull
    that stops writing one (because Canvas dropped it) legitimately sweep it.
    """
    deleted = []
    for ext in ("*.json", "*.html"):
        for f in course_dir.rglob(ext):
            if f.name == "_module.json":
                continue
            if f.name.endswith(".questions.json"):
                continue  # local-only quiz push source — never Canvas-backed
            if f.name.endswith(".newquiz.json"):
                continue  # New Quiz sidecar — tracked separately, not in index["files"]
            rel = str(f)
            if rel in meta_paths:
                continue  # metadata-only sidecar written by THIS pull
            if rel not in tracked_paths:
                f.unlink()
                deleted.append(rel)
                print(f"  [deleted] {rel}")
    return deleted


def cmd_status():
    """Show which local files differ from what was last synced to Canvas."""
    index = _load_index()
    files = index.get("files", {})

    if not files:
        print("No tracked files. Run --init first.")
        return

    changed = []
    missing = []

    for filepath_str, meta in files.items():
        path = Path(filepath_str)
        if not path.exists():
            missing.append(filepath_str)
            continue
        current_hash = _file_hash(path)
        if current_hash != meta.get("hash"):
            changed.append((filepath_str, meta))

    if not changed and not missing:
        print("Everything up to date. Nothing to push.")
        return

    if changed:
        print(f"Modified ({len(changed)} files):")
        for fp, meta in changed:
            print(f"  M  {fp}  [{meta['type']}]")

    if missing:
        print(f"\nMissing locally ({len(missing)} files):")
        for fp in missing:
            print(f"  ?  {fp}")

    print(f"\nRun --push to sync changes to Canvas.")


# ---------------------------------------------------------------------------
# Push: local files → Canvas
# ---------------------------------------------------------------------------

def _push_page(filepath: Path, meta: dict) -> bool:
    page_url = meta.get("page_url")
    if not page_url:
        print(f"    ERROR: no page_url in index for {filepath}")
        return False
    body = filepath.read_text(encoding="utf-8")
    result = _put(f"/courses/{CANVAS_COURSE_ID}/pages/{page_url}", {
        "wiki_page": {"body": body, "published": meta.get("published", True)}
    })
    if result.get("error"):
        print(f"    ERROR: {result['error']}")
        return False
    return True


_VALID_GRADING_TYPES = {"pass_fail", "percent", "letter_grade", "gpa_scale", "points", "not_graded"}


def _push_assignment(filepath: Path, meta: dict) -> bool:
    canvas_id = meta.get("canvas_id")
    if not canvas_id:
        print(f"    ERROR: no canvas_id in index for {filepath}")
        return False
    data = json.loads(filepath.read_text(encoding="utf-8"))
    payload: dict = {
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "points_possible": data.get("points_possible"),
        "published": data.get("published", True),
    }
    if "submission_types" in data:
        payload["submission_types"] = data["submission_types"]
    if "allowed_extensions" in data:
        payload["allowed_extensions"] = data["allowed_extensions"]
    if "omit_from_final_grade" in data:
        payload["omit_from_final_grade"] = data["omit_from_final_grade"]
    if "grading_type" in data:
        gt = data["grading_type"]
        if gt not in _VALID_GRADING_TYPES:
            print(f"    ERROR: unsupported grading_type '{gt}'. Valid values: {sorted(_VALID_GRADING_TYPES)}")
            return False
        payload["grading_type"] = gt
    # Handle date fields - include in payload even if None to allow clearing stale dates
    # Setting due_at/lock_at/unlock_at to null in JSON will clear the date in Canvas
    for date_field in ["due_at", "lock_at", "unlock_at"]:
        if date_field in data:
            payload[date_field] = data[date_field]
    result = _put(f"/courses/{CANVAS_COURSE_ID}/assignments/{canvas_id}", {
        "assignment": payload
    })
    if result.get("error"):
        print(f"    ERROR: {result['error']}")
        return False
    return True


def _push_quiz(filepath: Path, meta: dict) -> bool:
    """Push classic quiz metadata via quizzes endpoint; dates via linked assignment endpoint."""
    canvas_id = meta.get("canvas_id")
    if not canvas_id:
        print(f"    ERROR: no canvas_id in index for {filepath}")
        return False
    data = json.loads(filepath.read_text(encoding="utf-8"))
    payload: dict = {"description": data.get("description", "")}
    if "title" in data:
        payload["title"] = data["title"]
    if "points_possible" in data:
        payload["points_possible"] = data["points_possible"]
    if "time_limit" in data:
        payload["time_limit"] = data["time_limit"]
    if "shuffle_answers" in data:
        payload["shuffle_answers"] = data["shuffle_answers"]
    if "allowed_attempts" in data:
        payload["allowed_attempts"] = data["allowed_attempts"]
    result = _put(f"/courses/{CANVAS_COURSE_ID}/quizzes/{canvas_id}", {
        "quiz": payload
    })
    if result.get("error"):
        print(f"    ERROR: {result['error']}")
        return False
    # Dates must go to the linked assignment endpoint — quiz endpoint ignores due_at
    assignment_id = data.get("assignment_id")
    if assignment_id and any(k in data for k in ("due_at", "lock_at", "unlock_at")):
        date_result = _put(f"/courses/{CANVAS_COURSE_ID}/assignments/{assignment_id}", {
            "assignment": {
                "due_at": data.get("due_at"),
                "lock_at": data.get("lock_at"),
                "unlock_at": data.get("unlock_at"),
            }
        })
        if date_result.get("error"):
            print(f"    ERROR (dates): {date_result['error']}")
            return False
    return True


def _push_discussion(filepath: Path, meta: dict) -> bool:
    canvas_id = meta.get("canvas_id")
    if not canvas_id:
        print(f"    ERROR: no canvas_id in index for {filepath}")
        return False
    data = json.loads(filepath.read_text(encoding="utf-8"))
    result = _put(f"/courses/{CANVAS_COURSE_ID}/discussion_topics/{canvas_id}", {
        "title": data.get("title", ""),
        "message": data.get("message", ""),
        "todo_date": data.get("todo_date"),
        "published": data.get("published", True),
    })
    if result.get("error"):
        print(f"    ERROR: {result['error']}")
        return False
    return True


def cmd_push(target: Optional[str] = None):
    """Push changed local files to Canvas. Optionally filter to a module folder."""
    _check_env()

    index = _load_index()
    files = index.get("files", {})

    # Check homepage separately — tracked under index["homepage"], not index["files"]
    homepage_meta = index.get("homepage")
    if homepage_meta and (not target or "homepage" in target):
        homepage_path = Path(homepage_meta["filepath"])
        if homepage_path.exists():
            current_hash = _file_hash(homepage_path)
            if current_hash != homepage_meta.get("hash"):
                print(f"  [Homepage] {homepage_path}")
                body = homepage_path.read_text(encoding="utf-8")
                page_url = homepage_meta.get("page_url", "front-page")
                resp = requests.put(
                    f"{CANVAS_BASE_URL}/api/v1/courses/{CANVAS_COURSE_ID}/pages/{page_url}",
                    headers=_headers(),
                    json={"wiki_page": {"body": body}}, timeout=20)
                if resp.status_code < 400:
                    index["homepage"]["hash"] = current_hash
                    print(f"    OK")
                else:
                    print(f"    FAILED: {resp.text[:200]}")
                _save_index(index)

    # Check _course.json — late_policy and other course-level settings
    course_path = COURSE_DIR / "_course.json"
    if course_path.exists() and (not target or "_course" in target or "course" == target):
        course_hash = _file_hash(course_path)
        stored_hash = index.get("course_hash")
        if course_hash != stored_hash:
            print(f"  [Course] {course_path}")
            data = json.loads(course_path.read_text(encoding="utf-8"))
            lp = data.get("late_policy", {})
            if lp:
                resp = requests.patch(
                    f"{CANVAS_BASE_URL}/api/v1/courses/{CANVAS_COURSE_ID}/late_policy",
                    headers=_headers(),
                    json={"late_policy": lp}, timeout=20)
                if resp.status_code in (200, 204):
                    index["course_hash"] = course_hash
                    index["course"] = data
                    print(f"    OK (late_policy updated)")
                else:
                    print(f"    FAILED late_policy: {resp.text[:200]}")
                _save_index(index)

    # Check syllabus separately — it's tracked under index["syllabus"], not index["files"]
    syllabus_meta = index.get("syllabus")
    if syllabus_meta and (not target or "syllabus" in target):
        syllabus_path = Path(syllabus_meta["filepath"])
        if syllabus_path.exists():
            current_hash = _file_hash(syllabus_path)
            if current_hash != syllabus_meta.get("hash"):
                print(f"  [Syllabus] {syllabus_path}")
                body = syllabus_path.read_text(encoding="utf-8")
                url = f"{CANVAS_BASE_URL}/api/v1/courses/{CANVAS_COURSE_ID}"
                resp = requests.put(url, headers=_headers(),
                                    json={"course": {"syllabus_body": body}}, timeout=20)
                result = {"success": resp.status_code < 400, "status_code": resp.status_code,
                          "error": resp.text[:200] if resp.status_code >= 400 else None}
                if result.get("success"):
                    index["syllabus"]["hash"] = current_hash
                    print(f"    OK")
                else:
                    print(f"    FAILED: {result.get('error')}")
                _save_index(index)

    push_candidates = {}
    for filepath_str, meta in files.items():
        path = Path(filepath_str)
        # Filter to target module if specified
        if target and target not in filepath_str:
            continue
        if not path.exists():
            continue
        current_hash = _file_hash(path)
        if current_hash != meta.get("hash"):
            push_candidates[filepath_str] = (path, meta)

    if not push_candidates:
        print("Nothing to push — all files match Canvas.")
        return

    # Commit-style log prompt
    print(f"\n{len(push_candidates)} file(s) ready to push.")
    if os.getenv("CANVAS_SYNC_NO_PROMPT"):
        # CI / automated context — skip interactive prompt
        summary = os.getenv("CANVAS_SYNC_NO_PROMPT", "Automated push")
        comment = ""
    else:
        try:
            summary = input("Push summary (required): ").strip()
            if not summary:
                print("Aborted — summary is required.")
                return
            comment = input("Additional comments (optional, Enter to skip): ").strip()
        except (EOFError, KeyboardInterrupt):
            summary = "Automated push"
            comment = ""

    print(f"\nPushing {len(push_candidates)} changed file(s)...\n")

    pushed = 0
    for filepath_str, (path, meta) in push_candidates.items():
        item_type = meta.get("type")
        print(f"  [{item_type}] {filepath_str}")

        ok = False
        if item_type == "Page":
            ok = _push_page(path, meta)
        elif item_type == "Assignment":
            ok = _push_assignment(path, meta)
        elif item_type == "Discussion":
            ok = _push_discussion(path, meta)
        elif item_type == "Quiz":
            ok = _push_quiz(path, meta)
        elif item_type == "NewQuiz":
            print(f"    Canvas-only: NewQuiz descriptions must be edited in Canvas UI (API not supported)")
            # Acknowledge current state so it doesn't reappear on every push
            index["files"][filepath_str]["hash"] = _file_hash(path)
            _save_index(index)
            continue
        elif item_type in METADATA_ONLY_TYPES:
            print(f"    SKIP: {item_type} is metadata-only (manage in Canvas directly)")
            continue
        else:
            print(f"    SKIP: unknown type {item_type}")
            continue

        if ok:
            index["files"][filepath_str]["hash"] = _file_hash(path)
            print(f"    OK")
            pushed += 1
        else:
            print(f"    FAILED — hash not updated, will retry on next push")

    _save_index(index)
    _log_push(summary, comment, list(push_candidates.keys()), direction="push")
    print(f"\nPushed {pushed}/{len(push_candidates)} files.")
    print(f"Logged to {PUSH_LOG}")


# ---------------------------------------------------------------------------
# Upload: local file → Canvas Files
# ---------------------------------------------------------------------------

def _upload_file_to_canvas(local_path: Path, canvas_folder: str, course_id: str) -> dict:
    """Upload a local file to Canvas Files using the two-step upload API.

    Returns dict with canvas_file_id, filename, folder, url, local_source_path,
    or raises RuntimeError on failure.
    """
    import mimetypes

    filename = local_path.name
    file_size = local_path.stat().st_size
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # Step 1: request an upload token
    token_url = f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/files"
    token_resp = requests.post(
        token_url,
        headers={"Authorization": f"Bearer {CANVAS_API_TOKEN}"},
        json={
            "name": filename,
            "size": file_size,
            "content_type": content_type,
            "parent_folder_path": canvas_folder,
            "on_duplicate": "overwrite",
        },
        timeout=20,
    )
    if token_resp.status_code >= 400:
        raise RuntimeError(f"Upload token request failed ({token_resp.status_code}): {token_resp.text[:300]}")

    token_data = token_resp.json()
    upload_url = token_data["upload_url"]
    upload_params = token_data.get("upload_params", {})

    # Step 2: multipart POST to the pre-signed URL
    with local_path.open("rb") as fh:
        upload_resp = requests.post(
            upload_url,
            data=upload_params,
            files={"file": (filename, fh, content_type)},
            allow_redirects=True,
            timeout=60,
        )

    if upload_resp.status_code not in (200, 201, 301, 302):
        raise RuntimeError(f"Upload POST failed ({upload_resp.status_code}): {upload_resp.text[:300]}")

    # Canvas may return the file object directly or after a redirect
    file_obj = upload_resp.json() if upload_resp.text else {}

    # If Canvas returned a redirect URL instead of a JSON body, follow it
    if "id" not in file_obj and upload_resp.history:
        confirm_resp = requests.get(
            upload_resp.url,
            headers={"Authorization": f"Bearer {CANVAS_API_TOKEN}"},
            timeout=20,
        )
        file_obj = confirm_resp.json() if confirm_resp.text else {}

    canvas_file_id = file_obj.get("id")
    file_url = file_obj.get("url", "")

    return {
        "canvas_file_id": canvas_file_id,
        "filename": filename,
        "folder": canvas_folder,
        "url": file_url,
        "local_source_path": str(local_path),
    }


def cmd_upload(target: str, folder: str = "course_assets") -> None:
    """Upload a local file (or all files in a folder) to Canvas Files.

    Stores canvas_file_id, filename, folder, url, and local_source_path in
    index["files_uploaded"] keyed by local path string.

    Args:
        target: path to a local file or directory to upload
        folder: Canvas folder path to place files in (default: "course_assets")
    """
    index = _load_index()
    if "files_uploaded" not in index:
        index["files_uploaded"] = {}

    target_path = Path(target)
    if not target_path.exists():
        print(f"ERROR: path not found — {target}")
        sys.exit(1)

    if target_path.is_dir():
        candidates = [p for p in target_path.iterdir() if p.is_file() and not p.name.startswith(".")]
    else:
        candidates = [target_path]

    if not candidates:
        print("No files found to upload.")
        return

    uploaded = 0
    failed = 0
    for local_path in sorted(candidates):
        try:
            _vprint(f"  Uploading: {local_path} → Canvas Files/{folder}/")
            meta = _upload_file_to_canvas(local_path, folder, CANVAS_COURSE_ID)
            index["files_uploaded"][str(local_path)] = meta
            _vprint(f"    ✓ canvas_file_id={meta['canvas_file_id']}  url={meta['url']}")
            uploaded += 1
        except RuntimeError as exc:
            print(f"  ERROR uploading {local_path.name}: {exc}")
            failed += 1

    _save_index(index)
    print(f"\nUpload complete. {uploaded} uploaded, {failed} failed.")
    if uploaded:
        print(f"  File metadata stored in {INDEX_PATH} under 'files_uploaded'.")
        print(f"  Use the URL from the index to link files in assignment descriptions or pages.")


# ---------------------------------------------------------------------------
# Build: course_src/*.md → course/*.html
# ---------------------------------------------------------------------------

def cmd_build():
    """Convert course_src markdown files to Canvas-ready HTML in course/.

    Reads all pages tracked in the index that have a markdown_path, converts
    the .md file to HTML, and writes it to the corresponding course/ path.
    Run this after editing markdown, then use --push to sync to Canvas.
    """
    index = _load_index()
    built = 0
    skipped = 0

    for filepath_str, meta in index.get("files", {}).items():
        if meta.get("type") != "Page":
            continue
        md_path_str = meta.get("markdown_path")
        if not md_path_str:
            continue
        md_path = Path(md_path_str)
        if not md_path.exists():
            _vprint(f"  SKIP: markdown source missing — {md_path_str}")
            skipped += 1
            continue
        html_path = Path(filepath_str)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        md_content = md_path.read_text(encoding="utf-8")
        html_content = _md_to_html(md_content)
        html_path.write_text(html_content, encoding="utf-8")
        _vprint(f"  [built] {filepath_str}")
        built += 1

    print(f"Build complete. {built} page(s) built from markdown.")
    if skipped:
        print(f"  {skipped} page(s) skipped — markdown source missing (run --pull first)")
    if built:
        print(f"  Run --status to review changes, then --push to sync to Canvas.")


# ---------------------------------------------------------------------------
# Pull single resource (re-sync from Canvas → local)
# ---------------------------------------------------------------------------

def cmd_pull(target: str):
    """
    Re-pull a specific file from Canvas, overwriting local.
    Use this when Canvas was edited directly and you want to accept that change.
    Logs the undocumented Canvas change to .canvas/push_log.md.
    Example: --pull course/sprint-1-setup-dag-demo/sprint-1-overview.html
    """
    index = _load_index()
    files = index.get("files", {})

    matches = {k: v for k, v in files.items() if target in k}
    if not matches:
        print(f"No tracked file matching: {target}")
        return

    for filepath_str, meta in matches.items():
        path = Path(filepath_str)
        item_type = meta.get("type")
        print(f"Pulling {filepath_str} from Canvas...")

        if item_type == "Page":
            page_url = meta.get("page_url")
            body = _pull_page(CANVAS_COURSE_ID, page_url)
            if body is not None:
                path.write_text(body, encoding="utf-8")
                index["files"][filepath_str]["hash"] = _file_hash(path)
                print(f"  OK — local file updated from Canvas")
            else:
                print(f"  ERROR — could not fetch page {page_url}")

        elif item_type == "Assignment":
            data = _pull_assignment(CANVAS_COURSE_ID, meta["canvas_id"])
            if data:
                path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
                index["files"][filepath_str]["hash"] = _file_hash(path)
                print(f"  OK — local file updated from Canvas")

        elif item_type == "Discussion":
            data = _pull_discussion(CANVAS_COURSE_ID, meta["canvas_id"])
            if data:
                path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
                index["files"][filepath_str]["hash"] = _file_hash(path)
                print(f"  OK — local file updated from Canvas")

        else:
            print(f"  SKIP: pull not implemented for {item_type}")

    _save_index(index)

    # Log undocumented Canvas-side change
    pulled_files = list(matches.keys())
    try:
        comment = input("Note about this Canvas-side change (optional, Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        comment = ""
    _log_push(f"Canvas-side edit accepted: {target}", comment, pulled_files, direction="pull")
    print(f"Logged to {PUSH_LOG}")


# ---------------------------------------------------------------------------
# File-aware pulling commands (issue #16)
# ---------------------------------------------------------------------------

def cmd_pull_files(max_file_size: Optional[int] = None,
                   max_total_size: Optional[int] = None) -> None:
    """Download referenced Canvas files into course/_files/ based on index["linked_files"].

    Run --pull first to populate the linked_files reverse map. This command
    fetches metadata for each referenced file_id, prompts for size confirmation,
    then downloads approved files. Updates each entry with metadata + local_path.

    Args:
        max_file_size: skip individual files larger than this (bytes); None = no limit
        max_total_size: abort if total scanned size exceeds this (bytes); None = no limit
    """
    _check_env()
    index = _load_index()
    linked = index.get("linked_files", {})

    if not linked:
        print("No file references in index. Run --pull first to scan content for /courses/X/files/N references.")
        return

    print(f"Fetching metadata for {len(linked)} referenced file(s)...\n")

    # Fetch folder hierarchy once for path resolution
    folders = _get(f"/courses/{CANVAS_COURSE_ID}/folders", params={"per_page": 100})
    folder_paths = {f["id"]: f.get("full_name", "") for f in (folders if isinstance(folders, list) else [])}

    file_inventory: dict = {}  # {fid: meta_dict}
    missing: list = []
    total_size = 0
    for fid_str in linked.keys():
        fid = int(fid_str)
        meta = _get_file_metadata(CANVAS_COURSE_ID, fid)
        if meta is None:
            missing.append(fid)
            continue
        size = meta.get("size", 0) or 0
        if max_file_size is not None and size > max_file_size:
            _vprint(f"  [skip-large] file {fid} ({_format_size(size)}) exceeds --max-file-size")
            continue
        file_inventory[fid] = meta
        total_size += size

    if missing:
        print(f"  {len(missing)} file(s) referenced from content but no longer exist in Canvas (broken references)")
        for fid in missing[:5]:
            srcs = linked[str(fid)].get("referenced_by", [])
            print(f"    file_id={fid} (referenced by {len(srcs)} content file(s))")

    if not file_inventory:
        print("\nNothing to download.")
        return

    if max_total_size is not None and total_size > max_total_size:
        print(f"\nABORT: total size {_format_size(total_size)} exceeds --max-total-size {_format_size(max_total_size)}.")
        return

    if not _prompt_file_download(file_inventory, total_size):
        print("Skipped — no files downloaded.")
        return

    print(f"\nDownloading {len(file_inventory)} file(s) into {LINKED_FILES_DIR}/...")
    downloaded = 0
    failed = 0
    for fid, meta in file_inventory.items():
        local_path = _local_path_for_file(meta, folder_paths)
        if _download_file(meta, local_path):
            entry = index["linked_files"][str(fid)]
            entry.update({
                "filename": meta.get("filename"),
                "display_name": meta.get("display_name"),
                "size": meta.get("size"),
                "content_type": meta.get("content_type"),
                "url": meta.get("url"),
                "folder": folder_paths.get(meta.get("folder_id"), ""),
                "local_path": str(local_path),
                "updated_at": meta.get("updated_at"),
            })
            _vprint(f"  [ok] {local_path} ({_format_size(meta.get('size'))})")
            downloaded += 1
        else:
            print(f"  [FAILED] file {fid} — could not download")
            failed += 1

    _save_index(index)
    print(f"\nDownloaded {downloaded}/{len(file_inventory)} file(s). {failed} failed.")


def cmd_find_file(pattern: str) -> None:
    """Read-only fuzzy search of Canvas Files for a pattern. Prints matches; modifies nothing."""
    _check_env()
    matches = _search_files(CANVAS_COURSE_ID, pattern)

    if not matches:
        print(f"No files match '{pattern}'.")
        return

    # Cross-reference with linked_files to mark which are linked vs orphan
    index = _load_index()
    linked_ids = {int(fid) for fid in index.get("linked_files", {}).keys()}

    print(f"Found {len(matches)} file(s) matching '{pattern}':\n")
    print(f"  {'STATUS':<8} {'SIZE':<10} {'NAME':<40} ID")
    for m in matches:
        fid = m.get("id")
        is_linked = fid in linked_ids
        status = "linked" if is_linked else "orphan?"
        name = (m.get("display_name") or m.get("filename") or "?")[:40]
        size = _format_size(m.get("size"))
        print(f"  {status:<8} {size:<10} {name:<40} {fid}")

    print(f"\n('orphan?' status is preliminary — run course_quality_check.py --files for the full audit.)")


def cmd_pull_file(pattern: str) -> None:
    """Interactive: search Canvas Files for pattern, prompt user to pick, download selected."""
    _check_env()
    matches = _search_files(CANVAS_COURSE_ID, pattern)

    if not matches:
        print(f"No files match '{pattern}'.")
        return

    print(f"Found {len(matches)} file(s) matching '{pattern}':\n")
    for i, m in enumerate(matches, start=1):
        name = m.get("display_name") or m.get("filename", "?")
        size = _format_size(m.get("size"))
        print(f"  [{i}] {name}  ({size})  id={m.get('id')}")

    try:
        choice = input(f"\nDownload which? [1-{len(matches)} | 'all' | 'q' to cancel]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return

    if choice in ("q", "", "n"):
        return

    selected = []
    if choice == "all":
        selected = matches
    else:
        try:
            i = int(choice)
            if 1 <= i <= len(matches):
                selected = [matches[i - 1]]
        except ValueError:
            print("Unrecognized input.")
            return

    if not selected:
        print("No selection.")
        return

    folders = _get(f"/courses/{CANVAS_COURSE_ID}/folders", params={"per_page": 100})
    folder_paths = {f["id"]: f.get("full_name", "") for f in (folders if isinstance(folders, list) else [])}

    index = _load_index()
    if "linked_files" not in index:
        index["linked_files"] = {}

    for meta in selected:
        local_path = _local_path_for_file(meta, folder_paths)
        if _download_file(meta, local_path):
            fid = meta.get("id")
            index["linked_files"][str(fid)] = {
                "canvas_file_id": fid,
                "filename": meta.get("filename"),
                "display_name": meta.get("display_name"),
                "size": meta.get("size"),
                "content_type": meta.get("content_type"),
                "url": meta.get("url"),
                "folder": folder_paths.get(meta.get("folder_id"), ""),
                "local_path": str(local_path),
                "updated_at": meta.get("updated_at"),
                "referenced_by": index["linked_files"].get(str(fid), {}).get("referenced_by", []),
            }
            print(f"  [ok] {local_path}")
        else:
            print(f"  [FAILED] {meta.get('display_name', meta.get('id'))}")

    _save_index(index)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="canvas_sync — local mirror of a Canvas course",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  --pull              Full course pull from Canvas (cleans stale local files)
  --pull <path>       Re-pull one file from Canvas and log the Canvas-side change
  --push              Push all local changes to Canvas (prompts for summary + comment)
  --push <module>     Push changed files in one module only
  --build             Convert course_src/*.md → course/*.html (run before --push after editing markdown)
  --status            Show local changes not yet pushed
  --init              Alias for --pull (full course pull)

Markdown authoring workflow:
  1. --pull           Populates both course/ (HTML) and course_src/ (Markdown)
  2. Edit .md files   Edit in course_src/ — human-friendly, agent-friendly
  3. --build          Converts .md back to HTML in course/
  4. --status         Review what changed
  5. --push           Sync to Canvas

Flags:
  --quiet             Suppress per-file lines; show only headers and totals

Safe zones:
  course/             Canvas mirror — overwritten on every --pull. Do not place local-only files here.
  course_src/         Markdown authoring mirror — edit here, then --build before --push.
  course_ref/         Local-only artifacts (answer keys, drafts, helpers) — never touched by --pull.
  course/*.questions.json   Classic quiz push sources — skipped by --pull cleanup.

File upload workflow:
  1. Place template files in course_ref/ (local-only safe zone)
  2. --upload course_ref/my-template.docx   Upload to Canvas Files/course_assets/
  3. Index stores canvas_file_id + URL — reference in assignment descriptions

Change log:  .canvas/push_log.md  (appended on every --push and --pull <path>)
        """
    )
    parser.add_argument("--version", action="version",
                        version=f"canvas-toolbox {__version__}")
    parser.add_argument("--init", action="store_true", help="Pull full course into course/ (same as --pull with no path)")
    parser.add_argument("--status", action="store_true", help="Show changed files")
    parser.add_argument("--push", nargs="?", const="", metavar="MODULE", help="Push changed files to Canvas")
    parser.add_argument("--pull", nargs="?", const="", metavar="PATH",
                        help="Full course pull (no path) or re-pull one file from Canvas (with path)")
    parser.add_argument("--build", action="store_true", help="Convert course_src/*.md to course/*.html")
    parser.add_argument("--upload", metavar="PATH", help="Upload a local file or folder to Canvas Files")
    parser.add_argument("--folder", default="course_assets", metavar="FOLDER",
                        help="Canvas folder to upload into (default: course_assets)")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-file output; show only headers and totals")

    # File-aware pulling (issue #16) — separate, opt-in commands
    parser.add_argument("--pull-files", action="store_true",
                        help="Download referenced Canvas files into course/_files/ "
                             "(requires --pull to have been run first to populate the linked_files map)")
    parser.add_argument("--find-file", metavar="PATTERN",
                        help="Read-only fuzzy search of Canvas Files by filename/display_name")
    parser.add_argument("--pull-file", metavar="PATTERN",
                        help="Interactive: search Canvas Files, pick, download selected")
    parser.add_argument("--max-file-size", metavar="SIZE",
                        help="Skip individual files larger than this (e.g. 100mb, 1gb)")
    parser.add_argument("--max-total-size", metavar="SIZE",
                        help="Abort --pull-files if total scanned size exceeds this")
    parser.add_argument("--allow-enrolled", action="store_true",
                        help="bypass the startup safety guard (allow writes to a "
                             "course flagged as enrolled or a Blueprint child)")

    args = parser.parse_args()

    if args.quiet:
        globals()["QUIET"] = True

    # Startup safety guard (#27) — never block --build (local-only, no Canvas call).
    if not args.build:
        _write_mode = bool(args.push is not None) or bool(args.upload)
        _course_guard(CANVAS_BASE_URL, _headers(), CANVAS_COURSE_ID,
                      "write" if _write_mode else "read",
                      allow_override=args.allow_enrolled,
                      label="CANVAS_COURSE_ID")

    if args.init or args.pull == "":
        cmd_init()
    elif args.status:
        cmd_status()
    elif args.push is not None:
        cmd_push(args.push if args.push else None)
    elif args.pull:
        cmd_pull(args.pull)
    elif args.build:
        cmd_build()
    elif args.upload:
        cmd_upload(args.upload, args.folder)
    elif args.pull_files:
        cmd_pull_files(
            max_file_size=_parse_size(args.max_file_size),
            max_total_size=_parse_size(args.max_total_size),
        )
    elif args.find_file:
        cmd_find_file(args.find_file)
    elif args.pull_file:
        cmd_pull_file(args.pull_file)
    else:
        parser.print_help()

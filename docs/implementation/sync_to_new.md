# sync_to_new.py — Implementation Plan

**Tool name:** `lib/tools/sync_to_new.py`
**Purpose:** Deploy course content from local repo to a new Canvas course (reverse sync)
**Status:** Planning phase
**Target:** Field deployment for next semester prep
**Size:** L (3-4 weeks full), M (1-2 weeks MVP)

---

## Overview

Deploy locally-stored course content (pulled via `canvas_sync.py --pull`) into a **new Canvas course** with a different course ID. This solves the "campus deletes old courses" problem by making git the source of truth for course content.

**Use case:**
1. Instructor pulls course content once: `canvas_sync.py --pull`
2. Git tracks course content in `course/` directory
3. Next semester: create new Canvas course, update `.env` with new course ID
4. Deploy: `sync_to_new.py --apply`
5. Course populated in 2-5 minutes

**Approach:** Reverse sync (API-by-API recreation), **not** Canvas import API + IMSCC generation.

**Why reverse sync:**
- Reuses 80% of existing canvas_sync infrastructure
- Selective restore capability (by module or content type)
- Transparent errors (know exactly which item failed)
- Preview mode (dry-run shows what will be created)
- Incremental rollback (can delete created items)

---

## Architecture

### Input Source
**`.canvas/index.json`** — Single source of truth containing:
- Course metadata (course_id, base_url)
- Module structure (order, titles, published states)
- All content items (pages, assignments, quizzes, discussions)
- Module item relationships (what's in each module)
- Assignment groups and weights
- Homepage and syllabus references

**`course/` directory** — Actual content files:
- HTML files for pages
- JSON files for assignments/quizzes/discussions
- `_files/` subdirectory for Canvas file attachments
- `_module.json` per folder for module metadata

### Output Target
**New Canvas course** specified by `CANVAS_COURSE_ID` in `.env`

### Dependencies from Existing Tools
```python
from canvas_sync import (
    _get, _post, _put,          # API helpers with pagination
    _headers,                    # Auth headers
    _load_index,                 # Parse .canvas/index.json
    _safe_filename,              # Sanitize file paths
)
from canvas_course_guard import (
    verify_course_access,        # Safety check
    is_sandbox_course,           # Sandbox detection
)
```

---

## Phased Implementation

### Phase 1: MVP (M-sized, 1-2 weeks)
**Goal:** Restore modules, pages, and basic assignments

**Scope:**
- Module creation in order
- Page creation and linking as module items
- Basic assignments (no rubrics, no quizzes)
- Dry-run mode (preview without creating)
- Progress reporting

**Success criteria:**
- Can restore 3 modules with 10 pages to sandbox course
- Preview mode shows accurate item list
- All pages render correctly in new course

**Deliverable:** `sync_to_new.py` with flags:
```bash
# Preview what would be created
uv run python lib/tools/sync_to_new.py

# Apply: create modules and pages only
uv run python lib/tools/sync_to_new.py --apply --pages-only
```

**Lines of code estimate:** ~200 + tests

---

### Phase 2: Assignments + Assignment Groups (M-sized, 1-2 weeks)
**Goal:** Support assignment creation with proper grading structure

**Scope:**
- Assignment groups (weighted gradebook structure)
- Regular assignments (descriptions, points, due dates, submission types)
- Graded and ungraded discussions
- External URLs and file links
- Homepage and syllabus

**Success criteria:**
- Can restore assignments with correct assignment group weights
- Gradebook structure matches source course
- Graded discussions work correctly

**Deliverable:** Full assignment restore with grading structure

**Lines of code estimate:** ~200 + tests

**Note:** Assignment group data is ALREADY in `.canvas/index.json` (canvas_sync.py pulls it). Just needs restore logic.

---

### Phase 3: Quiz Questions + Question Banks (L-sized, 2-3 weeks)
**Goal:** Support Classic Quiz restoration with question banks

**Prerequisites:** Enhance canvas_sync.py first:
1. Pull question banks via `/courses/:id/quiz_question_banks`
2. Pull classic quiz questions via `/courses/:id/quizzes/:quiz_id/questions`
3. Store in `.canvas/index.json` and separate JSON files

**Scope:**
- Question bank creation in target course
- Classic quiz question restoration
- Quiz question linking to question banks
- Quiz settings (time limits, allowed attempts, shuffle)

**Success criteria:**
- Classic quizzes restore with all questions
- Question banks restore with all questions
- Quizzes linked to correct question banks

**Deliverable:** Complete classic quiz restoration

**Lines of code estimate:**
- canvas_sync.py enhancement: ~150 lines
- sync_to_new.py restore logic: ~200 lines
- Total: ~350 + tests

**Note:** NewQuizzes cannot be restored (Canvas API limitation — questions not exposed)

---

### Phase 4: Files + Advanced Features (M-sized, 1-2 weeks)
**Goal:** Handle file uploads and advanced scenarios

**Scope:**
- File uploads for referenced assets in `course/_files/`
- File ID rewriting (update HTML/JSON with new file IDs)
- Rubric attachment (if stored locally)
- Module prerequisites and completion requirements
- Selective restoration by module or item type
- Date shifting (adjust due dates for new semester)

**Success criteria:**
- Images in pages render correctly (files uploaded + links rewritten)
- PDFs linked correctly
- Module prerequisites work correctly

**Implementation approach (based on testing 2026-07-10):**

### Hybrid Strategy: Server-Side Copy + Local Upload Fallback

**PRIMARY: Server-Side Copy (Fast & Reliable)**
```python
POST /api/v1/folders/:dest_folder_id/copy_file
{ "source_file_id": 58757114, "on_duplicate": "overwrite" }
```
- ✅ Tested: 100% success rate (5/5 files)
- ✅ Fast: 0.39s average per file
- ✅ Immediate response (no progress polling)
- ✅ Use when source course accessible

**FALLBACK: Local Upload**
- Use when source course deleted or inaccessible
- Requires `--pull-files` before restore
- Tested: works but slower (5s per file vs 0.39s)

**Workflow:**
1. **Check source course accessibility**
   - Try GET /courses/:source_id (with auth)
   - If accessible → use server-side copy
   - If 401/403/404 → use local files

2. **Server-side copy** (when source exists)
   - Get target course root folder: `GET /courses/:id/folders/root`
   - Copy each file: `POST /folders/:dest_id/copy_file`
   - Build mapping: old_file_id → new_file_id
   - **5.4x faster** than local upload (tested with 7 files: 2.73s vs 14.7s)

3. **Local upload** (fallback)
   - Verify files exist in `course/_files/`
   - Two-step upload for each file (token + multipart POST)
   - Build mapping: old_file_id → new_file_id

4. **Rewrite file URLs** in content (both methods)
   - Update HTML pages: `/courses/145706/files/58757114` → `/courses/427952/files/167671322`
   - Update assignment descriptions, quiz descriptions
   - Use regex: `s|/courses/\d+/files/(\d+)|/courses/{new_course_id}/files/{new_file_id}|g`

5. **Create content** (modules, pages, assignments) with updated URLs

**Deliverable:** Flags for selective restore:
```bash
# Restore specific modules only
uv run python lib/tools/sync_to_new.py --modules "Module 1,Module 2" --apply

# Restore specific content types only
uv run python lib/tools/sync_to_new.py --types pages,assignments --apply

# Shift dates forward by 365 days
uv run python lib/tools/sync_to_new.py --shift-days 365 --apply
```

**Lines of code estimate:** ~200 + tests

**Test results:** See `/tmp/file_restoration_final_strategy.md`
- Server-side copy: 100% success (5/5 files, 0.39s avg)
- Local upload: 100% success (1/1 file, 5s)
- Upload by URL: 0% success (unreliable, do not use)

---

### Phase 5: Field Hardening (S-sized, 3-5 days)
**Goal:** Production-ready reliability

**Scope:**
- Rollback capability (delete created items on error)
- Progress bar and detailed logging
- Validation checks (detect missing files, broken references)
- Safety guards (confirm before overwriting existing course)
- Resume capability (skip already-created items)

**Success criteria:**
- Tool recovers gracefully from API errors
- Can resume after network failure
- Warns if target course has existing content

**Deliverable:** Production-ready tool with full error handling

**Lines of code estimate:** ~100 + tests

---

## Detailed API Patterns

### 1. Module Creation

**Read from:** `.canvas/index.json` → `modules` array

**API endpoint:** `POST /api/v1/courses/:course_id/modules`

**Pattern:**
```python
def create_module(course_id: str, module_data: dict, token: str) -> dict:
    """Create module in target course.

    Args:
        module_data: {
            "title": "Module Title",
            "position": 1,
            "published": true,
            "unlock_at": "2026-01-13T00:00:00Z",  # optional
            "require_sequential_progress": false   # optional
        }

    Returns:
        Canvas module object with new canvas_id
    """
    url = f"{base_url}/api/v1/courses/{course_id}/modules"
    payload = {"module": module_data}

    response = _post(url, payload, token)
    return response.json()
```

**Existing pattern location:** Similar to `canvas_sync.py` module updates

---

### 2. Page Creation

**Read from:** `course/module-slug/page-name.html`

**API endpoint:** `POST /api/v1/courses/:course_id/pages`

**Pattern:**
```python
def create_page(course_id: str, page_data: dict, html_content: str, token: str) -> dict:
    """Create wiki page in target course.

    Args:
        page_data: {
            "title": "Page Title",
            "published": false,
            "front_page": false  # if homepage
        }
        html_content: Raw HTML from course/module-slug/page-name.html

    Returns:
        Canvas page object with page_url
    """
    url = f"{base_url}/api/v1/courses/{course_id}/pages"
    payload = {
        "wiki_page": {
            "title": page_data["title"],
            "body": html_content,
            "published": page_data.get("published", False),
            "front_page": page_data.get("front_page", False),
        }
    }

    response = _post(url, payload, token)
    return response.json()
```

**Existing pattern location:** `canvas_sync.py` lines 450-480 (page updates)

---

### 3. Module Item Linking

**Read from:** `.canvas/index.json` → `modules[].items` array

**API endpoint:** `POST /api/v1/courses/:course_id/modules/:module_id/items`

**Pattern:**
```python
def create_module_item(course_id: str, module_id: int, item_data: dict, token: str) -> dict:
    """Link content item to module.

    Args:
        item_data: {
            "title": "Item Title",
            "type": "Page",           # Page, Assignment, Quiz, Discussion, ExternalUrl
            "content_id": 123456,     # Canvas ID of the content (page_id, assignment_id, etc.)
            "position": 1,
            "indent": 0,              # 0-3 for visual hierarchy
            "completion_requirement": {  # optional
                "type": "must_view",     # must_view, must_submit, must_contribute, min_score
                "min_score": null
            }
        }

    Returns:
        Canvas module item object
    """
    url = f"{base_url}/api/v1/courses/{course_id}/modules/{module_id}/items"
    payload = {"module_item": item_data}

    response = _post(url, payload, token)
    return response.json()
```

**Notes:**
- Must create content FIRST (page, assignment, etc.)
- Then link it to module using returned content_id
- Canvas auto-generates module_item_id

---

### 4. Assignment Creation

**Read from:** `course/module-slug/assignment-name.json`

**API endpoint:** `POST /api/v1/courses/:course_id/assignments`

**Pattern:**
```python
def create_assignment(course_id: str, assignment_data: dict, token: str) -> dict:
    """Create assignment in target course.

    Args:
        assignment_data: {
            "name": "Assignment Title",
            "description": "<p>HTML description</p>",
            "points_possible": 100,
            "grading_type": "points",        # points, percent, letter_grade, pass_fail
            "submission_types": ["online_text_entry", "online_upload"],
            "due_at": "2026-02-15T23:59:00Z",
            "lock_at": "2026-02-20T23:59:00Z",
            "unlock_at": "2026-02-01T00:00:00Z",
            "published": false,
            "assignment_group_id": 12345     # Must create group first
        }

    Returns:
        Canvas assignment object with new assignment_id
    """
    url = f"{base_url}/api/v1/courses/{course_id}/assignments"
    payload = {"assignment": assignment_data}

    response = _post(url, payload, token)
    return response.json()
```

**Existing pattern location:** `canvas_sync.py` has assignment update patterns

**Date shifting:**
```python
def shift_date(date_str: str, days: int) -> str:
    """Shift ISO 8601 date forward by N days."""
    if not date_str:
        return None
    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    shifted = dt + timedelta(days=days)
    return shifted.isoformat().replace('+00:00', 'Z')
```

---

### 5. Assignment Group Creation

**Read from:** `.canvas/index.json` → `assignment_groups` array

**API endpoint:** `POST /api/v1/courses/:course_id/assignment_groups`

**Pattern:**
```python
def create_assignment_group(course_id: str, group_data: dict, token: str) -> dict:
    """Create assignment group (for weighted gradebook).

    Args:
        group_data: {
            "name": "Homework",
            "group_weight": 40.0,
            "position": 1
        }

    Returns:
        Canvas assignment group object with new id
    """
    url = f"{base_url}/api/v1/courses/{course_id}/assignment_groups"
    payload = group_data

    response = _post(url, payload, token)
    return response.json()
```

**Note:** Must create assignment groups BEFORE assignments (assignments reference group_id)

---

### 6. Classic Quiz Creation

**Read from:** `course/module-slug/quiz-name.json`

**API endpoint:** `POST /api/v1/courses/:course_id/quizzes`

**Pattern:**
```python
def create_quiz(course_id: str, quiz_data: dict, token: str) -> dict:
    """Create classic quiz in target course.

    Args:
        quiz_data: {
            "title": "Quiz Title",
            "description": "<p>Instructions</p>",
            "quiz_type": "assignment",        # practice_quiz, assignment, graded_survey
            "time_limit": 60,                 # minutes
            "allowed_attempts": 1,
            "points_possible": 100,
            "due_at": "2026-02-15T23:59:00Z",
            "published": false
        }

    Returns:
        Canvas quiz object with new quiz_id
    """
    url = f"{base_url}/api/v1/courses/{course_id}/quizzes"
    payload = {"quiz": quiz_data}

    response = _post(url, payload, token)
    return response.json()
```

**Quiz questions (separate API):**
```python
def create_quiz_question(course_id: str, quiz_id: int, question_data: dict, token: str):
    """Add question to quiz.

    Endpoint: POST /api/v1/courses/:course_id/quizzes/:quiz_id/questions
    """
    url = f"{base_url}/api/v1/courses/{course_id}/quizzes/{quiz_id}/questions"
    payload = {"question": question_data}

    response = _post(url, payload, token)
    return response.json()
```

**Existing pattern location:** `canvas_quiz_questions.py` has quiz question reading patterns

**NewQuizzes limitation:** Cannot create NewQuizzes via API (LTI tool). Skip with warning message.

---

### 7. Discussion Creation

**Read from:** `course/module-slug/discussion-name.json`

**API endpoint:** `POST /api/v1/courses/:course_id/discussion_topics`

**Pattern:**
```python
def create_discussion(course_id: str, discussion_data: dict, token: str) -> dict:
    """Create discussion topic in target course.

    Args:
        discussion_data: {
            "title": "Discussion Title",
            "message": "<p>Prompt</p>",
            "discussion_type": "threaded",    # side_comment, threaded
            "published": false,
            "assignment": {                   # if graded discussion
                "points_possible": 10,
                "due_at": "2026-02-15T23:59:00Z",
                "assignment_group_id": 12345
            }
        }

    Returns:
        Canvas discussion topic object
    """
    url = f"{base_url}/api/v1/courses/{course_id}/discussion_topics"
    payload = discussion_data

    response = _post(url, payload, token)
    return response.json()
```

---

### 8. File Upload (for course/_files/)

**Read from:** `course/_files/` directory

**API endpoint:** Two-step process (Canvas pattern)

**Pattern:**
```python
def upload_course_file(course_id: str, file_path: Path, token: str) -> dict:
    """Upload file to Canvas course files.

    Two-step process:
    1. POST to /api/v1/courses/:course_id/files (get upload URL)
    2. POST multipart to pre-signed URL

    Returns:
        Canvas file object with file_id
    """
    # Step 1: Request upload URL
    url = f"{base_url}/api/v1/courses/{course_id}/files"
    payload = {
        "name": file_path.name,
        "size": file_path.stat().st_size,
        "parent_folder_path": "imported_files"  # organize imports
    }
    response = _post(url, payload, token)
    upload_data = response.json()

    # Step 2: Upload to pre-signed URL
    with open(file_path, 'rb') as f:
        files = {'file': f}
        upload_response = requests.post(
            upload_data['upload_url'],
            data=upload_data['upload_params'],
            files=files
        )

    return upload_response.json()
```

**Existing pattern location:** `canvas_sync.py` has file upload logic (search for "pre-signed")

---

## Implementation Sequence (Phase 1 MVP)

### Step 1: Parse Local Course Content
```python
def load_course_content(canvas_dir: Path = Path(".canvas")) -> dict:
    """Load course structure from .canvas/index.json.

    Returns:
        {
            "course_id": "145706",
            "modules": [...],
            "files": {...},
            "assignment_groups": [...]
        }
    """
    index_path = canvas_dir / "index.json"
    with open(index_path) as f:
        return json.load(f)
```

### Step 2: Create Modules in Order
```python
def create_modules(target_course_id: str, modules: list, token: str) -> dict:
    """Create all modules in target course.

    Returns:
        Mapping of old slug → new Canvas module_id
    """
    slug_to_id = {}

    for module in sorted(modules, key=lambda m: m['position']):
        new_module = create_module(
            target_course_id,
            {
                "name": module["title"],
                "position": module["position"],
                "published": module.get("published", False),
            },
            token
        )
        slug_to_id[module["slug"]] = new_module["id"]
        print(f"✓ Created module: {module['title']}")

    return slug_to_id
```

### Step 3: Create Pages and Link to Modules
```python
def create_pages_in_modules(
    target_course_id: str,
    files: dict,
    module_mapping: dict,
    token: str
) -> dict:
    """Create all pages and link them to modules.

    Returns:
        Mapping of old page path → new Canvas page_id
    """
    page_mapping = {}

    # Filter for pages only
    pages = {path: meta for path, meta in files.items() if meta["type"] == "Page"}

    for page_path, page_meta in pages.items():
        # Read HTML content
        html_content = Path(page_path).read_text()

        # Create page
        new_page = create_page(
            target_course_id,
            page_meta,
            html_content,
            token
        )
        page_mapping[page_path] = new_page["page_id"]

        # Link to module
        module_slug = page_meta.get("module_slug")
        if module_slug and module_slug in module_mapping:
            create_module_item(
                target_course_id,
                module_mapping[module_slug],
                {
                    "title": page_meta["title"],
                    "type": "Page",
                    "content_id": new_page["page_id"],
                    "position": page_meta.get("module_item_position", 1),
                    "indent": page_meta.get("indent", 0)
                },
                token
            )
            print(f"  ✓ Linked page to module: {page_meta['title']}")

    return page_mapping
```

### Step 4: Preview Mode (Dry-run)
```python
def preview_restoration(course_content: dict):
    """Show what would be created without making changes."""
    print("Preview: What will be created\n")

    print(f"Modules ({len(course_content['modules'])}):")
    for module in course_content['modules']:
        print(f"  - {module['title']} (position {module['position']})")

    pages = [f for f in course_content['files'].values() if f['type'] == 'Page']
    print(f"\nPages ({len(pages)}):")
    for page in pages[:10]:  # Show first 10
        print(f"  - {page['title']} → Module: {page.get('module_slug', 'none')}")
    if len(pages) > 10:
        print(f"  ... and {len(pages) - 10} more pages")

    print("\nRe-run with --apply to create these items.")
```

### Step 5: Main Orchestration
```python
def main():
    parser = argparse.ArgumentParser(
        description="Deploy local course content to new Canvas course"
    )
    parser.add_argument("--apply", action="store_true",
                       help="Actually create content (default is dry-run)")
    parser.add_argument("--pages-only", action="store_true",
                       help="MVP: Create modules and pages only")
    args = parser.parse_args()

    # Load environment
    load_env()
    target_course_id = os.environ["CANVAS_COURSE_ID"]
    token = os.environ["CANVAS_API_TOKEN"]
    base_url = os.environ["CANVAS_BASE_URL"]

    # Safety check
    verify_course_access(target_course_id, token)
    if not is_sandbox_course(target_course_id):
        confirm = input("Target is PRODUCTION course. Continue? (yes/no): ")
        if confirm.lower() != "yes":
            print("Aborted.")
            return 1

    # Load course content
    print("Loading course content from .canvas/index.json...")
    course_content = load_course_content()

    # Preview mode
    if not args.apply:
        preview_restoration(course_content)
        return 0

    # Apply mode
    print(f"\nDeploying to course {target_course_id}...\n")

    # Phase 1: Create modules
    print("Step 1/2: Creating modules...")
    module_mapping = create_modules(target_course_id, course_content["modules"], token)

    # Phase 2: Create pages
    print("\nStep 2/2: Creating pages and linking to modules...")
    page_mapping = create_pages_in_modules(
        target_course_id,
        course_content["files"],
        module_mapping,
        token
    )

    print(f"\n✓ Restoration complete!")
    print(f"  - {len(module_mapping)} modules created")
    print(f"  - {len(page_mapping)} pages created")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

---

## Command-Line Interface

### Phase 1 (MVP)
```bash
# Preview what would be created (dry-run, default)
uv run python lib/tools/sync_to_new.py

# Apply: create modules and pages
uv run python lib/tools/sync_to_new.py --apply --pages-only
```

### Phase 2-3 (Full Feature)
```bash
# Create all content types (modules, pages, assignments, quizzes, discussions)
uv run python lib/tools/sync_to_new.py --apply

# Selective restore: specific modules only
uv run python lib/tools/sync_to_new.py --modules "Module 1,Module 3" --apply

# Selective restore: specific content types only
uv run python lib/tools/sync_to_new.py --types pages,assignments --apply

# Shift dates forward by 365 days (for next year's course)
uv run python lib/tools/sync_to_new.py --shift-days 365 --apply

# Resume after failure (skip already-created items)
uv run python lib/tools/sync_to_new.py --resume --apply
```

### Phase 4 (Production)
```bash
# With progress bar and detailed logging
uv run python lib/tools/sync_to_new.py --apply --verbose

# Rollback: delete all items created in last run
uv run python lib/tools/sync_to_new.py --rollback
```

---

## Testing Strategy

### Unit Tests
**Location:** `lib/tests/test_sync_to_new.py`

```python
def test_create_module_payload():
    """Verify module payload matches Canvas API spec."""
    module_data = {"title": "Test Module", "position": 1, "published": False}
    # Assert payload structure

def test_create_page_payload():
    """Verify page payload with HTML content."""
    # Assert wiki_page structure

def test_module_item_linking():
    """Verify module item payload for Page type."""
    # Assert type, content_id, position

def test_date_shifting():
    """Verify dates shift correctly by N days."""
    original = "2026-02-15T23:59:00Z"
    shifted = shift_date(original, 365)
    assert shifted == "2027-02-15T23:59:00Z"

def test_preview_mode():
    """Verify dry-run doesn't make API calls."""
    # Mock API calls, assert none were made
```

### Integration Tests (Sandbox Required)
```python
def test_restore_modules_to_sandbox():
    """End-to-end: restore 2 modules to sandbox course."""
    # Requires CANVAS_SANDBOX_ID in .env
    # Create 2 test modules
    # Verify they exist in Canvas

def test_restore_pages_with_html():
    """End-to-end: restore 3 pages with images."""
    # Create pages with <img> tags
    # Verify HTML renders correctly

def test_resume_after_partial_failure():
    """Test resume flag skips already-created items."""
    # Create 1 module, simulate failure
    # Re-run with --resume
    # Verify no duplicate modules
```

---

## Error Handling

### API Errors
```python
def safe_api_call(func, *args, max_retries=3):
    """Retry API calls with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func(*args)
        except requests.HTTPError as e:
            if e.response.status_code == 429:  # Rate limit
                wait = 2 ** attempt  # 1s, 2s, 4s
                print(f"Rate limited. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise Exception(f"Failed after {max_retries} retries")
```

### Validation Errors
```python
def validate_course_content(course_content: dict) -> list[str]:
    """Check for issues before starting restoration.

    Returns:
        List of warning messages
    """
    warnings = []

    # Check for missing files
    for path, meta in course_content["files"].items():
        if not Path(path).exists():
            warnings.append(f"Missing file: {path}")

    # Check for NewQuizzes (unsupported)
    for path, meta in course_content["files"].items():
        if meta.get("quiz_type") == "quizzes.next":
            warnings.append(f"NewQuiz '{meta['title']}' will be skipped (API unsupported)")

    # Check for broken module references
    module_slugs = {m["slug"] for m in course_content["modules"]}
    for path, meta in course_content["files"].items():
        module_slug = meta.get("module_slug")
        if module_slug and module_slug not in module_slugs:
            warnings.append(f"Item '{meta['title']}' references missing module '{module_slug}'")

    return warnings
```

### Rollback on Failure
```python
def rollback_created_items(created_items: dict, course_id: str, token: str):
    """Delete all items created during this run.

    Args:
        created_items: {"modules": [id1, id2], "pages": [id3, id4], ...}
    """
    print("Rolling back created items...")

    # Delete in reverse order (items before modules)
    for page_id in created_items.get("pages", []):
        _delete(f"{base_url}/api/v1/courses/{course_id}/pages/{page_id}", token)
        print(f"  Deleted page {page_id}")

    for module_id in created_items.get("modules", []):
        _delete(f"{base_url}/api/v1/courses/{course_id}/modules/{module_id}", token)
        print(f"  Deleted module {module_id}")

    print("Rollback complete.")
```

---

## Known Limitations

### Cannot Restore (Technical)
1. **NewQuizzes** — LTI tool, no REST API support
2. **External Tools** — LTI links are institution-specific
3. **Course navigation customizations** — Complex Canvas UI state
4. **Gradebook history** — Not course content
5. **Student submissions** — Not course content
6. **Blueprint course associations** — Requires Blueprint status

### Cannot Restore (Policy)
1. **Canvas IDs will differ** — New course gets new IDs (expected behavior)
2. **Dates may need adjustment** — Use `--shift-days` flag
3. **File URLs will differ** — Canvas generates new URLs for uploaded files

### Mitigations
- **NewQuizzes:** Skip with warning message, list them in summary
- **External Tools:** Warn user to manually reconfigure LTI links
- **Dates:** Provide `--shift-days` flag for automatic adjustment
- **File URLs:** Warn that embedded file links may need updating

---

## Progress Reporting

### Phase 1 (Simple)
```
Loading course content from .canvas/index.json...
✓ Loaded 5 modules, 42 pages

Deploying to course 145706...

Step 1/2: Creating modules...
✓ Created module: Week 1 - Introduction
✓ Created module: Week 2 - Foundations
... (5 total)

Step 2/2: Creating pages and linking to modules...
✓ Linked page to module: Welcome
✓ Linked page to module: Course Overview
... (42 total)

✓ Restoration complete!
  - 5 modules created
  - 42 pages created
```

### Phase 4 (Advanced with Progress Bar)
```
Loading course content from .canvas/index.json...
✓ Loaded 5 modules, 42 pages, 15 assignments, 3 quizzes

Validation check...
⚠ Warning: NewQuiz 'Midterm Exam' will be skipped (API unsupported)

Deploying to course 145706...

[▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░] 85% (51/60 items)
Creating assignment: Project 1... ✓

✓ Restoration complete! (2m 34s)
  - 5 modules created
  - 42 pages created
  - 15 assignments created (3 with rubrics)
  - 2 quizzes created (1 skipped: NewQuiz)

⚠ Manual steps required:
  - Reconfigure external LTI tool: Kaltura Media
  - Manually recreate NewQuiz: Midterm Exam
```

---

## File Structure

```
lib/tools/sync_to_new.py          # Main tool
lib/tests/test_sync_to_new.py     # Unit tests
docs/implementation/sync_to_new.md # This document
```

**Dependencies:**
- `canvas_sync.py` (API helpers, _load_index)
- `canvas_course_guard.py` (safety checks)
- `_env_loader.py` (load .env)
- Standard library: `argparse`, `json`, `pathlib`, `time`

---

## Example .canvas/index.json Structure

```json
{
  "course_id": "145706",
  "base_url": "https://byui.instructure.com",
  "modules": [
    {
      "canvas_id": 4662961,
      "title": "Week 1 - Introduction",
      "slug": "week-1-introduction",
      "position": 1,
      "published": true,
      "unlock_at": null,
      "items": [
        {
          "canvas_id": 45084830,
          "title": "Welcome",
          "type": "Page",
          "content_id": null,
          "position": 1,
          "indent": 0,
          "completion_requirement": {"type": "must_view"}
        }
      ]
    }
  ],
  "files": {
    "course/week-1-introduction/welcome.html": {
      "canvas_id": null,
      "type": "Page",
      "title": "Welcome",
      "page_url": "welcome",
      "module_item_id": 45084830,
      "module_slug": "week-1-introduction",
      "module_canvas_id": 4662961,
      "hash": "0b188e9b83f32f8a",
      "published": true
    },
    "course/week-1-introduction/assignment-1.json": {
      "canvas_id": 12345,
      "type": "Assignment",
      "title": "Assignment 1",
      "module_item_id": 45084832,
      "module_slug": "week-1-introduction",
      "points_possible": 100,
      "due_at": "2026-02-15T23:59:00Z",
      "published": false
    }
  },
  "assignment_groups": [
    {
      "id": 98765,
      "name": "Homework",
      "group_weight": 40.0,
      "position": 1
    }
  ]
}
```

---

## Next Steps

### Immediate (for field use)
1. **Prototype Phase 1 MVP** (1-2 weeks)
   - Implement module + page restoration
   - Test against user's actual course content
   - Ship for field testing

2. **Gather feedback** from field deployment
   - What content types are most critical?
   - Are dates shifting correctly?
   - Any edge cases discovered?

3. **Iterate to Phase 2-3** based on field needs
   - Add content types user actually needs
   - Refine selective restore flags
   - Improve error messages

### Long-term
- **Phase 4 hardening** for broader release
- **Document migration workflow** in main README
- **Create video tutorial** for common use cases
- **Add to cb_init.py onboarding** (recommend pulling course first)

---

## Success Metrics

**MVP success:**
- User can restore their course structure to new Canvas course
- Pages render correctly (no broken HTML)
- Modules appear in correct order
- Tool completes in < 5 minutes for 50-item course

**Full release success:**
- Handles all content types (pages, assignments, quizzes, discussions)
- Selective restore works (by module, by type)
- Date shifting works correctly
- Users prefer this over Canvas course copy (resilience to deletion)

---

**Document status:** Planning complete, ready for implementation
**Last updated:** 2026-07-10
**Next action:** Begin Phase 1 MVP implementation

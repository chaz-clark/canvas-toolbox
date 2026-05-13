# Canvas Content Sync Agent Guide

## Agent Instructions
1. Read this for mission, principles, quickstart, and pitfalls.
2. Parse `canvas_content_sync.json` for structured data, endpoint mappings, index schema, and operation procedures.
3. Keep this file lean — structured data (endpoint quirks, payload schemas, write procedures) lives in the JSON.

---

## Mission

**What it does**: Takes approved content (Markdown or HTML) from this repository and pushes it to Canvas LMS as pages and module items, keeping `.canvas/index.json` accurate with every Canvas ID, slug, and module item ID after each write.

**Why it exists**: The canvas_course_expert agent audits and proposes; this agent executes. Once Chaz approves a content change, this agent handles the two-step Canvas API sequence (create page → insert module item), avoids common silent failures, and maintains an auditable index so future sessions don't re-fetch what's already known.

**Who uses it**: Chaz Clark (BYU-Idaho instructor) when pushing finalized page content from local markdown files into a live Canvas course.

**Example**: "Chaz approves the Sprint 2 Overview page rewrite. The agent builds HTML via `build_canvas_content.py --strip-reader`, creates the page via Python, stores the returned slug in `.canvas/index.json`, then inserts the page as module item position 1 in the Sprint 2 module — also via Python. MCP was used to confirm the module ID from the index; no extra read call was needed."

---

## Agent Quickstart

1. **Load Index**: Read `.canvas/index.json`. Confirm `course_id` is present. If missing, ask Chaz and persist it.
2. **Identify Target**: What content is being pushed? (page title, source markdown path, target module, position).
3. **Build HTML**: Run `build_canvas_content.py --strip-reader` on the source markdown to produce Canvas-ready HTML.
4. **Propose**: Present the plan — resource type, target module, position, publish state. Wait for approval.
5. **Execute (writes via Python)**:
   - Create or update the page → capture slug and `canvas_id` → write to index.
   - Insert or update the module item → capture `module_item_id` → write to index.
6. **Verify**: Spot-check the index entry and confirm Canvas returned 200.

For endpoint schemas, payload formats, and index update procedures, see `canvas_content_sync.json`.

---

## File Organization: JSON vs MD

### This Markdown File Contains
- Mission and why this agent exists
- Design principles and their rationale
- Pitfalls explained narratively with root cause context
- External System Lessons — Canvas API non-obvious behaviors
- Workflow narrative and examples

### The JSON File Contains
- Canvas API endpoint mappings with `mcp_or_python` designations
- Payload schemas for every write operation
- Persistent index schema and update procedures
- Write operation step sequences (two-step page insert, rename steps)
- Validation checklists and test cases
- Error handling fallbacks

**Rule of Thumb**: If the agent needs to parse it to know what payload to send → JSON. If Chaz needs to understand why the agent behaves a certain way → MD.

---

## Domain Terms

| Term | Definition |
|------|------------|
| `CANVAS_INDEX` | `.canvas/index.json` — the local cache of Canvas IDs, slugs, and module item IDs for this course. Always check before making a read API call; always update after every write. |
| `course_id` | The numeric Canvas course ID from the course URL (`/courses/XXXXXX`). Must be in the index before any write can proceed. |
| `slug` | The URL-safe string Canvas assigns to a wiki page (e.g., `sprint-3-overview`). Returned in the `url` field of a page creation response. Required — not the numeric `page_id` — when inserting a Page as a module item. |
| `module_item_id` | The Canvas ID for an item's slot inside a module. Separate from the underlying resource ID. Required when renaming a module item title independently of the page or assignment name. |
| `--strip-reader` | Flag for `build_canvas_content.py` that removes reader-only blocks (slides, quiz placeholders, checklists, rubric tables, links to `.md` files) from the HTML before pushing to Canvas. Always use this flag for Canvas writes — never edit source markdown to strip content. |
| `two-step insert` | The Canvas API pattern for adding a page to a module: (1) create the page → capture slug; (2) insert module item using `page_url: slug`. A single call cannot do both. |

---

## Key Principles

### 1. MCP for Reads, Python for Writes

**Description**: Use the Canvas MCP server for GET operations during the planning phase. Use Python `requests` for all POST/PUT operations.

**Why**: Canvas API write responses return the full updated resource — a single page update response can be thousands of tokens. At scale (syncing 6 modules × multiple items), MCP write traffic alone consumes most of the context window before reasoning can continue. Python scripts call the same API and return only `{success, resource_id, status_code, slug}`.

**How**: During planning, use MCP to confirm module IDs (or check the index first — skip MCP entirely if the ID is already cached). For all writes, call Python functions in `canvas_api_tool.py` that return minimal summaries. See `canvas_content_sync.json → primary_data.canvas_api_endpoints` for the `mcp_or_python` field on each endpoint.

### 2. Index First, API Second

**Description**: Always check `.canvas/index.json` before making any read API call. Always update the index immediately after any write.

**Why**: Re-fetching module IDs on every session wastes tokens and makes sessions slower. The index is the durable cache that makes this agent fast. A stale index is worse than no index — if an ID is wrong, the agent will silently update the wrong resource.

**How**: On session start, load the index. For any needed ID (module, page, assignment), check the index first. If missing, use MCP to fetch and then write the result to the index. After every Python write call, update the index with the returned `canvas_id`, `slug`, and `module_item_id` before proceeding to the next step.

### 3. Confirm Before Mutating

**Description**: Propose what will be created or updated, wait for Chaz's approval, then execute one resource at a time.

**Why**: A Canvas API write is visible to enrolled students the moment it completes. A mis-pushed page or wrong module position cannot be undone with a single call — it requires a separate correction. Proposing first costs one turn; cleaning up a bad write costs much more.

**How**: For open-ended requests ("sync Sprint 3"), present the full plan (page titles, modules, positions, publish states) and wait for approval. For complete single-step requests ("push this markdown as the Sprint 2 Overview, position 1, published"), execute and report. See `canvas_content_sync.json → constraints.autonomy_guidance` for the exact rules.

### 4. Two-Step Page Insertion Is Not Optional

**Description**: Creating a Canvas page and inserting it as a module item are always two separate API calls. There is no single call that does both.

**Why**: The Canvas API has no atomic "create page and add to module" endpoint. Skipping step 2 leaves the page created but invisible to students navigating via Modules. Skipping step 1 (trying to create a module item pointing to a non-existent page) returns a silent 422 or creates a broken link.

**How**: Always follow the sequence in `canvas_content_sync.json → primary_data.write_procedures.create_page_and_insert`. Cache the slug from step 1 before making step 2 call. Never use the numeric `page_id` in the module item call — use `page_url: slug`.

### 5. Never Read Credentials from .env

**Description**: Auth is handled transparently by the Canvas MCP server. Do not read `CANVAS_ACCESS_TOKEN` from `.env` files or environment variables.

**Why**: The MCP server (DMontgomery40/mcp-canvas-lms) is already configured with credentials in Claude Code's environment. Reading `.env` directly is an unnecessary credential exposure pattern that this agent's design explicitly avoids.

**How**: MCP calls go through the configured server automatically. Python write scripts pass auth via the MCP-provided token — see `canvas_api_tool.py` for the implementation pattern. If MCP is unavailable, fall back to Python with credentials sourced from the MCP environment, not a .env file read.

### 6. Context Budget: Hard Limits Per Session

**Description**: Cap each session at 3 write operations (page creates or updates). Never pass raw Canvas API response bodies into the reasoning loop. Never re-fetch what's already in the index.

**Why**: Canvas API responses are large — a single `GET /modules` response listing all items is 4–8KB of JSON, which is 1,000–2,000 tokens. Six modules × re-fetch-per-session × write confirmations fills the context window before any reasoning happens. This is why the co-worker's canvas-sync.md agent required explicit context management workarounds — MCP write responses were consuming context faster than the agent could reason. Three writes per session keeps the budget sustainable.

**How**:
- **3 write operations per session max.** If Chaz asks to sync all 6 sprints in one session, split it across two: Sprints 1–3 first, then 2–6. Never attempt a full-course sync in a single session.
- **Never pass raw API response bodies to the reasoning loop.** Python write functions return `{success, canvas_id, status_code, slug}` only. If a write function returns more, strip it before surfacing the result. If MCP is used for a read, extract only the field needed (the module ID or slug), discard the rest.
- **Index is the read-cache — trust it.** If `.canvas/index.json` has a module `canvas_id`, use it directly. Do not re-fetch to confirm unless Chaz explicitly says the index may be wrong. A stale entry is corrected after a failed write, not by pre-emptive re-fetching.
- **One read call per missing ID, not one call per session.** If two IDs are missing from the index, make two targeted reads (one per resource), not one broad `GET /modules` that returns everything.

**What this prevents**: The "context blowup" pattern where each turn accumulates: MCP read (full list) + review HTML + Python confirmation + index update + next MCP read — and the context is full after 3 modules with nothing left for reasoning.

### 7. Graceful Degradation When MCP Is Unavailable

**Description**: If the Canvas MCP server is not available in the current environment, fall back to Python `requests` for read operations too. Do not block.

**Why**: The MCP server requires Docker (docker-compose.yml). In environments where Docker is not running, MCP calls will fail. The agent should still be able to operate using the Python fallback and the cached index.

**How**: On any MCP protocol error or "tool not found" response, switch to Python requests for that operation. The index cache minimizes how many fallback read calls are needed. Document the fallback in every session where it's used.

---

## Behavioral Discipline (core)

This agent follows the behavioral discipline defined in `make-ai-agents/knowledge/behavioral_discipline.md` and `make-ai-agents/knowledge/behavioral_discipline.json` (populated as a local clone in canvas-toolbox; see [AGENTS.md](../../AGENTS.md#existing-tooling)). The principles applicable to this agent type (single_write_workflow):

- **P-001 Read Before Claiming** (*Genchi Genbutsu*): Read the actual source before claiming anything about content, code, or system state. Training-data priors are not a substitute for reading what's in front of you. *Trigger*: Every claim about content, code, data, or system state.
- **P-002 Plan Before Acting** (*Nemawashi + TBP*): For any state-changing task with more than one step, propose the plan and wait for user confirmation before non-reversible action. The plan is a draft — refine through back-and-forth before committing. *Trigger*: Any task with more than one step that changes state.
- **P-003 Stop on Defect** (*Jidoka + Andon*): First failed test, first failed precondition, first ambiguity that can't be resolved → stop. Don't paper over. Don't retry blindly. Surface the issue: 'I cannot proceed because X.' *Trigger*: Any failure, any unresolved ambiguity, any precondition the agent can't verify.
- **P-004 Find the Root Cause** (*5 Whys*): When something doesn't work as expected, walk the chain of causation. Stop when the answer is structural — that's where the fix lives. *Trigger*: Any bug, any unexpected output, any 'this should work but doesn't.'
- **P-006 Document the Change** (*A3*): For any non-trivial change, structure the report so a non-technical reviewer can audit it without reading the diff. Use the A3 template (see templates.a3_change_report). *Trigger*: Any change to more than one file or page; any change with non-obvious downstream effects; any change a reviewer would want to inspect.
- **P-007 Pull, Don't Push** (*JIT + 3 Ms (Muda/Mura/Muri)*): Generate exactly what was asked. No speculative features. The discipline isn't laziness — it leaves room for the user to decide what comes next. *Trigger*: Every change. Default is minimum scope.
- **P-008 Mistake-Proof Outputs** (*Poka-yoke + Standard Work*): Format outputs consistently across runs so the user can predict what they'll see. Decide once for the agent: JSON for parsed output, Markdown for human-read output, Markdown+JSON code block for both. *Trigger*: Any output a downstream consumer (human or system) parses or compares across invocations.
- **P-009 Reflect, and Tell the User** (*Hansei + Yokoten*): At the end of any task that produced a surprise, took longer than expected, or revealed non-obvious behavior, name the lesson in the response ('Worth noting: ...') AND append it to the agent's spec MD External System Lessons section. *Trigger*: End of any task with surprise, unexpected duration, or non-obvious external system behavior.
- **P-010 Respect the User's Intent** (*Respect for People + Hoshin Kanri*): Two failure modes: (a) anti-substitution — don't override or reinterpret the user's stated goal silently; (b) anti-drift — in long sessions, every action should still trace to the original goal; surface drift when it happens. *Trigger*: Any action beyond the literal request (anti-substitution); any long-running session every ~5 turns (anti-drift).

**Hard rule on overrides**: before skipping any principle, the agent must state in one sentence which principle is being skipped and why. Principles [P-001, P-003, P-007, P-010] have no override.

P-005 (Decompose When Necessary) is omitted: single_write_workflow is by definition a one-step state change with confirmation, so decomposition discipline doesn't apply.

The Key Principles section above operationalizes this discipline for the Canvas content-sync workflow. Principle 3 (Confirm Before Mutating) is P-003/P-007 in concrete form; Principle 4 (Two-Step Page Insertion Is Not Optional) is P-008 — the agent must keep the Canvas page + module item write atomic from the user's perspective even though it's two API calls.

For the full principle definitions, examples, and override rationale, see `make-ai-agents/knowledge/behavioral_discipline.md`.

---

## How to Use This Agent

### Prerequisites
- Python 3.10+
- `.canvas/index.json` with `course_id` populated (or be ready to provide it)
- Canvas MCP server running (preferred) or Python fallback available
- Source markdown files in the repo for any content being pushed

### Existing Tooling

| Tool / File | Purpose | When to use |
|---|---|---|
| `.canvas/build_canvas_content.py` | Converts markdown to Canvas HTML using `.canvas/template.html`; `--strip-reader` removes reader-only blocks | Always run before pushing page content to Canvas |
| `.canvas/index.json` | Persistent cache of Canvas IDs, slugs, and module item IDs | Check before any read API call; update after every write |
| `canvas_api_tool.py` | Python implementation for all Canvas write operations; returns minimal summaries | All POST and PUT operations |
| `canvas_course_expert.json → primary_data.canvas_api_endpoints` | Canonical endpoint reference with payload schemas and quirks | Cross-reference when building a write request |

**Reuse-first rule**: `build_canvas_content.py` already handles `<% slides %>`, `<% quiz %>`, `<% links %>`, `<% checklist %>`, and `<% editor %>` tags. Do not write new preprocessing logic — extend `preprocess()` in that script if new tags appear.

### Basic Usage

**Step 1: Load the index**
```python
import json
index = json.load(open(".canvas/index.json"))
course_id = index["course_id"]  # Must be non-null before proceeding
```

**Step 2: Build HTML from markdown**
```bash
python .canvas/build_canvas_content.py sprint-3-overview.md --strip-reader --output /tmp/sprint-3-overview.html
```

**Step 3: Push via Python (write operations only)**
```python
# Example: create_page returns {success, canvas_id, slug, status_code}
result = create_page(course_id, title="Sprint 3 Overview", body=html, published=True)
# Then insert as module item
insert_module_item(course_id, module_id=index["modules"]["Sprint 3: ..."]["canvas_id"],
                   title="Sprint 3 Overview", page_url=result["slug"], position=1)
```

**Step 4: Update the index immediately after each write**
```python
index["pages"][result["slug"]] = {
    "canvas_id": result["canvas_id"],
    "title": "Sprint 3 Overview",
    "published": True
}
json.dump(index, open(".canvas/index.json", "w"), indent=2)
```

**Step 5: Verify**
- Index entry exists with non-null `canvas_id` and `slug`
- Python returned `status_code: 200` for each call
- If anything is ambiguous, spot-check in Canvas before marking done

---

## Common Pitfalls and Solutions

### 1. Using `page_id` Instead of `slug` for Module Item Insertion

**Problem**: The module item is created but links to the wrong page or returns a 404 when students click it.

**Why it happens**: Canvas page creation returns both a numeric `page_id` and a `url` field (the slug). Passing the `page_id` as `content_id` in a `type: Page` module item call will silently succeed but link nothing useful — or link the wrong resource entirely.

**Solution**: For `type: Page` module items, always use `page_url: <slug>`, never `content_id`. The slug is the `url` field in the page creation response (e.g., `sprint-3-overview`). Store it in the index immediately.

### 2. Pushing Content to a Live Course Without Checking Enrollment

**Problem**: A content push causes immediate confusion for students who are actively working in the module.

**Why it happens**: This agent has no awareness of enrollment state or term dates. It pushes when asked.

**Solution**: Before any push to a published module, confirm with Chaz whether students are currently active. For mid-semester pushes, prefer unpublishing the module item first, pushing, then republishing. Check `course_id` in the index against Canvas term dates if uncertain.

### 3. Forgetting the Second Step of a Rename

**Problem**: Chaz renames a page or assignment, but the module still displays the old title.

**Why it happens**: Canvas module item `title` is independent of the underlying resource name. Updating the page or assignment name does not cascade to the module item.

**Solution**: Every rename requires two PUT calls: (1) update the resource (page or assignment) name, and (2) update the module item `title` via `PUT /courses/:id/modules/:module_id/items/:item_id`. See `canvas_content_sync.json → primary_data.write_procedures.rename_resource`.

### 4. Not Running `--strip-reader` Before Pushing

**Problem**: Reader-only content (slide embeds, quiz placeholders, rubric tables, links to `.md` files) appears in the live Canvas page and confuses students.

**Why it happens**: The source markdown contains blocks intended only for the instructor's local reading environment. Without `--strip-reader`, these blocks are converted to raw HTML and pushed as-is.

**Solution**: Always run `build_canvas_content.py --strip-reader` before any Canvas push. Never edit the source markdown to remove these blocks — the flag is the correct removal mechanism.

### 5. Index Out of Sync After a Failed Write

**Problem**: The index shows a `canvas_id` for a resource that doesn't actually exist in Canvas (write failed mid-sequence).

**Why it happens**: If a Python write returns an error after the index was already updated optimistically, or if a session is interrupted mid-operation, the index can become stale.

**Solution**: Only write to the index after receiving a `status_code: 200` from the Python write call. If a write fails, log the failure in `change_ledger` with `status: failed` and do not write the `canvas_id` to the pages/modules/assignments sections. On the next session, the missing ID will trigger a re-attempt.

### 6. Parallel Tool Calls for a Sequential Two-Step Operation

**Problem**: The agent attempts to create a page and insert the module item simultaneously, before the slug is available.

**Why it happens**: Parallel tool use is efficient for independent operations. The two-step page insert is not independent — step 2 requires the slug from step 1's response.

**Solution**: Disable parallel tool use for write sequences. `disable_parallel_tool_use` is set to `true` in `canvas_content_sync.json → implementation.llm_agent.parameters`. Never attempt both steps of the two-step insert in a single parallel call batch.

---

## External System Lessons

### Canvas API — Page Module Items Require Slug, Not Page ID

**Behavior**: When inserting a page as a module item (`type: Page`), the API requires `page_url` set to the URL slug (e.g., `sprint-3-overview`), not the numeric `page_id` as `content_id`. The API does not return an error — it silently creates a broken or mis-linked module item.

**Why it matters**: This failure is invisible at write time. The agent sees `200 OK` and believes the operation succeeded. Students see a broken or missing link in the module.

**How to handle it**: After every `POST /courses/:id/pages`, immediately capture the `url` field (not `id`) from the response and store it in the index. Use only `page_url: <slug>` for the subsequent module item POST.

### Canvas API — Quiz Points Require a Separate PUT After Creation

**Behavior**: Creating a quiz via `POST /courses/:id/quizzes` with `points_possible` in the body does not reliably set the linked gradebook assignment's point total. The quiz and its assignment both show 0 points until a separate `PUT /courses/:id/quizzes/:quiz_id` with `quiz[points_possible]` is sent.

**Why it matters**: Students and instructors see 0 points in the gradebook even though the quiz was created successfully. This looks like a bug but is a required second API call.

**How to handle it**: Always follow a quiz creation with a separate `update_quiz_points` call after all questions are added. Never rely on the initial POST to set points. See `canvas_content_sync.json → primary_data.canvas_api_endpoints.update_quiz_points`.

### Canvas API — Assignment Group Bodies Must Be Flat (Not Nested)

**Behavior**: `POST /courses/:id/assignment_groups` expects `name`, `group_weight`, and `position` as flat top-level fields in the request body. Wrapping them in `assignment_group: { ... }` causes the name and weight to be silently ignored — the group is created with default values, not the ones specified.

**Why it matters**: The group appears to be created successfully (200 OK, returns an object), but with the wrong name and 0% weight. Gradebook weights are wrong and the group name is a Canvas default string.

**How to handle it**: Send flat JSON bodies for assignment group operations. See `canvas_content_sync.json → primary_data.canvas_api_endpoints.create_assignment_group` for the correct payload schema.

### Canvas API — Renames Require Two Independent Updates

**Behavior**: Updating a page title or assignment name does NOT update the title displayed for that item in the Modules view. The module item `title` field is stored independently and must be updated via a separate `PUT /courses/:id/modules/:module_id/items/:item_id` call.

**Why it matters**: The resource is renamed in the page editor and gradebook, but the Modules view (the primary student navigation) still shows the old name. Students navigate by modules — this is what they see.

**How to handle it**: Every rename operation is two calls. Always update the module item title after updating the resource. The `module_item_id` must be stored in the index (under the assignment or page entry) to make this call possible without a new read.

### Canvas API — `published: false` on Module Item ≠ Unpublished Content

**Behavior**: Setting `published: false` on a module item hides it from the module list view. The underlying page or assignment remains accessible via direct URL — it is NOT truly hidden from students with the direct link.

**Why it matters**: Instructor-only notes pushed with `published: false` on the module item may still be discoverable via URL. Content that must not be student-visible requires both the module item AND the underlying resource to be unpublished.

**How to handle it**: For instructor-only content, always unpublish both the module item and the underlying page or assignment. Document this in the index entry with a note. Verify in Student View when the content is sensitive.

---

## Examples

### Example 1: Pushing a New Overview Page to a Module

**Scenario**: The Sprint 3 Overview page has been rewritten locally. Chaz wants it pushed as position 1 in the Sprint 3 module, published.

**Input**: `sprint-3/overview.md` is the source. Module `Sprint 3: SFTP DAG + DW SQL LAB (W05 - W06)` already has `canvas_id: 4595059` in the index.

**Approach**: Agent checks index for existing page slug (not present → new creation). Builds HTML via `--strip-reader`. Proposes the plan (new page, module 4595059, position 1, published). After approval, calls `create_page` via Python, captures slug, inserts module item via Python, updates index.

**Output (index update)**:
```json
"pages": {
  "sprint-3-overview-sftp-dag-w05-w06": {
    "canvas_id": 16700123,
    "title": "Sprint 3 Overview: SFTP DAG (W05-W06)",
    "published": true,
    "module_item_id": 88234501
  }
}
```

**Code**: See `canvas_content_sync.json → primary_data.write_procedures.create_page_and_insert`

### Example 2: Renaming a Page That Already Exists in Canvas

**Scenario**: "Sprint 2 Overview" needs to be renamed to "Sprint 2 Overview: API DAG + DW SQL Lab".

**Approach**: Index lookup gives `canvas_id` and `module_item_id` for the existing page. Agent proposes two calls: (1) `PUT /pages/:slug` to update title; (2) `PUT /modules/:id/items/:module_item_id` to update module item title. After approval, executes both and updates the index entry.

**Code**: See `canvas_content_sync.json → primary_data.write_procedures.rename_resource`

### Example 3: MCP Unavailable — Fallback to Python for Reads

**Scenario**: Docker is not running. The MCP server is unavailable. Chaz wants to push a page but the module ID for Sprint 4 is not yet in the index.

**Approach**: On MCP failure, agent switches to Python `requests` GET call to fetch modules list. Caches the returned module IDs to the index. Proceeds with all writes via Python as normal. Documents the fallback in the session summary.

**Code**: See `canvas_content_sync.json → error_handling.fallbacks`

---

## Validation and Testing

### Quick Validation
1. Run a dry-run push on a known page: verify HTML output from `build_canvas_content.py --strip-reader` before sending to Canvas.
2. After any write, verify `status_code: 200` in the Python return and confirm the index entry was updated.
3. Confirm the page slug in the index matches what Canvas shows in the page URL.

### Comprehensive Validation
For detailed pre/post checklists, see `canvas_content_sync.json → validation`.

The validation section includes:
- Pre-run checklist (index has `course_id`, source file exists, `--strip-reader` applied)
- Post-run checklist (index updated, module item created, slug captured)
- Success criteria for page creation, module item insertion, and rename operations
- Test cases with expected `status_code` and index state

---

## Quality Bar

- [ ] Index has `course_id` populated before any write proceeds
- [ ] Every page write captures slug from response and stores it in the index before the module item call
- [ ] `build_canvas_content.py --strip-reader` was run on every markdown source before push — never raw markdown
- [ ] Every rename issues both the resource update AND the module item title update
- [ ] Python write calls return `status_code: 200` before index is updated (never optimistic writes)

---

## Resources and References

### Agent Files
- **`canvas_content_sync.json`**: Endpoint mappings, payload schemas, write procedures, validation
- **`canvas_api_tool.py`**: Python implementation for all Canvas write operations
- **`.canvas/index.json`**: Runtime state — Canvas IDs, slugs, module item IDs for this course
- **`.canvas/build_canvas_content.py`**: Markdown-to-HTML converter with `--strip-reader` flag

### Related Agents
See `canvas_content_sync.json → cross_references.related_agents` for:
- `canvas_course_expert`: The audit agent that identifies what needs to change — this agent applies those changes
- `canvas-sync`: The predecessor prompt this agent was adapted from

### Canvas API Reference
- Canvas REST API docs: https://canvas.instructure.com/doc/api/
- MCP server: DMontgomery40/mcp-canvas-lms (docker-compose.yml in this repo)

---

## Quick Reference Card

| Aspect | Value |
|--------|-------|
| **Purpose** | Push approved page content from local markdown to Canvas LMS; keep `.canvas/index.json` accurate |
| **Input** | Source markdown file path, target module, position, publish state |
| **Output** | Canvas page created/updated + module item inserted/updated + index updated |
| **Agent Type** | `llm_agent` |
| **Complexity** | standard |
| **Key Files** | `canvas_content_sync.json`, `canvas_api_tool.py`, `.canvas/index.json` |
| **Quickstart** | Check index → build HTML (`--strip-reader`) → propose → create page (Python) → insert module item (Python) → update index |
| **Common Pitfall** | Using `page_id` instead of `slug` for module item insertion — silent failure, broken link |
| **Dependencies** | `requests>=2.31.0`, Canvas MCP server (Docker), `canvas_api_tool.py` |
| **Temperature** | 0.1 (all tool-use and write phases) |

# Canvas Blueprint Sync Agent Guide

## Agent Instructions
1. Read this for mission, workflow, and pitfalls.
2. Parse `canvas_blueprint_sync.json` for endpoint schemas, field maps, and validation data.
3. This agent is Python-first — the heavy lifting is done by `lib/tools/blueprint_sync.py`. The agent role is to orchestrate, validate, and report.

---

## Mission

**What it does**: One-way sync of the master course to the Blueprint course in Canvas. Master is always the source of truth. Blueprint is overwritten — content, settings, homepage, syllabus.

**Why it exists**: Each semester a new course is created from the Blueprint. If the Blueprint is stale, every new section starts from outdated content. This sync ensures Blueprint always reflects the polished master.

**Who uses it**: Instructor or TA at end of semester, or any time the master course is significantly updated.

**What it also syncs**: Due dates, lock_at, and unlock_at from master assignments/quizzes/discussions. Blueprint dates should reflect the current master semester so new clones start with a realistic baseline.

**What it does NOT do**: Modify module order, touch student data, or set `late_policy` (requires Canvas admin token — set manually in Blueprint Settings).

---

## Agent Quickstart

1. **Verify master is current** — confirm `canvas_sync.py --status` shows nothing to push. Master must be fully synced to Canvas before blueprint sync runs.

2. **Pull blueprint structure** — run `blueprint_sync.py --pull` to do a full init of `blueprint_course/` (mirroring what `canvas_sync.py --init` does for master). Fetches all items + content including current dates. Required before first push and after any module restructuring.

3. **Check coverage** — run `blueprint_sync.py --status` to confirm mapping coverage and date coverage. Investigate any unmapped master items before proceeding.

4. **Push** — run `blueprint_sync.py --push`. Full overwrite: settings → homepage → syllabus → all mapped module items with content + dates.

5. **Verify** — spot-check 2–3 pages in Canvas Blueprint student view. Confirm grading scheme in Blueprint course settings. Set `late_policy` manually (requires admin token — instructor token returns 403).

---

## File Organization: JSON vs MD

### This Markdown File Contains:
- Mission and sync philosophy
- Quickstart workflow
- What is and is not synced
- Pitfalls and external system quirks

### The JSON File Contains:
- Canvas API endpoint schemas for blueprint operations
- Field mapping: master JSON keys → blueprint API payload keys
- Validation checklist for post-sync verification
- Known unmappable item types and their handling

---

## Key Principles

### 1. Master Is Always Right
**Description**: Never read blueprint content as a source of truth. Only the master `course/` folder drives the sync.
**Why**: Blueprint may have been touched directly in Canvas UI. Pulling from blueprint would corrupt the master.
**How**: `blueprint_sync.py` reads from `course/` and `.canvas/index.json` exclusively. `blueprint_course/` is a read-only mirror of what Blueprint currently holds — it is never the source of truth.

### 2. --pull Is a Full Init, Not Just a Mapping Step
**Description**: `--pull` fully mirrors the blueprint into `blueprint_course/` (same pattern as `canvas_sync.py --init` for master). It fetches all modules, items, and content — including current dates. `blueprint_index.json` stores canvas IDs, blueprint filepaths, and current blueprint dates for comparison.
**Why**: Title-matching alone was brittle. Having a full local mirror means you can compare `index.json` (master) vs `blueprint_index.json` (blueprint) field by field, including dates. It also means --pull is the correct diagnostic tool before --push.
**How**: Run `--pull` before every `--push`. Always re-pull after any direct Canvas edits to the Blueprint module structure.

### 3. Dates Are Synced from Master
**Description**: `--push` includes `due_at`, `lock_at`, and `unlock_at` from master files in every assignment, quiz, and discussion payload.
**Why**: Blueprint should reflect the master semester dates so that new course clones start with a realistic baseline. The semester setup agent then adjusts dates for each new section. Without this, Blueprint accumulates stale dates from when it was first set up.
**How**: Assignments, quizzes, and discussions in master JSON files include `due_at`/`lock_at`/`unlock_at`. These are passed directly in the API payload on `--push`.

### 4. Propose Before Execute (for agent runs)
**Description**: When the agent is driving the sync, show a status report and confirm with the user before running `--push`.
**Why**: Push is a full overwrite including dates. Confirming coverage (items mapped, items with due_at) before executing prevents surprises.
**How**: Run `--status`, present the counts, ask for confirmation, then run `--push`.

### 5. Titles Are the Identity, IDs Are Course-Specific
**Description**: Canvas IDs are unique per course — the same assignment has a different ID in master, blueprint, and every cloned section. Titles are stable across courses. When reconciling content across courses, always match by title first; only use IDs within a single course context.
**Why**: Matching by ID across courses will always fail. Matching by title may surface same-named items with different IDs — that is expected and correct. The duplicate-deletion lesson: when two items share a title and one is in a module, the floating one is the orphan regardless of which ID is "older."
**How**: All sync scripts use exact title matching for cross-course mapping. Never hard-code a canvas_id obtained from one course and apply it in another. When the quality check flags a floating published item, check if something with the same title is already in a module before treating it as missing.

### 6. Every Module Item Must Exist in Both the Course AND a Module
**Description**: Adding content to Canvas requires two steps: (1) creating the item in the course (assignment/quiz/page), and (2) linking it as a module item. An item that exists in the course but is not in any module is invisible to students.
**Why**: Students navigate entirely through modules. A published assignment not linked in any module appears in Grades but has no way for students to access it — they see the due date but cannot open it.
**How**: Any time you create or add content — via API, tool, or agent — confirm both steps completed. The quality check (`course_quality_check.py`) flags published items not linked in any module. After any push, run the quality check to catch gaps.

---

## Behavioral Discipline (core)

This is a **deterministic Python script** (`lib/tools/blueprint_sync.py`) — no LLM at runtime. The v3.6 behavioral discipline therefore applies to the **operator** invoking the sync: either a human (running the CLI directly) or an upstream LLM agent (e.g., `canvas_course_expert` orchestrating the sync). Interaction pattern: **multi_step_batch** (the push decomposes into many per-item Canvas PUTs).

Full source: `make-ai-agents/knowledge/behavioral_discipline.md`. All 10 principles apply to the operator:

- **P-001 Read Before Claiming** — Read `canvas_sync.py --status` and `blueprint_sync.py --status` output before claiming the master is current or the blueprint is mapped. Don't assert "everything looks good" without reading the actual coverage counts.
- **P-002 Plan Before Acting** — Always run `--status` and present coverage to the user before `--push`. The status output IS the batch plan. Wait for explicit approval.
- **P-003 Stop on Defect** — If `--pull` produces many unmapped items, if `--status` shows <80% mapping coverage, or if a push logs FAILED lines — stop and surface the issue. Don't proceed assuming "it'll be fine."
- **P-004 Find the Root Cause** — When a page 404s on push: don't retry. Find why (title renamed in Canvas UI? page deleted? blueprint restructured?). Re-pull mappings, then push.
- **P-005 Small Steps, Evenly Sized** — The script already enforces this (each item is its own PUT). The operator must not bypass this by running `--push` repeatedly to "force through" failures — investigate failures before re-running.
- **P-006 Document the Change** — The final report (pushed count, failed count, settings results) is the A3. A non-technical reviewer should be able to read it without inspecting the API responses.
- **P-007 Pull, Don't Push** — Don't speculatively edit Blueprint content in Canvas UI between pulls — the script will overwrite it on next push. If a Blueprint-only change is needed, it belongs in master first.
- **P-008 Mistake-Proof Outputs** — Same `--status` format, same final report format every run. The operator should know what to expect.
- **P-009 Reflect, and Tell the User** — If a push surfaced something new (e.g., a NewQuiz that couldn't be content-pushed via REST, or an unexpected 403 pattern), name it and append to "External System Lessons" in this file.
- **P-010 Respect the User's Intent** — Don't run `--push` mid-semester unless explicitly asked (active student cohorts using the Blueprint may be affected by content-lock changes). Don't drift into "while I was in there I also synced dates differently."

**No-override principles:** P-001, P-003, P-007, P-010 apply unconditionally.

**BD-QC checks N/A for this agent:** BD-QC-002 (no system_prompt — no LLM at runtime) and BD-QC-004 (no LLM tool enumeration — behavior is defined by the Python source).

---

## How to Use This Agent

### Prerequisites
- `BLUEPRINT_COURSE_ID` set in `.env`
- Master course fully synced: `canvas_sync.py --status` → clean
- Blueprint course exists in Canvas and instructor token has write access to it

### Existing Tooling

| Tool | Purpose | When to use |
|---|---|---|
| `lib/tools/blueprint_sync.py --pull` | Full init: mirrors blueprint into `blueprint_course/`, builds mapping with IDs + dates | Before every push; required on first run and after module changes |
| `lib/tools/blueprint_sync.py --push` | Full overwrite: master content + dates → blueprint | After any master course update |
| `lib/tools/blueprint_sync.py --status` | Shows mapping coverage + date coverage | Before push, to confirm coverage |
| `lib/tools/canvas_sync.py --status` | Confirms master is fully synced | Before blueprint sync |
| `blueprint_course/` | Read-only mirror of current blueprint state (like `course/` for master) | Reference / comparison |
| `.canvas/blueprint_index.json` | master filepath → blueprint canvas ID + date mapping | Read-only reference |
| `.canvas/blueprint_log.md` | Append-only audit trail | Review after push |

### Commands

```bash
# 1. Confirm master is clean
uv run python lib/tools/canvas_sync.py --status

# 2. Pull blueprint structure (build/refresh mapping)
uv run python lib/tools/blueprint_sync.py --pull

# 3. Check coverage
uv run python lib/tools/blueprint_sync.py --status

# 4. Sync
uv run python lib/tools/blueprint_sync.py --push
```

---

## First-Time Setup Lessons (New Course or New Blueprint)

These lessons came from the first ITM 327 blueprint sync and apply to any future course.

### 1. Master Index Must Have Titles Before --pull
Title-matching is how master items are mapped to blueprint items. If the master index was built before title tracking was added to `canvas_sync.py`, all titles will be `None` and --pull will match 0 items.
**Fix**: Ensure `canvas_sync.py --pull` has been run after the title-tracking code was added. Check that `index.json` entries have `"title": "..."` (not null) before running blueprint --pull.

### 2. Blueprint Has Draft-Era Dirty Titles
When a course is first built in Canvas, items often have questions or comments embedded in their titles (e.g., `"Needs context & instructions. How do students set up Notebook? W01 NotebookLM: CH1-2"`). These won't title-match anything in master.
**Fix before --pull**: Rename dirty Blueprint items via API or Canvas UI so titles match master clean names. API method:
- For NewQuiz/Assignment: `PUT /courses/:bp_id/assignments/:content_id {"assignment": {"name": "Clean Title"}}`
- For ExternalTool/module items: `PUT /courses/:bp_id/modules/:mid/items/:item_id {"module_item": {"title": "Clean Title"}}`

### 3. New Items in Master Won't Exist in Blueprint
If master was updated after the blueprint was created (e.g., new sprint overview pages were added), those items won't exist in blueprint at all — they appear in `unmapped_master`. `--push` will create them as new Pages and add them to the correct module. Assignments, Discussions, and Quizzes that are unmapped are skipped (create manually in Canvas if needed).

### 4. Stale Filename Duplicates in Master
Draft-era files often have stale names that survive a `--pull` because they still have valid hashes. If you see two master index entries pointing to the same canvas_id, the old-named file needs to be deleted from disk and from `index.json`. Run `--pull` after deleting to get a clean state.

### 5. late_policy Requires Admin Token
`PATCH /courses/:id/late_policy` returns 403 for instructor tokens. This is a Canvas permission boundary. Set late_policy manually in Blueprint → Settings → Gradebook, or ask Canvas admin to apply it. Document the desired policy in `course/_course.json` for reference.

### 6. Blueprint Dates Are Stale from Initial Setup
Blueprint may have semester-specific dates from when it was first created (or old semester dates). Master has the correct current dates. Always run `--push` after initial blueprint setup to get master dates into blueprint — the semester setup agent will then adjust dates for each new cloned section.

---

## Common Pitfalls and Solutions

### 1. Low Mapping Coverage After --pull

**Problem**: `--status` shows many master items unmapped to blueprint.

**Why it happens**: Blueprint item titles don't exactly match master item titles. Title matching is case-sensitive and exact. A renamed item in either course breaks the match.

**Solution**: Check `unmapped_master` in `blueprint_index.json`. If items were renamed in master, they won't match old blueprint titles. Options: (a) rename the item in Blueprint Canvas UI to match master, then re-pull, or (b) manually add the mapping to `blueprint_index.json` under `"mappings"`.

### 2. Push Succeeds But Blueprint Looks Wrong

**Problem**: Blueprint pages show old content even after a successful push.

**Why it happens**: Canvas caches page content aggressively. Also, the Blueprint course may be locked by Canvas Blueprint locking — instructors who created sections from Blueprint may have content locked.

**Solution**: Wait 1–2 minutes and hard-refresh in Canvas. If locked, check Blueprint course settings → Blueprint → unlock content before syncing.

### 3. Mapping Goes Stale After Blueprint Module Restructure

**Problem**: Items push to the wrong Blueprint page or fail with 404.

**Why it happens**: `blueprint_index.json` was built when Blueprint had a different structure. Canvas item IDs don't change when items are renamed, but `page_url` slugs do.

**Solution**: Re-run `--pull` to rebuild the mapping. Always re-pull after any direct Canvas edits to the Blueprint module structure.

### 4. Settings Push Returns 200 But Doesn't Apply

**Problem**: `late_policy` or `grading_standard_id` appears to push successfully but Blueprint settings don't change.

**Why it happens**: Blueprint courses in Canvas can have settings inherited from the account level that override course-level settings.

**Solution**: Verify in Blueprint → Settings → Course Details that the setting is editable at course level. If grayed out, it's account-controlled — contact Canvas admin.

---

## External System Lessons

### Canvas Blueprint Course — Content Locking

**Behavior**: When a Blueprint course pushes content to associated courses, it can lock that content so instructors of child courses can't edit it. This is a Canvas Blueprint feature unrelated to this tool.

**Why it matters**: If Blueprint locking is enabled, running `blueprint_sync.py --push` may trigger a Blueprint "sync" in Canvas that locks content in all child sections. This is usually desirable but should be done intentionally.

**How to handle it**: Check Blueprint settings in Canvas before push if child sections are active (mid-semester). Prefer to sync Blueprint at start of semester before sections are created.

### Canvas API — Page URL vs Canvas ID for Pages

**Behavior**: Pages are identified by `page_url` (a slug), not a numeric canvas ID. The slug can change if the page title is edited in Canvas.

**Why it matters**: If a Blueprint page is renamed in Canvas UI, its `page_url` changes. The mapping in `blueprint_index.json` stores the old slug and pushes fail silently with a 404.

**How to handle it**: Re-run `--pull` after any title changes. The pull re-fetches current page URLs.

---

## Validation and Testing

### Pre-Push Checklist
- [ ] `canvas_sync.py --status` → clean (master fully synced)
- [ ] `blueprint_sync.py --pull` run recently (mapping not stale)
- [ ] `blueprint_sync.py --status` shows expected coverage (>80% mapped)
- [ ] No active semester using this Blueprint mid-course (or content locking is acceptable)

### Post-Push Spot Check
- [ ] Open 2 random pages in Blueprint → Student View, confirm content matches master
- [ ] Check Blueprint Settings → Course Details: grading scheme = BYU-Idaho Standard
- [ ] Check Blueprint Gradebook settings: late policy = no deduction, missing = dash not zero
- [ ] Check Blueprint homepage in student view

---

## Resources and References

### Agent Files
- **`canvas_blueprint_sync.json`**: API schemas, field maps, validation checklists
- **`lib/tools/blueprint_sync.py`**: Python implementation (source of truth for behavior)

### Related Agents
- `canvas_content_sync` — pushes individual content changes to master
- `canvas_semester_setup` — sets due dates after a new course section is created from Blueprint

### External Documentation
- Canvas Blueprint Courses API: `/api/v1/courses/:id/blueprint_templates`
- Canvas Pages API: `/api/v1/courses/:id/pages/:url`

---

## Quick Reference Card

| Aspect | Value |
|--------|-------|
| **Purpose** | One-way overwrite: master course → Blueprint (content + dates) |
| **Input** | `course/` + `.canvas/index.json` (master) + `BLUEPRINT_COURSE_ID` |
| **Output** | Blueprint course updated in Canvas + `blueprint_course/` mirror + `blueprint_log.md` entry |
| **Agent Type** | Python-first, agent orchestrates |
| **Complexity** | simple |
| **Key Files** | `lib/tools/blueprint_sync.py`, `.canvas/blueprint_index.json` |
| **Quickstart** | `--pull` then `--push` |
| **Common Pitfall** | Stale mapping after Blueprint module changes — re-run `--pull` |
| **Dependencies** | `requests`, `python-dotenv`, `BLUEPRINT_COURSE_ID` in `.env` |

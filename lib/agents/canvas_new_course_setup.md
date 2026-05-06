# Canvas New Course Setup Agent Guide

Use this guide when setting up a fresh clone or fork of this repo for a new Canvas course. Follow each phase in order. Do not skip verification steps — Canvas IDs are course-specific and most errors trace to mismatched IDs.

---

## Phase 1 — Repo Preparation

After forking or cloning, strip out the prior course's content before doing anything with Canvas.

**Remove course-specific files:**
```bash
rm -rf course/                  # prior course mirror — you will regenerate this
rm -rf blueprint_course/        # prior blueprint mirror
rm -rf .canvas/                 # prior ID index and push log
rm -f quality_report.md
```

**Keep everything else** — the tools, agents, and knowledge files are course-agnostic.

**Rename the starter config:**
```bash
cp CLAUDE.md.example CLAUDE.md
```

Open `CLAUDE.md` and fill in:
- Institution and course name/code at the top
- The three course IDs once you have them (see Phase 2)
- Any course-specific notes at the bottom (module/unit structure, grading model, key dates, known Canvas quirks)

`CLAUDE.md` is gitignored — it stays local to your machine and contains course-specific context for Claude Code.

---

## Phase 2 — Canvas Course IDs

You need up to three Canvas course IDs. Open each course in Canvas — the ID is the number after `/courses/` in the URL.

| Variable | What it is | Required |
|---|---|---|
| `CANVAS_COURSE_ID` | Your working/source course — this is what you edit | Yes |
| `MASTER_COURSE_ID` | Clean template course — receives pushes from source | Optional |
| `BLUEPRINT_COURSE_ID` | Canvas Blueprint — new semester sections clone from this | Optional |

If you only have one course, set only `CANVAS_COURSE_ID` and ignore the master/blueprint tools.

**Generate an API token:**
Canvas → Account → Settings → Approved Integrations → New Access Token. Requires instructor or admin role on all courses you plan to write to.

---

## Phase 3 — Environment Setup

```bash
uv sync
cp .env.example .env
```

Edit `.env`:
```
CANVAS_API_TOKEN=your_token_here
CANVAS_BASE_URL=https://your-institution.instructure.com
CANVAS_COURSE_ID=123456
MASTER_COURSE_ID=123457        # optional
BLUEPRINT_COURSE_ID=123458     # optional
```

Verify connectivity before pulling:
```bash
# Quick smoke test — should print course name and enrollment type
curl -s -H "Authorization: Bearer $CANVAS_API_TOKEN" \
  "$CANVAS_BASE_URL/api/v1/courses/$CANVAS_COURSE_ID" | python3 -m json.tool | grep -E '"name"|"enrollment_type"'
```

If you see `"type": "teacher"` or `"type": "admin"` in enrollments, you have write access.

---

## Phase 4 — Pull the Source Course

```bash
uv run python lib/tools/canvas_sync.py --init
```

This mirrors the live Canvas course into `course/` — modules, pages, assignments, quizzes, discussions, syllabus. It also builds `.canvas/index.json` with all content IDs and hashes.

After the pull:
- `course/_course.json` — course metadata including `start_at` / `end_at`
- `course/[module-slug]/` — one folder per module
- `course/syllabus.html` — Canvas Syllabus tab content

Verify the pull looks right:
```bash
ls course/
cat course/_course.json | python3 -m json.tool | grep -E '"name"|"start_at"|"end_at"'
```

---

## Phase 5 — Pull Master and Blueprint (if using three-course architecture)

```bash
uv run python lib/tools/course_mirror.py --pull        # map master item IDs
uv run python lib/tools/blueprint_sync.py --pull       # mirror blueprint + build ID mapping
```

`course_mirror --pull` does not change any files — it reads the master course and maps its item IDs for use in future pushes.

`blueprint_sync --pull` builds `.canvas/blueprint_index.json` — the title→ID mapping used when syncing master → blueprint.

After Canvas runs its built-in Blueprint sync to push content to sections, validate that it landed correctly:

```bash
uv run python lib/tools/validate_blueprint_sync.py
```

This checks all configured sections (`S1_COURSE_ID`, `S2_COURSE_ID`, …) against the Blueprint for:
- Items present in one section but missing from another (section drift)
- `lock_at`, `allowed_extensions`, or `submission_types` diverging from Blueprint
- Duplicate assignments or quizzes from direct-push + Blueprint overlap
- Completion-requirement items whose `lock_at` has passed, blocking the prerequisite chain

Add `--report` to write findings to `blueprint_sync_validation.md`.

---

## Phase 6 — First Quality Check

Run the quality auditor against your source course before making any changes:

```bash
uv run python lib/tools/course_quality_check.py
```

Review `quality_report.md`. Common issues in a fresh course:

| Issue | What it means |
|---|---|
| `published_not_in_module` | Item exists but students cannot find it — link it to a module or unpublish it |
| `empty_module` | Module has no items (or only NewQuiz/ExternalTool) — students see an empty module |
| `date_out_of_window` | Due/lock/unlock date is outside the course start–end window |
| `duplicate_assignment` | Same title appears twice — if one copy is Blueprint-locked it goes to `manual_review` (keep the locked copy); otherwise `auto_fixable` |

Fix `auto_fixable` items with:
```bash
uv run python lib/tools/course_quality_check.py --fix
```

Items in `manual_review` (NewQuiz, ExternalTool, unpublished items with date issues) must be fixed in the Canvas UI.

---

## Phase 7 — Verify Module Prerequisites and Completion Requirements

If your course uses a locked module progression (students must complete module N before unlocking module N+1), verify two things:

**1. Prerequisites are set on each module** — in Canvas: Modules → edit each module → "Students must complete the following module" checkbox.

**2. Every item in every module has a completion requirement** — assignments/quizzes need `must_submit`, pages/tools/URLs need `must_view`. Without these, the prerequisite lock has nothing to check and students pass through freely.

The quality check does not yet audit completion requirements — verify these in Canvas UI or via API:
```bash
# List module items for a module (replace IDs)
curl -s -H "Authorization: Bearer $CANVAS_API_TOKEN" \
  "$CANVAS_BASE_URL/api/v1/courses/$CANVAS_COURSE_ID/modules/$MODULE_ID/items?per_page=50" \
  | python3 -m json.tool | grep -E '"title"|"completion_requirement"'
```

---

## Phase 8 — Establish Your Workflow

Once the course is pulled and clean, your standard editing loop is:

```bash
# Before editing
uv run python lib/tools/canvas_sync.py --status        # confirm no pending local changes

# Edit files in course/ using any text editor or Claude Code

# After editing
uv run python lib/tools/canvas_sync.py --push          # push changed files to Canvas
uv run python lib/tools/course_quality_check.py        # verify no new issues introduced
uv run python lib/tools/canvas_sync.py --pull --quiet  # refresh metadata
```

**Never edit Canvas directly while you have local changes.** If someone edits Canvas directly:
```bash
uv run python lib/tools/canvas_sync.py --pull          # accept Canvas edits (answer y to confirm)
```

---

## What Cannot Be Pushed via the REST API

These item types must be managed in the Canvas UI — the sync tools will warn but cannot push them:

- **NewQuiz** — use Canvas's New Quizzes editor
- **ExternalTool** — LTI tools (Honorlock, Studio, etc.)
- **late_policy** — 403 for instructor tokens; set in Canvas Settings → Gradebook
- **Completion requirements on items you cannot push** — set in Canvas Modules UI

Modules that contain *only* these types will land empty in master/blueprint after a push. The sync scripts warn you before this happens.

---

## Common First-Run Errors

**`--pull` returns empty modules**
→ Verify `CANVAS_COURSE_ID` is correct and the token has instructor access.

**Push returns 403**
→ Token is read-only or student-level. Generate a new token from an instructor account.

**`--status` shows everything changed after `--pull`**
→ Index hashes were not written. Re-run `--pull` (safe to re-run).

**Quality check shows "published not in module"**
→ Item exists in the course but was never linked to a module. Add via Canvas UI or investigate whether it is a sync artifact to delete.

**Classic quiz shows 0 points after pushing questions**
→ Known Canvas bug. Fix with:
```bash
curl -X PUT -H "Authorization: Bearer $CANVAS_API_TOKEN" \
  "$CANVAS_BASE_URL/api/v1/courses/$CANVAS_COURSE_ID/quizzes/$QUIZ_ID" \
  -d "quiz[points_possible]=10"
```

---

## Course Design Conventions

Each student-facing module should follow a consistent internal structure. A common pattern:

1. **Overview page** — learning outcomes, estimated time, how items connect
2. **Content** — readings, videos, demos
3. **Discussion** — students explain or apply concepts to peers
4. **Assessment** — assignment, quiz, or project demonstrating mastery

Module naming should follow a consistent convention, e.g., `Module X: Topic` or `Week X: Topic`.

The `canvas_course_expert` agent audits against four frameworks particularly relevant at course setup time:

| Framework | Knowledge file | What it checks |
|---|---|---|
| CLO Quality | [`knowledge/outcomes_quality_knowledge.md`](../agents/knowledge/outcomes_quality_knowledge.md) | Whether learning outcomes are well-formed before building content |
| Designer Thinking | [`knowledge/designer_thinking_knowledge.md`](../agents/knowledge/designer_thinking_knowledge.md) | Whether the course was designed backward from outcomes or forward from content |
| Cognitive Load Theory | [`knowledge/cognitive_load_theory_knowledge.md`](../agents/knowledge/cognitive_load_theory_knowledge.md) | Extraneous load from navigation, structure, or module design |
| Hattie 3-Phase | [`knowledge/hattie_3phase_knowledge.md`](../agents/knowledge/hattie_3phase_knowledge.md) | Surface → Deep → Transfer coverage across the course |

**Check CLO Quality and Designer Thinking first.** Auditing structure against broken or forward-designed outcomes produces misleading findings — fix the outcomes, then audit the course.

Run `canvas_course_expert` after Phase 6 to get a structured gap analysis. If your institution has specific teaching standards, add them to `CLAUDE.md` so the agent can audit against them.

---

## Files You Will Customize

| File | What to do |
|---|---|
| `CLAUDE.md` | Rename from `CLAUDE.md.example`; fill in course IDs, institution, course-specific notes |
| `.env` | Add your API token, base URL, course IDs |
| `course/` | Generated by `--init`; edit these files to change Canvas content |
| `course/syllabus.html` | Canvas Syllabus tab — push via `canvas_sync --push syllabus` |

Everything else in the repo is a tool or agent guide — don't modify unless you are extending the toolkit.

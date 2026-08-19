---
name: course-build
description: Use for building and syncing Canvas course CONTENT — mirroring a course to/from local files (canvas_sync pull/push/build), master→blueprint→section propagation (blueprint_sync), module prerequisites/completion settings (module_settings_sync), multi-course orchestration, and offline (.imscc) editing. Load this when the task is "make Canvas match the local source" or "propagate content across sections" — NOT grading and NOT read-only auditing.
---

# Course Build (CI / sync)

Manage Canvas course content as code: mirror to local files, edit locally, and push
approved changes back through the Canvas REST API.

> The **constitution** (AGENTS.md) binds you: confirm scope before any write, and
> Canvas writes go through the toolkit (never a hand-rolled API call). This skill is
> the content-sync *how*.

## Core principle — local is the source of truth

The local working folder is authoritative; **Canvas is the sync target.** Pull to
mirror, edit locally, push to apply. Canvas has no version history — the local
files + git are your history.

## The multi-course model

| Term | What | `.env` id | Folder |
|---|---|---|---|
| **Master** | Template course where authoring happens | `MASTER_COURSE_ID` | `master/` (or `course/` legacy) |
| **Blueprint** | Canvas Blueprint sections clone from (online programs) | `BLUEPRINT_COURSE_ID` | `blueprint/` |
| **Section** | Live per-semester course (S1, S2…) | `S1_COURSE_ID`, … | `s1/`, `s2/` |

**Confirm scope before every write** — master vs blueprint vs section. A stale
`.env` can silently target the wrong course (Canvas API lesson L12); `canvas_course_guard`
defends against it, but naming the target explicitly is on you.

## Tools

| Task | Tool |
|---|---|
| Mirror one course (pull/push/build) | `canvas_sync.py --pull` / `--push` / `--build` |
| Master → Blueprint propagation | `blueprint_sync.py` |
| Validate a blueprint sync | `validate_blueprint_sync.py` + `blueprint_exception_report.py` |
| Module prerequisites / completion | `module_settings_sync.py` |
| Create a custom grading scheme | `grading_scheme_setup.py --title ... --tiers ... --apply` |
| Multi-course wrapper | `sync_context.sh` |
| Post-push structural audit | `course_quality_check.py` *(then hand off to the `audit` skill)* |

**Always run `course_quality_check.py` after a push** to catch duplicates, floating
items, and date-window problems the write may have introduced.

## Canvas API write lessons that bite content sync

The full catalog is [`lib/agents/knowledge/canvas_api_lessons_learned.md`](../../../lib/agents/knowledge/canvas_api_lessons_learned.md).
The ones that matter here:

- **Module prerequisites & published state are FORM-ENCODED, not JSON** (L1, L2) —
  a JSON payload silently no-ops.
- **Date writes need the `due_at`/`lock_at`/`unlock_at` trio** (L3); discussions use
  `todo_date`, not `due_at` (L7).
- **`late_policy` PATCH is admin-only** — 403 for teacher tokens (L4).
- **Classic quizzes have two IDs** (`quiz_id` + `assignment_id`); `points_possible`
  reads 0 until questions are pushed (L5, L6).
- **NewQuiz / ExternalTool items can't be content-pushed via REST** (L8) — sync
  tools warn-and-skip; edit those in the Canvas UI.
- **Blueprint resync can spawn `-N` slug orphan Pages and silently revert section
  page bodies** (L13, L14) — `blueprint_orphan_pages.py` detects both.
- **Page title collisions auto-suffix** `-2`/`-4` (L15).

Adding content is a **two-step** operation (course item + module item) — a page/
assignment isn't visible to students until it's also a module item.

## Offline mode (v1.7)

Tools read a local `course/` (from `canvas_sync --pull` or `offline_import` of a
`.imscc`) and run identically online/offline. The `.imscc` is the source of truth;
`course/` is the working folder. `imscc_record` patches your `course/` edits back
into the sidecar `.imscc` faithfully (quiz questions / files / LTI preserved
byte-for-byte) for re-import via the Canvas UI.

## Quick command map

| Ask | Command |
|---|---|
| "Pull the course from Canvas" | `canvas_sync.py --pull` |
| "Push changes to Canvas" | `canvas_sync.py --push` |
| "Sync master → blueprint" | `blueprint_sync.py` |
| "Fix module prerequisites" | `module_settings_sync.py` |

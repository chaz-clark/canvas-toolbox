---
description: List all available Canvas toolkit commands
---

# Available Canvas Toolkit Commands

Quick reference for slash commands. Type `/` to see auto-complete list.

## Core Workflows

- **`/sync`** — Single-course Canvas sync (pull/push/build)
- **`/audit`** — One-command pre-semester health check (rubrics/CLOs/syllabus/workload)
- **`/quality-check`** — Post-push structural validation (duplicates, floating items, dates)

## Blueprint Workflows

- **`/blueprint-sync`** — Master → Blueprint sync (content + settings)
- **`/validate-blueprint`** — Post-sync validation (drift + exceptions)
- **`/module-settings`** — Module prerequisite/completion reconciliation

## Full Toolkit

**All tools:** [lib/tools/README.md](../../lib/tools/README.md)

Categories in full catalog:
- Core sync tools (canvas_sync, sync_context, blueprint_sync, course_mirror)
- Blueprint tools (validation, presync checks, orphan detection)
- Quality/audit tools (course_audit, quality_check, syllabus_audit, workload_audit, clo_quality_audit)
- Rubric tools (coverage, quality, recommender, fixtures)
- Module tools (settings sync, structure diff)
- Quiz tools (question manager)
- Shared modules (syllabus_outcomes, bloom_verbs, canvas_api_tool)

**Agent specs:** [lib/agents/](../../lib/agents/)
- canvas_course_expert (8-framework audit)
- canvas_schedule_auditor (date validation)
- canvas_blueprint_sync (Blueprint workflow guide)
- canvas_semester_setup (roll dates forward)
- canvas_new_course_setup (first-time setup)

**Knowledge base:** [lib/agents/knowledge/README.md](../../lib/agents/knowledge/README.md)
- Instructional design frameworks (CLT, Hattie, Three Domains, etc.)
- Canvas API lessons learned
- Rubrics knowledge, Outcomes quality, Course design patterns

---

Which tool would you like to learn more about?

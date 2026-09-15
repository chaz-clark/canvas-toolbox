---
name: audit
description: Use for READ-MOSTLY analysis of a Canvas course's design quality — one-command health checks (course_audit), post-push structural checks (course_quality_check), the 8-framework instructional-design audit stack, rubric quality/coverage, and blueprint exception reports. Load this when the task is "check / audit / report on" a course's structure or instructional design. (For Title IV engagement / unofficial-withdrawal compliance, use the `title-iv` skill instead.)
---

# Audit

Analyze course structure, instructional-design quality, and Title IV engagement.
These tools mostly **read**; they surface problems, they don't apply fixes.

> The **constitution** (AGENTS.md) binds you: FERPA Zone-2 files are never read, and
> reports containing student names are written OUTSIDE the repo (see Title IV below).

**Findings go on the board, not into the void.** When an audit surfaces something worth
fixing, log it as a card in the course's `IMPROVEMENTS.md` (the `improve` skill) with
`src: audit <date>` — so it's tracked to *done*, not filed in a one-off report and
forgotten. An audit's real output is a prioritized set of cards.

## Structural + quality audits

| Task | Tool |
|---|---|
| One-command pre-semester health check (rubrics / CLOs / syllabus / workload) | `course_audit.py --course-id <id>` |
| Post-push structural audit (duplicates, floating items, date windows) | `course_quality_check.py` |
| Rubric quality + coverage | `rubric_quality_audit.py` |
| Blueprint sync exceptions (silent per-section skips) | `blueprint_exception_report.py` |

Validate the audit **baseline** before proposing a redesign — check
`.canvas/audit/<course_id>.json`. Ground pedagogical findings in the knowledge
base and cite the framework used.

## The 8-framework instructional-design stack

Audits score against: Cognitive Load, Hattie 3-Phase, Three Domains, BYUI Taxonomy
Explorer, Experiential Learning, Designer Thinking, Course Design Language, and the
Toyota A3. References live in [`lib/agents/knowledge/README.md`](../../../lib/agents/knowledge/README.md).

## Title IV engagement → a separate skill

The last-date-of-engagement / unofficial-withdrawal audit
(`course_engagement_audit.py`) is **federal-compliance** work with its own stakes and
vocabulary — it lives in the **`title-iv`** skill, not here. Load that skill for
"who stopped participating", UW/UF, R2T4, or last-date-of-attendance work.

## Quick command map

| Ask | Command |
|---|---|
| "Audit the course" / "health check" | `course_audit.py --course-id <id>` |
| "Check quality after a push" | `course_quality_check.py` |
| "Check the rubrics" | `rubric_quality_audit.py` / `rubric_coverage_audit.py` |

# Course Design

Course construction, synchronization, quality audits, instructional-design analysis, and
improvement tracking. No student submission data.

This file is a package entry point, not a playbook. The playbook lives in the skills
declared in `manifest.yaml` — load `audit` for read-mostly analysis, `course-build` for
making Canvas match local content, and `improve` for the `IMPROVEMENTS.md` kanban. This
file does not duplicate their instructions; a second copy would drift from the first the
same way a second Zone-2 pattern list did (see `lib/tools/package_validate.py`).

**Default data boundary:** course content and configuration only — outcomes, rubrics,
modules, dates, syllabus text. Never student submissions, grades, or roster identity.

**Writes:** sanctioned course-build tools only (declared in `manifest.yaml` as
`canvas_content_write`), each gated by plan/confirmation/verification per the root
`AGENTS.md` Canvas-write doctrine. This package never writes a grade or a comment.

**Supersedes (informational, not yet removed):** `lib/agents/canvas_course_expert.md`,
`canvas_blueprint_sync.md`, `canvas_content_sync.md`, `canvas_schedule_auditor.md`,
`canvas_new_course_setup.md`, `canvas_semester_setup.md`, `ira_program_alignment.md`,
`canvas-sync.md`. Those files predate the skills split and describe the same workflows
at greater length; `.claude/skills/audit,course-build,improve/SKILL.md` are current.

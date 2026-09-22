# Grading

FERPA-safe preparation, review, and sanctioned delivery of assignment grades and feedback.

This file is a package entry point, not a playbook. Load `grading` for the fetch →
consensus → review → push workflow and the HG-5 human-in-the-loop protocol, `ferpa-deid`
for the de-id/re-id machinery, and `voicing` for writing in the instructor's established
tone. This file does not duplicate their instructions.

**FERPA Zone 2 is denied unconditionally.** No skill, tool, or manifest declaration in
this package may weaken that — see the root `AGENTS.md` FERPA discipline section, which
is constitutional and never overridden by a package.

**Writes:** every tool in this package that reaches a Canvas grade or comment endpoint
is declared `canvas_grade_comment_write` with `approval: always`. That set is broader
than the two tools root `AGENTS.md` names by name (`grader_push.py`, `grader_standing.py`)
— `grader_push_comments.py` (transports grader-staged, reviewed comments),
`grader_letter_comments.py` (instructor-authored comment-only writes, its own sanctioned
replacement for a hand-written bypass), `grader_audit_workflow.py --fix` (idempotent
grade re-post, no new grade value), and `grader_quiz_clear_pending.py` (zeroes pending
quiz scores) are each individually gated the same way. None of them accept AI-drafted,
unreviewed content — read each tool's own docstring before use.

**Supersedes (informational, not yet removed):** `lib/agents/canvas_grader.md`. That file
predates the skills split; `.claude/skills/grading,ferpa-deid,voicing/SKILL.md` are current.

# Student Support

Accommodations and Title IV engagement workflows involving individual students.

This file is a package entry point, not a playbook. Load `accommodations` for time
extensions, late grace, SAS overrides, and submit-on-behalf; load `title-iv` for the
engagement/unofficial-withdrawal audit. This file does not duplicate their instructions.

**Default data boundary:** opaque `user_id`/`deid_code` only. Names are excluded from
agent output per the root `AGENTS.md` naming convention — a student is never named
beside an intervention, exemption, or engagement classification in anything this
package's tools cause an agent to write.

**Writes:** every tool that reaches Canvas on a student's behalf is declared
`canvas_student_intervention` with `approval: always` and per-student confirmation:
`apply_sas_accommodations.py` (dispatches the two tools below across a roster),
`student_late_accommodation.py`, `student_quiz_time_extension.py`, `exempt_by_date.py`,
and `submit_on_behalf.py`.

**Supersedes:** no dedicated `lib/agents/*.md` predates this package —
`.claude/skills/accommodations,title-iv/SKILL.md` are the only prior specification.

---
name: accommodations
description: Use for per-student interventions in Canvas — SAS/disability accommodations, quiz time extensions, late-work grace, assignment/date exemptions, group-override recalculation, and submitting on a student's behalf. All are keyed by an opaque --deid-code or --user-id the INSTRUCTOR supplies (you never look up the name). Load this when the task is "give student X extra time / late grace / an override / an exemption", NOT grading and NOT course content.
---

# Accommodations & student interventions

Per-student operational actions an instructor directs: accommodations, extensions,
grace, overrides, exemptions. These write to Canvas and are always **instructor-
initiated for a specific student**.

> The **constitution** (AGENTS.md) binds you: the instructor looks up the student
> in the local `.deid_master.csv` and hands you ONLY the opaque `deid_code` or
> numeric `user_id`. You use it as-is — **no re-identification, never a name.**

## The identity contract

Every tool here accepts `--deid-code <S-XXXXXX>` or `--user-id <n>` directly. You do
**not** read `.deid_master.csv` to "look up" the student — that's a FERPA Zone-2
violation. If the instructor says "give Sydney extra time," ask them for Sydney's
deid_code or user_id; you never resolve the name yourself.

Output discipline: ✅ "Applied 1.5× time for deid_code S-95DBB6" · ❌ "…for Sydney."

## Tools

| Intervention | Tool |
|---|---|
| Quiz time extension (e.g. 1.5× / 2× on timed quizzes) | `student_quiz_time_extension.py --deid-code <code> --multiplier 1.5 --all-timed --apply` |
| Late-work grace / reopen past-due assignments | `student_late_accommodation.py --deid-code <code> --from-days-ago 14 --apply` |
| SAS / disability-office accommodation dispatcher (processes letters) | `apply_sas_accommodations.py --apply` |
| Exempt a student from an assignment by date | `exempt_by_date.py …` |
| Student can't submit / override not taking effect / force recalc | `fix_group_override_recalc.py --course-id <id> --student-id <id>` |
| Submit an artifact on a student's behalf | `submit_on_behalf.py …` |

## Discipline

- **`--apply` is the write gate.** Every tool defaults to a dry-run preview; nothing
  reaches Canvas until `--apply`. Preview first, confirm the target student + change,
  then apply.
- **`canvas_course_guard` still applies** — an enrolled-course write is gated; the
  instructor's own course needs the explicit override the tool documents.
- **Canvas write lessons that bite here:** overrides + due-date changes need the full
  `due_at`/`lock_at`/`unlock_at` trio, and a group override sometimes needs a forced
  recalc before Canvas honors it (`fix_group_override_recalc.py`).

## Quick command map

| Ask | Command |
|---|---|
| "Give student X 1.5× on all quizzes" | `student_quiz_time_extension.py --deid-code <code> --multiplier 1.5 --all-timed --apply` |
| "Let student X submit late" | `student_late_accommodation.py --deid-code <code> --from-days-ago 14 --apply` |
| "Process the SAS letters" | `apply_sas_accommodations.py --apply` |
| "Student X still can't submit" | `fix_group_override_recalc.py --course-id <id> --student-id <id>` |

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
violation. If the instructor says "give Ada extra time," ask them for Ada's
deid_code or user_id; you never resolve the name yourself.

Output discipline: ✅ "Applied 1.5× time for deid_code S-68BC40" · ❌ "…for Ada."

## Tools

| Intervention | Tool |
|---|---|
| Quiz time extension (e.g. 1.5× / 2× on timed quizzes) | `student_quiz_time_extension.py --deid-code <code> --multiplier 1.5 --all-timed --apply` — covers Classic Quizzes and New Quizzes. Canvas can't be asked whether a New Quiz accommodation applied: confirm on the quiz's Moderate page or in Student View, once the student has an attempt available |
| Time extension or extra attempt on one New Quiz | `student_quiz_time_extension.py --deid-code <code> --new-quiz-id <assignment id> --multiplier 1.5 [--extra-attempts 1] --apply` (no `--manually-unlock` / `--extend-from-end-at`: Classic Quizzes only) |
| Extra quiz attempt / manual unlock (one quiz) | `student_quiz_time_extension.py --deid-code <code> --quiz-id <id> --extra-attempts 1 [--manually-unlock] [--extend-from-end-at <min>] --apply` — Canvas can't delete a classic submission; check the quiz's score-keeping policy (highest vs latest) to know whether the old attempt still counts |
| Late-work grace / reopen past-due assignments | `student_late_accommodation.py --deid-code <code> --from-days-ago 14 --apply` |
| SAS / disability-office accommodation dispatcher (processes letters) | `apply_sas_accommodations.py --apply` |
| Exempt a student from an assignment by date | `exempt_by_date.py …` |
| Excuse one student from specific assignments | `exempt_by_date.py --user-id <id> --assignment-ids <id>[,<id>] --apply` — refuses the Test Student, an inactive student, or someone not in the course (#443) |
| Student can't submit / override not taking effect / force recalc | `fix_group_override_recalc.py --course-id <id> --student-id <id>` |
| Submit an artifact on a student's behalf | `submit_on_behalf.py …` |

## Discipline

- **A `[WARN]` about a module means the student still won't see the change.** A module that opens later wins over an earlier Available from, and a module whose prerequisites the student hasn't finished stays locked (lesson L37). Canvas has no per-student module dates, so tell the instructor the two options the tool names: change the module's Lock until date for everyone, or move the item. The line "the student needs to finish …" names where a chain of locked modules starts. The change is still written; it takes effect when the module unlocks.
- **`--apply` is the write gate.** Every tool defaults to a dry-run preview; nothing
  reaches Canvas until `--apply`. Preview first, confirm the target student + change,
  then apply.
- **`canvas_course_guard` runs, set for an intervention** (#475), in `exempt_by_date`,
  `student_late_accommodation`, `student_quiz_time_extension` and `submit_on_behalf`.
  The course the student is enrolled in (often a Blueprint-child Course Section) is
  the normal target, so it
  proceeds with no `--allow-enrolled`. When the course has students it prints one
  line naming the course and its enrollment: read it before you report the change. No
  line means the course has no students (likely the wrong course: stop and ask) or the
  guard couldn't reach Canvas ("could not verify"). It **refuses** `--apply` from a
  folder opened above several courses. These tools write to `CANVAS_COURSE_ID`; never
  set it on the command line to reach another course.
  `fix_group_override_recalc` runs it too (#502), for a student or a group. It
  writes on a plain run (`--dry-run` previews), so a plain run is the guarded write.
  It takes `--course-id` on the command line, so the guard also **refuses** a course
  outside this folder's `.env`; `CB_COURSE_SWITCH=<id>` is only for the instructor's
  explicit say-so.
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

<!-- GENERATED by lib/tools/generate_adapters.py from skills/accommodations/SKILL.md — do not edit this copy directly; edit the canonical file and regenerate. schema_version: 1 -->

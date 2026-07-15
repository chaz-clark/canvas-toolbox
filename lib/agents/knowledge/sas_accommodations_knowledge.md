# SAS accommodations — catalog + dispatch knowledge

**Source:** life-pm produces SAS accommodation handoffs from BYUI
Accessibility Services notification letters (sender:
`byui.as@accessiblelearning.com`, subject pattern: `[AS] <student> -
<COURSE> - … - Notification of Disability Accommodations <Term>`).

**Consumed by:** `lib/tools/apply_sas_accommodations.py` (v0.72.0).

**Why this file exists:** the catalog of accommodation types is
stable boilerplate — the AS office issues the same set of standardized
asks letter-to-letter. Codifying them once here lets the dispatcher
classify every observed key without LLM judgment, and lets future
agents reason about what's automatable vs. instructor-discretion.

---

## Three tiers — what gets automated, what's a flag

| Tier | Count | Examples | Dispatcher behavior |
|---|---|---|---|
| `canvas` | 4 | `extra_time_1.5x`, `extra_time_2.0x`, `occasional_extensions`, `test_reschedule` | Invoke the matching canvas-toolbox tool |
| `proctoring` | 2 | `proctorio_breaks`, `private_room_exams` | Flag for operator — out of Canvas API scope |
| `policy` | 11 | `spelling_grammar`, `attendance_notification`, `recording_device`, `assignment_clarification`, etc. | Flag for operator — instructor-practice, no LMS toggle |

---

## Canvas-tier key → tool dispatch

| Catalog key | Faculty ask | Dispatched tool | Notes |
|---|---|---|---|
| `extra_time_1.5x` | "Please allow 50% extra time on all timed exams and quizzes." | `student_quiz_time_extension --multiplier 1.5 --all-timed` | Classic Quizzes only. New Quizzes follow-up. |
| `extra_time_2.0x` | "Please allow 100% extra time (double time) on all exams and quizzes." | `student_quiz_time_extension --multiplier 2.0 --all-timed` | Same scope as 1.5x. |
| `occasional_extensions` | "Students are expected to meet assignment deadlines. However, occasional extensions may be appropriate…" | `student_late_accommodation --all` (or scoped by YAML `scope`) | Dropped `lock_at` (no close date). Scope flags: `from_days_ago`, `from`. |
| `test_reschedule` | "This student has health issues that may warrant a need to reschedule their exam date…" | `student_late_accommodation --shift-by-days N` | Shifts unlock/due/lock forward by N days. Distinct from `occasional_extensions`. |

### `occasional_extensions` vs `test_reschedule` — pick by what should move

Both call `student_late_accommodation`, but they change **different dates**. Pick by
intent, not by the word "reschedule" (mis-picking these is what surfaced #178):

| What the letter/instructor actually means | Use | What changes |
|---|---|---|
| **"Let the student submit late"** — open + due dates stay the same, they just need the submit button open past the close date | `occasional_extensions` | Drops `lock_at` only. `unlock_at` + `due_at` unchanged (gradebook keeps the original due date). |
| **"Move this student's exam/assignment later"** — they'll open it later and be graded against the new dates | `test_reschedule` | Shifts `unlock_at`, `due_at`, `lock_at` all forward by N days. |

**Default to `occasional_extensions` for "allow late submission."** Shifting `due_at`
(`test_reschedule`) changes the gradebook due date and late-penalty math — only do that
when the intent is genuinely to *move* the assignment, not to forgive lateness.

**⚠️ Gotcha — an auto Late Policy undermines the drop-lock accommodation.** If the
course's Gradebook Late Policy is on, `occasional_extensions` lets the student submit
(lock dropped) but the submission is still past `due_at`, so Canvas **auto-deducts
anyway** — silently undercutting the accommodation. Check `GET /courses/:id/late_policy`
(syllabus_audit surfaces this); if it's on, either shift `due_at` too or handle that
student's penalty manually. (See #185.)

---

## Proctoring-tier flags (faculty handle outside Canvas)

| Catalog key | Faculty ask | What operator does |
|---|---|---|
| `proctorio_breaks` | "This student may need to look away from the computer screen or take a break…" | Whitelist behavior in the course's Proctorio config so monitoring doesn't flag it. |
| `private_room_exams` | "The student needs access to a private room with reduced distraction…" | Coordinate with the BYUI Testing Center; student reserves a private room in advance. |

---

## Policy-tier flags (instructor practice, no LMS change)

All 11 policy-tier keys surface as a one-line note in the dispatcher
output. Faculty add them to their personal accommodation checklist for
that student. None of these have a Canvas API counterpart.

| Catalog key | Faculty ask |
|---|---|
| `assignment_clarification` | Allow student to communicate with you / TA for clarification. |
| `recording_device` | Permission to record lectures for personal educational use. |
| `breaks_during_class` | Permission to leave class briefly for short breaks. |
| `spelling_grammar` | Consider not penalizing spelling/grammar errors (subject to fundamental-alteration clause). |
| `food_drink_medication` | Permission to have food/drink/medication accessible during class & exams. |
| `class_participation_mod` | Advance notice when called on; provide questions in advance; consider alternate assignments (subject to fundamental-alteration clause). |
| `attendance_notification` | Flexibility for cyclical acute episodes affecting attendance. |
| `hat_in_class` / `hat_in_class_testing` | Permission to wear a hat (dress-standard exception). |
| `tinted_glasses` | Permission to wear tinted glasses in class/testing. |
| `service_animal` | Refer to BYUI Animal Policy. |

---

## Handoff schema (YAML — `grading/.sas_accommodations.yml`)

FERPA tier 2 (gitignored). The de-id master sits next to it
(`grading/.deid_master.csv`) so the dispatcher resolves `deid_code` →
`user_id` without ever reading sortable_name.

```yaml
- deid_code: S-95DBB6           # required, looked up in de-id master
  letter_date: 2026-06-22       # optional, audit trail
  accommodations:
    - key: extra_time_1.5x
    - key: occasional_extensions
      scope: from_days_ago      # optional: all (default) | from_days_ago | from
      days: 14
    - key: test_reschedule
      shift_by_days: 7          # optional, defaults to 7
      assignment_id: 12345      # optional, applies to all if absent
    - key: spelling_grammar     # policy tier → emit checklist line
    - key: proctorio_breaks     # proctoring tier → emit checklist line
```

---

## Updating the catalog

When life-pm surfaces a new accommodation type not in the v0.72.0 list:

1. The dispatcher will print `UNKNOWN key '<name>'` and skip it.
2. Add the key to the right tier set in
   `apply_sas_accommodations.py` (`_CANVAS_KEYS`, `_PROCTORING_KEYS`,
   or `_POLICY_KEYS`).
3. If it's `canvas`-tier, add a branch in `_build_canvas_command()`
   mapping the key to a tool invocation.
4. Update the tables in this knowledge file.
5. Bump the catalog version date in the next handoff.

---

## Related

- `deid_master_knowledge.md` — the de-id master this dispatcher consumes
- `course_engagement_audit_knowledge.md` — Title IV pattern; same FERPA tier discipline
- `handoffs/2026-06-26-accessibility-accommodations-catalog.md` — the
  original life-pm catalog this knowledge file vendors from
- Cross-repo: `[[project-sas-accommodations-handoff]]` user memory

# Canvas Semester Setup Agent Guide

## Agent Instructions
1. Read this file for mission, principles, and workflow.
2. Parse `canvas_semester_setup.json` for the week-to-week due date rules, API patterns, and validation steps.
3. Do not parse this Markdown for structured data.

---

## Mission

**What it does**: Updates all Canvas assignment due dates for a new semester. Given a semester name and Week 1 Monday start date, it calculates due dates for every assignment across all 14 weeks and pushes them to Canvas.

**Why it exists**: Updating due dates manually each semester is error-prone (wrong UTC offsets, missed items, leftover test dates). This agent reads the course's established week→assignment mapping, computes dates for the new semester, and pushes all 40+ updates in one pass.

**Who uses it**: Instructor or TA at the start of each new semester — typically when preparing for Spring, Fall, or Winter term.

---

## Agent Quickstart

1. **Get inputs**: Confirm the semester name (e.g., "Spring 2026") and the Week 1 Monday start date (e.g., "2026-04-20"). Ask for the end date if you don't know it — needed to calculate W14 due date.
2. **Determine UTC offset**: MDT (Apr–Oct) = UTC-6, MST (Nov–Mar) = UTC-7. 11:59 PM local = T05:59:00Z (MDT) or T06:59:00Z (MST).
3. **Read setup notes**: Fetch `course/setup-notes-and-course-settings` page (page_url: `setup-notes-and-course-settings`) to confirm week structure, time zone, and any course-specific rules.
4. **Build week calendar**: Map each week number to its Sunday 11:59 PM due date using the start date.
5. **Load index**: Read `.canvas/index.json` → `modules[]` → items with `due_at`, `lock_at`, `unlock_at` fields.
6. **Map assignments to weeks**: Use the `primary_data.week_assignment_map` in `canvas_semester_setup.json` to look up which week each `canvas_id` belongs to.
7. **Propose**: Show the full mapping (canvas_id, title, old due_at, new due_at) for confirmation before any writes.
8. **Push**: Call `PUT /api/v1/courses/:id/assignments/:id` with `{"assignment": {"due_at": "...", "lock_at": null, "unlock_at": null}}`. Discussions use `PUT /discussion_topics/:id` with `{"discussion_topic": {"todo_date": "..."}}`.
9. **Update local files**: Write the new `due_at` into each local `.json` file in `course/`.
10. **Update index**: Write the new `due_at` into `index["modules"]` items.

---

## File Organization: JSON vs MD

### This Markdown File Contains:
- Mission, quickstart, principles, pitfalls, workflow narrative

### The JSON File Contains:
- `week_assignment_map` — canvas_id → week number for all 40+ items
- `special_due_dates` — items with non-standard timing (W09 Demo 3 = Monday, W14 = end of semester)
- `skip_list` — canvas_ids that should never be updated (university surveys, unpublished templates)
- `api_patterns` — correct request payloads for assignments vs discussions vs quizzes
- `utc_offset_rules` — MDT vs MST boundary dates

---

## Key Principles

### 1. Propose Before Execute
Always show the full diff table (old due_at → new due_at for every item) and wait for explicit approval before making any API calls. Never start writing without a "yes" or "go ahead."

### 2. Clear lock_at and unlock_at on Every Update
Reading quizzes have availability dates set from prior semesters. If you set `due_at` without clearing `lock_at`/`unlock_at`, Canvas returns 400 ("must be between availability dates"). Always send `lock_at: null, unlock_at: null` with every due date update.

### 3. UTC Offset Depends on Semester, Not Instructor Location
Spring (mid-Apr to end of Jul) → Mountain Daylight Time (MDT) → UTC-6 → 11:59 PM = T05:59:00Z.
Winter/Fall (Aug–mid-Apr) → Mountain Standard Time (MST) → UTC-7 → 11:59 PM = T06:59:00Z.
Get this wrong and due dates appear an hour off for students.

### 4. Week Boundaries Are Monday–Sunday
Week 1 starts on the given Monday. Week ends Sunday. Due date = that Sunday at 11:59 PM MT.
W14 is special: the semester may end mid-week — use the actual last day of the semester at 11:59 PM MT.

### 5. W09 Demo 3 has a Monday Due Date
The dbt Demo 3 assignment (canvas_id: 16858423) is due Monday of Week 9 (first day of the week), not Sunday. It's meant to be completed at the very start of the sprint.

---

## Behavioral Discipline (core)

This agent operates under the v3.6 behavioral discipline. Full source: `make-ai-agents/knowledge/behavioral_discipline.md`. Interaction pattern: **multi_step_batch** (the full discipline applies because a batch rollover decomposes into many individual writes).

**All 10 principles apply:**

- **P-001 Read Before Claiming** — Read `.canvas/index.json`, local `course/*.json`, and the setup notes page before computing any date.
- **P-002 Plan Before Acting** — The proposed-diff table (canvas_id | title | old due_at | new due_at) IS the batch plan. Show it in full and wait for explicit approval before any write.
- **P-003 Stop on Defect** — On the first 4xx response from the Canvas API, STOP. Do not retry blindly across remaining items. Surface the failing canvas_id and the error.
- **P-004 Find the Root Cause** — If a date doesn't push (400, 403, lock-window error), walk the cause: missing `lock_at: null`? wrong endpoint (assignment vs discussion vs classic-quiz-via-assignment)? Don't paper over.
- **P-005 Small Steps, Evenly Sized** — Decompose the batch into per-item writes so each can fail independently. Don't bulk-update via a single multi-row call.
- **P-006 Document the Change** — Final report uses the A3 template: which items succeeded, which failed, and why. Reviewable without reading the diff.
- **P-007 Pull, Don't Push** — Update exactly the items asked for. Don't speculatively touch availability windows, points, or other fields beyond `due_at`/`lock_at`/`unlock_at` (or `todo_date` for discussions).
- **P-008 Mistake-Proof Outputs** — Same proposal-table format every run. Same final-report format every run. The instructor should know what to expect.
- **P-009 Reflect, and Tell the User** — If something was surprising (e.g., an item turned out to be a NewQuiz that can't be content-pushed, or a discussion `todo_date` failed silently), name the lesson in the response and append to External System Lessons in this file.
- **P-010 Respect the User's Intent** — Don't substitute interpretations of ambiguous date rules. Always ask the instructor. Don't drift mid-batch into adjacent edits ("while I was in there I also fixed X") — that's a separate request.

**No-override principles:** P-001, P-003, P-007, P-010 apply unconditionally — they cannot be skipped under any circumstances.

**Hard rule:** before skipping any principle, state in one sentence which principle is being skipped and why.

---

## How to Use This Agent

### Prerequisites
- `.env` file with `CANVAS_API_TOKEN`, `CANVAS_BASE_URL`, `CANVAS_COURSE_ID`
- `.canvas/index.json` up to date (run `uv run python lib/tools/canvas_sync.py --init` if stale)
- Instructor confirms: semester name, Week 1 Monday start date, last day of semester

### Input Required
```
Semester: Spring 2026
Week 1 Monday: 2026-04-20
Last day: 2026-07-22
```

### What the Agent Produces
1. A due date proposal table (one row per assignment)
2. Canvas API calls (all 40+ assignments in one pass after approval)
3. Updated local `.json` files with new `due_at`
4. Updated `index["modules"]` items with new `due_at`

### Existing Tooling

| Tool / File | Purpose | When to use |
|---|---|---|
| `lib/tools/canvas_sync.py --init` | Rebuilds `.canvas/index.json` from live Canvas | Run if index is stale (before semester setup) |
| `.canvas/index.json` → `modules[]` items | Source of all assignment canvas_ids and current dates | Read at start to discover all items |
| `canvas_semester_setup.json` → `week_assignment_map` | Week number for each canvas_id | Use to compute due date per item |
| `course/setup-notes-and-course-settings` (page_url) | Course-specific week structure and timing rules | Read to confirm rules before computing |

---

## Common Pitfalls and Solutions

### 1. Reading Quiz Due Date 400 Error

**Problem**: `PUT /assignments/:id` returns 400 "must be between availability dates"

**Why it happens**: Reading quizzes were set up with `lock_at`/`unlock_at` availability windows from a prior semester. The new due date falls outside that window.

**Solution**: Always send `{"assignment": {"due_at": "...", "lock_at": null, "unlock_at": null}}` — never just `{"assignment": {"due_at": "..."}}`.

### 2. Wrong UTC Offset

**Problem**: Due dates appear at 12:59 AM or 10:59 PM instead of 11:59 PM for students.

**Why it happens**: Using MST offset (T06:59:00Z) for a spring/summer semester that observes MDT (T05:59:00Z), or vice versa.

**Solution**: Spring semesters (roughly Apr–Jul) = MDT = T05:59:00Z. Winter/Fall semesters (roughly Aug–Mar) = MST = T06:59:00Z. Confirm with semester dates in `canvas_semester_setup.json` → `utc_offset_rules`.

### 3. Updating University Survey Due Dates

**Problem**: Agent updates W05 Student Feedback or W13 End-of-Course Evaluation — these are BYUI-managed and should not be touched.

**Why it happens**: They appear in `index["modules"]` as regular assignments.

**Solution**: Check `canvas_semester_setup.json` → `skip_list` before building the update batch. Never update those canvas_ids.

### 4. Classic Quiz (Syllabus Quiz) Uses Assignment ID, Not Quiz ID

**Problem**: `PUT /quizzes/5911959` doesn't accept `due_at` updates.

**Why it happens**: Classic Canvas Quizzes have a separate linked assignment. The quiz `canvas_id` (5911959) is the quiz_id; the linked assignment_id is 16858181.

**Solution**: Use assignment_id 16858181 for Syllabus Quiz updates. This is documented in `canvas_semester_setup.json` → `special_due_dates`.

---

## External System Lessons

### Canvas API — Reading Quiz Lock Dates Persist Across Semesters

**Behavior**: Reading quizzes set up in a prior term retain `lock_at` and `unlock_at`. Canvas enforces that `due_at` must fall within those bounds — even when the bounds are in the past.

**Why it matters**: Any due date update for reading quizzes will fail with 400 unless `lock_at: null, unlock_at: null` is included in the same PUT.

**How to handle it**: Always include both null-clear fields in every assignment update. Side effect: this removes any availability window, which is intentional for this course (no available dates policy).

### Canvas API — Discussions Use a Different Endpoint

**Behavior**: The Peer Audit (W14) is a Discussion, not an Assignment. Due dates for discussions use `todo_date` in `PUT /discussion_topics/:id`, not `due_at` in `PUT /assignments/:id`.

**How to handle it**: Check `canvas_semester_setup.json` → `special_due_dates` for the discussion canvas_id and the correct payload key.

---

## Validation

After pushing all updates, verify:
- [ ] Spot-check 3 assignments in Canvas UI — confirm dates show correctly in student view (local timezone)
- [ ] Confirm W09 Demo 3 is due Monday, not Sunday
- [ ] Confirm W14 items are due the last day of semester, not Sunday of that week
- [ ] Confirm reading quizzes show no lock/unlock dates
- [ ] Confirm Syllabus Quiz (classic quiz) shows updated due date

---

## Resources and References

### Agent Files
- `canvas_semester_setup.json` — week assignment map, skip list, API patterns
- `lib/tools/canvas_sync.py` — `--init` rebuilds index with current dates
- `.canvas/index.json` — current due_at for all assignments (after --init)
- `course/setup-notes-and-course-settings` (Canvas page, page_url: `setup-notes-and-course-settings`) — authoritative week structure

### Related Agents
- `canvas_course_expert` — full course audit and content edits
- `canvas_content_sync` — pushes page content changes

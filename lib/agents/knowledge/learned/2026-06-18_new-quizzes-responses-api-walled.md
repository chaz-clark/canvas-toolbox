---
name: new-quizzes-responses-api-walled
description: Canvas New Quizzes (Quizzes.Next) exposes quiz STRUCTURE but not per-student RESPONSE values via API. Branching tree below shows the three viable paths (Reporting API for file-upload questions, Classic-mirror workaround for full response data, submitted-proxy for completion-only quizzes). Always classify a quiz BEFORE trying to read responses.
version: "1.0"
author: chaz-clark
license: MIT
metadata:
  topic: canvas-api / new-quizzes
  precipitating-event: 2026-06-16 m119 + ds460 + itm327 NQ-API exploration
  affects: any tool that reads or grades quiz responses
  related-tools:
    - grader_fetch_nq_responses.py (issue #87 — Reporting API path)
    - _quiz_kind.py (issue #86 — detector helper)
    - grader_reconcile.py (the submitted-proxy path for completion quizzes)
---

# New Quizzes responses are API-walled — branch by data need

## The empirical table (verified across 3 consumer repos, 2026-06-16)

| Endpoint | Result |
|---|---|
| `GET /api/quiz/v1/courses/:cid/quizzes` | 200 (list works) |
| `GET /api/quiz/v1/courses/:cid/quizzes/:id/items` | 200 (questions / structure) |
| `GET /api/quiz/v1/courses/:cid/quizzes/:id/submissions` | **404** |
| `GET /api/quiz/v1/courses/:cid/quizzes/:id/reports` | 200 (the way through — see below) |
| `GET /api/quiz/v1/courses/:cid/quizzes/:id/results` | **404** |
| `GET /api/v1/courses/:cid/quizzes/:id/submissions` (Classic API on NQ id) | **404** (resource does not exist) |
| `GET /api/v1/courses/:cid/assignments/:id/submissions` | 200, but `submission_type=basic_lti_launch`, no `submission_data`, no item answers — only LTI `preview_url` / `external_tool_url` |
| Canvas course files (`/courses/:cid/files`) | empty (quiz file uploads don't land in course files) |

**What IS available** via the standard `/assignments/:id/submissions` endpoint on a NQ assignment:
- `submitted_at` (timestamp)
- `score` / `entered_score` (Canvas auto-grades; partial credit visible)
- `workflow_state` — note: a NQ can strand auto-scored submissions in `pending_review` until the instructor manually clears them

**What is NOT available** via API at all:
- Per-question response values (numeric, essay)
- Per-question rubric data
- File URLs or binaries from file-upload questions

## The three viable paths (in priority order)

### Path 1 — `student_analysis` Reporting API (file-upload + numeric data)

`POST /api/quiz/v1/courses/{cid}/quizzes/{qid}/reports` with
`{"quiz_report": {"report_type": "student_analysis", "includes_all_versions": true}}`
returns a `progress` object. Poll `/api/v1/progress/{pid}` until
`workflow_state=="completed"`, then download from `results.url` (signed
inst-fs URL, TTL ~24h).

The CSV exposes per-student rows with **uploaded filenames** (not URLs),
submitted_at, and per-question answer + earned-points triples. This is
how `grader_fetch_nq_responses.py` (#87) works.

**Use this path when** you need per-student response DATA — uploaded
filenames for file-upload questions, numeric answers, or essay text.

### Path 2 — Classic-mirror workaround (full submission_data access)

The Classic Quiz API (`online_quiz` submission_type) exposes
`submission_data` per submission via
`/assignments/:aid/submissions?include[]=submission_history` — the full
question-id → answer-text map.

To use this for a quiz that's currently a New Quiz:
1. Create an unpublished CLASSIC clone with identical title / desc /
   due / module placement
2. Swap the live version New → Classic from a given week onward
3. All subsequent weeks' submissions become readable via
   `submission_data`

DS 460's stand-up pipeline uses this for numeric self-reports (wide-range
auto-graded questions that always full-credit).

**Use this path when** Path 1 doesn't expose what you need (e.g.,
multi-choice answer letters, free-text essays where the Reporting API
truncates) AND you control the assignment lifecycle.

### Path 3 — submitted-proxy (completion-credit quizzes)

For quizzes graded on COMPLETION rather than CONTENT (binary
complete / incomplete, full-credit for showing up), you don't need
response data at all. `/assignments/:aid/submissions` gives you
`submitted_at` + `score`, which is sufficient for the
`grader_reconcile.py` `completion_basis: submitted | nonzero | full_credit`
gating logic.

**Use this path when** the grade is structural (submitted? scored?
full credit?) and the response values themselves don't matter.

## Pending-review finalizer note

NQ auto-scored submissions can land in `workflow_state: "pending_review"`
even when Canvas's auto-grader assigned points. They finalize cleanly
via `PUT /api/v1/courses/:cid/assignments/:id/submissions/:uid` with
`submission[posted_grade]` — Canvas transitions the row to `graded`.
This is captured in the parking lot as a follow-up tool
(`pending_review_finalizer.py`); not in scope of #86.

## Detection guide

Any tool that reads or grades quiz responses MUST classify the quiz
first. Use `_quiz_kind.py::detect_quiz_kind(base, headers, cid, aid)` —
returns `{"kind": "new_quiz" | "classic_quiz" | "not_a_quiz",
"recommended_path": "reporting_api" | "submission_data" | "submitted_proxy" |
"none"}`.

Don't assume. The four real signals:
- `submission_types == ["external_tool"]` is necessary but NOT
  sufficient for "is a NQ" — could be a regular LTI tool
- `external_tool_tag_attributes.url` containing `quiz-lti` or
  `quiz_lti` is the confirming pattern
- `submission_types == ["online_quiz"]` is unambiguous Classic Quiz
- An `assignment` with `quiz_id` set + `online_quiz` is Classic; the
  `quiz_id` field is NULL on NQ assignments

## Why this matters

Skipping the detection step is how m119 / ds460 / itm327 each spent
~2 hours independently rediscovering the API wall before finding the
workaround. This note + the detector helper close that loss for
everyone else.

---
name: canvas_api_knowledge
version: '1.0'
last_updated: '2026-07-16'
description: 'What Canvas''s own documentation says about its REST API: endpoints, data model, permission scopes, pagination, and the patterns Canvas itself describes. Empirical findings the toolkit discovered through use (the things Canvas does NOT docum'
skill_type: knowledge
shape: reference
scope: 'Canvas''s REST API surface as Canvas documents it. Mental models, universal patterns, per-resource endpoint pointers — all sourced from Instructure''s own published documentation (rendered docs site + open-source canvas-lms YARD comments). Empirical findings live in the paired file canvas_api_lessons_learned.md. Out of scope: project conventions, canvas-toolbox tool patterns, GraphQL, LTI launch internals.'
consumed_by:
- canvas_course_expert.md
- canvas_schedule_auditor.md
- canvas_semester_setup.md
- canvas_blueprint_sync.md
- canvas_content_sync.md
- canvas_new_course_setup.md
provenance:
  sources:
  - Canvas LMS REST API canonical documentation — https://canvas.instructure.com/doc/api/ (Instructure's published reference docs site).
  - instructure/canvas-lms — https://github.com/instructure/canvas-lms (open-source repo; YARD docstrings in app/controllers/*_controller.rb are Instructure's API documentation as code, canonical when the docs site is unreachable).
  - Canvas LMS Pagination documentation — https://canvas.instructure.com/doc/api/file.pagination.html
  - Canvas LMS OAuth / Authorization documentation — https://canvas.instructure.com/doc/api/file.oauth.html
companion_json_deprecated: 2026-07-16 - consolidated into YAML frontmatter (JSON purge convention)
runtime_strategy: read_at_runtime
metadata:
  knowledge_id: canvas_api_knowledge
---

# Canvas API — Documented Surface

> Reference. What Canvas's own documentation says about its REST API: endpoints, data model, permission scopes, pagination, and the patterns Canvas itself describes. Empirical findings the toolkit discovered through use (the things Canvas does NOT document, or does so incorrectly) live in the paired file [`canvas_api_lessons_learned.md`](canvas_api_lessons_learned.md).

**Sources** (Canvas-authored only):
- Canvas LMS REST API canonical documentation — `https://canvas.instructure.com/doc/api/` (rendered Markdown / HTML reference).
- [instructure/canvas-lms](https://github.com/instructure/canvas-lms) — open-source repository. YARD docstrings in `app/controllers/*_controller.rb` are Instructure's API documentation as code; canonical when the docs site is unreachable (e.g., observed 503s 2026-05-20/21).

The two are Instructure's own writing, in different forms (rendered docs vs. source comments). No third-party sources, no canvas-toolbox tools, no empirical findings appear in `facts[]` or `provenance.sources` for this file.

**Used by:** `canvas_course_expert.md`, `canvas_schedule_auditor.md`, `canvas_semester_setup.md`, `canvas_blueprint_sync.md`, `canvas_content_sync.md`, `canvas_new_course_setup.md`

**Companions:** [`canvas_api_lessons_learned.md`](canvas_api_lessons_learned.md) (the empirical-findings half — paired file; every audit/sync workflow uses both), [`canvas_rubrics_api_survey.md`](../pre_knowledge/rubrics/canvas_rubrics_api_survey.md) (per-resource deep-dive sourced from Canvas docs), [`pages_api_survey.md`](../pre_knowledge/canvas_api/pages_api_survey.md) (per-resource deep-dive sourced from Canvas docs), [`rubrics_knowledge.md`](rubrics_knowledge.md) (rubric quality framework — uses the rubric API surface documented here).

**Scope**: Canvas's REST API surface as Canvas documents it. Covers (a) the data-model facts Canvas's docs describe — three-resource pattern for rubrics, two-ID pattern for classic quizzes, two-step pattern for module items, NewQuiz/ExternalTool REST gap, (b) the universal patterns Canvas documents — pagination via Link header, role-based permission scopes, parameter encoding, (c) per-resource endpoint pointers to the canonical docs and per-resource surveys derived from them. Out of scope: behaviors Canvas does NOT document or documents incorrectly (live in `canvas_api_lessons_learned.md`), canvas-toolbox tool conventions, GraphQL.

**Provenance**: Each fact in the JSON companion's `facts[]` cites either a `canvas.instructure.com/doc/api/<page>.html` URL or an `instructure/canvas-lms/blob/<sha>/app/controllers/<file>.rb` path with YARD-doc line reference. No empirical citations.

_Last updated: 2026-05-21_

> **Version note:** v0.1, untested. Per the canvas-toolbox `0.x` convention, this file is not catalogued in [`knowledge/README.md`](README.md) until promoted to v1.0 (real-course audit verification). Not yet wired into consuming agents' `cross_references.knowledge_files[]` — that is a deliberate downstream step (P-007 Pull Don't Push).

---

## Two Files, One Workflow

Most Canvas-touching agent tasks need both this file and its pair:

| Question | File |
|---|---|
| "What endpoint do I call to do X?" | This file |
| "What's the documented permission scope?" | This file |
| "How does Canvas's docs describe pagination?" | This file |
| "What goes wrong when I call X the documented way?" | [`canvas_api_lessons_learned.md`](canvas_api_lessons_learned.md) |
| "How does the toolkit work around behavior Y?" | [`canvas_api_lessons_learned.md`](canvas_api_lessons_learned.md) |
| "Does Canvas's documented behavior match real behavior here?" | Both — Canvas says X in this file; we observed Y in the lessons file |

Always read both when planning a write or audit operation.

---

## Documented Data Models

These are data-model facts that appear explicitly in Canvas's published API docs. They're not project conventions — Canvas's REST surface is shaped this way by Canvas's design.

### D1 — Rubrics are three resources

Canvas's API docs describe Rubric, RubricAssociation, and RubricAssessment as three distinct resources:

| Resource | Documented at | Owns (per Canvas docs) |
|---|---|---|
| **Rubric** | `/doc/api/rubrics.html` | `criteria[]`, `points_possible`, `free_form_criterion_comments`, `criterion_use_range`, `hide_score_total` (on the rubric template) |
| **RubricAssociation** | `/doc/api/rubric_associations.html` | `use_for_grading`, `hide_score_total` (on the association), `purpose` (`grading` / `bookmark`), `bookmarked`, `association_type` |
| **RubricAssessment** | `/doc/api/rubric_assessments.html` | `assessment_type` (`grading` / `peer_review` / `provisional_grade`), per-criterion `points` + `comments`, `score`, `artifact_id`, `artifact_type` |

The split is Canvas's: `use_for_grading` lives on the **join** (RubricAssociation), not on the rubric template. Deep survey: [`canvas_rubrics_api_survey.md`](../pre_knowledge/rubrics/canvas_rubrics_api_survey.md).

### D2 — Module Items reference content; they are not the content

Canvas's Modules API docs describe Module Items as navigation entries that reference content stored in other resources. A Module Item carries `type` (`Page` | `Assignment` | `Quiz` | `Discussion` | `ExternalTool` | `ExternalUrl` | `SubHeader`), `content_id` (the canvas_id of the referenced resource), and its own `module_item_id`. Creating the content and creating the module item that references it are two separate API calls per Canvas's docs.

### D3 — Classic Quizzes have two canonical IDs

A Classic Quiz is documented in two REST contexts:
- `GET /api/v1/courses/:course_id/quizzes/:id` returns the quiz with `id` (the quiz_id)
- `GET /api/v1/courses/:course_id/assignments/:id` with `submission_types: ["online_quiz"]` returns the same quiz as an assignment with `assignment_id`

Canvas's docs note `quiz_id` is used for quiz-engine operations and `assignment_id` for gradebook operations (including due dates). The two IDs are linked but distinct.

### D4 — New Quizzes are LTI-based

Per Canvas's documentation, New Quizzes is delivered as an LTI 1.3 tool, not as REST resources. The Canvas Quizzes Next / New Quizzes documentation explicitly states that content for New Quizzes is managed in the New Quizzes UI (LTI launch), not via the Quizzes REST API. Same for arbitrary ExternalTool items — the LTI launch surface is the integration point.

### D5 — Classic Quiz vs. Discussion date fields

Canvas's docs document distinct date semantics:
- **Assignments and Classic Quizzes:** `due_at`, `lock_at`, `unlock_at` (assignment override model)
- **Discussions:** `todo_date` (separate field on `PUT /discussion_topics/:id`)

Conflating the two is incorrect per Canvas's data model.

### D6 — Course context vs. Account context

Many resources (Rubrics, Outcomes, OutcomeGroups, Files) can be created at either course scope (`/api/v1/courses/:course_id/...`) or account scope (`/api/v1/accounts/:account_id/...`). Canvas's docs note the permission model differs: course-scoped operations require course-level capabilities; account-scoped require account-admin capabilities.

---

## Documented Universal Patterns

These appear explicitly in Canvas's API documentation as guidance for any consumer.

### U1 — Pagination via `Link` header

Canvas's pagination documentation states all paginated responses return a `Link` header with relations `current`, `next`, `prev`, `first`, `last`. Consumers should follow `rel="next"` until absent. `per_page` query parameter controls page size (default low; max 100 per Canvas's docs, varies by endpoint).

### U2 — Parameter encoding: form-encoded or JSON

Canvas's docs state requests can be made with either `application/x-www-form-urlencoded` or `application/json` payloads. The docs use the form-encoded notation `module[name]=value` to express nested parameters. Both are accepted by the API.

(Caveats on this universal statement live in [`canvas_api_lessons_learned.md`](canvas_api_lessons_learned.md) — empirically, several endpoints accept-but-no-op on JSON for nested parameters.)

### U3 — Permission scopes are role-based

Canvas's API authorization documentation describes a role-based permission model. Operations require named capabilities (e.g., `manage_rubrics`, `manage_assignments`, `read_course_content`). Student tokens, teacher tokens, and admin tokens carry different capability sets. Per Canvas's docs:

| Role | Carries (typical) | Examples of endpoints requiring higher scope |
|---|---|---|
| **Student** | `read_course_content` for enrolled courses | `GET /courses/:id/rubrics` requires `manage_rubrics` — 403 for student tokens |
| **Teacher** | `manage_rubrics`, `manage_assignments`, `manage_grades`, most course-level writes | Account-level operations require admin |
| **Account Admin** | Account-level capabilities | (out of typical toolkit scope) |

### U4 — Include parameter for embedded resources

Canvas's docs document the `include[]` query parameter on many endpoints — request additional embedded resources in the response. Example: `GET /api/v1/courses/:id/assignments?include[]=rubric` returns each assignment with its associated rubric criteria inline. Documented include values vary per endpoint.

### U5 — Standard HTTP verbs

Canvas's docs map HTTP verbs to operations consistently:
- `GET` — read (list or single resource)
- `POST` — create
- `PUT` — update (full replacement for most resources)
- `PATCH` — partial update (supported on some resources)
- `DELETE` — delete

Per Canvas's docs, `POST` to a create endpoint with an existing-resource identifier in the path is implementation-defined per resource (some redirect to `PUT`).

### U6 — Standard HTTP status codes

Per Canvas's API documentation:
- `200` — success
- `201` — created
- `204` — success with empty body (DELETE)
- `400` — validation error (response body carries `errors[]`)
- `401` — authentication failure
- `403` — authorization failure (token lacks capability)
- `404` — resource not found
- `422` — semantic validation error
- `5xx` — Canvas-side error

---

## Per-Resource Endpoint Pointers

Pointer table — full endpoint inventories live in per-resource surveys (or Canvas's canonical docs).

| Resource | Canvas docs page | Repo survey (if exists) | API path roots |
|---|---|---|---|
| **Rubrics** | `/doc/api/rubrics.html` | [`canvas_rubrics_api_survey.md`](../pre_knowledge/rubrics/canvas_rubrics_api_survey.md) | `/courses/:id/rubrics`, `/accounts/:id/rubrics` |
| **Rubric Associations** | `/doc/api/rubric_associations.html` | Same survey | `/courses/:id/rubric_associations` |
| **Rubric Assessments** | `/doc/api/rubric_assessments.html` | Same survey | `/courses/:id/rubric_associations/:rid/rubric_assessments` |
| **Pages** | `/doc/api/pages.html` | [`pages_api_survey.md`](../pre_knowledge/canvas_api/pages_api_survey.md) | `/courses/:id/pages` |
| **Modules** | `/doc/api/modules.html` | (TBD survey) | `/courses/:id/modules`, `.../items` |
| **Assignments** | `/doc/api/assignments.html` | (TBD survey) | `/courses/:id/assignments` |
| **Classic Quizzes** | `/doc/api/quizzes.html` | (TBD survey) | `/courses/:id/quizzes`, `.../quiz_questions` |
| **New Quizzes (LTI)** | `/doc/api/new_quizzes.html` (or noted as LTI) | n/a — REST gap | LTI 1.3 launch surface |
| **Discussion Topics** | `/doc/api/discussion_topics.html` | (TBD survey) | `/courses/:id/discussion_topics` |
| **Outcomes** | `/doc/api/outcomes.html` + `/doc/api/outcome_groups.html` | (TBD survey) | `/courses/:id/outcomes`, `/outcome_groups` |
| **Files** | `/doc/api/files.html` | (TBD survey) | `/courses/:id/files` |
| **Blueprint Courses** | `/doc/api/blueprint_courses.html` | (TBD survey) | `/courses/:bp/blueprint_templates`, `/blueprint_subscriptions` |
| **Courses** | `/doc/api/courses.html` | (TBD survey) | `/courses/:id` |
| **Submissions** | `/doc/api/submissions.html` | (TBD survey) | `/courses/:id/assignments/:aid/submissions` |
| **Users / Enrollments** | `/doc/api/users.html`, `/doc/api/enrollments.html` | (TBD survey) | `/courses/:id/users`, `/courses/:id/enrollments` |

---

## Out of Scope

- **Empirical behaviors and footguns** — live in [`canvas_api_lessons_learned.md`](canvas_api_lessons_learned.md).
- **canvas-toolbox tool conventions** — pagination helpers, safety guards, idempotent-upsert patterns. Those are project decisions, not Canvas-documented.
- **GraphQL.** Canvas's GraphQL API surface is documented separately at Canvas; the toolkit uses REST only.
- **LTI 1.3 integration** for New Quizzes / ExternalTool content. Per-vendor; outside REST.
- **Live Events / streaming.** Canvas's webhook and live-event APIs are out of audit scope.

---

## Pairs With

- [`canvas_api_lessons_learned.md`](canvas_api_lessons_learned.md) — the empirical companion. Read both when planning any write or audit.
- [`rubrics_knowledge.md`](rubrics_knowledge.md) — the rubric quality framework that runs on top of the rubric API surface documented here.
- [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) — outcomes framework; pairs with the alignment-chain audit that uses the documented `?include[]=rubric` and outcomes endpoints.

---

## References

Full provenance per fact in `provenance.sources` of the JSON companion. Per-resource deep-dives in `pre_knowledge/canvas_api/` and `pre_knowledge/rubrics/`.

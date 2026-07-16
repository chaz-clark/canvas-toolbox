---
name: canvas_api_lessons_learned
version: '1.0'
last_updated: '2026-07-16'
description: 'The 18 Canvas REST API behaviors the canvas-toolbox discovered through production use — behaviors Canvas does NOT document, documents incorrectly, or where the documented behavior diverges from observed behavior. Each lesson cost real time '
skill_type: knowledge
shape: reference
scope: 'Behaviors Canvas exhibits that are NOT in Canvas''s own documentation, OR that contradict it. The 16 footguns the canvas-toolbox has hit and defended against in production, plus cross-cutting patterns that bake the defenses into new tools. Out of scope: documented Canvas behavior (lives in canvas_api_knowledge.md); speculative behaviors not yet reproduced.'
consumed_by:
- canvas_course_expert.md
- canvas_schedule_auditor.md
- canvas_semester_setup.md
- canvas_blueprint_sync.md
- canvas_content_sync.md
- canvas_new_course_setup.md
provenance:
  sources:
  - 'GitHub issues capturing each empirical finding: #25 (vendored-tool drift + module_settings_sync de-hardcoding + clear-quirk), #26 (Page idempotent upsert), #27 (startup safety guard), #28 (Blueprint exception report), #29 (Page-level integrity audit).'
  - 'Production incidents: ITM-327 (4× page duplication; L12 + L15 amplification), W01 (lock-state-only body reversion observed 2026-05-20; L14).'
  - 'Defending tools in lib/tools/: canvas_pages.py, canvas_course_guard.py, blueprint_exception_report.py, blueprint_orphan_pages.py, module_settings_sync.py, canvas_quiz_questions.py, course_quality_check.py, canvas_sync.py.'
  - 'Defending agents: canvas_semester_setup.md, canvas_new_course_setup.md.'
  - AGENTS.md External System Lessons table — migrated here 2026-05-21; AGENTS.md retains a pointer.
companion_json_deprecated: 2026-07-16 - consolidated into YAML frontmatter (JSON purge convention)
runtime_strategy: read_at_runtime
metadata:
  knowledge_id: canvas_api_lessons_learned
---

# Canvas API — Lessons Learned (Empirical Companion)

> Reference. The 18 Canvas REST API behaviors the canvas-toolbox discovered through production use — behaviors Canvas does NOT document, documents incorrectly, or where the documented behavior diverges from observed behavior. Each lesson cost real time before becoming a lesson. Paired with [`canvas_api_knowledge.md`](canvas_api_knowledge.md) (the Canvas-documented-only half).

**Sources** (canvas-toolbox empirical only):
- GitHub issues that captured each finding: #25 (vendored-tool drift + module_settings_sync de-hardcoding + clear-quirk), #26 (Page idempotent upsert), #27 (startup safety guard), #28 (Blueprint exception report), #29 (Page-level integrity audit).
- Production incidents that drove each fix: ITM-327 (4× page duplication across master/blueprint/sections via stale `.env` + non-idempotent writes), W01 (lock-state-only body reversion observed 2026-05-20).
- Defending tools in `lib/tools/`: `canvas_pages.py`, `canvas_course_guard.py`, `blueprint_exception_report.py`, `blueprint_orphan_pages.py`, `module_settings_sync.py`, `canvas_quiz_questions.py`, `course_quality_check.py`, `canvas_sync.py`, `canvas_semester_setup.md` agent.
- AGENTS.md External System Lessons table (now migrated here; AGENTS.md retains a pointer).

**Used by:** `canvas_course_expert.md`, `canvas_schedule_auditor.md`, `canvas_semester_setup.md`, `canvas_blueprint_sync.md`, `canvas_content_sync.md`, `canvas_new_course_setup.md`

**Companions:** [`canvas_api_knowledge.md`](canvas_api_knowledge.md) (the Canvas-docs companion — always read both together), [`canvas_rubrics_api_survey.md`](../pre_knowledge/rubrics/canvas_rubrics_api_survey.md) (rubric-specific gotchas in the wider survey form), [`pages_api_survey.md`](../pre_knowledge/canvas_api/pages_api_survey.md) (page-specific gotchas in survey form), [`rubrics_knowledge.md`](rubrics_knowledge.md), [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md).

**Scope**: Behaviors Canvas exhibits that are NOT in Canvas's own documentation, OR that contradict it. Covers (a) the 18 footguns the toolkit has hit and defended against, (b) the audit indicators that surface these footguns in real courses, (c) the tool-author checklist that bakes the defenses into new code. Out of scope: documented Canvas behavior (lives in [`canvas_api_knowledge.md`](canvas_api_knowledge.md)).

**Provenance**: Each fact in the JSON companion's `facts[]` cites the issue / commit / incident where the lesson was discovered, and the in-repo tool that now defends against it. No facts here have a Canvas-authored citation — by design, this file documents what Canvas does NOT document.

_Last updated: 2026-06-01_

> **Version note:** v0.1, untested as a knowledge file (though every individual lesson IS exercised against production via the defending tools). Per the canvas-toolbox `0.x` convention, this file is not catalogued in [`knowledge/README.md`](README.md) until promoted to v1.0. Not yet wired into consuming agents' `cross_references.knowledge_files[]`.

---

## Why This File Exists

Canvas's REST API is not a clean abstraction over Canvas's data model — it's a thin wrapper over the Ruby controllers that back the web UI. Several "obvious" REST operations either go through unexpected paths, accept-but-ignore parameters that look like they work, or silently misbehave on the second-most-common case. Treating Canvas's docs as complete leads to silent data corruption (Page duplication, Blueprint sync skips, decorative rubrics) that surfaces weeks or months later.

This file is the project's institutional memory of those behaviors. Every fact here has a defending tool in `lib/tools/`; if the lesson is documented but the defense is missing, that's a bug.

**Read alongside [`canvas_api_knowledge.md`](canvas_api_knowledge.md):** that file tells you what Canvas's docs say to do. This file tells you what actually happens.

---

## The 19 Lessons

Each lesson follows the same structure: **what Canvas does** (the behavior), **why it matters** (the failure mode), **how the toolkit handles it** (the defense), and **provenance** (issue / commit / incident).

### L1 — Module prerequisites silently fail with JSON payload

**What Canvas does:** `PUT /api/v1/courses/:id/modules/:mid` with a JSON payload setting `module[prerequisite_module_ids]` returns 200 OK but does NOT actually set the prerequisite. The response looks successful.

**Why it matters:** The gating chain between sprints silently breaks. Students reach later sprints without completing earlier ones. The instructor cannot diagnose from the UI because Canvas displays the prerequisite as set in some views and unset in others.

**How the toolkit handles it:** Form-encoded payload: `data={"module[prerequisite_module_ids][]": id}`. Setting it as form-encoded (not JSON) makes Canvas actually persist the prerequisite.

**Provenance:** `module_settings_sync.py` policy layer (#25 Part 2). Discovered during ITM-327 series.

### L2 — Module published state is form-encoded too

**What Canvas does:** Same JSON-vs-form-encoded silent-no-op as L1, for `module[workflow_state]`.

**Why it matters:** Modules appear published in API responses (the JSON state is reflected) but Canvas's gating logic uses a different code path that respects only the form-encoded write.

**How the toolkit handles it:** `data={"module[workflow_state]": "active"|"unpublished"}`.

**Provenance:** `module_settings_sync.py`, `blueprint_sync.py`. Same pattern as L1.

### L3 — Semester due-date updates fail without `lock_at: null` and `unlock_at: null`

**What Canvas does:** `PUT /quizzes/:id` with only `due_at` set returns 400 when the quiz retains a prior-semester `lock_at` or `unlock_at` window. Canvas's docs don't surface this constraint.

**Why it matters:** Reading Quizzes (the common Classic Quiz pattern) carry prior-semester availability windows that don't auto-clear. A semester roll that updates only `due_at` produces a wall of 400s for every reading quiz.

**How the toolkit handles it:** Always send all three together when rolling dates forward:

```python
data = {"quiz[due_at]": new_due, "quiz[lock_at]": None, "quiz[unlock_at]": None}
```

**Provenance:** `canvas_semester_setup.md` agent + sync tools. Discovered during early semester-roll work.

### L4 — `late_policy` PATCH returns 403 for instructor tokens

**What Canvas does:** `PATCH /api/v1/courses/:id/late_policy` returns 403 even with a teacher-token that carries `manage_grades`. Canvas requires admin-level scope for the operation.

**Why it matters:** Tools cannot programmatically configure missing-submission and late-submission policies. The new-course setup flow has to break for manual UI configuration.

**How the toolkit handles it:** `canvas_new_course_setup.md` agent documents the manual step (Canvas Settings → Gradebook). Admin-token holders can automate.

**Provenance:** `canvas_new_course_setup.md` agent runbook.

### L5 — Classic quiz `points_possible` may show 0 after question push

**What Canvas does:** Pushing questions to a Classic Quiz via `POST /quizzes/:id/questions` causes Canvas to auto-calculate `points_possible` from the question sum — but the quiz object's `points_possible` field is NOT updated to reflect this. Gradebook shows 0 until a manual refresh in the UI.

**Why it matters:** Auto-graded quizzes show as 0-point in the gradebook the moment students submit. Students see "0 / 0" on a multi-point quiz.

**How the toolkit handles it:** Explicit `PUT /quizzes/:id {"quiz": {"points_possible": N}}` after the question push.

**Provenance:** `canvas_quiz_questions.py`.

### L6 — Classic quizzes have two IDs

**What Canvas does:** Documented — Canvas's quiz docs DO describe the two-ID pattern (covered in `canvas_api_knowledge.md` D3). The lesson here is what the toolkit had to do to handle it.

**Why it matters:** Audit tools comparing module references to assignment dates naively report false "not in module" positives — they look up the quiz_id in the assignments table and miss the assignment_id mapping.

**How the toolkit handles it:** Maintains a `quiz_id ↔ assignment_id` index per course; resolves both directions before flagging.

**Provenance:** `course_quality_check.py`.

### L7 — Discussions use `todo_date`, not `due_at`

**What Canvas does:** Documented date semantics (covered in `canvas_api_knowledge.md` D5). The lesson is that the toolkit had to learn this through 400 errors before reading the docs.

**Why it matters:** `PUT /discussion_topics/:id` with `due_at` either no-ops silently or returns a confusing 400.

**How the toolkit handles it:** Discussion-specific date handling in `canvas_sync.py`.

**Provenance:** `canvas_sync.py` Discussion path.

### L8 — NewQuiz / ExternalTool items can't be content-pushed via REST

**What Canvas does:** New Quizzes (formerly Quizzes.Next) is a separate **LTI 1.3 tool**, not part of the core Canvas REST API (`/api/v1/`). In the core API a New Quiz surfaces only as an **Assignment shell** with `submission_types == ["external_tool"]`: the assignment *metadata* (title, points, due dates, module placement) is REST-addressable, but the quiz *body* (questions/items, settings, stimulus) lives in the New Quizzes engine, exposed through a **separate API at `/api/quiz/v1/`**. Classic Quizzes, by contrast, is fully REST-addressable (`/api/v1/courses/:id/quizzes` + `quiz_questions`), which is why Classic content syncs cleanly and New does not. (LTI integration is documented in `canvas_api_knowledge.md` D4; this lesson is the empirical sync consequence.)

**Read/write asymmetry (the crux):** The `/api/quiz/v1/` engine API supports **reads** — the toolkit pulls a read-only sidecar of a New Quiz's settings + items (`_pull_new_quiz_sidecar` → `quiz_engine: new_quiz`). But there is **no reliable REST create/write path** for the quiz content. So a sync tool can recreate the assignment *shell* (the external_tool link) in a target course, yet has no API to repopulate the questions — and the recreated link points at source-course quiz content that doesn't exist in the target.

**Why it matters:** Both the module shell and the assignment shell sync, and the API reports success, so the operation *looks* clean — but the item body lands **empty** in the target: students see a module entry / assignment with no quiz behind it. The failure is silent; nothing errors.

**Detection signal:** The toolkit classifies an assignment as `NewQuiz` when `submission_types == ["external_tool"]` (`canvas_sync.py:674`). That plus `ExternalTool`, `ExternalUrl`, and the sub-header types form `NO_PUSH_TYPES`.

**How the toolkit handles it:** Sync scripts **warn-and-skip** anything in `NO_PUSH_TYPES` with a pre-write warning; `course_quality_check.py` flags the resulting empty/floating items afterward. Read-only New Quiz content is preserved in the sidecar for backup/inspection, not re-pushed. **Correct remediation** (what actually moves a New Quiz between courses): Canvas's own server-side machinery — **content migration / course copy / blueprint association** — not REST item recreation. `course_mirror.py` explicitly notes New Quiz content must be set manually in Canvas.

**Provenance:** `canvas_sync.py` (`_get_new_quiz` → `/api/quiz/v1/`, `_pull_new_quiz_sidecar`, NewQuiz detection at :674), `blueprint_sync.py` / `course_mirror.py` (`NO_PUSH_TYPES`, warn-and-skip), `course_quality_check.py` (post-sync flag).

**Prevalence (rising, Instructure-wide):** New Quizzes is no longer a niche opt-in. Instructure enables New Quizzes **by default for all users on 2026-07-01** and **enforces it 2026-08-15** (Classic Quizzes phased out, no announced EOL). Some institutions flipped early (e.g. BYUI: every course, Winter 2026). Consequence: the L8 sync gap now affects a fast-growing share of courses, not an edge case — the warn-and-skip path will fire far more often. (Source: Instructure Community "New Quizzes Native Integration | Q1 2026"; BYUI EdTech-2026 post → `pre_knowledge/byui_learning_teaching/byui_edtech_2026.md`.)

### L9 — Workaround: `GET /assignments?include[]=rubric` works for student tokens

**What Canvas does:** `GET /api/v1/courses/:id/rubrics` requires `manage_rubrics` (teacher-token); returns 403 for student tokens. This permission boundary IS documented. The lesson is the discovered workaround.

**Why it matters:** Student-token-safe audit tools cannot list rubrics by the documented path.

**How the toolkit handles it:** `GET /api/v1/courses/:id/assignments?include[]=rubric` returns each assignment's rubric criteria inline and works for student tokens. Per-assignment iteration replaces the rubric list. Does NOT return RubricAssociation metadata (`use_for_grading`, `purpose`); for those, teacher-token + `/rubric_associations` is required.

**Provenance:** `course_quality_check.py:588-594` (`--alignment` audit).

### L10 — Empty modules are a sync artifact

**What Canvas does:** When all items in a module are NewQuiz / ExternalTool, the module shell syncs but lands empty in the target (L8 cascade).

**Why it matters:** Students see a module label with nothing in it. Looks like a content gap, is actually a sync-skip side effect.

**How the toolkit handles it:** Sync scripts pre-warn the operator; `course_quality_check.py` flags post-sync.

**Provenance:** `course_quality_check.py` default structural mode.

### L11 — Blueprint migration reports `workflow_state: completed` even when items silently skipped

**What Canvas does:** `GET /api/v1/courses/:bp/blueprint_templates/default/migrations/:mid` returns `state: completed` regardless of per-section `exceptions[].conflicting_changes`. Per-section migration-details endpoint records the actual skips. The migration-level state does NOT.

**Why it matters:** Trusting `completed` produces a false "sync worked" signal. **Real incident: ITM-327 S2 skipped 51 of 80 items with migration state `completed`.** No operator alert; discovered weeks later when content drift was reported.

**How the toolkit handles it:** Read the subscriber-side migration-details endpoint per associated course. Group exceptions by `conflicting_changes` type; emit PASS / WARN / FAIL per type. `content` and `deleted` exceptions → FAIL (resync after locking the item). `points`, `state`, `settings` → WARN. `due_dates`, `availability_dates` → PASS.

**Provenance:** `blueprint_exception_report.py` (#28).

### L12 — A stale `.env` can silently point a write-capable tool at the wrong course

**What Canvas does:** `CANVAS_COURSE_ID` / `MASTER_COURSE_ID` / `BLUEPRINT_COURSE_ID` are env vars the toolkit reads. Canvas's API has no notion of "is this the right kind of course for this operation?" — a write to an enrolled section or a Blueprint child course succeeds at the Canvas level but does the wrong thing.

**Why it matters:** Combined with non-idempotent writes, this amplifies catastrophically. **Real incident: ITM-327 produced 4× page duplication across master/blueprint/2 sections — the same page POSTed in each course where `CANVAS_COURSE_ID` happened to be pointed at the time, with Canvas's title-collision auto-suffix (see L15) creating `page-2` / `page-4` / `page-5`.**

**How the toolkit handles it:** Startup safety guard before any write — `canvas_course_guard.enforce()` GETs `?include[]=total_students` + `/blueprint_subscriptions`, hard-stops (`sys.exit(2)`) when the target is enrolled (`total_students > 0`) or a Blueprint child (non-empty subscriptions), unless `--allow-enrolled` is passed.

**Provenance:** `canvas_course_guard.py` (#27). Wired into `canvas_sync.py`, `course_mirror.py`, `blueprint_sync.py`, `course_quality_check.py`.

### L13 — Canvas's UI sync creates `-N` slug orphan Pages

**What Canvas does:** When a Blueprint sync re-pushes a locked Page into a section that previously deleted its copy, Canvas creates a new page at `slug-2` (or `-N` for repeated cycles) carrying the canonical content — but does NOT update the unsuffixed slug the module item still points at.

**Why it matters:** Silent split between *content* (the new `-N` page) and *navigation* (the module item still pointing at the unsuffixed slug). Students follow the module link and see stale section-local content; the canonical material exists but is unreachable from navigation. Section-side delete of either is blocked while the master is locked (403).

**How the toolkit handles it:** Detection via 5-point fingerprint: (1) A's slug ends in `-N`, B's doesn't; (2) same title; (3) A's body hash matches blueprint's canonical; (4) B's body hash differs from blueprint's canonical; (5) A is NOT linked from any module item, B IS. Cleanup path is unlock → PUT canonical body onto unsuffixed slug → DELETE `-N` orphan → re-lock (deferred to Phase 2 per #29 ticket).

**Provenance:** `blueprint_orphan_pages.py` Detector A (#29 Phase 1, read-only).

### L14 — Canvas's lock-state-only sync can silently revert section page bodies

**What Canvas does:** A locked Page in a section can be overwritten with a body hash that **never** existed in the blueprint's revision history. Migration reports `state: completed` with zero exceptions. **This directly contradicts Canvas's published documentation** ("Changed content will always overwrite the existing content in the associated courses for all locked objects").

**Why it matters:** The strongest reversion signal — section page body has no provenance in any blueprint revision. Likely cross-section contamination via the master-link. Observed deterministically on 2026-05-20 (incident W01) on the lock-state-only sync path (a Blueprint UI sync that carried only lock-state metadata changes, no body diffs).

**How the toolkit handles it:** Flag section pages whose body has no provenance in blueprint's `revisions[]` history. **Operator warning printed when this fires:** do NOT run a Blueprint UI sync that only carries lock-state metadata changes (no body diffs). Sync only when intentional body edits exist on the blueprint — that is the safer path.

**Provenance:** `blueprint_orphan_pages.py` Detector B (#29 Phase 1). Underlying behavior reproduced and documented 2026-05-20.

### L15 — Canvas auto-suffixes a Page URL on title collision

**What Canvas does:** `POST /api/v1/courses/:id/pages` with a title that already exists on another page in the same course silently creates a second page at `…-2` / `-4` / `-5`. Canvas's docs don't surface this as a hazard for programmatic clients.

**Why it matters:** Repeated non-idempotent pushes (each `canvas_sync --push` re-POSTs every page) duplicate the same page on every run. Combined with L12 (stale `.env` pointing at multiple courses), this is the root cause of the ITM-327 4× duplication.

**How the toolkit handles it:** Title-existence check before any POST. `canvas_pages.upsert_page()` flow: (1) GET `/courses/:id/pages?search_term=<title>` and filter exact-match client-side; (2) if 1 match → PUT to update; (3) if 0 matches → POST to create; (4) if >1 match → route to manual review (don't guess). `page_in_module()` guards the module-item link to prevent duplicate links to the same canonical page.

**Provenance:** `canvas_pages.py` (#26).

### L16 — Clearing a module-item completion requirement needs the whole object blanked

**What Canvas does:** `PUT /api/v1/courses/:id/modules/:mid/items/:iid` with `data={"module_item[completion_requirement][type]": ""}` returns `400 Invalid completion requirement type`. Canvas's docs describe how to SET a completion requirement but not how to CLEAR one.

**Why it matters:** Tools that manage completion requirements need both set and clear paths. The naive empty-string for `[type]` doesn't work.

**How the toolkit handles it:** Clear the whole object: `data={"module_item[completion_requirement]": ""}` (blank the entire field). Setting still uses `data={"module_item[completion_requirement][type]": "must_submit"}`.

**Provenance:** `module_settings_sync.py` (#25).

### L17 — Blueprint `asset_type` vocabulary differs between two endpoints

**What Canvas does:** The same conceptual asset is named in **two different vocabularies** depending on the Blueprint endpoint. `unsynced_changes` (pre-sync) returns **lowercase snake_case** (`wiki_page`, `assignment`, `assignment_group`, `quizzes::quiz`); `migration-details` (post-sync, the `ChangeRecord.asset_type`) returns **Rails CamelCase class names** (`WikiPage`, `Assignment`, `Quizzes::Quiz`, `DiscussionTopic`, `ContextExternalTool`). Neither set matches the other, and a lookup table built for one silently misses on the other.

**Why it matters:** A map keyed for migration-details (CamelCase) returns `None` for every `unsynced_changes` value, and vice-versa — a silent miss, not an error. (#37: `blueprint_presync_check --suggest-locks` punted every lock to "do it in the UI" because it reused #28's CamelCase `ASSET_TYPE_MAP` against snake_case `unsynced_changes` values.) Conveniently, the **`unsynced_changes` snake_case values are already the `restrict_item` `content_type` values** (`wiki_page`→`wiki_page`, `assignment`→`assignment`), so no translation is needed there — only `quizzes::quiz`→`quiz` and `context_external_tool`→`external_tool` need normalizing.

**How the toolkit handles it:** `blueprint_presync_check.py` keeps its own snake_case `_LOCKABLE_CONTENT_TYPE` map (passthrough + the two qualified-name normalizations) instead of importing #28's CamelCase map; `blueprint_exception_report.py` keeps its CamelCase `ASSET_TYPE_MAP` for migration-details. Two endpoints, two maps — don't share one.

**Provenance:** `blueprint_presync_check.py` (#36/#37), `blueprint_exception_report.py` (#28).

### L18 — Canvas does NOT update / strip `data-api-*` enrichment when an `<a href>` is later swapped

**What Canvas does:** When a user (or the API) inserts a link to a Canvas-internal resource into a Page/Assignment/Quiz/Discussion description, Canvas auto-injects `data-api-endpoint="…/api/v1/courses/{id}/{type}/{id}"` and `data-api-returntype="Page|Assignment|Quiz|Discussion|…"` attributes on the `<a>` tag. If the `href` is later swapped (to a different Canvas resource OR to an external URL like `video.byui.edu/media/t/…`), Canvas leaves the original `data-api-*` attributes in place — they do **not** track the new `href`.

**Why it matters:** The link **clicks** correctly (browsers follow `href`, not `data-api-*`), so the bug is invisible at first glance. But:
- Canvas's hovercard/preview UI uses `data-api-endpoint` — it will try to fetch and render the **old** target (e.g. preview a discussion when the link now points at a Kaltura video).
- Audit tools reading `data-api-endpoint` (vs `href`) misreport where a link points — false positives for "still references the old thing" even when the visible link is correct.
- Description hashes / diffs become noisy — the metadata residue makes "is this content current?" hard to answer.

**Provenance incident (#42):** ITM 327 Lab 1/2 walkthrough `href` swap (2026-06-03). The cleanup was a second PUT that regex-stripped the orphan `data-api-endpoint` + `data-api-returntype` attributes. Same residue propagated through Blueprint sync to two live sections before cleanup.

**How the toolkit handles it:** Shared stdlib helper `lib/tools/_link_metadata.py` — `strip_stale_link_metadata(html) → (normalized_html, count)`. Idempotent. Detection rule: parse `href` and `data-api-endpoint` into canonical `(course_id, resource_path)` form; if they disagree (different resource, different course, or `href` is external) → strip both `data-api-*` attributes. Matching pairs are left untouched. Read-only companion `find_stale_link_metadata(html) → [findings]` powers an opt-in `course_quality_check.py --link-metadata` audit. Writer-side wire-in (auto-normalize on every PUT through `blueprint_sync.py` / `course_mirror.py`) is the planned follow-up after the opt-in audit validates the detector on real fleet data.

**Provenance:** `_link_metadata.py` + `course_quality_check.py --link-metadata` (#42). Companion `lib/tests/test_link_metadata.py` covers the matching-pair / stale / external-href / idempotency / multi-anchor cases.

---

### L19 — "Submit on behalf of student" is a GraphQL mutation, not the REST `/submissions` endpoint

**What Canvas does:** `POST /api/v1/courses/:id/assignments/:aid/submissions` (with `submission[user_id]`) is a *general grading* call — it respects the assignment's lock date and records no proxy submitter, so on a locked/past-due assignment it is rejected (403, sometimes 400). This looks like an institutional block but is the **wrong endpoint**. The actual "Submit on behalf of student" feature is the GraphQL `createSubmission` mutation (`POST /api/graphql`): passing **`studentId`** flips the call into a *proxy submission*, which is authorized by the **proxy-submission permission** (not the normal submit right), **skips the lock**, and stamps **`proxySubmitter`** (the instructor's name) as in-Canvas evidence. `submissionType: online_upload` is a GraphQL **enum — unquoted**.

**Why it matters:** This is the sanctioned way to submit a Slack/emailed file for a student after an assignment locks, with no date changes and a clean audit trail — exactly the accommodation case `submit_on_behalf.py` exists for. The REST 403 previously read as "BYU-I disabled it," sending the toolkit down a manual-SpeedGrader workaround; the real fix was the endpoint.

**The two-step gotcha:** the mutation's `fileIds` must point at an attachment that lives in the **student's** submission files. Upload to `.../assignments/:aid/submissions/:user_id/files` (the instructor's grading permission authorizes it); a file from the instructor's own `/courses/:id/files` is **rejected** by the mutation. Group assignments upload to `/groups/:group_id/files` instead — mutation identical.

**How the toolkit handles it:** `lib/tools/submit_on_behalf.py` — `upload_file_to_student_submission()` (student-scoped 3-step upload) → `submit_on_behalf()` (the `createSubmission` proxy mutation, checks both transport-level and mutation-level `errors`, returns the `submission` incl. `proxySubmitter`). `--comment` is a separate REST call on the now-existing submission (the mutation takes none). Dry-run by default; `--apply` to execute.

**Provenance:** endpoint verified against the live BYU-I instance + Canvas source by the Canvas admin (2026-07-13); the browser Gradebook "Submit for Student" button fires this exact call. Prerequisite: proxy-submission permission enabled in the account (now on for all courses). Relates to L4 (instructor-token 403 on the wrong endpoint).

---

### L20 — Grades pushed under a MANUAL posting policy are entered but HIDDEN, not "stuck"

**What Canvas does:** `PUT .../submissions/:user_id` with `submission[posted_grade]` sets the grade and transitions `workflow_state` to `graded` correctly — but if the assignment's posting policy is **manual** (`post_manually: true`), the grade is **not released**: `posted_at` stays `null`, the student can't see it, and the gradebook reads **"needs grading."** This looks like a workflow_state bug but is the posting policy. `submission[workflow_state]` is **not** a settable parameter — Canvas ignores it — so "force the state to graded" fixes are a no-op. Verified on the sandbox: the *identical* `posted_grade` call leaves `posted_at` set under an automatic policy and `null` under a manual one.

**Why it matters:** a bulk API grading run against manual-posting assignments (e.g. pass/fail Core Tasks) leaves every grade entered-but-invisible — it reads as done to the script and as "needs grading" to the instructor. The naive "fixes" (a null→value double-PUT, or setting `workflow_state`) don't *post* the grade; only posting does.

**The fix:** release grades with the GraphQL `postAssignmentGrades` mutation (`POST /api/graphql`) — the same action as the Gradebook "Post grades" button; there is no REST endpoint for it. `postAssignmentGrades(input: {assignmentId, gradedOnly: true})`. Detect the condition by reading the assignment's `post_manually`, or a pushed submission's `posted_at == null` while `grade` is set. Setting the posting policy itself via API is still only a feature request (canvas-lms#2517); posting after the fact is the supported path.

**How the toolkit handles it:** `lib/tools/grader_push.py` — after a push, `assignment_posts_manually()` checks the policy; if manual it warns that grades are entered-but-hidden, and `--post` releases them via `post_assignment_grades()` (the GraphQL mutation). Never auto-posts without the flag (posting is student-facing).

**Provenance:** issue #199 (DS460 run — grades across pass/fail sprints read "needs grading", 2026-07-15); root cause + fix reproduced end-to-end on sandbox 427808 (2026-07-16): auto policy posts, manual policy hides, `postAssignmentGrades` releases. Canvas dev docs confirm `workflow_state` is a response-only field.

---

## Cross-Cutting Patterns

These are the toolkit conventions that bake defenses against the 20 lessons into every new tool.

### P-LL1 — Form-encoded for nested writes (defends L1, L2, L16)

Default to `application/x-www-form-urlencoded` for any write that uses the nested `parent[child]` parameter shape. JSON works for flat objects; for anything nested, form-encoded is the safer path. Canvas's docs say either works (U2 in `canvas_api_knowledge.md`); empirically, several endpoints accept-but-no-op on JSON.

### P-LL2 — Date writes always send `due_at` + `lock_at` + `unlock_at` (defends L3)

Even when only changing `due_at`, send all three with explicit null for the others if not setting them. Pre-empts the 400-on-stale-window failure mode.

### P-LL3 — Idempotent writes via title-existence check (defends L15, prevents L12 amplification)

Every create must check title-existence first. Reference: `canvas_pages.upsert_page()`. Generalize the pattern to any resource where Canvas auto-suffixes on collision.

### P-LL4 — Startup safety guard for writes (defends L12)

Every write tool wires in `canvas_course_guard.enforce()` before any mutation. Read tools call it advisory-only.

### P-LL5 — Plan-first, apply-second with explicit confirmation (defends every L)

Operations that modify Canvas emit a plan; require explicit operator confirmation; THEN apply. `--plan` default / `--apply` confirmation-gated. Reference: `module_settings_sync.py`. Pre-empts amplification of any of the 16 by giving the operator a chance to abort.

### P-LL6 — Post-write verification (defends L5, L11)

After any write, GET the affected resource and verify the change took. L5 (quiz points_possible) and L11 (Blueprint migration silent skips) both require post-write reads to detect. `blueprint_exception_report.py` is the post-write reader for Blueprint sync.

### P-LL7 — Polite throttling and pagination (universal hygiene)

Use `per_page=100` for list reads (U1 in canvas_api_knowledge). Add request timeouts (the toolkit uses 20-30s). Don't hammer Canvas — every tool here paginates and respects `Retry-After` headers when they appear.

---

## Audit Indicators

When these signals appear in audit output, route to the indicated lesson + defending tool:

| Signal | Lesson | Tag emission | Defending tool |
|---|---|---|---|
| Page exists at `slug-N` (N ≥ 2) with unsuffixed slug carrying stale body | L13 | `page_orphan: true` | `blueprint_orphan_pages.py` Detector A |
| Section page body has no provenance in blueprint revisions | L14 | `page_reversion: true` + operator warning | `blueprint_orphan_pages.py` Detector B |
| Module item exists but `content_id` 404s | L8 | `floating_item: true` | `course_quality_check.py` |
| Module without items (or only NewQuiz/ExternalTool items) | L10 | `empty_module: true` | `course_quality_check.py` |
| Quiz with `points_possible: 0` after question push | L5 | `quiz_points_drift: true` | `canvas_quiz_questions.py` |
| Target course `total_students > 0` and write tool invoked | L12 | `guard_blocked: true` | `canvas_course_guard.py` |
| Blueprint migration `state: completed` with non-empty `exceptions[]` | L11 | `migration_silent_skip: true` | `blueprint_exception_report.py` |
| Multiple pages with same title in one course | L15 | `page_duplicate: true` | `course_quality_check.py --files` |
| Module prerequisite chain shows as set in JSON GET but doesn't gate | L1 | `module_prereq_broken: true` | `module_settings_sync.py` |
| Module-item completion requirement won't clear | L16 | `module_item_clear_failed: true` | `module_settings_sync.py` |

---

## Quick Reference for Tool Authors

When building a new Canvas-touching tool, run through this checklist:

1. **Read both knowledge files first.** `canvas_api_knowledge.md` for what Canvas's docs say; this file for what Canvas actually does. Identify which lessons apply.
2. **Token scope.** Decide teacher vs student token. Document. If write tool, teacher token + safety guard. If read tool and student-token-safe paths exist, prefer them (L9 workaround pattern).
3. **Encoding.** Any nested parameter (`module[...]`, `quiz[...]`, `rubric[criteria][...]`)? Default to form-encoded (P-LL1).
4. **Idempotency.** Will your operation run repeatedly? Title-existence check (P-LL3).
5. **Safety guard.** Write tool? Wire in `canvas_course_guard.enforce()` (P-LL4).
6. **Date writes.** Always send the trio (P-LL2).
7. **Plan + confirm + apply.** Never silently mutate (P-LL5).
8. **Post-write verification.** GET the affected resource and verify (P-LL6).
9. **Pagination + throttling.** `per_page=100`, follow Link rel="next" (P-LL7).
10. **Exit codes.** 0 = no findings / write applied. 1 = findings (audit) or recoverable error. 2 = configuration / cannot run.
11. **`--version` flag.** Import `__version__` from `lib/tools/__toolbox_version__.py` (#25 Part 1).
12. **Audit indicators.** If your tool detects a new failure mode, add it to the Audit Indicators table above and update the corresponding lesson's provenance.

---

## Out of Scope

- **Canvas-documented behavior** — lives in [`canvas_api_knowledge.md`](canvas_api_knowledge.md).
- **Instructional-design theory** — lives in the other knowledge files (`outcomes_quality`, `rubrics`, `assessments`, etc.).
- **Speculative footguns.** This file is empirical only. Suspected-but-unverified Canvas behaviors don't get a lesson here until reproduced.

---

## Pairs With

- [`canvas_api_knowledge.md`](canvas_api_knowledge.md) — always read both. This file is meaningless without its companion's documented baseline.
- [`rubrics_knowledge.md`](rubrics_knowledge.md) — L9 + the rubric-specific lessons in `canvas_rubrics_api_survey.md` feed the audit tags this file emits.
- [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) — the alignment chain that walks the API surface uses both documented patterns (parent file) and the workaround patterns documented here.

---

## References

Full provenance per fact in the JSON companion's `facts[].citations` — each lesson cites its discovery issue, the production incident (if any), and the defending tool.

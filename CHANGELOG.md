# Changelog

All notable changes to canvas-toolbox. Format follows [Keep a
Changelog](https://keepachangelog.com/). Versioning follows [SemVer](https://semver.org/)
on the `v0.x` line (canonical — see [AGENTS.md → Active Context](AGENTS.md#active-context)
for the versioning rationale).

For migration help between versions, see [UPDATE.md](UPDATE.md).

---

## [Unreleased]

(Nothing yet.)

---

## [0.50.1] — 2026-06-15

Doc sweep: agent-facing surfaces now know about `cb_report_bug.py`.

### Changed
- `AGENTS.md` gains a "Continuous improvement — bugs + enhancements"
  section codifying the DO / DO-NOT calibration for when to surface
  the bug-intake CLI. Refreshes Active Context for the v0.36 → v0.50
  grader sprint + bug-intake worker deployment.
- `README.md` adds a "Hit a bug? Hit a wish?" section with title-prefix
  examples (`bug:` / `enhancement:`) + the always-works
  github.com/issues/new fallback.
- `grading_readme.md` adds a grader-scoped reporter section with the
  "FERPA gate is not a bug" caveat.
- `lib/agents/canvas_grader.md` gains principle **P-011 Surface the
  bug-report path** + a tooling-table row for `cb_report_bug.py`.
- 8 other agent specs (canvas-sync / canvas_blueprint_sync /
  canvas_content_sync / canvas_course_expert / canvas_new_course_setup
  / canvas_schedule_auditor / canvas_semester_setup /
  ira_program_alignment) gain a uniform "Continuous improvement"
  cross-reference to AGENTS.md.
- `cb_report_bug.py` docstring documents the title-prefix convention.

## [0.50.0] — 2026-06-15

The v1.0 readiness gate: a zero-friction bug + enhancement reporting
path for faculty without GitHub accounts.

### Added
- `lib/tools/cb_report_bug.py` — one-command CLI that bundles toolkit
  context, scrubs PII locally (emails, /Users paths, roster names),
  and POSTs to the canvas-toolbox bug-intake Cloudflare Worker. No
  GitHub account, `gh`, browser auth, or PAT on the faculty side.
- `infra/bug-intake-worker/` — Cloudflare Worker source + deploy
  README. Receives `POST /bug`, validates (UA prefix, body cap, PII
  scrub, per-IP rate limit via KV), files via GitHub Issues API using
  the maintainer's narrow-scope PAT (Issues:RW only, 90-day rotation).
- `.github/workflows/agent-submitted-label.yml` — auto-applies the
  `agent-submitted` label by body-footer detection. (Workaround for
  GitHub fine-grained PATs silently dropping the `labels` field on
  issue create when scoped to Issues:write only — documented inline.)
- `infra/bug-intake-worker/MAINTENANCE.local.md` — gitignored
  maintainer runbook with PAT rotation schedule, troubleshooting
  notes (Safari OAuth quirk, workers.dev onboarding URL move), and
  take-offline procedure.

## [0.49.1] — 2026-06-14

### Fixed
- **#74** `grader_push` UnboundLocalError on `csv` — L669 loop variable
  shadowed the `import csv` module, crashing the default `--review`
  path. Renamed to `rc`.

## [0.49.0] — 2026-06-14

### Added
- **#71** `grader_meta_summary --cohort-glob` accepts multiple values
  via `action="append"`.
- **#72** `grader_push` HOLD_<DIMENSION> grade-hold pattern (lifted
  from itm327's `build_mid_letter_comments` + `push_mid_letter`).
  Posts the qualitative comment, withholds the grade write until the
  operator clears the heading token + re-pushes.

### Fixed
- **#73** `_uid_from_filename` in grader_meta_summary + grader_join
  now accepts grader_fetch / `_external` / Canvas-bulk-download
  conventions; whitespace-tolerant; WARNs when a keymap has rows but
  zero resolve.

## [0.48.2] — 2026-06-14

### Fixed
- **#70** `grader_meta_summary` task-level CSV row-binding now accepts
  `user_id`-keyed CSVs (m119 layout) via a `_row_uid` helper that tries
  `key` first then falls back to `user_id`.

## [0.48.1] — 2026-06-14

### Fixed
- **#67** `fetch_active_filter` follows `Link: rel="next"` instead of
  blindly incrementing page numbers (Canvas's /enrollments 400s past
  the last page; cohorts ≤100 hit this every call).
- **#66** `detect_adapter` relaxed from "100% markers" to majority
  rule (more than half) for routing `.html` cohorts to the Databricks
  adapter. Plus the cosmetic: roster-count message reports total
  roster size, not just newly-added.
- **#68** `grader_join` regex accepts `<prefix>_<uid>_external.<ext>`;
  conflict resolution prefers original keys over `_external` ones.
- **#69** `grader_meta_summary` Path B: task-level feedback CSVs are
  read first when surface-level is absent (m119's multi-surface
  layout).

## [0.48.0] — 2026-06-14

### Added
- **#54-B** `grader_join.py` — FERPA-safe `_userid_key_grade_join.json`
  builder for multi-surface tasks.
- **#54-C** `grader_meta_summary.py` — cross-task uid × task matrix
  + flag-streak detection + per-uid band distribution.

### Changed
- **#54-E** Single-surface vs multi-surface convention codified in
  grading_readme.md.

## [0.47.0] — 2026-06-14

### Added
- **#54-A** `grader_scaffold.py` — canonical
  `grading/<task>[_combined]/<surface>/` layout scaffolder.
- **#54-F** `scaffold/grading/rubric_templates/` — AI Log + Cohesive
  Narrative canonical templates that `grader_scaffold` auto-copies.

## [0.46.1] — 2026-06-14

### Fixed
- **#54-D** Re-run prefix duality in all 6 deid adapters — refuse to
  write a second prefix family into the same `submissions_deid/`;
  `--cleanup-legacy` opt-in to remove stale legacy files.

## [0.46.0] — 2026-06-14

### Added
- **#57** `grader_push_comments.py` — pushes staged
  `## Suggested Canvas Comment` H2 blocks from per-student feedback
  files to Canvas; reuses #61/#62/#63 guards; idempotent.

## [0.45.0] — 2026-06-14

### Added
- **#60** `grader_competency_grade.py` — config-driven "highest tier
  where all element thresholds are met" deterministic grade.
  Lifted from DS250's `calc_mid_grades.py`.

## [0.44.0] — 2026-06-14

### Added
- **#59** `grader_reconcile` per-dimension `completion_basis`
  (`submitted` / `nonzero` / `full_credit`) emits a `<dim>_complete`
  column the competency grader consumes.

## [0.43.0] — 2026-06-14

### Added
- **#64** `grader_submission_health.py` — read-only per-submission
  health check; flags broken-not-absent submissions
  (empty/near-zero uploads, wrong content-type, empty body,
  submitted-but-nothing).

## [0.42.0] — 2026-06-14

### Added
- **#63** `grader_push` availability awareness (warn on resubmit-style
  comment when assignment is locked) + first-class `--retract` for
  previously-pushed comments via per-assignment ledger.

## [0.41.0] — 2026-06-14

### Added
- **#62** `grader_push` pre-push comment-collision guard — warns on
  recent non-self comments via the FERPA-safe deid layer (#65) before
  posting.

## [0.40.0] — 2026-06-14

### Changed
- **#61** `grader_push` push surface excludes Canvas's Test Student
  + inactive/withdrawn/completed/rejected enrollments by default.
  `--include-inactive` reverts for the rare intentional case.

## [0.39.0] — 2026-06-14

### Added
- **#56** `grader_pull_ta_grades.py` — symmetric PULL counterpart to
  `grader_grade.py` for calibration cohorts. FERPA-safe (user_id +
  grade + score only).

## [0.38.0] — 2026-06-14

### Added
- **#55** `grader_list_assignments.py` — read-only Canvas assignment
  discovery; eliminates the inline `canvasapi` snippet operators were
  authoring repeatedly.

## [0.37.0] — 2026-06-14

### Added
- **#65** `grader_deidentify_comments.py` — FERPA de-id layer for
  Canvas submission_comments threads. Drops `author_name`, converts
  `author_id` to role (self/instructor/ta/peer/unknown), scrubs the
  body, refuses to write on any post-scrub roster-name leak.
  Prerequisite for #62 + #63.

## [0.36.0] — 2026-06-14

### Added
- **#58** `grader_config_audit.py` — read-only audit of every
  `assignment_id` in a reconcile/competency config against the live
  course. Catches the silent-misconfig "DS=0 with full DS credit"
  failure mode before any grading run.

---

## [0.35.4] and earlier

See `git log` for the v0.35.x series — `grader_follow_share_url.py`,
`grader_fetch.py`, FERPA Step 0, and the canonical grading folder
layout. The v0.36 — v0.50 series above is the day-1 sprint that
took the grader pipeline from "in-flight" to "1.0 ready."

# Canvas Toolbox

A Canvas LMS course management toolkit — mirrors live Canvas courses to local files, audits structure against an 8-framework instructional-design stack, and applies instructor-approved changes via the Canvas REST API.

## Project Purpose

**This is**:
- A toolkit for managing Canvas courses as code (mirror, edit, audit, push)
- An 8-framework instructional-design audit engine (Cognitive Load, Hattie 3-Phase, Three Domains, BYUI Taxonomy Explorer, Experiential Learning, Designer Thinking, Course Design Language, Toyota A3)
- A multi-course orchestration system (master + blueprint + per-section live courses)
- Tool-agnostic — works with any LLM coding tool that reads AGENTS.md
- Originally built for BYU-Idaho; designed to be institution-agnostic

**This is NOT**:
- A Canvas replacement or LMS
- A student-facing tool
- A version-control system for Canvas content (no commit history, no branching, no conflict detection)
- A NewQuiz or ExternalTool editor (Canvas REST API limitation)

**Audience**: Instructors and instructional designers who edit Canvas courses, want auditable structure, and use LLM coding tools for course design work.

## Structure

```
canvas_toolbox/
├── lib/                   ← pull-safe toolkit code — always updated by git pull, never edit in place
│   ├── agents/            ← agent specs, knowledge references, templates
│   │   ├── canvas_*.md/.json
│   │   ├── knowledge/     ← instructional-design references (see knowledge/README.md)
│   │   ├── templates/     ← reusable HTML/JSON artifacts (see templates/README.md)
│   │   └── AGENT_LAYERS.md ← runtime / capability / specification taxonomy
│   ├── tools/             ← Python CLI scripts (uv run python canvas_toolbox/lib/tools/<script>)
│   │   ├── canvas_sync.py
│   │   ├── sync_context.sh ← multi-course wrapper
│   │   ├── blueprint_sync.py
│   │   ├── course_mirror.py
│   │   ├── course_quality_check.py
│   │   ├── canvas_quiz_questions.py
│   │   └── canvas_api_tool.py
│   └── tests/             ← regression tests (pytest)
├── scaffold/              ← copy-once starters for your course repo (copy to your repo root, then own them)
│   ├── gitignore          ← rename to .gitignore in your course repo
│   └── .env.example       ← copy to .env and fill in credentials + course IDs
├── examples/              ← reference material (read-only — never auto-synced)
│   └── setup_notes/       ← example instructor setup notes
├── course_src/            ← markdown authoring workspace (gitignored, --build compiles to course/)
├── make-ai-agents/        ← local clone of upstream tool (gitignored, separate dev tool)
├── gh-issues-agent/       ← local clone of upstream tool (gitignored, separate dev tool)
├── handoff/               ← local clone of upstream tool (gitignored, separate dev tool)
├── master/                ← master course working dir (gitignored, multi-course mode)
├── s1/, s2/, s3/          ← per-section working dirs (gitignored)
├── course/                ← legacy single-course mirror (gitignored)
├── .canvas/               ← runtime indexes and logs (gitignored)
├── AGENTS.md              ← this file
└── README.md              ← user-facing documentation and command reference
```

**Consumer usage**: clone `canvas_toolbox` as a subdirectory of your course repo (`git clone https://github.com/chaz-clark/canvas_toolbox.git canvas_toolbox`). Copy `scaffold/` starters to your repo root once. Run tools as `uv run python canvas_toolbox/lib/tools/<script>`. Update safely at any time: `cd canvas_toolbox && git pull origin main` — only `lib/`, `scaffold/`, and `examples/` change; your course files are untouched.

For full setup and command reference, see [`README.md`](README.md). For agent-engineering taxonomy (Runtime / Capability / Specification / Tool layers), see [`lib/agents/AGENT_LAYERS.md`](lib/agents/AGENT_LAYERS.md).

## Working Style

This project follows the behavioral discipline defined in `make-ai-agents/knowledge/behavioral_discipline.md` (when the upstream `Make-AI-Agents` clone is populated locally — see Existing Tooling) or the equivalent discipline loaded via the host tool's skill system.

In short, every contributor — human or LLM — operates under these principles: read before claiming, plan before acting on changes, stop on the first defect rather than papering over, find root causes for bugs, document non-trivial changes in a structured form, generate exactly what was asked (no speculative additions), produce mistake-proof outputs, reflect and tell the user about non-obvious learnings, and respect the user's intent without substitution or drift.

For the full principles and override rules, see `knowledge/behavioral_discipline.md` → "The Ten Principles". The four no-override principles (P-001 Read Before Claiming, P-003 Stop on Defect, P-007 Pull Don't Push, P-010 Respect Intent) apply unconditionally.

**Project-specific rules**:
- **Local files are source of truth.** Canvas is the sync target, not the source. Never treat Canvas as authoritative unless `--pull` was just run.
- **Canvas IDs are course-specific.** Match content across courses by title, never by ID. The same assignment has different IDs in master, blueprint, and every section.
- **Adding content requires two steps: course + module.** Creating an assignment, quiz, or page is not enough — it must also be added as a module item, or students cannot find it.
- **Confirm scope before any write.** Master, blueprint, and sections are different courses with different IDs. A push scoped wrong replicates to the wrong course.
- **`request_confirmation()` must return `approved=true` before any Canvas write.** Audit agents enforce this; honor it manually too.
- **Run `course_quality_check.py` after every push** — surfaces orphaned items, duplicates, and dates outside the course window.
- **Completion requirements enable the prerequisite chain.** Sequential sprint locks silently fail if any item lacks `must_submit` (assignments, quizzes), `must_contribute` (discussions), or `must_view` (pages, tools, URLs). This is the `chain-complete` policy `module_settings_sync.py` applies by default.

## Active Context

_Last updated: 2026-05-20_

**Versioning:** the `v0.x` semver line is canonical (matches `git describe` and `lib/tools/__toolbox_version__.py`). A separate `v1.x` git tag series exists in history; it is not part of the `v0.x` line and is not maintained — treat `v0.x` as canonical going forward. Downstream repos that vendor `lib/tools/` check drift with any primary sync tool's `--version` flag and re-sync via `cd canvas_toolbox && git pull` (never patch vendored copies in place).

- **v0.20.0 just shipped** — **#29 Phase 1** new `lib/tools/blueprint_orphan_pages.py` (read-only): post-sync Page-level integrity audit catching two Canvas behaviors the migration log silently masks. Detector A: 5-point fingerprint for Canvas's `-N` slug orphan pattern (sync re-pushes a locked page into a section that previously deleted its copy → Canvas creates `slug-2`/`-N` with canonical content but doesn't update the unsuffixed slug the module item still points at; students see stale, canonical material exists but is unreachable). Detector B: silent body reversion — section page body has no provenance in blueprint's revision history (the strongest signal; plain drift stays with `validate_blueprint_sync.py`). Detector B's behavior, reproduced deterministically 2026-05-20 on the lock-state-only sync path, **contradicts Canvas's published docs** ("Changed content will always overwrite the existing content in the associated courses for all locked objects") — operator warning printed when it fires, advising against lock-state-only Blueprint UI syncs until Canvas's behavior is understood. Two new External System Lessons added. **Phase 2** (`--apply` cleanup via unlock/write/re-lock cycle) is **deferred** — risk of leaving items half-unlocked on mid-sequence failure; needs Phase 1 detection exercised against real courses first. With this, the ITM-327 chain post-sync hygiene is fully covered: `validate_blueprint_sync` (drift), `blueprint_exception_report` (skipped items + reasons), `blueprint_orphan_pages` (orphans + reversions). Verification limit (honest): no live course in this repo — static + argparse only.
- **v0.19.0** — **#27** startup safety guard (closes the last open issue in the ITM-327 trigger → amplification → observability chain alongside #26 and #28). New shared module `lib/tools/canvas_course_guard.py` (pure functions, sibling to `canvas_pages.py` / `__toolbox_version__.py`): GETs `?include[]=total_students` + `/blueprint_subscriptions` per target course; hard-stops writes (`sys.exit(2)`) when the target is enrolled (`total_students > 0`) or a Blueprint child (non-empty subscriptions), unless `--allow-enrolled` is passed; advisory only on read modes; guard's own API errors never block (degraded-mode warn). Wired into 4 tools: `canvas_sync` (write on `--push`/`--upload`, advisory on `--pull`/`--status`/`--init`/`--pull-files`; `--build` skipped — local-only), `course_mirror` (source + target on `--push`), `blueprint_sync` (source + target on `--push`), `course_quality_check` (advisory-only — read-only audit). New External System Lesson added. `module_settings_sync` deliberately not wired (per P-007 + scope decision; can follow). Verification limit (honest, this session's discipline): no live course in this repo — static + argparse only.
- **v0.18.0** — **#28** new `lib/tools/blueprint_exception_report.py` (read-only): post-Blueprint-sync exception report per associated section — reads the subscriber-side migration-details endpoint Canvas exposes, groups by `conflicting_changes` type, emits PASS / WARN / FAIL with remediation guidance (FAIL on `content`/`deleted` → lock + resync; WARN on `points`/`state`/`settings`; PASS on `due_dates`/`availability_dates`). `--suggest-locks` emits a ready-to-run lock+resync script; `--report` writes markdown; `--migration-id <id>` inspects a historical migration. Resolves the Canvas footgun where `workflow_state: completed` is reported even when sections silently skipped majority of items via exceptions (real ITM-327 S2 incident: 51/80 items skipped with `completed` state). Pairs with `validate_blueprint_sync.py` — that tool sees STATE-DIFF (*what is*); this tool sees SYNC-LOG (*what happened, why, fix*). New External System Lesson added for the underlying Canvas behavior. Verification limit: end-to-end requires a live Blueprint sync; static + argparse only here.
- **v0.17.0** — **#25 fully closed** (mapping: Part 1 vendored-tool drift → version stamp + `--version` + documented re-sync, delivered v0.16.0; Part 2 `module_settings_sync` de-hardcoding → policy layer `076d466` + surface args `82c4278`: `--target` / `--module-prefix` / `--rename-match`, rename-discovery now opt-in, `"performance review"` literal removed, ITM-327 reproduced via explicit flags; Part 3 Canvas clear-quirk → documented via #26). Also: new procedural knowledge `evidence_centered_design_knowledge` (`v0.1`/untested — its own knowledge-file version scale; promoted to `1.0` only after a real-course test; not yet catalogued or wired into agent `cross_references[]` per the `0.x` convention); `module_structure_diff.py` documented as a general read-only diagnostic + docstring de-misleadinged; keystone-uv project half (`.python-version` = `3.14`). Upstream this cycle: Make-AI-Agents #13/#14/#15 (make_AGENTS workflow block; make_agent_knowledge section-order contradiction + optional-section list).
- **v0.16.0** — versioning coherence + vendored-tool drift visibility: added `lib/tools/__toolbox_version__.py` as the single source of truth and a `--version` flag on the four primary sync tools (`canvas_sync`, `blueprint_sync`, `course_mirror`, `module_settings_sync`). Reconciled the version landscape (stale "v0.14.0 just shipped" marker, a divergent `v1.x` tag series, no constant). Folded in the then-unreleased **#26** idempotent Page upsert (`canvas_pages.py` shared module) and **#25 Part 2 policy layer** (`module_settings_sync --policy`).
- **v0.14.0** — agent retrofit series R3–R6: all 6 consuming agents migrated from template v3.1 → v3.6 behavioral-discipline contract. Each agent now declares `interaction_pattern`, a full `behavioral_discipline` object (applicable principles + no-override + override decisions + BD-QC checks), and `cross_references.knowledge_files[]` per the v3.6 contract. Patterns surfaced: `single_write_workflow` (canvas_course_expert, canvas_content_sync); `multi_step_batch` (canvas_schedule_auditor, canvas_semester_setup, canvas_blueprint_sync); `conversational` (ira_program_alignment, with documented P-005 `out_of_scope` override — the 5-phase workflow IS the small-steps decomposition). First non-LLM agent retrofit (canvas_blueprint_sync) introduced the `applies_to: "operator"` + `_qc_checks_na` pattern for deterministic scripts — captured upstream as [Make-AI-Agents#11](https://github.com/chaz-clark/Make-AI-Agents/issues/11). First conversational `.json` companion generated from scratch (ira_program_alignment had no prior JSON). Per-retrofit commits: R3 `7d5ade6`, R4.1 `a4923b1`, R4.2 `8f8123b`, R4.3 `6818e10`, R5 `f8916bb`, R6 `58de57e`.
- **v0.13.0** — knowledge-framework expansion: 2 new pairs (`assessments_knowledge`, `backwards_design_knowledge` — Yale Poorvu + Hardman + Wiggins/McTighe UbD) and 10 JSON companion retrofits for all pre-existing framework MDs (CLT, Hattie, Three Domains, Taxonomy Explorer, Experiential, Designer Thinking, Course Design Language, Toyota Gap, Outcomes Quality, Inverted Bloom's). All JSONs declare `read_at_runtime` per selective-load access pattern. Knowledge catalog ([lib/agents/knowledge/README.md](lib/agents/knowledge/README.md)) updated. Source: Genchi Genbutsu pass from Make-AI-Agents (handoff 2026-05-13).
- **v0.12.0** — `validate_blueprint_sync.py` (post-Blueprint-sync validation: section drift, Blueprint field drift, duplicate detection, locked-item prerequisite check; live API, read-only, exits non-zero on findings; #24). Also: `course_quality_check.py` Blueprint-aware duplicate detection — Blueprint-locked copy is canonical, routes to `manual_review` instead of auto-deleting (#23). Canvas sync field gaps closed: quiz dates via linked assignment endpoint, discussion `todo_date`, assignment `name` on push, `allowed_extensions`, `omit_from_final_grade`, quiz metadata fields (#21, #22).
- **v0.9.0** — `course_quality_check.py --validate-dates` (out-of-window, ordering sanity, duplicate due dates per group, label-vs-week/sprint drift; read-only, exits non-zero on findings; #20). Also: repo restructured into `lib/` / `scaffold/` / `examples/` for pull-safe boundaries (#19).
- **v0.6.0 / 0.7.0 / 0.8.0** — three independent opt-in audit/sync features:
  - `canvas_sync.py --pull-files` / `--find-file` / `--pull-file` (file-aware pulling, fuzzy search, pre-download confirmation thresholds; #16)
  - `course_quality_check.py --files` (orphan + broken-reference + duplicate audit, read-only; #17)
  - `course_quality_check.py --alignment` (Course Outcome → Module Outcome → Rubric Criterion chain audit, read-only; #18)
- **Open canvas_toolbox issues**: none. Issue tracker is empty — ready for empirical validation against real courses.
- **v0.5.0** — Course Design Language as the 8th knowledge framework, with the `byui_course_design/` template-set (11 HTML components + canonical rubric JSON)
- **v0.4.0 multi-course orchestration** in production — `lib/tools/sync_context.sh` invokes `canvas_sync.py` per context (master/blueprint/s1/s2/...). Validated against a real multi-section course setup.
- **Make-AI-Agents clone** at `make-ai-agents/` is gitignored. Populate locally with the `git clone` command in Existing Tooling when needed.
- **Roadmap (canvas_toolbox)**: convert `canvas_course_expert` to deployable `.agents/skills/canvas-audit/` (first deployable skill, parameterize for non-BYUI institutions); capture conversion as `lib/agents/deploy_agent.md`; convert `canvas_schedule_auditor` to validate the template; cite `toyota-way-agents` skill from AGENTS.md once it lands upstream and gets cloned in.
- **Upstream-tracked work** lives in [`Make-AI-Agents`](https://github.com/chaz-clark/Make-AI-Agents) (separate repo, separate issue tracker). Toyota Way × AI agents skill design + clone consumer hygiene live there.

Vision: another university clones this repo, opens it in any modern AI coding tool, and the canvas-audit capability is auto-discovered by their LLM — zero install friction beyond clone-and-open.

## Domain Terms

| Term | Definition |
|---|---|
| **Master** | The template course where authoring happens. One per course. Identified by `MASTER_COURSE_ID` in `.env`. Folder: `master/` (or `course/` in legacy single-course mode). |
| **Blueprint** | A Canvas Blueprint course that semester sections clone from. Optional — only used by online programs. Identified by `BLUEPRINT_COURSE_ID`. Folder: `blueprint/`. |
| **Section** | A live student-facing course for a specific semester (S1, S2, S3...). Cloned from blueprint or master. Identified by `S1_COURSE_ID`, `S2_COURSE_ID`, etc. Folders: `s1/`, `s2/`, `s3/`. |
| **Sprint module** | A weekly or bi-weekly module containing related content. Sequential by default; can have prerequisites that lock later sprints until prior items are completed. |
| **Module item** | An entry inside a module — Page, Assignment, Quiz, Discussion, ExternalTool, ExternalUrl, or SubHeader. Has its own `module_item_id` distinct from the underlying content's `canvas_id`. |
| **NewQuiz** | Canvas's newer quiz engine (LTI-based). Cannot be content-pushed via REST API — must be edited in Canvas UI. Distinct from Classic Quiz. |
| **Classic Quiz** | Canvas's original quiz engine. Has both a `quiz_id` (in `/quizzes`) and an underlying `assignment_id` (in `/assignments` with `submission_types: ["online_quiz"]`). REST API works fully. |
| **Source of truth** | The local working folder (`master/course/` in multi-course mode, `course/` in single-course). Canvas is the sync *target*. |

## External System Lessons

Canvas API has multiple non-obvious behaviors discovered through use. Each is a real footgun:

| Behavior | Why it matters | How to handle |
|---|---|---|
| Module prerequisites silently fail with JSON payload | Returns 200 OK but doesn't actually set the prerequisite | Always use form-encoded: `data={"module[prerequisite_module_ids][]": id}` |
| Module published state is form-encoded too | Same pattern as prerequisites | `data={"module[workflow_state]": "active"\|"unpublished"}` |
| Semester due-date updates fail without `lock_at: null` and `unlock_at: null` | Reading quizzes retain prior-semester availability windows; sending `due_at` alone causes 400 errors | Always send all three together when rolling forward dates |
| `late_policy` PATCH returns 403 for instructor tokens | Cannot set programmatically with most tokens | Set manually in Canvas Settings → Gradebook, or use admin token |
| Classic quiz `points_possible` may show 0 after question push | Canvas auto-calculates from questions but doesn't update the quiz object | Explicit `PUT /quizzes/:id {"quiz": {"points_possible": N}}` after question push |
| Classic quizzes have two IDs | Module items reference `quiz_id`; due dates use `assignment_id` | Quality check maps both to avoid false "not in module" positives |
| Discussions use `todo_date`, not `due_at` | Different field on `PUT /discussion_topics/:id` | Don't conflate with assignment / quiz date semantics |
| NewQuiz / ExternalTool items can't be content-pushed via REST | Module shell syncs but item body is empty in target | Sync scripts skip and warn; manage these in Canvas UI |
| `GET /courses/:id/rubrics` requires teacher token | Returns 403 with student token | Workaround: `GET /courses/:id/assignments/:id?include[]=rubric` works for student tokens too |
| Empty modules are a sync artifact | When all items in a module are NewQuiz / ExternalTool, the module shell syncs but lands empty | Sync scripts warn before; quality check flags after |
| Blueprint migration reports `workflow_state: completed` even when items silently skipped | Per-section `exceptions[].conflicting_changes` records the skip (`content`, `deleted`, `due_dates`, …); the migration-level state does not. Trusting `completed` produces a false "sync worked" signal | Read the subscriber-side migration-details endpoint per associated course. `blueprint_exception_report.py` does this and emits PASS / WARN / FAIL with remediation per type (`content`/`deleted` → lock + resync via the blueprint). State-diff (`validate_blueprint_sync.py`) sees *that* items diverged; this sees *why* (#28) |
| A stale `.env` can silently point a write-capable tool at the wrong kind of course | `CANVAS_COURSE_ID`/`MASTER_COURSE_ID`/`BLUEPRINT_COURSE_ID` are just env vars — a hand-edited or stale `.env` can point a write target at an enrolled student section, or at a Blueprint **child** course. Combined with non-idempotent writes, this amplifies (ITM-327: 4× page duplication across master/blueprint/2 sections) | Startup safety guard (`lib/tools/canvas_course_guard.py`, #27) runs in `canvas_sync`/`course_mirror`/`blueprint_sync`/`course_quality_check`: GETs `?include[]=total_students` + `/blueprint_subscriptions`; hard-stops writes (`sys.exit(2)`) when the target is enrolled or a Blueprint child unless `--allow-enrolled` is passed; advisory only on reads. Guard error itself never blocks the tool |
| Canvas's UI sync creates `-N` slug orphan Pages | When a Blueprint sync re-pushes a locked Page into a section that previously deleted its copy, Canvas creates a new page at `slug-2` (or `-N`) carrying canonical content — but does NOT update the unsuffixed slug the module item still points at. Result: silent split between *content* and *navigation*; students see stale | `blueprint_orphan_pages.py` (#29 Phase 1) Detector A — 5-point fingerprint per section, READ-ONLY detection. Cleanup is unlock → PUT canonical body onto unsuffixed slug → DELETE `-N` orphan → re-lock; section-side deletes are blocked while master is locked (403). `--apply` automation deferred to Phase 2 |
| Canvas's lock-state-only sync can silently revert section page bodies to a hash that doesn't exist in the blueprint's revision history | Observed 2026-05-20 deterministically: a locked Page in a section was overwritten with a body hash that **never** existed in blueprint's revisions (cross-section contamination via the master-link, per the W01 evidence). Migration reports `state: completed` with zero exceptions — directly contradicts Canvas's published behavior ("Changed content will always overwrite the existing content in the associated courses for all locked objects") | `blueprint_orphan_pages.py` (#29 Phase 1) Detector B — flags section pages whose body has no provenance in blueprint's `revisions` history (the strongest signal). **Operator warning printed when Detector B fires:** do NOT run a Blueprint UI sync that only carries lock-state metadata changes (no body diffs) — the lock-state-only path is the one observed to cause the reversion |
| Canvas auto-suffixes a Page URL on title collision | `POST /courses/:id/pages` with a title that already exists silently creates a second page at `…-2`/`-4`/`-5`; repeated non-idempotent pushes duplicate the same page across master/blueprint/sections | Never POST a Page without a title-existence check. Use `lib/tools/canvas_pages.upsert_page()` (GET-by-title → reuse+PUT / create / >1→manual review) and `page_in_module()` to guard the module-item link (#26) |
| Clearing a module-item completion requirement needs the whole object blanked | `data={"module_item[completion_requirement][type]": ""}` returns `400 Invalid completion requirement type` | Form-encode the whole object blank: `data={"module_item[completion_requirement]": ""}`. Setting still uses `data={"module_item[completion_requirement][type]": "must_submit"}` (#25) |

## Existing Tooling

Before generating new sync or audit code, check whether these already do what's needed:

| Tool | Purpose | When to use |
|---|---|---|
| `lib/tools/canvas_sync.py` | Single-course mirror (pull, status, push, build, upload). Plus opt-in: `--pull-files` / `--find-file <q>` / `--pull-file <q>` for working with referenced Canvas Files. Startup safety guard (#27) refuses writes when `CANVAS_COURSE_ID` looks enrolled or Blueprint-associated; bypass with `--allow-enrolled`. | All single-course sync work |
| `lib/tools/sync_context.sh <context>` | Multi-course wrapper — invokes `canvas_sync.py` for master / blueprint / s1 / s2 / ... | Anytime more than one course is in this repo |
| `lib/tools/blueprint_sync.py` | Master → Blueprint sync (one-way overwrite: course settings, homepage, syllabus, and Page/Assignment/Discussion/Quiz content + published state + dates). Page creation is idempotent (title-upsert, #26). Does **not** sync module structure, item order, or module completion requirements. Startup safety guard (#27) covers both source (`MASTER_COURSE_ID`) and target (`BLUEPRINT_COURSE_ID`); bypass with `--allow-enrolled`. | Online programs using Canvas Blueprint |
| `lib/tools/course_mirror.py` | Source → Master one-off mirror. Startup safety guard (#27) covers both source (`CANVAS_COURSE_ID`) and target (`MASTER_COURSE_ID`); bypass with `--allow-enrolled`. | Manually replicating between two courses |
| `lib/tools/course_quality_check.py` | Four opt-in audit modes (mode-switching, not combined): structural (default — duplicates, floating items, empty modules, date window), `--files` (orphans + broken refs + duplicates), `--alignment` (Course Outcome → Module Outcome → Rubric Criterion chain breaks), `--validate-dates` (out-of-window, ordering sanity, duplicate due dates per group, label-vs-week/sprint drift). Startup safety guard (#27) runs **advisory-only** here (read-only audit; warns but never blocks). | After every push to any course; `--files`, `--alignment`, and `--validate-dates` on demand |
| `lib/tools/validate_blueprint_sync.py` | Post-Blueprint-sync validation: section drift, Blueprint field drift (lock_at, allowed_extensions, submission_types), duplicate detection, locked-item prerequisite check. Live API queries, read-only. `--report` writes markdown. STATE-DIFF only — pairs with `blueprint_exception_report.py` for the sync-log side. | After every Canvas Blueprint sync |
| `lib/tools/blueprint_exception_report.py` | Per-section Blueprint-migration **exception** report (#28). Reads the subscriber-side migration-details endpoint; groups exceptions by type; PASS / WARN / FAIL verdict (FAIL on `content`/`deleted`; WARN on `points`/`state`/`settings`; PASS on `due_dates`/`availability_dates`). `--suggest-locks` emits a lock+resync script; `--report` writes markdown; `--migration-id <id>` overrides most-recent. Read-only. | After every Canvas Blueprint sync — run alongside `validate_blueprint_sync.py` to see *why* items skipped, not just *that* they diverged |
| `lib/tools/blueprint_orphan_pages.py` | Post-sync Page-level integrity audit (#29 Phase 1, **read-only**). Detector A: 5-point fingerprint for Canvas's `-N` slug orphan pattern. Detector B: silent body reversion — section page body has no provenance in blueprint's revision history (the strongest signal; plain drift is left to `validate_blueprint_sync.py`). Prints an **operator warning** when Detector B fires: don't run a lock-state-only Blueprint UI sync. `--report` writes markdown. Cleanup (`--apply`) is deferred to Phase 2. | After every Canvas Blueprint UI sync — pairs with `validate_blueprint_sync.py` (state-diff) and `blueprint_exception_report.py` (sync-log) |
| `lib/tools/canvas_quiz_questions.py` | Classic quiz question manager (push, list, clear) | Editing quiz questions outside Canvas UI |
| `lib/tools/module_settings_sync.py` | Module-settings reconciliation (prereq chain, "complete all" mode, per-item completion requirements). `--plan` default / `--apply` confirmation-gated + self-verifying. Course-agnostic: `--target` (default `MASTER_COURSE_ID`), `--module-prefix` (default `sprint-`), `--rename-match` (self-assessment rename-discovery, OFF unless given). Two policies: `chain-complete` (default — per the Completion-requirements rule above) and `graded-work-only` (opt-in deviation, needs `BLUEPRINT_COURSE_ID`). Reproduce original ITM-327 behavior: `--policy graded-work-only --rename-match "performance review"`. | Reconciling module gating on any course (#25) |
| `lib/tools/module_structure_diff.py` | **Read-only** diff of module prerequisites + completion requirements between Blueprint and master (GET only, never writes). General-purpose: no course-ID or module-name hardcoding; title-slug matching (Rule 2); enforces no policy. | Inspecting blueprint↔master module-structure drift before any mirror/reconcile step |
| `lib/tools/canvas_api_tool.py` | Audit engine + Canvas write functions | Wrapped by audit agents; rarely invoked directly |
| `lib/agents/canvas_course_expert` | 8-framework instructional-design audit | Conceptual / pedagogical audit |
| `lib/agents/canvas_schedule_auditor` | Rule-based date audit (propose-before-execute) | Pre-semester or mid-semester date validation |
| `lib/agents/canvas_blueprint_sync` / `canvas_content_sync` | Agent guides for sync workflows | Reference, not invoked directly |
| `lib/agents/canvas_semester_setup` | Roll due dates forward for a new semester | Once per semester |
| `lib/agents/canvas_new_course_setup` | First-time setup walkthrough | Once per new course adoption |

For framework theory (CLT / Hattie / etc.), see [`lib/agents/knowledge/README.md`](lib/agents/knowledge/README.md). For the agent abstraction taxonomy, see [`lib/agents/AGENT_LAYERS.md`](lib/agents/AGENT_LAYERS.md).

**Populating the gitignored upstream tool clones** (each is a normal local git clone — independent of canvas_toolbox's git history):

```bash
# Make-AI-Agents (template generation skills: make_agent, make_AGENTS, make_gem)
git clone https://github.com/chaz-clark/Make-AI-Agents.git make-ai-agents

# gh-issues-agent (GitHub issue triage tool)
git clone https://github.com/chaz-clark/gh_issues_agent.git gh-issues-agent

# handoff (agent-to-agent handoff tool)
git clone https://github.com/chaz-clark/handoff.git
```

Each is a real git clone with its own `.git/` directory. Edits flow upstream (edit at the source repo's local clone, not here). Future updates: `cd <dir> && git pull origin main`.

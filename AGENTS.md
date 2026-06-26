---
name: canvas-toolbox-agents
description: AGENTS.md for the `canvas-toolbox` repo — a Canvas LMS course-management & audit toolkit. Working style, handoff recognition, learning loop, audit-tool catalog, and external-system lessons.
version: "0.1"
author: chaz-clark
license: MIT
metadata:
  repo: canvas-toolbox
  spec-source: Make-AI-Agents/make_AGENTS
---

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
├── Make-AI-Agents/        ← local clone of upstream tool (gitignored, separate dev tool)
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

This project follows the behavioral discipline defined in `Make-AI-Agents/knowledge/behavioral_discipline.md` (when the upstream `Make-AI-Agents` clone is populated locally — see Existing Tooling) or the equivalent discipline loaded via the host tool's skill system.

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
- **Keep institutional and course-specific facts out of committed files.** This toolkit is institution-agnostic by design. Course IDs, semester data, instructor names, institutional vocabulary that isn't already neutralized (e.g., "BYUI" outside the institution-specific `byui_course_design/` template-set), and any per-course working state belong in `.env`, in `pre_knowledge/` (gitignored), or in per-course downstream repos that subtree-pull this toolkit — never in `AGENTS.md`, `README.md`, or other committed top-level files.
- **Sandbox-first testing: validate new or changed tools against a sandbox course before handing them off.** Before a new/changed tool is committed for a downstream repo or person to test (e.g., a course repo that subtree-pulls this toolkit), exercise it first against a write-safe sandbox course (`CANVAS_SANDBOX_ID` in `.env`) on the real Canvas API — not just unit tests and `--help`/argparse smoke. If the change needs specific conditions to exercise (e.g., rubrics of various shapes for the rubric audit tools), **create those scenarios in the sandbox** — it's write-safe and built for exactly this. Real-API failures should be caught in-house, not by downstream testers. (Motivating case: 2026-05-21, the rubric audit tools were handed to a downstream course repo with no live-API run here first; they hit a blocking `CANVAS_BASE_URL` scheme bug on the first invocation — a defect a 30-second sandbox run would have caught.)
- **Surface-before-apply (P-002) applies to every state-changing action**, not just cross-repo handoffs. **GitHub-issue triage is in scope:** between *"I understand the issue"* and the first `Edit` / `Bash` commit / `gh issue close`, propose the fix and wait for explicit go. **A one-word reply on a *summary* is ambiguous** — *"continue"* / *"yes"* / *"ok"* can mean *"continue the conversation, what's the plan?"* or *"go execute."* Clarify, don't infer. **Explicit go triggers** (honored without re-surfacing): *"go,"* *"yes apply,"* *"flow approved,"* *"fix and ship,"* *"I trust the call here."* No smallness loophole — a one-line `replace_all` and a 200-line refactor both need surfacing. (Motivating case: 2026-06-01, issue #38 fix bypassed surfacing because the agent inferred go from a *"continue"* that was meant as continue-the-conversation. See [`lib/agents/knowledge/learned/2026-06-01_surface-before-apply-on-issue-triage.md`](lib/agents/knowledge/learned/2026-06-01_surface-before-apply-on-issue-triage.md) for the failure-mode write-up.)
- **`git push` after every commit** — in BOTH consumer repos AND canvas-toolbox itself. A commit that isn't pushed isn't a backup; it can be lost to disk failure, mistaken `reset --hard`, or just forgotten across a session boundary. **Local-only commits are a smell.** The goal is `git log --branches --not --remotes` showing zero commits at all times. Use `git add ... && git commit -m "..." && git push` as the single operation; if `git push` is omitted, the next session inherits unpushed work. **Two motivating cases**: (a) 2026-06-17, itm327-master had 23 local-only commits ahead of origin spanning ~3 weeks of canvas-toolbox-prompted work (issue #88); (b) 2026-06-18, canvas-toolbox itself had 6 local-only commits when an adopter cloned from GitHub and found `cb_init.py` missing — the v0.54.0 work was complete locally but invisible to the world. The rule applies to maintainers, not just adopters.
- **Placeholder names in code comments, commit messages, and prose docs must be visibly fake.** In any prose context (code comments, commit messages, AGENTS.md entries, learned-lessons docs, parking-lot entries), the first appearance of a placeholder name **gets the explicit "fake" annotation** — `"Sarah" (fake name)` — and subsequent appearances in the same artifact stay in quotes: `"Sarah"`. The annotation is an **active FERPA-discipline signal** so any reader (auditor, IRB, future contributor) immediately knows the name is not real. Inside test FIXTURES (literal grading-comment strings), names stay un-quoted because the tests assert against the literal shape; instead, the test file's top docstring documents the convention. Common first names ("Sarah", "Alex", "Maria") chosen for readability remain fine — the discipline is to make their placeholder-status VISIBLE, not to invent obscure tokens. **Motivating case**: 2026-06-22 (v0.57.1 → v0.57.2), the FERPA-fix commit for #94 used "Sarah" throughout as a placeholder (the reporter had been more careful, using `<Name>`). Operator caught the inconsistency: "we shipped a FERPA fix; did we ourselves follow FERPA discipline in the artifacts?" — answer: not visibly enough. The annotation pattern was adopted to over-communicate the discipline rather than rely on context for it.
- **Deterministic-first grader design — bias toward Python; reach for the LLM where contextual judgment or voice-anchored prose is the better fit. It's a tuning preference, not a hard rule.** Many rubric criteria (output matching, structural checks, function-signature presence, count thresholds, completion-basis ratios, file-presence) are cleanly deterministic — `regex` / `Levenshtein` / `AST parse` / a counter + a threshold. The LLM has clear strength on: contextual judgment on prose where a rule can't reach (was the reflection coherent? did they engage with the prompt?), and writing voice-anchored student-facing comments. **But there's a real messy middle** where the right call isn't obvious — "is the code well-organized?" / "did the analysis go deep enough?" / "is the voice appropriate?" — criteria that LOOK rule-friendly but resist clean regex, OR look LLM-only but have deterministic shadows (length checks, structural-flatness heuristics) that approximate the judgment cheaply. **The principle is a preference, not a mechanical filter:** prefer Python when the criterion is cleanly deterministic; prefer the LLM when contextual judgment is genuinely required; in the messy middle, **the rubric author / instructor decides** based on pedagogical intent, available time, and what fits THEIR rubric (sometimes a deterministic prefilter + LLM-on-what-passes is the right hybrid). **Migration is fine** — a criterion may start as LLM (cheap proof-of-concept) and harden to deterministic later when patterns emerge; or start deterministic and escalate to LLM when the rule misses cases. **The grader pipeline today already follows the preference for parts of the work** (`grader_signals.py` extracts signals deterministically; `grader_reconcile.py` counts via `completion_basis`; `grader_competency_grade.py` applies tier thresholds rule-based) — the discipline is to ASK the question at design time, not to assume the LLM is the default. **Why it matters**: deterministic checks are free (no token cost), reproducible, auditable, and FERPA-safe by default. The LLM's cost / drift / pedagogical-risk concentrate on the (smaller) judgment-required portion. **Motivating case**: 2026-06-22 design conversation on a potential v1.2 auto-grade-on-cycle feature — original framing assumed the LLM grades everything per submission; operator's reframe ("use deterministic where you can; LLM for context and comments") collapsed token cost + drift + safety concerns substantially, BUT the operator also flagged the messy middle so the principle is "tuned toward Python first" — not a hard binary. See `lib/agents/knowledge/grader_knowledge.md` §16 + the v1.2 parking-lot entry for the full nuance.

## Handoff document recognition

This repo participates in the cross-repo `handoff` convention (canonical spec: [`handoff/CONVENTION.md`](https://github.com/chaz-clark/handoff/blob/main/CONVENTION.md)). When operating in this repo, treat the following file patterns as **handoff documents** — structured artifacts with a lifecycle, NOT prose conversation:

| Path pattern | What it is |
|---|---|
| `handoffs/HANDOFF_<topic>.md` | Outgoing `request`-direction handoff (canonical copy; dropped into producer's root after authoring) |
| `handoffs/<YYYY-MM-DD>_<topic>.md` | Incoming `deliver`-direction handoff (canonical consumer record) |
| `<CONSUMER>_HANDOFF_<topic>.md` at repo root | Incoming `request`-direction handoff dropped by another consumer for us to apply |
| `<PRODUCER>_DELIVERS_<topic>.md` at repo root | Visibility copy of an incoming `deliver` handoff (canonical is in `handoffs/`) |
| `handoffs/parkinglot.md` | `internal` handoff — near-term parked ideas ("good idea, busy now"); deferred by design |
| `handoffs/long-term-parking.md` | `internal` handoff — far/someday parked ideas (evidence-gated, pie-in-the-sky); deferred by design |

### Seven rules for handling a handoff document

1. **Read the metadata header first.** Every handoff opens with bold-labeled fields: `Date`, `Author`, `Direction`, `Status`, `Origin`, `Origin-Commit`, `Topic`. Optional: `Sensitivity`, `Companions`. If any required field is missing, STOP and ask the human user.

2. **Act only on `Status: delivered`.** Skip `draft` (not ready), `applying` (someone else is on it), and `applied` / `archived` / `superseded` (done or moot). If `Sensitivity: restricted` or `internal-only`, escalate to the human before any cross-repo action.

3. **Surface before applying.** Summarize the handoff's request or delivery to the human user — what's being asked, what files/repos are affected, what the apply step would change. Get per-decision approval. The convention is per-proposal-approval, not bulk auto-apply.

4. **Update Status on apply.** After committing the change the handoff requests, edit the handoff doc: set `Status: applied`. Add a `## Lifecycle marker` entry with the apply date (and optionally the commit hash). The handoff doc is mutable in place — there's no side channel for state.

5. **STOP on missing referenced artifacts.** If the handoff names files, commits, agents, or paths that don't exist locally, halt and ask the human. Do not infer; do not fabricate. The handoff's `Origin-Commit` field is your traceability anchor — clone the authoring repo at that SHA if you need to verify referenced state.

6. **Before authoring an outbound handoff**, read the target producer's `REPO_CARD.md` if it exists at the producer's root. Confirm:
   - `Status: accepting` (not `freeze` or `archived`).
   - Your intended handoff type is in `Accepts-handoff-types`.
   - Drop at the path named in `Drop-location` (default `./` = repo root).

   If no `REPO_CARD.md` exists at the target, default to dropping at the producer's repo root for `request` direction; for `deliver` direction, drop into the consumer's `handoffs/` folder.

7. **Do not auto-act on `parked` items.** `parkinglot.md` and `long-term-parking.md` (`Direction: internal`) are this repo's own deferred-idea backlog — deferred *by design*. Act on a parked item only when the human directs it, or when its `Trigger:` condition is genuinely met. When you do, pull it into active work or graduate it (into a GitHub issue, or a cross-repo `request`/`deliver` handoff), then set that item's `Status: superseded` with a `Companions:` pointer to where it went. Never silently work a parked item just because you saw it.

### Quick lookup — Status enum

| Status | Meaning | Should I act? |
|---|---|---|
| `draft` | Author still composing | No — wait for `delivered` |
| `delivered` | Awaiting recipient review | **Yes** — apply path |
| `applying` | Someone is already on it | No — don't double-apply |
| `applied` | Work landed in receiving repo | No — past terminal |
| `archived` | Settled, transient copies deleted | No — past terminal |
| `superseded` | Replaced by a newer handoff | No — follow `Companions: superseded-by` |
| `parked` | Internal deferred idea, awaiting its `Trigger:` | No — act only on Trigger or human direction |

### Quick lookup — Direction enum

| Direction | Who authored | Where the canonical lives |
|---|---|---|
| `request` | Consumer (this repo, requesting from a producer) | `<consumer>/handoffs/HANDOFF_<topic>.md` |
| `deliver` | Producer (another repo, delivering to consumer) | `<consumer>/handoffs/<YYYY-MM-DD>_<topic>.md` |
| `internal` | This repo (handoff to a future session of itself) | `handoffs/parkinglot.md`, `handoffs/long-term-parking.md` |

## Learning loop

Session insight → durable knowledge.

- **Capture trigger.** When an interaction surfaces a non-obvious fact, a recurring trap, or a validated approach that future sessions should not have to rediscover, the operator (or agent, on confirmation) writes a small Markdown file to `lib/agents/knowledge/learned/`.
- **File shape.** Each file carries agentskills.io frontmatter (`name`, `description`, `version`, `author`, `license`, `metadata`). Body is the lesson itself — what was learned, why, how to apply it.
- **Promotion rule.** When a file in `lib/agents/knowledge/learned/` has been referenced twice, promote it to a first-class file under `lib/agents/knowledge/`. Promotion is a deliberate act, not automatic — confirm with the operator.
- **Boundary.** `lib/agents/knowledge/learned/` is for *this repo's* lessons. Cross-repo lessons go through the handoff convention above, not this lane.

> Path note: this repo's canonical knowledge directory is `lib/agents/knowledge/` (not `knowledge/` at root, which the make_AGENTS template assumes). The learned lane sits alongside the other knowledge files at `lib/agents/knowledge/learned/`.

## Continuous improvement — bugs + enhancements

The toolkit ships with TWO complementary capture mechanisms; the agent's job is to recognize the moment and route appropriately.

### Channel 1 — `cb_report_bug.py` (immediate, external)

A one-command CLI that files a scrubbed report on `chaz-clark/canvas-toolbox` via the Cloudflare-fronted intake worker (`infra/bug-intake-worker/`). **No GitHub account needed on the operator's side.** Use for:

- **Bugs** — something broke, something surprised you, something diverged from documented behavior. Title prefix: `bug:`.
- **Enhancements** — operator articulated something the tool doesn't yet do, OR a recurring friction has been captured in `learned/` at least once already (the Hermes promotion threshold). Title prefix: `enhancement:`.

The maintainer triages bug-vs-enhancement at the issue level. The CLI doesn't need a flag — the title's prefix is the signal. A GitHub Action auto-labels every filed issue `agent-submitted` for filtering.

### Channel 2 — `lib/agents/knowledge/learned/` (patient, internal)

The Hermes Learning loop (Sprint B, see above). When the friction is interesting but you're not sure it rises to "file it now" — capture it here as a durable lesson. The promotion rule applies: a learned entry that gets **referenced a second time** is the agent's signal to surface filing as an enhancement via Channel 1.

### Bias: err toward surfacing

A low-quality report costs the maintainer ~10s to close. A real bug or enhancement never filed costs much more (silent toolkit drift, hand-rolled workarounds in consumer repos, lost trust). **When in doubt, surface the option.** The operator decides whether to file.

### Default — DO surface filing when

- A tool exits non-zero and the message doesn't read like operator config.
- A tool produces output that "feels off" — wrong band, over-aggressive scrub, an audit that flags everything or nothing, a sync that touches more than expected.
- Documented behavior diverges from observed behavior.
- A Canvas API call fails with a status you can't immediately attribute to operator action (a 4xx that isn't auth, a persistent 5xx, persistent timeouts).
- The operator asked for something the tool doesn't do, or proposed a workflow that would benefit from new behavior.
- Performance surprised you, or you had to stop and re-read the code to be sure it was doing the right thing.
- A `learned/` entry is being referenced for the second time — that's the Hermes promotion threshold; surface the file-as-enhancement option.

### Hard rules — do NOT suggest filing when

These are the system working as designed, not bugs:

- **FERPA gate refusing.** `grader_name_leak_check.py` finding a name; deid quarantining a docx into `submissions_deid/_REVIEW/`; `_challenge_dir_guard` refusing the toolkit clone path. The check fired correctly; the operator's roster or challenge dir needs fixing.
- **Push gate refusing.** Missing `--mark-reviewed`; `canvas_course_guard` refusing live-course writes without `--allow-enrolled`; the collision / lock / hold guards (issues #62 / #63 / #72) blocking a push. Each is a documented guardrail.
- **Operator config gaps** — missing env var, missing keymap, missing rubric. Tool message already says what to fix.
- **The agent itself supplied bad inputs.** Wrong assignment id, wrong path, wrong flag. Re-try with the correction first; only suggest filing if the CORRECTED invocation also behaves wrong.

### How to surface

ONE line at the end of the agent's response, clear and skippable.

For bugs:
> _If this looks like a toolkit bug rather than a config issue, `uv run python lib/tools/cb_report_bug.py --from <log path> --title "bug: <short title>"` files it scrubbed + maintainer-routed. No GitHub account needed._

For enhancements:
> _This looks like an enhancement candidate. If the toolkit should grow this behavior, `uv run python lib/tools/cb_report_bug.py --title "enhancement: <short title>"` files it for the maintainer to triage._

For repeated friction crossing the Hermes promotion threshold:
> _This is the second time this friction has shown up (first capture at `lib/agents/knowledge/learned/<earlier>.md`). That's the Hermes promotion threshold — worth filing as an enhancement via `cb_report_bug.py` so the toolkit can grow to handle it natively._

### Bundling discipline

Propose a specific title — that's the maintainer's primary triage signal. "test bug" is useless; "bug: grader_push 4xx on KC1 assignment 16958677" is actionable. Suggest `--from <log path>` when a log exists. The CLI auto-bundles toolkit version, Python version, platform, sanitized cwd, and the last 150 log lines; it opens `$EDITOR` for the operator's "what I expected vs what happened" detail before posting.

### Adopter upgrade discoverability

When you're working in a CONSUMER repo (m119-master, ds460-master,
ds250-onln-master, itm327-master, aol-student, etc.) and you notice
`canvas-toolbox/` is at an older version than the latest, surface
[`UPGRADING.md`](UPGRADING.md) at the canvas-toolbox repo root. It carries
the scenario-driven migration guide (vs. [`CHANGELOG.md`](CHANGELOG.md)
which is the per-version mechanical record). One-line check:

```bash
uv run python canvas-toolbox/lib/tools/grader_fetch.py --version
```

If the printed version is behind the latest (currently **v0.50.1**),
the upgrade is usually a clean `cd canvas-toolbox && git pull && uv sync`.
UPGRADING.md flags behavior changes the operator might notice (the
v0.40+ Test Student exclusion, the v0.41-0.42 push guards, the
v0.50 bug-intake CLI). The toolkit does not auto-upgrade; that's by
design (operator control). But agents can and should notice the gap.

### Security issues are NOT bugs

If you find (or the operator surfaces) a path that LEAKS student PII,
exposes the bug-intake worker's PAT, or otherwise bypasses a FERPA
gate — **don't file via `cb_report_bug.py`** (it files publicly).
Follow [`SECURITY.md`](SECURITY.md) instead: email the maintainer
directly. The public intake channel is for bugs + enhancements; the
private channel is for security.

## Active Context

_Last updated: 2026-06-26_

### Recent: BYUI SAS accommodation sprint — quiz time extension + test_reschedule + apply dispatcher (v0.72.0, 2026-06-26)

**v0.72.0** — three-item sprint closing out the BYUI Accessibility
Services catalog dispatch chain. Triggered by the life-pm handoff at
`handoffs/2026-06-26-accessibility-accommodations-catalog.md`.

**S1 — `lib/tools/student_quiz_time_extension.py`** (~265 lines).
Per-student quiz time multiplier (1.5x, 2.0x, or any > 1.0). Targets
CLASSIC Canvas quizzes only (New Quizzes documented as a follow-up).
Pulls quiz `time_limit` from API; computes `extra_time` minutes via
`ceil(time_limit * (multiplier - 1))`; POSTs to `/quizzes/<id>/extensions`
with `quiz_extensions[][user_id]` + `quiz_extensions[][extra_time]`.
Scopes: `--quiz-id` (one) or `--all-timed` (every timed quiz in
course). PII-free via `--user-id` or `--deid-code` lookup. Auto-skips
untimed quizzes. Pure-helper `compute_extra_minutes` uses `math.ceil`
so partial minutes always round UP — the student never gets less time
than the multiplier promises.

**S2 — `--shift-by-days N` mode on `student_late_accommodation.py`**.
For SAS `test_reschedule` (distinct from `occasional_extensions`):
shift unlock/due/lock forward by N days instead of dropping lock_at.
New pure helper `shift_iso_timestamp(ts, days)` advances the date
prefix of an ISO 8601 string while preserving the time-of-day and
timezone suffix (no full tz parser needed — string-prefix arithmetic
is sufficient for accommodation-grade precision). New
`build_shift_payload(assignment, user_id, days)` is the
analog of `build_override_payload` but emits all three dates shifted.

**S3 — `lib/tools/apply_sas_accommodations.py`** (~280 lines). YAML
dispatcher. Reads `grading/.sas_accommodations.yml`, walks each
student × accommodation, classifies each `key` into one of 4 tiers
(`canvas` / `proctoring` / `policy` / `unknown`). Canvas-tier
accommodations are invoked as subprocess calls to the matching tool
(so each tool stays standalone, no cross-tool imports). Proctoring +
policy tiers surface as a one-line operator checklist. Audit trail
written to `grading/.sas_accommodations_applied.log` (FERPA tier 2,
gitignored). Catalog hard-coded in three frozen sets at the top of
the module — single source of truth, easy to extend when life-pm
surfaces new accommodation types.

**Knowledge file — `lib/agents/knowledge/sas_accommodations_knowledge.md`**
vendors the life-pm catalog into the canvas-toolbox knowledge surface
so future agents can reason about SAS dispatch without re-reading the
handoff each time. Maps every catalog key → tier → tool invocation;
documents the YAML handoff schema; explains the
"how to add a new key" extension process.

**README — 12th workflow row + dedicated SAS section** between
the de-id master section and "Sharing your grader." Late-work
accommodation section now distinguishes the two flavors (drop lock_at
for `occasional_extensions` vs `--shift-by-days N` for
`test_reschedule`) in addition to the four scoping modes.

**55 new tests passing** (605 passing total, up from 550):
- 21 tests for quiz time extension (compute_extra_minutes ceil
  behavior, filter_timed_quizzes, payload shape, master lookup edge
  cases)
- 12 new tests for shift-by-days mode (shift_iso_timestamp edge
  cases: month/year boundaries, timezone preservation, null
  passthrough, negative-days defensive; build_shift_payload all-three-
  dates invariant)
- 22 tests for SAS dispatcher (classify_key for all catalog members,
  plan_one_accommodation for each canvas-tier key with default + YAML
  overrides, plan_entries flatten/skip/order behavior, audit-line
  format invariants)

**What's NOT yet done (deferred):**
- New Quizzes (LTI) support — they use a different endpoint
- `apply_sas_accommodations.py` is invoked manually; future work
  could wire it into a daily/weekly cron or post-fetch hook

### Earlier: Path A migration — `.known_names.txt` auto-derived from the de-id master (v0.71.0, 2026-06-26)

**v0.71.0** — Path A of the de-id master consolidation. Mid-build
operator question after v0.70.0 shipped: *"Do all de-id scripts run
off the new master? Anything re-id'ed goes to Downloads?"* — surfaced
that the master was purely additive (only 2 tools used it); the
scrub-pass roster `.known_names.txt` was still populated separately
by `grader_fetch.py`.

**What landed:**

1. **`build_deid_master.py` now auto-derives `.known_names.txt`** —
   single new helper `render_known_names_lines()` emits BOTH sortable
   ("Lastname, Firstname") and display ("Firstname Lastname") forms
   per student so the scrub matches whichever literal appears in
   submission text. Case-insensitive dedup; sorted; header comments
   so a future reader doesn't hand-edit it.

2. **7 new tests** (550 passing total, up from 543). Covers both-forms
   emission, header comments, dedup, empty-name skip, single-word
   names (no comma → no display-form duplicate), determinism, sort
   order.

**Unchanged (deliberate):**
- `grader_fetch.py`'s `update_known_names()` still works as before
  (append-mode dedup; appends submitters who weren't in the People
  view yet). Path A is additive, not replacement.
- Per-assignment keymaps untouched. Grader pipeline hot path unchanged.

**Path B deferred** — full migration where the master replaces
per-assignment keymaps for the grader pipeline — approved in principle
but deferred to a future session per operator direction. Path B becomes
harder over time; the deferral is intentional and credit-aware.

### Earlier: Course-wide de-id master + per-student late-work accommodation primitives (v0.70.0, 2026-06-26)

**v0.70.0** — closes issue #109 (agent-submitted ~10 min after v0.69.1
shipped, from the DS 460 pilot). Two related primitives + four-mode
scoping + the README cleanups Chaz flagged mid-build.

**The missing primitive** — until v0.70.0, the toolkit could de-identify
within a single grading workflow (per-assignment keymaps) and could
scrub names (.known_names.txt) but had NO course-wide stable
`code ↔ user_id ↔ name` surface. That's the primitive every keyed /
FERPA workflow actually wants — and it's what enables the accommodation
tool to take `--deid-code S-95DBB6` instead of `--user-id 173819`
(so the operator never speaks the student's name to the agent).

**What landed:**

1. **`lib/tools/build_deid_master.py`** — fetches Canvas People with
   ALL enrollment states (active + invited + inactive + completed),
   hashes user_id → `S-XXXXXX` (6 hex from sha256, configurable
   prefix + hash-bits), writes `grading/.deid_master.csv` (FERPA
   tier 2). Auto-writes `grading/.gitignore` to make tier 2 bulletproof.
   Detects collisions at write-time with clear recovery message
   (`--hash-bits 8`). Default prefix `S-`; opt out via `--prefix`.

2. **`lib/tools/student_late_accommodation.py`** — lifted from DS 460
   pilot + generalized. Writes per-student assignment overrides that
   keep `unlock_at` + `due_at` but omit `lock_at` (no close date).
   **Four scoping modes** (the v0.70.0 mid-build operator ask):
   - `--assignment-id` — ONE assignment
   - `--all` — every published, backdated
   - `--from YYYY-MM-DD` — due on/after a specific date
   - `--from-days-ago N` — rolling window (recommended default; e.g.
     `--from-days-ago 14` = last 2 weeks through end of term)
   Resolves student via `--user-id` OR `--deid-code` (PII-free).
   `--remove` flag works with any scope.

3. **`lib/agents/knowledge/deid_master_knowledge.md`** — the
   4-column contract, collision math, FERPA tier 2 explanation,
   how downstream tools should consume the master (never read
   `sortable_name` unless explicit).

4. **54 new tests passing** (543 passing total, up from 489;
   Title IV pure-helper pattern continued — function in/out, no
   Canvas API mocking).

5. **README mid-build tweaks** (Chaz-flagged):
   - Step 3 prompt now explicitly invokes `cb-init` (so the agent
     uses our purpose-built idempotent bootstrap, not its own ad-hoc
     sequence)
   - `byui.instructure.com` → `your-institution.instructure.com`
     (generic across institutions)
   - "Who uses it" section DROPPED (was leading with BYUI specifics)
   - "Sharing back with the project" SIMPLIFIED from a technical
     PATH/fallback wall to a 3-row agent-prompt table
   - 11th workflow row added: "Give one student late-work accommodation"
   - NEW dedicated section "Per-student late-work accommodation"
     with the 4-mode scope table
   - Trailing version line names the new primitives

**Field validation** (from issue #109 author):
- DS 460 pilot: 1 real student, 36 assignments, `--all` applied
  cleanly — every override kept original open/due with lock=null
- 30 active → 37 total → 7 withdrawn surfaced (the `withdrawn` flag's
  value, hidden by the active-only People view)
- Canvas GET overrides slow-path caveat baked into the tool: APPLY
  POSTs directly without listing existing overrides; only REMOVE reads

### Earlier: README streamline — cut technical setup options + surface AI architect capability (v0.69.1, 2026-06-26)

**v0.69.1** — docs-only patch. Two operator-flagged issues:

1. **Setup steps had too many forks** — the non-technical
   agent-driven prompt was buried under TL;DR one-liner + Option B
   (manual fast-path cb-init + manual long path) + Option C. Cut
   Option B entirely. Cut TL;DR one-liner. Promoted Option A as
   THE path; faculty pastes one prompt to their agent and the
   agent handles git/uv/Python/deps. Option C (colleague-handover)
   retained as a small sub-section. Migration paragraph kept as
   one-line footer for existing users.

   **Rationale:** technical users will figure it out without
   instructions; the README's job is to lower the bar for
   non-technical faculty. Forks confuse the audience that needs
   the most hand-holding.

2. **AI architect capability not surfaced** — the toolkit ships
   with 20+ pedagogical knowledge files (backwards design / Hattie
   3-phase / Merrill / Kolb / Cognitive Load Theory / AAC&U
   rubrics / Carnegie workload / etc.) that the agent uses when
   designing a NEW course or redesigning an existing one. README
   only documented audit / sync / grade flows — never said the
   toolkit can help you BUILD a course. Added:

   - **10th agent-prompt row**: *"Design or improve a course (AI
     architect)"* — links to dedicated section
   - **NEW dedicated section** *"Architecting a course with AI
     assistance"* between Step 3 and Auditing — names the 22
     design-relevant knowledge files in a table, names the
     prompt, names the 6 things the agent walks the faculty
     through (CLOs → assessments → module sequence → rubrics →
     workload → accessibility), keeps the *"you stay the
     architect; AI is the assistant"* framing

**No code changes.** No new tests required. Version triple-sync
0.69.0 → 0.69.1 (patch — docs only). 483 tests unchanged.

### Earlier: Title IV course-engagement audit + Downloads-folder FERPA tier 3 (v0.69.0, 2026-06-26)

**v0.69.0** — new audit tool category: federal Title IV last-date-
of-engagement classifier for UW/UF reporting (R2T4 candidates).
Establishes a **new FERPA tier**: named reports outside the repo
entirely (LLM has no working-directory access to `~/Downloads/`).

**Why:** federal Title IV (34 CFR 668.22) requires faculty /
institutions to report last-date-of-academic-engagement for any
student who unofficially withdraws. Manual workflow: trawl
SpeedGrader + Discussions + Quizzes per student at term-end.

**What landed:**

1. **`lib/tools/course_engagement_audit.py`** — fetches assignments
   + quizzes + discussion entries per enrolled student, computes
   `last_engagement` as max timestamp (deliberately EXCLUDES
   `last_activity_at` and page views per DOE *"logging in is not
   sufficient"*), classifies into ACTIVE / UW / UF /
   NEVER_PARTICIPATED against operator-provided UF cutoff,
   re-identifies user_id → name ONLY at the last step, writes
   PDF + MD to `~/Downloads/`. Hard refuses to write inside cwd
   (FERPA tier 3 defense-in-depth).

2. **`lib/tools/update_title_iv_snapshot.py`** — companion tool.
   Fetches 6 canonical Title IV sources, regex-extracts body
   content (no LLM tokens; deterministic), writes Markdown
   snapshots + sha256 manifest. Mozilla UA to avoid anti-scraping
   shells; content-length sanity check.

3. **6 cached Title IV sources** (~674k chars total) at
   `lib/agents/knowledge/sources/title_iv/` — CFR 668.22, FSA
   Handbook Vol 5 Ch 1/2/3 + Vol 2 Ch 1, Federal Register final
   rules effective 2026-07-01. Auditable provenance.

4. **NEW knowledge file** `course_engagement_audit_knowledge.md` —
   Title IV research foundation + classification rules +
   Downloads-folder pattern + re-verification cadence.

5. **`grader_knowledge.md §1` extended** — "two zones" → "three
   tiers." NEW tier 3: named reports outside the repo entirely.

6. **44 new tests** (483 total, up from 439).

7. **README updated** — 9th agent-prompt row added; new "Title IV
   last-participation audit" section; comparison table gains a
   Title IV row; trailing version line names verification date.

**Title IV verification date stamp: 2026-06-26. Next review:
2027-06-26.** The new Distance Ed + R2T4 final rules go into
effect **2026-07-01** (this week at time of build) — the cached
Federal Register snapshot captures their canonical text.

Operator's specific asks all honored:
- ✅ "Research with confirm" — 4 parallel WebSearches; findings
  synthesized in the knowledge file with explicit Title IV
  citations
- ✅ "Document in the readme.md" — capability bullet + dedicated
  section + comparison table + agent-prompt row
- ✅ "Date of update incase title iv updates" — verification date
  + next-review date at top of knowledge file + in README + in
  manifest + in tool docstring
- ✅ "Never participated also in scope" — 4 buckets (ACTIVE /
  UW / UF / NEVER_PARTICIPATED)
- ✅ "PDF" — primary output format; MD as editable source
- ✅ "Root level Downloads" — top-level `~/Downloads/`
- ✅ "Match Title IV naming but allow them to call it last
  participation check" — file is `course_engagement_audit.py`
  (matches existing audit naming); agent recognizes prompts like
  "UW check", "last participation report", "engagement audit"
- ✅ "I like the separation of storage as a rule to enhance our
  FERPA position" — documented as FERPA tier 3 in
  `grader_knowledge.md §1`
- ✅ "Save the Title IV resources and produce an update script" —
  `update_title_iv_snapshot.py` + 6 cached sources + manifest
- ✅ "Regex the tags needed from the html to reduce token useage" —
  regex-only extraction; no LLM tokens used; deterministic; sha256
  manifest skips unchanged sources on re-run

Ships via PR (third use of branch protection) on
`feat/course-engagement-audit`.

### Recent: README rebalance — broader toolbox positioning + 8-workflow agent-prompt list (v0.68.2, 2026-06-26)

**v0.68.2** — second README correction after operator feedback on
v0.68.1: *"overall the rest is too grader heavy focused - this tool
does so much more, grader is a key compoennt and probably the
marketing one but we cant turn the toolbox into a grader only"* +
*"the 'what it looks like in practice' should be a positive
experience"* + *"we need the list of how to use it back to prompt
ideas again of all 8 tools"*

**Six structural changes:**

1. **Intro grammar fixes** — *"you're always in the loop"* (was
   *"your"*) and *"everything in Canvas"* (was lowercase). Operator-
   authored intro otherwise preserved.
2. **"What it looks like in practice" replaced** — was a negative
   example (regression gate refusing a lower). Now a POSITIVE example
   showing `_all_comments.md` ready for review + per-student evidence
   files generated. Ends with *"Nothing pushes to Canvas until you
   mark reviewed"* — reassurance, not threat.
3. **NEW section: "What you can ask your AI agent to do"** — 8-row
   table of prompt-shaped workflows (sync, quick audit, full audit,
   course map, NQ response data, grading, cross-faculty sharing,
   semester rollout). The most adopter-friendly part of the legacy
   README; restored in marketing-shaped form.
4. **"Why this exists" rebalanced** — opens with *"Your course is a
   document. The boring parts… should be your call."* The wedge story
   is still grading (the marketing centerpiece) but the framing now
   covers ALL workflows.
5. **"What changes" table restructured** — was AI-grading-as-a-service
   vs Canvas Toolbox (grader-only). Now Canvas-UI-alone vs Canvas
   Toolbox across SIX workflows: editing, auditing, grading, sharing,
   semester rollout, NQ response data.
6. **"What you can trust" split into two sub-sections** —
   (a) Architectural commitments that apply everywhere (FERPA two-
   zone + voice-preservation + brain-agnostic + read-only-audits +
   local-source-of-truth); (b) Grading safety gates (the 11 — still
   present but framed as the highest-stakes-workflow specifics).

**Length:** 474 lines (up from v0.68.1's 447). Adds the 8-workflow
table; the rebalance otherwise didn't add net length.

**No code changes; 439 tests passing; pre-commit green.**

Ships via PR (second use of branch protection's PR flow).

### Recent: README correction — restored faculty install scaffold + voice rewrite in Chaz's voice (v0.68.1, 2026-06-26)

**v0.68.1** — corrects v0.68.0 after operator feedback: *"the quick
start is too small compared to the old readme.md remember our
audiance is mostly non-technical faculty you lost our audiance with
your research of GH"* and *"your voicing is too AI for the readme.md
you should scal all my *-master courses for their voicing."*

**Two things were wrong with v0.68.0:**

1. **Audience mismatch.** v0.68.0 was researched against top-starred
   GH READMEs (Astro, Tailwind, shadcn/ui, etc.) — all aimed at
   developer-fluent audiences. canvas-toolbox's audience is
   non-technical faculty. The legacy 862-line README's verbose
   Step 1/2/3 install scaffold wasn't bloat — it was THE entry
   point. v0.68.0 compressed install to ~5 lines + TODO links.
   That's wrong for the audience.

2. **Voice mismatch.** The v0.68.0 prose read as marketing-formal
   ("The architectural commitment isn't rhetoric. It's enforced in
   code") — not Chaz's voice. Six parallel Explore agents scanned
   `*-master` repos (itm327, ds250-onln, ds250-onml, ds460, m119,
   cse450) to extract Chaz's actual writing voice from his
   README.md / AGENTS.md / handoffs/. Consistent signature
   surfaced: short + punchy alternated with structured detail;
   imperative + consequence ("Edit X first. Never push Y."); "This
   is / This is NOT" scope framing; "My lean:" for opinions;
   "Source of truth:" framing; "Note:" / "Never..." / "Always..."
   markers; explicit trade-offs with named costs; no marketing
   speak ("leveraging", "seamlessly", "powerful"); no hedging
   ("might", "perhaps", "may want to").

**The fix:**

1. **Restored** the full Step 1 → Step 2 → Step 3 install scaffold
   from the legacy README. Step 1 (pick an IDE) + Step 2 (pick an
   AI assistant) + Step 3 (TL;DR / Option A agent-driven / Option B
   manual / Option C colleague-handover / migration). Plus the
   audit-tool catalog + grading pipeline detail (condensed but
   present, not TODO-linked).
2. **Rewrote** the prose throughout in Chaz's voice. Marketing
   wedge + safety-gate table kept (those landed well in v0.68.0);
   the connective tissue is now matter-of-fact + imperative + no
   filler. Example: v0.68.0 said *"Eleven coded safety gates like
   this one stand between AI-assisted grading and the student's
   gradebook — accumulated from real lived failures, not
   speculative design."* v0.68.1 says: *"Eleven safety gates
   between AI-assisted grading and the student's gradebook. Each
   one came from a real incident. Each one shipped within hours of
   being filed."*
3. **Length** — 447 lines (up from v0.68.0's 206, down from
   legacy's 862). The audit-tool catalog stays inline; grading
   pipeline links to `grading_readme.md`; no TODO links to
   nonexistent `INSTALL.md` / `OPERATIONS.md` (those references
   were premature in v0.68.0 — the legacy is still in
   `lib/marketing/README-LEGACY-2026-06-26.md` as source material
   if those docs are extracted later).
4. **Voice research** captured to
   `handoffs/2026-06-26_chaz-voice-extraction.md` (gitignored;
   six per-repo agent reports synthesized).

**Branch protection — first PR-flow test.** v0.68.1 ships via PR
on `feat/readme-restore-faculty-scaffold` branch (not direct push)
since branch protection went live earlier this session. CI
required + linear history + force-push-blocked. Auto-merge on CI
green.

### Recent: Marketing-perspective README pass — Phase 2 (v0.68.0, 2026-06-26)

**v0.68.0** — replaces the 862-line developer-doc README with a
206-line marketing-pass README. Research-grounded redesign per the
operator's 2026-06-26 ask. Same Option C delivery shape as v0.65.0
voice coaching: research synthesis + draft + ship.

**The wedge story made operational:**

The new README leads with the **shadcn/ui-style category reframe**:

> "This is not an AI grader. It is how an instructor uses AI to
> grade *with* them — staying the author of every grade and every
> word the student reads."

That's the parking-lot positioning work (instructor-author vs
AI-author wedge from 2026-06-24 meeting) made into the README's
opening promise. Everything else flows from there: the FERPA
two-zone architecture, the voice-preservation contract, the 11
safety gates, the cross-faculty sharing pattern.

**Six top-starred GH repos researched** (anthropics/claude-code,
shadcn-ui/ui, withastro/astro, tailwindlabs/tailwindcss,
ollama/ollama, continuedev/continue) for structural + marketing
patterns. Headline finding: every one of them is dramatically shorter
than canvas-toolbox's prior 862 lines (mean 108). The new draft at
206 lines is a 76% reduction while keeping more "why" framing than
typical (canvas-toolbox's category isn't established yet — needs
the positioning section).

**Seven cross-cutting patterns applied:**

1. **One-line value hook** — `"FERPA-safe AI-assisted Canvas LMS
   toolkit. Your voice. Your accountability. Your students' privacy."`
2. **Category reframe** — shadcn/ui pattern; the "not X, is how
   you Y" inversion
3. **Visual above-the-fold** — synthetic terminal-output example
   showing the regression gate firing (Claude Code demo-GIF analog)
4. **Install front-loaded** — single-line install at line ~85 with
   link to dedicated `INSTALL.md` (TODO follow-up doc)
5. **Adoption signals as scannable table** — 11 safety gates with
   a 1-line description of what each one prevents (Ollama
   ecosystem-flex analog, but with safety gates as the breadth)
6. **Detail moved out** — `OPERATIONS.md` + `INSTALL.md` referenced
   as follow-up docs (TODOs); the 862-line legacy README is preserved
   at `lib/marketing/README-LEGACY-2026-06-26.md` as source material
   for those follow-ups
7. **Tone: middle** — academic credibility + value-forward hook;
   no marketing fluff (no "revolutionary," "next-generation,"
   "AI-powered" — every faculty BS-detector would catch those)

**What stayed from the old README** (rewritten, not removed):
title + badges, capability framing, FERPA story, license. The voice
is recognizably canvas-toolbox.

**What's new**: the wedge positioning, the safety-gate trust table,
the cross-faculty sharing prominent section, the comparison table
vs AI-grading-as-a-service, the synthetic terminal-output demo.

**Two reference artifacts created:**

1. **[lib/marketing/README-LEGACY-2026-06-26.md](lib/marketing/README-LEGACY-2026-06-26.md)** —
   the 862-line predecessor, preserved as source material for the
   `OPERATIONS.md` / `INSTALL.md` extractions when those land
2. **[handoffs/2026-06-26_readme-marketing-research.md](handoffs/2026-06-26_readme-marketing-research.md)** —
   gitignored audit-trail synthesis: the 6 repo analyses,
   7 cross-cutting patterns, recommended structure, the wedge story
   made concrete

**Follow-up work parked** (not blocking v0.68.0 ship):

- `OPERATIONS.md` — extract the audit-tool catalog detail from the
  legacy README
- `INSTALL.md` — extract the Step 1/2/3 IDE+AI-assistant detail
- Operator review pass on the rendered GH README (the operator
  said: "I will review it in GH rendered and come back with any
  tweaks")

**Cross-walk with parking-lot positioning work:**

The instructor-author vs AI-author wedge from the 2026-06-24
meeting (captured in `handoffs/parkinglot.md`) is now the README's
opening promise. The wedge moved from "captured for future
positioning work" to "live on the README." LinkedIn-marketing copy
(parking-lot idea C) can now draw verbatim from the README hook +
comparison table + safety-gate stack.

The cumulative session-arc since 2026-06-24 (~3 days):

| Day | Versions | Theme |
|---|---|---|
| 06-24 | v0.59.0 → v0.62.1 | Push-side safety gates (#95-#98) |
| 06-25 | v0.63.0 → v0.66.0 | Silent-success gates + group workflow + research-grounded knowledge files (#99/#101/#102/#100/#103) |
| 06-26 | v0.67.0 → v0.68.0 | Cross-faculty sharing + voice coaching ships + marketing pass |

**11 versions, 11 closed issues, 2 parking-lot ideas shipped, +178 tests in 3 days.** All lived-experience-driven or operator-research-grounded. Zero speculative.

### Recent: README mentions cross-faculty sharing — Phase 1 of marketing pass (v0.67.1, 2026-06-26)

**v0.67.1** — small docs-only patch. The v0.67.0 cross-faculty
sharing feature (grader_export.py + grader_import.py) wasn't
mentioned in the README; this patch adds a bullet to the "What you
can do with it" list naming the feature + the voice-preservation
guarantee + the FERPA exclusions + the version-compatibility refuse.

**Phase 1 of the larger marketing-perspective README pass** (operator
ask 2026-06-26). Phase 2 is the full marketing-shaped README rewrite
with research-grounded structure pulled from top-starred GH repos —
deferred to a separate work block per the established
research-synthesis-first pattern (same shape as the v0.65.0 voice
coaching deliverable).

### Recent: cross-faculty sharing — grader_export.py + grader_import.py (v0.67.0, 2026-06-26)

**v0.67.0** — ships parking-lot **Idea B (cross-section sharing)** as
formalized adoption-multiplier infrastructure. Faculty A teaching
Course X can now bundle their rubrics + task specs + configs into a
share.zip; Faculty B teaching the same course imports it as their
starting substrate. Per the voice-preservation contract from
v0.65.0: **the sending faculty's per-instructor voice file is NEVER
in the export.** The receiver builds their own voice.

**Operator decisions baked in** (locked during the 2026-06-26 scoping
pass):

| # | Decision | Resolution |
|---|---|---|
| 1 | Tool shape | Pair of scripts (`grader_export.py` + `grader_import.py`) — matches the established naming convention |
| 2 | Export granularity | Operator passes `--challenges` list; default = all subdirectories of `grading/`. Supports both per-challenge and whole-course sharing scenarios |
| 3 | Voice handling | Per-instructor voice file NEVER exported. NEW course-level `voice_pitfalls.md` convention introduced (per-challenge optional file capturing course-content common mistakes, NOT voice). Universal pitfalls stay in `grader_voice_knowledge.md §5` (ships natively with canvas-toolbox; no need to bundle) |
| 4 | Version compatibility | Hard refuse if local canvas-toolbox is OLDER than the export's. Error message names the exact upgrade commands. Same-or-newer is fine |

**What landed:**

1. **[lib/tools/grader_export.py](lib/tools/grader_export.py)** —
   bundles a course's shareable artifacts into a ZIP. Whitelist:
   `RUBRIC.md`, `assignment_spec.md`, `voice_pitfalls.md`,
   `config.json`/`config.yml`/`config.yaml`, `README.md` per challenge.
   Defense-in-depth FERPA blacklist enforced (refuses to write any
   path matching `submissions_*`, `feedback/`, `.keymap.json`,
   `.fetch_log.json`, `.review.csv*`, `.push_log.md`,
   `_existing_grades.csv`, `_consensus.csv`, `_summary.csv`,
   `_all_comments.md`, `_gradebook_actuals.csv`,
   `UNIQUE_GROUP_MEMOS.md`, `student_feedback_voice_*`, `_corpus`).
   Writes `share-manifest.yml` + `READ_ME_BEFORE_IMPORT.md` at the
   ZIP root.
2. **[lib/tools/grader_import.py](lib/tools/grader_import.py)** —
   reads + validates the manifest, runs the version compatibility
   check (HARD REFUSE if local < export), shows the receiver exactly
   what's about to land + what's intentionally excluded, prompts
   `Type 'import' to confirm`, then extracts. Defense-in-depth
   blacklist enforced again on the receiving side.
3. **NEW `voice_pitfalls.md` convention** documented in
   [`grader_voice_knowledge.md §5`](lib/agents/knowledge/grader_voice_knowledge.md) —
   optional per-challenge file capturing course-level common mistakes
   (e.g., "in this Polars course, students confuse `top_k` and
   `head`; always redirect to `top_k`"). EXPORTED with the share
   bundle; distinct from the per-instructor voice file which is
   NEVER exported.
4. **[`grader_knowledge.md §17`](lib/agents/knowledge/grader_knowledge.md)** —
   new section "Cross-faculty sharing: export/import the course
   substrate, never the voice." Documents the two tools, the
   inclusion/exclusion lists, version compatibility, and the
   receiver's next-steps. The receiver README echo: *"Your voice is
   the asset. The imported substrate is a starting point."*
5. **38 new tests** in `test_grader_share_helpers.py` covering:
   - Defense-in-depth blacklist (submissions, feedback, identity
     bridges, reviewer/push artifacts, per-cohort grading data,
     per-instructor voice files, TA corpora, group memos, case
     insensitivity, false-positive guard on whitelisted files)
   - File-whitelist behavior (rubric/spec/config/voice_pitfalls
     inclusion; subdirectory recursion EXCLUDED to keep FERPA-
     protected per-student dirs invisible; deterministic sort;
     empty/nonexistent dirs safe)
   - Manifest building (required fields, voice-preservation named
     explicitly in exclusion list, challenge sorting determinism)
   - Receiver README rendering (course label named, voice
     preservation emphasized, numbered next-steps)
   - Semver parsing (basic, build metadata stripped, prerelease
     stripped, unparseable → None)
   - Version compatibility (same OK, newer OK, older REFUSED with
     versions named, unparseable proceeds with warning)
   - Manifest validation (minimal-ok, missing required fields,
     wrong types, defensive against garbage YAML)

**Total tests now 439 (up from 401).** All pre-commit hooks pass.

**Cross-issue + parking-lot composition.** This v0.67.0 release is
the cross-faculty adoption multiplier the parking-lot positioning
work has been pointing at:

- Idea **A** (voicing coach, v0.65.0) — receiver runs the articulation
  interview to build their own voice
- Idea **B** (cross-section sharing, v0.67.0 — THIS RELEASE) — sharing
  tool that preserves voice while transferring everything else
- Idea **C** (LinkedIn / adoption) — now provable: "AI-assisted
  grading where the instructor stays the author" has receiving-end
  enforcement, not just sending-end policy
- Idea **D** (robust nemawashi) — `voice_pitfalls.md` is one of the
  share-back mechanisms; cross-faculty sharing is the other

**The voice-preservation contract is now provable, not just
documented.** Two faculty teaching the same course can share rubrics
and task specs and course-content pitfalls — and the receiving
faculty's grading sounds like THEM, not like the sending faculty.
That's the architectural commitment from v0.65.0 made operational
in v0.67.0.

**Cross-repo:** DS 250 + DS 460 + CE 162 inherit the tools on next
pull. The first real-world use case is likely a future
multi-instructor BYUI offering (DS 250 next semester with a
different instructor; CE 162 picking up an additional section, etc.).
The pattern is also the most credible LinkedIn-ready feature for
the broader adoption story.

### Recent: grader_fetch pulls latest attempt by default — issue #103 (v0.66.0, 2026-06-25)

**v0.66.0** — closes issue #103. **High-severity bug:** before this
fix, `grader_fetch.py` skipped re-downloading when a file of the same
filename already existed locally. Canvas filenames are stable across
attempts → student resubmits → toolkit silently kept stale attempt-1
file → operator graded stale content → 3 DS 250 students were pushed
"still needs revision" comments while they had actually fixed and
resubmitted. The worst failure mode.

**Root cause:** the skip decision was by filename existence, not
attempt freshness. Nothing compared the local file to the remote
submission's `attempt` / `submitted_at`.

**The fix (default behavior change — strictly more correct):**

1. **New pure helper `needs_refetch(local_exists, recorded_attempt,
   remote_attempt, recorded_submitted_at, remote_submitted_at)`** in
   [grader_fetch.py:399-456](lib/tools/grader_fetch.py#L399-L456).
   Returns True when there's positive evidence the remote is newer.
   Defensive across None/missing/non-numeric values — partial data
   never CAUSES a refetch and never PREVENTS one.

2. **`.fetch_log.json` entry schema extended** to record `attempt` +
   `submitted_at` per file (default path + quiz path) and
   `latest_activity_at` per user (discussion path). Old logs without
   these fields still readable — `needs_refetch` falls back to local-
   exists semantics when prior signals are missing.

3. **All three fetch paths wired** (discussion / quiz / default). The
   default path covers attachments + online_text_entry + online_url
   sub-branches. Discussion path uses the max `created_at`/`updated_at`
   across the user's entries (discussions have no attempt# concept).

4. **`--force` semantics unchanged** — still "re-download everything
   regardless." The new default only re-pulls when remote is genuinely
   newer (cheap and correct).

5. **Visibility** — refetched rows print `(refetched: attempt N → N+1)`
   so the operator sees what changed. For discussion-path refetches,
   `(refetched: discussion updated)`.

6. **11 new tests** in `test_grader_fetch_helpers.py` covering the
   `needs_refetch` decision matrix (local missing → fetch; remote
   attempt newer → fetch; remote submitted_at newer → fetch; same
   attempt → skip; same submitted_at → skip; attempt-disagreement-
   with-timestamp → attempt wins; no recorded data + local exists →
   skip / don't speculatively refetch; non-numeric attempts safely
   ignored; partial signals don't trigger false refetch; empty-string
   timestamps treated as missing; remote attempt older → no refetch).

7. **[grader_knowledge.md §10](lib/agents/knowledge/grader_knowledge.md)** —
   added pull-latest-by-default subsection paired with the v0.60.0
   regression-gate story. Names the two layers explicitly: upstream
   (#103) ensures the local file IS the latest attempt; downstream
   (#96) ensures the push doesn't accidentally lower a grade. They
   compose: the grade reaching Canvas was computed from the LATEST
   submission AND won't accidentally drop below what the student
   already had.

**Total tests now 401 (up from 390).** All pre-commit hooks pass.

**Cross-issue thread.** This is the 4th lived-experience-driven
grading-safety fix from DS 250 this week (#95 / #96 / #97 / #98 / #99
/ #101 / #102 from yesterday + today's earlier batch, now #103).
Pattern continues: bug-intake-worker → GH issue → lived RCA →
shipped fix → cohort inherits on pull.

**Cross-repo:** DS 250 + DS 460 + CE 162 inherit on next pull. The
new behavior is strictly more correct than the old; operators who
were relying on `--force` to handle resubmissions will see them
detected automatically going forward.

### Recent: voice_coaching_knowledge.md — upstream scaffolding for the per-instructor voice file (v0.65.0, 2026-06-25)

**v0.65.0** — first knowledge file produced under canvas-toolbox's
research-grounded path (Option C from the planning conversation:
research synthesis doc + draft knowledge file, both committed to
audit-trail). Closes parking-lot idea A (voicing coach) from the
2026-06-24 meeting.

**Operator-set constraint:** preserve the faculty's voice; add value
through phrasing while keeping the voicing intact. Apply the 80/20
rule. This constraint reshaped the entire deliverable — instead of a
"here's how to give better feedback" file that would have flattened
faculty into a generic best-practices yardstick, the file separates
WHAT (universal effectiveness — checkable; agent-applied) from HOW
(per-instructor voice — preserved; agent-respected).

**What landed:**

1. **[lib/agents/knowledge/voice_coaching_knowledge.md](lib/agents/knowledge/voice_coaching_knowledge.md)**
   (~3,900 words) — the v1.0 shippable artifact. 8 sections:
   - §1 — The WHAT/HOW split, named explicitly
   - §2 — The WHAT: 4-point universal effectiveness check (Hattie
     three questions + cognitive-load 1-2 priority items)
   - §3 — The HOW: 8 voice dimensions with synthetic worked
     examples ("same WHAT, different HOWs")
   - §4 — The 80/20 boundary made visible
   - §5 — First-time voice articulation interview (5 questions, ~30
     min, produces a starter `student_feedback_voice_<instructor>.md`)
   - §6 — Edge cases: surface-don't-override pattern when voice and
     effectiveness conflict
   - §7 — Cross-walk to existing voice infrastructure
   - §8 — Research citations
2. **handoffs/2026-06-25_voice-coaching-research.md** (~3,900 words,
   gitignored) — the audit-trail research synthesis. 8 frameworks
   analyzed, DS 250 + DS 460 voice artifacts compared, decisions
   that shaped the knowledge file documented. Available locally for
   anyone who wants to see WHY each section is structured as it is.
3. **[lib/agents/knowledge/README.md](lib/agents/knowledge/README.md)** —
   updated routing table + new "The files" entry following the
   established pattern.

**The research foundation** (8 frameworks):

- **Hattie & Timperley (2007)** — three feedback questions (Where am
  I? How am I? Where to next?). The spine.
- **Wiggins (2012)** — seven keys: goal-referenced, tangible,
  actionable, user-friendly, timely, ongoing, consistent.
- **Dweck (1998-ongoing)** — process vs ability praise. Treated as a
  DIMENSION (not a rule) per operator preference — "nothing should be
  'hard' or 'rules'."
- **Brookhart (2008/2017)** — content + strategy element framework.
- **Cognitive Load Theory (Sweller 1988-ongoing)** — working memory
  limits → 1-2 priority items rule.
- **Warm-demander pedagogy (Hammond 2014; Delpit; Kleinfeld)** —
  high expectations + high warmth + culturally-grounded.
- **Black & Wiliam (1998/2009)** — closing-the-gap formative
  feedback. Almost identical to Hattie three; reinforces the spine.
- **AI voice preservation literature (2025-2026)** — voice fidelity
  is THE adoption barrier; teacher-as-collaborator framing.

**DS 250 + DS 460 cross-course voice signature** (extracted via
Explore-agent mapping of both repos):

- "To be unclear is to be unkind" — appears in BOTH repos as a core
  value (Chaz Clark's voice signature)
- Anti-meta-scaffolding ("Cut 'I want to be clear...'") in BOTH
- "These students are adults" / "consulting engagement" — peer-
  professional register in BOTH
- Forward-looking + concise + specific-praise-only — consistent
  across both courses

The coaching file uses synthetic worked examples (not corpus
extracts) per operator preference — "synthetic + label ok" — to
avoid biasing toward Chaz's voice as "the example."

**Operator decisions baked into the file** (from the scoping pass):

| Question | Operator answer | Implementation |
|---|---|---|
| Worked examples shape | Synthetic + labeled | §3 examples are clearly marked synthetic |
| Dweck framing | Dimension, not rule | Axis 6 treats process/ability as a position |
| Override behavior on edge cases | Never unilateral | §6 "surface, don't override" |
| Edits to existing voice file? | No — standalone | `grader_voice_knowledge.md` unchanged |
| Length | OK at ~3,900 words | Kept as drafted |

**What's NOT in scope:**

- Edits to `grader_voice_knowledge.md` — kept standalone per operator
  decision (avoid bloat)
- Companion JSON file — the knowledge file is markdown-only for v1.0;
  if downstream tools need structured access, that's a follow-up
- Sample-feedback corpus extracts in examples — synthetic per
  operator preference
- Automated WHAT-check validation tool — knowledge file is reference;
  the agent applies the 4-point check on each draft comment

**Cross-repo implication:** DS 250, DS 460, CE 162 (and any future
adopter) inherit the coaching file on next pull. The file is
particularly valuable for first-time instructors who don't yet have
a per-instructor voice file the existing edit roundtrip can refine
— Section 5's articulation interview produces a starter voice file in
~30 minutes.

**Pairs with the broader marketing positioning** (parking lot —
"AI-assisted grading where the instructor stays the author, not the
AI"). The voice-preservation contract in §1 is the architectural
proof that this positioning is real, not just rhetoric.

### Recent: first-class Canvas group-assignment workflow — issue #100 (v0.64.0, 2026-06-25)

**v0.64.0** — closes issue #100. First non-DS-250/DS-460 issue this
session — filed from **CE 162 Land Surveying (BYUI)**, a different
course/instructor adopting the toolkit. The course had a real
multi-tool workaround for Canvas group assignments (lab memos, one
per group, but Canvas creates per-member submission rows that
duplicate the content); they wanted first-class support upstream
rather than carrying the workaround forward per cohort.

**Three-phase implementation across three tools, plus knowledge:**

**Phase A — `grader_fetch.py`** detects group context, fetches groups
+ members, writes two new artifacts. New pure helpers:
`is_group_assignment(asg_meta)`, `grades_individually(asg_meta)`,
`build_group_map(groups, members_by_group)`,
`pick_group_representatives(group_map, submitter_uids)`,
`render_unique_group_memos_md(...)`,
`group_context_for_fetch_log(...)`. New Canvas API helpers:
`fetch_group_category_groups`, `fetch_group_members`. Wired into all
three sub-paths (discussion / quiz / default).

Artifacts (both FERPA-safe — user_ids + group_ids, no names):
- `<challenge-dir>/UNIQUE_GROUP_MEMOS.md` — human-readable per-group
  listing (representative submitter / mirrored members /
  non-submitters / groups without submissions). Agent reads this
  BEFORE grading.
- `.fetch_log.json` `"group_context"` block — JSON
  user_id → {group_id, group_name, member_user_ids} mapping.
  Consumed by reidentify + push.

**Phase B — `grader_reidentify.py`** mirrors the rep's score + reason
+ feedback file to mirrored group-member rows in `.review.csv`. New
pure helpers: `build_user_to_keys(keymap)`,
`pick_group_representatives_from_context(...)`,
`mirror_group_rows(...)`. New column on `.review.csv`:
`group_mirror_of` (empty for non-mirror rows; rep_key for mirrors).

**Phase C — `grader_push.py`** drops mirrored rows from the push plan
in shared-grade mode (Canvas distributes the rep's grade via
`comment[group_comment]=true`); preserves them in individual-grade
mode. Operator can override per-row by setting `final_grade` on a
mirrored row — kept as an explicit individual push. New pure
helpers: `is_group_mirror_row(row)`,
`filter_group_mirror_rows(rows, group_context)`.

**Phase D — knowledge**. New "Group assignments — grade one
representative per group" subsection in `grader_knowledge.md §10`.
Three-artifact table + two-mode behavior + agent Standard Work for
the group grading flow + operator override rule.

**`.gitignore`** adds `**/UNIQUE_GROUP_MEMOS.md` for consistency
with the other per-challenge artifacts.

**46 new tests** across three test files:
- `test_grader_fetch_helpers.py` +21 (group detection, group_map
  building, rep picking, MEMOS rendering, fetch_log context shape)
- `test_grader_reidentify_helpers.py` +15 (NEW FILE — `build_user_to_keys`,
  `pick_reps_from_context`, `mirror_group_rows` with mirror /
  override / multi-group / missing-rep-feedback edge cases)
- `test_grader_push_helpers.py` +10 (is_group_mirror_row +
  filter_group_mirror_rows behavior across shared / individual /
  operator-override modes)

Total tests 390 (up from 344).

**The lived failure the workaround surfaced (and why upstream
support matters).** Without group support, an instructor grading a
7-group × 3-members-each assignment had to either:
- (a) Hand-edit the CSV to dedupe rows + manually copy feedback
  files across mirrors (the CE 162 workaround), OR
- (b) Accept that the agent would re-grade 21 identical
  submissions independently and risk inconsistent grades/comments
  across members of the same group

Both are real cohort-level grading failures. The first-class
workflow eliminates both: agent grades the 7 representatives;
mirror logic propagates to the 14 group-mates; push collapses to
7 PUTs (each with `group_comment=true`) instead of 21.

**Cross-repo adoption signal.** CE 162 filed the issue with a
fully-worked local solution (their `UNIQUE_GROUP_MEMOS.md`
prototype) AND specific advice on which Canvas API endpoints to hit
+ which fields matter. That's mature adopter behavior — they're
running canvas-toolbox in production on Windows and shipping
contributions back. Worth surfacing for the LinkedIn marketing
story (parking-lot positioning section): "first non-DS-cohort
contribution arrived 2026-06-24."

### Recent: three paired "silent-success looks like success" gates — issues #99 / #101 / #102 (v0.63.0, 2026-06-25)

**v0.63.0** — closes three DS 250 issues filed yesterday afternoon /
this morning, all surfacing the same failure pattern: **the tool
reports a green signal that conceals a systematic error.** Different
seams, same lesson — make the tool fail loudly when the underlying
assumption is unsafe.

| Issue | Failure mode | Coded gate |
|---|---|---|
| **#99** | Operator blanks `final_grade` to hold a row; `recommended_score` fallback fires; sentinel `(held)` gets coerced by Canvas to incomplete/score=0 on pass_fail; a student's COMPLETE silently became FAIL | New pure helper `validate_grade_for_grading_type` refuses sentinels + invalid grades pre-PUT, surfaces clearly per row, counts in summary line |
| **#101** | Solution-derived rubric required an OPTIONAL chart; 3/3 grader passes unanimous (spread 0.00); 4 students wrongly marked incomplete; consensus output read as "high confidence" because spread stats measure inter-grader consistency, not rubric correctness | New pure helper `detect_calibration_anchor` + prominent UNCALIBRATED-COHORT warning that inverts the spread framing on uncalibrated runs; `--uncalibrated` flag for soft acknowledgment |
| **#102** | Rubric inherited a requirement from the answer key that the task page explicitly called OPTIONAL — same DS 250 U4T3 incident as #101, input side | New `assignment_spec.md` artifact written by `grader_fetch.py` capturing the Canvas description + the linked course-site task page text; agent reads it BEFORE grading; knowledge files codify "task page = source of truth, answer key = reference" |

**The cross-issue thread.** Yesterday's #95/#96/#97 sprint was
"documented-but-unenforced gates." Today's #99/#101/#102 sprint is the
companion thread:

> **"The gate's signal looks like success but is silently wrong."**

#99 — sentinel LOOKS pushed; coerced silently. #101 — consensus LOOKS
confident; rubric was wrong. #102 — Canvas description LOOKS like the
spec; it's just a pointer.

Together: 6 production safety gates shipped across 24 hours (v0.59.0
→ v0.63.0). All bug-intake-worker driven (issues #95-#98 + #99 + #101
+ #102). 100% lived-experience scope; zero speculative.

**Code shape:**

1. **[grader_push.py:181-264](lib/tools/grader_push.py#L181-L264)**:
   new `validate_grade_for_grading_type(grade, grading_type)` returning
   `'ok' / 'sentinel' / 'invalid' / 'not_graded' / 'unknown_type'`.
   Recognizes parenthesized sentinels (`(held)`, `(not graded)`,
   `(skip)`), bare keywords (`held`, `n/a`, `tbd`, `pending`), and
   validates against `grading_type` (`pass_fail`, `points`, `percent`,
   `gpa_scale`, `letter_grade`, `not_graded`).
2. **`fetch_assignment_lock_state` extended** to return `grading_type`
   from the same `/assignments/:aid` call (no extra API round-trip).
3. **[grader_consensus.py:81-130](lib/tools/grader_consensus.py#L81-L130)**:
   new `detect_calibration_anchor(challenge_dir, feedback_dir)`
   scanning for `ta_grades*.json/csv` + `_groundtruth.json/csv`.
   Warning header is prominent (78-char banner) on uncalibrated runs;
   consistency-stats footer adds the "consistency ≠ correctness" line
   on uncalibrated cohorts.
4. **[grader_fetch.py](lib/tools/grader_fetch.py)**: new
   `extract_task_page_url(canvas_description_html)` +
   `fetch_task_page_text(url)` + `render_assignment_spec(...)` +
   `write_assignment_spec_md(...)`. Wired into `main()` right after
   `fetch_assignment_metadata` — runs once per fetch, covers all three
   sub-paths (discussion / quiz / default).
5. **Knowledge file updates:**
   - [grader_knowledge.md §10](lib/agents/knowledge/grader_knowledge.md):
     new "Standard Work — task page = source of truth" subsection.
     Three-artifact discipline table (task page / answer key / rubric)
     + the OPTIONAL-by-default rule + the diagnostic for rubric
     requirements under review.
   - [grader_setup_knowledge.md §Step 2](lib/agents/knowledge/grader_setup_knowledge.md):
     new "Precondition for ALL three paths — task spec is source of
     truth" sub-section. Applies to rubric-construction in Path C +
     rubric-validation in Paths A and B.
6. **37 new tests** across `test_grader_push_helpers.py` (+15
   `validate_grade_for_grading_type` cases), new
   `test_grader_consensus_helpers.py` (9 `detect_calibration_anchor`
   cases), and `test_grader_fetch_helpers.py` (+13 `extract_task_page_url`
   + `render_assignment_spec` cases). Total tests now 338 (up from
   307).
7. **`.gitignore`** adds `**/assignment_spec.md` for consistency with
   the other per-challenge artifacts.

**What's NOT in scope** (deferred for follow-up if DS 250 surfaces
need): the automated rubric-vs-spec mismatch check. The spec capture
+ knowledge update is the actionable lever; the automated check is a
backstop that can land later if the human-readable spec doesn't
catch the same class of error.

**Cross-issue cumulative guarantee (now 6 gates strong):**

> The grade reaching Canvas is **consensus-backed** (#95), **never
> accidentally lower than what the student already had** (#96), **never
> pushed without explicit human review** (#97), **uses the
> de-identified comment thread for triage** (#98), **passes
> grading-type validation** (#99), **fails loudly on uncalibrated
> unanimity** (#101), and **is graded against the student-facing task
> spec, not the answer key** (#102).

### Recent: --skip-if-student-replied surfaces the de-id'd latest comment inline — issue #98 (v0.62.1, 2026-06-24)

**v0.62.1** — small DS 250 quality-of-life enhancement. Closes
issue #98. Filed from `ds250-onln-master/canvas-toolbox` (W08 Joins
push held 6 rows; all benign "I resubmitted" replies that required
a separate `grader_deidentify_comments.py` pass to confirm).

**The gap:** the `--skip-if-student-replied` skip-print used only
the key — operator had to run a second tool to read each held
thread and decide whether the student's reply was benign ("I fixed
it / re-uploaded") vs. an open question (still needs a response).
The deid'd latest comment was already in hand from the #62
collision-guard pipeline; the skip-print just discarded it.

**The fix (display-only, no behavior change):**

1. New pure helper **[`truncate_comment_preview(text, limit=240)`](lib/tools/grader_push.py)**
   — one-line preview with newline collapse + ellipsize past `limit`.
2. **`student_replied_keys: set` → `student_replied_latest: dict`**
   — same gate behavior, but the dict carries the deid'd latest
   comment alongside the key.
3. **Skip-print updated** to surface `[KEY] role=self <created_at>:
   "<scrubbed comment>"`. The comment text is already FERPA-scrubbed
   (issue #65 collision-guard deid pipeline produced it).
4. **6 new tests** in
   [test_grader_push_helpers.py](lib/tests/test_grader_push_helpers.py)
   — short text passthrough, newline collapse, CRLF normalization,
   truncation past limit, default-240-char limit, None/empty
   handling.

**FERPA note:** no new surface. The same `deidentify_submission_comments`
pipeline that produces the scrubbed text for the collision-guard
print produces it here. This change wires the in-hand data through
to the skip-print; it does NOT fetch or process anything new.

**Operator UX:** one-pass triage of held rows. Benign resubmission
replies vs. open questions become visible in the same output instead
of requiring a second tool invocation per push.

### Recent: --mark-reviewed --yes refused on LLM-comment path — issue #97 (v0.62.0, 2026-06-24)

**v0.62.0** — closes issue #97 ("enforce the human-in-the-middle
review gate before push"). Lived (DS 460): a grading agent ran
`grade` → `--mark-reviewed --yes` → `--push` in one motion under
"grade these late ones now" pressure. The grades were sound, but
the human-in-the-middle review of `_all_comments.md` never happened.
Instructor caught it after the push. The grades being correct
doesn't redeem the gate being skipped — the next batch might not be.

**Investigation finding:** the `.reviewed` marker requirement was
already in place ([grader_push.py:1192-1217](lib/tools/grader_push.py#L1192-L1217))
— `--push` refuses without it, auto-invalidates on review-surface
mtime changes. Fix 1 of the issue was a duplicate. The REAL gap
was the `--yes` shortcut: an agent could pass it with
`--mark-reviewed` to bypass the "Type 'reviewed' to confirm" prompt
and self-attest the review. That's the hole.

**The fix:**

1. **New pure helper `is_yes_refused_on_review(comment_files, yes_flag)`**
   in [grader_push.py:181-198](lib/tools/grader_push.py#L181-L198) —
   returns True when the caller should refuse. Path-aware: refuses
   only on the LLM-comment sub-path (where `prefix-*.md` files
   exist); allows on the value-only / human-graded path (human IS
   the grader; `--yes` there is a script convenience).
2. **Refusal wired into `--mark-reviewed`** with a clear error
   message: "An agent can pass --yes; a human must physically type
   'reviewed' to attest review of `_all_comments.md`."
3. **`--yes` help text updated** to mention the carve-out so
   `--help` discovery surfaces the rule.
4. **[grader_knowledge.md §10](lib/agents/knowledge/grader_knowledge.md)**
   — new Standard Work subsection codifying the agent-side rule:
   "grade X" produces the review artifact and STOPS; pushing is a
   SEPARATE explicitly human-approved step; the agent never chains
   grade→push under "do it now" pressure; the agent never passes
   `--yes` to `--mark-reviewed`. The tool refusal is the safety net;
   the agent's protocol-level rule is the first line of defense.
5. **4 new tests** in [test_grader_push_helpers.py](lib/tests/test_grader_push_helpers.py)
   covering the predicate (comment-files-present + --yes refused;
   value-only + --yes allowed; no --yes always allowed; refusal
   independent of file count).

**The cross-issue pattern (#95 / #96 / #97).** Three
documented-but-unenforced protocols each failed under operator-busy
pressure. v0.59.0–v0.62.0 converts each from prose policy into a
coded precondition:

| Issue | Failure mode | Coded gate |
|---|---|---|
| #95 | Single pass ships without consensus | `_consensus.csv` presence + freshness gate at `--mark-reviewed` |
| #96 | Re-grade silently lowers existing grade | Regression direction gate at PUT seam + upstream `_existing_grades.csv` |
| #97 | Agent self-attests review with `--yes` | `--yes` refused on LLM-comment review path |

Together the guarantee: the grade reaching Canvas is **consensus-backed,
never accidentally lower than what the student already had, and
never pushed without explicit human review.**

### Recent: grader_fetch surfaces existing Canvas grades for re-grade detection — issue #96 part 3 (v0.61.0, 2026-06-24)

**v0.61.0** — completes the upstream half of issue #96. The
downstream push-side regression gate (v0.60.0) is the SAFETY NET; this
release adds the UPSTREAM PREVENTATIVE so the agent recognizes a
re-grade BEFORE doing the work of grading cold.

**The artifact:** `<challenge-dir>/_existing_grades.csv` (gitignored,
FERPA-safe — opaque key only, no PII):

```csv
key,existing_grade,existing_score,workflow_state
KC1-A1B2C3,3.75,3.75,graded
KC1-D4E5F6,B+,87.0,graded
KC1-G7H8I9,complete,100.0,graded
```

- **Keyed by the same opaque SHA-256 key** the agent sees later via
  `key_for(filename, prefix)`. Imported from
  `grader_deidentify_databricks` to guarantee derivation parity.
- **Filtered to `workflow_state == "graded"`** — only existing prior
  grades surface (per operator preference; non-graded states absent
  until a use case demands otherwise).
- **Always written** — header-only file = fresh cohort with no prior
  grades. Presence of file = fetch completed.

**Two pure helpers** in [grader_fetch.py](lib/tools/grader_fetch.py):

- `existing_grades_rows(raw_dir, subs, prefix)` — walks raw_dir,
  joins each `<prefix>_<uid>.<ext>` filename to the matching
  submission by uid, filters to graded, derives keys via `key_for`.
- `write_existing_grades_csv(challenge_dir, rows)` — header-stable
  emit; overwrites on re-run so stale data can't mislead the agent.

**Wired into all three fetch paths** (discussion / quiz / default
attachment). The discussion path didn't previously call
`fetch_submissions`; one extra API call surfaces the grade + score +
state. Quiz + default paths reuse the `subs` already in scope.

**[grader_knowledge.md §10](lib/agents/knowledge/grader_knowledge.md)**
— new "Re-grade detection — consult `_existing_grades.csv` before
assigning a score" subsection. Codifies the Standard Work:

1. Look up the key in `_existing_grades.csv` before scoring.
2. If `existing_grade` non-empty → RE-GRADE. Apply re-grade rules:
   anchor to existing, surface explicitly in reason column, NEVER
   silently lower.
3. Consensus still runs; high spread on a re-grade lands in
   NEEDS-REVIEW.

The push-side regression gate from v0.60.0 remains the final safety
net (refuses to LOWER without `--allow-lower`), but the upstream
surface means the conflict, when it exists, is visible from the
first pass rather than emerging at push time.

**12 new tests** in [test_grader_fetch_helpers.py](lib/tests/test_grader_fetch_helpers.py)
covering filter-to-graded, key-derivation parity with `key_for`,
None handling, stale-prefix skipping, missing-submission skipping,
empty-dir behavior, multi-attachment suffix support, letter-grade +
pass-fail value preservation, header-only emit, full row emit,
overwrite semantics.

**Open next:** issue #97 (review-gate enforcement). Investigation
confirmed fix 1 of the issue is already in place
([grader_push.py:1171-1204](lib/tools/grader_push.py#L1171-L1204) —
the `.reviewed` marker is required for `--push` and auto-invalidates
on review-surface changes). The real gap is: `--mark-reviewed --yes`
on the LLM-comment sub-path bypasses the interactive "Type
'reviewed' to confirm" prompt. The fix is one conditional refusing
`--yes` on that sub-path + an agent-knowledge update saying "grade X"
stops at `_all_comments.md` and never auto-pushes. Scoped as v0.62.0.

### Recent: grader_push refuses to silently LOWER an existing grade — issue #96 (v0.60.0, 2026-06-24)

**v0.60.0** — closes issue #96 ("grader_push must never silently
lower an existing grade"). Lived (DS 460): an out-of-band Slack drop
was treated as an initial submission and graded fresh. Student was
already graded 3.75 in an earlier run; local `submissions_raw/` was
empty for that uid so the existing local-file re-submission check
passed. The fresh re-grade (3.5) was about to ship — caught only
because an ad-hoc print showed `before → after`. Silent grade
regression is the highest-stakes failure mode in grading.

**Three layers of fix in the push seam:**

1. **[grader_push.py](lib/tools/grader_push.py) `normalize_grade` +
   `regression_check`** — new pure helpers that classify a grade as
   `numeric` / `letter` / `pass_fail` / `empty` / `unknown` and
   direction-compare existing vs new. Letter scale is full F → A+
   (F, D-, D, D+, C-, C, C+, B-, B, B+, A-, A, A+) with rank ordering.
   Pass/fail is `incomplete` < `complete` (case-insensitive).
2. **Push loop gate** — fetches each submission's current Canvas
   grade and refuses to LOWER it without `--allow-lower`. Class
   mismatches (numeric vs letter, etc.) and unknown grade strings
   refuse the push and surface for manual review — a grade we can't
   classify is a grade we can't direction-check.
3. **Visibility by default** — every row prints `pushed KEY:
   before → after`; every push-log line records `grade <before> →
   <after> pushed to assignment <aid>`. The blind-write failure
   mode is gone.

**New flag `--allow-lower`** — explicit, logged opt-out (for
legitimate cases like an academic-integrity reversal). Follows the
existing `--allow-*` convention. The bypass is logged inline per row
so the audit trail shows the intentional regrade.

**fetch_submissions extended** — the lean default response now
includes `grade` (display string) + `score` (numeric) per row in
addition to `user_id` + `id`. Cost: same single API call that was
already made; no extra round-trips.

**17 new tests** in [test_grader_push_helpers.py](lib/tests/test_grader_push_helpers.py)
— 7 for `normalize_grade` (empty / numeric / letter / case-insensitive
/ pass-fail / unknown strings / full F→A+ ordering chain) + 10 for
`regression_check` (first-fill / numeric lower-is-regression / raise-or-equal /
letter regression / letter raise / pass-fail regression / pass-fail
raise / class mismatch / unknown-class halt / new-empty mismatch).

**[grader_knowledge.md §10](lib/agents/knowledge/grader_knowledge.md)** —
new mechanism item #10 documenting the regression gate + updated
"Out-of-band drops and re-submissions" subsection with the lived
DS 460 failure as the motivating example.

**Out of scope (filed as follow-up):** issue #96 part 3 — pre-grade
check via `grader_fetch` surfacing "this user already has a Canvas
grade" to the agent BEFORE grading. The push-side gate is the
safety net that prevents the harm reaching Canvas; the pre-grade
check is upstream preventative work. Recommend file as separate
issue when ready.

### Recent: 3-pass consensus is now enforced at the push seam — issue #95 (v0.59.0, 2026-06-24)

**v0.59.0** — closes issue #95 ("make 3-grader consensus the default
with a hard opt-out"). Lived (DS 460 Key-Challenge batch): a single
grader pass nearly shipped because the keyless agent collapsed to 1
pass under parallel-grading pressure. When the 3-pass consensus was
retroactively run, **6 of 15 scores moved + 7 of 15 flagged
NEEDS-REVIEW**. The documented 3-pass protocol was advisory, not
enforced — exactly the failure mode the "doc-only protocols fail
when the operator is busy" lesson predicts.

**Root cause + fix:** the seams enforcement was incomplete. The
existing safeguards are good — `grader_consensus.py` already defaults
to `--expected 3` and halts on too-few graders; `grader_grade.py`
already has the `--single`/`--bulk`/`.calibrated` triad — but
`grader_push.py` had no gate. A keyless agent could write
`_grader1.csv` + per-student feedback files directly and push without
ever invoking consensus.

**What changed:**

1. **[grader_push.py:181-203](lib/tools/grader_push.py#L181-L203)** —
   new pure helper `consensus_gate_status(fbdir)` returns `'ok'`,
   `'missing'`, or `'stale'` based on `_consensus.csv` presence +
   mtime vs. the newest `_grader*.csv`.
2. **[grader_push.py](lib/tools/grader_push.py) `--mark-reviewed` path** —
   for LLM-graded runs (path with `prefix-*.md` files present), the
   gate refuses to write `.reviewed` (and therefore `--push` refuses
   in turn) unless `_consensus.csv` exists AND is fresh. Clear error
   message points at `grader_consensus.py`. The value-only /
   human-graded sub-path is unaffected (no graders → no gate).
3. **New flag `--allow-single-pass`** — explicit, logged opt-out.
   Follows the existing `--allow-collisions` / `--allow-enrolled` /
   `--allow-locked-resubmit` convention. Logs a warning when used so
   the bypass is visible in the operator's terminal.
4. **[grader_knowledge.md §4](lib/agents/knowledge/grader_knowledge.md)** —
   new "Standard Work — the 3-pass default is enforced, not advisory"
   subsection. Codifies: produce 3 passes by default on the keyless
   agent path; OFFER the 3-pass run before any LLM-graded batch and
   get explicit operator decline before single-pass; the seam check
   is the safety net, not the only line of defense.
5. **7 new tests** in [test_grader_push_helpers.py](lib/tests/test_grader_push_helpers.py) —
   missing / stale / fresh / equal-mtime / newest-mtime-of-many /
   no-graders edge cases.

**What's NOT in scope:** existing safeguards (consensus.py's
`--expected 3` halt; grader_grade.py's `.calibrated` marker; the
mechanism doc itself) are already correct and untouched. Surgical
change at the one seam that actually leaked.

**Cross-repo implication:** DS 460 + DS 250 + any future grader-fork
inherits this gate automatically on their next pull. Operators who
were running single-pass intentionally (calibration cohorts) need
`--allow-single-pass` — but the `--mark-calibrated` upstream gate
should mean those flows don't hit `--mark-reviewed` to begin with.

### Recent: Cline added as Ollama alternative; Continue.dev still preferred (v0.58.2, 2026-06-23)

**v0.58.2** — small README polish following v0.58.1. Operator wants
Cline listed alongside Continue.dev as a viable Ollama extension
("preferred is Continue.dev"; operator will personally test both).

Two README edits:
  1. The Ollama row in Step 2's matrix now reads "Continue.dev
     (preferred) — or Cline as an alternative." Both Marketplace
     URLs surfaced + the Ollama link stays.
  2. The 🦙 caveat note now covers both — Continue.dev framed as the
     safer first pick (Apache 2.0; broader adoption; more stable
     backend abstraction); Cline framed as newer-but-capable for the
     same agentic workflow. Both are local-first; both are open-source.

**Why both rather than just one:** the operator plans to personally
test each before locking the long-term recommendation. Documenting
both NOW protects future-me from re-deriving why the alternative was
considered + lets adopters who already prefer Cline see it's a
documented path.

**No code changes.** README + AGENTS.md + version triple update only.

### Recent: Ollama + Continue.dev added to README Step 2 (v0.58.1, 2026-06-23)

**v0.58.1** — docs-only follow-up to v0.58.0. Operator flagged that the
README's "Pick your AI assistant" matrix only covered subscription-keyed
options (ChatGPT, Claude, Copilot) + the Antigravity / Gemini fallback.
Missing: local models for the FERPA-strict + cost-conscious adopter
cohort.

**Added a new row** to README Step 2 between Copilot and Antigravity:
  - **Local models (Ollama)** → **Continue.dev** (open-source, Apache 2.0,
    fully agentic VS Code extension)
  - No account; configure Ollama backend in Continue's settings
  - Links to both Continue Marketplace listing + ollama.com

**Added a 🦙 caveat note** explaining honestly:
  - What the path is (Continue.dev + Ollama, fully agentic — reads files,
    runs commands, edits code; same workflow as cloud extensions)
  - Why it's worth considering (local-first; nothing leaves the machine;
    FERPA-strict-friendly; no subscription cost)
  - The trade-off (today's local code models handle deterministic +
    structural work well but typically need extra calibration for nuanced
    prose grading vs Claude / GPT-4)
  - Concrete starting-point models (qwen2.5-coder, deepseek-coder-v2,
    codestral) without over-prescribing

**Why this matters strategically:** aligns with canvas-toolbox's standing
"brain-agnostic" philosophy + the deterministic-first grader principle
codified in v0.57.3. Local models excel at the deterministic-first
work (which is most of the grader pipeline) and only struggle with the
LLM-eval portion (the messy middle from grader_knowledge.md §16).
Adopters with FERPA constraints that prevent cloud LLM use now have
a documented path.

**No code changes; README-only patch.** All 261 tests still passing.
Triple-version-sync maintained (pyproject + plugin + marketplace all
0.58.0 → 0.58.1).

**Deeper integration deferred to a future trigger:** the `GraderLLM`
interface in `grader_grade.py` already abstracts the LLM provider
(today's only impl is `AnthropicGraderLLM`). An `OllamaGraderLLM`
subclass would plug in cleanly when an adopter actually uses the
keyholder path with local models. Not yet built; would land as a v0.X.Y
when an institutional signal arrives or the operator pulls it.

### Recent: `course_homepage_build.py` v0.1 — DesignPLUS-free course home page (v0.58.0, 2026-06-22)

**v0.58.0** — new tool surface. Triggered by: BYUI moving off DesignPLUS for
cost savings; operator was added to a REL 130 Missionary Prep course
(cid=415138) with a DesignPLUS-themed home page; flagged it as worth
absorbing into canvas-toolbox knowledge AS an HTML/CSS-native replacement.

**What v0.1 ships:**
- `lib/tools/course_homepage_build.py` (~430 lines) — reads `schedule.yml` +
  today's date, renders a static HTML home page with the CURRENT week
  pre-expanded as a `<details open>`, others collapsed. Three modes:
  `--bootstrap-from-canvas` (generates a starter schedule.yml from a
  course's modules), default render (write HTML to file), `--apply`
  (PUT to Canvas /front_page, honors canvas_course_guard).
- `lib/agents/templates/course_homepage/schedule.example.yml` — documented
  schedule schema with all fields commented.
- `lib/agents/knowledge/course_homepage_knowledge.md` (~250 lines) —
  design rationale, when to use, accessibility notes, FERPA assessment
  (clean by construction — modules + dates aren't student data),
  decision tree for when NOT to use this, integration with other tools,
  anti-patterns to refuse if instructors ask.
- `lib/tests/test_course_homepage_build.py` — 33 pure-logic tests
  covering date parsing, schedule validation, current-week selection,
  module-URL building, render output shape (incl. no-JS guarantee,
  no-external-stylesheet guarantee, current-week-marking).

**The model is pure-CSS + scheduled regenerate:**
- No JavaScript in the rendered page (Canvas-WYSIWYG-safe; no
  DesignPLUS account-level injection required)
- Pure-CSS techniques: anchor-jump nav links + native `<details>/<summary>`
  accordions + `<details open>` for the current week (baked in at build
  time based on today + schedule)
- Regenerate cadence: manual `--apply` Monday morning, OR local cron,
  OR GitHub Actions scheduled workflow — operator chooses; the tool
  doesn't dictate
- The schedule.yml lives in the consumer repo (per-course state);
  canvas-toolbox provides the template + rendering

**Live-tested READ-ONLY** against `CANVAS_SANDBOX_ID` (cid=145706):
- Bootstrap correctly pulled 14 modules
- Schedule validator correctly refused the `<EDIT:>` placeholder dates
- After hand-patching dates, render with `--date 2020-10-15` correctly
  marked Week 6 as current (`<details id="week-6" class="ct-week" open>`)
  and added `class="current"` to the Week 6 button
- All other weeks rendered as collapsed accordions

**NOT YET tested live:** the `--apply` push to Canvas. Parked for v0.2
along with the visual-polish work below.

**Visual polish — explicit v0.2 work** (parked in `handoffs/parkinglot.md`):
After visual review of the rendered output, operator feedback: "looks
horrible compared to where we got the HTML from." The functional core
works; the visual polish does not match DesignPLUS quality (no banner
exercised in the test course, plain CSS vs. DesignPLUS's mature theme,
emoji vs. Font Awesome icons). v0.2 will add:
  - `style.css_override` field in schedule.yml — institutions drop in
    their own CSS file; tool inlines it
  - Starter CSS themes directory (`lib/agents/templates/course_homepage/themes/`):
    BYUI-aligned + neutral + minimal
  - Sandbox push test against a different course ID (one with a banner
    + real modules + real dates) — operator to provide that ID tomorrow

**Triple-version sync** maintained (pyproject + .claude-plugin/plugin.json
+ .claude-plugin/marketplace.json all 0.57.3 → 0.58.0). New direct
dependency added to pyproject: `pyyaml>=6.0.3` (already a transitive
dep; now declared).

**Tests: 261 passing** (was 228 — added 33 for the new tool). 13 sprint
tests still deselected (Canvas-API gated). All four pre-commit hooks
pass. CI gate green.

### Recent: Deterministic-first grader design principle — v0.57.3 (2026-06-22)

**v0.57.3** — codifies a grader-design principle that emerged from a
"side thought" conversation about auto-grade-on-cycle: **bias toward
Python; reach for the LLM where contextual judgment or voice-anchored
prose is the better fit. It's a tuning preference, not a hard rule.**
Three artifacts updated:

1. **AGENTS.md → Working Style** — new project-specific rule
   ("Deterministic-first grader design") that lays out the preference
   + the messy-middle nuance + the migration pattern + a pointer at
   the deeper knowledge file.

2. **`lib/agents/knowledge/grader_knowledge.md`** — new §16
   ("Deterministic-first design principle") with: what canvas-toolbox
   already follows (the good pattern); a 6-row messy-middle examples
   table; the criteria-author decision dimensions (time, intent, cost,
   failure mode); the migration pattern; why the discipline matters.

3. **`handoffs/parkinglot.md`** — new v1.2 entry parked: "Auto-grade
   on cycle, deterministic-first." Captures the full design
   conversation (event/poll trigger, three-lane exit routing, rubric
   criterion-type schema with the new `hybrid` type, prerequisites
   incl. the DS 250 calibrate-against-historical share-back, the
   pedagogical-line decision shape (α auto-draft vs β auto-push).

**The operator caught two calibrations in real-time during this work:**
  - Original framing was too binary ("LLM has exactly two superpowers;
    everything else is engineering") → softened to acknowledge the
    messy middle.
  - The rubric criterion-type schema gained a 4th type (`hybrid`)
    for deterministic-prefilter + LLM-judgment-on-passes, matching
    real rubric needs.

**No code changes; no behavior changes.** Pure design-principle
codification. The existing tools that ALREADY follow deterministic-
first (`grader_signals`, `grader_reconcile`, `grader_competency_grade`,
`grader_submission_health`, `_quiz_kind`, `grader_consensus`) are
documented as the pattern to extend.

**Tests: 228 passing (unchanged).** All four pre-commit hooks pass.
Triple-version sync maintained.

### Recent: Placeholder-name discipline rule — v0.57.2 (2026-06-22)

**v0.57.2** — discipline-only follow-up immediately after the v0.57.1
FERPA fix. Operator caught the inconsistency: "we shipped a FERPA fix
using `'Sarah'` throughout as a placeholder, but the reporter had been
more careful using `<Name>` — did we ourselves follow FERPA discipline
in the artifacts?" Answer: not visibly enough.

**New Working Style rule:** placeholder names in code comments, commit
messages, and prose docs get the explicit `"Sarah" (fake name)`
annotation on first appearance per artifact; subsequent appearances
stay in quotes (`"Sarah"`). Test fixtures keep literal strings (the
tests assert literal shapes), but each test file's top docstring now
documents the convention so reviewers don't mistake the names for
real.

**Why not "scrub all common names"?** The reporter used `<Name>` — a
disambiguating-but-unreadable placeholder. The annotation pattern
(`"Sarah" (fake name)`) keeps the readability of "Alice/Bob"-style
examples AND **over-communicates** the discipline. Future code
reviewers see the discipline in the artifacts themselves rather than
having to know about it externally.

**Files updated:**
- `lib/tools/grader_deidentify_comments.py` — code comment block
  showing the precipitating failure case now reads
  `'Excellent work, "Sarah" (fake name)!'` with explicit annotation
  + a one-line lead-in pointing at Working Style.
- `lib/tests/test_grader_deidentify_comments.py` + `lib/tests/
  test_grader_name_leak_check.py` — top docstring documents the
  convention; test fixture strings unchanged (the tests assert
  against literal comment shapes).
- `AGENTS.md` § Working Style — new bullet codifying the rule + the
  2026-06-22 motivating case.

**Tests:** 228 passing (unchanged — pure docs/comment change). All
four pre-commit hooks pass. Triple-version-sync maintained.

**Honest note on the v0.57.1 commit message** (`1920a00`, on
`origin/main` since earlier today): it contains the older "Sarah"
references without the annotation. That commit message lives in git
history; rewriting it would require a force-push, which is
destructive and the risk doesn't warrant it ("Sarah" alone without
any linkage to a real student is not PII under FERPA — just a common
first name in a representative example). Forward-going artifacts
follow the new rule.

### Recent: FERPA fix — off-roster greeting names — closes #94 (2026-06-22)

**v0.57.1** — three-layer fix for the FERPA leak reported in #94. A real
incident: a TA comment `Excellent work, "Sarah" (fake name)!` where
"Sarah" was a dropped student NOT in the active roster. (Throughout
this entry "Sarah" is an obviously-fake placeholder — see Working
Style → placeholder-name discipline below.) The de-id pipeline left
"Sarah" intact AND the leak-check (using the same roster) reported
"0 hits / clean" — silent FERPA leak.

**Three layers, each independent:**

1. **Roster expansion (`grader_fetch.py:182-183`)** — enrollment_state[]
   now includes `inactive` + `completed` in addition to `active` +
   `invited`. Dropped students land in `.known_names.txt`; the canonical
   roster scrub catches them. Load-bearing fix; closes the originating
   gap.

2. **Greeting-position scrub (`grader_deidentify_comments.py`)** —
   safety net for off-roster names. New module-level
   `_GREETING_NAME_RE` matches `(case-insensitive greeting phrase)
   (separator)(Capitalized name)` and redacts the captured name. 11
   greeting phrases per the reporter's recommendation: Hi / Hey /
   Hello / Dear / Nice work / Great work / Excellent work / Good work
   / Good job / Well done / Nicely done. Runs AFTER the roster pass
   (roster catches known names more precisely; this is the fallback).
   Greeting is case-insensitive; name MUST be capitalized to avoid
   redacting every common word.

3. **Heuristic leak check (`grader_name_leak_check.py`)** — new
   `heuristic_greeting_hits()` helper + a second pass in `main()` that
   runs independent of the roster. If a capitalized name in greeting
   position survived ALL the scrubs, it's flagged with a distinct
   "HEURISTIC" category (vs the "ROSTER" hits). Different remediation
   per category: ROSTER miss → add to `.known_names.txt` + re-run
   deidentify; HEURISTIC miss → scrubber bug OR a name pattern not yet
   covered. Exit code 2 on either flag type (was 2 on roster only).

**Deliberate non-extraction:** the greeting regex is duplicated between
`grader_deidentify_comments.py` and `grader_name_leak_check.py`. Per
our 2nd-consumer rule (the Hermes "extract on 2nd occurrence" pattern
that triggered `_quiz_kind.py` in v0.52.0), we'd extract to a shared
helper when a 3rd consumer needs the same pattern (e.g. PDF or jupyter
scrubbers). Right now there are 2 consumers, both at the FERPA-critical
edge — duplication is cheaper than premature abstraction. Both files
carry sync notes.

**Tests:** 228 passing (was 214 — added 14). Eight new tests in
`test_grader_deidentify_comments.py` cover all 11 greeting phrases +
case sensitivity + accepted over-redaction trade. New
`test_grader_name_leak_check.py` (7 tests) covers the heuristic
helper, the headline regression case (off-roster name caught), empty/
None defenses, and the over-redaction trade documentation.

**Accepted trade (per reporter):** occasionally over-redacts a
capitalized non-name in greeting position ("Hi There," → "There"
redacted). A leaked name is the larger harm. Documented in code
comments + tests to prevent future drift.

**FERPA discipline signal:** this is the kind of fix that DOES belong
in production-grade scope, NOT minimum-scope. The proposal scope was
calibrated DOWN from the original 3-hour "extract shared helper" plan
to a 1-hour "ship the 3 layers directly" plan after operator pushback
(documented in handoffs/parkinglot.md → research-filter calibration).
The smaller fix matches the reported bug exactly; the shared helper
gets pulled when 3rd consumer arrives.

### Recent: Top-stars sweep ship-now batch — v0.57.0 (2026-06-18)

**v0.57.0** — the 4 SHIP-NOW items from the top-stars-sweep research
(handoffs/2026-06-18_top-gh-stars-research.md) + the SHIP-NOW item
from the headroom research (handoffs/2026-06-18_headroom-research.md).
Five OSS-readiness moves in one commit:

**1. `.github/ISSUE_TEMPLATE/` — YAML form templates** (matches
`astral-sh/uv/.github/ISSUE_TEMPLATE/` shape):
  - `bug.yml` — toolkit deviation; structured fields for tool name +
    version + OS + what-happened + repro; FERPA hygiene checkbox
  - `enhancement.yml` — feature request; use case + proposed behavior;
    explicit note: "already built? use share: instead"
  - `share.yml` — contribution flow; what-built + link-to-code +
    FERPA + two-zone-architecture checkboxes
  - `config.yml` — disables blank issues; routes 3 contact links:
    cb-report-bug (preferred), Discussions, Private Vulnerability Reporting

**2. `.github/PULL_REQUEST_TEMPLATE.md`** — short Summary / Test plan
template + pre-merge checklist (pre-commit pass / tests added /
AGENTS.md updated / triple-version sync / FERPA preserved). Matches
the `astral-sh/uv` + `astral-sh/ruff` PR template shape.

**3. GitHub Discussions enabled** — `gh api -X PATCH repos/chaz-clark/
canvas-toolbox -f has_discussions=true` returned `has_discussions:
True`. Pairs with the `cb-share` flow as a place to surface "share-back"
threads + open-ended design conversation. ISSUE_TEMPLATE's config.yml
points there for non-bug Q&A.

**4. `scripts/install.ps1` Windows installer** (~130 lines, PowerShell
shape matching `Aider-AI/aider/aider/website/install.ps1`). One-line
install for Windows: `irm https://raw.githubusercontent.com/chaz-clark/
canvas-toolbox/main/scripts/install.ps1 | iex`. Mirrors install.sh
exactly: detects OS, ensures git is on PATH, installs uv via Astral's
PS1 installer if missing, clones into ./canvas-toolbox, runs `cb-init
--yes`, branches on exit code for the "edit .env" vs "fully configured"
final message. Honors `$env:CANVAS_TOOLBOX_INSTALL_DRY_RUN` for tests.

**5. `/llms.txt` curated AI-agent doc index** — the `llmstxt.org`
convention; a Markdown file at repo root that gives AI agents a focused
index of the project's docs instead of crawling the whole tree.
Curated entries: README, AGENTS.md, CONTRIBUTING.md, CHANGELOG.md,
install scripts, 8 agent specs, the knowledge catalog, the tools
catalog, plugin manifests, working-style rules, share-back paths.
Pairs naturally with `AGENTS.md` (in-context agents working ON
the project) — `llms.txt` is for agents working WITH the project
(an adopter's IDE agent learning what canvas-toolbox does).

**Tests:** 214 passing (was 208 — added 6 for install.ps1 coverage:
exists, references uv installer, references cb_init, has dry-run
branch, idempotency guard present, recovery path mentions cb_init).
13 sprint tests still deselected. All four pre-commit hooks pass
(ruff, actionlint, shellcheck w/ bin/ scope).

**Yes-count delta:** canvas-toolbox went from 2/13 → 7/13 on the
comparison matrix (added issue templates, PR template, Discussions,
multi-platform installer, plus llms.txt which isn't a row but
counts toward AI-agent discoverability).

Park-pile from the same sweep (deferred):
  - MkDocs Material docs site
  - pluggy plugin/hook system
  - shell completion (`cb-init --completions bash`)
  - rooster-style sectioned CHANGELOG auto-generation
  - `examples/` directory expansion
  - direct `headroom` integration in grader_grade.py
  - documenting headroom as adjacent operator tool
Skip-pile: `.github/FUNDING.yml` (out of step with institutional footing).

### Recent: Share-back paths — bin/ wrappers + CONTRIBUTING.md + share: prefix (2026-06-18)

**v0.56.0** — broadens the share-back surface from "report a bug or
file an enhancement" to **three discoverable paths**, all surfaced in
the README + cb-init's step 8:

**1. `share:` title prefix added to cb_report_bug.py.**
The existing `bug:` / `enhancement:` prefixes are now joined by `share:`
for the case where an operator BUILT something locally and wants to
contribute it back — distinct from `enhancement:` (asked for, not yet
built). Maintainer triages these differently. Triggered by the
2026-06-18 observation that a beta tester's group-grading extension
work didn't come through the bug-intake worker — likely because the
existing "report a bug" framing didn't invite contribution.

**2. `bin/` wrappers** — three short-alias passthrough scripts:
  - `bin/cb-init` → `uv run python lib/tools/cb_init.py`
  - `bin/cb-report-bug` → `uv run python lib/tools/cb_report_bug.py`
  - `bin/cb-share` → same target as cb-report-bug (alias for the
    contribution use case; semantic name maps to the `share:` prefix)

  Each is a 3-line bash wrapper. shellcheck pre-commit hook scope
  widened to include `bin/cb-*` files. Adopters can put `<repo>/bin/`
  on PATH to invoke as `cb-init` / `cb-share` / etc. from anywhere.

**3. README "How can you share back?" section.** Restructured the
prior "Hit a bug? Hit a wish?" header into a 3-path table:
  - bug → `cb-report-bug` with `bug:` prefix
  - enhancement → `cb-report-bug` with `enhancement:` prefix
  - share (built it locally) → `cb-share` with `share:` prefix
  - PR (code push) → CONTRIBUTING.md
  Plus an explicit "How to put `bin/` on PATH" snippet for adopters
  who want short commands, plus three documented fallbacks (long-form,
  gh CLI, web UI) for users without the bin/ wrappers handy.

**4. NEW: CONTRIBUTING.md** (~130 lines). First-class contributor doc:
  - All three contribution shapes (bug-report, share-back, PR)
  - Pre-commit hook install instructions (mandatory for PRs)
  - Tests required before PR + what the maintainer reviews
  - Explicit "what the maintainer is NOT looking for" section
    (style-only PRs, tool renames, FERPA-removing optimizations,
    demographic integrations without institutional partnership)
  - Communication norm: design discussion via `cb-share` BEFORE
    long PRs; PRs stay focused on code, not design debate.

**5. cb-init step 8 wording updated.** The "Hit a bug?" hint now reads
as three lines — bug / enhancement / share — so adopters see the full
share-back surface on first install, not just the bug-reporting framing.

**Tests:** 208 passing (was 199 — added 9 across bin/ wrapper tests:
exists+executable, bash -n syntax parse, correct-target-file). 13
sprint tests still deselected. All four pre-commit hooks pass
(ruff, actionlint, shellcheck w/ bin/ scope, ruff again).

### Recent: README polish — surface easier-startup + new capabilities (2026-06-18)

**v0.55.1** — docs-only follow-up after Sprint 2B. Two changes:

**1. README "Getting started" — surface the one-liner as the lead.**
Sprint 2B's `scripts/install.sh` was shipped but the README still
opened Step 3 with "Most people use Option A" + a buried 💡 tip
pointing at the curl-pipe inside Option B. Restructured:
  - NEW: `### TL;DR — one-line install (macOS / Linux)` section
    immediately after the Step 3 header. Audience: technical users
    with `git` + a terminal habit.
  - REMOVED: the `💡` tip (now redundant)
  - REMOVED: the `#### Fastest path — one-line install` subsection
    inside Option B (now redundant with the TL;DR)
  - KEPT: Option A's agent-driven 8-step runbook (target audience
    is non-technical faculty whose AI assistant walks them through;
    Option A's checklist also covers git install + gitignore creation
    + course pull, three things `install.sh` doesn't do)
  - KEPT: Option B's `#### Fast path — cb-init (3 lines)` for users
    who want the manual equivalent of the one-liner across any OS

**2. README "What you can do" — added the New Quizzes response bullet.**
Sprint 2 (#87) shipped `grader_fetch_nq_responses` — a genuinely
new user-facing capability (per-student NQ response data via the
student-analysis Reporting API) — but the "What you can do" list
hadn't been updated to surface it. Added the bullet immediately
before the existing grading bullet so the NQ feature is visible
to adopters scanning the capability list. Also added a brief
"specs-grading reconciliation with @100%-credit counts" inline
mention to the existing grading bullet (#47 from Sprint 2).

No code changes. Triple-version-sync maintained (pyproject + plugin +
marketplace), 199 tests still green, all four pre-commit hooks pass.

### Recent: Sprint 2B — `scripts/install.sh` one-line installer (2026-06-18)

**v0.55.0** — the curl-pipe wrapper around Sprint 2's `cb-init`.
True one-line install for macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/chaz-clark/canvas-toolbox/main/scripts/install.sh | bash
```

`scripts/install.sh` (~140 lines) detects OS (bails on Windows with
a pointer to the manual 3-line flow), ensures `git` + installs `uv`
via Astral's official installer if missing, clones canvas-toolbox
into cwd, and runs `cb-init --yes`. `--yes` is the right default
because curl-pipe consumes stdin, so interactive prompts wouldn't
work anyway — and the whole point of the one-liner is non-interactive.
Refuses to clobber a pre-existing `canvas-toolbox/` directory; prints
a recovery hint at `cd canvas-toolbox && uv run python
lib/tools/cb_init.py` (the resume path).

**Test coverage** — Sprint 1's pattern continues:
  - 4 new pytest tests under `lib/tests/test_install_script.py`:
    file-exists-and-executable, `bash -n` syntax parse, dry-run
    end-to-end (via `CANVAS_TOOLBOX_INSTALL_DRY_RUN=1`), and the
    pre-existing-clone-dir refusal case
  - `shellcheck` added to `.pre-commit-config.yaml` (matching the
    ruff + actionlint pattern from v0.53.0) — catches the same
    class of bash bugs ruff catches for Python
  - **Manual end-to-end verified before commit**: ran `install.sh`
    in `/tmp/canvas-toolbox-real-test`, cloned from GitHub, ran
    cb-init through step 3 halt, confirmed the final "Next: edit
    .env" message. cwd-control behavior verified (.env landed at
    the test dir's canvas-toolbox/ subdir, not anywhere else).

**README** — replaced the 3-line "Fast path" with a tiered structure:
"Fastest path" = the curl-pipe one-liner (macOS/Linux); "Fast path"
= the 3-line manual flow (any OS, fully interactive). Windows users
explicitly directed to the 3-line flow.

**Adopter pitch is now genuinely one line**: paste the curl URL,
fill in `.env`, re-run cb-init. Total time from zero to working
canvas-toolbox install on a fresh machine: ~3 minutes (depending
on Python download speed).

Tests: 199 passing (was 195 — added 4). All three CI tiers + the
new shellcheck hook green.

### Recent: git-push discipline rule added — closes #88 (2026-06-18)

**v0.54.1** — adds a single bullet to Working Style §Project-specific
rules: "**`git push` after every commit** — in BOTH consumer repos
AND canvas-toolbox itself." Closes issue #88, filed via the bug-intake
worker on 2026-06-17 after the operator surfaced 23 local-only
commits in itm327-master from ~3 weeks of canvas-toolbox-prompted
work. The rule additionally bakes in 2026-06-18's maintainer-side
incident: 6 local-only commits in canvas-toolbox itself when an
adopter tried to clone from GitHub and found `cb_init.py` missing.
The rule explicitly applies to maintainers, not just adopters —
the same failure mode bites both. Doc-only change; no behavior shift.

### Recent: Productional Dependabot wave — merged #89/#90/#91/#92 (2026-06-18)

Four Dependabot PRs landed clean after a rebase against the conftest
fix: setup-python v5→v6 (dormant regression.yml only),
setup-uv v3→v7 + checkout v4→v7 (CI-validated), and the Python deps
group bump (anthropic 0.93→0.111, beautifulsoup4 4.14→4.15,
canvasapi 3.5→3.6, lxml 6.0→6.1.1, pdfplumber 0.11.4→0.11.10,
requests 2.33→2.34.2). Sanity-tested locally: `grader_grade.py
--help` works on anthropic 0.111 (the SDK import path is unchanged);
195/195 tier-1 tests still green; ruff clean. v0.53.0's Dependabot
config + pre-commit + ruff layers proved themselves on first
real run — the maintenance loop is wired and operational.

### Recent: Sprint 2 — `cb-init` one-command bootstrap (2026-06-18)

**v0.54.0** — new `lib/tools/cb_init.py` (~370 lines): the
one-command bootstrap that closes the "what do I do AFTER I clone?"
friction every adopter (and every fresh agent) hits. Inspired by
`roborev init` (research 2026-06-18); locked to the canvas-toolbox
trust + working-style discipline.

**8 idempotent steps**, each silent when there's nothing to do +
prompts y/n when there is (decision G — "smart prompts"):
  1. Install uv via Astral's official installer if missing (macOS/Linux)
  2. Install Python 3.14 via uv (won't touch system Python)
  3. Write `.env` stub at cwd if absent — STOPS for manual fill-in
     of CANVAS_API_TOKEN + CANVAS_BASE_URL (decision: stays manual)
  4. `uv sync --group dev` from REPO_ROOT
  5. `uv run playwright install chromium` (skippable via --skip-playwright)
  6. `uv run pre-commit install` (ruff + actionlint hook)
  7. Canvas API smoke — `GET /users/self` (read-only; reports the
     authenticated user's name)
  8. Surface AGENTS.md + cb-report-bug one-liner

**Key design calls captured during the planning conversation:**
  - **`.env` stays manual** — no $EDITOR invocation; stub goes to cwd
    + halts so the operator fills in tokens, then re-runs cb-init
  - **uv-managed everything** — tool installs uv + Python itself, so
    non-technical faculty don't need to know what Python is, AND
    technical users get a contained env that doesn't pollute their
    global Python
  - **No `gh` requirement** — confirmed: canvas-toolbox doesn't need
    `gh` at runtime; bug-intake goes through the Cloudflare worker
  - **Mode: explicit `--mode {maintainer,adopter}` flag, default
    adopter** (decision A) — auto-detection from git origin surfaces
    a suggestion but doesn't override; flag is the explicit toggle
    for future co-maintainers
  - **stub_is_filled requires only TOKEN + BASE_URL** — caught
    during live testing: maintainer's working .env doesn't have
    CANVAS_COURSE_ID (most tools accept --course-id per-command).
    COURSE_ID + SANDBOX_ID stay in the stub commented out as
    OPTIONAL.
  - **Tests: pure-logic + ONE tmp-repo integration** (decision E
    a+c) — 20 tests under lib/tests/test_cb_init.py covering
    detect_mode_from_remote (6), env_stub_content (1),
    stub_is_filled (8), parse_canvas_self_name (4), plus the
    end-to-end --check dry-run integration test
  - **install.sh curl-pipe wrapper parked as Sprint 2B** (decision F)
    — let cb-init prove itself in real use before adding the
    one-line install layer on top

**Updates to README.md Getting Started:**
  - Hint at the top of Step 3 pointing technical users at the
    cb-init fast path
  - New "Fast path — `cb-init`" subsection inside Option B (manual
    setup) with the 3-line clone + cd + cb-init flow + the flag
    table (--check, --yes, --mode, --skip-playwright)

**Version sync:** pyproject.toml + .claude-plugin/plugin.json +
.claude-plugin/marketplace.json all bumped 0.53.0 → 0.54.0
(maintain this triple-sync convention from the v0.53.0 plugin shipped
last commit).

**Tests:** 195 passing (was 175 after Sprint 1 — added 20). 13 sprint
tests still deselected (Canvas-API gated). All three CI tiers green.

### Recent: Productional sprint — Claude plugin + ruff + pre-commit + actionlint + Dependabot (2026-06-18)

**v0.53.0** — three productional-alignment moves inspired by the
`kenn-io/roborev` research (1.4k ⭐ Go project — "continuous code
review for AI agents"). Each is a small layer; together they shift
canvas-toolbox from "clone, read, configure" toward "plug in, hooks
auto-run, deps auto-update."

**Move 1 — Claude Code plugin manifest.** New `.claude-plugin/`
directory (matches roborev's shape exactly): `plugin.json` +
`marketplace.json` + a companion `README.md`. The plugin points
at `./lib/agents/` — adopters who have Claude Code can install the
toolkit's agent specs + 20+ pedagogical knowledge files as a single
plugin rather than cloning the full repo. The brain-agnostic
philosophy in `lib/agents/*.md` means the same skill catalogue
works for Codex / Cursor / Aider etc. when their plugin specs
stabilize (placeholder `.codex-plugin/` not added yet — wait for
Codex's spec).

**Move 2 — ruff + pre-commit + actionlint.** Three monitoring
layers in one commit, scoped conservatively:
- **ruff** added to `[dependency-groups].dev`. Initial ruleset enforces
  bug-catching families (F + B + E + W + I) and explicitly DEFERS
  stylistic rules (F541 f-string-no-placeholder; I001 import-order;
  E70x multi-stmt-per-line; B007 unused-loop-var; B905 zip-strict;
  E741 ambiguous-name) to a future style-sweep PR. The narrow ruleset
  catches REAL defects without forcing 60+ tool reformats.
- **First lint pass caught a real bug**: F821 in `course_mirror.py`
  line 568 referenced an undefined `master_slug`. Tier 0 wouldn't
  catch it (function not exercised by `--help`); Tier 1 had no test
  for that function. Ruff caught it on first run. Fix: compute
  `master_slug = _slug(master_title)` in the loop body where it's
  used. Cleaned 5 dead-variable assignments (F841) across canvas_sync,
  course_mirror, grader_grade, grading_load_audit, rubric_recommender
  + 12 unused imports (F401) auto-fixed across the codebase.
- **`.pre-commit-config.yaml`** runs `ruff check --fix` + actionlint
  on every commit. `pre-commit` added to dev deps. **`ruff format`
  intentionally NOT in pre-commit** — would have reformatted 84
  existing files on first run; deferred to a dedicated style-sweep
  PR so the working-style discipline ("Surgical Changes") holds.
- **CI Tier 2** appended to `.github/workflows/ci.yml`: `ruff check`
  runs after the Tier 1 pytest, plus an `actionlint` action lints the
  workflow files themselves (catches a class of CI bugs that would
  otherwise surface as opaque "workflow failed to start").

**Move 3 — Dependabot.** New `.github/dependabot.yml` configures
weekly automated dependency PRs for two ecosystems: Python (via uv,
reads pyproject.toml + uv.lock) and GitHub Actions (versions pinned
in our workflow files). Minor + patch updates grouped to reduce PR
volume; majors stay separate for case-by-case review.

**No behavior change to existing tools.** Tests: 175 passing, 13
sprint tests still deselected (Canvas-API gated). All three CI
tiers green locally.

**Source research:** `kenn-io/roborev` — see the Tier-2-followup
session notes (2026-06-18) for the full lesson set. roborev does
more (goreleaser binary releases, multi-agent ACP, `prek.toml`
versus traditional pre-commit, version-pinned linter as
single-source-of-truth, per-checkout cache, `install_scripts_test.go`)
— most of those are deferred until they're needed.

### Recent: Tier 2 — NQ + specs-grading sprint, closes #47 #86 #87 (2026-06-18)

**v0.52.0** — three consumer-demand issues closed in one focused
sprint, no behavior change to existing flows.

**#47 — `grader_reconcile` per-dimension `at_full_ratio`.** Adds an
optional dimension field (`at_full_ratio: 1.0` for strict full credit,
`0.9` for "90%+", or the issue's `count_mode: full_credit` alias)
that emits a NEW `<dim>_at_full` column counting submissions where
`score >= points_possible * ratio`. Closes the DS250 mid-letter
Spring 2026 false-flag where `submitted=3` but `@100%=2` was promoting
A- students to A. Independent of `completion_basis` (#59) — set on
any dimension where you need at-full visibility alongside
`<dim>_complete`. Two new helpers in grader_reconcile.py
(`_is_at_full_ratio` + `_resolve_at_full_ratio` for the dual config
syntax) with 15 new unit tests.

**#87 — `grader_fetch_nq_responses`.** Ports the validated
itm327-master `grade_standups.py` Reporting API pattern into a
canvas-toolbox primitive (~400 lines). POST report → poll progress →
download CSV → parse to uid-keyed dict. Default-on local CSV cache
(23h TTL, under Canvas's ~24h inst-fs URL expiry) with `--no-cache`
and `--force-refresh` opt-outs. Inline filename-date extractor
(`--extract-filename-dates`) with the 4 known screenshot patterns
(Mac default, Windows default, generic ISO, Snipping Tool).
FERPA-safe by default: uid-keyed output, names OMITTED unless
`--include-names` is passed for review-surface generation. 15 new
unit tests covering parse_filename_date, parse_canvas_ts, and
parse_student_analysis_csv against a synthetic CSV fixture modeled
on the real Canvas shape. The fetch primitive doesn't decide grades
— consuming tools apply bucket logic.

**#86 — NQ detection helper + knowledge note.** New shared module
`_quiz_kind.py` (~140 lines) with a pure classifier
(`classify_assignment_shape(assn_payload) -> (kind, path)`) plus a
network-touching wrapper (`detect_quiz_kind`). Classifies an
assignment as `new_quiz` / `classic_quiz` / `not_a_quiz` and
recommends one of three paths (`reporting_api` /
`submission_data` / `submitted_proxy` / `none`). Strongest signal
wins: explicit `quiz_id` → classic; `submission_types: [online_quiz]`
→ classic; `submission_types: [external_tool]` + NQ URL marker
(`quiz-lti` / `quiz_lti` / `quizzes.next`) → new_quiz; otherwise
not-a-quiz. The matching `learned/` knowledge note
(`2026-06-18_new-quizzes-responses-api-walled.md`) captures the
empirical endpoint table + the three viable data paths so the next
consumer doesn't re-spend the ~2 hours m119/ds460/itm327 each spent
discovering this. 11 new unit tests covering all classifier branches.

Total: 33 new unit tests (175 passing total, 13 sprint tests still
deselected). Tier 0 `--help` smoke green on both new tools.
`pending_review_finalizer.py` (sidecar suggested in #86) parked as a
separate follow-up — has its own design surface (gating, bulk vs
single, interaction with `grader_push.py`).

### Recent: CI tests Tier 0 + Tier 1 — closes #83 (2026-06-17)

**v0.51.0** — the toolkit's first automated test layer. New
`.github/workflows/ci.yml` runs on every push + PR. Three checks:
**Tier 0a** compiles every Python file in `lib/tools/` (catches the
#74 class — syntax errors, broken imports, type-annotation drift);
**Tier 0b** runs `--help` against every primary CLI tool — exactly
the cheap one-minute check that would have caught #74 before push;
**Tier 1** runs `pytest lib/tests/ -k "not sprint"` (the
sandbox-API sprint tests stay dormant pending a credentials policy
call). Seven new test files (~50 functions) cover the pure-logic
helpers flagged in #83: `extract_uid` / `_uid_from_filename` /
`_row_uid` (filename → uid resolution), `extract_hold_token` /
`comment_has_resubmit_language` / `collision_warnings_for_submission`
(grader_push #62/#63/#72), `_is_complete_under_basis` (grader_reconcile
#59), `evaluate_tier_thresholds` / `assign_band` (grader_competency_grade
#60), `classify_submission` (grader_submission_health #64),
`infer_surface` / `infer_task_slug` (grader_scaffold #54-A),
`scrub_comment` (grader_deidentify_comments #65). 127/127 pass
locally + 13 sprint tests deselected (kept for the regression.yml
path when activated). pytest added to `[dependency-groups].dev` in
pyproject.toml; install with `uv sync --group dev`. **Tier 0
caught a real bug on first run** — `module_structure_diff.py` had
no argparse, so `--help` failed env-check before showing usage; fixed
in this cycle by adding a minimal `argparse.ArgumentParser` with
`--version` to match every other tool's convention.

### Recent: grader sprint + bug-intake worker (2026-06-14 → 2026-06-15)

The grader pipeline jumped from **v0.35.4 → v0.50.x** across one intense
day of issue-driven work (issues #54-#74 closed; m119 + ds460 consumer
repos as the testing surface). New tools shipped: `grader_config_audit`
(#58), `grader_deidentify_comments` (#65, FERPA), `grader_list_assignments`
(#55), `grader_pull_ta_grades` (#56), `grader_submission_health` (#64),
`grader_competency_grade` (#60), `grader_push_comments` (#57),
`grader_scaffold` (#54-A), `grader_join` (#54-B), `grader_meta_summary`
(#54-C). Existing tools hardened: `grader_push` got default-exclude of
Test Student + inactive (#61), pre-push comment-collision guard (#62),
availability-aware comments + first-class `--retract` (#63), and the
HOLD_<DIM> grade-hold pattern (#72). `grader_reconcile` got
`completion_basis` per dimension (#59). All 6 deid adapters got
re-run prefix duality guards (#54-D).

### Recent: bug-intake worker (2026-06-15)

The v1.0 readiness gate. `lib/tools/cb_report_bug.py` + the Cloudflare
Worker at `infra/bug-intake-worker/` give faculty a one-command path
to file bugs / enhancements with no GitHub account, no `gh` CLI, no
browser auth, no PAT on their side. The maintainer's PAT lives in
Cloudflare's encrypted secret store; rotation is ~5 min/quarter.
Faculty-side: `uv run python lib/tools/cb_report_bug.py`. The
`agent-submitted` label is applied by a GitHub Action (`.github/workflows/agent-submitted-label.yml`)
that detects the worker's body footer — keeps the PAT scope at minimum
(Issues:RW only). See `infra/bug-intake-worker/README.md` for the
operations runbook and `MAINTENANCE.local.md` (gitignored) for the
maintainer's instance-specific details + PAT rotation schedule.

### Older: knowledge-base QC audit (2026-05-26) — done, came back clean

- **Knowledge-base QC audit (2026-05-26) — done, came back clean.** Audited all 17 `knowledge/*.md`+`.json` pairs against the `make_agent_knowledge` KNW-QC standard + distilled-vs-pasted + bloat + cross-file redundancy. **Result: the two-layer architecture holds — no file is raw paste**; distillation discipline is real and consistent (the two largest, `assessments` 4.3k words and `rubrics` 4.3k words, are the most carefully structured, with explicit verbatim-vs-gloss labeling). Universal `read_at_runtime` is a documented `selective_load` choice, not a defect. **5 small fixes applied:** `syllabus_knowledge.json` brought onto the house schema (facts object → `facts[]` array per KNW-QC-003; provenance → `{sources:[]}`; added `runtime_strategy`); MD header spines completed on `designer_thinking` / `cognitive_load_theory` / `toyota_gap_analysis`; `three_domains` dangling `blooms_taxonomy_knowledge.md` refs resolved (point to `taxonomy_explorer` + `outcomes_quality` until the dedicated file exists). **Residual forward item:** `blooms_taxonomy_knowledge.md` is referenced as "forthcoming" by `three_domains` but not yet built — verb lists currently live in `taxonomy_explorer_knowledge.md` + `outcomes_quality_knowledge.md`; create the dedicated file only if a tool needs a single Bloom verb-reference home.

**Versioning:** the `v0.x` semver line is canonical (matches `git describe` and `lib/tools/__toolbox_version__.py`). A separate `v1.x` git tag series exists in history; it is not part of the `v0.x` line and is not maintained — treat `v0.x` as canonical going forward. Downstream repos that vendor `lib/tools/` check drift with any primary sync tool's `--version` flag and re-sync via `cd canvas_toolbox && git pull` (never patch vendored copies in place).

- **Post-Stage-6 backlog (deferred limitations of the in-flight rubrics workstream — none block Stage 6 wiring; all are worth visiting after first real-course run reveals what actually matters)**:
  - **Knowledge-file content gaps.** (a) Backbone meta-rubric PDF lacks citation metadata in [`pre_knowledge/rubrics/rubrics of rubrics.pdf`](lib/agents/pre_knowledge/rubrics/rubrics%20of%20rubrics.pdf) — author/origin unrecorded. (b) Walvoord-Auburn 404 — Walvoord-BU on disk covers similar PTA ground; pursue an alternate (Bean / UT Austin / KU CTE) only if Stage 6 shows it matters. (c) `learningandteaching.byui.edu` is sign-in-gated (Crowded platform) — likely a major resource for ALL pre_knowledge frameworks; harvest manually while logged in and drop into `pre_knowledge/<topic>/`. (d) `canvas.instructure.com/doc/api/` was 503 through 2026-05-20/21 authoring — every Canvas-authored fact in `canvas_api_knowledge` is currently GitHub-YARD-sourced; re-fetch and promote `📄 documented` → `✅ verified` when reachable. (e) 9 of 11 resource pointers in `canvas_api_knowledge` lack per-resource surveys (only Pages + Rubrics done); write on-demand as new tools touch each resource.
  - **Stage 4 (`rubric_coverage_audit.py`) heuristic edges.** (a) `use_rubric_for_grading` is `❓ inferred` to be in the `include[]=rubric_settings` response — current tool treats missing-field as `None` (not flagged), which may underflag decorative rubrics; first real-course run will reveal whether to fall back to `/rubric_associations/:id`. (b) `submission_types == ['external_tool']` assumed to be NewQuiz/LTI — could be a regular LTI tool; refine via `external_tool_tag_attributes` if false-positives appear. (c) `non_submittable` may include legitimately graded items (e.g., participation graded via `['none']`); monitor and add a points-possible + submission-presence check if needed.
  - **Stage 5 (`rubric_quality_audit.py`) heuristic calibration** — partly validated against the sandbox fixture matrix 2026-05-22 (`sandbox_rubric_fixtures.py` in `CANVAS_SANDBOX_ID`). ~~**Highest priority deferred item**: Criterion 1 "unverified → flagged" misbehavior~~ **DONE 2026-05-21** — Criterion 1 three-state; `None` (no CLOs) → `criterion_unverified`, not a flag, no `validity_flag`; new `meets_criteria_unverified` verdict. ~~Criterion 3 binary test fires on every rubric lacking process-vocabulary~~ **DONE 2026-05-22** — sandbox showed C3 flagged ALL fixtures incl. the well-formed one (near-useless always-on signal); retightened to flag only when positive output-only evidence exists with no process counterbalance (the `weak` fixture still correctly flags; the well-formed/single-point/decorative fixtures no longer do). **`criterion_use_range` round-trip CONFIRMED 2026-05-22** — the range-based fixture's `points_and_weights` flag fired, proving the field comes back via `include[]=rubric` and C4 detects it (resolves the prior `❓ inferred`). **New sandbox finding: Canvas coerces an omitted/null `points_possible` to `0.0` via REST** (PUT `''` and `'null'` both yield `0.0`) — a true `points_possible=None` cannot be created through the API; it only arises via UI/import/blueprint paths (how ITM327's contract-graded course got them). The `None→missing_rubric` classifier fix stays unit-test-validated. Lower priority calibration items (still deferred — confirm before tuning): Criterion 1 token-overlap can fire spuriously on common words (tune stopword list / threshold post-run); Criterion 2 subjective-term regex is English-only and finite (extend after first run) AND **over-fires on bare hedge words** — sandbox 2026-05-22: "**Mostly** description" tripped the bare `mostly` term (a legitimate descriptor, not subjective); tighten `mostly`/`somewhat`/`partially` to require a following evaluative word, or drop the bare hedges (the explicit terms good/fair/poor/`minor errors` carry the real signal — confirm before changing); Criterion 3 binary test ("0 process AND ≥1 output → fail") may mis-classify legitimately-mixed rubrics; Criterion 4 `criterion_use_range` field unverified to be in `include[]=rubric` (`--probe` mode would dump one rubric's raw structure pre-run); Criterion 4 accountability detection depends on description keyword overlap; typology classifier never returns `developmental` (no heuristic); three-column single-point heuristic looks for specific labels that real Gonzalez-2017 rubrics may not use; verdict threshold (3+ flags → `needs_revision`) is arbitrary.
  - **Tool ergonomics.** (a) No unified report combining Stage 4 + Stage 5 — thin orchestrator `rubric_audit.py` would emit a combined markdown + JSON (~50 lines). (b) No assignment-description-vs-rubric gap surface in Stage 5 detailed mode — data is already fetched. (c) No persistent state / week-over-week diff (skip unless workflow demands it). (d) No mock-Canvas for end-to-end testing — unit tests cover classifier/detectors; skip integration fixtures unless flakiness warrants.
  - **Architectural watch items.** (a) The 17-row nav index in [External System Lessons](#external-system-lessons) duplicates the TOC of [`canvas_api_lessons_learned.md`](lib/agents/knowledge/canvas_api_lessons_learned.md) — drift risk; update both on every lesson edit, consider scripted sync if drift becomes a problem. (b) The strict two-file read obligation (`canvas_api_knowledge` + `canvas_api_lessons_learned`) is by design but creates workflow burden — monitor whether consuming agents actually read both. (c) CLO alignment heuristic in Stage 5 partially duplicates `course_quality_check.py --alignment` — extract into shared `lib/tools/clo_alignment.py` if Stage 5 evolves OR consolidate when one gains a feature the other should have. (d) Three v0.x knowledge files now stacked — at Stage 6, promote selectively to v1.0 based on what the real run actually exercised; leave others at v0.x with a dated reason. (e) L14 (lock-state-only sync reversion) is a single observation (incident W01, 2026-05-20) — if observed again, upgrade `blueprint_orphan_pages.py` operator warning from "advisory" to "blocker."
  - **Stage 6 prerequisites (not deferred — these are the entry path):** (1) Run `rubric_coverage_audit.py --json --report coverage.md` against a real Canvas course. (2) Run `rubric_quality_audit.py --json --report quality.md --detailed` against same. (3) Capture findings; calibrate Stage 5 heuristics only if signal-to-noise suggests it. (4) Wire exercised knowledge files into [`canvas_course_expert.json`](lib/agents/canvas_course_expert.json) `cross_references.knowledge_files[]`. (5) Promote exercised knowledge files to v1.0; bump `__toolbox_version__` to v0.21.0; add catalog entries to [`lib/agents/knowledge/README.md`](lib/agents/knowledge/README.md). (6) Tag and ship.

- **v0.27.0 just shipped** — **#36 `blueprint_presync_check.py`** (read-only PRE-sync lock-readiness preflight), the complement to `blueprint_exception_report.py` (post-sync). Predicts which pending blueprint changes will be **silently skipped** (unlocked + locally edited in a section) BEFORE a sync, and `--suggest-locks` emits the lock script to fix it first — collapsing edit→sync→discover→lock→resync into edit→preflight→sync-once. **Design grounded in a live empirical check** (relayed via the ITM327 agent on the #36 thread): `unsynced_changes` carries no `exceptions` pre-sync, so the tool infers local edits itself — **precise for pages** (reuses the #32 revision-provenance primitive: section hash ∉ blueprint revisions = local edit) and **honestly "can't pre-verify" for assignments/quizzes/discussions** (no `/revisions` trail; never false-confident — sets up a v2 snapshot baseline). Reuses #28's asset_type→restrict_item map. Validated read-only on ITM327 (415130): correctly flags S2's locally-edited `course-homepage`, passes "behind" pages. Benefits every online course (all get a blueprint). Closes #36.
- **v0.26.0 just shipped** — **PTC deep-dive new topics** (full-book read for genuinely-new topics, not gap-filling). Surfaced 3 course-auditable topics with public sources; built all 3, wired 2: **(#1 wired) `workload_audit.py` + `workload_calibration_knowledge.md`** — aggregate workload *distribution* audit (Carnegie credit-hour norm + due-date clustering; honest that reading *hours* aren't measurable from the API). Validated read-only (ITM327 uneven; sandbox/ds250 balanced). **(#2 wired) `structured_teaching_knowledge.md`** — reasoning enrichment (Sathy & Hogan "structure as an equity lever" + Walton & Cohen belonging); no tool, layered over existing structural findings; non-demographic. **(#3 ORPHANED) `content_representation_audit.py` + `content_representation_knowledge.md`** — surfaces named sources cited in course content for *human* representation review (does NOT infer demographics; evidence-based). Built + smoke-tested but **deliberately orphaned** (consumed only by its own tool; NOT wired to the agent, `course_audit`, or the user README) pending a real use case + an explicit appropriateness decision. #1/#2 wired into `canvas_course_expert` cross_references + `knowledge/README.md`; #1 also in the user README + tool catalog. All public-sourced — never the internal PTC manuscript.
- **v0.25.0 just shipped** — **`course_audit.py`** (read-only orchestrator: the capstone that composes all four audit legs into one health report — `HEALTHY`/`REVIEW`/`NEEDS_ATTENTION` + aggregated fixes), built as a tool-side application of the `make_orchestrator_agent` skill (specialists are sealed `--json` subprocesses, decoupled + referenced by path; `canvas_course_expert` is the agent-layer orchestrator). Validated on sandbox + real ITM327. **Plus the non-issue backlog batch:** (a) **PTC gap-audit** (pulled from the garage) — deep-read Preface/Ch3/Ch8 of the Eaton PTC text vs the pedagogy knowledge base; **confirmed the base is sound**, applied 3 small citable enrichments (expert-blind-spot + the Deslauriers 2019 "feeling of learning" gap → `cognitive_load_theory_knowledge`; group-work quality sub-check → `hattie_3phase_knowledge`); findings in gitignored `pre_knowledge/PTC/ptc_gap_audit_findings.md`. (b) **`syllabus_knowledge` promoted v0.1 → v1.0** (validated read-only on real ITM327 + the shared outcomes parser across m119/ds250/ds460). (c) **`rubric_recommender` Bloom verbs migrated** to the shared `bloom_verbs.py` (DRY). (d) "Beyond Doom and Gloom" AI post intentionally skipped (cluster complete).
- **v0.24.0 just shipped** — **`clo_quality_audit.py`** (3rd leg of the audit suite) + the **#30/#31/#32 agile fixes from real-course (ITM327/DS250/m119) testing**. (a) **#32** `blueprint_orphan_pages` Detector B: was mislabeling every drifted page a "reversion" (revisions LIST omits `body`; no lock gate) → now fetches per-revision bodies + gates on content-lock; **validated 0 false positives on the real ITM327 blueprint** (was 5). (b) **#30/#31** new shared `syllabus_outcomes.py` DOM-aware CLO parser fixes the broken syllabus-outcome extraction (was capturing the stem + a deadline line, missing all real CLOs) and consolidates the 3 outcome paths; `rubric_recommender` now hard-gates on CLO discovery (`--allow-generic` overrides). (c) **`clo_quality_audit.py`** scores discovered CLOs against the AoL rubric, conservatively calibrated against real data (only `not_measurable`/`double_barreled` are hard flags; relevance/recency are human review). New shared `bloom_verbs.py` (resolves the blooms_taxonomy residual). **All read-only audits validated across 5 real courses with no false positives** (read-only against real course IDs — no sandbox import needed). **Test matrix discovered:** m119 `409936`, ds460 `407908`, ds250 `415194`/`415196` (+BP `415094`), itm327 `402262` (+BP `415130`, S1 `415320`, S2 `415322`). **Closes #30, #31, #32.** #33 (blueprint_exception_report labeling) deferred to a cleanup batch.
- **v0.23.0 just shipped** — **`syllabus_audit.py`** (read-only syllabus completeness audit), the first tool from the BYUI Learning & Teaching harvest. Audits a course's `syllabus_body` against the **9 required sections** of the BYU-Idaho syllabus template + a first-class **AI-policy REQUIRED gate** (BYUI now mandates a generative-AI statement per `byui.edu/ai`; Stoplight / AI-Assessment-Scale framework detection is advisory). Same evidence-based stance as the rubric tools: verdict driven only by deterministic section + AI-policy detection; bloat / outcomes-stated / Learning-Model signals are advisory data, not verdict-drivers; keyword "not detected" = review, not proven-absent. **Sandbox-first validated** (16/16 logic checks + live `CANVAS_SANDBOX_ID` run: 5/9 on a real syllabus, exit codes + `--json` confirmed). Grounded in the gitignored `pre_knowledge/byui_learning_teaching/byui_syllabus_guidance.md` + `byui_ai_hub.md`. **Harvest provenance:** Tier A+B BYUI portal harvest complete (syllabus template, APA Top-20, AI cluster of 5 posts → `byui_ai_agency.md`, the public `byui.edu/ai` hub → `byui_ai_hub.md`, EdTech-2026 → L8 New-Quizzes prevalence note now Instructure-wide). PTC text (Eaton Vol 1) indexed + deep-read deferred (internal-use-only, gitignored). **Open follow-ups:** (a) no tracked `knowledge/syllabus_knowledge.md` yet — the checklist lives in the tool; an institution-neutral distillation could be promoted later; (b) `clo_quality_audit.py` still wants the gated AoL CLO rubric. **Note:** `v0.22.0` (rubric_recommender, Stage 7) shipped without a prose entry here — this is its catch-up.
- **v0.21.0 just shipped** — **Rubrics workstream + Canvas-API knowledge architecture**, validated against real Canvas (ITM327 production + `CANVAS_SANDBOX_ID` ground-truth fixtures). **`rubrics_knowledge.md/.json` promoted to v1.0** — 4-criterion backbone meta-rubric (Criteria Alignment=validity / Rating Levels=reliability / Process-Oriented / Points & Weights), 4 typologies with exemption rules, AAC&U VALUE + Walvoord PTA + BYUI anchors; **Criterion 1 (alignment=validity) is evidence-based — data + human-review signal, not a verdict-driver** (lexical matching can't make a validity judgment). Catalogued in `knowledge/README.md`; wired into `canvas_course_expert.json`. **Two audit tools (sandbox-validated):** [`rubric_coverage_audit.py`](lib/tools/rubric_coverage_audit.py) (Stage 4 — coverage classifier: `has_rubric`/`decorative_rubric`/`missing_rubric`/`lti_external_tool`/`non_submittable`/`non_gradable`) and [`rubric_quality_audit.py`](lib/tools/rubric_quality_audit.py) (Stage 5 — backbone scoring; verdict from C2/C3/C4 + `validity_review` + `alignment` recommendations). Both `--json`-capable. **New write tool** [`sandbox_rubric_fixtures.py`](lib/tools/sandbox_rubric_fixtures.py) (seeds the validation fixture matrix; proved the rubric CREATE flow). **New project rule:** sandbox-first testing (Working Style). **Two knowledge files still v0.x** (partially exercised — keep until more surface validated): [`canvas_api_knowledge.md/.json`](lib/agents/knowledge/canvas_api_knowledge.md) v0.1 (Canvas-docs-only surface) and [`canvas_api_lessons_learned.md/.json`](lib/agents/knowledge/canvas_api_lessons_learned.md) v0.1 (16-lesson empirical companion; the `CANVAS_BASE_URL`-scheme footgun ITM327 hit was fixed across 6 tools this cycle). Post-Stage-6 backlog (deferred calibration, C1 semantic limits, recommender tool) is in the Active Context backlog bullet above. **Next:** rubric recommender (generative — propose CLO-aligned, Bloom-targeted rubrics for assignments lacking them; hybrid scaffold-now/agent-enrich-later).

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
- **Make-AI-Agents clone** at `Make-AI-Agents/` is gitignored. Populate locally with the `git clone` command in Existing Tooling when needed.
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

Canvas API has multiple non-obvious behaviors the toolkit discovered through production use. The full catalog of 17 lessons (each with behavior, why-it-matters, defense, and provenance) has been migrated to the dedicated knowledge file [`lib/agents/knowledge/canvas_api_lessons_learned.md`](lib/agents/knowledge/canvas_api_lessons_learned.md) (2026-05-21). It pairs with [`lib/agents/knowledge/canvas_api_knowledge.md`](lib/agents/knowledge/canvas_api_knowledge.md), which holds the Canvas-documented surface (strict source discipline: only Instructure-authored docs in that file; only empirical findings in the lessons file).

Always read both knowledge files when planning a Canvas write or audit. The 17 lessons are abbreviated here as a navigation index — full content + defense citations live in the knowledge file:

| # | Lesson (one-liner) | Defending tool |
|---|---|---|
| L1 | Module prerequisites silently fail with JSON payload (use form-encoded) | `module_settings_sync.py` |
| L2 | Module published state is form-encoded too | `module_settings_sync.py`, `blueprint_sync.py` |
| L3 | Date writes need the `due_at`/`lock_at`/`unlock_at` trio | `canvas_semester_setup.md` agent |
| L4 | `late_policy` PATCH returns 403 for teacher tokens (admin-only) | `canvas_new_course_setup.md` agent |
| L5 | Classic quiz `points_possible` shows 0 after question push | `canvas_quiz_questions.py` |
| L6 | Classic quizzes have two IDs (`quiz_id` + `assignment_id`) | `course_quality_check.py` |
| L7 | Discussions use `todo_date`, not `due_at` | `canvas_sync.py` |
| L8 | NewQuiz / ExternalTool items can't be content-pushed via REST | sync tools (warn-and-skip) |
| L9 | Workaround: `GET /assignments?include[]=rubric` for student tokens | `course_quality_check.py` |
| L10 | Empty modules are a sync artifact (cascade of L8) | `course_quality_check.py` |
| L11 | Blueprint migration reports `state: completed` with silent per-section skips | `blueprint_exception_report.py` (#28) |
| L12 | A stale `.env` can silently target the wrong course (ITM-327 amplification) | `canvas_course_guard.py` (#27) |
| L13 | Canvas creates `-N` slug orphan Pages on Blueprint resync | `blueprint_orphan_pages.py` Detector A (#29 Phase 1) |
| L14 | Canvas's lock-state-only sync can silently revert section page bodies | `blueprint_orphan_pages.py` Detector B (#29 Phase 1) + operator warning |
| L15 | Page title collision → auto-suffix (`-2`/`-4`/`-5`) | `canvas_pages.upsert_page()` (#26) |
| L16 | Clearing a module-item completion requirement needs the whole object blanked | `module_settings_sync.py` (#25) |
| L17 | Blueprint `asset_type` vocab differs by endpoint (snake_case `unsynced_changes` vs CamelCase migration-details) | `blueprint_presync_check.py` (#36/#37) + `blueprint_exception_report.py` (#28) |

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
| `lib/tools/blueprint_presync_check.py` | **PRE-sync** lock-readiness preflight (#36, **read-only**) — the complement to `blueprint_exception_report.py` (post-sync). Reads `unsynced_changes` (pending items + `locked`, no exceptions pre-sync) and predicts which will be **silently skipped**: for **pages**, precise via the #32 revision-provenance primitive (section body hash ∉ blueprint revisions → local edit → will skip; ∈ → merely behind → will sync); for **assignments/quizzes/discussions** (no `/revisions` trail) reported honestly as "can't pre-verify" with safe options, never false-confident. Only evaluates `locked == false` content changes (locked = force-overwrite). `--suggest-locks` emits the restrict_item lock script (reuses #28's map) to lock at-risk items BEFORE the first sync — collapsing edit→sync→discover→lock→resync into edit→preflight→sync-once. `--bp <id>` / `BLUEPRINT_COURSE_ID`; `--json`/`--report`. Verdict `presync` ∈ {ready / at_risk / review / nothing_pending}. **Validated read-only on ITM327 (415130)**: page provenance correctly flags S2's locally-edited `course-homepage`, passes "behind" pages. | BEFORE a Canvas Blueprint sync — lock at-risk items first; pairs with `blueprint_exception_report.py` (post-sync) |
| `lib/tools/blueprint_orphan_pages.py` | Post-sync Page-level integrity audit (#29 Phase 1, **read-only**). Detector A: 5-point fingerprint for Canvas's `-N` slug orphan pattern. Detector B: silent body reversion — section page body has no provenance in blueprint's revision history (the strongest signal; plain drift is left to `validate_blueprint_sync.py`). Prints an **operator warning** when Detector B fires: don't run a lock-state-only Blueprint UI sync. `--report` writes markdown. Cleanup (`--apply`) is deferred to Phase 2. | After every Canvas Blueprint UI sync — pairs with `validate_blueprint_sync.py` (state-diff) and `blueprint_exception_report.py` (sync-log) |
| `lib/tools/canvas_quiz_questions.py` | Classic quiz question manager (push, list, clear) | Editing quiz questions outside Canvas UI |
| `lib/tools/module_settings_sync.py` | Module-settings reconciliation (prereq chain, "complete all" mode, per-item completion requirements). `--plan` default / `--apply` confirmation-gated + self-verifying. Course-agnostic: `--target` (default `MASTER_COURSE_ID`), `--module-prefix` (default `sprint-`), `--rename-match` (self-assessment rename-discovery, OFF unless given). Two policies: `chain-complete` (default — per the Completion-requirements rule above) and `graded-work-only` (opt-in deviation, needs `BLUEPRINT_COURSE_ID`). Reproduce original ITM-327 behavior: `--policy graded-work-only --rename-match "performance review"`. | Reconciling module gating on any course (#25) |
| `lib/tools/module_structure_diff.py` | **Read-only** diff of module prerequisites + completion requirements between Blueprint and master (GET only, never writes). General-purpose: no course-ID or module-name hardcoding; title-slug matching (Rule 2); enforces no policy. | Inspecting blueprint↔master module-structure drift before any mirror/reconcile step |
| `lib/tools/rubric_coverage_audit.py` | **Read-only** rubric coverage audit per assignment: classifies as `has_rubric` / `decorative_rubric` (rubric attached but `use_rubric_for_grading=false`, [L9](lib/agents/knowledge/canvas_api_lessons_learned.md)) / `missing_rubric` (the gap — includes assignments with `points_possible=None`, which are real gaps, not non-gradable) / `lti_external_tool` (`submission_types=['external_tool']` — NewQuiz or any other LTI tool, indistinguishable via the API; [L8](lib/agents/knowledge/canvas_api_lessons_learned.md)) / `non_submittable` / `non_gradable` (explicit 0 points only). `--target <env_var>` (default `CANVAS_COURSE_ID`) or `--course-id <id>` (literal). `--detailed` (per-assignment with module location). `--report PATH` writes markdown. Exits non-zero on `missing_rubric` or `decorative_rubric` findings. Advisory safety guard. **Sandbox-validated 2026-05-22** (CANVAS_SANDBOX_ID fixtures: 9/9 buckets correct) + run against ITM327 production (48 assignments). Stage 4 of the rubrics workstream. | Pre-semester rubric coverage check; pairs with [`rubrics_knowledge.md`](lib/agents/knowledge/rubrics_knowledge.md) |
| `lib/tools/rubric_quality_audit.py` | **Read-only** per-rubric backbone meta-rubric scoring per [`rubrics_knowledge.md`](lib/agents/knowledge/rubrics_knowledge.md). Verdict (`rubric_quality` ∈ {meets_criteria / meets_criteria_unverified / partial / needs_revision / absent}) is driven by the machine-checkable criteria **C2 Rating Levels** (subjective-language scan), **C3 Process-Oriented** (output-only-evidence scan), **C4 Points & Weights** (`criterion_use_range` API signal + accountability-weighting check) → `rubric_criteria_flags`. **Criterion 1 (Criteria Alignment = validity) is evidence-based and does NOT drive the verdict** — it is paramount but a human judgment; the tool surfaces an `alignment` object (status + per-criterion CLO-overlap data + actionable recommendations) and a `validity_review` signal for human verification (uses the real `outcome_group_links` endpoint + stemming). Honors single-point (C2) and developmental (C3) exemption rules. `--json` for machine output. All flags reviewable (heuristic). Same `--target`/`--course-id`/`--detailed`/`--report PATH`/`--allow-enrolled` shape as `rubric_coverage_audit.py`. Exits non-zero on partial/needs_revision. **Sandbox-validated 2026-05-22** (CANVAS_SANDBOX_ID fixtures: all verdicts correct; `criterion_use_range` round-trip confirmed; distribution 14/14/3 meets/partial/needs). Stage 5 of the rubrics workstream. | After `rubric_coverage_audit.py` to triage rubric quality; pairs with [`rubrics_knowledge.md`](lib/agents/knowledge/rubrics_knowledge.md) and [`outcomes_quality_knowledge.md`](lib/agents/knowledge/outcomes_quality_knowledge.md) |
| `lib/tools/sandbox_rubric_fixtures.py` | **Write tool (sandbox only).** Seeds a known rubric fixture matrix (9 fixtures covering every Stage 4 bucket + Stage 5 verdict) into a sandbox course for ground-truth validation of the rubric audit tools. `--plan` default / `--apply` / `--teardown`; guard-checked; idempotent by `FIXTURE:` title prefix; `--course-id` (default `CANVAS_SANDBOX_ID`). Proves the rubric CREATE flow works (assignment + nested-criteria rubric + association). | Re-validating the rubric audits after any change (the sandbox-first rule in action) |
| `lib/tools/syllabus_audit.py` | **Read-only** syllabus completeness audit. Fetches `GET /courses/:id?include[]=syllabus_body`, strips HTML to text, and keyword-detects the **9 required sections** of the BYU-Idaho syllabus template (Instructor Contact / Overview / Requirements / Structure[BYUI] / Expectations / Grading / Students-with-Disabilities / University-Policies / Disclaimers) plus a first-class **AI-policy REQUIRED gate** (BYUI now mandates a generative-AI statement — `byui.edu/ai`; framework detection for Stoplight + AI-Assessment-Scale is advisory). Verdict (`complete` / `incomplete` / `no_syllabus`) is driven only by the deterministic section + AI-policy checks; **advisory signals** (word-count/bloat, outcomes-stated, Learning-Model-introduced) are reported as data and do NOT affect the verdict. Detection is keyword-heuristic → "not detected" means *review*, not proven-absent (evidence-based stance). `--target <env_var>` (default `CANVAS_COURSE_ID`; repo `.env` ships `CANVAS_SANDBOX_ID`) or `--course-id <id>`; `--detailed`/`--report PATH`/`--json`/`--allow-enrolled`. Exits 0 complete / 1 incomplete / 2 no-body-or-config. Advisory safety guard. **Sandbox-validated 2026-05-22** (16/16 logic checks; live run vs `CANVAS_SANDBOX_ID` → 5/9 sections on a real 293-word body; exit codes + JSON confirmed). Grounded in `pre_knowledge/byui_learning_teaching/byui_syllabus_guidance.md` + `byui_ai_hub.md` (both gitignored). | Pre-semester syllabus completeness check; pairs with the BYUI syllabus template guidance |
| `lib/tools/course_audit.py` | **Read-only orchestrator** — one-command course health audit. Composes the four read-only audits (rubric coverage + rubric quality + syllabus + CLO quality) into a single report: a rolled-up verdict (`HEALTHY` / `REVIEW` / `NEEDS_ATTENTION`) + one aggregated "top things to fix" list. **Tool-side application of the `make_orchestrator_agent` skill**: each audit is invoked as a sealed `--json` subprocess (specialists decoupled + referenced by path, never reimplemented; each stays usable standalone) and their verdicts are composed visibly. The agent-layer orchestrator is `canvas_course_expert`. `--target`/`--course-id`/`--detailed`/`--report`/`--json`/`--allow-enrolled` (forwarded). Exits 0 healthy / 1 findings / 2 no-specialist-ran. **Validated 2026-05-26** on sandbox + real ITM327 (402262). | The single pre-semester course health check; the capstone over the four audit legs |
| `lib/tools/workload_audit.py` | **Read-only** aggregate student-workload **distribution** audit (PTC deep-dive new topic #1). Buckets gradable assignments by due-date week and flags clustering/crunch weeks (the reliable signal: a week ≥2× the term average), front/back-loading, and unscheduled work; `--credits` adds a rough volume sanity note. **Honest scope** (per `workload_calibration_knowledge.md`): distribution is computed confidently from due dates; reading *hours* are NOT measured (readings are links/files), so volume is a sanity note, not an hour budget. Verdict `workload` ∈ {balanced / uneven / sparse / unscheduled}. `--target`/`--course-id`/`--credits`/`--detailed`/`--report`/`--json`. Exits 0 balanced / 1 review / 2 no-assignments. **Validated 2026-05-26** read-only (ITM327 uneven; sandbox/ds250 balanced). | Pre-semester crunch-week / over-assignment check; pairs with `cognitive_load_theory` (per-task load) |
| `lib/tools/clo_quality_audit.py` | **Read-only** CLO quality audit — the third leg of the audit suite. Discovers course outcomes via the shared path (Canvas Outcomes API first, then the DOM-aware syllabus parser) and scores each against the **AoL CLO rubric** (`outcomes_quality_knowledge.md`). Evidence-based, conservatively calibrated: the only hard per-CLO flags are **`not_measurable`** (explicit non-observable primary verb — understand/know/appreciate; a verb merely absent from the finite Bloom list is NOT flagged) and **`double_barreled`** (a conjunction directly joining two distinct-level goal verbs, with means/relative-clause + verb-as-noun guards). Course-level **`scope`** (3–8) + **`rigor`** (Bloom spread) signals; **vague_language** advisory; relevance/recency left to human review. Tag `clo_quality` ∈ {meets_criteria / partial / needs_revision / unverified} (+ `clo_criteria_flags`); `unverified` = no CLOs discovered. `--target`/`--course-id`/`--detailed`/`--report`/`--json`. Exits 0 meets / 1 partial-or-needs / 2 unverified-or-config. **Validated 2026-05-26**: 6/6 calibration unit tests + 5 real courses read-only (ITM327 9 CLOs→scope-only, m119 partial[genuine "Appreciate"], ds250/sandbox meets — no false positives after calibration). | Before the rubric audits (a rubric aligned to a broken outcome is meaningless); pairs with [`outcomes_quality_knowledge.md`](lib/agents/knowledge/outcomes_quality_knowledge.md) |
| `lib/tools/syllabus_outcomes.py` | **Shared module (not a CLI).** DOM-aware parser for a syllabus's Learning Outcomes section: `detect_outcomes_section()` + `extract_outcomes()`. Locates the section by heading/stem, returns the `<li>` items (verb-first paragraph fallback), treats the stem as a delimiter. Consolidates the three outcome paths (#31) and fixes the extraction bug (#30). Used by `syllabus_audit`, `rubric_quality_audit.fetch_course_outcomes`, `rubric_recommender`. | — |
| `lib/tools/bloom_verbs.py` | **Shared module (not a CLI).** Single home for Bloom's revised verb→level data + non-observable flag list + `detect_bloom()`/`all_bloom_levels()`/`leading_nonobservable()`. Grounds the measurable/rigor checks in `clo_quality_audit`. (`rubric_recommender` still has an older inline copy — queued migration.) | — |
| `lib/tools/rubric_recommender.py` | **Generative (Stage 7, write-capable).** For assignments lacking a rubric (`missing_rubric`), recommends a rubric **scaffold** whose criteria are derived from the course's matched CLOs (alignment built in by construction) with 4 observable levels templated from each outcome's verb, pitched at the assignment's detected **Bloom's level**; flags assignment-vs-CLO Bloom mismatches and (when no CLO matches by wording) emits a generic scaffold + an explicit alignment-gap note. Hybrid: deterministic scaffold now, `canvas_course_expert` agent-enrichment later. `--plan` default / `--apply` (writes via the rubric CREATE flow, guard-checked) / `--assignment-id` (one) / `--json` / `--report` / `--detailed`. **Sandbox-validated 2026-05-22** (CANVAS_SANDBOX_ID: `--plan` 36 CLO-matched / 13 generic of 49; `--apply` write path created+verified+cleaned). Sandbox-first before any real-course `--apply`. | Recommending rubrics for no-rubric assignments after `rubric_coverage_audit.py` finds them; pairs with [`rubrics_knowledge.md`](lib/agents/knowledge/rubrics_knowledge.md) + [`outcomes_quality_knowledge.md`](lib/agents/knowledge/outcomes_quality_knowledge.md) |
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

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

---

## ⚠️ AI Agent FERPA Discipline

**If you are an AI agent working in this repo or a course repo using this toolkit**, the following files are **FERPA Zone 2** and you **MUST NEVER READ THEM**:

- `grading/.deid_master.csv` — **user_id to name map** (most common violation)
- `grading/.known_names.txt` — full course roster (names)
- `grading/*/.keymap.json` — de-id key to filename+user_id map
- `grading/**/.fetch_log.json` — fetch keymap with names
- `grading/*/.review.csv` — re-identified grading results
- `grading/*/feedback/_grader*.csv` — grading sheets with names
- `grading/**/submissions_raw/**` — raw submissions with potential name leaks

**Tool discipline — never read or display these files:**

Trust the tool's summary output. Never use Read, cat, head, tail, grep, or any other file-reading command on these files. They must NEVER enter LLM context, logs, or any cloud surface. For file verification, use only `wc -l` or `ls -la`.

**Bash command discipline for .deid_master.csv:**

```bash
# ✅ SAFE: Check file exists (no output displayed)
ls grading/.deid_master.csv >/dev/null 2>&1 && echo "✓ Found"

# ✅ SAFE: Count entries (no PII displayed)
wc -l grading/.deid_master.csv

# ✅ SAFE: Verify specific deid code exists (only show deid_code + user_id columns)
grep "DS-95DBB6" grading/.deid_master.csv | cut -d',' -f1,2
# Output: DS-95DBB6,173819 (no name)

# ❌ VIOLATION: These commands display the sortable_name column (FERPA Zone 2)
head grading/.deid_master.csv
cat grading/.deid_master.csv
tail grading/.deid_master.csv
grep "pattern" grading/.deid_master.csv  # without cut to filter columns
```

**The sortable_name column is FERPA Zone 2.** All bash commands on `.deid_master.csv` must either:
- Redirect output to /dev/null (no display), OR
- Use `cut -d',' -f1,2` to show ONLY deid_code + user_id columns

When testing or verifying, use `wc -l` or existence checks. Never display file contents.

**Why you don't need Zone 2 files:**

Accommodation tools (`student_late_accommodation.py`, `student_quiz_time_extension.py`, `apply_sas_accommodations.py`) accept `--user-id` and `--deid-code` directly. The **human instructor** looks up the identifier locally in `.deid_master.csv` and hands you ONLY the opaque code or numeric user_id. You use it as-is; **no re-identification needed**.

**Output discipline:**

- ✅ CORRECT: "Reopened for user_id 280379"
- ✅ CORRECT: "Applied 1.5x time extension for deid_code S-95DBB6"
- ❌ VIOLATION: "Reopened for Sam Bradshaw (280379)"
- ❌ VIOLATION: Reading `.deid_master.csv` to "look up" the user

**If the instructor asks "who is user_id 280379?"** — respond: "I don't have access to the name mapping file (FERPA Zone 2). Please check `grading/.deid_master.csv` locally."

**Incident history:**

- 2026-07-01: AI agent read `.deid_master.csv` during accommodation workflow, surfaced student name in response. Initial FERPA section added.
- 2026-07-02: AI agent ran `build_deid_master.py` successfully (FERPA-clean output), then displayed `head -5 grading/.deid_master.csv` showing real student names. Enhanced with explicit file patterns and tool discipline (issue #131).

---

## Common Tasks Quick Reference

**When the instructor asks you to:**

| Request | Command |
|---------|---------|
| "Sync students" / "Pull student list" / "Update enrollment" / "Sync all students" / "Update the deid master" / "Rebuild the student list" | `uv run python lib/tools/build_deid_master.py --force` |
| "Pull the course from Canvas" / "Sync course content" | `uv run python lib/tools/canvas_sync.py --pull` |
| "Audit the course" / "Check course quality" / "Run a health check" | `uv run python lib/tools/course_audit.py --course-id <id>` |
| "Grade this assignment" / "Grade KC1" / "Start grading" / "Fetch submissions for grading" | `uv run python lib/tools/grader_fetch.py --challenge-dir grading/<name>` then 3-pass consensus grading |
| "Push grades to Canvas" / "Upload grades" / "Post the grades" | `uv run python lib/tools/grader_push.py --challenge-dir grading/<name> --mark-reviewed` |
| "Run a UW check" / "Last participation report" / "Check who's still active" / "Find students who stopped participating" / "Title IV report" | `uv run python lib/tools/course_engagement_audit.py --uf-date YYYY-MM-DD` |
| "Give student X extra time on quizzes" / "Apply 1.5x time for student X" / "Give double time on all quizzes" / "Apply quiz time extension" | `uv run python lib/tools/student_quiz_time_extension.py --deid-code <code> --multiplier 1.5 --all-timed --apply` |
| "Let student X submit late" / "Give late-work grace" / "Reopen assignments for student X" / "Drop the deadline for student X" | `uv run python lib/tools/student_late_accommodation.py --deid-code <code> --from-days-ago 14 --apply` |
| "Apply SAS accommodations" / "Run the accommodation dispatcher" / "Process accommodation letters" | `uv run python lib/tools/apply_sas_accommodations.py --apply` |
| "Student still can't submit" / "Override isn't working" / "Fix assignment access for student X" / "Force Canvas to recalculate" | `uv run python lib/tools/fix_group_override_recalc.py --course-id <id> --student-id <id>` |
| "Push changes to Canvas" | `uv run python lib/tools/canvas_sync.py --push` |

**Note:** `build_deid_master.py` creates `grading/.deid_master.csv` from current Canvas enrollment. It's the source of truth for student de-identification codes used by accommodation tools.

---

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

**Consumer usage (v1.6+)**: clone `canvas_toolbox` into your course folder (`git clone https://github.com/chaz-clark/canvas_toolbox.git canvas_toolbox`), then run `uv run python canvas_toolbox/lib/tools/cb_init.py` which auto-creates course files (.env, .gitignore, AGENTS.md) at course root. Tools run from course root: `uv run python canvas_toolbox/lib/tools/<script>`. Update safely: `cd canvas_toolbox && git pull origin main` — only toolkit code updates; your course files are untouched.

v1.6 architecture moves all course files to course root (DS460/), not inside canvas_toolbox/. The toolkit is gitignored; course context lives in course-root AGENTS.md. Migration from v1.5: cb-init detects old .env location and offers to migrate.

For full setup and command reference, see [`README.md`](README.md). For agent-engineering taxonomy (Runtime / Capability / Specification / Tool layers), see [`lib/agents/AGENT_LAYERS.md`](lib/agents/AGENT_LAYERS.md).

## Working Style

This project follows the behavioral discipline defined in `Make-AI-Agents/knowledge/behavioral_discipline.md` (when the upstream `Make-AI-Agents` clone is populated locally — see Existing Tooling) or the equivalent discipline loaded via the host tool's skill system.

In short, every contributor — human or LLM — operates under these principles: read before claiming, plan before acting on changes, stop on the first defect rather than papering over, find root causes for bugs, document non-trivial changes in a structured form, generate exactly what was asked (no speculative additions), produce mistake-proof outputs, reflect and tell the user about non-obvious learnings, and respect the user's intent without substitution or drift.

For the full principles and override rules, see `knowledge/behavioral_discipline.md` → "The Ten Principles". The four no-override principles (P-001 Read Before Claiming, P-003 Stop on Defect, P-007 Pull Don't Push, P-010 Respect Intent) apply unconditionally.

**Project-specific rules**:
- **Local files are source of truth.** Canvas is the sync target, not the source. Never treat Canvas as authoritative unless `--pull` was just run.
- **Ground pedagogical work in the knowledge base — don't free-style it.** Before any course design, redesign, audit, or outcome/assessment/rubric work (e.g. *"architect a redesign — start with the CLOs"*), read [`lib/agents/knowledge/README.md`](lib/agents/knowledge/README.md) and follow its routing table to the relevant knowledge file(s) **first**, then pull them in the documented order. Cite which files you used so the operator can verify the work is grounded in the toolkit's cited frameworks rather than the model's generic training. The deterministic audit tools (`clo_quality_audit.py`, `rubric_quality_audit.py`, etc.) encode the same frameworks and emit tags — run them to get real course data, but the knowledge files carry the judgment the tools can't (e.g. catching a rubric-criterion artifact mis-discovered as a CLO).
- **Validate audit baseline before redesign workflows.** Before starting a redesign (Flow A in [`docs/course-design-workflow.md`](docs/course-design-workflow.md)), check `.canvas/audit/<course_id>.json` for a recent audit artifact: (1) verify `course_id` matches the target course (never redesign course X using course Y's audit), (2) warn if `run_at` > 30 days (semester-scale staleness), (3) if absent/stale, run `course_audit.py` first. The artifact enables **progress tracking across iterations** — compare findings semester-over-semester (`missing_rubrics: 32 → 22 → 12`) to validate iterative improvements. See [`docs/proposals/audit-artifact-progress-tracking.md`](docs/proposals/audit-artifact-progress-tracking.md) for rationale.
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

### Surfacing guidelines

**Bias toward surfacing.** A low-quality report costs ~10s to close; a real bug never filed costs much more. When in doubt, offer filing.

**DO surface when:** Tool exits non-zero (not config error), output "feels off", documented behavior diverges, Canvas API fails unexpectedly, operator wants unimplemented behavior, `learned/` entry referenced twice (Hermes promotion threshold).

**DON'T surface when:** FERPA/push gates fire correctly, operator config gaps (missing env var/keymap), agent supplied wrong inputs (retry with correction first).

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

### Roadmap voting — community prioritization

When the operator wants a feature on the [roadmap](docs/ROADMAP.md), offer to vote via `lib/tools/vote_feature.py`. This signals demand without requiring GitHub accounts.

**Offer when:** Operator wants/needs a roadmap feature (e.g., "what do I need to pass?" → grade-forecast).

**How:** `uv run python lib/tools/vote_feature.py --feature-id <id>` after confirmation. Use `--list` to show all features with current vote counts and IDs. Feature IDs are kept in sync with `lib/tools/vote_feature.py` (source of truth).

### Adopter upgrade discoverability

When you're working in a CONSUMER repo (m119-master, ds460-master,
ds250-onln-master, itm327-master, aol-student, etc.) and you notice
`canvas-toolbox/` is at an older version than the latest, surface
[`UPGRADING.md`](docs/UPGRADING.md) in the canvas-toolbox repo. It carries
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
Follow [`SECURITY.md`](.github/SECURITY.md) instead: email the maintainer
directly. The public intake channel is for bugs + enhancements; the
private channel is for security.

### Dev tools & docs — maintainer-only

**IMPORTANT:** AGENTS.md is public. Secrets/credentials → `docs/dev/` (gitignored). Workflow instructions → AGENTS.md.

**Dev tools** (lib/tools/, gitignored): `add_roadmap_feature.py` (voting system updater). When creating: add to `.gitignore` immediately, update this list, include docstring.

**Dev docs** (docs/dev/, gitignored): Deployment runbooks with real tokens, API key procedures, private architecture. Public architecture/workflow stays in AGENTS.md.

## Active Context

_Last updated: 2026-07-07_

Latest 5 releases only — full detail for every version is in
[`CHANGELOG.md`](CHANGELOG.md). On each release, add the new entry on top and
rotate the oldest out. Kept to ≤5 entries / ≤150 lines / ≤25k tokens, enforced
in CI per make_AGENTS AGENTS-QC-010 + AGENTS-QC-011.

### Recent: v1.6 course-centric architecture (v1.6.0, 2026-07-07)

Major architecture refactor: course files (.env, AGENTS.md, course/, grading/, handoffs/) now live at course root (DS460/), not inside canvas-toolbox/. cb-init auto-detects subdirectory context and creates files in the right location. Includes v1.5 → v1.6 migration detection for .env relocation. 13-step cb-init (was 9): adds .gitignore creation, canvas-sync --pull, course-level AGENTS.md stub generation, and opt-in handoffs/ directory (--with-handoffs flag). Eliminates multi-course "which canvas-toolbox is this?" confusion. Tools continue to run from course root unchanged. Full backward compatibility for standalone mode. See docs/proposals/v1.6-cb-init-refactor-plan.md for implementation details.

### Earlier: AGENTS.md trimmed to rotating latest-5 + CI guard (v0.72.3, 2026-06-29)

Active Context had grown into a 182 KB append-only release log (past host-tool
read limits). Trimmed to the latest 5 entries; full history moved to CHANGELOG.
CI guard enforces the rotation/size thresholds. Also repaired 25 stale relative
links (doc moves + `lib/agents/`).

### Earlier: README marketing restructure + repo-root declutter (v0.72.2, 2026-06-29)

Marketing-ready landing: setup moved to the top, three-box launchpad
(Build & revise · Audit & improve · Grade), advanced Orca multi-course option.
Repo root decluttered 18 → 12 files (health files → `.github/`, long docs → `docs/`).

### Earlier: README polish — surface quiz time extension + fix late-work intro (v0.72.1, 2026-06-26)

Docs-only: gave `student_quiz_time_extension.py` a standalone README section +
13th workflow row; fixed the late-work intro to mention both override flavors
(drop lock_at vs `--shift-by-days`).

### Earlier: BYUI SAS accommodation sprint — quiz time + test_reschedule + dispatcher (v0.72.0, 2026-06-26)

Three-item SAS sprint: `student_quiz_time_extension.py` (per-student classic-quiz
time multiplier), `--shift-by-days` mode on `student_late_accommodation.py`
(test_reschedule), and `apply_sas_accommodations.py` (YAML dispatcher, 4-tier
classify, FERPA audit log). +55 tests. New Quizzes (LTI) deferred.

_Earlier releases (v0.71.0 and back) live in the [CHANGELOG](CHANGELOG.md)._


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

**Full catalog:** [lib/tools/README.md](lib/tools/README.md)

**Most commonly used:**
- `canvas_sync.py` — Single-course mirror (pull/push/build)
- `course_audit.py` — One-command pre-semester health check (rubrics/CLOs/syllabus/workload)
- `course_quality_check.py` — Post-push structural audit (duplicates, floating items, date windows)
- `blueprint_sync.py` — Master → Blueprint sync (content + settings)
- `validate_blueprint_sync.py` + `blueprint_exception_report.py` — Post-Blueprint-sync validation
- `module_settings_sync.py` — Module prerequisite/completion reconciliation

**Related agents:** `canvas_course_expert`, `canvas_schedule_auditor`, `canvas_blueprint_sync`, `canvas_semester_setup`, `canvas_new_course_setup` (see [lib/agents/](lib/agents/))

**Knowledge base:** [lib/agents/knowledge/README.md](lib/agents/knowledge/README.md) (frameworks), [AGENT_LAYERS.md](lib/agents/AGENT_LAYERS.md) (taxonomy)

**Populating upstream clones** (gitignored, local only):
```bash
git clone https://github.com/chaz-clark/Make-AI-Agents.git make-ai-agents
git clone https://github.com/chaz-clark/gh_issues_agent.git gh-issues-agent
git clone https://github.com/chaz-clark/handoff.git
```

Each is a real git clone with its own `.git/` directory. Edits flow upstream (edit at the source repo's local clone, not here). Future updates: `cd <dir> && git pull origin main`.

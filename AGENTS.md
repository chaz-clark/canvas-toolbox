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

### Roadmap voting — community prioritization

The toolkit has a [roadmap of planned features](docs/ROADMAP.md) organized by priority phase. When the operator mentions wanting a feature that's on the roadmap (or similar to one), **offer to vote on their behalf** via the voting system. This signals demand to the maintainer without requiring GitHub accounts.

**When to offer voting:**
- Operator says they want a feature that matches a roadmap entry (exactly or conceptually similar)
- Operator expresses pain that a roadmap feature would solve
- Operator asks "when will X be available?" and X is on the roadmap
- During "what do I need to pass?" questions → mention grade forecast is roadmap item #1

**How to offer:**
```
_That feature is on the roadmap: "Student grade forecast" (Phase 1, HIGH DEMAND).
Would you like me to vote for this feature to signal demand?
I can run: uv run python lib/tools/vote_feature.py --feature-id grade-forecast_
```

**After operator confirms:**
- Run the voting tool with `--feature-id <id>` (not `--feature` — IDs are unambiguous)
- Show the updated vote count
- Don't over-explain the voting system unless asked

**Don't offer voting for:**
- Features not on the roadmap (file as enhancement via `cb_report_bug.py` instead)
- Features already implemented (check docs/ first)
- Vague "it would be cool if..." without clear roadmap match

**Roadmap feature IDs** (kept in sync with `lib/tools/vote_feature.py`):
- `grade-forecast` — Student grade forecast (what do I need to pass?)
- `engagement-early-warning` — Student engagement early warning system
- `bulk-reminder` — Bulk assignment reminder sender
- `group-override-manager` — Group override manager
- `assignment-performance-analyzer` — Assignment performance analyzer
- `accommodation-notifier` — Accommodation notification tool
- `weekly-announcements` — Weekly announcement publisher
- `ta-grading-status` — TA grading status & voice coaching
- `course-restore` — Course restoration from local repo
- `module-scheduler` — Module release scheduler
- `rubric-library` — Rubric template library
- `grade-audit-trail` — Grading audit trail exporter
- `random-groups` — Random group generator

View full roadmap with `--list`: `uv run python lib/tools/vote_feature.py --list`

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

### Dev tools — maintainer-only automation

The toolkit includes maintainer-only scripts for managing the toolkit itself (not for operator use). These live in `lib/tools/` alongside user-facing tools but are gitignored.

**Current dev tools:**
- `add_roadmap_feature.py` — Atomically updates voting system when adding roadmap features (vote_feature.py, update_roadmap_votes.py, worker.ts, AGENTS.md)

**When creating new dev tools:**
1. Place in `lib/tools/` (keeps all tools in one directory)
2. Name clearly (prefix with purpose, not `_dev_` or similar)
3. Add to `.gitignore` under the "Dev tools" section
4. Update the list above in AGENTS.md
5. Include usage docstring in the script

**Why gitignore dev tools?**
- They're maintainer-specific (update voting worker, manage releases, etc.)
- Operators don't need them (would clutter `lib/tools/`)
- They often have hardcoded assumptions (e.g., wrangler config, file paths)
- Keeps the public repo focused on operator-facing functionality

**Pattern:** When you create a dev tool during this session, immediately add it to `.gitignore` and update the list above. Don't wait until commit time — easy to forget.

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

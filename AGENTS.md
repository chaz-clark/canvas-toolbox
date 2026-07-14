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

> **Cloudflare Workers moved out (2026-07-12).** The bug-intake + voting workers (formerly `infra/`) now live in the **`edge-infra`** sister repo (`chaz-clark/edge-infra`, private), alongside the new `heartbeat-worker`. It's a *peer* repo, not cloned here. The deployed `canvas-toolbox-bugs` worker is unaffected; redeploy from `edge-infra/workers/bug-intake-worker/`.

**Consumer usage (v1.6+)**: clone `canvas_toolbox` into your course folder (`git clone https://github.com/chaz-clark/canvas_toolbox.git canvas_toolbox`), then run `uv run python canvas_toolbox/lib/tools/cb_init.py` which auto-creates course files (.env, .gitignore, AGENTS.md) at course root. Tools run from course root: `uv run python canvas_toolbox/lib/tools/<script>`. Update safely: `cd canvas_toolbox && git pull origin main` — only toolkit code updates; your course files are untouched.

v1.6 architecture moves all course files to course root (DS460/), not inside canvas_toolbox/. The toolkit is gitignored; course context lives in course-root AGENTS.md. Migration from v1.5: cb-init detects old .env location and offers to migrate.

For full setup and command reference, see [`README.md`](README.md). For agent-engineering taxonomy (Runtime / Capability / Specification / Tool layers), see [`lib/agents/AGENT_LAYERS.md`](lib/agents/AGENT_LAYERS.md).

## Working Style

This project follows the behavioral discipline defined in `Make-AI-Agents/knowledge/behavioral_discipline.md` (when the upstream `Make-AI-Agents` clone is populated locally — see Existing Tooling) or the equivalent discipline loaded via the host tool's skill system.

In short, every contributor — human or LLM — operates under these principles: read before claiming, plan before acting on changes, stop on the first defect rather than papering over, find root causes for bugs, document non-trivial changes in a structured form, generate exactly what was asked (no speculative additions), produce mistake-proof outputs, reflect and tell the user about non-obvious learnings, and respect the user's intent without substitution or drift.

For the full principles and override rules, see `knowledge/behavioral_discipline.md` → "The Ten Principles". The four no-override principles (P-001 Read Before Claiming, P-003 Stop on Defect, P-007 Pull Don't Push, P-010 Respect Intent) apply unconditionally.

**Project-specific rules** (summaries — see [`lib/agents/knowledge/working_style_canvas_toolbox.md`](lib/agents/knowledge/working_style_canvas_toolbox.md) for detailed explanations + motivating cases):

- Local files are source of truth (Canvas is sync target)
- Ground pedagogical work in knowledge base (cite frameworks used)
- Validate audit baseline before redesign (check `.canvas/audit/<course_id>.json`)
- Canvas IDs are course-specific (match by title, not ID)
- Adding content requires course + module steps
- Confirm scope before any write (master vs blueprint vs sections)
- `request_confirmation()` required before Canvas writes
- Run `course_quality_check.py` after every push
- Completion requirements enable prerequisite chain
- Keep institutional facts out of committed files (institution-agnostic)
- Sandbox-first testing before handoffs
- Surface-before-apply on every state change (including GitHub issues)
- `git push` after every commit (no local-only commits)
- Placeholder names must be visibly fake (`"Sarah" (fake name)`)
- Deterministic-first grader design (Python over LLM when deterministic)

## Quality Discipline (Toyota Production System)

AI agents working in this repo must follow three core quality principles:

### 1. Genchi Gembutsu (現地現物) - Go and See

**Don't assume, verify with real data:**
- Test with REAL user data, not synthetic fixtures
- When uncertain about format, examine actual files
- Verify in real environment, don't trust docs alone
- Read actual code before claiming understanding

**Behavioral trigger**: When you catch yourself saying "probably" or "should" → STOP and verify

### 2. Jidoka (自働化) - Built-in Quality / Stop on Defect

**Build quality in, stop when defect detected:**
- Write tests WITH code, not after
- Red tests block progress - fix immediately, don't defer
- Validation runs automatically (not manual step)
- Can't merge/export with errors (blocked by design)

**Behavioral trigger**: When you want to say "we'll fix this later" → STOP and fix now

**Aligns with**: P-003 Stop on Defect

### 3. Poka-yoke (ポカヨケ) - Mistake-Proofing

**Design so mistakes can't happen:**
- Automate validation (no manual steps)
- Use pre-commit hooks to catch errors
- Type hints catch errors at write-time
- Block operations that would create defects
- **Always run via `uv run`** (`uv run pytest lib/tests -q`, `uv run python lib/tools/...`) — dependencies (`markdownify`, etc.) live in the uv venv; system `python3`/`pytest` will report false failures from missing modules.

**Behavioral trigger**: When manual verification required → Design it out

---

## Quality Loop

These three work together:

```
Prevent (Poka-yoke) → Detect (Jidoka) → Verify (Genchi Gembutsu)
         ↑______________________________________________|
```

When you find a defect:
1. **Fix it** (Jidoka - stop and correct)
2. **Verify the fix** (Genchi Gembutsu - test with real data)
3. **Prevent recurrence** (Poka-yoke - add automated check)

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

A one-command CLI that files a scrubbed report on `chaz-clark/canvas-toolbox` via the Cloudflare-fronted intake worker (now in the `edge-infra` sister repo — private — at `workers/bug-intake-worker/`). **No GitHub account needed on the operator's side.** Use for:

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

If the printed version is behind the latest (currently **v1.7.0**),
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

_Last updated: 2026-07-12_

Latest 3 releases only — full detail for every version is in [`CHANGELOG.md`](CHANGELOG.md). On each release, add the new entry on top and rotate the oldest out. Kept to ≤3 entries / ≤100 lines / ≤10k tokens for active development phase (faster HERMES cycle during beta/sprint cadence).

**Versioning policy (2026-07-13):** SemVer with a continuous-patch cadence — bump `pyproject.toml` **in the PR itself**: **patch** (3rd) by default, **minor** (2nd) for a medium shift (like the v1.7 offline suite), **major** (1st) for a breaking change; a docs-only PR may leave it unchanged. On merge, [`.github/workflows/version-bump.yml`](.github/workflows/version-bump.yml) auto-tags the commit `vX.Y.Z` from `pyproject` (skips if the tag already exists). The bump rides the protected-PR flow — the bot can't commit to `main`, but tags aren't branch-protected. Consumers track `main` via `git pull`, so the version is a milestone + drift-detection marker, not a per-merge gate.

### Recent: v1.7 offline mode (v1.7.0, 2026-07-12)

Offline mode: tools read a local `course/` (from `canvas_sync --pull` or `offline_import` of a `.imscc`), running identically online/offline. 7 audits gained `--local` with exact parity (workload / syllabus / accessibility / content_representation / grading_structure / rubric_coverage / rubric_quality); offline foundation (`CANVAS_MODE`; gradebook de-id / re-id / apply; `.imscc` date-shift; the `course/` loader; `offline_import`). Also: `clo_catalog_import` (Kuali catalog → Canvas Outcomes), institution-agnostic `syllabus_audit`, and the Cloudflare Workers migrated out to the `edge-infra` sister repo. Proven both ways that a `.imscc` carries course-owned outcomes (export + import round-trip).

**Offline write (v1.7.7):** `course/` is the working folder (iterate freely); the `.imscc` is the source of truth. `offline_import` saves the original as the sidecar `course/.source.imscc`. When done, `imscc_record` patches your `course/` edits into that sidecar in place — faithful (quiz questions / files / LTI preserved byte-for-byte; it patches, never rebuilds) — for re-import via the Canvas UI.

### Recent: v1.6 course-centric architecture (v1.6.0, 2026-07-07)

Major architecture refactor: course files (.env, AGENTS.md, course/, grading/, handoffs/) now live at course root (DS460/), not inside canvas-toolbox/. cb-init auto-detects subdirectory context and creates files in the right location. Includes v1.5 → v1.6 migration detection for .env relocation. 13-step cb-init (was 9): adds .gitignore creation, canvas-sync --pull, course-level AGENTS.md stub generation, and opt-in handoffs/ directory (--with-handoffs flag). Eliminates multi-course "which canvas-toolbox is this?" confusion. Tools continue to run from course root unchanged. Full backward compatibility for standalone mode.

### Earlier: AGENTS.md trimmed to rotating latest-5 + CI guard (v0.72.3, 2026-06-29)

Active Context had grown into a 182 KB append-only release log (past host-tool read limits). Trimmed to latest 5 entries; full history moved to CHANGELOG. CI guard enforces rotation/size thresholds. Also repaired 25 stale relative links (doc moves + `lib/agents/`).

_Earlier releases (v0.72.0 and back) live in the [CHANGELOG](CHANGELOG.md)._


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

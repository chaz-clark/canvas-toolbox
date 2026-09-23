---
name: canvas-toolbox-agents
description: Constitution for the `canvas-toolbox` repo — a Canvas LMS course-management & audit toolkit. The always-on rules that govern EVERY session (FERPA discipline, the Canvas-write safety doctrine, behavioral principles, git/handoff conventions) plus the index of operating-mode skills. Mode-specific procedure lives in the skills, not here.
version: "0.2"
author: chaz-clark
license: MIT
metadata:
  repo: canvas-toolbox
  spec-source: Make-AI-Agents/make_AGENTS
---

# Canvas Toolbox

A Canvas LMS course-management toolkit — mirrors live Canvas courses to local files,
audits structure against an 8-framework instructional-design stack, and applies
instructor-approved changes via the Canvas REST API.

**This is**: a toolkit for managing Canvas courses as code (mirror, edit, audit,
push), an 8-framework audit engine, and a multi-course orchestration system.
Tool-agnostic (any LLM tool that reads AGENTS.md); built for BYU-Idaho but
institution-agnostic.

**This is NOT**: a Canvas replacement, a student-facing tool, a VCS for Canvas
content, or a NewQuiz/ExternalTool editor (REST API limits).

**Audience**: instructors and instructional designers who edit Canvas courses and
use LLM coding tools for course-design work.

---

## How this file works — constitution + skills

**This file is the constitution: the always-on rules that bind you in EVERY session,
whatever the task.** The step-by-step procedure for each kind of work lives in a
**skill** that loads on demand. Read the constitution always; load the skill for the
mode you're in.

### Skills — the operating modes

Load the matching skill *before* doing that kind of work — it carries the full
playbook (tools, gates, order of operations) so you don't operate from half-memory.

| Skill | Load it for | Examples |
|---|---|---|
| **`grading`** | Any grade that could reach a student | fetch → consensus → review → push; `grader_standing`; disclosure menu |
| **`course-build`** | Making Canvas match local content | `canvas_sync`, `blueprint_sync`, module settings, offline/`.imscc` |
| **`audit`** | Read-mostly course-design analysis | `course_audit`, quality check, 8 frameworks, rubric coverage/quality |
| **`accommodations`** | Per-student interventions | time extensions, late grace, SAS letters, overrides, exemptions, submit-on-behalf |
| **`ferpa-deid`** | De-id/re-id machinery | `build_deid_master`, de-identify artifacts, re-identify by key, name-leak check |
| **`title-iv`** | Federal engagement / withdrawal compliance | `course_engagement_audit` (UW/UF/R2T4), Title IV snapshot |
| **`voicing`** | Writing student-facing text in the instructor's voice | load the course's voicing profile for grading comments / notes — never invent a voice |
| **`improve`** | Logging & tracking course improvements | the `IMPROVEMENTS.md` kanban — audit findings + user notes as cards, Backlog → Ready → In Progress → In Review → Done |

Meta/lifecycle tools (`cb_init` setup, `cb_report_bug`, `vote_feature`) are governed
here in the constitution, not a skill.

---

## ⚠️ FERPA discipline (constitutional — never overridden)

**These files are FERPA Zone 2. NEVER READ OR DISPLAY THEM** — not with Read, `cat`,
`head`, `tail`, or bare `grep`. They must never enter LLM context, logs, or any cloud
surface:

- `grading/.deid_master.csv` — user_id ↔ name map (most common violation)
- `grading/.known_names.txt` — full roster (names)
- `grading/*/.keymap.json` — de-id key ↔ filename+user_id
- `grading/**/.fetch_log.json` — fetch keymap with names
- `grading/*/.review.csv` — re-identified results
- `grading/*/feedback/_grader*.csv` — grading sheets with names
- `grading/**/submissions_raw/**` — raw submissions (potential name leaks)

**A course adds its own Zone-2 files in `.claude/ferpa_zone2.txt`** (one regex per
line). The list above is Canvas filenames; a course on another LMS has different
name-bearing files, and `grade_guardian` enforces only what it knows about — an
installed hook covering none of your files is worse than no hook. `cb_update` prints
the active pattern count so "present" can't be read as "covered".

**The git layer is guarded too.** `grade_guardian` stops *you* reading these; it
cannot see `git push`, and a push can't be undone. `cb_update` installs a
`pre-push` hook reading that same pattern file, which checks the commit RANGE —
history is what gets published, and a later commit deleting a file doesn't unpublish
it. Path checks run by default; content scans (uid→name maps, roster surnames) are
opt-in via `.claude/ferpa_scan_content`, because surname matching false-positives on
ordinary prose. `cb_update` also reports name-bearing directories git isn't ignoring.

**Verify with `wc -l` or `ls` only.** To confirm a code exists, filter columns:
`grep "S-68BC40" grading/.deid_master.csv | cut -d',' -f1,2` (shows deid_code +
user_id, never the `sortable_name` column). Redirect to `/dev/null` or `cut` to
columns 1,2 — never display raw rows.

**Zone 2-ADJACENT — names may be present, but NEVER beside an evaluation.** This
tier covers both files you legitimately READ that carry names, and student-facing
text you WRITE:

- *Reading:* `grading/*/_computed_grades.csv`, `grading/*/_gradebook_canvas.csv`,
  `grading/*/_actual_grades.csv`, `grading/*/FINAL_REVIEW_COMMENTS_*.md`
- *Writing:* student-facing text you draft for the operator to deliver to one
  identified student (a discussion reply, a message asking which data set they used)

**Use codes, not names — no matter which file the name came from.** Tools accept
`--deid-code`/`--user-id`; the *human* looks up the identifier locally and hands you
the opaque code. You never re-identify, and **being allowed to read a name never
makes you allowed to print one** — refer to students only by `user_id` or
`deid_code` in every response, summary, table, and commit message. (Text you draft
*for a student to read* is the one place a name belongs — see the convention below.
Everything you write *about* a student uses codes.)
✅ "Reopened for user_id 900003" · ❌ "Reopened for Cid Cole (900003)"
✅ "FR-B75C87 earned a B+ elevated to A" · ❌ "Student 900003 (Cid Cole) …"
If asked "who is user_id 900003?" → "I don't have the name mapping (FERPA Zone 2);
check `grading/.deid_master.csv` locally."

**In student-facing text, the convention governs the TEXT, not the file.** Refer to
a student by given name plus last initial — never a full surname, not in headers,
not in parentheticals, not in peer mentions. This is **exposure minimization, not
de-identification**: in a small section a first name plus an initial usually resolves
to one person, and the student's full name is already visible on the thread the draft
is destined for. What it limits is what accumulates in the repo and in transcripts.

**Operator-facing scaffolding** — the material required to LOCATE and CONFIRM the
right artifact before delivering into it — is not student-facing text and may carry
full names. Typically the platform's printed name, the thread title and the
timestamp; where those don't uniquely identify a thread it may include a short
excerpt of the post, or another participant's name where that is what disambiguates.
**The test is necessity for navigation, not convenience:** if removing it wouldn't
make the artifact harder to find, it isn't scaffolding. Never a licence for
name-bearing prose.

A *peer's* name is the sharpest case — the naming convention above bans peer mentions
in student-facing text, so admitting one here needs the strictest reading of that
test: last resort, when name-plus-timestamp-plus-excerpt still doesn't disambiguate.

Scaffolding must live under an **already-gitignored path** — a per-directory
`.gitignore` containing `*`, written when the directory is created, as
`build_deid_master.py` already does for `grading/`. Protection that ships with the
directory survives edits to the root ignore file; a root rule is only as durable as
the next person restructuring it. (A consumer restructuring theirs found a blanket
grading-directory deny had been the only thing covering three other name-bearing
paths, and a replacement line matched nothing because a trailing comment became part
of the pattern. Both caught by checking, not by design.)

**Operator-supplied names.** This rule governs what you produce on your own
initiative. A name the operator supplies in the same turn may be used
conversationally *within that turn* — repeating it discloses nothing they did not
just write, and refusing teaches them the rule is unusable. It must not otherwise be
persisted: not to a file, not to a commit message, not to any artifact outlasting
the exchange.

**Unchanged and unconditional: a name never appears beside a score, a rubric
criterion, a grade band, or a standing.** No exception, no tier, no turn scope.

*The judgment call has not been eliminated, only moved* — from "is this a
facilitation draft?" to "is there an evaluation next to this name?" The second is a
condition you can check; the first is an inference about intent. Keep checking.

*Three real incidents. 2026-07-01 and 2026-07-02: an agent read/`head`-ed
`.deid_master.csv` and surfaced a name — the READ failure, now also blocked by
`grade_guardian`. 2026-07-28: an agent read names out of a legitimately-readable
working file and printed them next to grades — the OUTPUT failure, which no read
rule can catch. Both directions are covered above.*

---

## ⚠️ Canvas writes go through the toolkit (constitutional — never overridden)

**Grades and comments reach Canvas ONLY through a sanctioned `lib/tools/` writer:**
`grader_push.py` (submission feedback, HG-5-gated), `grader_standing.py` (the standing
column), `grader_push_comments.py` (transports grader-staged, reviewed comments),
`grader_letter_comments.py` (instructor-authored comment-only, never AI-drafted),
`grader_audit_workflow.py --fix` (idempotent grade re-post, never a new value), and
`grader_quiz_clear_pending.py` (zeroes pending quiz scores). Every one of these is
declared `canvas_grade_comment_write` in `agent-packages/grading/manifest.yaml` and
approval-gated by `package_validate.py`'s `CONSTITUTIONAL_WRITERS` list — read a tool's
own docstring before use; none of them accept unreviewed, AI-drafted content.
**Never** hand-write a Canvas grade/comment write — no custom `requests`/`curl`, no
inline `python -c`, no `/tmp/*.py`. A direct write skips *every* safeguard at once
(review gate, duplicate-comment Andon, Test-Student exclusion, grade validation,
`canvas_course_guard`, disclosure). Duplicate comments, grades on Test Student, and
wrong grade scales in the field were **all** hand-written scripts bypassing the tool.

Before implementing *any* Canvas operation: **search `lib/tools/` first**; if a tool
exists, use it; if none does, propose one and ask — don't improvise a write.

**The `grade_guardian` PreToolUse hook enforces this deterministically** — it blocks
*creating* a bypass script (Write), *editing* one (Edit), and *running* one
(`python x.py` whose body writes to Canvas). If it blocks you: use the tool, or
surface the blocker to the instructor. **Do not route around it, and do not stack
`--yes`/`--regrade`/`--allow-enrolled` to force a gate** — a blocked gate means "get
the human," not "add a flag." (Deep grading protocol: the `grading` skill.)

The one carve-out: an **explicit, specific instruction from the instructor** to use
that flag for *this* operation on *this* course ("push the approved date changes to
423164 with `--allow-enrolled`") *is* getting the human. Confirm the scope back to
them, then run it with the flag. What's barred is the agent reaching for the flag on
its own judgment, or treating a vague "sounds good" as authorization.

Confirm scope before every write — master vs blueprint vs section. `request_confirmation()`
is required before Canvas writes.

---

## Working style

Every contributor — human or LLM — operates under the behavioral discipline in
`Make-AI-Agents/knowledge/behavioral_discipline.md` (when the upstream clone is
populated) or the equivalent loaded via the host tool's skill system: read before
claiming, plan before acting, stop on the first defect, find root causes, generate
exactly what was asked (no speculative additions), mistake-proof outputs, and respect
intent without drift. Five **no-override** principles apply unconditionally: **P-001
Read Before Claiming, P-003 Stop on Defect, P-007 Pull Don't Push, P-010 Respect
Intent, P-011 Toyota Quality Loop** (below).

**Ground claims in the source — letters are read, not parsed.** Any statement you repeat
to a student (their requested grade, their evidence, what their letter "says") must come
from **reading that student's prose in full** — never a regex/NLP extraction. A parser on
prose fabricates (a field script emitted *"you requested an A"* to students who asked for
a C). Structured data (code, notebooks, CSVs, the gradebook) may be parsed; a letter,
self-assessment, or reflection is comprehension data — read it, or abstain from the claim.

**Always run via `uv run`** (`uv run pytest lib/tests -q`, `uv run python lib/tools/…`).
Dependencies (`markdownify`, etc.) live in the uv venv; system `python3`/`pytest`
reports false failures from missing modules.

**Audience = non-technical faculty.** Complete actions *for* them; never hand an
instructor a terminal command to copy-paste, `cd` into, or type a confirmation at.
If a tool refuses non-interactive input, that's a signal to find the sanctioned
non-interactive path (e.g. grader_standing's `--yes` for value-only pushes) or to
surface a plain-language choice — not to send a non-technical user to a terminal.
The exception is a genuine human-review gate on **AI-drafted** grades (grader_push
HG-5), where the instructor's terminal confirmation is the point; there, do the
review together in chat and hand off only that final confirmation.

Project-specific rules (detail: [`lib/agents/knowledge/working_style_canvas_toolbox.md`](lib/agents/knowledge/working_style_canvas_toolbox.md)):
local files are the source of truth (Canvas is the sync target); ground pedagogical
work in the knowledge base; match Canvas objects by title, not ID; keep institutional
facts out of committed files; placeholder names must be visibly fake (`"Sarah" (fake
name)`); deterministic-first grader design (Python over LLM when deterministic).

---

## Toyota Quality Loop (P-011 — no-override)

Every task completes the loop: **Prevent (Poka-yoke) → Detect (Jidoka) → Verify
(Genchi Gembutsu).** Violating it creates technical debt — Genchi Gembutsu without
Jidoka verifies after the damage is done; Jidoka without Poka-yoke catches the same
mistake repeatedly; Poka-yoke without Genchi Gembutsu prevents the wrong things.

**Genchi Gembutsu (現地現物) — go and see.** Don't assume, verify with real data: test
against real course data, not synthetic fixtures; when uncertain about a format,
examine the actual file; verify in a real Canvas sandbox, don't trust docs alone; read
the actual code before claiming to understand it.
*Trigger: when you catch yourself saying "probably" or "should" → STOP and verify.*

**Jidoka (自働化) — built-in quality, stop on defect.** Write tests with the code, not
after; a red test blocks progress — fix it, don't defer; validation runs
automatically, not as a manual step; a push with errors is blocked by design, not by
discipline. *Trigger: when you want to say "we'll fix this later" → STOP and fix now
(aligns with P-003).*

**Poka-yoke (ポカヨケ) — mistake-proofing.** Design so the mistake can't happen:
automate validation instead of a manual step; use hooks (`grade_guardian`,
pre-commit) to catch errors at the harness, not at review; block the operation that
would create the defect. *Trigger: when manual verification is required → design it
out instead.*

When you find a defect: fix it (Jidoka), verify the fix with real data (Genchi
Gembutsu), then add an automated guard so it can't recur (Poka-yoke).

---

## Git & versioning

Trunk-based: branch off `main`, PR, squash-merge, delete branch, sync local `main`.
`main` always works. **Bump `pyproject.toml` version IN THE PR** — patch by default,
minor for a medium shift, major for a breaking change; docs-only may leave it. A
change to the toolkit's **shape** — a new architecture (like the operating-mode
skills split), a new subsystem, a consumer-facing reorganization — is a **minor**
even if it's "just docs / just files": bump the 2nd digit when the toolkit
*reorganizes*, not only when behavior changes. (The skills split shipped as a patch
by oversight; 1.8.0 is its milestone.) On merge,
`.github/workflows/version-bump.yml` auto-tags `vX.Y.Z`. Consumers track `main` via
`git pull`, so the version is a milestone + drift marker, not a per-merge gate.

---

## Repo structure & consumer model

```
canvas-toolbox/
├── lib/
│   ├── agents/            ← agent specs, knowledge/, templates/, AGENT_LAYERS.md
│   ├── tools/             ← Python CLIs (uv run python lib/tools/<script>)
│   └── tests/             ← pytest (dev-only — not distributed to course repos)
├── skills/                ← operating-mode skills, CANONICAL source (grading,
│                             course-build, audit, …)
├── .claude/skills/, .agents/skills/  ← GENERATED runtime adapters — never edit
│                             directly; regenerate via generate_adapters.py
├── agent-packages/        ← schema-validated capability manifests (course-design,
│                             grading, student-support) + registry.yaml
├── schemas/                ← package-manifest / distribution-manifest JSON schemas
├── distribution/manifest.yaml  ← the course-facing payload allowlist — narrower
│                             than `git ls-files`; see the file's own header
├── bin/                    ← cb-init, cb-report-bug, cb-share entry points
├── scaffold/                ← copy-once starters (.gitignore, .env.example)
├── knowledge/                ← cross-cutting knowledge (behavioral discipline,
│                             naming conventions, trunk-based development)
├── docs/, examples/, README.md, CHANGELOG.md
```

**Consumer usage (v2.0+, flat layout — current default):** `cb_init.py`/`cb_flatten.py`
bootstrap a course repo directly at its own root — no visible `canvas-toolbox/`
subdirectory. A hidden pristine clone (`.canvas-toolbox/`, gitignored) is the update
source; `cb_flatten.py` copies the distribution manifest's allowlist into the course
root and merges AGENTS.md (constitution + the course's own HERMES learning, joined by
sentinel markers — see `merge_cleanup.py`). Run tools from the course root:
`uv run python lib/tools/<script>`. Update: `uv run python lib/tools/cb_update.py --pull --apply`.

**Legacy nested layout (v1.6–v1.22, still supported):** a course repo clones
`canvas-toolbox` into its own root (gitignored) as a visible subdirectory, runs
`cb_init.py` from there, and runs tools via
`uv run python canvas-toolbox/lib/tools/<script>`. Update: `cd canvas-toolbox && git pull`.
`migrate_nested_to_flat.py` converts an existing nested install to flat.
[`docs/UPGRADING.md`](docs/UPGRADING.md) predates the flat layout — it currently
only covers nested-layout version bumps.

Full setup/command reference: [`README.md`](README.md). Agent-layer taxonomy:
[`lib/agents/AGENT_LAYERS.md`](lib/agents/AGENT_LAYERS.md).

---

## Handoff recognition

This repo participates in the cross-repo `handoff` convention (canonical:
[`handoff/CONVENTION.md`](https://github.com/chaz-clark/handoff/blob/main/CONVENTION.md)).
Treat `handoffs/<YYYY-MM-DD>_<topic>.md` (deliver), `handoffs/HANDOFF_<topic>.md`
(request), and root `<X>_HANDOFF_<topic>.md` as structured artifacts with a lifecycle,
not prose. Essentials:

- **Read the metadata header first** (Date/Author/Direction/Status/Origin/Topic); a
  missing required field → STOP and ask.
- **Act only on `Status: delivered`.** Skip `draft`/`applying`/`applied`/`archived`/
  `superseded`. `parkinglot.md` / `long-term-parking.md` (`internal`) are deferred by
  design — act only on human direction or a met `Trigger:`.
- **Surface before applying** — summarize what changes, get per-decision approval
  (never bulk auto-apply). **On apply, set `Status: applied`** + a Lifecycle marker.
- **STOP on missing referenced artifacts** — don't infer or fabricate.

---

## Continuous improvement

Two capture channels. **`cb_report_bug.py`** files a scrubbed, maintainer-routed
issue (no GitHub account needed) — title prefix `bug:` or `enhancement:`. **`lib/agents/knowledge/learned/`**
holds durable session lessons; a lesson referenced a second time is the signal to
file it as an enhancement. Bias toward surfacing (one skippable line at the end of a
response) when a tool exits non-zero unexpectedly, output feels off, or the operator
wants unimplemented behavior. Don't surface when a FERPA/push gate fires correctly or
the operator supplied wrong inputs.

**Security issues are NOT bugs** — a PII leak, an exposed token, or a bypassed FERPA
gate goes to [`SECURITY.md`](.github/SECURITY.md) (private email), never the public
`cb_report_bug.py`.

**Maintainer-only:** AGENTS.md is public. Secrets/runbooks → `docs/dev/` (gitignored).
Dev tools (gitignored) → add to `.gitignore` on creation.

---

## Active Context

_Last updated: 2026-09-22._ Latest few releases only; full history in
[`CHANGELOG.md`](CHANGELOG.md).

- **v2.0.0 — runtime-neutral agent packaging (2026-09-22, #317):** the flat layout
  above, replacing the nested `canvas-toolbox/` subdirectory as the default consumer
  model. Distribution manifest, schema-validated agent packages, and a
  capability-consent gate (instructor approves Canvas-write capability growth
  explicitly — see `capability_consent.py`). Validated by real pilots against four
  live course repos before merge. A known gap tracked separately, not merge-blocking:
  `--approve-all` has no check for an unattended/scheduled invocation (#343).
- **v1.22.x — peer review + intake follow-ups (2026-09-21/22):** `peer_review_setup.py`
  / `peer_review_assign.py` / `peer_review_summary.py` (#331); `cb_report_bug.py --issue
  N` to comment on an existing filed issue instead of always opening a new one (#275);
  `grade_guardian`'s Zone-2 shell-read matching moved to per-segment, quote- and
  heredoc-aware (#334, #338), closing several false-positive denials.
- **v1.8–v1.21 (2026-08):** the skills split (operating-mode skills as loadable units
  instead of one monolithic constitution — 1.8.0 is its milestone); see `CHANGELOG.md`
  for the full run.
- **v1.6 course-centric architecture (v1.6.0, 2026-07-07):** course files live at
  course root, not inside canvas-toolbox/; `cb_init` auto-detects context.

---

## Domain terms

| Term | Definition |
|---|---|
| **Master** | Template course where authoring happens. `MASTER_COURSE_ID`; folder `master/`. |
| **Blueprint** | Canvas Blueprint sections clone from (online programs). `BLUEPRINT_COURSE_ID`; `blueprint/`. |
| **Section** | Live per-semester course (S1, S2…). `S1_COURSE_ID`…; `s1/`, `s2/`. |
| **NewQuiz** | LTI-based quiz engine; can't be content-pushed via REST (edit in UI). |
| **Classic Quiz** | Original engine; has both `quiz_id` and an underlying `assignment_id`; REST works. |
| **Source of truth** | The local working folder; Canvas is the sync *target*. |

---

## References

- **Canvas API knowledge:** [`lib/agents/knowledge/canvas_api_knowledge.md`](lib/agents/knowledge/canvas_api_knowledge.md)
  (documented surface) + [`canvas_api_lessons_learned.md`](lib/agents/knowledge/canvas_api_lessons_learned.md)
  (17 empirical lessons — form-encoding, date trios, quiz dual-IDs, blueprint orphans).
  Read both before a Canvas write or audit; the relevant ones are surfaced in the
  `course-build` and `audit` skills.
- **Instructional-design frameworks:** [`lib/agents/knowledge/README.md`](lib/agents/knowledge/README.md).
- **Tool catalog:** [`lib/tools/README.md`](lib/tools/README.md).
- **Toolkit reuse doctrine:** [`lib/agents/knowledge/toolkit_reuse_knowledge.md`](lib/agents/knowledge/toolkit_reuse_knowledge.md).

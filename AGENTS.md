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

**Verify with `wc -l` or `ls` only.** To confirm a code exists, filter columns:
`grep "S-95DBB6" grading/.deid_master.csv | cut -d',' -f1,2` (shows deid_code +
user_id, never the `sortable_name` column). Redirect to `/dev/null` or `cut` to
columns 1,2 — never display raw rows.

**Use codes, not names.** Tools accept `--deid-code`/`--user-id`; the *human* looks
up the identifier locally and hands you the opaque code. You never re-identify.
✅ "Reopened for user_id 280379" · ❌ "Reopened for Sam Bradshaw (280379)". If asked
"who is user_id 280379?" → "I don't have the name mapping (FERPA Zone 2); check
`grading/.deid_master.csv` locally."

*Two real incidents (2026-07-01, 2026-07-02) came from an agent reading/`head`-ing
`.deid_master.csv` and surfacing a name. That is the failure this rule prevents.*

---

## ⚠️ Canvas writes go through the toolkit (constitutional — never overridden)

**Grades and comments reach Canvas ONLY through a sanctioned `lib/tools/` writer:**
`grader_push.py` (submission feedback) or `grader_standing.py` (the standing column).
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

Confirm scope before every write — master vs blueprint vs section. `request_confirmation()`
is required before Canvas writes.

---

## Working style

Every contributor — human or LLM — operates under the behavioral discipline in
`Make-AI-Agents/knowledge/behavioral_discipline.md` (when the upstream clone is
populated) or the equivalent loaded via the host tool's skill system: read before
claiming, plan before acting, stop on the first defect, find root causes, generate
exactly what was asked (no speculative additions), mistake-proof outputs, and respect
intent without drift. The four **no-override** principles apply unconditionally:
**P-001 Read Before Claiming, P-003 Stop on Defect, P-007 Pull Don't Push, P-010
Respect Intent.**

**Toyota Production System discipline:** *Genchi Gembutsu* (verify with real data —
when you say "probably", STOP and check), *Jidoka* (write tests with code; a red test
blocks progress), *Poka-yoke* (design mistakes out). Quality loop: Prevent → Detect →
Verify; on a defect, fix it, verify with real data, then add an automated guard.

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
│   └── tests/             ← pytest
├── .claude/skills/        ← operating-mode skills (grading, course-build, audit, …)
├── scaffold/              ← copy-once starters (.gitignore, .env.example)
├── docs/, examples/, README.md, CHANGELOG.md
```

**Consumer usage (v1.6+):** a course repo clones `canvas-toolbox` into its root
(gitignored), runs `cb_init.py` to create course files (.env, .gitignore, AGENTS.md)
at course root, and runs tools from there: `uv run python canvas-toolbox/lib/tools/<script>`.
Update: `cd canvas-toolbox && git pull` — toolkit code updates; course files
untouched. When in a consumer repo and `canvas-toolbox/` is behind latest, surface
[`docs/UPGRADING.md`](docs/UPGRADING.md).

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

_Last updated: 2026-07-28._ Latest few releases only; full history in
[`CHANGELOG.md`](CHANGELOG.md).

- **v1.7.31–1.7.39 (grading-safety + tooling train, 2026-07-27/28):** TTY-only push
  confirmation (#241); `grader_standing` standing-column tool; `grade_guardian` now
  catches bypass scripts at create/edit **and run**; engagement-audit auto-dates from
  Canvas + includes inactive students; disclosure-tag menu (`--disclosure
  ai|hybrid|script`); `build_deid_master` dedups multi-section students.
- **v1.7 offline mode (v1.7.0, 2026-07-12):** tools read a local `course/`; 7 audits
  gained `--local`; `.imscc` round-trip (`offline_import` → edit → `imscc_record`).
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

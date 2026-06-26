# Canvas Toolbox

[![CI](https://github.com/chaz-clark/canvas-toolbox/actions/workflows/ci.yml/badge.svg)](https://github.com/chaz-clark/canvas-toolbox/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)

**FERPA-safe AI-assisted Canvas LMS toolkit. Your voice. Your accountability. Your students' privacy.**

> This is not an AI grader. It is how an instructor uses AI to grade *with* them — staying the author of every grade and every word the student reads.

---

## What it looks like in practice

When an instructor's grading workflow includes a regression, the tool stops it before it reaches the student:

```
$ uv run python lib/tools/grader_push.py --challenge-dir grading/kc1 --push

Assignment 16958677: 22 Canvas submissions, 22 review rows.

  pushed KC1-A1B2C3: — → 3.75
  pushed KC1-D4E5F6: — → 3.5
  ⛔ [REGRESSION] KC1-G7H8I9: uid=12345: 3.75 → 3.5
      — refusing to LOWER (pass --allow-lower to permit)
  pushed KC1-J2K3L4: 3.0 → 3.5

Pushed 21/22; 1 regression row skipped (--allow-lower forces it through;
manual review recommended).
```

Eleven coded safety gates like this one stand between AI-assisted grading and the student's gradebook — accumulated from real lived failures, not speculative design. Every gate was driven by a documented incident in production grading.

---

## Why this exists

Two faculty teaching the same Canvas course shouldn't have to choose between *AI does the grading and signs the AI's name to it* and *the instructor does every comment by hand*. Both have real costs. The first surrenders pedagogical authorship; the second doesn't scale.

Canvas Toolbox is the third option: **AI-assisted grading where the instructor stays the author.** The AI helps produce comments in the instructor's voice. The instructor reviews and approves every grade. The student sees their professor — not "AI Grader" — as the author of the feedback.

### What changes

| | AI-grading-as-a-service | Canvas Toolbox |
|---|---|---|
| **Comment authorship** | "AI Grader" — students KNOW it's AI | The instructor — their voice, their accountability |
| **FERPA boundary** | Trust the vendor's tenant | Two-zone architecture: cloud sees keys only, never names |
| **LLM provider** | Locked to one vendor | Brain-agnostic — Claude / GPT / Gemini / local Ollama |
| **Canvas auth** | One institutional key | Per-faculty Canvas token (faculty's own login) |
| **Adoption gate** | Institution must procure / contract | Faculty pulls and runs — no procurement |

The architectural commitment ("instructor stays the author") isn't rhetoric. It's enforced in code: when an instructor exports their grader to share with another faculty teaching the same course, their personal voice file is **refused by the export** by design. The receiving faculty builds their own voice. Both faculty's students hear their own professor.

---

## What you can trust

Eleven production safety gates and three architectural commitments — each driven by a documented incident, each landed within hours of being filed:

### Architectural commitments

- **FERPA two-zone architecture** — the cloud sees opaque keys (`KC1-A1B2C3`); only the local zone has names. The AI never reads a student name. Files on disk are keyed by `user_id`, never by name.
- **Voice-preservation contract** — per-instructor voice files are NEVER copied, exported, or shared between faculty. Each instructor's voice is theirs alone; the system is built to keep it that way.
- **Brain-agnostic LLM** — Claude, GPT, Gemini, or local Ollama. The toolkit doesn't lock you into a vendor.

### Safety gates (each one is a refused-by-default behavior with an explicit opt-out)

| # | The gate | What it prevents |
|---|---|---|
| 1 | **Pull-latest-by-default** (#103) | Grading a stale attempt-1 file when the student has resubmitted attempt-2 |
| 2 | **Grading-type validation** (#99) | Canvas silently coercing `(held)` to `incomplete` on a pass/fail assignment |
| 3 | **3-pass consensus enforced** (#95) | Single-pass grading slipping through without inter-rater-reliability check |
| 4 | **Regression direction gate** (#96) | A re-grade silently lowering a student's existing grade |
| 5 | **Existing-grade awareness** (#96 part 3) | Grading cold without knowing the student already has a Canvas grade |
| 6 | **Human-review gate** (#97) | An agent self-attesting review with `--yes` instead of a human typing 'reviewed' |
| 7 | **Inline triage of student replies** (#98) | Skipping a held row without seeing why the student replied |
| 8 | **Uncalibrated-cohort warning** (#101) | Unanimous consensus reading as confidence when the rubric itself was wrong |
| 9 | **Student-facing task spec as source-of-truth** (#102) | Grading against what the solution code happens to do, not what students were asked |
| 10 | **Group-assignment first-class workflow** (#100) | Re-grading 21 identical group-submission rows independently with inconsistent comments |
| 11 | **Cross-faculty sharing with voice-preservation** (v0.67.0) | Exporting a grader package and accidentally locking the receiving faculty into the sending faculty's voice |

Every gate refuses by default; every gate has a documented opt-out flag for the rare intentional case (e.g., `--allow-lower` for a legitimate academic-integrity reversal). Operators can audit which gates fired in a push from the per-row console output and the `.push_log.md` audit trail.

**Total tests in the verification suite: 439.** Every safety gate has unit tests covering the lived failure mode + the bypass path.

---

## Quick start

The toolkit installs as a single Python package; agents pick it up automatically when you run the included install script.

```bash
git clone https://github.com/chaz-clark/canvas-toolbox.git
cd canvas-toolbox
./scripts/install.sh
```

Then point your AI assistant at the repo. The toolkit supports any of:

- **Claude Code** (keyless-by-default; faculty use their existing subscription)
- **Cursor / Continue.dev / Cline** (also work; see [`INSTALL.md`](INSTALL.md) Step 2)
- **Local Ollama** (FERPA-strict / cost-conscious deployments)

For institutions with API keys (Anthropic, OpenAI, or Azure OpenAI), the `grader_grade.py` orchestrator runs the grading pipeline programmatically. For BYUI-style institutions where faculty can't get API keys, the keyless-agent path is the production default — the agent under the operator's existing subscription IS the grader.

**Full install + your-IDE-of-choice setup:** [`INSTALL.md`](INSTALL.md) *(extracted from this README in the marketing pass — TODO if not yet present)*.

---

## What it does

The toolkit covers two workflow categories:

### Auditing your course (read-only)

| Audit | What it checks |
|---|---|
| **Full health sweep** — `course_audit.py --full` | 11 read-only audits composed (rubrics · syllabus · outcomes · alignment chain · learning model · formative variety · grading structure · grading load · accessibility · workload) |
| **Module + item visibility** | Items students can't find; empty modules; broken module structure |
| **Date validation** | Due dates in the right window, in the right order, not duplicated |
| **Outcome alignment chain** | Rubric criteria → module outcomes → course outcomes — does the chain actually connect? |
| **Pedagogy phase coverage** | Does each module exercise BYUI Learning Model / Kolb / Hattie 3-phase / Merrill's First Principles? |
| **WCAG 2.1 AA aid** | Alt-text, captions, headings, reading level, color-only signaling, distracting elements |
| **Syllabus completeness** | BYU-I 25-item rubric scored; link-presence detection for required policy links |

Each audit produces a paired `.md` + `.pdf` report when you use `--report <name>.md`.

**Full audit-tool catalog:** [`OPERATIONS.md`](OPERATIONS.md) *(TODO if not yet present)*.

### Grading an assignment (FERPA-safe, instructor-author-first)

Fetch → de-identify → grade (3-pass consensus) → review → push. The AI never sees a student name. The instructor reviews and approves every grade. Gated end-to-end:

1. **Fetch** — `grader_fetch.py` pulls submissions keyed by user_id (no name in any filename); detects resubmissions and pulls the latest attempt
2. **De-identify** — adapters for docx / databricks / pdf / xlsx / jupyter; output is `submissions_deid/<KEY>.<ext>`
3. **Grade** — 3 independent grader passes per submission; consensus + spread → NEEDS-REVIEW queue (default: agent-in-the-loop on the operator's existing subscription; optional: `grader_grade.py` orchestrator for keyholders)
4. **Review** — instructor reads `_all_comments.md`, edits in their voice, the toolkit syncs back to per-student files
5. **Push** — `grader_push.py` with `--mark-reviewed` gate; eleven safety gates run before each grade reaches Canvas

**Full grading pipeline:** [`grading_readme.md`](grading_readme.md) — canonical folder layout + 8-step pipeline + dual-push pattern + setup interview.

---

## Sharing your grader with another faculty

When two faculty teach the same Canvas course, the second one shouldn't start from scratch. v0.67.0 ships `grader_export.py` + `grader_import.py` for cross-faculty sharing.

```bash
# Faculty A (the sender) bundles their course substrate:
uv run python lib/tools/grader_export.py \
  --course-label "DS 250 — Data Science for Business" \
  --out ds250-share-2026-06.zip

# Faculty B (the receiver) imports it:
uv run python lib/tools/grader_import.py --zip ds250-share-2026-06.zip
```

**What's IN the export:** rubrics, task specs, per-challenge configs, course-level voice pitfalls (course-content insights, NOT instructor voice), and a manifest documenting the canvas-toolbox version.

**What's NEVER in the export:** the sending faculty's per-instructor voice file, any student submissions, any feedback files, any grading artifacts, any identity bridges. Defense-in-depth: a FERPA blacklist refuses to write OR extract any of these files even if a manifest tried to include them.

**Version compatibility:** if the receiver's canvas-toolbox is older than the export's required version, `grader_import.py` HARD REFUSES with the exact upgrade command. No silent feature-mismatch failures.

The voice-preservation contract is reasserted in the receiver's README inside the ZIP: *"Your voice is the asset. The imported substrate is a starting point."* Faculty B runs the voice articulation interview from [`voice_coaching_knowledge.md §5`](lib/agents/knowledge/voice_coaching_knowledge.md) (~30 min) to build their own voice file — they never see Faculty A's.

---

## Who uses it

- **BYU-Idaho** (institutional pilot) — multiple faculty across DS 250, DS 460, and CE 162 (Land Surveying)
- **DS 250 Online** — ~448 student-cohort observations across 27 sections (the deepest production validation; the 11 safety gates were driven by lived failures in DS 250 grading)
- **CE 162 Land Surveying** — first non-DS adoption (filed the group-assignment workflow enhancement that became v0.64.0 with a fully-worked local prototype)

If you're piloting at another institution: file an issue ([`cb-report-bug`](#sharing-back-with-the-project)) — adoption stories help shape the next safety gate.

---

## Sharing back with the project

Three lightweight paths, all under one tool:

```bash
./bin/cb-report-bug    # report a bug (auto-prefix: bug:)
./bin/cb-report-bug    # request a feature (auto-prefix: enhancement:)
./bin/cb-share         # share something you built locally (auto-prefix: share:)
```

These open your editor for a description, scrub PII locally (names, emails, `/Users` paths), bundle your toolkit version + last 150 log lines + sanitized cwd, and post to a Cloudflare-fronted intake worker that files the GitHub issue using the maintainer's PAT. No GitHub account required.

Standard PRs are also welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for the fork → branch → PR shape.

**The bug-intake loop is the heartbeat of this project.** Eleven issues filed via the worker have closed in the last three days — every one drove a coded safety gate that's now live. If you find a hole, fill it via the worker; the loop closes within hours.

---

## License + acknowledgments

MIT. See [`LICENSE`](LICENSE).

Built at BYU-Idaho. Designed for all instructors. Works with any Canvas institution.

The architecture (FERPA two-zone, voice-preservation contract, consensus-based grading, push-side safety gates, cross-faculty sharing) reflects pedagogical research from Hattie & Timperley, Wiggins, Dweck, Brookhart, Cognitive Load Theory, Hammond's warm-demander pedagogy, and Black & Wiliam — distilled in [`lib/agents/knowledge/`](lib/agents/knowledge/README.md) and applied as Standard Work in the grader pipeline.

---

## Current version

**v0.67.1** — 11 production safety gates across 11 closed issues; 439 unit tests; ~70 versioned releases since v0.1. See [`AGENTS.md`](AGENTS.md) Active Context for the running release log + per-feature lived-experience rationale.

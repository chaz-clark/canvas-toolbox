# Canvas Toolbox

[![CI](https://github.com/chaz-clark/canvas-toolbox/actions/workflows/ci.yml/badge.svg)](https://github.com/chaz-clark/canvas-toolbox/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)

**FERPA-safe AI-assisted Canvas LMS toolkit. Your voice, your choice, you're always in the loop. Your students' privacy is #1.**

> **This is** how an instructor uses AI as a *tool* — staying the author of everything in Canvas including grades and every word the student reads.
>
> **This is NOT** an AI grader. The AI doesn't sign its name to the comment. You do.

Built at BYU-Idaho. Designed for all instructors. Works with any Canvas institution. You don't have to be a developer — the agent handles the technical bits; you answer its questions.

---

## What it looks like in practice

A consensus grading run finishes. Three things land in your review folder. Nothing pushes to Canvas yet — that's your call:

```
$ uv run python lib/tools/grader_consensus.py --challenge-dir grading/kc1

Consistency over 22 submissions (3 graders):
  exact 16/22, within 0.25 20/22, within 0.5 22/22; mean spread 0.07

NEEDS-REVIEW queue (spread ≥ 0.5): 2 submissions
  KC1-G7H8I9: graders [3.0, 3.5, 4.0] → consensus 3.5 (spread 1.0)
  KC1-M2N3O4: graders [2.5, 3.0, 3.5] → consensus 3.0 (spread 1.0)

  → feedback/_all_comments.md  (22 comments compiled for your review)
  → feedback/_consensus.csv    (per-grader scores + spread + flags)
  → feedback/<KEY>.md          (22 per-student evidence files — one per submission)

Open _all_comments.md to read + edit comments in your voice.
Nothing pushes to Canvas until you mark reviewed.
```

That's the grading workflow. The toolbox does more — audits, sync, sharing, semester rollout. Each one ends with **your review surface ready** and **you in control of what reaches Canvas**.

---

## What you can ask your AI agent to do

Nine workflows. Each one is a prompt your agent can act on.

| You want to… | Ask your agent | What happens |
|---|---|---|
| **Pull your Canvas course to your computer** | *"Pull my Canvas course into a local folder so I can start working with it"* | Mirrors all modules, pages, assignments, quizzes, discussions, syllabus into a `course/` folder. Edit any file locally; push back when ready. |
| **Get a quick health check** | *"Run a course health audit"* | 4-audit summary in ~30 seconds (rubrics, syllabus, outcomes, outcome quality) → verdict + top things to fix. |
| **Run the full pre-publish sweep** | *"Run the full course health sweep and share the results"* | 11 read-only audits composed into one report — alignment chain, learning model, accessibility, workload, grading load, formative variety. PDF + MD per finding. |
| **Build a Course Map + Schedule** | *"Build a Course Map and 14-week schedule from this course"* | Architects-of-Learning–style map: CLOs, per-module outcomes, 14-week pacing analysis. |
| **Pull New Quiz response data** | *"Pull the per-student responses from quiz <id>"* | The New Quizzes API doesn't expose responses directly; the toolkit reads them via the student-analysis report. FERPA-safe by default (uid-keyed; names opt-in). |
| **Grade an assignment end-to-end** | *"Grade the KC1 assignment"* | Fetch → de-identify → 3-pass consensus → review surface (`_all_comments.md`) → push gated behind `--mark-reviewed`. You approve every grade. |
| **Run a UW / UF check (Title IV)** | *"Run a UW check with UF date 2026-04-15"* or *"Last participation report"* | Classifies each enrolled student as ACTIVE / UW / UF / NEVER_PARTICIPATED by their last academically related activity vs your UF cutoff. PDF + MD report drops in **~/Downloads/** (outside the repo — FERPA tier 3). Compliant with 34 CFR 668.22 + the 2025-2026 FSA Handbook (verified 2026-06-26). |
| **Share your grader with another faculty teaching the same course** | *"Bundle this course's rubrics and configs to share with another faculty"* | Exports a ZIP with rubrics, task specs, configs, course-level pitfalls. Your personal voice file is REFUSED by the export — by design. They build their own voice. |
| **Roll out a new semester** | *"Sync my master course to the spring section"* | Master → Blueprint; Canvas handles section distribution. Safety gates keep section edits from leaking back to master. |

Each workflow has a deeper section below. Most non-technical faculty drive the toolkit entirely by asking their agent — no terminal required after setup.

---

## Why this exists

Your course is a document. The boring parts — sync, audit, grade, share, roll out a new semester — shouldn't be manual click-through work. They should be **your call, with the boring work automated, and you in the loop on every meaningful decision.**

The wedge moment is grading. Two faculty teaching the same Canvas course shouldn't have to choose between:

1. **AI does the grading and signs the AI's name to it.** Students see "AI Grader" as the comment author.
2. **The instructor does every comment by hand.** Doesn't scale past 30 students.

Canvas Toolbox is the third option: **AI-assisted everything where the instructor stays the author.** The agent does the legwork. The instructor reviews and approves. The student sees their professor — not "AI Grader" — as the author of the grade and the words.

### What changes

| | Canvas UI alone | Canvas Toolbox |
|---|---|---|
| **Editing course content** | Click through Canvas one item at a time | Pull to your computer; edit in any text editor; push back |
| **Auditing your course** | Hope nothing's broken | 11 read-only audits compose one health report (PDF + MD) |
| **Grading at scale** | Manual click-through SpeedGrader | FERPA-safe AI-assisted; you stay the author of every word |
| **Title IV UW/UF reporting** | Manually trawl SpeedGrader + Discussions + Quizzes per student at term-end | One command → classified report in `~/Downloads/`; compliant with 34 CFR 668.22 |
| **Sharing with another faculty teaching the same course** | Email files; lose track of versions | Bundle + import with voice-preservation built in |
| **Rolling out a new semester** | Manually copy modules + fix broken IDs | Sync master to Blueprint; Canvas handles section distribution |
| **Pulling New Quiz response data** | Not directly possible via the API | Via the student-analysis report; uid-keyed by default |

**Voice-preservation is in the code, not just in the docs.** When you export a grader to share with another faculty teaching the same course, your personal voice file is REFUSED by the export — by design. The receiving faculty builds their own voice. Both faculty's students hear their own professor.

---

## What you can trust

### Architectural commitments (apply everywhere)

- **FERPA two-zone** — the cloud sees opaque keys (`KC1-A1B2C3`). Only the local zone has names. The AI never reads a student name. Files on disk are keyed by `user_id`, never by name.
- **Voice-preservation** — per-instructor voice files are NEVER copied, exported, or shared between faculty. Your voice is yours alone.
- **Brain-agnostic LLM** — Claude, GPT, Gemini, or local Ollama. You're not locked into a vendor.
- **Read-only by default for audits** — every audit reports findings; none of them change anything in your Canvas course.
- **Local files are source of truth** — Canvas is the sync target, not the source. Nothing pushes without your explicit approval.

### Grading safety gates (the highest-stakes workflow)

Eleven gates between AI-assisted grading and the student's gradebook. Each one driven by a documented incident. Each one shipped within hours of being filed. Every gate refuses by default; every gate has an explicit opt-out flag for the rare intentional case.

| # | The gate | What it prevents |
|---|---|---|
| 1 | Pull-latest-by-default (#103) | Grading a stale attempt-1 file when the student has resubmitted attempt-2 |
| 2 | Grading-type validation (#99) | Canvas silently coercing `(held)` to `incomplete` on a pass/fail assignment |
| 3 | 3-pass consensus enforced (#95) | A single grading pass slipping through without inter-rater check |
| 4 | Regression direction gate (#96) | A re-grade silently lowering a student's existing grade |
| 5 | Existing-grade awareness (#96 part 3) | Grading cold without knowing the student already has a Canvas grade |
| 6 | Human-review gate (#97) | An agent self-attesting review with `--yes` instead of you typing 'reviewed' |
| 7 | Inline triage of student replies (#98) | Skipping a held row without seeing why the student replied |
| 8 | Uncalibrated-cohort warning (#101) | Unanimous consensus reading as confidence when the rubric itself was wrong |
| 9 | Student-facing task spec as source-of-truth (#102) | Grading against what the solution code happens to do, not what students were asked |
| 10 | Group-assignment first-class workflow (#100) | Re-grading 21 identical group-submission rows with inconsistent comments |
| 11 | Cross-faculty sharing with voice-preservation (v0.67.0) | Exporting a grader and accidentally locking the receiver into your voice |

Audit which gates fired in a push from the per-row console output + `.push_log.md`. **Total tests covering these + the rest of the toolkit:** 439.

---

# Getting started

Three small choices before the toolkit is yours:

1. **Pick an IDE** — the app where you'll open files and talk to your AI assistant.
2. **Pick an AI assistant** — use whichever AI subscription you already have, so you don't pay twice. (If you don't have one, there's a generous free path.)
3. **Get the toolkit running** — your AI agent walks you through it (recommended), or do the steps yourself.

You don't have to be a developer. The agent handles the technical bits; you answer its questions.

---

## Step 1 — Pick your IDE

An **IDE** ("integrated development environment") is the app you'll work in. Pick one, download it, and install it like any other application.

| If you… | Use | Free? | Download |
|---|---|---|---|
| **have no strong preference** *(the safe default)* | **Visual Studio Code** — the standard, with the largest selection of AI assistant extensions | yes | [code.visualstudio.com](https://code.visualstudio.com/) |
| **want the AI to drive** *(and want a generous free option built in)* | **Antigravity IDE** — Google's agent-first IDE; Gemini AI is built in, no separate extension needed | yes (public preview, full Gemini 3 Pro, no usage limits announced) | [antigravityide.org](https://antigravityide.org/) |
| **teach data science** *(R, Python, Quarto)* | **Positron** — Posit's data-science IDE, with a built-in AI assistant called *Positron Assistant* | yes | [positron.posit.co/download](https://positron.posit.co/download.html) |

> ⚠️ **About Antigravity IDE:** it has Gemini built in and is **locked to Gemini** — you can't plug a ChatGPT, Claude, or Copilot subscription into it. Pick Antigravity if you're happy using Gemini (free now, paid tiers available). If you have a ChatGPT, Claude, or Copilot subscription you want to use, pick **Visual Studio Code** here and the matching extension in Step 2.

---

## Step 2 — Pick your AI assistant

Use the subscription you **already have** so you don't pay twice. In your IDE, open the **Extensions panel** (the icon that looks like four squares on the side bar), search by the name below, click **Install**, then **sign in** when it prompts you.

| You already have… | Install this | Sign in with | Link |
|---|---|---|---|
| **ChatGPT** *(Plus / Pro / Business / Edu / Enterprise)* | **Codex — OpenAI's coding agent** | your ChatGPT account | [Marketplace](https://marketplace.visualstudio.com/items?itemName=openai.chatgpt) |
| **Claude** *(Pro / Team / Max)* | **Claude Code** *(official Anthropic extension)* | your Claude account | [Marketplace](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code) |
| **GitHub Copilot** | **GitHub Copilot** + **GitHub Copilot Chat** | your GitHub account | [Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) · [Copilot Chat](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot-chat) |
| **Local models (Ollama)** *(no subscription, no cloud, data stays on your machine)* | **Continue.dev** (preferred) — or **Cline** as an alternative — both open-source agentic extensions; configure with your local Ollama models | no account — set the Ollama backend in the extension's settings | [Continue](https://marketplace.visualstudio.com/items?itemName=Continue.continue) · [Cline](https://marketplace.visualstudio.com/items?itemName=saoudrizwan.claude-dev) · [Ollama](https://ollama.com) |
| **None of those** | Use **Antigravity IDE** instead of VS Code (from Step 1) — it's free, no extension to install, Gemini is built in | a Google account | [antigravityide.org](https://antigravityide.org/) |

> 💡 **A common mix-up:** GitHub Copilot is a *separate* Microsoft/GitHub subscription — it does **not** connect to a ChatGPT account, even though they're both AI tools. If you have ChatGPT Plus, install **Codex** (first row). If you have Copilot, install **Copilot** (third row). Each is tied to its own account.

> 🦙 **About Ollama + Continue.dev / Cline:** Both are open-source and fully agentic — they read files, run terminal commands, edit code, the same workflow as the cloud extensions above. **Continue.dev** is the safer first pick (Apache 2.0, broader adoption, more stable backend abstraction). **Cline** is a strong alternative — newer but capable for the same workflow. Both are local-first; nothing leaves your machine. Good fit for FERPA-strict institutions or cost-conscious workflows. The honest trade: today's local code models (e.g. `qwen2.5-coder`, `deepseek-coder-v2`, `codestral`) handle deterministic + structural work well, but need extra calibration for nuanced prose grading compared to Claude / GPT-4. Start with a recent code-focused model; tune from there.

> 📓 **Positron users:** Positron has a built-in **Positron Assistant** — you don't need to install an extension for AI help. Skip Step 2 and go to Step 3.

---

## Step 3 — Get the toolkit running

Three paths. **Most non-technical faculty use Option A.** Technical users with a terminal habit start with the TL;DR.

### TL;DR — one-line install (macOS / Linux)

If you already have `git` and a terminal habit:

```bash
curl -fsSL https://raw.githubusercontent.com/chaz-clark/canvas-toolbox/main/scripts/install.sh | bash
```

The script installs `uv` if missing, clones `canvas-toolbox/` into your current directory, and runs `cb-init`. It halts after writing a `.env` stub — fill in your `CANVAS_API_TOKEN` + `CANVAS_BASE_URL`, then:

```bash
cd canvas-toolbox && uv run python lib/tools/cb_init.py
```

Total time on a fresh machine: ~3 minutes.

**Windows users**, or anyone who'd rather have their AI assistant walk them through it: skip the one-liner and use **Option A** below.

---

### Option A — Start here: your agent sets it up

Create a new empty folder on your computer, open it in the IDE you set up in Steps 1 and 2, then give your AI assistant this prompt:

> *"Help me set up Canvas Toolbox for my Canvas course. The toolkit is at https://github.com/chaz-clark/canvas-toolbox — please clone it, install dependencies, and walk me through connecting it to my course."*

The agent checks what's installed, handles anything missing, and guides you through the rest. You just answer its questions.

**Agent setup checklist** *(the agent follows these steps; you respond when asked)*

1. **Check git** — `git --version`. If missing:
   - Mac: `xcode-select --install`
   - Windows: `winget install --id Git.Git -e --source winget` (or download from [git-scm.com/download/win](https://git-scm.com/download/win))

2. **Clone the toolkit**
   ```bash
   git clone https://github.com/chaz-clark/canvas-toolbox.git canvas_toolbox
   ```

3. **Check uv** — `uv --version`. If missing:
   - Mac/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

4. **Install dependencies** (one-time)
   ```bash
   cd canvas_toolbox && uv sync && cd ..
   ```

5. **Create config files**
   ```bash
   cp canvas_toolbox/scaffold/.env.example .env
   cp canvas_toolbox/scaffold/gitignore .gitignore
   ```

6. **Collect Canvas credentials** — you'll need:
   - **Course ID** — the number after `/courses/` in your Canvas course URL
   - **API token** — Canvas → Account → Settings → Approved Integrations → New Access Token (requires instructor or admin role)
   - **Institution URL** — your Canvas login address (e.g., `https://byui.instructure.com`)

7. **Fill in `.env`** with your credentials:
   ```
   CANVAS_API_TOKEN=your_token
   CANVAS_BASE_URL=https://your-institution.instructure.com
   CANVAS_COURSE_ID=123456
   ```

8. **Pull the course**
   ```bash
   uv run python canvas_toolbox/lib/tools/canvas_sync.py --init
   ```
   This mirrors the entire course — modules, pages, assignments, quizzes, discussions, syllabus — into a `course/` folder. Takes about a minute.

---

### Option B — Manual setup

Use this if you prefer to run each step yourself, or if your AI tool doesn't run terminal commands.

**Open a terminal:**
- **Mac:** Cmd + Space → type "Terminal" → Enter
- **Windows:** Windows key → type "PowerShell" → Enter

#### Fast path — `cb-init` (3 lines, fully interactive, any OS)

```bash
git clone https://github.com/chaz-clark/canvas-toolbox.git canvas-toolbox
cd canvas-toolbox
uv run python lib/tools/cb_init.py
```

`cb-init` is **idempotent** — re-running is safe and fast. It installs `uv` if missing, installs Python 3.14, writes a `.env` stub (then stops so you can fill in your Canvas credentials), installs all dev tools, smoke-tests your Canvas API token, and surfaces `AGENTS.md`.

Useful flags:

| Flag | Use |
|---|---|
| `--check` | Dry-run: shows what each step would do, writes nothing |
| `--yes` | Skip all y/n prompts (for CI / Codespaces) |
| `--skip-playwright` | Skip the 92 MB Chromium download |

If `cb-init` runs cleanly, skip the rest of Option B and go straight to **"Pull your course"**.

#### Manual long path

```bash
git clone https://github.com/chaz-clark/canvas-toolbox.git canvas_toolbox
cd canvas_toolbox && uv sync && cd ..
cp canvas_toolbox/scaffold/.env.example .env
cp canvas_toolbox/scaffold/gitignore .gitignore
```

Then fill in `.env` with your Canvas credentials (see the agent checklist above, step 6 + 7).

> **Can't see the `.env` file?** Its name starts with a dot, which hides it by default. **Mac:** Cmd + Shift + . in Finder. **Windows:** File Explorer → View → check "Hidden items".

**Pull your course:**
```bash
uv run python canvas_toolbox/lib/tools/canvas_sync.py --init
```

---

### Option C — A colleague is setting it up for you

Gather three pieces of information and hand them over:

- **Course ID** — the number after `/courses/` in your Canvas course URL
- **API token** — Canvas → Account → Settings → Approved Integrations → New Access Token (requires instructor or admin role)
- **Institution URL** — your Canvas login address (e.g., `https://byui.instructure.com`)

Share them in this format:

```
CANVAS_API_TOKEN=your_token_here
CANVAS_BASE_URL=https://byui.instructure.com
CANVAS_COURSE_ID=123456
```

They'll handle the rest.

---

### Already have an older canvas-toolbox setup? Migrate it.

If you have a Canvas course repo with an *older* canvas-toolbox layout — vendored as a git subtree, or in a folder your parent repo still tracks — there's a one-command migration:

```bash
python3 canvas-toolbox/scaffold/migrate_to_clone_layout.py
```

**Dry-run by default** — inspects your repo, reports its state, prints the exact plan it would run. Re-run with `--apply` to execute. Backs up existing canvas-toolbox content to `/tmp/` before changing anything. Safe to run on a setup that's already correct (reports *"Already on the new layout. Nothing to do."*).

---

# Auditing your course

Read-only. Reports findings, never changes anything. Run as often as you like.

**Not sure where to start?** Run the health check below — it composes the rubric, syllabus, and outcome audits and gives you one summary.

## "Give me a full health check"

Two tiers — pick by where you are in the course lifecycle.

### QUICK — mid-authoring, ~30 seconds

**Ask your agent:** *"Run a course health audit"*

```bash
uv run python canvas_toolbox/lib/tools/course_audit.py
```

Runs the four core read-only audits — rubric coverage, rubric quality, syllabus completeness, outcome quality — and composes one report: overall verdict (**HEALTHY / REVIEW / NEEDS ATTENTION**) plus a "top things to fix" list.

### FULL — pre-publish / pre-semester sweep

**Ask your agent:** *"Run the full course health sweep and share the results"*

```bash
uv run python canvas_toolbox/lib/tools/course_audit.py --full
```

Composes 11 read-only audits into one report — rubrics · syllabus · outcomes · alignment chain · learning model · formative variety · grading structure · grading load · accessibility · workload. Each finding gets a single page with what was checked, what was found, and what to do.

Every audit produces a paired `.md` + `.pdf` when you use `--report <name>.md`. PDF is the faculty-friendly default; MD is the editable source.

## What else the audits cover

- **Items students can't find** — broken module structure, items not linked from any module
- **Date validation** — due dates in the right window, in the right order, not duplicated
- **Outcome alignment chain** — rubric criteria → module outcomes → course outcomes (does the chain actually connect?)
- **Pedagogy phase coverage** — does each module exercise BYUI Learning Model / Kolb / Hattie 3-phase / Merrill's First Principles?
- **WCAG 2.1 AA aid** — alt-text, captions, headings, reading level, color-only signaling, distracting elements (aids review, doesn't certify compliance)
- **Unused files** — files sitting in Canvas that nothing links to
- **Course Map & Schedule** — Architects-of-Learning–style course map (CLOs, per-module outcomes, 14-week schedule, pacing analysis)
- **Syllabus scored against the BYU-I Completeness Rubric** — 25 specific items + link-presence detection for required policy links (Grievance / FERPA / Honor Code / Policy Library)
- **New Quiz response data** — the New Quizzes API doesn't expose per-student responses directly; `grader_fetch_nq_responses` reads them via the student-analysis report. FERPA-safe by default (uid-keyed; names opt-in via `--include-names`)

Full audit catalog + agent framework references: [`lib/agents/knowledge/README.md`](lib/agents/knowledge/README.md).

---

# Grading an assignment

Fetch → de-identify → grade → review → push. The AI never sees a student name. The instructor reviews and approves every grade. Gated end-to-end.

1. **Fetch** — `grader_fetch.py` pulls submissions keyed by user_id (no name in any filename); detects resubmissions and pulls the latest attempt
2. **De-identify** — adapters for docx / databricks / pdf / xlsx / jupyter; output is `submissions_deid/<KEY>.<ext>`
3. **Grade** — 3 independent grader passes per submission; consensus + spread → NEEDS-REVIEW queue. The default is **agent-in-the-loop on your existing subscription**; `grader_grade.py` is an optional orchestrator for institutions with API keys
4. **Review** — instructor reads `_all_comments.md`, edits in their voice, the toolkit syncs back to per-student files
5. **Push** — `grader_push.py` with `--mark-reviewed` gate. Eleven safety gates run before each grade reaches Canvas

The push surface refuses by default in the dangerous direction. Every refusal has a documented opt-out flag.

**Full grading pipeline:** [`grading_readme.md`](grading_readme.md) — canonical folder layout + 8-step pipeline + dual-push pattern + setup interview.

---

# Title IV last-participation audit (UW / UF reporting)

Federal Title IV (34 CFR 668.22) requires reporting a **last date of academically related activity** for any Title-IV-aid recipient who fails to complete the enrollment period. The R2T4 (Return of Title IV funds) calculation depends on it. Without this audit, the workflow is trawling SpeedGrader + Discussions + Quizzes per student at term-end.

```bash
uv run python lib/tools/course_engagement_audit.py --uf-date 2026-04-15
```

The audit:

1. Fetches each enrolled student's last engagement timestamp from **assignment submissions + quiz submissions + discussion entries** (per DOE: *"logging in is not sufficient"* — page views and `last_activity_at` deliberately excluded)
2. Classifies each student against the operator-provided UF cutoff:
   - **ACTIVE** — engagement on or after the UF date
   - **UW** — stopped engaging before UF date, passing-or-unknown grade
   - **UF** — stopped engaging before UF date AND failing — R2T4 candidate
   - **NEVER_PARTICIPATED** — enrolled but no engagement on record (no-show rule applies)
3. Re-identifies user_ids → names ONLY at the last step before writing the report
4. **Writes the named PDF + MD to `~/Downloads/`** — outside the repo entirely, so the LLM has no working-directory access to the student-named output. This is **FERPA tier 3** (see [`grader_knowledge.md §1`](lib/agents/knowledge/grader_knowledge.md))

**Title IV definitions verified:** 2026-06-26. The 6 canonical sources (CFR text, FSA Handbook chapters, Federal Register notice) are cached locally at [`lib/agents/knowledge/sources/title_iv/`](lib/agents/knowledge/sources/title_iv/) — re-runs of the audit don't require fresh web fetches. Refresh with:

```bash
uv run python lib/tools/update_title_iv_snapshot.py
```

The script reports **NEW / UPDATED / UNCHANGED / SUSPICIOUS** per source so material rule changes surface. **Next review of the cached Title IV sources is 2027-06-26** or sooner if DOE issues new R2T4 / distance-ed guidance. The Distance Ed + R2T4 final rules effective **2026-07-01** are the latest material change (and the most recent caching captures them).

Full audit documentation: [`course_engagement_audit_knowledge.md`](lib/agents/knowledge/course_engagement_audit_knowledge.md).

---

# Sharing your grader with another faculty

When two faculty teach the same Canvas course, the second one shouldn't start from scratch.

```bash
# You bundle your course substrate:
uv run python lib/tools/grader_export.py \
  --course-label "DS 250 — Data Science for Business" \
  --out ds250-share-2026-06.zip

# The receiving faculty imports it:
uv run python lib/tools/grader_import.py --zip ds250-share-2026-06.zip
```

**What's IN the export:** rubrics, task specs, per-challenge configs, course-level voice pitfalls (course-content insights, NOT instructor voice), and a manifest documenting the canvas-toolbox version.

**What's NEVER in the export:** your per-instructor voice file. Any student submissions. Any feedback files. Any grading artifacts. Any identity bridges. A FERPA blacklist refuses to write OR extract any of these — defense in depth.

**Version compatibility:** if the receiver's canvas-toolbox is older than the export's, `grader_import.py` REFUSES with the exact upgrade command. No silent feature-mismatch failures.

The receiver's README inside the ZIP says it plainly: *"Your voice is the asset. The imported substrate is a starting point."* The receiving faculty runs the voice articulation interview from [`voice_coaching_knowledge.md §5`](lib/agents/knowledge/voice_coaching_knowledge.md) (~30 min) and builds their own voice file. They never see yours.

Full sharing pattern: [`grader_knowledge.md §17`](lib/agents/knowledge/grader_knowledge.md).

---

# Who uses it

- **BYU-Idaho** (institutional pilot) — multiple faculty across DS 250, DS 460, and CE 162 (Land Surveying)
- **DS 250 Online** — ~448 student-cohort observations across 27 sections (the deepest production validation; the 11 safety gates were driven by lived failures in DS 250 grading)
- **CE 162 Land Surveying** — first non-DS adoption; filed the group-assignment workflow enhancement that became v0.64.0 with a fully-worked local prototype

If you're piloting at another institution, file an issue (see below). Adoption stories shape the next safety gate.

---

# Sharing back with the project

Three lightweight paths, all under one tool:

```bash
./bin/cb-report-bug    # report a bug (auto-prefix: bug:)
./bin/cb-report-bug    # request a feature (auto-prefix: enhancement:)
./bin/cb-share         # share something you built locally (auto-prefix: share:)
```

These open your editor for a description, scrub PII locally (names, emails, `/Users` paths), bundle your toolkit version + last 150 log lines + sanitized cwd, and post to a Cloudflare-fronted intake worker that files the GitHub issue using the maintainer's PAT. **No GitHub account required.** Roundtrip: ~1 second.

| You want to… | Use | What happens |
|---|---|---|
| **Report a bug** (toolkit deviated from documented behavior) | `cb-report-bug` with title `bug: <short description>` | Files an issue tagged `agent-submitted`. ~1 second. |
| **Request a feature** | `cb-report-bug` with title `enhancement: <short description>` | Same path; title prefix triages it. |
| **Share something you built** (a tool, config, workflow extension) | `cb-share` with title `share: <short description>` + a body that links or pastes the code | Same path; `share:` prefix tells the maintainer this is contribution-shaped. |
| **Push code via a PR** | Standard GitHub PR workflow | See [`CONTRIBUTING.md`](CONTRIBUTING.md). |

**Want shorter commands?** Put `bin/` on your PATH:

```bash
echo 'export PATH="'"$(pwd)"'/bin:$PATH"' >> ~/.zshrc   # or ~/.bashrc
source ~/.zshrc
# now: cb-init, cb-report-bug, cb-share work from anywhere
```

**Fallbacks** (work if `bin/` isn't on PATH):

```bash
uv run python lib/tools/cb_report_bug.py    # long-form, equivalent
gh issue create -R chaz-clark/canvas-toolbox  # if you have gh + a GitHub account
```

Or go directly: <https://github.com/chaz-clark/canvas-toolbox/issues/new>.

The bug-intake loop is the heartbeat of this project. Eleven issues filed via the worker have closed in the last three days — every one drove a coded safety gate. If you find a hole, fill it via the worker. The loop closes within hours.

---

# License + acknowledgments

MIT. See [`LICENSE`](LICENSE).

Built at BYU-Idaho. Designed for all instructors. Works with any Canvas institution.

The architecture (FERPA two-zone, voice-preservation contract, consensus-based grading, push-side safety gates, cross-faculty sharing) reflects pedagogical research from Hattie & Timperley, Wiggins, Dweck, Brookhart, Cognitive Load Theory, Hammond's warm-demander pedagogy, and Black & Wiliam — distilled in [`lib/agents/knowledge/`](lib/agents/knowledge/README.md) and applied as Standard Work in the grader pipeline.

---

**Current version:** v0.69.x · 11 grading safety gates · Title IV definitions verified 2026-06-26 (next review 2027-06-26) · 483 unit tests · ~70 versioned releases since v0.1. Running release log + per-feature rationale in [`AGENTS.md`](AGENTS.md) Active Context.

For help, see the doc tree above or file a `cb-report-bug` (~1 second roundtrip; no GitHub account needed).

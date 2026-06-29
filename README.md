# Canvas Toolbox

[![CI](https://github.com/chaz-clark/canvas-toolbox/actions/workflows/ci.yml/badge.svg)](https://github.com/chaz-clark/canvas-toolbox/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)

**FERPA-safe AI-assisted Canvas LMS toolkit. Your voice, your choice, you're always in the loop. Your students' privacy is #1.**

> **This is** how an instructor uses AI as a *tool* — staying the author of everything in Canvas including grades and every word the student reads.
>
> **This is NOT** an AI grader. The AI doesn't sign its name to the comment. You do.

Built at BYU-Idaho. Designed for all instructors. Works with any Canvas institution. You don't have to be a developer — the agent handles the technical bits; you answer its questions.

---

# Getting started

Three small choices before the toolkit is yours:

1. **Pick an IDE** — the app where you'll open files and talk to your AI assistant.
2. **Pick an AI assistant** — use whichever AI subscription you already have, so you don't pay twice. (If you don't have one, there's a generous free path.)
3. **Get the toolkit running** — your AI agent walks you through it (recommended), or do the steps yourself.

---

## Step 1 — Pick your IDE

An **IDE** ("integrated development environment") is the app you'll work in. Pick one, download it, and install it like any other application.

| If you… | Use | Free? | Download |
|---|---|---|---|
| **have no strong preference** *(the safe default)* | **Visual Studio Code** — the standard, with the largest selection of AI assistant extensions | yes | [code.visualstudio.com](https://code.visualstudio.com/) |
| **want the AI to drive** *(and want a generous free option built in)* | **Antigravity IDE** — Google's agent-first IDE; Gemini AI is built in, no separate extension needed | yes (public preview, full Gemini 3 Pro, no usage limits announced) | [antigravityide.org](https://antigravityide.org/) |
| **teach data science** *(R, Python, Quarto)* | **Positron** — Posit's data-science IDE, with a built-in AI assistant called *Positron Assistant* | yes | [positron.posit.co/download](https://positron.posit.co/download.html) |

> ⚠️ **About Antigravity IDE:** it has Gemini built in and is **locked to Gemini** — you can't plug a ChatGPT, Claude, or Copilot subscription into it. Pick Antigravity if you're happy using Gemini (free now, paid tiers available). If you have a ChatGPT, Claude, or Copilot subscription you want to use, pick **Visual Studio Code** here and the matching extension in Step 2.

> 🐳 **Advanced — running the toolkit across several courses at once:** If you teach multiple courses and want to work them in parallel, **[Orca](https://github.com/stablyai/orca)** ([onorca.dev](https://onorca.dev)) is an alternative to a single IDE. It's an agent-orchestration workspace — desktop app plus a mobile companion, on macOS / Windows / Linux — that runs several AI coding agents at the same time, each in its own isolated git worktree. You can drive one course's grading run while another course's health audit runs beside it, then review and merge each independently. It's agent-agnostic (not locked to any one AI vendor) and integrates with GitHub directly. This is power-user territory — most faculty should start with **Visual Studio Code** above and reach for Orca only once juggling several course repos becomes the bottleneck.

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

**Create an empty folder on your computer, open it in the IDE you set up in Steps 1 and 2, and paste this prompt to your AI assistant:**

> *"Help me set up Canvas Toolbox for my Canvas course. Please clone https://github.com/chaz-clark/canvas-toolbox into this folder, run `cb-init` to bootstrap everything, and walk me through filling in my Canvas credentials when it pauses."*

That's it. `cb-init` is our one-command bootstrap — it installs `uv` and Python, writes a `.env` stub, syncs dependencies, smoke-tests your Canvas API token, and is **idempotent** (safe to re-run). You'll just need to provide three pieces of information when it asks:

- **Course ID** — the number after `/courses/` in your Canvas course URL
- **API token** — Canvas → Account → Settings → Approved Integrations → New Access Token (requires instructor or admin role)
- **Institution URL** — your Canvas login address (e.g., `https://your-institution.instructure.com`)

Total time on a fresh machine: ~5 minutes (most of it is the agent installing dependencies in the background).

---

### If a colleague is setting it up for you

Just hand them those three pieces of information in this format:

```
CANVAS_API_TOKEN=your_token_here
CANVAS_BASE_URL=https://your-institution.instructure.com
CANVAS_COURSE_ID=123456
```

They'll handle the rest.

---

> **Already have an older canvas-toolbox setup?** Ask your agent to run `python3 canvas-toolbox/scaffold/migrate_to_clone_layout.py` — it dry-runs by default, reports what it would change, and only writes when you re-run with `--apply`.

---

## What you'll do most

Three core jobs — jump straight in, or skim the full workflow list further down.

| 🏗️ **Build & revise** | 🔍 **Audit & improve** | ✅ **Grade** |
|:-:|:-:|:-:|
| Add or revise modules, assessments, and rubrics in a course you already teach — or design a new one from scratch. Built backward from outcomes, guided by 20+ pedagogical knowledge files. | Run read-only health audits — alignment, accessibility, workload, Title IV UW/UF — and get a prioritized fix list. Nothing changes without your say-so. | Fetch → de-identify → 3-pass consensus → edit in your voice → push, gated end-to-end. The AI never signs its name; you do. |
| [Build or improve a course →](#architecting-a-course-with-ai-assistance) | [Audit your course →](#auditing-your-course) | [Grade an assignment →](#grading-an-assignment) |

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

Thirteen workflows. Each one is a prompt your agent can act on.

| You want to… | Ask your agent | What happens |
|---|---|---|
| **Pull your Canvas course to your computer** | *"Pull my Canvas course into a local folder so I can start working with it"* | Mirrors all modules, pages, assignments, quizzes, discussions, syllabus into a `course/` folder. Edit any file locally; push back when ready. |
| **Design or improve a course (AI architect)** | *"Help me design a new course on [topic]"* / *"Architect a new course"* / *"Improve the design of this course"* | Agent walks you through CLOs → assessments backward from outcomes → module sequence (Hattie / Merrill / Kolb) → rubrics → workload calibration. Uses 18+ pedagogical knowledge files. See [Architecting a course](#architecting-a-course-with-ai-assistance) below. |
| **Get a quick health check** | *"Run a course health audit"* | 4-audit summary in ~30 seconds (rubrics, syllabus, outcomes, outcome quality) → verdict + top things to fix. |
| **Run the full pre-publish sweep** | *"Run the full course health sweep and share the results"* | 11 read-only audits composed into one report — alignment chain, learning model, accessibility, workload, grading load, formative variety. PDF + MD per finding. |
| **Build a Course Map + Schedule** | *"Build a Course Map and 14-week schedule from this course"* | Architects-of-Learning–style map: CLOs, per-module outcomes, 14-week pacing analysis. |
| **Pull New Quiz response data** | *"Pull the per-student responses from quiz <id>"* | The New Quizzes API doesn't expose responses directly; the toolkit reads them via the student-analysis report. FERPA-safe by default (uid-keyed; names opt-in). |
| **Grade an assignment end-to-end** | *"Grade the KC1 assignment"* | Fetch → de-identify → 3-pass consensus → review surface (`_all_comments.md`) → push gated behind `--mark-reviewed`. You approve every grade. |
| **Run a UW / UF check (Title IV)** | *"Run a UW check with UF date 2026-04-15"* or *"Last participation report"* | Classifies each enrolled student as ACTIVE / UW / UF / NEVER_PARTICIPATED by their last academically related activity vs your UF cutoff. PDF + MD report drops in **~/Downloads/** (outside the repo — FERPA tier 3). Compliant with 34 CFR 668.22 + the 2025-2026 FSA Handbook (verified 2026-06-26). |
| **Give one student late-work accommodation** | *"Give student S-95DBB6 late-work grace for the rest of the semester"* / *"…starting from the last 2 weeks"* / *"…on assignment 1234 only"* | Writes per-student assignment overrides. Two flavors (drop close date OR shift dates forward) × four scoping modes (one assignment / whole semester / from a date / rolling window). PII-free via the [de-id master](#the-de-id-master--the-primitive-under-everything). See [Per-student late-work accommodation](#per-student-late-work-accommodation) below. |
| **Give one student extra time on timed quizzes** | *"Give student S-95DBB6 1.5x time on all timed quizzes"* / *"…2x time on quiz 1234"* | Writes per-student quiz extensions on classic Canvas quizzes — `--multiplier 1.5` adds 50% extra; `--multiplier 2.0` adds double time. `--all-timed` covers every timed quiz in the course; `--quiz-id` scopes to one. Untimed quizzes auto-skip. |
| **Apply a BYUI Accessibility Services letter** | *"Apply the SAS accommodations for this student"* / *"Run my .sas_accommodations.yml"* | Reads `grading/.sas_accommodations.yml` (produced by life-pm from your BYUI Outlook inbox), dispatches per accommodation key. **Canvas-tier** (quiz time extension 1.5x/2.0x, occasional extensions, test reschedule) auto-runs; **proctoring-tier** (Proctorio breaks, private testing room) + **policy-tier** (spelling/grammar, attendance, recording, etc.) surface as an instructor checklist. Audit log at `grading/.sas_accommodations_applied.log`. |
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

# Architecting a course with AI assistance

**Canvas Toolbox isn't only for existing courses — the agent can help you build one.**

The toolkit ships with **20+ pedagogical knowledge files** the agent reads when you're designing or redesigning a course. You stay the architect; the AI is the assistant — it asks questions, surfaces tradeoffs, and writes drafts you approve.

**What the agent has on hand:**

| Topic | Knowledge surface |
|---|---|
| **Backwards design** | Wiggins & McTighe Understanding by Design — outcomes → evidence → activities |
| **Designer thinking** | BYUI's 5-stage course-design process |
| **Learning models** | Hattie 3-phase (Surface → Deep → Transfer), Merrill's First Principles, Kolb experiential cycle, inverted Bloom's |
| **CLO quality** | BYUI Assurance of Learning 6-criteria rubric, Bloom's revised taxonomy, three domains (cognitive / affective / psychomotor) |
| **Assessment design** | Formative vs summative, evidence-centered design, AI-era productive friction |
| **Rubric design** | AAC&U VALUE rubrics + 4-criterion backbone; analytic / holistic / single-point / developmental |
| **Workload calibration** | Carnegie credit-hour budget + Wake Forest workload estimator |
| **Cognitive load** | Sweller's CLT — intrinsic / extraneous / germane load management |
| **Course design standards** | BYUI Campus Online + NWCCU cross-walk |
| **Content representation** | Multiple representations, accessibility (WCAG 2.1 AA), universal design |
| **Critical thinking** | Paul-Elder framework; embedding intellectual standards into tasks |
| **Course design language** | Shared vocabulary so the agent and faculty mean the same thing |

**Ask your agent:**

> *"Help me design a new course on [topic]. It's [X credits] / [length weeks]. The outcomes I have in mind are [...]."*
>
> Or, for an existing course you want to improve:
>
> *"Architect a redesign of this course — start with the CLOs and work outward."*

**The agent walks you through:**

1. **CLOs (Course Learning Outcomes)** — drafted and refined against the BYUI AoL 6-criteria rubric; measurable, aligned, appropriately scoped
2. **Assessment plan (backward design)** — what evidence demonstrates each CLO; pick formative vs summative; design for AI-resistant evidence where it matters
3. **Module sequence** — Hattie 3-phase, Merrill's First Principles, Kolb cycle, or experience-first — pick the framework that fits your discipline
4. **Rubric drafts** — analytic / holistic / single-point / developmental — agent recommends based on the assessment type, then drafts the rubric
5. **Workload calibration** — Carnegie credit-hour budget; distribution across the term; flag overloaded weeks before you publish
6. **Accessibility + AI-era design** — WCAG 2.1 AA defaults; productive friction patterns for AI-resistant evidence

**You can write the artifacts straight into your Canvas course (via the sync tools), into a `course/` folder for review first, or into a fresh repo if you haven't pulled anything yet.**

For an existing course you want to *improve* (not redesign), start with the [full health check](#auditing-your-course) — the audit reports surface what to redesign first.

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

**Full grading pipeline:** [`grading_readme.md`](docs/grading_readme.md) — canonical folder layout + 8-step pipeline + dual-push pattern + setup interview.

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

# Per-student late-work accommodation

When ONE student needs deadline flexibility — for any reason, on some or all assignments — the toolkit writes Canvas **assignment overrides** in one of two flavors: either **drop the close date** (student still sees the original due date but can submit after it, marked "late") OR **shift the dates forward by N days** (the entire availability window moves; the student gets a real new hard close). The class is unaffected either way.

## Two flavors of accommodation + four scoping modes

**Flavors** (which Canvas dates to change):

| Flavor | What happens | When you'd use it | SAS catalog key |
|---|---|---|---|
| Default (drop `lock_at`) | Keep original open/due; remove the close date | *"Allow late submission without penalty"* — student still sees the original deadline, can submit after | `occasional_extensions` |
| `--shift-by-days N` | Shift open + due + close forward by N days | *"Reschedule the exam for this student"* — student gets a moved window with a real hard close | `test_reschedule` |

**Scopes** (which assignments to apply to):

| Scope flag | What it covers | When you'd use it |
|---|---|---|
| `--assignment-id <id>` | ONE specific assignment | Single missed item with a known reason |
| `--all` | EVERY published assignment | Whole-semester grace (backdates retroactively too) |
| `--from YYYY-MM-DD` | Assignments due on/after the date | "From spring break onward" / specific start date |
| `--from-days-ago N` | Assignments due in the last N days through end of term | **Recommended default** — *"They hit the wall 1-2 weeks ago; grace from there forward."* Try `--from-days-ago 14`. |

```bash
# Preview (dry-run by default — use --apply to actually write)
uv run python lib/tools/student_late_accommodation.py \
  --deid-code S-95DBB6 --from-days-ago 14

# Apply for one specific assignment
uv run python lib/tools/student_late_accommodation.py \
  --deid-code S-95DBB6 --assignment-id 123 --apply

# Apply from a specific date forward (rest of semester)
uv run python lib/tools/student_late_accommodation.py \
  --deid-code S-95DBB6 --from 2026-04-01 --apply

# Apply across whole semester with backdating
uv run python lib/tools/student_late_accommodation.py \
  --deid-code S-95DBB6 --all --apply

# Undo cleanly — same scope flags work for --remove
uv run python lib/tools/student_late_accommodation.py \
  --deid-code S-95DBB6 --from-days-ago 14 --remove --apply
```

## The de-id master — the primitive under everything

`--deid-code S-95DBB6` resolves to a Canvas user_id **without anyone ever speaking the student's name to the agent**. That works because of a new primitive in v0.70.0: a **course-wide de-identification master** at `grading/.deid_master.csv` (gitignored, FERPA tier 2).

Build it once, refresh when your roster changes:

```bash
uv run python lib/tools/build_deid_master.py
```

One row per enrolled student, four columns: `deid_code, user_id, sortable_name, withdrawn`. The `withdrawn` flag catches students who dropped mid-semester — the default Canvas People view silently hides them, and that's how 7 dropped students went missing from one pilot's final-grade analysis until this primitive existed.

**You** look up "Sydney" in the local CSV → see `S-95DBB6` → hand the agent only that code. The tool reads only the `user_id` column. Names never cross the LLM boundary.

Full knowledge file: [`deid_master_knowledge.md`](lib/agents/knowledge/deid_master_knowledge.md).

---

# Per-student extra time on timed quizzes

For accommodations that say *"give Sydney 1.5x time on quizzes"* — whether they came through a formal SAS letter or an informal arrangement — the toolkit writes Canvas quiz extensions on classic quizzes. The tool computes the right number of extra minutes from each quiz's `time_limit` so a 60-minute quiz becomes 90 (1.5x) or 120 (2.0x) for that student only.

```bash
# Preview: 1.5x on every timed quiz in the course
uv run python lib/tools/student_quiz_time_extension.py \
  --deid-code S-95DBB6 --multiplier 1.5 --all-timed

# Apply 2.0x (double time) across all timed quizzes
uv run python lib/tools/student_quiz_time_extension.py \
  --deid-code S-95DBB6 --multiplier 2.0 --all-timed --apply

# Apply to ONE specific quiz
uv run python lib/tools/student_quiz_time_extension.py \
  --deid-code S-95DBB6 --multiplier 1.5 --quiz-id 12345 --apply
```

Partial minutes always round UP — the student never gets less time than the multiplier promises. Untimed quizzes are skipped automatically (no extension is needed). PII-free via the same de-id master.

> **Note on New Quizzes (LTI):** this tool covers classic Canvas quizzes only. New Quizzes use a different API path; per-student time multipliers there are currently set via the New Quizzes Moderation UI. New Quizzes API support is a follow-up.

---

# BYUI Accessibility Services accommodations (SAS dispatcher)

If you're at BYU-Idaho and you get accommodation letters from `byui.as@accessiblelearning.com`, the `apply_sas_accommodations.py` dispatcher closes the loop. Your **life-pm** repo reads your Outlook for the letters, extracts the catalog keys (PII-free), and drops a structured YAML at `grading/.sas_accommodations.yml`. Canvas-toolbox reads the YAML and dispatches each accommodation to the right tool.

```bash
# Dry-run — see what the dispatcher plans to do
uv run python lib/tools/apply_sas_accommodations.py

# Apply
uv run python lib/tools/apply_sas_accommodations.py --apply
```

Three tiers:

| Tier | Count | Behavior |
|---|---|---|
| **Canvas** | 4 keys (`extra_time_1.5x`, `extra_time_2.0x`, `occasional_extensions`, `test_reschedule`) | Dispatcher invokes the matching tool (quiz time extension or late-work override) |
| **Proctoring** | 2 keys (`proctorio_breaks`, `private_room_exams`) | Surface as a checklist line for the operator — out of Canvas API scope |
| **Policy** | 11 keys (`spelling_grammar`, `attendance_notification`, `recording_device`, etc.) | Surface as instructor-practice checklist — no LMS change |

Every action lands in an audit log at `grading/.sas_accommodations_applied.log` (FERPA tier 2, gitignored). Full catalog + handoff schema: [`sas_accommodations_knowledge.md`](lib/agents/knowledge/sas_accommodations_knowledge.md).

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

# Sharing back with the project

Three things you can ask your agent to do:

| You want to… | Ask your agent | What happens |
|---|---|---|
| **Report a bug** | *"Report a bug: [what went wrong]"* | Agent runs `cb-report-bug`. Opens your editor for the description, scrubs PII locally (names, emails, `/Users` paths), bundles your toolkit version + last 150 log lines, files the GitHub issue. ~1 second. No GitHub account needed. |
| **Ask for a feature** | *"Ask for this feature: [what you want]"* | Same path as bug reporting; the title prefix triages it. |
| **Share something you built** | *"Share this with the project: [link / paste]"* | Agent runs `cb-share`. Same intake path; `share:` prefix tells the maintainer this is contribution-shaped. |

The intake loop is fast — issues filed via the worker have been driving new safety gates within hours.

---

# License + acknowledgments

MIT. See [`LICENSE`](LICENSE).

Built at BYU-Idaho. Designed for all instructors. Works with any Canvas institution.

The architecture (FERPA two-zone, voice-preservation contract, consensus-based grading, push-side safety gates, cross-faculty sharing) reflects pedagogical research from Hattie & Timperley, Wiggins, Dweck, Brookhart, Cognitive Load Theory, Hammond's warm-demander pedagogy, and Black & Wiliam — distilled in [`lib/agents/knowledge/`](lib/agents/knowledge/README.md) and applied as Standard Work in the grader pipeline.

---

**Current version:** v0.72.2 · 11 grading safety gates · Title IV definitions verified 2026-06-26 (next review 2027-06-26) · 605 unit tests · 20+ pedagogical knowledge files for AI-architected course design · BYUI SAS accommodation dispatcher (quiz time extension + late-work + test reschedule) · ~70 versioned releases since v0.1. Running release log + per-feature rationale in [`AGENTS.md`](AGENTS.md) Active Context.

For help, see the doc tree above or file a `cb-report-bug` (~1 second roundtrip; no GitHub account needed).

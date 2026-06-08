# Canvas Course Toolkit

A set of tools that lets you manage your Canvas course like a document — pull it down to your computer, make changes, push it back. Your course structure becomes auditable, reviewable, and fixable without living in the Canvas UI.

Built at BYU-Idaho, designed for all instructors. Works with any Canvas institution.

---

# What you can do with it

- **Keep your course in sync** — pull your Canvas course to a local folder, edit content in any text editor, push changes back
- **Catch problems before students do** — audit for broken module structure, items students can't find, and empty modules
- **Validate your dates** — check that due dates are in the right window, in the right order, and not accidentally duplicated
- **Check your outcome chain** — see whether your course outcomes actually connect to what you're grading
- **Find unused files** — surface files sitting in Canvas that nothing links to
- **Build a Course Map & Schedule** — generate an Architects-of-Learning–style course map (CLOs, per-module outcomes, 14-week schedule, pacing analysis) from your Canvas course
- **Score your syllabus against the BYU-I Completeness Rubric** — 25 specific items with link-presence detection for required policy links (Grievance / FERPA / Honor Code / Policy Library)
- **Roll out a new semester** — sync your master course to a Blueprint and let Canvas handle section distribution

Full knowledge base and agent framework references: [`lib/agents/knowledge/README.md`](lib/agents/knowledge/README.md)

---

# Getting started

Three small choices before the toolkit is yours:

1. **Pick an IDE** — the app where you'll open files and talk to your AI assistant.
2. **Pick an AI assistant** — use whichever AI subscription you already have, so you don't pay twice. (If you don't have one, there's a generous free path.)
3. **Get the toolkit running** — your AI agent walks you through it (recommended), or do the steps yourself.

You don't have to be a developer. The agent handles the technical bits; you just answer its questions.

---

## Step 1 — Pick your IDE

An **IDE** ("integrated development environment") is the app you'll work in. Pick one, download it, and install it like any other application.

| If you… | Use | Free? | Download |
|---|---|---|---|
| **have no strong preference** *(the safe default)* | **Visual Studio Code** — the standard, with the largest selection of AI assistant extensions | yes | [code.visualstudio.com](https://code.visualstudio.com/) |
| **want the AI to drive** *(and want a generous free option built in)* | **Antigravity IDE** — Google's agent-first IDE; Gemini AI is built in, no separate extension needed | yes (public preview, full Gemini 3 Pro, no usage limits announced) | [antigravityide.org](https://antigravityide.org/) |
| **teach data science** *(R, Python, Quarto)* | **Positron** — Posit's data-science IDE, with a built-in AI assistant called *Positron Assistant* | yes | [positron.posit.co/download](https://positron.posit.co/download.html) |

> ⚠️ **About Antigravity IDE:** it has Gemini built in and is **locked to Gemini** — you cannot plug a ChatGPT, Claude, or Copilot subscription into it. Pick Antigravity if you're happy using Gemini (free now, paid tiers available). If you have a ChatGPT, Claude, or Copilot subscription you want to use, pick **Visual Studio Code** here and the matching extension in Step 2.

---

## Step 2 — Pick your AI assistant

Use the subscription you **already have** so you don't pay twice. In your IDE, open the **Extensions panel** (the icon that looks like four squares on the side bar), search by the name below, click **Install**, then **sign in** when it prompts you.

| You already have… | Install this | Sign in with | Link |
|---|---|---|---|
| **ChatGPT** *(Plus / Pro / Business / Edu / Enterprise)* | **Codex – OpenAI's coding agent** | your ChatGPT account | [Marketplace listing](https://marketplace.visualstudio.com/items?itemName=openai.chatgpt) |
| **Claude** *(Pro / Team / Max)* | **Claude Code** *(official Anthropic extension)* | your Claude account | [Marketplace listing](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code) |
| **GitHub Copilot** | **GitHub Copilot** + **GitHub Copilot Chat** | your GitHub account | [Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) · [Copilot Chat](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot-chat) |
| **None of those** | Use **Antigravity IDE** instead of VS Code (from Step 1) — it's free, no extension to install, Gemini is built in | a Google account | [antigravityide.org](https://antigravityide.org/) |

> 💡 **A common mix-up:** GitHub Copilot is a *separate* Microsoft/GitHub subscription — it does **not** connect to a ChatGPT account, even though they're both AI tools. If you have ChatGPT Plus, install **Codex** (first row); if you have Copilot, install **Copilot** (third row). Each is tied to its own account.

> 📓 **Positron users:** Positron has a built-in **Positron Assistant** — you don't need to install an extension for AI help. Skip Step 2 and go to Step 3.

---

## Step 3 — Get the toolkit running

Now that you have an IDE and an AI assistant ready, pick the path that fits your comfort level. Most people use Option A.

### Option A — Start here: your agent sets it up

Create a new empty folder on your computer, open it in the IDE you set up in Steps 1 and 2, then give your AI assistant this prompt:

*"Help me set up Canvas Toolbox for my Canvas course. The toolkit is at https://github.com/chaz-clark/canvas-toolbox — please clone it, install dependencies, and walk me through connecting it to my course."*

The agent checks what's installed, handles anything missing, and guides you through the rest. You just answer its questions.

---

**Agent setup checklist** — *the agent follows these steps; the user responds when asked*

**1. Check git** — run `git --version`
- Found: continue.
- Not found: tell the user git is missing and ask permission to install it, then run:
  - Mac: `xcode-select --install` — a dialog will appear; ask the user to click Install and confirm when done.
  - Windows: `winget install --id Git.Git -e --source winget` — if winget is not available, ask the user to download Git from [git-scm.com/download/win](https://git-scm.com/download/win) and confirm when the install is done.

**2. Clone the toolkit**
```bash
git clone https://github.com/chaz-clark/canvas-toolbox.git canvas_toolbox
```

**3. Check uv** — run `uv --version`
- Found: continue.
- Not found: tell the user uv is missing and ask permission to install it, then run:
  - Mac/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- After installing: ask the user to close and reopen their terminal, then confirm `uv --version` works before continuing.

**4. Install toolkit dependencies** (one-time)
```bash
cd canvas_toolbox && uv sync && cd ..
```

**5. Create config files**
```bash
cp canvas_toolbox/scaffold/.env.example .env
cp canvas_toolbox/scaffold/gitignore .gitignore
```

**6. Collect Canvas credentials** — ask the user for:
- **Course ID** — the number after `/courses/` in their Canvas course URL
- **API token** — Canvas → Account → Settings → Approved Integrations → New Access Token (requires instructor or admin role)
- **Institution URL** — their Canvas login address (e.g., `https://byui.instructure.com`)

**7. Fill in `.env`** with their credentials:
```
CANVAS_API_TOKEN=their_token
CANVAS_BASE_URL=https://their-institution.instructure.com
CANVAS_COURSE_ID=123456
```

**8. Pull the course**
```bash
uv run python canvas_toolbox/lib/tools/canvas_sync.py --init
```
This mirrors the entire course — modules, pages, assignments, quizzes, discussions, and syllabus — into a `course/` folder. It may take a minute.

---

### Option B — Manual setup

Use this if you prefer to run each step yourself, or if your AI tool doesn't run terminal commands. Install git and uv first using the same steps in Option A's checklist above, then continue here.

**Open a terminal:**
- **Mac:** press Cmd + Space, type "Terminal", press Enter
- **Windows:** press the Windows key, type "PowerShell", press Enter

**Step 1 — Download the toolkit**

```bash
git clone https://github.com/chaz-clark/canvas-toolbox.git canvas_toolbox
```

A `canvas_toolbox` folder will appear in your current directory.

**Step 2 — Install dependencies**

```bash
cd canvas_toolbox
uv sync
cd ..
```

uv downloads everything the toolkit needs. This only runs once.

**Step 3 — Create your configuration files**

```bash
cp canvas_toolbox/scaffold/.env.example .env
cp canvas_toolbox/scaffold/gitignore .gitignore
```

This creates a `.env` file in your folder — you'll fill it in next.

**Step 4 — Enter your Canvas credentials**

You'll need three things before this step:
- **Course ID:** open your Canvas course — it's the number in the URL after `/courses/`
- **API token:** Canvas → Account → Settings → Approved Integrations → New Access Token (requires instructor or admin role)
- **Institution URL:** your Canvas login address (e.g., `https://byui.instructure.com`)

Open the `.env` file in a plain-text editor:
- **Mac:** right-click the file → Open With → TextEdit
- **Windows:** right-click the file → Open With → Notepad

> **Can't see the `.env` file?** Its name starts with a dot, which hides it by default. **Mac:** press Cmd + Shift + . in Finder to show hidden files. **Windows:** in File Explorer, click View → check "Hidden items".

```
CANVAS_API_TOKEN=your_token_here
CANVAS_BASE_URL=https://byui.instructure.com
CANVAS_COURSE_ID=123456
```

Save and close the file.

**Step 5 — Pull your course into a local folder**

**Ask your agent:** *"Pull my Canvas course into a local folder so I can start working with it"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/canvas_sync.py --init
```

This copies your entire Canvas course — all modules, pages, assignments, quizzes, discussions, and syllabus — into a `course/` folder on your computer. It may take a minute. When it finishes, you'll see the `course/` folder appear.

---

### Option C — A colleague is setting it up for you

You just need to gather three pieces of information and hand them over:

- **Course ID:** open your Canvas course — it's the number in the URL after `/courses/`
- **API token:** Canvas → Account → Settings → Approved Integrations → New Access Token (requires instructor or admin role)
- **Institution URL:** your Canvas login address (e.g., `https://byui.instructure.com`)

Share them in this format:

```
CANVAS_API_TOKEN=your_token_here
CANVAS_BASE_URL=https://byui.instructure.com
CANVAS_COURSE_ID=123456
```

They'll handle the rest.

### Already have an older canvas-toolbox setup? Migrate it.

If you already have a Canvas course repo with an *older* canvas-toolbox layout — vendored as a git subtree (committed into your repo's history), or in a folder that your parent repo still tracks — there's a one-command migration:

```bash
python3 canvas-toolbox/scaffold/migrate_to_clone_layout.py
```

This is a **dry-run by default** — it inspects your repo, tells you what state it's in (already correct / half-converted / subtree-vendored / missing), and prints the exact plan it would run. Re-run with `--apply` to actually execute. It backs up your existing canvas-toolbox content to `/tmp/` before changing anything (in case you had local patches), converts the layout to a gitignored clone, and offers to scaffold the convention sister-repo folders (`handoff/`, `Make-AI-Agents/`, `gh-issues-agent/`) — prompts you per-sister by default.

Safe to run on a setup that's already correct — it'll report *"Already on the new layout. Nothing to do."* and exit.

---

From here, edit any file locally and push changes back to Canvas.

---

# Auditing your course

Questions the audit tools can answer. All of them are read-only — they report findings but never change anything in your course. Run them as often as you like.

**Not sure where to start?** Run the one-command health check below — it runs the rubric, syllabus, and outcome audits together and gives you one summary.

## "Give me a full health check" (start here)

**Ask your agent:** *"Run a full course health audit"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/course_audit.py
```

Runs the four read-only audits — rubric coverage, rubric quality, syllabus completeness, and outcome quality — and composes one report: an overall verdict (**HEALTHY / REVIEW / NEEDS ATTENTION**) plus a single "top things to fix" list. Run the individual audits below when you want the full detail on one area.

## "Are there items students can't find?"

**Ask your agent:** *"Run the course quality check and tell me what it finds"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/course_quality_check.py
```

Checks for:
- Items published but not linked to any module (students can't navigate to these)
- Duplicate assignments, quizzes, or module items
- Empty modules
- Due dates outside the course date window

## "Are my dates going to confuse anyone?"

**Ask your agent:** *"Check my course due dates for any problems"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/course_quality_check.py --validate-dates
```

Checks for:
- Due dates outside the course start/end window
- Lock dates that come before the due date (students lose access before the deadline)
- Two items in the same group sharing the same due date
- Items named "Week 3" or "Sprint 2" whose due date falls in a different week or sprint

Exits with an error code when problems are found — safe to run as a pre-push check.

## "Do my outcomes connect to what I'm grading?"

**Ask your agent:** *"Audit my course for outcome alignment gaps"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/course_quality_check.py --alignment
```

Walks the chain: Course Outcome → Module Outcome → Rubric Criterion. Flags:
- Course-level outcomes that no assessment evidences
- Rubric criteria that no upstream outcome justifies
- Module outcomes with no rubric coverage

> Note: this uses text-matching, so treat results as a starting point for review rather than a definitive bug list.

## "Are there files I'm not using?"

**Ask your agent:** *"Find any unused or orphaned files in my Canvas course"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/course_quality_check.py --files
```

Cross-references everything linked from your course content against what's actually in Canvas Files. Flags:
- Orphaned files — in Canvas but nothing links to them
- Broken references — linked from content but the file was deleted
- Likely duplicates — same filename, different IDs

Read-only — nothing is deleted automatically.

## "Score my syllabus against the BYU-I Completeness Rubric"

**Ask your agent:** *"Score my syllabus against the BYU-I Syllabus Completeness Rubric"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/syllabus_audit.py --rubric
```

Scores your syllabus against **25 specific items** across 11 categories (the BYU-I Syllabus Completeness Rubric: 0 = missing / 1 = thin / 2 = complete). Includes link-presence detection for required policy links (Student Grievance, CES Honor Code, Academic Honesty, FERPA, Policy Library — a keyword mention without an `<a href=>` scores lower than one with the link). Outputs a per-item table, category groupings, and a total signal score. Use `--rubric --detailed` to also print the 9-section umbrella audit.

The rubric template + canonical BYU-I syllabus template are at [`lib/agents/templates/syllabus_completeness_rubric.md`](lib/agents/templates/syllabus_completeness_rubric.md) and [`lib/agents/templates/byui_syllabus_template.md`](lib/agents/templates/byui_syllabus_template.md).

## "Is my syllabus complete?"

**Ask your agent:** *"Audit my syllabus for completeness"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/syllabus_audit.py
```

Reads your course's syllabus page and checks for the sections a student needs — instructor contact, overview/outcomes, requirements, structure, expectations, grading, a disability/accessibility statement, university policies, disclaimers — plus a **generative-AI policy** (now expected on every syllabus). Reports `complete` / `incomplete` and lists what to add. Advisory extras (not counted against you): word-count/bloat, whether outcomes are stated, whether the learning model is introduced.

> Note: this uses keyword-matching on your Canvas *syllabus body*, so "not detected" means *review*, not proven-missing. If your syllabus lives on a linked Page or uploaded file, the tool can't see it there.

## "Which assignments are missing rubrics?"

**Ask your agent:** *"Check which assignments are missing rubrics"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/rubric_coverage_audit.py
```

Classifies every assignment as having a rubric, missing one (the gap), or carrying a decorative rubric (attached but not used for grading). Exits with an error code when gaps are found — safe as a pre-semester check.

## "Are my rubrics well-built?"

**Ask your agent:** *"Audit the quality of my rubrics"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/rubric_quality_audit.py
```

Scores each rubric against a four-part backbone (clear criteria, distinct rating levels, process-oriented language, sensible points/weights) and surfaces an outcome-alignment review for you to confirm. Heuristic — treat results as a starting point for review.

## "Are my learning outcomes well-written?"

**Ask your agent:** *"Audit my course learning outcomes"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/clo_quality_audit.py
```

Finds your course outcomes (Canvas Outcomes, or the syllabus's Learning Outcomes section) and checks each against the standard quality criteria: is it **measurable** (an observable verb, not "understand"/"appreciate"), is it **single-barreled** (one goal, not "design *and* evaluate"), is the set the right **scope** (3–8 outcomes), and do they spread across **Bloom's levels** (not all recall). Flags are conservative review prompts; relevance and recency are left for your judgment. Run it before the rubric audits — a rubric aligned to a broken outcome is meaningless.

## "Is the workload reasonable and well-spread?"

**Ask your agent:** *"Audit my course workload distribution"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/workload_audit.py
```

Buckets your gradable assignments by due-date week and flags **crunch weeks** (one week carrying far more than the term average), front- or back-loading, and work with no due date. Add `--credits 3` for a rough over/under-assignment sanity note. It reports `balanced` / `uneven` / `sparse` / `unscheduled`. (Honest limit: it measures *distribution* from due dates — it can't see reading *hours* inside linked files, so it doesn't compute a precise time budget.)

## "Build me a Course Map & Schedule for my course"

**Ask your agent:** *"Build me a Course Map and Schedule for my course"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/course_map_build.py
```

Generates an Architects-of-Learning–style **Course Map & Schedule** Markdown artifact (sections: CLOs from syllabus, Architect's Analysis, Key Assessments with heuristic Type / CLO / Domain·Level, Assessment Strategy, optional Assessment Design Deep-Dive, 14-week At-a-Glance, per-module Details with CLO Coverage Matrix + MLO extraction + Bloom Scaffolding Ladder, Semester Schedule with auto-detected class cadence + Prepare/In-Class/Assignment classification, Pacing Reflection with heavy-week ranking, Gap Report). Prose sections (Architect's Analysis, Pacing Reflection, AI Opportunities/Vulnerabilities, Lesson Topics) are write-in by design — the tool produces structure + data; you bring the editorial voice.

Common variants:
- `--emit-blank --output-md template.md` — emit just the blank template (university-agnostic)
- `--course 415320 --output-md /tmp/my_map.md` — pull a specific course instead of `MASTER_COURSE_ID`
- `--class-days "Mon,Wed"` — override auto-detected meeting days (or set `CLASS_DAYS` env var)

The committed template lives at [`lib/agents/templates/course_map_blank.md`](lib/agents/templates/course_map_blank.md). Pass 1 patterns + 19 lessons captured at [`lib/agents/knowledge/learned/2026-06-05_course-map-from-canvas-pass-1-lessons.md`](lib/agents/knowledge/learned/2026-06-05_course-map-from-canvas-pass-1-lessons.md).

---

# Syncing your course

## The basic loop

**Ask your agent:** *"Pull my course, show me what's changed, then push my updates to Canvas"*

Approve the run of each step:
```bash
uv run python canvas_toolbox/lib/tools/canvas_sync.py --pull     # pull course into course/
uv run python canvas_toolbox/lib/tools/canvas_sync.py --status   # see what's changed locally
uv run python canvas_toolbox/lib/tools/canvas_sync.py --push     # push changes to Canvas
```

Always run `--status` before `--push` so you know exactly what will change.

## What gets pulled

| Content type | Format | Editable locally |
|---|---|---|
| Pages | `.html` | Yes |
| Assignments | `.json` | Yes — description, points, due date |
| Discussions | `.json` | Yes — title, body |
| Quizzes | `.json` | Yes — description, metadata |
| ExternalTool / SubHeader / ExternalUrl | `.json` | No — manage in Canvas UI |

Not pulled: gradebook, submissions, student data.

## Downloading files referenced in your course

**Ask your agent:** *"Download all the files referenced in my course"* or *"Find the rubric file in my Canvas files"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/canvas_sync.py --pull-files          # download all referenced files
uv run python canvas_toolbox/lib/tools/canvas_sync.py --find-file "rubric"  # search by name, no download
uv run python canvas_toolbox/lib/tools/canvas_sync.py --pull-file "rubric"  # search + pick + download
```

Files land at `course/_files/`. The toolkit warns you before downloading large batches:

| Total size | What happens |
|---|---|
| Under 50 MB | Downloads automatically |
| 50 MB – 1 GB | Shows a summary and asks you to confirm |
| Over 1 GB | Shows the full file list before proceeding |

---

# Multi-course setup (optional)

For programs using Canvas Blueprints to distribute content to sections:

```
Source course   ← where you author content
      ↓ course_mirror.py
Master course   ← clean template
      ↓ blueprint_sync.py
Blueprint       ← Canvas clones new sections from this
```

## Syncing master → Blueprint

**Ask your agent:** *"Sync my master course to the Blueprint"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/blueprint_sync.py --pull    # mirror blueprint locally
uv run python canvas_toolbox/lib/tools/blueprint_sync.py --status  # see what's changed
uv run python canvas_toolbox/lib/tools/blueprint_sync.py --push    # sync master → blueprint
```

Then let Canvas run its built-in Blueprint sync to push changes to sections.

## Before a Blueprint sync (avoid silent skips)

Canvas silently **skips** blueprint items that are unlocked *and* have been locally edited in a section — you don't find out until after a wasted sync. Run this first to catch them:

**Ask your agent:** *"Check my blueprint is ready to sync"*

```bash
uv run python canvas_toolbox/lib/tools/blueprint_presync_check.py --bp <blueprint_course_id> --suggest-locks
```

It looks at your pending changes and predicts which will be skipped. For **pages** it's precise (it can tell a locally-edited section copy from one that's merely out of date); for **assignments/quizzes** it flags that it can't verify those pre-sync (no revision history) and suggests locking to be safe. `--suggest-locks` prints a lock script to run *before* you sync — so you sync once instead of twice. Read-only.

## Validating after a Blueprint sync

After Canvas finishes syncing to sections, run this to confirm it landed correctly:

**Ask your agent:** *"Validate that the Blueprint sync landed correctly across all sections"*

Approve the run of:
```bash
uv run python canvas_toolbox/lib/tools/validate_blueprint_sync.py
```

Checks for:
- Items present in one section but missing from another
- Fields that diverged from Blueprint — `lock_at`, `allowed_extensions`, `submission_types`
- Duplicate assignments or quizzes from direct-push + Blueprint overlap (see the quality check for resolution)
- Items with completion requirements whose `lock_at` has passed — students cannot submit and the downstream prerequisite chain is blocked

Add `--report` to save findings to `blueprint_sync_validation.md`.

That tool sees **what state diverged**. To see **why items got skipped** by Canvas during the sync (e.g., `content`/`deleted` exceptions on locally-edited items — easily missed because Canvas still reports the migration as `completed`), also run:

```bash
uv run python canvas_toolbox/lib/tools/blueprint_exception_report.py
```

Per section it emits a PASS / WARN / FAIL verdict (FAIL on `content`/`deleted` — lock the listed items in the blueprint and re-sync to fix; WARN on `points`/`state`/`settings`; PASS on `due_dates`/`availability_dates`). Add `--suggest-locks` to get a ready-to-run lock+resync script, or `--report` to save findings to `blueprint_exception_report.md`.

And to catch the Page-level corruption Canvas's UI sync can leave behind that the migration log doesn't surface — `-N` slug orphans, and silent body reversions — also run:

```bash
uv run python canvas_toolbox/lib/tools/blueprint_orphan_pages.py
```

Read-only audit (#29 Phase 1). Two detectors: orphan `-N` slugs (Canvas creates these when re-syncing into a section that previously deleted its copy — module items keep pointing at stale content while canonical content lives at an unreachable `-N` slug); and silent body reversions (a section page body that has no provenance in the blueprint's revision history — observed deterministically and **directly contradicts Canvas's published behavior**, so the tool prints an operator warning when this fires).

Requires `BLUEPRINT_COURSE_ID` and at least one `S1_COURSE_ID` in your `.env`.

If you only have one course, ignore this section entirely — `canvas_sync.py` is all you need.

---

# Using with AI coding tools

This repo ships an `AGENTS.md` that any modern AI coding tool loads automatically as project context. Open the repo in your tool of choice and ask *"what can you do for me?"* — the course audit agent's capabilities are built in.

| Tool | How it loads |
|---|---|
| Claude Code, Cursor, Antigravity, Codex, Aider, Windsurf, Zed, Amp | Automatic — just open the repo |
| VS Code + Copilot | Set `chat.useAgentsMdFile: true` once in user settings |

The agent can audit your course against ten instructional-design frameworks (Cognitive Load, Hattie 3-Phase, Three Domains, BYUI Taxonomy Explorer, Experiential Learning, Designer Thinking, Course Design Language, Toyota Gap Analysis, CLO Quality, and Inverted Bloom's) and propose specific changes with before/after previews.

---

# BYUI course structure conventions

The toolkit enforces this module order:

1. **Overview page** — outcomes, estimated time, how the pieces connect
2. **Content** — readings, videos, demos
3. **Teach One Another** — discussion where students explain or apply to peers
4. **Prove It** — assignment, quiz, or milestone demonstrating mastery

Module naming: `Sprint X: Topic (WXX–WXX)` or `Week X: Topic`.

---

# Troubleshooting

**`--pull` returns empty modules** — check that `CANVAS_COURSE_ID` is correct and your token has instructor access.

**Push returns 403** — your token is read-only or student-level. Generate a new one from an instructor or admin account in Canvas → Account → Settings.

**`--status` shows everything changed right after `--pull`** — re-run `--pull` (it's safe to run again). The toolkit needs one extra pull to finish recording which files it just downloaded.

**Page looks wrong in Canvas after push** — Canvas adds its own CSS wrapper. The `.html` files store body content only. Check the result in Student View, not the editor.

**Quality check shows "published not in module"** — the item exists in the course but was never added to a module. Students can't navigate to it. Add it via Canvas UI or contact your instructional designer.

**Tool refuses to write — "REFUSING WRITE to … enrolled / blueprint child"** — startup safety guard (#27). Your `.env` is pointing the write target at a course with enrolled students or one that's a Blueprint child — almost always a stale or hand-edited `.env`. **Sections belong in `S#_COURSE_ID` (`S1_COURSE_ID`, `S2_COURSE_ID`, …), not `CANVAS_COURSE_ID`.** Fix the `.env` and re-run. If you genuinely intend the write (rare, e.g., explicit one-off into a live section after considered review), add `--allow-enrolled` to bypass.

**Students see stale page content after a Blueprint sync, even though the migration says "completed"** — Canvas may have created a `-N` slug orphan (the canonical content went to a new `slug-2`/`-N` page that's not in any module, while the module item keeps pointing at the old slug with stale content). Run `blueprint_orphan_pages.py` to detect; cleanup is a manual unlock → PUT canonical body onto the unsuffixed slug → DELETE the `-N` page → re-lock (Phase 2 `--apply` automation is deferred per #29). If the tool also fires Detector B (silent body reversion), heed the printed operator warning — Canvas's lock-state-only sync path has been observed to cause this; don't re-run that sync.

---

# Technical reference

## canvas_quiz_questions.py — classic quiz questions

Manages questions for classic Canvas quizzes (not NewQuiz) from a local JSON file:

```bash
uv run python canvas_toolbox/lib/tools/canvas_quiz_questions.py --push course/.../quiz.questions.json
uv run python canvas_toolbox/lib/tools/canvas_quiz_questions.py --list course/.../quiz.questions.json
uv run python canvas_toolbox/lib/tools/canvas_quiz_questions.py --clear course/.../quiz.questions.json
```

Question file format:
```json
{
  "canvas_quiz_id": 5911959,
  "course_id": "415322",
  "questions": [
    {
      "question_name": "Short label",
      "question_text": "Full question shown to student.",
      "question_type": "multiple_choice_question",
      "points_possible": 1,
      "answers": [
        {"answer_text": "Correct answer", "answer_weight": 100},
        {"answer_text": "Wrong answer",   "answer_weight": 0}
      ]
    }
  ]
}
```

Supported types: `multiple_choice_question`, `true_false_question`, `short_answer_question`, `multiple_answers_question`, `essay_question`.

Note: `canvas_quiz_id` and `course_id` are course-specific — the same quiz has a different ID in every course and section. Push to each course separately.

## Keeping canvas_toolbox in sync across courses

The standard pattern: each Canvas course gets its own git repo, and `canvas_toolbox/` lives inside it as a plain clone. Toolkit updates flow downstream; your course content is never touched.

```bash
# Update the toolkit in any course repo
cd canvas_toolbox && git pull origin main && cd ..
```

Only files under `canvas_toolbox/lib/`, `canvas_toolbox/scaffold/`, and `canvas_toolbox/examples/` change on a pull. Your `course/`, `.env`, and everything at your repo root are untouched.

**Check which version you're on** (any primary sync tool reports it):

```bash
uv run python canvas_toolbox/lib/tools/canvas_sync.py --version
# → canvas-toolbox 0.20.0
```

If that's behind the latest [release tag](https://github.com/chaz-clark/canvas-toolbox/tags), run the `git pull` above. **Never patch a vendored tool copy in place** — local edits diverge silently from upstream and miss every later fix. The `v0.x` tags are the canonical line (an older `v1.x` tag series exists in history and is not maintained).

## Canvas API gotchas

- **Module prerequisites** — use form-encoded `data={"module[prerequisite_module_ids][]": id}`, not JSON. JSON returns 200 but silently does nothing.
- **Completion requirements** — must be set on every item in a module for the prerequisite lock to enforce. `must_submit` for assignments/quizzes, `must_view` for pages/tools/URLs.
- **Classic quiz points** — Canvas may show 0 after questions are pushed. Fix with `PUT /quizzes/:id {"quiz": {"points_possible": N}}`.
- **late_policy PATCH** — returns 403 for instructor tokens. Set manually in Canvas Settings → Gradebook.
- **IDs are course-specific** — the same assignment has a different ID in every course and section. Always match content across courses by title, never by ID.
- **Content + module = two steps** — creating an assignment or page makes it exist in the course but students can't access it until it's also added as a module item.

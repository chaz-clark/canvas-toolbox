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
- **Roll out a new semester** — sync your master course to a Blueprint and let Canvas handle section distribution

Full knowledge base and agent framework references: [`lib/agents/knowledge/README.md`](lib/agents/knowledge/README.md)

---

# Getting started

Choose the path that fits your situation:

---

## Option A — Start here: your agent sets it up

Create a new empty folder on your computer, open it in Antigravity, Claude Code, Cursor, or any AI coding tool, then give the agent this prompt:

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

## Option B — Manual setup

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

## Option C — A colleague is setting it up for you

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

---

From here, edit any file locally and push changes back to Canvas.

---

# Auditing your course

Four questions the audit tools can answer. All of them are read-only — they report findings but never change anything in your course. Run them as often as you like.

**Not sure where to start?** Run the first one below.

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
# → canvas-toolbox 0.19.0
```

If that's behind the latest [release tag](https://github.com/chaz-clark/canvas-toolbox/tags), run the `git pull` above. **Never patch a vendored tool copy in place** — local edits diverge silently from upstream and miss every later fix. The `v0.x` tags are the canonical line (an older `v1.x` tag series exists in history and is not maintained).

## Canvas API gotchas

- **Module prerequisites** — use form-encoded `data={"module[prerequisite_module_ids][]": id}`, not JSON. JSON returns 200 but silently does nothing.
- **Completion requirements** — must be set on every item in a module for the prerequisite lock to enforce. `must_submit` for assignments/quizzes, `must_view` for pages/tools/URLs.
- **Classic quiz points** — Canvas may show 0 after questions are pushed. Fix with `PUT /quizzes/:id {"quiz": {"points_possible": N}}`.
- **late_policy PATCH** — returns 403 for instructor tokens. Set manually in Canvas Settings → Gradebook.
- **IDs are course-specific** — the same assignment has a different ID in every course and section. Always match content across courses by title, never by ID.
- **Content + module = two steps** — creating an assignment or page makes it exist in the course but students can't access it until it's also added as a module item.

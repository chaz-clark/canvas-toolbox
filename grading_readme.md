# Grading with the Canvas Toolkit

A FERPA-safe, faculty-driven, AI-assisted grading pipeline. The instructor
makes every final call; the AI never sees a student name.

This document is the **faculty-facing entry point** — the canonical folder
layout, the 8-step pipeline, the operational rules, and the link to the deep
knowledge files for anyone who wants the reasoning. If you're an agent
reading the repo to drive the pipeline, your spec is
[`lib/agents/canvas_grader.md`](lib/agents/canvas_grader.md).

---

## What the skill does

Take any Canvas assignment (code take-home, prose self-review, lab report,
discussion, performance review) and:

1. Fetch all submissions from Canvas, **keyed by `user_id`** — the student
   name never appears in any filename, console line, or AI context.
2. De-identify the file contents — strip names, emails, paths, and
   hardcoded secrets.
3. Verify there is **no name leak** before any AI sees the submissions.
4. Have **N independent graders** (the agent runs N passes; default N=3)
   score each submission against your rubric, with per-question evidence
   citations and a student-facing comment in your voice.
5. Compute **consensus** (majority rule with spread-based auto-flag for
   borderlines) and surface the needs-review queue first.
6. Re-identify the keyed scores back to Canvas `user_id`s LOCALLY (the AI
   never sees the bridge).
7. Let you review every score + comment in one compiled document
   (`_all_comments.md`), edit phrasing in one place, sync edits back.
8. Push grades and comments to Canvas — gated behind `--mark-reviewed`,
   guarded by `canvas_course_guard`, idempotent across re-runs.

The pipeline has been validated on two real assignments (DS460 Spring 2026):
KC1 code take-home (20/22 within 0.5 of the original push) and Mid
Performance Review prose self-review (5 of 6 acceptance bars empirically
PASS; the 6th legitimately deferred).

---

## The FERPA boundary — non-negotiable

> Read this section before changing any tool in the pipeline.

The whole architecture is built on a **two-zone** principle:

| Zone | What lives there | Who reads it |
|---|---|---|
| **Local-only** (gitignored) | submissions_raw/ · .keymap.json · .fetch_log.json · .known_names.txt · .review.csv · .push_log.md | **You** (and the local Python tools) |
| **AI-safe** (de-identified) | submissions_deid/ · RUBRIC.md · config.json · feedback/ | The grading AI |

- The student name is fetched from Canvas, used locally, and is **never**
  printed to stdout/stderr, written into a filename, or sent to any cloud
  surface (LLM, log aggregator, error tracker).
- Canvas `user_id` is an internal database row ID, not a SIS/student ID;
  printing it is FERPA-safe (FERPA protects directory info + grades, not
  the LMS's own row IDs).
- The re-identification step runs **locally**, by the operator, against the
  local keymap. The grading agent never re-identifies.
- `scaffold/grading/.gitignore` is the single source of truth for what
  stays local. Copy it into your course repo's `grading/` directory; do
  not remove entries from it.
- **`submissions_raw/` is ALWAYS gitignored** — at any nesting depth, no
  matter what's inside it. Even after de-identification, the raw files
  stay local. The gitignore pattern is `**/submissions_raw/` plus
  `**/_raw/`, so a sub-cohort folder like `grading/spring2026/kc1/
  submissions_raw/` is caught too. There is no path by which a student
  submission file gets pushed to git, even if its contents were
  de-identified or obfuscated — the folder itself is the boundary, not
  the contents.
- If a name slips past de-identification, the chain stops at
  `grader_name_leak_check.py` with a non-zero exit code. Investigate before
  letting any AI read `submissions_deid/`.

---

## Canonical folder layout

The whole skill works against this shape. Every tool takes `--challenge-dir
grading/<assignment>/` and derives subpaths from it.

```
grading/
├── <assignment>/                          ← --challenge-dir (one per assignment)
│   ├── config.json                        ← per-assignment grader config (emitted by setup interview)
│   ├── RUBRIC.md                          ← named-tier rubric (or OUTCOMES.md for outcomes-based)
│   ├── PROCESS.md                         ← (optional) operational doc for this assignment
│   ├── template/                          ← (optional) source assignment template (e.g. Mid Review .docx)
│   │
│   ├── submissions_raw/                   ← LOCAL — names live here; never read by AI
│   ├── submissions_deid/                  ← AI-safe — key-encoded; the grader reads this
│   │
│   ├── .keymap.json                       ← LOCAL — key ↔ user_id ↔ name ↔ filename bridge
│   ├── .fetch_log.json                    ← LOCAL — fetch audit (grader_fetch)
│   ├── .known_names.txt                   ← LOCAL — peer-mention scrub roster
│   ├── .mark_reviewed                     ← push gate (touched only after review)
│   ├── .push_log.md                       ← push audit trail (one line per push)
│   ├── .review.csv                        ← re-identified review sheet (from grader_reidentify)
│   │
│   └── feedback/
│       ├── _signals.json                  ← static-analysis priors (grader_signals)
│       ├── _gradebook_actuals.csv         ← reconciliation (grader_reconcile)
│       ├── _grader<n>.csv                 ← per-pass scores (one per grader pass)
│       ├── _consensus.csv                 ← per-grader + consensus + spread + needs_review
│       ├── _summary.csv                   ← key,score,one_line_reason (what reidentify reads)
│       ├── _all_comments.md               ← compiled review document (edit here, sync back)
│       ├── _pass<n>/<KEY>.md              ← per-pass per-student file with Evidence + Comment
│       ├── <KEY>.md                       ← winner pass per submission (what push reads)
│       │
│       └── <output_label>/                ← MULTI-OUTPUT scoping (Mid Review case)
│           ├── _grader<n>.csv  _summary.csv  _consensus.csv  _all_comments.md
│           └── _pass<n>/<KEY>.md  <KEY>.md
│
└── answer_keys/                           ← optional — for code/notebook assignments
    ├── README.md                          ← committed (the convention)
    └── <assignment>/                      ← gitignored
        ├── <key>.ipynb                    ← raw instructor answer key
        └── key_clean.md                   ← secret-scrubbed reference (grader_prep_answer_key)
```

Everything that is FERPA-sensitive is **gitignored by default** via
`scaffold/grading/.gitignore`. Copy that file into your course repo's
`grading/` folder once at setup time.

---

## The 8-step pipeline (default)

```
1. Fetch                grader_fetch.py
                          ├─ pre-populates .known_names.txt from FULL course roster
                          ├─ downloads submissions keyed by user_id (no name in filename)
                          └─ chains by default into Steps 2 + 3 (--no-chain opts out)

2. De-identify          grader_deidentify_<adapter>.py    (auto-picked by file types)
                          ├─ Adapters by submission type:
                          │    .docx              → grader_deidentify_docx.py
                          │    .html (Databricks) → grader_deidentify_databricks.py
                          │    .html (bare body)  → grader_deidentify_text.py
                          │      OR .txt / .md       (online_text_entry case)
                          │    .ipynb             → grader_deidentify_jupyter.py
                          │      (per-cell extraction; metadata + images dropped)
                          │    .pdf               → grader_deidentify_pdf.py
                          │      (warns + writes placeholder on image-only PDFs;
                          │       operator OCRs or skips)
                          │    .xlsx              → grader_deidentify_xlsx.py
                          │      (workbook audit pattern: structure, formulas,
                          │       formatting, charts — NOT the raw binary;
                          │       file properties scrubbed)
                          │  Plus grader_fetch.py auto-detects discussion_topic
                          │  and online_quiz assignments and writes per-student
                          │  files (HTML or Markdown) that route to the text
                          │  adapter — see "Canvas submission-type coverage" below.
                          ├─ All adapters: strip names, emails, paths, hardcoded
                          │  secrets; honor .known_names.txt for peer-mention scrub
                          ├─ Writes keyed .md files to submissions_deid/
                          └─ Writes .keymap.json (key → filename bridge)

3. Name-leak check      grader_name_leak_check.py
                          └─ FAILS NON-ZERO if any name from .known_names.txt
                             survived. STOP and fix before letting AI read deid/.

4. (Optional) Signals   grader_signals.py
                          └─ Static analysis priors (not scores) — surfaces shape
                             of student work for the grader's reference.

5. (Optional) Reconcile grader_reconcile.py
                          └─ Anonymously pulls real Canvas gradebook scores by user_id
                             for self-review assignments where the rubric scores
                             "honest self-assessment" against real data.

6. Grade × N            agent-in-the-loop (default; keyless)
                        or grader_grade.py (orchestrator; requires API key)
                          ├─ N=3 by default (cheapest configuration giving majority rule)
                          ├─ Each pass writes feedback/_grader<n>.csv + feedback/_pass<n>/<KEY>.md
                          ├─ Per-student file shape (see below):
                          │     Score + Evidence per question + Confidence + Comment to student
                          └─ Wellbeing flags surface in feedback/_checkin_flags.md
                             (categories: health/family/stuck/ask_for_help/safety/financial)

7. Consensus            grader_consensus.py
                          ├─ MAJORITY: score ≥2/3 graders agree on wins; else median
                          ├─ Spread auto-flags borderlines (configurable threshold)
                          ├─ Writes _consensus.csv + _summary.csv + winner <KEY>.md
                          └─ Compiles _all_comments.md (the edit-here document)

8. Re-identify + Push   grader_reidentify.py → grader_push.py
                          ├─ Re-identify is LOCAL — bridges keyed sheet back to user_ids
                          ├─ grader_push refuses until --mark-reviewed is set
                          ├─ canvas_course_guard refuses live-course writes without
                          │  --allow-enrolled
                          └─ Idempotent: per-assignment push_log.md prevents double-pushes
```

The default `grader_fetch.py` invocation chains 1 → 2 → 3 automatically. A
fresh `grader_fetch.py --challenge-dir grading/kc1 --assignment-id 12345`
call lands at a fully-de-identified, leak-verified `submissions_deid/` ready
for grading.

---

## The value-only / human-graded push path

Not every push needs an LLM-generated comment. Common case: a **TA already graded** the assignment, and the instructor only needs to **post the consequential number** (e.g., the Layer-2 "Your Grade" in a Mid-Review-style dual-push, or any flat numeric grade the human computed). In that case the pipeline runs as:

```
grader_reconcile  →  grader_reidentify --summary  →  review .review*.csv + _gradebook_actuals.csv  →  grader_push --mark-reviewed  →  grader_push --grade-only --push
```

Two important differences from the LLM-comment path:

1. **No per-student `<KEY>.md` files exist.** The grader didn't write comments — the instructor (or a TA) graded out-of-band. `grader_push --mark-reviewed` detects this (issue #46 fix) and switches the review surface from "per-student `<KEY>.md` + `_all_comments.md`" to **`.review*.csv` + `feedback/_gradebook_actuals.csv`**. The confirmation prompt names the actual files; the mtime auto-invalidation gates on those CSVs instead.

2. **`grader_push --grade-only`** is the actual write. Suppresses the comment-field write entirely — only the grade value posts to Canvas. (Pair with `--default-comment "<text>"` if you want a fixed comment on every push, e.g. *"See Mid Review for detailed feedback."*)

The mtime auto-invalidation still applies: if you edit a `.review*.csv` after marking reviewed, the gate detects the change and forces re-review. Same trust guarantee as the LLM-comment path.

**Building the `key,score` summary by hand.** When no LLM grader ran, the operator builds `feedback/_summary.csv` (or `_summary_<output>.csv` for multi-output) from the syllabus's competencies table, a counts→grade mapping, or just direct judgment. The CSV shape is `key,score,one_line_reason` — same as what `grader_consensus` would emit. `grader_reidentify --summary <path>` reads it and emits the keyed `.review*.csv` for human review.

## The two grading paths

There are **two grading paths** in step 6, with the same downstream
artifacts.

### A. Agent-in-the-loop (default — KEYLESS)

The AI agent in your IDE (Claude Code / Cursor / Antigravity / Aider /
Codex) reads `submissions_deid/<KEY>.md`, the rubric, the voice file, and
the answer key (if present), and writes the per-pass artifacts directly:

- `feedback/_grader<n>.csv` (one CSV per pass)
- `feedback/_pass<n>/<KEY>.md` (the per-student file)

You run N passes by asking the agent to re-grade with slightly different
emphasis each time (one with strict rubric focus, one with critical-thinking
emphasis, one with the voice file as the primary anchor). The agent does
the random tier-order shuffle the orchestrator would do programmatically.

**This is the path BYUI faculty use** because BYUI cannot issue
`ANTHROPIC_API_KEY` to faculty for institutional reasons. It's been
validated as the production path: KC1 alpha (20/22 within 0.5) used it; Mid
Performance Review keyless ghost-run confirmed 5/6 acceptance bars
empirically PASS.

### B. Orchestrator (optional accelerator for key-holders)

`grader_grade.py` invokes the LLM API directly with N programmatic passes,
deterministic temperature variation (`0.3`, `0.5`, `0.7` by default),
per-pass framing tokens, and seeded tier-order shuffling. Requires
`ANTHROPIC_API_KEY` (or a future provider via the `GraderLLM` abstraction).

When to use B over A: CI/gold-set regression checks, institutional gateway
deployments, power users who want unattended grading runs. Otherwise A is
the same quality with one less moving part.

---

## Per-student file shape (the audit-trail template)

Every per-student file at `feedback/_pass<n>/<KEY>.md` and the winner copy
at `feedback/<KEY>.md` should follow this shape — it's the audit trail that
defends an appeal or override:

```markdown
# <PREFIX> Feedback — <KEY>
**Score: <score> / <max> — <header_phrase>**
_Recommendation for instructor review. Score per <rubric reference>.
Critical-thinking notes are formative coaching, not part of the score._

## Evidence for the score
- **<Question or Section> (<location>):** <observation>. <correct/incorrect rationale, citing the specific cell/paragraph>.
- **<Question or Section> (<location>):** ...

**Confidence:** <High|Medium|Low>.

## Comment to student

Overall: <tier>
<one-sentence specific strength tied to the work>

Coaching Tips:
<one idea per paragraph>

<one paragraph on the habit to build going forward>
```

The two halves serve different audiences:

- **"Evidence for the score"** (top half) is for the **instructor** during
  review. Specific, citation-heavy, defensible. Cell numbers / paragraph
  numbers / section headers. If a student appeals, this is what justifies
  the score.
- **"Comment to student"** (bottom half) is what gets pushed to Canvas. In
  the instructor's voice (per the voice file). Specific strength + coaching
  + habit-to-build. **Never feeds back data values** (concept + question
  instead, per the voice contract — fairness + safety).

The two are written together by the same grader pass so the comment is
grounded in the evidence above it.

---

## The compiled review document — `_all_comments.md`

After consensus runs, `grader_consensus.py` compiles every winner file's
"Comment to student" block into a single `feedback/_all_comments.md`:

```markdown
# KC1 — all student comments (edit phrasing here)

`Overall:` uses the rubric's named tiers. Coaching Tips: one idea per
paragraph. Edit phrasing here; the sync-back step propagates edits to
per-student files before push.

## KC1-00D64F  ·  4/4

Overall: Leading
All six questions are right and you reached for the correct columns...

Coaching Tips:
The prompt describes a longer stretch of time...

## KC1-3FEBAC  ·  4/4

Overall: Leading
All six right, your SQL is sharp...

(etc.)
```

This is the document the instructor reads cover-to-cover before push. Edit
phrasing in ONE place, then sync edits back to the per-student files (a
sync-back tool is on the backlog; for now, copy edits back manually or use
your editor's search-and-replace across `feedback/<KEY>.md`).

Pass `--score-max 4` to render `<KEY>  ·  <score>/4`. Omit for just
`<KEY>  ·  <score>`.

---

## Multi-output / dual-push pattern (Mid Review case)

Some assignments produce **two grades** on **two different Canvas
assignments** from ONE student artifact. Mid Performance Review is the
canonical example:

| Layer | Canvas assignment | Scale | Graders | Comment? |
|---|---|---|---|---|
| 1. Did the review | Mid Performance Review | 0–4 | single | yes (honest-review note + the agreed mid grade) |
| 2. Where they stand | Your Grade | value (typical ranges) | 3 reviewers → consensus | no (value only) |

The order matters: **Layer 2 runs FIRST** (3 reviewers decide where the
student stands → consensus value), then **Layer 1 runs** (single grader
writes the 0–4 + comment, using Layer 2's value inside the comment).

For multi-output assignments, the `feedback/` directory has per-output
sub-scoping:

```
feedback/
├── your_grade/                    ← Layer 2 (3 reviewers, value scale)
│   ├── _grader1.csv  _grader2.csv  _grader3.csv
│   ├── _consensus.csv  _summary.csv  _all_comments.md
│   └── _pass<n>/<KEY>.md  <KEY>.md
└── did_the_review/                ← Layer 1 (single grader, 0-4 + comment)
    ├── _grader1.csv
    ├── _summary.csv  _all_comments.md
    └── _pass1/<KEY>.md  <KEY>.md
```

The grader config `outputs[]` array drives this — one entry per layer,
each with its own `grader_count`, `assignment_id`, `scale`, and optional
`band_to_score` mapping. See
[`lib/agents/knowledge/grader_setup_knowledge.md`](lib/agents/knowledge/grader_setup_knowledge.md) §4–§5
for the full config schema.

---

## Consensus thresholds + MAJORITY tiebreak

`grader_consensus.py` computes the consensus and flags borderlines for
review. Two parameters tune to the scale:

| Scale | Recommended `--flag` (NEEDS-REVIEW threshold) |
|---|---|
| 0–4 named tier (KC) | 0.5 (default) |
| Letter-tier (Mid Review your_grade) | 1 band |
| Points / value scale (e.g. 0–100) | 10 |
| Quarter-band scoring | 0.25 |

The **MAJORITY rule** has a deliberate tiebreak: the score that ≥2 of N
graders agree on wins, even when one grader is higher and one lower. So
**2 high + 1 low → high**; **2 low + 1 high → low**. Only when all N
graders disagree does the median tiebreak kick in.

`--expected N` enforces the grader pool size. Default 3; lower to 1 for
calibration cohort runs; raise to 5+ for higher-rigor pools.

---

## Operational rules

### Non-submitters

Canvas's **late/missing policy** is what handles non-submitters — typically
an automatic 0 from a course setting. The grader does **not** handle them
and **never pushes a 0 for a non-submitter**.

The pipeline only processes the actual files in `submissions_raw/`. The
assignment's *graded* count in Canvas (including auto-0s) will exceed the
number this pipeline pushes, and that's expected — don't treat the
difference as missing work. The only thing to verify is that every student
who *did* submit has a file in `submissions_raw/`.

### Out-of-band drops (Slack / email submissions)

Sometimes a student sends a file directly outside Canvas. To bring it into
the pipeline without leaking a name through the filename:

1. **Filename → `<prefix>_<userid>.<ext>`** — look up the student's
   `user_id` in Canvas (People → student → profile URL is `.../users/<id>`)
   and rename the dropped file. The user_id is all `grader_push` needs to
   route the grade.
2. **Name → `.known_names.txt`** — add the student's name (one line). This
   replaces what the Canvas filename normally gives the de-id pipeline; the
   peer-mention scrub catches the student's own name AND any peer
   references inside the submission.

The student's name **never** goes into the filename.

### Re-submissions

An out-of-band file is often a *replacement* for an already-submitted file
(e.g., a corrupt export that de-id skipped). Before adding it, check by
**user_id** whether that student already has an entry in
`submissions_raw/`:

```bash
ls grading/<assignment>/submissions_raw/ | grep "_<userid>\."
```

If a prior (bad) file exists: **delete the bad one, keep the good
`<prefix>_<userid>.<ext>`, prune its stale `.keymap.json` entry, re-run
de-id, grade, and push with `--force`** (overwrites the placeholder). Don't
leave both — that double-counts the student under two keys.

---

## Setup — the 6-step interview

For any new instructor / new assignment, the **6-step setup interview**
(per `grader_setup_knowledge.md`) gets you from "I have an assignment" to a
runnable `config.json` in 20–40 minutes:

1. **Input format** → picks the de-id adapter (Databricks HTML / Word docx
   / future plain text)
2. **Rubric** → three paths: has-rubric / outcomes-or-contract / NEITHER
   (Path C **builds** a rubric collaboratively — the highest-leverage step)
3. **Critical thinking** → scored against the rubric or formative coaching?
4. **Outputs** → one grade or several (multi-output dual-push case)
5. **Reconciliation** → does evidence live in the gradebook or in a quiz?
   (if quiz, branch to the Classic-quiz mirror pattern below)
6. **Scale, bands, equivalences, voice, cost preview** → finalize the
   config

Run the interview by asking your agent: *"Run the canvas-toolbox grader
setup interview for assignment X."* The agent reads
`grader_setup_knowledge.md` and walks you through. Subsequent cohorts of
the same assignment skip most of the interview — `config.json` and
`RUBRIC.md` already exist.

---

## Voice — the instructor-specific comment file

The student-facing comment voice is **per-instructor**. Each instructor's
preferred phrasing, banned terms, opener/closer conventions, and tier
diction live in
`grading/<assignment>/student_feedback_voice_<instructor>.md` (or a shared
voice file at the course level).

The voice file is **learned**, not authored: the first cohort produces a
calibration set, the instructor edits the phrasing in `_all_comments.md`
(the compiled review doc), the edits are baked back into the voice file,
and subsequent cohorts inherit the voice. See
[`lib/agents/knowledge/grader_voice_knowledge.md`](lib/agents/knowledge/grader_voice_knowledge.md)
for the structure + the edit-roundtrip protocol.

**One hard rule across all instructors:** never feed back data values to a
student. Use the concept + question instead. ("How are you counting
buildings?" not "Your count of 312 includes duplicates.") Fairness +
safety.

---

## Answer keys (optional)

For code/notebook take-home assignments, drop the instructor answer key
into `grading/answer_keys/<assignment>/<key>.ipynb` and run:

```bash
uv run python canvas_toolbox/lib/tools/grader_prep_answer_key.py \
  grading/answer_keys/<assignment>/<key>.ipynb
```

This secret-scrubs the notebook (PATs, tokens, API keys, emails redacted)
and writes a clean `key_clean.md` next to the source — that's what the
grader reads. The raw `.ipynb` is gitignored and never seen by the AI.

The answer key is a **reference, not a gate**. Many real-world tasks have
valid alternate approaches; the key informs feedback, it doesn't force one
right answer into the score.

See [`scaffold/grading/answer_keys/README.md`](scaffold/grading/answer_keys/README.md)
for the full convention.

---

## Classic-quiz mirror — for verifiable self-reports

When an assignment depends on a student-submitted self-report quiz (weekly
hours, stand-up completions, missed-meeting notes), Canvas's **New Quizzes
API does NOT expose per-student item responses** (only metadata).
**Classic Quizzes do** via `submission_data` on
`/assignments/:aid/submissions?include[]=submission_history`.

`grader_quiz_mirror.py` mirrors each New Quiz as an **unpublished** Classic
Quiz (same title/description/due/group/module) with numeric questions and
wide answer ranges (any answer = correct = full points → auto-grades on
submit; no manual review). The grader then reads the Classic quiz's
per-student answers to ground the reconciliation.

This is operator-tooling, not an extra burden on students — they keep
filling out the same New Quiz. See `grader_setup_knowledge.md` §J for the
full pattern.

---

## Push — the gate

`grader_push.py` is the only tool in the pipeline that writes to Canvas.
Three gates stand between it and a destructive push:

1. **`--mark-reviewed` mtime gate.** The tool refuses to push until you
   touch a `.mark_reviewed` file. ANY edit to a per-student `<KEY>.md`
   afterward invalidates the gate (forces re-review).
2. **`canvas_course_guard`.** Refuses live-course writes unless you pass
   `--allow-enrolled`. Catches the "I pointed CANVAS_COURSE_ID at a wrong
   course" mistake.
3. **Per-assignment idempotency.** `.push_log.md` records every successful
   push by `<key, user_id, assignment_id, score>`. A subsequent re-run
   skips already-pushed entries (one-line log + skip) unless `--force`.

Validate the Canvas PUT on the **Test Student first** (Canvas's standard
test-user, display name "Test Student") — `grader_fetch.py
--test-student-only` makes this trivially repeatable.

---

## Canvas submission-type coverage

Canvas exposes 10 `submission_type` values. The grader pipeline currently
covers the ones below; gaps are documented so you know what's missing and
what to ask for if your assignment uses a format we haven't built yet.

| `submission_type` | What it is | Coverage |
|---|---|---|
| `online_text_entry` | Student types into a box | ✅ `grader_deidentify_text.py` (HTML-strip + scrub) |
| `online_upload` `.docx` | Word doc | ✅ `grader_deidentify_docx.py` |
| `online_upload` `.pdf` | PDF (text-layer extraction; image-only warned) | ✅ `grader_deidentify_pdf.py` |
| `online_upload` `.xlsx` | Excel (workbook audit pattern: structure + formulas + formatting + charts) | ✅ `grader_deidentify_xlsx.py` |
| `online_upload` `.html` w/ Databricks marker | Databricks notebook export (cell-aware extraction) | ✅ `grader_deidentify_databricks.py` |
| `online_upload` `.html` bare | Generic HTML body | ✅ `grader_deidentify_text.py` (flat tag-strip) |
| `online_upload` `.ipynb` | Jupyter notebook (per-cell extraction; metadata + base64 images dropped) | ✅ `grader_deidentify_jupyter.py` |
| `online_upload` `.txt` / `.md` / `.qmd` | Plain text / Markdown / Quarto markdown | ✅ `grader_deidentify_text.py` (encoding fallback: UTF-8 → CP1252 → Latin-1; `.qmd` accepted natively — no rename to `.md` needed) |
| `online_upload` `.csv` | CSV data | ✅ falls through `grader_deidentify_text.py` (CSV is just text) |
| `online_upload` code (`.py` / `.js` / `.r` / `.sql` / `.java` / `.cpp` etc.) | Raw source code | ✅ falls through `grader_deidentify_text.py` (code is already plain text) |
| `discussion_topic` | Student's discussion-thread posts + replies | ✅ `grader_fetch.py` detects via assignment metadata + fetches `/discussion_topics/:tid/view`; aggregates per-user chronologically to bare HTML; text adapter handles |
| `online_quiz` | Classic Canvas quiz (or NWQ→Classic-mirrored) | ✅ `grader_fetch.py` detects + extracts `submission_data` + joins with quiz questions; renders Q+A as Markdown; text adapter handles |
| `online_upload` `.pptx` | PowerPoint | ❌ Not built — ask if your assignment needs it |
| `online_upload` `.mp3` / `.mp4` / `.m4a` / `.wav` | Audio / video | ❌ Not built (transcription pipeline) — ask if your assignment needs it |
| `online_upload` `.zip` | Archive | ❌ Not built (extract + delegate per inner file) — ask if your assignment needs it |
| `student_annotation` | Annotations on instructor-uploaded doc | ❌ Not built (Canvas DocViewer API) — ask if your assignment needs it |
| `online_url` | Student submits a URL | ⚠ `grader_fetch.py` writes the URL to a file; no content fetch (arbitrary external URLs are FERPA-risky to cache locally) |
| `external_tool` | LTI tool (Pearson, McGraw-Hill, etc.) | ⚠ Vendor handles grading; NWQ has the Classic-mirror pattern (`grader_quiz_mirror.py`). Other LTIs return scores only |
| `on_paper` | Physical submission | n/a — operator grades in the gradebook UI |
| `none` | No submission | n/a |

### Have a use case that's not covered? Reach out.

If your assignment uses one of the unbuilt formats above (or a format
that's not listed at all), file an issue at
[chaz-clark/canvas-toolbox/issues](https://github.com/chaz-clark/canvas-toolbox/issues)
with:

1. The Canvas `submission_type` value (visible in the assignment's API
   payload or the Edit Assignment UI)
2. The submission file extension(s) you're seeing
3. A sample (de-identified by you) of what one student's submission
   looks like
4. Whether structure (cells / slides / annotations / threads) matters
   for grading or whether flat text extraction would suffice

Each new adapter ports in 150-300 lines once a real consumer signal lands —
the canonical layout + the FERPA two-zone architecture stay the same,
only the file-format parser changes.

## Backlog (parked items, surfaced as they're needed)

These are in the parking lot (`handoffs/parkinglot.md`); pulled into a real
build when a triggering signal appears:

1. **`grader_comments_sync.py`** — sync edits in `_all_comments.md` back to
   per-student files (`feedback/<KEY>.md`). Currently the operator copies
   edits manually or uses editor search-and-replace.
2. **Per-student file shape: enforce "Evidence for the score" in the
   orchestrator** — `grader_grade.py`'s emit shape is currently
   "Coaching points (Strength/Growth)". The agent-in-the-loop path
   naturally follows the ds460-style "Evidence for the score" shape (this
   document's spec); the orchestrator's SYSTEM_PROMPT + JSON schema update
   to match is parking-lot work for v1.0.1.
3. **Rubric versioning + regrade/appeal loop** — track which rubric
   version was used for which cohort; allow a clean re-grade with a new
   rubric version.
4. **Batch-resume on crash** — `grader_grade.py` resumes on re-run via the
   existing-keys skip; the agent-in-the-loop path doesn't yet.
5. **Gold-set regression check** — a curated set of submissions with
   known-correct scores; re-run after any prompt change and compare.
6. **Enumerated rubric with bound feedback** — the "v2 of this skill"
   pattern: graders pick from named tiers + canned feedback fragments per
   tier (vs. emitting free-form). The strongest known lever for
   cross-grader consistency.
7. **Formal bias audit on a style-varied set** — present the same
   substance in varied writing styles (formal/informal, native/non-native
   English) and verify the score doesn't shift.

---

## Validation receipts

| Assignment | Result | Source |
|---|---|---|
| **DS460 KC1** code take-home (PySpark GroupBy, 22 students, 0-4 named-tier rubric) | 20/22 within 0.5 of original push; cohort mean within 0.09 of original; 1 real borderline flagged | KC1 alpha 2026-06-10 |
| **DS460 Mid Performance Review** prose self-review (multi-output dual-push, 0–4 + value scale + wellbeing flags) | 5 of 6 acceptance bars EMPIRICAL PASS (1 deferred — no fitting no-rubric case to test Path C). New `safety` wellbeing category caught a domestic-abuse disclosure cleanly. | Mid Review keyless ghost-run 2026-06-10 |

---

## References

### Knowledge files (read these for the reasoning behind the rules)

- [`lib/agents/knowledge/grader_knowledge.md`](lib/agents/knowledge/grader_knowledge.md) — FERPA architecture, holistic scoring, consensus design, prompt-injection guard (sentinel-delimited), wellbeing flags, push gate
- [`lib/agents/knowledge/grader_voice_knowledge.md`](lib/agents/knowledge/grader_voice_knowledge.md) — per-instructor comment voice, banned terms, edit-roundtrip protocol
- [`lib/agents/knowledge/grader_setup_knowledge.md`](lib/agents/knowledge/grader_setup_knowledge.md) — the 6-step interview, the three rubric paths, the Classic-quiz mirror pattern

### Agent specs (read these if you're an agent driving the pipeline)

- [`lib/agents/canvas_grader.md`](lib/agents/canvas_grader.md) — the operator-facing pipeline spec; the agent reads this end-to-end before running any cohort
- [`lib/agents/canvas_grader.json`](lib/agents/canvas_grader.json) — agent system prompt + tool roster

### Tools

All grader tools live in `lib/tools/grader_*.py`. They share the
`--challenge-dir` convention; pass `--help` to any of them for the full
flag list:

- `grader_fetch.py` — Step 0 (fetch + roster + chain to deid + leak-check)
- `grader_deidentify_databricks.py` · `grader_deidentify_docx.py` · `grader_deidentify_text.py` · `grader_deidentify_pdf.py` · `grader_deidentify_xlsx.py` · `grader_deidentify_jupyter.py` — de-id adapters by file type. `grader_fetch.py`'s auto-chain picks the right adapter automatically; `--deid-adapter` overrides.
- `grader_fetch.py` also branches by Canvas `submission_type`: graded discussions (`/discussion_topics/:tid/view`) and Classic quizzes (`submission_data` + question join) get their own fetch paths — output routes to the text adapter downstream.
- `grader_name_leak_check.py` — name-leak verifier (FERPA gate)
- `grader_prep_answer_key.py` — secret-scrub instructor answer keys for code/notebook assignments
- `grader_signals.py` — static-analysis priors (not scores)
- `grader_reconcile.py` — anonymous gradebook reconciliation (self-review assignments)
- `grader_grade.py` — optional N-pass LLM orchestrator (requires API key)
- `grader_consensus.py` — N-grader majority + spread + `_all_comments.md` compile
- `grader_reidentify.py` — LOCAL re-identification (key → user_id)
- `grader_push.py` — Canvas write (gated behind `--mark-reviewed`)
- `grader_quiz_mirror.py` — Classic-quiz mirror for self-report verification

# Canvas Grader Agent Guide

## Agent Instructions
1. Read this file for mission, principles, quickstart, and pitfalls.
2. Parse `canvas_grader.json` for tool definitions, per-assignment config schema, pipeline stage contracts, and validation cases.
3. Load the three knowledge files at runtime — they carry the lessons this agent's behavior is grounded in:
   - [`knowledge/grader_knowledge.md`](knowledge/grader_knowledge.md) — Core: FERPA architecture, scoring philosophy, signals-as-priors, consensus, prompt-injection, judge-bias, multi-output, grade-earned reconciliation, wellbeing flags, push gate, rubric handling, ruled-out list, open gaps, acceptance bars.
   - [`knowledge/grader_voice_knowledge.md`](knowledge/grader_voice_knowledge.md) — Per-instructor comment voice: structure, never-feed-back-values, edit-roundtrip protocol, banned patterns, per-instructor file contract.
   - [`knowledge/grader_setup_knowledge.md`](knowledge/grader_setup_knowledge.md) — The 6-step setup interview + per-assignment config shape + verifiable-quiz Classic-mirror pattern (§J) + new-instructor onboarding.
4. The course mirror is `lib/tools/canvas_sync.py`. Use `--pull` to refresh before any reconciliation. Local state is the source of truth for non-grading data.
5. Per-assignment config (the output of the setup interview) lives at `grading/<assignment>/config.yml` in the consumer repo. The agent reads it; the agent does NOT modify it without explicit operator instruction.

---

## Grading path (read first — sets which tools the operator actually uses)

**The default faculty grading path is KEYLESS.** Confirmed 2026-06-10: BYUI faculty cannot obtain `ANTHROPIC_API_KEY`, and this is a standing institutional constraint. The agent (Claude Code / IDE agent) running under the operator's existing subscription auth performs the N grading passes; no per-user API key is ever required for the production path. This is how the round-1 + round-2 ds460 beta + the KC1 alpha-test validation (20/22 within 0.5) all ran.

**`lib/tools/grader_grade.py` is an OPTIONAL accelerator** for whoever DOES hold a key (CI gold-set regression harness, institution with an API gateway, power user). Not required for faculty grading. See `grader_knowledge.md` → `grading_path_keyless_default` fact for the full rationale.

The pipeline tools (de-id, signals, consensus, reidentify, push) are **identical** regardless of which grading path produced the per-pass `_grader<n>.csv` files. The agent path and the orchestrator path are interchangeable upstream of consensus.

---

## Mission

**What it does**: Drives a reusable, FERPA-safe, AI-assisted grading pipeline for any course. Walks an instructor through a 6-step setup interview to produce a per-assignment config, then runs the pipeline: de-identify submissions locally → extract objective signals (priors only, never scores) → grade with N independent LLM passes against a named-tier rubric + per-instructor voice + per-class course context → apply majority-rule consensus + auto-flag high-spread to review → reconcile claims against the real gradebook anonymously (where applicable) → surface wellbeing flags for the instructor → re-identify locally for review → push grades + comments to Canvas behind a required human-review gate, idempotently. Identity never reaches the cloud. The instructor finalizes every grade.

**Why it exists**: Every course re-forking its own grading kit is the drift trap canvas-toolbox was built to avoid. The de-identification / pre-screen / consensus / Canvas-rubric / push plumbing is generic; only the rubric, course knowledge, answer keys, and instructor voice are per-class. This agent + its three knowledge files + the supporting `lib/tools/grader_*.py` tools (Phase 3) are the toolkit's answer to "how does any course grade an assignment with AI assist, safely."

**Who uses it**: BYU-Idaho instructors (and any institution following similar FERPA discipline) grading code take-homes, prose self-reviews, performance reviews, or any other student artifact that benefits from rubric-anchored multi-pass review with reconciliation against the real gradebook.

**Example**: "Run the grader on Mid Performance Review. The setup interview walked the instructor through their syllabus Performance Table (no rubric → Path B), captured that critical thinking is scored, mapped the multi-output pattern (one `did_the_review` completion grade + one `your_grade` consequential grade), and enabled reconciliation against the gradebook including the Classic-quiz-mirrored hours/involvement data. The grader produced 22 keyed grades + 22 student comments in the instructor's voice + 3 wellbeing flags. The instructor reviewed, marked-reviewed, and pushed; 22 of 22 succeeded; no name reached the cloud at any stage."

---

## Agent Quickstart

### First time on this assignment

1. **Confirm inputs**: course ID (`CANVAS_COURSE_ID`), assignment ID, where submissions are staged locally (default: `grading/<assignment>/submissions_raw/`). Confirm canvas_course_guard awareness — writes to enrolled courses will refuse without explicit `--allow-enrolled`.
2. **Run the 6-step setup interview** (`grader_setup_knowledge.md` §1–§6) to produce `grading/<assignment>/config.yml`:
   1. Input format → de-id adapter
   2. Rubric path (has / contract-or-outcomes / neither → Path C builds one)
   3. Critical thinking: formative or scored
   4. One grade or several (multi-output)
   5. Reconciliation against gradebook (incl. quiz branch)
   6. Scale, bands, equivalences, voice file, cost preview
3. **First calibration cohort**: 5–10 submissions, single-grader, instructor reviews each. This is the voice-roundtrip baseline AND the spec calibration moment. DO NOT start with bulk + parallel.
4. **Edit-roundtrip the voice file**: emit all-comments → instructor edits → sync back into per-student files → bake recurring patterns into `agents/knowledge/student_feedback_voice_<instructor>.md`.

### Subsequent cohorts of the same assignment

1. Confirm `config.yml` still applies (any changes since last term?).
2. Confirm voice file is current.
3. Confirm cost preview.
4. Run the pipeline.

### Pipeline run order

The default invocation is **`grader_fetch.py`** — one command runs steps 0–2
(fetch + de-identify + leak-check) for ANY supported Canvas `submission_type`.
The auto-chain can be opted out with `--no-chain` if the operator wants
manual control of each step.

0. **Fetch** (`grader_fetch.py`) — the new Step 0. One up-front call to
   `/api/v1/courses/:cid/assignments/:aid` surfaces the `submission_types`
   and branches:
   - **Attachment-based** (`online_upload` / `online_text_entry` /
     `online_url`) — paginates `/submissions`, downloads attachments
     **keyed by `user_id`** (NO student name in the filename), writes
     `submissions_raw/<prefix>_<userid>.<ext>`. Also handles
     `online_text_entry` (body wrapped to .html) and `online_url`
     (URL text to `.url.txt`).
   - **`discussion_topic`** — pulls `/discussion_topics/:tid/view` (the
     threaded view), flattens per-user (top-level posts + nested replies,
     sorted chronologically), writes bare HTML per student.
   - **`online_quiz`** — pulls quiz questions once + submissions w/
     `submission_history`, joins question_id to question text, renders
     each student's Q+A as Markdown per student.
   - **Default ON** — pre-populates `.known_names.txt` from the FULL
     enrolled roster (catches peer mentions of non-submitters too).
     `--no-roster` opts out.
1. **De-identify** — `grader_fetch.py` auto-detects file types in
   `submissions_raw/` and chains to the right adapter (see Existing
   Tooling table below). All adapters: produce keyed `<KEY>.md` in
   `submissions_deid/` + update `.keymap.json`. Strips names/emails/
   userpaths + format-specific identity (PDF metadata, xlsx file
   properties, ipynb notebook metadata, Databricks identity keys).
   `--no-chain` skips this and the next step.
2. **Name-leak check** — `grader_name_leak_check.py` runs against
   `submissions_deid/`. **FAILS NON-ZERO** if any name from
   `.known_names.txt` survived. Chain stops; operator must investigate
   before the AI sees `submissions_deid/`.
3. **Reconcile** (if config.yml `reconciliation.enabled`) — resolve
   `key → user_id` via local keymap; pull gradebook actuals via Canvas
   API; emit keyed actuals sheet to `feedback/_gradebook_actuals.csv`.
4. **Grade** — run N grading passes (N = `outputs[].grader_count`).
   Default agent-in-the-loop (keyless); orchestrator (`grader_grade.py`)
   is the optional accelerator for key-holders. Each pass reads the
   de-id'd work + rubric/outcomes + per-class context + per-instructor
   voice file + calibration anchors. Per-pass artifacts:
   `feedback/_grader<n>.csv` + `feedback/_pass<n>/<KEY>.md`.
5. **Consensus** (`grader_consensus.py`) — majority + spread; auto-flag
   `spread ≥ threshold` to NEEDS-REVIEW queue (default 0.5 on a 0–4
   scale; tune per scale via `--flag`). MAJORITY rule: score ≥2/N agree
   wins, else median. Emits `_consensus.csv` + `_summary.csv` + winner
   `feedback/<KEY>.md` per submission + `_all_comments.md` (the
   compiled review document for instructor edit-and-sync).
6. **Re-identify locally** (`grader_reidentify.py`) — instructor reviews
   the per-student `<KEY>.md` files (re-id'd) and the `_all_comments.md`
   overview. Wellbeing flags reach the instructor via
   `feedback/_checkin_flags.md` (categories: health / family / stuck /
   ask_for_help / safety / financial).
7. **Push gate** (`grader_push.py`) — `--mark-reviewed` after instructor
   eyeball; gate auto-invalidates if any comment changed since.
   `canvas_course_guard` refuses live-course writes without
   `--allow-enrolled`. Per-assignment idempotency via `.push_log.md`
   (skips already-pushed keys; `--force` overrides). Validate on Test
   Student first (`grader_fetch.py --test-student-only`).

For structured data — config schema, pipeline stage contracts, output formats, test cases — see `canvas_grader.json`.

---

## File Organization: JSON vs MD

### This Markdown File Contains
- Mission, why, who uses it, example
- Quickstart workflow narrative (first-time + subsequent + pipeline order)
- Principles (cross-references to the three knowledge files)
- Behavioral discipline block (standard across all toolkit agents)
- Domain terms specific to grading
- Pitfalls with root cause
- External system lessons (Canvas grading API quirks)
- Examples

### The JSON File Contains
- Tool definitions (parameters, descriptions, examples)
- The per-assignment config.yml schema (formal)
- Pipeline stage contracts (input/output per stage, idempotency, failure semantics)
- Output format templates (per-student file shape, all-comments overview, _checkin_flags.md, actuals sheet)
- Validation test cases (acceptance bars from `grader_knowledge.md` §12)
- Knowledge file pointers (consumed_by + load_at_runtime)

---

## Key Principles

### 1. FERPA Two-Zone Architecture (`grader_knowledge.md` ferpa_two_zones)

**Description**: The grading pipeline crosses a privacy boundary every time. The two-zone architecture (cloud = keys only; local = identity) is the guardrail every other lesson depends on. De-identify BEFORE anything reaches the cloud. The key↔name map is never read by the AI. The instructor re-identifies locally.

**Why**: A leak doesn't have to be malicious — round 1 leaked a name via the IDE's "open file" notice on a single click. The architecture (not a checklist) is what keeps you safe when a tool is wrapped, reused, or extended later.

**How**: Two-zone discipline at every step. The grading prompt never sees the keymap. All output paths use keys. `check_name_leak.py` runs on de-id outputs before any cloud step and prints counts only. Console output is keys + counts only. The leak surface is the editor — quarantine raw files; never open them in the IDE while AI is active; list by key, not filename.

### 2. Holistic Scoring, Never Additive (`grader_knowledge.md` scoring_philosophy)

**Description**: Score against the named band as a single judgment, not per-criterion point arithmetic. Big-data / design / writing / reflective work has no single right answer; the answer key is a reference, not a gate. Honor course-specific equivalences (configurable). Don't change the bar mid-semester — quarter-points are finer placement within a band, not a new expectation.

**Why**: Additive scoring invites gaming and produces brittle comparisons across submissions. Holistic + named tiers + observable behavior at each tier is the only stable basis for cross-grader consistency and student-facing transparency.

**How**: The grader spec reads the rubric as a structured set of named tiers with observable behaviors; emits a band per output; quarter-point precision is allowed for within-band placement. Per-criterion math, if needed for any downstream report, is computed POST-band — it never drives the band.

### 3. Signals Are Priors, Never Scores (`grader_knowledge.md` signals_are_priors)

**Description**: Objective signals — language idioms, output presence, viz count, comment density, prose questions — are extracted as priors only. They feed into the grader's CONTEXT, not its score. When priors disagree with the LLM band, emit a `conflict_needs_review` flag rather than letting either win silently.

**Why**: Round-1 evidence: a static pre-screen mis-ranked a clean Spark-SQL solution as the weakest because the priors counted only DataFrame-API idioms. The LLM correctly ranked it among the strongest. Signals miss what the holistic read catches.

**How**: `checks.py` (or its generic descendant) emits a `priors[]` block per submission. The grader spec includes priors as context-only. The consensus phase exposes the disagreement; the human reviews flagged cases.

### 4. Three Graders, Majority + Spread Queue (`grader_knowledge.md` consensus_three_graders)

**Description**: Run N=3 independent grader passes per submission. Take the majority recommendation if ≥2/3 agree; else the median. Auto-flag high-spread submissions to a NEEDS-REVIEW queue. Calibrate single-grader first; switch to parallel once the spec is stable.

**Why**: A single LLM judgment is not stable enough for grading. Three is the cheapest configuration that enables majority rule. The spread is itself a signal — high-spread cases are precisely the borderlines a human should see.

**How**: `consensus.py` reads `feedback/_grader{1,2,3}.csv`, computes majority + spread, auto-flags `spread ≥ 0.5` (0–4 scale; tune per scale) to NEEDS-REVIEW. Parallel graders read the same rubric + the same calibration anchors so their outputs are comparable.

### 5. Per-Instructor Voice — Learned, Not Authored (`grader_voice_knowledge.md` edit_roundtrip)

**Description**: The student-facing comment voice is per-instructor, not universal. It's LEARNED through an edit roundtrip — emit all comments to one file, instructor edits in their voice, sync back into per-student files, bake recurring patterns into the per-instructor voice file. Subsequent cohorts of the same assignment start much closer to the instructor's voice.

**Why**: A "good voice" template flattens the instructor's personhood and produces uniform AI prose; the same word is fine in one voice and a tell in another. Per-instructor learning is the only way comments stay authentic across courses.

**How**: First-cohort run produces `feedback/all_comments.md` for the instructor to edit. After editing, `sync_voice_edits.py` writes per-student files. Patterns the instructor consistently changed go into `agents/knowledge/student_feedback_voice_<instructor>.md`. Default banned-pattern list is in `grader_voice_knowledge.md` §5.

### 6. Push Only Behind a Required Review Gate (`grader_knowledge.md` push_local_gated)

**Description**: Real Canvas writes refuse without `--mark-reviewed`. The marker is auto-invalidated if any comment file changed since it was set. Validate on Test Student first; never push raw. Push is idempotent — keys already in the audit log are skipped; `--force` overrides. Per-assignment-scoped audit log supports the multi-output pattern.

**Why**: A grade change is immediately visible to the student. Mistakes are not just costly; they erode trust in the entire pipeline. The gate forces a human eyeball on every batch before any write reaches Canvas.

**How**: `push_grades.py` defaults to dry-run. `--push` requires the marker. Marker mtime is checked against every per-student comment file's mtime. The canvas_course_guard live-course block requires `--allow-enrolled` to bypass on enrolled courses. The Test Student push is the proof-of-config step; clear and run the real batch.

### 7a. Value-Only / Human-Graded Push (issue #46)

**Description**: Not every push has an LLM-generated comment. When a TA already graded out-of-band (or the instructor is posting a value-only consequential grade in a dual-push setup), the pipeline runs `grader_reconcile → grader_reidentify --summary → review .review*.csv + _gradebook_actuals.csv → --mark-reviewed → grader_push --grade-only --push`. `grader_push --mark-reviewed` auto-detects this (no per-student `<KEY>.md` files exist) and switches the review surface to the CSV files + actuals; the mtime auto-invalidation gates on those instead.

**Why**: The pre-#46 review gate assumed an LLM comment artifact and printed *"reviewed all 0 comments / read _all_comments.md"* (a file that didn't exist) when run in value-only mode. The `.reviewed` marker still wrote, but the gate was effectively bypassed because the watched files didn't exist. That's not a real review surface. The fix gates on whatever review artifact actually exists in this run.

**How**: `grader_push --mark-reviewed` checks `fbdir.glob(f"{prefix}-*.md")` first; if empty, falls back to `challenge.glob(".review*.csv")` + `feedback/_gradebook_actuals.csv`. The push-gate's `watch` list is the UNION of all four (`<KEY>.md` files + `_all_comments.md` + `.review*.csv` + `_gradebook_actuals.csv`) so the mtime check fires no matter which subset exists. Use `grader_push --grade-only` to suppress comment writes; pair with `--default-comment "<text>"` for a fixed comment on every push.

### 7. Non-Submitters Are the LMS's Job

**Description**: The grader processes actual submissions only. It never pushes a 0 for a no-show. The course's missing/late policy in Canvas auto-assigns 0; the assignment's graded count will exceed the pushed count BY DESIGN.

**Why**: A grader that pushes zeros is duplicating LMS behavior with worse semantics — it can't distinguish "not submitted" from "submitted-but-failing-rubric." Let the LMS handle the absence; the grader handles the evidence.

**How**: When the submissions API returns no submission for a roster entry, the grader skips that key. The audit log records "no submission, skipped"; the push log records nothing for that user_id. The graded vs pushed count delta is reported in the final A3.

### 8. Wellbeing — Surface, Never Score (`grader_knowledge.md` wellbeing_flags)

**Description**: Reflective and prose assignments surface real hardships. The grader writes a keyed `_checkin_flags.md` listing students whose submissions disclose a struggle. **The flag does not move the score.** The instructor reviews with full context and makes any compassion adjustment off-band.

**Why**: Compassion calls require context the AI doesn't have (this student's pattern, current cohort dynamics, the back story). Automating them is both wrong and unsafe. But ignoring the disclosure is worse — the instructor needs to see it.

**How**: The grader prompt asks for wellbeing detection as a separate output (categories: health, family/safety, academic stuck-ness, direct ask for help). The flag is written to `_checkin_flags.md` (keyed). The Canvas comment carries NONE of the private specifics. The instructor's compassion response is private off-channel.

---

## Behavioral Discipline (core)

This agent follows the behavioral discipline defined in `make-ai-agents/knowledge/behavioral_discipline.md` and `make-ai-agents/knowledge/behavioral_discipline.json` (populated as a local clone in canvas-toolbox; see [AGENTS.md](../../AGENTS.md#existing-tooling)). The principles applicable to this agent type (multi_step_batch — the full discipline applies because grading decomposes into per-submission operations that compose into a batch push):

- **P-001 Read Before Claiming**: Read the actual submission, rubric, and config before any claim about a grade.
- **P-002 Plan Before Acting**: For the first cohort run, propose the calibration plan (5–10 single-grader, instructor reviews each) and wait for confirmation before bulk.
- **P-003 Stop on Defect**: First de-id failure, first FERPA self-check failure, first 4xx in the push batch → STOP. Don't retry blindly across remaining items; surface the error.
- **P-004 Find the Root Cause**: When a grade looks wrong, walk back through the consensus → priors → rubric tier → calibration anchor chain. The structural fix is where the problem lives.
- **P-005 Decompose When Necessary**: Per-submission outputs are independent; a crashed bulk run resumes per-key. The batch is a composition, not an atom.
- **P-006 Document the Change**: Final A3 reports keys graded, keys pushed, keys flagged for review, keys skipped (no submission), wellbeing flags, and any spec/voice updates made during the run.
- **P-007 Pull, Don't Push**: Don't speculate features. If the operator asks for grading, don't auto-push. If they ask for a single output, don't grade for the multi-output flow.
- **P-008 Mistake-Proof Outputs**: Per-student files match the documented shape (Overall: <Tier> → strength → Coaching Tips: → one idea per paragraph → habit-to-build). All-comments overview is one file with a stable per-key heading format. Output stability matters for the edit roundtrip.
- **P-009 Reflect, and Tell the User**: At the end of a cohort run, name anything that surprised — a borderline the consensus missed, a new banned-term pattern, an out-of-band-drop quirk. Update the voice file or this spec.
- **P-010 Respect the User's Intent**: Two failure modes: anti-substitution — don't auto-add comments to a `--grade-only` output; anti-drift — in a long batch, every push should still trace to the operator's reviewed-set; surface any drift.

**Hard rule on overrides**: before skipping any principle, state in one sentence which is being skipped and why. P-001, P-003, P-007, P-010 have no override. **P-001 applies twice**: read the actual submission AND read the actual rubric. Don't claim "the rubric says X" without reading it.

**Batch-specific application**: P-002 is operationalized as the calibration-first cohort + per-batch dry-run + `--mark-reviewed` gate. P-003 means: on the first 4xx in the push, STOP. P-005: per-submission outputs are independent. P-006: the A3 lists all four counts (graded / pushed / flagged / skipped).

For the full principle definitions, see `make-ai-agents/knowledge/behavioral_discipline.md`.

---

## Domain Terms

| Term | Definition |
|------|------------|
| `key` | Anonymized handle for a student in a single cohort. Format: `<cohort>-<n>` (e.g. `kc1-7`) or just `A1`, `B7`. Used in every cloud / AI artifact. NEVER associated with a name except in the local keymap. |
| `keymap` | Local-only CSV mapping `key → name → user_id → filename`. Sits at `grading/<assignment>/.keymap.csv` (gitignored). Never read by the AI. |
| `de-id'd submission` | The cloud-safe form of a student submission — name, email, paths, secrets all scrubbed; cell outputs capped. Lives at `grading/<assignment>/submissions_deid/<KEY>.md`. |
| `prior` | A static-extraction signal (idiom count, output presence, viz count, comment density, etc.) used as CONTEXT for the grader, never as a score. |
| `band` | A named rubric tier — `Meets/Developing/Does Not Yet Meet` or industry equivalents like INL's `Leading/Strong/Solid/Building/Insufficient`. |
| `quarter-point` | Finer-grained placement within a band (e.g. 3.25, 3.5, 3.75). Not a new band — same anchor, finer scoring. |
| `consensus` | Result of N=3 independent grader passes — majority recommendation + spread. |
| `spread` | `max(grader_scores) - min(grader_scores)` for one submission. `≥ 0.5` (default threshold) routes the submission to NEEDS-REVIEW. |
| `multi-output` | One submission produces multiple grades that push to multiple Canvas assignments (e.g. completion + consequential). |
| `reconciliation` | Anonymously pulling actual gradebook scores via the keymap to cross-check claims (self-assessments, effort/participation contracts). |
| `Classic mirror` | An UNPUBLISHED Classic Quiz that mirrors a New Quiz — same content, but exposes per-student responses via API where New Quizzes don't. Pattern §J. |
| `wellbeing flag` | A per-key disclosure of struggle (health, family, stuck) written to `_checkin_flags.md` for the instructor. Does NOT move the score. |
| `out-of-band drop` | A submission that arrives outside Canvas (Slack, email). Recipe: rename to `<prefix>_<userid>.<ext>` + add name to `.known_names.txt`. |
| `--mark-reviewed` | Marker file the instructor sets after eyeballing the per-student sheets. Auto-invalidated if any comment changed since. Required for `--push`. |
| `Test Student` | The Canvas-provided test enrollment used to validate the push pipeline. Push there first, inspect, clear, then push the real batch. |

---

## Existing Tooling

All tools shipped at v1.0+ as of 2026-06-11. The path column lists the
real `lib/tools/` location; the When-to-use column maps to the
Pipeline-run-order steps above.

### Fetch (Step 0) — the new default entry point

| Tool | Purpose | Path | When to use |
|---|---|---|---|
| `grader_fetch.py` | Fetch submissions FROM CANVAS keyed by user_id (no name in any filename/console/AI surface) + roster pre-fetch into `.known_names.txt` + auto-chain to deidentify + leak-check. Branches by `submission_type`: attachment / discussion_topic / online_quiz. | `lib/tools/grader_fetch.py` | **Step 0** — the default entry point. One command lands at a leak-verified `submissions_deid/`. |
| `grader_prep_answer_key.py` | Secret-scrub instructor `.ipynb` answer keys into `key_clean.md` for grading reference (tokens / PATs / API keys redacted; NOT student data, so only secrets are scrubbed, not names). | `lib/tools/grader_prep_answer_key.py` | Once per assignment — only for code/notebook assignments where the grader needs an instructor reference. |

### De-id adapters (Step 1) — one per format; `grader_fetch.py` auto-detects which to chain

| Adapter | Handles | Path | When auto-detect picks it |
|---|---|---|---|
| `grader_deidentify_databricks.py` | Databricks HTML notebook exports (cell-aware extraction via base64-encoded notebook model) | `lib/tools/grader_deidentify_databricks.py` | All `.html` files have `__DATABRICKS_NOTEBOOK_MODEL` marker |
| `grader_deidentify_docx.py` | Word documents (paragraphs + table cells in document order; `Name:` / `Signature:` form fields stripped) | `lib/tools/grader_deidentify_docx.py` | All files are `.docx` |
| `grader_deidentify_text.py` | Plain text / Markdown / online_text_entry (HTML-wrapped) / generic bare HTML. UTF-8 → CP1252 → Latin-1 encoding fallback. | `lib/tools/grader_deidentify_text.py` | All files are `.txt` / `.md` (or mix) OR all `.html` WITHOUT Databricks marker |
| `grader_deidentify_pdf.py` | PDF submissions via pdfplumber text-layer extraction. Image-only PDFs: warn + write placeholder explaining operator must OCR. PDF metadata (Author / Title / Creator / Producer) scrubbed. | `lib/tools/grader_deidentify_pdf.py` | All files are `.pdf` |
| `grader_deidentify_xlsx.py` | Excel via the workbook-audit pattern: sheets / freeze-panes / column formatting / cell details (first 10 rows × 20 cols) / formulas grouped by column-run / charts / named tables. File properties NEVER in output. | `lib/tools/grader_deidentify_xlsx.py` | All files are `.xlsx` |
| `grader_deidentify_jupyter.py` | Jupyter `.ipynb` per-cell extraction (markdown + code + text outputs; base64 images dropped; notebook metadata scrubbed). | `lib/tools/grader_deidentify_jupyter.py` | All files are `.ipynb` |

### FERPA gate (Step 2) + downstream pipeline

| Tool | Purpose | Path | When to use |
|---|---|---|---|
| `grader_name_leak_check.py` | Local FERPA self-check on `submissions_deid/`. Greps for any name in `.known_names.txt`. Non-zero exit if leak detected. | `lib/tools/grader_name_leak_check.py` | **Step 2** — automatic in the chain. Stops pipeline non-zero on leak. |
| `grader_signals.py` | Objective signal extraction (priors only — NEVER scores). | `lib/tools/grader_signals.py` | Optional Step 4 prep — provides context to grading passes. |
| `grader_reconcile.py` | Anonymous gradebook reconciliation via local keymap. | `lib/tools/grader_reconcile.py` | Step 3 — if `reconciliation.enabled`. |
| `grader_grade.py` | N-pass LLM grading orchestrator. **Requires `ANTHROPIC_API_KEY`**. Optional accelerator for key-holders; agent-in-the-loop is the keyless default. | `lib/tools/grader_grade.py` | Step 4 — when a key is available. |
| `grader_consensus.py` | Majority + spread + auto-flag NEEDS-REVIEW + `_all_comments.md` compile. | `lib/tools/grader_consensus.py` | Step 5 — after all grader passes complete. |
| `grader_reidentify.py` | Local-only join keys → names → instructor review sheet. | `lib/tools/grader_reidentify.py` | Step 6 — instructor-only. |
| `grader_push.py` | Local grade+comment push to Canvas. Gated behind `--mark-reviewed`. Per-assignment idempotency via `.push_log.md`. | `lib/tools/grader_push.py` | Step 7 — final write. |
| `grader_quiz_mirror.py` | Classic-quiz mirror for verifiable self-reports (NWQ API doesn't expose per-item responses; Classic does). | `lib/tools/grader_quiz_mirror.py` | §J branch of setup interview — once per assignment that depends on a quiz. |

### When the agent picks an adapter manually

The default is `grader_fetch.py` auto-detect. The operator only needs to
override when the cohort has a MIXED file-type set (auto-detect returns
`mixed_or_unknown`), via `--deid-adapter <choice>`. Choices:
`{auto, databricks, docx, text, pdf, xlsx, jupyter, none}`. `none`
disables the chain even when `--no-chain` is not set.

| Existing canvas-toolbox tool | Purpose | Role here |
|---|---|---|
| [`lib/tools/canvas_api_tool.py`](../tools/canvas_api_tool.py) | Canvas API client (auth, paging, error handling) | Underlying API surface for push + reconcile |
| [`lib/tools/canvas_course_guard.py`](../tools/canvas_course_guard.py) | Blocks writes to enrolled courses by default | The push pipeline integrates; `--allow-enrolled` for instructor's own course |
| [`lib/tools/canvas_sync.py`](../tools/canvas_sync.py) | Pull/push course mirror | `--pull` before any reconciliation; the agent reads from local state |
| [`lib/tools/sandbox_rubric_fixtures.py`](../tools/sandbox_rubric_fixtures.py) | `create_rubric` (POST /courses/:id/rubrics) | Reused for the Path C generated-rubric case |

**Reuse-first rule**: Do not write new Canvas API call code. Reference `canvas_api_tool.py` for any pattern the grader tools don't already cover.

---

## How to Use This Agent

### Prerequisites
- `.env` configured with `CANVAS_API_TOKEN`, `CANVAS_BASE_URL`, `CANVAS_COURSE_ID`.
- Course pulled locally: `uv run python lib/tools/canvas_sync.py --pull`.
- Submissions staged at `grading/<assignment>/submissions_raw/` (or wherever the config points).
- Per-instructor voice file at `agents/knowledge/student_feedback_voice_<instructor>.md` (or a stub if first cohort).
- Calibration time budget: 30–60 min for Path C (rubric build); 5–10 min per submission during the calibration cohort.

### First-Time Setup

If this is the first assignment graded with this agent in this course, run the 6-step interview (`grader_setup_knowledge.md`) to produce `grading/<assignment>/config.yml`. The agent surfaces the cost preview before any grading runs.

### Calibration Cohort

5–10 submissions, single-grader, instructor reviews EACH per-student file:
- Confirm the rubric and band assignments are accurate.
- Edit comments in the all-comments overview to the instructor's voice.
- Sync edits back, bake patterns into the voice file.
- Spot-check the wellbeing flags + reconciliation results.

After this, proceed to bulk + parallel.

### Bulk Run

```bash
# Run the pipeline (config.yml drives everything)
uv run python lib/tools/grader_deidentify_<adapter>.py \
  --raw grading/<asg>/submissions_raw/ \
  --out grading/<asg>/submissions_deid/

uv run python lib/tools/grader_name_leak_check.py grading/<asg>/submissions_deid/
# (FERPA self-check — must pass before continuing)

# ... signals, reconcile (if enabled), grading passes (3 parallel), consensus, reidentify ...

# Push gate
uv run python lib/tools/grader_push.py \
  --config grading/<asg>/config.yml \
  --review grading/<asg>/feedback/per_student/ \
  --mark-reviewed grading/<asg>/.mark_reviewed \
  --dry-run   # verify first
uv run python lib/tools/grader_push.py \
  --config grading/<asg>/config.yml \
  --review grading/<asg>/feedback/per_student/ \
  --mark-reviewed grading/<asg>/.mark_reviewed \
  --push
```

### Verify

After push, the assignment's gradebook page should show the expected count of graded entries (≤ roster size, depending on submissions). Run a spot check: pull one Canvas comment, confirm it matches the per-student file.

---

## Common Pitfalls and Solutions

### 1. Forgetting the FERPA self-check before cloud steps

**Problem**: De-id ran, but a peer mention or signature value slipped through. The grader prompt sees the name.

**Why it happens**: De-id adapters scrub names from the FILENAME and the `Name:` field, but peer-mention scrubbing depends on `.known_names.txt` being populated.

**Solution**: Always run `grader_name_leak_check.py` after de-id. Refuse to proceed if it flags. The agent should display the count line and surface any non-zero hit.

### 2. Starting with bulk + parallel before calibrating

**Problem**: 60 submissions graded with 3-grader consensus, instructor reviews the first 10, realizes the spec is mis-reading the rubric tier descriptions, has to redo everything.

**Why it happens**: 3× tokens × N submissions is expensive when you haven't validated the prompt yet. The voice is also un-calibrated for the cohort.

**Solution**: Single-grader, 5–10 submissions, instructor reviews each, edit-roundtrip the voice, THEN bulk + parallel. Decision tree in `grader_knowledge.md` consensus_three_graders.

### 3. Feeding back data values in the comment

**Problem**: The grader writes "you got 26 rows but the answer is 12" — student edits to match 12, underlying misunderstanding survives.

**Why it happens**: The default LLM behavior is to be specific and helpful. Specifying values feels more helpful than asking a question.

**Solution**: The grader spec explicitly forbids values; uses concept + question instead. See `grader_voice_knowledge.md` never_feed_back_values for the substitution. Spot-check the first calibration cohort for value leakage.

### 4. Pushing 0s for no-shows

**Problem**: 25 students enrolled, 18 submitted, agent pushed 25 grades (7 zeros for no-shows).

**Why it happens**: An iterator over the roster instead of over the submissions list.

**Solution**: Always iterate over `GET /assignments/:aid/submissions` (filtered to actual submissions), not the roster. Let Canvas's missing/late policy handle the absence (Principle 7). The graded count will exceed the pushed count by design.

### 5. Pushing during the review window

**Problem**: Instructor previewed the comments, ran `--mark-reviewed`, then noticed a typo and edited two comments. Pushed anyway because the marker existed.

**Why it happens**: A static "you reviewed it" flag can be invalidated by subsequent edits.

**Solution**: `--mark-reviewed` is auto-invalidated by mtime — if any comment file is newer than the marker, the push refuses. Operator must re-eyeball + re-mark.

### 6. New Quizzes evidence with no Classic mirror

**Problem**: Reconciliation against weekly hours fails because New Quizzes API returns 404 for `/api/quiz/v1/.../{submissions,results,reports}`.

**Why it happens**: New Quizzes don't expose per-student responses via the API. Only metadata is reachable.

**Solution**: The §J Classic-quiz mirror pattern. Mirror each New Quiz as an UNPUBLISHED Classic; auto-grade wide-range numerics; pull via `submission_data` on the submissions API. See `grader_setup_knowledge.md` classic_quiz_mirror_pattern.

### 7. The instructor's voice file is stale

**Problem**: First cohort of a new term — voice file from last term emits comments that feel slightly off because the assignment shifted or the instructor's tone moved.

**Why it happens**: Voice files are point-in-time captures; assignments and instructors evolve.

**Solution**: Treat the first cohort of each term as a calibration cohort even if the assignment hasn't changed. Run the edit roundtrip; the voice file accumulates the new patterns.

---

## External System Lessons

### Canvas — Submissions API ID Resolution

**Behavior**: To push a grade, the API needs `user_id`, not the student name or the filename. `user_id` is on the submissions API response, not on the assignment object.

**Why it matters**: Resolving `name → user_id` is a privacy risk (the name has to travel through the resolver). The grader uses the keymap (`key → user_id`) so the name never reaches the resolver.

**How to handle it**: At de-id time, also record `key → user_id` from the submissions API (where the filename → key mapping is already happening). The keymap carries both. Push reads `user_id` directly.

### Canvas — New Quizzes API Gap

**Behavior**: New Quizzes expose only metadata via API. `/api/quiz/v1/.../{submissions,results,reports}` return 404 for per-student item responses. Classic Quizzes don't have this gap.

**Why it matters**: Any reconciliation against quiz-collected evidence is blocked without a workaround.

**How to handle it**: The §J Classic-quiz mirror pattern. Mirror New → Classic, auto-grade wide-range numerics, swap mid-term if needed. Recipe in `grader_setup_knowledge.md` classic_quiz_mirror_pattern.

### Canvas — Test Student Excluded from Reports

**Behavior**: The Canvas student-analysis report on quizzes EXCLUDES the Test Student (and any Student-View submissions). The submissions API does NOT — it returns Test Student responses.

**Why it matters**: Validating the push pipeline against the Test Student via the report would show zero — but it works fine.

**How to handle it**: Use the submissions API (`GET /assignments/:aid/submissions`) for validation, not the report. The Test Student is just another `user_id` for these calls.

### Canvas — Quiz Submissions Can't Be API-Deleted

**Behavior**: Once a quiz submission exists, `DELETE` on it doesn't remove it. The only way to clear is delete + recreate the quiz.

**Why it matters**: Validating on Test Student leaves a submission behind that can't be cleared individually.

**How to handle it**: For test-only validation, delete the quiz + recreate from a saved spec, OR validate on a sandbox quiz that's allowed to accumulate test submissions. Document the chosen approach.

### Canvas — Idempotent PUT semantics on grades

**Behavior**: `PUT /assignments/:aid/submissions/:user_id` with `{submission: {posted_grade: "X"}}` is idempotent — pushing the same grade twice is a no-op (other than the audit log entry on Canvas's side). Pushing a different grade overwrites.

**Why it matters**: The push tool's idempotency is reinforced by Canvas's. Late-add re-runs of the push are safe.

**How to handle it**: Trust the idempotency. The audit log (`push_log.md`) records the local intent; Canvas's audit log records the actual write.

---

## Examples

### Example 1: Code take-home with a rubric (round-1 KC1 reproduction)

**Scenario**: ds460-master KC1 — 20 Databricks `.html` submissions, 0–4 rubric, single Canvas assignment.

**Setup interview output (config.yml excerpt)**:
```yaml
input.adapter: databricks_html
rubric.source: file
rubric.path: ./grading/kc1/RUBRIC.md
rubric.named_tiers: [Meets, Developing, Does Not Yet Meet]
policies.critical_thinking_mode: formative
policies.language_equivalence: ["Spark SQL == DataFrame API"]
outputs:
  - label: kc1
    canvas_assignment_id: <id>
    scale: "0-4"
    grader_count: 3
    comment_mode: with_comment
reconciliation.enabled: false
voice.file: agents/knowledge/student_feedback_voice_chaz.md
```

**Run**: de-id 20 files; signals; 3-grader passes; consensus + spread; reidentify; 2 NEEDS-REVIEW flags; instructor reviews; mark-reviewed; push 20 grades + 20 comments. Final A3: 20 graded, 20 pushed, 2 reviewed, 0 wellbeing flags.

**Acceptance bar (from `grader_knowledge.md` §12)**: ds460 reproduces its original KC1 score distribution using this generic skill.

### Example 2: Prose self-review, no rubric, multi-output, gradebook-reconciled (round-2 Mid Performance Review reproduction)

**Scenario**: ds460-master Mid Performance Review — 22 Word `.docx` self-reviews, no rubric (Path B against syllabus Performance Table), multi-output (completion + consequential), reconciliation enabled including Classic-quiz-mirrored hours/involvement.

**Setup interview output (config.yml excerpt)**:
```yaml
input.adapter: docx_form
rubric.source: outcomes
rubric.path: ./grading/mid_review/OUTCOMES.md   # Performance Table transcribed
rubric.named_tiers: [A, B, C, D, F]
policies.critical_thinking_mode: scored
outputs:
  - label: did_the_review
    canvas_assignment_id: <id_a>
    scale: "0-4"
    grader_count: 1
    comment_mode: with_comment
    is_consequential: false
  - label: your_grade
    canvas_assignment_id: <id_b>
    scale: "A-F"
    grader_count: 3
    comment_mode: grade_only
    is_consequential: true
reconciliation.enabled: true
reconciliation.dimensions:
  - dimension: hours
    source: classic_quiz_submissions
    assignment_ids: [<classic_mirrors>]
    mirror_source_ids: [<new_quizzes>]
    zero_means: not_submitted
  - dimension: key_challenges
    source: gradebook
    assignment_ids: [<kc_ids>]
    zero_means: not_submitted
voice.file: agents/knowledge/student_feedback_voice_chaz.md
```

**Run**: de-id 22 docx; reconcile (claims vs earned, keyed); 1-grader on did_the_review + 3-grader on your_grade; consensus on the consequential output; reidentify; 3 wellbeing flags; instructor reviews (the flags + the spread; spot-checks the gap between claims and earned); mark-reviewed; push completion grades (with comments) + consequential grades (grade-only). Final A3: 22 graded (44 pushes — 22 each output), 22 + 22 pushed, 1 NEEDS-REVIEW on the consequential output, 3 wellbeing flags surfaced.

### Example 3: Path C — building a rubric from scratch

**Scenario**: A new course (m119) has an assignment with no rubric and no syllabus performance table — just the instructor's intent in their head.

**Setup interview (Step 2 Path C)**:
- Agent: "What are you actually looking for in this assignment?"
- Instructor: "I want to see if they can connect derivatives to the visual interpretation, and if they can explain WHY a slope changes."
- Agent decomposes into criteria → drafts a 3-tier rubric with observable thresholds at each → instructor confirms → saved as `grading/<assignment>/RUBRIC.md`.

Subsequent cohorts of the same assignment skip Path C — the rubric persists.

---

## Validation and Testing

### Quick Validation

1. **FERPA self-check**: Run `grader_name_leak_check.py` against a known de-id output. Confirm 0 hits. Plant a name in a test file; confirm the tool flags it.
2. **Idempotency**: Push a small batch. Re-run the push. Confirm the second run reports "all keys already in audit log; nothing to do."
3. **Mark-reviewed invalidation**: Set the marker, edit a comment file (touch its mtime), attempt push. Confirm refusal.
4. **canvas_course_guard integration**: Attempt push without `--allow-enrolled` on an enrolled course. Confirm refusal.
5. **Test Student validation**: Push a grade to the Test Student. Inspect in Canvas. Clear. Confirm the real push proceeds without the test entry.

### Comprehensive Validation

See `canvas_grader.json → validation` for full test cases mapping to the six acceptance bars in `grader_knowledge.md` §12:

- [x] **BAR-1** — Handles both validated assignment types through config alone. *PASS EMPIRICAL (ds460 Mid Review keyless ghost-run 2026-06-10: full multi-output flow, **zero tool-code edits**; the `feedback/<label>/` scoping fix + `band_to_score` map both work; multi-output artifacts coexist without clobbering).*
- [ ] **BAR-2** — Setup interview takes an instructor with no rubric to a gradeable rubric. *Legitimately deferred — no fitting DS460 Path C case; re-confirms when a real no-rubric assignment arrives.*
- [x] **BAR-3** — Reconciliation works (gradebook + Classic-quiz-mirror branches). *PASS empirically (ds460 Mid Review ghost-run: config-driven reconcile reproduced gradebook values exactly per user_id).*
- [x] **BAR-4** — Wellbeing flags produced for reflective assignments. *PASS EMPIRICAL (ds460 Mid Review keyless ghost-run: all 3 hardship keys caught; the new `safety` category correctly categorized the 25539C domestic-abuse disclosure that round-2's prompt couldn't; flags did NOT move any score — compassion overrides stayed off-band per design).*
- [x] **BAR-5** — FERPA: outputs keyed, no name in any cloud artifact or console. *PASS empirically (ds460 Mid Review ghost-run: 23 de-id'd, 0 leaks, console clean).*
- [x] **BAR-6** — ds460 reproduces its KC1 result calling this skill. *PASS empirically (ds460 alpha 2026-06-10: 20/22 within 0.5 on the medium criterion; cohort mean within 0.09 of original push).*

**v0.1 → v1.0 PROMOTED** on 2026-06-10 based on the math above. As of the post-fix Mid Review keyless ghost-run (also 2026-06-10), **5 of 6 bars are EMPIRICAL PASS** (1, 3, 4, 5, 6) + BAR-2 legitimately deferred. The earlier "by inference" language on BAR-1 + the "GAP-closed-in-code" framing on BAR-4 are now empirically backed. Knowledge files catalogued in [`knowledge/README.md`](knowledge/README.md). Same-day Mid Review run also confirmed the calibration-anchor finding across a 2nd assignment type — see `grader_knowledge.md` §4 (the ~1-named-band top-boundary strictness is now a 2-data-point pattern, not a single-course observation; baked first-class into `grader_setup_knowledge.md` §6b).

### Regression Guard

After any cohort run, the final A3 records: (a) per-output counts (graded / pushed / skipped / flagged), (b) wellbeing flag count, (c) any spec or voice file updates made. The next cohort's A3 should show similar shape — sudden drift (e.g. skip count jumps from 2 to 12) is the signal to investigate.

---

## Quality Bar

- [ ] Every cohort run produces a final A3 with the four counts (graded / pushed / flagged / skipped) + wellbeing count.
- [ ] No Canvas write is attempted without `--mark-reviewed` and (for enrolled courses) `--allow-enrolled`.
- [ ] Every comment in the all-comments overview matches the structure (Overall: <Tier> → strength → Coaching Tips: → one idea per paragraph → habit-to-build).
- [ ] No comment in any output contains a data value the student could chase.
- [ ] FERPA self-check passes before any cloud step.
- [ ] After push, the gradebook count for the consequential assignment matches the audit log's pushed count.
- [ ] The per-instructor voice file is updated if the cohort revealed new patterns.

---

## Resources and References

### Agent Files
- **`canvas_grader.json`**: Tool definitions, config schema, pipeline stage contracts, output formats, validation cases.
- **`knowledge/grader_knowledge.md`**: Core grader lessons (FERPA architecture, scoring, signals, consensus, prompt-injection, bias, multi-output, grade-earned, push gate).
- **`knowledge/grader_voice_knowledge.md`**: Per-instructor comment voice (structure, never-feed-back-values, edit roundtrip, banned patterns).
- **`knowledge/grader_setup_knowledge.md`**: The 6-step setup interview + per-assignment config shape + Classic-quiz mirror pattern.

### Related Agents
- **`canvas_course_expert.md`**: Course-level audit (design, alignment) — sister concern; the grader handles per-submission evaluation, the expert handles the course-level standards.
- **`canvas_schedule_auditor.md`**: Date-drift audit — orthogonal to grading. Both follow the same propose-before-execute discipline.

### Beta Origin
- **`ds460-master/grading/`** (commits 754c966..91a5113 + 8f7814b + 2fd277f): the working prototype this skill generalizes. While Phase 3 is in progress, ds460 is the working code-of-record; after Phase 3 + Phase 4, ds460 retires its local kit and calls this skill instead.
- **`ds460-master/handoffs/HANDOFF_generic-grader-skill.md`**: the originating spec + lessons compendium (28KB, round 1 + round 2 + landscape survey + acceptance checks).

### External Documentation
- Canvas LMS REST API: `/api/v1/courses/:id/assignments/:id/submissions/:user_id` (PUT grade + comment), `/api/v1/courses/:id/assignments/:id/submissions?include[]=submission_history` (pull per-question quiz responses).
- Anthropic prompt-injection hardening guidance — Worth lifting before v1.0 (see `grader_knowledge.md` open gaps).

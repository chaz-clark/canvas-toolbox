# Grader — Setup Interview Knowledge

> Reference. The interview the operator (or the operator's AI agent) walks an instructor through to go from "I have an assignment" to "the grader is configured for this assignment." Produces a per-assignment config object the grader pipeline runs against.

**Sources:**
- ds460-master round 2 (commit 8f7814b) — the round-2 generalization section §A of the originating handoff, plus the working KC1 + Mid Performance Review config files.
- Originating handoff: `ds460-master/handoffs/HANDOFF_generic-grader-skill.md` §A (the 6-step interview) + §B (critical-thinking mode) + §C (multi-output) + §D (grade-earned reconciliation) + §J (verifiable-quiz Classic mirror).

**Used by:** [`canvas_grader.md`](../canvas_grader.md) — the operator-facing agent runs this interview during onboarding.

**Companions:** [`grader_knowledge.md`](grader_knowledge.md) (the lessons each interview step is grounded in), [`grader_voice_knowledge.md`](grader_voice_knowledge.md) (the voice baseline the interview captures in step 6).

**Scope:** the interview flow, the decisions captured at each step, the structure of the per-assignment config the interview emits, and the verifiable-quiz Classic-mirror pattern that pairs with the interview when the assignment depends on quiz-collected self-reports. Out of scope: the grading philosophy itself (`grader_knowledge.md`), comment voice (`grader_voice_knowledge.md`), and the implementation of the per-assignment config schema in code (that lives in the agent spec and the tools).

_Last updated: 2026-06-10_ · _**v1.0**, real-course-validated. Promoted alongside `grader_knowledge` v1.0. The 6-step interview was run informally for ds460 round 1 (KC1) and round 2 (Mid Review) and produced runnable configs both times; the structured form here is the formalization. The "second instructor onboarded via this interview" milestone (BAR-2 Path C, currently deferred) re-confirms when a fitting no-rubric case arrives but is not the v1.0 gate. Catalogued in [`knowledge/README.md`](README.md)._

---

## Why this interview matters

Round 2's biggest finding: **most instructors have an assignment but not a gradeable rubric.** They have a sense of what they're looking for, sometimes a syllabus contract or an outcomes table, often just "I'll know it when I see it." The interview is the work of turning that sense into a structured config the grader can run against. It's the **highest-leverage onboarding step** — get this right and the rest of the pipeline configures itself.

A second finding: instructors also vary on **what should be scored** (especially critical thinking — see §B) and **how many grades come out of one submission** (§C) and **whether claims are gradebook-verifiable** (§D). The 6-step interview is the smallest set of questions that captures these variations without burying the instructor in optionality.

---

## The 6-step interview (run in order)

### Step 1 — Input format → which de-id adapter to use

**Ask:** "What file format do students submit in?"

**Capture:**

| Answer | Adapter |
|---|---|
| Databricks notebook export (`.html`) | `databricks_html` |
| Jupyter notebook (`.ipynb`) | `ipynb` |
| Word document (`.docx`) | `docx_form` (handles `Name:` / `Signature:` form-field patterns) |
| Plain markdown / text | `markdown` |
| PDF | `pdf` (extract text; warn that figures don't reach the grader) |
| Multiple formats in one cohort | `multi` — adapter chosen per file by extension |

**Sub-questions if the answer is one of the structured formats:**

- "Do students submit through Canvas, or sometimes via Slack/email?" → captures the **out-of-band** path (`grader_knowledge.md` §10): if yes, the operator pre-stages those files with `<prefix>_<userid>.<ext>` naming and adds the student's name to `.known_names.txt`.
- "Are there typical hardcoded secrets in this assignment type?" → captures token-scrub patterns for the de-id adapter (e.g. Databricks tokens for ds460, AWS keys for an infra course).

### Step 2 — Rubric or no rubric → THREE paths

**Ask:** "Do you have a rubric for this assignment?"

The branching is the most important moment in the interview. Three paths:

#### Path A — Has a rubric

**Ask:** "Where does it live?"

- In Canvas attached to the assignment → `--rubric-from-canvas <assignment_id>` — the grader pulls it via `GET /assignments/:aid?include[]=rubric`.
- In the course repo as `RUBRIC.md` → `--rubric ./grading/<assignment>/RUBRIC.md`.
- In a Google Doc / Word file → "Please paste the rubric text into `./grading/<assignment>/RUBRIC.md` — the grader reads from there." (Don't paste into the interview.)

Validate the rubric structure (`grader_knowledge.md` §11):
- Named tiers? (Meets/Developing/Does-Not-Yet — or industry tiers like INL's Leading/Strong/Solid/Building/Insufficient.)
- Each tier has both a **description** (the name) and a **long_description** (the observable behavior — `course_design_language_knowledge.md` §5)?
- If not, offer to walk through one criterion to fix the shape; loop.

#### Path B — No rubric, but a contract / outcomes model

**Ask:** "Do you have an outcomes document, a syllabus performance table, or a contract describing what an A / B / C looks like?"

Round 2's Mid Performance Review case: the syllabus had a **Performance Table** with five dimensions (Hours · Key Challenges · Written Challenges · Involvement · Impact), each with A / B / C thresholds. The grader read this as the standard.

**Capture:**
- The path to the outcomes file (often the syllabus or a course-policies doc).
- The dimensions named in it.
- The thresholds (or letter-grade band descriptions) for each.

The setup interview emits a structured `OUTCOMES.md` that maps `dimension → tier → threshold-description`, derived from the source document. The grader uses this in place of a rubric.

#### Path C — Neither (the highest-value onboarding case)

**Ask:** "What are you *actually* looking for in this assignment?"

This is an open-ended conversation. The job is to extract from the instructor's intent a set of **gradeable criteria** with **observable thresholds**. Recipe:

1. **List the criteria** — "If I gave you four students' work, what would you look at first? Then what?" Each named thing is a criterion candidate.
2. **For each criterion, name what 'strong' looks like.** Push for **observable behavior**, not adjectives ("clear data interrogation, with specific questions written next to the data" — not "good critical thinking").
3. **For each criterion, name what 'weak' looks like.** Same rule.
4. **Draft a rubric** — three or five named tiers, observable behavior at each, points if appropriate.
5. **Instructor confirms.** Edit until they say "yes, this is what I'd grade against."
6. **Save as `RUBRIC.md`** in the course repo. Future cohorts of the same assignment skip Path C.

Don't promise this is fast. A new rubric for an assignment that's been graded by feel for years is **the work**. Plan 30–60 minutes for Path C. The output is permanent.

### Step 3 — Critical thinking: scored or formative?

**Ask:** "Is critical thinking (data interrogation, self-questioning, reasoning quality) part of the grade, or is it something you want surfaced as coaching but not scored?"

**Two modes** (`grader_knowledge.md` §2):

| Mode | Capture | Behavior |
|---|---|---|
| **`formative`** (default) | "I want to see it but it doesn't change the band." | Grader surfaces critical-thinking observations in the COACHING; score reflects only the named rubric dimensions. |
| **`scored`** | "It's a named rubric dimension and weighted." | Grader treats critical thinking as one of the rubric criteria, scores it like any other. The rubric (from Step 2) must already have a critical-thinking criterion — if not, loop back and add it. |

The setup writes `policies.critical_thinking_mode = formative|scored` to the config.

### Step 4 — One grade or several? (multi-output)

**Ask:** "How many grades does this assignment produce, and where do they go in Canvas?"

Most assignments are one grade → one Canvas gradebook entry. But round 2 surfaced the **multi-output** case (`grader_knowledge.md` §7) — one submission produces N grades to N Canvas items.

For each output, capture:

| Field | Example |
|---|---|
| `label` | `did_the_review` |
| `canvas_assignment_id` | `40123` |
| `scale` | `0-4` |
| `grader_count` | `1` |
| `comment_mode` | `with_comment` / `grade_only` / `default_comment` |
| `default_comment_text` (if applicable) | `See Mid Review for detailed feedback` |
| `is_consequential` | `true` / `false` (informational — which is the "real" grade) |

If multi-output, the setup writes a `outputs[]` array; if single-output, a single entry. The `push_grades.py` tool's per-assignment idempotency handles the rest.

### Step 5 — Verifiable against the gradebook?

**Ask:** "Does this assignment make claims that can be checked against actual gradebook records — like a self-assessment, an effort/participation contract, or a mid-term review?"

| Answer | Action |
|---|---|
| **No** — original work (essay, code, project) | No reconciliation. Skip. |
| **Yes** — and the evidence is in the standard gradebook | Capture which assignments/categories to pull (KC, WC, participation, etc.). The grader will run `reconcile_gradebook.py` and produce the keyed actuals sheet. |
| **Yes** — but the evidence lives in **quizzes** | Branch to the verifiable-quiz Classic-mirror pattern (§J below). New Quizzes don't expose per-student responses via API; Classic Quizzes do. |

**Capture per reconcilable dimension:**

| Field | Example |
|---|---|
| `dimension` | `hours` |
| `source` | `gradebook` / `classic_quiz_submissions` |
| `assignment_ids[]` | `[40050, 40051, 40052, ...]` |
| `zero_means` | `not_submitted` / `failure` (per-course convention — `grader_knowledge.md` §8) |

### Step 6 — Scale, bands, labels, voice

This is where the **course-flavor** decisions go.

**Sub-questions:**

a. **Whole points or quarter-points?** `0,1,2,3,4` or `0,0.25,0.5,...,4`. Quarter-points are finer placement within a band, NOT new bands (`grader_knowledge.md` §11). Capture.

b. **What are the named bands?** Default: `Meets / Developing / Does Not Yet Meet`. Industry variants: INL's `Leading / Strong / Solid / Building / Insufficient`; letter scales `A / B / C / D / F`. Capture.

   **Boundary-anchor question (now first-class — empirically confirmed across 2 assignment types 2026-06-10):** for the **top band**, walk through specifically what counts and what doesn't. The generic skill consistently runs **~1 named-band stricter at the top boundary** than an instructor's local anchor (KC1 alpha: three local 4.0s came back 3.5; Mid Review keyless ghost-run: 4/23 exact band, 17/23 within 1 band, with the same A→A- / A-→B+ pattern). Surface the question explicitly: *"What does a flawless-top-band submission look like for THIS assignment? What can be thin or imperfect and still land in the top band? Is sparse prose / a minor display issue / an unverified self-report acceptable at the top?"* Capture the instructor's answers as anchor descriptors in the rubric file (or in the `band_to_score` map's tolerance notes). The calibration cohort + voice roundtrip then operationalize those anchors so subsequent cohorts converge.

   **Why this matters:** the ~1-band top-boundary delta isn't a defect — it's the design intent (`grader_knowledge.md` §4 "Calibration is the tool's design intent, not a defect to fix"). The 80/20 principle holds: ~80% of bands land where the instructor would; the calibration cohort tunes the remaining ~20%, concentrated at the top boundary. **Skipping this question = the delta surfaces in the first real cohort as a "the AI is too strict on As" complaint that no amount of grader-prompt tweaking fixes (it's a rubric-anchor problem, not a prompt problem).**

c. **Course-specific equivalences?** "Are there approaches you treat as equivalent for grading?" e.g. `Spark SQL == DataFrame API` for ds460. Capture as `policies.language_equivalence[]`.

d. **Voice file.** "Have we already built a voice profile for you, or is this the first cohort?"
- If existing: `voice_file: agents/knowledge/student_feedback_voice_<instructor>.md`.
- If not: schedule the **edit roundtrip** for the first calibration cohort (`grader_voice_knowledge.md` §4) and create a stub voice file with default dial settings.

e. **Cost preview.** Show the instructor an estimate based on:
- Number of submissions × extracted-token estimate
- Grader count (3 for consensus by default, 1 if calibrating)
- Voice-roundtrip overhead (the edit pass)

Confirm before proceeding.

---

## After the interview — the per-assignment config object

The interview emits a structured config (YAML or JSON) the grader pipeline reads. Canonical shape:

```yaml
assignment:
  name: "Mid Performance Review"
  primary_canvas_assignment_id: 40123

input:
  adapter: docx_form              # step 1
  out_of_band: false              # step 1 sub
  scrub_secrets: false            # step 1 sub

rubric:                            # step 2
  source: outcomes                # 'canvas' | 'file' | 'outcomes' | 'generated'
  path: ./grading/mid_review/OUTCOMES.md
  named_tiers: ["A", "B", "C", "D", "F"]   # step 6b

policies:
  critical_thinking_mode: scored  # step 3
  language_equivalence: []         # step 6c

outputs:                          # step 4
  - label: did_the_review
    canvas_assignment_id: 40123
    scale: "0-4"
    grader_count: 1
    comment_mode: with_comment
    is_consequential: false
  - label: your_grade
    canvas_assignment_id: 40124
    scale: "A-F"
    grader_count: 3
    comment_mode: grade_only
    is_consequential: true

reconciliation:                   # step 5
  enabled: true
  dimensions:
    - dimension: hours
      source: classic_quiz_submissions
      assignment_ids: [40050, 40051, 40052, ...]
      zero_means: not_submitted

voice:                            # step 6d
  file: agents/knowledge/student_feedback_voice_<instructor>.md
  edit_roundtrip_scheduled: false

cost_preview:                     # step 6e
  estimated_tokens: 150000
  estimated_dollars: 2.40
```

This object is what `canvas_grader` runs against. Every per-assignment difference between courses is captured here; the grading code itself never changes per-course.

---

## §J — The verifiable-quiz Classic-mirror pattern (Step 5 branch)

When Step 5's answer is "yes, but the evidence lives in quizzes," New Quizzes' API gap forces a workaround. This is the working ds460 recipe (commit 2fd277f).

### The problem

Many courses collect weekly self-reports (hours, attendance/involvement, missed stand-ups, completion) in **New Quizzes** for the gradebook signal. **New Quizzes do NOT expose per-student item responses via the API** — `/api/quiz/v1/.../{submissions,results,reports}` return only metadata or 404. **Classic Quizzes DO** expose per-student responses through `submission_data` on `/assignments/:aid/submissions?include[]=submission_history`.

### The recipe (mirror New Quiz → Classic Quiz)

1. **Mirror** each weekly New Quiz as an UNPUBLISHED Classic Quiz — same title / description / due / assignment-group / module. Tool: `mirror_standups_classic.py` in the beta.
2. **Filter the source set** on `submission_types == external_tool` (which is what marks a New Quiz). **Real bug:** quizzes ARE assignments, so a naive title-filter like "Stand Up" mirrors your own Classic output → duplicates. The filter prevents this.
3. **Auto-grade, zero review** — for a pure self-report quiz:
   - **Numeric questions with a wide range:** any answer = correct = full points → auto-grades on submit. The instructor doesn't manually grade.
   - **No essay questions.** Essays force manual grading. The missed-work justification comes in as a **submission comment** instead, which auto-grading doesn't block.
4. **Validate via the Test Student** (the role Canvas provides):
   - Post answers with `?as_user_id=<test_student>` (start submission → answer with `as_user_id` → complete).
   - Pull them back, confirm the answers landed.
   - **Caveat:** quiz submissions can NOT be API-deleted. Clear by delete+recreate the quiz.
   - **Caveat:** the student-analysis report **excludes Student-View** — use `submission_data` from the submissions API, which includes everyone.
5. **Swap mid-term if needed.** For weeks with 0 submissions, unpublish the New Quiz + publish the Classic mirror. Students take the Classic version for the rest of the term. Same questions, same module spot, same due dates — **students see no change**. Fully reversible.
6. **Pull path** (in `reconcile_gradebook.py → classic_standup_totals`):
   ```
   GET /assignments/:aid/submissions?include[]=submission_history
     → submission_data → per-question {question_id, text}
     → sum per user_id
   ```
   Report-free, works for all students.

### What the operator captures in the config

```yaml
reconciliation:
  enabled: true
  dimensions:
    - dimension: hours
      source: classic_quiz_submissions
      assignment_ids: [40050, 40051, 40052, 40053, 40054, 40055]  # the Classic mirrors
      zero_means: not_submitted
      mirror_source_ids: [40010, 40011, 40012, 40013, 40014, 40015]  # the original New Quizzes (for record)
```

### Generic capability

Any review dimension backed by quiz self-reports — hours, involvement, comprehension checks, weekly reflections — becomes **gradebook-verifiable** through this pattern. This feeds **grade-earned, not asked** for the final letters.

---

## Pipeline after the interview

Once the per-assignment config is set, the grader pipeline runs in order:

1. **De-identify** — adapter from step 1; produces keyed `<KEY>.md` + local `.keymap.csv`. FERPA self-check passes.
2. **Reconcile** (if step 5 enabled) — pull gradebook actuals via local keymap; emit keyed actuals sheet.
3. **Grade** — run N grading passes (N from step 4 outputs[].grader_count); each pass reads de-id'd work + rubric/outcomes + course context + per-instructor voice file.
4. **Consensus** — majority + spread; auto-flag high-spread to NEEDS-REVIEW.
5. **Re-identify locally** — instructor reviews per-student files.
6. **Push gate** — `--mark-reviewed` after eyeball; validates on Test Student; pushes to Canvas via `push_grades.py` (idempotent, per-assignment-scoped).
7. **Wellbeing flags** — keyed `_checkin_flags.md` reaches the instructor before the final push.

Each step's success criteria are checklists from `grader_knowledge.md` §12.

---

## Onboarding a brand-new instructor

When the instructor has never used the toolkit grader before, run the 6-step interview AND the additional steps:

- Confirm Canvas API access (CANVAS_API_TOKEN + course ID in `.env`).
- Confirm canvas_course_guard awareness — the instructor will see live-course-write blocks until they pass `--allow-enrolled` deliberately.
- Schedule the **first calibration cohort** (5–10 submissions, single-grader, instructor reviews each) — this is the voice-roundtrip baseline AND the spec calibration moment. Don't start with bulk + parallel.
- Create the stub `student_feedback_voice_<instructor>.md` with default dials; commit to running the edit roundtrip after the calibration cohort.

After the calibration cohort succeeds and the voice file is built, the instructor is "onboarded" and subsequent cohorts of the same assignment skip Steps 1, 2, 6c, 6d (they're already captured) and only confirm the cost preview (6e).

---

## Quick-reference: the interview in one paragraph

Six questions in order: **input format** (picks a de-id adapter); **rubric** (have one / contract-or-outcomes / neither — Path C builds one collaboratively, the highest-value step); **critical thinking** (formative or scored); **outputs** (one grade or several, each with its own Canvas assignment + comment mode); **gradebook reconciliation** (does this assignment's evidence live in the gradebook or quizzes — if quizzes, branch to the Classic-mirror pattern); **scale, bands, equivalences, voice, and cost preview**. The interview emits a structured per-assignment config; the grader pipeline runs from there with no per-course code changes. The voice file is built through a calibration cohort + edit roundtrip after the interview; subsequent cohorts of the same assignment skip most of the interview.

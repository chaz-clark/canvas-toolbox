---
name: grading
description: Use for ANY grading work in a Canvas course — fetching submissions, running consensus grading, reviewing feedback, pushing grades/comments to Canvas (grader_push), the "your grade" standing column (grader_standing), de-identifying submissions before the LLM, or re-identifying results. Carries the HG-5 human-in-the-loop protocol, the push gates, the disclosure-tag menu, and the FERPA de-id/re-id flow. Load this before touching any grade that could reach a student.
---

# Grading

Grading with AI is **decision support, not autonomy.** A human decides every grade
that reaches a student. This skill is the operating manual for that discipline.

> The **constitution** (AGENTS.md) already binds you at all times: never read FERPA
> Zone-2 files, and grades reach Canvas ONLY through a sanctioned `lib/tools/`
> writer. This skill is the *how*; those are the *never*.

## HG-5 — the instructor is the top layer

Principle **HG-5** of the [hybrid grading architecture](../../../lib/agents/knowledge/grader_hybrid_architecture.md):
the agent drafts; the instructor reviews and confirms; only then does anything post.

### The push protocol — never skip a step

1. **Grade** — `grader_fetch.py --challenge-dir grading/<name>` → 3-pass consensus
   (`grader_grade.py --bulk` → `grader_consensus.py`). Single-pass LLM grading
   drifts; consensus is the default.
2. **Review** — a **human** reads `feedback/_all_comments.md` + each per-student
   `<KEY>.md`. This is the gate, not a formality.
3. **Attest** — `grader_push.py --challenge-dir grading/<name> --mark-reviewed`.
   The human types `reviewed`. The marker auto-invalidates if any feedback file
   changes afterward.
4. **Push** — `grader_push.py --challenge-dir grading/<name> --push`. The human
   types `push` at the confirmation.

## What the code enforces (so the protocol isn't docs-only)

- **`--yes` cannot bypass human review on the AI-drafted path.** With per-student
  comment files, `--yes` is refused at *both* `--mark-reviewed` (#97) and the final
  `--push` (#207, HG-5). The value-only / human-graded path (no comment files) keeps
  `--yes` — there the human *is* the grader.
- **Confirmation requires a real terminal (#241).** The `reviewed`/`push` prompts
  refuse piped/redirected stdin — `echo push | grader_push …` no longer satisfies
  the gate. If you are an assistant and hit this prompt, **hand the command to the
  instructor to run in their terminal**; do not pipe an answer and do not stack
  `--yes`/`--regrade`/`--grade-only`/`--allow-enrolled` to force it.
- **Duplicate-comment Andon.** Canvas *appends* comments, so re-runs stack them.
  Default mode refuses an already-graded submission; `--regrade` admits ONLY
  genuine resubmissions and *supersedes* (deletes old grader comments) rather than
  appending.
- **Disclosure is mandatory** (see the menu below), appended automatically.

**Do not** run `grader_push.py --yes --push` to "just get the grades in." That is
the exact HG-5 breach an [RCA](https://github.com/chaz-clark/canvas-toolbox/issues/207)
was written about — students received AI-drafted grades with no review. If a gate
blocks you, the fix is to *do the review*, not to reach for an override.

## Never hand-write a Canvas write (the field failure mode)

Grades and comments reach Canvas **only** through `grader_push.py` (feedback) or
`grader_standing.py` (the standing column) — never a custom `requests`/`curl`
script, an inline `python -c`, or a `/tmp/*.py`. A direct write skips **every**
safeguard at once: the review gate, the duplicate-comment Andon, Test-Student
exclusion (#61), grade validation, `canvas_course_guard`, the disclosure tag.
Duplicate comments, grades on Test Student, and wrong grade scales in the field
were **all** hand-written scripts bypassing the tool.

The `grade_guardian` PreToolUse hook enforces this deterministically — it blocks
**creating** such a script (Write), **editing** one (Edit), and **running** one
(`python x.py` whose body writes to Canvas). If it blocks you: use the tool, or
surface the blocker to the instructor. Do **not** route around it.

## The disclosure-tag menu — say honestly what graded vs commented

`--disclosure` picks the provenance tag appended to each comment:

| kind | tag students see | when |
|---|---|---|
| `ai` *(default)* | `— AI drafted, instructor reviewed` | AI suggested grade + wrote comment |
| `hybrid` | `— script graded, AI-drafted comment, instructor approved` | script graded, AI wrote the comment |
| `script` | `— script graded, instructor reviewed` | script graded, no AI in the comment |

A course that grades one way every time can set `CANVAS_DISCLOSURE_DEFAULT=hybrid`
in its `.env` and skip the flag; an explicit `--disclosure` still wins. The chosen
tag prints in the pre-push banner. It won't stack if you switch graders mid-stream.

## grader_standing — the "your grade" column

For a No-Submission column (often weighted 100%) that you compute from a syllabus
table and refresh weekly — instructor-computed, value-only, roster-keyed. It
sidesteps Canvas's auto-zero and the regrade gate. It **computes nothing** — your
script produces the values (from the gradebook — `grader_fetch_gradebook.py` mirrors
it locally, de-identified and cached, as that upstream input); the tool pushes them,
dry-run by default, with strict
guards (unmatched/ambiguous key → hard fail; out-of-bounds → abort; big drop →
abort unless `--allow-swings`).

**Confirming a standing push — use `--yes`, NOT a terminal.** Because standing is
value-only and instructor-computed (no AI-drafted feedback to review), `--yes` is
**allowed** here — the safe side of HG-5, unlike grader_push. The right flow: run the
dry-run, **show the instructor the `old → new` preview**, and when they confirm
(e.g. they say "push"), **re-run with `--yes` yourself**. Do **not** tell the
instructor to open a terminal and type `push` — our audience is non-technical
faculty; that's a dead end. Their confirmation of the preview *is* the attestation;
`--yes` captures it. (You still never generate the grades yourself and `--yes` them —
the values come from the instructor's script/CSV.)

```
grader_standing.py --csv standing.csv --assignment-id <id>                    # dry-run diff
grader_standing.py --csv standing.csv --assignment-id <id> --push --allow-enrolled
grader_standing.py --csv standing.csv --assignment-id <id> --push --yes --allow-enrolled   # weekly
```

## FERPA during grading — de-identify before the LLM, re-identify by key

- `grader_fetch.py` de-identifies submissions (strips names → opaque keys) before
  anything reaches the LLM. Names live only in the gitignored keymap/master.
- **Re-identify by KEY, never by sort order.** `grader_reidentify.py` maps
  `key → user_id` via `.keymap.json`, and is duplicate-aware (`user_id → [keys]`) —
  one student legitimately has many keys across submission batches. Positional /
  sort-order mapping is wrong and will misattribute grades.
- `build_deid_master.py` builds the course-wide `.deid_master.csv` (one row per
  student, keyed by user_id; dedups multi-section students).
- Zone-2 files (`.deid_master.csv`, `.keymap.json`, `.known_names.txt`,
  `.review.csv`, `submissions_raw/`, `feedback/_grader*.csv`) are **never** read or
  displayed. Verify with `wc -l` / `ls`, never `cat`/`head`/`grep`.

## Known case: an auto-scored quiz stuck in "To Do"

A classic quiz with an essay/file-upload question auto-scores on submission
(`workflow_state: graded`) but stays in the instructor's To-Do because the manual
question is `pending_review`. **Do NOT reach for grader_push** — `regrade_gate`
correctly refuses (it's already graded; this isn't a grade push), and stacking
`--force`/`--regrade` is the wrong move. If that manual question is worth **0 points**,
use `grader_quiz_clear_pending.py`: it posts a 0 to the 0-point manual question to
clear the flag — and it *can't change a grade* because it only ever touches 0-point
questions. If the pending question is worth points, that's real grading → SpeedGrader.

## Quick command map

| Ask | Command |
|---|---|
| Grade an assignment | `grader_fetch.py --challenge-dir grading/<name>` → consensus |
| Attest review | `grader_push.py --challenge-dir grading/<name> --mark-reviewed` |
| Push feedback | `grader_push.py --challenge-dir grading/<name> --push` |
| Re-grade a resubmission | add `--regrade` |
| Update the "your grade" column | `grader_standing.py --csv <f> --assignment-id <id> --push` |
| Rebuild the de-id master | `build_deid_master.py --force` |
| Mirror the live gradebook locally (feeds standing/reconcile) | `grader_fetch_gradebook.py` |
| Clear an auto-scored quiz stuck on a 0-point manual question | `grader_quiz_clear_pending.py --assignment-id <id> --apply` |

Full grading knowledge: [`lib/agents/knowledge/grader_hybrid_architecture.md`](../../../lib/agents/knowledge/grader_hybrid_architecture.md)
and [`lib/agents/knowledge/toolkit_reuse_knowledge.md`](../../../lib/agents/knowledge/toolkit_reuse_knowledge.md).

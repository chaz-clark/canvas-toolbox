---
name: grading
description: Use for ANY grading work in a Canvas course — fetching submissions, running consensus grading, reviewing feedback, pushing grades/comments to Canvas (grader_push), the "your grade" standing column (grader_standing), de-identifying submissions before the LLM, or re-identifying results. Carries the HG-5 human-in-the-loop protocol, the push gates, the disclosure-tag menu, and the FERPA de-id/re-id flow. Load this before touching any grade that could reach a student.
---

# Grading

Grading with AI is **decision support, not autonomy.** A human decides every grade
that reaches a student. This skill is the operating manual for that discipline.

## Fresh data before any grading decision

A grading decision is only as good as the data under it. A stale cache — a
`_computed_grades.csv` from an earlier sync, a day-old export — has produced
confidently-wrong conclusions ("KC3 blocker" when 19/31 had actually completed it).
So: **pull fresh Canvas data before you reason about grades**, and never trust a
cache without checking its age.

The toolkit already builds this in — do NOT hand-roll a `verify_data_freshness.sh` or
a timestamped CSV:
- **`grader_fetch_gradebook.py`** mirrors the whole gradebook, stamps it with
  `fetched_at`, and **skips the fetch only if the cache is younger than
  `--max-age-hours` (default 6)** — `--force` always refreshes. Use it (or its cache)
  as the source of truth for gradebook-wide reasoning.
- **`grader_fetch.py`** re-fetches a challenge's submissions; when in doubt, re-run it
  rather than reusing an old fetch.

If a course keeps a *computed* file (final grades, standings), regenerate it from a
fresh fetch each run — never read a cached custom CSV whose age you can't see.

> The **constitution** (AGENTS.md) already binds you at all times: never read FERPA
> Zone-2 files, and grades reach Canvas ONLY through a sanctioned `lib/tools/`
> writer. This skill is the *how*; those are the *never*.

## Final letters are READ, not parsed

A student's grade-request **letter** (or self-assessment, reflection — any prose where
they make a case) is **comprehension** data, not structured data. **Never regex/NLP-extract
the requested grade, the evidence, or any claim you'll repeat back to them.** A parser on
prose *fabricates*: a field script "extracted" *"you requested an A"* for students who
asked for a **C**, and it reached them before anyone caught it.

- **Read each letter in full** — every one, no sampling — before you write feedback that
  references what it says.
- **Ground or abstain.** If you can't tie a claim like "you requested X" to the actual
  words of *that* student's letter, do **not** write it — leave it out. Never default.
- **Files may be parsed; letters may not.** Code, notebooks, CSVs, the gradebook →
  programmatic extraction is fine. Prose where a human makes a claim → read it.

## HG-5 — the instructor is the top layer

Principle **HG-5** of the [hybrid grading architecture](../../../lib/agents/knowledge/grader_hybrid_architecture.md):
the agent drafts; the instructor reviews and confirms; only then does anything post.

### The push protocol — you run all of it; the human clicks to approve, twice

**You are not blocked from pushing** — but you may **not** skip the review. Run the whole
flow yourself (never send the instructor to a terminal), and the instructor clicks an
in-chat pop-up at TWO points: to attest the review, and to authorize the push. You
cannot click either for them, and you cannot self-attest.

1. **Grade** — `grader_fetch.py --challenge-dir grading/<name>` → 3-pass consensus
   (`grader_grade.py --bulk` → `grader_consensus.py`). Single-pass LLM grading
   drifts; consensus is the default.
2. **Show the review surface in the conversation — mandatory, never skip it.** Present
   `feedback/_all_comments.md` + the per-student `<KEY>.md` and the **old→new grade
   preview** (dry-run) right here in chat. This IS the review. Do not run
   `--mark-reviewed` until you have actually shown the comments.
3. **Attest** — run `grader_push.py --challenge-dir grading/<name> --mark-reviewed --yes`.
   The `grade_guardian` hook fires a permission **pop-up** — the instructor clicks Allow
   to attest they reviewed `_all_comments.md` (Deny if you skipped showing it, #265). The
   `.reviewed` marker records the attested state (auto-invalidates if a file changes).
4. **Push** — run `grader_push.py --challenge-dir grading/<name> --push --yes`. The
   `grade_guardian` hook fires a **second** pop-up; the instructor **clicks Allow** — that
   click authorizes the write (#264). No terminal, ever.

## What the code enforces (so the protocol isn't docs-only)

- **`--yes` is honored on every path — including AI-drafted comments (#264).** You run
  `--mark-reviewed --yes` then `--push --yes`. Do not tell the instructor to open a
  terminal or type `reviewed`/`push` at a shell; do not pipe answers on stdin.
- **The human gate is TWO in-chat pop-ups you cannot skip (#264, #265).** On the
  AI-drafted path, `grade_guardian` returns an `ask` at BOTH `--mark-reviewed` and
  `--push`, so Claude Code prompts the instructor to click at each. `--yes` does not
  bypass these — the hook fires above the tool. This is what stops an agent from running
  `--mark-reviewed --yes` and self-attesting a review the human never saw.
  (Value-only / `grader_standing` pushes don't prompt — the human is the grader there.)
- **Duplicate-comment Andon.** Canvas *appends* comments, so re-runs stack them.
  Default mode refuses an already-graded submission; `--regrade` admits ONLY
  genuine resubmissions and *supersedes* (deletes old grader comments) rather than
  appending.
- **When rows are SKIPPED, read why — never reach for the API.** grader_push skips
  already-pushed rows (re-push with `--regrade`), rows that would LOWER an existing
  grade (`--allow-lower`), and inactive/Test students (#61 — `--include-inactive`). The
  fix is always a flag *on the tool*; a hand-written `requests`/`python -c` write skips
  every safeguard and the guardian blocks it anyway.
- **Add or FIX comments after grading → `--comments-only`.** To attach feedback to
  ALREADY-GRADED work (grade now, comment later) or replace a wrong comment, use
  `--comments-only`: it posts the comment, leaves the grade untouched, bypasses the
  regrade gate, and *supersedes* the prior grader comment so nothing stacks. Never clear
  grades to "get past" the gate — that's destructive and re-opens the sync-mismatch bugs.
- **Comment on a NON-SUBMITTER (0 / no submission) → `--roster-csv`.** The file-keyed
  push can't see a student with no submission file. `--roster-csv <user_id,comment>`
  posts comment-only straight to `/submissions/<user_id>` — their empty submission
  object still accepts it. Grade untouched, guardian pop-up still gates it. For an
  instructor-written note there, pass `--disclosure script` (it's not AI-drafted).
- **Disclosure is mandatory** (see the menu below), appended automatically.

**The in-chat review is the gate, not a rubber-stamp.** The failure an
[RCA](https://github.com/chaz-clark/canvas-toolbox/issues/207) was written about was
students getting AI-drafted grades with *no* review. `--yes --push` is the sanctioned
path now — but only because the review moved into the conversation and the guardian
prompt makes the instructor consciously approve the write. So actually show the comments
and the old→new grades and get a real "yes" before you push; never stack overrides to
skip a gate you hit.

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

**Which push tool? Ask: does the assignment take a student submission?**
**Yes** (online upload / text / quiz) → `grader_push` (keyed on submission files).
**No** (a No-Submission "Your Grade" / standing column) → **`grader_standing`** (roster-keyed
by user_id, overwrites freely, no regrade gate). Using grader_push on a No-Submission
column hits the regrade gate and dead-ends — grader_push now detects this and refuses
with a pointer here, but pick the right tool up front.

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

## Final-letter grading — split the write, two sanctioned tools

A "final letter" workflow has two Canvas writes; do NOT hand-write a `fix_push.py`
(the `grade_guardian` hook blocks it, correctly). Keep your course-specific
computation (the tier/stretch logic in `calc_final_grades.py`), and route both writes:

1. **The grade** (Course Grade column, value-only) → `grader_standing.py` — emit a
   `user_id,final_grade` CSV, then `--push --yes` (instructor-computed, value-only).
2. **The comment** (End Letter, comment-only, preserves the existing grade) →
   `grader_letter_comments.py` — a `user_id,comment` CSV → comment-only writes, no
   grade change. `--yes` allowed because these are the **instructor's own** notes.

**AI-drafted per-student feedback is NOT a final-letter comment** — that goes through
`grader_push` (the HG-5 review gate). `grader_letter_comments` is for instructor-
authored notes only.

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

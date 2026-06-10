# Grader — Comment Voice Knowledge

> Reference. How the grader writes the student-facing comment. **Per-instructor**, not universal — comment voice is the part of grading that's most personal and most often wrong by default when an AI writes it. This file explains the structure and the learning protocol; the per-instructor specifics live in a course-local `agents/knowledge/student_feedback_voice_<instructor>.md` that the grader loads at runtime.

**Sources:**
- ds460-master round 2, commit 8f7814b — `agents/knowledge/student_feedback_voice_knowledge.md` (the working per-instructor voice file in the beta).
- Originating handoff: `ds460-master/handoffs/HANDOFF_generic-grader-skill.md` §F.

**Used by:** [`canvas_grader.md`](../canvas_grader.md), every consumer of [`grader_knowledge.md`](grader_knowledge.md).

**Companions:** [`grader_knowledge.md`](grader_knowledge.md) (the FERPA / scoring / consensus / push pipeline this voice rides on top of), [`grader_setup_knowledge.md`](grader_setup_knowledge.md) (the setup interview that baselines the voice file from the instructor's first edit pass).

**Scope:** the structure, banned-pattern catalog, and edit-roundtrip protocol for the Canvas comment a student reads. Out of scope: rubric design (`grader_knowledge.md` §11), gradebook reconciliation (`grader_knowledge.md` §8), wellbeing flag content (`grader_knowledge.md` §9 — kept OUT of the comment).

_Last updated: 2026-06-10_ · _v0.1, untested. Promotes to v1.0 after a second instructor (not Chaz) successfully baselines a voice file through the edit roundtrip in §4._

---

## Why per-instructor

The comment voice is the part of grading that most strongly carries the **instructor's personhood** — their warmth, their specific phrasings, their pedagogical priorities. A global "good voice" template flattens that and produces uniform AI prose. Worse, the same word reads as fine in one instructor's voice and as a tell in another's (round 2 catch: "idiomatic" is fine in some technical contexts, a dead giveaway in ds460's).

**The rule:** each instructor maintains their own voice file. The grader loads it at runtime; the spec's "voice" section is just `read_at_runtime(voice_file)`. The structure below is shared across instructors; the **specifics** (banned terms, characteristic phrases, exact opener wording) live in the per-instructor file.

---

## 1 — The structure (shared across instructors)

The Canvas comment is the **only** thing the student sees. Every coaching point lives here; nothing meaningful stays in an internal "coaching" section the student never sees.

### The four parts, in order

```
Overall: <Tier>

<one or two sentences naming a specific strength>

Coaching Tips:

<one idea per paragraph. Each paragraph is a single coaching point.>

<habit-to-build paragraph — the closing>
```

### Why each part exists

| Part | Why | Failure mode if omitted |
|---|---|---|
| **`Overall: <Tier>`** | The first thing the student reads must be the band. Saves them scanning for the score. | Students hunt for the verdict, miss the coaching. |
| **Specific strength** | Anchors the student in what worked before what didn't. Without it, every comment reads as criticism even when the score is high. | Coaching feels like attack; student defends instead of learns. |
| **`Coaching Tips:`** header | A visual break. Tells the student "here's the work." | Coaching blurs with the strength sentence; nothing reads as actionable. |
| **One idea per paragraph** | Discrete coaching points are readable. Multi-point paragraphs require the student to parse. | Reader stops at the first point; later coaching unread. |
| **Habit-to-build closing** | One thing to take forward, framed as practice, not deficiency. | Comment ends on the worst thing; no forward motion. |

### Anti-pattern: the "two things" preamble

Don't write `Here are two things I noticed...` or `A couple of things to think about...`. The structure already telegraphs that coaching is coming; the preamble is filler that reads as AI. Go straight to the first paragraph.

---

## 2 — The hard rule: never feed back data values

This is both a **fairness rule** and a **safety rule**.

### What it means

The comment must NOT contain:
- The student's numbers (e.g. "Your DataFrame had 26 rows" or "You filtered to 14 buildings")
- The "correct" numbers (e.g. "The expected answer was 12 rows after the join")
- Any comparison of value vs value (e.g. "You got 26, the expected was 12")
- Specific data interpretations the assignment was supposed to elicit

### Why fairness

Naming a value lets the student **swap the number to chase the answer** instead of fixing the reasoning. They'll patch their submission to match the comment, but the underlying misunderstanding survives. The same comment for a re-submission would then be wrong about a value that's now correct, and the cycle starts over.

### Why safety

LLMs hallucinate numbers. A comment that names a value is a comment the instructor MUST verify by hand before posting. A comment that names a **concept** is safe by construction — there's no value to verify.

### The substitution: concept + question

Replace `you got 26 rows but the right answer is 12` with:

> The key tool here is counting *distinct entities* rather than rows — when one building shows up across many months, counting rows lets each month re-count the building. Which Python/SQL operation gives you one row per unique value?

This explains the **concept** behind the miss and **poses the question** that leads the student to it. The student does the work; the comment doesn't do it for them.

---

## 3 — Tone (the dial)

Across instructors the dial settings differ; the dial itself is the same.

### The dimensions to calibrate per instructor

| Dimension | Low setting | High setting |
|---|---|---|
| **Warmth** | Clinical / procedural | Warm / personal / "I" |
| **Directness** | Hedged / "you might consider..." | Plain / direct / "do X" |
| **Technical density** | Approachable / metaphor-first | Technical / vocabulary-dense |
| **Encouragement frequency** | Once per comment | Multiple per comment |
| **Brevity** | 2 short paragraphs | 5+ paragraphs |

### Cross-instructor invariants

These hold regardless of dial settings:

- **Conversational, not formal.** No `pursuant to`, `in alignment with the rubric criteria`, etc. The comment is one professional talking to another professional in training.
- **Plain English.** Define jargon on first use or replace it with a phrase.
- **Instructor-to-student**, not robot-to-record. Use "I" and "you" naturally.
- **No bureaucratese.** No "going forward," no "moving the needle," no "leveraging."
- **No emojis** unless the per-instructor voice file explicitly opts in.

---

## 4 — The edit roundtrip (how the per-instructor voice file gets built)

The voice file is **learned**, not hand-authored on day one. Protocol:

### Step 1 — Bulk-emit ALL comments to ONE file

The grader produces a single `feedback/all_comments.md` (or similar) for the cohort, with every student's comment plus their score, by key. Not the per-student files — those are for the appeals/review path. This single file is the **instructor's editing surface**.

### Step 2 — Instructor edits in their voice

The instructor reads through, edits every comment to match their voice. This is fast (5–10 min per comment after the first few) and produces the truth. Edits go in-place on the same file.

### Step 3 — Sync edits back into per-student files

A tool (e.g. `sync_voice_edits.py`) parses the edited `all_comments.md`, splits by key, and overwrites the per-student `<KEY>.md` files with the instructor's text. The per-student files become the artifact of record.

### Step 4 — Bake recurring patterns into the per-instructor voice file

After step 3, the instructor scans their own edits for **patterns**:

- Words they consistently removed (→ banned-terms list)
- Phrasings they consistently shortened (→ "preferred phrasing" examples)
- Structural choices they always made (→ update the structure section's per-instructor notes)
- Encouragement frequency that emerged (→ pin the dial setting)

These go into `student_feedback_voice_<instructor>.md` so the **next** cohort's auto-emit starts much closer to the instructor's voice and the edit pass is shorter.

### Why both review surfaces matter

The all-comments overview (one file) is the **fast pass** — read the cohort in 20 minutes, see the spread, see whose comments are weird, edit the bad ones. The per-student files are the **evidence behind a score** — what the student will see if they appeal, what the instructor reads if they need to defend a band. **Keep both.** Don't try to grade out of one and review out of the other; you'll forget what's in the comment by the time you push.

---

## 5 — Banned patterns (default list — extendable per instructor)

These are AI-tells that nearly every instructor edits out. They go in `grader_voice_knowledge.md` as the **default banned list**; per-instructor files extend or remove items.

### Word-level

| Pattern | Why banned | Replace with |
|---|---|---|
| `idiomatic` | Round-2 specific tell; sounds clinical | Be specific about what's idiomatic (e.g. "more conventional Spark usage") or omit |
| `leveraging` / `leverage` | Bureaucratese | "Using" |
| `going forward` | Filler; nothing-bureaucratese | Just say what to do next, or omit |
| `moving the needle` | Marketing jargon | Concrete language |
| `pursuant to` / `in accordance with` | Legalese | Plain reference |
| `as per the rubric` | Bureaucratese | Reference the band by name |
| `unpack` (as in "let's unpack...") | Therapy-talk; preachy | "Look at" / "think about" |
| `the user` / `the learner` | Reader of the comment IS the student | "You" |
| `delve into` / `delve` | LLM tell | "Look at" / "dig into" |

### Phrase-level

| Pattern | Why banned |
|---|---|
| `Here are two things I noticed...` (or "a couple of...") | Filler preamble — see §1 anti-pattern |
| `Great job!` followed by criticism | Praise sandwich; reads as performative |
| `Overall, this was a strong submission, but...` | The "but" cancels the "strong." Replace with the specific strength + drop the contrast. |
| `Hope this helps!` (as closing) | Reflexive AI closing; doesn't add anything. Use the habit-to-build paragraph instead. |
| `I noticed that you...` (every paragraph) | Repetitive opener. Vary or drop. |
| `One thing to consider...` (every paragraph) | Same. |

### Structure-level

| Pattern | Why banned |
|---|---|
| Multiple coaching points per paragraph | Hard to read; reader stops at first. One idea per paragraph (§1). |
| Internal-only "Notes for instructor" sections that the student doesn't see | The comment IS the coaching. Don't keep a hidden version. |
| Per-criterion point arithmetic in the comment ("3/4 for clarity, 2/4 for evidence") | Holistic scoring (`grader_knowledge.md` §2). Comment names the band, not the math. |

---

## 6 — Template openers are intentional (NOT an AI tell)

The grader emits openers like `Overall: Strong` because the structure (§1) requires them. A student reading three classmates' comments will see the same opener three times. **This is by design, not an AI tell.**

Why it's safe:
- The opener is a **functional element** of the comment (the band) — students benefit from finding it in the same place every time.
- The body of the comment is per-student, written against the student's actual work.
- The instructor's voice file shapes the body; the opener stays canonical.

The instructor can override the opener wording per their voice file (e.g. `Score: Strong` instead of `Overall: Strong`) — but consistency across the cohort is correct, not lazy.

---

## 7 — What does NOT go in the comment

The Canvas comment is the **public student-facing artifact**. Several things the grader produces never reach it:

| Surface | Where it goes | Why not in the comment |
|---|---|---|
| Per-criterion point breakdown | Per-student file (review surface only) | Comment names the band, not the math (§5) |
| Internal calibration / spread notes | Per-student file or audit log | Student doesn't need to know they were a 0.5-spread borderline |
| Wellbeing flags | `_checkin_flags.md` (instructor-only) | Compassion is a private conversation, not a record (`grader_knowledge.md` §9) |
| Reconciliation evidence (claim vs earned) | Keyed actuals sheet (instructor review) | The earned grade IS the comment's band; the gap analysis is for the instructor's decision |
| The instructor's coaching-to-self notes about a student's pattern across the term | Local instructor journal | Not the AI's to write |

---

## 8 — When the comment doesn't fit

Some grades push with `--grade-only` (`grader_knowledge.md` §7) — no comment. Examples:

- The consequential grade in a multi-output flow (one assignment gets the comment, the other gets `--grade-only`).
- Grades pushed retroactively for completion-only items.
- The `default-comment` flag pattern, where every student in a batch gets a fixed short comment ("See Mid Review for detailed feedback").

The structure (§1) still applies when there IS a comment. The voice file still gates the words. But "no comment" is a valid output of the grader, not a failure.

---

## 9 — Per-instructor file contract (what `student_feedback_voice_<instructor>.md` must contain)

The shape the grader expects to find when it loads a per-instructor voice file:

```
# Voice — <Instructor name>

## Dial settings
Warmth: <low / medium / high>
Directness: <low / medium / high>
Technical density: <low / medium / high>
Encouragement frequency: <once / multiple>
Brevity: <2 paragraphs / 3-4 / 5+>

## Opener wording
"<the literal opener — e.g. 'Overall: <Tier>' or 'Score: <Tier>'>"

## Strength sentence template
"<one-line guide for the post-opener strength sentence>"

## Coaching paragraph opener (if any consistent one)
"<the literal opener — or 'vary, no template'>"

## Habit-to-build closing template
"<one-line guide for the closing paragraph>"

## Extra banned terms (instructor-specific, beyond the default list in grader_voice_knowledge.md §5)
- term1 → replace with X
- term2 → omit

## Preferred phrasings (instructor's characteristic moves)
- pattern → instructor's version

## Worked example (one full comment, instructor-edited)
<a real edited comment, keyed, with the band noted>
```

The grader reads this at runtime alongside the rubric and the per-class course context. Adding a new instructor to the toolkit is **writing one of these files** + running the §4 roundtrip on a calibration cohort.

---

## Quick-reference: the voice rules in one paragraph

The Canvas comment is the only artifact the student sees, so it carries every coaching point — never feed back data values (concept + question instead); use the structure `Overall: <Tier>` → one-sentence strength → `Coaching Tips:` header → one idea per paragraph → habit-to-build closing; honor the per-instructor banned-terms list and dial settings loaded from `student_feedback_voice_<instructor>.md`; learn the voice through the edit roundtrip (emit all-comments → instructor edits in their voice → sync back → bake patterns into the voice file); and remember the leak surface is what's IN the comment — keep wellbeing specifics, per-criterion arithmetic, and reconciliation evidence OUT (those live on instructor-only surfaces).

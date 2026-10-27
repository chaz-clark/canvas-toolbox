---
name: voicing
description: Use whenever you draft ANY student-facing text — grading comments, feedback, the "your grade" note, an announcement, an email. Load and apply the instructor's established VOICING PROFILE (their feedback tone/voice) so every comment sounds like them, not like a fresh AI voice each time. Never invent a new voice when a profile exists. Load this together with the `grading` skill before writing feedback.
---

# Voicing

Student-facing text should sound like the **instructor**, consistently — the same
warmth, directness, and phrasing across every assignment. The failure this prevents:
an agent invents a *new* voice each session (or per assignment), so a student gets
feedback that reads differently every time and doesn't match the instructor's.

## The one rule

**Before drafting any student-facing comment, load the course's voicing profile and
write in that voice. Never make up a new one when a profile exists.**

## How to name the student in it

**Given name plus last initial — never a full surname**, not in headers, not in
parentheticals, not in peer mentions. This is Zone 2-Adjacent text (constitution →
FERPA discipline): the artifact IS the student-facing text, so a name belongs in it,
but the convention limits what accumulates in the repo and in transcripts. It is
exposure minimization, **not** de-identification — a first name plus an initial
usually resolves to one person in a small section, so it never makes a name safe to
place beside a score, a rubric criterion, or a standing. That line is unconditional.

Operator-facing scaffolding in a working file — what you need to locate and confirm
the right thread before delivering into it — is not student-facing text and may carry
full names. The test is necessity for navigation, not convenience: if removing it
wouldn't make the artifact harder to find, it isn't scaffolding. It lives under an
already-gitignored path. See the constitution's FERPA section for the full rule.

## Find the profile — two layers

A voice has two parts, and they live in two places:

| Layer | Location | Holds |
|---|---|---|
| **Instructor** | `~/.canvas/FEEDBACK_VOICE.md` | What stays true across every course the instructor teaches: core principles, dial settings, banned jargon and phrases, the "never recite scores" and poka-yoke rules |
| **Course** | `grading/FEEDBACK_VOICE.md` | Only what differs for this course: comment shapes per assignment type, template openers, tier names, course-specific rules and examples |

**Load both, instructor first, then the course.** Where they conflict the **course wins**
— it overrides, it doesn't silently merge. If only one exists, use it alone: a course
profile that stands by itself (the DS250 / ITM327 / DS460 style) is still valid, so a
fresh clone or a TA on another machine isn't left without a voice.

The instructor layer is the instructor's own file in their home directory — never
committed to a course repo, and not a credential (that is `~/.canvas/config`, which you
never read). Neither layer is student PII, so both are safe to read.

Fallbacks when `grading/FEEDBACK_VOICE.md` is absent, in order:
1. `grading/tasks/feedback_voice*.md` or `agents/knowledge/student_feedback_voice*.md`
   — older/alt spots some courses used before the convention settled
2. A location the course `AGENTS.md` names (some courses point to their own)

Read the files fully before you write. A course profile should not restate the instructor
layer — if you see the same rule in both, drop it from the course file.

## The standard structure

Profiles follow a shared skeleton (see `FEEDBACK_VOICE.template.md` in this skill) —
so once you know it, you can read any course's profile fast:

- **Core principles** — how feedback should read (second person, specific, short, …)
- **Banned jargon (hard rule)** — words/phrases that read as "AI"; NEVER use them
- **Template openers — keep them** — intentional frames to preserve, not "improve"
- **Comment structure (by assignment type)** — the shape per KC / milestone / review /
  final-letter: what to lead with, order, length, how to deliver criticism
- **Before / after** — "too AI" vs in-voice pairs (the sharpest signal)
- **Hard rules / poka-yokes** — non-negotiables (e.g. never blame a student for the
  course's own inconsistency)

Apply **all** of it. When the profile and a rubric conflict, the rubric governs *what*
you say; the profile governs *how* you say it.

## If there is no profile yet

Do **not** silently invent one. Instead:
1. Copy `FEEDBACK_VOICE.template.md` (in this skill) as the structure.
2. Fill it from the instructor — ask about tone, openers/closers, jargon they hate,
   how blunt to be — **and** from their existing edited comments if any are available.
3. Save it to **`grading/FEEDBACK_VOICE.md`** so every future comment reuses it — that's
   the whole point. Confirm the save with the instructor.

## Promoting shared rules to the instructor layer

When an instructor has a profile and **no** `~/.canvas/FEEDBACK_VOICE.md` — or has two
or more course profiles repeating the same rules — offer to promote:

1. Copy `INSTRUCTOR_VOICE.template.md` to `~/.canvas/FEEDBACK_VOICE.md`.
2. Move into it the sections that read the same in every course (core principles, dial
   settings, banned jargon/phrases, universal hard rules). Show the instructor what
   moves; do it for them — don't hand them a dotfile to edit.
3. Delete those lines from the course file, leaving only what is course-specific.

Never promote a rule that names a course, tier, assignment type, or tool.

## Where this plugs in

- **Grading feedback** (`grader_push` comments, `grader_letter_comments` End-Letter
  notes): draft in the profile's voice, then the usual HG-5 review/push.
- The profile shapes *voice only* — it never changes a grade, a rubric score, or the
  HG-5 gate. Load the `grading` skill for those.

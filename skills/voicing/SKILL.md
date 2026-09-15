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

## Find the profile (check, in order)

1. **`grading/FEEDBACK_VOICE.md`** — the canonical location (what DS250 / ITM327 use)
2. `grading/tasks/feedback_voice*.md` or `agents/knowledge/student_feedback_voice*.md`
   — older/alt spots some courses used before the convention settled
3. A location the course `AGENTS.md` names (some courses point to their own)

The profile is course context (the instructor's voice — **not** student PII), so it's
Zone-1: safe to read and to commit. Read it fully before you write.

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

## Where this plugs in

- **Grading feedback** (`grader_push` comments, `grader_letter_comments` End-Letter
  notes): draft in the profile's voice, then the usual HG-5 review/push.
- The profile shapes *voice only* — it never changes a grade, a rubric score, or the
  HG-5 gate. Load the `grading` skill for those.

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

## Find the profile (check, in order)

1. `VOICING.md` at the course root
2. `grading/voicing.md` (or `grading/voicing_profile.md`)
3. A location the course `AGENTS.md` points to (some courses name their own)

The profile is course context (the instructor's voice — **not** student PII), so it's
Zone-1: safe to read and to commit. Read it fully before you write.

## Apply it

A voicing profile typically pins: overall tone (warm / direct / formal), how to open
and close, how to deliver criticism (sandwich? straight?), encouragement style,
signature phrases to **use** and ones to **avoid**, length, and second-person vs
third. Match all of it. When the profile and a rubric conflict on wording, the rubric
governs *what* you say; the profile governs *how* you say it.

## If there is no profile yet

Do **not** silently invent one. Instead:
1. Ask the instructor a few quick questions — tone, how they like to open/close,
   phrases they love/hate, how blunt to be about problems.
2. Draft a short profile from their answers **and their existing comments** if any
   are available for reference.
3. Save it to `VOICING.md` (or `grading/voicing.md`) so **every future comment reuses
   it** — that's the whole point. Confirm the save with the instructor.

## Where this plugs in

- **Grading feedback** (`grader_push` comments, `grader_letter_comments` End-Letter
  notes): draft in the profile's voice, then the usual HG-5 review/push.
- The profile shapes *voice only* — it never changes a grade, a rubric score, or the
  HG-5 gate. Load the `grading` skill for those.

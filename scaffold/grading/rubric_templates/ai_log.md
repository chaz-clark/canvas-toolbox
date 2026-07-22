# AI Log — Rubric (canonical 5-tier classification)

**Canvas grading:** instructor configures Pass/Fail OR scored. The canonical
stance most adopting instructors take is **"give feedback, not police"** —
classify the AI-use pattern for instructor signal, pass any honest
engagement. Mark as Fail only when the submission doesn't address the
assignment.

This template is per-instructor configurable. Edit `## Pass criteria` and
`## Per-student file shape` below to match your course.

## Tier classification — applied PER PROMPT/TURN

A single submission's prompts can span tiers. The grader classifies each
turn, then reports the percentage distribution. The "dominant" tier
becomes the headline; the full mixture is the formative signal.

| Tier | Named band | Observable in a single prompt/turn |
|---|---|---|
| 1 | Outsourcing             | "Do this for me." AI output copied verbatim. No follow-up, no first attempt. |
| 2 | Assisted production     | "Help me with ___" (= give me the answer) / "Correct this" with no prior work shown. Off-loads parts. |
| 3 | Scaffolded learning     | "Help me with ___" (= guide me through) / "Correct this for me ___" with prior work shown. Iterates, rejects bad suggestions. |
| 4 | Inquiry & verification  | "I want to understand ___" / "I just want to confirm ___" Has a hypothesis or specific question. |
| 5 | Critical inquiry        | "Why is it that ___" Questions AI's responses; tests its confidence; cross-checks against own knowledge. |
| N/A | No AI use stated        | Student submits "I did this myself." |

## Criteria checkability (issue #192, HG-1)

This is a **single-dimension** rubric — the whole submission is classified on one
axis (the AI-engagement tier), which is a **judgment** call. NLP contributes only
weak hints (e.g. detecting `"Why is it that"` / question-pattern turns as tier-5
signals); the tier itself is the LLM's read. Multi-criterion rubrics tag one row
per criterion; here there is one:

| Criterion | Checkability | Evidence hint |
|---|---|---|
| AI-engagement tier | judgment | question-pattern turns, hypothesis language → weak tier-5 hints only |

Validate + freeze: `uv run python canvas-toolbox/lib/tools/grader_rubric.py --rubric ./RUBRIC.md`.

## Pass criteria (instructor-edited)

- **Pass** = any honest engagement. Every tier mixture passes, including
  "No AI use." Trust the student's stated mode of working.
- **Fail** = the submission doesn't address the assignment (off-topic
  text, wrong file, blank).

Adapt these criteria for stricter courses (e.g. a CS integrity policy
that gates on Tier 1 — Outsourcing).

## AI safety checks (toolkit built-in)

1. **Prompt-injection guard** (sentinel-delimited per
   `grader_knowledge.md`) — required: student logs literally contain AI
   prompts; the sentinel keeps those as DATA, not instructions.
2. **Wellbeing flags** → `_checkin_flags.md`.

## Per-student file shape (template)

```markdown
# AI_LOG Feedback — <KEY>
**Score: Pass — primary tier: <name>** (or "No AI use stated")

## Evidence for the score

**Tier mixture (across N classified turns):**
- Tier 1 Outsourcing:            XX%  (n/N turns)
- Tier 2 Assisted production:    XX%  (n/N)
- Tier 3 Scaffolded learning:    XX%  (n/N)
- Tier 4 Inquiry & verification: XX%  (n/N)
- Tier 5 Critical inquiry:       XX%  (n/N)

**Cited examples per tier present:**
- Tier <n>: <one-line quote from the turn that exemplifies this tier>

## Suggested Canvas Comment (rubric-grounded)

> <instructor-configurable; default OFF for the SP26-style "no per-student
>  comment" approach>
```

## Notes for the instructor

- Edit the band names if "Outsourcing/Assisted/Scaffolded/Inquiry/Critical"
  doesn't fit your course's framing. The toolkit treats them as opaque
  string labels.
- The "Suggested Canvas Comment" block is what `grader_push_comments.py`
  (#57) extracts when posting comments. Leave it empty or remove the H2
  if you don't want comments posted for this assignment.

---
name: inverted_blooms_knowledge
version: '1.0'
last_updated: '2026-07-16'
description: 'Traditional Bloom''s assumes students build understanding before creating. AI inverts that: students can now *Create* first — which means assessment design must deliberately reclaim the lower levels.'
skill_type: knowledge
shape: reference
scope: 'Assessment-design framework for the AI age — audit whether assessments produce genuine student learning or inadvertently accept AI-generated work as a substitute. Boundaries: does not cover CLO well-formedness (see outcomes_quality) or Bloom verb classification (see taxonomy_explorer); layers on top of those, not replaces them.'
consumed_by:
- canvas_course_expert.md
- ira_program_alignment.md
provenance:
  sources:
  - Kassorla, M. Inverted Bloom's for the Age of AI. Substack. https://michellekassorla.substack.com/p/inverted-blooms-for-the-age-of-ai
companion_json_deprecated: 2026-07-16 - consolidated into YAML frontmatter (JSON purge convention)
runtime_strategy: read_at_runtime
metadata:
  knowledge_id: inverted_blooms_knowledge
---

# Inverted Bloom's — Assessment Design for the Age of AI

A framework for auditing whether course assessments are designed to produce genuine student learning, or whether they inadvertently accept AI-generated work as a substitute for it.

> Traditional Bloom's assumes students build understanding before creating. AI inverts that: students can now *Create* first — which means assessment design must deliberately reclaim the lower levels.

**Source:** Kassorla, M. *Inverted Bloom's for the Age of AI.* Substack. https://michellekassorla.substack.com/p/inverted-blooms-for-the-age-of-ai

---

## The Core Shift

Traditional Bloom's Taxonomy runs bottom-up: students build foundational knowledge and work their way up to complex creation.

**Traditional model:** Remember → Understand → Apply → Analyze → Evaluate → Create

This sequence assumed that students who produced sophisticated work had already internalized the lower levels to get there. That assumption is broken in an AI-enabled environment.

**What changed:** Students now have access to tools that generate high-quality outputs at the *Create* level on demand — before they have built the understanding, analysis, or memory that traditionally preceded creation. The output can look polished while the learning didn't happen.

---

## The Inverted Model

Kassorla inverts the taxonomy to reflect how AI-era students actually enter work:

| Agency Level | Bloom's Stage | Student Behavior | AI Influence |
|---|---|---|---|
| 1 | **Create** | Submits AI-generated artifact with minimal engagement | Maximum |
| 2 | **Evaluate** | Judges AI output using AI-supplied criteria | High |
| 3 | **Analyze** | Breaks down AI feedback superficially | Moderate-High |
| 4 | **Apply** | Implements insights with increasing personal initiative | Moderate |
| 5 | **Understand** | Makes connections through reflection and iteration | Low |
| 6 | **Remember** | Internalizes knowledge independently, without AI scaffolding | Minimal |

**The goal of assessment design:** scaffold students *down* the agency scale — from AI-dependent creation toward student-owned understanding and retention. The measure of success is not the quality of the final artifact; it is the evidence that the student's own thinking produced it.

---

## Productive Friction

The key mechanism is **productive friction** — the cognitive struggle that generates authentic learning. AI bypasses this friction by default. Assessment design must deliberately reintroduce it.

Productive friction examples:
- Revision cycles with instructor or peer feedback before final submission
- Staged drafts with required justification for changes
- Oral defense or live explanation of submitted work
- Process documentation (annotated bibliography, design journal, revision history)
- Failure states that must be diagnosed and corrected (not just avoided)

Without productive friction, a polished submission is evidence of AI use, not student learning.

---

## The Post-Creation Learning Journey

The inverted model reframes what outcomes need to specify. Traditional outcomes say what students will *produce*. AI-age outcomes need to also specify how students will *own* the production — the reasoning and reflection that prove the work was genuinely theirs.

**Traditional outcome framing:**
> "Students will design a marketing campaign for a target demographic."

**AI-age outcome framing adds the ownership clause:**
> "Students will design a marketing campaign for a target demographic *and* explain, in a recorded debrief, why each design decision was made and what alternatives were rejected."

The added clause is not busywork — it is the only evidence that the student traveled through Understand and Apply before arriving at Create.

---

## Canvas Audit Indicators

Flag the following when reviewing assessments in Canvas:

**`ai_dependent` signals:**
- Rubric evaluates only the final artifact — no criteria for process, reasoning, or iteration
- Assignment instructions ask for a deliverable with no evidence-of-thinking requirement
- No staged submission (no draft, outline, or checkpoint before the final)
- No peer review, reflection prompt, or oral component
- CLO could be satisfied by submitting an AI-generated response unchanged
- Submissions are text-only products (essay, report, presentation) with no embedded rationale

**`scaffolded` signals:**
- At least one stage before the final submission (draft or outline required)
- Rubric includes at least one process criterion ("sources evaluated," "revision explained")
- Reflection prompt exists but is a separate, low-weight item
- Peer feedback is optional or ungraded

**`student_owned` signals:**
- Rubric explicitly scores reasoning and decision-making, not just the artifact
- Multiple checkpoints with required justification for changes
- Oral defense, screenshare walk-through, or live explanation is part of the grade
- Process documentation is graded equally with or heavier than the artifact
- Assignment design includes deliberate failure states or revision cycles
- AI use policy is assignment-specific and tied to rubric criteria, not just a general course policy

---

## Practical Test for Auditors

For each graded assessment in a module, ask three questions:

1. **Could a student submit this assignment by pasting AI output and meet the rubric?**
   → Yes = `ai_dependent`

2. **Does the rubric evaluate how the student *thought*, not just what they *submitted*?**
   → No = `ai_dependent` or `scaffolded` at best

3. **Is there productive friction built into the assignment — a stage where failure is possible and must be corrected?**
   → Yes = candidate for `student_owned`

---

## Relationship to Traditional Bloom's

This framework does not replace Bloom's — it layers on top of it. The existing taxonomy tells you *what level of thinking* an outcome requires. The Inverted Bloom's lens tells you *whether the assessment actually requires the student to do that thinking*, given that AI can now simulate most of the output.

A course can have all six Bloom's levels represented in its outcomes and still be fully `ai_dependent` in its assessment design if it only evaluates the artifact, not the process.

---

## Quick Reference for Auditors

1. **Pick any graded assessment.** Can AI satisfy the rubric undetected?
2. **Check for staged submissions** — at minimum one checkpoint before the final
3. **Read the rubric** — are any criteria about *how* the student reasoned, not just *what* they produced?
4. **Look for oral, live, or screencast components** — strongest signal of `student_owned`
5. **Check CLOs against the assessment** — does the CLO require demonstrating judgment, not just producing an artifact?
6. **Review AI use policy** — is it assignment-specific or generic? Specific = more intentional design

**Audit tag:** `ai_agency` ∈ {`ai_dependent`, `scaffolded`, `student_owned`}

**Pairs with:**
- `outcomes_quality_knowledge.md` — well-formed CLOs need to anticipate AI generation; ownership-clause framing starts at the outcome level
- `designer_thinking_knowledge.md` — backward design now means designing the productive friction backward from the outcome, not just the assessment task
- `cognitive_load_theory_knowledge.md` — germane load (schema formation through effortful processing) is precisely what AI bypasses; `student_owned` designs maximize germane load

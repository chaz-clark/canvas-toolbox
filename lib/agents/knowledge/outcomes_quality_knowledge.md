---
name: outcomes_quality_knowledge
version: '1.0'
last_updated: '2026-07-16'
description: Judging the wording quality of a learning outcome — alignment to a poorly-written outcome is meaningless; criteria for measurable, well-formed outcomes.
skill_type: knowledge
shape: reference
scope: 'Framework for evaluating whether learning outcomes are well-formed BEFORE auditing whether they are aligned. Alignment checks that outcomes are wired together; this framework checks that the outcomes themselves are worth wiring. Boundaries: alignment traceability lives in course_design_language Principle 6; Bloom verb classification lives in taxonomy_explorer.'
consumed_by:
- canvas_course_expert.md
- canvas_new_course_setup.md
- ira_program_alignment.md
- clo_quality_audit.py
provenance:
  sources:
  - Morrison, G.R., Ross, S.M., Morrison, J.R., & Kalman, H.K. (2019). Designing Effective Instruction, 8th ed. Chapter 5. Wiley.
  - BYU-Idaho Learning and Teaching. Learning Outcomes. learningandteaching.byui.edu
  - BYU-Idaho Assurance of Learning. CLO Rubric AoL (internal document).
  - Anderson, L.W., Krathwohl, D.R., et al. (2001). A Taxonomy for Learning, Teaching, and Assessing.
  - Merrill, M.D. (1983). Component Display Theory.
companion_json_deprecated: 2026-07-16 - consolidated into YAML frontmatter (JSON purge convention)
runtime_strategy: read_at_runtime
metadata:
  knowledge_id: outcomes_quality_knowledge
---

# CLO Quality & Outcome Hierarchy

A framework for evaluating whether learning outcomes are well-formed before auditing whether they are aligned. Alignment checks that outcomes are *wired together*; this framework checks that the outcomes themselves are *worth wiring*.

> If the outcome isn't well-written, alignment to it is meaningless.

**Sources:**
- Morrison, G.R., Ross, S.M., Morrison, J.R., & Kalman, H.K. (2019). *Designing Effective Instruction*, 8th ed. Chapter 5. Wiley.
- BYU-Idaho Learning and Teaching. *Learning Outcomes*. learningandteaching.byui.edu
- BYU-Idaho Assurance of Learning. *CLO Rubric AoL* (internal document).

---

## The Outcome Hierarchy

At BYU-Idaho (and most accredited institutions), outcomes are nested from general to specific. Each level is responsible for a distinct scope of learning:

| Level | Description | Assessed by |
|---|---|---|
| **ILO** — Institutional Learning Outcome | University-wide graduate goals (e.g., disciple-leadership model) | Indirect or proxy measures |
| **PLO** — Program/Major Learning Outcome | Competencies for a degree; what graduates will *do* | Combination of direct + indirect measures |
| **CLO** — Course Learning Outcome | What a student achieves by completing the course; skills and competencies | Direct measures (exams, projects, rubrics) |
| **LLO** — Lesson/Class Learning Outcome | What a student achieves in a single class session | Direct measures within a session |

**The rule:** Classroom outcomes accomplish course outcomes. Course outcomes, combined across a program, accomplish program and institutional outcomes. If any level is broken, the level above it is unsupported.

**BYUI full hierarchy (general → specific):**
University Academic Outcomes → Foundations Outcomes → College Outcomes → Department Outcomes → Major Outcomes → Course Outcomes → Lesson Outcomes

### BYUI's 5 Kinds of Learning Outcomes

BYU-Idaho groups all outcomes — at any level — into five types that can coexist in a single course:

| Kind | What it targets |
|---|---|
| **Knowledge** | Information, concepts, facts students will know |
| **Character & Values** | Attitudes, professional behavior, judgment |
| **Skills** | Observable abilities students can perform |
| **Experiences** | Meaningful contexts that shape perspective |
| **Learning-to-Learn** | Metacognitive habits, self-regulation |

Most audits find CLOs only in the Knowledge and Skills buckets. The high-value gap is almost always Character & Values — outcomes that imply professional judgment but never name it.

---

## What Makes an Outcome Well-Formed

### The Standard Statement Format

Every outcome, regardless of level or type, follows this pattern:

> **The student will be able to:** *[action verb]* + *[subject-content reference]*

Optional additions that sharpen precision (especially for mastery or competency-based programs):
- **Level of achievement** — the minimum performance standard ("…with 90% accuracy," "in proper order")
- **Conditions of performance** — constraints under which the student performs ("Given a client scenario," "Using only the tools provided in class")

### Behavioral vs. Cognitive Objective Formats

Two accepted approaches (both valid — choose based on context):

**Behavioral (Mager-style):** Most precise. Specifies verb + content + optional standard + optional conditions. Best for mastery-based or competency-based programs.
> *Given five black-and-white photographs of insects, the learner will correctly identify the three insects detrimental to corn.*

**Cognitive (Gronlund-style):** More flexible. States a general outcome, then lists 2–3 sample behaviors that indicate mastery. Best for higher-order outcomes where the full range of performance can't be specified in advance.
> *Interprets a graph.*
> 1. Determines which group sold the most.
> 2. Identifies groups performing below average.
> 3. Determines the year with the greatest number of sales.

---

## The AoL CLO Quality Rubric (6 Criteria)

BYU-Idaho's Assurance of Learning rubric scores CLOs on six dimensions. Apply each as a pass/flag during audit:

| Criterion | Great | Good | Needs Work |
|---|---|---|---|
| **Scope** | 3–6 CLOs total | 3–8 CLOs total | <3 or >8 CLOs |
| **Language Clarity** | No jargon; no subjective or comparative language | Some jargon or comparative language present | Not stakeholder-friendly; heavy jargon |
| **Measurable** | Observable action verb enables mastery validation | Not all verbs are observable | No observable action verb |
| **Single-barreled** | Each CLO targets exactly one goal | Some CLOs contain more than one goal | All CLOs are multi-goal |
| **Rigor** | Mix of know/do/become verb levels, appropriate to course level | Some outcomes are mismatched to course level, or rigor spread is missing | All outcomes at same (wrong) level |
| **Relevance** | Logical fit for the course | Relevance to course is ambiguous | Outcomes don't fit the course, or insufficient data |
| **Recency** | Based on current industry practices/research | Some outcomes reflect dated practices | All outcomes based on outdated research |

**Scoring note:** Scope and Measurability failures are the most common and the most fixable. Rigor failures are the most consequential — a course where all CLOs are at Bloom's *Remember* level cannot produce the higher-order thinking its PLO requires.

---

## The Process vs. Outcome Anti-Pattern

The most common writing error: stating what the *instructor* does or what *activity* students complete, instead of what the *student* achieves.

| Anti-pattern | Problem | Fix |
|---|---|---|
| "To view a videotape on ecological safeguards" | Describes an activity, not an outcome | Rewrite: "Evaluate the ecological impact of [X] using the criteria discussed in class" |
| "The instructor will describe types of fire extinguishers" | Instructor-focused | Rewrite: "Given a combustible material, select the appropriate fire extinguisher type" |
| "The learner will use PowerPoint to learn fire safety" | Focuses on tool/process, not knowledge/skill | Rewrite: "Classify fire extinguisher types by combustible material category" |
| "Students will understand the water cycle" | Non-observable verb | Rewrite: "Students will explain the water cycle, identifying each phase and its cause" |

**Test:** Ask — *"Is this outcome what I want the learner to know or demonstrate after completing the topic?"* If the answer is no, rewrite it.

---

## Observable Verb Reference (Bloom's Revised, Anderson et al. 2001)

| Level | Observable Verbs |
|---|---|
| **Remembering** | arrange, define, duplicate, label, list, match, memorize, name, order, relate, repeat, reproduce, state |
| **Understanding** | classify, describe, discuss, explain, express, identify, indicate, locate, report, restate, review, select, sort, tell, translate |
| **Applying** | apply, choose, demonstrate, dramatize, employ, illustrate, interpret, operate, practice, prepare, schedule, sketch, solve, use |
| **Analyzing** | analyze, appraise, calculate, categorize, compare, contrast, criticize, diagram, differentiate, discriminate, distinguish, examine, experiment, question, test |
| **Evaluating** | argue, assess, defend, design, determine, evaluate, judge, predict, rate, value |
| **Creating** | combine, construct, decide, estimate, formulate, organize, predict, rank, synthesize, write |

**Flag verbs:** "understand," "know," "appreciate," "be aware of," "learn," "feel," "recognize" — all non-observable. Replace with a verb from the appropriate Bloom's level.

---

## The Performance-Content Matrix (Merrill 1983)

A secondary classification tool that helps select the right instructional strategy for each objective. Classify each CLO by its content type AND performance level:

| Content Type | Description | Performance |
|---|---|---|
| **Fact** | A specific association (Columbus was an explorer) | Recall only — facts cannot be applied |
| **Concept** | A category or class (what counts as a "mammal") | Recall or Application |
| **Principle/Rule** | A relationship between concepts ("metal expands when heated") | Recall or Application |
| **Procedure** | A sequence of steps to achieve a goal | Recall (list steps) or Application (perform) |
| **Interpersonal** | Spoken/nonverbal interaction skills | Application |
| **Attitude** | Disposition toward an action or situation | Application (inferred from behavior) |

**Why it matters for audit:** A course designed around Fact-Recall objectives cannot develop Procedure-Application competencies. Mismatches between the content type, performance level, and instructional strategy are the root cause of "we covered it, but they can't do it."

---

## Canvas Audit Indicators

Flag when reviewing a course in Canvas:

- No outcome statements visible in course intro page, module overviews, or syllabus
- Outcomes use "understand," "know," "appreciate," or other non-observable verbs
- Fewer than 3 or more than 8 CLOs for the course
- All CLOs cluster at the same Bloom's level (no rigor spread)
- Outcomes describe instructor activities ("students will read chapter 5") rather than learner achievements
- All outcomes are Knowledge-type — no Character/Values, Skills, Experiences, or Learning-to-Learn outcomes present
- Rubric criteria don't trace back to a named CLO

---

## Quick Reference for Auditors

1. **Count the CLOs** — 3–6 ideal; flag if <3 or >8
2. **Check every verb** — observable? Replace any "understand/know/feel"
3. **Single-barreled?** — one goal per CLO; split multi-goal outcomes
4. **Rigor spread?** — do verbs span at least 2–3 Bloom's levels?
5. **Student-focused?** — does each describe a change *in the student*, not an activity *for the student*?
6. **Kind coverage?** — are any of the 5 kinds (Knowledge, Character, Skills, Experiences, Learning-to-Learn) implied but unnamed?
7. **Rubric traceback?** — does each major assessment have a rubric criterion that maps to a CLO?

**Audit tag:** `clo_quality` ∈ {`meets_criteria`, `partial`, `needs_revision`}
**Companion tag:** `clo_criteria_flags` — list which of the 6 AoL criteria fail (scope, clarity, measurable, single_barreled, rigor, relevance, recency)

**Pairs with:** `designer_thinking_knowledge.md` (the upstream question — why write outcomes at all?), `taxonomy_explorer_knowledge.md` (the BYUI verb tool for writing them), `three_domains_knowledge.md` (the academic framing for rigor and domain coverage).

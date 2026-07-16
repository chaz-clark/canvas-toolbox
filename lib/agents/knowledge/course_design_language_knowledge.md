---
name: course_design_language_knowledge
version: '1.0'
last_updated: '2026-07-16'
description: Whether a BYU-I course reads as a coherent, well-designed artifact — visual grammar, rubric quality, and alignment across the course map.
skill_type: knowledge
shape: identity
scope: 'The canonical design-language specification for BYU-Idaho Canvas courses — prescriptive principles for whether a course feels like one coherent artifact to the student. Boundaries: does not cover Hattie phase progression (see hattie_3phase) or working-memory mechanics (see cognitive_load_theory); see those files plus designer_thinking, taxonomy_explorer, toyota_gap_analysis for adjacent concerns.'
consumed_by:
- canvas_course_expert.md
- canvas_content_sync.md
provenance:
  sources:
  - BYU-Idaho Architects of Learning course (405800) — the course whose subject matter is course architecture and whose own build is the exemplar.
  - 'Companion frameworks: hattie_3phase_knowledge.md, cognitive_load_theory_knowledge.md, designer_thinking_knowledge.md, taxonomy_explorer_knowledge.md, toyota_gap_analysis_knowledge.md.'
  - 'BYUI institutional view: see agents/templates/byui_course_design/ for the 11 HTML component templates and 1 rubric JSON shape that implement these principles.'
companion_json_deprecated: 2026-07-16 - consolidated into YAML frontmatter (JSON purge convention)
runtime_strategy: read_at_runtime
principles:
- id: unified_visual_grammar
  name: Principle 1 — Unified Visual Grammar
  compact_statement: Every artifact is assembled from the same small set of components (banner, role chip, title, section headers, callout boxes, cards with semantic top-borders, tables with primary-color headers). Students learn the grammar once on Week 01 and get it for free for the rest of the course.
- id: narrative_metaphor
  name: Principle 2 — Sustained Narrative Metaphor
  compact_statement: The course is named for a metaphor and the metaphor is load-bearing, not decorative — it appears in the course title, recurring component names (Architect's Lens, Architect's Reflection, Architect's Question), the reasoning of every weekly purpose statement, and in the capstone.
- id: dual_framing
  name: Principle 3 — Dual-Framing on Every Task
  compact_statement: Every instructional artifact opens with a two-panel header — one panel answers why this exists (Purpose / The Metaphor), the other answers what you will have by the end (Overview / The Outcome). Neither panel is optional and neither may repeat the other.
- id: structural_beats
  name: Principle 4 — Consistent Structural Beats
  compact_statement: Every week page hits the same sections in the same order (Banner → Core Questions → Purpose → Preparation → Weekly Schedule); every assignment hits its own beats in order (Banner → Purpose+Overview → Instructions Parts → Submission Criteria → Architect's Reflection); every syllabus hits its order. Students develop an automatic navigation schema.
- id: observable_rubrics
  name: Principle 5 — Rubrics as Observable Behaviors, Not Adjectives
  compact_statement: Use a 3-level rating scale (Meets / Developing / Does Not Yet Meet Expectations) on every rubric. Each rating has a description (name) and long_description (full sentence describing observable behavior). Meets-level descriptor names the minimum threshold, not aspirational. Include an Organization & Professional Communication criterion on every rubric.
- id: alignment_traceability
  name: Principle 6 — Alignment Traceability
  compact_statement: 'You can draw a straight line from any artifact a student touches back to a course-level outcome: Course Outcome → Module Outcome → Assessment → Rubric Criterion → Activity. A broken link anywhere is a latent gap. This operationalizes Designer Thinking''s Outcome → Evidence chain at the artifact level.'
metadata:
  knowledge_id: course_design_language_knowledge
---

# Course Design Language — Knowledge Reference

The canonical design-language spec for **BYU-Idaho** Canvas courses, derived from the faculty-development course **Architects of Learning** (course `405800`) — the course whose subject matter *is* course architecture and whose own build is the exemplar. Patterns in this file are **prescriptive**, not observational: if you are building or auditing a course at BYU-Idaho, this is the recipe.

**BYUI institutional view.** Other universities adopting this toolkit can fork the principles structure (visual grammar, narrative metaphor, dual-framing, structural beats, observable rubrics, alignment traceability) and swap the institution-specific implementation (palette, role-chip labels, banner image) for their own. See [`agents/templates/byui_course_design/README.md`](../templates/byui_course_design/README.md) for forking guidance.

Used by: `canvas_course_expert.md` (design/alignment audit), `canvas_content_sync.md` (generates artifacts against the recipe).

Companions:
- [`hattie_3phase_knowledge.md`](hattie_3phase_knowledge.md) — learning progression. Hattie tells you *whether learning is scaffolded*; this file tells you whether *delivery is coherent*. The two are independent axes.
- [`cognitive_load_theory_knowledge.md`](cognitive_load_theory_knowledge.md) — load mechanics. Every principle in this file primarily reduces extraneous load. The mapping table later in this file shows which principle hits which axis.
- [`designer_thinking_knowledge.md`](designer_thinking_knowledge.md) — backward design (Outcome → Evidence → Experience → Content → Reality Check). Principle 6 (Alignment Traceability) operationalizes Designer Thinking at the artifact level.
- [`taxonomy_explorer_knowledge.md`](taxonomy_explorer_knowledge.md) — Bloom's Revised verb classification. Principle 6 references Bloom-scaffolded module outcomes; defer to that file for verb-level classification.
- [`toyota_gap_analysis_knowledge.md`](toyota_gap_analysis_knowledge.md) — gap remediation. Findings from this file's principles get written up as Toyota A3 entries.

---

## Why this exists

Hattie tells you *whether learning is scaffolded*. CLT tells you *what consumes working memory*. Toyota tells you *how to close gaps*. None of them tell you whether the course **feels like one coherent artifact** to the student. Incoherence is pure extraneous load: even when content, assessments, and outcomes are all present, students burn working memory re-orienting on every page.

This file names six principles of coherence and gives the implementation recipe for each.

---

## The Palette

These six colors carry semantic meaning across every artifact. Do not introduce new accents; do not repurpose existing ones.

| Hex | Role | Used on |
|---|---|---|
| `#37474F` | Primary / assignment chrome | Assignment banner, chip, title, Instructions left-border, grading-scale header |
| `#006A79` | Instructional chrome | Week-instruction banner, chip, title, section-header text, Weekly Schedule table header |
| `#006EB6` | Core Questions / callout | Blue callout box border + heading |
| `#EE5655` | Foundational / resource | Red-topped cards (Readings & Resources, Foundational Documents) |
| `#DB9888` | Reflection / lens | Tan-topped cards (Architect's Lens, Architect's Reflection), accent underline on italicized subtitles |
| `#CFD8DC` / `#F5F7F8` / `#FBFBFB` / `#EEEEEE` | Neutrals | Card backgrounds, table borders, panel fills |

Typography: `'Open Sans', Arial, sans-serif` for every heading. Body inherits Canvas default. Icons: [Material Icons](https://github.com/google/material-design-icons) only — never mix icon libraries, never use emoji for functional roles.

---

## Principle 1 — Unified Visual Grammar

Every artifact is assembled from the same small set of components: banner + role chip + title (+ optional subtitle), section headers with an icon, callout boxes, cards with a semantic top-border, tables with the primary color in the header. Students learn the grammar once on Week 01 and get it for free for the rest of the course.

### Recipe (required on every instructional artifact)
1. **Banner image** — full-width, course banner file, background color matches the artifact's primary color
2. **Role chip** directly under the banner — one of: `Course Syllabus`, `Week NN Instruction`, `Week NN Assignment`, `Announcement`. Chip background = artifact's primary color; white text; `0.75rem`; `4px 12px` padding; `border-radius: 4px`
3. **H1 title** in the artifact's primary color, `2.2rem`, Open Sans, `line-height: 1.1`
4. **Optional subtitle** — gray `#666`, `1.1rem`, italic, left-border `3px solid #DB9888`, `padding-left: 15px`
5. **Content area** — white background, `40px` padding, `border: 1px solid #e0e0e0`, rounded bottom corners

Implementation: [`templates/byui_course_design/artifact_wrapper.html`](../templates/byui_course_design/artifact_wrapper.html).

### Gap signals (audit)
| Signal | What it means |
|---|---|
| Artifact has no banner or chip | Students can't tell what kind of thing they're on |
| Banner color doesn't match the chip/title color | Breaks the semantic palette |
| H1 uses a different font or size on different pages | No grammar; every page is a new read |
| Same content type rendered different ways across weeks | Pattern-breaking — trains the wrong mental model |
| Color used decoratively (different accent per page) | Noise, not signal |
| >6 accent colors on one page | Visual hierarchy collapses |

---

## Principle 2 — Sustained Narrative Metaphor

The course is named for a metaphor (*Architects of Learning*) and the metaphor is *load-bearing*, not decorative. It appears in the course title, in the name of recurring components, in the reasoning of every weekly overview, and in the capstone. Students carry the metaphor out of the course as the handle they hold the content by.

### Recipe
1. **Choose a single metaphor** that maps to the domain. For course-design courses: architecture (foundation, blueprint, load-bearing, stress test, structural integrity). For writing courses: craft (draft, revision, reader). Pick one and commit.
2. **Name recurring components with the metaphor**:
   - Reflection prompt on every week page → `The Architect's Lens`
   - Closing reflection on every assignment → `The Architect's Reflection`
   - Course-level guiding question → `The Architect's Question`
3. **Use the metaphor to reason in week purpose statements**:
   > *The Metaphor:* Just as an architect subjects a structure to stress tests, we must design assessments that accurately measure whether students can withstand the rigors of the "Peak Actions" we've identified.
   > *The Outcome:* By the end of this week, you will have a draft of your primary assessments that align with your weekly outcomes.
4. **Keep the metaphor visible in the capstone.** If Week 13 abandons the language, the metaphor was never load-bearing.

### Gap signals
| Signal | What it means |
|---|---|
| Metaphor named in syllabus, absent from weekly pages | Marketing language, not design language |
| Metaphor switches or mixes (architect + journey + recipe) | Framework thrash |
| Weekly artifacts use the metaphor in titles but not in reasoning | Surface decoration |
| Metaphor disappears after Week 3 or 4 | Writer fatigue, not design |

---

## Principle 3 — Dual-Framing on Every Task

Every instructional artifact opens with a two-panel header. One panel answers *why this exists*. The other answers *what you will have by the end*. Neither panel is optional and neither may repeat the other.

### Recipe — Week instruction page
1. **Core Questions callout** (blue, `#006EB6`) — 1–3 questions the week answers. Implementation: [`core_questions_callout.html`](../templates/byui_course_design/core_questions_callout.html).
2. **Purpose section** with two paragraphs:
   - **The Metaphor:** — relates the week to the course's central metaphor
   - **The Outcome:** — names the concrete artifact the student will have by week's end (a draft, a map, a reflection — never "understand X")

   Implementation: [`purpose_metaphor_outcome.html`](../templates/byui_course_design/purpose_metaphor_outcome.html).

### Recipe — Assignment
Two side-by-side flex panels at the top of the body (each `flex: 1; min-width: 280px;`):
- **Purpose** (left) — one sentence on why this assignment exists in the course arc
- **Overview** (right) — one sentence on what the student will produce

Implementation: [`assignment_purpose_overview.html`](../templates/byui_course_design/assignment_purpose_overview.html).

### Gap signals
| Signal | What it means |
|---|---|
| Page starts with instructions, no purpose | Student executing without knowing why |
| "Outcome" is a learning-objective verb ("students will understand") | No observable target |
| Purpose and Overview say the same thing | Dual-framing is performative, not functional |
| Assignment description opens with submission logistics | Priority inversion — admin before meaning |

---

## Principle 4 — Consistent Structural Beats

Beyond visual grammar, there is a **rhythm**. Every week page hits the same beats in the same order; every assignment hits its own set of beats in the same order. Students develop an automatic navigation schema.

### Recipe — Week instruction page, in this order
1. Banner + chip + title + subtitle ([`artifact_wrapper.html`](../templates/byui_course_design/artifact_wrapper.html))
2. Core Questions callout ([`core_questions_callout.html`](../templates/byui_course_design/core_questions_callout.html))
3. Purpose section ([`section_header.html`](../templates/byui_course_design/section_header.html) icon `format_shapes` + [`purpose_metaphor_outcome.html`](../templates/byui_course_design/purpose_metaphor_outcome.html))
4. Preparation section (`section_header.html` icon `build`) — one row of cards:
   - **Readings & Resources** ([`card_red_readings.html`](../templates/byui_course_design/card_red_readings.html))
   - **The Architect's Lens** ([`card_tan_architects_lens.html`](../templates/byui_course_design/card_tan_architects_lens.html))
5. Weekly Schedule section (`section_header.html` icon `event`) — [`weekly_schedule_table.html`](../templates/byui_course_design/weekly_schedule_table.html)

### Recipe — Assignment, in this order
1. Banner + chip + title (`artifact_wrapper.html`)
2. Purpose + Overview two-panel ([`assignment_purpose_overview.html`](../templates/byui_course_design/assignment_purpose_overview.html))
3. Instructions panel with numbered Part blocks ([`assignment_instructions_parts.html`](../templates/byui_course_design/assignment_instructions_parts.html))
4. *(Optional)* Submission Criteria block ([`assignment_submission_criteria.html`](../templates/byui_course_design/assignment_submission_criteria.html))
5. The Architect's Reflection closing card ([`closing_architects_reflection.html`](../templates/byui_course_design/closing_architects_reflection.html))

### Recipe — Syllabus, in this order
1. Banner + `Course Syllabus` chip + course title H1
2. Course Description + Course Outcomes two-panel (description 2/3 width, outcomes panel 1/3 width on `#f5f7f8`)
3. Instructor Information — one card per instructor in a responsive grid
4. Grading Scale + Grading Components two-panel
5. AI Policy section (border-left `#37474f`, `#f8fafb` bg)
6. Course Policies grid (responsive `minmax(300px, 1fr)`)
7. Closing Architect's Reflection card (`closing_architects_reflection.html`)

### Gap signals
| Signal | What it means |
|---|---|
| Section order changes week to week | No schema can form |
| Some weeks have a reflection, some don't | Inconsistent closure |
| Assignments vary between bullet instructions and prose instructions | Extra parsing cost per assignment |
| Weeks 11–13 abandon the structure used in Weeks 01–10 | Capstone is exactly when structure matters most |

---

## Principle 5 — Rubrics as Observable Behaviors, Not Adjectives

Use a **3-level rating scale** on every rubric. Each rating gets a name and a full sentence describing what that level looks like. No adjectives standing alone.

### Recipe
1. **Three rating levels, always**: `Meets Expectations` → `Developing` → `Does Not Yet Meet Expectations`
2. **Each rating has a `description` (the name) and a `long_description` (the full sentence).** Never write "Excellent" with no body.
3. **Meets-level descriptor describes the minimum threshold**, not aspirational. Developing describes partial coverage. Does-not-yet describes what's missing.
4. **Include an Organization and Professional Communication criterion on every rubric** — consistent weight (1 point is typical) — to train students that craft matters regardless of content.
5. **Weight criteria by priority.** The heaviest criterion is the central learning target, not the longest one to grade.
6. **Tag each criterion to a framework or outcome** in the `description` field (e.g., `Scaffolding Through Bloom's Taxonomy`, `Course Map Alignment`).
7. **Show the rubric to students before submission**, not after grading.

Canvas-shape reference: [`templates/byui_course_design/rubric_3level_canonical.json`](../templates/byui_course_design/rubric_3level_canonical.json).

### Canonical example (Week 07 Course Map rubric, criterion 5 of 5)

> **Course Map Alignment** — 3 points
> - **Meets Expectations (3):** Completes a course map that shows how course outcomes connect to module outcomes, assessments, activities, and instructional materials. The relationships among these elements are present and usable for planning the course.
> - **Developing (2):** Completes a course map, but some connections among outcomes, assessments, activities, or materials are missing, partial, or uneven.
> - **Does Not Yet Meet Expectations (0):** Provides an incomplete course map or does not show usable connections among outcomes, assessments, activities, and materials.

Notice: Meets is observable ("relationships are present and usable for planning"), Developing names the specific degradation ("missing, partial, or uneven"), Does-Not-Yet names the absent behavior ("does not show usable connections").

### Gap signals
| Signal | What it means |
|---|---|
| 5+ rating levels | Discrimination collapses — graders default to middle |
| Rating descriptors are single adjectives | Grade depends on grader mood |
| Criteria overlap | Students graded twice for one thing |
| No Organization/Communication criterion on any assignment | Signals craft doesn't matter (it always does) |
| Weights don't match criterion importance | Students optimize for grade, not learning |
| Rubric shown only at grading time | Used for judgment, not learning |

### Canvas API note — fetching rubrics with a student token

`GET /api/v1/courses/:id/rubrics` requires teacher permission. Workaround:

```
GET /api/v1/courses/:id/assignments/:id?include[]=rubric
```

Returns the full criterion + ratings tree for student tokens. Use this when auditing rubrics from a non-teacher token context.

---

## Principle 6 — Alignment Traceability

You can draw a straight line from **any artifact a student touches** back to a **course-level outcome**. The chain is:

`Course Outcome → Module Outcome → Assessment → Rubric Criterion → Activity`

A broken link anywhere in the chain is a latent gap. This principle operationalizes the Outcome → Evidence chain from [`designer_thinking_knowledge.md`](designer_thinking_knowledge.md) at artifact level.

### Recipe
1. **Write course outcomes first, once, in the syllabus.** Phrase each as an observable capability.
2. **Write module outcomes as a Bloom-scaffolded sub-sequence of the course outcomes.** Earlier weeks sit lower on the cognitive taxonomy (Remember, Understand, Apply); later weeks climb (Analyze, Evaluate, Create). For verb-level classification see [`taxonomy_explorer_knowledge.md`](taxonomy_explorer_knowledge.md).
3. **Make each assignment's rubric criteria restate module outcome language.** If the module taught Bloom's scaffolding, the rubric has a criterion called `Scaffolding Through Bloom's Taxonomy`.
4. **Reference outcomes explicitly** in the assignment's Purpose panel when possible.
5. **Verify the capstone rubric maps to the course outcomes listed in the syllabus.** This is the traceability audit.

### Gap signals
| Signal | What it means |
|---|---|
| Syllabus outcomes never reappear in any week page or assignment | Outcomes are ornamental |
| Rubric criteria measure something the week's instruction didn't teach | Assessment/instruction mismatch |
| Module outcomes use identical verbs at the same Bloom level every week | No scaffolding |
| A rubric exists but the assignment body doesn't mention its criteria | Students grade-farm instead of learning |
| A course outcome has no assessment mapped to it | Unverifiable outcome — drop it or build for it |

### Auditable from a course mirror

The alignment chain is mechanically auditable. Proposed extension to `course_quality_check.py` (flag: `--alignment`) tracked as a follow-up issue:

1. Parse outcomes from `syllabus.html` → list of course outcomes
2. For each module (`_module.json` + overview page), extract module-level outcomes
3. For each assignment (`*.json`), fetch rubric via `assignments/:id?include[]=rubric`
4. Tokenize criterion descriptions; check substring coverage of outcome verbs/nouns
5. Flag: (a) course outcomes with no downstream rubric criterion, (b) rubric criteria with no upstream module outcome, (c) module outcomes with no rubric evidence

---

## Cognitive Load Mapping

> See [`cognitive_load_theory_knowledge.md`](cognitive_load_theory_knowledge.md) for load-type definitions and audit indicators. This table maps each Course Design Language principle to its primary load axis.

| Principle | Primary load axis |
|---|---|
| 1. Unified Visual Grammar | Reduces **extraneous load** |
| 2. Sustained Metaphor | Reduces **extraneous load**, supports **germane load** (transfer) |
| 3. Dual-Framing | Reduces **extraneous load** (priority set before content) |
| 4. Consistent Structural Beats | Reduces **extraneous load** (navigation schema becomes automatic) |
| 5. Observable Rubrics | Reduces **extraneous load**, increases **germane load** (criteria as study tool) |
| 6. Alignment Traceability | Aligns **intrinsic load** to outcomes |

None of these principles add content load. They all reduce friction, freeing working memory for the intrinsic difficulty of the material.

---

## Hattie Phase Mapping

> See [`hattie_3phase_knowledge.md`](hattie_3phase_knowledge.md) for phase definitions and audit indicators. This table maps each principle to its strongest phase impact.

| Principle | Strongest phase impact |
|---|---|
| 1. Unified Visual Grammar | **Surface** — navigation predictability |
| 2. Sustained Metaphor | **Transfer** — the handle students carry content with |
| 3. Dual-Framing | **Surface → Deep** — intention before acquisition |
| 4. Consistent Structural Beats | **Surface** — schema for course navigation |
| 5. Observable Rubrics | **Deep → Transfer** — self-assessment against observable targets |
| 6. Alignment Traceability | **All phases** — broken alignment blocks any phase it touches |

---

## Quick Audit Checklist

Score each 0–2 (0 = absent, 1 = inconsistent, 2 = consistent):

| # | Question | Score |
|---|---|---|
| 1 | Does every artifact of the same type look the same? | 0–2 |
| 2 | Is there a metaphor, and does it survive to the capstone? | 0–2 |
| 3 | Does every task open with both *why* and *what you'll have*? | 0–2 |
| 4 | Do section beats repeat in the same order every week? | 0–2 |
| 5 | Do rubric ratings describe observable behavior, not adjectives? | 0–2 |
| 6 | Can I trace every rubric criterion back to a course outcome? | 0–2 |

**Total / 12**, mapping to the `design_coherence` audit tag:

| Total | `design_coherence` | Reading |
|---|---|---|
| **10–12** | `architected` | The course is teaching by example what good design looks like — the highest form of instructional design |
| **6–9** | `partial` | Principles satisfied in some places, not others — usually a few weeks or one artifact-type lagging |
| **0–5** | `assembled` | Built from inconsistent pieces; no through-line. Students burn working memory re-orienting on every page |

---

## Audit Tags Used in Audit Output

Two paired tags. Together they describe *which* principle is affected (`design_principle`) and *how well* it's satisfied (`design_coherence`).

| Tag | Values | Source |
|---|---|---|
| `design_coherence` | `architected` \| `partial` \| `assembled` | This file (Quick Audit Checklist totals) |
| `design_principle` | `visual_grammar` \| `narrative_metaphor` \| `dual_framing` \| `structural_beats` \| `observable_rubrics` \| `alignment_traceability` | This file (the six principles above) |

A well-formed audit issue uses both. Example:

> *Sprint 3 lacks the Purpose/Overview two-panel header used in Sprints 1–2 and 4–6.*
> Tags: `design_coherence: partial`, `design_principle: dual_framing`

The Toyota A3 wrapper from [`toyota_gap_analysis_knowledge.md`](toyota_gap_analysis_knowledge.md) packages the actual change plan around the finding.

---

## Templates

The 11 HTML components and 1 rubric JSON shape live as standalone files in [`agents/templates/byui_course_design/`](../templates/byui_course_design/). The principles above reference each template at its point of use. See the [templates README](../templates/byui_course_design/README.md) for the full list and substitution variables.

---

## Quick Reference for Auditors

When evaluating a BYUI Canvas course's design coherence:

1. **Pull the same artifact type across weeks** (e.g., all week-instruction pages, or all assignments). Inconsistencies between them are Principle 1 (visual grammar) or Principle 4 (structural beats) failures.
2. **Read the syllabus + Week 1 + capstone (Week 12+) end-to-end.** Does the metaphor survive? Are the outcomes still visible? That's Principle 2 + Principle 6.
3. **For every assignment, check that Purpose + Overview both exist and say different things.** Principle 3.
4. **For every rubric, check that each rating has a `long_description` describing observable behavior.** Principle 5. Use `GET /assignments/:id?include[]=rubric` to fetch with a student token.
5. **Trace one course outcome through to one rubric criterion.** Pick the most important course outcome; can you find it referenced in a module overview, in an assignment Purpose panel, and as a criterion `description` in the assignment's rubric? If any link breaks, Principle 6.

A "no" or "partial" on any of the six is a defect to flag with `design_coherence: partial` (or `assembled` if widespread) and the matching `design_principle` value.

# Rubric Quality & Typology — Auditor's Reference

> Reference. A framework for evaluating whether a rubric is well-formed before judging whether learning is well-evidenced by it. If the rubric isn't well-formed, the grades and feedback it produces are meaningless.

**Sources:**
- *Rubric for Evaluating a Rubric* — backbone meta-rubric (`pre_knowledge/rubrics/rubrics of rubrics.pdf`; 4 criteria × 4 levels; author/origin to be backfilled).
- Association of American Colleges & Universities (AAC&U). *VALUE Rubrics* (16 LEAP outcomes; `pre_knowledge/rubrics/aacu_value_rubrics.pdf`).
- Walvoord, B.E., & Anderson, V.J. *Effective Grading: A Tool for Learning and Assessment in College* (Primary Trait Analysis; `pre_knowledge/rubrics/walvoord_departmental_assessment.pdf`).
- Czajka, C.D., Reynders, G., Stanford, C., Cole, R., Lantz, J., & Ruder, S. (2021). *A Novel Rubric Format Providing Effective Feedback for Learner-Centered Teaching.* J. College Sci. Teaching, July/Aug 2021 (NSF #1524399, #1524936, #1524965; `pre_knowledge/rubrics/nsta_novel_rubric_process_skills.md`).
- Gonzalez, J. *Know Your Terms: Holistic, Analytic, and Single-Point Rubrics.* Cult of Pedagogy, 2014.
- Gonzalez, J. *Meet the Single Point Rubric.* Cult of Pedagogy, 2015 (+ 2017 three-column variation).
- Hashem, D. *6 Reasons to Try a Single-Point Rubric.* Edutopia, 2017.
- Sheridan Center for Teaching and Learning, Brown University. *Designing Grading Rubrics.*
- Center for Advancing Teaching and Learning Through Research (CATLR), Northeastern University. *Designing Effective Rubrics.*
- BYU-Idaho Campus Curriculum Development. *Assessment Services* (institutional context: validity & reliability framing).
- *Canvas Rubrics API Survey* — paired API-surface mapping for the canvas-toolbox audit framework (`pre_knowledge/rubrics/canvas_rubrics_api_survey.md`; survey of the Rubrics, RubricAssociations, and RubricAssessments REST resources + critical write-side gotchas).

**Used by:** `canvas_course_expert.md`

**Companions:** [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) (rubric criteria must trace back to a well-formed CLO — if the CLO is malformed, no rubric can save the alignment), [`assessments_knowledge.md`](assessments_knowledge.md) (the rubric scores the assessment — Litmus failures often surface as rubric weaknesses), [`evidence_centered_design_knowledge.md`](evidence_centered_design_knowledge.md) (rubric redesign is part of the `full_assessment_redesign` Decision 5), [`course_design_language_knowledge.md`](course_design_language_knowledge.md) (alignment-traceability lives in Principle 6 — this file checks the rubric end of the chain), [`canvas_rubrics_api_survey.md`](../pre_knowledge/rubrics/canvas_rubrics_api_survey.md) (the API surface that grounds the Canvas-detectable audit signals listed below).

**Scope**: Reference for auditing rubrics in Canvas courses. Covers (a) the 4-criterion meta-rubric for evaluating any rubric's well-formedness, (b) the four rubric typologies — analytic, holistic, single-point, developmental/feedback — and when each is fit-for-purpose, (c) institutional and Canvas-specific audit indicators, and (d) the `rubric_quality` audit-tag enum. Out of scope: how to *write* the rubric from scratch (that's the consuming agent's redesign playbook), and how to pull rubrics from Canvas (that's the upcoming `canvas_rubrics_api_survey` and downstream tooling — this file describes what to check, not how to fetch).

**Provenance**: 10 cited sources above. The backbone is the 4×4 *Rubric for Evaluating a Rubric* PDF in `pre_knowledge/rubrics/`. Tier-2 sources (Cult of Pedagogy, Edutopia, Brown, Northeastern, BYUI Assessment Services) are summary-quality extractions; the NSTA paper is a full extraction; AAC&U VALUE and Walvoord-BU are primary PDFs on disk. See `provenance.sources` in the JSON.

_Last updated: 2026-05-20_

> **Version note:** v0.1, untested. Per the canvas-toolbox `0.x` convention, this knowledge file is not yet promoted to `1.0`; promotion requires a successful audit against a real Canvas course rubric. Not yet wired into `canvas_course_expert.json`'s `cross_references.knowledge_files[]` — that is the next step.

---

## The Core Question

If the outcome isn't well-formed, alignment to it is meaningless ([`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md)). The same applies one layer down: **if the rubric isn't well-formed, the scores and feedback it produces are meaningless.** A well-aligned outcome with a malformed rubric breaks the chain at the assessment end. This file is the rubric end of the alignment audit.

---

## The 4-Criteria Meta-Rubric (backbone)

The backbone PDF defines four criteria for evaluating any rubric, each scored on a 4-level scale (Beginning → Developing → Proficient → Exemplary). Apply each criterion as an audit dimension; flag below Proficient.

### Criterion 1 — Criteria Alignment

| Level | Verbatim language |
|---|---|
| **Beginning (1)** | Learning outcomes are undefined; there are significant gaps in the intent of what is to be measured. |
| **Developing (2)** | Outcomes are measurable and criteria align to those outcomes, but criteria are not stated as skills, knowledge, or dispositions to be measured. |
| **Proficient (3)** | Outcomes are measurable; criteria align with outcomes and are appropriate components of the construct(s) that are the focus of the rubric. |
| **Exemplary (4)** | Outcomes are measurable; criteria align with outcomes and are appropriate components of the construct(s); the scope of the criteria ensures the entire construct is evaluated with no gaps. |

**What this audits:** does each rubric criterion trace back to a stated CLO? Are the criteria expressed as skills/knowledge/dispositions (not as task-completion checkpoints)? Do the criteria together cover the full construct the assessment is measuring?

**Cross-check:** the CLO must itself be well-formed ([`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) — observable verb, single-barreled, appropriate rigor). A rubric criterion aligned to a malformed CLO is a chain break disguised as alignment.

### Criterion 2 — Rating Levels

| Level | Verbatim language |
|---|---|
| **Beginning (1)** | Rating levels are subjective and/or overlap or do not align to the criteria. |
| **Developing (2)** | Rating levels use subjective words or phrases as differentiators between levels; some levels progress on a continuum for some criteria, but other levels are disconnected from each other. |
| **Proficient (3)** | Rating levels are mostly free of subjective words or phrases; differentiating between levels requires minimal inference; progression from level to level has gaps or lacks connection to levels of achievement for each criterion. |
| **Exemplary (4)** | Rating levels are free of subjective words or phrases; differentiating between levels requires minimal inference; progression from level to level is directly connected to distinct levels of achievement for each criterion. |

**What this audits:** do level descriptors use observable, non-subjective language? Is each level discriminable from the adjacent ones (no overlap)? Does the progression describe qualitatively different performance — not just "more" of the same?

**Flag phrases (subjective):** "shows good understanding," "demonstrates strong effort," "mostly correct," "somewhat thorough," "minor errors." Replace with observable behaviors per Northeastern's guidance: "integrates feedback to strengthen argument structure" rather than "shows improvement."

### Criterion 3 — Process-Oriented Assessment

| Level | Verbatim language |
|---|---|
| **Beginning (1)** | Focus is solely on output with no attention to process. |
| **Developing (2)** | Attention to evaluation of the learning process is limited but present; primary focus is on the output product/artifact submitted or skills required to create the output, but these are not directly aligned to assessment outcomes. |
| **Proficient (3)** | Integrates evaluation of the learning process along with the output/artifact submitted. |
| **Exemplary (4)** | Evaluation of both the learning process and output uses the assessment plan and outcomes, not the assessment instructions, as the foundation to define rubric criteria. |

**What this audits:** does the rubric only score the final artifact, or also the thinking process behind it? Output-only rubrics are vulnerable in AI-rich environments (echoes [`evidence_centered_design_knowledge.md`](evidence_centered_design_knowledge.md)'s Decision 4 stress-test) — they reward the polished product without verifying authentic student reasoning.

**Cross-link to ECD:** A rubric that only scores output is the rubric-level signature of the assessment failure ECD's `ai_visibility_stress_test` is built to catch. Rubric redesign is a candidate Decision 5 improvement.

### Criterion 4 — Points and Weights

| Level | Verbatim language |
|---|---|
| **Beginning (1)** | Points for each rubric aspect (row) are equal, even for aspects included for accountability that do not directly align with assessment outcomes; there are ranges of points for each rating level. |
| **Developing (2)** | Points for each rubric aspect (row) are distinct; aspects included for accountability are of lesser value than content criteria; there are ranges of points for each rating level. |
| **Proficient (3)** | Weighting of each rubric aspect and points across rating levels align to the assessment plan and outcomes, not the assessment instructions, as the foundation; there are no ranges of points for each rating level. |
| **Exemplary (4)** | Weighting of each rubric aspect and points across rating levels align to the assessment plan; points can be adjusted for different contexts while maintaining alignment to outcomes; there are no ranges of points for each rating level, with documented rationale. |

**What this audits:** do the point weights match the instructional emphasis the CLOs declare? Are accountability criteria (file-format, on-time, name-on-paper) weighted *less* than content criteria? Are point ranges within a level eliminated in favor of discrete cell values (a "3 of 4" cell with a 6-9 point range hides scoring inconsistency)?

**Anti-pattern:** equal-weight rubrics across criteria of unequal CLO importance. If the CLO emphasis is "argumentation," but the rubric weights "argumentation" equal to "MLA formatting," the rubric contradicts the outcome.

---

## Rubric Typology

Four distinct rubric forms, each fit-for-purpose. The meta-rubric above applies to all four, but how each form expresses well-formedness differs.

### Analytic

**What it is:** Breaks an assignment into discrete criteria; scores each criterion independently across performance levels (typically 3-5 levels). Multi-cell grid: criteria × levels.

**When to use:** Most common form in Canvas. Right when criteria are separable and the assessment has multiple competencies to evaluate (a research paper with thesis, evidence, organization, mechanics).

**Strengths:** Targeted feedback per criterion; surfaces precise strengths and weaknesses; defensible scoring (each criterion has a rationale).

**Weaknesses:** Time-intensive to develop; students may not read the full grid; risk of fragmenting holistic judgment into checklist mechanics.

**Sources:** Gonzalez (2014), Brown Sheridan Center, Walvoord & Anderson (PTA is the analytic form done rigorously).

### Holistic

**What it is:** One descriptor per overall performance level (3-5 levels). Single column; the grader picks the level that best matches the whole work.

**When to use:** Standardized testing, very-high-volume grading where speed dominates; first-pass rough sort before analytic feedback.

**Strengths:** Fast to grade; fast to create; produces a single summative judgment.

**Weaknesses:** No targeted feedback; students see a level but not why; weak for formative use; limited learning value.

**Sources:** Gonzalez (2014), Brown Sheridan Center.

### Single-Point

**What it is:** One column describing target proficiency only — no levels above or below. Optionally extended (Gonzalez's 2017 variation) with two flanking columns: "Concerns" (left, areas needing improvement) and "Advanced" (right, areas where work exceeds expectations). Term coined by Mary Dietz (2000); effectiveness studied by Jarene Fluckiger (2010).

**When to use:** When the cost of describing every failure mode exceeds the cost of personalized written feedback; when creativity matters and the upper bound shouldn't be pre-described; when the audience reads short rubrics but ignores long ones.

**Strengths:** Concise — students actually read it. Open-ended excellence encourages creativity. Quicker to create than analytic. Research (Fluckiger 2010) shows increased student achievement, especially when students help create the rubric and self-assess.

**Weaknesses:** Requires more detailed teacher commentary per submission (the work moves from rubric design to feedback writing). Honest tension with the backbone meta-rubric's Criterion 2 "distinct levels per criterion" — single-point has no levels-per-criterion to evaluate. **Treat single-point as exempted from Criterion 2 if intentionally used; the Concerns/Advanced columns substitute for level descriptors.**

**Sources:** Gonzalez (2015), Hashem (2017, Edutopia), Dietz (2000 — origin), Fluckiger (2010 — research base).

### Developmental / Feedback-Style

**What it is:** A rubric form that pairs each criterion with **process-skill descriptors** of student behavior rather than performance levels. Used in scientific reasoning, oral communication, peer-process skills (Czajka et al. 2021 / ELIPSS project, NSF-funded). Designed for student self-assessment first, instructor feedback second.

**When to use:** When the goal is metacognition and self-regulated learning, not just summative grading. Strong fit for inquiry-based and process-oriented assessments.

**Strengths:** Improves student self-assessment accuracy over time (Czajka et al. found Lin's Concordance Correlation Coefficient r_c = 0.175 pre vs 0.403 post-feedback — students became substantially better at judging their own work after using the rubric form). Aligns naturally with [`evidence_centered_design_knowledge.md`](evidence_centered_design_knowledge.md)'s process-evidence emphasis.

**Weaknesses:** Newer form, less institutional familiarity; tooling (Canvas Rubrics) doesn't model it cleanly — typically implemented as analytic with process-skill criteria.

**Sources:** Czajka et al. (2021), NSF ELIPSS project.

### Comparison

| Form | Levels per criterion | Grading cost | Feedback quality | Best for |
|---|---|---|---|---|
| Analytic | 3-5 | High | High (targeted) | Multi-competency assessments |
| Holistic | 3-5 (total, not per-criterion) | Low | Low | High-volume, standardized |
| Single-Point | 1 (target) + 2 flanking | Medium | High (personalized) | Creativity, short attention |
| Developmental | Process-skill descriptors, not levels | Medium | High (metacognitive) | Self-assessment, process-heavy |

---

## Number-of-Criteria and Number-of-Levels Guidance

**Number of criteria (Brown Sheridan Center):** 4-6 is optimal — captures essential competencies without excessive grading burden. Below 4 risks losing discriminability; above 6 risks fragmentation and unread rubrics.

**Number of levels (Brown Sheridan Center):** Even numbers preferred (4 levels typically) to avoid "middle-ground" ambiguity where graders default to the safe middle. Odd numbers (3 or 5) allow grader hedging at the center; even numbers force a directional judgment.

**Apply to backbone Criterion 2:** A rubric with the right *number* of levels can still fail Criterion 2 if the level descriptors are subjective or overlap. Quantity is necessary but not sufficient.

---

## The Process vs. Product Anti-Pattern (rubric edition)

[`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) names a parallel anti-pattern at the outcomes layer ("To view a videotape on ecological safeguards" — describes an activity, not learner achievement). The rubric edition of the same anti-pattern:

| Anti-pattern | Problem | Fix |
|---|---|---|
| "Completed the assignment on time" | Accountability checkpoint, not a learning judgment | Remove or weight ≤ 5%; backbone Criterion 4 |
| "Used at least 3 sources" | Counts, not evaluation | Replace with judgment: "Sources are appropriate to argument and credibly cited" |
| "Showed effort" / "Demonstrated good understanding" | Subjective; non-observable | Replace with observable behavior: "Connects evidence to claim explicitly in each paragraph" — backbone Criterion 2 |
| "Fewer than 5 grammar errors" | Quantitative threshold uncoupled from rhetorical quality | Replace with: "Sentence structure supports clarity of argument; mechanical errors do not impede meaning" |
| Equal weights across all criteria | Implies equal CLO emphasis where there is none | Weight per CLO emphasis — backbone Criterion 4 |

**Test:** for each criterion in the rubric, ask — *"Could two trained graders score this row identically without consulting each other?"* If the answer is "probably not," the row fails backbone Criterion 2 (rating levels) or Criterion 1 (criteria alignment).

---

## AAC&U VALUE Rubrics — Cross-Institutional Reference

The Association of American Colleges & Universities (AAC&U) publishes 16 VALUE (Valid Assessment of Learning in Undergraduate Education) rubrics covering LEAP outcomes — written communication, critical thinking, quantitative literacy, civic engagement, intercultural knowledge, ethical reasoning, integrative learning, and others. Each VALUE rubric is analytic, with 4 performance levels (Capstone, Milestones-3, Milestones-2, Benchmark).

**When to cite VALUE during audit:**
- The course CLO maps to a LEAP outcome and the existing rubric is weak — VALUE is a credible, peer-reviewed starting template.
- The auditor needs a benchmark for what a well-formed analytic rubric looks like in a specific domain (writing, critical thinking, etc.).
- Cross-institutional defensibility matters (accreditation, transfer credit alignment).

**Limitation:** VALUE rubrics are general — they intentionally don't specify discipline content. They evaluate the *skill* (critical thinking) across domains. For discipline-specific competencies, VALUE is a scaffold, not a finished rubric.

**Source:** `pre_knowledge/rubrics/aacu_value_rubrics.pdf`.

---

## Walvoord & Anderson — Primary Trait Analysis

Walvoord and Anderson's *Primary Trait Analysis* (PTA) is the analytic-rubric methodology done rigorously: identify the **primary traits** (criteria) that define quality for the specific assignment, then describe distinct performance levels per trait. PTA is what an "Exemplary"-tier analytic rubric is when the criteria are derived from the CLOs rather than copied from a template.

**Key contributions PTA makes to rubric audit:**
- Criteria are *derived from the assignment's learning goals*, not lifted from a generic template — pre-empts Criterion 1 alignment failures.
- Level descriptors are *behavioral* (what the work *shows*), not subjective (what the work *seems like*) — pre-empts Criterion 2 failures.
- Departmental assessment use case: PTA rubrics roll up across course sections to support program-level assurance of learning (the BU PDF on disk emphasizes this departmental dimension).

**When to cite PTA:** when the rubric exists but feels generic; when criteria don't quite trace back to a CLO; when the department needs program-level assessment evidence.

**Source:** `pre_knowledge/rubrics/walvoord_departmental_assessment.pdf`.

---

## BYUI Institutional Context

BYU-Idaho Assessment Services frames evaluation tools (rubrics included) around two foundational criteria:

- **Validity:** the rubric measures what it is intended to measure. (Maps to backbone Criterion 1 — Criteria Alignment.)
- **Reliability:** the rubric produces consistent results over time. (Maps to backbone Criterion 2 — Rating Levels.)

Rubric Review is one of six Assessment Services offerings (alongside Course Learning Outcome Analysis, Assessment Alignment, Course Audit, Syllabus Review, and Personalized Consultancy). The institutional language anchors the canvas-toolbox audit vocabulary: an audit emitting `rubric_quality: needs_revision` with a `validity` flag means Criterion 1 failed; with a `reliability` flag means Criterion 2 failed.

**Source:** [byui_assessment_services.md](../pre_knowledge/rubrics/byui_assessment_services.md).

---

## Common Pitfalls (synthesized across sources)

1. **Overlapping or hidden criteria** — two rubric rows that score the same trait (e.g., "Organization" and "Coherence" both about logical flow). Northeastern flags this. (Backbone Criterion 1.)
2. **Vague descriptors lacking specificity** — "shows good understanding" across all levels with only adverb changes. Northeastern + backbone Criterion 2.
3. **Misaligned point distribution** — weights that don't match CLO emphasis. Northeastern + backbone Criterion 4.
4. **Static rubrics without revision** — the same rubric for 5 semesters without testing against student work. Northeastern explicit: "Test rubrics with hypothetical scoring scenarios. Seek colleague review before implementation" (Brown).
5. **Single-point rubric misapplied to large, anonymous-graded assessments** — single-point's strength is personalized commentary; deployed where commentary won't be written, it fails. (Gonzalez tension.)
6. **Holistic rubric used for formative feedback** — holistic gives a single score; formative needs criterion-level diagnosis. Wrong-typology selection. (Gonzalez 2014.)
7. **Analytic rubric with subjective level descriptors** — the form is analytic but the cell text is holistic-style ("good," "fair," "poor"). Backbone Criterion 2 catches this.
8. **Process-only or output-only when the CLO requires both** — backbone Criterion 3. Echoed by `evidence_centered_design_knowledge.md` Decision 4.
9. **No documented rationale for weights** — weights look intentional but no defense exists for why one criterion is 30% and another 10%. Backbone Criterion 4 Exemplary requires documented rationale.
10. **Rubric criteria that don't trace to any CLO** — orphan rubric criteria. Mirror of [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md)'s "rubric criteria don't trace back to a named CLO" — same defect, audited from the rubric end.

---

## Canvas Audit Indicators

Flag when reviewing a Canvas course rubric:

- **No rubric attached** to a graded assignment (the most basic flag — assignment-without-rubric is the gap-analysis target).
- **Rubric attached but `use_for_grading: false`** — rubric exists but is decorative; grade comes from elsewhere; students see a rubric the instructor doesn't use.
- **Rubric criteria don't trace to any CLO listed in the syllabus or course outcomes** — Criterion 1 alignment failure (orphan rubric).
- **Cell text is subjective ("good," "fair," "shows understanding")** without behavioral descriptors — Criterion 2 failure.
- **Equal points across criteria for an assessment whose CLOs imply unequal emphasis** — Criterion 4 failure.
- **Point ranges within a single cell** (e.g., "Proficient: 6-9 points") — Criterion 4 failure; reduces inter-grader reliability.
- **Only output-oriented criteria** ("submitted on time," "5 pages") for an assessment whose CLO targets reasoning or process — Criterion 3 failure.
- **More than 6 or fewer than 3 criteria** without a stated reason — Brown's range guidance violated; flag for review.
- **Rubric used across multiple assignments with no per-assignment tailoring** — generic-template signal; pre-empts Walvoord PTA's discipline-grounded approach.
- **Single-point rubric on a 200-student auto-graded assessment** — typology mismatch (single-point needs personalized commentary the workflow won't deliver).

### Canvas API Signals

API-detectable signals from the Canvas Rubrics REST surface (full mapping in [`canvas_rubrics_api_survey.md`](../pre_knowledge/rubrics/canvas_rubrics_api_survey.md)). These are the *programmatic* flavor of the observational indicators above — same defects, fetched and tagged from API fields rather than read off the screen.

- **RubricAssociation `use_for_grading: false`** → `validity_flag: true`. The rubric exists and displays but contributes nothing to the grade. Detectable via `GET /api/v1/courses/:id/rubric_associations/:id` (or inline on assignment fetches). The API-grounded form of the "decorative rubric" observational indicator above.
- **Criterion `criterion_use_range: true`** → `rubric_criteria_flags: ["points_and_weights"]`. Canvas's API flag for the backbone Criterion 4 "point ranges per cell" anti-pattern. Each level cell holds a min-max range instead of a discrete value; reduces inter-grader reliability. Returned on rubric GETs; check every criterion.
- **`used_locations.count > 1`** → write-safety warning, not an audit failure. When a rubric is associated to multiple courses (master + sections), any PUT against it CLONES the rubric instead of updating in place (canvas-lms gotcha #1; see API survey). Surface this as a *blocker* for any future rubric-redesign tool, not as a rubric-quality flag.
- **RubricAssociation `purpose: "bookmark"`** (not `"grading"`) → bookmarked-only rubric, not active on any submission flow. Detectable via the same association endpoint. Pair with `use_for_grading` to disambiguate "intentionally archived" vs. "decorative."
- **Rubric returned via `GET /assignments?include[]=rubric`** carries criteria but NOT the association metadata (`use_for_grading`, `purpose`). Use the assignment-include path for student-token-safe criterion reads; use `GET /rubric_associations` (teacher-token required) when association metadata matters. Documented in AGENTS.md External System Lessons.
- **Rubric with one criterion AND `free_form_criterion_comments: true`** → candidate single-point typology signal (heuristic; not confirmed without inspecting cell content). Use to bias `rubric_typology` classification, not to assert it.

---

## Quick Reference for Auditors

For each rubric encountered during a Canvas audit:

1. **Identify typology** — analytic, holistic, single-point, or developmental? If the form doesn't match the assessment's purpose (formative vs. summative, high-volume vs. personalized), that's the first flag.
2. **Trace each criterion to a CLO** — if any criterion is orphan, Criterion 1 fails.
3. **Read level descriptors for subjective language** — "good," "fair," "shows," "demonstrates strong" → Criterion 2 fails.
4. **Test level discriminability** — could two trained graders score the same work identically using only the cell text? If not, Criterion 2 fails.
5. **Check process vs. output coverage** — does the rubric only score the final artifact, or also the thinking process? If CLO requires both and rubric scores only output, Criterion 3 fails.
6. **Inspect weights** — do they match CLO emphasis? Are accountability criteria weighted less than content? Are point ranges per cell eliminated? If not, Criterion 4 fails.
7. **Count criteria** — 3-8 is the acceptable range (4-6 ideal per Brown). Outside flags.
8. **Count levels** — 3-5 typical; even-numbered preferred per Brown. Single-point and developmental exempted from this count.
9. **Cross-link to assessment Litmus** — if the assessment fails [`assessments_knowledge.md`](assessments_knowledge.md)'s Litmus Test, the rubric is often the visible expression of that failure.

---

## Audit Tags

**Primary tag:** `rubric_quality` ∈ {`meets_criteria`, `partial`, `needs_revision`, `absent`}

- `absent` — no rubric attached to a graded assignment.
- `needs_revision` — rubric attached but at least one backbone criterion at Beginning (1) level.
- `partial` — rubric attached, all backbone criteria at Developing (2) or above, but at least one below Proficient (3).
- `meets_criteria` — all four backbone criteria at Proficient (3) or above.

**Companion tags:**
- `rubric_typology` ∈ {`analytic`, `holistic`, `single_point`, `developmental`, `unknown`}
- `rubric_criteria_flags` — list of backbone criteria failing: `criteria_alignment`, `rating_levels`, `process_oriented`, `points_and_weights`
- `rubric_use_for_grading` ∈ {`true`, `false`, `n/a`} — Canvas's `use_for_grading` field; `false` is a soft flag.
- `validity_flag` — boolean; true when Criterion 1 fails (BYUI vocabulary).
- `reliability_flag` — boolean; true when Criterion 2 fails (BYUI vocabulary).

**Single-point exemption rule:** when `rubric_typology = single_point`, suppress the `rating_levels` flag (Criterion 2) — single-point intentionally has no levels-per-criterion. Evaluate the Concerns/Advanced columns under Criterion 2 instead.

**Developmental exemption rule:** when `rubric_typology = developmental`, evaluate Criterion 3 (Process-Oriented Assessment) at Proficient or above by default — the form is process-oriented by design.

---

## Pairs With

- [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) — the outcome end of the alignment chain. A well-formed rubric aligned to a malformed CLO still fails.
- [`assessments_knowledge.md`](assessments_knowledge.md) — the assessment-quality Litmus Test. Rubric weaknesses are often Litmus failures expressed at the rubric layer.
- [`evidence_centered_design_knowledge.md`](evidence_centered_design_knowledge.md) — rubric redesign is part of the `full_assessment_redesign` Decision 5; the AI-visibility stress test (Decision 4) often surfaces Criterion 3 failures.
- [`course_design_language_knowledge.md`](course_design_language_knowledge.md) — Principle 6 (alignment traceability) declares the chain CLO → Module Outcome → Rubric Criterion. This file is the rubric-criterion node of that chain.
- [`taxonomy_explorer_knowledge.md`](taxonomy_explorer_knowledge.md) — the verb tool informs whether rubric criterion verbs are observable.

---

## References

Full citation list — see `provenance.sources` in the JSON companion. Source files on disk in [`lib/agents/pre_knowledge/rubrics/`](../pre_knowledge/rubrics/).

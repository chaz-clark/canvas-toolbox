# Knowledge References

Distilled instructional-design knowledge sources used by the Canvas audit agents (`agents/canvas_course_expert.md` and the audit rules in `canvas_course_expert.json`). Each file is a self-contained reference: theory, audit indicators, and the tag the agent emits when the framework applies.

These files travel with the upstream `agents/` folder, so any course repo that pulls from canvas_toolbox gets them automatically.

---

## How to choose between them

The twelve files cover overlapping but distinct ground. Quick routing:

| If you're auditing… | Start with |
|---|---|
| Module navigation, item count, working-memory load | [`cognitive_load_theory_knowledge.md`](cognitive_load_theory_knowledge.md) |
| Whether learning progresses Surface → Deep → Transfer | [`hattie_3phase_knowledge.md`](hattie_3phase_knowledge.md) |
| Whether the course covers more than just thinking (cognitive vs. affective vs. psychomotor) | [`three_domains_knowledge.md`](three_domains_knowledge.md) *(academic framing)* or [`taxonomy_explorer_knowledge.md`](taxonomy_explorer_knowledge.md) *(BYUI tool framing)* |
| Whether the module sequence is brain-aligned (experience before explanation) | [`experiential_learning_knowledge.md`](experiential_learning_knowledge.md) |
| Whether the course was designed backward from outcomes (vs. assembled forward from content) | [`backwards_design_knowledge.md`](backwards_design_knowledge.md) *(Wiggins/McTighe UbD — academic framing)* or [`designer_thinking_knowledge.md`](designer_thinking_knowledge.md) *(BYUI five-stage descendant)* |
| Whether each module exercises task-centered / activation / demonstration / application / integration (Merrill) | [`merrill_first_principles_knowledge.md`](merrill_first_principles_knowledge.md) |
| Whether the course's learning outcomes are well-formed (precedes alignment) | [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) |
| Whether a rubric is well-formed (4-criterion backbone, typology, alignment-to-CLOs) | [`rubrics_knowledge.md`](rubrics_knowledge.md) |
| Whether a specific assessment is the right type (formative vs. summative) and AI-resistant | [`assessments_knowledge.md`](assessments_knowledge.md) |
| How to *redesign* a weak assessment into stronger evidence of learning (procedural, AI-era) | [`evidence_centered_design_knowledge.md`](evidence_centered_design_knowledge.md) |
| Whether assessments accept AI-generated work as a substitute for learning | [`inverted_blooms_knowledge.md`](inverted_blooms_knowledge.md) |
| Whether an assignment prompts critical thinking — and how to *score* student work on a critical-thinking criterion | [`critical_thinking_knowledge.md`](critical_thinking_knowledge.md) |
| Whether a course meets the BYUI / NWCCU course-design master checklist (audit-coverage map) | [`course_design_standards_knowledge.md`](course_design_standards_knowledge.md) |
| Whether a BYUI course is a coherent artifact (visual grammar, rubrics, alignment) | [`course_design_language_knowledge.md`](course_design_language_knowledge.md) |
| Writing a precise change plan for a flagged issue | [`toyota_gap_analysis_knowledge.md`](toyota_gap_analysis_knowledge.md) |
| Setting up + running a FERPA-safe AI-assisted grading pipeline (core lessons) | [`grader_knowledge.md`](grader_knowledge.md) |
| Per-instructor comment voice for the grading pipeline | [`grader_voice_knowledge.md`](grader_voice_knowledge.md) |
| Coaching a new faculty on feedback style — research-grounded WHAT/HOW split + first-time voice articulation | [`voice_coaching_knowledge.md`](voice_coaching_knowledge.md) |
| Onboarding a new instructor / assignment to the grader (6-step interview) | [`grader_setup_knowledge.md`](grader_setup_knowledge.md) |
| Title IV course-engagement audit — classifying students into UW/UF/Never-Participated/Active by last engagement date for R2T4 reporting (NEW FERPA tier 3 — Downloads-folder named report) | [`course_engagement_audit_knowledge.md`](course_engagement_audit_knowledge.md) |

---

## The files

### [`hattie_3phase_knowledge.md`](hattie_3phase_knowledge.md)

**Source:** Hattie, J. (2009). *Visible Learning*.
**Core idea:** Every learner moves through three phases — Surface → Deep → Transfer. A gap at any phase blocks the next.
**When to use:** Diagnosing *what kind of learning* a module is supporting. Course content can be present and still fail because Surface gaps (no overview, broken nav) starve Deep and Transfer of any foundation.
**Audit tag:** `hattie_phase` ∈ {surface, deep, transfer, all}.

---

### [`cognitive_load_theory_knowledge.md`](cognitive_load_theory_knowledge.md)

**Source:** Sweller (1988); Atkinson & Shiffrin memory model; Medical College of Wisconsin CLT guide (2022).
**Core idea:** Working memory holds 5–9 chunks. Three load types compete for that space — **manage** intrinsic, **minimize** extraneous, **maximize** germane.
**When to use:** Almost always. CLT is the mechanics layer underneath Hattie's phases — every audit issue gets a CLT load type.
**Audit tag:** `cognitive_load_type` ∈ {extraneous, intrinsic, germane}.
**Pairs with:** `hattie_3phase_knowledge.md` (which phase is which load blocking?).

---

### [`three_domains_knowledge.md`](three_domains_knowledge.md)

**Source:** Wilson, L.O. *The Second Principle*. Bloom (1956), Krathwohl (1964), Anderson & Krathwohl (2001), Harrow (1972).
**Core idea:** Courses can be cognitive, affective, or psychomotor — and most "non-emotional" courses still imply affective objectives they never name. Wilson uses **Harrow's 6-level psychomotor**.
**When to use:** When auditing learning outcomes against the academic-research framing, or when the affective domain (collaboration, judgment, professional behavior) is in scope.
**Audit tag:** `learning_domain` ∈ {cognitive, affective, psychomotor, multi}.
**Pairs with:** `taxonomy_explorer_knowledge.md` (BYUI's tool view of the same three domains).

---

### [`taxonomy_explorer_knowledge.md`](taxonomy_explorer_knowledge.md)

**Source:** BYU-Idaho. *The Taxonomy Explorer.* `content.byui.edu/file/c5d91be3-…/Taxonomy_Explorer.html`
**Core idea:** BYUI's institutional verb-classification tool. Same three domains as Wilson, but uses **Simpson's 7-level psychomotor** (Perception → Origination) instead of Harrow.
**When to use:** When the course's outcomes were written using BYUI's verb-lookup tool, or when faculty prefer the BYUI institutional view.
**Audit tag:** `taxonomy_source` ∈ {byui_explorer, wilson, agnostic}.
**Pairs with:** `three_domains_knowledge.md` (theory, holistic-design rationale, physical ≠ psychomotor boundary — all deferred to that file).

---

### [`experiential_learning_knowledge.md`](experiential_learning_knowledge.md)

**Source:** Aswad, M. *How does the brain learn? And why don't we teach that way?* Times Higher Education, Campus.
**Core idea:** The brain learns experience-first. Reverse the dominant LMS pattern — instead of *theory → example → practice*, sequence as **Experience → Observation → Discussion → Explanation → Theory**.
**When to use:** When a module is structurally complete but feels like transmission. Experiential adds the sequencing diagnostic that Hattie and CLT alone miss.
**Audit tag:** `sequencing` ∈ {experience_first, explanation_first, not_applicable}.
**Pairs with:** `hattie_3phase_knowledge.md` (sequences across phases), `designer_thinking_knowledge.md` (educator-as-designer rationale).

---

### [`backwards_design_knowledge.md`](backwards_design_knowledge.md)

**Source:** McTighe, J., & Wiggins, G. (2012). *Understanding by Design® Framework.* ASCD. Plus the Wiggins UbD video transcript (ASCD, 10 min).
**Core idea:** UbD is a planning framework — three stages: (1) Identify desired results, (2) Determine acceptable evidence, (3) Plan learning experiences. Design backward from understanding and transfer goals; *the textbook is a resource, not the syllabus*.
**When to use:** When auditing whether a course was *designed backward* from intended results or *assembled forward* from content. The academic / research-lineage framing of the same principle BYUI's "designer thinking" implements institutionally.
**Audit tag:** none yet (reference-shape; consumed via fact lookup).
**Pairs with:** `designer_thinking_knowledge.md` (BYUI five-stage descendant), `assessments_knowledge.md` (Stage 2 evidence), `outcomes_quality_knowledge.md` (Stage 1 quality gate).

---

### [`merrill_first_principles_knowledge.md`](merrill_first_principles_knowledge.md)

**Sources:** Merrill, M.D. (2002). *First Principles of Instruction* (ETR&D). Merrill, M.D. (2013). *First Principles of Instruction: Identifying and Designing Effective, Efficient, and Engaging Instruction*. Frick, Chadha, Watson, Wang & Green (2010) replication. Margaryan, Bianco & Littlejohn (2015) MOOC audit. Mayer (2017) Multimedia Learning Principles overlap.
**Core idea:** Five cross-theory principles that predict effective instruction: (1) **Task-centered** — learning is anchored in real-world problems, not abstract topics; (2) **Activation** — prior experience is recalled before new content; (3) **Demonstration** — concepts are shown (worked examples), not just told; (4) **Application** — learners do the task with coaching and feedback; (5) **Integration** — learners transfer to their own context, reflect, and share. Sequenced as the *pebble-in-the-pond* progression (whole task → unpacked components → reassembled).
**When to use:** When auditing whether a module/course follows research-validated design principles that cut across Hattie / Kolb / UbD. Generalizes across institutions — institution-agnostic by design. Available as the `merrill` preset in `learning_model_audit.py` alongside `byui`, `kolb`, and `bloom-3`.
**Audit tag:** `learning_model_integration` ∈ {`complete`, `partial`, `unverified`} (shared with `learning_model_audit` — Merrill is a preset, not a separate tag namespace).
**Status:** ⚠️ **v0.1** — knowledge file + audit preset built same-day (2026-06-10); calibration against real courses pending.
**Consumed by:** `learning_model_audit.py` (as `--preset merrill`), `canvas_course_expert`. **Pairs with:** [`hattie_3phase_knowledge.md`](hattie_3phase_knowledge.md) (Surface/Deep/Transfer maps to Demonstration/Application/Integration), [`experiential_learning_knowledge.md`](experiential_learning_knowledge.md) (Kolb cycle overlaps Activation/Application), [`backwards_design_knowledge.md`](backwards_design_knowledge.md) (UbD Stage 3 = task-centered framing), [`assessments_knowledge.md`](assessments_knowledge.md) (Application/Integration are formative→summative bridge).

---

### [`designer_thinking_knowledge.md`](designer_thinking_knowledge.md)

**Source:** Backward Design framework (Wiggins & McTighe lineage), distilled from BYUI *Teacher and Designer Thinking* materials.
**Core idea:** Design backward from outcomes. Five stages — Outcome → Evidence → Experience → Content → Reality Check. *Content is a tool, not the destination.*
**When to use:** When a course has lots of content but unclear outcomes, or when assessments don't trace back to claimed outcomes. BYUI's institutional descendant of `backwards_design_knowledge.md`.
**Audit tag:** `design_mode` ∈ {teacher, designer}.
**Pairs with:** `backwards_design_knowledge.md` (UbD parent), `experiential_learning_knowledge.md` (supplies the neural rationale for content-as-tool).

---

### [`course_design_language_knowledge.md`](course_design_language_knowledge.md)

**Source:** BYU-Idaho *Architects of Learning* faculty-development course (course `405800`).
**Core idea:** Six prescriptive principles for course coherence at the artifact level: visual grammar, sustained narrative metaphor, dual-framing, consistent structural beats, observable rubrics (3-level scale with `long_description` on every rating), and alignment traceability (Course Outcome → Module Outcome → Assessment → Rubric Criterion → Activity).
**When to use:** When auditing a BYUI course and the underlying theory (Hattie / CLT / domain coverage) all check out but the course still feels incoherent — that's the design language layer. **BYUI institutional view**; other universities can fork the principles structure and swap the palette/templates.
**Audit tag:** Two paired tags — `design_coherence` ∈ {architected, partial, assembled} (how well a principle is satisfied) + `design_principle` ∈ {visual_grammar, narrative_metaphor, dual_framing, structural_beats, observable_rubrics, alignment_traceability} (which principle).
**Pairs with:** [`agents/templates/byui_course_design/`](../templates/byui_course_design/) (the 11 HTML components and 1 rubric JSON shape that implement the recipe).

---

### [`toyota_gap_analysis_knowledge.md`](toyota_gap_analysis_knowledge.md)

**Source:** Toyota Production System / A3 Problem Solving methodology.
**Core idea:** For every flagged issue, force specificity: Current State → Target State → Gap → Root Cause → Countermeasure → Verification. Surfaces systemic causes that propagate across modules.
**When to use:** Always — this is the **change-plan format** every audit finding ends in. Without it, the audit is a list of complaints; with it, it's a plan.
**Audit tag:** none (it's the output format, not a classifier).

---

### [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md)

**Sources:** Morrison, Ross, Morrison & Kalman (2019). *Designing Effective Instruction*, 8th ed. Ch. 5; BYU-Idaho Learning and Teaching. *Learning Outcomes*; BYU-Idaho Assurance of Learning CLO Rubric.
**Core idea:** Alignment checks that outcomes are *wired together*; this framework checks that the outcomes themselves are *worth wiring*. Provides the full BYUI outcome hierarchy (ILO → PLO → CLO → LLO), BYUI's 5 kinds of outcomes (Knowledge, Character & Values, Skills, Experiences, Learning-to-Learn), the AoL 6-criteria CLO quality rubric, Bloom's observable verb lists, the behavioral vs. cognitive objective formats, and the process-vs-outcome anti-pattern.
**When to use:** When auditing whether a course's CLOs are well-formed before checking alignment. Precedes `designer_thinking_knowledge.md` in the audit order — you can't meaningfully check backward design if the outcomes themselves are broken.
**Audit tag:** `clo_quality` ∈ {`meets_criteria`, `partial`, `needs_revision`} + `clo_criteria_flags` listing which of the 6 AoL criteria fail.
**Pairs with:** `designer_thinking_knowledge.md` (backward design from outcomes), `taxonomy_explorer_knowledge.md` (BYUI verb tool), `three_domains_knowledge.md` (domain coverage and rigor spread).

---

### [`rubrics_knowledge.md`](rubrics_knowledge.md)

**Sources:** *Rubric for Evaluating a Rubric* backbone meta-rubric; AAC&U VALUE rubrics; Walvoord & Anderson (Primary Trait Analysis); Czajka et al. (2021, developmental/feedback rubrics); Cult of Pedagogy (rubric typology, single-point); Brown Sheridan Center; Northeastern CATLR; BYU-Idaho Assessment Services. Paired with `canvas_rubrics_api_survey.md`.
**Core idea:** Where `outcomes_quality` checks the *outcome*, this checks the *rubric* that scores against it. A 4-criterion backbone meta-rubric — **Criteria Alignment** (= validity), **Rating Levels** (= reliability), **Process-Oriented Assessment**, **Points & Weights** — plus four typologies (analytic / holistic / single-point / developmental) with their exemption rules. Criterion 1 (alignment = validity) is paramount but a *human* judgment, so the auditor surfaces alignment data + recommendations rather than auto-asserting it; the verdict is driven by the machine-checkable criteria (C2/C3/C4).
**When to use:** Auditing whether a rubric is well-formed (Stage 5 of the rubric workstream), after `rubric_coverage_audit.py` finds which assignments have rubrics. The rubric end of the CLO → Module Outcome → Rubric Criterion alignment chain.
**Audit tag:** `rubric_quality` ∈ {`meets_criteria`, `meets_criteria_unverified`, `partial`, `needs_revision`, `absent`} + `rubric_criteria_flags` (C2/C3/C4) + `validity_review` + `alignment` data + `rubric_typology`.
**Consumed by:** `rubric_quality_audit.py` (the scoring engine), `canvas_course_expert.md`. **Pairs with:** `outcomes_quality_knowledge.md` (the outcome end of the chain), `canvas_api_knowledge.md` / `canvas_api_lessons_learned.md` (the API surface the audit runs on).

---

### [`assessments_knowledge.md`](assessments_knowledge.md)

**Source:** Yale Poorvu Center *Formative & Summative Assessments*; Hardman (2024) *Redesigning Instruction & Assessment in the Age of AI*; Wiggins UbD video transcript (ASCD); BYUI *Architects of Learning* assessment week (2026).
**Core idea:** Formative vs. summative as the two main assessment types — formative is *for* learning (low-stakes, iterative, gap-closing); summative is *of* learning (evaluative, comparative). Plus AI-era design adjustments: productive friction, in-process evidence, oral defenses, staged drafts.
**When to use:** When classifying a single assessment or evaluating whether its design is right for what it's evidencing. Pairs with `backwards_design` to answer "is this the right assessment for Stage 2?"
**Audit tag:** none yet (reference-shape; consumed via fact lookup).
**Pairs with:** `backwards_design_knowledge.md` (upstream UbD logic), `outcomes_quality_knowledge.md` (the outcome the assessment claims to evidence), `inverted_blooms_knowledge.md` (AI-agency framing), `course_design_language_knowledge.md` (observable rubrics).

---

### [`evidence_centered_design_knowledge.md`](evidence_centered_design_knowledge.md)

**Source:** BYUI *Architects of Learning* workshop deck *Designing Stronger Assessments — Engineering Stronger Evidence of Learning* (13 slides, 2026-05-18).
**Core idea:** Procedural — trigger-keyed playbooks for *strengthening* a weak assessment. Five decisions: (1) clarify the core learning, (2) identify convincing evidence, (3) make learning visible, (4) stress-test visibility in an AI-rich environment, (5) add one architectural improvement. The thesis: *AI mostly threatens assessments that mistake product for cognition.* Moves an assessment from Weak (task completion / polished product / output) to Strong (thinking demonstration / decision-making / process + judgment).
**When to use:** When the assessment audit flags a weakness and you need to *act on it*. Composes with `assessments_knowledge` (diagnostic — what type), `backwards_design` (Decisions 1–2 mirror UbD Stages 1–2), `inverted_blooms` (AI-agency framing feeds Decision 4), and `toyota_gap_analysis` (A3 format for the redesign write-up).
**Audit tag:** none (procedural — produces redesign artifacts, not classification).
**Status:** ⚠️ **v0.1** — extracted from source deck; field calibration pending.
**Consumed by:** `canvas_course_expert.json`, `ira_program_alignment.md`. **Pairs with:** [`assessments_knowledge.md`](assessments_knowledge.md), [`backwards_design_knowledge.md`](backwards_design_knowledge.md), [`inverted_blooms_knowledge.md`](inverted_blooms_knowledge.md), [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md), [`toyota_gap_analysis_knowledge.md`](toyota_gap_analysis_knowledge.md).

---

### [`inverted_blooms_knowledge.md`](inverted_blooms_knowledge.md)

**Source:** Kassorla, M. *Inverted Bloom's for the Age of AI.* Substack.
**Core idea:** Traditional Bloom's assumes students build foundational knowledge before creating. AI inverts this — students can now *Create* first using AI tools, then need to be scaffolded *down* to genuine understanding and retention. Assessment design must deliberately reintroduce productive friction: staged drafts, oral defenses, process documentation, or revision cycles that require evidence of the student's own thinking. A polished submission is no longer evidence of learning.
**When to use:** When auditing whether assessments are designed to produce student-owned learning or inadvertently accept AI-generated work. Applies to every assignment and rubric in the course. Most urgent for text-based, artifact-submission assignments.
**Audit tag:** `ai_agency` ∈ {`ai_dependent`, `scaffolded`, `student_owned`}
**Pairs with:** `outcomes_quality_knowledge.md` (CLOs need ownership-clause framing), `designer_thinking_knowledge.md` (productive friction as part of backward design), `cognitive_load_theory_knowledge.md` (germane load is what AI bypasses).

---

### [`syllabus_knowledge.md`](syllabus_knowledge.md)

**Sources:** BYU-Idaho Campus Curriculum Development syllabus template (9 required sections); BYU-Idaho AI hub *AI in the Syllabus* (`byui.edu/ai` — a generative-AI policy is required); general higher-ed syllabus practice.
**Core idea:** Whether a syllabus is *complete* — contains the sections students need (instructor contact, overview/outcomes, requirements, structure, expectations, grading, disability/accessibility, university policies, disclaimers) plus a now-required generative-AI policy. A completeness check, not a prose-quality judgment; the announcement layer of the CLO → assessment → rubric chain. Institution-neutral checklist with the BYUI template as the anchor profile (Learning Model / Vision flagged BYUI-specific).
**When to use:** Pre-semester syllabus completeness check, before or alongside the rubric/CLO audits.
**Audit tag:** `verdict` ∈ {`complete`, `incomplete`, `no_syllabus`} + per-section `detected` flags + `ai_policy` gate (+ detected framework) + advisory signals (bloat / outcomes-stated / learning-model).
**Status:** ✅ **v1.0** — validated read-only against real courses (ITM327 + the shared outcomes parser across m119/ds250/ds460), 2026-05-26.
**Consumed by:** `syllabus_audit.py` (the detection engine; reads `syllabus_body`), `canvas_course_expert`. **Pairs with:** `outcomes_quality_knowledge.md` (the outcomes named in the syllabus), `rubrics_knowledge.md` (the assessment/rubric end), `canvas_api_knowledge.md` / `canvas_api_lessons_learned.md` (the API surface).

---

### [`workload_calibration_knowledge.md`](workload_calibration_knowledge.md)

**Sources:** Carnegie credit-hour norm (~3 hrs total work per credit/week); ~250 wpm academic reading rate; Wake Forest Course Workload Estimator (Barre & Esarey).
**Core idea:** The *aggregate* workload budget — how much gradable work a course asks and (most reliably) how it's *distributed* across the term. Clustering/crunch weeks are a defect even when the total is fine. Honest scope: distribution/density is computable from due dates; reading *hours* aren't (readings are links/files), so volume is a rough sanity note only. Complements `cognitive_load` (per-task) with the aggregate view.
**When to use:** Pre-semester, to catch crunch weeks and over/under-assignment.
**Audit tag:** `workload` ∈ {`balanced`, `uneven`, `sparse`, `unscheduled`} + flags (uneven_distribution / front_loaded / back_loaded / mostly_unscheduled / low_volume / high_volume).
**Status:** ⚠️ **v0.1** — real-course-validated (ITM327 uneven; sandbox/ds250 balanced) but the thresholds are fresh; calibration may refine.
**Consumed by:** `workload_audit.py`, `canvas_course_expert`. **Pairs with:** `cognitive_load_theory_knowledge.md` (per-task load), `syllabus_knowledge.md` (the schedule).

---

### [`course_design_standards_knowledge.md`](course_design_standards_knowledge.md)

**Source:** BYU-Idaho Campus Online *Course Design Standards* (2026 edition — both the .xlsx instrument and the canonical HTML at `content.byui.edu/file/25dac126-…/course-design-standards.html`); cross-walked to **NWCCU 2020 Standards for Accreditation** (specifically Std. 2.C learning outcomes, 2.E faculty/courses, 4 instructional design / accessibility).
**Core idea:** The institutional master checklist (~40 standards across 7 categories — Outcomes / Alignment / Pedagogy / Assessment / Materials / Accessibility / Workload) mapped onto NWCCU accreditation codes, with an **audit-coverage map** for canvas-toolbox: which standards are already deterministically auditable, which are heuristic, and which remain "human review only." Currently 13 standards fully covered, 9 partial, 0 open standards-gap audits remaining (the five originally-parked audits — `course_alignment`, `learning_model`, `formative_variety`, `grading_structure`, `grading_load`, `accessibility` — all shipped 2026-06-10).
**When to use:** When triaging a course against the institutional checklist, or scoping a new audit tool against the standards it would close. Also the reference faculty cite when arguing "this audit maps to standard X.Y."
**Audit tag:** none (cross-walk reference; consumed via fact lookup).
**Status:** ⚠️ **v0.1** — checklist baseline + coverage map; refreshed as audits ship.
**Consumed by:** `canvas_course_expert.md`, the audit tools' standards-mapping comments. **Pairs with:** every audit-producing knowledge file (each closes one or more rows of the coverage map).

---

### [`critical_thinking_knowledge.md`](critical_thinking_knowledge.md)

**Sources:** AAC&U *Critical Thinking VALUE Rubric*; Paul-Elder Framework (Foundation for Critical Thinking — 8 elements + 9 intellectual standards); Anderson & Krathwohl (2001) revised Bloom's *Analyze / Evaluate / Create*; Brookhart (2010) *How to Assess Higher-Order Thinking Skills*; Socratic-questioning taxonomies; Willingham (2008) *Critical Thinking: Why Is It So Hard to Teach?*; Toulmin argumentation model; Bean (2011) *Engaging Ideas*.
**Core idea:** A shared vocabulary used by **two consumers** — (a) the **grader** scoring student work against a "critical thinking" rubric criterion, and (b) the **audit agent** evaluating whether an assignment is *designed to prompt* critical thinking. Five-dimension spine from the AAC&U VALUE rubric (explanation of issues, evidence, context/assumptions, position/perspective, conclusions/implications) with scorable anchors at each level. Distinguishes critical *thinking* (analyze / evaluate / synthesize) from critical *questioning* (Socratic taxonomy — clarification / probe assumptions / probe reasons / probe perspective / probe implications). Critically: most rubrics that name "critical thinking" do so with *vague descriptors* and need scorable anchors to be defensible.
**When to use:** When grading any criterion that names critical thinking, when authoring/auditing a rubric criterion meant to capture it, or when auditing whether an assignment's design *prompts* the skill (vs. recall).
**Audit tag:** none yet (reference-shape, dual-consumer; consumed via fact lookup by grader + audit).
**Status:** ⚠️ **v0.1** — dual-consumer file built ahead of a real critical-thinking criterion landing in a graded cohort; calibration pending.
**Consumed by:** [`canvas_grader.md`](canvas_grader.md) (when a rubric criterion targets critical thinking), `canvas_course_expert.md`. **Pairs with:** [`rubrics_knowledge.md`](rubrics_knowledge.md), [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md), [`grader_knowledge.md`](grader_knowledge.md), [`assessments_knowledge.md`](assessments_knowledge.md).

---

### [`grader_knowledge.md`](grader_knowledge.md)

**Source:** ds460-master grader beta (commits 754c966..91a5113 + 8f7814b + 2fd277f — round 1 KC1 code take-home + round 2 Mid Performance Review prose self-review + Classic-quiz mirror addendum); the originating handoff in `ds460-master/handoffs/HANDOFF_generic-grader-skill.md`; prior art across nbgrader / otter-grader / PrairieLearn / Gradescope and 2025-26 LLM-as-judge / grading-fairness research.
**Core idea:** The domain lessons for running a FERPA-safe, fair, defensible AI-assisted grading pipeline at the course level. Two-zone architecture (cloud = keys only; local = identity); holistic scoring (no per-criterion arithmetic); signals are priors not scores; 3-grader consensus + spread-driven NEEDS-REVIEW queue; grading runs agent-in-the-loop by default (the orchestrator `grader_grade.py` is an optional accelerator for key-holders); prompt-injection treated as content (sentinel-delimited); judge-bias mitigations (position/verbosity/self-preference); multi-output grading; grade-earned-not-asked reconciliation (incl. Classic-quiz mirror for New Quiz API gaps); wellbeing flags surface, never move score; push gated behind `--mark-reviewed` + canvas_course_guard; calibration is the design intent, not a defect (80/20 close + tunable).
**When to use:** Any course-grading workflow with the canvas-toolbox grader skill. Read alongside `grader_voice_knowledge.md` (per-instructor comment voice) and `grader_setup_knowledge.md` (the 6-step setup interview).
**Audit tag:** none (operational reference, not an audit producer).
**Status:** ✅ **v1.0** (ds460 KC1 alpha 2026-06-10: 20/22 within 0.5 on the medium criterion; cohort mean within 0.09 of the original push).
**Consumed by:** `canvas_grader.md`. **Pairs with:** [`grader_voice_knowledge.md`](grader_voice_knowledge.md), [`grader_setup_knowledge.md`](grader_setup_knowledge.md), [`rubrics_knowledge.md`](rubrics_knowledge.md), [`canvas_api_knowledge.md`](canvas_api_knowledge.md), [`canvas_api_lessons_learned.md`](canvas_api_lessons_learned.md), [`assessments_knowledge.md`](assessments_knowledge.md), [`backwards_design_knowledge.md`](backwards_design_knowledge.md).

---

### [`grader_voice_knowledge.md`](grader_voice_knowledge.md)

**Source:** ds460-master round 2 (commit 8f7814b — `agents/knowledge/student_feedback_voice_knowledge.md` — the working per-instructor voice file from the beta); originating handoff §F.
**Core idea:** How the grader writes the student-facing Canvas comment. Comment voice is per-instructor (not universal). The shared structure: `Overall: <Tier>` + one-sentence specific strength + `Coaching Tips:` header + one idea per paragraph + habit-to-build closing. **Hard rule:** never feed back data values (concept + question instead — fairness + safety). The per-instructor specifics (banned terms, dial settings, opener wording) live in `student_feedback_voice_<instructor>.md` the grader loads at runtime. The voice file is **learned**, not authored — via an edit roundtrip (bulk-emit → instructor edits → sync back → bake recurring patterns into the voice file).
**When to use:** Anywhere the grader emits a student-facing comment. Configures via the per-instructor file path in `config.voice.file`.
**Audit tag:** none.
**Status:** ✅ **v1.0** (the voice file framework drove the alpha's 20/22-within-0.5 result; KC1's `student_feedback_voice_chaz.md` is the working exemplar of the per-instructor file contract).
**Consumed by:** `canvas_grader.md`. **Pairs with:** [`grader_knowledge.md`](grader_knowledge.md), [`grader_setup_knowledge.md`](grader_setup_knowledge.md).

---

### [`grader_setup_knowledge.md`](grader_setup_knowledge.md)

**Source:** ds460-master round 2 §A (commit 8f7814b — the 6-step interview surfaced during the Mid Performance Review generalization); originating handoff §A + §B + §C + §D + §F + §J.
**Core idea:** The 6-step interview that gets an instructor from "I have an assignment" to a runnable per-assignment grader config. (1) input format → de-id adapter; (2) rubric — three paths: has-rubric / outcomes-or-contract / NEITHER (Path C builds one, the highest-leverage onboarding step); (3) critical thinking scored or formative; (4) one grade or several (multi-output); (5) reconciliation against the gradebook (incl. the §J Classic-quiz mirror pattern for New Quiz API gaps); (6) scale + bands + equivalences + voice + cost preview. Emits a structured `config.json` the grader pipeline runs against; subsequent cohorts of the same assignment skip most of the interview.
**When to use:** Onboarding a new instructor or new assignment to the grader.
**Audit tag:** none.
**Status:** ✅ **v1.0** (the 6-step interview was run informally for ds460 round 1 KC1 + round 2 Mid Review, producing runnable configs both times; the structured form here is the formalization). BAR-2 Path C (no-rubric case) deferred to a real example but not a v1.0 gate.
**Consumed by:** `canvas_grader.md`. **Pairs with:** [`grader_knowledge.md`](grader_knowledge.md), [`grader_voice_knowledge.md`](grader_voice_knowledge.md).

---

### [`voice_coaching_knowledge.md`](voice_coaching_knowledge.md)

**Sources:** Hattie & Timperley (2007) *The Power of Feedback* — three feedback questions; Wiggins (2012) *Seven Keys to Effective Feedback* (ASCD); Dweck (1998-ongoing) process vs ability praise; Brookhart (2008/2017) *How to Give Effective Feedback*; Sweller (1988-ongoing) Cognitive Load Theory; Hammond (2014) *Culturally Responsive Teaching and the Brain* (warm-demander pedagogy); Black & Wiliam (1998/2009) *Inside the Black Box* + *Assessment for Learning* (formative-feedback closing-the-gap); AI voice preservation literature (2025-2026); validated against DS 250 + DS 460 voice artifacts. Full audit trail at `handoffs/2026-06-25_voice-coaching-research.md` (gitignored).
**Core idea:** Upstream coaching scaffolding for the per-instructor voice file. Separates the **WHAT** (universal effectiveness criteria: hits the three Hattie questions, anchored to specific evidence, scoped to 1-2 priority items, forward-looking) from the **HOW** (per-instructor voice: 8 dimensions — warmth / directness / technical density / encouragement frequency / brevity / praise focus / question style / cultural register). Applies the canvas-toolbox 80/20 — this coaching file delivers the 80% via universal WHAT criteria; the existing edit roundtrip (`grader_voice_knowledge.md §4`) tunes per-instructor HOW. Includes a 5-question articulation interview for first-time faculty who don't yet have a voice file the existing roundtrip can refine. Edge cases (voice vs effectiveness conflicts) are handled via "surface, don't override" — agent flags with research citation; operator decides.
**When to use:** Anywhere a faculty member is being coached on grading-comment voice — first-time setup (before the edit roundtrip can refine), conflicts between voice habits and research-grounded effectiveness, or when articulating the WHAT/HOW boundary for an adopter who's confused about what the AI does and doesn't change.
**Audit tag:** none (coaching reference; consumed via fact lookup).
**Status:** ✅ **v1.0** — research-grounded across 8 pedagogical frameworks; validated against DS 250 + DS 460 voice artifacts. The voice-preservation contract honors the operator-set constraint that the AI must add value in PHRASING without losing the faculty's voice.
**Consumed by:** [`canvas_grader.md`](canvas_grader.md), the agent grading any LLM-comment cohort. **Pairs with:** [`grader_voice_knowledge.md`](grader_voice_knowledge.md) (structure + per-instructor file contract + edit roundtrip — the downstream operational layer), [`grader_setup_knowledge.md`](grader_setup_knowledge.md) (per-assignment config interview), [`grader_knowledge.md`](grader_knowledge.md) (push pipeline + safety gates the voice rides on top of).

---

### [`course_engagement_audit_knowledge.md`](course_engagement_audit_knowledge.md)

**Sources:** 34 CFR 668.22 (Cornell Law / eCFR); 2025-2026 Federal Student Aid Handbook Vol 5 Ch 1 + Ch 2 + Ch 3 (Withdrawals + R2T4 calculations); 2025-2026 FSA Handbook Vol 2 Ch 1 (Institutional Eligibility — academic engagement definition); Federal Register 89 FR 31031 (2025-01-03) — Distance Education + Return of Title IV final rules effective 2026-07-01. **All 6 sources cached locally** at [`sources/title_iv/`](sources/title_iv/); refreshed by [`update_title_iv_snapshot.py`](../../tools/update_title_iv_snapshot.py).
**Core idea:** Title IV federal-compliance audit that classifies a course's enrolled students into ACTIVE / UW / UF / NEVER_PARTICIPATED based on their last date of academically related activity vs an operator-provided UF cutoff date. Compliant per DOE definition: counts assignment submissions + quiz submissions + discussion entries; explicitly does NOT count Canvas page views or `last_activity_at` (DOE: *"logging in is not sufficient"*). Establishes a **NEW FERPA tier 3** — the named report is written to `~/Downloads/` (outside the repo entirely) so the LLM has no working-directory access to the student-named output.
**When to use:** Term-end (or any time the institution needs an R2T4 candidate list). Faculty provides a UF cutoff date; the audit produces a Markdown + PDF report in the user's Downloads folder with each student classified + the documented last-engagement timestamp.
**Audit tag:** `engagement_classification` ∈ {`active`, `uw`, `uf`, `never_participated`}.
**Status:** ✅ **v1.0** — Title IV definitions verified 2026-06-26 against the 6 cached canonical sources. **Next review:** 2027-06-26 (or sooner if DOE issues new R2T4 / distance-ed guidance). The Distance Ed + R2T4 final rules effective 2026-07-01 are the latest material rule change.
**Consumed by:** [`canvas_grader.md`](canvas_grader.md), `canvas_course_expert.md`. **Pairs with:** [`grader_knowledge.md`](grader_knowledge.md) §1 (FERPA tier 3 — Downloads-folder named report), the cached Title IV sources in [`sources/title_iv/`](sources/title_iv/).

---

### [`structured_teaching_knowledge.md`](structured_teaching_knowledge.md)

**Sources:** Sathy & Hogan (2022), *Inclusive Teaching*; Walton & Cohen (belonging uncertainty); Felten & Lambert (2020), *Relationship-Rich Education*.
**Core idea:** *Structure is an equity lever* — clear specs, scaffolding, defined roles, and predictable cadence help all students and disproportionately the underserved (they reduce the hidden "unwritten rules" tax). This is the reasoning frame that gives the toolkit's existing structural findings their "so what / who it hurts most" layer; belonging uncertainty is the mechanism. Reasoning enrichment, not a new audit. Non-demographic — reasons about course design, never labels students.
**When to use:** When interpreting a structural gap — name the equity stake, frame fixes as "more structure, for everyone."
**Audit tag:** none (reasoning enrichment, consumed via fact lookup).
**Status:** ✅ **v1.0** (reasoning enrichment; no calibration risk).
**Consumed by:** `canvas_course_expert`. **Pairs with:** `cognitive_load_theory_knowledge.md`, `hattie_3phase_knowledge.md`, `course_design_language_knowledge.md`.

---

## Tag stack — full audit output

A well-formed audit issue carries up to nine tag dimensions so the reader can route it cleanly:

| Tag | From file |
|---|---|
| `hattie_phase` | `hattie_3phase_knowledge.md` |
| `cognitive_load_type` | `cognitive_load_theory_knowledge.md` |
| `learning_domain` | `three_domains_knowledge.md` or `taxonomy_explorer_knowledge.md` |
| `taxonomy_source` | `taxonomy_explorer_knowledge.md` (only when BYUI-tool framing was used) |
| `sequencing` | `experiential_learning_knowledge.md` |
| `design_mode` | `designer_thinking_knowledge.md` |
| `design_coherence` | `course_design_language_knowledge.md` |
| `design_principle` | `course_design_language_knowledge.md` |
| `clo_quality` | `outcomes_quality_knowledge.md` |
| `clo_criteria_flags` | `outcomes_quality_knowledge.md` (list of failing AoL criteria) |
| `ai_agency` | `inverted_blooms_knowledge.md` |

The Course Design Language tags are paired (two-axis): `design_coherence` ∈ `{architected, partial, assembled}` describes *how well* a principle is satisfied; `design_principle` ∈ `{visual_grammar, narrative_metaphor, dual_framing, structural_beats, observable_rubrics, alignment_traceability}` says *which principle* the finding is about.

The Toyota A3 structure wraps the issue itself.

---

## Adding a new knowledge file

If you add a new framework reference here, follow the existing pattern:

1. Frontmatter: source citation, who uses it (`canvas_course_expert.md` etc.), companion files.
2. Theory section — short, prose-first.
3. Canvas Audit Indicators — concrete signals that flag the issue.
4. The audit tag the agent should emit.
5. Quick Reference for Auditors — a numbered checklist.
6. Add a one-paragraph entry to this README.

**Versioning convention:** a knowledge file's JSON `changelog` starts at `0.x` while it is built-but-unvalidated, and is promoted to `1.0` only after it has been successfully exercised against a real course (the build → test → update loop). A `0.x` file is intentionally **not** added to "The files" catalog above until it reaches `1.0` — an untested file should not read as authoritative or be advertised as a routing target.

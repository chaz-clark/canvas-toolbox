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
| Whether the course's learning outcomes are well-formed (precedes alignment) | [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) |
| Whether a rubric is well-formed (4-criterion backbone, typology, alignment-to-CLOs) | [`rubrics_knowledge.md`](rubrics_knowledge.md) |
| Whether a specific assessment is the right type (formative vs. summative) and AI-resistant | [`assessments_knowledge.md`](assessments_knowledge.md) |
| Whether assessments accept AI-generated work as a substitute for learning | [`inverted_blooms_knowledge.md`](inverted_blooms_knowledge.md) |
| Whether a BYUI course is a coherent artifact (visual grammar, rubrics, alignment) | [`course_design_language_knowledge.md`](course_design_language_knowledge.md) |
| Writing a precise change plan for a flagged issue | [`toyota_gap_analysis_knowledge.md`](toyota_gap_analysis_knowledge.md) |
| Setting up + running a FERPA-safe AI-assisted grading pipeline (core lessons) | [`grader_knowledge.md`](grader_knowledge.md) |
| Per-instructor comment voice for the grading pipeline | [`grader_voice_knowledge.md`](grader_voice_knowledge.md) |
| Onboarding a new instructor / assignment to the grader (6-step interview) | [`grader_setup_knowledge.md`](grader_setup_knowledge.md) |

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

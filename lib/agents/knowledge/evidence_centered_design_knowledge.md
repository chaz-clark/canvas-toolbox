---
name: evidence_centered_design_knowledge
version: '1.0'
last_updated: '2026-07-16'
description: 'Trigger-keyed playbooks for *strengthening* an assessment: clarifying the core learning, identifying convincing evidence, making learning visible, stress-testing that visibility in an AI-rich environment, and adding one architectural improv'
skill_type: knowledge
shape: procedural
scope: 'Actionable sequential procedure for redesigning a single assessment into stronger evidence of learning (Evidence-Centered Design). Boundaries: does not classify/audit assessments (assessments_knowledge.md, reference shape) and does not decide what a course should teach (backwards_design_knowledge.md). The ''do'' step that runs after the audit flags weakness; composes with both, replaces neither.'
consumed_by:
- canvas_course_expert.json
- ira_program_alignment.md
provenance:
  sources:
  - 'BYUI ''Architects of Learning'' workshop deck — *Designing Stronger Assessments: Engineering Stronger Evidence of Learning* (13 slides; instructor name to be backfilled). pre_knowledge/assessments/Designing Stronger Assessments.pptx, retrieved 2026-05-18. The deck names its frame ''Evidence-Centered Assessment Design.'''
companion_json_deprecated: 2026-07-16 - consolidated into YAML frontmatter (JSON purge convention)
runtime_strategy: read_at_runtime
metadata:
  knowledge_id: evidence_centered_design_knowledge
---

# Evidence-Centered Assessment Design (ECD) — Redesign Playbooks

> Procedural. Trigger-keyed playbooks for *strengthening* an assessment: clarifying the core learning, identifying convincing evidence, making learning visible, stress-testing that visibility in an AI-rich environment, and adding one architectural improvement.

Source: BYUI "Architects of Learning" workshop deck *Designing Stronger Assessments — Engineering Stronger Evidence of Learning* (13 slides; instructor name to be backfilled), dropped in `pre_knowledge/assessments/Designing Stronger Assessments.pptx` on 2026-05-18.

Used by: `canvas_course_expert.json`, `ira_program_alignment.md`

Companions: [`assessments_knowledge.md`](assessments_knowledge.md) (the *diagnostic* — formative/summative, the Litmus Test, the Strategies catalog; this file is what you run to *act on* a Litmus failure), [`backwards_design_knowledge.md`](backwards_design_knowledge.md) (Decision 1 ≈ UbD Stage 1 desired results; Decision 2 ≈ UbD Stage 2 assessment evidence), [`inverted_blooms_knowledge.md`](inverted_blooms_knowledge.md) (AI-agency framing feeds Decision 4), [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) (Decision 1 "core learning" must be a well-formed outcome), [`toyota_gap_analysis_knowledge.md`](toyota_gap_analysis_knowledge.md) (A3 format for the redesign write-up).

**Scope**: An actionable, sequential procedure for redesigning a *single* assessment into stronger evidence of learning. Out of scope: classifying or auditing an assessment (that is [`assessments_knowledge.md`](assessments_knowledge.md) — `reference` shape, descriptive), and deciding *what* a course should teach (that is [`backwards_design_knowledge.md`](backwards_design_knowledge.md)). This file is the *do* step that runs after the audit flags weakness; it composes with both, replacing neither.

**Provenance**: BYUI Architects of Learning workshop deck *Designing Stronger Assessments* (`pre_knowledge/assessments/Designing Stronger Assessments.pptx`, 13 slides, retrieved 2026-05-18; instructor name to be backfilled). The deck names its frame "Evidence-Centered Assessment Design." See `provenance.sources` in the JSON.

_Last updated: 2026-05-18_

---

## Operating frame

**The thesis (slide 4):** *AI mostly threatens assessments that mistake product for cognition.* Redesign moves an assessment from the Weak column to the Strong column:

| Weak focus | Strong focus |
|---|---|
| Task completion | Thinking demonstration |
| Polished product | Decision-making |
| Correctness | Reasoning |
| Recall | Transfer / translation |
| Output | Process + judgment |

**The orienting question (slide 3):** *If learning is invisible, how do we make it visible — credibly?* "Learning is invisible; assessment is the art of making it visible credibly" (slide 9). The playbooks below are the engineering steps for that.

---

## Playbooks

### full_assessment_redesign

**Trigger:** An instructor wants to strengthen a specific assessment — typically one flagged by the [`assessments_knowledge.md`](assessments_knowledge.md) Litmus Test (`litmus_pass_rate` low, or `grading_target: output_only`, or `assesses_struggle: false`), or chosen from a course workbook. One assessment at a time.

**Prerequisites:**
- One named assessment selected (not a whole course — slide 6: "Select ONE assessment").
- Its current intent, task, and rubric available (Canvas-pulled or instructor-supplied via `course_ref/`).
- The instructor present and answering — Decisions 1–2 require their judgment; never infer the "core learning" from the task title.

**Steps (the five design decisions — order matters):**
1. **Clarify the Core Learning.** Ask: *what is the most important thing students should learn or be able to do?* Push the answer **beyond** "what they produce" / "assignment format" **toward** capability, reasoning, transfer, habits of mind, disciplinary thinking. Cross-check the result is a well-formed outcome ([`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md)) and aligns to UbD Stage 1 ([`backwards_design_knowledge.md`](backwards_design_knowledge.md)).
2. **Identify Convincing Evidence.** Ask: *what would genuinely convince you the student achieved that learning?* Push **beyond** completion / polished output / correctness **toward** synthesis, transfer, prioritization, adaptation, judgment, reflection, demonstration, reasoning. (UbD Stage 2 alignment.)
3. **Make the Learning Visible.** Ask: *through what activity, behavior, or performance would students reveal that evidence?* Candidate forms: oral defense, case analysis, annotation, reflection, draft progression, critique, presentation, simulation, novel-context application, peer review, revision rationale, discussion/debate. Choose the form that surfaces the Decision-2 evidence most directly.
4. **Stress-Test the Visibility (AI-rich environment).** Run the four questions: (a) Could AI complete this without meaningful student engagement? (b) What role *should* AI play in this task? (c) What parts reflect authentic student thinking? (d) Are we assessing learning, AI orchestration, or both? Frame as intentional design, **not prohibition**. This is the same lens as the `assessments_knowledge.md` Litmus rows "Resist easy automation by AI" / "Rely on unsupervised work" and the `inverted_blooms_knowledge.md` `ai_agency` tag — reuse those classifications here.
5. **Strengthen the Architecture.** Add **exactly ONE** meaningful improvement (constraint from slide 11 — one major change prevents overwhelm). Menu: iterative drafts, checkpoints, oral defense, process annotations, AI-use documentation, transfer tasks, peer review, revision reflections. Map the chosen improvement back to which Decision-4 weakness it closes.

**Success condition:** One redesigned assessment concept with (a) an explicit core-learning statement, (b) named convincing evidence, (c) a visibility activity, (d) a documented AI stress-test result, and (e) exactly one applied improvement traceable to a specific weakness. Output as an A3 ([`toyota_gap_analysis_knowledge.md`](toyota_gap_analysis_knowledge.md)): current → target → gap → countermeasure (the one improvement) → verification (the validity-gate check below).

---

### ai_visibility_stress_test

**Trigger:** Need to judge whether an existing assessment's evidence is trustworthy in an AI-rich environment, *without* doing a full redesign (e.g., a fast pass during a course audit, or triaging which assessments need `full_assessment_redesign` first).

**Prerequisites:** The assessment task + submission type known. AI-agency vocabulary available ([`inverted_blooms_knowledge.md`](inverted_blooms_knowledge.md): `ai_dependent` / `scaffolded` / `student_owned`).

**Steps:**
1. Ask: could AI complete this without meaningful student engagement? (If yes → high risk.)
2. Ask: what role *should* AI play here — and is that role designed in or just unaddressed?
3. Ask: what parts of the artifact reflect authentic student thinking vs. could be AI-produced with no trace?
4. Ask: is the assessment measuring the learning, the student's AI orchestration, or both — and is that intended?

**Success condition:** A per-assessment trustworthiness verdict (`student_owned` / `scaffolded` / `ai_dependent`, aligned with `inverted_blooms_knowledge.md`) plus a one-line reason. Feeds the `full_assessment_redesign` trigger when the verdict is `ai_dependent` and the core learning warrants it.

---

### validity_gate_check

**Trigger:** A redesign or improvement has been proposed and you must decide whether it actually adds validity (slide 12 whole-class debrief). Run before accepting any Decision-5 change.

**Prerequisites:** A concrete proposed change (ideally the single Decision-5 improvement).

**Steps:**
1. Ask: does this redesign improve the *evidence of learning* (not just deter AI)?
2. Ask: did it add complexity *without* adding validity? If yes — reject or simplify (overwhelm constraint, slide 11).
3. Ask the decisive question (slide 12): **would this change improve learning even if AI didn't exist?** "That final question matters most." If the answer is no, the change is AI-theater, not stronger evidence — send it back to Decision 5.

**Success condition:** The proposed change passes question 3 (improves learning independent of AI) and question 2 (validity gain ≥ complexity cost). Only then is the `full_assessment_redesign` success condition satisfied.

---

## Related Knowledge

`assessments_knowledge.md` answers *"is this assessment weak, and how?"* (Litmus Test, Strategies catalog, audit tags). This file answers *"given that it's weak, how do I rebuild it?"* The intended flow:

1. `canvas_course_expert` audits a course using `assessments_knowledge.md` → emits `litmus_test_flags`, `strategy_match`, `ai_agency`.
2. For a flagged assessment, the agent invokes `full_assessment_redesign` here, feeding the audit tags as inputs to Decisions 4–5.
3. `validity_gate_check` is the verification step — it closes the A3.

Do **not** use this file to *classify* assessments (wrong shape — that's the `reference` file). Do **not** append redesign procedures into `assessments_knowledge.md` (shape violation — it is `reference`, this is `procedural`).

---

## References

- BYUI Architects of Learning, *Designing Stronger Assessments — Engineering Stronger Evidence of Learning* (workshop deck, 13 slides, 2026; instructor name to be backfilled). `pre_knowledge/assessments/Designing Stronger Assessments.pptx`.
- Evidence-Centered Design (ECD) — the deck's named frame (slide 5: "Evidence-Centered Assessment Design").
- Companion knowledge: `assessments_knowledge.md`, `backwards_design_knowledge.md`, `inverted_blooms_knowledge.md`, `outcomes_quality_knowledge.md`, `toyota_gap_analysis_knowledge.md`.

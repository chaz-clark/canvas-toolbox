# Assessments — Formative, Summative, and AI-Resistant Design

Source: Poorvu Center for Teaching and Learning, Yale University. *Formative & Summative Assessments*. https://poorvucenter.yale.edu/teaching/teaching-resource-library/formative-summative-assessments ; Hardman, P. (2024). *Redesigning Instruction & Assessment in the Age of AI*. https://drphilippahardman.substack.com/p/redesigning-instruction-and-assessment ; BYUI Architects of Learning instructor (2026, name TBD), 6-slide deck on AI-era assessment design (`pre_knowledge/assessments/`).

Used by: `canvas_course_expert.json`, `ira_program_alignment.md`

Companions: [`backwards_design_knowledge.md`](backwards_design_knowledge.md) (Wiggins/McTighe 3-stage UbD — the upstream design logic that decides *which* assessment to write), [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) (CLO well-formedness — must pass before alignment is meaningful), [`inverted_blooms_knowledge.md`](inverted_blooms_knowledge.md) (AI-agency framing for whether an assessment produces student-owned evidence), [`designer_thinking_knowledge.md`](designer_thinking_knowledge.md) (backward design five-stage frame — *content as tool, not destination*), [`hattie_3phase_knowledge.md`](hattie_3phase_knowledge.md) (Surface → Deep → Transfer — which phase the assessment is probing), [`cognitive_load_theory_knowledge.md`](cognitive_load_theory_knowledge.md) (germane load — what the student's own working memory is actually doing), [`course_design_language_knowledge.md`](course_design_language_knowledge.md) (observable rubrics), [`taxonomy_explorer_knowledge.md`](taxonomy_explorer_knowledge.md) and [`three_domains_knowledge.md`](three_domains_knowledge.md) (verb classification), [`experiential_learning_knowledge.md`](experiential_learning_knowledge.md), [`toyota_gap_analysis_knowledge.md`](toyota_gap_analysis_knowledge.md) (output A3 format).

> Reference. Indexable definitions and design principles for formative vs. summative assessment, alignment to outcomes, and AI-resistant assessment design. Consult at runtime when classifying an assessment or evaluating its design.

**Scope**: Definitions, distinctions, and design principles for the two main assessment types and for AI-era design adjustments. Out of scope: the upstream question of *what* to assess (that is decided by backward design — see [`backwards_design_knowledge.md`](backwards_design_knowledge.md)) and the question of whether the outcomes the assessment targets are themselves well-formed (see [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md)).

**Provenance**: Yale Poorvu Center *Formative & Summative Assessments* page (8 pages, retrieved 2026-05-12); Hardman *Redesigning Instruction & Assessment in the Age of AI* (Substack, 2024 — saved HTML; body content not extractable from saved snapshot, citation by title and stated thesis only); Chaz Clark's *Designing Assessments — Testing the Foundation* notes (BYUI faculty-development "Architects of Learning" week on assessments, 2026); Grant Wiggins UbD video transcript (10 min, ASCD); **BYUI Architects of Learning instructor (2026, name to be backfilled) — 6-slide deck on AI-era assessment design, dropped in `pre_knowledge/assessments/` on 2026-05-14: *What Hasn't Changed*, *How AI Broke the Assumption*, *The Limits of Grading Outputs*, *The Assessment Litmus Test*, *Assessment Strategies*, *The Path Forward*.** See `provenance.sources` in the JSON.

_Last updated: 2026-05-14_

---

## Terms

### Formative Assessment

**Definition (Poorvu).** An assessment employed *while learning is ongoing* to collect information about whether course objectives are being advanced and how teaching can be improved. Aims to identify strengths, challenges, and misconceptions and to close those gaps. May involve students assessing themselves, peers, or even the instructor — through writing, quizzes, conversation, polls, low-stakes group work, weekly quizzes, 1-minute reflections, homework, or surveys.

**Why it matters.** Formative assessment improves student learning by allowing teachers to better understand misconceptions (Bakula, 2010), and bolsters student motivation, metacognition, and performance on later summative assessments (Trumbull & Lash, 2013; McLaughlin & Yan, 2017; King, 2023).

**Audit signal.** A course with only summative graded artifacts and no in-flight checks is structurally fragile — there is no mechanism for the instructor to detect misconceptions before the high-stakes measurement.

### Summative Assessment

**Definition (Poorvu).** An assessment used by instructors *to evaluate student learning, knowledge, proficiency, or success at the conclusion* of an instructional period — a unit, course, or program. Almost always formally graded, often heavily weighted. Common forms: exams, papers, presentations, final projects, final reports, final grades.

**Why it matters.** Summative assessments designed to test the ability to *apply* skills and course material (rather than rote memorization) allow for a more holistic evaluation of understanding and performance (Ali, 2024).

**Audit signal.** A course where every summative is recall-only is mismatched to any CLO that uses an Apply-and-above verb. Cross-check with [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md).

### When to combine

Formative and summative are very effective in conjunction. Formative improves both teaching (instructor signal) and learning (student metacognition); summative measures the final state. Using both promotes student motivation, metacognition, and understanding of course content. Instructors should also use formative assessment results and student feedback to inform future teaching practice.

---

## The Seven Principles for Formative Assessment

Adapted by Poorvu from Nicol & Macfarlane-Dick (2007), with additions. Use these as a checklist when auditing a course's formative-assessment design.

1. **Provide clear criteria for good performance.** Explain criteria; encourage discussion through office hours, post-grade peer review, or exam/assignment wrappers; hold class-wide conversations on criteria at strategic moments throughout a term.
2. **Encourage self-reflection.** Ask students to evaluate their own or a peer's work against course criteria; have them describe strengths and weaknesses through writing or group discussion.
3. **Give detailed, actionable feedback.** Feedback should be specific, tied to predefined criteria, and accompanied by an opportunity to revise or re-apply *before* final submission. Feedback should be corrective and forward-looking, not merely evaluative. Examples: comments on multiple paper drafts, criterion discussions in 1-on-1 conferences, regular online quizzes.
4. **Encourage dialogue around the formative learning process.** Mid-semester feedback, small-group feedback sessions, and weaving student feedback into the syllabus.
5. **Promote positive motivational beliefs and self-esteem.** Allow rewrites/resubmissions; use low-stakes formative tools or anonymous automated online testing where unlimited resubmissions are appropriate.
6. **Provide opportunities to close the gap between current and desired performance.** Resubmission opportunities, specific action points for writing or task-based assignments, sharing study or process strategies that the instructor would use.
7. **Collect feedback to shape teaching.** Use student feedback to provide targeted instruction; identify where students face challenges in assignments, exams, and written submissions; this promotes metacognition. Poorvu staff can perform classroom observations or small-group feedback sessions. Incorporate this feedback into future pedagogy.

---

## Recommendations for Summative Assessments

From Poorvu Center. Apply when auditing a course's summative artifacts and rubrics.

1. **Share a rubric.** A rubric lays out expected performance criteria for a range of grades. Rubrics describe what an ideal assignment looks like and "summarize" expected performance at the beginning of a term — providing clarity and expectations. (Cross-reference: [`course_design_language_knowledge.md`](course_design_language_knowledge.md) on observable rubrics with `long_description` on every rating.)
2. **Design clear, effective questions.** For essay questions, ensure they are clear and aligned with course materials and objectives, while allowing students freedom to express knowledge creatively and in ways that honor how they digested, constructed, or mastered meaning.
3. **Assess comprehensiveness.** Effective summative assessments give students an opportunity to consider the totality of the course content — making broad connections, demonstrating synthesized skills, and exploring deeper concepts that drive or found a course's ideas and content. Select the assessment type (exam, final paper, project) such that students can demonstrate learning and conceptual understanding.
4. **Make parameters clear.** Length, depth of response, time and date, grading standards must be well-defined. Knowledge assessed must relate clearly to content covered in the course. Provide required space and support for students with disabilities.
5. **Grade blindly when bias risk is high.** When the goal is truly unbiased results, consider blind-grading techniques. When the goal is feedback that speaks to a student's term-long trajectory, know whose work you are grading.

---

## AI-Resistant Assessment Design (Hardman 2024; Kassorla *Inverted Bloom's*; BYUI Architects of Learning 2026)

The Hardman article (subtitle: *"the increasingly critical role of instructional design in the AI world"*) frames the central shift: in the AI era, the polished submission is no longer evidence of learning. Assessment design must produce **student-owned evidence**, not merely an artifact that *could have been* student-produced.

**Note on provenance.** The saved HTML snapshot of the Hardman article (in `pre_knowledge/assessments/`) is a JavaScript-rendered Substack page; the article body did not extract from the saved file. The thesis above is established from the article's stated title, subtitle, and the role it plays in Chaz's *Designing Assessments — Testing the Foundation* week. For specifics beyond the thesis, consult the live URL or the companion file [`inverted_blooms_knowledge.md`](inverted_blooms_knowledge.md), which carries the AI-agency framing in full. The expanded structural treatment in the subsections below (*What hasn't changed*, *How AI broke the assumption*, *The limits of grading outputs*, *The Assessment Litmus Test*, *Assessment Strategies catalog*, *The Path Forward*) is sourced from the BYUI Architects of Learning slide deck dropped in `pre_knowledge/assessments/` on 2026-05-14 (instructor name to be backfilled).

### What hasn't changed

Despite everything AI has disrupted, the fundamentals remain. Students still need to learn:

- Content knowledge
- Communication skills
- Problem-solving
- Critical thinking

**The goal hasn't shifted — only the methods need to evolve.** Assessment must verify that *real learning happened*, not just that a product was submitted.

This is the load-bearing premise for everything below: the response to AI is not to lower expectations of what students must master, but to redesign how we collect evidence that they have.

### How AI broke the assumption

The implicit assumption of traditional assessment — *the student wrote it, so the student learned it* — no longer holds. AI broke six specific load-bearing pieces:

1. **Authorship is unreliable.** You can no longer assume the student wrote it.
2. **Detection has failed.** AI-detection tools are inaccurate and inequitable (false positives concentrate on ESL writers and neurodivergent students).
3. **Out-of-class work lost credibility.** Unsupervised submissions are now unverifiable as evidence of student work.
4. **Foundational skills became skippable.** Students can bypass the learning process — turning in summative artifacts without ever doing the cognitive work the assignment was designed to provoke.
5. **Difficulty ≠ rigor.** Hard tasks are not rigorous if AI can do them. The difficulty of the prompt no longer tells you anything about the cognitive demand on the student.
6. **Feedback loops got distorted.** Feedback now targets the AI's output, not the student's thinking — eroding the formative signal that feedback was meant to carry.

These six mechanisms are why every AI-resistant design move that follows is *structural*, not stylistic. You cannot patch this with a stricter rubric or a longer assignment prompt — the assumption the assessment rested on is broken at the foundation.

### The limits of grading outputs

Even before AI, grading the final output (essay, code, lab report, polished deliverable) was a structurally incomplete signal of learning. AI made the structural problem acute, but the limits below predate it. Six reasons output-only grading is insufficient:

1. **Outputs hide decision-making.** The student's choices — what they considered and rejected, what they reframed, what they got stuck on — are erased from the artifact.
2. **Outputs reward fluency and style over understanding.** A clean-prose submission can mask a shallow conceptual model; a rough-prose submission can mask a deep one.
3. **Learning occurs in the middle of a process — outputs come at the end.** Grading only the end-state measures the destination, not the journey. The cognitive work the assessment was designed to drive is no longer visible to the grader.
4. **Independent function doesn't always signal competence.** A student who produces the right answer through trial-and-error, AI assistance, or memorization of worked examples may have no transferable model — they can do *this* task but not the *next* task in the same skill class.
5. **Outputs can reward formulaic template-following instead of transferability.** A five-paragraph essay that hits all the rubric criteria can score full marks without demonstrating that the student could write effectively for a different audience or purpose.
6. **Outputs incentivize performance over growth.** Students optimize for the score, not the learning — and the assessment trains them to do so.

> *Performance = optimizing efficiency and decreasing risk. Growth = developing new skills at the fringe of understanding.*

The audit corollary: a course that grades only finished artifacts cannot distinguish a high-performing student from a high-growth student — and over time, will lose the latter to the former.

### Design principles (synthesized from notes + transcript + Kassorla via `inverted_blooms_knowledge.md`)

- **Productive friction is the design goal, not an obstacle.** Staged drafts, oral defenses, process documentation, and revision cycles all introduce friction that requires evidence of the student's own thinking. A submission with no friction is structurally indistinguishable from an AI-generated artifact.
- **Shift from artifact-as-evidence to process-as-evidence.** Assessments that grade only the final product accept whatever produced it. Assessments that grade the trajectory (outline → draft → critique → revision → oral) measure the student.
- **Align the assessment to a CLO that names student agency.** Outcomes worded around "the student will produce X" accept any X. Outcomes worded around "the student will demonstrate, justify, and revise X" require the student themselves to be present in the evidence.
- **AI-agency tag.** Apply the `ai_agency` ∈ {`ai_dependent`, `scaffolded`, `student_owned`} tag from [`inverted_blooms_knowledge.md`](inverted_blooms_knowledge.md). Every text-based, artifact-submission assignment should be classified.

### The Assessment Litmus Test

A direct yes/no checklist an auditor (or instructor) can apply to any assessment in any course. Each row produces one bit of audit signal. A well-designed assessment passes most of the left column and avoids all of the right column.

| ✓ Assessments should… | ✗ Assessments shouldn't… |
|---|---|
| Encourage growth over performance | Equate a polished product with deep knowing |
| Reveal the learning process | Rely on unsupervised work as proof of learning |
| Resist easy automation by AI | Use difficulty as a proxy for rigor |
| Assess transferable understanding | Assume independent work signals competence |
| Provide feedback on both the thinking and the output | Incentivize efficiency over understanding |

**How to apply during an audit:**

For each assessment in the course, score the 10 rows (5 shoulds + 5 shouldn'ts) as pass / fail / unclear. The output is a `litmus_test_flags` array of failed rows, plus a per-assessment `litmus_pass_rate` (e.g., `8/10`). An assessment that fails more than 2 rows is structurally weak; flag for redesign rather than minor revision.

**Pairs with other tags:**
- A failure on *"Rely on unsupervised work as proof of learning"* should co-occur with `ai_agency: ai_dependent` (from `inverted_blooms_knowledge.md`).
- A failure on *"Assess transferable understanding"* should co-occur with `tma_balance: acquisition_only` (from `backwards_design_knowledge.md` — Stage 3 T-M-A coding).
- A failure on *"Reveal the learning process"* should co-occur with `assessment_type: summative` *only* — formative-only courses can fail this row without it indicating defect.

### Assessment Strategies catalog

Seven strategies that move an assessment toward the left column of the Litmus Test. Each is paired with its honest challenge — the failure mode that emerges when the strategy is applied lazily. Use as a redesign menu, not a prescription.

| Strategy | Benefit | Challenge |
|---|---|---|
| **Process-Oriented Assignments** | Ensures students engage in a learning process | Can still be faked. Requires assessing the process, which isn't something we're all used to. |
| **Oral & Performance-Based** | Hard for AI to complete — requires human demonstration | May assess delivery over knowledge. Distance-learning environments are especially challenged. |
| **Frequent, Low-Stakes Assessments** | Tracks ongoing progress and ensures continuous engagement | Can still be faked. Adds to student load and risks becoming busy work. |
| **Two-Lane Approach** | Gives credit for work both with and without AI. Emphasizes core content and AI application skills. | Lane 1 (no-AI) requires extensive safeguarding, especially in online environments. Can it be done? |
| **Authentic Assessment** | Students apply understanding to real situations | Students will authentically use AI. How do you know what they actually know? Transferability to online courses varies. |
| **Personalized & Adaptive Learning** | Leverages AI to help students learn and potentially assess performance within the experience | We're not there yet, especially at scale or in distance education. Access remains a concern. |
| **Peer Assessment** | Assesses both the author's work and the reviewer's understanding | May require deeper analysis of the reviewer's feedback to be meaningful. |

**Strategy-to-litmus mapping (audit cross-reference):**

| If the assessment fails the Litmus row… | …the strategy most likely to fix it |
|---|---|
| Reveal the learning process | Process-Oriented Assignments |
| Rely on unsupervised work as proof of learning | Oral & Performance-Based |
| Encourage growth over performance | Frequent, Low-Stakes Assessments |
| Use difficulty as a proxy for rigor | Two-Lane Approach |
| Assess transferable understanding | Authentic Assessment |
| Assume independent work signals competence | Peer Assessment |

**Auditor's note:** Every strategy has a known failure mode — that is design honesty, not a reason to avoid the strategy. Flag in the audit when an instructor reaches for a strategy but no safeguard against its named challenge is visible. Example: a "Process-Oriented" rubric that grades only the final draft (with the outline submitted but ungraded) is structurally Process-Oriented in name only — and the agent should surface it as `strategy_match: process_oriented_unguarded`.

### The Path Forward

The reframing question that holds the whole section together:

> **Stop asking:** *"How do we prevent students from using AI?"*
> **Start asking:** *"What does our assessment actually measure?"*

The first question is unanswerable in any durable way — detection has failed (see *How AI broke the assumption*), and every prevention move triggers an arms race. The second question is answerable, and the answer determines whether the assessment is structurally sound regardless of what tools the student uses.

Four directives follow from the reframe:

1. **Make thinking visible.** Assess process and reasoning, not just final products. (Cross-references: *The limits of grading outputs* and *Assessment Strategies catalog → Process-Oriented Assignments*.)
2. **Value struggle.** Reward growth and risk-taking over polished performance. The Litmus row *"Encourage growth over performance"* operationalizes this.
3. **Verify authorship while trusting students.** Use in-class work, drafts, and dialogue to encourage learning — not to police AI use. The distinction matters: in-class work and dialogue produce student-owned evidence as a *byproduct* of the design, without framing the student as a suspect.
4. **Test transferability.** Require application to novel contexts. This is the same transfer goal that drives UbD Stage 1 — see [`backwards_design_knowledge.md`](backwards_design_knowledge.md) → *Stage 1 — Identify Desired Results* and the *T-M-A* coding in Stage 3. An assessment that doesn't test transfer cannot, by Wiggins/McTighe's framing, measure understanding.

**Audit output:** Each assessment in the course should be tagged with which directives it honors (`directives_honored: [make_thinking_visible, value_struggle, verify_authorship, test_transferability]`). An assessment that honors zero of the four is a candidate for redesign rather than revision, regardless of its current rubric quality.

### BYUI-context constraints (Chaz)

- **No Sunday due dates.** Faith/values respect is non-negotiable in BYUI courses; design weekly rhythms so summative deadlines do not land on Sunday.
- **HITL non-negotiable.** Any AI use in feedback, grading, or formative scaffolding must include a human in the loop on consequential decisions.

---

## Alignment to Outcomes (the why behind the assessment)

The Poorvu page opens with a definition that ties everything together:

> *"Assessments are evaluative assignments that allow instructors and students to monitor progress towards achieving course learning objectives."*

This is the **alignment claim**. An assessment that does not let either party monitor progress toward a specific CLO is not an assessment — it is a graded artifact. The audit question is:

**For each assessment in the course, name the CLO it measures. If you cannot, the assessment is orphaned.**

Pairs with [`backwards_design_knowledge.md`](backwards_design_knowledge.md) (the design logic: outcomes determine assessments; assessments are not chosen first) and [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) (rubric criteria must trace back to a named CLO; the AoL Rubric criterion check).

---

## Quick Reference for Auditors

1. **Classify every assessment** as formative or summative. A course with zero formative checks is structurally fragile.
2. **For each summative, name the CLO** it measures. Orphaned summatives are red flags.
3. **For each formative, name what it tells the instructor or student.** Formatives that produce no actionable signal are decorative.
4. **Check the seven formative principles.** Most courses fail principles 3 (actionable feedback) and 6 (gap-closing opportunity).
5. **Check the five summative recommendations.** Most courses fail principles 1 (shared rubric) and 4 (parameter clarity).
6. **Apply the Assessment Litmus Test** (5 shoulds + 5 shouldn'ts) per assessment. Emit `litmus_test_flags[]` + `litmus_pass_rate`. > 2 failures → redesign candidate.
7. **For each weak assessment, map to a Strategies catalog entry** and check whether the strategy's named challenge is safeguarded. If not, emit `strategy_match: <strategy>_unguarded`.
8. **Tag each assessment with the Path Forward directives it honors** (`directives_honored: [make_thinking_visible, value_struggle, verify_authorship, test_transferability]`). Zero honored → redesign candidate.
9. **Apply the AI-agency tag** from `inverted_blooms_knowledge.md` to every text/artifact submission.
10. **Verify no Sunday due dates.** (BYUI constraint.)
11. **Verify HITL is present** for any AI-mediated feedback or grading.

---

## Audit Tags Emitted

- `assessment_type` ∈ {`formative`, `summative`, `mixed`, `decorative`} — `decorative` flags an assessment that measures nothing actionable
- `assessment_alignment` ∈ {`clo_traced`, `orphaned`, `under-specified`}
- `formative_principles_flags` — list which of the seven principles fail
- `summative_recommendations_flags` — list which of the five recommendations fail
- `ai_agency` ∈ {`ai_dependent`, `scaffolded`, `student_owned`} (inherited from `inverted_blooms_knowledge.md`)
- `litmus_test_flags` — list of failed Litmus rows (e.g., `["reveal_learning_process", "test_transferability"]`); see *The Assessment Litmus Test*
- `litmus_pass_rate` — e.g., `"8/10"`; per-assessment summary
- `strategy_match` — the Strategies catalog entry that most closely fits this assessment, with `_unguarded` suffix when the strategy's named challenge isn't safeguarded (e.g., `process_oriented_unguarded`)
- `directives_honored` — subset of `{make_thinking_visible, value_struggle, verify_authorship, test_transferability}` from *The Path Forward*
- `grading_target` ∈ {`output_only`, `process_only`, `both`} — whether the rubric grades the artifact, the process, or both
- `assesses_struggle` — boolean; does the assessment reward growth/risk-taking, or only polished performance?
- `requires_transfer` — boolean; does the assessment require application to a novel context (not the one practiced in class)?

---

## References (full)

- Ali, Q. I. (2024). Towards more effective summative assessment in OBE: a new framework integrating direct measurements and technology. *Discover Education*, 3(1), 107.
- Bakula, N. (2010). The benefits of formative assessments for teaching and learning. *Science Scope*, 34(1).
- King, D. (2023). Assessing the benefits of online formative assessments on student performance. *Journal of Learning Development in Higher Education*, (27).
- Maki, P. L. (2002). Developing an assessment plan to learn about student learning. *Journal of Academic Librarianship*, 28(1-2), 8-13.
- McLaughlin, T., & Yan, Z. (2017). Diverse delivery methods and strong psychological benefits: A review of online formative assessment. *Journal of Computer Assisted Learning*, 33(6), 562-574.
- Nicol, D. J., & Macfarlane-Dick, D. (2007). Formative assessment and self-regulated learning: A model and seven principles of good feedback practice.
- Trumbull, E., & Lash, A. (2013). *Understanding formative assessment: Insights from learning theory and measurement theory.* San Francisco: WestEd.
- Hardman, P. (2024). *Redesigning Instruction & Assessment in the Age of AI*. drphilippahardman.substack.com.
- Yale Poorvu Center for Teaching and Learning. *Formative & Summative Assessments*. poorvucenter.yale.edu.
- Wiggins, G. *Understanding by Design* (10-min video, ASCD).
- Chaz Clark. *Designing Assessments — Testing the Foundation* (BYUI Architects of Learning week notes, 2026).

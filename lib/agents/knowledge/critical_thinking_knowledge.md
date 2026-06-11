# Critical Thinking & Critical Questioning — Auditor's & Grader's Reference

> Reference. The shared vocabulary canvas-toolbox uses when (a) **grading** student work against a rubric criterion that scores critical thinking, and (b) **auditing** whether an assignment is designed to *prompt* critical thinking in students. One file, two consumers.

**Sources (the synthesis):**
- **Facione, P. A. (1990)** — *Critical Thinking: A Statement of Expert Consensus for Purposes of Educational Assessment and Instruction (Delphi Report).* The canonical academic definition + the six core skills (interpretation, analysis, evaluation, inference, explanation, self-regulation). The Delphi was a 2-year expert-consensus process; this is the field's anchor definition.
- **AAC&U VALUE Rubric — Critical Thinking** (Association of American Colleges & Universities). Peer-reviewed, freely available, structured as 5 criteria × 4 performance levels (Benchmark 1 / Milestones 2-3 / Capstone 4). The most rubric-defensible single source — used here as the structural spine.
- **Paul-Elder framework** (Foundation for Critical Thinking) — 8 elements of reasoning + 9 intellectual standards. The most widely-adopted higher-ed framework; gives the "elements" + "questions to probe each element" backbone for the audit-side rubric language.
- **Bloom's revised taxonomy** (Anderson & Krathwohl 2001) — the upper tier (Analyze / Evaluate / Create) IS the critical-thinking cognitive demand. Already partly covered by [`bloom_verbs.py`](../../tools/bloom_verbs.py); this file adds the "what counts as evidence of each" layer.
- **Brookhart, S. M. (2010, 2nd ed. 2018)** — *How to Assess Higher-Order Thinking Skills in Your Classroom* (ASCD). Provides rubric language directly + the gap-signal patterns ("critical thinking criterion but recall-level demands").
- **Socratic questioning taxonomy** (compiled from Paul/Elder + Yale Poorvu + classical philosophy) — six question types: clarification, assumptions, reasons/evidence, viewpoints/perspectives, implications/consequences, questions about the question.
- **Toulmin, S. (1958/2003)** — *The Uses of Argument.* Cambridge UP. The claim / data / warrant / backing / qualifier / rebuttal model of argument structure. Many rubrics that score "reasoning quality" or "evidence chain" implicitly use Toulmin's vocabulary; this file makes that explicit (§4.5).
- **Willingham, D. T. (2007/2008)** — *"Critical Thinking: Why Is It So Hard to Teach?"* American Educator / American Federation of Teachers. The empirical case that CT is domain-specific (you can't think critically about chemistry without chemistry knowledge); transfer between domains is hard. Anchors this file's scope decision: dimensions + signals are domain-general, but a course's CT prompt needs domain knowledge as a precondition.
- **Bean, J. C. (2011, 2nd ed.)** — *Engaging Ideas: The Professor's Guide to Integrating Writing, Critical Thinking, and Active Learning in the Classroom.* Jossey-Bass. Widely-used writing-across-the-curriculum guide; specific prose-assignment patterns that prompt CT (skepticism prompts, cognitive dissonance, exploratory vs. thesis-based writing). Anchors §6 prose-assignment audit signals.

**Used by:**
- **Grader path** (when an instructor configures `policies.critical_thinking_mode: scored` in `config.outputs[].band_to_score`): the grader loads this file to score student work against the "critical thinking" rubric criterion with concrete observable evidence per band.
- **Audit path** ([`canvas_course_expert.md`](../canvas_course_expert.md), future `critical_thinking_audit.py`): when auditing a rubric that *claims* to score critical thinking, OR auditing an assignment prompt for whether it *prompts* critical thinking.
- [`canvas_grader.md`](../canvas_grader.md) — explicit consumer when `critical_thinking_mode` is scored.

**Companions:**
- [`bloom_verbs.py`](../../tools/bloom_verbs.py) — Bloom verb classifier (verb-level layer; this file adds the dimension-level layer above it).
- [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) — outcome well-formedness (do the CLOs target critical thinking?).
- [`rubrics_knowledge.md`](rubrics_knowledge.md) — rubric quality framework (does the rubric criterion target critical thinking observably?).
- [`assessments_knowledge.md`](assessments_knowledge.md) — formative vs. summative (critical thinking is typically a Capstone-level summative target).
- [`backwards_design_knowledge.md`](backwards_design_knowledge.md) — UbD 3-stage (the design framework that makes critical thinking land as a CLO).
- [`hattie_3phase_knowledge.md`](hattie_3phase_knowledge.md) — Surface → Deep → Transfer (critical thinking lives at Deep/Transfer).
- [`grader_knowledge.md`](grader_knowledge.md) — the grader pipeline that may consume this file when scoring.

**Scope:** what critical thinking IS, what counts as evidence of it in student work, what makes an assignment prompt it, and what makes a rubric criterion measure it observably. Out of scope: domain-specific critical thinking (we don't try to define "critical thinking in nursing" or "critical thinking in software design" — those are course-level applications of the general framework here).

**Provenance:** Each fact in the JSON companion's `facts[]` cites at least one of the named sources (Facione / AAC&U / Paul-Elder / Bloom revised / Brookhart / Socratic-taxonomy synthesis). No empirical citations.

_Last updated: 2026-06-10_ · _v0.1, untested. Promotes to v1.0 after the grader scores a real cohort against a critical-thinking criterion using this file's vocabulary, OR an audit tool flags a real assignment as critical-thinking-prompting / critical-thinking-absent using this file's signals. Not catalogued in [`knowledge/README.md`](README.md) until promotion._

---

## Why this file exists (dual-consumer framing)

Canvas-toolbox grades student work and audits course design. "Critical thinking" comes up in both contexts and means slightly different things:

| Consumer | Question | Uses this file for |
|---|---|---|
| **Grader** (when `critical_thinking_mode: scored`) | *Did this student demonstrate critical thinking on this submission?* | Observable evidence at each performance band; consistent vocabulary across the 3 graders so they agree on what they're scoring |
| **Auditor** (rubric audit, assignment-prompt audit) | *Is this rubric criterion actually measuring critical thinking? Will this assignment prompt students to demonstrate it?* | Design signals; gap detection ("rubric says critical thinking but criteria are recall"); audit tags |

Both consumers consult the same five-dimension spine (the AAC&U VALUE Rubric structure). The grader reads it as "what evidence to look for in student work"; the auditor reads it as "what the assignment must demand for evidence to be possible."

---

## 1 — What critical thinking IS (Facione Delphi definition)

> *"Purposeful, self-regulatory judgment which results in interpretation, analysis, evaluation, and inference, as well as explanation of the evidential, conceptual, methodological, criteriological, or contextual considerations upon which that judgment is based."*
> — Facione (1990), Delphi Report consensus definition.

Operationally, the six core skills (Facione + AAC&U):

| Skill | What it does | Observable verb-level signal |
|---|---|---|
| **Interpretation** | Comprehending and expressing the meaning of varied data, judgments, criteria, events | Categorizes / decodes / clarifies meaning |
| **Analysis** | Identifying intended and actual inferential relationships among statements, questions, concepts | Examines ideas / detects arguments / analyzes arguments |
| **Evaluation** | Assessing the credibility of claims and the strength of arguments | Assesses claims / assesses arguments / judges quality |
| **Inference** | Drawing reasonable conclusions and considering relevant information | Queries evidence / conjectures alternatives / draws conclusions |
| **Explanation** | Stating + justifying the reasoning supporting one's conclusion | States results / justifies procedures / presents arguments |
| **Self-regulation** | Self-consciously monitoring and correcting one's reasoning | Self-examines / self-corrects / reflects on reasoning |

### What critical thinking is NOT

Naming these explicitly because they show up in rubrics that *claim* to score critical thinking:

- **Recall + summarization.** Restating what a source said, even at length, is interpretation at best — not analysis/evaluation.
- **Personal opinion without grounding.** "I think X because I feel X" is not evaluation.
- **Comparison without criteria.** Listing differences is observation, not analysis. Comparing *against named criteria* is analysis.
- **Long-form prose.** Length is not depth. A 5-page summary is not more critical than a 1-page evaluation.
- **Citing many sources.** Source count is breadth, not depth of engagement.

---

## 2 — The five-dimension spine (AAC&U VALUE Rubric)

The structural backbone for both grading evidence and audit signals. Each dimension below is rated 1 (Benchmark) / 2-3 (Milestones) / 4 (Capstone). The descriptors are the AAC&U's; we re-cast them for the grader-vs-audit lens.

### Dimension 1 — Explanation of issues

| Level | Grader: evidence in student work | Audit: assignment must demand |
|---|---|---|
| **Capstone (4)** | Issue/problem stated, described, and clarified so understanding is unambiguous. **All** relevant information is included for full understanding. | Prompt asks the student to *articulate* the problem, not just solve a pre-stated one. Open-endedness lets the student frame. |
| **Milestone 3** | Issue stated; description leaves some terms undefined, ambiguities unexplored, or boundaries undetermined | Prompt allows for the issue to be partially mis-stated and still earn credit (compatibility with milestones) |
| **Milestone 2** | Issue stated but with omissions resulting in incomplete description | n/a (audit looks at top + bottom) |
| **Benchmark (1)** | Issue stated without clarification or description | Prompt accepts a stated-without-clarification framing (low ceiling) |

**Grader scoring shortcut:** the student's *opening framing* of the problem is the strongest signal for this dimension. If they re-state the prompt verbatim, that's Benchmark. If they re-frame, name the constraints, surface ambiguities — that's Capstone.

**Audit signal:** if the prompt provides the issue fully pre-framed ("explain how X causes Y"), the assignment caps at Milestone 2-3 for this dimension. Capstone-level performance requires the student to do at least some of the framing work themselves.

### Dimension 2 — Evidence (selecting + using sources)

| Level | Grader: evidence in student work | Audit: assignment must demand |
|---|---|---|
| **Capstone (4)** | Information is taken from source(s) with enough interpretation/evaluation to develop a comprehensive analysis or synthesis. Sources are questioned thoroughly. | Prompt requires sources to be *evaluated*, not just *cited*. Multiple sources from different perspectives. |
| **Milestone 3** | Information taken with enough interpretation to develop a coherent analysis or synthesis. Sources are questioned. | Prompt requires sources to be cited + critiqued, but allows single-perspective sourcing |
| **Milestone 2** | Information taken with some interpretation to develop a partial analysis. Sources are sometimes questioned. | n/a |
| **Benchmark (1)** | Information taken from source(s) without any interpretation/evaluation. Viewpoints of experts are taken as fact, without question. | Prompt accepts source listing / quotation without critique |

**Grader scoring shortcut:** count signals where the student **interrogates** a source — challenges a claim, names a limitation, contrasts an author against another, notes context/bias/methodology. Zero interrogation = Benchmark; multiple per source = Capstone.

**Audit signal:** if the prompt says "cite at least N sources" without saying *what to do with them*, that's a Benchmark-permitting assignment. Capstone requires explicit "evaluate / compare / critique."

### Dimension 3 — Influence of context and assumptions

| Level | Grader: evidence in student work | Audit: assignment must demand |
|---|---|---|
| **Capstone (4)** | Thoroughly analyzes own and others' assumptions; carefully evaluates the relevance of contexts. | Prompt requires explicit treatment of assumptions and/or context. |
| **Milestone 3** | Identifies own and others' assumptions; several relevant contexts considered. | Prompt asks for "what assumptions are we making?" or equivalent |
| **Milestone 2** | Questions some assumptions. Identifies several relevant contexts. | n/a |
| **Benchmark (1)** | Shows an emerging awareness of present assumptions (sometimes labels assertions as assumptions). Begins to identify some contexts. | Prompt doesn't require assumption-naming |

**Grader scoring shortcut:** does the student use the word "assume" / "assumption" / "context" / "given that" / "if we accept" — and does using it lead to evaluation, not just acknowledgement? Zero "assumption" language = Benchmark; explicit evaluation of named assumptions = Capstone.

**Audit signal:** if the prompt never asks "what are you assuming?" or "what context does this apply to?", the assignment caps below Capstone. The Paul-Elder element "assumptions" is the spine here — see Section 4.

### Dimension 4 — Student's position (perspective, thesis, hypothesis)

| Level | Grader: evidence in student work | Audit: assignment must demand |
|---|---|---|
| **Capstone (4)** | Specific position is imaginative; takes into account complexities of an issue; others' points of view acknowledged within position. | Prompt requires a defensible position + engagement with opposing views |
| **Milestone 3** | Specific position takes into account complexities. Others' points of view acknowledged. | Prompt requires position + counterargument |
| **Milestone 2** | Specific position presented. Acknowledges different sides of issue. | Prompt requires position-taking, allows minimal counterargument |
| **Benchmark (1)** | Specific position stated but is simplistic and obvious. | Prompt allows a single declarative position with no defense |

**Grader scoring shortcut:** does the student name an opposing or alternative position AND respond to it? Zero engagement with opposing views = Benchmark; substantive engagement = Capstone.

**Audit signal:** the prompt's verb matters. "State your opinion" = Benchmark ceiling. "Defend your position considering at least one alternative" = Capstone-permitting. "Compare and contrast X with Y" = position not required (different demand).

### Dimension 5 — Conclusions and related outcomes (implications, consequences)

| Level | Grader: evidence in student work | Audit: assignment must demand |
|---|---|---|
| **Capstone (4)** | Conclusions are logical and reflect informed evaluation. Related implications and consequences are presented clearly. Conclusion ties to evidence with priorities clear. | Prompt requires conclusions + named implications/consequences |
| **Milestone 3** | Conclusion logically tied to information (incl. opposing views); related outcomes (consequences and implications) identified clearly. | Prompt requires conclusions + at least one named implication |
| **Milestone 2** | Conclusion logically tied to information. | Prompt requires conclusion-stating |
| **Benchmark (1)** | Conclusion is inconsistently tied to some of the information discussed. Related outcomes oversimplified. | Prompt accepts a conclusion that doesn't follow from the analysis |

**Grader scoring shortcut:** can you trace the student's conclusion line by line through their evidence? If yes (and they also say "this implies X / leads to Y" beyond the conclusion itself), Capstone. If their conclusion appears unsupported or unconnected, Benchmark.

**Audit signal:** the assignment prompt's word for the final step matters. "State your conclusion" = at most Milestone 2. "Conclude AND identify the implications for [domain]" = Capstone-permitting.

---

## 3 — Critical questioning (the Socratic taxonomy)

Critical thinking is closely related to but distinct from critical *questioning*: the act of generating probing questions that drive analysis forward. Both this file's consumers care about it:

- **Grader:** does the student *ask* critical questions in their submission (especially in reflective / analytical / prose work)? Question-asking is one of the most reliable signals of high-level cognitive engagement.
- **Auditor:** does the assignment *require* students to generate questions, or does it only require them to answer ones?

### The six Socratic question types

| Type | Purpose | Example prompt patterns |
|---|---|---|
| **Clarification** | Surface unstated meaning, definitions | "What do you mean by X?" "Can you give an example?" "How does X relate to Y?" |
| **Probing assumptions** | Surface what's being taken as given | "What are you assuming?" "What if the opposite were true?" "How did you choose this assumption?" |
| **Probing reasons / evidence** | Surface the support behind a claim | "What evidence supports this?" "Is the source reliable?" "Could this be a coincidence?" |
| **Probing viewpoints / perspectives** | Surface alternative framings | "How might someone disagree?" "What's the counterargument?" "Whose interests are served by this framing?" |
| **Probing implications / consequences** | Surface what follows from the claim | "What follows from this?" "How does this affect [stakeholder]?" "What's the long-term consequence?" |
| **Questions about the question** | Surface meta-level concerns | "Is this the right question to ask?" "Why does this question matter?" "What does this question presuppose?" |

(Sources: synthesized from Paul-Elder, Yale Poorvu's Socratic-questioning resources, and classical Socratic-method taxonomies. The set varies slightly across sources; this is the operative common core.)

### Observable in student work (grader)

For a submission that *includes question-generation* as part of the task:

| Level | What you see |
|---|---|
| **Capstone** | Generates questions across multiple types; questions are non-obvious; the student then attempts to answer their own questions OR explicitly leaves them open as "questions for further investigation" |
| **Milestone 3** | Generates questions across 2-3 types; questions are substantive (not just clarification) |
| **Milestone 2** | Generates questions but mostly clarification or "is this right?" type |
| **Benchmark** | Generates no questions, or only questions that the prompt explicitly told them to ask |

### Observable in assignment prompts (audit)

| Demand level | What the prompt requires |
|---|---|
| **Capstone-permitting** | "Generate questions about X — your own, not from the readings. Then answer or rationalize leaving them open." |
| **Milestone-permitting** | "Pose 2-3 questions about X" (without specifying types or follow-through) |
| **Benchmark-only** | No question-generation requirement; OR the prompt provides the questions to answer |

---

## 4 — Paul-Elder framework (the elements + intellectual standards)

A complementary framing that some BYU-I rubrics use directly. The grader/auditor consults this when the rubric's language mirrors Paul-Elder's vocabulary.

### Eight elements of reasoning

Every act of reasoning involves these eight elements. The Paul-Elder framing is: **good critical thinking applies the nine intellectual standards (next section) to each of these eight elements.**

1. **Purpose** — What's the goal of this reasoning? Is the purpose clear?
2. **Question at issue** — What's the question being addressed? Is it the right question?
3. **Information** — What evidence is being used? Is it accurate, complete, relevant?
4. **Interpretation and inference** — What conclusions are being drawn? Do they follow?
5. **Concepts** — What ideas/theories/principles are being used? Are they used correctly?
6. **Assumptions** — What's being taken for granted? Are the assumptions justified?
7. **Point of view** — From what perspective is this reasoned? Whose interests are served?
8. **Implications and consequences** — What follows from this reasoning?

### Nine intellectual standards

These are the *quality criteria* applied to each element above.

| Standard | Test question |
|---|---|
| **Clarity** | Could you elaborate? Could you illustrate? Could you give an example? |
| **Accuracy** | Is that really true? How could we check that? |
| **Precision** | Could you be more specific? Could you give more details? |
| **Relevance** | How does that relate to the question? How does that help us with the issue? |
| **Depth** | What factors make this difficult? What complexities are we ignoring? |
| **Breadth** | Do we need to consider another point of view? Are there other ways to look at this? |
| **Logic** | Does this really make sense? Does that follow from what you said? |
| **Significance** | Which of these facts is most important? Is this the central idea? |
| **Fairness** | Are we considering all relevant viewpoints? Have we vested interests? |

### Toulmin's argument structure (when a student is *making an argument*)

Many CT-graded assignments ask students to *argue* — defend a position, make a case, justify a conclusion. The Toulmin model gives both grader and auditor a structural decomposition of what a good argument contains. Use this when the rubric criterion is "reasoning quality," "argumentation," or similar.

The six elements:

| Element | What it is | Grader: observable signal |
|---|---|---|
| **Claim** | The position/conclusion being defended | Stated explicitly, usually early; framed as a thesis, not a question |
| **Data / Grounds** | The evidence supporting the claim | Specific facts, sources, examples cited *and tied to* the claim |
| **Warrant** | The bridging principle linking data to claim — often implicit | Made *explicit* when the link is non-obvious; otherwise inferable |
| **Backing** | Support for the warrant itself | Reasoning for *why* the warrant holds; theory, prior cases, generalization |
| **Qualifier** | Confidence modifier ("usually," "in most cases," "with the caveat that") | Calibrates strength of claim to strength of evidence |
| **Rebuttal** | Acknowledgment of when/where the claim doesn't hold; engagement with counterarguments | Names exceptions; engages alternative positions before dismissing |

**Capstone-level argument** has all six elements present and operative. **Benchmark-level** has only claim + data, often without explicit warrant, no qualifier, no rebuttal.

**Audit signal:** if an assignment's rubric uses "argument" or "reasoning chain" language without naming any of these elements, it's vague (Brookhart anti-pattern). A Toulmin-aware rubric criterion might read: *"States a defensible claim, supports it with evidence specifically tied to the claim via an explicit or clearly-inferable warrant, qualifies the claim's scope, and engages at least one substantive counterargument with a rebuttal."*

### How Paul-Elder maps to AAC&U (the dual-framework bridge)

Operators using a Paul-Elder-styled rubric can map back to the 5-dimension spine:

| Paul-Elder element | AAC&U dimension |
|---|---|
| Purpose, Question at issue | Dimension 1 (Explanation of issues) |
| Information | Dimension 2 (Evidence) |
| Interpretation and inference, Concepts | Dimensions 4 + 5 (Position + Conclusions) |
| Assumptions, Point of view | Dimension 3 (Context and assumptions) |
| Implications and consequences | Dimension 5 (Conclusions and related outcomes) |
| (the standards) | Applied across all 5 dimensions |

---

## 5 — Rubric language patterns (for authoring + scoring against)

Rubric-author-friendly language for criteria that score critical thinking. Each line is a tested phrasing pattern; the grader looks for the corresponding evidence in student work.

### Author-side patterns (use these in rubrics)

| Want to score… | Don't write | Write |
|---|---|---|
| Analysis depth | "demonstrates critical thinking" | "identifies and evaluates assumptions underlying the argument" |
| Evidence quality | "uses good sources" | "evaluates source credibility, methodology, and context; cites limitations" |
| Position-defense | "states a position" | "defends a position, engaging with at least one substantive counterargument" |
| Reasoning quality | "uses logic" | "presents a chain of reasoning where each step follows from the evidence and the prior step" |
| Implications | "discusses impact" | "names specific implications and traces them to identifiable stakeholders or outcomes" |
| Self-regulation | "shows growth" | "identifies what they missed on a prior attempt and what changed in their reasoning" |

The right-hand column gives the GRADER concrete behaviors to score; the left-hand column is the vague-rubric anti-pattern Brookhart names.

### Grader-side patterns (what to look for in student work)

When scoring a criterion that *should* measure critical thinking, look for these explicit textual signals:

- **Hedging on certainty** ("this suggests" / "this might imply" / "with the caveat that" — the student is calibrating confidence to evidence quality, a Capstone signal)
- **Counter-construction** ("one could argue that..., but..." — engagement with opposing views)
- **Assumption-surfacing** ("if we accept that X, then..." / "this assumes..." — Dimension 3)
- **Methodological awareness** ("the source used method Y, which means..." — Dimension 2)
- **Question-generation** ("this raises the question of..." — see Section 3 on Socratic questioning)
- **Limitation-acknowledgement** ("this analysis is limited because..." — Capstone-level self-regulation)

Inverse signals (suggesting BENCHMARK at best):

- **Restating the prompt verbatim** as the analysis
- **Asserting without warrant** ("clearly," "obviously," "everyone knows")
- **Source-as-authority** ("the article says X, so X")
- **Position-without-defense** ("I think X" with no reasoning chain)

---

## 6 — Gap signals (what to flag during an audit)

Audit-side red flags — concrete patterns the auditor uses to identify "critical thinking is named but not actually demanded / measured."

### Rubric-audit gap signals

| Signal | What it means |
|---|---|
| Criterion title is "Critical Thinking" but the rating descriptors use recall verbs (defines / lists / restates) | Mislabeled criterion — measures recall, not critical thinking |
| Criterion uses bare adjectives ("excellent critical thinking," "weak critical thinking") with no observable behavior | Vague rubric — graders default to subjective judgment; inter-rater reliability collapses |
| Highest-band descriptor is "demonstrates critical thinking" verbatim — no decomposition | Tautology — what does demonstrating actually look like? Brookhart's #1 gap pattern |
| Lowest-band descriptor is "does not demonstrate critical thinking" (the negative tautology) | Same as above, inverse |
| Critical thinking criterion is worth <10% of grade | Rubric-incentive mismatch — students rationally optimize away from it |
| No critical-thinking criterion at all, but the CLO claims to develop critical thinking | Alignment break ([`course_alignment_audit.py`](../../tools/course_alignment_audit.py) territory) |
| Each band's descriptor is structurally the same with just severity adjectives swapped ("mostly demonstrates" / "somewhat demonstrates" / "doesn't demonstrate") | Adjective-ladder anti-pattern — no behavioral differentiation between bands |

### Assignment-prompt audit gap signals

| Signal | What it means |
|---|---|
| Prompt's primary verb is at Bloom levels 1-3 (remember / understand / apply) | Lower-Bloom prompt; critical thinking cannot show up at the prompted level |
| Prompt provides the issue, the position to take, AND the evidence to use | All work pre-framed; student executes, doesn't think critically |
| Prompt asks "what is X" / "summarize Y" / "list Z" | Recall-only; no critical thinking possible |
| Prompt has a single correct answer | If there's a key, there's not much room for evaluation/inference |
| Prompt is "reflect on X" with no anchoring questions | Reflection without structure → free-association, not analysis |
| Prompt assigns critical-thinking work but provides only Benchmark-level rubric criteria | The work is asked for but won't be measured |
| No counterargument / alternative perspective requirement anywhere in the prompt | Dimension 4 ceiling — Capstone unreachable |
| No "what are you assuming?" / "what context?" prompt | Dimension 3 ceiling — Capstone unreachable |
| No "what's the implication?" / "what follows?" prompt | Dimension 5 ceiling — Capstone unreachable |

### Prose-assignment-specific signals (Bean, *Engaging Ideas*)

For writing assignments specifically — where most CT-graded work lives in higher ed:

| Bean pattern | Prompts CT? | Why |
|---|---|---|
| **Skepticism prompt** — "Argue against the obvious answer" or "What's wrong with the standard view?" | ✅ Strongly prompts | Forces analysis of assumptions + alternative perspectives (Dim 3 + Dim 4) |
| **Cognitive-dissonance prompt** — present two conflicting sources, ask the student to resolve | ✅ Strongly prompts | Forces evaluation + position-taking + integration (Dim 2 + Dim 4) |
| **Microtheme** — short focused writing tied to a specific question (1-2 paragraphs) | ✅ Often prompts | Concision forces the student to make choices about what to include — analysis under constraint |
| **Exploratory writing** ("freewrite about X for 10 min") | ⚠ Neutral | Develops reasoning *process*; doesn't on its own require CT product. Best as scaffolding, not assessment. |
| **Thesis-based writing** ("argue for/against X") | ✅ Often prompts | If counterargument is required (Dim 4 ceiling check) |
| **Summary / précis assignment** | ❌ Suppresses | Recall + condensation; no analysis demanded |
| **"Reflect on your learning"** with no anchoring question | ❌ Often suppresses | Free-association without structure; no CT signal possible |
| **Reading response with structured questions** ("identify the author's main claim; identify one assumption; identify one weakness") | ✅ Prompts | Toulmin / Paul-Elder elements baked into the prompt |

Bean's broader argument: **prompting CT in writing requires the assignment to ask students to do something *with* what they read — not just read or summarize it.** The verb structure of the prompt is the single best audit signal.

---

## 7 — Audit tags

For audit tool output. Two tags surface from this knowledge file:

### `critical_thinking_prompt`

What an *assignment prompt* (not the student's work) demands. Values:

- **`prompts`** — The prompt actively requires critical thinking. At least one of: assumption-naming required; counterargument required; implication-naming required; position-defense required; source-evaluation (not just citing) required. Bloom verb level ≥ 4 (Analyze) on the primary task.
- **`neutral`** — The prompt doesn't actively prevent critical thinking, but doesn't require it either. Student could earn full credit at Apply level. Most "explain your answer" prompts land here.
- **`suppresses`** — The prompt requires recall or single-correct-answer work. Critical thinking would be off-task. "Define X," "list Y," "calculate Z."

### `critical_thinking_demand_level`

If `critical_thinking_prompt` is `prompts`, the ceiling of demand:

- **`capstone`** — All 5 AAC&U dimensions are demanded at the highest level. Rare; usually capstone projects, theses, defenses.
- **`milestone3`** — 3-4 dimensions at Capstone-permitting level; 1-2 at Milestone-3.
- **`milestone2`** — Most dimensions at Milestone-2 level; some Capstone-permitting.
- **`benchmark`** — Prompt requires critical thinking but caps at Benchmark level on all dimensions (rare; usually indicates a poorly-designed assignment).

These tags slot into the audit tag stack alongside `cognitive_load_type`, `learning_domain`, `hattie_phase`, etc. (see `knowledge/README.md` § Tag stack).

---

## 8 — Cross-walk to other knowledge files

| When you're asking… | Pair this file with |
|---|---|
| "Does the CLO target critical thinking?" | [`bloom_verbs.py`](../../tools/bloom_verbs.py) (verb level) + [`outcomes_quality_knowledge.md`](outcomes_quality_knowledge.md) (CLO well-formedness) |
| "Does the rubric criterion measure critical thinking observably?" | [`rubrics_knowledge.md`](rubrics_knowledge.md) (rubric quality) + this file (what counts as observable evidence) |
| "Does the assignment prompt critical thinking?" | This file (Section 6 gap signals) + [`assessments_knowledge.md`](assessments_knowledge.md) (formative vs summative — critical thinking is typically summative) |
| "Did the student demonstrate critical thinking?" | This file (Sections 2 + 3 grader columns) + [`grader_knowledge.md`](grader_knowledge.md) (grading pipeline + voice) |
| "Is the course design building toward critical thinking?" | This file + [`hattie_3phase_knowledge.md`](hattie_3phase_knowledge.md) (critical thinking lives at Deep/Transfer) + [`backwards_design_knowledge.md`](backwards_design_knowledge.md) (UbD designs backward from CT outcomes) |

---

## Operator notes

- **Critical thinking is taught + assessed; it's not a "give them a hard prompt" matter.** If the course's earlier scaffolding doesn't develop the skills (Hattie Surface → Deep), Capstone-level critical thinking is unreachable. An assignment that prompts critical thinking in week 14 of a course that did recall in weeks 1-13 will produce frustrated students, not critical thinkers.
- **Willingham's caveat: CT is domain-specific.** Willingham (2007/2008) makes the empirical case that you cannot think critically about chemistry without chemistry knowledge — background knowledge is a *precondition* for CT in any domain, not a separable layer. Transfer between domains is hard. Audit implication: a course that prompts CT before the domain content is in place will produce surface-level reasoning even from strong students. The dimensions + signals in this file are *domain-general*; the instructor's rubric applies them to a specific domain, and the course's content scaffolding must provide the knowledge base CT operates on.
- **Inter-rater reliability collapses on vague critical-thinking rubrics.** The grader's `consensus_three_graders` (`grader_knowledge.md` §4) produces high spread when the criterion is "demonstrates critical thinking" with no observable behavior. The fix is rubric-side (use Brookhart's language), not grader-side.
- **Critical questioning is a separable, often-overlooked skill.** If you want students to *ask* critical questions (not just answer them), the assignment has to require it. Section 3's audit signals catch the gap.
- **Domain-specific critical thinking** is the next layer down — what critical thinking looks like in your discipline. This file deliberately doesn't go there. The dimensions + signals here are domain-general; the instructor's rubric should apply them to the discipline.

---

## What this knowledge file does NOT cover

- **Generic "higher-order thinking"** without a critical-thinking-specific lens — Brookhart's broader book covers it, but this file is scoped to CT specifically.
- **Creativity / creative thinking** — related but distinct (creativity = generating novel options; CT = evaluating options). Could be a sibling knowledge file when needed.
- **Problem-solving** as a separate skill — overlaps but is process-oriented in ways CT isn't.
- **Metacognition** beyond self-regulation — also overlaps but Schraw/Pintrich/Zimmerman are the canonical sources, not Facione/Paul-Elder.

These could be future companions if a consuming audit/grader surfaces the need.

_Last updated: 2026-06-10_ · _v0.1, untested per the canvas-toolbox 0.x convention. Promotes when (a) the grader scores a real cohort against a critical-thinking criterion using this file, OR (b) an audit tool flags a real assignment as prompts / neutral / suppresses using this file's signals._

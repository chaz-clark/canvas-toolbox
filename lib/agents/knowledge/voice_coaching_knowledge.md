---
name: voice_coaching_knowledge
version: "1.0"
last_updated: 2026-06-25
description: Upstream coaching layer for the per-instructor voice file — research grounding for effective feedback, the voice-preservation contract, and first-time voice articulation.
skill_type: knowledge
shape: reference   # settled reference; flip to identity later if coaching-principle issues surface
scope: "The WHAT/HOW boundary, research-grounded WHAT criteria, voice dimensions faculty position on, and the articulation interview for new faculty. Out of scope: comment structure + edit roundtrip (grader_voice_knowledge)."
consumed_by:
  - canvas_grader.md
companion_json_deprecated: "2026-07-16 - authored as YAML frontmatter (JSON purge convention)"
provenance:
  sources:
    - "8 pedagogical frameworks (Hattie/Wiggins/Dweck/Brookhart/CLT/warm-demander/Black-Wiliam/AI-voice-preservation); handoffs/2026-06-25_voice-coaching-research.md"
runtime_strategy: read_at_runtime
metadata: { knowledge_id: voice_coaching_knowledge }
---

# Voice Coaching — Upstream Scaffolding for the Per-Instructor Voice File

> Reference. **Companion to [`grader_voice_knowledge.md`](grader_voice_knowledge.md).** That file is the structural framework + the per-instructor voice file CONTRACT. This file is the **upstream coaching layer** — research grounding for what makes feedback effective, voice-preservation contract that protects faculty identity, and scaffolding for first-time voice articulation BEFORE the existing edit roundtrip can refine it.

**Used by:** [`canvas_grader.md`](../canvas_grader.md), every consumer of [`grader_knowledge.md`](grader_knowledge.md), the agent grading any LLM-comment cohort.

**Companions:**
- [`grader_voice_knowledge.md`](grader_voice_knowledge.md) — the structural framework + edit roundtrip + per-instructor file contract
- [`grader_knowledge.md §10`](grader_knowledge.md) — the push pipeline + safety gates the voice rides on top of
- [`grader_setup_knowledge.md`](grader_setup_knowledge.md) — the interview that anchors a per-assignment config

**Scope:** the WHAT/HOW boundary, research-grounded WHAT criteria, the voice dimensions faculty position themselves on, and the articulation interview for new faculty whose voice isn't yet articulated. Out of scope: structural rules for the comment itself (lives in `grader_voice_knowledge.md`), edit roundtrip mechanics (same), rubric design (`grader_knowledge.md §11`).

_Created: 2026-06-25_ · _**v1.0**, research-grounded across 8 pedagogical frameworks (Hattie/Wiggins/Dweck/Brookhart/CLT/warm-demander/Black-Wiliam/AI-voice-preservation), validated against DS 250 + DS 460 voice artifacts. Audit trail: `handoffs/2026-06-25_voice-coaching-research.md`._

---

## The contract — your voice is the asset

Before anything else, the rule that anchors this file:

> **The AI does NOT replace your voice. It strengthens what your voice already does.**

The literature on AI-mediated feedback consistently identifies VOICE FIDELITY as the largest barrier to faculty adoption. Faculty trust an AI to assist with grading when they recognize their own voice in the output; they don't trust it when the output flattens them into generic prose. Students share this preference — they want to know their professor is reading their work, want to see the professor's jokes and idioms, want the feedback to sound like a real person they know.

So the coaching file does two things, and only those two things:

1. **Protect the HOW** — the specific words, length norms, formality register, pet phrases, encouragement style, cultural register, and pedagogical positioning that makes the faculty's grading recognizably theirs
2. **Strengthen the WHAT** — the underlying cognitive content (does the feedback answer the right questions? is it specific to evidence? is it scoped to working-memory capacity? is it forward-looking?)

Everything below splits into those two columns. If you find yourself reading a section and thinking "but this would change how my professor SOUNDS" — that's a signal you've crossed from WHAT into HOW. Push back.

---

## 1 — The WHAT/HOW split, named

Most feedback literature conflates two dimensions. They're separable, and the separation is what makes coaching faculty without flattening them possible.

| Dimension | What it is | Universal or per-instructor? |
|---|---|---|
| **WHAT** the feedback contains | Cognitive content — does it hit the right questions? Specific to evidence? Forward-looking? Scoped to working-memory capacity? | Universal — derived from pedagogical research |
| **HOW** the feedback says it | Warmth, length, formality, directness, pet phrases, encouragement style, cultural register | Per-instructor — derived from teaching identity |

**The 80/20 application** (pairs with the canvas-toolbox-wide pattern documented in `grader_knowledge.md §4`):

- **80%** — this coaching file applies universal WHAT-effectiveness criteria to whatever voice the faculty has. Same coaching file across all instructors.
- **20%** — the existing edit roundtrip (`grader_voice_knowledge.md §4`) tunes per-instructor HOW. Different voice file per instructor.

When you read this file, hold the boundary in mind: every WHAT criterion is checkable on a draft comment without changing voice. Every HOW dimension is a position the faculty chooses; the file makes the dimensions visible, not the position prescribed.

---

## 2 — The WHAT — universal effectiveness criteria (4-point check)

Every feedback comment the agent drafts should pass these four checks. The checks are content-only; passing them doesn't constrain the voice.

### Check 1 — Does it answer "Where am I going?"

The student has to know what the work was meant to demonstrate. In the structured comment (`grader_voice_knowledge.md §1`), this lives in the **specific strength sentence** — naming what was achieved implicitly names what was asked.

**Why this matters:** Hattie & Timperley's three-question framework (the most-replicated feedback model in education research, 2007 onward) identifies this as "Feed-up." Without it, every coaching point reads as criticism — the student has nothing to anchor against.

**The check:** does the comment open with a specific evidence-grounded strength sentence? Or does it open with a generic "Nice work" / "Strong submission" that could apply to any cohort?

**Pass example** (drawn from DS 250 patterns): `Overall: Complete. Your join captured the unique buildings correctly + your `top_k` call narrowed cleanly to the right slice.`

**Fail example:** `Overall: Complete. Good work on this assignment.` — generic; no anchor.

### Check 2 — Does it answer "How am I going?"

Coaching has to be anchored to specific evidence in THIS submission, not generic. The cognitive content here is HIGH; the voice content is LOW (the SHAPE of "anchored to evidence" is universal, but the WORDS faculty use are theirs).

**Why this matters:** Wiggins's seven keys (ASCD 2012) identifies "tangible and transparent" + "user-friendly" as core criteria. Brookhart's effective-feedback framework (2017) puts **specificity** as a content element. The student has to be able to see WHAT in the work the feedback is reacting to.

**The check:** does each coaching paragraph name a specific evidence noun from the work (a variable, a function call, a structural choice, a missing element)? Or does it use general nouns ("the data," "the analysis")?

**Pass example:** `In Q4, the chart's y-axis runs 0-100 instead of 0-10 — the magnitude scale obscures the within-cohort variance the rubric asks you to surface.` — names Q4, names the y-axis, names the variance the rubric asks for.

**Fail example:** `Your visualization could be improved.` — no anchor; student can't act on it.

### Check 3 — Does it answer "Where to next?"

Feedback that names a problem without naming the action to take is diagnosis without prescription. The Hattie/Black-Wiliam frameworks call this "closing the gap" — there must be enough information in the feedback that the student can take action.

**Why this matters:** This is where Wiggins's "actionable" key + Black-Wiliam's closing-the-gap criterion both land. Feedback that names a gap without a way to close it is incomplete by research consensus. In `grader_voice_knowledge.md §1` this is the **habit-to-build closing paragraph**.

**The check:** does the comment end with a concrete next action (a habit, a question to investigate, a tool to try, a pattern to practice)? Or does it end with a generic "Hope this helps" / "Keep up the good work"?

**Pass example:** `For next time, ask yourself before every chart: 'what's the variance in the data?' Let the y-axis follow that, not the data's possible range.`

**Fail example:** `Keep working on visualizations.` — vague; no action to take.

### Check 4 — Is it scoped to 1-2 priority items?

The cognitive-load implications of working memory are blunt. Sweller's Cognitive Load Theory (1988, replicated extensively): working memory handles 2-4 chunks of concurrent information. Feedback with 5+ coaching points loses ~70% of recall past point 2.

**Why this matters:** Faculty have many things they could say; the highest-leverage 1-2 things are what the student will actually use. The other 3+ are noise that displaces the important signal.

**The check:** does the comment have 1-2 coaching paragraphs (plus the strength + habit-to-build)? Or does it have 4+ coaching paragraphs?

**If there are 3+ things you want to say:** pick the highest-leverage 1-2. The others either (a) wait for the next submission, or (b) become a meta-comment for the instructor only ("noted these for the next assignment").

This check is the one most likely to require operator override — sometimes a submission has 3+ critical issues that all need surfacing for safety/integrity reasons. Override is fine; the default is 1-2.

### The four checks in summary

If a draft comment passes all four, the WHAT is sound. The voice (HOW) below can then carry the comment in whatever register the faculty prefers. If a draft FAILS one of the four, the agent fixes the failure WITHOUT changing the surrounding voice — adds the strength sentence, anchors a vague paragraph to specific evidence, adds the next-action closing, picks the 1-2 highest-leverage points from a list of 5.

---

## 3 — The HOW — voice dimensions (8 axes)

Each axis is a position the faculty occupies. There is no "right" position — the literature endorses the warm-demander combination (high warmth + high standards) but doesn't prescribe a single voice. The coaching file makes the dimensions visible so faculty can position themselves consciously.

This expands the 5-dial system in `grader_voice_knowledge.md §3` with three new axes informed by the literature.

| # | Dimension | Low end | High end | Where in literature |
|---|---|---|---|---|
| 1 | **Warmth** | Clinical / procedural | Warm / personal / "I" | Pre-existing; warm-demander pedagogy |
| 2 | **Directness** | Hedged / "you might consider..." | Plain / "do X" | Pre-existing |
| 3 | **Technical density** | Approachable / metaphor-first | Vocabulary-dense | Pre-existing |
| 4 | **Encouragement frequency** | Once per comment | Multiple per comment | Pre-existing |
| 5 | **Brevity** | 2 short paragraphs | 5+ paragraphs | Pre-existing; CLT implications |
| 6 | **Praise focus** (NEW) | Process-anchored ("you worked hard on X") | Ability-anchored ("you clearly understand X") | Dweck on process vs ability praise |
| 7 | **Question style** (NEW) | Direct prescription ("change Y to Z") | Socratic question ("what would happen if Y were Z?") | Brookhart on function (descriptive vs evaluative) |
| 8 | **Cultural register** (NEW) | Apprentice-supportive ("here's how I'd think about this") | Peer-professional ("you and I both know this isn't tight yet") | Warm-demander; DS 460's "consulting engagement" framing |

### Notes on the new axes

**Axis 6 — Praise focus.** Dweck's research strongly endorses process praise as growth-mindset-promoting and ability praise as fixed-mindset-risking. But: this is a long-run dimension. One ability-anchored comment in an otherwise process-rich corpus doesn't damage anything. Faculty whose voice naturally includes ability acknowledgment ("you clearly understand this material") aren't doing harm — they're recognizing pattern. Position consciously: if your voice drifts toward ability praise on every submission, that's worth knowing.

**Axis 7 — Question style.** Some faculty are direct prescribers ("change your aggregation from sum to count_distinct"); others are Socratic ("what does each row in your aggregation represent?"). Both can land the same insight. Socratic is more cognitively demanding for the student but builds stronger transfer; direct is faster but builds less reasoning capacity. Voice choice; not a verdict.

**Axis 8 — Cultural register.** The warm-demander pedagogy literature highlights that faculty register choice signals relationship: apprentice-supportive ("here's how I'd think about this") frames the student as learner-to-be-coached; peer-professional ("you and I both know this isn't tight yet") frames the student as colleague-in-training. DS 460's "consulting engagement" framing is firmly peer-professional. Both work; the register depends on course context + faculty teaching identity.

### Worked examples — the same WHAT, different HOWs

Same submission, same four-check passing, different voice positions:

**Voice A — warm + brief + Socratic + apprentice-supportive:**

> Overall: Solid. Your join captured the unique buildings — that was the move I was hoping to see.
>
> Coaching Tips:
>
> In Q4, your chart's y-axis runs 0-100 even though the values cluster around 10-30. What's the smallest range that would still show the within-cohort variance you're trying to make visible?
>
> For next time: before every chart, ask yourself "what's the variance in the data?" and let the y-axis follow that. Small habit, big payoff.

**Voice B — direct + technical + prescriptive + peer-professional:**

> Overall: Solid. The `unique(building_id)` join is clean.
>
> Coaching Tips:
>
> Q4: drop the y-axis from 0-100 to 0-30. The current range washes out the variance the rubric asks you to surface. `ylim=(0, 30)` in your matplotlib call, or `scale_y_continuous(limits=c(0,30))` if you're using ggplot.
>
> Habit: y-axis = variance range, not value range. Set this every chart.

Both pass the four WHAT checks. Both have specific strength (Q1 + the join). Both have specific evidence-grounded coaching (Q4 + the y-axis). Both have next-action habit-to-build. Both are scoped to 1 priority item. **The WHAT is identical.** The HOW is wildly different. Both are valid. The faculty's voice file determines which one the agent produces.

This is what voice preservation looks like in practice.

---

## 4 — The 80/20 boundary, made visible

What this coaching file CHANGES, and what it explicitly DOES NOT:

| Changes (WHAT) | Doesn't change (HOW) |
|---|---|
| Whether feedback hits the Hattie three questions (strength + coaching + habit) | The specific words the faculty uses |
| Specificity to evidence (no generic "good work") | The faculty's pet phrases ("nice tool reach" / "this is tight") |
| 1-2 priority items, not 5+ | Length norms (some faculty are brief; others write a paragraph per point) |
| Forward-looking closing (habit, not recap) | Tone register (formal vs casual; idiomatic vs literal) |
| `Overall: <Tier>` → strength → Coaching Tips → habit-to-build structure | Praise frequency and style (process / ability / specific / overall) |
| No data values; no AI tells; no meta-scaffolding | Cultural register (apprentice / peer / professional / colleague) |
| Cognitive-load discipline (one idea per paragraph) | Punctuation conventions, sentence-length rhythm, paragraph-break choices |

If the agent produces a draft and the operator says "this doesn't sound like me" — the operator is identifying a HOW mismatch. Fix via the per-instructor voice file + edit roundtrip; do not change the WHAT discipline.

If the operator says "this is sound but missing the strength sentence" — the operator is identifying a WHAT failure. Fix in the coaching layer (here); not in the voice file.

---

## 5 — First-time voice articulation (the interview)

The existing edit roundtrip (`grader_voice_knowledge.md §4`) assumes the faculty has SOME voice the agent can learn from. For new faculty / TAs / instructors-in-training, that assumption fails — they need scaffolding to ARTICULATE their voice before the roundtrip can refine it.

The articulation interview takes ~30 minutes per faculty member and produces enough material that the existing edit roundtrip can refine in 1-2 cohorts instead of 4-5.

### The five questions

Run in order. Each question's answer informs one or more voice dimensions from Section 3.

**Q1.** *"Show me 3 comments you wrote on the same rubric tier (e.g. three "B" comments, or three "Meets" comments, or three "Complete" comments). What's the shared thread?"*

What you're looking for: the faculty's recurring structural moves. Do all three open with a strength sentence? Are they all the same length? Do they all end with an action? The patterns the faculty produces consistently are their voice signature.

Maps to: dimensions 1, 4, 5 (warmth, encouragement frequency, brevity).

**Q2.** *"What's the LAST word you'd want to read in feedback from a colleague? Why?"*

What you're looking for: the AI tells the faculty actively dislikes. Common answers: "leveraging" / "robust" / "comprehensive" / "delve into" / "unpack" / "circling back." Whatever they name goes into the per-instructor banned-terms list.

Maps to: the banned-pattern catalog (`grader_voice_knowledge.md §5`).

**Q3.** *"When a student struggles on something, which is more your instinct: ask them a question that helps them see it, or tell them what's wrong?"*

What you're looking for: the question-style dimension. Socratic-tending faculty give different feedback than prescription-tending faculty; both work, both are valid voices.

Maps to: dimension 7 (question style).

**Q4.** *"When a student succeeds, which is more your instinct: name what they did right specifically, or affirm them as a learner?"*

What you're looking for: the praise-focus dimension. Specific-praisers ("nice use of `count_distinct`") differ from affirming-praisers ("you're clearly catching on to this"). Dweck research says specific is growth-promoting; either way, the answer here positions the faculty consciously.

Maps to: dimension 6 (praise focus).

**Q5.** *"If a student appealed a grade and you had to defend the comment, what's the structure of your defense?"*

What you're looking for: how the faculty THINKS about a comment when they have to defend it. Faculty who say "the comment names the evidence in the work" are tangible/transparent (Wiggins). Faculty who say "the comment connects to the rubric" are goal-referenced. Faculty who say "the comment offers a specific next step" are forward-looking. The answer tells you which Hattie/Wiggins criteria the faculty already operationalizes naturally.

Maps to: which of the four WHAT checks (Section 2) the faculty already passes by instinct.

### The output

After the 30-minute interview, the operator + faculty draft a `student_feedback_voice_<instructor>.md` per the contract in `grader_voice_knowledge.md §9`. The draft has:

- A position on each of the 8 dimensions in Section 3
- A list of 5-10 banned-for-them phrases (their own AI tells from Q2)
- An opener wording (from the patterns in Q1)
- A characteristic coaching-paragraph opener (or "vary, no template" — also valid)
- A habit-to-build closing template (from Q5 — the structure they defend with)

The draft is a STARTING POINT. The edit roundtrip (`grader_voice_knowledge.md §4`) then refines it across the calibration cohort + first real cohort.

---

## 6 — Edge cases — when voice and effectiveness conflict

Rare but real. Three scenarios where a faculty's natural voice pushes against the WHAT-effectiveness criteria. The pattern across all three: **surface to the operator; cite the research; let the human decide.** Don't override unilaterally — that violates the voice-preservation contract.

### Scenario A — voice includes harsh comparative feedback

> "Most students get this on the first try; you didn't."

Growth-mindset research (Dweck and successors) argues comparative feedback is counterproductive — it shifts the student's frame from "what can I improve?" to "am I in the bottom half?". The student's effort drops; the fixed-mindset risk spikes.

**The agent's move:** flag during the LLM-comment draft. Suggest replacing with a non-comparative version. Cite the research. Let the operator decide whether to accept or override.

**Example flag:**
> `⚠️ [voice-warn] The phrase 'most students get this on the first try; you didn't' is comparative — growth-mindset research argues this reduces student effort. Suggested alternative: 'This is one of the harder corners of the rubric. Here's what to check.' Operator may keep original if intentional.`

### Scenario B — voice never affirms anything

Faculty whose voice is pure critique — never a strength sentence, never specific positive recognition. Hattie's research on the three questions argues this fails Check 1 (Where am I going?) — students have nothing to anchor against; every comment reads as attack; defensive responses dominate.

**The agent's move:** when drafting a comment for a strong submission, surface the absence. Don't fabricate a strength sentence to fit the structure — that would be patronizing. Instead surface: "this submission earned a high band; no strength sentence in the corpus suggests one. Suggest the operator add one specific observation about what worked."

### Scenario C — voice is so long students disengage

Faculty whose voice runs 7+ paragraphs per comment. Cognitive Load Theory implication: students lose ~70% of feedback past point 2. The faculty is investing effort the students aren't receiving.

**The agent's move:** surface during draft review. "This draft has 6 coaching paragraphs; CLT research suggests 1-2 are absorbed and 4+ are lost. Suggest the operator pick the highest-leverage 1-2 + note the others in a private journal for next-assignment teaching." Let the operator override if they have evidence their students DO read fully.

### The pattern

In all three scenarios, the agent surfaces the tension to the operator with a research citation. The operator's voice is never overridden unilaterally. The agent's job is to make the trade-off visible, not to win the argument. Some faculty intentionally hold the position the research argues against (an experienced instructor who knows their students respond well to direct comparative feedback in a specific course context, for example) — that override is valid. The system honors it.

---

## 7 — Cross-walk to the existing voice infrastructure

This file is the upstream coaching layer. Where everything else lives:

| Concept | This file (`voice_coaching_knowledge.md`) | `grader_voice_knowledge.md` | `grader_setup_knowledge.md` | `grader_knowledge.md` |
|---|---|---|---|---|
| WHAT/HOW split | §1 — defines the split | (assumes WHAT) | (operationalizes WHAT) | (assumes WHAT) |
| Universal WHAT criteria | §2 — research-grounded 4-point check | (implicit in structure) | — | — |
| Voice dimensions (8) | §3 — full catalog | §3 — 5-dial subset | — | — |
| 80/20 boundary | §4 — explicit | (implicit) | — | (broader 80/20 in §4) |
| First-time articulation | §5 — interview pattern | (assumes voice exists) | (interview baselines per-assignment config; not voice) | — |
| Edge cases / voice vs effectiveness | §6 — surface-don't-override | — | — | — |
| Comment structure (Overall / strength / Coaching Tips / habit) | (references) | §1 — defines | — | (references in §10) |
| Banned-pattern catalog | §5 (Q2 informs per-instructor list) | §5 — default + per-instructor | — | — |
| Edit roundtrip | (assumed) | §4 — full protocol | — | — |
| Per-instructor file contract | (informs) | §9 — full contract | (interview produces a config; voice file is separate) | — |
| Push gate / FERPA | — | (references) | — | §10 (and §1 for FERPA) |

This coaching file doesn't replace any of those. It sits upstream, scaffolding the first-time articulation + research-grounding the WHAT criteria + naming the boundary that protects voice.

---

## 8 — The research grounding (one-line citations)

The coaching file's WHAT criteria + voice dimensions are grounded in the following bodies of work:

- **Hattie & Timperley** (2007), "The Power of Feedback" — three feedback questions (Where am I? How am I? Where next?)
- **Wiggins** (2012), "Seven Keys to Effective Feedback" — goal-referenced, tangible, actionable, user-friendly, timely, ongoing, consistent
- **Dweck** (1998-ongoing) — process vs ability praise as a long-run dimension
- **Brookhart** (2008/2017), *How to Give Effective Feedback to Your Students* — content + strategy element framework
- **Sweller / Cognitive Load Theory** (1988-ongoing) — working memory limits → 1-2 priority items rule
- **Hammond** (2014), *Culturally Responsive Teaching and the Brain* — warm-demander pedagogy (high expectations + high warmth)
- **Black & Wiliam** (1998 / 2009), "Inside the Black Box" + *Assessment for Learning* — closing-the-gap formative feedback
- **AI voice preservation literature** (2025-2026, multiple papers) — voice fidelity as the AI-grading adoption barrier; teacher-as-collaborator framing

Full audit trail with quotes + analysis lives in `handoffs/2026-06-25_voice-coaching-research.md` (gitignored; available locally).

---

## Quick-reference: the voice coaching rules in one paragraph

The AI does NOT replace the faculty's voice; it strengthens what their voice already does — separate the WHAT (universal effectiveness: hits the three Hattie questions, anchored to specific evidence, scoped to 1-2 priority items, forward-looking) from the HOW (per-instructor voice: warmth, directness, technical density, encouragement frequency, brevity, praise focus, question style, cultural register); apply the 80/20 — this coaching file delivers the 80% via universal WHAT criteria, the existing edit roundtrip tunes the per-instructor 20%; for new faculty without a voice file, run the 5-question articulation interview to scaffold a starting draft before the roundtrip refines it; when voice and effectiveness conflict (harsh comparison, no affirmation, runaway length), surface the tension with research citation and let the operator decide — never override the voice unilaterally.

# Hattie's 3-Phase Learning Model — Knowledge Reference

Source: Hattie, J. (2009). *Visible Learning*. Routledge.
Used by: `canvas_course_expert.md` (audit framework), `canvas_course_expert.json` (hattie_phase field on each audit rule)
Companion: [`cognitive_load_theory_knowledge.md`](cognitive_load_theory_knowledge.md) — Hattie sequences learning across phases; CLT addresses the working-memory mechanics within each phase.

_Last updated: 2026-05-26 (added Deep-phase group-work quality sub-check — PTC gap-audit)_

---

## The Three Phases

John Hattie's research identifies three phases every learner must move through. A well-designed course scaffolds all three in sequence. A gap in an earlier phase blocks progression to the next.

**Phase 1 → Surface → Phase 2 → Deep → Phase 3 → Transfer**

A course cannot support Deep learning if the Surface is broken. A course cannot support Transfer if Deep is absent.

---

## Phase 1: Surface Learning

Students acquire foundational knowledge — the "what" and "how." They need clear navigation, sequenced content, and low extraneous load so they can focus on new information rather than figuring out where to go.

### Canvas indicators Surface is supported

- Module has an overview page (outcomes, time estimate, sequence of items)
- Content items are clearly labeled and logically ordered
- Navigation is predictable — consistent module naming, no orphaned pages
- Item count is manageable (≤7 per module)
- All items in a published module are also published (no broken links)

### Canvas indicators of a Surface gap

| Signal | What it means |
|--------|---------------|
| No overview page | Students don't know what they're learning or why before they start |
| Module starts with an assessment | Students are tested before they've been taught |
| Inconsistent module naming | Navigation is unpredictable; students can't build a mental map of the course |
| Unpublished items in a live module | Students hit dead ends — orientation collapses |
| >7 items in a module | Cognitive overload before content learning begins |
| Duplicate instructions | Students waste working memory resolving contradictions |

### Cognitive load connection

Surface gaps are almost always **extraneous load**. See [`cognitive_load_theory_knowledge.md`](cognitive_load_theory_knowledge.md) for load mechanics and the working-memory limit that justifies the ≤7 items rule.

---

## Phase 2: Deep Learning

Students connect ideas, find patterns, and build understanding — the "why" and "when." They need activities that require them to explain, compare, debate, or teach. Surface knowledge is the raw material; Deep learning is where it becomes understanding.

### Canvas indicators Deep is supported

- Discussion activities where students apply or explain concepts to each other (BYUI: Teach One Another)
- Assignments that require synthesis, comparison, or judgment — not just recall
- Learning outcomes explicitly stated on overview pages (students need to know *what* to connect)
- Peer review or collaborative tasks
- Reflection prompts tied to content

> **Group/peer-task *quality* caveat.** A peer or group task supports Deep learning only if it is *designed* for it — poorly designed group work backfires. Treat "a group task exists" as a green flag only when both hold: (a) **individual accountability** (each student's own contribution is assessable, defusing freeloader anxiety), and (b) **interdependent roles** (the task genuinely requires collaboration, not parallel solo work stapled into "modular silos"). The reason peer construction works at all is the *expert blind spot* — a near-peer who recently struggled often unsticks a novice better than the expert (see [`cognitive_load_theory_knowledge.md`](cognitive_load_theory_knowledge.md) schemas).

### Canvas indicators of a Deep gap

| Signal | What it means |
|--------|---------------|
| Module has only quizzes and readings | No mechanism for students to construct meaning |
| All assessments are multiple-choice | Recall is tested, not understanding |
| No discussion or peer interaction | Students process individually only — no social construction of knowledge |
| Group project with no individual accountability or interdependent roles | Freeloader anxiety + "modular silos"; collaboration is nominal, no co-construction |
| Overview page exists but states no outcomes | Students can't connect new content to goals they understand |

### Cognitive load connection

Deep learning gaps often mean **germane load is absent** — no activity is doing the schema-building work. See [`cognitive_load_theory_knowledge.md`](cognitive_load_theory_knowledge.md) for germane-load audit indicators.

---

## Phase 3: Transfer Learning

Students apply knowledge to new, unfamiliar contexts — the "what if" and "so what." Transfer is the goal of education. It requires authentic tasks with real-world stakes or cross-domain application, where students must make judgment calls rather than follow a procedure.

### Canvas indicators Transfer is supported

- Project-based or milestone assessments with open-ended scope
- Self-assessment or reflection assignments
- Assignments that require applying skills to problems the course hasn't explicitly modeled
- Capstone tasks that integrate multiple modules
- Students make design or judgment decisions (not just execute a known procedure)

### Canvas indicators of a Transfer gap

| Signal | What it means |
|--------|---------------|
| No project or milestone assignment | Students never have to apply knowledge independently |
| All assessments are closed (structured lab with answer key, quiz) | Every problem has a right answer — no transfer required |
| No self-assessment or end-of-unit reflection | Students never evaluate their own understanding |
| Module ends immediately after a quiz | No consolidation or application after assessment |

### Cognitive load connection

Transfer requires upstream load discipline — extraneous removed in Surface, germane built in Deep. Transfer gaps are usually symptoms of CLT failures earlier in the sequence. See [`cognitive_load_theory_knowledge.md`](cognitive_load_theory_knowledge.md).

---

## Phase Gap Tags Used in Audit Output

Every audit issue includes a `hattie_phase` field:

| Value | Meaning |
|-------|---------|
| `surface` | Issue blocks foundational acquisition |
| `deep` | Issue prevents connection and understanding |
| `transfer` | Issue removes authentic application opportunity |
| `all` | Issue impairs the entire learning progression |

Prioritize fixing issues tagged `all` first (e.g., missing overview, broken module navigation), then `surface`, then `deep`, then `transfer`.

---

## Mapping to BYUI Module Structure

| BYUI Element | Hattie Phase |
|---|---|
| Overview page | Surface — orients and reduces extraneous load |
| Content (readings, videos, demos) | Surface — foundational acquisition |
| NotebookLM / AI tools | Surface → Deep — acquisition + elaboration |
| Teach One Another (discussion) | Deep — peer construction of meaning |
| Stand Up Report / quiz | Deep → Transfer — checking understanding, beginning application |
| Prove It (assignment, milestone) | Transfer — authentic demonstration |
| Self-assessment / reflection | Transfer — metacognitive consolidation |

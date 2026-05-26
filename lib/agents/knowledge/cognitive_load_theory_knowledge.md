# Cognitive Load Theory — Knowledge Reference

Source: Sweller, J. (1988); Atkinson & Shiffrin (1968) memory model; *Cognitive Load Theory: A Guide to Applying CLT to Your Teaching* (Medical College of Wisconsin, Office of Educational Improvement, May 2022).

Used by: `canvas_course_expert.md` (audit framework), `canvas_course_expert.json` (`analyze_cognitive_load` tool, load-type tags on every audit rule).

Companion: [`hattie_3phase_knowledge.md`](hattie_3phase_knowledge.md) — Hattie sequences learning (Surface → Deep → Transfer); CLT addresses the working-memory mechanics that determine whether any phase can succeed.

_Last updated: 2026-05-13_

---

## The Memory Model

Three stages process incoming information:

```
Incoming → Sensory Memory → Working Memory → Long-Term Memory
                  ↓               ↓
             (forgotten)     (forgotten)
```

- **Sensory memory** filters most stimuli, passing select information to working memory.
- **Working memory** processes 5–9 chunks at a time. It either discards information or encodes it into long-term memory.
- **Long-term memory** stores information in **schemas** — organized structures that compress prior knowledge into a single retrievable chunk.

The bottleneck is working memory. Course design either respects its limits or overwhelms it.

---

## Schemas: Why Prior Knowledge Matters

A well-developed schema, no matter how complex, counts as **one chunk** in working memory. This is why experts can hold and manipulate ideas a novice cannot — the expert's schema compresses what the novice must process piece by piece.

**Implications for course design:**
- Activate prior knowledge before introducing new material — students need a schema to attach new content to.
- Target instruction at the **gap between what learners know and what we need them to learn** (the "problem space").
- If the problem space is too large, learners overload and retain nothing.

---

## The Three Types of Cognitive Load

| Type | Definition | Source | Design implication |
|---|---|---|---|
| **Intrinsic** | The inherent difficulty of the material | Content complexity | Cannot reduce without changing the outcome — but can be sequenced (simpler → harder). |
| **Extraneous** | Effort spent fighting the *presentation*, not the content | Poor design | **Eliminate.** This is the load you have direct control over. |
| **Germane** | Productive cognitive work that builds schemas | Learning activity | **Encourage.** Discussion, comparison, application — the work of understanding. |

**Cognitive overload** = intrinsic + extraneous + germane > working memory capacity. Even capable learners fail when the total exceeds the limit.

**Priority for designers:** Reduce extraneous first. Intrinsic is fixed by the subject. Germane is what you want — you cannot afford to crowd it out with extraneous noise.

---

## Dual Channel Theory

Working memory has **two separate processing channels** — auditory and visual. They do not compete with each other.

**Implications:**
- Pairing a visual diagram with spoken narration *expands* total processing capacity.
- Pairing a diagram with on-screen text duplicates the visual channel — students must split attention between two visual sources, which *reduces* capacity.
- Effective design: visual + audio that **complement** each other (not duplicate).

---

## The Problem Space

The gap between a learner's current state and the desired goal. CLT framing:
- **Too small** → boring, no learning.
- **Too large** → overload, no learning.
- **Right size** → progress, with effort.

Effective scaffolding shrinks the problem space by chunking — break a complex task into ordered sub-tasks that each fit in working memory.

---

## Canvas Audit Indicators

### Extraneous load — eliminate

| Signal | Why it's extraneous |
|--------|---------------------|
| >7 items in a module | Exceeds working memory's 5–9 chunk limit before learning even starts |
| Inconsistent module/item naming | Students burn cycles re-orienting instead of learning |
| Duplicate or contradictory instructions | Working memory spent reconciling the contradiction |
| Labels separated from diagrams | Forces eye movement and re-association — split-attention effect |
| Unpublished items in a published module | Students hit dead ends; navigation collapses |
| No time estimate on readings/assignments | Students can't plan working-memory allocation |
| Required external tool with no direct link | Effort spent navigating, not learning |
| Module starts mid-task with no overview | No schema activation; new content has nothing to attach to |

### Intrinsic load — sequence, don't reduce

| Signal | Implication |
|--------|---------|
| Hard concept introduced before its prerequisites | Intrinsic load too high because schema isn't built |
| Multiple new concepts in one item | Decompose into chunks |
| Assessment requires combining skills not yet practiced individually | Sequence: practice components before integration |

### Germane load — protect and encourage

| Signal | Why it matters |
|--------|---------------|
| Module has only readings + a quiz | No germane activity — students memorize, don't build schemas |
| Discussions with no synthesis prompt | Surface engagement, no schema construction |
| All assessments are recall-only | Germane load absent — long-term schema never forms |
| No reflection or self-assessment | Metacognition is germane work; without it, schemas stay shallow |

---

## Load-Type Tags Used in Audit Output

Every audit issue should be tagged with a `cognitive_load_type` field:

| Value | Meaning | Priority |
|-------|---------|----------|
| `extraneous` | Design friction; competes with learning | **Highest — fix first** |
| `intrinsic` | Content sequencing or chunking issue | Medium |
| `germane` | Missing or weak schema-building activity | Medium-high |

Pair this with the `hattie_phase` tag from `hattie_3phase_knowledge.md` for a full diagnosis: *what kind of load* (CLT) is blocking *which phase of learning* (Hattie).

---

## Quick Reference for Auditors

When evaluating a Canvas course element, ask in order:

1. **Working memory test** — Can a student hold this whole task in mind at once? If item count > 7 or instructions span multiple unlinked locations, no.
2. **Extraneous load test** — Is any of the difficulty about navigation, formatting, or reconciliation rather than the actual content? If yes, that load is removable.
3. **Schema activation test** — Does the module start with something that connects to prior knowledge (overview, recap, concept map)? If not, students are building on nothing.
4. **Dual channel test** — When media is paired, does it complement (visual + audio) or duplicate (visual + on-screen text)?
5. **Germane work test** — Is there at least one activity in the module that requires synthesis, comparison, application, or explanation? If not, no schemas are forming.

A "no" on any of these is a defect to flag with the corresponding load type.

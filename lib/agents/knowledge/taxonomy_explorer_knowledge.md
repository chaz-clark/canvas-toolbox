---
name: taxonomy_explorer_knowledge
version: '1.0'
last_updated: '2026-07-16'
description: BYUI's institutional view of the three learning domains, including BYUI's chosen psychomotor model (Simpson 1972, 7 levels) and the live verb-classification tool faculty actually use. Faculty preferring BYUI tool view → this file; faculty p
skill_type: knowledge
shape: reference
scope: BYUI's institutional view of the three learning domains, including BYUI's chosen psychomotor model (Simpson 1972, 7 levels) and the live verb-classification tool faculty actually use. Faculty preferring BYUI tool view → this file; faculty preferring academic-research view → three_domains_knowledge.md. For domain theory, affective-domain-matters argument, physical ≠ psychomotor distinction, and audit interpretation, defer to three_domains_knowledge.
consumed_by:
- canvas_course_expert.md
provenance:
  sources:
  - BYU-Idaho. The Taxonomy Explorer. https://content.byui.edu/file/c5d91be3-1a6e-4f21-bf0a-610f9f1e2dd6/1/Taxonomy_Explorer.html
  - Anderson, L.W. & Krathwohl, D.R. (2001). Cognitive taxonomy revision.
  - Krathwohl, D.R. (1964). Affective taxonomy.
  - Simpson, E.J. (1972). The classification of educational objectives in the psychomotor domain.
companion_json_deprecated: 2026-07-16 - consolidated into YAML frontmatter (JSON purge convention)
runtime_strategy: read_at_runtime
metadata:
  knowledge_id: taxonomy_explorer_knowledge
---

# BYUI Taxonomy Explorer — Knowledge Reference

Source: BYU-Idaho. *The Taxonomy Explorer.* https://content.byui.edu/file/c5d91be3-1a6e-4f21-bf0a-610f9f1e2dd6/1/Taxonomy_Explorer.html

Used by: `canvas_course_expert.md` (audit framework) — provides the **BYUI institutional view** of the three learning domains, including BYUI's chosen psychomotor model and the live verb-classification tool faculty actually use.

Companion: [`three_domains_knowledge.md`](three_domains_knowledge.md) — academic-research framing (Wilson, *The Second Principle*). Both files describe the same three domains; this file documents BYUI's institutional expression of them. **Faculty preferring the BYUI tool view → this file. Faculty preferring the academic-research view → `three_domains_knowledge.md`.** For domain theory, the affective-domain-matters argument, the physical ≠ psychomotor distinction, and audit interpretation, defer to that file.

---

## What the Taxonomy Explorer Is

A live BYUI tool that classifies educational objectives by domain (Cognitive, Affective, Psychomotor) and level. Two functions:

1. **Domain hierarchy view** — visual pyramid of each domain's levels (1 → top).
2. **Verb lookup** — instructor enters a verb (e.g., *evaluate*, *organize*, *adapt*) and the tool returns the matching domain + level.

The tool is what BYUI faculty are pointed to when writing learning outcomes. Auditing against BYUI standards means auditing against this tool's classifications.

---

## BYUI's Domain Summaries

Verbatim from the Taxonomy Explorer main page:

| Domain | BYUI summary |
|---|---|
| **Cognitive** | "Intellectual skills, knowledge, and mental processes." Knowledge acquisition, comprehension, and thinking processes ranging from basic recall to complex evaluation and creation. |
| **Affective** | "Growth in feelings, values, appreciation, and attitudes." Progresses from basic receiving of information to the internal characterization of a personal value system. |
| **Psychomotor** | "Physical movement, coordination, and motor-skill areas." Progresses from basic perception and imitation to independent mastery and creative original performance. |

---

## Cognitive Domain — Bloom Revised (Anderson & Krathwohl, 2001)

Six levels, simple → complex. Same as Wilson's framing — see [`three_domains_knowledge.md`](three_domains_knowledge.md) for Bloom-1956-vs-2001 verb-list interpretation.

| Lvl | Level | One-line meaning |
|---|---|---|
| 1 | **Remembering** | Retrieve relevant knowledge from long-term memory |
| 2 | **Understanding** | Construct meaning from instructional messages |
| 3 | **Applying** | Carry out or use a procedure in a given situation |
| 4 | **Analyzing** | Break material into parts; detect relationships |
| 5 | **Evaluating** | Make judgments based on criteria and standards |
| 6 | **Creating** | Put elements together to form a coherent or original whole |

---

## Affective Domain — Krathwohl (1964)

Five levels of internalization. Identical to Wilson's framing — see [`three_domains_knowledge.md`](three_domains_knowledge.md) for verb lists and design rationale.

| Lvl | Level | One-line meaning |
|---|---|---|
| 1 | **Receiving** | Awareness; willingness to attend |
| 2 | **Responding** | Active attention; motivation to engage |
| 3 | **Valuing** | Acceptance, preference, or commitment to a value |
| 4 | **Organizing** | Sorting values into a coherent system |
| 5 | **Characterizing** | Values become a stable life pattern |

---

## Psychomotor Domain — Simpson (1972) — *BYUI's chosen model*

**This is where BYUI diverges from Wilson.** Wilson uses Harrow (6 levels). The BYUI Taxonomy Explorer uses **Simpson's 7-level taxonomy** (Elizabeth Simpson, 1972), which is the more common instructional-design model and emphasizes skill acquisition rather than developmental movement.

| Lvl | Level | One-line meaning |
|---|---|---|
| 1 | **Perception** | Using sensory cues to guide motor activity |
| 2 | **Set** | Readiness to act — mental, physical, and emotional |
| 3 | **Guided Response** | Early performance via imitation and trial-and-error |
| 4 | **Mechanism** | Learned responses become habitual; basic proficiency |
| 5 | **Complex Overt Response** | Skilled performance of complex motor acts |
| 6 | **Adaptation** | Modifying skills to fit new or problem situations |
| 7 | **Origination** | Creating new movement patterns to fit a situation |

### Simpson vs. Harrow — when each fits

| Use Simpson (this file) when… | Use Harrow ([three_domains](three_domains_knowledge.md)) when… |
|---|---|
| Auditing against BYUI's Taxonomy Explorer tool | Auditing against Wilson's *Second Principle* / general instructional-design literature |
| Faculty wrote outcomes using the BYUI verb-lookup | Faculty wrote outcomes from Bloom/Wilson reference materials |
| Skill acquisition is the focus (lab technique, performance) | Movement development is the focus (PE, dance, early-childhood motor skills) |

The two models classify a verb similarly at the low and high ends but diverge in the middle. *Mechanism* (Simpson) ≈ *Skilled movements* (Harrow); *Origination* (Simpson) ≈ *Nondiscursive communication* (Harrow). Simpson's *Set* and *Guided Response* have no clean Harrow analog.

---

## Verb Lookup — How It Works

The tool accepts a single verb and returns its domain + level. For audits, this means:

1. Pull the verb from each learning outcome.
2. Look it up (or simulate the lookup using the level definitions above).
3. Compare claimed cognitive level (in the outcome statement) to the tool's classification of the verb actually used.

Common audit finding: outcome says "students will *understand*…" but the assessment requires *analyzing* or *evaluating*. The verb in the outcome is Lvl 2 cognitive; the assessment is Lvl 4–5. Misalignment.

---

## Canvas Audit Indicators (BYUI-Tool Framing)

| Signal | What it indicates |
|---|---|
| Outcome verb classifies as cognitive Lvl 1–2, assessment requires Lvl 4–6 | Outcome-assessment misalignment — flag |
| Outcome uses a verb the BYUI tool does not classify (vague: "know", "learn", "be familiar with") | Unmeasurable outcome — flag |
| All outcomes in a course classify as Cognitive only (no Affective, no Psychomotor) | Single-domain course — note as retention risk per Wilson's holistic argument (defer to `three_domains_knowledge.md`) |
| Course claims a psychomotor outcome but the verb classifies as cognitive | Physical-supporting-cognitive miscategorization — defer to `three_domains_knowledge.md` for the boundary rule |
| Affective outcomes use Lvl 1 (Receiving) verbs only | Surface affective design — students are asked to attend, not to value or commit |

---

## Tag Used in Audit Output

When an audit is performed against the BYUI Taxonomy Explorer rather than Wilson, add a `taxonomy_source` field:

| Value | Meaning |
|---|---|
| `byui_explorer` | Classification follows the BYUI Taxonomy Explorer (Simpson psychomotor) |
| `wilson` | Classification follows Wilson / Harrow psychomotor |
| `agnostic` | Cognitive or Affective only — both sources agree |

Pair with the existing `learning_domain` and `hattie_phase` tags. The `taxonomy_source` field tells the reader which framework the audit applied — important when a course's outcomes were authored using BYUI's tool.

---

## Quick Reference for Auditors (BYUI Mode)

When auditing a BYUI course's learning outcomes:

1. **Pull the verb** from each outcome statement.
2. **Classify the verb** using the Simpson/Bloom/Krathwohl tables above (or the live BYUI tool).
3. **Match to assessment** — does the assessment require the same domain + level the verb claims?
4. **Check domain coverage** — are all outcomes cognitive, or do affective/psychomotor outcomes also exist where the course implies them?
5. **Flag vague verbs** — anything not in the tool's classification (know, learn, understand-as-vague-synonym) is unmeasurable.

For domain theory and the holistic-design argument, defer to [`three_domains_knowledge.md`](three_domains_knowledge.md).

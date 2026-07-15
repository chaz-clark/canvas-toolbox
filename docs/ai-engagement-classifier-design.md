# AI Engagement Classifier — Design

> **Status: DESIGN DRAFT.** Defines a new cb tool, `ai_engagement_classifier`, and the
> **pluggable engagement-taxonomy** it runs. cb owns this primitive; ngai-n8n consumes it.
> The initial shipped taxonomy is a **placeholder** — our own working approximation of the
> aimodes.ai structure (Dr. Mark Keith), *not* his validated instrument. See
> `../../ngai-n8n/design/keith-collaboration-pitch.md`.

## 1. The one design decision

Do **not** hard-code any engagement framework into the classifier. The framework —
tiers, modes, per-mode thresholds, transition model, archetypes — lives in a swappable
**taxonomy profile** (a `.json` file). The classifier is a generic engine:

```
classify(transcript, profile)  ->  engagement report (stable JSON contract)
```

This buys everything the project needs:

| Need | How the pluggable profile delivers it |
|---|---|
| Placeholder for dev **now** | Ship `aimodes_placeholder.json` (our definitions). |
| Revert to a **3-tier** model | Swap in `three_tier.json`. Zero code change. |
| Compare a **5-tier AI-use** model | Add `five_tier_aiuse.json`. Same engine, same data model. |
| Plug in **Keith's validated** framework if he collaborates | His definitions/thresholds/routes become `aimodes_keith.json`, attributed to him. |
| Don't waste dev-era data | Raw transcripts are stored; **re-classify history** under any new profile later. |

The profile is the pluggable, attributable, swappable piece. The engine and the output
contract stay stable across all of them.

## 2. Taxonomy profile schema

One file per framework, in `lib/agents/knowledge/engagement_taxonomy/<profile_id>.json`.

```jsonc
{
  "profile_id": "aimodes_placeholder",
  "schema_version": "1.0",
  "version": "0.1.0-placeholder",
  "display_name": "AI Modes (placeholder approximation)",
  "status": "placeholder",              // placeholder | validated
  "attribution": "Structure inspired by aimodes.ai (Dr. Mark Keith, BYU). Definitions are our own working drafts — NOT Keith's validated instrument. Do not represent as his model.",

  "tiers": [
    { "id": "passivity",   "order": 1, "label": "Passivity",   "agency_weight": 0,   "description": "Student outsources thinking; AI produces, student receives." },
    { "id": "partnership", "order": 2, "label": "Partnership", "agency_weight": 50,  "description": "Student and AI think together; shared cognitive load." },
    { "id": "agency",      "order": 3, "label": "Agency",      "agency_weight": 100, "description": "Student drives and checks the AI; AI serves the student's direction." }
  ],

  "modes": [
    { "id": "oracle",              "tier": "passivity",   "label": "Oracle",                    "threshold": 0.10, "definition": "...", "signals": ["..."] },
    { "id": "production_assistant","tier": "passivity",   "label": "Production Assistant",      "threshold": 0.10, "definition": "...", "signals": ["..."] },
    { "id": "tutor",               "tier": "partnership", "label": "Tutor",                     "threshold": 0.20, "definition": "...", "signals": ["..."] },
    { "id": "collab_solver",       "tier": "partnership", "label": "Collaborative Problem-Solver","threshold": 0.20, "definition": "...", "signals": ["..."] },
    { "id": "verification_agent",  "tier": "agency",      "label": "Verification Agent",        "threshold": 0.10, "definition": "...", "signals": ["..."] },
    { "id": "creative_expander",   "tier": "agency",      "label": "Creative Expander",         "threshold": 0.10, "definition": "...", "signals": ["..."] },
    { "id": "critical_challenger", "tier": "agency",      "label": "Critical Challenger",       "threshold": 0.10, "definition": "...", "signals": ["..."] },
    { "id": "problem_setter",      "tier": "agency",      "label": "Problem Setter",            "threshold": 0.10, "definition": "...", "signals": ["..."] }
  ],

  "archetypes": [
    { "id": "delegator",  "label": "Delegator",  "rule": "passivity tier >= 0.50" },
    { "id": "learner",    "label": "Learner",    "rule": "tutor is the modal mode" },
    { "id": "partner",    "label": "Partner",    "rule": "partnership tier >= 0.50" },
    { "id": "challenger", "label": "Challenger", "rule": "critical_challenger >= its threshold and agency tier >= 0.33" },
    { "id": "explorer",   "label": "Explorer",   "rule": "creative_expander + problem_setter >= 0.25" },
    { "id": "specialist", "label": "Specialist", "rule": "one agency mode >= 0.40" }
  ],
  "archetype_default": "partner"
}
```

- **`threshold`** = target share of a student's turns that *should* fall in this mode
  ("where a student should be" — Keith's per-mode thresholds). Placeholder values here;
  Keith's validated numbers replace them when/if he's in.
- **`agency_weight`** drives the 0–100 agency score (§4). Tier-level, so any tier count works
  (3-tier aimodes, or a 5-tier scale that defines 5 tiers each with its own weight).
- **`archetypes[].rule`** is a small, fixed DSL evaluated in code (§4) — not eval'd. Keeping
  the rules *declarative in the profile* means a new framework ships its own archetypes.

### Swap targets (revert / compare)

- `three_tier.json` — 3 modes that ARE the 3 tiers (Passivity/Partnership/Agency), thresholds
  only at tier granularity. Reverts to the coarse model.
- `five_tier_aiuse.json` — 5 tiers/modes for the "5-level AI usage" research you're evaluating
  (e.g. No-AI → AI-planned → AI-collaboration → AI-led → Full-AI). Fill definitions when chosen.

## 3. Placeholder mode definitions (ours, working drafts)

These are cb's own approximations for dev. Crisp, classifiable from a transcript.

| Mode | Tier | The student is… |
|---|---|---|
| **Oracle** | Passivity | asking for a fact/answer and taking it as-is. "What's the answer to X?" |
| **Production Assistant** | Passivity | delegating production of an artifact. "Write the code/essay for X." |
| **Tutor** | Partnership | asking the AI to explain so *they* understand. "Explain why X works." |
| **Collaborative Problem-Solver** | Partnership | iterating jointly — proposing, having the AI refine, pushing back. |
| **Verification Agent** | Agency | checking *their own* work/reasoning. "Here's my solution — where's my error?" |
| **Creative Expander** | Agency | broadening options beyond their own. "Give me 5 alternative approaches." (student selects) |
| **Critical Challenger** | Agency | inviting adversarial pressure. "Argue against my thesis / find the holes." |
| **Problem Setter** | Agency | framing/scoping the problem itself, setting the agenda, using AI as an instrument. |

## 4. Output contract (the stable JSON cb emits)

**Only student turns are classified** — the mode describes how the *student* is using the AI in
that exchange; the AI turn is context. The **ordered** `sequence` is what makes route/transition
mapping possible (a distribution alone can't).

```jsonc
{
  "schema_version": "1.0",
  "profile_id": "aimodes_placeholder",
  "profile_version": "0.1.0-placeholder",
  "conversation_id": "<caller-supplied>",
  "message_count": 12,
  "student_turn_count": 6,

  "sequence": [                                 // ORDERED student turns → enables routes
    { "index": 0, "mode": "oracle", "tier": "passivity", "confidence": 0.82, "evidence": "short quote/rationale" },
    { "index": 1, "mode": "tutor",  "tier": "partnership","confidence": 0.71, "evidence": "..." }
    // ...
  ],

  "tier_distribution":  { "passivity": 0.33, "partnership": 0.50, "agency": 0.17 },
  "mode_distribution":  { "oracle": 0.17, "tutor": 0.33, "collab_solver": 0.17, "verification_agent": 0.17, "problem_setter": 0.16 },

  "agency_score": 42,                           // 0–100, Σ(tier_share × agency_weight)

  "threshold_gaps": [                           // actual vs. target per mode (where they should be)
    { "mode": "problem_setter", "actual": 0.16, "target": 0.10, "gap": +0.06 },
    { "mode": "critical_challenger", "actual": 0.0, "target": 0.10, "gap": -0.10 }
  ],

  "transitions": [                              // the ROUTE — consecutive student-mode hops
    { "from": "oracle", "to": "tutor", "count": 1 },
    { "from": "tutor",  "to": "collab_solver", "count": 1 }
  ],

  "archetype": { "id": "learner", "label": "Learner", "rationale": "tutor is the modal mode" }
}
```

Everything below `sequence` is **computed in Python from `sequence`** (deterministic, testable) —
the LLM only produces `sequence`. That keeps the LLM's job small (classify each turn) and makes
distribution/score/gaps/transitions/archetype unit-testable without the model.

## 5. How it plugs into ngai-n8n (the consumer)

- **cb is the primitive.** `ai_engagement_classifier` is versioned + tested, emits the contract
  above. ngai-n8n's qc-agent stops hand-rolling CT/CQ and calls this instead (n8n → Python CLI,
  same pattern as the planned grade write-back).
- **Storage.** Persist the full contract on `conversation_analysis`, keyed by
  `canvas_user_id × course_id × term`. Minimal columns: `engagement_profile_id`,
  `engagement_agency_score`, `engagement_archetype`, and the contract as JSONB
  (`engagement_report`). Derive CT/CQ + the pass-gate *from* it (Keith's model subsumes CT/CQ).
- **Retroactive re-classification.** Raw transcripts already live in `messages`. When a new
  profile arrives (e.g. Keith's validated one), re-run the classifier over history → new report
  rows with the new `profile_id`. The dev-era back-catalog becomes valid data in the new model.
- **Longitudinal rollup.** Aggregate `agency_score` + `tier_distribution` + `threshold_gaps`
  per student across conversations → per module → per course → per term → across terms. Join the
  **project axis** (can-do, from grades) with this **knowledge axis** (how they engaged) → the
  two-axis competency map: *can I do it* × *do I understand it*, tracked over time, with the
  route showing how they moved mode-to-mode within a conversation.

## 6. Non-goals / boundaries

- The placeholder is **not** Keith's instrument and must never be presented as such (the profile
  `attribution`/`status` fields enforce this in every output).
- The classifier does not fetch conversations — it takes a normalized transcript (ngai-n8n has
  the messages; cb's `grader_follow_share_url` can supply share-URL transcripts).
- Thresholds/routes in the placeholder are provisional and exist to exercise the pipeline, not to
  make claims about students.

## 7. Build order (C)

1. `lib/agents/knowledge/engagement_taxonomy/aimodes_placeholder.json` — full placeholder profile.
2. `lib/agents/knowledge/engagement_taxonomy/three_tier.json` — proves swappability.
3. `lib/tools/ai_engagement_classifier.py` — profile loader, prompt builder, LLM provider (reuse
   grader_grade's `GraderLLM`/`make_provider` pattern), strict-JSON parse, the deterministic
   Python aggregation (§4), CLI. `--dry-run` emits the assembled prompt + empty contract with no
   LLM call.
4. `lib/tests/test_ai_engagement_classifier.py` — profile-loads, swap works, aggregation math,
   transition extraction, archetype rules, threshold gaps. All deterministic (no LLM in tests).

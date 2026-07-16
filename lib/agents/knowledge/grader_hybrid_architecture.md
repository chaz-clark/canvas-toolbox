# Hybrid grading architecture — layer-routed NLP + LLM

**Consumed by:** the grading agent + `grader_signals.py`, `grader_grade.py`,
`grader_consensus.py`. Tracks issue #192.

**Why this file exists:** canvas-toolbox grades *with* an LLM, but the LLM is not the
whole grader. The defensible, reproducible way to grade prose, code, and methodology is a
**layer-routed hybrid** — deterministic NLP owns the observable layers, the LLM owns the
semantic/judgment layers, a deterministic pass audits the LLM, and the instructor decides.
This file is the *how to think*, so grading follows the architecture by default rather than
only when a human steers it. Read alongside `grader_knowledge` (the workflow) and
`critical_thinking_knowledge` / `byui_ai_agency` (the rubric grounding).

---

## The core principle

Route every rubric criterion and every quality signal to the layer that is *authoritative*
for it — and never let a layer overreach. Regex must not pretend to judge insight; the LLM
must not be trusted to count deterministically. The originality of good AI-assisted grading
is not any one trick — it is the **disciplined refusal to let a layer do another layer's job.**

## The four layers (cheapest/most-deterministic → richest/most-semantic)

| # | Layer | Examples | Owner |
|---|---|---|---|
| 1 | **Lexical / pattern** | regex, counts, term-banks, citation detection, required-item coverage | **NLP** — deterministic evidence |
| 2 | **Syntactic / structural** | sectioning, code-vs-prose split, AST, readability | **NLP** — deterministic structure |
| 3 | **Semantic** | does the argument cohere, is this really addressing the prompt, is the reasoning sound | **LLM** |
| 4 | **Holistic judgment** | insight, synthesis, the rubric's quality bands, feedback prose | **LLM** |

Above all four sits **the instructor** — the top layer, who decides. The stack is
**decision support, not autonomy** (see "The ceiling" below).

## Routing rubric criteria by checkability

The single decision that makes "put rubric knowledge in the script" robust instead of brittle:

| Criterion type | Example | NLP can produce | Authoritative layer |
|---|---|---|---|
| **Mechanical / binary** | "includes a thesis", "≥3 citations", "defines the term", "code runs" | regex / count / AST → **hard evidence** | **NLP** (LLM confirms) |
| **Coverage** | "addresses all 5 prompts", "discusses each of the 3 regulations" | per-item presence → **strong evidence, watch paraphrase** | **shared** — NLP flags, LLM verifies |
| **Judgment / quality** | "demonstrates critical insight", "synthesizes sources", "clarity" | weak proxies only (readability, quote:analysis ratio) → **hints** | **LLM** (NLP contributes little) |

Let NLP own the mechanical and coverage rows; leave the judgment rows to the LLM. Forcing
regex onto "critical insight" is the fastest way to build an extractor that *fights* the LLM.

## The guardrails (non-negotiable)

1. **Priors never score.** NLP produces evidence and priors; it never sets the grade. The
   grade is LLM judgment (consensus) confirmed by the instructor.
2. **Evidence, not verdict.** Present every NLP feature to the LLM as evidence *to verify
   against the text* — e.g. `citations: literal match 0 — check for paraphrase` — never as
   "criterion met/unmet." This keeps the corpus in the loop and defeats keyword-stuffing (a
   stuffed term-bank inflates the count, but the LLM reading the corpus catches the emptiness
   — only if the feature is framed as evidence, not a met criterion).
3. **Route by checkability.** NLP is authoritative only on mechanical/coverage rows.
4. **The audit stays (semi-)independent.** NLP audits the LLM consensus against the evidence
   and routes conflicts to a human; it never auto-moves a score. Feeding a signal *into* the
   pass prompt reduces that signal's power *as an auditor* (the passes were nudged toward it),
   so decide per signal whether it **grounds**, **audits**, or **both**.
5. **The instructor is the top layer.** The stack surfaces evidence + judgment + conflicts;
   the human decides.

## Signal taxonomy — tag every signal in `grader_signals.py`

- **`structural`** — reorganizes/parses the input (HTML → sections, code vs comments). Pure
  feature engineering, **zero leakage**. Always inject.
- **`evaluative`** — an observable property tied to a rubric row (citation count, coverage,
  term-bank hits). Inject to ground **and/or** hold for the audit — operator choice per signal.
- **`judgment-hint`** — a weak proxy for a soft row (readability, quote:analysis ratio).
  Provide as a hint at most; never let it approach a score.

The "leakage" worry scales with how *answer-like* a signal is: structural = none;
observable-property = low (legitimate feature engineering); answer-proximity (similarity to a
key) = high — that one makes the audit circular and invites parroting, so handle with care.

## Enrichment vs token-reduction — know which lever you're pulling

Two **opposite** uses of NLP. Both valid; never conflate them:

- **Enrichment (quality lever):** corpus **+** computed features → the LLM grades better with
  evidence pre-surfaced. Spends *more* tokens to buy accuracy and defensibility.
- **Token-reduction (cost lever):** **densify, do not truncate.** Reorganize and surface the
  relevant evidence so the same signal fits in fewer tokens; route pass-count by difficulty
  (clear-cut → 1 pass, borderline → N); skip trivial cases. **Trimming the corpus blindly cuts
  signal and lowers grade quality** — remove noise, never signal.

On local Ollama tokens are ~free → prefer **enrichment**. On the cloud path → token-reduction pays.

## Stage 0 — when there is no rubric, elicit one first

Everything above assumes a rubric with rows exists. Often it does not — the "rubric" lives in
an assignment spec (e.g. a `challenge.md`), a few exemplars, or only in the professor's head.
**Grading cannot start until that intent is made explicit.** Stage 0 is the precondition:
co-create a structured rubric from the unstructured source *before* the layer-routed pipeline
runs. (DS460 is the canonical case — the `challenge.md` *is* the rubric source.)

It is itself a hybrid:
- **Extract candidate criteria** — NLP/LLM pulls the explicit deliverables, requirements, and
  constraints out of the spec (structural work).
- **Elicit the quality bands** — the LLM proposes tiers / what-good-looks-like per criterion
  and the professor refines them. This is the "tease out what they're looking for" step, and
  the judgment is the professor's, not the model's.
- **Tag each criterion by checkability** as you go (mechanical / coverage / judgment) with its
  term-banks / required-items — so the output is already in the shape the pipeline consumes.

Two Stage-0 guardrails:
- **The professor owns the rubric.** The LLM proposes; the professor approves. Same "instructor
  is the top layer" principle applied to the rubric itself — never grade against criteria the
  professor didn't intend.
- **Freeze the agreed rubric as a versioned artifact.** A teased-out rubric re-improvised each
  run destroys reproducibility and defensibility (you'd grade against a moving target). A
  `challenge.md`-derived rubric becomes a **checked-in** rubric the grading run reads, not a
  fresh improvisation — that is what lets "the rubric is the source of truth" (below) hold even
  when the rubric started life as prose.

Existing cb tooling: the `grader_setup_knowledge` 6-step interview is where the elicitation
happens; `rubrics_knowledge` / `rubric_recommender` help draft criteria. Stage 0 is those,
aimed at producing a **hybrid-ready (checkability-tagged), frozen** rubric. After it, the full
architecture applies unchanged.

## The rubric is the source of truth

Encode rubric knowledge as **data derived from the rubric** (term banks, required-item lists,
thresholds), not hardcoded in the script. A rubric edit must update the extractors, or you
silently grade last term's rubric. When the rubric came from Stage 0, "the rubric" means the
**frozen artifact**, not the original prose spec.

## The audit loop

N independent **blind** LLM passes (temperature-varied, tier-shuffled) → **majority consensus**
→ deterministic **conflict check** (majority tier vs its own evidence prior: tier-above-threshold
but prior-below-floor, and vice-versa) → `conflict_needs_review` routed to a human. Consensus
tames single-pass drift (one pass defaults conservatively to the middle tier); the audit catches
where the holistic read diverged from the mechanical evidence. **Never auto-moves a score.**

## How it maps to cb tools

- **`grader_signals.py`** — the NLP layer: `structural` + `evaluative` + `judgment-hint`
  signals, rubric-derived, each tagged. Prose set (length, citations, per-criterion term-banks,
  coverage) alongside the existing code/notebook set.
- **`grader_grade.py --with-signals`** — inject the evidence block into each pass prompt,
  labeled "priors, NOT the score."
- **`grader_consensus.py`** — emit `conflict_needs_review` from the prior-vs-tier rule table;
  respect each signal's inject/audit/both tag.

## The ceiling (build at the right altitude)

"Rounds out the grader" is true for **decision support**, not autonomy. The stack is only as
complete as the rubric decomposes, the extractors are good, and the LLM's soft-row judgment
holds — and some dimensions (factual correctness of a domain claim, genuine originality)
*neither* layer nails reliably. So the human stays in the loop not as a fallback but as the top
layer. This is the same line cb draws everywhere: *your voice, your judgment.* The honest claim
is the **most complete, most defensible decision-support grader** — it makes the human's call
better and more auditable; it does not replace it.

## Anti-patterns

- **Regex on a judgment row** (insight, synthesis) — misleads; that's the LLM's job.
- **A feature presented as a verdict** — invites over-trust and rewards keyword-stuffing.
- **Hardcoded rubric knowledge** — drifts from the rubric silently.
- **Trimming the corpus to save tokens** — cuts signal, lowers quality. Densify instead.
- **Letting a prior set the score** — the entire architecture exists so it never does.

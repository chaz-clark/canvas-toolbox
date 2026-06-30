# Proposal (RFC): audit-aware redesign via a conventional findings artifact

**Status:** Draft / for discussion (not implemented)
**Date:** 2026-06-30
**Author:** community contribution (agent-assisted)
**Type:** enhancement request — sketch only; no code in this PR

> Filed as a **draft PR** per `.github/CONTRIBUTING.md` ("open a draft PR early … easier to
> course-correct before hours of code than after"). This document is the design discussion; if
> the maintainer accepts the shape, implementation can follow as a separate, test-covered PR.

---

## Context — the gap this addresses

There is **no automatic data flow** from `course_audit.py` into a course *redesign*. There is no
"redesign program" at all: a redesign is an **agent-orchestrated workflow** (read the knowledge
files, run individual tools, reason), documented in
[`course_design_workflow.md`](../course_design_workflow.md). The connection between *"I audited
the course"* and *"I redesigned it"* is carried entirely by the **agent's session memory** of
having run the audit.

That works inside one session, but it's fragile across the seam that matters most:

- A **fresh** agent session asked to *"redesign my course, start with the CLOs"* has **no audit
  context**. It will either silently proceed without the evidence base, redundantly re-run the
  audit, or rely on the operator to say "read `audit.md`."
- The audit's output file (`audit.md` / its `--json`) **persists on disk, but nothing reaches in
  and reads it.** It's inert unless an agent is told to use it.
- Worst case: an agent redesigns course X while an *unrelated or stale* `audit.md` is what's
  lying around — there's no guard tying the audit to the course or to a freshness window.

## Goals

1. Make the audit→redesign handoff **reliable across sessions**, not dependent on one agent's memory.
2. Keep it **honest**: the redesign is still agent-driven judgment (a tool cannot write CLOs); we
   are formalizing a *handoff*, not pretending the redesign is deterministic.
3. **Additive and opt-in** — no change to existing tool behavior or outputs by default.

## Non-goals

- A monolithic `course_redesign.py` that "does the redesign." The redesign is irreducibly
  human-in-the-loop (outcomes, assessments, and rubric language are the instructor's to approve).
- Auto-pushing anything to Canvas. Unchanged: local-files-source-of-truth + confirm-before-write.

---

## Options considered

### Option A (recommended) — conventional machine-readable findings artifact
Have `course_audit.py` *also* write its structured findings to a **well-known, stable path**
(`.canvas/last_audit.json`, already the gitignored runtime dir). Document a convention — in
`AGENTS.md` and `course_design_workflow.md` — that **Flow A (redesign) reads
`.canvas/last_audit.json` first**, validates it matches the target course and is fresh, and only
re-runs the audit if it's absent/stale/mismatched.

- **Pros:** Smallest change; `course_audit.py` already emits `--json`, so this is "persist it to a
  known path." The agent stays the orchestrator (honest), but now has a *conventional* handoff
  instead of session memory. Adds the missing **course-match + staleness guard**.
- **Cons:** Still convention-enforced (an agent must follow the documented behavior) — but that's
  true of every agent step in this toolkit, and the routing-pointer work (#121) is the same shape.

### Option B — a `--with-audit` flag / thin orchestrator
A wrapper that runs the audit, then hands its JSON to the redesign workflow as a structured
"redesign context."

- **Pros:** One command; harder to forget.
- **Cons:** Implies an automated redesign that doesn't (and shouldn't) exist; more code; blurs the
  honest line that the redesign is agent judgment. The audit-running part is one line the agent can
  already do.

### Option C — status quo + docs only
Rely on the agent reading `audit.md` when told (what #124's guide already encourages).

- **Pros:** Zero code.
- **Cons:** Leaves the cross-session gap and the no-staleness-guard failure mode unaddressed.

---

## Sketch of Option A

### 1. Artifact (`.canvas/last_audit.json`)
`course_audit.py` writes this whenever it runs (additive; the human-facing `.md`/`.pdf` are
unchanged). Shape (illustrative — mirrors the existing `--json` composition):

```json
{
  "schema_version": 1,
  "course_id": "415492",
  "run_at": "2026-06-30T17:10:00Z",
  "tier": "full",
  "verdict": "NEEDS_ATTENTION",
  "areas": {
    "rubric_coverage": {"verdict": "needs_attention", "missing": 32, "decorative": 1, "ok": 7},
    "rubric_quality":  {"verdict": "review", "meet": 6, "partial": 2},
    "syllabus":        {"verdict": "incomplete", "sections": "8/9", "missing": ["disclaimers"]},
    "clo_quality":     {"verdict": "meets_criteria", "clos": 4},
    "workload":        {"verdict": "back_loaded"}
  },
  "top_fixes": ["32 assignments missing a rubric", "workload back-loaded", "syllabus: add Disclaimers"]
}
```

### 2. Guard (the part that prevents the worst failure mode)
Before a redesign uses the artifact, the agent checks:
- **course match** — `course_id` equals the course being redesigned (never redesign course X off
  course Y's audit), and
- **freshness** — `run_at` is within a documented window (suggest: warn if > 7 days, since a live
  course's assignments/dates drift).

If absent / mismatched / stale → run `course_audit.py` first. This is the rule the docs encode.

### 3. Documentation changes
- `course_design_workflow.md` → Flow A step A0 becomes: *"read `.canvas/last_audit.json`; if absent,
  stale, or for a different course, run `course_audit.py --full` first."*
- `AGENTS.md` → one line in the existing knowledge-grounding rule pointing at the convention.

### FERPA note
`.canvas/` is already gitignored. The artifact holds **structural** findings only (counts,
verdicts, section names) — no student data — consistent with the audits being read-only and
PII-free. The course id is course-specific and stays in the gitignored runtime dir, never committed.

## Open questions for the maintainer

1. Is `.canvas/last_audit.json` the right home, or should it be keyed per course
   (`.canvas/audit/<course_id>.json`) so multiple courses in one repo don't clobber each other?
   (Leaning per-course.)
2. Freshness window — 7 days, or tie it to "has the course been pushed to since the audit?"
3. Should `clo_quality` in the artifact carry the per-CLO data so the redesign's CLO step can skip
   re-running `clo_quality_audit.py`? (Trade: richer artifact vs. always-fresh re-run.)
4. Is this better as a convention (Option A) or genuinely not worth the surface area (Option C)?

---

*This proposal was drafted while exercising the redesign workflow on a real course and noticing the
audit→redesign handoff is session-memory-mediated. Companion to #121 (routing pointer) and #124
(workflow guide).*

---
name: workload_calibration_knowledge
version: '1.0'
last_updated: '2026-07-16'
description: 'How much gradable work a course asks (volume) and how it''s distributed across the term (density/clustering). Complements cognitive_load (per-task mental load) with the aggregate budget view. Boundaries: per-task load is cognitive_load; the '
skill_type: knowledge
shape: reference
scope: 'How much gradable work a course asks (volume) and how it''s distributed across the term (density/clustering). Complements cognitive_load (per-task mental load) with the aggregate budget view. Boundaries: per-task load is cognitive_load; the term schedule is syllabus; this is the aggregate work distribution. Honest scope: distribution computable from due dates; reading hours NOT reliably knowable from the API.'
consumed_by:
- workload_audit.py
- canvas_course_expert.md
provenance:
  sources:
  - Carnegie unit / U.S. credit-hour norm (~1 hr instruction + ~2 hrs out-of-class per credit per week).
  - Common academic reading rate ~250 words/minute.
  - Course Workload Estimator (Wake Forest; Betsy Barre & Justin Esarey) — estimate student hours from readings + assignments.
companion_json_deprecated: 2026-07-16 - consolidated into YAML frontmatter (JSON purge convention)
runtime_strategy: read_at_runtime
metadata:
  knowledge_id: workload_calibration_knowledge
---

# Workload Calibration — Auditor's Reference

How much work does a course actually ask of students, and is it distributed sanely
across the term? Where `cognitive_load` checks *per-task* mental load, this checks the
*aggregate* load budget — the thing that produces "this course is a death march" or
"weeks 6–8 all pile up at once."

**Sources (public):**
- Carnegie unit / U.S. credit-hour norm: ~1 hour of instruction + ~2 hours of out-of-class work per credit per week (so a 3-credit course ≈ 9 total hrs/week; online courses fold the "instruction" hour into the same ~3 hrs/credit budget).
- Common reading-rate estimate for academic prose: ~250 words/minute (slower for dense/technical text).
- Course Workload Estimator lineage (Wake Forest / Betsy Barre & Justin Esarey) — the standard "estimate student hours from readings + assignments" approach.

---

## The two questions

1. **Volume** — does estimated total student time roughly match the credit-hour budget,
   or is the course over- / under-assigned? (Carnegie: ≈ `credits × 3` hrs/week.)
2. **Distribution** — is the work spread evenly across the term, or does it clump
   (three major deliverables in one week, then nothing)? Clumping is a workload defect
   even when the *total* is reasonable.

## Honest scope (what's computable from the API vs not)

- **Computable now:** the count, type, points, and **due-date distribution** of gradable
  work (assignments/quizzes) across the term; week-by-week clustering; points concentration.
- **Not reliably computable:** exact **reading hours** — readings are usually links or
  file attachments whose word counts the API can't see. So the toolkit audits **work
  *distribution and density*** confidently, and offers only a **rough volume sanity note**
  (assignment count vs. a credits-scaled expectation), not a precise hour budget. Precise
  hour-estimation (the Wake Forest estimator) needs reading word-counts a human supplies.

This is the same evidence-based posture as the other audits: surface what's reliably
measurable (distribution), flag the rest for human review, don't over-claim.

## Audit signals

| Signal | Meaning |
|---|---|
| **Uneven distribution** | One or more weeks carry far more gradable work (or points) than the term average — a clustering/crunch risk. The primary, reliable finding. |
| **Front-/back-loading** | Work concentrated early (weeder pattern) or piled at the end. |
| **Volume sanity (rough)** | Gradable-item count is very high or very low relative to a `credits`-scaled expectation — a prompt to check total time, not a verdict. |
| **No due dates** | Work exists but isn't scheduled — distribution can't be assessed; flag for the instructor to add dates. |

## Audit output

A workload **distribution** report, not a precise hour budget:
- gradable items total + the per-week (or per-bucket) distribution,
- the heaviest bucket vs. the average (the clustering signal),
- points concentration,
- a rough volume sanity note if `--credits` is supplied,
- explicit note that reading hours are not measured.

Verdict `workload` ∈ {`balanced`, `uneven`, `sparse`, `unscheduled`}.

**When to use:** pre-semester, to catch crunch weeks and over/under-assignment before
students hit them. Pairs with `syllabus_audit` (the schedule) and `cognitive_load`
(per-task load — the complement to this aggregate view).

**Consumed by:** `workload_audit.py`, `canvas_course_expert`.

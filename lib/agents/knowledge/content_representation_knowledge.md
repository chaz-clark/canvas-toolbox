---
name: content_representation_knowledge
version: '1.0'
last_updated: '2026-07-16'
description: Surfacing whose voices, authors, and examples a course's content draws on (source material, not structure), so an instructor can judge representation. v0.1 — experimental/unwired.
skill_type: knowledge
shape: reference
scope: 'Surfacing whose voices/authors/examples a course''s content draws on, so an instructor can judge representation. Checks SOURCE material, not structure. Boundaries: structure/scaffolding lives in cognitive_load + course_design_language; outcome/rubric/syllabus quality have their own files. EXPERIMENTAL/UNWIRED — built ahead of an explicit decision to wire it.'
consumed_by:
- content_representation_audit.py
provenance:
  sources:
  - University of Chicago, Chicago Center for Teaching & Integrated Learning. Inclusive Pedagogy (representation of perspectives/scholars).
  - Tatum, B. D. (1997/2017). Why Are All the Black Kids Sitting Together in the Cafeteria? Basic Books.
  - General inclusive-curriculum practice ('diversify the syllabus / cite a range of scholars').
companion_json_deprecated: 2026-07-16 - consolidated into YAML frontmatter (JSON purge convention)
runtime_strategy: read_at_runtime
metadata:
  knowledge_id: content_representation_knowledge
---

# Content Representation — Auditor's Reference

> ⚠️ **v0.1 — EXPERIMENTAL, UNWIRED.** Not yet consumed by `canvas_course_expert`
> or `course_audit`. Built ahead of wiring. The audit *surfaces data for human
> review* — it deliberately does **not** infer anyone's demographics.

A framework for surfacing *whose* voices, authors, and examples appear in a course's
content, so an instructor can judge the representation themselves. Where
`outcomes_quality` / `rubrics` / `syllabus` check the *structure* of a course, this
checks the *sources* it draws on — the inclusive-pedagogy question "who is in the
room, on the page, and in the examples?"

**Sources (public — never the internal PTC manuscript that prompted this):**
- University of Chicago, Chicago Center for Teaching & Integrated Learning. *Inclusive Pedagogy* — representation of perspectives/scholars in course material.
- Tatum, B. D. (1997/2017). *Why Are All the Black Kids Sitting Together in the Cafeteria?* — identity, belonging, whose voices are centered.
- General "diversify the syllabus / cite a range of scholars" inclusive-curriculum practice.

---

## The core idea

Two courses can be structurally identical (clear outcomes, good rubrics, complete
syllabus) yet draw their readings, quoted authorities, worked examples, and case
studies from a narrow or a broad range of voices. Representation is about the
**source material**, not the scaffolding. The auditable artifact question:

> Across this course's content — readings, cited authors, quoted experts, examples,
> case studies — *whose* perspectives appear, and how concentrated are they?

## The evidence-based stance (why the tool surfaces, never scores)

Representation is a **human judgment**, and the toolkit's job is to make it *informed*,
not to make it *for* the instructor. So the audit:

- **Inventories the named sources** it can detect in course content (citation patterns
  like `Author (Year)`, "by …", "according to …", quoted attributions) and presents a
  deduplicated, counted list.
- **Does NOT infer demographic attributes** (gender, ethnicity, etc.) of those names.
  Automated demographic inference is error-prone and ethically fraught; the tool refuses
  to do it. The instructor reviews the surfaced list and makes the representation call.
- Treats the list as **heuristic** — extraction from arbitrary HTML is imperfect; a
  name missed or a false hit is expected. "Not detected" ≠ "not present." (Same posture
  as `rubrics_knowledge` Criterion 1 and `syllabus_knowledge` detection.)

This keeps a genuinely useful surface (an instructor rarely has a consolidated list of
*everyone their course cites*) without the toolkit overstepping into judgments it can't
make reliably or appropriately.

## What it can and can't see (honest scope)

- **Can:** inline citation/attribution patterns in page bodies, assignment descriptions,
  and the syllabus.
- **Can't (today):** authors inside linked PDFs/files, video creators, publisher/LMS
  metadata, or sources named only in external links. A course that delivers readings as
  file attachments will surface little — that's a limitation, not a finding.

## Audit output (what the tool emits)

A **content-source inventory**, not a verdict:
- distinct named sources detected + mention counts,
- which content items each appears in,
- a concentration note (e.g., "N distinct sources across M items"),
- an explicit reminder that this is review data, demographics are not inferred.

**When to use:** when an instructor wants a consolidated view of the voices their course
content draws on, as a starting point for a representation review. Pairs with the
inclusive-/structured-teaching reasoning (Sathy & Hogan) if that knowledge is later added.

**Consumed by:** `content_representation_audit.py` (experimental). NOT wired into
`canvas_course_expert` or `course_audit` yet — promote + wire after real-course exercise
and an explicit decision that the surface is useful and appropriate.

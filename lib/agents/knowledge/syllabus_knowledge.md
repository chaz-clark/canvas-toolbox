# Syllabus Completeness — Auditor's Reference

A framework for evaluating whether a course syllabus is *complete* — whether it
contains the sections a student needs to understand what the course is, how it
works, and what is expected. This is a completeness check, not a prose-quality
judgment: tone, clarity, and "is each outcome actually assessed" are human
judgments, surfaced as advisory data, never as a pass/fail.

> A syllabus is the course's first message to students — a communication channel,
> a planning framework, and an assessment/accreditation artifact. If a required
> section is missing, students are missing something they need.

**Sources:**
- BYU-Idaho Campus Curriculum Development. *Syllabus template* (9 required sections; the concrete anchor profile). `pre_knowledge/byui_learning_teaching/byui_syllabus_guidance.md`.
- BYU-Idaho AI hub. *AI in the Syllabus* — every syllabus must state a generative-AI policy. `byui.edu/ai/academics/ai-in-the-syllabus`; `pre_knowledge/byui_learning_teaching/byui_ai_hub.md`.
- General higher-ed syllabus practice (instructor contact, outcomes, materials, grading, accessibility statement, academic-integrity policy) — broadly consistent across institutional templates.

---

## The completeness checklist (required sections)

The anchor profile is the **BYU-Idaho syllabus template's 9 required sections**.
Most are institution-neutral; the BYUI-specific flavor is flagged.

| # | Section | Contains | Neutral? |
|---|---------|----------|----------|
| 1 | **Instructor Contact Information** | Name, office, office hours, email, phone | ✅ general |
| 2 | **Overview** | Course description, credits, **outcomes**, vision | ✅ general (Vision is BYUI-flavored) |
| 3 | **Requirements** | Prerequisites, materials/texts, technology, **AI policy** | ✅ general |
| 4 | **Structure** | **Learning Model**, key assessments | ⚠️ BYUI (Learning Model) |
| 5 | **Expectations** | Feedback, workload | ✅ general |
| 6 | **Grading** | Grading scale, late-work policy | ✅ general |
| 7 | **Students with Disabilities** | Accommodation / accessibility statement | ✅ general |
| 8 | **University Policies** | Academic honesty / integrity, Title IX, etc. | ✅ general |
| 9 | **Disclaimers** | "Subject to change" / right-to-revise | ✅ general |

## The AI-policy requirement (a first-class gate)

Distinct from the section checklist because it is now an explicit institutional
**requirement**, not a nice-to-have: per BYU-Idaho's AI hub, *"every course syllabus
must include a statement about generative AI use."* The audit treats AI-policy
presence as a required gate that can drive an `incomplete` verdict on its own.

**Two named policy frameworks** a syllabus may use (detection of *which* is advisory):
- **Stoplight Framework** — RED (disallow) / YELLOW (limited use) / GREEN (active application).
- **AI Assessment Scale** — No AI → AI for Ideas → AI for Feedback → AI for Content → AI-Led.

The five free-text option statements (No AI / No AI Content Creation / Cite / Open /
Case-by-Case) trace to James Helfrich; the Stoplight framework is the BYU-I AI Task
Force's. (See `pre_knowledge/byui_learning_teaching/byui_ai_agency.md` for the
detection-vs-declaration evidence base — AI detectors are unreliable, so a clear,
operationalized policy beats policing.)

## Advisory signals (data only — never drive the verdict)

- **Syllabus bloat** (pitfall #1) — including every possible policy makes a syllabus
  hard to navigate; very high word count is a flag, not a failure.
- **Vague expectations** (pitfall #2) and **dry/contractual tone** (pitfall #3) — human
  judgments; out of scope for deterministic detection.
- **Outcomes stated** — are course outcomes present in the syllabus text (the deeper
  "each outcome mapped + assessed" check is human/`outcomes_quality` territory).
- **Learning-Model introduced** — BYUI-specific; whether the BYU-I Learning Model and
  its use are described.

## Detection caveat (evidence-based stance)

Section detection is **keyword-heuristic** on the stripped syllabus HTML. A section
can legitimately exist under an unanticipated heading, so **"not detected" means
*review*, not proven-absent** — the same posture `rubric_quality_audit.py` takes on
Criterion 1. The audit surfaces data for a human decision; it does not certify a
syllabus as deficient.

**When to use:** Pre-semester syllabus completeness check, before or alongside the
rubric/CLO audits. The syllabus is where the CLO → assessment → rubric alignment chain
is *announced* to students.

**Consumed by:** `syllabus_audit.py` (the detection engine; reads `syllabus_body` via
`GET /courses/:id?include[]=syllabus_body`). **Pairs with:** `outcomes_quality_knowledge.md`
(the outcomes named in the syllabus), `rubrics_knowledge.md` (the assessment/rubric end),
`canvas_api_knowledge.md` / `canvas_api_lessons_learned.md` (the API surface).

_Last updated: 2026-05-26 (promoted to v1.0 — validated read-only against real courses)_

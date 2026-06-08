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

---

## v0.2 (2026-06-08) — granular 25-item rubric integration

The BYU-I Academic Office distributes a **Syllabus Completeness Rubric** (faculty-authored 2026) that scores syllabi against **25 specific items** across 11 categories, using a 0/1/2 (missing / thin-uneven / complete) scale. This is *more granular than the 9-section umbrella* and adds checks the original audit missed.

**Why it matters:** the 9-section umbrella catches missing categories but not missing specific items within them. The rubric distinguishes "University Policies present" (umbrella) from "Link to FERPA page present" (specific). Real faculty submissions get scored at this granularity.

### What the rubric adds (over the original 9-section check)

| Category | New specific items | Why distinct |
|---|---|---|
| **Course Information** | Title / Code / Credits / Semester-year / Prerequisites (5 items) | Originally lumped under "Overview". Faculty often miss Credits + specific Semester. |
| **Course Description** | "matches what is in the catalog" | Adds a catalog-alignment check (vs just "description present") |
| **Course Outcomes** | "match what is in the catalog" | Same — alignment, not just presence |
| **Grading and Assessments** | Weighting + Grading Scale + Exams + Projects (4 items) | Originally one umbrella; each is a distinct decision faculty must communicate |
| **Expectations** | Attendance policy (separate from workload) | Workload tells you HOW MUCH; attendance tells you WHAT COUNTS AS PRESENT |
| **AI Usage** | Policy + "right to modify" clause + tips for success | The "right to modify" + "tips for success" are new asks beyond just AI-policy presence |
| **Additional Information** | Link to a page with additional info | New umbrella for course-specific addendum |
| **University Statements & Policies** | Personal Challenges / Disabilities / Sexual Harassment / Student Grievance link / CES Honor Code link / Academic Honesty link / FERPA link / Policy Library link / Copyright disclaimer (9 items) | Original lumped these. Specific LINK presence (vs keyword mention) is what the rubric scores. |

**Total: 25 scored items.** See [`lib/agents/templates/syllabus_completeness_rubric.md`](../templates/syllabus_completeness_rubric.md) for the full rubric template + scoring scale.

### Canonical sources

| Source | URL | Use |
|---|---|---|
| **BYU-I Syllabus Template** | `byui.instructure.com/courses/405800/pages/syllabus-template` (Canvas API accessible with auth) | Verbatim section headings + verbatim University Statements text. Transcribed to [`lib/agents/templates/byui_syllabus_template.md`](../templates/byui_syllabus_template.md). |
| **Syllabus Completeness Rubric** | Faculty-distributed PDF (2026) | The 25-item rubric — transcribed to [`lib/agents/templates/syllabus_completeness_rubric.md`](../templates/syllabus_completeness_rubric.md). |
| **Dean of Students — Syllabus Statements** | https://www.byui.edu/dean-of-students/syllabus-statements | Three required statement texts (Personal Challenges, Accommodations, Sexual Harassment). |
| **AI in the Syllabus** | https://www.byui.edu/ai/academics/ai-in-the-syllabus | Required-gate definition + Stoplight framework + AI Assessment Scale + AI Statement Wizards. |
| **Faculty Guide 3.3 Duties and Opportunities** | `webmailbyui.sharepoint.com/sites/Policies/SitePages/3.3 Duties and Opportunities.aspx` | Auth-required; faculty-side context for syllabus expectations. Not WebFetch-able. |

### Link-presence detection (new in audit)

Five `Other Policies` items are scored on **link presence** (not just keyword mention):

| Item | Detected by |
|---|---|
| Student Grievance link | `byui.edu/student-records/grievance` URL OR "student grievance" + href anchor |
| CES Honor Code link | `churchofjesuschrist.org` or `byui.edu` + "honor code" + href |
| Academic Honesty link | `byui.edu/student-honor-office/academic-integrity` OR "academic honesty" + href |
| FERPA link | `byui.edu/student-records/ferpa-rights` OR "ferpa" + href |
| Policy Library link | `byui.edu/policies` URL OR "policy library" + href |

**Reasoning:** the rubric specifies *link* (not just "policy mentioned"). A syllabus that says "see the FERPA page" without linking it scores 1 (thin); one that includes the URL scores 2 (complete).

### Honest limit: 0 vs 1 vs 2 with a keyword detector

The rubric distinguishes:
- **0** = missing entirely
- **1** = present but thin / uneven
- **2** = complete and clear

A keyword detector can score 0 vs ≥1 reliably (found or not). It **cannot reliably distinguish 1 from 2** — that's a human-judgment call about clarity. The audit surfaces "present once" as a *possibly-thin* signal (advisory), but doesn't auto-assign 1 vs 2. The final score is reported as **N/26 detected** with a per-item table the operator can refine to true 0/1/2 by hand.

---

## Faculty Guide 3.3.1 (canonical BYU-I policy — operator-supplied 2026-06-08)

The BYU-I Faculty Guide §3.3.1 *Syllabus* is the authoritative institutional policy on syllabus requirements. Lives on `webmailbyui.sharepoint.com/sites/Policies/SitePages/3.3 Duties and Opportunities.aspx` (SharePoint, auth-required — couldn't WebFetch; transcribed below from operator-supplied text 2026-06-08):

> **3.3.1 Syllabus**
>
> Faculty members are required to publish a syllabus for each class they teach. The most important function of the syllabus is to help **create a vision for students**. It is the first chance teachers have to help students see *why* the things they will learn in the course matter. As important as other functions of the syllabus are, they should not overshadow this primary purpose of the syllabus as **a persuasive document that motivates students to learn**.
>
> In addition, each syllabus should contain:
> - a course description
> - the anticipated outcomes (which may be established on the department level)
> - a list of materials the students need to purchase
> - grading and attendance policies
> - the final examination schedule
> - information on how and when to contact the instructor
> - an invitation for students with special educational needs to identify themselves in a timely manner
>
> Additionally, a class calendar should either be incorporated into or attached to the syllabus (see 3.3.14 Grades and 3.3.16 Academic Honesty).
>
> Each semester, faculty members keep a record of past syllabi for accreditation and grading disputes. Faculty members should submit paper or electronic copies of electronic syllabi to the Department Chair each semester for long-term storage and access (see 3.3.15 Records Retention).

### What 3.3.1 adds beyond the 25-item rubric

The Syllabus Completeness Rubric (faculty-distributed PDF, transcribed at `templates/syllabus_completeness_rubric.md`) is the *scoring framework*; 3.3.1 is the *policy*. The two largely overlap but 3.3.1 surfaces two things not as explicit in the rubric:

1. **"Persuasive document that motivates students to learn" / "create a vision for students"** — this is the *primary purpose* of the syllabus per BYU-I policy, ahead of every checklist item. The audit's tone-quality signals are out of scope for deterministic detection, but this framing belongs in the operator-facing audit output as advisory context: a complete-but-bureaucratic syllabus may still fail this primary test, which is a *human judgment* the audit does not make.
2. **"Final examination schedule"** specifically (not just "Exams present"). The current rubric item *Exams (if applicable)* covers presence; the 3.3.1 requirement is for an actual **schedule**. Audit-side: could add a sub-detection for date/time language near exam mentions in a future enhancement; for now this is a manual-review item the rubric covers under *Exams*.
3. **Class calendar** must be either incorporated or attached. The current rubric covers this under *Main Course Assignments* (topics, reading assignments, descriptions). Operators using canvas-toolbox can additionally generate the calendar artifact via `lib/tools/course_map_build.py` (v0.30.0+), which produces the per-week schedule the syllabus can attach.

### Cross-walk: 3.3.1 required elements → 25-item rubric

| 3.3.1 requirement | Rubric item(s) that cover it | Gap? |
|---|---|---|
| Course description | Course Description / catalog alignment | ✅ |
| Anticipated outcomes | Course Outcomes / catalog alignment | ✅ |
| Materials to purchase | Materials | ✅ |
| Grading policy | Weighting + Grading scale | ✅ |
| Attendance policy | Attendance | ✅ |
| **Final examination schedule** | Exams (if applicable) | ⚠ *covers presence, not schedule explicitly* |
| **Instructor contact** | (umbrella 9-section audit catches this; **NOT in the 25-item rubric**) | ⚠ *rubric gap — umbrella covers* |
| Invitation for special educational needs | Accommodations for Students with Disabilities | ✅ |
| Class calendar | Main Course Assignments (topics covered) | ⚠ *implicit — could be explicit* |
| Records retention (process, not content) | (not a syllabus-content check) | n/a |

### Implication for the audit

Two minor enhancements worth tracking (parking-lot-grade, not blocking):

1. **Add "Instructor contact" as a 26th rubric item** — would close the gap between the rubric and FG 3.3.1. The umbrella audit already detects it, so the data is available; just needs to be surfaced as a per-item score in `--rubric` mode.
2. **Add a "Vision / motivation" advisory signal** — heuristic detection of *why-the-course-matters* language (verbs like *prepare you to*, *equip*, *empower*, *will help you*). Not pass/fail (per the existing evidence-based stance); just a data signal to remind operators the rubric scores *what's present*, not *whether it motivates*.

Both would be backward-compatible additions to `lib/tools/syllabus_audit.py`. Filed for the next syllabus-audit iteration.

### Source attribution

- **Operator-supplied verbatim text:** Chaz, 2026-06-08 (after the canvas-toolbox v0.31.0 commit identified the SharePoint URL as auth-gated). The verbatim block above is the authoritative source for what this knowledge file's policy claims rest on.
- **SharePoint URL** (for re-verification by authorized users): `webmailbyui.sharepoint.com/sites/Policies/SitePages/3.3 Duties and Opportunities.aspx`.

_Last updated: 2026-06-08 (v0.2.1 — Faculty Guide 3.3.1 verbatim block + cross-walk to 25-item rubric)_

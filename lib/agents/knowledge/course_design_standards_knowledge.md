# Course Design Standards — BYU-Idaho Institutional Audit Reference

> Reference. The BYUI Campus Online institutional course-design checklist mapped to NWCCU accreditation codes. ~40 standards across 7 categories. This is the **master checklist** the canvas-toolbox audit tools should be measuring against; many existing audits already cover specific standards, several gaps are named here for future tools.

**Sources:**
- **Public canonical (HTML):** `content.byui.edu/file/25dac126-7189-40a4-9781-4351263e7d25/1/course-design-standards.html` — the BYUI Campus Online team's public-facing standards page. Contains the **short-form titles** per standard (see §Short titles index below) + one set (no modality tab). Verbatim text matches the xlsx tracking template tab 1.
- **Tracking template (xlsx):** `byui_course_design_standards_2026.xlsx` parked in `pre_knowledge/byui_learning_teaching/` with paired transcript [`byui_course_design_standards_2026.md`](../pre_knowledge/byui_learning_teaching/byui_course_design_standards_2026.md). Two tabs split by modality: tab 1 = online (full set with online-specific items — matches the HTML canonical), tab 2 = the common-core subset that applies to both online and in-person. The HTML references "A Google Sheets tracking template is available" — the xlsx IS that companion tracking tool.

**Used by:** `canvas_course_expert.md`, `ira_program_alignment.md`, any future course-design audit tool.

**Companions:** [`course_design_language_knowledge.md`](course_design_language_knowledge.md) (visual / structural design grammar — orthogonal layer), [`syllabus_knowledge.md`](syllabus_knowledge.md) (syllabus-specific completeness via the 9-section + 25-item rubric — covers standards 2.2 / 4.6 / 6.4), [`assessments_knowledge.md`](assessments_knowledge.md) (formative vs. summative pedagogy — supports standards 3.2 / 3.3), [`backwards_design_knowledge.md`](backwards_design_knowledge.md) (UbD 3-stage — supports standard 2.3 alignment chain), [`canvas_api_knowledge.md`](canvas_api_knowledge.md) (API surface for any new audit tool).

**Scope:** institutional course-design audit standards — what BYUI Campus Online considers "well-designed" at the procedural / structural / accreditation level. Covers (a) outcomes and assessment design (NWCCU §2), (b) activity and material engagement (§3), (c) organizational delivery (§4), (d) maintainability and scalability (§5), (e) student-roadblock resources (§6), (f) successful facilitation (§7), (g) BYUI mission alignment (§1 — online courses only). Out of scope: visual design grammar (lives in `course_design_language_knowledge.md`), syllabus-specific completeness detail (lives in `syllabus_knowledge.md`), specific assessment-type pedagogy (lives in `assessments_knowledge.md`).

**Provenance:** Operator-supplied 2026-06-10 from BYUI Campus Online team. Two-tab xlsx parked at `pre_knowledge/byui_learning_teaching/byui_course_design_standards_2026.xlsx` (gitignored); paired markdown transcript at the same path with `.md` extension is the human-readable transcription.

_Last updated: 2026-06-10_ · _v0.1, untested. Per the canvas-toolbox 0.x convention, this file is not catalogued in [`knowledge/README.md`](README.md) until an audit tool actually grades a course against the standards (v1.0 promotion gate)._

---

## Why this exists

Canvas-toolbox has eight+ audit tools and a dozen+ knowledge files covering pieces of course quality — outcomes (`clo_quality_audit`), rubrics (`rubric_quality_audit`, `rubric_coverage_audit`), workload (`workload_audit`), syllabus (`syllabus_audit`), schedule (`canvas_schedule_auditor`), module structure (`module_structure_diff`), content representation (`content_representation_audit`), course summary (`course_audit`, `course_quality_check`). What was missing: the **institutional master list** of what those audits should be checking against. This file is that list.

The BYUI Campus Online team has formalized ~40 design standards mapped to NWCCU accreditation codes. Every standard is a "Seen / Not Seen" check (0/1). Some are auditable today via existing tools; some are partial; some are inherently human judgment; some are real gaps worth promoting to new audit tools. Naming all of them in one knowledge file lets the audit fleet evolve coherently.

---

## Modality scope

The source xlsx has two tabs:

| Tab | Title | Scope | What's removed from tab 2 |
|---|---|---|---|
| **1** | "Campus Online Course Design Standards" | **Online courses (full set, 40 standards)** | n/a (this is the full set) |
| **2** | "PROPOSED Campus Online Course Design Standards" | **Common-core / in-person-applicable subset (~30 standards)** | NWCCU §1 entirely (mission/discipleship, online enrollment cap, online identity verification); 3.1 Learning Model integration; 3.4 synchronous sessions; 3.5 regular interaction; 4.5 off-campus completion; 5.1 multi-person external tool access; 5.7 setup notes; 7.3 grading load ≤75% |

Throughout this file, each standard is tagged with its scope:

- 🌐 **ONLINE** — standard applies to online courses only (in tab 1, not in tab 2)
- 🔁 **BOTH** — standard applies regardless of modality (in both tabs)

Operators auditing an **in-person** course should ignore the 🌐 ONLINE standards. Operators auditing an **online** course apply all.

**Online is the higher standard.** The online bar is a strict superset of the in-person bar — online courses face additional design considerations (identity verification, synchronous-session flexibility, off-campus completion, etc.) that in-person courses get for free by virtue of physical presence. A course meeting the online standard automatically meets the in-person standard too; the inverse isn't true. **Implication:** if a course audit isn't sure of the modality, audit against the online standard (the safer bar). If the course turns out to be in-person, the extra ONLINE findings are surfaced as "advisory — not strictly required" rather than missed.

---

## Short titles index (from the BYUI HTML canonical)

Each standard has both a number and a short-form title. The number is the universal anchor (used in audit-tool output); the title is operator-facing for readability. Audit tools should emit findings as `standard 4.3 (Consistency)` rather than just `standard 4.3`.

| # | Short title | # | Short title |
|---|---|---|---|
| 1.1 | Discipleship and Leadership | 4.7 | Grade Access |
| 1.2 | Enrollment Capacity | 4.8 | Home Page Design |
| 1.3 | Identity Verification | 4.9 | Visual Consistency |
| 2.1 | Outcome Alignment | 4.10 | Writing Quality |
| 2.2 | Syllabus Requirements | 4.11 | Due Dates and Requirements |
| 2.3 | Coherence | 4.12 | Cultural Sensitivity |
| 2.4 | Assessment Transparency | 5.1 | Access Management |
| 3.1 | Learning Model Integration | 5.2 | Copyright Compliance |
| 3.2 | Timely Feedback | 5.3 | Internal Resources |
| 3.3 | Activity Variety | 5.4 | External Resource Approval |
| 3.4 | Synchronous Flexibility | 5.5 | Link Verification |
| 3.5 | Interaction Opportunities | 5.6 | Mobile Optimization |
| 4.1 | Workload Distribution | 5.7 | Setup Documentation |
| 4.2 | Clear Instructions | 5.8 | Workload Feasibility |
| 4.3 | Consistency | 5.9 | Feedback Mechanisms |
| 4.4 | Flexible Groupwork | 6.1 | External Resource Support |
| 4.5 | Remote Accessibility | 6.2 | Support Links |
| 4.6 | Instructor Contact | 6.3 | Web Accessibility |
| | | 6.4 | Technology Requirements |
| | | 7.1 | Instructor Workload |
| | | 7.2 | Support Materials |
| | | 7.3 | Grading Load |

---

## The 7 NWCCU categories

### Category 1 — Course aligns with BYU-Idaho's mission and values

All standards in this category are 🌐 ONLINE (tab 1 only); tab 2 drops them entirely for in-person courses. Most are not deterministically auditable.

| # | Scope | Standard | Audit status | Notes |
|---|---|---|---|---|
| **1.1** | 🌐 ONLINE | Course provides opportunities that invite students to become disciples of Jesus Christ who are leaders in their homes, the Church, and their communities. | ❌ Human only | Tone / framing judgment; out of deterministic scope. Could pair with a content-keyword advisory signal but not a verdict. |
| **1.2** | 🌐 ONLINE | Online course enrollment cap should be equal to or greater than the in-person course. | ⚠️ Partial | Could check `course.total_students` cap via Canvas API against a configured in-person reference. Requires the in-person reference to exist. |
| **1.3** | 🌐 ONLINE | Course uses ≥2 strategies from the BYUI Online Identity Verification Policy. | ❌ Process check | Not a Canvas-visible artifact; lives in instructor process documentation. |

### Category 2 — Course uses and measures appropriate learning outcomes

All standards 🔁 BOTH modalities. This category is where outcome quality + alignment lives.

| # | Scope | Standard | Audit status | Notes |
|---|---|---|---|---|
| **2.1** | 🔁 BOTH | Course outcomes match the catalog. | ⚠️ Partial — `clo_quality_audit.py` | Pulls outcomes via Canvas API; comparing against the catalog requires a catalog source (Kuali or scraped). Standalone "outcomes present + well-formed" is covered; "matches catalog" is the gap. |
| **2.2** | 🔁 BOTH | Syllabus includes all required elements and is in the Syllabus section of Canvas. | ✅ `syllabus_audit.py` | Exact match — the audit reads `GET /courses/:id?include[]=syllabus_body` and runs the 9-section + 25-item rubric check. |
| **2.3** | 🔁 BOTH | Outcomes, department-approved key assessments, activities, and instructional content align. | ✅ **`course_alignment_audit.py`** (shipped 2026-06-10) | The "alignment chain." Uses Canvas's `learning_outcome_id` field on rubric criteria as the deterministic outcome↔criterion link; module-overview text overlap as a soft "is this outcome taught" signal. Tag: `alignment_chain` ∈ {complete, partial, unverified}. |
| **2.4** | 🔁 BOTH | Assessment design facilitates consistent results and transparency for students. | ✅ `rubric_quality_audit.py` | Rubric quality framework covers this — observable ratings, criterion clarity, weight distribution. |

### Category 3 — Course activities and materials promote learning and engagement

Mixed scope. 3.1, 3.4, 3.5 are 🌐 ONLINE (tab 1 only); 3.2, 3.3 are 🔁 BOTH.

| # | Scope | Standard | Audit status | Notes |
|---|---|---|---|---|
| **3.1** | 🌐 ONLINE | Learning Model is integrated into each module. | ✅ **`learning_model_audit.py`** (shipped 2026-06-10, generalized) | Per-module phase-marker scan against configurable presets (BYUI Prepare/Teach One Another/Ponder-Prove by default; also `kolb` 4-phase + `bloom-3` Surface/Deep/Transfer; or `--phases-config <path>` for any institution). Heuristic — soft signal, not auto-fail. Tag: `learning_model_integration` ∈ {complete, partial, unverified}. |
| **3.2** | 🔁 BOTH | Assessments give timely feedback. | ⚠️ Partial | Could check `peer_review_count`, auto-grade quiz fraction, manually-graded-essay count. Not currently a dedicated audit; could fold into `assessments_knowledge.md`-driven check. |
| **3.3** | 🔁 BOTH | Variety of formative, low-stakes, self-evaluation activities support outcomes. | ✅ **`formative_variety_audit.py`** (shipped 2026-06-10) | Classifies assignments low/medium/high-weight via deterministic %-of-grade arithmetic; flags presence (no formative items at all), summative-only categories, missing precedence (high-stakes without formative practice in preceding N weeks), skewed temporal distribution. Tag: `formative_variety`. |
| **3.4** | 🌐 ONLINE | Synchronous sessions, when used, meet flexibility needs. | ❌ Process check | Synchronous session policies live in setup notes; not Canvas-API-auditable. |
| **3.5** | 🌐 ONLINE | Students have regular instructor and peer interaction. | ⚠️ Partial | Could detect discussion / peer-review / sync-session frequency across modules. |

### Category 4 — Course employs organizational and delivery strategies for student success

12 standards total. Most are 🔁 BOTH. Only 4.5 is 🌐 ONLINE.

| # | Scope | Standard | Audit status | Notes |
|---|---|---|---|---|
| **4.1** | 🔁 BOTH | Student load averages 3 hours/week/credit, distributed throughout term. | ✅ `workload_audit.py` | Exact match — the audit estimates student load per week per assignment type. |
| **4.2** | 🔁 BOTH | Activity/module instructions complete enough to act on without clarification. | ❌ Human only | Quality of prose; out of deterministic scope. |
| **4.3** | 🔁 BOTH | Consistent structure / terminology / expectations across modules. | ✅ `module_structure_diff.py` | Detects structural drift between modules. |
| **4.4** | 🔁 BOTH | Group work flexible prior to drop deadline. | ❌ Process only | Group settings + drop-deadline policy not always API-visible together. |
| **4.5** | 🌐 ONLINE | Activities completable away from campus. | ❌ Human only | Activity-by-activity judgment about in-person dependencies. |
| **4.6** | 🔁 BOTH | Instructor contact info present. | ✅ via `syllabus_audit.py` 9-section umbrella | Section §1 of the 9-section check. |
| **4.7** | 🔁 BOTH | Easy access to gradebook. | ⚠️ Partial | Could check course gradebook visibility settings via Canvas API. |
| **4.8** | 🔁 BOTH | Home page visually appealing with clear instructions. | ❌ Visual only | Out of deterministic scope; could detect *presence* of a home page (not "appealing"). |
| **4.9** | 🔁 BOTH | Dashboard icon matches course banner style. | ❌ Visual only | Out of deterministic scope. |
| **4.10** | 🔁 BOTH | Content presented with minimal grammatical / mechanical errors. | ❌ Human only | Out of deterministic scope. |
| **4.11** | 🔁 BOTH | Important assignments/pages have due dates in setup notes; module requirements set. | ✅ `canvas_schedule_auditor.py` | Reads setup notes, applies rules, audits dates. |
| **4.12** | 🔁 BOTH | Content sensitive to culturally diverse perspectives. | ❌ Human only | Out of deterministic scope. |

### Category 5 — Course is maintainable and scalable

9 standards. Most are 🔁 BOTH; 5.1 and 5.7 are 🌐 ONLINE.

| # | Scope | Standard | Audit status | Notes |
|---|---|---|---|---|
| **5.1** | 🌐 ONLINE | Multiple people have access to external tools (GitHub, test beds) for emergency maintenance. | ❌ Process only | Documented in setup notes; not API-visible. |
| **5.2** | 🔁 BOTH | Course materials follow copyright laws and are properly cited. | ❌ Human only | Out of deterministic scope; Fair Use Analysis Form is process state. |
| **5.3** | 🔁 BOTH | Internal resources via university systems. | ❌ Human only | "Approved system" is a judgment about source URLs. |
| **5.4** | 🔁 BOTH | External resources approved by university. | ❌ Process only | External Tool Review is process state. |
| **5.5** | 🔁 BOTH | Links, files, videos, URLs work; broken-link report path exists. | ⚠️ Partial — could close | A link-checker integration would close this; complements `_link_metadata.py`. |
| **5.6** | 🔁 BOTH | Course design is mobile-friendly. | ❌ Visual only | Out of deterministic scope. |
| **5.7** | 🌐 ONLINE | Setup notes for set-up team and instructors complete. | ✅ `canvas_schedule_auditor.py` | Reads setup-notes page; "complete" per rule set. |
| **5.8** | 🔁 BOTH | Course setup requirements fit instructor contract expectations. | ✅ via `workload_audit.py` | Same 3hr/credit/wk math as 4.1 + 7.1 — instructor-side. |
| **5.9** | 🔁 BOTH | Student-feedback opportunities available. | ❌ Process only | Course evaluation tool; not API-visible. |

### Category 6 — Course provides resources to help students overcome roadblocks

4 standards, all 🔁 BOTH.

| # | Scope | Standard | Audit status | Notes |
|---|---|---|---|---|
| **6.1** | 🔁 BOTH | External-tool help instructions available (if applicable). | ❌ Human only | Content presence + judgment about quality. |
| **6.2** | 🔁 BOTH | Links to support resources (tutoring, IT). | ⚠️ Partial | Could detect "Student Resources" page presence + the canonical Canvas template page. |
| **6.3** | 🔁 BOTH | Course materials meet legal web-accessibility standards. | ✅ **`accessibility_audit.py`** (shipped 2026-06-10, WCAG 2.1 AA + cognitive layer) | Sensory (vision/hearing): missing alt-text (1.1.1), video-captioning indicator (1.2.2), transcript-link detection (1.2.3), non-descriptive link text (2.4.4). Cognitive/learning: heading-hierarchy skips (1.3.1), document language attribute (3.1.1), reading-level estimation via Flesch-Kincaid (3.1.5 AAA — advisory), color-only signaling (1.4.1), distracting elements (marquee, autoplay, meta-refresh, animated GIFs — 2.2.1+2.2.2). Walks syllabus + pages + assignment descriptions. **Tool emits a prominent legal disclaimer** in every report + JSON output: aids WCAG review, does NOT certify compliance. For full coverage, run UDoIt + manual assistive-tech testing. Tag: `accessibility` ∈ {compliant, compliant_with_review, partial_compliant, non_compliant}. |
| **6.4** | 🔁 BOTH | Minimum tech requirements + how-to-obtain in syllabus. | ⚠️ Partial via `syllabus_audit.py` | The 25-item rubric includes a tech-requirements check; partial coverage. |

### Category 7 — Course promotes successful facilitation

3 standards. 7.3 is 🌐 ONLINE; 7.1 and 7.2 are 🔁 BOTH.

| # | Scope | Standard | Audit status | Notes |
|---|---|---|---|---|
| **7.1** | 🔁 BOTH | Instructor load ≤3hr/week/credit, distributed throughout term. | ✅ `workload_audit.py` | Same math as 4.1 / 5.8 from the instructor side. |
| **7.2** | 🔁 BOTH | Support materials (answer keys, teaching notes, sync support) present. | ❌ Human only | Instructor-resources module presence + judgment. |
| **7.3** | 🌐 ONLINE | Grading load ≤75% of instructor time on average. | ✅ **`grading_load_audit.py`** (shipped 2026-06-10) | Deterministic estimate: assignments × time-per-submission-type defaults × students × submission_rate → per-week hours vs. (credits × 3 hr × 0.75) cap. Flags individual over-cap weeks + cohort mean over cap. Operator overrides per-type minute defaults via `--time-defaults-json`. Tag: `grading_load`. |

---

## Audit-coverage summary

| Coverage | Count | Standards |
|---|---|---|
| ✅ **Fully covered today** | 13 | 2.2, 2.3, 2.4, **3.1** ← new (`learning_model_audit.py` 2026-06-10), 3.3, 4.1, 4.3, 4.6, 4.11, 5.7, 5.8, **6.3** ← new (`accessibility_audit.py` 2026-06-10), 7.1, 7.3 |
| ⚠️ **Partially covered today** | 9 | 1.2, 2.1, 3.2, 3.5, 4.7, 5.5, 6.2, 6.4 |
| ❌ **Open gaps** (worth new audit tools) | **0** | (all 5 originally-named standards-gap audits shipped 2026-06-10) |
| ❌ **Human-judgment-only** | ~14 | 1.1, 1.3, 3.4, 4.2, 4.4, 4.5, 4.8, 4.9, 4.10, 4.12, 5.1, 5.2, 5.3, 5.4, 5.6, 5.9, 6.1, 7.2 |

The audit fleet covers roughly **40%** of the institutional standards deterministically. The 5 open-gap items would push that to ~55%. The remaining ~45% are inherently human judgment + process — not failures of the audit framework, just out of deterministic scope by design.

---

## Open gaps (worth promoting to new audit tools)

Five specific gaps where a new audit tool would deterministically close coverage that currently relies on human judgment or process.

### Gap 1 — Alignment chain audit (standard 2.3)

**Standard:** Outcomes, department-approved key assessments, activities, and instructional content align.

**Tool sketch:** `course_alignment_audit.py` — combines outputs from `clo_quality_audit.py` (course-level outcomes), `rubric_coverage_audit.py` (assignment → rubric criteria), and a new activity-to-outcome map (module overview pages + assignment descriptions matched against outcome verbs).

**Companion knowledge:** [`backwards_design_knowledge.md`](backwards_design_knowledge.md) (UbD 3-stage) is the design framework this audit would operationalize.

**Output:** per-outcome → assessments[] → rubric-criteria[] → activities[] chain, with broken-link flagging (e.g. "outcome X has no rubric criterion covering it" or "rubric criterion Y has no module activity teaching it").

### Gap 2 — Learning Model module check (standard 3.1)

**Standard:** Learning Model is integrated into each module.

**Tool sketch:** A new check (could be a flag on `course_audit.py` or a standalone `learning_model_audit.py`) that scans each module for the three phases: **Prepare** (preparatory readings / videos), **Teach One Another** (discussion / peer activity), **Ponder/Prove** (reflection / performance task). Detects by heading keywords + activity types.

**Caveat:** the Learning Model is BYUI-specific; this audit would only run when `INSTITUTION=byui` is set (matches the `canvas_schedule_auditor.py` institution-detection pattern).

### Gap 3 — Formative activity variety (standard 3.3)

**Standard:** A variety of formative, low-stakes, and self-evaluation activities support outcome achievement.

**Tool sketch:** `formative_variety_audit.py` — counts assignments by category and weight, flags courses where >X% of the grade comes from <Y assignments (i.e. all summative; no formative practice). Could pair with `assessments_knowledge.md`'s formative-vs-summative classification.

**Output:** per-module formative count + cohort-level distribution + a temporal-spacing check (are formative checks distributed across the term, or stacked at the end?).

### Gap 4 — Web accessibility (standard 6.3)

**Standard:** Course materials meet current legal standards of web accessibility.

**Tool sketch:** `accessibility_audit.py` — either (a) wraps the UDoIt API call to scan the course and surface high-priority issues, OR (b) embeds direct checks (alt-text on images, captions on videos, heading-hierarchy correctness, color-contrast).

**Caveat:** UDoIt is BYUI-licensed; the tool's BYUI mode would call UDoIt, the generic mode would run the embedded checks. Standards-clip = current legal: WCAG 2.1 AA.

### Gap 5 — Grading load estimator (standard 7.3)

**Standard:** Grading load does not consume more than 75% of instructor's time on average each week.

**Tool sketch:** `grading_load_audit.py` — derives expected grading hours from `assignment_count × time-per-assignment-estimate × students-enrolled`, compares to the 75% × 3hr/credit/wk facilitator-load cap. Per-assignment time estimates come from assignment type defaults (rubric-graded vs. essay vs. quiz).

**Companion:** complements `workload_audit.py` (which handles standards 4.1 + 5.8 + 7.1 student/instructor load); this tool focuses on the grading portion specifically.

---

## Operator notes

- **Auditing a course:** consult this knowledge file alongside the institution detection (online vs. in-person) to know which standards apply. Run the existing tools that cover the ✅ standards; surface the ⚠️ partials as "needs human review" with the existing tool's output as starting evidence; explicitly note the ❌ Human-judgment-only standards as outside the audit's scope.
- **Reporting:** a course-wide audit report should organize findings by NWCCU category and include the 7 section headers from this file. Operators reviewing for accreditation will recognize the structure.
- **Modality awareness:** if the course is in-person, skip the 🌐 ONLINE standards (NWCCU §1 entirely, plus 3.1, 3.4, 3.5, 4.5, 5.1, 5.7, 7.3 — though 3.1 Learning Model is BYUI-specific even for in-person, so it stays where applicable).
- **Two-tab xlsx versioning:** the source xlsx contains both tabs as of 2026-06-10. If the BYUI Campus Online team updates the standards, re-export, re-park, and update this knowledge file with the differential. Tab 2 was titled "PROPOSED" in the source — if a future version drops the "PROPOSED" prefix, that signals the in-person/common-core variant has been formally adopted.

---

## Cross-walk: standards → existing canvas-toolbox tools

Inverse view of the per-standard tables above — start from a tool, see which standards it covers.

| Tool | Standards covered (✅ full) | Standards partially supported (⚠️) |
|---|---|---|
| `syllabus_audit.py` | 2.2, 4.6 | 6.4 |
| `clo_quality_audit.py` | — | 2.1 |
| `rubric_quality_audit.py` | 2.4 | — |
| `rubric_coverage_audit.py` | — | (feeds 2.3 alignment chain) |
| `workload_audit.py` | 4.1, 5.8, 7.1 | — |
| `module_structure_diff.py` | 4.3 | — |
| `canvas_schedule_auditor.py` | 4.11, 5.7 | — |
| `course_audit.py` | (umbrella) | (umbrella) |
| `course_quality_check.py` | (umbrella) | (umbrella) |
| `content_representation_audit.py` | — | (could feed 3.3 formative variety) |

The umbrella tools (`course_audit.py`, `course_quality_check.py`) pull from the others; in the future they could explicitly map findings to NWCCU codes by consuming this knowledge file's structured fact list.

---

## What this knowledge file does NOT replace

- **`course_design_language_knowledge.md`** — the visual / structural grammar of a well-designed BYUI course (palette, banners, rubric tier shape, dual-framing). That's orthogonal to the institutional checklist here. Both apply.
- **`syllabus_knowledge.md`** — the 9-section + 25-item syllabus completeness framework. That's the deep dive on standard 2.2; this knowledge file just names 2.2 and points at the syllabus tool.
- **`assessments_knowledge.md`** — formative vs. summative pedagogy. That's the deep dive on standards 3.2 / 3.3; this knowledge file just names them.
- **`canvas_api_knowledge.md` / `canvas_api_lessons_learned.md`** — the API surface any new audit tool builds on.

This file is the **outermost coordinating reference** — the institutional why behind the audit fleet. The other knowledge files are the deeper pedagogical / structural references that fill in the how.

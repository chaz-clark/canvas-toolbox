---
name: course-map-from-canvas-pass-1-lessons
description: Lessons learned from building the BYU-I Architects-of-Learning "Course Map & Schedule" report from Canvas data. v0.1 captured ITM 327 Pass 1 (eight iterations); v0.2 (2026-06-06) added 11 lessons from comparing against a second filled exemplar (buddy's Construction Mgmt course). Covers extraction patterns, gap-analysis architecture, pedagogy vocabulary, class-cadence detection, AI-vs-faculty content boundaries, and operator-workflow defaults.
version: "0.2"
author: chaz-clark
license: MIT
metadata:
  repo: canvas-toolbox
  surfaced: "2026-06-05 — ITM 327 Course Map Pass 1 (8 iterations, v1 → v8)"
  v02_surfaced: "2026-06-06 — comparison against buddy's filled Course Map AoL.xlsx (Construction Mgmt Adv Estimating); 11 new lessons; script bumped to v11"
  binds-to: parkinglot.md "Course-Map Audit tool" entry; future Course Map asks
  related: lib/agents/knowledge/canvas_api_lessons_learned.md (L12 enrolled-course guard; L13 orphan-slug; syllabus_body extraction)
---

# Course-Map-from-Canvas — what we learned in Pass 1

## Context

A BYU-Idaho faculty member needs to fill the *Architects of Learning* `Course_Map_With_PLO.xlsx` workbook for their course. The workbook has 5 sheets (Outcomes + Assessment Strategy / At-a-Glance / Per-Module Details / Semester Schedule / Bloom Dropdown Data) and the assignment rubric scores 5 criteria (Map Alignment / Scaffolding / Calendar Completeness / Pacing Reflection / Organization).

Pass 1 was the operator's actual ITM 327 submission build (8 versions, 2 days). What follows is what an agent should know **before** picking up the same task for another course.

---

## Architecture lessons

### 1. Template-first, fill-second. Always.

The first valuable artifact is a **BLANK template** with placeholders for every Excel element — saved out as its own file. This:

- Proves 100% workbook coverage independent of any course (the operator can audit *before* you touch Canvas).
- Is reusable across courses with no Canvas dependency.
- Makes gaps visible at the structural level, separately from data-side gaps.

The fill is the **second** artifact, layered on top. Same renderer, different mode (`emit_report(data=None)` vs `emit_report(data=dict)`). One source of truth for structure.

**Don't:** start by pulling Canvas data and shaping a report around it. The template never gets validated against the workbook in that flow, and you end up retrofitting columns the operator's Excel actually needs.

### 2. Faculty already author the editorial layer. The tool scaffolds, never replaces.

The operator brought 14 weeks of Lesson Topics, 5 condensed CLOs (a *revision* of the syllabus's 9), 5 hand-rolled assessment families, manual CLO mappings (`1,3` for DAGS Milestones), and seed prose for Architect's Analysis + Assessment Strategy. **Canvas cannot reproduce any of this** — it is the editorial work the rubric is actually grading.

What Canvas CAN provide: structure (modules, assignments, due-dates, syllabus LOs, page bodies), heavy-week math, MLO heuristic extraction. **What it cannot:** condensation rationale, family-rollup labels, AI-opp/AI-vuln per assessment, lesson-topic phrasing, reflection voice.

**Pattern:** scaffold the structure → fill the data → surface gaps → preserve operator's editorial layer wherever it exists.

### 3. Multi-iteration is the norm, not a failure mode

ITM 327 went through 8 versions to converge. Every iteration was valid:

- v1: initial Canvas pull, suggested-shape MD
- v2: re-shaped to template-mirror per operator request
- v3: pivoted to rubric-aligned flow with operator's "use all info but flow it well" guidance
- v4: fixed week-mapping bug (Master `start_at=None` → use W## prefix instead)
- v5: split BLANK template + ITM327-filled as two phases
- v6: pulled syllabus LOs + Canvas-only fill + Gap Analysis section
- v6.1: dropped PLO columns (catalog harvest non-standard)
- v7: AI-drafted all non-Canvas content + side-by-side AI-vs-Excel gap
- v8: merged submission draft (operator wins on editorial; AI wins on differentiation)

**Don't:** try to one-shot this. Surface the structure, the data pull, the gaps, the AI drafts, the merge as separate decisions. Each one needs operator input.

---

## Data-extraction lessons

### 4. Master courses often have `course.start_at = None`. Use W## prefix instead.

ITM 327's Master course (Canvas id `402262`) had `start_at` and `end_at` both null. Due-date math anchored on `start_at` returned `None` for every assignment, producing an all-zeros heavy-week table in v3 — a real bug that only showed up after rendering.

**Reliable signals, in order of priority:**

1. **`W##` prefix in assignment name** (e.g., `W01 DAG Demo 1`, `W14 Peer Audit`). Covered 43 of 44 published assignments for ITM 327. The W## is the canonical signal because operators name assignments by week-of-course on Master.
2. **Earliest published `due_at`, walked back to Monday** as a derived `course_start_dt`. Works when (1) doesn't match — `Your Grade` and similar utility assignments don't have W## prefixes.
3. **Module position** (1-indexed). Last resort; only useful when modules carry `W##` or `Sprint #` in their names.

Code pattern:
```python
_WK_NAME_RE = re.compile(r"^W(\d{1,2})\b", re.IGNORECASE)

def week_of_assignment(a, start_dt):
    m = _WK_NAME_RE.match((a.get("name") or "").strip())
    if m:
        wk = int(m.group(1))
        if 1 <= wk <= 14: return wk
    if not start_dt: return None
    due = a.get("due_at")
    if not due: return None
    d = datetime.fromisoformat(due.replace("Z", "+00:00"))
    return (d - start_dt).days // 7 + 1
```

### 5. CLOs live in `course.syllabus_body`, after a "Learning Outcomes" header

Canvas API call: `GET /courses/{id}?include[]=syllabus_body`. The HTML body of the syllabus is searchable for a "Learning Outcomes" / "Course Outcomes" header, followed by a numbered list of verb-led sentences. Stop on the next major heading (`Required Resources`, `Textbook`, `Grading`, `Policies`, `Assessment`, `Schedule`).

For ITM 327: extracted 9 LOs cleanly. The operator's 5-CLO Excel revision is a **condensation** of those 9 — that condensation is the Architect's Analysis topic the rubric asks the faculty to defend.

**Pattern:** pull syllabus LOs and show them as the "existing" source-of-truth. The operator's revised set (if any) is the editorial layer that goes on top.

### 6. Canvas Outcomes API ≠ PLOs

For ITM 327, `GET /courses/{id}/outcome_groups` returned only the course itself as one group — no hierarchy, no program-level outcomes. Tried `GET /courses/{id}/account` → 404. **Canvas doesn't carry PLOs for this course** (and likely most BYU-I courses).

The user's Excel had numeric PLO Primary/Secondary fields (1, 2, 3) — but the *numbers* don't help without *definitions*, and the definitions live in the BYU-I catalog. Tried catalog harvest:

- `https://www.byui.edu/catalog/` requires JavaScript.
- `https://www.byui.edu/majors/information-technology-management-bs` → 404.
- BYU-Pathway pages have program PLOs but ITM 327 isn't in the BYU-Pathway IT program.
- BYU-I Data Science BS page lists ITM 327 as a "highlighted course" but no PLO block.

**Verdict:** PLOs are not standard, not harvestable across courses. **Drop the column from the template by default.** If a specific operator's course IS in a known program with documented PLOs, harvest with a course-specific WebFetch and add it back. Don't try to auto-resolve.

### 7. MLO extraction from module overview pages is heuristic

Module overview pages (the `w##-u#-unit-overview` naming pattern in ITM 327) sometimes contain a "Module Learning Outcomes" / "By the end of this week" block followed by verb-led bullets. Sometimes they don't. For ITM 327, 8 of 12 modules had parseable MLOs.

The extraction pattern:

```python
MLO_HINT_RE = re.compile(r"(?:learning outcomes?|by the end|students? will|you will)", re.IGNORECASE)
# Scan page body for hint regex → capture verb-led short sentences in following block.
```

**Flag missing MLOs as a gap** with the module names listed. Don't fabricate MLOs from item titles — operator will catch it.

---

## Rendering lessons

### 8. MD → PDF: Chrome headless is the most reliable path on macOS

Tried and failed:

- **weasyprint** — needs `libpango-1.0-0`, not installed.
- **xhtml2pdf** — pulls in `pycairo`, needs Meson + native cairo.
- **pandoc** — separate Haskell binary, not pip-installable.

What worked:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf=OUT.pdf "file://IN.html"
```

`uv run --with markdown python3` produces the HTML from the MD; Chrome renders it. No native deps required. Chrome is on most operator Macs.

**Pattern:** generate MD → wrap in styled HTML → Chrome headless → PDF. Filter Chrome's stderr (task_policy_set / externally_managed / gcm errors are noise — actual PDF write succeeds).

### 9. Tables vs. prose: tables earn their place when comparison/structure benefits

The operator's instinct was right: not everything that's a grid in Excel needs to be a table in MD.

**Keep as table:** CLO list (multi-column comparison), Key Assessments (multi-dimensional), At-a-Glance (week-by-week scan), per-module MLO + Learning Experiences (alignment columns), Bloom Scaffolding Ladder (matrix view), Heavy-Week density bars (sortable comparison), Bloom Reference (domain × level).

**Keep as prose:** Architect's Analysis (write-in response to prompts), Assessment Strategy Reflection (same), Pacing Reflection (same), Methodology notes.

**The hard call:** Semester Schedule (14 weeks × 3 day-rows × 5 cols, mostly write-in cells). My recommendation was prose-blocks; operator said keep table. **Operator was right** — preserving the grid lets users scan across weeks visually, and the "mostly write-in" objection was wrong (Date/Day/Due are real data; only Prepare/In-Class are write-in).

---

## Gap-analysis lessons

### 10. Gap analysis is the killer feature, not the template

The operator's most valuable output is the **§6.4 Gap Analysis** — explicit side-by-side of what Canvas could fill vs. what the operator authored vs. what AI could draft. It surfaces editorial decisions that would otherwise stay implicit.

**Three sources to compare:**

1. **Canvas-derivable** (syllabus LOs, assignments, modules, dates) — auto-pulled, marked ✓
2. **Operator's Excel content** (CLO condensation, family rollups, manual CLO mapping, AI Opp/Vuln, Lesson Topics, seed prose) — preserved as the editorial layer
3. **AI-drafted** (per-family AI Opp/Vuln, full reflection prose, Lesson Topic suggestions) — proposed where the operator left blanks or where AI's differentiation outperforms operator's uniform values

**Heuristic for source choice in the final merged draft:**

| Element | Default source |
|---|---|
| CLO list | Operator (their revision is the editorial work the rubric asks for) |
| Architect's Analysis prose | Operator voice + AI structure |
| Family rollup labels | Operator (editorial judgment) |
| Manual CLO mapping per assessment | Operator (outperforms keyword heuristic) |
| AI Opportunities / AI Vulnerabilities per assessment | **AI** (per-family differentiation beats uniform values) |
| Assessment Strategy Reflection prose | Operator voice + AI structure |
| Lesson Topics | Operator (if filled in Excel) |
| MLO extraction | Canvas + heuristic |
| Schedule dates / due dates | Canvas |
| Prepare / In-Class daily content | Operator (write-in; Canvas has no field) |
| Pacing Reflection prose | AI-drafted from Canvas heavy-week data (operator's seed if any) |

### 11. AI-drafted content needs explicit per-family differentiation

The operator's Excel had uniform "Co-Create w/AI, Review Code" / "Does it for them" across 4 of 5 key assessments. **AI's per-family differentiation is more rubric-defensible** — each assessment has its own co-pilot affordances and ghost-writer risks, and saying so explicitly demonstrates the architect-level thinking the rubric grades.

**Pattern:** for AI-content sections, draft per-row distinct content even if it took the operator less effort to use uniform values. Faculty value the differentiation when they see it side-by-side.

### 12. Heavy-week reflection writes itself from points-per-week data

The Pacing Reflection criterion asks operators to identify heavy weeks and explain why. **The data tells most of the story** — for ITM 327, the bi-weekly Sprint pattern (W2/4/6/8 all at 301 pts, 3 major items each) is unmistakable in the heavy-week table.

The AI-drafted Pacing Reflection in v7/v8 was grounded entirely in three patterns surfaced by the data:

1. **Onboarding cliff** — Week 1 is 110+ pts heavier than next-heaviest, with setup-debt-compounds risk.
2. **Bi-weekly sprint-end stack** — every-other-week 301pt pattern in W2-W8.
3. **Mid-semester transition** — W7 (self-assessment) → W8 (sprint close) → W9 (dbt pivot) with no light week between.

**Pattern:** for Pacing Reflection, lead with the data-derived patterns and provide a draft that names them; operator can edit voice/specifics. Don't leave §5 blank — it's the easiest section for AI to ground in actual numbers.

---

## Operational defaults for future Course Map asks

When a future operator asks for the same kind of report:

1. **Confirm course ID + Master ID** before any pull. Don't assume the env file.
2. **Pull syllabus_body** in the same call as the course metadata: `?include[]=syllabus_body`.
3. **Skip PLO columns** by default — they're not Canvas-derivable. Mention as a gap if the operator's workbook expects them.
4. **Default to AI-drafted §5 Pacing Reflection** — operator likely hasn't authored this and the data supports it.
5. **Preserve operator's Excel content verbatim** when they share it; never paraphrase or "improve" without explicit permission.
6. **Generate both BLANK template and FILLED draft** in one run; deliver both files.
7. **Use Chrome headless for PDF rendering** (weasyprint and xhtml2pdf fail on most macOS setups without native deps).
8. **Surface gap analysis prominently** — §6.4 is the actual deliverable, not the template itself.
9. **Keep §4 Semester Schedule as a table**, even when most cells are write-in (operator confirmed this preference; the grid scan value is real).
10. **AI Opp/AI Vuln columns:** always per-family differentiated, never uniform. Even if the operator's Excel had uniform values, propose differentiation in the gap analysis.

---

## Trigger for promoting this work into a real canvas-toolbox tool

The Course Map exercise is currently glue-code in `/tmp/build_course_map_v8.py` (~900 lines including AI content constants). It is **not yet in `lib/tools/`**. The trigger for promotion (per `handoffs/parkinglot.md` "Course Map Auditor"):

- A second operator (or the same operator on a different course) asks for the same report.
- The README "What you can do with it" faculty rewrite ships (this would be the headline tool).
- A new Canvas course needs the audit and the glue-code needs minor refactoring (env-var name, course-specific keywords) — extract to a tool at that point.

Until then: park the script. Refer to this knowledge file when the next ask comes in.

## Files referenced

- `/tmp/build_course_map_v8.py` — the production script (kept locally; not in canvas-toolbox `lib/tools/` yet)
- `/tmp/Course_Map_Template_BLANK.md` — proves Excel coverage
- `/tmp/ITM327_Course_Map.md` + `.pdf` — final submission draft for ITM 327
- `/Users/chazclar/Downloads/Course_Map_With_PLO.xlsx` — operator's source workbook
- `handoffs/parkinglot.md` "Grading-structure audit tool" entry — adjacent parked idea, may merge with Course Map Auditor when promoted

---

# v0.2 update — lessons from a SECOND filled exemplar (2026-06-06)

A second faculty operator's filled Course Map (`Course Map AoL.xlsx`, Construction Management — Advanced Estimating & Bidding, 2026 Fall) was compared against the ITM 327 Pass 1 output. The buddy's file is **fully populated** for all 14 modules (164 rows of Course Map Details), uses **richer pedagogy vocabulary**, and shows a **different class cadence** (M/W lecture, not Tue/Thu/Sun). These 11 lessons came out of that comparison and were applied to script v11 + the BLANK template.

## 13. CLOs span all three Bloom domains, not just Cognitive

**Observed:** buddy's 6 CLOs were 4 × Cognitive (Apply, Create, Evaluate) + 1 × Affective ("Defend ethical bidding practices" → Valuing) + 1 × Psychomotor ("Perform digital quantity takeoffs" → Skilled Movements). My ITM 327 default-everything-to-Cognitive heuristic was wrong.

**Defense (script v11):** stronger Domain detection — `Defend / Value / Respect / Justify / Embrace / Adopt` → Affective; `Perform / Execute / Operate / Manipulate` (hands-on) → Psychomotor. Default to Cognitive only when no other signal fires.

**Pattern for future asks:** never assume mono-domain CLOs. Even technical courses often have one Affective (ethics, professionalism) and one Psychomotor (hands-on craft).

## 14. CLO count is dynamic — 5 is NOT the universal

**Observed:** buddy's file has 6 CLOs plus a row-7 placeholder (anticipating CLO 7). Faculty leave room for additions.

**Defense:** loop over `USER_EXCEL_CLOS` dynamically; never hardcode `range(1, 6)`. Blank template should show 5 example rows + a "[add more rows as needed]" note.

## 15. AI Opportunities / Vulnerabilities are PARAGRAPHS, not phrases

**Observed:** buddy's per-assessment AI Opp/Vuln entries are 2-3 sentence paragraphs, course-specific, with explicit WHY framing. Example (Estimate #4):

> *AI Opp:* "AI can help students compare estimate types, identify scope gaps, organize assumptions, and think through project risk as the design develops. It can also help students communicate and justify estimating decisions more clearly."
>
> *AI Vuln:* "Students may trust AI generated pricing, assumptions, or scope interpretations without verifying them against drawings, specifications, logistics, and real project conditions. AI can create confidence without understanding."

My v7-v10 AI Opp/Vuln were one-line phrases — pedagogically thinner.

**Defense (v11):** rewrote `AI_KEY_ASSESSMENT_AI_NOTES` as paragraphs following buddy's pattern: `AI can help students [X], [Y], and [Z]. It can also help students [communication/synthesis angle].` for Opp; `Students may [risk verb] AI generated [thing] without [verification]. [Consequence sentence].` for Vuln.

**Pattern for future asks:** AI Opp/Vuln drafts should always be 2-3 sentences per family. The WHY (not just WHAT) is what makes the architect's argument rubric-defensible.

## 16. "Type of Experience" uses PEDAGOGY vocabulary, not Canvas widget names

**Observed:** buddy's Type column uses: `Reading` / `Video` / `Practice` / `Formative Assessment` / `Synthesize` / `Create` / `Discussion` / `Discussion/Lecture` / `Performance` / `Demo` / `Peer Review` / `Exploration` / `Summative Assessment` / `Review`.

My v10 used Canvas-type names: `Reading / Material` / `Activity / Minor` / `Major Assessment` / `Quiz / Check`. These are the words *Canvas the application* uses, not the words faculty use to *think about teaching*.

**Defense (v11):** `classify_type()` now maps to pedagogy vocab, with name-pattern matching first (Demo / Lab / Quiz / Presentation / Reading / Workshop / Final / Milestone / Peer Review / Stand Up), Canvas type only as fallback.

**Pattern for future asks:** when wrapping any Canvas data for faculty consumption, translate Canvas's widget vocabulary into pedagogy vocabulary. Faculty say "Practice" not "Activity / Minor"; "Performance" not "Major Assessment"; "Formative Assessment" not "Quiz / Check".

## 17. MLOs are 2-3 per module — quality, not quantity

**Observed:** buddy's modules have 2-3 MLOs each, with explicit Bloom level per MLO. My heuristic was extracting up to 5 (and sometimes the wrong text, like "Estimated time: 6-9 hours per week").

**Defense (v11):** MLO extraction cap reduced from 5 → 3. The pattern matches what the AoL workbook template actually expects (rows 4-6 in Course Map Details = 3 MLO slots).

**Pattern for future asks:** when extracting MLOs from overview pages, take the top 2-3 (in document order); discard any line that's clearly meta (estimated time, instructor notes, etc.). Better to surface 2 high-quality MLOs than 5 noisy ones.

## 18. Lesson Topics use ACTION VERBS, not topic nouns

**Observed:** buddy's Lesson Topics column has multi-sentence action statements:

> *"Apply unit pricing to quantities. Calculate total costs for THOW."*
> *"Analyze commercial plans. Organize scope of work for missing components."*

My v7 AI-drafted Lesson Topics were closer to *"Airflow DAG anatomy · API authentication patterns"* — topic lists, not actions.

**Defense (v11):** AI-drafted Lesson Topics should follow the *"Verb the noun. Verb the noun."* pattern. Two sentences per cell, both starting with a Bloom-level-appropriate action verb.

**Pattern for future asks:** when drafting Lesson Topics for a faculty operator, **describe what students DO** (Apply, Analyze, Construct, Defend, Calculate, Compare) — not what content TOPICS they encounter. Topics-as-nouns are syllabus-style; actions-as-verbs are course-map-style.

## 19. Module Concept/Title is the ARTIFACT/PROJECT NAME, not the abstract container

**Observed:** buddy's modules are named for the actual deliverable they build toward: *"Course Intro & Tiny House on Wheels"*, *"BYU-I Parking Lot"*, *"Provo Fire Station"* (which spans 7 weeks!), *"Final Conceptual, Schematic, DD, GMP"*.

Operator (ITM 327) uses *"Sprint 1"*, *"Sprint 2"*, etc. — abstract container names. Both work, but the artifact-named approach is more immediate for students and makes the course map more legible.

**Pattern for future asks:** if a course's Canvas modules are named generically (`Module N`, `Week N`, `Sprint N`), prompt the operator at run time for a project/artifact name per module. Don't auto-generate generic labels.

## 20. Class meeting cadence is course-dependent — DETECT, don't hardcode

**Observed:** buddy = 2 sessions/week (M+W lecture, 30 schedule rows). ITM 327 (online pilot) = no in-person class; due dates concentrate on Sundays.

My v10 hardcoded `["Tue", "Thu", "Sun"]` — wrong for both courses.

**Defense (v11):** `detect_class_cadence(assignments)` returns the top 2-3 modal day-of-week values from published `due_at` timestamps. Falls back to Tue/Thu/Sun only if no signal. Row placement in §4 maps each item's actual due-DoW to the nearest detected day.

**Pattern for future asks:** never hardcode meeting days. Detect from data, or expose as a configurable (`CLASS_DAYS=M,W` env var). The §4 table structure should always reflect the actual course cadence, not a template assumption.

## 21. Holiday handling matters — schedule needs `No Class` markers

**Observed:** buddy's W11 Wed cell explicitly says *"No Class (Thanksgiving Break)"*. Real semesters have holidays.

**Defense (v11):** added a per-week "Holiday / special note this week" write-in line below each Week table in §4. Operator marks holidays manually (no programmatic source for BYU-I academic calendar yet).

**Future enhancement:** consider fetching BYU-I academic calendar via WebFetch and pre-populating holidays.

## 22. Assessment Type vocabulary is richer than Formative / Summative

**Observed:** buddy uses `Performance` (hands-on project deliverables) / `Summative` (comprehensive exams) / `Recall` (memorization quizzes like MasterFormat / UniFormat indexing). My v10 forced everything into Formative / Formative-Summative / Summative.

**Defense (v11):** updated assessment-type classifier — `Performance` for project/lab/milestone/presentation/estimate names; `Recall` for memorization-style quizzes (vocab/terminology/MasterFormat-style); `Summative` for finals/exams/capstones; `Formative` as default for low-stakes checks.

**Pattern for future asks:** the AoL workbook's Assessment Type column is intentionally open-ended. Use precise pedagogy labels, not just a 3-value Formative/Mixed/Summative enum.

## 23. NEW SHEET: "Assessment Design Pt1" — exemplar redesign with rubric

**Observed:** buddy's file has a sheet NOT in your operator's `Course_Map_With_PLO.xlsx` — `Assessment Design Pt1`. It's a deep-dive redesign of one specific assessment (his MasterFormat Final Quiz → "The MasterFormat Estimator's Audit", an in-class scenario-based case study). Includes:

- Proposed format (in-class / take-home / scenario-based / etc.)
- Detailed instructions for students
- A 3×3 rubric matrix (Criteria × Excellent / Competent / Needs Improvement)

This is a pedagogy exercise — pick one weak assessment from §1.3, redesign it deeply as an exemplar of evidence-centered assessment design.

**Defense (v11):** added optional Section 1.5 to BLANK template + filled report: "Assessment Design Deep-Dive". All cells are operator write-in (Canvas has no field for this). Marked as `⊘ optional write-in` in the gap report so operator can skip if their AoL assignment doesn't require it.

**Pattern for future asks:** when the operator's AoL workbook has more than the standard 5 sheets, surface each extra sheet as an optional section. Don't drop content from the workbook just because it wasn't in the first operator's template.

---

## Updated operational defaults (v0.2)

In addition to the 10 defaults from v0.1, these 5 from v0.2:

11. **Domain heuristic** — actively detect Affective and Psychomotor verbs; don't default to Cognitive for everything.
12. **AI Opp/Vuln** — always paragraphs (2-3 sentences), per-assessment differentiated, never uniform.
13. **Type of Experience** — translate Canvas widget names to pedagogy vocabulary. The faculty-facing version always uses pedagogy words.
14. **Class cadence** — detect from data, never hardcode Tue/Thu/Sun.
15. **Optional new sheets** — if the operator's AoL workbook has 6+ sheets, surface each as an optional Section in the report (don't drop them).

## v11 script artifacts

- `/tmp/build_course_map_v11.py` — generator with all 11 lessons applied
- `/tmp/Course_Map_Template_BLANK.md` — updated template (12.1 KB)
- `/tmp/ITM327_Course_Map.md` + `.pdf` — re-generated ITM 327 output with v11 improvements

## Promotion path

The script is still glue-code in `/tmp/`. Promotion trigger remains the same as v0.1: a second operator (or same operator on a different course) asks for the Course Map report, OR the faculty-rewrite README ships, OR ~3 operators have used the pattern.

Two filled exemplars now exist (ITM 327 + buddy's Construction Mgmt). One more independent use would be sufficient to justify lifting from `/tmp/` to `lib/tools/course_map_audit.py`.

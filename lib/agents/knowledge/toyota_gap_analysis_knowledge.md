---
name: toyota_gap_analysis_knowledge
version: '1.0'
last_updated: '2026-07-16'
description: Toyota gap-analysis method for writing a precise change plan for a flagged issue — Current -> Target -> Countermeasure -> Verification, scoped to the specific gap.
skill_type: knowledge
shape: identity
scope: 'The Toyota Production System / A3 Problem Solving methodology applied to Canvas course design audits. The single frame is Genchi Genbutsu (go and see) — the prerequisite to honest A3 work. The A3 structure (Current/Target/Gap/Root Cause/Countermeasure/Verification) is the artifact this frame produces. Boundaries: does not cover what to audit (see hattie_3phase, cognitive_load_theory, course_design_language); covers how to write up findings as a remediation plan.'
consumed_by:
- canvas_course_expert.md
provenance:
  sources:
  - Toyota Production System / A3 Problem Solving methodology.
  - Applied to Canvas course design audits via canvas_course_expert.md.
companion_json_deprecated: 2026-07-16 - consolidated into YAML frontmatter (JSON purge convention)
runtime_strategy: read_at_runtime
principles:
- id: genchi_genbutsu
  name: Genchi Genbutsu — Go and See for Yourself
  compact_statement: '現地現物. Don''t make decisions from reports, dashboards, or theory. Go to gemba (the actual place where work happens) and observe the real work in real conditions. Toyota holds that A3 problem-solving cannot be done honestly without first going to gemba — you cannot accurately fill in Current State from a summary, Gap from intuition, or Root Cause from speculation. Each section requires firsthand observation. Applied to Canvas: gemba is the live course/ mirror (actual pages, module items, rubrics, student-visible titles). The audit agent MUST call parse_course_export() or read the course/ mirror via canvas_sync.py BEFORE proposing any A3. The principle in one line: an A3 written without going to gemba is a wish list; an A3 written after going to gemba is a plan.'
metadata:
  knowledge_id: toyota_gap_analysis_knowledge
---

# Toyota Gap Analysis — Knowledge Reference

Source: Toyota Production System / A3 Problem Solving methodology.
Applied to: Canvas course design audits by `canvas_course_expert.md`.

_Last updated: 2026-05-13_

---

## Why Gap Analysis for Course Design

Toyota's A3 methodology forces specificity at the root cause level. Without it, "add an overview page" is a to-do item. With it — "this module was duplicated from last semester without updating the template, and that's true for all 6 Sprints" — the fix becomes "create one overview template and apply it to all 6 Sprints at once."

That's the difference between patching and fixing.

The same principle applies to Canvas courses: most design problems aren't isolated. They're systemic — caused by a single upstream decision (copied module structure, missing template, overlooked standard) that propagates across the entire course.

---

## Genchi Genbutsu — The Prerequisite to A3

**Genchi Genbutsu (現地現物)** — "go and see for yourself." A core Toyota Production System principle: don't make decisions from reports, dashboards, or theory. Go to **gemba** (the actual place where work happens) and observe the real work in real conditions.

Toyota holds that A3 problem-solving cannot be done honestly without first going to gemba. You cannot accurately fill in *Current State* from a summary, *Gap* from intuition, or *Root Cause* from speculation. Each section requires firsthand observation.

**Applied to Canvas course audits:**

| Toyota concept | Canvas equivalent |
|---|---|
| **Gemba** (the real place) | The live `course/` mirror — actual pages, actual module items, actual rubrics, actual student-visible titles |
| **Genchi Genbutsu** (go and see) | Read the artifacts directly. Don't summarize the course from memory. Don't theorize from the syllabus alone. Don't trust last semester's audit report. |
| **The trap to avoid** | Filling in A3 sections from the agent's prior knowledge of "what BYUI courses usually look like" instead of what *this specific course* actually contains right now |

**For the audit agent specifically:** before proposing any A3, the agent must call `parse_course_export()` or read the `course/` mirror via `canvas_sync.py`. Producing a *Current State* line without having read the actual content is a Genchi Genbutsu violation — the audit becomes theory dressed up as observation, and the *Root Cause* and *Countermeasure* downstream are unreliable as a result.

**The principle in one line:** an A3 written without going to gemba is a wish list. An A3 written after going to gemba is a plan.

---

## The A3 Structure (applied to course design)

Each issue in the change plan uses this format:

| Field | Question it answers | Course design example |
|-------|--------------------|-----------------------|
| **Current State** | What does the course do right now? | "Sprint 3 opens with a NotebookLM link" |
| **Target State** | What should it do? (per BYUI standards, Hattie phases, CL principles) | "Sprint 3 opens with an overview page stating outcomes, time, and flow" |
| **Gap** | What is the precise distance between current and target? | "Students enter Sprint 3 with no orientation — Surface phase is impaired from the first click" |
| **Root Cause** | Why does the gap exist? | "Overview page was never created; module was built by duplicating Sprint 2 items" |
| **Countermeasure** | What specific Canvas change closes the gap? | "Create 'Sprint 3 Overview' wiki page; insert as item 1; include 2–3 outcomes, time estimate, and connection sentence" |
| **Verification** | How do we confirm it worked? | "Re-run audit — CL-002 and Surface gap no longer fire for Sprint 3" |

---

## Isolated vs. Systemic Gaps

Before proposing a countermeasure, the agent determines whether a gap is **isolated** or **systemic**.

**Isolated gap** — affects one module or item. Fix it directly.

> Example: Sprint 4 has a mid-performance review with "make template" in the title. Only Sprint 4. Fix: rename the item.

**Systemic gap** — the same root cause produces the same gap across multiple modules or the entire course. One countermeasure applied everywhere.

> Example: No Sprint module has an overview page. Root cause: no overview template exists in the course design. Fix: create one overview template, then apply to all 6 Sprints at once — not 6 separate fixes.

**How to identify systemic gaps:** if the same rule fires on 3+ modules, treat it as systemic. Ask: what single decision upstream caused this? Fix that decision, not each instance.

---

## A3 Example — Sprint 3 Missing Overview

```
Current State : Sprint 3: SFTP DAG + DW SQL LAB (W05-W06) opens with
                "W05/6 NotebookLM: CH7-8" as the first module item.

Target State  : Sprint 3 opens with an overview page that states:
                - 2-3 learning outcomes for the sprint
                - Estimated time commitment
                - How the NotebookLM, DAG assignment, and lab connect

Gap           : Students enter Sprint 3 with no orientation.
                Hattie Surface phase is impaired from the first click.
                CL-002 (extraneous load) fires: no overview/intro page.

Root Cause    : Overview page was never created. Sprint 3 was built by
                duplicating Sprint 2's item list without adding an intro.
                This is systemic: all 6 Sprints have the same root cause.

Countermeasure: [Systemic fix]
                1. Create an "Overview" page template with placeholders
                   for outcomes, time, and connection sentence
                2. Duplicate and fill for each of the 6 Sprint modules
                3. Insert as item 1 in each Sprint module via Canvas API

Verification  : Re-run audit — CL-002 does not fire for any Sprint
                module. Each module's first item title contains "Overview".
```

---

## A3 Example — Editor Notes in Item Titles (Sprint 1)

```
Current State : Sprint 1 contains items whose Canvas-visible titles
                include editor instructions:
                - "Needs editing. What should students know and be
                   tested on? W01 Introduction: Syllabus Quiz"
                - "Put in teacher notes: Instructors need to adjust
                   red portion... W01 Sign-up: Contract of Employment"

Target State  : All student-visible item titles are clean, professional,
                and match the naming pattern used in other Sprints
                (e.g., "W01 Introduction: Syllabus Quiz")

Gap           : Students see internal editor notes as their course
                navigation labels. Damages trust and clarity.
                Hattie Surface phase: extraneous load from confusion.

Root Cause    : Items were created with working notes in the title field
                as a build-in-progress convention. Notes were never
                removed before publish.

Countermeasure: [Isolated — Sprint 1 only]
                Rename 5 items to clean titles, stripping all text
                before the actual assignment name. Publish 3 items
                currently marked unpublished or move to instructor module.

Verification  : No item title in Sprint 1 contains "needs editing",
                "make template", "🖥", or inline question text.
                CL-010 does not fire for Sprint 1.
```

---

## Output Format for Change Plans

When presenting a change plan to the instructor, the agent groups findings as:

**1. Systemic gaps** (fix these first — one countermeasure covers many modules)
**2. Critical isolated gaps** (fix before course goes live)
**3. Warnings** (fix before the semester is in full swing)
**4. Info / improvement opportunities** (consider for next redesign)

Within each group, each item is presented in A3 format. The instructor approves at the group level ("apply all systemic fixes") or selects individual items.

---

## Gap Severity vs. Hattie Phase Priority

These are independent dimensions. A gap can be:
- Low severity but in the Surface phase → fix it anyway (Surface blocks everything downstream)
- High severity but in the Transfer phase → still urgent, but won't cascade

When two gaps compete for attention, fix Surface gaps first regardless of severity. A broken Surface means Deep and Transfer fixes won't land.

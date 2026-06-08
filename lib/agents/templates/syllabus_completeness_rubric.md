# Syllabus Completeness Rubric

Use this rubric to review a course syllabus against the BYU-I required template. For each row, assign a score of **2**, **1**, or **0**.

**Performance levels:**

| Score | Meaning |
|---|---|
| **2** | Complete and clear |
| **1** | Present but thin or uneven |
| **0** | Missing |
| **N/A** | Only when an item does not apply to the course |

---

## Rubric items (25 criteria across 11 categories)

| Category | Criteria | Score (0–2) |
|---|---|---|
| **Course Information** | Course Title is present | _[score]_ |
| | Course Code is present | _[score]_ |
| | Course Credits is present | _[score]_ |
| | Specific semester/year (if on-campus) is present | _[score]_ |
| | Prerequisites is present or none are noted | _[score]_ |
| **Course Description** | Course description matches what is in the catalog | _[score]_ |
| **Course Outcomes** | Course Outcomes match what is in the catalog | _[score]_ |
| **Materials** | Required/recommended textbooks, software, or equipment are identified | _[score]_ |
| **Grading and Assessments** | Weighting of assignments is present (if applicable) | _[score]_ |
| | Grading scale is present (if applicable) | _[score]_ |
| | Exams is present (if applicable) | _[score]_ |
| | Projects is present (if applicable) | _[score]_ |
| **Main Course Assignments** | Topics covered, major course experiences, and/or descriptions of how students will achieve the course outcomes are present | _[score]_ |
| **Expectations** | Workload is clarified | _[score]_ |
| | Attendance policy is present | _[score]_ |
| **AI Usage** | A policy on AI tool usage, a "right to modify" clause, and tips for success is present | _[score]_ |
| **Additional Information** | A link to a page with additional information is present, if applicable | _[score]_ |
| **University Statements & Policies** | Personal Challenges statement is present | _[score]_ |
| | Accommodations for Students with Disabilities statement is present | _[score]_ |
| | Sexual Harassment statement is present | _[score]_ |
| | Link to Student Grievance page is present | _[score]_ |
| | Link to CES Honor Code page is present | _[score]_ |
| | Link to Academic Honesty page is present | _[score]_ |
| | Link to FERPA page is present | _[score]_ |
| | Link to Policy Library is present | _[score]_ |
| | Copyright disclaimer is present | _[score]_ |
| **TOTAL** | (sum of 25 items, max 50) | _[total]_ |

---

## Reflection questions

1. Which 2–3 sections of your syllabus need the most attention?
2. Which items could be improved quickly?
3. What updates will make the syllabus more helpful and clear for students?

---

## Source

Authored by BYU-Idaho Academic Office / Faculty Development. Distributed as the *Syllabus Completeness Rubric* PDF (2026). Anchors the 25-item granular completeness check against the canonical [BYU-Idaho Syllabus Template](byui_syllabus_template.md).

## How `lib/tools/syllabus_audit.py` uses this

The audit tool scores a syllabus against these 25 items using heuristic keyword + link-presence detection. Honest limit: detection can score 0 vs ≥1 reliably; the rubric's distinction between **1 (present but thin)** and **2 (complete and clear)** is a human-judgment call about clarity that a keyword detector cannot make. The tool surfaces "present once" as a *possibly-thin* signal but does not score it definitively.

## Related artifacts

- [`byui_syllabus_template.md`](byui_syllabus_template.md) — the canonical BYU-I syllabus template (canvas course 405800 page `syllabus-template`)
- [`../knowledge/syllabus_knowledge.md`](../knowledge/syllabus_knowledge.md) — the auditor's reference (umbrella sections + AI policy gate + advisory signals)
- [`../knowledge/learned/2026-06-05_course-map-from-canvas-pass-1-lessons.md`](../knowledge/learned/2026-06-05_course-map-from-canvas-pass-1-lessons.md) — related Pass 1 lessons (course design / faculty workflow)

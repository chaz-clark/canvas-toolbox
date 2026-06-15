---
name: byui-course-map-aol-xlsx-schema
description: BYUI's "Course Map AoL" xlsx template uses heavily merged cells; column anchors are NOT 1-N like a normal table. Document the actual column positions so any tool parsing this format doesn't burn time hunting them.
version: "1.0"
author: chaz-clark
license: MIT
metadata:
  topic: xlsx-parsing
  source-format: BYUI Course Map AoL xlsx (5-sheet workbook)
  precipitating-event: 2026-06-15 conversion of a friend's ACCTG 433 xlsx → canonical canvas-toolbox course-map MD+PDF
  affects: any tool reading the AoL xlsx format (e.g. a future `course_map_build.py --from-xlsx` mode)
---

# BYUI Course Map AoL xlsx — schema notes

## What happened

A friend sent Chaz a filled-in BYUI "Course Map AoL" Excel workbook
(ACCTG 433 — Advanced Spreadsheet Application). The ask: convert it to
the canvas-toolbox canonical course-map MD + PDF. A one-off script at
`/tmp/xlsx_to_course_map.py` did the work — but burned ~10 minutes
discovering that the xlsx's column layout doesn't match what
`iter_rows(values_only=True)` makes it look like.

Capturing the load-bearing schema here so the next tool / agent
reading this format doesn't repeat the discovery.

## The non-obvious fact

The "Outcomes & Key Assessment Strat" sheet looks like a 6-column table
when you scan with `iter_rows`. It is **not** — it's a heavily
merged-cell layout where data columns are at positions
`1, 9, 14, 16, 24, 32`. Naively reading columns 1-6 gets you the names
but drops the type / CLOs / alignment / AI opportunities / AI
vulnerabilities entirely (they come back as `None`).

This is the kind of trap that produces a "compiles and runs but the
output is mostly empty" failure mode — easy to ship past, hard to
diagnose downstream.

## The actual column anchors

### Sheet 1: `Outcomes & Key Assessment Strat`

**Row 1 (course header):**
| Col | Content |
|---|---|
| 1 | Course code (e.g. `ACCTG 433`) |
| 6 | Course name (e.g. `ADVANCED SPREADSHEET APPLICATION`) |
| 24 | Literal `Mode:` label |
| 27 | Mode value (e.g. `IN-PERSON`, `Online Pilot`) |
| 35 | Section label (`O & A`) |

**Rows 3-9 — CLOs:**
| Col | Content |
|---|---|
| 1 | CLO number (int) |
| 2 | CLO text |
| 31 | Domain (`Cognitive`, `Affective`, `Psychomotor`) |
| 36 | Bloom level (`Remembering`, `Understanding`, `Applying`, `Analyzing`, `Evaluating`, `Creating`) |

**Rows 10-15 — Architect's Analysis:** col 1 carries the prompt
heading + the response. If the cell text starts with `See Assignment`
(e.g. `See Assignment 3_Course Outcomes Review file`), that's a
**legitimate placeholder pattern** — faculty doing the assignment
series may legitimately point at a separate file rather than fill
inline. Don't flag as missing; preserve verbatim.

**Rows 17-24 — Key Assessments table:**
| Col | Content |
|---|---|
| 1 | Assessment name |
| 9 | Assessment type (e.g. `Product/Process`, `Proctored Multiple Choice Exam`) |
| 14 | CLOs covered (e.g. `2`, `1&2`) |
| 16 | Domain/Level Alignment (e.g. `Fits-Summative. Students are creating.`) |
| 24 | AI Opportunities |
| 32 | AI Vulnerabilities |

**Rows 26-32 — Assessment Strategy Reflection:** col 1, same
`See Assignment X file` placeholder pattern as the Architect's Analysis.

### Sheet 2: `Course Map-At a Glance`

**Row 2 (header) + rows 3-16 (14 weeks):**
| Col | Content |
|---|---|
| 1 | Week number (1-14) |
| 3 | Module Concept/Title |
| 12 | Lesson Topics |
| 20 | Minor Activities/Assignments |
| 30 | Key Assessments |

### Sheet 3: `Course Map Details`

A multi-block layout, one block per module. Block structure:

- **Module header row:** col 1 = `Module N:`, col 5 = module title.
  - Detection: `re.match(r"^Module\s+\d+\s*:", col_1_value)`.
  - **Don't match `Module Learning Outcomes`** — that's a sub-header
    inside the block, not a new module. Strict regex required.
- **MLO sub-table** (just after the module header):
  - Col 1 = MLO number (int), col 2 = MLO text, col 34 = Bloom level,
    col 38 = CLOs.
- **Learning Experiences sub-table** (later in the block):
  - Header row signals state: col 1 = `MLO`, col 2 starts with
    `Learning Experiences`. AFTER this row, (int, text) pairs in
    cols 1+2 are learning-experience refs, NOT MLOs. Track a
    state flag — parsers that don't flip get duplicate "MLO" rows.

### Sheet 4: `Semester Schedule`

**Row 2 (header) + rows 3-44 (one block per week, 3 day-rows per block):**
| Col | Content |
|---|---|
| 1 | Week number (only on the first row of each week's block) |
| 3 | Date |
| 5 | Day |
| 7 | Prepare items |
| 18 | In-Class items |
| 30 | Assignments |

In practice this sheet is often filled LAST — the friend's ACCTG 433
xlsx had week numbers only, all other cells empty. Treat the empty
schedule as "in flight" not "missing."

### Sheet 5: `Dropdown Data`

983 rows of reference data backing the xlsx's dropdown form controls
(Bloom levels per domain, plus per-CLO data-prep columns). Don't read
for content; it's metadata feeding the input forms in the other sheets.

## How to apply

If/when `course_map_build.py` grows a `--from-xlsx` mode (the natural
v1.x enhancement when a second BYUI faculty member sends an AoL
workbook), implement the column anchors from this file. The one-off
script at `/tmp/xlsx_to_course_map.py` (generated 2026-06-15) has them
all wired correctly — use it as the reference implementation.

The "See Assignment X file" pointer pattern (rows 10-15 + 26-32 of
sheet 1) is **intentional, not missing.** A converter should preserve
the pointer verbatim AND flag it in the Gap Report as
"written elsewhere; merge later" rather than `_[write-in pending]_`.

## Promotion rule (Hermes)

This file lives in `learned/` because the column-anchors trap has only
been hit once (2026-06-15, this session). If a SECOND BYUI faculty
member sends Chaz an AoL workbook AND it triggers the same parsing
trap, promote this entry to a first-class knowledge file under
`lib/agents/knowledge/`. Until then, single-session lesson.

## Cross-references

- `/tmp/xlsx_to_course_map.py` (this session's one-off converter; the
  reference implementation for column anchors)
- `lib/agents/templates/course_map_blank.md` (canonical destination
  format that this xlsx hydrates into)
- `lib/tools/course_map_build.py` (the existing tool that emits the
  blank template + Canvas-pull mode; the natural home for an eventual
  `--from-xlsx` mode)

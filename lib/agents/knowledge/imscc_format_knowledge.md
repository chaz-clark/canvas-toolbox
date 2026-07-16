---
name: imscc_format_knowledge
version: "1.0"
last_updated: 2026-07-12
description: Technical reference for the Canvas .imscc format (IMS Common Cartridge v1.1 + Canvas extensions) — archive structure, manifest, XML, and parsing.
skill_type: knowledge
shape: reference
scope: "The .imscc archive structure, imsmanifest.xml, course_settings/ Canvas extensions, and how to parse them — for .imscc import/export implementation."
consumed_by:
  - canvas_content_sync.md
companion_json_deprecated: "2026-07-16 - authored as YAML frontmatter (JSON purge convention)"
provenance:
  sources:
    - "Canvas LMS docs, IMS Global Common Cartridge spec, canvas-imscc examples"
runtime_strategy: read_at_runtime
metadata: { knowledge_id: imscc_format_knowledge }
---

# Canvas .imscc Format - Technical Reference

**Purpose**: Knowledge base for Sprint 4 (.imscc import/export) implementation
**Source**: Research from Canvas LMS docs, IMS Global CC spec, and canvas-imscc examples
**Last Updated**: 2026-07-12

---

## Overview

**`.imscc` = IMS Common Cartridge v1.1 + Canvas Extensions**

- ZIP archive containing course content
- Based on IMS Global Learning Consortium Common Cartridge standard
- Canvas adds proprietary extensions in `course_settings/` directory
- Must be parsed as ZIP → extract files → parse XML

---

## File Structure

### Top-Level Files (Standard IMS CC)

```
course_export.imscc (ZIP file)
├── imsmanifest.xml          # Main manifest (IMS CC standard)
├── course_settings/
│   ├── course_settings.xml  # Canvas course-level settings
│   ├── module_meta.xml      # Canvas module structure (IMPORTANT!)
│   └── syllabus.html        # Course syllabus HTML
├── wiki_content/
│   └── *.html               # Page content files
├── web_resources/
│   └── *.jpg/png/pdf        # File attachments
└── [assignment_folders]/
    └── assignment_*.xml     # Assignment metadata (one per assignment)
```

### Critical Insight: Dual System

**imsmanifest.xml** = IMS CC-compliant org hierarchy + resource declarations
**module_meta.xml** = Canvas module structure + content types + external URLs

**You MUST read both files together** - neither is complete alone!

---

## Assignment Date Fields

### Date Fields in Assignment XML

Assignment metadata is stored in **individual XML files** (not in imsmanifest.xml):

```xml
<assignment>
  <title>Week 1 Homework</title>
  <due_at>2013-08-28T23:59:00-06:00</due_at>
  <unlock_at>2013-08-21T00:00:00-06:00</unlock_at>
  <lock_at>2013-09-04T23:59:00-06:00</lock_at>
  <points_possible>100</points_possible>
  <!-- ... other fields ... -->
</assignment>
```

### Date Format Specification

> ⚠️ **Corrected by real exports (2026-07-12, 4 dated courses).** The actual
> format is **naive `YYYY-MM-DDThh:mm:ss` with NO timezone offset** — e.g.
> `<due_at>2026-06-23T05:59:59</due_at>`. The values are already UTC (05:59:59
> UTC = Sat 23:59:59 Mountain, matching the BYUI Saturday-11:59pm rule).
> `all_day_date` is date-only `YYYY-MM-DD`. There is NO `Z` and NO `+/-hh:mm`.
> Implication for date-shift: parse naive, add `timedelta(days=N)`, re-emit the
> SAME naive format — no timezone conversion needed (and none must be
> introduced, or Canvas would misread the value).

**Legacy note (older/other instances may differ)**: some exports historically
used ISO 8601 *with* an offset (`2013-08-28T23:59:00-06:00`). A robust parser
should accept both an offset and none; the BYUI exports observed here have none.

### Date Constraints (Canvas Validation)

```python
# Canvas enforces these rules on import:
if unlock_at and due_at:
    assert unlock_at < due_at, "unlock_at must be before due_at"

if lock_at and due_at:
    assert lock_at > due_at, "lock_at must be after due_at"

if unlock_at and lock_at:
    assert unlock_at < lock_at, "unlock_at must be before lock_at"
```

**Important**: These constraints apply to **course-level dates**. Student-specific overrides (SAS accommodations, individual extensions) are **NOT** in .imscc files - they require API access.

---

## Module Structure and Unlock Dates

### module_meta.xml Structure

```xml
<modules>
  <module identifier="m_001">
    <title>Week 1: Introduction</title>
    <unlock_at>2013-08-21T00:00:00-06:00</unlock_at>
    <items>
      <item identifier="i_001">
        <content_type>Assignment</content_type>
        <identifierref>assignment_001</identifierref>
        <title>Week 1 Homework</title>
      </item>
      <item identifier="i_002">
        <content_type>Page</content_type>
        <identifierref>wiki_page_001</identifierref>
        <title>Week 1 Overview</title>
      </item>
    </items>
  </module>
</modules>
```

**Key Fields**:
- `<unlock_at>` - When module becomes visible to students
- `<items>` - Ordered list of content in module
- `<content_type>` - Assignment, Page, Quiz, ExternalUrl, File, etc.
- `<identifierref>` - Links to resource in imsmanifest.xml

---

## Quiz Date Handling

Quizzes have **similar date fields** to assignments:

```xml
<quiz>
  <title>Week 1 Quiz</title>
  <due_at>2013-08-28T23:59:00-06:00</due_at>
  <unlock_at>2013-08-27T00:00:00-06:00</unlock_at>
  <lock_at>2013-08-29T23:59:00-06:00</lock_at>
  <time_limit>60</time_limit>  <!-- minutes -->
  <!-- ... -->
</quiz>
```

**Quiz-Specific Dates** (also in .imscc):
- `show_correct_answers_at` - When to reveal answers
- `hide_correct_answers_at` - When to hide answers again

**Student-Specific Quiz Extensions** (NOT in .imscc):
- Per-student time extensions require API (`student_quiz_time_extension.py`)
- Per-student extra attempts require API

---

## File Attachments and References

### File Storage in .imscc

Files are stored in `web_resources/` directory:

```
web_resources/
├── $IMS_CC_FILEBASE$/folder1/image.jpg
├── $IMS_CC_FILEBASE$/folder2/document.pdf
└── $IMS_CC_FILEBASE$/banner.png
```

**Important**: `$IMS_CC_FILEBASE$` is a literal string used as a placeholder

### File References in HTML

Pages and assignments reference files by identifier:

```html
<!-- In wiki_content/page_001.html -->
<img src="$IMS_CC_FILEBASE$/folder1/image.jpg" alt="Diagram">
<a href="$IMS_CC_FILEBASE$/folder2/document.pdf">Download PDF</a>
```

**On Import to Canvas**:
1. Canvas uploads files to course Files
2. Rewrites `$IMS_CC_FILEBASE$/...` → `/courses/123/files/456/preview`
3. Assigns Canvas file IDs

**For Date Adjustment Workflow**:
- File references DON'T need date adjustment
- Just preserve the `$IMS_CC_FILEBASE$/...` paths
- Canvas will handle rewrites on import

---

## Canvas-Specific Extensions

### Triggering Canvas Import Mode

Canvas detects .imscc as "Canvas-flavored" if these files exist:

```
course_settings/
├── course_settings.xml    # REQUIRED for Canvas mode
└── syllabus.html          # REQUIRED for Canvas mode
```

**Without these files**: Canvas treats as generic IMS CC (limited features)
**With these files**: Canvas enables full feature import (modules, external tools, etc.)

> ⚠️ **Corrected by real export (2026-07-12, Genchi Genbutsu).** A real Canvas
> `.imscc` export (`byui_learning_teaching`) had **NO `course_settings.xml` and
> NO `syllabus.html`**. Its `course_settings/` held instead:
> `canvas_export.txt`, `context.xml`, `module_meta.xml`, `assignment_groups.xml`,
> `files_meta.xml`, `learning_outcomes.xml`, `media_tracks.xml`, `rubrics.xml`.
> So the "required trigger" is NOT `course_settings.xml` — the reliable Canvas
> markers are **`course_settings/canvas_export.txt`** and **`course_settings/context.xml`**.
> Trigger detection must check for those, not hard-require `course_settings.xml`.
> **Fuller survey (5 real exports, 2026-07-12):** 4 of 5 (DS 250, DS 460,
> ITM 327, M 119) DID contain `course_settings.xml` + `syllabus.html`; only the
> content-only reference course lacked them. `canvas_export.txt` + `context.xml`
> were in ALL 5. So: `course_settings.xml` is normally present but NOT
> guaranteed; `canvas_export.txt`/`context.xml` are the universal markers.
>
> Also observed: that export contained **zero date fields** (`due_at`/`unlock_at`/
> `lock_at`/`start_at` absent everywhere) — because it had no native
> assignments/quizzes (content/pages/modules only; LTI-heavy). Dates live in
> per-assignment / per-quiz XMLs, so a course WITHOUT native graded items has
> nothing to date-adjust. Test the date-adjust workflow against an export from a
> course that HAS dated assignments (e.g. DS 250 / DS 460), not this reference course.

### course_settings.xml Structure

```xml
<course>
  <title>Data Science 250</title>
  <course_code>DS250</course_code>
  <start_at>2013-08-21T00:00:00-06:00</start_at>
  <conclude_at>2013-12-15T23:59:00-06:00</conclude_at>
  <is_public>false</is_public>
  <allow_student_discussion_topics>true</allow_student_discussion_topics>
  <!-- ... many other settings ... -->
</course>
```

**Important Course-Level Dates**:
- `<start_at>` - Course start date
- `<conclude_at>` - Course end date
- `<term_start_date>` - Term start (if applicable)
- `<term_end_date>` - Term end (if applicable)

**For Semester Copies**: Adjust these dates along with assignment/module dates!

---

## Identifiers and Canvas Import Requirements

### Identifier Format (CRITICAL!)

Canvas uses `g` + 32-character MD5 hex for identifiers:

```xml
<!-- CORRECT (will import successfully) -->
<resource identifier="g14e5e1d8a8b4f0e9a1c2d3e4f5a6b7c8" type="webcontent">

<!-- WRONG (human-readable IDs cause silent import failures!) -->
<resource identifier="assignment_week_1" type="webcontent">
```

**Why MD5 Hex?**
- Canvas internally uses UUIDs
- Human-readable IDs look valid but fail on import (no error message!)
- Must generate proper identifiers when reconstructing .imscc

**Generation Example**:
```python
import hashlib
import uuid

def generate_canvas_identifier(content_type: str, title: str) -> str:
    """Generate Canvas-compatible identifier — ONLY for net-new content.

    Roundtrip / date-adjust flows PRESERVE the original identifier read from the
    source .imscc (see "Re-Import Behavior"). Regenerating an existing item's id
    makes Canvas duplicate it instead of updating in place.
    """
    # Use UUID5 (deterministic from namespace + name)
    namespace = uuid.UUID('00000000-0000-0000-0000-000000000000')
    identifier_uuid = uuid.uuid5(namespace, f"{content_type}:{title}")
    return "g" + identifier_uuid.hex
```

---

## Re-Import Behavior (Canvas Overwrite Semantics) — CRITICAL for offline_export.py

**Finding (2026-07-12 research, verified against Canvas docs)**: When you re-import an
`.imscc` into a course, Canvas does **not** duplicate content — it **matches by the
original migration identifier and overwrites the matching item in place**. This applies to
Modules, Pages, Assignments, Files, and Quizzes.

### Implication: PRESERVE identifiers on roundtrip — do NOT regenerate them

For the date-adjust roundtrip (export → edit → re-import to the **same** course), you MUST
carry the **original** identifiers from the source `.imscc` through to the output
unchanged. If `offline_export.py` mints **new** identifiers (e.g. via
`generate_canvas_identifier()`), Canvas sees the content as brand-new and **duplicates** it
instead of updating.

- ✅ Existing content (came from the source export) → **reuse its original identifier verbatim**
- ✅ Genuinely new content (created locally, never in Canvas) → generate a fresh `g` + 32 hex id
- ❌ Never regenerate identifiers for content that already exists in Canvas

> This corrects earlier guidance in this file: `generate_canvas_identifier()` is ONLY for
> net-new content. The default offline workflow (import → adjust dates → export) preserves
> every identifier it read.

### ⚠️ Overwrite is DESTRUCTIVE

Canvas warns that re-importing "can cause any changes made to the destination course,
including submissions and grades, to be **lost permanently**." Same-course re-import is
therefore only safe when:

- The destination is an **empty / new** course (the semester-copy workflow — the safe default), OR
- The course has **no student activity yet** (no submissions/grades).

`offline_export.py` / `validate_imscc.py` must surface a **loud guard** before producing an
`.imscc` aimed at a course that already has student work. Lead faculty toward the
**new-course** copy path.

### New Quizzes revert quirk

Re-importing a **New Quizzes** assessment reverts it to the original — edits don't apply. To
update a New Quiz you must duplicate it in Canvas, then import. Flag New Quizzes during
validation so faculty aren't surprised.

### Blueprint-locked items "shift back" (2026-07-12 finding)

If a course is **associated with a Canvas Blueprint**, blueprint-locked items (commonly
standardized things like the end-of-course evaluation) get their locked attributes —
including dates — from the MASTER course. A date-shift + re-import does NOT stick on those
items: the blueprint sync (or the import itself) overrides the shifted dates with the
master's, so they **revert / "shift back."** Shifting a locked item is therefore futile as
well as against policy — **do not touch blueprint-locked items.**

Crucially, **blueprint-lock status is NOT in the `.imscc`** — it's a Canvas-side association,
not exported content. So `imscc_adjust_dates` (which edits the file) cannot see or skip
locked items; it shifts every date, and Canvas reverts the locked ones on import. A
blueprint-aware shift (exclude/flag locked items) would require the **API**
(`GET /courses/:id/blueprint_subscriptions` / blueprint restrictions), not the export.

Observed: the sandbox's "W13 End-of-Course Evaluation" had `lock_at` 59 seconds before
`due_at` (a blueprint-set value Canvas tolerates) — which also surfaced that the date
validator must NOT block on pre-existing source quirks, only on issues a shift introduces.

### Related gradebook finding (not .imscc, but shapes the offline flow)

Canvas gradebook **CSV import does not carry submission comments** — scores only (open,
unimplemented feature request). Offline comment delivery therefore can't ride the CSV;
it needs the API (`grader_push_comments.py`) or manual SpeedGrader paste.

**Sources**:
- Overwrite/identifier-match: <https://classhelp.screenstepslive.com/a/1859694-avoiding-overwriting-course-content-when-using-the-import-tool>
- Destructive re-import: <https://community.canvaslms.com/t5/Idea-Conversations/Import-Course-Content-should-always-be-non-destructive/idi-p/368391>
- CSV comments unsupported: <https://community.instructure.com/en/discussion/510567/including-comments-when-importing-a-grades-csv-file>

---

## What's NOT in .imscc Files

### Student-Specific Data (Requires API)

❌ **Per-student accommodations**:
- SAS accommodations (extended time, extra attempts)
- Individual late exemptions
- Custom due date overrides
- Quiz time extensions

❌ **Student work**:
- Submissions
- Grades
- Comments
- Submission history

❌ **Enrollment data**:
- Student roster
- TA assignments
- Section memberships

❌ **Analytics data**:
- Page views
- Participation metrics
- Access logs

### Course Elements That ARE Included

✅ **Content**:
- Pages (HTML)
- Assignments (metadata + descriptions)
- Quizzes (questions + settings)
- Discussions (prompts)
- Modules (structure + unlock dates)
- Files (actual file binaries)

✅ **Settings**:
- Course-level settings
- Rubrics
- Grading schemes
- External tool configurations

✅ **Dates** (course-level only):
- Assignment due/unlock/lock dates
- Quiz due/unlock/lock dates
- Module unlock dates
- Course start/end dates

---

## Date Adjustment Workflow (for Sprint 4)

### Parsing .imscc for Date Adjustment

```python
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dateutil import parser, tz

def extract_imscc(imscc_path, extract_dir):
    """Extract .imscc ZIP to directory."""
    with zipfile.ZipFile(imscc_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

def parse_assignment_dates(assignment_xml_path):
    """Parse assignment XML and extract dates."""
    tree = ET.parse(assignment_xml_path)
    root = tree.getroot()

    dates = {}
    for date_field in ['due_at', 'unlock_at', 'lock_at']:
        elem = root.find(date_field)
        if elem is not None and elem.text:
            # Parse ISO 8601 with timezone
            dates[date_field] = parser.isoparse(elem.text)

    return dates

def adjust_dates(dates, shift_days):
    """Shift all dates by N days."""
    adjusted = {}
    for field, dt in dates.items():
        adjusted[field] = dt + timedelta(days=shift_days)
    return adjusted

def write_assignment_dates(assignment_xml_path, dates):
    """Update assignment XML with new dates."""
    tree = ET.parse(assignment_xml_path)
    root = tree.getroot()

    for field, dt in dates.items():
        elem = root.find(field)
        if elem is not None:
            # Format back to ISO 8601 with timezone
            elem.text = dt.isoformat()

    tree.write(assignment_xml_path, encoding='utf-8', xml_declaration=True)

def repack_imscc(extract_dir, output_imscc_path):
    """Pack directory back into .imscc ZIP."""
    with zipfile.ZipFile(output_imscc_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, extract_dir)
                zipf.write(file_path, arcname)
```

### Full Workflow

```bash
# 1. Extract .imscc
python offline_import.py --imscc course_export.imscc --output /tmp/extracted/

# 2. Adjust dates (modify XML files in place)
python adjust_dates.py --source /tmp/extracted/ --shift-days 365 --adjust-for-holidays

# 3. Repack to .imscc
python offline_export.py --source /tmp/extracted/ --imscc course_import.imscc

# 4. Upload via Canvas UI
# Settings → Import Course Content → Upload course_import.imscc
```

---

## Timezone Considerations

### Never Assume Pacific Time

Canvas is used globally. Always:

1. **Check `<time_zone_edited>` in assignment files** (if present)
2. **Ask user for timezone preference** during date adjustment
3. **Default to UTC** if unknown

### Timezone Conversion Pattern

```python
from dateutil import tz

def convert_to_user_timezone(dt_utc, user_tz_name="America/Denver"):
    """Convert UTC datetime to user's local timezone."""
    user_tz = tz.gettz(user_tz_name)
    return dt_utc.astimezone(user_tz)

def convert_to_utc(dt_local, user_tz_name="America/Denver"):
    """Convert local datetime to UTC for storage."""
    user_tz = tz.gettz(user_tz_name)
    dt_aware = dt_local.replace(tzinfo=user_tz)
    return dt_aware.astimezone(tz.UTC)
```

### Holiday Adjustment Strategy

```python
def adjust_for_holidays(dates, holidays, strategy="skip"):
    """
    Adjust dates that fall on holidays.

    Args:
        dates: List of datetime objects
        holidays: List of holiday date objects
        strategy: "skip" (move to next day) or "previous" (move to previous day)
    """
    adjusted = []
    for dt in dates:
        if dt.date() in holidays:
            if strategy == "skip":
                # Move forward to next non-holiday
                while dt.date() in holidays:
                    dt += timedelta(days=1)
            elif strategy == "previous":
                # Move backward to previous non-holiday
                while dt.date() in holidays:
                    dt -= timedelta(days=1)
        adjusted.append(dt)
    return adjusted
```

---

## Testing Strategy

### Sample .imscc for Testing

**Minimum viable .imscc for testing**:
```
test_course.imscc
├── imsmanifest.xml          # Minimal manifest
├── course_settings/
│   ├── course_settings.xml  # Basic course info
│   ├── module_meta.xml      # 1 module, 1 assignment
│   └── syllabus.html        # Empty or minimal
└── assignment_001/
    └── assignment_settings.xml  # 1 assignment with dates
```

### Validation Checklist

After date adjustment, verify:

- [ ] All dates are still in ISO 8601 format with timezone
- [ ] `unlock_at < due_at < lock_at` constraints maintained
- [ ] Module unlock dates adjusted consistently
- [ ] Course start/end dates adjusted
- [ ] Timezone preserved (don't accidentally convert to wrong TZ)
- [ ] ZIP file is valid (can be extracted)
- [ ] Identifiers unchanged (still `g` + 32 hex chars)
- [ ] Canvas successfully imports the .imscc

---

## Common Pitfalls

### 1. Human-Readable Identifiers

**Problem**: Using `assignment_week1` instead of `g14e5e1d8a8b4f0e9a1c2d3e4f5a6b7c8`
**Symptom**: Canvas import silently fails (no error, content missing)
**Fix**: Always use `g` + 32 hex char format

### 2. Missing course_settings/ Files

**Problem**: No `course_settings.xml` or `syllabus.html`
**Symptom**: Canvas treats as generic IMS CC, modules don't import
**Fix**: Always include both files (can be minimal)

### 3. Timezone Conversion Errors

**Problem**: Converting dates but losing timezone info
**Symptom**: Dates shift by hours after import
**Fix**: Always preserve timezone in ISO 8601 format

### 4. Breaking Date Constraints

**Problem**: Adjusting `due_at` but not `lock_at`, creating `lock_at < due_at`
**Symptom**: Canvas import fails with validation error
**Fix**: Adjust all three dates (`unlock_at`, `due_at`, `lock_at`) together

### 5. Forgetting Module Dates

**Problem**: Adjusting assignment dates but not module unlock dates
**Symptom**: Assignments have correct dates but modules are locked
**Fix**: Parse and adjust `module_meta.xml` unlock dates

---

## References

- **IMS Global CC Spec**: https://www.imsglobal.org/cc/index.html
- **Canvas API Assignment Docs**: https://canvas.instructure.com/doc/api/assignments.html
- **canvas-imscc Skill**: https://github.com/brockcraft/canvas-imscc (example implementation)
- **Canvas LMS Source**: https://github.com/instructure/canvas-lms (for edge cases)

---

## Sprint 4 Implementation Checklist

When building `offline_import.py` and `offline_export.py`:

- [ ] Unzip .imscc to temp directory
- [ ] Parse `imsmanifest.xml` (resource declarations)
- [ ] Parse `module_meta.xml` (module structure)
- [ ] Parse individual assignment XML files (dates)
- [ ] Convert `.imscc` structure → `.canvas/` JSON structure
- [ ] Build `adjust_dates.py` tool (operate on `.canvas/` JSON)
- [ ] Convert `.canvas/` JSON → `.imscc` structure
- [ ] Preserve original identifiers on roundtrip; generate `g` + 32 hex ONLY for net-new content
- [ ] Preserve timezone info in all date operations
- [ ] Validate date constraints before repacking
- [ ] Create valid ZIP with all required files
- [ ] Test import in Canvas sandbox course

**Success Criteria**: Export → Adjust → Import produces working course with correct dates.

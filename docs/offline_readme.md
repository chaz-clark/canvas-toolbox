# Canvas Toolbox - Offline Mode Guide

**For faculty without API access** - Use Canvas UI downloads + local processing

---

## What is Offline Mode?

Offline mode allows you to use Canvas Toolbox tools **without a Canvas API token**. Instead of connecting directly to Canvas via API, you:

1. **Download** files via Canvas UI (Settings → Export, Grades → Export, etc.)
2. **Process** locally using Canvas Toolbox tools (same editing workflow)
3. **Upload** results back to Canvas via UI (Settings → Import, Grades → Import)

**Benefits**:
- Works when IT restricts API access
- Faculty-controlled (no permanent API credentials)
- Same editing workflows (e.g., `_all_comments.md`)
- FERPA-compliant (automatic de-identification)

**Tradeoffs**:
- Manual download/upload steps (vs automatic API sync)
- Some tools require data not available via Canvas UI
- Slower for bulk operations

---

## Quick Start

### 1. Configure Offline Mode

```bash
# In your .env file
CANVAS_MODE=offline  # Enable offline mode
CANVAS_TOKEN=        # Leave empty (no API token needed)
```

### 2. Download Course Data (via Canvas UI)

**Course Content** (for course copying, date adjustment):
- Canvas → Course → Settings → Export Course Content
- Select: "Common Cartridge (.imscc)"
- Download: `course_export_145706.imscc` → `~/Downloads/`

**Gradebook** (for grading workflows):
- Canvas → Grades → Export
- Select: "Export Entire Gradebook"
- Download: `grades-145706.csv` → `~/Downloads/`

**Submissions** (for grading individual assignments):
- Canvas → Assignments → [Assignment Name] → Download Submissions
- Download: `submissions_123.zip` → `~/Downloads/`

### 3. Run Tools (Same as API Mode)

Tools automatically detect files in `~/Downloads/`:

```bash
# Grading workflow
python lib/tools/grader_fetch.py              # Auto-detects submissions_*.zip
python lib/tools/grader_grade.py              # Works on local files
python lib/tools/grader_push.py               # Exports CSV for upload

# Course management
python lib/tools/canvas_sync.py --import-imscc ~/Downloads/course_export.imscc
python lib/tools/adjust_dates.py --shift-days 365
python lib/tools/sync_to_new.py --export-imscc ~/Desktop/course_import.imscc
```

### 4. Upload Results (via Canvas UI)

**Grades**:
- Canvas → Grades → Import
- Upload: `grades-145706-updated.csv`

**Course Content**:
- Canvas → Settings → Import Course Content
- Upload: `course_import.imscc`

---

## Workflows

### Workflow 1: Grading Assignments (Offline)

**Download** (via Canvas UI):
```
1. Grades → Export → grades-145706.csv → ~/Downloads/
2. Assignments → [Assignment] → Download Submissions → submissions_123.zip → ~/Downloads/
```

**Process** (using tools):
```bash
# Set offline mode
echo "CANVAS_MODE=offline" >> .env

# Fetch submissions (auto-detects ~/Downloads)
python lib/tools/grader_fetch.py
# Output: ✓ Found submissions: ~/Downloads/submissions_123.zip
# Output: ⚠ Real student data detected - de-identifying...

# Grade locally
vim course/_all_comments.md  # Edit grades and comments

# Generate upload CSV
python lib/tools/grader_push.py
# Output: ✓ Export for upload: ~/Desktop/grades-145706-updated.csv
```

**Upload** (via Canvas UI):
```
Grades → Import → Upload grades-145706-updated.csv
```

**Result**: Grades and comments updated in Canvas (same as API mode)

---

### Workflow 2: Copy Course to New Semester (Offline)

**Download** (via Canvas UI):
```
Settings → Export Course Content → .imscc → course_export_145706.imscc → ~/Downloads/
```

**Process** (using tools):
```bash
# Import course content
python lib/tools/canvas_sync.py --import-imscc ~/Downloads/course_export_145706.imscc
# Output: ✓ Imported to .canvas/ directory

# Adjust dates for new semester
python lib/tools/adjust_dates.py --shift-days 365

# Export for new course
python lib/tools/sync_to_new.py --export-imscc ~/Desktop/course_spring_2027.imscc
# Output: ✓ Exported to course_spring_2027.imscc
```

**Upload** (via Canvas UI):
```
1. Create new course in Canvas (or use existing empty course)
2. Settings → Import Course Content → Upload course_spring_2027.imscc
```

**Result**: New course created with adjusted dates (same as API workflow)

---

### Workflow 3: Audit Course Quality (Offline)

**Download** (via Canvas UI):
```
Settings → Export Course Content → .imscc → course_export.imscc → ~/Downloads/
```

**Process** (using tools):
```bash
# Import course
python lib/tools/canvas_sync.py --import-imscc ~/Downloads/course_export.imscc

# Run audits (all work on local data)
python lib/tools/course_audit.py
python lib/tools/course_alignment_audit.py
python lib/tools/accessibility_audit.py
python lib/tools/rubric_quality_audit.py

# Review reports in course/reports/
```

**No Upload Needed** - Audits are read-only reports

---

## Tool Compatibility Matrix

### ✅ Fully Supported in Offline Mode

These tools work identically in offline mode (with `.imscc` or CSV downloads):

| Tool | Offline Data Source | Notes |
|------|---------------------|-------|
| **Grading Tools** |
| `grader_fetch.py` | `submissions_*.zip` (UI download) | Auto-detects ~/Downloads |
| `grader_grade.py` | Local files | Works on fetched submissions |
| `grader_push.py` | Local CSV | Exports CSV for UI upload |
| `grader_deidentify_*` | Local files | De-ID happens automatically |
| `grader_reidentify.py` | Local mapping | Re-ID before upload |
| `fix_group_override_recalc.py` | `grades-*.csv` (UI export) | Recalculates weighted grades |
| **Course Management** |
| `canvas_sync.py` | `.imscc` file (UI export) | Use `--import-imscc` flag |
| `sync_to_new.py` | `.canvas/` directory | Use `--export-imscc` flag |
| `adjust_dates.py` | Local JSON | No Canvas connection needed |
| `course_mirror.py` | `.imscc` import/export | Roundtrip via UI |
| **Auditing Tools** |
| `course_audit.py` | `.imscc` import | Audits local course data |
| `course_alignment_audit.py` | `.imscc` import | Checks learning objectives |
| `accessibility_audit.py` | `.imscc` import | WCAG compliance check |
| `rubric_quality_audit.py` | `.imscc` import | Rubric analysis |
| `rubric_coverage_audit.py` | `.imscc` import | CLO coverage |
| `grading_structure_audit.py` | `.imscc` import | Assignment structure |
| `content_representation_audit.py` | `.imscc` import | Media balance |
| `syllabus_audit.py` | `.imscc` import | Syllabus completeness |
| `workload_audit.py` | `.imscc` import | Student workload analysis |
| **Utilities** |
| `deidentify_gradebook.py` | `grades-*.csv` | PII removal |
| `reidentify_gradebook.py` | De-identified CSV | PII restoration |
| `export_imscc.py` | `.canvas/` directory | Pack for Canvas import |

---

### ⚠️ Partially Supported (Limited Functionality)

These tools work offline but with reduced capabilities:

| Tool | Offline Limitation | Workaround |
|------|-------------------|------------|
| `course_engagement_audit.py` | No page views / participation data | Download multiple semester exports for basic trend analysis |
| `grader_submission_health.py` | No real-time submission status | Use submission timestamps from downloaded ZIP |
| `module_structure_diff.py` | Requires two .imscc files | Download both courses via UI, import separately |

---

### ❌ Not Supported in Offline Mode

These tools require API-only data not available via Canvas UI:

| Tool | Why API Required | Alternative |
|------|------------------|-------------|
| **Analytics & Engagement** |
| `course_engagement_audit.py` (full) | Page views, participation metrics | Use Canvas Analytics UI |
| `grading_load_audit.py` | Real-time grading workload data | Manual tracking in spreadsheet |
| **Blueprint Operations** |
| `blueprint_sync.py` | Blueprint sync requires API | Use Canvas UI for blueprint sync |
| `blueprint_presync_check.py` | Checks API-only blueprint metadata | Manual verification |
| `blueprint_exception_report.py` | Blueprint exception tracking | Canvas UI reports |
| `blueprint_orphan_pages.py` | Cross-course blueprint comparison | Manual comparison |
| **Student-Specific Modifications** |
| `apply_sas_accommodations.py` | Per-student accommodation updates | Canvas SAS integration UI |
| `student_quiz_time_extension.py` | Per-student quiz time adjustments | Canvas quiz settings UI (individual) |
| `student_late_accommodation.py` | Per-student late exemptions | Canvas assignment settings UI |
| `exempt_by_date.py` | Per-student assignment exemptions | Canvas gradebook UI (individual) |
| `submit_on_behalf.py` | Student submission creation | Manual Canvas UI submission |
| **Real-Time Operations** |
| `grader_pull_ta_grades.py` | Pull TA grades from API | Use Canvas Gradebook export |
| `submission_history_fetch.py` | Submission version history | Download submission comments via UI |
| **Development Tools** |
| `sandbox_rubric_fixtures.py` | Creates test rubrics via API | Create manually in Canvas |
| `canvas_api_tool.py` | Direct API access | N/A (API tool) |
| **Voting/Feature Tools** |
| `vote_feature.py` | Canvas Community API | Use Canvas Community website |
| `update_roadmap_votes.py` | GitHub + Canvas integration | Manual updates |
| `add_roadmap_feature.py` | GitHub issue creation | Use GitHub UI |

---

## Data Sources Quick Reference

### What You Can Download via Canvas UI

| Canvas UI Action | File Format | Tools That Use It |
|------------------|-------------|-------------------|
| **Settings → Export Course Content** | `.imscc` (ZIP) | `canvas_sync.py`, all audit tools, `sync_to_new.py`, date adjustment tools |
| **Grades → Export** | `.csv` | `grader_push.py`, `fix_group_override_recalc.py`, de-ID tools |
| **Assignment → Download Submissions** | `.zip` | `grader_fetch.py`, all `grader_deidentify_*` tools |
| **Gradebook → Comments** | Included in CSV | `grader_push.py` (comments column) |

**Important**: `.imscc` files include **course-level dates** (assignment due dates, unlock dates, lock dates, module unlock dates). This means you CAN adjust dates for semester copies offline! However, `.imscc` does NOT include **student-specific** accommodations (SAS extensions, individual quiz time, late exemptions).

### What's NOT Available via UI

| Data Type | Why API Required | Impact |
|-----------|------------------|--------|
| **Page Views** | Analytics API only | No engagement tracking |
| **Participation Metrics** | Analytics API only | No activity tracking |
| **Submission Version History** | API pagination required | No version comparison |
| **Real-Time Submission Status** | API polling required | No live tracking |
| **Blueprint Metadata** | Blueprint API only | No blueprint automation |
| **Cross-Course Comparisons** | Requires multi-course API access | Manual comparison needed |

---

## FERPA Compliance in Offline Mode

### Automatic De-Identification

When you download a gradebook CSV via Canvas UI, it contains **real student names**. Canvas Toolbox automatically de-identifies this data for local work:

**Before De-ID** (as downloaded from Canvas):
```csv
Student,ID,SIS User ID,Assignment1,Assignment2
"Doe, John",12345,sis123,95,88
"Smith, Jane",12346,sis456,92,90
```

**After De-ID** (automatic, used for local work):
```csv
Student,ID,SIS User ID,Assignment1,Assignment2
"Student 001",1,sid001,95,88
"Student 002",2,sid002,92,90
```

**Re-ID for Upload** (automatic, before Canvas import):
```csv
Student,ID,SIS User ID,Assignment1,Assignment2,Comments
"Doe, John",12345,sis123,95,88,"Great work!"
"Smith, Jane",12346,sis456,92,90,"Excellent analysis"
```

### How It Works

1. **Download**: You get real student data from Canvas
2. **Auto De-ID**: Tool detects PII and de-identifies before local work
3. **Work Safely**: Edit grades/comments with anonymous data
4. **Auto Re-ID**: Tool restores real names before export
5. **Upload**: You upload real student data back to Canvas

**Mapping File**: `.canvas/gradebook/student_mapping.json` (git-ignored)

**No Manual Steps**: De-ID/Re-ID happens automatically when tools detect real names

---

## Troubleshooting

### "No data source available"

**Problem**: Tool can't find API token or downloaded files

**Solution**:
```bash
# 1. Verify offline mode is set
grep CANVAS_MODE .env
# Should show: CANVAS_MODE=offline

# 2. Check for downloaded files
ls -la ~/Downloads/grades-*.csv
ls -la ~/Downloads/submissions_*.zip
ls -la ~/Downloads/*.imscc

# 3. Download via Canvas UI if missing (see Quick Start above)
```

---

### "CSV format not recognized"

**Problem**: Downloaded CSV doesn't match expected Canvas format

**Solution**:
```bash
# Ensure you downloaded via "Export Entire Gradebook" (not "Export Current View")
# Canvas UI: Grades → Actions → Export → Export Entire Gradebook
```

---

### "Real student data detected in export"

**Warning** (not error): Tool is reminding you it will de-identify

**Action**: This is normal. Tool will automatically de-identify before local work.

**Verify**:
```bash
# Check that mapping file was created
ls -la .canvas/gradebook/student_mapping.json

# Verify CSV is de-identified
head .canvas/gradebook/grades-deidentified.csv
# Should show "Student 001", not real names
```

---

### "Cannot upload de-identified CSV"

**Problem**: Trying to upload anonymous CSV to Canvas (would fail)

**Solution**: Use the re-identified export:
```bash
# Tool automatically creates re-identified CSV
ls ~/Desktop/grades-*-updated.csv

# Upload this file (has real names restored)
# Canvas: Grades → Import → Upload grades-*-updated.csv
```

---

### ".imscc file is corrupted or incomplete"

**Problem**: Canvas export failed or file truncated during download

**Solution**:
```bash
# 1. Verify file size is reasonable (>1MB for most courses)
ls -lh ~/Downloads/*.imscc

# 2. Re-export from Canvas
# Settings → Export Course Content → Wait for email → Download fresh copy

# 3. Verify ZIP is valid
unzip -t ~/Downloads/course_export.imscc
```

---

## Hybrid Mode (Recommended for Most Faculty)

You don't have to choose all-or-nothing. **Hybrid mode** uses API when available, falls back to CSV when not:

```bash
# .env configuration
CANVAS_MODE=online       # Use API by default
CANVAS_TOKEN=<token>     # Keep your token
```

**Benefits**:
- Fast API operations when IT allows
- CSV backup workflow when API restricted
- Smooth transition if IT policy changes

**Example**:
```bash
# Normally: API mode (fast)
python lib/tools/grader_push.py
# → Uploads via API

# When API blocked: Download CSV manually
# ~/Downloads/grades-145706.csv

# Tool auto-detects and uses CSV
python lib/tools/grader_push.py
# → Exports CSV for manual upload
```

---

## Migration Path

Faculty can transition gradually:

```
100% API → Hybrid (API + CSV backup) → 100% Offline
```

1. **Start with API mode** - Fastest, most convenient
2. **Try hybrid mode** - Keep API, learn CSV workflow
3. **Switch to offline if needed** - When IT restricts API

**No lock-in**: Switch modes anytime by changing `.env`

---

## FAQ

### Q: Is offline mode slower?

**A**: Download/upload steps add time, but **editing workflows are identical**. Grading 50 students takes the same time whether you use API or CSV.

**Overhead**: ~2-5 minutes for download + upload steps per session

---

### Q: Can I mix API and CSV workflows?

**A**: Yes! Use hybrid mode. Tools auto-detect data source.

---

### Q: Will offline mode work forever?

**A**: Yes, as long as Canvas supports CSV import/export and .imscc format (both are stable, decade-old Canvas features).

---

### Q: What if Canvas changes CSV format?

**A**: Tools include format detection and validation. We'll update parsers if Canvas changes formats.

---

### Q: Can I still use API mode after setting up offline mode?

**A**: Yes! Just change `CANVAS_MODE=online` in `.env` and tools will use API.

---

### Q: Is my data safe in offline mode?

**A**: Yes. De-identification is automatic, mapping files are git-ignored, and PII is only restored at the last moment before Canvas upload.

---

## Next Steps

1. **Try offline grading workflow** (Workflow 1 above) - Most common use case
2. **Test course copy workflow** (Workflow 2 above) - Useful for semester setup
3. **Run course audits** (Workflow 3 above) - Quality improvement
4. **Read**: [offline_mode.md](./offline_mode.md) - Technical architecture
5. **Read**: [offline_mode_sprints.md](./offline_mode_sprints.md) - Implementation plan

---

## Support

**Issues**: If a tool doesn't work in offline mode as documented, please report:
- Tool name
- Error message
- Which Canvas UI download you used
- Your `.env` configuration (without token)

**Feature Requests**: Request offline support for currently API-only tools via GitHub issues.

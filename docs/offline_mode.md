# Offline Mode Plan
**Goal**: Support faculty who cannot use Canvas API tokens (IT policy restriction)

## Philosophy: Unified Workflow

Tools should work identically whether faculty have API access or not. The only difference is the **transfer layer**:

```
API Mode:     Tool → Canvas API → Canvas
Offline Mode: Tool → Local Files → Faculty Upload → Canvas
```

Everything between "download" and "upload" is **exactly the same**.

---

## Current API Operations → File Equivalents

### Read Operations

| Current API Call | Canvas UI Download | File Format | Location |
|------------------|-------------------|-------------|----------|
| **Course Content** |
| GET /courses/:id | Settings → Export Course Content | `.imscc` (ZIP) | `~/Downloads/` |
| GET /courses/:id/modules | ↑ (included in export) | `imsmanifest.xml` | Inside `.imscc` |
| GET /courses/:id/pages | ↑ (included in export) | `*.html` files | Inside `.imscc` |
| GET /courses/:id/assignments | ↑ (included in export) | `*.xml` per assignment | Inside `.imscc` |
| GET /courses/:id/files | ↑ (included in export) | Actual files | Inside `.imscc` |
| **Gradebook** |
| GET /courses/:id/students | Grades → Export Entire Gradebook | `grades-{id}.csv` | `~/Downloads/` |
| GET /assignments/:id/submissions | ↑ (grades included) | CSV columns per assignment | Same CSV |
| GET /submissions/:id/comments | ↑ (comments included) | `Comments` column | Same CSV |
| **Submissions** |
| GET /assignments/:id/submissions (files) | Assignment → Download Submissions | `submissions.zip` | `~/Downloads/` |
| **Analytics** |
| GET /courses/:id/analytics | No UI equivalent | ❌ Not available offline | N/A |

### Write Operations

| Current API Call | Canvas UI Upload | File Format | Process |
|------------------|------------------|-------------|---------|
| **Content Updates** |
| POST /courses/:id/pages | Settings → Import Course Content | `.imscc` (modified) | Manual import |
| PUT /assignments/:id | ↑ (assignments included) | `.imscc` (modified) | Manual import |
| **Grades & Comments** |
| POST /submissions/:id/grade | Grades → Import | `grades-{id}.csv` (edited) | Manual upload |
| POST /submissions/:id/comment | ↑ (comments column) | CSV with `Comments` column | Same |
| PUT /assignments/:id/due_at | Must use API or edit in UI | ❌ Not in CSV | Manual in UI |

---

## Offline Workflow Architecture

### Phase 1: Download (Faculty Action)

**Via Canvas UI**:
1. **Course Content**: Settings → Export → `.imscc` → Save to `~/Downloads/course_export.imscc`
2. **Gradebook**: Grades → Export → `.csv` → Save to `~/Downloads/grades-{course_id}.csv`
3. *(Optional)* **Submissions**: Per-assignment → Download → Save to `~/Downloads/submissions_assignment_{id}.zip`

**Tool Auto-Detection**:
```bash
# Tool checks for files in order of preference:
# 1. API available? Use it
# 2. Files in ~/Downloads? Use them
# 3. Files in .canvas/? Use them (cached)
# 4. Error: No data source available
```

### Phase 2: Unpack → Standard Format

**Tool**: `offline_import.py`

```bash
# Convert Canvas exports to .canvas/ directory structure
python lib/tools/offline_import.py \
  --imscc ~/Downloads/course_export.imscc \
  --gradebook ~/Downloads/grades-145706.csv \
  --output .canvas/
```

**Result**: Same `.canvas/` structure that `canvas_sync.py --pull-all` creates:
```
.canvas/
  index.json           # Course metadata + structure
  files/               # Mapping of all files
course/
  modules/             # Module structure
  pages/               # Page HTML files
  assignments/         # Assignment JSON files
  _files/              # Actual file attachments
gradebook/
  grades.csv           # Normalized gradebook
  students.json        # Student roster
```

### Phase 3: Work Locally (Existing Tools - No Changes!)

Tools work **identically** in both modes because they read from `.canvas/`:

```bash
# Date adjustment (existing)
python lib/tools/adjust_dates.py --shift-days 365

# Grading workflow (existing)
python lib/tools/grade_assignments.py --generate-comments
# Edit: course/_all_comments.md
python lib/tools/grade_assignments.py --apply-comments

# Analysis (existing)
python lib/tools/course_audit.py
```

### Phase 4: Pack → Export Format

**Tool**: `offline_export.py`

```bash
# Convert .canvas/ back to Canvas import formats
python lib/tools/offline_export.py \
  --source .canvas/ \
  --imscc ~/Desktop/course_import.imscc \
  --gradebook ~/Desktop/grades_updated.csv
```

**Outputs**:
1. `course_import.imscc` - Modified course content (dates adjusted, assignments updated)
2. `grades_updated.csv` - Updated grades + comments (from `_all_comments.md`)

### Phase 5: Upload (Faculty Action)

**Via Canvas UI**:
1. **Course Content**: Settings → Import → Upload `course_import.imscc` → Import
2. **Gradebook**: Grades → Import → Upload `grades_updated.csv` → Import

---

## Implementation: Gradebook CSV → _all_comments.md Integration

### Current Workflow (API Mode):
```bash
# 1. Download via API
python lib/tools/grade_assignments.py --generate-comments

# 2. Creates course/_all_comments.md with:
# Student Name | Assignment | Current Grade | Comments | New Grade

# 3. Faculty edits in markdown

# 4. Upload via API
python lib/tools/grade_assignments.py --apply-comments
```

### New Workflow (Offline Mode):
```bash
# 1. Faculty downloads CSV: grades-145706.csv → ~/Downloads/

# 2. Tool imports CSV → .canvas/gradebook/
python lib/tools/offline_import.py --gradebook ~/Downloads/grades-145706.csv

# 3. Generate comments (same tool!)
python lib/tools/grade_assignments.py --generate-comments
# Reads from: .canvas/gradebook/grades.csv (normalized from Canvas CSV)
# Writes to: course/_all_comments.md

# 4. Faculty edits _all_comments.md

# 5. Apply comments to CSV (same tool, different output!)
python lib/tools/grade_assignments.py --apply-comments --offline
# Reads from: course/_all_comments.md
# Writes to: .canvas/gradebook/grades.csv (updated)

# 6. Export CSV in Canvas format
python lib/tools/offline_export.py --gradebook ~/Desktop/grades_updated.csv
# Converts: .canvas/gradebook/grades.csv → Canvas CSV format

# 7. Faculty uploads via Canvas UI
# Grades → Import → Upload grades_updated.csv
```

**Key insight**: `_all_comments.md` stays **exactly the same** - tools just read/write different formats at the edges.

---

## Tool Modifications Required

### 1. Auto-Detect Data Source

**Every tool that reads data needs**:
```python
def get_data_source():
    """Determine data source in order of preference."""
    # 1. API available?
    if os.environ.get("CANVAS_TOKEN"):
        return DataSource.API

    # 2. Downloaded files?
    if Path("~/Downloads").glob("grades-*.csv"):
        return DataSource.DOWNLOADS

    # 3. Cached .canvas/?
    if Path(".canvas/index.json").exists():
        return DataSource.CACHED

    raise NoDataSourceError("No API token, downloads, or cached data")
```

### 2. Read Abstraction Layer

**Before**:
```python
# Direct API call
grades = api.get_gradebook(course_id)
```

**After**:
```python
# Unified interface
grades = get_gradebook()  # Auto-detects source
```

**Implementation**:
```python
def get_gradebook() -> pd.DataFrame:
    """Get gradebook from any available source."""
    source = get_data_source()

    if source == DataSource.API:
        return api.get_gradebook(course_id)

    elif source == DataSource.DOWNLOADS:
        csv_path = find_latest_gradebook_csv("~/Downloads")
        return read_canvas_gradebook_csv(csv_path)

    elif source == DataSource.CACHED:
        return read_gradebook_cache(".canvas/gradebook/grades.csv")
```

### 3. Write Abstraction Layer

**Before**:
```python
# Direct API call
api.update_grade(submission_id, grade, comment)
```

**After**:
```python
# Unified interface
update_grade(student_id, assignment_id, grade, comment)  # Auto-routes
```

**Implementation**:
```python
def update_grade(student_id, assignment_id, grade, comment):
    """Update grade via any available method."""
    source = get_data_source()

    if source == DataSource.API:
        api.update_grade(submission_id, grade, comment)
        print("✓ Updated via API")

    else:  # DOWNLOADS or CACHED
        # Update local CSV
        update_gradebook_csv(student_id, assignment_id, grade, comment)
        print("✓ Updated local CSV")
        print("  Export and upload to Canvas when ready:")
        print("  python lib/tools/offline_export.py --gradebook grades_updated.csv")
```

---

## Tools That Need Offline Support

### Priority 1: Grading Tools (Most Critical)

| Tool | Current Mode | Offline Support | Effort |
|------|--------------|-----------------|--------|
| `grade_assignments.py --generate-comments` | API read | ✅ CSV read | Low |
| `grade_assignments.py --apply-comments` | API write | ✅ CSV write | Low |
| `fix_group_override_recalc.py` | API read/write | ✅ CSV read/write | Medium |

### Priority 2: Course Management

| Tool | Current Mode | Offline Support | Effort |
|------|--------------|-----------------|--------|
| `canvas_sync.py --pull-all` | API read | ✅ Import from .imscc | High |
| `sync_to_new.py` | API write | ✅ Export to .imscc | High |
| `adjust_dates.py` | Local files | ✅ Already works | None |

### Priority 3: Analysis Tools

| Tool | Current Mode | Offline Support | Effort |
|------|--------------|-----------------|--------|
| `course_audit.py` | API read | ✅ .imscc read | Medium |
| `course_engagement_audit.py` | API read | ⚠️ Partial (no analytics) | High |

---

## File Format Specifications

### Canvas Gradebook CSV Format

**Structure**:
```csv
Student,ID,SIS User ID,SIS Login ID,Section,Assignment1,Assignment2,...
"Doe, John",12345,sis123,john@example.com,Section 01,95,87,...
```

**Columns**:
- `Student`: Full name (Last, First)
- `ID`: Canvas user ID
- `SIS User ID`: Institution ID
- `SIS Login ID`: Email/username
- `Section`: Course section
- `[Assignment Name]`: Grade (points or blank)
- `[Assignment Name] (Comments)`: Submission comments (optional)

**Special Values**:
- `""` or blank: No submission
- `EX`: Excused
- `0`: Zero points (different from no submission!)

### Canvas Common Cartridge (.imscc) Format

**Structure** (ZIP file):
```
course_export.imscc/
  imsmanifest.xml          # Table of contents
  course_settings/
    course_settings.xml    # Course metadata
  wiki_content/
    *.html                 # Pages
  assessment/
    *.xml                  # Quizzes/assignments
  web_resources/
    *.jpg, *.pdf, ...      # Files
```

**Key Files**:
- `imsmanifest.xml`: Maps all resources (modules, pages, files)
- `course_settings.xml`: Dates, navigation, settings
- Individual HTML/XML files for content

---

## FERPA Compliance: De-Identification Tool

**Problem**: Downloaded CSV contains PII (student names, IDs, emails)

**Use Cases**:
- Sharing with TAs/graders
- Testing tools with sample data
- Documentation/examples
- Git commits (for tracking changes to structure)

### De-Identification Tool: `deidentify_gradebook.py`

**Usage**:
```bash
# De-identify downloaded gradebook
python lib/tools/deidentify_gradebook.py \
  --input ~/Downloads/grades-145706.csv \
  --output grades-145706-deidentified.csv \
  --mapping .canvas/gradebook/student_mapping.json
```

**What It Does**:
```csv
Before:
Student,ID,SIS User ID,SIS Login ID,Section,Assignment1
"Doe, John",12345,sis123,john@example.com,Section 01,95

After:
Student,ID,SIS User ID,SIS Login ID,Section,Assignment1
"Student 001",1,sid001,student001@example.com,Section 01,95
```

**Mapping File** (`.canvas/gradebook/student_mapping.json`):
```json
{
  "12345": {
    "original_name": "Doe, John",
    "anonymous_name": "Student 001",
    "original_id": "sis123",
    "anonymous_id": "sid001"
  }
}
```

**Re-Identification** (for re-upload):
```bash
# After grading with anonymous data, restore real names
python lib/tools/reidentify_gradebook.py \
  --input grades-deidentified-updated.csv \
  --mapping .canvas/gradebook/student_mapping.json \
  --output grades-145706-updated.csv
```

**Security**:
- Mapping file stored in `.canvas/gradebook/` (git-ignored)
- Never commit real student data
- Tools detect de-identified CSVs and warn before upload

### Workflow Integration with Existing Grading Tool

**Current Pattern** (grade_assignments.py already does this):
```python
# 1. Check for API
if has_api_token():
    submissions = api.download_submissions()

# 2. Fallback to ~/Downloads
else:
    zip_path = find_latest_file("~/Downloads/submissions_*.zip")
    submissions = extract_submissions(zip_path)

# 3. Process locally (same code path)
process_submissions(submissions)
```

**Add Gradebook CSV Support** (same pattern):
```python
# 1. Check for API
if has_api_token():
    gradebook = api.get_gradebook()

# 2. Fallback to ~/Downloads
else:
    csv_path = find_latest_file("~/Downloads/grades-*.csv")

    # Auto-detect if de-identification needed
    if contains_real_names(csv_path):
        print("⚠ Real student data detected")
        print("  De-identifying for local work...")
        gradebook = deidentify_csv(csv_path)
    else:
        gradebook = read_csv(csv_path)

# 3. Process locally (same code path)
generate_comments(gradebook)  # → _all_comments.md
```

**Faculty Workflow** (simplified):
```bash
# Faculty downloads via UI:
# 1. Grades → Export → grades-145706.csv → ~/Downloads/
# 2. Assignment → Download Submissions → submissions_123.zip → ~/Downloads/

# Run tool (auto-detects and uses Downloads):
$ python lib/tools/grade_assignments.py --generate-comments
✓ Found gradebook: ~/Downloads/grades-145706.csv
⚠ Real student data detected - de-identifying for local work...
✓ Found submissions: ~/Downloads/submissions_123.zip
✓ Generated course/_all_comments.md (42 students, de-identified)

# Edit comments:
$ vim course/_all_comments.md

# Apply comments:
$ python lib/tools/grade_assignments.py --apply-comments
✓ Updated grades in: .canvas/gradebook/grades.csv (de-identified)
✓ Export for upload: grades-145706-updated.csv (re-identified)

Then upload via Canvas UI: Grades → Import → grades-145706-updated.csv
```

**Key Simplification**:
- No explicit de-ID command needed
- Tool auto-detects PII and handles it
- Faculty just: Download → Edit → Upload
- Same 3-step workflow as API mode

**Features**:
- ✅ Consistent IDs across sessions (same student always gets same anonymous ID)
- ✅ Preserves section structure
- ✅ Maintains grade/comment relationships
- ✅ Reversible (mapping file = key)
- ✅ Git-safe (no PII in commits)

---

## Implementation Phases

### Phase A: Foundation (Week 1)
- [ ] `offline_import.py` - Unpack `.imscc` → `.canvas/`
- [ ] `offline_export.py` - Pack `.canvas/` → `.imscc`
- [ ] CSV import/export utilities
- [ ] Data source auto-detection
- [ ] `deidentify_gradebook.py` - Remove PII from CSV
- [ ] `reidentify_gradebook.py` - Restore PII before upload

### Phase B: Grading Tools (Week 2)
- [ ] `grade_assignments.py` offline mode
- [ ] CSV ↔ `_all_comments.md` integration
- [ ] `fix_group_override_recalc.py` offline mode
- [ ] De-ID detection in all tools (warn if uploading anonymous data)

### Phase C: Course Management (Week 3)
- [ ] `canvas_sync.py` import from `.imscc`
- [ ] `sync_to_new.py` export to `.imscc`
- [ ] Date adjustment verification

### Phase D: Testing & Documentation (Week 4)
- [ ] End-to-end offline workflow test
- [ ] Faculty user guide
- [ ] Troubleshooting guide

---

## User Experience Comparison

### API Mode (Current):
```bash
# 1-step workflow
$ python lib/tools/grade_assignments.py --apply-comments
✓ Updated 42 grades via API
```

### Offline Mode (New):
```bash
# Multi-step but still straightforward
$ python lib/tools/grade_assignments.py --apply-comments --offline
✓ Updated 42 grades in local CSV

Export for Canvas upload:
  python lib/tools/offline_export.py --gradebook ~/Desktop/grades.csv

Then in Canvas:
  Grades → Import → Upload grades.csv
```

**Key**: Same editing workflow (`_all_comments.md`), different transfer method.

---

## Edge Cases & Limitations

### What Works Offline:
- ✅ Course content (pages, assignments, files)
- ✅ Gradebook (grades, comments)
- ✅ Date adjustments
- ✅ Local analysis/reports

### What Requires API:
- ❌ Analytics data (page views, participation)
- ❌ Real-time grade sync
- ❌ Automated submission downloads
- ❌ Bulk operations (>1000 students)

### Import Behavior:
- **Canvas matches by name**: "Assignment 1" in CSV must match "Assignment 1" in course
- **Overwrites on conflict**: New grade replaces old (irreversible via UI)
- **Preserves unmentioned**: Grades not in CSV stay unchanged
- **Student matching**: Uses SIS ID > Canvas ID > Name (in that order)

---

## Migration Path

Faculty can transition gradually:

```
100% API → Hybrid (API + CSV backup) → 100% Offline
```

**Hybrid Mode Benefits**:
- API for automation
- CSV backup for verification
- Can switch to offline if API revoked
- Best of both worlds

**Recommendation**: All faculty should download CSV regularly (even with API) as backup.

---

## Open Questions

1. **IMSCC Import Fidelity**: Does Canvas preserve all metadata when re-importing?
   - Test: Export course → Import to sandbox → Verify all fields match

2. **Gradebook Import Limits**: Max rows/columns in CSV import?
   - Test: Large course (1000+ students, 100+ assignments)

3. **File Upload in IMSCC**: Are embedded images preserved correctly?
   - Test: Page with 10+ images → Export → Import → Verify all render

4. **Overwrite Behavior**: What happens if assignment names don't match exactly?
   - Test: CSV with "Assignment 1" vs course with "Assignment 1 (Updated)"

5. **Comment Format**: Exact syntax for multi-line comments in CSV?
   - Test: Comment with newlines/quotes → Export → Import → Verify formatting

---

## Next Steps

1. **Get sample `.imscc`**: Export course 145706 to examine structure
2. **Build CSV parser**: Read Canvas gradebook CSV format
3. **Test import roundtrip**: Export → Import → Verify no data loss
4. **Create offline_import.py**: `.imscc` → `.canvas/` converter
5. **Update grading tools**: Add `--offline` flag

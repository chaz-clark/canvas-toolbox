# Offline Mode Implementation - Sprint Plan

**Goal**: Enable Canvas toolbox to work without API access via CANVAS_MODE flag
**Reference**: [offline_mode.md](./offline_mode.md)
**Timeline**: 6 sprints (~6-8 weeks)

---

## Sprint 1: Core Infrastructure (1-2 weeks)

**Goal**: Establish CANVAS_MODE foundation that all tools will use

### Tasks
- [ ] Create `lib/utils/canvas_mode.py` utility module
  - `get_canvas_mode()` - Read CANVAS_MODE from .env (default: "online")
  - `check_mode_requirements()` - Validate mode + token requirements
  - `is_online_mode()` / `is_offline_mode()` - Helper functions
- [ ] Create `lib/utils/csv_utils.py` for Canvas CSV parsing
  - `read_canvas_gradebook_csv()` - Parse Canvas gradebook export format
  - `write_canvas_gradebook_csv()` - Write Canvas-compatible CSV
  - `detect_csv_format()` - Validate Canvas CSV structure
- [ ] Create `lib/utils/file_finder.py` for Downloads detection
  - `find_latest_gradebook_csv()` - Find grades-*.csv in ~/Downloads
  - `find_latest_submissions_zip()` - Find submissions_*.zip in ~/Downloads
  - `find_latest_imscc()` - Find *.imscc in ~/Downloads
- [ ] Update `.env.example` with CANVAS_MODE documentation
- [ ] Add CANVAS_MODE to existing .env file

### Success Criteria
- ✅ `get_canvas_mode()` returns "online" or "offline" correctly
- ✅ `check_mode_requirements()` raises error if CANVAS_MODE=online without token
- ✅ CSV utils can parse actual Canvas gradebook export
- ✅ File finder locates test files in ~/Downloads

### Dependencies
- None (foundational sprint)

### Testing
```bash
# Test mode detection
CANVAS_MODE=offline python -c "from lib.utils.canvas_mode import get_canvas_mode; print(get_canvas_mode())"

# Test CSV parsing on real export
python -c "from lib.utils.csv_utils import read_canvas_gradebook_csv; print(read_canvas_gradebook_csv('~/Downloads/grades-145706.csv'))"
```

---

## Sprint 2: Gradebook De-Identification (1 week)

**Goal**: FERPA-compliant de-identification for gradebook CSV files

### Tasks
- [ ] Create `lib/tools/deidentify_gradebook.py`
  - Parse Canvas gradebook CSV
  - Generate deterministic anonymous IDs (Student 001, sid001)
  - Create mapping file (`.canvas/gradebook/student_mapping.json`)
  - Output de-identified CSV
- [ ] Create `lib/tools/reidentify_gradebook.py`
  - Read mapping file
  - Restore real names/IDs before upload
  - Validate mapping completeness
- [ ] Add `lib/utils/pii_detection.py`
  - `contains_real_names()` - Detect if CSV has real student data
  - `is_deidentified()` - Check if CSV already de-identified
  - Auto-detection logic

### Success Criteria
- ✅ De-identification is deterministic (same student → same anon ID across runs)
- ✅ Mapping file created and git-ignored
- ✅ Re-identification restores exact original CSV format
- ✅ Auto-detection works on real Canvas exports

### Dependencies
- Sprint 1 (CSV utils)

### Testing
```bash
# Download real gradebook
# Canvas: Grades → Export → grades-145706.csv → ~/Downloads/

# De-identify
python lib/tools/deidentify_gradebook.py \
  --input ~/Downloads/grades-145706.csv \
  --output .canvas/gradebook/grades-deidentified.csv

# Verify mapping created
ls -la .canvas/gradebook/student_mapping.json

# Re-identify
python lib/tools/reidentify_gradebook.py \
  --input .canvas/gradebook/grades-deidentified-updated.csv \
  --mapping .canvas/gradebook/student_mapping.json \
  --output ~/Desktop/grades-145706-updated.csv

# Diff should show only grade changes, not student data
diff ~/Downloads/grades-145706.csv ~/Desktop/grades-145706-updated.csv
```

---

## Sprint 3: Grading Tools Offline Mode (2 weeks)

**Goal**: Enable `grade_assignments.py` to work with CSV instead of API

### Tasks
- [ ] Add CANVAS_MODE support to `lib/tools/grade_assignments.py`
  - Check mode at startup
  - If offline: read from `find_latest_gradebook_csv()`
  - Auto-detect PII and de-identify if needed
  - Generate `_all_comments.md` from CSV data
- [ ] Add `--apply-comments` offline mode
  - Read `_all_comments.md`
  - Update local CSV (de-identified)
  - Export re-identified CSV for upload
- [ ] Add offline mode to `lib/tools/fix_group_override_recalc.py`
  - Read assignments from CSV columns
  - Calculate weighted totals
  - Update CSV instead of API
- [ ] Add CSV export messages
  - Clear instructions for Canvas upload
  - Warn if trying to upload de-identified data

### Success Criteria
- ✅ `grade_assignments.py --generate-comments` works with CSV in ~/Downloads
- ✅ Auto-detects and de-identifies PII automatically
- ✅ `_all_comments.md` format unchanged (faculty workflow identical)
- ✅ `--apply-comments` outputs upload-ready CSV
- ✅ Error messages guide faculty to download files via Canvas UI

### Dependencies
- Sprint 1 (mode infrastructure)
- Sprint 2 (de-identification)

### Testing
```bash
# Download files via Canvas UI
# 1. Grades → Export → grades-145706.csv
# 2. Assignment → Download Submissions → submissions_123.zip

# Set offline mode
echo "CANVAS_MODE=offline" >> .env

# Generate comments (should auto-detect CSV)
python lib/tools/grade_assignments.py --generate-comments
# Expected: "✓ Found gradebook: ~/Downloads/grades-145706.csv"
# Expected: "⚠ Real student data detected - de-identifying..."
# Expected: "✓ Generated course/_all_comments.md"

# Edit comments
vim course/_all_comments.md

# Apply comments
python lib/tools/grade_assignments.py --apply-comments
# Expected: "✓ Updated grades in: .canvas/gradebook/grades.csv"
# Expected: "✓ Export for upload: ~/Desktop/grades-145706-updated.csv"

# Upload via Canvas UI
# Grades → Import → Upload grades-145706-updated.csv
```

---

## Sprint 4: .imscc Import/Export Utilities (2 weeks)

**Goal**: Tools to convert between .imscc files and .canvas/ directory structure

### Tasks
- [ ] Research .imscc format
  - Download sample .imscc from course 145706
  - Unzip and analyze structure (imsmanifest.xml, etc.)
  - Document format in `docs/imscc_format.md`
- [ ] Create `lib/tools/offline_import.py`
  - Unpack .imscc ZIP file
  - Parse `imsmanifest.xml`
  - Convert to `.canvas/` structure:
    - `index.json` (course metadata)
    - `course/modules/` (module structure)
    - `course/pages/` (page HTML)
    - `course/assignments/` (assignment JSON)
    - `course/_files/` (file attachments)
  - Import gradebook CSV to `.canvas/gradebook/grades.csv`
- [ ] Create `lib/tools/offline_export.py`
  - Read `.canvas/` structure
  - Build `imsmanifest.xml`
  - Pack into .imscc ZIP file
  - Export gradebook CSV in Canvas format
- [ ] Add validation
  - Verify roundtrip: export → import → compare
  - Check for data loss

### Success Criteria
- ✅ Can unpack real .imscc export into `.canvas/` format
- ✅ Can pack `.canvas/` back into .imscc
- ✅ Roundtrip preserves all content (modules, pages, assignments, files)
- ✅ CSV import/export works

### Dependencies
- Sprint 1 (CSV utils, file finder)

### Testing
```bash
# Export course via Canvas UI
# Settings → Export Course Content → .imscc → ~/Downloads/course_export_145706.imscc

# Import to .canvas/
python lib/tools/offline_import.py \
  --imscc ~/Downloads/course_export_145706.imscc \
  --gradebook ~/Downloads/grades-145706.csv \
  --output .canvas/

# Verify structure
ls -la .canvas/
tree course/

# Make local changes
python lib/tools/adjust_dates.py --shift-days 365

# Export back to .imscc
python lib/tools/offline_export.py \
  --source .canvas/ \
  --imscc ~/Desktop/course_import.imscc \
  --gradebook ~/Desktop/grades_updated.csv

# Upload via Canvas UI
# Settings → Import Course Content → Upload course_import.imscc
```

---

## Sprint 5: Course Management Tools (1 week)

**Goal**: Add .imscc support to `canvas_sync.py` and `sync_to_new.py`

### Tasks
- [ ] Add .imscc import to `canvas_sync.py`
  - Add `--import-imscc` flag
  - Use `offline_import.py` utilities
  - Sync to `.canvas/` directory
- [ ] Add .imscc export to `sync_to_new.py`
  - Add `--export-imscc` flag
  - Use `offline_export.py` utilities
  - Pack adjusted content for Canvas import
- [ ] Update workflow guidance
  - Add offline mode instructions
  - Update error messages for missing .imscc files

### Success Criteria
- ✅ `canvas_sync.py --import-imscc` creates same `.canvas/` as `--pull-all`
- ✅ `sync_to_new.py --export-imscc` creates upload-ready .imscc
- ✅ Workflow messages guide faculty through offline process

### Dependencies
- Sprint 4 (.imscc utilities)

### Testing
```bash
# Offline workflow: semester copy
# 1. Download source course
CANVAS_MODE=offline python lib/tools/canvas_sync.py \
  --import-imscc ~/Downloads/course_export_145706.imscc

# 2. Adjust dates
python lib/tools/adjust_dates.py --shift-days 365

# 3. Export for new course
python lib/tools/sync_to_new.py --export-imscc ~/Desktop/course_new_semester.imscc

# 4. Upload via Canvas UI
# Settings → Import Course Content → Upload course_new_semester.imscc
```

---

## Sprint 6: Testing & Documentation (1 week)

**Goal**: Comprehensive testing and user documentation

### Tasks
- [ ] End-to-end integration tests
  - Full offline grading workflow
  - Full offline course copy workflow
  - Hybrid mode (API + CSV backup)
- [ ] ✅ Create `docs/offline_readme.md` (faculty-facing) - **COMPLETED**
  - Tool compatibility matrix (✅ supported, ⚠️ partial, ❌ not supported)
  - Quick start guide (download → process → upload)
  - Common workflows (grading, course copy, audits)
  - FERPA compliance (auto de-ID/re-ID)
  - Troubleshooting guide
  - Hybrid mode documentation
- [ ] Update main `README.md`
  - Add "Offline Mode (No API Required)" section under Features
  - Link to `docs/offline_readme.md`
  - Update setup instructions to mention both API and offline modes
  - Add CANVAS_MODE environment variable to config section
- [ ] Update `.env.example`
  - Add CANVAS_MODE documentation
  - Explain online vs offline modes
  - Link to offline_readme.md
- [ ] Create demo video (optional)
  - Screen recording of offline workflow
  - Faculty-friendly walkthrough

### Success Criteria
- ✅ Faculty can complete grading workflow without API
- ✅ Faculty can copy course to new semester without API
- ✅ Documentation covers all common scenarios
- ✅ Error messages are clear and actionable

### Dependencies
- Sprints 1-5 (all features complete)

### Testing
```bash
# Full offline workflow test (no API token)
# 1. Remove API token
sed -i '' 's/^CANVAS_TOKEN=.*/CANVAS_TOKEN=/' .env
echo "CANVAS_MODE=offline" >> .env

# 2. Download via Canvas UI
# - Course export: .imscc
# - Gradebook: CSV
# - Submissions: ZIP

# 3. Run grading workflow
python lib/tools/grade_assignments.py --generate-comments
vim course/_all_comments.md
python lib/tools/grade_assignments.py --apply-comments

# 4. Upload via Canvas UI
# - Grades → Import → CSV

# 5. Run course copy workflow
python lib/tools/canvas_sync.py --import-imscc ~/Downloads/export.imscc
python lib/tools/adjust_dates.py --shift-days 365
python lib/tools/sync_to_new.py --export-imscc ~/Desktop/import.imscc

# 6. Upload via Canvas UI
# - Settings → Import → .imscc

# All steps should succeed without API token
```

---

## Priority Order (if time-constrained)

If we need to deliver incrementally, prioritize in this order:

1. **Sprint 3** (Grading Tools) - Highest faculty value, uses CSV only
2. **Sprint 2** (De-Identification) - Required for Sprint 3, FERPA compliance
3. **Sprint 1** (Infrastructure) - Required for Sprints 2 & 3
4. **Sprint 4** (.imscc utilities) - Enables course management
5. **Sprint 5** (Course Management) - Completes feature set
6. **Sprint 6** (Testing & Docs) - Polish and hardening

**Minimum Viable Product (MVP)**: Sprints 1-3 enable offline grading workflow (highest value)

**Complete Feature**: Sprints 1-6 enable full offline mode (grading + course management)

---

## Dependencies Diagram

```
Sprint 1 (Infrastructure)
    ↓
    ├─→ Sprint 2 (De-ID) ──→ Sprint 3 (Grading Tools)
    └─→ Sprint 4 (.imscc) ─→ Sprint 5 (Course Mgmt)
                                  ↓
                            Sprint 6 (Testing & Docs)
```

**Critical Path**: Sprint 1 → Sprint 2 → Sprint 3 (grading MVP)
**Full Feature**: Sprint 1 → Sprint 4 → Sprint 5 → Sprint 6 (course management)

---

## Success Metrics

**After Sprint 3 (MVP)**:
- [ ] Faculty can grade assignments without API token
- [ ] `_all_comments.md` workflow unchanged
- [ ] PII automatically de-identified
- [ ] CSV upload works via Canvas UI

**After Sprint 6 (Complete)**:
- [ ] Faculty can run entire toolbox without API
- [ ] Download → Process → Upload pattern works for all tools
- [ ] Hybrid mode allows mixing API and CSV workflows
- [ ] Documentation enables self-service adoption

---

## Risk Mitigation

**Risk: .imscc format changes**
- Mitigation: Version detection in parser, graceful degradation

**Risk: Canvas CSV format varies by institution**
- Mitigation: Format detection, validation, clear error messages

**Risk: PII leaks in de-identification**
- Mitigation: Extensive testing, mapping file validation, git-ignore enforcement

**Risk: Faculty confusion about which mode to use**
- Mitigation: Clear docs, auto-detection where possible, helpful error messages

---

## Next Steps

1. **Review this sprint plan** with stakeholders
2. **Verify course 145706** is appropriate test course (has gradebook data, assignments, files)
3. **Start Sprint 1** - Create infrastructure utilities
4. **Test with real data** - Use actual Canvas exports throughout development
5. **Iterate on UX** - Ensure faculty workflow is smooth and well-documented

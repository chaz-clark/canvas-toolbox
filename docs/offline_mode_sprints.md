# Offline Mode Implementation - Sprint Plan

> ## ⚠️ STATUS & RE-SCOPE — updated 2026-07-12 (read this first)
>
> This header supersedes the original plan below, which mis-scoped the
> architecture. The original 6-sprint plan is kept underneath as history.
>
> ### What actually shipped — Sprints 1–4 (merged to `main`)
> Offline **data formats** — the pieces that let offline data exist:
> - **S1 (#141)** — `CANVAS_MODE` flag, gradebook CSV parse/write (`_csv_utils`),
>   download finder + offline hard-stop (`_file_finder`). Helpers live in
>   `lib/tools/` as `_`-prefixed modules (NOT `lib/utils/`). Real env var is
>   `CANVAS_API_TOKEN` (the plan's `CANVAS_TOKEN` was never real).
> - **S2 (#142)** — gradebook de-identify / re-identify, reusing the toolbox-wide
>   `deid_code_for`. Opt-out posture; deterministic code-based re-ID.
> - **S3 (#143)** — `grader_gradebook_apply.py`: offline scores → gradebook CSV
>   (resolves by Canvas id / de-id code / name).
> - **S4 (#144)** — `.imscc` date-shift **in place** (identifiers preserved) +
>   `validate_imscc` + **DST-correct** shifting via `CANVAS_TIMEZONE`.
>
> ### The architectural correction (the real goal)
> The original plan assumed a `.imscc → .canvas/` converter would make the tools
> work offline. That was wrong:
> - **59 tools call the Canvas API directly**; only ~4 read the local `course/`.
> - `canvas_sync --pull` ALREADY writes the full course into **`course/`**
>   (`_course.json`, per-module `_module.json`, page `.html`, assignment/quiz
>   `.json` with dates/points). `.canvas/index.json` is sync STATE only.
> - So audits **re-fetch data they already have locally** — redundant API overuse.
>
> **Intended architecture:** every tool reads `course/`, source-agnostic.
> `canvas_sync` fills `course/` from the API; `offline_import` fills it from
> `.imscc`. "How the files got there" is the only difference — and reading
> `course/` kills the API overuse in ONLINE mode too.
>
> **Known constraint:** `course/` doesn't yet hold everything — `canvas_sync`
> skips **rubrics, learning outcomes, assignment groups**. Tools needing those
> require the local store to be widened first. Analytics/engagement is API-only.
>
> ### Re-scoped sprints — status
> - **S5 ✅ (#146)** — `_course_loader.py` + `workload_audit --local`, parity-tested on 427808.
> - **S6 ✅ (#147, #148)** — `offline_import` (`.imscc → course/`) + 4-course cross-validation.
> - **S8 ✅ (#149, #150)** — content path (syllabus + descriptions) + 3 content audits
>   (`syllabus`, `accessibility`, `content_representation`) read `course/`.
> - **S9 ✅** — honest docs: `offline_readme.md` rewritten; `offline_mode.md` accurate
>   architecture header; tool boundary documented.
> - **S7 (pending)** — widen the store: **assignment groups** (needs a group↔assignment
>   join) and **rubrics** (nested) in `offline_import` (+ optionally `canvas_sync`), then
>   convert `grading_structure_audit` / `formative_variety_audit` / rubric audits.
>   **Learning outcomes are API-only** — account-level, `learning_outcomes.xml` empty in a
>   course export → `clo_quality_audit` stays API-only.
>
> ### Tool boundary (decided)
> - **Read/report** (audits) → offline via `course/`.
> - **Content write-back** (`imscc_adjust_dates`) → new/empty course only (destructive on live).
> - **Student-specific writes** (SAS, quiz-time ext, late/exempt, submit-on-behalf) → **API-only**.
> - **Outcomes / analytics** → **API-only**.
>
> ### Doc corrections to fold in at S9
> - `grade_assignments.py` and `adjust_dates.py` are **fictional** — the real
>   pipeline is `grader_fetch → grader_grade → grader_push`; date-shift is
>   `imscc_adjust_dates.py`.
> - Comments **cannot** ride a gradebook CSV import (Canvas is scores-only) —
>   offline comments = API (`grader_push_comments`) if a token exists, else
>   SpeedGrader paste of `feedback/_all_comments.md`.
> - `CANVAS_API_TOKEN` (not `CANVAS_TOKEN`); sandbox is `CANVAS_SANDBOX_ID`
>   (427808, not the docs' 427952). Helpers in `lib/tools/`, not `lib/utils/`.

---

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

## Sprint 4: .imscc Import/Export Utilities

**Goal**: Tools to convert between .imscc files and .canvas/ directory structure
**Size**: XL
**Risk**: HIGH - Canvas has silent failure modes (identifier format, missing files)
**Mitigation**: Built-in validation before export

### Tasks

#### Build Phase
- [ ] ✅ Research .imscc format - **COMPLETED**
  - Knowledge base: `lib/agents/knowledge/imscc_format_knowledge.md`
  - Sample data: Real .imscc from course 145706
- [ ] Create `lib/tools/offline_import.py`
  - Unpack .imscc ZIP file
  - Parse `imsmanifest.xml` + `course_settings/module_meta.xml`
  - Convert to `.canvas/` structure:
    - `index.json` (course metadata)
    - `course/modules/` (module structure)
    - `course/pages/` (page HTML)
    - `course/assignments/` (assignment JSON)
    - `course/_files/` (file attachments)
  - Import gradebook CSV to `.canvas/gradebook/grades.csv`
- [ ] Create `lib/tools/offline_export.py`
  - Read `.canvas/` structure
  - Build `imsmanifest.xml` + `course_settings/module_meta.xml`
  - Generate Canvas-compatible identifiers (`g` + 32 hex chars)
  - Pack into .imscc ZIP file
  - Export gradebook CSV in Canvas format
  - **Integrated validation** (calls validate_imscc before writing output)
- [ ] Create `lib/tools/validate_imscc.py` - **RISK REDUCTION**
  - Validate identifier format (detect human-readable IDs)
  - Check Canvas trigger files (course_settings.xml, syllabus.html)
  - Verify date constraints (unlock < due < lock)
  - Check timezone presence in all dates
  - Validate file references ($IMS_CC_FILEBASE$ paths exist)
  - CLI tool for manual validation before upload

#### Test Phase
- [ ] Unit tests (`tests/test_imscc_parser.py`)
  - Parse imsmanifest.xml correctly
  - Parse module_meta.xml correctly
  - Extract files from ZIP
- [ ] Identifier generation tests (`tests/test_canvas_identifiers.py`)
  - Generate valid `g` + 32 hex format
  - Deterministic (same input → same ID)
- [ ] Validation tests (`tests/test_imscc_validation.py`)
  - Catch human-readable identifiers
  - Catch missing Canvas trigger files
  - Catch date constraint violations
  - Catch missing timezones
  - Catch broken file references
  - Accept valid .imscc files
- [ ] Failure injection tests (`tests/test_imscc_failure_modes.py`)
  - Intentionally create bad .imscc with each known failure mode
  - Verify validator catches each one
  - Document Canvas behavior for each failure
- [ ] Roundtrip tests (`tests/test_imscc_roundtrip.py`)
  - Export → Import → Compare (no data loss)
  - Dates preserved (including timezones)
  - Files preserved
  - Module structure preserved
- [ ] Regression tests (Sprint 1 utilities still work)
  - `pytest tests/test_canvas_mode.py`
  - `pytest tests/test_csv_utils.py`
  - `pytest tests/test_file_finder.py`

#### Integration Phase
- [ ] Canvas import verification (semi-manual)
  - Export validated .imscc
  - Upload to sandbox course (427952)
  - Verify content intact
  - Verify dates correct
  - Document any Canvas quirks

### Success Criteria

**Functionality**:
- ✅ Can unpack real .imscc export into `.canvas/` format
- ✅ Can pack `.canvas/` back into .imscc
- ✅ Roundtrip preserves all content (modules, pages, assignments, files, dates)
- ✅ Canvas successfully imports validated .imscc

**Quality** (Risk Reduction):
- ✅ **Validator catches all known silent failure modes**
- ✅ **No .imscc exported with validation errors**
- ✅ **Failure injection tests pass** (validator detects intentionally broken files)
- ✅ **All Sprint 1 regression tests pass**

**Real Data**:
- ✅ Tested with real .imscc from course 145706
- ✅ Tested with real Canvas sandbox import (course 427952)

### Dependencies
- Sprint 1 (file finder, mode utils)

### Known Failure Modes (from knowledge base)

**Critical (Silent Failures)**:
1. Human-readable identifiers (`assignment_week1` instead of `g` + 32 hex) → Canvas accepts, content missing after import
2. Missing `course_settings/course_settings.xml` → Canvas treats as generic IMS CC, modules don't import

**High (Import Errors)**:
3. Date constraints violated (`lock_at` before `due_at`) → Canvas rejects with error
4. Missing timezones in dates → Dates shift by hours

**Medium (Incomplete Import)**:
5. Broken file references (`$IMS_CC_FILEBASE$/missing.jpg`) → Missing images, no error

### Testing Workflow

```bash
# 1. Export course via Canvas UI
# Settings → Export Course Content → .imscc → ~/Downloads/course_export_145706.imscc

# 2. Import to .canvas/
python lib/tools/offline_import.py \
  --imscc ~/Downloads/course_export_145706.imscc \
  --gradebook ~/Downloads/grades-145706.csv \
  --output .canvas/

# 3. Verify structure
ls -la .canvas/
tree course/

# 4. Make local changes
python lib/tools/adjust_dates.py --shift-days 365

# 5. Export back to .imscc (with validation)
python lib/tools/offline_export.py \
  --source .canvas/ \
  --imscc ~/Desktop/course_import.imscc \
  --gradebook ~/Desktop/grades_updated.csv

# Output should show:
# Validating .imscc structure...
# ✓ ZIP structure valid
# ✓ Required files present
# ✓ All identifiers valid (g + 32 hex)
# ✓ Date constraints satisfied
# ✓ Validated .imscc exported to: ~/Desktop/course_import.imscc

# 6. Manual validation (optional)
python lib/tools/validate_imscc.py ~/Desktop/course_import.imscc

# 7. Upload via Canvas UI
# Settings → Import Course Content → Upload course_import.imscc

# 8. Verify in Canvas
# Check modules, assignments, dates, files all present
```

### Quality Discipline (Toyota Jidoka)

**Built-in Quality**:
- Validation runs automatically in `offline_export.py` (no manual step)
- Export blocked if validation fails (stop-on-red)
- Clear error messages with fix guidance

**Mistake-Proofing (Poka-yoke)**:
- Can't export .imscc with validation errors
- Validator catches failures before Canvas upload
- Failure injection tests document each failure mode

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

## Quality Discipline (Toyota Way)

### Three Core Principles

**1. Genchi Gembutsu (現地現物) - Go and See**
- Test with REAL Canvas exports, not synthetic data
- Verify in Canvas sandbox (course 427952), don't assume
- When uncertain about .imscc format, download and examine actual file
- Don't trust documentation alone - check actual behavior

**2. Jidoka (自働化) - Built-in Quality / Stop on Defect**
- Write tests WITH code, not after
- Can't export .imscc with validation errors (blocked automatically)
- Red tests block progress - fix immediately, don't defer
- Aligns with AGENTS.md P-003 "Stop on Defect"

**3. Poka-yoke (ポカヨケ) - Mistake-Proofing**
- Validation runs automatically (no manual step to forget)
- Pre-commit hooks run unit tests
- Git-ignore patterns prevent PII commits
- Type hints + linting catch errors early

### Per-Sprint Discipline

**Every Sprint Must**:
1. ✅ **Green before done** - All tests pass before moving to next sprint
2. ✅ **Regression first** - Run previous sprint tests BEFORE writing new code
3. ✅ **Real data** - Test with actual Canvas exports from course 145706
4. ✅ **Stop on red** - Fix failing tests immediately (Andon cord)
5. ✅ **API mode protected** - Verify online mode still works (no regressions)

### Test Pyramid

**Unit tests** (fast, many):
- Utilities, parsers, validators
- Run in pre-commit hook
- Example: `test_canvas_mode.py`, `test_csv_utils.py`

**Integration tests** (medium, fewer):
- Multi-component workflows
- Run in CI on PR
- Example: `test_csv_deid_integration.py`

**E2E tests** (slow, few):
- Full faculty workflows
- Run before release
- Example: `test_offline_grading_complete.py`

**Manual verification** (slowest, minimal):
- Canvas import acceptance
- Document in test log, not code

### Continuous Integration

**Pre-commit**:
```bash
# .git/hooks/pre-commit
pytest tests/unit/ --maxfail=1
```

**Pull Request**:
```bash
# .github/workflows/test.yml
pytest tests/ --cov=lib/
```

**Can't merge with**:
- ❌ Red tests
- ❌ Linting errors
- ❌ Coverage below threshold

### Kaizen (Continuous Improvement)

**After Each Sprint**:
- What tests caught issues? (Working)
- What issues slipped through? (Needs improvement)
- Update test suite based on findings
- Document lessons in `lib/agents/knowledge/learned/`

---

## Next Steps

1. **Review this sprint plan** with stakeholders
2. **Verify course 145706** is appropriate test course (has gradebook data, assignments, files)
3. **Start Sprint 1** - Create infrastructure utilities
4. **Test with real data** - Use actual Canvas exports throughout development
5. **Iterate on UX** - Ensure faculty workflow is smooth and well-documented

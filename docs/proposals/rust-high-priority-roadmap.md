# Rust High-Priority Roadmap

**Created:** 2026-07-07
**Status:** Planning phase
**Context:** Merge of issue #135 candidates + rust-value-proposition-analysis.md recommendations

---

## Completed (v1.5.0 - v1.5.1)

### 1. ✅ Assignment override enumeration (`fix_group_override_recalc.py`)
**Status:** DONE
**Performance gain:** 40-120x (5-10 min → 5-15 sec for 100+ assignments)
**Use case:** Accommodation workflows, group override fixes
**Frequency:** Medium (on-demand when overrides don't apply)
**Implementation:** Rust binary + Python fallback + dispatcher (v1.5.0-v1.5.1)

---

## High-Priority Candidates (Merged List)

### 2. Bulk submission fetching (`grader_fetch.py`)
**Source:** Issue #135 + analysis
**Current performance:** Unknown (no reported issues)
**Estimated gain:** 2-3x (not 40x - bottleneck is likely deidentify, not fetch)
**Bottleneck location:**
- API calls: GET /courses/:id/users, GET /assignments/:aid/submissions, GET attachment URLs
- File I/O: Writing downloads to disk
- Chained tools: deidentify, leak check (subprocess calls)

**Use case:** Every grading run starts with this
**Frequency:** **Very high** - run multiple times per assignment per semester

**Complexity:** Medium-high
- File downloads, directory management
- Subprocess orchestration (chaining to deidentify)
- Business logic mixed with I/O

**Analysis verdict:**
> "No open issues about grader_fetch being slow. Users run it regularly, no complaints. Likely fast enough for typical cohorts (20-40 students). Real bottleneck is DEIDENTIFY step (docx/pdf processing) or AI grading (waiting for LLM API)."

**Recommendation:**
- **Wait for user complaints** before implementing
- If implemented: focus on concurrent submission fetches (20-40 students → parallel HTTP)
- Attachment downloads could benefit from parallelization
- File I/O and subprocess chains won't benefit from Rust

**Estimated work:** 3-4 days (complex business logic, file handling, subprocess coordination)

---

### 3. Title IV engagement audit (`course_engagement_audit.py`)
**Source:** Analysis
**Current performance:** Unknown - likely slow for large courses
**Estimated gain:** 10-20x
**Bottleneck:** Sequential fetches across 3 endpoints per student

**What it does:**
- UW/UF audit (Title IV compliance)
- Fetches submissions, discussions, quiz submissions for ALL students
- Classifies by last engagement date

**Use case:** End-of-term compliance reporting
**Frequency:** Low (1-2 times per semester)

**Complexity:** Medium
- Three API endpoints per student
- Date parsing, classification logic
- PDF generation (Python/reportlab - can't Rust this part)

**Analysis verdict:**
> "No open issues. Likely slow for 100+ student courses. BUT: Run 1-2 times per semester, not daily."

**Recommendation:**
- **Good Rust candidate** if 100+ student courses hit timeout
- 10-20x speedup would make large-course audits practical
- Low frequency is acceptable (not daily use)

**Estimated work:** 2-3 days (straightforward parallel fetches + date logic)

---

### 4. Module traversal (audit tools)
**Source:** Issue #135 + analysis
**Current performance:** Unknown - likely acceptable
**Estimated gain:** 3-5x
**Bottleneck:** Sequential module item fetches

**Affected tools:**
- `course_alignment_audit.py`
- `course_accessibility_audit.py`
- `course_quality_check.py`
- Any tool that walks module structures

**What they do:**
- Scan module structures for audits (alignment, accessibility, quality)
- Many small API calls to build full course graph

**Use case:** Pre-publish audits, course quality checks
**Frequency:** Medium (pre-semester, occasional audits)

**Complexity:** Medium-high (business logic heavy)
- Module hierarchy traversal
- Item type handling (pages, assignments, quizzes, discussions)
- Content parsing and analysis

**Analysis verdict:**
> "No open issues about module traversal being slow. Modest gain (3-5x), not critical pain."

**Recommendation:**
- **Wait for user complaints**
- If implemented: create shared Rust module traversal library
- Complexity is in business logic (quality checks), not just HTTP

**Estimated work:** 4-5 days (multiple tools, shared library design)

---

### 5. Full course pull (`canvas_sync.py --pull`)
**Source:** Analysis
**Current performance:** Unknown - no reported issues
**Estimated gain:** 3-5x (2-3 min → 30-60 sec for large courses)
**Bottleneck:** Sequential API calls for large module structures

**What it does:**
- Pulls entire Canvas course to local files
- Modules, pages, assignments, quizzes, discussions, syllabus
- Hundreds of API calls for large courses (15+ modules, 100+ items)

**Use case:** Course design workflows, one-time pulls
**Frequency:** Medium (one-time per course, occasional updates)

**Complexity:** High
- Complex business logic (module hierarchy, item types)
- File writing, directory creation
- Markdown/HTML formatting
- Error handling for partial fetches

**Analysis verdict:**
> "No open issues. Large courses (15+ modules, 100+ items) might be slow. But users run this ONCE per course, not repeatedly. Not critical pain - one-time operation, users can wait."

**Recommendation:**
- **Wait for user complaints**
- Potential gain exists but low frequency usage
- High complexity for modest benefit

**Estimated work:** 5-6 days (complex business logic, file handling, format conversion)

---

### 6. Discussion thread flattening (crawling nested replies)
**Source:** Issue #135
**Current performance:** Unknown
**Estimated gain:** Unknown
**Bottleneck:** Recursive API calls for nested discussion threads

**What it does:**
- Fetches discussion topics and flattens nested reply trees
- Canvas discussions can have deep nesting (replies to replies)

**Use case:** Discussion analysis, grading discussions
**Frequency:** Unknown (no current tool uses this heavily)

**Complexity:** Medium
- Recursive/iterative traversal of reply trees
- API pagination at each level
- Thread reconstruction

**Analysis verdict:**
> Not mentioned in analysis (no current tool heavily relies on this)

**Recommendation:**
- **Lowest priority** - no current tool needs this
- Wait until we build a discussion-heavy tool
- Could be library for future discussion tools

**Estimated work:** 2-3 days (straightforward recursion, no complex business logic)

---

## Prioritization Matrix

| Tool | Frequency | Impact | Complexity | User Pain | Priority | Estimated Work |
|------|-----------|--------|------------|-----------|----------|----------------|
| ✅ `fix_group_override_recalc` | Medium | 40-120x | Low | **YES** (issue #135) | **DONE** | - |
| `course_engagement_audit` | Low | 10-20x | Medium | No (yet) | **High** | 2-3 days |
| `grader_fetch` | **Very High** | 2-3x | Med-High | No | Medium | 3-4 days |
| Module traversal | Medium | 3-5x | Med-High | No | Medium | 4-5 days |
| `canvas_sync --pull` | Medium | 3-5x | High | No | Low | 5-6 days |
| Discussion flattening | Unknown | Unknown | Medium | No | Low | 2-3 days |

---

## Recommended Implementation Order

### Phase 1: High-Impact, Proven Need (v1.5.2 - v1.6.0)
**Target:** 2-4 weeks

1. **`course_engagement_audit.py`** (2-3 days)
   - Highest estimated speedup (10-20x)
   - Clear concurrency opportunity (per-student parallel)
   - Compliance-critical (Title IV)
   - Wait for first user complaint, then implement immediately

### Phase 2: High-Frequency, Moderate Gain (v1.6.1 - v1.7.0)
**Target:** 4-6 weeks

2. **`grader_fetch.py`** (3-4 days)
   - Highest frequency (every grading run)
   - Modest gain (2-3x) but daily impact
   - Complex (file handling, subprocess chains)
   - **Conditional:** Only if users complain it's slow

### Phase 3: Shared Infrastructure (v1.7.1+)
**Target:** 6-8 weeks

3. **Module traversal library** (4-5 days)
   - Benefits multiple audit tools
   - Modest gain (3-5x) but reusable
   - Refactor existing tools to use shared library

### Phase 4: Lower Priority (v1.8.0+)
**Target:** 8-12 weeks (if demand exists)

4. **`canvas_sync.py --pull`** (5-6 days)
   - One-time operation (low frequency)
   - High complexity for modest gain
   - Wait for clear user demand

5. **Discussion thread flattening** (2-3 days)
   - No current tool needs this
   - Future-proofing for discussion-heavy features

---

## Decision Points (Check Every 4 Weeks)

### Proceed with Phase 1 if:
- ✅ User reports `course_engagement_audit` timeout (100+ students)
- ✅ User requests faster engagement audits
- ⚠️ OR: Chaz hits slowness in daily use

### Proceed with Phase 2 if:
- ✅ 2+ users report `grader_fetch` slowness
- ✅ Profiling confirms HTTP is the bottleneck (not deidentify)
- ⚠️ OR: Chaz hits slowness in grading workflows

### Proceed with Phase 3 if:
- ✅ 2+ tools proven slow due to module traversal
- ✅ Users request faster audit tools

### Skip a phase if:
- ❌ No user complaints after 3 months
- ❌ Python performance acceptable for actual workloads
- ❌ Complexity outweighs benefit

---

## Medium-Priority Candidates (Deferred)

Review these after Phase 3 completion:

- `build_deid_master.py` — Already fast (single API call)
- `student_late_accommodation.py` — Small operation count
- `student_quiz_time_extension.py` — Small operation count
- `apply_sas_accommodations.py` — Dispatcher, delegates to other tools

---

## Success Metrics

### Per-tool metrics:
- Actual speedup (measured, not estimated)
- User adoption rate (% using Rust vs Python fallback)
- Error rate (Rust vs Python parity)

### Overall metrics:
- Number of tools with Rust implementations
- % of daily workflows benefiting from Rust
- User feedback: "Rust makes canvas-toolbox usable for large courses"

### Threshold for v2.x (Rust required):
- 5+ tools with proven 5x+ speedup
- >50% of users have Rust installed (cb-init metrics)
- Zero critical bugs in Rust implementations for 6+ months

---

## Next Steps

1. **Update issue #135** — mark override recalc as complete (v1.5.0/v1.5.1)
2. **Wait for user feedback** — 4-week checkpoint (2026-08-04)
3. **Create Phase 1 issue** when first user reports engagement audit slowness
4. **Revisit medium-priority list** after Phase 3 completion

---

**Last updated:** 2026-07-07
**Next review:** 2026-08-04 (4-week checkpoint)

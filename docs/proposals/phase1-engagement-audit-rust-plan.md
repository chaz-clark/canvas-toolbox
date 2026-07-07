# Phase 1: course_engagement_audit.py Rust Implementation

**Target:** v1.5.2
**Estimated work:** 2-3 days
**Expected speedup:** 10-20x (5-10 min → 30-60 sec for 100+ students)

---

## Bottleneck Analysis

**Current Python flow (lines 587-610):**
```python
for i, row in enumerate(keyed_rows, 1):  # SEQUENTIAL
    uid = row["user_id"]
    subs = fetch_student_submissions(base, cid, headers, uid)  # HTTP wait
    disc_timestamps = fetch_discussion_entries(base, cid, headers, uid)  # HTTP wait
    last = compute_last_engagement(...)
    row["classification"] = classify_student(...)
```

**Problem:** For 100 students:
- 100 sequential HTTP requests for submissions
- 100 sequential HTTP requests for discussions (each with nested topic fetches)
- Total: ~200+ sequential HTTP round trips

**Solution:** Concurrent fetching in Rust (tokio) - all students in parallel

---

## Architecture

### Rust Binary (`engagement_audit_rs`)
**Input:** JSON array of user_ids + course_id + base_url + token
**Output:** JSON array of per-student engagement data

```rust
struct StudentEngagementData {
    user_id: u64,
    submission_timestamps: Vec<String>,      // ISO timestamps
    discussion_timestamps: Vec<String>,       // ISO timestamps
    quiz_timestamps: Vec<String>,             // ISO timestamps (if separate)
}
```

**Responsibilities:**
- Concurrent per-student fetches (tokio::join_all)
- HTTP pagination for submissions (GET /courses/:cid/students/submissions?student_ids[]=:uid)
- HTTP pagination for discussion topics (GET /courses/:cid/discussion_topics)
- Filter discussion entries by user_id (GET /discussion_topics/:tid/entries)
- Return raw timestamps (no classification logic - keep in Python)

### Python Wrapper (`_course_engagement_audit_python.py`)
**Fallback for when Rust binary not available**

**Responsibilities:**
- Same as current implementation (lines 587-610)
- Sequential fetching (slower but works)

### Python Main (`course_engagement_audit.py`)
**Dispatcher pattern (like fix_group_override_recalc.py)**

**Keeps:**
- Enrollment fetching (small, one-time operation)
- Date classification logic (`compute_last_engagement`, `classify_student`)
- Re-identification (FERPA boundary - keymap[user_id] → name)
- Report generation (Markdown + PDF - Python libraries)
- ~/Downloads writing (outside repo)

**Changes:**
- Lines 587-610: Replace with Rust binary call OR Python fallback
- Dispatcher: detect Rust binary, fall back to Python if missing
- Same output format, same FERPA guarantees

---

## Implementation Steps

### Step 1: Create Rust project structure (30 min)
```bash
cd lib/tools
cargo new engagement_audit_rs --name engagement-audit
cd engagement_audit_rs
```

Add dependencies to `Cargo.toml`:
```toml
[dependencies]
tokio = { version = "1", features = ["full"] }
reqwest = { version = "0.12", features = ["json"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
anyhow = "1"
clap = { version = "4", features = ["derive"] }
```

### Step 2: Implement Rust core (6-8 hours)
- `main.rs`: CLI argument parsing, orchestration
- `canvas_client.rs`: HTTP client, pagination logic
- `models.rs`: Rust structs for Canvas API responses
- Concurrent fetching logic (tokio::join_all)
- Error handling (anyhow)

### Step 3: Create Python fallback (3-4 hours)
- Extract lines 350-462 (fetch functions) to `_course_engagement_audit_python.py`
- Add `run_python_fallback()` entry point
- Match Rust output format (JSON-compatible dicts)

### Step 4: Add dispatcher to main tool (2-3 hours)
- Detect Rust binary (`lib/tools/engagement_audit_rs/target/release/engagement-audit`)
- Call Rust binary with student IDs as JSON
- Parse Rust output (JSON array)
- Fall back to Python if Rust missing (with warning)
- Preserve all existing functionality

### Step 5: Test both paths (2-3 hours)
- Test Rust path with sandbox course
- Test Python fallback (rename Rust binary temporarily)
- Verify identical output
- Test with 0, 1, 10, 50+ students
- Verify FERPA boundaries unchanged

### Step 6: Update docs (1 hour)
- Update tool header docstring
- Add performance note to README
- Update CHANGELOG for v1.5.2

---

## Key Design Decisions

### 1. Why keep classification logic in Python?
**Reason:** It's simple date comparison logic (10 lines). Moving to Rust adds complexity for no performance gain. Python's `datetime` handling is clearer than Rust's `chrono`.

### 2. Why keep report generation in Python?
**Reason:** Markdown rendering and PDF generation use Python libraries (reportlab). Porting to Rust would require finding/wrapping Rust equivalents. No performance benefit (report gen is fast).

### 3. Why keep re-identification in Python?
**Reason:** FERPA boundary. Keeping name handling entirely in Python (never in Rust) makes the security model clearer.

### 4. What if discussion topic fetching is slow?
**Current Python:** Fetches topics once, then iterates per-student.
**Rust approach:** Same - fetch topics once (sequential), then concurrent per-student entry filtering.
**Optimization:** Could parallelize topic fetches too, but adds complexity. Start simple.

---

## Testing Strategy

### Correctness tests:
1. Run Python version, save output
2. Run Rust version with same inputs
3. Compare engagement timestamps (should match exactly)
4. Compare classifications (should match exactly)
5. Compare final report (should match exactly except generation timestamp)

### Performance tests:
1. Test course: M119 SP26 (409936) - 108 students (original issue #135 context)
2. Measure Python: time for lines 587-610 loop
3. Measure Rust: time for concurrent fetch + classification
4. Expected: 10-20x speedup (5-10 min → 30-60 sec)

### Failure mode tests:
1. Missing Rust binary → Python fallback works
2. Network errors → both handle gracefully
3. Malformed Canvas responses → both handle gracefully
4. Empty course → both handle gracefully

---

## Success Criteria

1. ✅ Rust version produces identical output to Python version
2. ✅ Python fallback works when Rust not available
3. ✅ 10x+ speedup for courses with 50+ students
4. ✅ No regressions (FERPA boundaries unchanged)
5. ✅ Clear warning when falling back to Python
6. ✅ All existing command-line flags work identically

---

## Rollback Plan

If Rust version has issues:
1. Python fallback guarantees tool still works
2. Can disable Rust detection temporarily (rename binary)
3. Can revert commits if needed (isolated changes)

---

## Next Actions

1. User approval of architecture
2. Create Rust project structure
3. Implement Rust core
4. Create Python fallback
5. Test both paths
6. Update docs, commit, tag v1.5.2

---

**Last updated:** 2026-07-07
**Status:** Awaiting approval

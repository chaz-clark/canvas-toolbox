# Student Accommodation Force-Recalc Research Findings

**Date:** 2026-07-08
**Research Context:** Deep dive on accommodation system reliability ("working 0-100% of the time")

---

## Executive Summary

The current force-recalc mechanism is **extremely inefficient** and explains the 10+ minute hangs reported in v1.5.4. The good news: we have multiple optimization paths that should dramatically improve reliability and performance.

**Current Approach:** Iterate ALL assignments in a course to find student-specific overrides, then "touch" each one with a no-op PUT request.

**Problem:** On a course with 200 assignments, this means:
- 1 API call to paginate all assignments
- 200 API calls to fetch overrides for each assignment
- N API calls to "touch" each matching override
- Result: 200+ API calls, 10+ minute runtime

---

## Key Findings from Research

### 1. Canvas Bulk Update API Exists
**Endpoint:** `PUT /api/v1/courses/:course_id/assignments/bulk_update`

**Capabilities:**
- Update due dates and availability dates for multiple assignments in ONE API call
- Returns Progress object for async tracking
- Performs update in background job
- Validates all assignments before saving (atomic operation)

**Limitations:**
- Cannot create or destroy overrides (only update existing ones)
- Dates not supplied will be defaulted
- Does NOT explicitly mention triggering recalculation

**Source:** https://www.canvas.instructure.com/doc/api/assignments.html

### 2. Canvas Internal Recalc Mechanism
**Class:** `SubmissionLifecycleManager` (Canvas LMS internal)

**Method:** `recompute_users_for_course(user_ids, course_id, grading_period_id, sis_import: bool, update_grades: bool)`

**Usage Context:**
- Called during SIS enrollment imports
- Triggered after enrollment batch processing
- Recalculates submission lifecycle data + grades for specific users

**Location in Canvas LMS:**
- Referenced in: `lib/sis/enrollment_importer.rb:49`
- Implementation file: Not publicly accessible via REST API (internal only)

**Key Insight:** Canvas does NOT expose a REST API endpoint for bulk recalculation. The override "touching" workaround is the only external trigger mechanism.

### 3. Known Canvas API Issues

**Issue #1774 (GitHub):** "Update assignment override does not return updated override"
- **Problem:** PUT returns stale data immediately after update
- **Workaround:** GET the override again after PUT to verify changes
- **Status:** Not fixed as of research date

**Community Reports:** Canvas caching issues
- **Problem:** Overrides sometimes require "reset user cache" from Canvas support
- **Pattern:** Usually resolves automatically after unknown delay
- **Status:** Intermittent, no documented fix

**Known Issue (Canvas LMS):** Section override due date validation bug
- **Problem:** "Due date cannot be after course end" errors
- **Status:** Fixed and deployed to production (Nov 20, 2024)

---

## Current Implementation Analysis

### File: `lib/tools/_override_recalc_helper.py`

**Function:** `force_recalc_for_student()`

**Current Logic:**
```python
# If no assignment_id specified:
1. GET /api/v1/courses/:course_id/assignments (paginated, all assignments)
2. For each assignment:
   - GET /api/v1/courses/:course_id/assignments/:id/overrides (paginated)
   - Filter overrides where student_id matches
   - PUT each override with same values (no-op "touch")
```

**Performance:**
- Course with 200 assignments: 200+ API calls
- Runtime: 10+ minutes on slow Canvas instances
- Rate limiting risk: High

**Why It's Slow:**
1. No assignment targeting - checks EVERY assignment even if student has 3 overrides
2. No caching - fetches all overrides every time
3. Sequential processing - no parallelization
4. No early exit - continues even after finding all overrides

### File: `lib/tools/student_late_accommodation.py:457-473`

**Current Usage:**
```python
# After creating overrides for specific assignments:
force_recalc_for_student(
    base=base_url,
    headers=headers,
    course_id=int(course_id),
    student_id=uid,
    quiet=False
)
# ⚠️ BUG: We know which assignments we just updated (assignment_ids list)
#     but we DON'T pass them to force_recalc_for_student!
```

**Critical Issue:** We have the assignment IDs that were just updated in `assignment_ids`, but we throw that information away and iterate ALL assignments anyway.

---

## Optimization Paths

### Option 1: Pass Known Assignment IDs (Immediate Fix) ⭐ RECOMMENDED FIRST
**Effort:** Low (10 lines of code)
**Impact:** Massive (200 API calls → 3 API calls)

**Change:**
```python
# In student_late_accommodation.py
if not args.remove and args.apply and args.force_recalc and assignment_ids:
    print(f"\nForcing Canvas override recalculation...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        touched = 0
        for aid in assignment_ids:  # ← We already have these!
            touched += force_recalc_for_student(
                base=base_url,
                headers=headers,
                course_id=int(course_id),
                student_id=uid,
                assignment_id=aid,  # ← Pass the specific assignment
                quiet=False
            )
        print(f"  [recalc] ✓ Recalculated {touched} assignment(s)")
```

**Benefits:**
- Reduces API calls from O(all assignments) to O(modified assignments)
- Student with 3 accommodations: 200+ calls → 3 calls
- Should complete in seconds instead of minutes

**Risks:**
- None (existing code path already supports assignment_id parameter)

### Option 2: Use Bulk Update API (Medium-Term)
**Effort:** Medium (requires refactoring how we create overrides)
**Impact:** High (atomic updates + background job handling)

**Approach:**
1. When updating multiple assignment dates, batch them into a single bulk_update call
2. Use Progress API to track completion
3. May still need override "touching" afterward (unclear if bulk_update triggers recalc)

**Benefits:**
- Atomic validation (all or nothing)
- Background job processing (non-blocking)
- Fewer API calls overall

**Risks:**
- Cannot create new overrides (only update existing)
- Unclear if it triggers automatic recalculation
- Requires restructuring current workflow

### Option 3: Add Verification + Retry Logic
**Effort:** Medium
**Impact:** Medium (improves reliability, not performance)

**Approach:**
```python
def verify_override_updated(base, headers, course_id, assignment_id, override_id, expected_values, max_retries=3):
    """Verify override was actually updated (workaround for Canvas caching)."""
    for attempt in range(max_retries):
        # GET the override to check current values
        r = requests.get(f"{base}/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides/{override_id}")
        override = r.json()

        if all(override.get(k) == v for k, v in expected_values.items()):
            return True  # Verified

        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)  # Exponential backoff

    return False  # Failed to verify
```

**Benefits:**
- Catches Canvas caching issues (Issue #1774)
- Provides immediate feedback if override didn't stick
- Can retry or warn user

**Risks:**
- Adds latency (more API calls)
- May not fix underlying Canvas caching issues

### Option 4: Make Force-Recalc Optional by Default
**Effort:** Low (change default flag)
**Impact:** Low (improves UX for fast Canvas instances)

**Rationale:**
- v1.5.4 already changed default to `--no-force-recalc`
- Many Canvas instances handle recalc automatically
- Let users opt-in with `--force-recalc` when needed

**Current Status:** Already implemented in v1.5.4

---

## Recommended Implementation Plan

### Phase 1: Immediate Fix (This Sprint)
1. **Fix the obvious bug** in student_late_accommodation.py:457-473
   - Pass `assignment_id` to `force_recalc_for_student()` for each modified assignment
   - Measure API call reduction (should be 50-100x faster)

2. **Test on real courses** with known accommodation issues
   - DS460 (large course, slow Canvas)
   - Test student with 5+ accommodations
   - Compare before/after API call counts + runtime

3. **Update CHANGELOG** with performance fix note

### ✅ Phase 1: IMPLEMENTED (v1.6.1)
**Status:** COMPLETE

Changes:
1. **student_late_accommodation.py** - Now passes specific assignment_ids to force_recalc
2. **student_quiz_time_extension.py** - Extracts assignment_ids from graded quizzes
3. **Performance:** 50-100x faster (200+ API calls → 3-5 API calls)

### ✅ Phase 2: IMPLEMENTED (v1.6.1)
**Status:** COMPLETE

Changes to **_override_recalc_helper.py**:
1. **Added `verify_override_updated()`** - Workaround for Canvas Issue #1774 (stale data after PUT)
2. **Added `_request_with_backoff()`** - Exponential backoff for 429 rate limiting (1s, 2s, 4s)
3. **Updated all API calls** - Now use backoff logic (GET assignments, GET overrides, PUT override)
4. **Parallel processing** - DEFERRED (not needed with targeted assignment approach)

### 🔄 Phase 3: Architecture Research (NEXT)
**Status:** IN PROGRESS

1. **Evaluate bulk_update API** for batch operations
   - Test if it triggers automatic recalc
   - Compare reliability vs current approach
   - Document findings

---

## Questions for User

1. **Scope:** Should we fix the immediate bug (Phase 1) in this session, or document it for later?

2. **Testing:** Do you have a course with known accommodation reliability issues we can test against?

3. **Default behavior:** Keep `--no-force-recalc` as default, or change back to `--force-recalc` once we fix the performance issue?

4. **Verification:** Should we add the verify_override_updated() logic, or is that overkill given the performance fix?

---

## Related Files

- `lib/tools/_override_recalc_helper.py` - Core recalc logic
- `lib/tools/student_late_accommodation.py` - Main accommodation tool
- `lib/tools/student_quiz_time_extension.py` - Quiz time extensions (uses same helper)
- `lib/tools/apply_sas_accommodations.py` - SAS accommodation bulk apply (uses same helper)
- `lib/tools/fix_group_override_recalc.py` - Standalone troubleshooting tool

---

## References

- Canvas API Assignment Overrides: https://www.canvas.instructure.com/doc/api/assignments.html
- Canvas LMS Issue #1774: https://github.com/instructure/canvas-lms/issues/1774
- Canvas LMS enrollment_importer.rb: https://github.com/instructure/canvas-lms/blob/master/lib/sis/enrollment_importer.rb
- v1.5.4 CHANGELOG: commit 58eaafe (changed default to --no-force-recalc)

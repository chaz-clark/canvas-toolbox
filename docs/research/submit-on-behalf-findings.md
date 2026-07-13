# Submit On Behalf Tool - Testing Results

**Date:** 2026-07-08
**Tool:** `lib/tools/submit_on_behalf.py`
**Test Environment:** BYUI Canvas (DS460 course)

---

## Executive Summary

The `submit_on_behalf.py` tool successfully uploads files to Canvas but **cannot complete submissions due to institutional permissions blocking the "Submit on behalf of student" API endpoint** at BYUI.

**Status:** File upload works (returns file_id), submission blocked with 403/400 errors

**Workaround:** Files are uploaded to Canvas; instructor can manually attach them in SpeedGrader

---

## Test Cases

### Test 1: DS-A16AE3 - Personal Challenge 2nd Attempt

**File:** `DS460 Personal Challenge 1 2026-06-20 10_57_38.html`
**Assignment:** 16958677 - "Key Challenge 1 - PySpark GroupBy Personal Challenge"
**Student:** DS-A16AE3 (user_id 173819)

**Results:**
- ✓ File uploaded successfully (Canvas file_id: 167590494)
- ✗ Submission failed: `403 Client Error: Forbidden`

**API Response:**
```
403 Client Error: Forbidden for url:
https://byui.instructure.com/api/v1/courses/407908/assignments/16958677/submissions
```

---

### Test 2: DS-BA2D38 - GroupBy Challenge

**File:** `pyspark_groupby_personal_challenge (1) 2026-06-24 02_46_48.html`
**Assignment:** 16958677 - "Key Challenge 1 - PySpark GroupBy Personal Challenge"
**Student:** DS-BA2D38 (user_id 164679)

**Results:**
- ✓ File uploaded successfully (Canvas file_id: 167590606)
- ✗ Submission failed: `403 Client Error: Forbidden`

---

### Test 3: DS-BA2D38 - PartitionBy Challenge

**File:** `pyspark_partitionby_personal_challenge-1 2026-06-24 04_26_25.html`
**Assignment:** 16958671 - "Key Challenge 2 - PySpark PartitionBy Personal Challenge"
**Student:** DS-BA2D38 (user_id 164679)

**Results:**
- ✓ File uploaded successfully (Canvas file_id: 167590628)
- ✗ Submission failed: `403 Client Error: Forbidden`

---

### Test 4: DS-BA2D38 - S5 Complex Features

**File:** `S5 Complex Features.html`
**Assignment:** 16958699 - "S5 - Complex Feature Engineering"
**Student:** DS-BA2D38 (user_id 164679)

**Results:**
- ✓ File uploaded successfully (Canvas file_id: 167590652)
- ✗ Submission failed: `400 Client Error: Bad Request`

**Note:** Different error code (400 vs 403) suggests different validation issue. File still uploaded successfully.

---

## Technical Analysis

### File Upload Process (Working)

Canvas file upload is a 3-step process that **works correctly**:

1. **Request upload URL**: POST to `/api/v1/courses/:course_id/files`
2. **Upload file**: POST file to Canvas storage URL
3. **Confirm upload**: Returns file object with Canvas file_id

**Status:** ✓ All steps successful, file_ids returned

### Submission Process (Blocked)

Submission API requires "Submit on behalf of student" permission:

**Endpoint:** `POST /api/v1/courses/:course_id/assignments/:assignment_id/submissions`

**Payload:**
```python
{
    "submission[submission_type]": "online_upload",
    "submission[file_ids][]": file_id,
    "submission[user_id]": user_id,
    "comment[text_comment]": "optional comment"
}
```

**Status:** ✗ Blocked at BYUI with 403 Forbidden

### Permission Analysis

**Root Cause:** Canvas "Submit on behalf of student" permission is disabled at institutional level

**Evidence:**
- Consistent 403 errors across multiple students and assignments
- File upload succeeds (different permission)
- Submission API specifically blocked

**Institutional Policies:**
- BYUI: Blocked (tested 2026-07-08)
- Other institutions: Unknown (likely varies)

---

## Tool Validation

### What Works ✓

1. **Deid code resolution** - Correctly looks up user_id from grading/.deid_master.csv
2. **Assignment lookup** - Fetches assignment details via API
3. **File upload** - Successfully uploads files to Canvas (3-step process)
4. **Error handling** - Clear error messages, dry-run mode
5. **FERPA compliance** - Never displays student names

### What Doesn't Work ✗

1. **Submission API** - Blocked by Canvas institutional permissions at BYUI
2. **Automatic submission** - Cannot complete end-to-end workflow

---

## Workaround

Since files upload successfully to Canvas, instructors can manually attach them:

1. Run tool to upload file (get file_id)
2. Open SpeedGrader for the assignment
3. Manually attach the uploaded file to student's submission
4. Add comment explaining the submission

**Uploaded files from this test (available for manual attachment):**
- DS-A16AE3 assignment 16958677: Canvas file_id 167590494
- DS-BA2D38 assignment 16958677: Canvas file_id 167590606
- DS-BA2D38 assignment 16958671: Canvas file_id 167590628
- DS-BA2D38 assignment 16958699: Canvas file_id 167590652

---

## Potential Solutions

### Option 1: Request Permission Enable
**Action:** Contact Canvas admin to enable "Submit on behalf of student" API permission
**Likelihood:** Low (institutional policy decision)
**Impact:** Would fully enable tool

### Option 2: Submission Comment Alternative
**Action:** Research if attaching files via submission comments bypasses permission
**Endpoint:** `POST /api/v1/courses/:course_id/assignments/:assignment_id/submissions/:user_id/comments`
**Status:** Not yet researched

### Option 3: Accept Limitation
**Action:** Document tool as "upload only" with manual attachment workflow
**Status:** Already documented in tool docstring

---

## Recommendation

Keep the tool as-is with documented limitation. The upload functionality is still valuable:

**Benefits:**
- Automates file upload (3-step Canvas process)
- Resolves deid codes to user_ids (FERPA-safe)
- Looks up assignment IDs by name
- Validates files exist before uploading
- Dry-run mode to preview actions

**Limitation:** Instructor must manually attach uploaded files in SpeedGrader (30 seconds per student)

This is still significantly faster than the current manual workflow (save from Slack → navigate to SpeedGrader → upload file → attach to submission).

---

## Related Files

- `lib/tools/submit_on_behalf.py` - Main tool (390 lines)
- `grading/.deid_master.csv` - Student deid lookup (FERPA Zone 2)
- `AGENTS.md:51-75` - FERPA bash command discipline

---

## References

- Canvas Submissions API: https://www.canvas.instructure.com/doc/api/submissions.html
- Canvas File Upload API: https://www.canvas.instructure.com/doc/api/file.file_uploads.html
- Canvas "Submit on behalf of student" permission: Course-level setting (admin only)

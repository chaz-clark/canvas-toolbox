# Submit On Behalf Tool - Testing Results

**Date:** 2026-07-08
**Tool:** `lib/tools/submit_on_behalf.py`
**Test Environment:** BYUI Canvas (live course)

---

## Executive Summary

The `submit_on_behalf.py` tool successfully uploads files to Canvas but **cannot complete submissions due to institutional permissions blocking the "Submit on behalf of student" API endpoint** at BYUI.

**Status:** File upload works (returns file_id), submission blocked with 403/400 errors

**Workaround:** Files are uploaded to Canvas; instructor can manually attach them in SpeedGrader

---

## Test Cases

### Test 1: DS-68BC40 - resubmission

**File:** `challenge1_resubmission.html`
**Assignment:** 345678 - "Challenge 1"
**Student:** DS-68BC40 (user_id 900001)

**Results:**
- ✓ File uploaded successfully (Canvas file_id: 987651)
- ✗ Submission failed: `403 Client Error: Forbidden`

**API Response:**
```
403 Client Error: Forbidden for url:
https://byui.instructure.com/api/v1/courses/123456/assignments/345678/submissions
```

---

### Test 2: DS-5E4E3C - Challenge 1

**File:** `challenge1_submission.html`
**Assignment:** 345678 - "Challenge 1"
**Student:** DS-5E4E3C (user_id 900004)

**Results:**
- ✓ File uploaded successfully (Canvas file_id: 987652)
- ✗ Submission failed: `403 Client Error: Forbidden`

---

### Test 3: DS-5E4E3C - Challenge 2

**File:** `challenge2_submission.html`
**Assignment:** 345679 - "Challenge 2"
**Student:** DS-5E4E3C (user_id 900004)

**Results:**
- ✓ File uploaded successfully (Canvas file_id: 987653)
- ✗ Submission failed: `403 Client Error: Forbidden`

---

### Test 4: DS-5E4E3C - Stretch problem

**File:** `stretch_submission.html`
**Assignment:** 345680 - "Stretch problem"
**Student:** DS-5E4E3C (user_id 900004)

**Results:**
- ✓ File uploaded successfully (Canvas file_id: 987654)
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
- DS-68BC40 assignment 345678: Canvas file_id 987651
- DS-5E4E3C assignment 345678: Canvas file_id 987652
- DS-5E4E3C assignment 345679: Canvas file_id 987653
- DS-5E4E3C assignment 345680: Canvas file_id 987654

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

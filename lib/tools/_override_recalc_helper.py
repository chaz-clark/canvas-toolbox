#!/usr/bin/env python3
"""
_override_recalc_helper.py — Shared helper for forcing Canvas assignment
override recalculation.

WHY THIS EXISTS
  Canvas doesn't always automatically trigger SubmissionLifecycleManager.recompute_users_for_course
  when overrides are created or modified via the REST API. This helper provides reusable
  functions that other tools can call to force recalculation after creating/updating overrides.

USAGE FROM OTHER TOOLS
  from _override_recalc_helper import force_recalc_for_student

  # After creating/updating a student override
  force_recalc_for_student(
      base=base_url,
      headers=headers,
      course_id=407908,
      student_id=280379,
      assignment_id=123456  # optional - recalc just this assignment
  )

ARCHITECTURE
  This helper is used by:
  - student_late_accommodation.py
  - student_quiz_time_extension.py
  - apply_sas_accommodations.py
  - fix_group_override_recalc.py (the standalone troubleshooting tool)

  The fix_group_override_recalc.py tool remains the user-facing troubleshooting
  command when manual intervention is needed. This helper provides the same
  recalculation logic for programmatic use.

HOW IT WORKS
  "Touches" the assignment override by performing a no-op PUT (re-sets the same values).
  This triggers Canvas's assignment_override_updated event, forcing recalculation.
"""

import requests
from typing import Optional

_TIMEOUT = 30


def touch_override(
    base: str,
    headers: dict,
    course_id: int,
    assignment_id: int,
    override: dict,
    timeout: int = _TIMEOUT
) -> dict:
    """
    Perform a no-op PUT on an assignment override to trigger recalculation.

    Re-sends the same values that already exist, which triggers Canvas's
    assignment_override_updated event and forces submission recalculation.

    Args:
        base: Canvas base URL (e.g., "https://byui.instructure.com")
        headers: Request headers including Authorization
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        override: The override dict from Canvas API (must include 'id')
        timeout: Request timeout in seconds

    Returns:
        The updated override dict from Canvas
    """
    override_id = override["id"]

    # Build the payload - preserve all existing values
    payload = {}

    # The Canvas API requires all current values to be included or they'll be unset
    if "due_at" in override and override["due_at"] is not None:
        payload["assignment_override[due_at]"] = override["due_at"]

    if "unlock_at" in override and override["unlock_at"] is not None:
        payload["assignment_override[unlock_at]"] = override["unlock_at"]

    if "lock_at" in override and override["lock_at"] is not None:
        payload["assignment_override[lock_at]"] = override["lock_at"]

    # Title is required for group/section overrides
    if "title" in override:
        payload["assignment_override[title]"] = override["title"]

    # Preserve group_id (though it can't be changed)
    if "group_id" in override:
        payload["assignment_override[group_id]"] = override["group_id"]

    # Preserve student_ids (though they can't be changed)
    if "student_ids" in override and override["student_ids"]:
        for sid in override["student_ids"]:
            payload[f"assignment_override[student_ids][]"] = sid

    r = requests.put(
        f"{base}/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides/{override_id}",
        headers=headers,
        data=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def force_recalc_for_student(
    base: str,
    headers: dict,
    course_id: int,
    student_id: int,
    assignment_id: Optional[int] = None,
    timeout: int = _TIMEOUT,
    quiet: bool = False
) -> int:
    """
    Force Canvas to recalculate assignment overrides for a specific student.

    Finds all assignments with overrides targeting this student and "touches"
    each override to trigger Canvas's recalculation.

    Args:
        base: Canvas base URL
        headers: Request headers including Authorization
        course_id: Canvas course ID
        student_id: Canvas student user ID
        assignment_id: Optional - if provided, only recalc this assignment's override
        timeout: Request timeout in seconds
        quiet: If True, suppress progress output

    Returns:
        Number of overrides successfully touched
    """
    if not quiet:
        print(f"  [recalc] Forcing override recalculation for student {student_id}...")

    # If specific assignment provided, only check that one
    if assignment_id:
        assignments_to_check = [{"id": assignment_id}]
    else:
        # Get all assignments (paginated)
        assignments_to_check = []
        page = 1
        while True:
            r = requests.get(
                f"{base}/api/v1/courses/{course_id}/assignments",
                headers=headers,
                params={"per_page": 100, "page": page},
                timeout=timeout,
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            assignments_to_check += batch
            page += 1

    # Find and touch overrides
    touched_count = 0
    for asg in assignments_to_check:
        asg_id = asg["id"]

        # Get overrides for this assignment
        overrides = []
        page = 1
        while True:
            r = requests.get(
                f"{base}/api/v1/courses/{course_id}/assignments/{asg_id}/overrides",
                headers=headers,
                params={"per_page": 100, "page": page},
                timeout=timeout,
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            overrides += batch
            page += 1

        # Check if any override targets our student
        student_overrides = [
            o for o in overrides
            if "student_ids" in o and student_id in o.get("student_ids", [])
        ]

        # Touch each override
        for override in student_overrides:
            try:
                touch_override(base, headers, course_id, asg_id, override, timeout)
                touched_count += 1
                if not quiet:
                    print(f"  [recalc]   ✓ Assignment {asg_id} override recalculated")
            except requests.HTTPError as e:
                if not quiet:
                    print(f"  [recalc]   ✗ Assignment {asg_id} recalc failed: {e}")

    if not quiet:
        if touched_count > 0:
            print(f"  [recalc] ✓ Recalculated {touched_count} override(s)")
        else:
            print(f"  [recalc] No overrides found to recalculate")

    return touched_count


def force_recalc_for_group(
    base: str,
    headers: dict,
    course_id: int,
    group_id: int,
    assignment_id: Optional[int] = None,
    timeout: int = _TIMEOUT,
    quiet: bool = False
) -> int:
    """
    Force Canvas to recalculate assignment overrides for a specific group.

    Finds all assignments with overrides targeting this group and "touches"
    each override to trigger Canvas's recalculation.

    Args:
        base: Canvas base URL
        headers: Request headers including Authorization
        course_id: Canvas course ID
        group_id: Canvas group ID
        assignment_id: Optional - if provided, only recalc this assignment's override
        timeout: Request timeout in seconds
        quiet: If True, suppress progress output

    Returns:
        Number of overrides successfully touched
    """
    if not quiet:
        print(f"  [recalc] Forcing override recalculation for group {group_id}...")

    # If specific assignment provided, only check that one
    if assignment_id:
        assignments_to_check = [{"id": assignment_id}]
    else:
        # Get all assignments (paginated)
        assignments_to_check = []
        page = 1
        while True:
            r = requests.get(
                f"{base}/api/v1/courses/{course_id}/assignments",
                headers=headers,
                params={"per_page": 100, "page": page},
                timeout=timeout,
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            assignments_to_check += batch
            page += 1

    # Find and touch overrides
    touched_count = 0
    for asg in assignments_to_check:
        asg_id = asg["id"]

        # Get overrides for this assignment
        overrides = []
        page = 1
        while True:
            r = requests.get(
                f"{base}/api/v1/courses/{course_id}/assignments/{asg_id}/overrides",
                headers=headers,
                params={"per_page": 100, "page": page},
                timeout=timeout,
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            overrides += batch
            page += 1

        # Check if any override targets our group
        group_overrides = [o for o in overrides if o.get("group_id") == group_id]

        # Touch each override
        for override in group_overrides:
            try:
                touch_override(base, headers, course_id, asg_id, override, timeout)
                touched_count += 1
                if not quiet:
                    print(f"  [recalc]   ✓ Assignment {asg_id} override recalculated")
            except requests.HTTPError as e:
                if not quiet:
                    print(f"  [recalc]   ✗ Assignment {asg_id} recalc failed: {e}")

    if not quiet:
        if touched_count > 0:
            print(f"  [recalc] ✓ Recalculated {touched_count} override(s)")
        else:
            print(f"  [recalc] No overrides found to recalculate")

    return touched_count

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
      course_id=123456,
      student_id=900003,
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

RELIABILITY IMPROVEMENTS (v1.6.1)
  - Exponential backoff for 429 rate limiting errors
  - Optional verification that override was actually updated (workaround for Canvas Issue #1774)
  - Parallel processing for multi-assignment recalc (when appropriate)
"""

import requests
import time
from typing import Optional

_TIMEOUT = 30
_MAX_RETRIES = 3
_MAX_WORKERS = 5  # Parallel requests for multi-assignment recalc


def _request_with_backoff(method: str, url: str, **kwargs) -> requests.Response:
    """Make an HTTP request with exponential backoff for rate limiting.

    Retries on 429 (Too Many Requests) with exponential backoff: 1s, 2s, 4s.
    Other errors are raised immediately.

    Args:
        method: HTTP method ('GET', 'POST', 'PUT', etc.)
        url: Request URL
        **kwargs: Passed through to requests.request()

    Returns:
        Response object

    Raises:
        requests.HTTPError: If non-429 error or retries exhausted
    """
    for attempt in range(_MAX_RETRIES):
        try:
            r = requests.request(method, url, **kwargs)
            r.raise_for_status()
            return r
        except requests.HTTPError as e:
            if e.response.status_code == 429 and attempt < _MAX_RETRIES - 1:
                # Rate limited - wait and retry
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(wait_time)
                continue
            # Non-429 error or retries exhausted
            raise
    # Should never reach here, but satisfy type checker
    raise RuntimeError("Exhausted retries (should have raised HTTPError)")


def _get_all(url: str, headers: dict, timeout: int) -> list:
    """GET every page of a Canvas list by following the `Link: rel="next"` header.

    Never count pages: the overrides list ignores `?page=` and returns the same
    overrides for every page number, so a loop that waits for an empty page never
    ends once an assignment has an override (#506, lesson L36).
    """
    out: list = []
    params: dict | None = {"per_page": 100}
    seen: set = set()
    while url and url not in seen:  # a next link back to a page already read ends it
        seen.add(url)
        r = _request_with_backoff("GET", url, headers=headers, params=params, timeout=timeout)
        out += r.json() or []
        url = r.links.get("next", {}).get("url")
        params = None  # the next link already carries them
    return out


def build_touch_payload(override: dict) -> list[tuple[str, object]]:
    """Form fields that re-send an override exactly as it is (#506).

    Canvas's docs: every overridden value must be sent again in a PUT to be kept.
    So every date the override has goes back, a null one as an empty value (a
    late grace's Until date is overridden as null; leaving it out would put the
    assignment's own Until date back). Every student id goes back as its own
    field: one key per id would keep only the last, and the PUT would drop the
    other students from the override.
    """
    fields: list[tuple[str, object]] = []
    for date in ("due_at", "unlock_at", "lock_at"):
        if date in override:
            fields.append((f"assignment_override[{date}]", override[date] or ""))
    if "title" in override:
        fields.append(("assignment_override[title]", override["title"]))
    if "group_id" in override:
        fields.append(("assignment_override[group_id]", override["group_id"]))
    for sid in override.get("student_ids") or []:
        fields.append(("assignment_override[student_ids][]", sid))
    return fields


def verify_override_updated(
    base: str,
    headers: dict,
    course_id: int,
    assignment_id: int,
    override_id: int,
    expected_values: dict,
    timeout: int = _TIMEOUT
) -> bool:
    """Verify that an override was actually updated (workaround for Canvas Issue #1774).

    Canvas API sometimes returns stale data immediately after a PUT. This
    helper GETs the override and checks that expected values match.

    Args:
        base: Canvas base URL
        headers: Request headers including Authorization
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        override_id: Canvas override ID
        expected_values: Dict of field names to expected values (e.g., {"due_at": "2026-07-08T23:59:00Z"})
        timeout: Request timeout in seconds

    Returns:
        True if all expected values match, False otherwise
    """
    try:
        r = _request_with_backoff(
            "GET",
            f"{base}/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides/{override_id}",
            headers=headers,
            timeout=timeout,
        )
        override = r.json()

        # Check each expected value
        for key, expected in expected_values.items():
            actual = override.get(key)
            if actual != expected:
                return False

        return True
    except Exception:
        # If verification fails, return False (don't crash)
        return False


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
    payload = build_touch_payload(override)  # the override exactly as it is (#506)

    r = _request_with_backoff(
        "PUT",
        f"{base}/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides/{override_id}",
        headers=headers,
        data=payload,
        timeout=timeout,
    )
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
        assignments_to_check = _get_all(
            f"{base}/api/v1/courses/{course_id}/assignments", headers, timeout)

    # Find and touch overrides
    touched_count = 0
    for asg in assignments_to_check:
        asg_id = asg["id"]

        # Get overrides for this assignment
        overrides = _get_all(
            f"{base}/api/v1/courses/{course_id}/assignments/{asg_id}/overrides",
            headers, timeout)

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
        assignments_to_check = _get_all(
            f"{base}/api/v1/courses/{course_id}/assignments", headers, timeout)

    # Find and touch overrides
    touched_count = 0
    for asg in assignments_to_check:
        asg_id = asg["id"]

        # Get overrides for this assignment
        overrides = _get_all(
            f"{base}/api/v1/courses/{course_id}/assignments/{asg_id}/overrides",
            headers, timeout)

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

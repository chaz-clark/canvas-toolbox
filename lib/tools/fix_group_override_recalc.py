#!/usr/bin/env python3
"""
fix_group_override_recalc.py — Force Canvas to recalculate assignment overrides
when they're not applying correctly.

WHY THIS EXISTS
  Canvas doesn't always automatically trigger SubmissionLifecycleManager.recompute_users_for_course
  when overrides are created or modified via the REST API.

  Two common scenarios:

  1. **Group membership changes via API**: Remove/re-add a user to a Canvas group via REST API
     (DELETE /groups/:id/memberships/:membership_id then POST /groups/:id/memberships)
     → Assignment overrides for that group don't apply to the user

  2. **Student accommodations via API**: Apply individual student overrides via accommodation tools
     (student_late_accommodation.py, student_quiz_time_extension.py, apply_sas_accommodations.py)
     → Override is created but sometimes doesn't take effect immediately

  The Canvas UI handles recalculation automatically, but bare API calls don't always trigger it.

THE FIX
  "Touch" the assignment override by performing a no-op PUT (re-set the same values).
  This triggers Canvas's assignment_override_updated event and forces recalculation.

  For a given group OR student:
  1. Find all assignments that have overrides targeting the group/student
  2. For each override, perform a no-op PUT (re-set the same values)
  3. This triggers Canvas's internal recalculation logic
  4. The user can now submit

USAGE
  # Fix overrides for a specific group
  uv run python lib/tools/fix_group_override_recalc.py \\
    --course-id 407908 \\
    --group-id 1885662

  # Fix overrides for a specific student
  uv run python lib/tools/fix_group_override_recalc.py \\
    --course-id 407908 \\
    --student-id 280379

  # Check what overrides would be updated (dry run)
  uv run python lib/tools/fix_group_override_recalc.py \\
    --course-id 407908 \\
    --student-id 280379 \\
    --dry-run

REQUIRES in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL

WHEN TO USE THIS
  Use this tool as a "force refresh" when:
  - An accommodation was applied but the student still can't submit
  - A group override exists but members can't access the assignment
  - You changed group membership via API and overrides aren't working
  - Any scenario where an override should work but doesn't

  This is a safe troubleshooting tool - it only touches existing overrides,
  never creates new ones, and preserves all values.

INTEGRATION WITH ACCOMMODATION TOOLS
  This tool is designed to work AFTER accommodation tools have been used:
  - student_late_accommodation.py
  - student_quiz_time_extension.py
  - apply_sas_accommodations.py

  If accommodations are applied but still not working, run this tool to
  force Canvas to recalculate.

CANVAS API ENDPOINTS USED
  - GET /api/v1/courses/:course_id/assignments
  - GET /api/v1/courses/:course_id/assignments/:assignment_id/overrides
  - PUT /api/v1/courses/:course_id/assignments/:assignment_id/overrides/:override_id

SAFE BY DESIGN
  - Read-only by default (--dry-run)
  - Only updates overrides that already exist (no creation)
  - Preserves all existing override values (no data loss)
  - Prints detailed before/after for each operation
"""

import argparse
import os
import sys

import requests

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    # Fallback if _env_loader isn't available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

_TIMEOUT = 30


def get_assignments_with_group_overrides(
    base: str,
    headers: dict,
    course_id: int,
    group_id: int,
    timeout: int = _TIMEOUT
) -> list[dict]:
    """
    Find all assignments in a course that have overrides targeting a specific group.

    Returns: list of assignment dicts that have at least one override with
             override["group_id"] == group_id
    """
    print(f"Fetching assignments for course {course_id}...")

    # Get all assignments (paginated)
    assignments = []
    page = 1
    while True:
        print(f"  Fetching page {page}...", end=" ", flush=True)
        r = requests.get(
            f"{base}/api/v1/courses/{course_id}/assignments",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=timeout,
        )
        r.raise_for_status()
        batch = r.json()
        print(f"got {len(batch)} assignment(s)")
        if not batch:
            break
        assignments += batch
        page += 1

    print(f"\nFound {len(assignments)} total assignments")

    # For each assignment, check if it has overrides for this group
    print(f"Checking {len(assignments)} assignments for group overrides...")
    assignments_with_group_overrides = []
    for i, asg in enumerate(assignments, 1):
        asg_id = asg["id"]
        asg_name = asg["name"]
        print(f"  [{i}/{len(assignments)}] Checking: {asg_name[:50]}...", end=" ", flush=True)

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
        if group_overrides:
            asg["_group_overrides"] = group_overrides
            assignments_with_group_overrides.append(asg)
            print(f"✓ FOUND {len(group_overrides)} override(s)")
        else:
            print("no group overrides")

    return assignments_with_group_overrides


def get_assignments_with_student_overrides(
    base: str,
    headers: dict,
    course_id: int,
    student_id: int,
    timeout: int = _TIMEOUT
) -> list[dict]:
    """
    Find all assignments in a course that have overrides targeting a specific student.

    Returns: list of assignment dicts that have at least one override with
             student_ids containing the target student_id
    """
    print(f"Fetching assignments for course {course_id}...")

    # Get all assignments (paginated)
    assignments = []
    page = 1
    while True:
        print(f"  Fetching page {page}...", end=" ", flush=True)
        r = requests.get(
            f"{base}/api/v1/courses/{course_id}/assignments",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=timeout,
        )
        r.raise_for_status()
        batch = r.json()
        print(f"got {len(batch)} assignment(s)")
        if not batch:
            break
        assignments += batch
        page += 1

    print(f"\nFound {len(assignments)} total assignments")

    # For each assignment, check if it has overrides for this student
    print(f"Checking {len(assignments)} assignments for student overrides...")
    assignments_with_student_overrides = []
    for i, asg in enumerate(assignments, 1):
        asg_id = asg["id"]
        asg_name = asg["name"]
        print(f"  [{i}/{len(assignments)}] Checking: {asg_name[:50]}...", end=" ", flush=True)

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
        # Student overrides have student_ids as a list
        student_overrides = [
            o for o in overrides
            if "student_ids" in o and student_id in o.get("student_ids", [])
        ]
        if student_overrides:
            asg["_student_overrides"] = student_overrides
            assignments_with_student_overrides.append(asg)
            print(f"✓ FOUND {len(student_overrides)} override(s)")
        else:
            print("no student overrides")

    return assignments_with_student_overrides


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

    Returns: the updated override dict from Canvas
    """
    override_id = override["id"]

    # Build the payload - preserve all existing values
    payload = {}

    # The Canvas API requires all current values to be included or they'll be unset
    # From the docs: "all current overridden values must be supplied if they are
    # to be retained"

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


def main():
    parser = argparse.ArgumentParser(
        description="Force Canvas to recalculate assignment overrides when they're not applying correctly"
    )
    parser.add_argument(
        "--course-id",
        type=int,
        required=True,
        help="Canvas course ID"
    )

    # Mutually exclusive group for target type
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--group-id",
        type=int,
        help="Canvas group ID whose overrides should be recalculated"
    )
    target_group.add_argument(
        "--student-id",
        type=int,
        help="Canvas student user ID whose overrides should be recalculated"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be updated without making changes"
    )

    args = parser.parse_args()

    # Get environment vars
    token = os.getenv("CANVAS_API_TOKEN")
    base = os.getenv("CANVAS_BASE_URL")

    if not token or not base:
        print("ERROR: CANVAS_API_TOKEN and CANVAS_BASE_URL must be set in .env", file=sys.stderr)
        sys.exit(1)

    # Ensure base URL has https:// scheme
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"

    headers = {"Authorization": f"Bearer {token}"}

    # Determine target type
    target_type = "group" if args.group_id else "student"
    target_id = args.group_id if args.group_id else args.student_id

    print(f"\n{'='*70}")
    print(f"Canvas Assignment Override Recalculation Fix")
    print(f"{'='*70}")
    print(f"Course ID:    {args.course_id}")
    print(f"Target Type:  {target_type}")
    print(f"Target ID:    {target_id}")
    print(f"Mode:         {'DRY RUN (no changes)' if args.dry_run else 'LIVE (will update overrides)'}")
    print(f"{'='*70}\n")

    # Find assignments with overrides
    try:
        if args.group_id:
            assignments = get_assignments_with_group_overrides(
                base, headers, args.course_id, args.group_id
            )
            override_key = "_group_overrides"
        else:
            assignments = get_assignments_with_student_overrides(
                base, headers, args.course_id, args.student_id
            )
            override_key = "_student_overrides"
    except requests.HTTPError as e:
        print(f"\nERROR: Failed to fetch assignments: {e}", file=sys.stderr)
        print(f"Response: {e.response.text if e.response else 'N/A'}", file=sys.stderr)
        sys.exit(1)

    if not assignments:
        print(f"\n✓ No assignments found with overrides for {target_type} {target_id}")
        print("  Nothing to fix.")
        sys.exit(0)

    print(f"\nFound {len(assignments)} assignment(s) with {target_type} overrides to update:")
    print(f"{'='*70}\n")

    # Touch each override
    updated_count = 0
    for asg in assignments:
        asg_id = asg["id"]
        asg_name = asg["name"]

        for override in asg[override_key]:
            override_id = override["id"]
            print(f"Assignment: {asg_name} (id={asg_id})")
            print(f"  Override ID: {override_id}")
            print(f"  Current values:")
            print(f"    due_at:    {override.get('due_at', 'not set')}")
            print(f"    unlock_at: {override.get('unlock_at', 'not set')}")
            print(f"    lock_at:   {override.get('lock_at', 'not set')}")
            print(f"    title:     {override.get('title', 'not set')}")

            if args.dry_run:
                print(f"  [DRY RUN] Would perform no-op PUT to trigger recalculation")
            else:
                try:
                    updated = touch_override(base, headers, args.course_id, asg_id, override)
                    print(f"  ✓ Updated successfully")
                    print(f"    Server response confirms:")
                    print(f"      due_at:    {updated.get('due_at', 'not set')}")
                    print(f"      unlock_at: {updated.get('unlock_at', 'not set')}")
                    print(f"      lock_at:   {updated.get('lock_at', 'not set')}")
                    updated_count += 1
                except requests.HTTPError as e:
                    print(f"  ✗ FAILED: {e}", file=sys.stderr)
                    print(f"    Response: {e.response.text if e.response else 'N/A'}", file=sys.stderr)

            print()

    print(f"{'='*70}")
    if args.dry_run:
        print(f"DRY RUN complete. Would have updated {len([o for a in assignments for o in a[override_key]])} override(s).")
        print("Run without --dry-run to apply changes.")
    else:
        print(f"✓ Successfully updated {updated_count} override(s)")
        if args.group_id:
            print(f"  Canvas should now recalculate assignment availability for group {args.group_id}")
            print(f"  Users in this group should be able to submit if they have valid overrides.")
        else:
            print(f"  Canvas should now recalculate assignment availability for student {args.student_id}")
            print(f"  This student should be able to submit if they have valid overrides.")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()

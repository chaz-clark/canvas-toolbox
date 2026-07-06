#!/usr/bin/env python3
"""
fix_group_override_recalc.py — Force Canvas to recalculate assignment overrides
after group membership changes.

WHY THIS EXISTS
  When you remove and re-add a user to a Canvas group via the REST API
  (DELETE /groups/:id/memberships/:membership_id then POST /groups/:id/memberships),
  Canvas doesn't automatically trigger SubmissionLifecycleManager.recompute_users_for_course.

  This causes assignment overrides (like due date extensions) to not apply correctly
  to the user, even though they're back in the group. The Canvas UI handles this
  recalculation automatically, but bare API calls don't.

  This tool works around the issue by "touching" the assignment override itself,
  which triggers Canvas's assignment_override_updated event and forces recalculation.

THE FIX
  For a given group and course:
  1. Find all assignments that have overrides targeting this group
  2. For each override, perform a no-op PUT (re-set the same values)
  3. This triggers Canvas's internal recalculation logic
  4. The user can now submit

USAGE
  # Fix overrides for a specific group
  uv run python lib/tools/fix_group_override_recalc.py \\
    --course-id 407908 \\
    --group-id 1885662

  # Check what overrides would be updated (dry run)
  uv run python lib/tools/fix_group_override_recalc.py \\
    --course-id 407908 \\
    --group-id 1885662 \\
    --dry-run

REQUIRES in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL

WHEN TO USE THIS
  Use this tool AFTER removing and re-adding a user to a group when:
  - The user has an assignment due date extension/exemption
  - The override isn't working (user can't submit)
  - Manual UI remove/re-add fixes it, but API remove/re-add doesn't

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
from typing import Optional

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
        description="Force Canvas to recalculate assignment overrides after group membership changes"
    )
    parser.add_argument(
        "--course-id",
        type=int,
        required=True,
        help="Canvas course ID"
    )
    parser.add_argument(
        "--group-id",
        type=int,
        required=True,
        help="Canvas group ID whose overrides should be recalculated"
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

    print(f"\n{'='*70}")
    print(f"Canvas Assignment Override Recalculation Fix")
    print(f"{'='*70}")
    print(f"Course ID: {args.course_id}")
    print(f"Group ID:  {args.group_id}")
    print(f"Mode:      {'DRY RUN (no changes)' if args.dry_run else 'LIVE (will update overrides)'}")
    print(f"{'='*70}\n")

    # Find assignments with group overrides
    try:
        assignments = get_assignments_with_group_overrides(
            base, headers, args.course_id, args.group_id
        )
    except requests.HTTPError as e:
        print(f"\nERROR: Failed to fetch assignments: {e}", file=sys.stderr)
        print(f"Response: {e.response.text if e.response else 'N/A'}", file=sys.stderr)
        sys.exit(1)

    if not assignments:
        print(f"\n✓ No assignments found with overrides for group {args.group_id}")
        print("  Nothing to fix.")
        sys.exit(0)

    print(f"\nFound {len(assignments)} assignment(s) with group overrides to update:")
    print(f"{'='*70}\n")

    # Touch each override
    updated_count = 0
    for asg in assignments:
        asg_id = asg["id"]
        asg_name = asg["name"]

        for override in asg["_group_overrides"]:
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
        print(f"DRY RUN complete. Would have updated {len([o for a in assignments for o in a['_group_overrides']])} override(s).")
        print("Run without --dry-run to apply changes.")
    else:
        print(f"✓ Successfully updated {updated_count} override(s)")
        print(f"  Canvas should now recalculate assignment availability for group {args.group_id}")
        print(f"  Users in this group should be able to submit if they have valid overrides.")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()

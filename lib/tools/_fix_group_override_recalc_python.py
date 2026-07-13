#!/usr/bin/env python3
"""
_fix_group_override_recalc_python.py — Python fallback implementation for
override recalculation (when Rust binary not available).

This is the SEQUENTIAL Python implementation. It works correctly but is
slower than the Rust version (5-10 minutes vs 5-15 seconds for 100+
assignments) because it processes overrides one at a time instead of
concurrently.

Called by fix_group_override_recalc.py when Rust binary is not found.
Not intended to be run directly - use the main tool instead.

For performance comparison:
- Python (this file): Sequential HTTP requests, ~5-10 min for 100 assignments
- Rust (fix_override_recalc_rs): Concurrent HTTP requests, ~5-15 sec

See docs/proposals/rust-value-proposition-analysis.md for benchmarks.
"""
from __future__ import annotations

import sys
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: requests module not installed", file=sys.stderr)
    print("Run: uv sync", file=sys.stderr)
    sys.exit(2)


class CanvasClient:
    """Sequential Canvas API client (Python fallback)."""

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "User-Agent": "canvas-toolbox-python/1.5.1",
        })

    def get_paginated(self, endpoint: str) -> list[dict[str, Any]]:
        """Fetch all pages from a Canvas API endpoint."""
        all_items = []
        page = 1

        while True:
            url = f"{self.base_url}/api/v1/{endpoint}"
            response = self.session.get(
                url,
                params={"per_page": 100, "page": page},
                timeout=30,
            )

            if not response.ok:
                raise RuntimeError(
                    f"HTTP {response.status_code} for GET {endpoint}"
                )

            items = response.json()
            if not items:
                break

            all_items.extend(items)
            page += 1

        return all_items

    def get_assignments(self, course_id: int) -> list[dict[str, Any]]:
        """Fetch all assignments for a course."""
        return self.get_paginated(f"courses/{course_id}/assignments")

    def get_overrides(
        self, course_id: int, assignment_id: int
    ) -> list[dict[str, Any]]:
        """Fetch all overrides for an assignment."""
        return self.get_paginated(
            f"courses/{course_id}/assignments/{assignment_id}/overrides"
        )

    def touch_override(
        self,
        course_id: int,
        assignment_id: int,
        override_data: dict[str, Any],
    ) -> None:
        """Perform a no-op PUT on an override to trigger recalculation."""
        override_id = override_data["id"]
        url = (
            f"{self.base_url}/api/v1/courses/{course_id}/"
            f"assignments/{assignment_id}/overrides/{override_id}"
        )

        # Build form data preserving all existing values
        form: dict[str, Any] = {}

        if "due_at" in override_data and override_data["due_at"] is not None:
            form["assignment_override[due_at]"] = override_data["due_at"]
        if "unlock_at" in override_data and override_data["unlock_at"] is not None:
            form["assignment_override[unlock_at]"] = override_data["unlock_at"]
        if "lock_at" in override_data and override_data["lock_at"] is not None:
            form["assignment_override[lock_at]"] = override_data["lock_at"]
        if "title" in override_data and override_data["title"] is not None:
            form["assignment_override[title]"] = override_data["title"]
        if "group_id" in override_data and override_data["group_id"] is not None:
            form["assignment_override[group_id]"] = override_data["group_id"]
        if (
            "student_ids" in override_data
            and override_data["student_ids"] is not None
        ):
            form["assignment_override[student_ids][]"] = override_data[
                "student_ids"
            ]

        response = self.session.put(url, data=form, timeout=30)

        if not response.ok:
            raise RuntimeError(
                f"HTTP {response.status_code} for PUT override {override_id}"
            )


def run_python_fallback(
    *,
    course_id: int,
    base_url: str,
    token: str,
    student_id: int | None = None,
    group_id: int | None = None,
    dry_run: bool = False,
    quiet: bool = False,
) -> int:
    """
    Python fallback implementation for override recalculation.

    Returns:
        0 on success, 1 on failure
    """
    # Validate mutually exclusive args
    if student_id is not None and group_id is not None:
        print("ERROR: Cannot specify both student_id and group_id", file=sys.stderr)
        return 1
    if student_id is None and group_id is None:
        print("ERROR: Must specify either student_id or group_id", file=sys.stderr)
        return 1

    client = CanvasClient(base_url, token)

    # Fetch all assignments
    if not quiet:
        print("Fetching assignments...", file=sys.stderr)
    try:
        assignments = client.get_assignments(course_id)
    except Exception as e:
        print(f"ERROR: Failed to fetch assignments: {e}", file=sys.stderr)
        return 1

    if not quiet:
        print(f"Found {len(assignments)} assignments", file=sys.stderr)

    # Fetch overrides for each assignment (sequential - this is the bottleneck)
    if not quiet:
        print("Fetching overrides (sequential - this is slow)...", file=sys.stderr)

    target_overrides: list[tuple[int, dict[str, Any], str]] = []

    for idx, assignment in enumerate(assignments, 1):
        assignment_id = assignment["id"]
        assignment_name = assignment.get("name", f"Assignment {assignment_id}")

        if not quiet and idx % 10 == 0:
            print(
                f"  Progress: {idx}/{len(assignments)} assignments checked...",
                file=sys.stderr,
            )

        try:
            overrides = client.get_overrides(course_id, assignment_id)
        except Exception as e:
            print(
                f"WARNING: Failed to fetch overrides for assignment {assignment_id}: {e}",
                file=sys.stderr,
            )
            continue

        for override in overrides:
            matches = False

            if student_id is not None:
                # Check if student is in the override
                override_student_ids = override.get("student_ids", [])
                matches = student_id in (override_student_ids or [])
            elif group_id is not None:
                # Check if group matches
                matches = override.get("group_id") == group_id

            if matches:
                target_overrides.append((assignment_id, override, assignment_name))

    if not target_overrides:
        print("No overrides found to recalculate")
        return 0

    action = "preview" if dry_run else "touch"
    print(f"Found {len(target_overrides)} override(s) to {action}")

    # Touch overrides (sequential)
    if dry_run:
        for assignment_id, override, name in target_overrides:
            override_id = override["id"]
            short_name = name[:40]
            print(f"  [DRY] Assignment {assignment_id} ({short_name}): override {override_id}")
    else:
        success_count = 0
        fail_count = 0

        for assignment_id, override, name in target_overrides:
            override_id = override["id"]
            short_name = name[:40]

            try:
                client.touch_override(course_id, assignment_id, override)
                success_count += 1
                if not quiet:
                    print(
                        f"  [OK] Assignment {assignment_id} ({short_name}): "
                        f"override {override_id} recalculated"
                    )
            except Exception as e:
                fail_count += 1
                print(f"  [FAIL] Assignment {assignment_id}: {e}", file=sys.stderr)

        print(f"\n✓ Recalculated {success_count} override(s) successfully")
        if fail_count > 0:
            print(f"✗ {fail_count} operation(s) failed", file=sys.stderr)
            return 1

    return 0

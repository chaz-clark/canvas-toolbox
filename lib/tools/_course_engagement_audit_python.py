#!/usr/bin/env python3
"""
_course_engagement_audit_python.py — Python fallback for engagement data fetching
(when Rust binary not available).

This is the SEQUENTIAL Python implementation. It works correctly but is slower
than the Rust version (5-10 minutes vs 30-60 seconds for 100+ students) because
it processes students one at a time instead of concurrently.

Called by course_engagement_audit.py when Rust binary is not found.
Not intended to be run directly - use the main tool instead.

For performance comparison:
- Python (this file): Sequential per-student HTTP requests
- Rust (engagement_audit_rs): Concurrent per-student requests

See docs/proposals/rust-high-priority-roadmap.md for details.
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


_TIMEOUT = 30


def fetch_student_submissions(
    base: str, cid: str, headers: dict, user_id: int | str,
) -> list[dict]:
    """All assignment + quiz submissions for one student."""
    out: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/students/submissions",
            headers=headers,
            params={
                "student_ids[]": str(user_id),
                "per_page": 100,
                "page": page,
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json() or []
        if not batch:
            break
        out += batch
        page += 1
    return out


def fetch_discussion_entries(
    base: str, cid: str, headers: dict, user_id: int | str,
) -> list[str]:
    """ISO timestamps of all discussion entries by one student."""
    timestamps: list[str] = []
    # Get topic IDs
    page = 1
    topic_ids: list[str] = []
    while True:
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/discussion_topics",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json() or []
        if not batch:
            break
        topic_ids += [str(t.get("id")) for t in batch if t.get("id")]
        page += 1
    uid_str = str(user_id)
    for tid in topic_ids:
        entry_page = 1
        while True:
            r = requests.get(
                f"{base}/api/v1/courses/{cid}/discussion_topics/{tid}/entries",
                headers=headers,
                params={"per_page": 100, "page": entry_page},
                timeout=_TIMEOUT,
            )
            if r.status_code >= 400:
                break  # some topics return 404; skip silently
            batch = r.json() or []
            if not batch:
                break
            for entry in batch:
                if str(entry.get("user_id")) == uid_str:
                    for k in ("updated_at", "created_at"):
                        v = entry.get(k)
                        if v:
                            timestamps.append(v)
            entry_page += 1
    return timestamps


def run_python_fallback(
    *,
    base_url: str,
    course_id: str,
    token: str,
    user_ids: list[int],
) -> list[dict[str, Any]]:
    """
    Python fallback for fetching engagement data.

    Returns list of dicts matching Rust output format:
    [
        {
            "user_id": 123,
            "submission_timestamps": ["2026-01-15T12:00:00Z", ...],
            "discussion_timestamps": ["2026-01-14T10:30:00Z", ...]
        },
        ...
    ]
    """
    headers = {"Authorization": f"Bearer {token}"}
    results = []

    for i, uid in enumerate(user_ids, 1):
        try:
            # Fetch submissions
            subs = fetch_student_submissions(base_url, course_id, headers, uid)
            sub_timestamps = [s.get("submitted_at") for s in subs if s.get("submitted_at")]

            # Fetch discussion entries
            disc_timestamps = fetch_discussion_entries(base_url, course_id, headers, uid)

            results.append({
                "user_id": uid,
                "submission_timestamps": sub_timestamps,
                "discussion_timestamps": disc_timestamps,
            })

            if i % 10 == 0:
                print(f"  ...processed {i}/{len(user_ids)} (Python sequential)", file=sys.stderr)

        except (requests.HTTPError, requests.RequestException) as e:
            print(f"  [WARN] Failed to fetch student {uid}: {e}", file=sys.stderr)
            results.append({
                "user_id": uid,
                "submission_timestamps": [],
                "discussion_timestamps": [],
            })

    print(f"  ...processed {len(user_ids)}/{len(user_ids)} (Python sequential)", file=sys.stderr)
    return results

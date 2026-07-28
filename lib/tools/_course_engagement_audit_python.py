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

import re
import sys
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: requests module not installed", file=sys.stderr)
    print("Run: uv sync", file=sys.stderr)
    sys.exit(2)


_TIMEOUT = 30


def _paged_get(base: str, headers: dict, path: str, params: dict,
               tolerate_errors: bool = False) -> list:
    """GET a Canvas collection, following the `Link: rel="next"` header instead of
    blindly incrementing `page`. Several endpoints — including
    `/students/submissions?student_ids[]` — return HTTP 400 (NOT an empty page) when
    asked for a page past the last. Blind `page += 1` therefore hit page 2 on a
    single-page result, got a 400, and crashed the fetch — so EVERY student looked
    'never participated' even with grades (issue #67). `tolerate_errors` lets a
    first-request 4xx return [] (some discussion topics 404)."""
    out: list = []
    url: str | None = f"{base}{path}"
    p: dict | None = {**params, "per_page": 100}
    while url:
        r = requests.get(url, headers=headers,
                         params=p if "?" not in url else None, timeout=_TIMEOUT)
        if tolerate_errors and r.status_code >= 400:
            break
        r.raise_for_status()
        out += r.json() or []
        m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link", ""))
        url = m.group(1) if m else None
        p = None
    return out


def fetch_student_submissions(
    base: str, cid: str, headers: dict, user_id: int | str,
) -> list[dict]:
    """All assignment + quiz submissions for one student (Link-paginated, #67)."""
    return _paged_get(base, headers, f"/api/v1/courses/{cid}/students/submissions",
                      {"student_ids[]": str(user_id)})


def fetch_discussion_entries(
    base: str, cid: str, headers: dict, user_id: int | str,
) -> list[str]:
    """ISO timestamps of all discussion entries by one student (Link-paginated)."""
    topics = _paged_get(base, headers, f"/api/v1/courses/{cid}/discussion_topics", {})
    uid_str = str(user_id)
    timestamps: list[str] = []
    for tid in (str(t.get("id")) for t in topics if t.get("id")):
        entries = _paged_get(
            base, headers, f"/api/v1/courses/{cid}/discussion_topics/{tid}/entries",
            {}, tolerate_errors=True)  # some topics 404 — skip
        for entry in entries:
            if str(entry.get("user_id")) == uid_str:
                for k in ("updated_at", "created_at"):
                    v = entry.get(k)
                    if v:
                        timestamps.append(v)
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

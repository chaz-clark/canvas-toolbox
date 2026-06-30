#!/usr/bin/env python3
"""
List Canvas assignments for a course — discovery input to `grader_fetch.py`.

Closes canvas-toolbox#55. `grader_fetch.py` requires `--assignment-id <N>`,
but the toolkit had no discovery path: operators wrote canvasapi snippets
inline (m119 SP26 calibration: same snippet authored 3 separate times) to
find the id by name. Trivial wrapper; eliminates the inline pattern.

USAGE
  uv run python lib/tools/grader_list_assignments.py
      --course-id 409936

  # Filter by name (regex, case-insensitive)
  uv run python lib/tools/grader_list_assignments.py
      --course-id 409936 --filter "task 1"
  uv run python lib/tools/grader_list_assignments.py
      --course-id 409936 --filter "cohesive|ai log"

  # Published only (drop draft / workflow_state=unpublished)
  uv run python lib/tools/grader_list_assignments.py
      --course-id 409936 --published-only

  # Add submitted/total column for "what's ready to grade" triage
  uv run python lib/tools/grader_list_assignments.py
      --course-id 409936 --include-unsubmitted-count

  # JSON for downstream tooling
  uv run python lib/tools/grader_list_assignments.py
      --course-id 409936 --format json

FERPA
  Returns assignment names + IDs + counts only. No student data. Safe by
  construction. `canvas_course_guard.enforce(mode="read")` prints an
  advisory but does not block (read-only).

ENV
  Honors CANVAS_API_TOKEN / CANVAS_BASE_URL / CANVAS_COURSE_ID via
  `_env_loader.py` (same pattern as the rest of the grader_* family).
  `--course-id` overrides CANVAS_COURSE_ID.

EXIT CODES
  0  list printed (even if empty / no matches — empty is a valid result)
  2  setup / env / course-not-found / Canvas API error
"""
from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import json
import os
import re
import sys

import requests

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    pass

try:
    import canvas_course_guard as guard
except ImportError:
    guard = None

_TIMEOUT = 30


def _env_canvas(course_id_override: str | None) -> tuple[str, str, str]:
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    cid = course_id_override or os.environ.get("CANVAS_COURSE_ID", "")
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return tok, cid, base


def _get_paged(base: str, headers: dict, path: str, params: dict | None = None) -> list:
    out: list = []
    url = f"{base}/api/v1{path}"
    base_params = {**(params or {}), "per_page": 100}
    while url:
        r = requests.get(url, headers=headers,
                         params=base_params if "?" not in url else None,
                         timeout=_TIMEOUT)
        r.raise_for_status()
        page = r.json()
        if isinstance(page, list):
            out.extend(page)
        else:
            return [page]
        link = r.headers.get("Link", "")
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
        base_params = None
    return out


def fetch_assignments(base: str, headers: dict, cid: str,
                      published_only: bool) -> list[dict]:
    # Canvas's /assignments endpoint has no direct "published-only" query
    # param — pull everything, filter client-side.
    rows = _get_paged(base, headers, f"/courses/{cid}/assignments")
    if published_only:
        rows = [a for a in rows if a.get("published") is True]
    return rows


def fetch_submission_counts(base: str, headers: dict, cid: str,
                            aid: int) -> tuple[int, int]:
    """(submitted_count, total_active_enrollments). Pulls the assignment's
    submission_summary plus the course's active student count."""
    summary = requests.get(
        f"{base}/api/v1/courses/{cid}/assignments/{aid}/submission_summary",
        headers=headers, timeout=_TIMEOUT,
    )
    summary.raise_for_status()
    js = summary.json() or {}
    graded = int(js.get("graded") or 0)
    ungraded = int(js.get("ungraded") or 0)
    not_submitted = int(js.get("not_submitted") or 0)
    submitted = graded + ungraded
    total = submitted + not_submitted
    return submitted, total


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def render_text(rows: list[dict], include_counts: bool) -> str:
    lines: list[str] = []
    if not rows:
        return "(no assignments)"
    if include_counts:
        for a in rows:
            submitted = a.get("_submitted")
            total = a.get("_total")
            count = f"{submitted}/{total}" if total is not None else "—"
            published = "" if a.get("published") else "  [draft]"
            lines.append(f"{a['id']} | {a['name']} | {count}{published}")
    else:
        for a in rows:
            published = "" if a.get("published") else "  [draft]"
            lines.append(f"{a['id']} | {a['name']}{published}")
    return "\n".join(lines)


def render_json(rows: list[dict], include_counts: bool) -> str:
    out: list[dict] = []
    for a in rows:
        rec = {
            "id": a.get("id"),
            "name": a.get("name"),
            "published": a.get("published"),
            "due_at": a.get("due_at"),
            "points_possible": a.get("points_possible"),
            "submission_types": a.get("submission_types"),
            "assignment_group_id": a.get("assignment_group_id"),
        }
        if include_counts:
            rec["submitted"] = a.get("_submitted")
            rec["total"] = a.get("_total")
        out.append(rec)
    return json.dumps(out, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="List Canvas assignments for a course (read-only; discovery input to "
                    "grader_fetch.py). Returns assignment names + IDs only — FERPA-safe.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--course-id", default=None,
                    help="Override CANVAS_COURSE_ID env var.")
    ap.add_argument("--filter", default=None,
                    help="Case-insensitive regex matched against assignment name.")
    ap.add_argument("--published-only", action="store_true",
                    help="Drop drafts (workflow_state != published).")
    ap.add_argument("--include-unsubmitted-count", action="store_true",
                    help="Add a submitted/total column. Costs one extra API call per assignment.")
    ap.add_argument("--format", choices=("text", "json"), default="text",
                    help="Output format. Default: text.")
    args = ap.parse_args()

    tok, cid, base = _env_canvas(args.course_id)
    for var, val in (("CANVAS_API_TOKEN", tok), ("CANVAS_BASE_URL", base), ("CANVAS_COURSE_ID", cid)):
        if not val:
            print(f"Missing {var} (env or --course-id).", file=sys.stderr)
            return 2
    headers = {"Authorization": f"Bearer {tok}"}

    if guard is not None:
        try:
            guard.enforce(base, headers, cid, mode="read", label="assignment list target")
        except SystemExit:
            raise
        except Exception as e:
            print(f"WARN: canvas_course_guard failed ({type(e).__name__}: {e}) — continuing read-only.",
                  file=sys.stderr)

    try:
        rows = fetch_assignments(base, headers, cid, args.published_only)
    except requests.HTTPError as e:
        print(f"Canvas API error fetching /courses/{cid}/assignments: {e}", file=sys.stderr)
        return 2

    if args.filter:
        try:
            pat = re.compile(args.filter, re.IGNORECASE)
        except re.error as e:
            print(f"Invalid --filter regex: {e}", file=sys.stderr)
            return 2
        rows = [a for a in rows if pat.search(a.get("name") or "")]

    if args.include_unsubmitted_count:
        for a in rows:
            try:
                submitted, total = fetch_submission_counts(base, headers, cid, int(a["id"]))
                a["_submitted"] = submitted
                a["_total"] = total
            except requests.HTTPError:
                a["_submitted"] = None
                a["_total"] = None

    rows.sort(key=lambda a: (a.get("due_at") or "9999", a.get("name") or ""))

    if args.format == "json":
        print(render_json(rows, args.include_unsubmitted_count))
    else:
        print(render_text(rows, args.include_unsubmitted_count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

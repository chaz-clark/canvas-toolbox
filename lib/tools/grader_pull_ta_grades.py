#!/usr/bin/env python3
"""
Pull TA grades for an assignment — symmetric PULL counterpart to
`grader_grade.py`'s PUSH path.

Closes canvas-toolbox#56. The toolkit had `grader_grade.py` to PUSH grades
but no symmetric PULL operation. For the calibration-cohort use case
(compare grader call against the TA's pass/fail call, ground every
contested band in a TA decision the instructor can defend), every cohort
needed `ta_grades_<surface>.json`. m119 SP26 calibration authored the same
canvasapi snippet inline 3 separate times.

OUTPUT SHAPE (canonical — matches what the m119 cohorts already use)
  JSON array, one record per non-skipped submission:

    [{"user_id": 33619, "grade": "complete", "score": 0.0},
     {"user_id": 86533, "grade": "complete", "score": 0.0}, ...]

  With --include-workflow-state, each record also has
  "workflow_state": "graded" | "submitted" | "pending_review" | ...

SKIPPED workflow states (consistent with grader_fetch.py's discipline)
  - unsubmitted
  - deleted

FERPA
  user_id + grade + score only. NO names, NO comments, NO submission body.
  user_id is an internal LMS row id (not SIS) — FERPA-safe per the same
  rationale that lets grader_fetch print user_id but never name.

USAGE
  uv run python lib/tools/grader_pull_ta_grades.py \\
      --assignment-id 16958397 \\
      --out grading/p1t1_combined/ai_log/ta_grades_ai_log.json

  # Override course id (rare — normally CANVAS_COURSE_ID env)
  uv run python lib/tools/grader_pull_ta_grades.py \\
      --course-id 409936 --assignment-id 16958397 --out <path>

  # Include workflow_state for "graded vs ungraded" downstream filtering
  uv run python lib/tools/grader_pull_ta_grades.py \\
      --assignment-id 16958397 --out <path> --include-workflow-state

EXIT CODES
  0  pulled + written
  2  setup / env / Canvas API error

NOT DONE IN v1
  --auto-chain (write both ai_log + cohesive at the _combined/ task level)
  is captured in the issue thread but blocks on the umbrella-#54 task-layout
  convention. Trivial to add once the canonical layout is finalized.
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
from pathlib import Path

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
_SKIP_STATES = {"unsubmitted", "deleted"}


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


def pull_ta_grades(base: str, headers: dict, cid: str, aid: int,
                   include_workflow_state: bool) -> list[dict]:
    rows = _get_paged(base, headers, f"/courses/{cid}/assignments/{aid}/submissions")
    out: list[dict] = []
    for s in rows:
        state = s.get("workflow_state") or ""
        if state in _SKIP_STATES:
            continue
        rec = {
            "user_id": s.get("user_id"),
            "grade": s.get("grade"),
            "score": s.get("score"),
        }
        if include_workflow_state:
            rec["workflow_state"] = state
        out.append(rec)
    return out


def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Pull TA grades for an assignment (FERPA-safe: user_id + grade + score only).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--assignment-id", required=True, type=int,
                    help="Canvas assignment id whose TA grades to pull.")
    ap.add_argument("--course-id", default=None,
                    help="Override CANVAS_COURSE_ID env var.")
    ap.add_argument("--out", required=True,
                    help="Output JSON path (e.g. grading/<task>/ai_log/ta_grades_ai_log.json).")
    ap.add_argument("--include-workflow-state", action="store_true",
                    help="Add workflow_state field per record (graded / submitted / pending_review / ...).")
    args = ap.parse_args()

    tok, cid, base = _env_canvas(args.course_id)
    for var, val in (("CANVAS_API_TOKEN", tok), ("CANVAS_BASE_URL", base), ("CANVAS_COURSE_ID", cid)):
        if not val:
            print(f"Missing {var} (env or --course-id).", file=sys.stderr)
            return 2
    headers = {"Authorization": f"Bearer {tok}"}

    if guard is not None:
        try:
            guard.enforce(base, headers, cid, mode="read", label="TA grade pull target")
        except SystemExit:
            raise
        except Exception as e:
            print(f"WARN: canvas_course_guard failed ({type(e).__name__}: {e}) — continuing read-only.",
                  file=sys.stderr)

    try:
        rows = pull_ta_grades(base, headers, cid, args.assignment_id, args.include_workflow_state)
    except requests.HTTPError as e:
        print(f"Canvas API error: {e}", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    # Console summary: counts only — never a name, never per-row detail.
    graded = sum(1 for r in rows if r.get("score") is not None or r.get("grade") not in (None, ""))
    print(f"  TA grades pulled → {out_path}  ({len(rows)} record(s), {graded} graded, "
          f"{len(rows) - graded} ungraded/pending).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

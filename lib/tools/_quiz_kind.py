"""_quiz_kind.py — classify a Canvas assignment as New Quiz / Classic Quiz
/ not-a-quiz and recommend the data-access path.

Closes the surface gap from issue #86: any tool that reads or grades
quiz responses MUST classify the quiz first, because New Quizzes
(Quizzes.Next) responses are API-walled. The detector saves every
consumer ~2 hours of independent rediscovery (m119, ds460, itm327 all
hit this in 2026-06).

USAGE — programmatic
    from _quiz_kind import detect_quiz_kind
    kind, path = detect_quiz_kind(base, headers, course_id, assignment_id)
    # kind in {"new_quiz", "classic_quiz", "not_a_quiz"}
    # path in {"reporting_api", "submission_data", "submitted_proxy", "none"}

USAGE — CLI (debugging)
    uv run python lib/tools/_quiz_kind.py --course-id 12345 --assignment-id 67890

The pure classifier `classify_assignment_shape(assn_payload)` takes an
already-fetched assignment dict and returns the same tuple. Use this
when you've already fetched the assignment for other reasons.

See lib/agents/knowledge/learned/2026-06-18_new-quizzes-responses-api-walled.md
for the full branching tree + the three viable data paths.
"""
from __future__ import annotations

import argparse
import json
import os
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

_TIMEOUT = 30

# URL fragments that confirm a New Quiz launcher. Canvas's NQ launcher
# URL has shifted over time — accept either pattern.
_NQ_URL_MARKERS = ("quiz-lti", "quiz_lti", "quizzes.next")


def classify_assignment_shape(assignment: dict) -> tuple[str, str]:
    """Pure classifier — takes an already-fetched assignment dict.

    Returns (kind, recommended_path) where:
      kind in {"new_quiz", "classic_quiz", "not_a_quiz"}
      path in {"reporting_api", "submission_data", "submitted_proxy", "none"}

    Decision order (strongest signal wins):
      1. quiz_id is set + non-null  → classic_quiz
      2. submission_types == ["online_quiz"]  → classic_quiz
      3. submission_types == ["external_tool"] AND
         external_tool_tag_attributes.url contains a NQ marker  → new_quiz
      4. anything else  → not_a_quiz
    """
    submission_types = assignment.get("submission_types") or []
    quiz_id = assignment.get("quiz_id")

    # Classic Quiz: explicit quiz_id beats everything
    if quiz_id is not None and quiz_id:
        return "classic_quiz", "submission_data"

    if "online_quiz" in submission_types:
        return "classic_quiz", "submission_data"

    if "external_tool" in submission_types:
        ext = (assignment.get("external_tool_tag_attributes") or {})
        url = (ext.get("url") or "").lower()
        if any(marker in url for marker in _NQ_URL_MARKERS):
            return "new_quiz", "reporting_api"
        # external_tool without a NQ URL → some other LTI launcher
        return "not_a_quiz", "none"

    return "not_a_quiz", "none"


def detect_quiz_kind(
    base: str, headers: dict, course_id: int, assignment_id: int,
) -> tuple[str, str]:
    """Fetch the assignment, then classify. Network-touching wrapper
    around classify_assignment_shape."""
    url = f"{base.rstrip('/')}/api/v1/courses/{course_id}/assignments/{assignment_id}"
    r = requests.get(url, headers=headers, timeout=_TIMEOUT)
    r.raise_for_status()
    return classify_assignment_shape(r.json() or {})


def _env_canvas() -> tuple[str, str]:
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return tok, base


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Classify a Canvas assignment as New Quiz / Classic Quiz / "
            "not-a-quiz and recommend the data-access path. Reads "
            "CANVAS_API_TOKEN + CANVAS_BASE_URL from the environment. "
            "Outputs JSON to stdout."
        ),
    )
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    ap.add_argument("--course-id", type=int, required=True)
    ap.add_argument("--assignment-id", type=int, required=True)
    args = ap.parse_args()

    tok, base = _env_canvas()
    if not tok or not base:
        print("Missing CANVAS_API_TOKEN or CANVAS_BASE_URL in .env",
              file=sys.stderr)
        return 1
    headers = {"Authorization": f"Bearer {tok}"}

    try:
        kind, path = detect_quiz_kind(base, headers, args.course_id,
                                       args.assignment_id)
    except requests.HTTPError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Recommended next-step messaging — gives the operator/agent a
    # concrete tool name, not just a category label.
    next_step = {
        "reporting_api": "use grader_fetch_nq_responses.py (#87)",
        "submission_data": ("use grader_reconcile.py "
                            "(classic_quiz_submissions source) or read "
                            "submission_history.submission_data directly"),
        "submitted_proxy": ("use grader_reconcile.py "
                            "(gradebook source + completion_basis)"),
        "none": "this isn't a quiz; use the appropriate non-quiz tooling",
    }[path]

    print(json.dumps({
        "course_id": args.course_id,
        "assignment_id": args.assignment_id,
        "kind": kind,
        "recommended_path": path,
        "next_step": next_step,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

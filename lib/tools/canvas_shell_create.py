#!/usr/bin/env python3
"""
canvas_shell_create.py — create a Classic Quiz or Assignment shell in Canvas (#349).

WHY THIS EXISTS
  canvas_sync.py's --push only ever PUTs: `_push_quiz`/`_push_assignment` require a
  `canvas_id` already present in `.canvas/index.json` and refuse otherwise ("no
  canvas_id in index"). There was no path to CREATE a new quiz or assignment through
  the toolkit at all — confirmed against a real course (m119-master) where the
  instructor had to create three new per-project reflection quizzes by hand in the
  Canvas UI, and separately keeps an unpublished "Project # (template)" assignment
  specifically so shells can be duplicated in the UI, evidence this gap isn't
  quiz-specific.

WHAT THIS DELIBERATELY DOES NOT DO
  Write the local `course/<module>/<slug>.json` file or `.canvas/index.json` entry
  that canvas_sync.py's normal pull/push cycle depends on. That logic already exists,
  is more involved than it looks (module-relative paths, markdown mirrors, hash
  tracking), and duplicating it here risks drifting from the real thing. Instead:
  create the object (and optionally place it in a module), then tell the operator to
  run `canvas_sync.py --pull` — the existing, proven path picks up anything sitting
  in a module and writes the matching local file + index entry itself.

  This also means an item created with no --module-id is real in Canvas (visible in
  the Assignments list / SpeedGrader) but invisible to canvas_sync's own tracking
  until it's placed in a module — the same way canvas_sync's pull already works
  (module-walking, not a course-wide assignments scan). Not a new limitation; the
  existing one, surfaced honestly rather than worked around here.

WHY UNPUBLISHED BY DEFAULT
  A student never sees an unpublished item. Same reasoning as every other creation
  tool in this project (peer_review_setup.py, grading_scheme_setup.py) — the instructor
  publishes when ready, not this tool on their behalf.

WHY THE CREATE IS READ BACK
  Same reason course dates and grading schemes are (#182) — a 200 is not proof the
  write landed as asked. Read back the created object before reporting success.

DRAFT FILE SHAPE (--draft PATH, JSON)
  Common:      {"kind": "quiz" | "assignment", "title": "...", "description": "...",
                "points_possible": 10, "due_at": "2026-10-01T05:59:00Z",
                "lock_at": "...", "unlock_at": "...",
                "assignment_group_id": 12345}
  Quiz only:   "quiz_type" (default "assignment"), "time_limit", "allowed_attempts"
  Assignment only: "submission_types" (default ["online_text_entry"]), "grading_type"

Usage:
  # dry run (default) — validates the draft, shows what would be created
  uv run python lib/tools/canvas_shell_create.py --draft prep_quiz.json

  # create it (unpublished), optionally placed in a module
  uv run python lib/tools/canvas_shell_create.py --draft prep_quiz.json --apply \\
      --module-id 456789

  # then, to track it locally like anything else canvas_sync manages:
  uv run python lib/tools/canvas_sync.py --pull

Requires in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, and the env var named by
--target (default CANVAS_COURSE_ID).

Exit codes:
  0  created (or already exists by exact title) and verified, or dry run
  1  Canvas did not apply the write, or read-back disagreed
  2  configuration / validation error
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available

import canvas_course_guard as guard
from __toolbox_version__ import __version__

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url

_TIMEOUT = 20
_VALID_GRADING_TYPES = {"pass_fail", "percent", "letter_grade", "gpa_scale", "points", "not_graded"}
_VALID_QUIZ_TYPES = {"practice_quiz", "assignment", "graded_survey", "survey"}
_DATE_FIELDS = ("due_at", "lock_at", "unlock_at")


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}", "Content-Type": "application/json"}


def _get(endpoint: str) -> dict | list | None:
    try:
        resp = requests.get(f"{CANVAS_BASE_URL}/api/v1{endpoint}", headers=_headers(),
                            params={"per_page": 100}, timeout=_TIMEOUT)
    except Exception:
        return None
    if resp.status_code >= 400:
        return None
    try:
        return resp.json()
    except Exception:
        return None


def _post(endpoint: str, form: dict) -> tuple[dict | None, str]:
    try:
        resp = requests.post(f"{CANVAS_BASE_URL}/api/v1{endpoint}", headers=_headers(),
                             json=form, timeout=_TIMEOUT)
    except Exception as e:
        return None, str(e)
    if resp.status_code >= 400:
        return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
    try:
        return resp.json(), ""
    except Exception:
        return None, "response was not JSON"


# ---------------------------------------------------------------------------
# Draft parsing + payload building (PURE)
# ---------------------------------------------------------------------------

def load_draft(path: str) -> dict:
    """Read and lightly normalize the draft file. Raises ValueError on bad JSON —
    caller turns that into exit code 2, never a traceback at the operator."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"draft file not found: {path}") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object, not a {type(data).__name__}")
    return data


def validate_draft(draft: dict) -> list[str]:
    """What's wrong with this draft, if anything. Empty list = ready to create.
    Refuses a shape Canvas would accept-but-render-wrong, same reasoning as
    grading_scheme_setup.py's validate_tiers — a retype is cheap, a confusing
    shell in front of students is not (mitigated further by unpublished-by-default,
    but the fields should still be sane before any write)."""
    errors = []
    kind = draft.get("kind")
    if kind not in ("quiz", "assignment"):
        errors.append('"kind" must be "quiz" or "assignment"')
    if not (draft.get("title") or "").strip():
        errors.append('"title" is required and must be non-empty')
    pts = draft.get("points_possible")
    if pts is not None and (not isinstance(pts, (int, float)) or pts < 0):
        errors.append('"points_possible" must be a non-negative number')
    gt = draft.get("grading_type")
    if gt is not None and gt not in _VALID_GRADING_TYPES:
        errors.append(f'"grading_type" {gt!r} is not one of {sorted(_VALID_GRADING_TYPES)}')
    qt = draft.get("quiz_type")
    if qt is not None and qt not in _VALID_QUIZ_TYPES:
        errors.append(f'"quiz_type" {qt!r} is not one of {sorted(_VALID_QUIZ_TYPES)}')
    st = draft.get("submission_types")
    if st is not None and (not isinstance(st, list) or not st):
        errors.append('"submission_types" must be a non-empty list when given')
    for field in _DATE_FIELDS:
        v = draft.get(field)
        if v is not None and not isinstance(v, str):
            errors.append(f'"{field}" must be an ISO 8601 date string, e.g. "2026-10-01T05:59:00Z"')
    return errors


def build_assignment_payload(draft: dict) -> dict:
    """Canvas's POST /assignments shape — a nested dict, matching canvas_sync.py's
    own _post()/_put() convention (json=payload, not form-encoded bracket keys;
    those are two different wire formats and mixing them sends Canvas a body it
    silently ignores every field of)."""
    assignment: dict = {
        "name": draft["title"],
        "description": draft.get("description") or "",
        "published": False,
        "submission_types": draft.get("submission_types") or ["online_text_entry"],
    }
    if draft.get("points_possible") is not None:
        assignment["points_possible"] = draft["points_possible"]
    if draft.get("grading_type"):
        assignment["grading_type"] = draft["grading_type"]
    if draft.get("assignment_group_id"):
        assignment["assignment_group_id"] = draft["assignment_group_id"]
    for field in _DATE_FIELDS:
        if draft.get(field):
            assignment[field] = draft[field]
    return {"assignment": assignment}


def build_quiz_payload(draft: dict) -> dict:
    """Canvas's POST /quizzes shape. Dates go on the quiz itself at create time —
    unlike an UPDATE, where _push_quiz's own comment notes the quiz endpoint ignores
    due_at and dates must go through the linked assignment instead."""
    quiz: dict = {
        "title": draft["title"],
        "description": draft.get("description") or "",
        "published": False,
        "quiz_type": draft.get("quiz_type") or "assignment",
    }
    if draft.get("points_possible") is not None:
        quiz["points_possible"] = draft["points_possible"]
    if draft.get("time_limit") is not None:
        quiz["time_limit"] = draft["time_limit"]
    if draft.get("allowed_attempts") is not None:
        quiz["allowed_attempts"] = draft["allowed_attempts"]
    if draft.get("assignment_group_id"):
        quiz["assignment_group_id"] = draft["assignment_group_id"]
    for field in _DATE_FIELDS:
        if draft.get(field):
            quiz[field] = draft[field]
    return {"quiz": quiz}


def build_module_item_payload(kind: str, content_id: int, title: str) -> dict:
    return {"module_item": {
        "title": title,
        "type": "Quiz" if kind == "quiz" else "Assignment",
        "content_id": content_id,
    }}


def print_plan(draft: dict) -> None:
    kind = draft.get("kind", "?")
    print(f"  kind:            {kind}")
    print(f"  title:           {draft.get('title')}")
    if kind == "quiz":
        if draft.get("points_possible") is not None:
            print(f"  points_possible: {draft['points_possible']}  "
                  "(sent, but Canvas derives a quiz's points from its questions —")
            print("                   this won't take effect until questions are added;")
            print("                   verified for real on a sandbox, #349)")
        print(f"  quiz_type:       {draft.get('quiz_type', 'assignment')}")
    else:
        print(f"  points_possible: {draft.get('points_possible', '(none)')}")
        print(f"  submission_types:{draft.get('submission_types', ['online_text_entry'])}")
    for field in _DATE_FIELDS:
        if draft.get(field):
            print(f"  {field}:          {draft[field]}")
    if draft.get("assignment_group_id"):
        print(f"  assignment_group_id: {draft['assignment_group_id']}")


# ---------------------------------------------------------------------------
# Writes (each read back — a 200 is not proof it landed, #182)
# ---------------------------------------------------------------------------

def find_existing(course_id: str, kind: str, title: str) -> dict | None:
    """An object already carrying this exact title, if any — idempotency by title,
    same convention as every other creation tool in this project."""
    endpoint = "/quizzes" if kind == "quiz" else "/assignments"
    for obj in _get(f"/courses/{course_id}{endpoint}") or []:
        name_field = "title" if kind == "quiz" else "name"
        if isinstance(obj, dict) and (obj.get(name_field) or "").strip() == title.strip():
            return obj
    return None


def create_shell(course_id: str, draft: dict) -> tuple[dict | None, str]:
    kind = draft["kind"]
    if kind == "quiz":
        created, err = _post(f"/courses/{course_id}/quizzes", build_quiz_payload(draft))
    else:
        created, err = _post(f"/courses/{course_id}/assignments", build_assignment_payload(draft))
    if not created:
        return None, err
    endpoint = "/quizzes" if kind == "quiz" else "/assignments"
    back = _get(f"/courses/{course_id}{endpoint}/{created['id']}")
    name_field = "title" if kind == "quiz" else "name"
    if not isinstance(back, dict) or (back.get(name_field) or "").strip() != draft["title"].strip():
        return None, (f"Canvas reported success but the {kind} did not read back intact "
                      f"(id {created.get('id')}). Check it in Canvas before re-running.")
    if back.get("published"):
        return None, f"Canvas created the {kind} but it came back published, not unpublished as asked."
    return back, ""


def add_to_module(course_id: str, module_id: str, kind: str, content_id: int,
                  title: str) -> tuple[bool, str]:
    created, err = _post(f"/courses/{course_id}/modules/{module_id}/items",
                         build_module_item_payload(kind, content_id, title))
    if not created:
        return False, err
    return True, ""


def main() -> int:
    force_utf8_console()  # #123

    ap = argparse.ArgumentParser(
        description="Create a Classic Quiz or Assignment shell in Canvas (unpublished).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--draft", required=True, metavar="PATH",
                    help="Local JSON file describing the shell — see this file's own "
                         "docstring for the shape.")
    ap.add_argument("--module-id", default=None,
                    help="Add the created item to this module. Omit to create it "
                         "unfiled (real in Canvas, but invisible to canvas_sync's "
                         "own tracking until placed in a module).")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Env var holding the course id (default CANVAS_COURSE_ID)")
    ap.add_argument("--course-id", default=None, help="Literal course id; overrides --target")
    ap.add_argument("--apply", action="store_true",
                    help="Write to Canvas. Without this the run is a dry run.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Proceed even if the course has enrolled students")
    args = ap.parse_args()

    if not CANVAS_API_TOKEN or not CANVAS_BASE_URL:
        print("ERROR: CANVAS_API_TOKEN and CANVAS_BASE_URL must be set.")
        return 2
    course_id = (args.course_id or os.environ.get(args.target, "")).strip()
    if not course_id:
        source = "--course-id" if args.course_id else f"${args.target}"
        print(f"ERROR: course ID not found via {source}.")
        print("       Set the env var, or pass --course-id <id> directly.")
        return 2

    try:
        draft = load_draft(args.draft)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 2
    errors = validate_draft(draft)
    if errors:
        print("ERROR: draft is invalid:")
        for e in errors:
            print(f"  - {e}")
        return 2
    kind = draft["kind"]

    print(f"{kind.capitalize()} shell: {draft['title']}"
          f"   ({'APPLYING' if args.apply else 'DRY RUN — pass --apply to write'})")
    print_plan(draft)
    if args.module_id:
        print(f"  module:          {args.module_id}")
    else:
        print("  module:          (none — will not be picked up by `canvas_sync.py "
              "--pull` until placed in a module)")

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="write" if args.apply else "read",
                  allow_override=args.allow_enrolled, label="shell-create target")

    existing = find_existing(course_id, kind, draft["title"])
    if existing:
        print(f"\n  already exists (id {existing.get('id')}) — nothing to do. "
              f"This tool never edits an existing {kind}; use canvas_sync.py --push "
              f"for that once it's tracked locally.")
        return 0

    if not args.apply:
        print("\nRe-run with --apply to create it.")
        return 0

    created, err = create_shell(course_id, draft)
    if not created:
        print(f"\nERROR creating {kind}: {err}")
        return 1
    cid = created["id"]
    print(f"\n  ✓ {kind} created and verified (id {cid}, unpublished)")

    if args.module_id:
        ok, err = add_to_module(course_id, args.module_id, kind, cid, draft["title"])
        if not ok:
            print(f"\nERROR adding to module {args.module_id}: {err}")
            print(f"  The {kind} exists (id {cid}) but was not placed in a module. "
                  f"Add it manually in Canvas, or re-run this tool's module-add step.")
            return 1
        print(f"  ✓ added to module {args.module_id}")

    print(f"\nNext: run `uv run python lib/tools/canvas_sync.py --pull` to track this "
          f"{kind} locally like everything else canvas_sync manages"
          + ("." if args.module_id else
             " — note it won't be picked up until it's placed in a module."))
    return 0


if __name__ == "__main__":
    sys.exit(main())

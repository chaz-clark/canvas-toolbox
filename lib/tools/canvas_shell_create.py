#!/usr/bin/env python3
"""
canvas_shell_create.py — create a Canvas object shell that doesn't exist yet (#349,
#351), or place an already-existing one into one or more modules (#355).

WHY THIS EXISTS
  canvas_sync.py's --push only ever PUTs: every `_push_*` function requires a
  `canvas_id`/`page_url` already present in `.canvas/index.json` and refuses
  otherwise ("no canvas_id in index"). There was no path to CREATE a new object
  through the toolkit at all — confirmed against a real course (m119-master) where
  the instructor had to create three new per-project reflection quizzes by hand in
  the Canvas UI, and separately keeps an unpublished "Project # (template)"
  assignment specifically so shells can be duplicated in the UI.

  #349/#350 closed this for quiz/assignment shells. A follow-up sweep of the rest of
  `lib/tools/` (documented in `handoffs/parkinglot.md` and `docs/ROADMAP.md`, #351)
  found the identical shape in 4 more object types: read support and
  update-an-existing-object support, but no create path outside `sync_to_new.py`'s
  whole-course clone (a different tool solving a different problem — migrating an
  entire course into a new shell, not adding one object to a course that already
  exists). This file now covers all six: `quiz`, `assignment`, `page`, `discussion`,
  `module`, `assignment_group`.

  New Quiz creation is deliberately out of scope for this Classic/API-v1 shell
  tool, not missed. New Quizzes use the separate `/api/quiz/v1` surface; their
  content path belongs in `canvas_sync.py` / the New Quiz sync workstream, while
  this tool continues to create only Classic Quiz shells.

  #355 closed a follow-on gap: module placement only ever fired inside
  create_shell()'s success path, once, at creation time — so there was no way to
  place an ALREADY-existing item into a module, and no way to place the SAME item
  into a SECOND module at all (real case: an assignment living in both a weekly
  module and a dedicated per-project module simultaneously). `--module-id` is now
  repeatable, and `--place` places an existing item without creating anything.

WHAT THIS DELIBERATELY DOES NOT DO
  Write the local `course/<module>/<slug>.json` file or `.canvas/index.json` entry
  that canvas_sync.py's normal pull/push cycle depends on. That logic already exists,
  is more involved than it looks (module-relative paths, markdown mirrors, hash
  tracking), and duplicating it here risks drifting from the real thing. Instead:
  create the object (and optionally place it in a module, for the kinds that are
  module-item-eligible), then tell the operator to run `canvas_sync.py --pull` — the
  existing, proven path picks up anything sitting in a module and writes the
  matching local file + index entry itself.

  This also means an item created with no --module-id is real in Canvas (visible in
  the Assignments list / SpeedGrader) but invisible to canvas_sync's own tracking
  until it's placed in a module — the same way canvas_sync's pull already works
  (module-walking, not a course-wide assignments scan). Not a new limitation; the
  existing one, surfaced honestly rather than worked around here. `module` and
  `assignment_group` shells are never module items themselves — Canvas has no such
  relationship — so `--module-id` is refused for those two kinds.

WHY UNPUBLISHED BY DEFAULT
  A student never sees an unpublished item. Same reasoning as every other creation
  tool in this project (peer_review_setup.py, grading_scheme_setup.py) — the instructor
  publishes when ready, not this tool on their behalf. Assignment groups have no
  publish state in Canvas (they're a grading category, not visible content) — the
  unpublished-by-default reasoning doesn't apply and read-back skips that check only
  for this one kind.

WHY THE CREATE IS READ BACK
  Same reason course dates and grading schemes are (#182) — a 200 is not proof the
  write landed as asked. Read back the created object before reporting success.

DRAFT FILE SHAPE (--draft PATH, JSON)
  Common:            {"kind": "quiz" | "assignment" | "page" | "discussion" |
                       "module" | "assignment_group", "title": "...",
                       "description": "..."}
  quiz/assignment only: "points_possible", "due_at", "lock_at", "unlock_at",
                       "assignment_group_id"
  Quiz only:         "quiz_type" (default "assignment"), "time_limit", "allowed_attempts"
  Assignment only:   "submission_types" (default ["online_text_entry"]), "grading_type"
  Page/Discussion:   "description" is the page body / discussion message
  Discussion only:   "is_announcement" (bool, default false)
  Module only:       "position" (int), "unlock_at"
  Assignment group only: "position" (int), "group_weight" (number)

Usage:
  # dry run (default) — validates the draft, shows what would be created
  uv run python lib/tools/canvas_shell_create.py --draft prep_quiz.json

  # create it (unpublished), optionally placed in one or more modules
  uv run python lib/tools/canvas_shell_create.py --draft prep_quiz.json --apply \\
      --module-id 456789 --module-id 456790

  # place an ALREADY-EXISTING item into one or more modules, no --draft needed
  uv run python lib/tools/canvas_shell_create.py --place assignment \\
      --title "Project 3 Compiled Report" --module-id 456789 --module-id 456791 \\
      --apply

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
_VALID_KINDS = {"quiz", "assignment", "page", "discussion", "module", "assignment_group"}
# Module items in Canvas can only point at these types — module/assignment_group
# shells are never module items themselves (no such relationship exists).
_MODULE_ITEM_KINDS = {"quiz", "assignment", "page", "discussion"}
# endpoint suffix, the field Canvas returns the title/name under
_KIND_ENDPOINT = {
    "quiz": "/quizzes",
    "assignment": "/assignments",
    "page": "/pages",
    "discussion": "/discussion_topics",
    "module": "/modules",
    "assignment_group": "/assignment_groups",
}
_KIND_NAME_FIELD = {
    "quiz": "title",
    "assignment": "name",
    "page": "title",
    "discussion": "title",
    "module": "name",
    "assignment_group": "name",
}
# Canvas Pages are addressed by url slug, not numeric id, in API paths.
_KIND_ID_FIELD = {"page": "url"}
# Assignment groups have no publish state in Canvas — a grading category, not content.
_KINDS_WITHOUT_PUBLISH_STATE = {"assignment_group"}


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
    if kind not in _VALID_KINDS:
        errors.append(f'"kind" must be one of {sorted(_VALID_KINDS)}')
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
    ia = draft.get("is_announcement")
    if ia is not None and not isinstance(ia, bool):
        errors.append('"is_announcement" must be true or false')
    pos = draft.get("position")
    if pos is not None and (not isinstance(pos, int) or isinstance(pos, bool) or pos < 1):
        errors.append('"position" must be a positive integer')
    gw = draft.get("group_weight")
    if gw is not None and (not isinstance(gw, (int, float)) or gw < 0):
        errors.append('"group_weight" must be a non-negative number')
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


def build_page_payload(draft: dict) -> dict:
    """Canvas's POST /pages shape. Same wrapper-key convention as quiz/assignment —
    the existing canvas_pages.py's upsert_page() already proves this wire format."""
    return {"wiki_page": {
        "title": draft["title"],
        "body": draft.get("description") or "",
        "published": False,
    }}


def build_discussion_payload(draft: dict) -> dict:
    """Canvas's POST /discussion_topics shape — flat, NOT wrapped in a
    "discussion_topic" key. Matches canvas_sync.py's own _push_discussion(), which
    PUTs this same endpoint with a flat body; the Discussion Topics API (unlike
    quizzes/assignments/pages) never uses a wrapper key."""
    return {
        "title": draft["title"],
        "message": draft.get("description") or "",
        "published": False,
        "is_announcement": bool(draft.get("is_announcement", False)),
    }


def build_module_payload(draft: dict) -> dict:
    """Canvas's POST /modules shape — proven wire format, already used by
    sync_to_new.py's create_module() for whole-course clones."""
    module: dict = {"name": draft["title"], "published": False}
    if draft.get("position") is not None:
        module["position"] = draft["position"]
    if draft.get("unlock_at"):
        module["unlock_at"] = draft["unlock_at"]
    return {"module": module}


def build_assignment_group_payload(draft: dict) -> dict:
    """Canvas's POST /assignment_groups shape — FLAT, NOT wrapped in an
    "assignment_group" key, unlike quiz/assignment/page/module. Caught on a sandbox,
    not assumed: sync_to_new.py's create_assignment_group() wraps it (matching the
    other 4 kinds' convention) and that assumption was wrong for this one endpoint —
    a wrapped POST returns 200 but silently creates a group named "Assignments" with
    group_weight 0, ignoring every field sent. No "published" field either —
    assignment groups have no publish state in Canvas."""
    ag: dict = {"name": draft["title"]}
    if draft.get("position") is not None:
        ag["position"] = draft["position"]
    if draft.get("group_weight") is not None:
        ag["group_weight"] = draft["group_weight"]
    return ag


_KIND_BUILDER = {
    "quiz": lambda d: build_quiz_payload(d),
    "assignment": lambda d: build_assignment_payload(d),
    "page": lambda d: build_page_payload(d),
    "discussion": lambda d: build_discussion_payload(d),
    "module": lambda d: build_module_payload(d),
    "assignment_group": lambda d: build_assignment_group_payload(d),
}


def build_module_item_payload(kind: str, content_id, title: str) -> dict:
    """content_id is the Canvas numeric id for quiz/assignment/discussion, or the
    page's url slug for a Page (Canvas's module-item API takes `page_url` instead
    of `content_id` for that one type)."""
    item_type = {"quiz": "Quiz", "assignment": "Assignment",
                 "page": "Page", "discussion": "Discussion"}[kind]
    item: dict = {"title": title, "type": item_type}
    if kind == "page":
        item["page_url"] = content_id
    else:
        item["content_id"] = content_id
    return {"module_item": item}


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
        for field in _DATE_FIELDS:
            if draft.get(field):
                print(f"  {field}:          {draft[field]}")
        if draft.get("assignment_group_id"):
            print(f"  assignment_group_id: {draft['assignment_group_id']}")
    elif kind == "assignment":
        print(f"  points_possible: {draft.get('points_possible', '(none)')}")
        print(f"  submission_types:{draft.get('submission_types', ['online_text_entry'])}")
        for field in _DATE_FIELDS:
            if draft.get(field):
                print(f"  {field}:          {draft[field]}")
        if draft.get("assignment_group_id"):
            print(f"  assignment_group_id: {draft['assignment_group_id']}")
    elif kind == "discussion":
        print(f"  is_announcement: {bool(draft.get('is_announcement', False))}")
    elif kind == "module":
        if draft.get("position") is not None:
            print(f"  position:        {draft['position']}")
        if draft.get("unlock_at"):
            print(f"  unlock_at:       {draft['unlock_at']}")
    elif kind == "assignment_group":
        if draft.get("position") is not None:
            print(f"  position:        {draft['position']}")
        if draft.get("group_weight") is not None:
            print(f"  group_weight:    {draft['group_weight']}")


# ---------------------------------------------------------------------------
# Writes (each read back — a 200 is not proof it landed, #182)
# ---------------------------------------------------------------------------

def find_existing(course_id: str, kind: str, title: str) -> dict | None:
    """An object already carrying this exact title, if any — idempotency by title,
    same convention as every other creation tool in this project."""
    endpoint = _KIND_ENDPOINT[kind]
    name_field = _KIND_NAME_FIELD[kind]
    for obj in _get(f"/courses/{course_id}{endpoint}") or []:
        if isinstance(obj, dict) and (obj.get(name_field) or "").strip() == title.strip():
            return obj
    return None


def create_shell(course_id: str, draft: dict) -> tuple[dict | None, str]:
    kind = draft["kind"]
    endpoint = _KIND_ENDPOINT[kind]
    name_field = _KIND_NAME_FIELD[kind]
    id_field = _KIND_ID_FIELD.get(kind, "id")

    created, err = _post(f"/courses/{course_id}{endpoint}", _KIND_BUILDER[kind](draft))
    if not created:
        return None, err
    back = _get(f"/courses/{course_id}{endpoint}/{created[id_field]}")
    if not isinstance(back, dict) or (back.get(name_field) or "").strip() != draft["title"].strip():
        return None, (f"Canvas reported success but the {kind} did not read back intact "
                      f"({id_field} {created.get(id_field)}). Check it in Canvas before re-running.")
    if kind not in _KINDS_WITHOUT_PUBLISH_STATE and back.get("published"):
        return None, f"Canvas created the {kind} but it came back published, not unpublished as asked."
    return back, ""


def item_in_module(course_id: str, module_id: str, kind: str, content_id) -> bool:
    """True if an item of this type/content already sits in this module — the
    module-item equivalent of find_existing()'s idempotency-by-title, so placing
    the same item into the same module twice is a no-op, not a duplicate row."""
    item_type = {"quiz": "Quiz", "assignment": "Assignment",
                 "page": "Page", "discussion": "Discussion"}[kind]
    field = "page_url" if kind == "page" else "content_id"
    for it in _get(f"/courses/{course_id}/modules/{module_id}/items") or []:
        if isinstance(it, dict) and it.get("type") == item_type and it.get(field) == content_id:
            return True
    return False


def add_to_module(course_id: str, module_id: str, kind: str, content_id,
                  title: str) -> tuple[str, str]:
    """Returns (status, error). status is 'added', 'already_in_module', or 'error'."""
    if item_in_module(course_id, module_id, kind, content_id):
        return "already_in_module", ""
    created, err = _post(f"/courses/{course_id}/modules/{module_id}/items",
                         build_module_item_payload(kind, content_id, title))
    if not created:
        return "error", err
    return "added", ""


def place_in_modules(course_id: str, kind: str, content_id, title: str,
                     module_ids: list[str]) -> bool:
    """Places (idempotently) into every module in module_ids — attempts all of
    them even if one fails (#355: a course-wide-per-module network hiccup
    shouldn't block placement into the OTHER modules), and prints a per-module
    line so a partial failure is never silently swallowed. Returns True iff
    every module succeeded (added or already there)."""
    all_ok = True
    for module_id in module_ids:
        status, err = add_to_module(course_id, module_id, kind, content_id, title)
        if status == "added":
            print(f"  ✓ added to module {module_id}")
        elif status == "already_in_module":
            print(f"  ✓ already in module {module_id} — nothing to do")
        else:
            print(f"  ✗ ERROR adding to module {module_id}: {err}")
            all_ok = False
    return all_ok


def main() -> int:
    force_utf8_console()  # #123

    ap = argparse.ArgumentParser(
        description="Create a Canvas object shell (quiz, assignment, page, discussion, "
                    "module, or assignment group), unpublished — or place an "
                    "already-existing one into one or more modules (--place).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--draft", default=None, metavar="PATH",
                    help="Local JSON file describing the shell to CREATE — see this "
                         "file's own docstring for the shape. Mutually exclusive "
                         "with --place.")
    ap.add_argument("--place", choices=sorted(_MODULE_ITEM_KINDS), default=None,
                    help="Place an ALREADY-EXISTING item of this kind into one or "
                         "more modules (#355), instead of creating anything. "
                         "Requires --title and at least one --module-id.")
    ap.add_argument("--title", default=None,
                    help="Exact title of the existing item to place — only used "
                         "with --place.")
    ap.add_argument("--module-id", action="append", default=[],
                    help="Place the item in this module. Repeatable — pass "
                         "--module-id more than once to place into 2+ modules "
                         "(#355). Only valid for kind in "
                         f"{sorted(_MODULE_ITEM_KINDS)} — modules and assignment "
                         "groups are never module items themselves. With --draft "
                         "and omitted, the created item is left unfiled (real in "
                         "Canvas, but invisible to canvas_sync's own tracking "
                         "until placed in a module).")
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

    if args.draft and args.place:
        print("ERROR: --draft (create) and --place (place an existing item) are "
              "mutually exclusive.")
        return 2
    if not args.draft and not args.place:
        print("ERROR: one of --draft or --place is required.")
        return 2

    if args.place:
        return _run_place(course_id=course_id, kind=args.place, title=args.title,
                          module_ids=args.module_id, apply=args.apply,
                          allow_enrolled=args.allow_enrolled)
    return _run_create(course_id=course_id, draft_path=args.draft,
                       module_ids=args.module_id, apply=args.apply,
                       allow_enrolled=args.allow_enrolled)


def _run_place(*, course_id: str, kind: str, title: str | None, module_ids: list[str],
               apply: bool, allow_enrolled: bool) -> int:
    if not title or not title.strip():
        print("ERROR: --place requires --title (the exact title of the existing item).")
        return 2
    if not module_ids:
        print("ERROR: --place requires at least one --module-id.")
        return 2

    print(f"Place existing {kind}: {title}"
          f"   ({'APPLYING' if apply else 'DRY RUN — pass --apply to write'})")
    for module_id in module_ids:
        print(f"  module:          {module_id}")

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="write" if apply else "read",
                  allow_override=allow_enrolled, label="shell-create target")

    existing = find_existing(course_id, kind, title)
    if not existing:
        print(f"\nERROR: no existing {kind} titled {title!r} found in course {course_id}.")
        return 1
    id_field = _KIND_ID_FIELD.get(kind, "id")
    ident = existing[id_field]
    print(f"\n  found existing {kind} ({id_field} {ident})")

    if not apply:
        print("\nRe-run with --apply to place it.")
        return 0

    ok = place_in_modules(course_id, kind, ident, title, module_ids)
    if not ok:
        return 1
    print(f"\nNext: run `uv run python lib/tools/canvas_sync.py --pull` to track this "
          f"{kind} locally like everything else canvas_sync manages.")
    return 0


def _run_create(*, course_id: str, draft_path: str, module_ids: list[str],
                apply: bool, allow_enrolled: bool) -> int:
    try:
        draft = load_draft(draft_path)
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
    id_field = _KIND_ID_FIELD.get(kind, "id")
    module_eligible = kind in _MODULE_ITEM_KINDS

    if module_ids and not module_eligible:
        print(f"ERROR: --module-id is not valid for kind '{kind}' — modules and "
              "assignment groups are never module items themselves.")
        return 2

    print(f"{kind.replace('_', ' ').capitalize()} shell: {draft['title']}"
          f"   ({'APPLYING' if apply else 'DRY RUN — pass --apply to write'})")
    print_plan(draft)
    if module_eligible:
        if module_ids:
            for module_id in module_ids:
                print(f"  module:          {module_id}")
        else:
            print("  module:          (none — will not be picked up by `canvas_sync.py "
                  "--pull` until placed in a module)")

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="write" if apply else "read",
                  allow_override=allow_enrolled, label="shell-create target")

    existing = find_existing(course_id, kind, draft["title"])
    if existing:
        ident = existing[id_field]
        print(f"\n  already exists ({id_field} {ident}) — nothing to do. "
              f"This tool never edits an existing {kind}; use canvas_sync.py --push "
              f"for that once it's tracked locally.")
        if module_ids and module_eligible:
            if not apply:
                print("\nRe-run with --apply to place it in the requested module(s).")
                return 0
            # #355: hitting "already exists" used to short-circuit before ever
            # reaching module placement, so --module-id silently did nothing on
            # a second run. Place it (idempotently) instead of just returning.
            ok = place_in_modules(course_id, kind, ident, draft["title"], module_ids)
            return 0 if ok else 1
        return 0

    if not apply:
        print("\nRe-run with --apply to create it.")
        return 0

    created, err = create_shell(course_id, draft)
    if not created:
        print(f"\nERROR creating {kind}: {err}")
        return 1
    ident = created[id_field]
    status = "no publish state" if kind in _KINDS_WITHOUT_PUBLISH_STATE else "unpublished"
    print(f"\n  ✓ {kind} created and verified ({id_field} {ident}, {status})")

    place_ok = True
    if module_ids:
        place_ok = place_in_modules(course_id, kind, ident, draft["title"], module_ids)
        if not place_ok:
            print(f"\n  The {kind} exists ({id_field} {ident}) but was not placed in "
                  f"every requested module. Add the missing one(s) manually in "
                  f"Canvas, or re-run with --place --title {draft['title']!r} "
                  f"--module-id <id>.")

    if module_eligible:
        print(f"\nNext: run `uv run python lib/tools/canvas_sync.py --pull` to track this "
              f"{kind} locally like everything else canvas_sync manages"
              + ("." if module_ids else
                 " — note it won't be picked up until it's placed in a module."))
    else:
        print(f"\nNext: run `uv run python lib/tools/canvas_sync.py --pull` to track this "
              f"{kind} locally — {kind}s are pulled directly, no module placement needed.")
    return 0 if place_ok else 1


if __name__ == "__main__":
    sys.exit(main())

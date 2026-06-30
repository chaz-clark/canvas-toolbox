#!/usr/bin/env python3
"""
sandbox_rubric_fixtures.py — seed known rubric scenarios into a sandbox course.

Purpose: the rubric audit tools (rubric_coverage_audit.py, rubric_quality_audit.py)
score rubric *quality*, which can only be validated against KNOWN inputs with
KNOWN-correct verdicts. A real production course rarely contains every rubric
shape (ITM327 had ZERO rubrics). This tool authors a fixture matrix in a
write-safe sandbox course so the audits can be asserted against ground truth.

This is the toolkit's first WRITE tool for rubrics. It creates assignments +
rubrics; it is confirmation-gated and guard-checked.

Fixture matrix (each maps to a known-correct audit result):
  analytic_well_formed   -> coverage:has_rubric        quality:meets_criteria[_unverified]
  single_point           -> coverage:has_rubric        quality:C2 exempted
  decorative             -> coverage:decorative_rubric  (use_for_grading=false)
  range_based            -> coverage:has_rubric        quality:C4 points_and_weights flag
  weak                   -> coverage:has_rubric        quality:needs_revision
  no_rubric_points       -> coverage:missing_rubric
  no_rubric_none_points  -> coverage:missing_rubric     (the None!=0 fix)
  no_rubric_zero_points  -> coverage:non_gradable
  external_tool          -> coverage:lti_external_tool

Endpoints used:
  GET    /courses/:id?include[]=total_students   (guard)
  GET    /courses/:id/blueprint_subscriptions    (guard)
  GET    /courses/:id/assignments                (idempotency: find by title)
  POST   /courses/:id/assignments                (create assignment)
  DELETE /courses/:id/assignments/:aid           (teardown)
  POST   /courses/:id/rubrics                     (create rubric + association)

Exit codes:
  0  success (plan shown, or apply/teardown completed)
  2  configuration error / cannot run / guard refused

Usage:
  uv run python canvas_toolbox/lib/tools/sandbox_rubric_fixtures.py            # --plan (default)
  uv run python canvas_toolbox/lib/tools/sandbox_rubric_fixtures.py --apply
  uv run python canvas_toolbox/lib/tools/sandbox_rubric_fixtures.py --teardown
  uv run python canvas_toolbox/lib/tools/sandbox_rubric_fixtures.py --course-id 12345 --apply

Requires in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_SANDBOX_ID
(or pass --course-id). Writes ONLY to the sandbox course.

All fixture assignments are titled with the FIXTURE_PREFIX so they are
identifiable and teardown only ever deletes fixtures it owns.
"""

from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import os
import sys

import requests
from dotenv import load_dotenv

import canvas_course_guard as guard
from __toolbox_version__ import __version__

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url
CANVAS_SANDBOX_ID = os.environ.get("CANVAS_SANDBOX_ID", "")

_TIMEOUT = 30
FIXTURE_PREFIX = "FIXTURE:"


# ---------------------------------------------------------------------------
# Fixture definitions
# ---------------------------------------------------------------------------
# Each fixture: title (without prefix), points, submission_types, and an
# optional rubric spec. A rubric spec is {use_for_grading, criteria:[...]}
# where each criterion is {description, long_description, points, use_range,
# ratings:[{description, long_description, points}]}.

def _levels(*pairs):
    """pairs of (description, long_description, points) -> rating dicts."""
    return [{"description": d, "long_description": ld, "points": p}
            for (d, ld, p) in pairs]


FIXTURES = [
    {
        "key": "analytic_well_formed",
        "title": "analytic well-formed",
        "points": 100, "submission_types": ["online_text_entry"],
        "expect_coverage": "has_rubric",
        "expect_quality": "meets_criteria OR meets_criteria_unverified (no CLOs)",
        "rubric": {
            "use_for_grading": True,
            "criteria": [
                {"description": "Thesis", "long_description": "States a clear, arguable thesis",
                 "points": 50, "use_range": False,
                 "ratings": _levels(
                     ("Exemplary", "States a precise arguable thesis in the first paragraph", 50),
                     ("Proficient", "States an arguable thesis", 38),
                     ("Developing", "States a topic but not an arguable thesis", 25),
                     ("Beginning", "No identifiable thesis", 0))},
                {"description": "Evidence", "long_description": "Supports claims with cited evidence",
                 "points": 50, "use_range": False,
                 "ratings": _levels(
                     ("Exemplary", "Cites three or more sources in support of each claim", 50),
                     ("Proficient", "Cites at least two sources per claim", 38),
                     ("Developing", "Cites one source per claim", 25),
                     ("Beginning", "Claims lack cited evidence", 0))},
            ],
        },
    },
    {
        "key": "single_point",
        "title": "single-point",
        "points": 100, "submission_types": ["online_text_entry"],
        "expect_coverage": "has_rubric",
        "expect_quality": "rating_levels (C2) exempted for single_point typology",
        "rubric": {
            "use_for_grading": True,
            "criteria": [
                {"description": "Argument quality", "long_description": "Target: a clear, evidence-backed argument",
                 "points": 50, "use_range": False,
                 "ratings": _levels(("Meets target", "Clear argument backed by cited evidence", 50))},
                {"description": "Organization", "long_description": "Target: logical paragraph progression",
                 "points": 50, "use_range": False,
                 "ratings": _levels(("Meets target", "Each paragraph advances the argument in order", 50))},
            ],
        },
    },
    {
        "key": "decorative",
        "title": "decorative (display-only rubric)",
        "points": 100, "submission_types": ["online_text_entry"],
        "expect_coverage": "decorative_rubric",
        "expect_quality": "scored, but use_rubric_for_grading=false",
        "rubric": {
            "use_for_grading": False,   # the decorative signal
            "criteria": [
                {"description": "Clarity", "long_description": "Writing is clear and well organized",
                 "points": 100, "use_range": False,
                 "ratings": _levels(
                     ("Exemplary", "Consistently clear and well organized throughout", 100),
                     ("Developing", "Clarity lapses in places", 50),
                     ("Beginning", "Frequently unclear", 0))},
            ],
        },
    },
    {
        "key": "range_based",
        "title": "range-based (criterion_use_range)",
        "points": 100, "submission_types": ["online_text_entry"],
        "expect_coverage": "has_rubric",
        "expect_quality": "points_and_weights (C4) flag from criterion_use_range",
        "rubric": {
            "use_for_grading": True,
            "criteria": [
                {"description": "Depth of analysis", "long_description": "Analytical depth across the work",
                 "points": 100, "use_range": True,   # the range signal
                 "ratings": _levels(
                     ("Exemplary", "Sustained, original analysis", 100),
                     ("Proficient", "Solid analysis", 70),
                     ("Developing", "Surface-level analysis", 40),
                     ("Beginning", "Mostly description, little analysis", 0))},
            ],
        },
    },
    {
        "key": "weak",
        "title": "weak (subjective levels + over-weighted accountability)",
        "points": 100, "submission_types": ["online_text_entry"],
        "expect_coverage": "has_rubric",
        "expect_quality": "needs_revision (rating_levels + process_oriented + points_and_weights)",
        "rubric": {
            "use_for_grading": True,
            "criteria": [
                {"description": "Submitted on time", "long_description": "Turned in by the deadline; correct file format",
                 "points": 50, "use_range": False,   # accountability weighted = content
                 "ratings": _levels(
                     ("Good", "On time", 50),
                     ("Fair", "Mostly on time", 25),
                     ("Poor", "Late", 0))},
                {"description": "Overall quality", "long_description": "General quality of the submission",
                 "points": 50, "use_range": False,
                 "ratings": _levels(
                     ("Good", "Shows good understanding", 50),
                     ("Fair", "Mostly correct with minor errors", 25),
                     ("Poor", "Somewhat incomplete", 0))},
            ],
        },
    },
    {
        "key": "no_rubric_points",
        "title": "no rubric, has points",
        "points": 100, "submission_types": ["online_text_entry"],
        "expect_coverage": "missing_rubric",
        "expect_quality": "n/a (not scored — no rubric)",
        "rubric": None,
    },
    {
        "key": "no_rubric_omitted_points",
        "title": "no rubric, points unset",
        "points": None, "submission_types": ["online_text_entry"],
        # FINDING (sandbox, 2026-05-22): Canvas coerces an omitted/null
        # points_possible to 0.0 via REST (PUT '' and 'null' both yield 0.0).
        # A true points_possible=None CANNOT be created through the API, so this
        # fixture lands in non_gradable, not missing_rubric. The None->missing_rubric
        # classifier fix is unit-tested and applies to None-points assignments
        # that arise via non-REST paths (UI / course import / blueprint copy) —
        # which is how ITM327's contract-graded course produced them.
        "expect_coverage": "non_gradable",
        "expect_quality": "n/a — Canvas coerced points to 0 (None not REST-creatable)",
        "rubric": None,
    },
    {
        "key": "no_rubric_zero_points",
        "title": "no rubric, zero points",
        "points": 0, "submission_types": ["online_text_entry"],
        "expect_coverage": "non_gradable",
        "expect_quality": "n/a",
        "rubric": None,
    },
    {
        "key": "external_tool",
        "title": "external tool (LTI)",
        "points": 50, "submission_types": ["external_tool"],
        "external_tool_url": "https://example.edu/lti/launch",
        "expect_coverage": "lti_external_tool",
        "expect_quality": "n/a",
        "rubric": None,
    },
]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(endpoint: str, params: dict | None = None):
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    results: list = []
    p: dict = {**(params or {}), "per_page": 100}
    while url:
        try:
            resp = requests.get(url, headers=_headers(), params=p, timeout=_TIMEOUT)
        except Exception:
            return None
        if resp.status_code >= 400:
            return None
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url = None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        p = {}
    return results


def full_title(fx: dict) -> str:
    return f"{FIXTURE_PREFIX} {fx['title']}"


def list_fixture_assignments(course_id: str) -> dict[str, dict]:
    """Return {title: assignment} for existing FIXTURE_PREFIX assignments."""
    out: dict[str, dict] = {}
    items = _get(f"/courses/{course_id}/assignments") or []
    if isinstance(items, list):
        for a in items:
            name = a.get("name") or ""
            if name.startswith(FIXTURE_PREFIX):
                out[name] = a
    return out


def create_assignment(course_id: str, fx: dict) -> dict | None:
    data = {
        "assignment[name]": full_title(fx),
        "assignment[published]": "true",
    }
    for st in fx["submission_types"]:
        data.setdefault("assignment[submission_types][]", st)
    if fx["points"] is not None:
        data["assignment[points_possible]"] = str(fx["points"])
    if fx.get("external_tool_url"):
        data["assignment[external_tool_tag_attributes][url]"] = fx["external_tool_url"]
        data["assignment[external_tool_tag_attributes][new_tab]"] = "true"
    try:
        resp = requests.post(
            f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/assignments",
            headers=_headers(), data=data, timeout=_TIMEOUT,
        )
    except Exception as e:
        print(f"    ERROR creating assignment: {e}", file=sys.stderr)
        return None
    if resp.status_code >= 400:
        print(f"    ERROR creating assignment '{fx['title']}': "
              f"{resp.status_code} {resp.text[:200]}", file=sys.stderr)
        return None
    return resp.json()


def create_rubric(course_id: str, assignment_id: int, fx: dict) -> dict | None:
    """POST a rubric + association onto the assignment. Form-encoded nested
    payload per the Canvas Rubrics survey."""
    spec = fx["rubric"]
    data: dict[str, str] = {
        "rubric[title]": f"{FIXTURE_PREFIX} {fx['title']} rubric",
        "rubric[free_form_criterion_comments]": "0",
        "rubric_association[association_id]": str(assignment_id),
        "rubric_association[association_type]": "Assignment",
        "rubric_association[purpose]": "grading",
        "rubric_association[use_for_grading]": "true" if spec["use_for_grading"] else "false",
    }
    for ci, crit in enumerate(spec["criteria"]):
        base = f"rubric[criteria][{ci}]"
        data[f"{base}[description]"] = crit["description"]
        data[f"{base}[long_description]"] = crit.get("long_description", "")
        data[f"{base}[points]"] = str(crit["points"])
        data[f"{base}[criterion_use_range]"] = "true" if crit.get("use_range") else "false"
        for ri, rating in enumerate(crit["ratings"]):
            rbase = f"{base}[ratings][{ri}]"
            data[f"{rbase}[description]"] = rating["description"]
            data[f"{rbase}[long_description]"] = rating.get("long_description", "")
            data[f"{rbase}[points]"] = str(rating["points"])
    try:
        resp = requests.post(
            f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/rubrics",
            headers=_headers(), data=data, timeout=_TIMEOUT,
        )
    except Exception as e:
        print(f"    ERROR creating rubric: {e}", file=sys.stderr)
        return None
    if resp.status_code >= 400:
        print(f"    ERROR creating rubric for '{fx['title']}': "
              f"{resp.status_code} {resp.text[:200]}", file=sys.stderr)
        return None
    return resp.json()


def delete_assignment(course_id: str, assignment_id: int) -> bool:
    try:
        resp = requests.delete(
            f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/assignments/{assignment_id}",
            headers=_headers(), timeout=_TIMEOUT,
        )
    except Exception:
        return False
    return resp.status_code < 400


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def do_plan(course_id: str) -> None:
    existing = list_fixture_assignments(course_id)
    print(f"PLAN — would seed {len(FIXTURES)} fixtures into course {course_id}:\n")
    for fx in FIXTURES:
        title = full_title(fx)
        status = "EXISTS (skip)" if title in existing else "CREATE"
        has_rub = "rubric" if fx["rubric"] else "no rubric"
        pts = fx["points"] if fx["points"] is not None else "None"
        print(f"  [{status:13}] {title}")
        print(f"      points={pts}  submission_types={fx['submission_types']}  {has_rub}")
        print(f"      expect coverage={fx['expect_coverage']}")
    print("\nRe-run with --apply to create (idempotent: existing fixtures skipped).")


def do_apply(course_id: str) -> None:
    existing = list_fixture_assignments(course_id)
    created, skipped, failed = 0, 0, 0
    for fx in FIXTURES:
        title = full_title(fx)
        if title in existing:
            print(f"  SKIP (exists)  {title}")
            skipped += 1
            continue
        print(f"  CREATE         {title}")
        a = create_assignment(course_id, fx)
        if not a:
            failed += 1
            continue
        aid = a.get("id")
        if fx["rubric"]:
            r = create_rubric(course_id, aid, fx)
            if not r:
                print(f"      (assignment {aid} created, but rubric failed)")
                failed += 1
                continue
        created += 1
    print(f"\nApplied: {created} created, {skipped} skipped, {failed} failed.")
    if failed:
        print("Some fixtures failed — see errors above. This is the sandbox-first "
              "loop working: fix the write path, re-run.", file=sys.stderr)


def do_teardown(course_id: str) -> None:
    existing = list_fixture_assignments(course_id)
    if not existing:
        print(f"No FIXTURE: assignments found in course {course_id}. Nothing to tear down.")
        return
    print(f"TEARDOWN — deleting {len(existing)} fixture assignments from course {course_id}:")
    deleted = 0
    for title, a in existing.items():
        ok = delete_assignment(course_id, a.get("id"))
        print(f"  {'DELETED' if ok else 'FAILED ':8} {title}")
        deleted += 1 if ok else 0
    print(f"\nDeleted {deleted}/{len(existing)}. (Deleting an assignment also removes "
          "its rubric association; the rubric object may remain in the course "
          "rubric library — harmless for re-seeding.)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Seed known rubric fixtures into a sandbox course for "
                    "ground-truth validation of the rubric audit tools."
    )
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--course-id", default=None,
                    help="Course ID to seed (default: CANVAS_SANDBOX_ID from .env)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Create the fixtures (write)")
    mode.add_argument("--teardown", action="store_true",
                      help="Delete all FIXTURE: assignments from the course")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Bypass the safety guard (NOT recommended; sandbox should be safe)")
    args = ap.parse_args()

    missing = []
    if not CANVAS_BASE_URL or CANVAS_BASE_URL == "https://":
        missing.append("CANVAS_BASE_URL")
    if not CANVAS_API_TOKEN:
        missing.append("CANVAS_API_TOKEN")
    if missing:
        print("ERROR: Missing required configuration:")
        for m in missing:
            print(f"  {m}")
        sys.exit(2)

    course_id = (args.course_id or CANVAS_SANDBOX_ID).strip()
    if not course_id:
        print("ERROR: no course ID. Set CANVAS_SANDBOX_ID in .env or pass --course-id.")
        sys.exit(2)

    writing = args.apply or args.teardown
    # Guard: writes must not hit an enrolled/blueprint course. A sandbox should
    # be neither. Read-mode (plan) is advisory only.
    guard.enforce(
        base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
        mode="write" if writing else "read",
        allow_override=args.allow_enrolled, label="sandbox",
    )

    print(f"Target course: {course_id}  (CANVAS_BASE_URL={CANVAS_BASE_URL})\n")

    if args.teardown:
        do_teardown(course_id)
    elif args.apply:
        do_apply(course_id)
    else:
        do_plan(course_id)


if __name__ == "__main__":
    main()

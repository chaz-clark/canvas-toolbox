"""Startup safety guard for write-capable Canvas tools (#27).

A stale or hand-edited .env can silently point `CANVAS_COURSE_ID` (or
another course-id env var) at an enrolled student section or a Blueprint
**child** course. Write-capable tools then push into the wrong kind of
course, which (combined with the non-idempotent page upsert #26 fixed)
amplified into the same page duplicated 4× across master/blueprint/2
sections during the ITM-327 incident.

This module checks before a tool writes:
  - GET /courses/:id?include[]=total_students   -> enrolled? (live section?)
  - GET /courses/:id/blueprint_subscriptions    -> Blueprint child?

`enforce()` hard-stops a write when either is true (sys.exit(2)) unless
the caller passes `allow_override=True` (from `--allow-enrolled`). On
`mode="read"` it prints an advisory and continues. On its own API error
it warns but does NOT block — guard failure must not break a tool.

Exception: an enrolled course that is still `unpublished` (students cannot
see it yet — e.g. a section built before the term starts) is NOT a
live-exposure risk. That case verdicts as ENROLLED_UNPUBLISHED and
`enforce()` proceeds with an advisory, no `--allow-enrolled` needed. A
Blueprint child still hard-stops regardless of publish state — that risk
is content propagation, not student exposure.

Pure functions: takes base_url + headers as args; no caller-globals
dependence; matches the canvas_pages.py / __toolbox_version__.py shared-
helper pattern.
"""

from __future__ import annotations

import os
import re
import sys

import requests

_TIMEOUT = 20

# Verdict values
SAFE = "safe"
ENROLLED = "enrolled"
ENROLLED_UNPUBLISHED = "enrolled_unpublished"  # enrolled but students can't see it yet
BLUEPRINT_CHILD = "blueprint_child"
ENROLLED_AND_BLUEPRINT_CHILD = "enrolled_and_blueprint_child"
ERROR = "error"  # guard call itself failed; don't block

# Course workflow_states in which students cannot see the course: enrollment
# exists but carries no live-exposure risk. "available" is the only published
# state; "completed"/"deleted" are handled elsewhere (concluded / 404).
_PREPUBLISH_STATES = {"unpublished", "created", "claimed"}

_SAFE_ALTERNATIVE = (
    "Sections belong in S#_COURSE_ID (S1_COURSE_ID, S2_COURSE_ID, …), "
    "not CANVAS_COURSE_ID."
)

# Some courses are for faculty (a training course, a cohort of instructors) but Canvas
# enrolls the participants under the Student role. COURSE_AUDIENCE=faculty in the
# course's .env tells the guard so its messages stop calling them students and stop
# pointing at the section-ID advice. It is context ONLY: the verdict, the write refusal
# and --allow-enrolled are unchanged — faculty-only never authorizes a write by itself.
_FACULTY_AUDIENCE_NOTE = (
    "Faculty-only course (COURSE_AUDIENCE=faculty): the Student-role enrollments are "
    "faculty, not students. Write safeguards are unchanged."
)


def is_faculty_only() -> bool:
    """True when the course's .env declares COURSE_AUDIENCE=faculty."""
    return os.environ.get("COURSE_AUDIENCE", "").strip().lower() == "faculty"


# ── Session scope lock (#444) ───────────────────────────────────────────────────
# One folder = one course family. The course ids this folder's .env declares
# (CANVAS_COURSE_ID, MASTER_/BLUEPRINT_/S1_… COURSE_ID) ARE the session's scope. A
# write aimed at any other course id is refused — the field failure was an agent
# working in one course and starting to change a different one. Reads only warn: the
# harm is a write to the wrong course, not looking at it.
#
# The explicit switch is CB_COURSE_SWITCH=<id>[,<id>] on that one command, per id, so
# permission is never blanket. Like --allow-enrolled it is for the instructor to
# authorize, not for the agent to reach for on its own.
_COURSE_ID_VAR = re.compile(r"^[A-Z0-9_]*COURSE_ID$")


def session_course_ids() -> set[str]:
    """Course ids this folder's environment declares. Empty set = nothing declared."""
    return {v.strip() for k, v in os.environ.items()
            if _COURSE_ID_VAR.match(k) and v.strip().isdigit()}


def check_session_scope(course_id: str, mode: str, label: str = "course") -> None:
    """Refuse a write to a course outside the folder's declared scope (#444)."""
    scope = session_course_ids()
    cid = str(course_id).strip()
    if not scope or cid in scope:
        return
    switched = {x.strip() for x in os.environ.get("CB_COURSE_SWITCH", "").split(",")}
    if cid in switched:
        print(f"ℹ️  canvas_course_guard: {label} {cid} is outside this folder's course "
              f"scope; CB_COURSE_SWITCH allows it for this command.", file=sys.stderr)
        return
    msg = (f"{label} {cid} is not one of this folder's courses "
           f"({', '.join(sorted(scope))}).")
    if mode == "read":
        print(f"⚠️  canvas_course_guard: {msg} Read-only; proceeding.", file=sys.stderr)
        return
    print(f"🔴 canvas_course_guard: REFUSING WRITE — {msg}", file=sys.stderr)
    print("    One folder is one course. Open that course's own folder/window, or, if "
          "the instructor explicitly wants this, re-run with "
          f"CB_COURSE_SWITCH={cid}.", file=sys.stderr)
    sys.exit(2)


# ── Wrong-folder guard (#444) ───────────────────────────────────────────────────
# Opening a folder that CONTAINS several course folders means no AGENTS.md, skills or
# grade_guardian hook load (they live in each course folder) and tools resolve .env by
# their own location, so there is no single course to lock to. Detect it and say so.
PARENT_FOLDER_MESSAGE = (
    "Please open one course folder per VS Code Window (or your IDE of Choice), this "
    "tool cannot be used if opened from a higher level folder with multiple courses."
)


def _is_course_folder(d) -> bool:
    return (d / ".env").is_file() or (d / "AGENTS.md").is_file()


def opened_above_courses(cwd=None) -> bool:
    """True when the working folder is not inside a course folder but holds two or
    more course folders directly beneath it."""
    from pathlib import Path
    here = Path(cwd or os.getcwd()).resolve()
    if any(_is_course_folder(d) for d in (here, *here.parents)):
        return False
    try:
        kids = [c for c in here.iterdir() if c.is_dir() and _is_course_folder(c)]
    except OSError:
        return False
    return len(kids) >= 2


def check_course_safety(
    base_url: str, headers: dict, course_id: str,
) -> tuple[str, list[str], str]:
    """Return (verdict, reasons, course_name).

    verdict: SAFE | ENROLLED | ENROLLED_UNPUBLISHED | BLUEPRINT_CHILD
             | ENROLLED_AND_BLUEPRINT_CHILD | ERROR
    reasons: human-readable lines explaining the verdict
    course_name: from the course object, or "<unknown>" if the call failed
    """
    course_name = "<unknown>"
    reasons: list[str] = []
    enrolled = False
    blueprint_child = False
    workflow_state = None

    try:
        resp = requests.get(
            f"{base_url}/api/v1/courses/{course_id}",
            headers=headers, params={"include[]": "total_students"},
            timeout=_TIMEOUT,
        )
        if resp.status_code >= 400:
            return ERROR, [f"GET /courses/{course_id} returned {resp.status_code}: "
                           f"{resp.text[:150]}"], course_name
        course = resp.json() if resp.content else {}
        course_name = course.get("name") or course_name
        workflow_state = course.get("workflow_state")
        total = course.get("total_students")
        if isinstance(total, int) and total > 0:
            enrolled = True
            reasons.append(f"{total} enrolled student{'s' if total != 1 else ''}")
    except Exception as e:  # network / JSON error
        return ERROR, [f"GET /courses/{course_id}: {e}"], course_name

    try:
        resp = requests.get(
            f"{base_url}/api/v1/courses/{course_id}/blueprint_subscriptions",
            headers=headers, timeout=_TIMEOUT,
        )
        if resp.status_code < 400:
            subs = resp.json() if resp.content else []
            if isinstance(subs, list) and len(subs) > 0:
                blueprint_child = True
                reasons.append(
                    f"Blueprint child — subscribed to {len(subs)} blueprint"
                    f"{'s' if len(subs) != 1 else ''}"
                )
        # 4xx here is non-fatal: many courses simply have no subscriptions
        # endpoint access; we already learned what we needed from the course
        # object call. Fall through.
    except Exception as e:
        # Don't downgrade the verdict on a soft secondary failure; record it.
        reasons.append(f"(blueprint_subscriptions check skipped: {e})")

    if enrolled and blueprint_child:
        return ENROLLED_AND_BLUEPRINT_CHILD, reasons, course_name
    if blueprint_child:
        return BLUEPRINT_CHILD, reasons, course_name
    if enrolled and workflow_state in _PREPUBLISH_STATES:
        reasons.append(f"course is {workflow_state} — students cannot see it yet")
        return ENROLLED_UNPUBLISHED, reasons, course_name
    if enrolled:
        return ENROLLED, reasons, course_name
    return SAFE, reasons, course_name


def enforce(
    base_url: str, headers: dict, course_id: str,
    mode: str, allow_override: bool = False, label: str = "course",
) -> None:
    """Run the guard. On unsafe + mode='write' + not allow_override -> exit 2.
    On unsafe + mode='read' -> advisory warning, continue.
    On enrolled-but-unpublished -> advisory, continue (no override needed).
    On guard error -> warning, continue (never block on guard failure)."""
    if mode not in ("read", "write"):
        raise ValueError(f"mode must be 'read' or 'write', got {mode!r}")

    if opened_above_courses():
        if mode == "write":
            print(f"🔴 canvas_course_guard: REFUSING WRITE — {PARENT_FOLDER_MESSAGE}",
                  file=sys.stderr)
            sys.exit(2)
        print(f"⚠️  canvas_course_guard: {PARENT_FOLDER_MESSAGE}", file=sys.stderr)

    check_session_scope(course_id, mode, label)

    verdict, reasons, name = check_course_safety(base_url, headers, course_id)

    if verdict == SAFE:
        return

    if verdict == ERROR:
        print(f"⚠️  canvas_course_guard: could not verify {label} {course_id} — "
              f"{'; '.join(reasons)}. Proceeding without the check.",
              file=sys.stderr)
        return

    reason_str = "; ".join(reasons)

    if verdict == ENROLLED_UNPUBLISHED:
        print(f"ℹ️  canvas_course_guard: {label} {course_id} ('{name}') — "
              f"{reason_str}. Students cannot see this course yet; proceeding.",
              file=sys.stderr)
        return

    header = (f"⚠️  canvas_course_guard: {label} {course_id} ('{name}') "
              f"flagged as {verdict.replace('_', ' ')} — {reason_str}.")
    # Faculty-only is context for a plain ENROLLED verdict. A Blueprint child is a
    # content-propagation risk regardless of who is enrolled, so it keeps the stock text.
    faculty = is_faculty_only() and verdict == ENROLLED
    advice = _FACULTY_AUDIENCE_NOTE if faculty else _SAFE_ALTERNATIVE

    if mode == "read":
        print(header, file=sys.stderr)
        print(f"    Read-only operation — proceeding with advisory. {advice}",
              file=sys.stderr)
        return

    # mode == "write"
    if allow_override:
        print(header, file=sys.stderr)
        print("    --allow-enrolled passed — proceeding with write despite the flag.",
              file=sys.stderr)
        return

    print(f"🔴 canvas_course_guard: REFUSING WRITE to {label} {course_id} "
          f"('{name}').", file=sys.stderr)
    print(f"    Reason: {reason_str}.", file=sys.stderr)
    print(f"    {advice}", file=sys.stderr)
    print("    To override knowingly: re-run with --allow-enrolled.", file=sys.stderr)
    sys.exit(2)

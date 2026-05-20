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

Pure functions: takes base_url + headers as args; no caller-globals
dependence; matches the canvas_pages.py / __toolbox_version__.py shared-
helper pattern.
"""

from __future__ import annotations

import sys

import requests

_TIMEOUT = 20

# Verdict values
SAFE = "safe"
ENROLLED = "enrolled"
BLUEPRINT_CHILD = "blueprint_child"
ENROLLED_AND_BLUEPRINT_CHILD = "enrolled_and_blueprint_child"
ERROR = "error"  # guard call itself failed; don't block

_SAFE_ALTERNATIVE = (
    "Sections belong in S#_COURSE_ID (S1_COURSE_ID, S2_COURSE_ID, …), "
    "not CANVAS_COURSE_ID."
)


def check_course_safety(
    base_url: str, headers: dict, course_id: str,
) -> tuple[str, list[str], str]:
    """Return (verdict, reasons, course_name).

    verdict: SAFE | ENROLLED | BLUEPRINT_CHILD | ENROLLED_AND_BLUEPRINT_CHILD | ERROR
    reasons: human-readable lines explaining the verdict
    course_name: from the course object, or "<unknown>" if the call failed
    """
    course_name = "<unknown>"
    reasons: list[str] = []
    enrolled = False
    blueprint_child = False

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
    if enrolled:
        return ENROLLED, reasons, course_name
    if blueprint_child:
        return BLUEPRINT_CHILD, reasons, course_name
    return SAFE, reasons, course_name


def enforce(
    base_url: str, headers: dict, course_id: str,
    mode: str, allow_override: bool = False, label: str = "course",
) -> None:
    """Run the guard. On unsafe + mode='write' + not allow_override -> exit 2.
    On unsafe + mode='read' -> advisory warning, continue.
    On guard error -> warning, continue (never block on guard failure)."""
    if mode not in ("read", "write"):
        raise ValueError(f"mode must be 'read' or 'write', got {mode!r}")

    verdict, reasons, name = check_course_safety(base_url, headers, course_id)

    if verdict == SAFE:
        return

    if verdict == ERROR:
        print(f"⚠️  canvas_course_guard: could not verify {label} {course_id} — "
              f"{'; '.join(reasons)}. Proceeding without the check.",
              file=sys.stderr)
        return

    reason_str = "; ".join(reasons)
    header = (f"⚠️  canvas_course_guard: {label} {course_id} ('{name}') "
              f"flagged as {verdict.replace('_', ' ')} — {reason_str}.")

    if mode == "read":
        print(header, file=sys.stderr)
        print(f"    Read-only operation — proceeding with advisory. {_SAFE_ALTERNATIVE}",
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
    print(f"    {_SAFE_ALTERNATIVE}", file=sys.stderr)
    print("    To override knowingly: re-run with --allow-enrolled.", file=sys.stderr)
    sys.exit(2)

"""
section_crosslist.py

Cross-list the sections of several Canvas courses into ONE destination course
(Canvas "cross-listing": the section, with its enrollments, moves into the
destination course; it stays a section — nothing is merged into a single section).

Which courses
  Default: every S#_COURSE_ID in the folder's .env (S1_COURSE_ID, S2_COURSE_ID, ...),
  lowest number first. The FIRST one is the destination; the rest are sources.
  Or name them: --courses 111,222,333 (first is the destination).
  --into <id> picks a different destination (it must be one of the courses).

  Every course must be one this folder's .env declares — the course guard refuses a
  write to any other id (see AGENTS.md "One course per session"). To cross-list a
  course that isn't declared, add it to .env as S#_COURSE_ID first.

What it does
  For each source course it lists the course's sections and, on --apply, calls
  POST /sections/:id/crosslist/:destination. A section already in the destination is
  skipped, so a re-run after a dropped connection only does what didn't land.
  After writing it re-reads the destination and reports which sections are in.

What it does NOT do
  - Move content, submissions or grades: students in a moved section see the
    DESTINATION course's content; their work in the source course stays there.
    Cross-list before students have started work.
  - Carry over section-level due-date overrides (they belong to the source course's
    assignments).

Undo (--undo)
  Sends cross-listed sections back to where they came from (DELETE
  /sections/:id/crosslist). Same course list, same plan-first / --apply / guards. Only
  sections in the destination that Canvas marks as coming from one of the OTHER listed
  courses are touched — a section that was always in the destination is never moved.
  Re-run after a partial failure: sections already back are simply not listed.

Usage:
    uv run python lib/tools/section_crosslist.py                    # plan (read-only), S# courses from .env
    uv run python lib/tools/section_crosslist.py --courses 111,222,333
    uv run python lib/tools/section_crosslist.py --apply            # write (confirmation-gated)
    uv run python lib/tools/section_crosslist.py --courses 111,222,333 --undo [--apply]

    --yes             apply without the APPLY prompt (caller already confirmed the plan with the instructor)
    --allow-enrolled  write to a live course / Blueprint child (the course guard refuses otherwise)
"""

import argparse
import os
import re
import sys

import requests

import canvas_course_guard as guard

from __toolbox_version__ import __version__

try:
    from _env_loader import load_env, force_utf8_console
    load_env()
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url

_SECTION_VAR = re.compile(r"^S(\d+)_COURSE_ID$")


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get_all(endpoint: str, params: dict = None) -> list:
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    out = []
    while url:
        resp = requests.get(url, headers=_headers(), params=params, timeout=20)
        if resp.status_code >= 400:
            print(f"ERROR {resp.status_code} GET {endpoint}: {resp.text[:200]}")
            sys.exit(1)
        out.extend(resp.json())
        url = resp.links.get("next", {}).get("url")
        params = None  # the next-link already carries the query string
    return out


def courses_from_env(environ=None) -> list[str]:
    """S#_COURSE_ID values from the environment, lowest # first."""
    environ = os.environ if environ is None else environ
    found = []
    for k, v in environ.items():
        m = _SECTION_VAR.match(k)
        if m and v.strip().isdigit():
            found.append((int(m.group(1)), v.strip()))
    return [cid for _, cid in sorted(found)]


def resolve_courses(courses_arg: str, into: str, environ=None) -> tuple[str, list[str]]:
    """Return (destination, sources). Exits with a plain message if it can't."""
    if courses_arg:
        ids = [c.strip() for c in courses_arg.split(",") if c.strip()]
    else:
        ids = courses_from_env(environ)
    ids = list(dict.fromkeys(ids))  # de-dupe, keep order
    if len(ids) < 2:
        print("ERROR: need at least two courses to cross-list. Pass --courses 111,222 "
              "or put S1_COURSE_ID, S2_COURSE_ID, ... in the course folder's .env.")
        sys.exit(1)
    dest = (into or ids[0]).strip()
    if dest not in ids:
        print(f"ERROR: --into {dest} is not one of the courses ({', '.join(ids)}).")
        sys.exit(1)
    return dest, [c for c in ids if c != dest]


def build_plan(dest: str, sources: list[str]) -> list[dict]:
    """One row per section in a source course, flagged if already in the destination."""
    dest_ids = {s["id"] for s in _get_all(f"/courses/{dest}/sections")}
    plan = []
    for src in sources:
        sections = _get_all(f"/courses/{src}/sections", {"include[]": "total_students"})
        if not sections:
            plan.append({"source": src, "section_id": None, "name": "(no sections left)",
                         "students": 0, "action": "none"})
        for s in sections:
            plan.append({"source": src, "section_id": s["id"], "name": s.get("name", ""),
                         "students": s.get("total_students") or 0,
                         "action": "skip" if s["id"] in dest_ids else "crosslist"})
    return plan


def build_undo_plan(dest: str, sources: list[str]) -> list[dict]:
    """One row per section in the destination that Canvas says came from a listed source."""
    plan = []
    for s in _get_all(f"/courses/{dest}/sections", {"include[]": "total_students"}):
        origin = str(s.get("nonxlist_course_id") or "")
        if origin in sources:
            plan.append({"source": origin, "section_id": s["id"], "name": s.get("name", ""),
                         "students": s.get("total_students") or 0, "action": "uncrosslist"})
    return plan


def print_plan(dest: str, plan: list[dict], undo: bool = False) -> int:
    act = "uncrosslist" if undo else "crosslist"
    print(f"\nDestination course: {dest}")
    print(f"{'source':>10}  {'section':>10}  {'students':>8}  action       name")
    for r in plan:
        sid = r["section_id"] if r["section_id"] is not None else "-"
        note = "already in destination" if r["action"] == "skip" else r["name"]
        print(f"{r['source']:>10}  {sid:>10}  {r['students']:>8}  {r['action']:<11}  {note}")
    todo = sum(1 for r in plan if r["action"] == act)
    if undo:
        print(f"\n{todo} section(s) to send back to their original course.")
        return todo
    print(f"\n{todo} section(s) to cross-list into {dest}.")
    if todo:
        print("Heads-up: moved students see the destination course's content; their work "
              "in the source course stays there. Section date overrides don't carry over.")
    return todo


def apply_undo(dest: str, plan: list[dict]) -> bool:
    """De-cross-list each planned section, then re-read the destination to verify."""
    failed = []
    for r in plan:
        resp = requests.delete(
            f"{CANVAS_BASE_URL}/api/v1/sections/{r['section_id']}/crosslist",
            headers=_headers(), timeout=20)
        if resp.status_code >= 400:
            print(f"  FAILED section {r['section_id']}: {resp.status_code} {resp.text[:200]}")
            failed.append(r["section_id"])
        else:
            print(f"  sent section {r['section_id']} ({r['name']}) back to course {r['source']}")
    still_in = {s["id"] for s in _get_all(f"/courses/{dest}/sections")}
    stuck = [r["section_id"] for r in plan if r["section_id"] in still_in]
    if stuck or failed:
        print(f"\nNOT all moved back. Still in destination: {stuck or 'none'}; errors: "
              f"{failed or 'none'}. Re-run --undo to retry only what's left.")
        return False
    print(f"\nVerified: those sections are no longer in course {dest}.")
    return True


def apply_plan(dest: str, plan: list[dict]) -> bool:
    """Cross-list each pending section, then re-read the destination to verify."""
    failed = []
    for r in plan:
        if r["action"] != "crosslist":
            continue
        resp = requests.post(
            f"{CANVAS_BASE_URL}/api/v1/sections/{r['section_id']}/crosslist/{dest}",
            headers=_headers(), timeout=20)
        if resp.status_code >= 400:
            print(f"  FAILED section {r['section_id']}: {resp.status_code} {resp.text[:200]}")
            failed.append(r["section_id"])
        else:
            print(f"  cross-listed section {r['section_id']} ({r['name']})")
    now_in = {s["id"] for s in _get_all(f"/courses/{dest}/sections")}
    missing = [r["section_id"] for r in plan
               if r["action"] == "crosslist" and r["section_id"] not in now_in]
    if missing or failed:
        print(f"\nNOT all landed. Not in destination: {missing or 'none'}; errors: {failed or 'none'}. "
              "Re-run to retry only what's missing.")
        return False
    print(f"\nVerified: all planned sections are now in course {dest}.")
    return True


def main():
    force_utf8_console()

    ap = argparse.ArgumentParser(description="Cross-list sections of several courses into one.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--courses", default="",
                    help="comma-separated course ids, first is the destination "
                         "(default: every S#_COURSE_ID in .env, S1 first)")
    ap.add_argument("--into", default="",
                    help="destination course id (default: the first course)")
    ap.add_argument("--undo", action="store_true",
                    help="send the cross-listed sections back to their original courses "
                         "(plan by default; add --apply to write)")
    ap.add_argument("--apply", action="store_true",
                    help="write the change (default is a read-only plan)")
    ap.add_argument("--yes", action="store_true",
                    help="apply without the interactive APPLY prompt. Only for a caller that has "
                         "ALREADY shown this exact plan to the instructor and had them confirm it. "
                         "Never add it on your own judgment.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="write even though a course has enrolled students or is a Blueprint "
                         "child (the course guard refuses otherwise). Instructor's explicit say-so only.")
    args = ap.parse_args()

    if not (CANVAS_BASE_URL and CANVAS_BASE_URL != "https://" and CANVAS_API_TOKEN):
        print("ERROR: Missing env vars: CANVAS_BASE_URL and/or CANVAS_API_TOKEN")
        sys.exit(1)

    dest, sources = resolve_courses(args.courses, args.into)

    # Cross-listing changes BOTH sides (the destination gains sections, each source loses
    # them), so the guard runs on every course involved, in write mode only with --apply.
    mode = "write" if args.apply else "read"
    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=dest, mode=mode,
                  allow_override=args.allow_enrolled, label="cross-list destination")
    for src in sources:
        guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=src, mode=mode,
                      allow_override=args.allow_enrolled, label="cross-list source")

    plan = build_undo_plan(dest, sources) if args.undo else build_plan(dest, sources)
    todo = print_plan(dest, plan, undo=args.undo)

    if not args.apply:
        print("\nREAD-ONLY: nothing written. Re-run with --apply to write.")
        return
    if todo == 0:
        print("\nNothing to apply.")
        return

    if args.undo:
        print(f"\n--apply will send {todo} section(s) out of course {dest} back to "
              f"{', '.join(sources)}.")
    else:
        print(f"\n--apply will cross-list {todo} section(s) into course {dest} "
              f"(from {', '.join(sources)}).")
    if args.yes:
        print("--yes: the caller confirmed this plan with the instructor; not prompting.")
        confirm = "APPLY"
    else:
        try:
            confirm = input('Type "APPLY" to proceed: ').strip()
        except (EOFError, KeyboardInterrupt):
            confirm = ""
    if confirm != "APPLY":
        print("Aborted — no changes written.")
        return
    if not (apply_undo if args.undo else apply_plan)(dest, plan):
        sys.exit(1)


if __name__ == "__main__":
    main()

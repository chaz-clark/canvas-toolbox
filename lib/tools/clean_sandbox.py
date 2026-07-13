#!/usr/bin/env python3
"""
clean_sandbox.py — empty the test sandbox (CANVAS_SANDBOX_EMPTY_ID) by deleting
its content item-by-item. DESTRUCTIVE.

Canvas content imports are additive (merge-only), so an import-test sandbox
accumulates cruft — e.g. `Test Sandbox` (427952) grew **61 duplicate
"Assignments" groups** + 100+ pages/modules from prior import tests. This resets
it to empty so it's a reusable clean fixture:
    clean_sandbox --yes  ->  import a cartridge  ->  verify  ->  clean_sandbox --yes

WHY item-by-item (not reset_content): Canvas's native `reset_content` needs an
account-admin permission BYUI does not grant instructor tokens (it 403s). A
teacher CAN delete their own course's content, which empties it just the same
and — better — keeps the SAME course id (no id rotation, no .env rewrite).

Deletion order matters: assignments before assignment_groups (deleting a group
cascades to its assignments, which is slow and can time out). Re-runnable — a
re-run just deletes whatever is left.

SAFETY (this wipes a whole course):
  - Targets ONLY `CANVAS_SANDBOX_EMPTY_ID`. Refuses if it equals
    `CANVAS_SANDBOX_ID` or is unset — the read/audit sandbox is never wiped here.
  - HARD refuse if the course has ANY enrolled students (no override).
  - Advisory: warns if the course name doesn't contain "sandbox".
  - Dry-run by default; requires `--yes` to actually delete.

Usage:
  uv run python canvas_toolbox/lib/tools/clean_sandbox.py          # dry-run (shows plan)
  uv run python canvas_toolbox/lib/tools/clean_sandbox.py --yes    # empty it

Exit codes: 0 ok / dry-run · 2 guard refusal / config error
"""
from __future__ import annotations

import argparse
import os
import sys

import requests
from dotenv import load_dotenv

from _canvas_mode import check_mode_requirements

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw and not _raw.startswith("http"):
    _raw = "https://" + _raw
CANVAS_BASE_URL = _raw
_TIMEOUT = 30
_DEL_TIMEOUT = 90  # deletes can cascade (e.g. a module / group) and run slow

# (label, list_path, id_field, delete_path_template, delete_params, base_override)
# Order matters: assignments before assignment_groups (group delete cascades).
_SPECS = [
    ("assignments", "assignments", "id", "courses/{cid}/assignments/{id}", {}),
    ("quizzes", "quizzes", "id", "courses/{cid}/quizzes/{id}", {}),
    ("discussions", "discussion_topics", "id", "courses/{cid}/discussion_topics/{id}", {}),
    ("pages", "pages", "url", "courses/{cid}/pages/{id}", {}),
    ("modules", "modules", "id", "courses/{cid}/modules/{id}", {}),
    ("files", "files", "id", "files/{id}", {}),
    ("rubrics", "rubrics", "id", "courses/{cid}/rubrics/{id}", {}),
    ("assignment_groups", "assignment_groups", "id", "courses/{cid}/assignment_groups/{id}", {"event": "delete"}),
]


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _list_first(course_id: str, list_path: str, per_page: int = 100):
    r = requests.get(f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/{list_path}",
                     headers=_headers(), params={"per_page": per_page}, timeout=_TIMEOUT)
    if r.status_code >= 400:
        return None, False
    items = r.json() if r.content else []
    return items, ('rel="next"' in r.headers.get("Link", ""))


def _count(course_id: str, list_path: str) -> str:
    items, more = _list_first(course_id, list_path)
    if items is None:
        return "err"
    return f"{len(items)}{'+' if more else ''}"


def _delete_all(course_id: str, spec) -> tuple[int, int]:
    """Delete every item of a content type (paginate-by-refetch). (deleted, failed)."""
    label, list_path, id_field, del_tmpl, del_params = spec
    deleted = failed = 0
    while True:
        items, _ = _list_first(course_id, list_path)
        if not items:
            break
        progressed = False
        for it in items:
            ident = it.get(id_field)
            if ident is None:
                failed += 1
                continue
            url = f"{CANVAS_BASE_URL}/api/v1/" + del_tmpl.format(cid=course_id, id=ident)
            try:
                d = requests.delete(url, headers=_headers(), params=del_params, timeout=_DEL_TIMEOUT)
                if d.status_code < 300:
                    deleted += 1
                    progressed = True
                else:
                    failed += 1
            except requests.RequestException:
                failed += 1
        if not progressed:  # everything on this page failed — stop rather than loop forever
            break
        print(f"   {label}: {deleted} deleted{f', {failed} failed' if failed else ''}…", flush=True)
    return deleted, failed


def _clear_outcomes(course_id: str) -> tuple[int, int]:
    """Unlink every outcome from the course's outcome groups."""
    deleted = failed = 0
    while True:
        r = requests.get(f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/outcome_group_links",
                         headers=_headers(), params={"per_page": 100}, timeout=_TIMEOUT)
        if r.status_code >= 400:
            break
        links = r.json() if r.content else []
        if not links:
            break
        progressed = False
        for ln in links:
            og = (ln.get("outcome_group") or {}).get("id")
            oc = (ln.get("outcome") or {}).get("id")
            if not (og and oc):
                failed += 1
                continue
            d = requests.delete(
                f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/outcome_groups/{og}/outcomes/{oc}",
                headers=_headers(), timeout=_DEL_TIMEOUT)
            if d.status_code < 300:
                deleted += 1
                progressed = True
            else:
                failed += 1
        if not progressed:
            break
    return deleted, failed


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description="Empty the test sandbox (CANVAS_SANDBOX_EMPTY_ID). DESTRUCTIVE.")
    ap.add_argument("--yes", action="store_true", help="Actually delete (default: dry-run)")
    args = ap.parse_args()

    try:
        check_mode_requirements()
    except ValueError as e:
        print(f"⛔ {e}", file=sys.stderr)
        return 2

    empty_id = (os.environ.get("CANVAS_SANDBOX_EMPTY_ID") or "").strip()
    full_id = (os.environ.get("CANVAS_SANDBOX_ID") or "").strip()
    if not empty_id:
        print("⛔ CANVAS_SANDBOX_EMPTY_ID is not set. This tool only ever empties that course.", file=sys.stderr)
        return 2
    if empty_id == full_id:
        print(f"⛔ CANVAS_SANDBOX_EMPTY_ID ({empty_id}) equals CANVAS_SANDBOX_ID — refusing, "
              "so the read/audit sandbox is never wiped.", file=sys.stderr)
        return 2

    c = requests.get(f"{CANVAS_BASE_URL}/api/v1/courses/{empty_id}",
                     headers=_headers(), params={"include[]": "total_students"}, timeout=_TIMEOUT)
    if c.status_code >= 400:
        print(f"⛔ GET /courses/{empty_id} -> {c.status_code}: {c.text[:150]}", file=sys.stderr)
        return 2
    course = c.json()
    name = course.get("name") or "<unknown>"
    students = course.get("total_students")
    if isinstance(students, int) and students > 0:
        print(f"🔴 REFUSING: sandbox {empty_id} ('{name}') has {students} enrolled student(s).", file=sys.stderr)
        return 2

    print(f"🧹 Target: {empty_id} '{name}'  students={students}  workflow={course.get('workflow_state')}")
    if "sandbox" not in name.lower():
        print("   ⚠️  advisory: course name has no 'sandbox' in it — double-check this is the throwaway course.")
    print("   current content:", ", ".join(f"{label}={_count(empty_id, lp)}" for label, lp, *_ in _SPECS),
          f", outcomes={_count(empty_id, 'outcome_group_links')}")

    if not args.yes:
        print("\nDRY RUN — would delete ALL of the above (assignments first, then groups; outcomes unlinked). "
              "Course id stays the same. Re-run with --yes to do it.")
        return 0

    print("\nDeleting…")
    tot_del = tot_fail = 0
    for spec in _SPECS:
        d, f = _delete_all(empty_id, spec)
        tot_del += d
        tot_fail += f
    od, of = _clear_outcomes(empty_id)
    tot_del += od
    tot_fail += of
    print(f"\n✅ Emptied {empty_id} '{name}': {tot_del} items deleted"
          + (f", {tot_fail} failed (re-run to retry)" if tot_fail else "") + ".")
    print("   remaining:", ", ".join(f"{label}={_count(empty_id, lp)}" for label, lp, *_ in _SPECS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

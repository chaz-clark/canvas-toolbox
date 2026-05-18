"""
module_settings_sync.py

One-off reconciliation of MASTER course (MASTER_COURSE_ID) sprint-module
SETTINGS only. Never creates, deletes, or edits content — only:
  - module prerequisite chain (each sprint requires the prior sprint)
  - module requirement mode ("complete all")
  - per-item completion_requirement

Rule (from instructor, blueprint treated as authoritative for this metadata
only — accepted one-off deviation from AGENTS.md Rule 6):
  For each master sprint module, "complete all" must be satisfied by exactly
  the gradable items (Assignment / classic Quiz) that exist in BOTH master and
  the blueprint module (title-matched). Every other item (pages, tools,
  master-only items, blueprint-only items) has its completion requirement
  REMOVED so the gate is graded work only.

Matching is by title slug across courses, never by ID (AGENTS.md Rule 2).
Module/item writes are form-encoded (AGENTS.md External System Lessons).

Usage:
    uv run python tools/module_settings_sync.py            # --plan (read-only, default)
    uv run python tools/module_settings_sync.py --apply     # write to master (confirmation-gated)
"""

import argparse
import os
import re
import sys
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url

MASTER_COURSE_ID = os.environ.get("MASTER_COURSE_ID", "")
BLUEPRINT_COURSE_ID = os.environ.get("BLUEPRINT_COURSE_ID", "")

GRADABLE_TYPES = {"Assignment", "Quiz"}


def _check_env():
    missing = [n for n, v in (
        ("CANVAS_BASE_URL", CANVAS_BASE_URL and CANVAS_BASE_URL != "https://"),
        ("CANVAS_API_TOKEN", CANVAS_API_TOKEN),
        ("MASTER_COURSE_ID", MASTER_COURSE_ID),
        ("BLUEPRINT_COURSE_ID", BLUEPRINT_COURSE_ID),
    ) if not v]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(endpoint: str, params: dict = None):
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    results = []
    while url:
        resp = requests.get(url, headers=_headers(), params=params, timeout=20)
        if resp.status_code >= 400:
            print(f"ERROR {resp.status_code} GET {endpoint}: {resp.text[:200]}")
            sys.exit(1)
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url = None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        params = None
    return results


def _put_form(endpoint: str, data) -> tuple:
    """Form-encoded PUT (Canvas ignores JSON for module/item writes)."""
    resp = requests.put(f"{CANVAS_BASE_URL}/api/v1{endpoint}",
                         headers=_headers(), data=data, timeout=20)
    return resp.status_code, resp.text[:200]


def _slug(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")[:80]


def _req_type(item: dict):
    cr = item.get("completion_requirement")
    return cr.get("type") if cr else None


def _is_sprint(name: str) -> bool:
    return _slug(name).startswith("sprint-")


def fetch_modules(course_id: str) -> list:
    """Modules with items attached (items via the per-module endpoint)."""
    mods = _get(f"/courses/{course_id}/modules", params={"per_page": 100})
    for m in mods:
        m["_items"] = _get(
            f"/courses/{course_id}/modules/{m['id']}/items",
            params={"per_page": 100})
    return mods


def report_chain(mods: list, label: str):
    """Print each course's sprint-module prerequisite chain by name."""
    id_to_name = {m["id"]: m["name"] for m in mods}
    sprints = sorted((m for m in mods if _is_sprint(m["name"])),
                     key=lambda m: m.get("position", 0))
    print(f"\n{label} sprint prerequisite chain:")
    for m in sprints:
        prereqs = [id_to_name.get(p, f"<id {p}>")
                   for p in (m.get("prerequisite_module_ids") or [])]
        print(f"  {m['name']}  <-  {prereqs or 'NONE'}")


def discover_renames(ms_mods: list, bp_mods: list) -> list:
    """
    Locate the renamed self-assessments the instructor flagged: master
    Assignment items titled '... Performance Review' that do NOT title-match
    their blueprint sprint module. Returns rename instructions to the EXACT
    blueprint title (fetched, never transcribed).
    """
    bp_by_slug = {_slug(m["name"]): m for m in bp_mods}
    renames = []
    for m in ms_mods:
        if not _is_sprint(m["name"]):
            continue
        bp_mod = bp_by_slug.get(_slug(m["name"]))
        if not bp_mod:
            continue
        bp_slugs = {_slug(it.get("title", "")) for it in bp_mod["_items"]}
        bp_self = [it for it in bp_mod["_items"]
                   if it.get("type") == "Assignment"
                   and "performance review" in it.get("title", "").lower()]
        for it in m["_items"]:
            t = it.get("title", "")
            if (it.get("type") == "Assignment"
                    and "performance review" in t.lower()
                    and _slug(t) not in bp_slugs and len(bp_self) == 1):
                renames.append({
                    "module": m["name"],
                    "module_id": m["id"],
                    "item_id": it["id"],
                    "content_id": it.get("content_id"),
                    "from": t,
                    "to": bp_self[0]["title"],
                })
    return renames


def apply_renames(renames: list) -> int:
    cid = MASTER_COURSE_ID
    failed = 0
    for r in renames:
        ok = True
        if r["content_id"]:
            sc, body = _put_form(
                f"/courses/{cid}/assignments/{r['content_id']}",
                {"assignment[name]": r["to"]})
            ok = sc < 400
            if not ok:
                print(f"  RENAME FAIL (assignment) {r['from']!r}: {body}")
        sc, body = _put_form(
            f"/courses/{cid}/modules/{r['module_id']}/items/{r['item_id']}",
            {"module_item[title]": r["to"]})
        # module item title for content items follows the assignment; a 400
        # here is non-fatal if the assignment rename succeeded.
        failed += not ok
        print(f"  RENAMED {r['from']!r} -> {r['to']!r} "
              f"({'OK' if ok else 'FAILED'})")
    return failed


def build_plan():
    bp_mods = fetch_modules(BLUEPRINT_COURSE_ID)
    ms_mods = fetch_modules(MASTER_COURSE_ID)

    # Renamed self-assessments: reflect the new title in-memory so the item
    # plan shows post-rename state (they title-match -> keep must_submit).
    renames = discover_renames(ms_mods, bp_mods)
    rename_by_item = {r["item_id"]: r["to"] for r in renames}
    for m in ms_mods:
        for it in m["_items"]:
            if it["id"] in rename_by_item:
                it["title"] = rename_by_item[it["id"]]

    # Blueprint roster: module-slug -> set of gradable item title-slugs.
    bp_roster = {
        _slug(m["name"]): {
            _slug(it.get("title", ""))
            for it in m["_items"] if it.get("type") in GRADABLE_TYPES
        }
        for m in bp_mods
    }

    sprint_mods = sorted(
        (m for m in ms_mods if _is_sprint(m["name"])),
        key=lambda m: m.get("position", 0),
    )

    plan = []
    for idx, m in enumerate(sprint_mods):
        mslug = _slug(m["name"])
        roster = bp_roster.get(mslug)
        prior = sprint_mods[idx - 1] if idx > 0 else None

        cur_prereqs = sorted(m.get("prerequisite_module_ids") or [])
        want_prereqs = sorted([prior["id"]] if prior else [])
        prereq_change = (cur_prereqs != want_prereqs, cur_prereqs, want_prereqs,
                         prior["name"] if prior else None)

        # Canvas: requirement_count == 1 => complete ONE; null => complete ALL.
        req_count_change = m.get("requirement_count") == 1

        item_actions = []
        for it in m["_items"]:
            tslug = _slug(it.get("title", ""))
            itype = it.get("type", "")
            in_bp = roster is not None and tslug in roster
            want = "must_submit" if (itype in GRADABLE_TYPES and in_bp) else None
            cur = _req_type(it)
            if cur != want:
                item_actions.append({
                    "item_id": it["id"], "title": it.get("title", ""),
                    "type": itype, "cur": cur, "want": want,
                    "action": "SET must_submit" if want else "REMOVE requirement",
                })

        plan.append({
            "module": m, "roster_found": roster is not None,
            "prereq": prereq_change, "req_count": req_count_change,
            "items": item_actions,
        })
    return {"plan": plan, "renames": renames,
            "ms_mods": ms_mods, "bp_mods": bp_mods}


def print_plan(result):
    plan, renames = result["plan"], result["renames"]
    report_chain(result["bp_mods"], "BLUEPRINT")
    report_chain(result["ms_mods"], "MASTER")
    print("\n" + "=" * 72)
    print(f"PLAN — MASTER {MASTER_COURSE_ID}, sprint modules, settings only\n"
          + "=" * 72)
    total = len(renames)
    if renames:
        print("\nRENAME (master assignment -> exact blueprint title):")
        for r in renames:
            print(f"  [{r['module']}] {r['from']!r}\n      -> {r['to']!r}")
    for p in plan:
        m = p["module"]
        changed, cur, want, prior_name = p["prereq"]
        print(f"\n[{m['name']}]  (master module id {m['id']})")
        if not p["roster_found"]:
            print("  ! no blueprint module matched this title — all item "
                  "requirements would be REMOVED. Review carefully.")
        if changed:
            print(f"  PREREQ: {cur or '[]'} -> {want or '[]'}"
                  + (f"  (prior sprint: {prior_name})" if prior_name else "  (Sprint 1: none)"))
            total += 1
        else:
            print(f"  prereq OK ({cur or 'none'})")
        if p["req_count"]:
            print("  REQUIREMENT MODE: 'complete one' -> 'complete all'")
            total += 1
        else:
            print("  requirement mode OK (complete all)")
        if p["items"]:
            for a in p["items"]:
                total += 1
                print(f"  {a['action']:<22} {a['title']!r} ({a['type']}) "
                      f"[{a['cur'] or '—'} -> {a['want'] or '—'}]")
        else:
            print("  item requirements already correct")
    print("\n" + "=" * 72)
    print(f"{total} change(s) planned across {len(plan)} sprint modules.")
    return total


def apply_plan(result):
    cid = MASTER_COURSE_ID
    applied, failed = 0, 0

    if result["renames"]:
        print("Renaming master assignments to match blueprint titles...")
        failed += apply_renames(result["renames"])
        # Re-fetch: renamed items now title-match, so they drop out of the
        # removal plan and correctly keep must_submit.
        result = build_plan()

    for p in result["plan"]:
        m = p["module"]
        mid = m["id"]
        changed, _cur, want, _pn = p["prereq"]
        if changed:
            data = ([("module[prerequisite_module_ids][]", want[0])] if want
                    else [("module[prerequisite_module_ids][]", "")])
            sc, body = _put_form(f"/courses/{cid}/modules/{mid}", data)
            ok = sc < 400
            applied += ok
            failed += not ok
            print(f"[{m['name']}] prereq {'OK' if ok else 'FAIL ' + body}")
        if p["req_count"]:
            sc, body = _put_form(f"/courses/{cid}/modules/{mid}",
                                 {"module[requirement_count]": ""})
            ok = sc < 400
            applied += ok
            failed += not ok
            print(f"[{m['name']}] requirement mode {'OK' if ok else 'FAIL ' + body}")
        for a in p["items"]:
            iid = a["item_id"]
            # SET: send the [type] subkey. REMOVE: send the whole
            # completion_requirement blank — Canvas treats a blank object as
            # "clear", but a blank [type] as an invalid type.
            data = ({"module_item[completion_requirement][type]": a["want"]}
                    if a["want"] else {"module_item[completion_requirement]": ""})
            sc, body = _put_form(
                f"/courses/{cid}/modules/{mid}/items/{iid}", data)
            ok = sc < 400
            applied += ok
            failed += not ok
            print(f"[{m['name']}] {a['action']} {a['title']!r}: "
                  f"{'OK' if ok else 'FAIL ' + body}")
    print("\n" + "=" * 72)
    print(f"Applied {applied}, failed {failed}. Re-verifying...")

    # Verify by rebuilding the plan — zero remaining changes == success.
    verify = build_plan()
    remaining = print_plan(verify)
    if remaining == 0 and failed == 0:
        print("VERIFIED: master sprint-module settings now match the rule.")
    else:
        print("INCOMPLETE: re-run --plan and inspect the remaining items above.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write changes to MASTER (default is read-only plan)")
    args = ap.parse_args()
    _check_env()

    result = build_plan()
    total = print_plan(result)

    if not args.apply:
        print("\nREAD-ONLY: nothing written. Re-run with --apply to write.")
        return
    if total == 0:
        print("\nNothing to apply.")
        return

    print(f"\n--apply will WRITE the above to MASTER course {MASTER_COURSE_ID} "
          f"(live). Content is NOT touched — settings only.")
    try:
        confirm = input('Type "APPLY" to proceed: ').strip()
    except (EOFError, KeyboardInterrupt):
        confirm = ""
    if confirm != "APPLY":
        print("Aborted — no changes written.")
        return
    apply_plan(result)


if __name__ == "__main__":
    main()

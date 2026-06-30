"""
course_mirror.py  —  ONE-OFF UTILITY

Push content from the local course/ folder (sourced from CANVAS_COURSE_ID)
into a second Canvas course (MASTER_COURSE_ID), making it a mirror.

This is the reverse of what blueprint_sync does for the Blueprint, applied to
a regular course. Same title-based matching, same content push (body, dates,
points, published state), same module structure sync (published, prerequisites).

Usage:
    uv run python tools/course_mirror.py --pull    # map MASTER_COURSE_ID item IDs
    uv run python tools/course_mirror.py --status  # show coverage
    uv run python tools/course_mirror.py --push    # push course/ → MASTER_COURSE_ID

Env vars required:
    CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID (source), MASTER_COURSE_ID (target)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from canvas_pages import page_in_module, upsert_page
from __toolbox_version__ import __version__
from canvas_course_guard import enforce as _course_guard

try:
    from _env_loader import load_env, force_utf8_console
    load_env()
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
BASE = ("https://" + _raw) if _raw and not _raw.startswith("http") else _raw
SOURCE_ID = os.environ.get("CANVAS_COURSE_ID", "")
TARGET_ID = os.environ.get("MASTER_COURSE_ID", "")

COURSE_DIR = Path("course")
MASTER_INDEX = Path(".canvas/index.json")
MIRROR_INDEX = Path(".canvas/master_mirror_index.json")

NO_PUSH_TYPES = {"NewQuiz", "ExternalTool", "ExternalUrl", "ContextModuleSubHeader", "SubHeader"}


def _check_env():
    missing = [v for v in ("CANVAS_API_TOKEN", "CANVAS_BASE_URL", "CANVAS_COURSE_ID", "MASTER_COURSE_ID")
               if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _h():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _get(endpoint, params=None):
    url = f"{BASE}/api/v1{endpoint}"
    results = []
    while url:
        r = requests.get(url, headers=_h(), params=params, timeout=20)
        if r.status_code >= 400:
            return None
        data = r.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        params = None
    return results


def _put(endpoint, payload):
    r = requests.put(f"{BASE}/api/v1{endpoint}", headers=_h(), json=payload, timeout=20)
    if r.status_code >= 400:
        return {"error": r.text[:300]}
    try:
        return r.json() or {"ok": True}
    except Exception:
        return {"ok": True}


def _slug(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")[:80]


def _load(path):
    return json.loads(path.read_text()) if path.exists() else {}


def _confirm_module_match(master_title: str, candidates: list, context: str = "") -> dict | None:
    """
    Exact-match-first module resolver with user confirmation for ambiguous cases.

    - If exactly one exact slug match: return it silently.
    - If duplicate exact matches (same slug, multiple modules): print warning, require user to pick.
    - If no exact match: print candidates (if any), SKIP — never auto-apply fuzzy match.
    - Returns the matched module dict or None (skip).
    """
    master_slug = _slug(master_title)
    exact = [m for m in candidates if _slug(m.get("name", "")) == master_slug]

    if len(exact) == 1:
        return exact[0]

    if len(exact) > 1:
        print(f"\n  WARNING: {len(exact)} modules in target share the same slug for '{master_title}':")
        for i, m in enumerate(exact):
            print(f"    [{i}] id={m['id']}  name={repr(m['name'])}")
        print(f"  {context}")
        try:
            choice = input(f"  Enter index to use (or ENTER to skip): ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = ""
        if choice.isdigit() and int(choice) < len(exact):
            return exact[int(choice)]
        print(f"  SKIPPED: '{master_title}' (ambiguous, no selection made)")
        return None

    # No exact match — never silently fuzzy-match
    print(f"  SKIP module '{master_title}': no exact match in target (slug='{master_slug}')")
    return None


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Pull: map MASTER_COURSE_ID item IDs by title-matching against course/
# ---------------------------------------------------------------------------

def cmd_pull():
    _check_env()
    master_index = _load(MASTER_INDEX)
    if not master_index.get("files"):
        print("ERROR: Master index empty. Run 'canvas_sync.py --pull' first.")
        sys.exit(1)

    print(f"Pulling target course {TARGET_ID} from {BASE}...\n")

    # title → (filepath, meta) from local index
    local_by_title = {}
    for fp, meta in master_index.get("files", {}).items():
        t = (meta.get("title") or "").strip().lower()
        if t:
            local_by_title[t] = (fp, meta)

    mirror = {
        "source_course_id": SOURCE_ID,
        "target_course_id": TARGET_ID,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "homepage": None,
        "mappings": {},
        "unmapped_local": [],
        "unmapped_target": [],
    }

    # Homepage
    hp = _get(f"/courses/{TARGET_ID}/front_page")
    if hp and not hp.get("errors"):
        mirror["homepage"] = {"page_url": hp.get("url", "front-page"), "title": hp.get("title", "")}
        print(f"  [homepage] {hp.get('url', 'front-page')}")

    # Modules + items
    modules = _get(f"/courses/{TARGET_ID}/modules", params={"per_page": 50, "include[]": "items"})
    if not modules:
        print("ERROR: Could not fetch target modules. Check MASTER_COURSE_ID.")
        sys.exit(1)
    print(f"  {len(modules)} modules, {sum(len(m.get('items',[])) for m in modules)} items")

    # Warn if target has duplicate module names — this will break matching
    from collections import Counter
    mod_name_counts = Counter(_slug(m.get("name", "")) for m in modules)
    dup_mods = [name for name, count in mod_name_counts.items() if count > 1]
    if dup_mods:
        print(f"\n  WARNING: Target course has {len(dup_mods)} duplicate module name(s):")
        for slug in dup_mods:
            names = [m.get("name") for m in modules if _slug(m.get("name", "")) == slug]
            print(f"    '{slug}' appears {len(names)}x")
        print(f"\n  This will cause ambiguous matching. Clean up duplicate modules in Canvas")
        print(f"  before running --push, or --push will skip ambiguous modules.\n")

    matched = 0
    for mod in modules:
        for item in mod.get("items", []):
            title = item.get("title", "")
            key = title.strip().lower()
            local = local_by_title.get(key)
            if local:
                fp, meta = local
                mirror["mappings"][fp] = {
                    "target_canvas_id": item.get("content_id"),
                    "target_page_url": item.get("page_url"),
                    "target_module_id": mod.get("id"),
                    "type": meta.get("type", item.get("type")),
                    "title": title,
                    "module": mod.get("name", ""),
                }
                matched += 1
            else:
                mirror["unmapped_target"].append(title)

    for fp in master_index.get("files", {}):
        if fp not in mirror["mappings"]:
            mirror["unmapped_local"].append(fp)

    _save(MIRROR_INDEX, mirror)

    print(f"\nPull complete.")
    print(f"  {matched} local items mapped to target canvas IDs")
    print(f"  {len(mirror['unmapped_local'])} local items not found in target")
    print(f"  {len(mirror['unmapped_target'])} target items not matched to local")
    unmapped_pushable = [fp for fp in mirror["unmapped_local"]
                         if _load(MASTER_INDEX)["files"].get(fp, {}).get("type") not in NO_PUSH_TYPES
                         and _load(MASTER_INDEX)["files"].get(fp, {}).get("type") != "NewQuiz"]
    if unmapped_pushable:
        print(f"\n  Unmapped pushable local items:")
        for fp in unmapped_pushable:
            t = master_index["files"].get(fp, {}).get("type", "?")
            print(f"    [{t}] {fp}")
    print(f"\n  Mapping → {MIRROR_INDEX}")
    print(f"  Run --status then --push.")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def cmd_status():
    master_index = _load(MASTER_INDEX)
    mirror = _load(MIRROR_INDEX)
    if not master_index.get("files"):
        print("Master index not found. Run 'canvas_sync.py --pull' first.")
        return
    if not mirror.get("mappings"):
        print("Mirror mapping not found. Run 'course_mirror.py --pull' first.")
        return

    mappings = mirror["mappings"]
    total = len(master_index["files"])
    mapped = sum(1 for fp in master_index["files"] if fp in mappings)
    pushable_types = {"Page", "Assignment", "Discussion", "Quiz"}
    pushable = sum(1 for fp, meta in master_index["files"].items()
                   if fp in mappings and meta.get("type") in pushable_types)

    print(f"Course mirror status")
    print(f"  Source: course {mirror.get('source_course_id')} (local course/)")
    print(f"  Target: course {mirror.get('target_course_id')}")
    print(f"  Last pull:  {mirror.get('pulled_at', 'never')}")
    print(f"  Local items:     {total}")
    print(f"  Mapped:          {mapped}")
    print(f"  Will push:       {pushable} (Page/Assignment/Discussion/Quiz)")
    print(f"  Skipped (no API):{mapped - pushable}")
    print(f"  Unmapped:        {total - mapped}")

    if mirror.get("unmapped_local"):
        pushable_unmapped = [fp for fp in mirror["unmapped_local"]
                             if master_index["files"].get(fp, {}).get("type") not in NO_PUSH_TYPES
                             and master_index["files"].get(fp, {}).get("type") != "NewQuiz"]
        if pushable_unmapped:
            print(f"\n  Unmapped pushable (will be created new on --push):")
            for fp in pushable_unmapped:
                t = master_index["files"].get(fp, {}).get("type", "?")
                print(f"    [{t}] {fp}")


# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------

def cmd_push():
    _check_env()
    master_index = _load(MASTER_INDEX)
    mirror = _load(MIRROR_INDEX)
    if not master_index.get("files"):
        print("ERROR: Master index empty.")
        sys.exit(1)
    if not mirror.get("mappings"):
        print("ERROR: Mirror mapping empty. Run --pull first.")
        sys.exit(1)

    target = TARGET_ID
    mappings = mirror["mappings"]
    pushed_files = []
    pushed = skipped = failed = 0

    print(f"Mirroring course/ → target course {target}...\n")

    # -----------------------------------------------------------------------
    # 1. Course settings
    # -----------------------------------------------------------------------
    master_course = _load(COURSE_DIR / "_course.json")
    if master_course:
        gs_id = master_course.get("grading_standard_id")
        if gs_id:
            print("  [Settings] grading_standard")
            r = _put(f"/courses/{target}", {"course": {"grading_standard_id": gs_id}})
            if r.get("error"):
                print(f"    FAILED: {r['error']}")
                failed += 1
            else:
                print(f"    OK")
                pushed_files.append("settings/grading_standard")

        print("  [Settings] show_announcements_on_home_page → false")
        r2 = requests.put(f"{BASE}/api/v1/courses/{target}", headers=_h(),
                          json={"course": {"show_announcements_on_home_page": False}}, timeout=20)
        if r2.status_code < 400:
            print(f"    OK")
        else:
            print(f"    FAILED: {r2.text[:150]}")
            failed += 1

    # -----------------------------------------------------------------------
    # 2. Homepage
    # -----------------------------------------------------------------------
    master_hp = master_index.get("homepage")
    target_hp = mirror.get("homepage")
    if master_hp and target_hp:
        hp_path = Path(master_hp["filepath"])
        if hp_path.exists():
            print(f"  [Homepage] {hp_path.name}")
            body = hp_path.read_text(encoding="utf-8")
            page_url = target_hp.get("page_url", "front-page")
            r = requests.put(f"{BASE}/api/v1/courses/{target}/pages/{page_url}",
                             headers=_h(), json={"wiki_page": {"body": body}}, timeout=20)
            if r.status_code < 400:
                print(f"    OK")
                pushed += 1
                pushed_files.append("homepage.html")
            else:
                print(f"    FAILED: {r.text[:200]}")
                failed += 1

    # -----------------------------------------------------------------------
    # 3. Syllabus
    # -----------------------------------------------------------------------
    master_syl = master_index.get("syllabus")
    if master_syl:
        syl_path = Path(master_syl["filepath"])
        if syl_path.exists():
            print(f"  [Syllabus] syllabus.html")
            body = syl_path.read_text(encoding="utf-8")
            r = requests.put(f"{BASE}/api/v1/courses/{target}", headers=_h(),
                             json={"course": {"syllabus_body": body}}, timeout=20)
            if r.status_code < 400:
                print(f"    OK")
                pushed += 1
                pushed_files.append("syllabus.html")
            else:
                print(f"    FAILED: {r.text[:200]}")
                failed += 1

    # -----------------------------------------------------------------------
    # 4. Module items
    # -----------------------------------------------------------------------
    # Fetch target modules for new-page creation
    target_mods = _get(f"/courses/{target}/modules", params={"per_page": 50}) or []
    target_mods_by_slug = {_slug(m.get("name", "")): m.get("id") for m in target_mods}

    for local_fp, local_meta in master_index.get("files", {}).items():
        bp_meta = mappings.get(local_fp)
        local_path = Path(local_fp)
        if not local_path.exists():
            skipped += 1
            continue

        item_type = local_meta.get("type")

        if not bp_meta:
            if item_type in NO_PUSH_TYPES or item_type in ("NewQuiz", "Assignment", "Discussion", "Quiz"):
                skipped += 1
                continue
            if item_type == "Page":
                title = local_meta.get("title") or local_path.stem.replace("-", " ").title()
                mod_slug = local_meta.get("module_slug", "")
                # Exact match only — no fuzzy
                tgt_mod_id = target_mods_by_slug.get(mod_slug)
                if not tgt_mod_id:
                    print(f"  [Page] NEW {local_fp}")
                    print(f"    SKIP: no exact module match for slug '{mod_slug}'")
                    skipped += 1
                    continue
                print(f"  [Page] NEW {local_fp}")
                body = local_path.read_text(encoding="utf-8")
                published = local_meta.get("published", True)
                # Idempotent upsert (issue #26): reuse an existing same-title
                # target page instead of POSTing a duplicate every run.
                page_url, action = upsert_page(
                    BASE, _h(), target, title, body, published
                )
                if action == "ambiguous":
                    print(f"    SKIP: >1 target page already titled '{title}' — "
                          f"manual review (corrupted state; see #23/#26)")
                    skipped += 1
                    continue
                if action.startswith("error"):
                    print(f"    FAILED upsert: {action[6:]}")
                    failed += 1
                    continue
                # Module-item guard (#26): don't re-link a page already in the module.
                if page_in_module(BASE, _h(), target, tgt_mod_id, page_url):
                    print(f"    {action.upper()} → {page_url} (already in module; not re-added)")
                    pushed += 1
                    pushed_files.append(local_fp)
                    continue
                r2 = requests.post(f"{BASE}/api/v1/courses/{target}/modules/{tgt_mod_id}/items",
                                   headers=_h(),
                                   json={"module_item": {"type": "Page", "page_url": page_url, "position": 1}},
                                   timeout=20)
                if r2.status_code < 400:
                    print(f"    {action.upper()} → {page_url} (linked to module)")
                else:
                    print(f"    {action} page but failed to add to module: {r2.text[:100]}")
                pushed += 1
                pushed_files.append(local_fp)
            else:
                skipped += 1
            continue

        tgt_canvas_id = bp_meta.get("target_canvas_id")
        tgt_page_url = bp_meta.get("target_page_url")

        if item_type in NO_PUSH_TYPES:
            skipped += 1
            continue

        print(f"  [{item_type}] {local_fp}")
        ok = False

        if item_type == "Page" and tgt_page_url:
            body = local_path.read_text(encoding="utf-8")
            r = _put(f"/courses/{target}/pages/{tgt_page_url}", {
                "wiki_page": {"body": body, "published": local_meta.get("published", True)}
            })
            ok = not r.get("error")
            if not ok:
                print(f"    FAILED: {r.get('error')}")

        elif item_type == "Assignment" and tgt_canvas_id:
            data = json.loads(local_path.read_text())
            r = _put(f"/courses/{target}/assignments/{tgt_canvas_id}", {
                "assignment": {
                    "description": data.get("description", ""),
                    "points_possible": data.get("points_possible"),
                    "published": data.get("published", True),
                    "due_at": data.get("due_at"),
                    "lock_at": data.get("lock_at"),
                    "unlock_at": data.get("unlock_at"),
                }
            })
            ok = not r.get("error")
            if not ok:
                print(f"    FAILED: {r.get('error')}")

        elif item_type == "Discussion" and tgt_canvas_id:
            data = json.loads(local_path.read_text())
            r = _put(f"/courses/{target}/discussion_topics/{tgt_canvas_id}", {
                "title": data.get("title", ""),
                "message": data.get("message", data.get("description", "")),
                "published": data.get("published", True),
                "delayed_post_at": data.get("unlock_at"),
                "lock_at": data.get("lock_at"),
            })
            ok = not r.get("error")
            if not ok:
                print(f"    FAILED: {r.get('error')}")

        elif item_type == "Quiz" and tgt_canvas_id:
            data = json.loads(local_path.read_text())
            r = _put(f"/courses/{target}/quizzes/{tgt_canvas_id}", {
                "quiz": {
                    "description": data.get("description", ""),
                    "due_at": data.get("due_at"),
                    "lock_at": data.get("lock_at"),
                    "unlock_at": data.get("unlock_at"),
                }
            })
            ok = not r.get("error")
            if not ok:
                print(f"    FAILED: {r.get('error')}")

        else:
            print(f"    SKIP: {item_type} (no canvas_id or unsupported)")
            skipped += 1
            continue

        if ok:
            print(f"    OK")
            pushed += 1
            pushed_files.append(local_fp)
        else:
            failed += 1

    # -----------------------------------------------------------------------
    # 5. Module structure: published state, prerequisites, item published/order
    # -----------------------------------------------------------------------
    print(f"\n  [Modules] syncing structure...")

    master_modules = []
    for mod_dir in sorted(COURSE_DIR.iterdir()):
        mf = mod_dir / "_module.json"
        if mf.exists():
            data = _load(mf)
            master_modules.append(data)
    master_modules.sort(key=lambda m: m.get("position", 999))

    # Map target modules by slug — used by `_confirm_module_match` below.
    target_mods_full = _get(f"/courses/{target}/modules", params={"per_page": 50, "include[]": "items"}) or []

    sprint_target_mod_ids = []
    for master_mod in master_modules:
        master_title = master_mod.get("title", "")
        master_slug = _slug(master_title)
        tgt_mod = _confirm_module_match(
            master_title, target_mods_full,
            context=f"Syncing published state + item order for this module."
        )
        if not tgt_mod:
            continue

        tgt_mod_id = tgt_mod.get("id")

        # Warn if all master module items are non-pushable — target module will end up empty
        master_items = master_mod.get("items", [])
        pushable_items = [it for it in master_items
                          if it.get("type") not in NO_PUSH_TYPES
                          and it.get("type") != "NewQuiz"]
        if master_items and not pushable_items:
            print(f"    WARNING: '{master_title}' has {len(master_items)} item(s) but none are pushable "
                  f"(all NewQuiz/ExternalTool) — module will be empty in target course")

        state = "active" if master_mod.get("published", True) else "unpublished"
        r = requests.put(
            f"{BASE}/api/v1/courses/{target}/modules/{tgt_mod_id}",
            headers={k: v for k, v in _h().items() if k != "Content-Type"},
            data={"module[workflow_state]": state},
            timeout=20,
        )
        ok = r.status_code < 400
        print(f"    {master_title}: published={master_mod.get('published', True)} → {'OK' if ok else 'FAILED'}")

        if "sprint" in master_slug or "project" in master_slug:
            sprint_target_mod_ids.append(tgt_mod_id)

        # Item published state + position
        tgt_items_by_title = {_slug(i.get("title", "")): i for i in tgt_mod.get("items", [])}
        for master_item in master_mod.get("items", []):
            item_title = master_item.get("title", "")
            tgt_item = tgt_items_by_title.get(_slug(item_title))
            if not tgt_item:
                continue
            tgt_item_id = tgt_item.get("id")
            payload = {}
            if master_item.get("published") != tgt_item.get("published"):
                payload["module_item[published]"] = str(master_item.get("published", True)).lower()
            if master_item.get("position") and master_item.get("position") != tgt_item.get("position"):
                payload["module_item[position]"] = master_item["position"]
            if payload:
                requests.put(
                    f"{BASE}/api/v1/courses/{target}/modules/{tgt_mod_id}/items/{tgt_item_id}",
                    headers={k: v for k, v in _h().items() if k != "Content-Type"},
                    data=payload,
                    timeout=20,
                )

    if len(sprint_target_mod_ids) > 1:
        print(f"    Prerequisites: chaining {len(sprint_target_mod_ids)} sprint modules...")
        for i in range(1, len(sprint_target_mod_ids)):
            requests.put(
                f"{BASE}/api/v1/courses/{target}/modules/{sprint_target_mod_ids[i]}",
                headers={k: v for k, v in _h().items() if k != "Content-Type"},
                data={"module[prerequisite_module_ids][]": sprint_target_mod_ids[i - 1]},
                timeout=20,
            )
        print(f"    Prerequisites: OK")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\nMirror complete.")
    print(f"  {pushed} pushed, {skipped} skipped, {failed} failed")
    print(f"  NOTE: late_policy and NewQuiz content must be set manually in Canvas.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    parser = argparse.ArgumentParser(description="One-off: mirror course/ → MASTER_COURSE_ID")
    parser.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    parser.add_argument("--pull", action="store_true", help="Map MASTER_COURSE_ID item IDs")
    parser.add_argument("--push", action="store_true", help="Push course/ content → MASTER_COURSE_ID")
    parser.add_argument("--status", action="store_true", help="Show coverage")
    parser.add_argument("--allow-enrolled", action="store_true",
                        help="bypass the startup safety guard (#27)")
    args = parser.parse_args()

    # Startup safety guard (#27): source (CANVAS_COURSE_ID) is read on every
    # mode; target (MASTER_COURSE_ID) is the write target on --push.
    if args.push or args.pull or args.status:
        _course_guard(BASE, _h(), SOURCE_ID, "read",
                      allow_override=args.allow_enrolled,
                      label="source (CANVAS_COURSE_ID)")
    if args.push:
        _course_guard(BASE, _h(), TARGET_ID, "write",
                      allow_override=args.allow_enrolled,
                      label="target (MASTER_COURSE_ID)")

    if args.pull:
        cmd_pull()
    elif args.push:
        cmd_push()
    elif args.status:
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

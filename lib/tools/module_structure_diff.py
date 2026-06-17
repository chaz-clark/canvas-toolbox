"""
module_structure_diff.py

READ-ONLY. Compares module prerequisites and completion requirements between
the Canvas Blueprint course (BLUEPRINT_COURSE_ID) and the master course
(MASTER_COURSE_ID). Makes only GET requests — never writes to Canvas.

General-purpose diagnostic: no course-ID hardcoding, no sprint/module-name
heuristics, works on any blueprint/master pair. It enforces no policy — it
just reports differences. "Blueprint -> would change master" is only the
diff's stated reference direction (which side is shown as the target), NOT
an "accepted deviation from AGENTS.md Rule 6"; the tool writes nothing and
takes no position on which course should win.

Modules and items are matched across courses by title slug, never by ID
(AGENTS.md Rule 2 — Canvas IDs are course-specific). Prerequisite module IDs
are resolved to module names within each course before comparison.

Usage:
    uv run python tools/module_structure_diff.py
"""

import argparse
import os
import re
import sys
from pathlib import Path

import requests

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    pass

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url

MASTER_COURSE_ID = os.environ.get("MASTER_COURSE_ID", "")
BLUEPRINT_COURSE_ID = os.environ.get("BLUEPRINT_COURSE_ID", "")


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
    """GET with pagination (read-only)."""
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    results = []
    while url:
        resp = requests.get(url, headers=_headers(), params=params, timeout=20)
        if resp.status_code >= 400:
            print(f"ERROR {resp.status_code} on GET {endpoint}: {resp.text[:200]}")
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


def _slug(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")[:80]


def _requirement_mode(module: dict) -> str:
    """Canvas: requirement_count == 1 -> complete ONE; null/absent -> complete ALL."""
    return "one" if module.get("requirement_count") == 1 else "all"


def _item_req(item: dict) -> str:
    cr = item.get("completion_requirement")
    if not cr:
        return "—"
    t = cr.get("type", "?")
    if t == "min_score":
        return f"min_score>={cr.get('min_score')}"
    return t


def fetch_course(course_id: str) -> dict:
    """Return {module_slug: {...}} with prereqs (as names) + completion data."""
    modules = _get(f"/courses/{course_id}/modules", params={"per_page": 100})
    id_to_name = {m["id"]: m["name"] for m in modules}
    out = {}
    for m in modules:
        items = _get(f"/courses/{course_id}/modules/{m['id']}/items",
                     params={"per_page": 100})
        prereq_names = sorted(
            id_to_name.get(pid, f"<id {pid}>")
            for pid in (m.get("prerequisite_module_ids") or [])
        )
        out[_slug(m["name"])] = {
            "name": m["name"],
            "position": m.get("position"),
            "prereqs": prereq_names,
            "sequential": bool(m.get("require_sequential_progress")),
            "requirement_mode": _requirement_mode(m),
            "items": {
                (_slug(it.get("title", "")), it.get("type", "")): {
                    "title": it.get("title", ""),
                    "type": it.get("type", ""),
                    "req": _item_req(it),
                }
                for it in items
            },
        }
    return out


def main():
    parser = argparse.ArgumentParser(
        description=(
            "READ-ONLY diff of module prerequisites + completion requirements "
            "between a Canvas Blueprint course and a master course. Reads "
            "BLUEPRINT_COURSE_ID + MASTER_COURSE_ID + CANVAS_BASE_URL + "
            "CANVAS_API_TOKEN from the environment (or .env). Writes nothing."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args()
    _check_env()
    print(f"READ-ONLY diff — Blueprint {BLUEPRINT_COURSE_ID} (authoritative) "
          f"vs Master {MASTER_COURSE_ID}\n" + "=" * 70)

    bp = fetch_course(BLUEPRINT_COURSE_ID)
    ms = fetch_course(MASTER_COURSE_ID)

    only_bp = sorted(set(bp) - set(ms))
    only_ms = sorted(set(ms) - set(bp))
    common = sorted(set(bp) & set(ms))

    if only_bp:
        print("\nModules in BLUEPRINT but not matched in master (by title):")
        for s in only_bp:
            print(f"  - {bp[s]['name']}")
    if only_ms:
        print("\nModules in MASTER not present in blueprint (left as-is):")
        for s in only_ms:
            print(f"  - {ms[s]['name']}")

    total_diffs = 0
    print("\n" + "=" * 70)
    print("PER-MODULE DIFFERENCES (blueprint -> would change master)")
    print("=" * 70)

    for s in common:
        b, m = bp[s], ms[s]
        lines = []

        if b["prereqs"] != m["prereqs"]:
            lines.append(f"  prerequisites : master={m['prereqs'] or '[]'}  "
                         f"-> blueprint={b['prereqs'] or '[]'}")
        if b["sequential"] != m["sequential"]:
            lines.append(f"  sequential_progress : master={m['sequential']} "
                         f"-> blueprint={b['sequential']}")
        if b["requirement_mode"] != m["requirement_mode"]:
            lines.append(f"  completion mode : master='complete {m['requirement_mode']}' "
                         f"-> blueprint='complete {b['requirement_mode']}'")

        item_keys = sorted(set(b["items"]) | set(m["items"]))
        for k in item_keys:
            bi, mi = b["items"].get(k), m["items"].get(k)
            if bi and mi and bi["req"] != mi["req"]:
                lines.append(f"  item req: {bi['title']!r} ({bi['type']}) "
                             f"master={mi['req']} -> blueprint={bi['req']}")
            elif bi and not mi:
                lines.append(f"  item only in blueprint: {bi['title']!r} "
                             f"({bi['type']}) req={bi['req']}")
            elif mi and not bi:
                lines.append(f"  item only in master: {mi['title']!r} "
                             f"({mi['type']}) req={mi['req']}")

        if lines:
            total_diffs += len(lines)
            print(f"\n[{b['name']}]")
            print("\n".join(lines))

    print("\n" + "=" * 70)
    if total_diffs == 0:
        print("No prerequisite / completion-requirement differences. "
              "Master already matches blueprint.")
    else:
        print(f"{total_diffs} difference(s) across {len(common)} matched modules.")
        print("READ-ONLY: nothing was written. Review above before any mirror step.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
FERPA leak self-check on de-identified outputs.

Part of the canvas-toolbox generic grader skill (v0.1). See:
  - lib/agents/canvas_grader.md (operator-facing pipeline guide)
  - lib/agents/knowledge/grader_knowledge.md (FERPA architecture, §1)

WHAT IT DOES
  Reads the key map (which has names) but prints ONLY keys + counts — never a name —
  so it's safe to run in a shared terminal / with an AI watching. A "possible hit"
  means a name-like token from the original filename appears in that key's de-identified
  .md. Review those specific files locally (you know the names); the AI never sees them.

  This is the gate before any cloud step. If any flag fires, STOP (P-003) — investigate
  before continuing to grading. Exit code 2 on any flagged file.

USAGE
  # Conventional layout
  uv run python lib/tools/grader_name_leak_check.py --challenge-dir grading/kc1

  # Explicit (for non-conventional layouts)
  uv run python lib/tools/grader_name_leak_check.py \\
    --map <keymap.json> --deid-dir <submissions_deid/>

GENERALIZED FROM: ds460-master/grading/check_name_leak.py
(commits 754c966..91a5113 — round-1 KC1 beta).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from _challenge_dir_guard import resolve_challenge_dir  # issue #44 FERPA guard

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

# Common boilerplate tokens that aren't names — adding course-specific extras via --stop is OK.
DEFAULT_STOP = {
    "html", "late", "the", "and", "submission", "ipynb", "copy", "final", "key",
    "challenge", "groupby", "partitionby", "pyspark", "databricks", "personal",
    "docx", "review", "midreview", "performance",
}


def name_tokens(filename: str, stop: set[str]) -> list[str]:
    """Tokens from the Canvas-format filename's name field.

    Canvas: "{lastname}{firstname}_{subid}_{attid}_{title}.html" — name is the
    first underscore-separated field. Out-of-band drops follow the convention
    "<prefix>_<userid>.<ext>" where the name was added to .known_names.txt (so
    the filename carries no name and this scan returns nothing for that file).
    """
    name_field = Path(filename).stem.split("_", 1)[0]
    return [t for t in re.split(r"[^A-Za-z]+", name_field)
            if len(t) >= 4 and t.lower() not in stop]


def main() -> int:
    ap = argparse.ArgumentParser(description="FERPA leak self-check on de-id'd outputs.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", dest="challenge_dir", default=None,
                    help="Convention base path (e.g. grading/kc1). Sets defaults for --map / --deid-dir.")
    ap.add_argument("--map", dest="mapfile", default=None,
                    help="Path to .keymap.json (default: <challenge-dir>/.keymap.json)")
    ap.add_argument("--deid-dir", dest="deid_dir", default=None,
                    help="Directory of keyed .md files (default: <challenge-dir>/submissions_deid)")
    ap.add_argument("--stop", action="append", default=[],
                    help="Additional stop tokens (course/format-specific). May be repeated.")
    args = ap.parse_args()

    if args.challenge_dir:
        cd = resolve_challenge_dir(args.challenge_dir, verb="leak-checking")
        args.mapfile = args.mapfile or str(cd / ".keymap.json")
        args.deid_dir = args.deid_dir or str(cd / "submissions_deid")

    if not args.mapfile or not args.deid_dir:
        print("Missing required arguments. Pass --challenge-dir OR both of --map and --deid-dir.",
              file=__import__("sys").stderr)
        return 1

    mapfile = Path(args.mapfile)
    deid_dir = Path(args.deid_dir)
    if not mapfile.exists():
        print(f"No key map at {mapfile} — run a grader_deidentify_* tool first.")
        return 1

    keymap = json.loads(mapfile.read_text(encoding="utf-8")).get("map", {})
    stop = DEFAULT_STOP | {s.lower() for s in args.stop}

    clean = flagged = missing = 0
    for key, fname in sorted(keymap.items()):
        md = deid_dir / f"{key}.md"
        if not md.exists():
            print(f"  {key}: no de-id output")
            missing += 1
            continue
        text = md.read_text(encoding="utf-8", errors="replace").lower()
        hits = sum(text.count(t.lower()) for t in name_tokens(fname, stop))
        if hits:
            print(f"  {key}: {hits} possible name hit(s) — review this file locally")
            flagged += 1
        else:
            clean += 1

    # counts only — no names
    print(f"\n{clean} clean, {flagged} to review, {missing} missing (of {len(keymap)} keys).")
    # P-003 stop-on-defect: exit 2 if any flag, 1 if missing-only, 0 if clean
    if flagged:
        return 2
    if missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

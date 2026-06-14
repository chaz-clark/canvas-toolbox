#!/usr/bin/env python3
"""
Build the canonical FERPA-safe `_userid_key_grade_join.json` for a
multi-surface task by joining each surface's `.keymap.json` (key → file)
with the optional `ta_grades_<surface>.json` (user_id → grade) sidecars.

Sub-item B of canvas-toolbox#54. m119 SP26 wrote this with bespoke Python
each cohort — rummage keymap, extract uid from filename via regex, join
with TA grades. Every multi-surface cohort needs the same artifact. This
automates it.

WHAT THE JOIN IS
  The central FERPA-safe artifact for any multi-surface task. Keyed by
  Canvas user_id (LMS row id — safe per the toolkit's standing rule);
  carries the opaque KEY for each surface (`P1T1-AI-LOG-A1B2C3`,
  `P1T1-COHESIVE-DEF456`); optionally carries the TA-recorded grade per
  surface (from grader_pull_ta_grades / #56). NO names anywhere — the
  AI-safe view of "who did what".

INPUT (canonical task layout — sub-A scaffolder builds this)
  <task-dir>/
      ai_log/
          .keymap.json           (built by deid; key → filename)
          ta_grades_ai_log.json  (optional; built by grader_pull_ta_grades #56)
      cohesive_narrative/
          .keymap.json
          ta_grades_cohesive_narrative.json
      ... (any surface subdirs)

  Single-surface tasks (no surface subdirs) are also supported: the tool
  treats the `<task-dir>` itself as the only surface (named after the
  task-dir basename or --surface override).

OUTPUT
  <task-dir>/_userid_key_grade_join.json — JSON array, one row per
  user_id seen in any surface's keymap:

    [{
      "user_id": 33619,
      "keys": {
        "ai_log":              "P1T1-AI-LOG-EFD332",
        "cohesive_narrative":  "P1T1-COHESIVE-7F3A02"
      },
      "ta_grades": {
        "ai_log":              {"grade": "complete", "score": 1.0},
        "cohesive_narrative":  {"grade": "Meets",    "score": 4.0}
      }
    }, ...]

FERPA
  - Reads .keymap.json (gitignored, local-only) + ta_grades_*.json
    (user_id + grade only — never names).
  - Output keyed by user_id. NO names anywhere.
  - canvas_course_guard not involved — this is a local-only file join.

UID RESOLUTION
  Filenames follow the grader_fetch.py convention: `<prefix>_<uid>.<ext>`.
  Uid is the last numeric segment before the extension. If a filename
  doesn't match (rare — out-of-band drops), the tool emits a `WARN`
  with the unresolvable filename and skips that key.

USAGE
  uv run python lib/tools/grader_join.py
      --task-dir grading/p1t1_combined

EXIT CODES
  0  wrote join file (or printed it to stdout)
  2  setup / unresolvable layout / no surfaces found
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _challenge_dir_guard import resolve_challenge_dir

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

# Issue #68: `<prefix>_<uid>.<ext>` is the canonical shape, AND the
# Playwright-rendered share-URL transcripts (#51 grader_follow_share_url)
# write `<prefix>_<uid>_external.<ext>` — a legitimate part of the deid
# pipeline. The optional `_external` suffix between uid and extension
# means both shapes resolve to the same uid.
_UID_FROM_FILENAME = re.compile(r"_(\d+)(?:_external)?\.[A-Za-z0-9]+$")


def extract_uid(filename: str) -> tuple[int, bool] | None:
    """Return (user_id, is_external) for a filename, or None if the
    `<prefix>_<uid>[_external].<ext>` convention doesn't match. The
    `is_external` flag surfaces the follow-share-url origin (#51) so
    downstream callers can see which keys came from a rendered transcript
    vs. the original submission file."""
    m = _UID_FROM_FILENAME.search(filename or "")
    if not m:
        return None
    is_external = "_external." in (filename or "").lower()
    return (int(m.group(1)), is_external)


def find_surface_dirs(task_dir: Path) -> list[tuple[str, Path]]:
    """Return [(surface_name, surface_dir)] for every immediate subdir
    of task_dir that has its own .keymap.json. If task_dir itself has a
    keymap, return a single (basename, task_dir) entry — single-surface
    task."""
    surfaces: list[tuple[str, Path]] = []
    own_map = task_dir / ".keymap.json"
    if own_map.exists():
        surfaces.append((task_dir.name, task_dir))
        return surfaces
    for child in sorted(task_dir.iterdir()):
        if child.is_dir() and (child / ".keymap.json").exists():
            surfaces.append((child.name, child))
    return surfaces


def load_keymap(surface_dir: Path) -> dict[str, str]:
    p = surface_dir / ".keymap.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    return raw.get("map", {}) if isinstance(raw, dict) else {}


def load_ta_grades(surface_dir: Path, surface_name: str) -> dict[int, dict]:
    """Look for any of {ta_grades_<surface>.json, ta_grades.json}. Return
    {user_id: {grade, score, ...}}."""
    candidates = [
        surface_dir / f"ta_grades_{surface_name}.json",
        surface_dir / "ta_grades.json",
    ]
    for p in candidates:
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return {int(row["user_id"]): {k: v for k, v in row.items() if k != "user_id"}
                        for row in data if "user_id" in row}
    return {}


def build_join(task_dir: Path) -> list[dict]:
    surfaces = find_surface_dirs(task_dir)
    if not surfaces:
        raise SystemExit(f"No .keymap.json found at {task_dir} or any immediate subdir.")

    # uid → {surface: key}  AND  uid → {surface: ta_grade}
    keys_by_uid: dict[int, dict[str, str]] = {}
    external_by_uid_surface: dict[tuple[int, str], bool] = {}
    ta_by_uid: dict[int, dict[str, dict]] = {}
    unresolved: list[tuple[str, str]] = []  # (surface, filename)

    for surface_name, sdir in surfaces:
        keymap = load_keymap(sdir)
        for key, filename in keymap.items():
            parsed = extract_uid(filename)
            if parsed is None:
                unresolved.append((surface_name, filename))
                continue
            uid, is_external = parsed
            slot = keys_by_uid.setdefault(uid, {})
            if surface_name in slot and slot[surface_name] != key:
                # Multiple keys for the same uid+surface. Prefer the
                # NON-external key (original submission) over the
                # _external.md key (Playwright-rendered transcript), and
                # otherwise keep the first seen. Issue #54-D / #68.
                prior_was_external = external_by_uid_surface.get((uid, surface_name), False)
                if prior_was_external and not is_external:
                    slot[surface_name] = key
                    external_by_uid_surface[(uid, surface_name)] = False
                    continue
                if not prior_was_external and is_external:
                    continue  # keep the original; ignore the external
                # Same flavor on both → legacy prefix duality
                print(f"WARN: uid={uid} has multiple keys for surface "
                      f"'{surface_name}': kept '{slot[surface_name]}', "
                      f"ignored '{key}'. Run --cleanup-legacy on the deid "
                      f"adapter to fix.", file=sys.stderr)
                continue
            slot[surface_name] = key
            external_by_uid_surface[(uid, surface_name)] = is_external

        ta_grades = load_ta_grades(sdir, surface_name)
        for uid, grade in ta_grades.items():
            ta_by_uid.setdefault(uid, {})[surface_name] = grade

    all_uids = set(keys_by_uid) | set(ta_by_uid)
    rows: list[dict] = []
    for uid in sorted(all_uids):
        # Issue #68: surface which surfaces came from a follow-share-url
        # rendered transcript (the `_external.md` files). Downstream
        # tools can use this to decide whether to weight a key
        # differently (a rendered transcript is the AI Log's
        # `link-only` submission path, not the original turn-by-turn
        # paste — same student, same task, slightly different shape).
        external_surfaces = sorted(
            s for (u, s), ext in external_by_uid_surface.items()
            if u == uid and ext
        )
        row = {
            "user_id": uid,
            "keys": keys_by_uid.get(uid, {}),
            "ta_grades": ta_by_uid.get(uid, {}),
        }
        if external_surfaces:
            row["external_surfaces"] = external_surfaces
        rows.append(row)

    if unresolved:
        print(f"\nWARN: {len(unresolved)} filename(s) didn't match the "
              f"<prefix>_<uid>.<ext> convention. Skipped:", file=sys.stderr)
        for s, f in unresolved[:5]:
            print(f"    {s}: {f}", file=sys.stderr)
        if len(unresolved) > 5:
            print(f"    ... +{len(unresolved) - 5} more", file=sys.stderr)

    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build the canonical FERPA-safe _userid_key_grade_join.json for a "
                    "multi-surface task (canvas-toolbox#54 sub-B).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--task-dir", required=True,
                    help="Task directory (e.g. grading/p1t1_combined). Auto-detects "
                         "surfaces from immediate subdirs that have .keymap.json. "
                         "Single-surface tasks (no subdirs) also supported.")
    ap.add_argument("--out", default=None,
                    help="Output path. Default: <task-dir>/_userid_key_grade_join.json")
    ap.add_argument("--stdout", action="store_true",
                    help="Print the JSON to stdout instead of (or in addition to) writing the file.")
    args = ap.parse_args()

    task_dir = resolve_challenge_dir(args.task_dir, verb="joining keys in")
    rows = build_join(task_dir)

    body = json.dumps(rows, indent=2, ensure_ascii=False)

    if args.stdout:
        print(body)

    out_path = Path(args.out) if args.out else (task_dir / "_userid_key_grade_join.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    print(f"  Join → {out_path}  ({len(rows)} user_id(s) across "
          f"{len({s for r in rows for s in r['keys']})} surface(s))",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Save a point-in-time snapshot of the course as ONE local zip.

The zip holds:
  canvas/course.imscc   Canvas's own Common Cartridge export (restorable by Canvas import)
  local/<dir>/...       the local mirror folder (default `course/`), if present
  SNAPSHOT.json         course id, timestamp, toolkit version, file counts

Read-only against Canvas (it asks Canvas to build an export; no course content
changes). FERPA Zone-2 paths (built-in list + `.claude/ferpa_zone2.txt`) are never
added to the zip.

Usage:
    uv run python lib/tools/cb_snapshot.py
    uv run python lib/tools/cb_snapshot.py --output-dir ~/Backups --no-local
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from _env_loader import load_env, force_utf8_console
    load_env()
except ImportError:
    force_utf8_console = lambda: None  # noqa: E731

from export_imscc import export_course
from grade_guardian import compile_zone2, load_zone2, load_zone2_exempt

DEFAULT_OUTPUT_DIR = "snapshots"
DEFAULT_LOCAL_DIR = "course"


def _toolkit_version() -> str:
    try:
        for line in (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text().splitlines():
            if line.startswith("version"):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "unknown"


def collect_local_files(local_dir: Path, course_root: Path) -> tuple[list[Path], int]:
    """(files safe to include, count skipped as Zone-2). Paths are checked
    relative to the course root, the form the Zone-2 patterns are written for."""
    entries, _ = load_zone2(course_root)
    path_re, _ = compile_zone2(entries, load_zone2_exempt(course_root))
    keep, skipped = [], 0
    for p in sorted(local_dir.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        if path_re.search(p.relative_to(course_root).as_posix()):
            skipped += 1
        else:
            keep.append(p)
    return keep, skipped


def build_snapshot(course_id: str, imscc: Path | None, local_dir: Path | None,
                   output_dir: Path, course_root: Path, now: datetime | None = None) -> Path:
    """Write the zip and return its path. `imscc` / `local_dir` may each be None."""
    now = now or datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    # A per-directory `*` ignore ships with the directory, so snapshots can't be
    # committed even if the root .gitignore predates this tool.
    gi = output_dir / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n", encoding="utf-8")

    out = output_dir / f"course-{course_id}-{now.strftime('%Y-%m-%d-%H%M%S')}.zip"
    files, skipped = ([], 0)
    if local_dir is not None:
        files, skipped = collect_local_files(local_dir, course_root)

    meta = {
        "course_id": course_id,
        "created_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "toolkit_version": _toolkit_version(),
        "canvas_export": bool(imscc),
        "local_dir": local_dir.name if local_dir else None,
        "local_files": len(files),
        "local_files_skipped_ferpa_zone2": skipped,
    }
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("SNAPSHOT.json", json.dumps(meta, indent=2) + "\n")
        if imscc:
            z.write(imscc, "canvas/course.imscc")
        for f in files:
            z.write(f, f"local/{local_dir.name}/{f.relative_to(local_dir).as_posix()}")
    return out


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description="Save a local zip snapshot of the course.")
    ap.add_argument("--output-dir", type=Path, default=Path(DEFAULT_OUTPUT_DIR),
                    help=f"Where to save the zip (default: ./{DEFAULT_OUTPUT_DIR}/, self-ignored by git)")
    ap.add_argument("--local-dir", type=Path, default=Path(DEFAULT_LOCAL_DIR),
                    help=f"Local mirror folder to include (default: ./{DEFAULT_LOCAL_DIR}/)")
    ap.add_argument("--no-local", action="store_true", help="Canvas export only")
    ap.add_argument("--no-canvas", action="store_true", help="Local files only (works offline)")
    args = ap.parse_args()

    if args.no_local and args.no_canvas:
        print("ERROR: nothing to snapshot (--no-local and --no-canvas)", file=sys.stderr)
        return 1

    course_id = os.environ.get("CANVAS_COURSE_ID", "")
    token = os.environ.get("CANVAS_API_TOKEN", "")
    base_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
    if not course_id:
        print("ERROR: CANVAS_COURSE_ID not set (check this folder's .env)", file=sys.stderr)
        return 1
    if not args.no_canvas and not (token and base_url):
        print("ERROR: CANVAS_API_TOKEN / CANVAS_BASE_URL not found", file=sys.stderr)
        return 1

    local_dir = None
    if not args.no_local:
        if args.local_dir.is_dir():
            local_dir = args.local_dir.resolve()
        elif args.no_canvas:
            print(f"ERROR: {args.local_dir}/ not found", file=sys.stderr)
            return 1
        else:
            print(f"Note: {args.local_dir}/ not found — snapshot will hold the Canvas export only.")

    with tempfile.TemporaryDirectory() as tmp:
        imscc = None
        if not args.no_canvas:
            imscc = Path(tmp) / "course.imscc"
            if not export_course(course_id, imscc, base_url, token):
                print("ERROR: Canvas export failed — no snapshot written.", file=sys.stderr)
                return 1
        out = build_snapshot(course_id, imscc, local_dir, args.output_dir, Path.cwd().resolve())

    print(f"\n✓ Snapshot saved: {out}  ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

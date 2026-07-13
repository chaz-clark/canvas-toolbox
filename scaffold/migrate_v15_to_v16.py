#!/usr/bin/env python3
"""Migrate canvas-toolbox v1.5 → v1.6 (course-centric architecture).

v1.6 moves all course files from canvas-toolbox/ to the parent course root:
  - .env (handled by cb-init, but this script can do it too)
  - course/, course_ref/, course_src/ (Canvas mirrors)
  - grading/ (grading workflows)
  - .canvas/ (runtime indexes)

USAGE:
  # Dry run (reports what it would do, no changes):
  python3 canvas-toolbox/scaffold/migrate_v15_to_v16.py

  # Actually move files:
  python3 canvas-toolbox/scaffold/migrate_v15_to_v16.py --apply

SAFETY:
  - Only runs if canvas-toolbox/ has course files to migrate
  - Only runs if parent directory exists and isn't a dev folder
  - Dry-run by default (requires --apply to write)
  - Preserves all files (uses shutil.move, no deletions)
  - Checks for conflicts before moving (won't overwrite)

AFTER MIGRATION:
  Run cb-init to finish setup:
    uv run python canvas-toolbox/lib/tools/cb_init.py

  This will:
  - Create .gitignore at course root
  - Create AGENTS.md stub
  - Verify .env migration
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def detect_v15_layout() -> tuple[Path, Path] | None:
    """Detect if running from v1.5 layout.

    Returns: (canvas_toolbox_dir, course_root) if v1.5 layout detected, else None.
    """
    # Assuming script is in canvas-toolbox/scaffold/
    script_dir = Path(__file__).resolve().parent
    canvas_toolbox = script_dir.parent

    if canvas_toolbox.name != "canvas-toolbox":
        return None

    course_root = canvas_toolbox.parent

    # Don't migrate if parent is a dev folder (standalone mode)
    dev_folders = {"GitHub", "github", "repos", "repositories", "projects", "src", "code", "dev", "Documents"}
    if course_root.name in dev_folders:
        return None

    # Check if any v1.5 course files exist in canvas-toolbox/
    course_files = [
        canvas_toolbox / ".env",
        canvas_toolbox / "course",
        canvas_toolbox / "course_ref",
        canvas_toolbox / "course_src",
        canvas_toolbox / "grading",
        canvas_toolbox / ".canvas",
    ]

    if any(f.exists() for f in course_files):
        return canvas_toolbox, course_root

    return None


def check_conflicts(source: Path, dest: Path) -> list[str]:
    """Check if moving source to dest would cause conflicts."""
    conflicts = []

    if dest.exists():
        conflicts.append(f"  ⚠ Conflict: {dest} already exists")

    return conflicts


def migrate_file(source: Path, dest: Path, *, dry_run: bool) -> bool:
    """Move source to dest. Returns True if successful."""
    if not source.exists():
        return True  # Nothing to do

    conflicts = check_conflicts(source, dest)
    if conflicts:
        print(f"  ⚠ Skipping {source.name} (conflict):")
        for conflict in conflicts:
            print(conflict)
        return False

    if dry_run:
        print(f"  → would move {source} to {dest}")
        return True

    shutil.move(str(source), str(dest))
    print(f"  ✓ Moved {source.name} to {dest}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate canvas-toolbox v1.5 → v1.6 (course-centric architecture)",
        epilog="After migration, run: uv run python canvas-toolbox/lib/tools/cb_init.py"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually move files (default is dry-run)"
    )
    args = parser.parse_args()

    print("=== canvas-toolbox v1.5 → v1.6 migration ===")
    print()

    # Detect v1.5 layout
    layout = detect_v15_layout()
    if not layout:
        print("✓ No v1.5 course files detected in canvas-toolbox/")
        print("  Already migrated, or running in standalone mode.")
        return 0

    canvas_toolbox, course_root = layout

    print(f"Detected v1.5 layout:")
    print(f"  canvas-toolbox: {canvas_toolbox}")
    print(f"  course root:    {course_root}")
    print()

    if args.apply:
        print("Mode: WRITE (--apply)")
    else:
        print("Mode: DRY RUN (use --apply to actually move files)")
    print()

    # Files to migrate
    migrations = [
        (".env", "Course configuration"),
        ("course", "Canvas mirror (course/)"),
        ("course_ref", "Canvas reference mirror (course_ref/)"),
        ("course_src", "Markdown authoring workspace (course_src/)"),
        ("grading", "Grading workflows (grading/)"),
        (".canvas", "Runtime indexes (.canvas/)"),
    ]

    print("Migrations:")
    success_count = 0
    skip_count = 0

    for filename, description in migrations:
        source = canvas_toolbox / filename
        dest = course_root / filename

        if not source.exists():
            print(f"  ⏭  {filename} — not present, skipping")
            skip_count += 1
            continue

        print(f"  📦 {description}")
        if migrate_file(source, dest, dry_run=not args.apply):
            success_count += 1
        else:
            skip_count += 1

    print()
    print(f"Summary: {success_count} items {'would be ' if not args.apply else ''}migrated, {skip_count} skipped")
    print()

    if not args.apply:
        print("To apply these changes, re-run with --apply:")
        print(f"  python3 {Path(__file__).relative_to(Path.cwd())} --apply")
    else:
        print("✓ Migration complete!")
        print()
        print("Next step: run cb-init to finish v1.6 setup:")
        print("  uv run python canvas-toolbox/lib/tools/cb_init.py")
        print()
        print("This will:")
        print("  - Create .gitignore at course root")
        print("  - Create AGENTS.md stub")
        print("  - Verify .env migration")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

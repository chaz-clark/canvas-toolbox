#!/usr/bin/env python3
"""
Validate a Canvas .imscc for known silent-failure modes (Sprint 4).

Checks: valid ZIP, imsmanifest.xml present, a Canvas trigger file
(course_settings/canvas_export.txt or context.xml), resource identifiers in the
Canvas `<letter>`+32hex form (human-readable ids import silently wrong), and
per-item date constraints (unlock ≤ due ≤ lock).

Exit 0 = clean, 1 = issues found.

USAGE
  uv run python lib/tools/validate_imscc.py ~/Downloads/course_export.imscc
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

from _imscc import validate_imscc


def main(argv=None) -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description="Validate a Canvas .imscc.")
    ap.add_argument("input", type=Path, help=".imscc file to validate")
    args = ap.parse_args(argv)

    issues = validate_imscc(args.input)
    if not issues:
        print(f"✓ {args.input.name}: valid (no known Canvas-import problems)")
        return 0
    print(f"✗ {args.input.name}: {len(issues)} issue(s):", file=sys.stderr)
    for i in issues:
        print(f"  - {i}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

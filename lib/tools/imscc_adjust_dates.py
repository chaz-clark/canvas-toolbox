#!/usr/bin/env python3
"""
Shift all schedule dates in a Canvas .imscc by N days, for a new semester (Sprint 4).

Identifiers and structure are preserved (dates are edited in place inside the
zip), so re-importing overwrites the SAME course in place instead of
duplicating. Validation runs on the output BEFORE it is kept — a failing
validation blocks the write (Jidoka: stop on defect).

Timezone note: .imscc dates are UTC (Canvas renders them in the course
timezone). A whole-day shift keeps the displayed local time stable EXCEPT across
a daylight-saving boundary, where a due time may drift by one hour. Spot-check
dates that cross a DST change.

USAGE
  uv run python lib/tools/imscc_adjust_dates.py \
    --input ~/Downloads/course_export.imscc --shift-days 365 \
    --out ~/Desktop/course_next_semester.imscc
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

from _imscc import adjust_dates_in_imscc, validate_imscc
import _file_finder


def main(argv=None) -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description="Shift Canvas .imscc dates by N days.")
    ap.add_argument("--input", type=Path, help=".imscc (default: newest in ~/Downloads)")
    ap.add_argument("--shift-days", type=int, required=True, help="days to shift (+forward / -back)")
    ap.add_argument("--out", type=Path, required=True, help="output .imscc")
    args = ap.parse_args(argv)

    src = args.input or _file_finder.require_imscc()

    pre = validate_imscc(src)
    if pre:
        print(f"⚠ input has {len(pre)} pre-existing issue(s) (Canvas's, not ours):", file=sys.stderr)
        for i in pre:
            print(f"    - {i}", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = adjust_dates_in_imscc(src, args.out, args.shift_days)

    post = validate_imscc(args.out)
    if post:
        args.out.unlink(missing_ok=True)  # Jidoka: never hand back a broken .imscc
        print(f"✗ output failed validation ({len(post)} issue(s)) — not written:", file=sys.stderr)
        for i in post:
            print(f"    - {i}", file=sys.stderr)
        return 2

    print(f"✓ shifted {n} dates by {args.shift_days:+d} days")
    print(f"  validated .imscc: {args.out}")
    print("  Re-import to the SAME course to overwrite in place (identifiers preserved).")
    print("  ⚠ Overwrite is DESTRUCTIVE on a course with student work — prefer a new/empty course.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

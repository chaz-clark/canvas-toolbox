#!/usr/bin/env python3
"""
Record course/ edits back into the source .imscc — the offline WRITE path.

course/ is the WORKING folder (iterate freely; audits read it). The .imscc is the
SOURCE OF TRUTH — offline_import saved the original as course/.source.imscc. When
course/ reaches a final state, this tool PATCHES only the fields course/ tracks
into the matching resources of that sidecar IN PLACE, copying every other byte
verbatim. Quiz questions/QTI, files (web_resources/), LTI, rubric long-
descriptions and formatting are PRESERVED — the decisive advantage over a
from-scratch packager: the mirror never rebuilds, it patches an already-valid
Canvas cartridge.

Fields written back (exactly what offline_import extracts): assignment
title/dates/points/workflow_state/submission_types/grading_type/group/description;
quiz title/dates/published/group; page HTML; module names/order/published/item
order; assignment-group names/weights; outcomes; syllabus.

Validation runs on the output BEFORE it is kept — a shift-INTRODUCED issue blocks
the write (Jidoka: stop on defect); pre-existing source quirks carry through.

USAGE
  # update the sidecar in place (default), or write a copy with --output:
  uv run python lib/tools/imscc_record.py --course-dir course
  uv run python lib/tools/imscc_record.py --course-dir course --output ~/Desktop/recorded.imscc
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

from _imscc import mirror_course_into_imscc, validate_imscc

SIDECAR = ".source.imscc"


def main(argv=None) -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description="Record course/ edits back into the source .imscc.")
    ap.add_argument("--course-dir", type=Path, default=Path("course"),
                    help="the course/ folder to record (default: course)")
    ap.add_argument("--output", type=Path,
                    help="write the recorded .imscc here (default: update course/.source.imscc in place)")
    args = ap.parse_args(argv)

    if not args.course_dir.is_dir():
        print(f"ERROR: {args.course_dir} is not a directory.", file=sys.stderr)
        return 2

    src = args.course_dir / SIDECAR
    if not src.is_file():
        print(
            f"ERROR: no source cartridge at {src}.\n"
            f"  This course wasn't created by offline_import — the mirror needs the\n"
            f"  original .imscc it saved as the sidecar. Re-run:\n"
            f"    uv run python lib/tools/offline_import.py --imscc <export.imscc> --out {args.course_dir}",
            file=sys.stderr,
        )
        return 2

    final = args.output or src
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(final.name + ".tmp")

    counts = mirror_course_into_imscc(args.course_dir, src, tmp)

    # Block ONLY on issues the record INTRODUCED — not ones already in the source
    # (Canvas already tolerates pre-existing quirks; a faithful patch carries them
    # through). Mirrors imscc_adjust_dates' Jidoka guard.
    pre = validate_imscc(src)
    post = validate_imscc(tmp)
    new_issues = [i for i in post if i not in set(pre)]
    if new_issues:
        tmp.unlink(missing_ok=True)
        print(f"✗ recording INTRODUCED {len(new_issues)} validation issue(s) — not written:", file=sys.stderr)
        for i in new_issues:
            print(f"    - {i}", file=sys.stderr)
        return 2

    os.replace(tmp, final)

    if pre:
        print(f"⚠ {len(pre)} pre-existing source issue(s) carried through (Canvas already tolerates these):",
              file=sys.stderr)
        for i in pre:
            print(f"    - {i}", file=sys.stderr)

    print(f"✓ recorded course/ edits -> {final}")
    print(f"  assignments={counts['assignments']} quizzes={counts['quizzes']} "
          f"pages={counts['pages']} modules={counts['modules']} "
          f"groups={counts['assignment_groups']} outcomes={counts['outcomes']} "
          f"syllabus={counts['syllabus']} descriptions={counts['descriptions']}")
    print(f"  {counts['fields_changed']} field(s) changed; {counts['skipped']} course/ item(s) "
          f"had no source resource (preserved, not recorded).")
    print("  Quiz questions, files and everything course/ can't track were preserved byte-for-byte.")
    print("  Import via Canvas UI: Course → Settings → Import Course Content → Common Cartridge 1.x")
    print("  ⚠ Re-import OVERWRITES the matching course in place (identifiers preserved) and is")
    print("    DESTRUCTIVE on a course with student work — prefer a new/empty course.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

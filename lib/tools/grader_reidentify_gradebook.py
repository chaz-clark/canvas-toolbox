#!/usr/bin/env python3
"""
Re-identify a de-identified gradebook CSV for Canvas upload (Sprint 2).

WHY
  grader_deidentify_gradebook.py replaced each student's identity with a stable
  opaque code (Student=code; ID / SIS User ID / SIS Login ID blanked). After you
  edit scores against the de-identified sheet, restore the real identity columns
  so Canvas can match students on Grades → Import. Re-identification is a
  DETERMINISTIC lookup on the code (a bijection with the Canvas user_id) — no
  fuzzy name-matching, so there is no wrong-student risk.

WHO RUNS THIS
  The instructor, LOCALLY. It restores real names, so — like grader_reidentify.py
  — the grading AI never runs it. Output holds PII; keep it out of git.

FERPA
  Prints ONLY counts + the output path, never a name.

USAGE
  uv run python lib/tools/grader_reidentify_gradebook.py \
    --input .canvas/gradebook/grades_deid.csv \
    --map   .canvas/gradebook/gradebook_reid_map.json \
    --out   ~/Desktop/grades_for_upload.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

from _csv_utils import read_canvas_gradebook_csv, write_canvas_gradebook_csv

_RESTORE = {  # map field -> gradebook column
    "student": "Student",
    "user_id": "ID",
    "sis_user_id": "SIS User ID",
    "sis_login_id": "SIS Login ID",
}


def reidentify(gradebook, by_code: dict) -> tuple[int, list[str]]:
    """Restore identity columns in place from the code in each row's Student
    cell. Returns (restored_count, unmatched_codes). Unmatched codes are NOT
    written back — the caller must treat any as a hard error before upload."""
    header = gradebook.header
    idx = {col: header.index(col) for col in _RESTORE.values() if col in header}
    student_i = header.index("Student")
    restored, unmatched = 0, []
    for s in gradebook.students:
        code = s.raw[student_i].strip()
        rec = by_code.get(code)
        if rec is None:
            unmatched.append(code)
            continue
        for field, col in _RESTORE.items():
            if col in idx:
                while len(s.raw) <= idx[col]:
                    s.raw.append("")
                s.raw[idx[col]] = str(rec.get(field, ""))
        restored += 1
    return restored, unmatched


def main(argv=None) -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description="Re-identify a de-identified gradebook CSV for upload.")
    ap.add_argument("--input", type=Path, required=True, help="de-identified (possibly edited) gradebook CSV")
    ap.add_argument("--map", type=Path, required=True, help="re-id map JSON from grader_deidentify_gradebook.py")
    ap.add_argument("--out", type=Path, required=True, help="re-identified CSV for Canvas upload")
    args = ap.parse_args(argv)

    by_code = json.loads(args.map.read_text(encoding="utf-8")).get("by_code", {})
    gb = read_canvas_gradebook_csv(args.input)
    restored, unmatched = reidentify(gb, by_code)

    if unmatched:
        # Fail loud: uploading rows whose code isn't in the map would send scores
        # against a code-as-name. Never let that reach Canvas.
        print(
            f"✗ {len(unmatched)} row(s) have a code not in the re-id map "
            f"(e.g. {unmatched[0]}). Aborting — wrong map, or rows were added.",
            file=sys.stderr,
        )
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_canvas_gradebook_csv(gb, args.out)
    print(f"✓ re-identified {restored} students")
    print(f"  upload-ready CSV: {args.out}")
    print("  Upload via Canvas: Grades → Import")
    return 0


if __name__ == "__main__":
    sys.exit(main())

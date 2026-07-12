#!/usr/bin/env python3
"""
De-identify a Canvas gradebook CSV for safe sharing / offline work (Sprint 2).

WHY
  The gradebook export (Grades → Export) carries PII for every student: name,
  Canvas ID, SIS User ID, SIS Login ID (email). Before sharing a gradebook with
  a TA, committing it, or handing it to an AI, replace those with stable opaque
  codes. Offline, this CSV is ALSO the roster — Canvas has no instructor-facing
  People export — so the de-id master is built from the CSV's own identity
  columns, no API call needed.

REUSE (toolbox-wide consistency)
  Codes come from build_deid_master.deid_code_for(user_id): `S-` + 6 hex of
  sha256(user_id). Same function the API path uses, so a student's code is
  IDENTICAL online and offline, and matches submission de-id. Collisions are
  caught with build_deid_master.detect_collisions before anything is written.

WHAT IT DOES
  - Student  -> deid_code
  - ID, SIS User ID, SIS Login ID -> blanked
  - Section, Root Account, grades, read-only columns -> unchanged
  - Writes a re-id map (JSON, code -> real identity) for grader_reidentify_gradebook.py

FERPA
  The re-id map holds names and MUST stay gitignored — it defaults under
  .canvas/ (already gitignored). This tool prints ONLY counts + paths, never a
  name, so it is safe to run in a shared terminal.

USAGE
  uv run python lib/tools/grader_deidentify_gradebook.py \
    --input ~/Downloads/2026-07-12T1053_Grades-DS_250.csv
  # offline: with no --input, finds the newest ~/Downloads gradebook (hard-stops
  # if none present)
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
from build_deid_master import deid_code_for, detect_collisions, StudentRow
import _file_finder

_PII_BLANK_COLUMNS = ("ID", "SIS User ID", "SIS Login ID")
_DEFAULT_OUT = Path(".canvas/gradebook/grades_deid.csv")
_DEFAULT_MAP = Path(".canvas/gradebook/gradebook_reid_map.json")


def build_reid_map(gradebook, prefix: str, hash_bits: int) -> dict:
    """Return {code: {user_id, student, sis_user_id, sis_login_id}} and raise on
    a code collision (two user_ids -> same code) before any file is written."""
    header = gradebook.header
    idx = {c: header.index(c) for c in ("Student",) + _PII_BLANK_COLUMNS if c in header}
    rows_for_collision: list[StudentRow] = []
    by_code: dict[str, dict] = {}
    for s in gradebook.students:
        cid = s.canvas_id.strip()
        if not cid.isdigit():
            continue  # non-student rows (e.g. a stray Test Student w/o id) — leave alone
        uid = int(cid)
        code = deid_code_for(uid, prefix=prefix, hash_bits=hash_bits)
        rows_for_collision.append(
            StudentRow(deid_code=code, user_id=uid, sortable_name=s.student, withdrawn=0)
        )
        by_code[code] = {
            "user_id": uid,
            "student": s.raw[idx["Student"]],
            "sis_user_id": s.raw[idx["SIS User ID"]] if "SIS User ID" in idx else "",
            "sis_login_id": s.raw[idx["SIS Login ID"]] if "SIS Login ID" in idx else "",
        }
    collisions = detect_collisions(rows_for_collision)
    if collisions:
        raise ValueError(
            f"de-id code collision(s): {collisions}. Increase --hash-bits and retry."
        )
    return by_code


def apply_deidentification(gradebook, by_code: dict, prefix: str, hash_bits: int) -> int:
    """Rewrite identity cells in place: Student->code, PII columns blanked.
    Returns the number of student rows de-identified."""
    header = gradebook.header
    student_i = header.index("Student")
    blank_idx = [header.index(c) for c in _PII_BLANK_COLUMNS if c in header]
    n = 0
    for s in gradebook.students:
        cid = s.canvas_id.strip()
        if not cid.isdigit():
            continue
        code = deid_code_for(int(cid), prefix=prefix, hash_bits=hash_bits)
        s.raw[student_i] = code
        for i in blank_idx:
            if i < len(s.raw):
                s.raw[i] = ""
        n += 1
    return n


def main(argv=None) -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description="De-identify a Canvas gradebook CSV.")
    ap.add_argument("--input", type=Path, help="gradebook CSV (default: newest in ~/Downloads)")
    ap.add_argument("--course", help="filename hint to disambiguate ~/Downloads (e.g. DS_250)")
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="de-identified CSV output")
    ap.add_argument("--map", type=Path, default=_DEFAULT_MAP, help="re-id map JSON output (gitignored)")
    ap.add_argument("--prefix", default="S-", help="de-id code prefix (default S-)")
    ap.add_argument("--hash-bits", type=int, default=6, help="hex chars of hash in code (default 6)")
    args = ap.parse_args(argv)

    src = args.input or _file_finder.require_gradebook_csv(name_hint=args.course)
    gb = read_canvas_gradebook_csv(src)

    by_code = build_reid_map(gb, args.prefix, args.hash_bits)
    n = apply_deidentification(gb, by_code, args.prefix, args.hash_bits)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.map.parent.mkdir(parents=True, exist_ok=True)
    write_canvas_gradebook_csv(gb, args.out)
    args.map.write_text(
        json.dumps(
            {"version": 1, "prefix": args.prefix, "hash_bits": args.hash_bits, "by_code": by_code},
            indent=2,
        ),
        encoding="utf-8",
    )
    # FERPA: counts + paths only, never a name.
    print(f"✓ de-identified {n} students")
    print(f"  de-identified CSV: {args.out}")
    print(f"  re-id map (gitignored): {args.map}")
    print("  Upload to Canvas ONLY after re-identifying: grader_reidentify_gradebook.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

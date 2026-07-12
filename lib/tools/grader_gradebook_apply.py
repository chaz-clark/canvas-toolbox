#!/usr/bin/env python3
"""
Apply graded scores to a Canvas gradebook CSV for offline upload (Sprint 3).

WHY
  Offline (no API token) the grading pipeline can't PUT scores via
  grader_push.py. Instead, write the scores into the gradebook CSV and upload
  via Grades → Import. This is the offline "scores → CSV" path.

INPUT — a simple scores CSV: two columns `key,score` (header required).
  The `key` is resolved against the gradebook roster three ways, in this order:
    - all digits           -> Canvas user id (the gradebook `ID` column)
    - starts with `S-`      -> de-id code (deid_code_for(user_id), matched over
                               the roster) — the same codes Sprint 2 writes, so
                               a de-identified grading run maps straight back
    - otherwise             -> the `Student` name (exact match)
  Unresolved keys are a HARD ERROR — a dropped score must never pass silently.

COMMENTS are not written here: Canvas gradebook import is scores-only. Push
  comments via grader_push_comments.py when a token exists, or paste
  feedback/_all_comments.md into SpeedGrader.

USAGE
  uv run python lib/tools/grader_gradebook_apply.py \
    --scores grading/kc1/scores.csv --assignment-id 16846723 \
    --gradebook ~/Downloads/2026-07-12T1053_Grades-DS_250.csv \
    --out ~/Desktop/grades_for_upload.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

from _csv_utils import read_canvas_gradebook_csv, write_canvas_gradebook_csv
from build_deid_master import deid_code_for
import _file_finder


def resolve_target_assignment(gradebook, assignment_id=None, assignment_name=None):
    """Return the AssignmentColumn matching id or name, or raise."""
    if assignment_id:
        a = gradebook.assignment_by_id(str(assignment_id))
        if a is None:
            raise ValueError(f"no assignment column with id {assignment_id!r}")
        return a
    if assignment_name:
        matches = [a for a in gradebook.assignments if a.name == assignment_name]
        if len(matches) != 1:
            raise ValueError(
                f"assignment name {assignment_name!r} matched {len(matches)} columns; "
                f"use --assignment-id"
            )
        return matches[0]
    raise ValueError("provide --assignment-id or --assignment-name")


def build_roster_index(gradebook, prefix="S-", hash_bits=6) -> dict:
    """Return {'by_id':..., 'by_code':..., 'by_name':...} mapping each key form
    to the StudentRow, for offline score resolution."""
    by_id, by_code, by_name = {}, {}, {}
    for s in gradebook.students:
        cid = s.canvas_id.strip()
        by_name[s.student.strip()] = s
        if cid.isdigit():
            by_id[cid] = s
            by_code[deid_code_for(int(cid), prefix=prefix, hash_bits=hash_bits)] = s
    return {"by_id": by_id, "by_code": by_code, "by_name": by_name}


def resolve_student(key: str, index: dict, prefix="S-"):
    """Resolve one scores-CSV key to a StudentRow, or None."""
    key = key.strip()
    if key.isdigit():
        return index["by_id"].get(key)
    if key.startswith(prefix):
        return index["by_code"].get(key)
    return index["by_name"].get(key)


def read_scores_csv(path) -> list[tuple[str, str]]:
    """Read a `key,score` CSV into [(key, score)]. Skips blank rows."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError(f"{path} is empty")
    out = []
    for r in rows[1:]:  # skip header
        if len(r) >= 2 and r[0].strip():
            out.append((r[0].strip(), r[1].strip()))
    return out


def apply_scores(gradebook, assignment, scores, index, prefix="S-") -> list[str]:
    """Set the assignment cell for each resolved student. Returns the list of
    unresolved keys (empty = all applied)."""
    unresolved = []
    for key, score in scores:
        s = resolve_student(key, index, prefix=prefix)
        if s is None:
            unresolved.append(key)
            continue
        s.set_grade(assignment.assignment_id, score)
    return unresolved


def main(argv=None) -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description="Apply scores to a Canvas gradebook CSV (offline).")
    ap.add_argument("--scores", type=Path, required=True, help="key,score CSV")
    ap.add_argument("--gradebook", type=Path, help="gradebook CSV (default: newest in ~/Downloads)")
    ap.add_argument("--course", help="filename hint to disambiguate ~/Downloads")
    ap.add_argument("--assignment-id", help="target assignment id (from the gradebook column header)")
    ap.add_argument("--assignment-name", help="target assignment name (exact)")
    ap.add_argument("--out", type=Path, required=True, help="updated gradebook CSV for Canvas upload")
    ap.add_argument("--prefix", default="S-", help="de-id code prefix (default S-)")
    args = ap.parse_args(argv)

    src = args.gradebook or _file_finder.require_gradebook_csv(name_hint=args.course)
    gb = read_canvas_gradebook_csv(src)
    assignment = resolve_target_assignment(gb, args.assignment_id, args.assignment_name)
    scores = read_scores_csv(args.scores)
    index = build_roster_index(gb, prefix=args.prefix)
    unresolved = apply_scores(gb, assignment, scores, index, prefix=args.prefix)

    if unresolved:
        print(
            f"✗ {len(unresolved)} score(s) did not match any student "
            f"(e.g. {unresolved[0]!r}). Aborting — no CSV written.",
            file=sys.stderr,
        )
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_canvas_gradebook_csv(gb, args.out)
    print(f"✓ applied {len(scores)} scores to '{assignment.name}' ({assignment.assignment_id})")
    print(f"  upload-ready gradebook: {args.out}")
    print("  Upload via Canvas: Grades → Import")
    print("  Comments (scores-only CSV can't carry them): grader_push_comments.py "
          "if you have a token, else paste feedback/_all_comments.md into SpeedGrader.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

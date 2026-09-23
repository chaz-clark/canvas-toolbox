#!/usr/bin/env python3
"""
local_feedback_join.py — join student names into agent-drafted feedback for a
course with no Canvas API (#339 Phase A).

WHY THIS EXISTS
  The existing FERPA de-id/re-id pipeline (build_deid_master.py, the
  grader_deidentify_*.py family, grader_reidentify.py) assumes a Canvas course:
  submissions fetched via the API, renamed to opaque codes as they land on
  disk. A course on another LMS with no API (Brightspace/D2L, no downloadable
  gradebook) has no fetch step to hook that renaming into — the instructor's
  notes and roster are already local files, and nothing in the toolkit reads
  a roster itself and joins names back in at output time. So the agent is
  pushed toward reading the roster directly (forbidden) or the instructor
  joins names back in by hand, in their head, while risking a name landing
  next to a grade in whatever the agent drafts.

  This is the re-identify HALF only, matching grader_reidentify.py's exact
  boundary: reads the roster IN-PROCESS, never surfaces it, and the agent
  only ever sees the opaque code it put in its own results file. The
  de-identify half (splitting a mixed discussion export by its per-student
  separators, or renaming already-per-student submission files) is Phase B —
  deliberately not built here; see #339 for the follow-up.

WHAT COUNTS AS THE "CODE"
  The roster's own id column (default header "OrgDefinedId" — a D2L Classlist
  export's own identifier, not a name) IS the opaque code, the same role
  Canvas's user_id plays elsewhere in this project's FERPA convention ("refer
  to students only by user_id or deid_code"). No separate deid-master file:
  the roster CSV the operator already has is the map, and this tool is the
  only thing that ever reads it.

WHY FIRST NAME ONLY, WITH A COLLISION ESCAPE
  Requested capability, #339: student-facing output addresses each student by
  first name only by default. Where two-or-more students in the FULL roster
  share a first name (case-insensitive) — not just among the students in this
  run's results, so the same student's fallback name never changes from one
  run to the next — those specific students get "First L." (last initial)
  instead, everyone else stays first-name-only. This is the existing
  given-name-plus-initial convention (AGENTS.md FERPA discipline), narrowed
  to only the names that would actually be ambiguous.

WHY THE JOINED OUTPUT NEVER TOUCHES STDOUT
  This tool's own console output — dry run AND --apply — prints counts only,
  never a name. The agent is the thing running this tool and reading its
  stdout; a name in that output defeats the entire boundary as surely as
  reading the roster directly would. The joined, named text exists ONLY in
  the file --output writes, for the instructor to open themselves.

WHY AN UNMATCHED RESULT ROW REFUSES RATHER THAN SKIPS
  A results row whose code matches no roster row is a data-integrity problem,
  not a normal "not graded yet" gap (the reverse direction — a roster row with
  no results — is normal and simply produces no output line for that student).
  Guessing who an unmatched code belongs to is worse than refusing outright.

Usage:
  # dry run (default) — counts only, writes nothing
  uv run python lib/tools/local_feedback_join.py \\
      --roster classlist.csv --results feedback_results.csv --output out.csv

  # write the joined, named output file
  uv run python lib/tools/local_feedback_join.py \\
      --roster classlist.csv --results feedback_results.csv --output out.csv --apply

ROSTER CSV (D2L Classlist export by default; column names configurable)
  Required columns (header names, case-sensitive by default):
    --id-column         (default "OrgDefinedId")
    --first-name-column (default "FirstName")
    --last-name-column  (default "LastName")

RESULTS CSV (agent-produced — codes only, never names)
  Required columns:
    --results-id-column   (default "id") — must match a roster id-column value
    --results-text-column (default "text") — the agent-drafted feedback body

Exit codes:
  0  dry run, or --apply wrote the output file
  1  an unmatched results row, a missing required column, or an I/O error
  2  argument/configuration error
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

from __toolbox_version__ import __version__


def _read_csv_rows(path: Path, required: list[str]) -> tuple[list[dict], list[str]]:
    """(rows, header). Raises ValueError (caller turns into a clean exit 2) if
    a required column is missing — lists the actual headers found so a typo'd
    --id-column is obvious, never a silent KeyError deep in the join."""
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        missing = [c for c in required if c not in header]
        if missing:
            raise ValueError(
                f"{path}: missing column(s) {missing} — header found: {header}"
            )
        rows = list(reader)
    return rows, header


def load_roster(path: Path, id_col: str, first_col: str, last_col: str) -> dict[str, dict]:
    """{code: {"first": ..., "last": ...}}. The ONLY function in this tool
    that reads name fields — everything downstream works with codes and the
    resolved display name, never raw roster rows."""
    rows, _ = _read_csv_rows(path, [id_col, first_col, last_col])
    roster: dict[str, dict] = {}
    for row in rows:
        code = (row.get(id_col) or "").strip()
        if not code:
            continue
        roster[code] = {
            "first": (row.get(first_col) or "").strip(),
            "last": (row.get(last_col) or "").strip(),
        }
    return roster


def resolve_display_names(roster: dict[str, dict]) -> dict[str, str]:
    """{code: display_name}. First name alone, UNLESS this first name (case-
    insensitive) belongs to 2+ students anywhere in the roster — then "First
    L." for exactly those students. Computed against the whole roster, not
    just matched results, so a student's display name is stable run to run."""
    by_first: dict[str, list[str]] = {}
    for code, entry in roster.items():
        key = entry["first"].casefold()
        if not key:
            continue
        by_first.setdefault(key, []).append(code)

    display: dict[str, str] = {}
    for code, entry in roster.items():
        first = entry["first"]
        if not first:
            display[code] = "(no first name on file)"
            continue
        collides = len(by_first.get(first.casefold(), [])) > 1
        if collides and entry["last"]:
            display[code] = f"{first} {entry['last'][0].upper()}."
        else:
            display[code] = first
    return display


def load_results(path: Path, id_col: str, text_col: str) -> list[dict]:
    rows, _ = _read_csv_rows(path, [id_col, text_col])
    return [{"code": (r.get(id_col) or "").strip(), "text": r.get(text_col) or ""}
           for r in rows if (r.get(id_col) or "").strip()]


def join_feedback(roster: dict[str, dict], results: list[dict]) -> tuple[list[dict], list[str]]:
    """(joined_rows, unmatched_codes). joined_rows: [{"code", "name", "text"}],
    in results order. unmatched_codes: results codes with no roster match —
    non-empty means the caller must refuse, not write a partial file."""
    display = resolve_display_names(roster)
    joined: list[dict] = []
    unmatched: list[str] = []
    for row in results:
        code = row["code"]
        if code not in roster:
            unmatched.append(code)
            continue
        joined.append({"code": code, "name": display[code], "text": row["text"]})
    return joined, unmatched


def write_output(path: Path, joined: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "text"])
        writer.writeheader()
        for row in joined:
            writer.writerow(row)


def main() -> int:
    force_utf8_console()  # #123

    ap = argparse.ArgumentParser(
        description="Join student names into agent-drafted, code-keyed feedback "
                    "for a course with no Canvas API (#339). Reads the roster "
                    "in-process; never prints a name to stdout.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--roster", required=True, type=Path, metavar="PATH",
                    help="D2L Classlist (or similar) roster CSV.")
    ap.add_argument("--results", required=True, type=Path, metavar="PATH",
                    help="Agent-produced CSV, keyed by roster id — codes only, no names.")
    ap.add_argument("--output", required=True, type=Path, metavar="PATH",
                    help="Where the joined, named output CSV is written. Never printed.")
    ap.add_argument("--id-column", default="OrgDefinedId")
    ap.add_argument("--first-name-column", default="FirstName")
    ap.add_argument("--last-name-column", default="LastName")
    ap.add_argument("--results-id-column", default="id")
    ap.add_argument("--results-text-column", default="text")
    ap.add_argument("--apply", action="store_true",
                    help="Write the output file. Without this the run is a dry run.")
    args = ap.parse_args()

    try:
        roster = load_roster(args.roster, args.id_column,
                             args.first_name_column, args.last_name_column)
    except (ValueError, OSError) as e:
        print(f"ERROR reading roster: {e}", file=sys.stderr)
        return 2
    try:
        results = load_results(args.results, args.results_id_column, args.results_text_column)
    except (ValueError, OSError) as e:
        print(f"ERROR reading results: {e}", file=sys.stderr)
        return 2

    joined, unmatched = join_feedback(roster, results)

    print(f"roster: {len(roster)} students")
    print(f"results: {len(results)} rows")
    print(f"matched: {len(joined)}")
    print(f"roster students with no results this run: {len(roster) - len(joined)}")
    if unmatched:
        print(f"UNMATCHED results codes (no roster row — not a name, safe to print): "
              f"{unmatched}", file=sys.stderr)
        print("\nERROR: refusing to write a partial join — every results code must "
              "match a roster row. Fix the code(s) above and re-run.", file=sys.stderr)
        return 1

    if not args.apply:
        print(f"\nDry run — would write {len(joined)} row(s) to {args.output}. "
              "Re-run with --apply.")
        return 0

    try:
        write_output(args.output, joined)
    except OSError as e:
        print(f"ERROR writing output: {e}", file=sys.stderr)
        return 1
    print(f"\n✓ wrote {len(joined)} row(s) to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

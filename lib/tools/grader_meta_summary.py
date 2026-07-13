#!/usr/bin/env python3
"""
Cross-task meta-summary: given N task directories, emit a per-uid matrix
of `task → score / band / flag` plus per-uid aggregates (tasks seen,
flag-streak length, tier mix).

Sub-item C of canvas-toolbox#54. The strongest signal from m119 SP26
calibration emerged from eyeballing cohort outputs side-by-side: uid
533831's 6-task FLAG streak; uid 720315's calibration arc (P1T1 Rule 2
violation → P1T2-P2T2 clean); uid 886517's 5-task transparent-Tier-3
pattern. No tool computed those patterns — they came from manual reads.
This automates the cross-task view so the patterns scale beyond the
operator's eyeball time.

INPUT
  Multiple task dirs via either `--task-dirs <dir1>,<dir2>,...` (explicit
  list) OR `--cohort-glob 'grading/p*'` (glob pattern). Both modes accept
  the canonical layout produced by grader_scaffold.py (#54 sub-A):

    <task-dir>/
        .keymap.json             OR each surface subdir has its own
        feedback/_summary.csv    consensus output (preferred)
        feedback/_grader1.csv    single-pass fallback
        _userid_key_grade_join.json (optional — from #54-B; replaces
                                    keymap + grade-CSV scan)

  Score CSV is expected to have columns: `key`, `score` (numeric or
  band-name), and optionally `flagged` / `band` / `tier`. Column choice
  is configurable via --score-column.

OUTPUT
  - Stdout: a wide table (uid × task → score), plus a per-uid summary
    column (tasks completed, flag streak).
  - `--out <path>`: same table as JSON or CSV via --format.
  - Per-uid aggregates:
      tasks_seen        count of task dirs the uid appears in
      flag_streak_max   longest run of "flagged" task results
      flag_total        total flagged tasks
      band_distribution {band: count}

  Console: aggregate counts only — never names.

FERPA
  - Reads .keymap.json (gitignored) + the grader's CSV outputs (already
    keyed — no names).
  - Output keyed by user_id (LMS row id — safe per the toolkit's
    standing rule). NO names.
  - canvas_course_guard not involved — local-only file scan.

USAGE
  # Glob mode (one cohort's tasks)
  uv run python lib/tools/grader_meta_summary.py
      --cohort-glob 'grading/p*'

  # Explicit list
  uv run python lib/tools/grader_meta_summary.py
      --task-dirs grading/p1t1_combined,grading/p1t2_combined,grading/p2t1_ai_log

  # Pull a different scoring source per cohort
  uv run python lib/tools/grader_meta_summary.py
      --cohort-glob 'grading/kc*' --score-file feedback/_grader1.csv

EXIT CODES
  0  emitted summary (any zero-result task is reported in the text)
  2  no task dirs found / unresolvable layout
"""
from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import csv
import glob
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

# Issue #73: handle TWO filename conventions:
#  1. grader_fetch (`<prefix>_<uid>.<ext>`) — uid is the LAST digit block
#     before the extension; tolerate optional whitespace (`kc1_ 33619.html`).
#  2. Canvas bulk download (`lastfirst_<uid>_<subid>_<title>.ext`) —
#     uid is the FIRST 3+ digit block flanked by underscores.
# Pre-fetch keymaps (created from Canvas's bulk download path) carry
# shape #2; new fetch-driven keymaps carry shape #1. The same two-pass
# logic lives in grader_join.extract_uid — keep in sync.
_UID_FETCH_RE = re.compile(r"_\s*(\d+)\.[A-Za-z0-9]+$")
_UID_BULK_RE = re.compile(r"_\s*(\d{3,})_")


def _uid_from_filename(filename: str) -> int | None:
    s = filename or ""
    m = _UID_FETCH_RE.search(s)
    if m:
        return int(m.group(1))
    m = _UID_BULK_RE.search(s)
    return int(m.group(1)) if m else None


def _looks_flagged(row: dict, score_col: str) -> bool:
    """Heuristic: a row is flagged when explicit columns say so, OR when
    the score column carries a band/tier name in {Fail, FLAG, 0, Tier 1,
    Outsourcing}. Conservative — false-positive flags here are cheap
    (one row in a table); false-negative streaks are the actual harm."""
    for k in ("flagged", "needs_review", "flag"):
        v = (row.get(k) or "").strip().lower()
        if v in ("1", "true", "yes", "y", "flag", "flagged"):
            return True
    score = (row.get(score_col) or "").strip().lower()
    if score in ("fail", "flag", "flagged"):
        return True
    if score in ("0", "0.0", "0.00"):
        return True
    if "outsourcing" in score:
        return True
    if "tier 1" in score or "tier-1" in score:
        return True
    return False


# ---------------------------------------------------------------------------
# Task-dir scanning
# ---------------------------------------------------------------------------

def _resolve_task_dirs(args) -> list[Path]:
    dirs: list[Path] = []
    if args.task_dirs:
        for d in args.task_dirs.split(","):
            d = d.strip()
            if not d:
                continue
            p = Path(d)
            if p.is_dir():
                dirs.append(p)
            else:
                print(f"WARN: --task-dirs path not a directory, skipping: {d}", file=sys.stderr)
    if args.cohort_glob:
        # Issue #71: argparse `action="append"` gives a list of patterns.
        # Single-use still works (one-element list).
        for pattern in args.cohort_glob:
            for d in sorted(glob.glob(pattern)):
                p = Path(d)
                if p.is_dir():
                    dirs.append(p)
    # Dedup preserving order
    seen: set = set()
    uniq: list[Path] = []
    for p in dirs:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq


def _surface_dirs(task_dir: Path) -> list[Path]:
    """A multi-surface task has each surface as a subdir with its own
    .keymap.json. A single-surface task has the keymap at task-dir root.
    Returns the list of dirs we should read scoring from."""
    own = task_dir / ".keymap.json"
    if own.exists():
        return [task_dir]
    return [child for child in sorted(task_dir.iterdir())
            if child.is_dir() and (child / ".keymap.json").exists()]


def _read_keymap_uid_index(surface_dir: Path) -> dict[str, int]:
    """{key: user_id} via the <prefix>_<uid>.<ext> (grader_fetch) OR
    `lastfirst_<uid>_<subid>_<title>.ext` (Canvas bulk download)
    convention. Issue #73: warn loudly when a keymap has entries but
    NONE resolve — silent mis-resolution (returning None and producing
    an empty matrix) is worse than failing loudly. Operator either
    re-fetches the cohort to get fetch-shape filenames or extends the
    resolver."""
    p = surface_dir / ".keymap.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    keymap = raw.get("map", {}) if isinstance(raw, dict) else {}
    out: dict[str, int] = {}
    for key, fname in keymap.items():
        uid = _uid_from_filename(fname)
        if uid is not None:
            out[key] = uid
    if keymap and not out:
        print(f"WARN: {surface_dir}/.keymap.json has {len(keymap)} entries but 0 "
              f"resolved to user_ids — filenames don't match grader_fetch "
              f"(`<prefix>_<uid>.<ext>`) OR Canvas bulk-download "
              f"(`lastfirst_<uid>_<subid>_<title>.ext`) shape. Re-fetch via "
              f"grader_fetch.py or extend `_uid_from_filename`.",
              file=sys.stderr)
    return out


def _read_score_rows(surface_dir: Path, score_file: str, score_col: str) -> list[dict]:
    p = surface_dir / score_file
    if not p.is_file():
        # Try the alternative
        alt = surface_dir / ("feedback/_grader1.csv" if score_file == "feedback/_summary.csv"
                             else "feedback/_summary.csv")
        if alt.is_file():
            p = alt
        else:
            return []
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _row_uid(row: dict, key_to_uid: dict[str, int]) -> int | None:
    """Issue #70: bind a score-CSV row to a user_id. The toolkit's canonical
    shape is `key`-keyed (output of grader_consensus / grader_grade), but
    multi-surface synthesis CSVs (m119's `<task>_combined/feedback/
    _grader1.csv`) are `user_id`-keyed because one row collapses both
    surfaces. Try `key` first; fall back to `user_id` if present."""
    key = (row.get("key") or "").strip()
    if key:
        uid = key_to_uid.get(key)
        if uid is not None:
            return uid
    uid_str = (row.get("user_id") or "").strip()
    if uid_str.isdigit():
        return int(uid_str)
    return None


def collect_matrix(task_dirs: list[Path], score_file: str, score_col: str) -> dict:
    """Returns:
      {
        "tasks":   [task_label, ...],
        "by_uid":  {uid: {task_label: {key, score, flagged}}},
        "missing_score_tasks": [...],  # tasks that lacked a score CSV
      }

    Layout handling (issue #69, Path B):
      - A task with surface subdirs AND a task-level feedback CSV (e.g.
        m119's `<task>_combined/feedback/_grader1.csv`) emits ONE entry
        per task. Keys in the task-level CSV are resolved against the
        UNION of all surface keymaps. The synthesis IS at task level.
      - A task with surface subdirs and per-surface feedback CSVs emits
        one entry per surface (existing behavior).
      - A single-surface task (keymap at task root) emits one entry per
        task (existing behavior).
    """
    tasks: list[str] = []
    by_uid: dict[int, dict[str, dict]] = defaultdict(dict)
    missing_score_tasks: list[str] = []

    for task in task_dirs:
        surfaces = _surface_dirs(task)
        if not surfaces:
            print(f"WARN: no .keymap.json in {task} or any subdir; skipping.", file=sys.stderr)
            continue

        # Issue #69 Path B: prefer task-level feedback when surface-level
        # is absent (or empty) AND the task has surface subdirs.
        task_level_rows: list[dict] = []
        if not (len(surfaces) == 1 and surfaces[0] == task):
            # Multi-surface task — check for task-level CSV first
            task_level_rows = _read_score_rows(task, score_file, score_col)

        if task_level_rows:
            label = task.name
            tasks.append(label)
            # Union of all surface keymaps for key→uid lookup. Cohort
            # synthesis CSVs (m119-style) are user_id-keyed; the
            # _row_uid helper handles both shapes (#70).
            key_to_uid: dict[str, int] = {}
            for sd in surfaces:
                key_to_uid.update(_read_keymap_uid_index(sd))
            for row in task_level_rows:
                uid = _row_uid(row, key_to_uid)
                if uid is None:
                    continue
                by_uid[uid][label] = {
                    "key": (row.get("key") or "").strip(),
                    "score": (row.get(score_col) or "").strip(),
                    "flagged": _looks_flagged(row, score_col),
                }
            continue

        for sd in surfaces:
            label = task.name if sd == task else f"{task.name}/{sd.name}"
            tasks.append(label)
            key_to_uid = _read_keymap_uid_index(sd)
            rows = _read_score_rows(sd, score_file, score_col)
            if not rows:
                missing_score_tasks.append(label)
                continue
            for row in rows:
                uid = _row_uid(row, key_to_uid)
                if uid is None:
                    continue
                by_uid[uid][label] = {
                    "key": (row.get("key") or "").strip(),
                    "score": (row.get(score_col) or "").strip(),
                    "flagged": _looks_flagged(row, score_col),
                }
    return {"tasks": tasks, "by_uid": dict(by_uid),
            "missing_score_tasks": missing_score_tasks}


# ---------------------------------------------------------------------------
# Per-uid aggregates
# ---------------------------------------------------------------------------

def _flag_streak(tasks: list[str], uid_data: dict[str, dict]) -> int:
    """Longest run of consecutive flagged results across the ordered task list."""
    best = cur = 0
    for t in tasks:
        cell = uid_data.get(t)
        if cell and cell.get("flagged"):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def compute_aggregates(matrix: dict) -> dict:
    tasks = matrix["tasks"]
    out: dict[int, dict] = {}
    for uid, uid_data in matrix["by_uid"].items():
        bands: dict[str, int] = {}
        for cell in uid_data.values():
            band = cell.get("score") or "?"
            bands[band] = bands.get(band, 0) + 1
        out[uid] = {
            "tasks_seen": len(uid_data),
            "flag_streak_max": _flag_streak(tasks, uid_data),
            "flag_total": sum(1 for c in uid_data.values() if c.get("flagged")),
            "band_distribution": bands,
        }
    return out


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def render_text(matrix: dict, aggregates: dict, *, max_text_width: int = 14) -> str:
    tasks = matrix["tasks"]
    by_uid = matrix["by_uid"]
    out: list[str] = []
    out.append(f"== grader_meta_summary  tasks={len(tasks)}  uids={len(by_uid)} ==")
    if matrix["missing_score_tasks"]:
        out.append(f"WARN: {len(matrix['missing_score_tasks'])} task(s) had no score CSV: "
                   f"{matrix['missing_score_tasks'][:3]}{'...' if len(matrix['missing_score_tasks']) > 3 else ''}")
    out.append("")

    def trim(s: str) -> str:
        return (s or "")[:max_text_width]

    header = ["uid"] + [trim(t) for t in tasks] + ["seen", "streak", "flag_total"]
    out.append("  " + "  ".join(f"{c:>{max_text_width}}" for c in header))

    # Sort by flag_streak DESC then uid (the highest-signal rows first)
    sorted_uids = sorted(by_uid, key=lambda u: (-aggregates[u]["flag_streak_max"], u))
    for uid in sorted_uids:
        cells = [str(uid)]
        for t in tasks:
            cell = by_uid[uid].get(t)
            cells.append(trim(cell["score"]) if cell else "-")
        agg = aggregates[uid]
        cells += [str(agg["tasks_seen"]), str(agg["flag_streak_max"]), str(agg["flag_total"])]
        out.append("  " + "  ".join(f"{c:>{max_text_width}}" for c in cells))
    return "\n".join(out)


def render_csv(matrix: dict, aggregates: dict) -> str:
    tasks = matrix["tasks"]
    buf = io.StringIO()
    fieldnames = ["user_id"] + tasks + ["tasks_seen", "flag_streak_max", "flag_total"]
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for uid, uid_data in matrix["by_uid"].items():
        row: dict[str, object] = {"user_id": uid}
        for t in tasks:
            cell = uid_data.get(t)
            row[t] = cell["score"] if cell else ""
        agg = aggregates[uid]
        row["tasks_seen"] = agg["tasks_seen"]
        row["flag_streak_max"] = agg["flag_streak_max"]
        row["flag_total"] = agg["flag_total"]
        w.writerow(row)
    return buf.getvalue()


def render_json(matrix: dict, aggregates: dict) -> str:
    return json.dumps({
        "tasks": matrix["tasks"],
        "missing_score_tasks": matrix["missing_score_tasks"],
        "rows": [
            {"user_id": uid, "per_task": matrix["by_uid"][uid], "aggregates": aggregates[uid]}
            for uid in sorted(matrix["by_uid"])
        ],
    }, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Cross-task meta-summary: uid × task matrix + flag-streak + band "
                    "distribution per uid (canvas-toolbox#54 sub-C).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--task-dirs", default=None,
                    help="Comma-separated explicit task dirs.")
    ap.add_argument("--cohort-glob", default=None, action="append",
                    help="Glob pattern (e.g. 'grading/p*'). Issue #71: pass multiple times to "
                         "include multiple prefixes (e.g. --cohort-glob 'grading/p1t*' "
                         "--cohort-glob 'grading/p2t*'). Combined with --task-dirs if both.")
    ap.add_argument("--score-file", default="feedback/_summary.csv",
                    help="Path within each surface dir to the score CSV. Defaults to "
                         "feedback/_summary.csv (consensus output); falls back to "
                         "feedback/_grader1.csv when the consensus file is missing.")
    ap.add_argument("--score-column", default="score",
                    help="Column name in the score CSV. Default: 'score'.")
    ap.add_argument("--out", default=None,
                    help="Output file path. Default: stdout.")
    ap.add_argument("--format", choices=("text", "csv", "json"), default="text")
    args = ap.parse_args()

    if not args.task_dirs and not args.cohort_glob:
        print("Pass --task-dirs OR --cohort-glob.", file=sys.stderr)
        return 2

    task_dirs = _resolve_task_dirs(args)
    if not task_dirs:
        print("No task dirs resolved.", file=sys.stderr)
        return 2

    matrix = collect_matrix(task_dirs, args.score_file, args.score_column)
    aggregates = compute_aggregates(matrix)

    if args.format == "csv":
        body = render_csv(matrix, aggregates)
    elif args.format == "json":
        body = render_json(matrix, aggregates)
    else:
        body = render_text(matrix, aggregates)

    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
        print(f"  -> {args.out}", file=sys.stderr)
    else:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

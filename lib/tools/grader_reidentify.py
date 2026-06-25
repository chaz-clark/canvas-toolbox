#!/usr/bin/env python3
"""
Re-identify grading results for the instructor's LOCAL review.

Part of the canvas-toolbox generic grader skill (v0.1). See:
  - lib/agents/canvas_grader.md (operator-facing pipeline guide)
  - lib/agents/knowledge/grader_knowledge.md §1 (FERPA two-zone architecture)

WHAT IT DOES
  Joins the key→name map (.keymap.json) with the agent's keyed feedback summary
  (feedback/_summary.csv or whichever summary was emitted by the grading passes)
  into a single review sheet (.review.csv) showing, per student: original filename,
  key, recommended score, one-line reason, and the feedback file to read.

  WHO RUNS THIS: the instructor, LOCALLY. The grading AI NEVER runs this and NEVER
  reads its output. Recommended scores are just that — recommendations. The
  instructor reviews feedback + originals, makes the final call, sets the
  final_grade column, then either runs grader_push.py with the marker set or
  records the grade in Canvas manually.

FERPA
  .keymap.json and .review.csv hold names and MUST be gitignored in the consumer
  course repo. This script prints ONLY counts and the output path — never a name —
  so it's safe to run in a shared terminal.

USAGE
  # Conventional layout
  uv run python lib/tools/grader_reidentify.py --challenge-dir grading/kc1

  # Multi-output: distinct review sheets per output
  uv run python lib/tools/grader_reidentify.py --challenge-dir grading/mid_review \\
    --summary feedback/_summary_did_the_review.csv --out .review_did_the_review.csv

GENERALIZED FROM: ds460-master/grading/reidentify.py
(commits 754c966..91a5113 — round-1 KC1 beta).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from _challenge_dir_guard import resolve_challenge_dir  # issue #44 FERPA guard

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"


# Issue #100: filename → user_id parser. Matches the same shape that
# grader_fetch writes to submissions_raw/: <prefix>_<uid>(_<suffix>)?.<ext>.
_FILENAME_UID_RE = re.compile(
    r"^(?P<prefix>[A-Za-z0-9-]+)_(?P<uid>\d+)(?:_[A-Za-z0-9]+)?\.[A-Za-z0-9.]+$"
)


def build_user_to_keys(keymap: dict[str, str]) -> dict[int, list[str]]:
    """Issue #100: invert the keymap from key→filename to user_id→[keys].

    A multi-attachment submission produces multiple files for the same
    user_id, hence the list. Order preserved in iteration order of the
    input keymap.
    """
    out: dict[int, list[str]] = {}
    for key, filename in keymap.items():
        m = _FILENAME_UID_RE.match(filename or "")
        if not m:
            continue
        try:
            uid = int(m.group("uid"))
        except (TypeError, ValueError):
            continue
        out.setdefault(uid, []).append(key)
    return out


def pick_group_representatives_from_context(
    group_context: dict, user_to_keys: dict[int, list[str]]
) -> dict[int, int]:
    """Issue #100: derive group_id → rep_uid from the embedded fetch-log
    group_context. The rep is the smallest user_id among submitters in
    that group (mirrors grader_fetch.pick_group_representatives).
    """
    user_to_group = group_context.get("user_to_group", {})
    # Build group_id → list of submitting uids
    by_group: dict[int, list[int]] = {}
    for uid_str, ctx in user_to_group.items():
        try:
            uid = int(uid_str)
        except (TypeError, ValueError):
            continue
        if uid not in user_to_keys:
            continue  # uid has no submission keys → didn't submit
        gid = ctx.get("group_id")
        if gid is None:
            continue
        by_group.setdefault(gid, []).append(uid)
    return {gid: sorted(uids)[0] for gid, uids in by_group.items() if uids}


def mirror_group_rows(
    rows: list[dict],
    group_context: dict | None,
    user_to_keys: dict[int, list[str]],
    summary_by_key: dict[str, dict],
    feedback_dir: Path,
) -> list[dict]:
    """Issue #100: when a group assignment is in shared-grade mode, copy
    the representative's score + reason + feedback file to mirrored
    member rows. Adds a `group_mirror_of` column showing the source key
    (empty for rep rows, non-group rows, or individual-grade-mode rows).

    Modifies and returns the same list (in-place mutation for caller
    simplicity). Pure logic — no file I/O beyond feedback_file existence
    check.
    """
    # Default: stamp empty group_mirror_of on every row
    for r in rows:
        r.setdefault("group_mirror_of", "")

    if not group_context:
        return rows
    if group_context.get("grade_group_students_individually"):
        return rows  # individual grade — no mirroring

    representatives = pick_group_representatives_from_context(
        group_context, user_to_keys
    )

    # Build key → rep_key lookup
    key_to_rep_key: dict[str, str] = {}
    user_to_group = group_context.get("user_to_group", {})
    for uid_str, ctx in user_to_group.items():
        try:
            uid = int(uid_str)
        except (TypeError, ValueError):
            continue
        gid = ctx.get("group_id")
        rep_uid = representatives.get(gid)
        if rep_uid is None or rep_uid == uid:
            continue  # rep row is itself the source; skip mirroring
        rep_keys = user_to_keys.get(rep_uid, [])
        if not rep_keys:
            continue
        rep_key = rep_keys[0]  # first attachment is canonical
        for key in user_to_keys.get(uid, []):
            key_to_rep_key[key] = rep_key

    # Apply mirroring
    for r in rows:
        rep_key = key_to_rep_key.get(r["key"])
        if not rep_key:
            continue
        rep_data = summary_by_key.get(rep_key)
        if not rep_data:
            continue
        r["recommended_score"] = rep_data.get("score", r["recommended_score"])
        r["reason"] = rep_data.get("one_line_reason", r["reason"])
        rep_fb = feedback_dir / f"{rep_key}.md"
        r["feedback_file"] = str(rep_fb) if rep_fb.exists() else "(missing)"
        r["group_mirror_of"] = rep_key
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-attach names to grading scores for LOCAL instructor review.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", dest="challenge_dir", default=None,
                    help="Convention base path (e.g. grading/kc1). Holds .keymap.json + feedback/.")
    ap.add_argument("--map", dest="mapfile", default=None,
                    help="Path to .keymap.json (default: <challenge-dir>/.keymap.json)")
    ap.add_argument("--summary", default="feedback/_summary.csv",
                    help="Keyed summary CSV (key,score,one_line_reason), relative to --challenge-dir. "
                         "Default: feedback/_summary.csv")
    ap.add_argument("--out", default=".review.csv",
                    help="Review sheet to write, relative to --challenge-dir. Use distinct names for "
                         "multi-output assignments. Default: .review.csv")
    args = ap.parse_args()

    if not args.challenge_dir:
        print("Missing --challenge-dir.", file=sys.stderr)
        return 1

    base = resolve_challenge_dir(args.challenge_dir, verb="reidentifying in")
    mapfile = Path(args.mapfile) if args.mapfile else base / ".keymap.json"
    summary = base / args.summary
    out = base / args.out

    if not mapfile.exists():
        print(f"No key map at {mapfile} — run a grader_deidentify_* tool first.")
        return 1
    if not summary.exists():
        print(f"No grading summary at {summary} — run the grader first (or pass --summary).")
        return 1

    keymap = json.loads(mapfile.read_text(encoding="utf-8")).get("map", {})
    scores: dict[str, dict] = {}
    with summary.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            scores[row.get("key", "")] = row

    fbdir = base / "feedback"
    rows = []
    for key, filename in sorted(keymap.items()):
        s = scores.get(key, {})
        fb = fbdir / f"{key}.md"
        rows.append({
            "submission_file": filename,            # the real name lives here — local only
            "key": key,
            "recommended_score": s.get("score", "(not graded)"),
            "reason": s.get("one_line_reason", ""),
            "feedback_file": str(fb) if fb.exists() else "(missing)",
            "final_grade": "",                      # instructor fills in, then push or manual
            "group_mirror_of": "",                  # issue #100: filled in below if applicable
        })

    # Issue #100: if .fetch_log.json embedded a group_context (group
    # assignment in shared-grade mode), mirror the representative's
    # score + reason + feedback_file to group-mate rows so the operator
    # sees all members of the group with their (shared) grade.
    group_mirrored = 0
    fetch_log = base / ".fetch_log.json"
    if fetch_log.exists():
        try:
            fl = json.loads(fetch_log.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            fl = {}
        group_context = fl.get("group_context")
        if group_context:
            user_to_keys = build_user_to_keys(keymap)
            mirror_group_rows(rows, group_context, user_to_keys, scores, fbdir)
            group_mirrored = sum(1 for r in rows if r["group_mirror_of"])

    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["submission_file", "key", "recommended_score",
                                           "reason", "feedback_file", "final_grade",
                                           "group_mirror_of"])
        w.writeheader()
        w.writerows(rows)

    graded = sum(1 for r in rows if r["recommended_score"] not in ("(not graded)", ""))
    # FERPA: print counts + path only, never a name
    print(f"Review sheet -> {out}  ({len(rows)} students, {graded} with a recommended score)")
    if group_mirrored:
        print(f"  Issue #100: {group_mirrored} row(s) mirrored from group "
              f"representatives (shared-grade group assignment).")
    print("Open it locally, review feedback + originals, set final_grade, then either run "
          "grader_push.py (with --mark-reviewed) or record in Canvas manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

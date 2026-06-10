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
import sys
from pathlib import Path

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"


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

    base = Path(args.challenge_dir)
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

    rows = []
    for key, filename in sorted(keymap.items()):
        s = scores.get(key, {})
        fb = base / "feedback" / f"{key}.md"
        rows.append({
            "submission_file": filename,            # the real name lives here — local only
            "key": key,
            "recommended_score": s.get("score", "(not graded)"),
            "reason": s.get("one_line_reason", ""),
            "feedback_file": str(fb) if fb.exists() else "(missing)",
            "final_grade": "",                      # instructor fills in, then push or manual
        })

    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["submission_file", "key", "recommended_score",
                                           "reason", "feedback_file", "final_grade"])
        w.writeheader()
        w.writerows(rows)

    graded = sum(1 for r in rows if r["recommended_score"] not in ("(not graded)", ""))
    # FERPA: print counts + path only, never a name
    print(f"Review sheet -> {out}  ({len(rows)} students, {graded} with a recommended score)")
    print("Open it locally, review feedback + originals, set final_grade, then either run "
          "grader_push.py (with --mark-reviewed) or record in Canvas manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

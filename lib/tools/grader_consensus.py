#!/usr/bin/env python3
"""
N-grader consensus: majority score + spread + auto-flag for NEEDS-REVIEW.

Part of the canvas-toolbox generic grader skill (v0.1). See:
  - lib/agents/canvas_grader.md (operator-facing pipeline guide)
  - lib/agents/knowledge/grader_knowledge.md §4 (consensus + confidence-driven review queue)

WHAT IT DOES
  Each grader pass writes a CSV of `key,score` to <challenge-dir>/feedback/_grader*.csv
  (one per pass). This reads them and per submission computes scores, consensus,
  spread (max-min), and flags NEEDS-REVIEW when spread ≥ threshold.

  CONSENSUS = MAJORITY: the score ≥2 of N graders agree on wins. If all differ,
  fall back to the median.

WHY
  Holistic scoring varies between graders. Three-grader consensus is the cheapest
  configuration that gives majority rule (two can't break ties; five+ hits
  diminishing returns at 3× token cost). The spread is itself a signal — high-spread
  cases are precisely the borderlines a human should see.

USAGE
  # Conventional layout (default flag threshold 0.5)
  uv run python lib/tools/grader_consensus.py --challenge-dir grading/kc1

  # Tune the spread threshold for a different scale
  uv run python lib/tools/grader_consensus.py --challenge-dir grading/kc1 --flag 1.0

GENERALIZED FROM: ds460-master/grading/consensus.py
(commits 754c966..91a5113 — round-1 KC1 beta).
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import Counter
from pathlib import Path

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"


def load(path: Path) -> dict[str, float]:
    """Read a single grader's CSV. Expects columns `key,score`. Ignores rows with bad score."""
    out: dict[str, float] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                out[row["key"]] = float(row["score"])
            except (KeyError, ValueError):
                pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="N-grader consensus (majority + spread + NEEDS-REVIEW queue).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", dest="challenge_dir", default=None,
                    help="Convention base path (e.g. grading/kc1). Sets defaults for --feedback-dir / --out.")
    ap.add_argument("--feedback-dir", dest="feedback_dir", default=None,
                    help="Directory containing _grader*.csv (default: <challenge-dir>/feedback)")
    ap.add_argument("--out", dest="outfile", default=None,
                    help="Path to write consensus CSV (default: <feedback-dir>/_consensus.csv)")
    ap.add_argument("--flag", type=float, default=0.5,
                    help="Spread (max-min) at/above which to flag NEEDS-REVIEW. Default 0.5 (tune per scale).")
    args = ap.parse_args()

    if args.challenge_dir:
        cd = Path(args.challenge_dir)
        args.feedback_dir = args.feedback_dir or str(cd / "feedback")

    if not args.feedback_dir:
        print("Missing required arguments. Pass --challenge-dir OR --feedback-dir.", file=sys.stderr)
        return 1

    fb = Path(args.feedback_dir)
    gfiles = sorted(fb.glob("_grader*.csv"))
    if len(gfiles) < 2:
        print(f"Need >=2 grader files (_grader*.csv) in {fb}; found {len(gfiles)}.")
        return 1

    graders = [load(g) for g in gfiles]
    names = [g.stem.replace("_grader", "g") for g in gfiles]
    keys = sorted(set.intersection(*[set(g) for g in graders]))
    if not keys:
        print("No submissions graded by ALL graders.")
        return 1

    rows: list[dict] = []
    flagged: list[tuple[str, list[float], float, float]] = []
    exact = within25 = within50 = 0

    print(f"{'key':14} " + " ".join(f"{n:>5}" for n in names) +
          f" {'consensus':>9} {'spread':>7} {'flag':>5}")
    for k in keys:
        sc = [g[k] for g in graders]
        # MAJORITY RULE: the score ≥2 of N graders agree on wins. Else median.
        val, n_agree = Counter(sc).most_common(1)[0]
        consensus = val if n_agree >= 2 else statistics.median(sc)
        spread = max(sc) - min(sc)
        flag = spread >= args.flag
        if spread == 0:
            exact += 1
        if spread <= 0.25:
            within25 += 1
        if spread <= 0.5:
            within50 += 1
        if flag:
            flagged.append((k, sc, consensus, spread))
        rows.append({
            "key": k,
            **{names[i]: sc[i] for i in range(len(sc))},
            "consensus": consensus,
            "spread": spread,
            "needs_review": flag,
        })
        print(f"{k:14} " + " ".join(f"{x:>5}" for x in sc) +
              f" {consensus:>9} {spread:>7} {'YES' if flag else '':>5}")

    n = len(keys)
    print(f"\nConsistency over {n} submissions ({len(graders)} graders): "
          f"exact {exact}/{n}, within 0.25 {within25}/{n}, within 0.5 {within50}/{n}; "
          f"mean spread {statistics.mean(r['spread'] for r in rows):.2f}")
    if flagged:
        print(f"\nNEEDS-REVIEW queue (spread >= {args.flag}) — review these first:")
        for k, sc, con, sp in flagged:
            print(f"  {k}: graders {sc} -> consensus {con} (spread {sp})")

    out = Path(args.outfile) if args.outfile else fb / "_consensus.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["key", *names, "consensus", "spread", "needs_review"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n-> {out}  (consensus = majority score ≥2 graders agree on, else median; "
          f"flagged still go to human review)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

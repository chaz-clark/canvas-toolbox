#!/usr/bin/env python3
"""
N-grader consensus: majority score + spread + auto-flag for NEEDS-REVIEW.

Part of the canvas-toolbox generic grader skill (v0.1). See:
  - lib/agents/canvas_grader.md (operator-facing pipeline guide)
  - lib/agents/knowledge/grader_knowledge.md §4 (consensus + confidence-driven review queue)

WHAT IT DOES
  Each grader pass writes a CSV of `key,score,one_line_reason` to
  <challenge-dir>/feedback/_grader*.csv (one per pass). This reads them and per
  submission computes scores, consensus, spread (max-min), and flags
  NEEDS-REVIEW when spread ≥ threshold.

  CONSENSUS = MAJORITY: the score ≥2 of N graders agree on wins. If all differ,
  fall back to the median.

  OWNS THE FULL AGGREGATION (single-sourced as of 2026-06-10):
    - _consensus.csv     per-grader scores + consensus + spread + needs_review (existing)
    - _summary.csv       key,score,one_line_reason (new — what reidentify reads)
    - <KEY>.md           copy of the consensus-pass's per-student file (new —
                         what push reads). Source: _pass<winner>/<KEY>.md.
    - _all_comments.md   (new — ds460 lesson, parked then promoted 2026-06-10) the
                         compiled review document: every winner file's
                         "## Comment to student" block, prefixed with
                         `## <KEY>  ·  <score>[/<max>]`. Instructor edits the
                         phrasing in ONE place, then a sync-back tool (parked)
                         propagates the edits to per-student files before push.

  Previously the orchestrator (grader_grade.py) had a parallel `_aggregate_summary`
  implementation. As of 2026-06-10 that's removed and consensus owns the aggregation.

  DEFAULT EXPECTS 3 GRADERS. The bulk-mode design is N=3 (the cheapest configuration
  that gives majority rule). The tool REFUSES to run if fewer than --expected
  grader CSVs are present, so a partial pass doesn't silently compute consensus
  over too few graders. Override --expected for calibration (N=1) or rigor (N=5+).

WHY 3
  Holistic scoring varies between graders. Three-grader consensus is the cheapest
  configuration that gives majority rule (two can't break ties; five+ hits
  diminishing returns at 3× token cost). The spread is itself a signal — high-spread
  cases are precisely the borderlines a human should see.

USAGE
  # Default bulk mode (expects exactly 3 grader CSVs, flag threshold 0.5)
  uv run python lib/tools/grader_consensus.py --challenge-dir grading/kc1

  # Single-grader calibration cohort (no consensus, no spread; just summary)
  uv run python lib/tools/grader_consensus.py --challenge-dir grading/kc1 --expected 1

  # Higher-rigor 5-grader pool
  uv run python lib/tools/grader_consensus.py --challenge-dir grading/kc1 --expected 5

  # Tune the spread threshold for a different scale
  uv run python lib/tools/grader_consensus.py --challenge-dir grading/kc1 --flag 1.0

GENERALIZED FROM: ds460-master/grading/consensus.py
(commits 754c966..91a5113 — round-1 KC1 beta).
"""
from __future__ import annotations

import argparse
import csv
import shutil
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


def load_with_reasons(path: Path) -> dict[str, dict]:
    """Read a grader's CSV preserving the `one_line_reason` column for `_summary.csv`.

    Tolerant of older CSVs that only have `key,score` (no reason) — returns
    {key: {score, one_line_reason}} with empty reason in that case.
    """
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                out[row["key"]] = {
                    "score": float(row["score"]),
                    "one_line_reason": row.get("one_line_reason", ""),
                }
            except (KeyError, ValueError):
                pass
    return out


def pass_number_for(grader_csv_path: Path) -> int | None:
    """Extract the pass number N from a `_grader<n>.csv` filename. Returns None
    if the file isn't structured that way."""
    stem = grader_csv_path.stem  # e.g. '_grader1'
    if not stem.startswith("_grader"):
        return None
    try:
        return int(stem[len("_grader"):])
    except ValueError:
        return None


def write_summary(out_path: Path, rows: list[dict]) -> None:
    """Write _summary.csv with the schema reidentify reads: key,score,one_line_reason."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["key", "score", "one_line_reason"])
        w.writeheader()
        w.writerows(rows)


def copy_winner_per_student(
    fb: Path, key: str, winner_pass: int,
) -> bool:
    """Copy feedback/_pass<winner>/<KEY>.md to feedback/<KEY>.md (what push reads)."""
    src = fb / f"_pass{winner_pass}" / f"{key}.md"
    dst = fb / f"{key}.md"
    if not src.exists():
        return False
    shutil.copyfile(src, dst)
    return True


def _extract_comment(per_student_md: str) -> str:
    """Extract the '## Comment to student' section body from a per-student file.
    Returns the body (without the heading), trimmed; '' if not found.
    The section runs from '## Comment to student' to the next top-level
    heading or end-of-file."""
    lines = per_student_md.splitlines()
    in_section = False
    body: list[str] = []
    for ln in lines:
        if not in_section:
            if ln.strip().lower().startswith("## comment to student"):
                in_section = True
            continue
        # End at the next heading (## or #), but allow ### subheadings
        stripped = ln.lstrip()
        if stripped.startswith("# ") or (stripped.startswith("## ")
                                         and not stripped.lower().startswith("## comment to student")):
            break
        body.append(ln)
    return "\n".join(body).strip()


def compile_all_comments(
    fb: Path,
    score_by_key: dict[str, object],
    score_max: str | None,
    prefix: str | None,
) -> tuple[int, int]:
    """Compile feedback/_all_comments.md from each winner file's
    '## Comment to student' block. Returns (compiled_count, missing_count).

    The output mirrors the ds460 KC1 round-1 shape (the artifact instructors
    actually edit before push):
        # <prefix> — all student comments (edit phrasing here)

        `Overall:` uses the rubric's named tiers. Coaching Tips: one idea per
        paragraph. Edit here; the sync-back step propagates to per-student files.

        ## <KEY>  ·  <score>[/<max>]

        <comment body>

        ## <KEY>  ·  <score>[/<max>]

        ...
    """
    items: list[tuple[str, str, str]] = []  # (key, score_label, comment_body)
    missing = 0
    for key in sorted(score_by_key):
        ws = fb / f"{key}.md"
        if not ws.exists():
            missing += 1
            continue
        try:
            body = _extract_comment(ws.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            missing += 1
            continue
        if not body:
            # Per-student file exists but has no Comment-to-student section
            # (e.g., grade-only output). Skip rather than emit an empty block.
            missing += 1
            continue
        sc = score_by_key[key]
        label = f"{sc}/{score_max}" if score_max else str(sc)
        items.append((key, label, body))

    if not items:
        return 0, missing

    title = f"# {prefix.upper() if prefix else 'Cohort'} — all student comments (edit phrasing here)"
    header = (
        title + "\n\n"
        "`Overall:` uses the rubric's named tiers. Coaching Tips: one idea "
        "per paragraph. Edit phrasing here; the sync-back step propagates "
        "edits to per-student files before push.\n"
    )
    body_blocks = "\n\n".join(
        f"## {k}  ·  {label}\n\n{body}" for k, label, body in items
    )
    out_path = fb / "_all_comments.md"
    out_path.write_text(header + "\n" + body_blocks + "\n", encoding="utf-8")
    return len(items), missing


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
    ap.add_argument("--expected", type=int, default=3,
                    help="Required grader count. Default 3 (bulk-mode design). The tool refuses if "
                         "fewer than this many _grader*.csv files are present, so a partial pass "
                         "doesn't silently compute consensus over too few graders. Use --expected 1 "
                         "for single-grader calibration; --expected 5 for a higher-rigor pool.")
    ap.add_argument("--score-max", default=None,
                    help="Optional max-score label (e.g. '4') for the _all_comments.md headers. "
                         "Renders '<KEY>  ·  <score>/<max>'. Omit for '<KEY>  ·  <score>'.")
    args = ap.parse_args()

    if args.challenge_dir:
        cd = Path(args.challenge_dir)
        args.feedback_dir = args.feedback_dir or str(cd / "feedback")

    if not args.feedback_dir:
        print("Missing required arguments. Pass --challenge-dir OR --feedback-dir.", file=sys.stderr)
        return 1

    fb = Path(args.feedback_dir)
    gfiles = sorted(fb.glob("_grader*.csv"))
    if args.expected < 1:
        print(f"--expected must be >= 1; got {args.expected}.", file=sys.stderr)
        return 1
    if len(gfiles) < args.expected:
        # The 3-grader bulk-mode default is the design (grader_knowledge §4).
        # Refuse a partial pass; the operator must either complete the missing pass(es)
        # or explicitly lower --expected (e.g. calibration with N=1).
        print(f"Expected {args.expected} grader file(s) (_grader*.csv) in {fb}; "
              f"found {len(gfiles)}.", file=sys.stderr)
        if args.expected == 3:
            print("Default is 3 (the round-1 bulk-mode design). Either run the missing pass(es), "
                  "or re-run with --expected 1 for a calibration cohort / --expected 2 for a "
                  "two-grader cohort.", file=sys.stderr)
        return 1
    # Sanity: if the operator supplied MORE CSVs than expected, that's also a smell —
    # they may have an old run mixed in. Warn but don't refuse; they may have intentionally
    # accumulated more passes than the default and want all included.
    if len(gfiles) > args.expected:
        print(f"NOTE: found {len(gfiles)} grader files but --expected is {args.expected}; "
              f"using all {len(gfiles)}. Delete stale _grader*.csv files if this is unintended.",
              file=sys.stderr)

    # Load all grader CSVs with reasons (for _summary.csv) keyed by pass number
    per_pass: dict[int, dict[str, dict]] = {}
    for gf in gfiles:
        pn = pass_number_for(gf)
        if pn is None:
            print(f"NOTE: {gf.name} doesn't match _grader<N>.csv naming; skipping.",
                  file=sys.stderr)
            continue
        per_pass[pn] = load_with_reasons(gf)

    # Derive prefix for _all_comments.md heading from challenge-dir basename when present
    cd_prefix = (Path(args.challenge_dir).name if args.challenge_dir else None)

    if args.expected == 1:
        # Single-grader calibration mode — no majority to compute. Still write
        # _summary.csv (copied from the single grader) + copy _pass1/<KEY>.md →
        # <KEY>.md so downstream reidentify + push have the artifacts they expect.
        pn = next(iter(per_pass))  # the only one
        only = per_pass[pn]
        summary_rows = [{"key": k, "score": only[k]["score"],
                         "one_line_reason": only[k]["one_line_reason"]}
                        for k in sorted(only)]
        summary_path = fb / "_summary.csv"
        write_summary(summary_path, summary_rows)
        copied = sum(1 for k in only if copy_winner_per_student(fb, k, pn))
        missing = len(only) - copied
        # Compile _all_comments.md from winner per-student files (grade-only outputs
        # without per-student .md skip cleanly because compile_all_comments returns 0)
        score_by_key = {k: only[k]["score"] for k in sorted(only)}
        compiled, ac_missing = compile_all_comments(fb, score_by_key, args.score_max, cd_prefix)
        print(f"Single-grader calibration mode (--expected 1): no consensus to compute.")
        print(f"  -> {summary_path}  ({len(summary_rows)} rows, copy of _grader{pn}.csv)")
        if missing == len(only) and copied == 0:
            print(f"  -> {fb}/<KEY>.md   (no per-student files to copy — "
                  f"grade-only output expected)")
        else:
            print(f"  -> {fb}/<KEY>.md   ({copied} per-student files copied from _pass{pn}/"
                  + (f"; ⚠ {missing} missing source — partial)" if missing > 0 else ")"))
        if compiled:
            print(f"  -> {fb}/_all_comments.md  ({compiled} comment block(s) compiled "
                  f"for instructor review/edit)")
        return 0

    # Multi-pass: majority + spread + flag
    graders = [per_pass[pn] for pn in sorted(per_pass)]  # ordered by pass number
    pass_numbers = sorted(per_pass)
    names = [f"g{pn}" for pn in pass_numbers]
    keys = sorted(set.intersection(*[set(g) for g in graders]))
    if not keys:
        print("No submissions graded by ALL graders.")
        return 1

    rows: list[dict] = []
    summary_rows: list[dict] = []
    winners: dict[str, int] = {}  # key → which pass was the winner (for per-student copy)
    flagged: list[tuple[str, list[float], float, float]] = []
    exact = within25 = within50 = 0

    print(f"{'key':14} " + " ".join(f"{n:>5}" for n in names) +
          f" {'consensus':>9} {'spread':>7} {'flag':>5}")
    for k in keys:
        sc = [g[k]["score"] for g in graders]
        # MAJORITY RULE: the score ≥2 of N graders agree on wins. Else median.
        val, n_agree = Counter(sc).most_common(1)[0]
        if n_agree >= 2:
            consensus = val
            # Winner = the (first) pass that agreed with the majority value
            winner_pn = next(pn for pn, g in zip(pass_numbers, graders)
                             if g[k]["score"] == consensus)
        else:
            consensus = statistics.median(sc)
            # Winner = the pass closest to the median (for one_line_reason + winner-copy)
            winner_pn = min(pass_numbers,
                            key=lambda pn: abs(per_pass[pn][k]["score"] - consensus))
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
        summary_rows.append({
            "key": k,
            "score": consensus,
            "one_line_reason": per_pass[winner_pn][k]["one_line_reason"],
        })
        winners[k] = winner_pn
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

    # 1. _consensus.csv — per-grader columns + consensus + spread + needs_review
    out = Path(args.outfile) if args.outfile else fb / "_consensus.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["key", *names, "consensus", "spread", "needs_review"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n-> {out}  (consensus = majority score ≥2 graders agree on, else median)")

    # 2. _summary.csv — what reidentify reads (key, score, one_line_reason)
    summary_path = fb / "_summary.csv"
    write_summary(summary_path, summary_rows)
    print(f"-> {summary_path}  ({len(summary_rows)} rows, score+reason from winning pass)")

    # 3. Per-student file copies — what push reads (feedback/<KEY>.md from the winner's pass)
    copied = sum(1 for k in keys if copy_winner_per_student(fb, k, winners[k]))
    missing = len(keys) - copied
    # Grade-only outputs don't produce per-student .md files (no comment to write).
    # If ALL winners are missing their source file, that's the signal — treat as
    # expected (grade-only output) rather than surfacing as a partial-missing error.
    # (Per the ds460 Mid Review ghost-run feedback 2026-06-10.)
    if missing == len(keys) and copied == 0:
        print(f"-> {fb}/<KEY>.md  (no per-student files to copy — "
              f"grade-only output expected; consensus + summary still emitted)")
    elif missing > 0:
        print(f"-> {fb}/<KEY>.md  ({copied} copied from winning pass; "
              f"⚠ {missing} missing _pass<n>/<KEY>.md source — "
              f"partial output, expected if grade-only)")
    else:
        print(f"-> {fb}/<KEY>.md  ({copied} copied from winning pass)")

    # 4. _all_comments.md — compiled review document (ds460 lesson). Reads each
    # winner per-student file's "## Comment to student" section and stitches them
    # with `## <KEY>  ·  <score>[/<max>]` headers. Grade-only outputs (no per-
    # student .md) cleanly produce 0 compiled blocks; tool stays quiet then.
    score_by_key = {r["key"]: r["consensus"] for r in rows}
    compiled, ac_missing = compile_all_comments(fb, score_by_key, args.score_max, cd_prefix)
    if compiled:
        print(f"-> {fb}/_all_comments.md  ({compiled} comment block(s) compiled "
              f"for instructor review/edit"
              + (f"; ⚠ {ac_missing} per-student file(s) had no Comment block)" if ac_missing else ")"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

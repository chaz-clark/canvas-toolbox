#!/usr/bin/env python3
"""HG-6 low-band benefit-of-the-doubt audit (issue #192, Sprint 4).

WHY THIS EXISTS
  Deterministic layers UNDER-detect: a narrow term-bank or a regex that misses a
  paraphrase is a false negative that drags the grade DOWN on work the student did.
  The consensus may have been nudged low by those thin priors. So every consensus
  that lands in the LOW band gets one more look — but a look with the priors
  REMOVED, reading the raw submission, asking only "does the required thing actually
  exist here, however it's worded?"

  If that priors-excluded re-read grades HIGHER than the low consensus, the low band
  may be an artifact of a wrong/narrow NLP scope — flag `undergrade_suspected` and
  route it to the instructor. It NEVER lowers a grade and NEVER auto-raises one:
  disagreements resolve TOWARD the student, by a human (HG-5/HG-6). Benefit of the
  doubt is the default.

  This is the grade-time complement to grader_term_banks.py's build-time alignment:
  widen the net up front, rescue what still slips here.

Usage:
    uv run python lib/tools/grader_lowband_audit.py --challenge-dir grading/<task> \\
        --rubric grading/<task>/RUBRIC.md
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

try:
    from _challenge_dir_guard import resolve_challenge_dir
except ImportError:
    resolve_challenge_dir = None


def low_band_keys(rows: list, frac: float = 0.25) -> list:
    """Keys whose consensus is in the bottom `frac` of the cohort's score range.

    Pure. Returns [] when the cohort has no spread (hi == lo) — no "low band" to audit.
    """
    scores = [r["consensus"] for r in rows if r.get("consensus") is not None]
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi <= lo:
        return []
    thresh = lo + frac * (hi - lo)
    return [r["key"] for r in rows
            if r.get("consensus") is not None and r["consensus"] <= thresh]


def audit_verdict(consensus: float, audit_score) -> tuple:
    """Compare the priors-excluded audit score to the low consensus. Never lowers.

    Returns (undergrade_suspected, reason). Fires only on an UPWARD disagreement —
    resolve toward the student.
    """
    if audit_score is None:
        return False, "audit produced no comparable score — review manually"
    if audit_score > consensus:
        return True, (f"priors-excluded re-read graded {audit_score} vs consensus "
                      f"{consensus} — the text supports a higher band; verify toward the "
                      "student (HG-6)")
    return False, (f"priors-excluded re-read graded {audit_score} (≤ consensus "
                   f"{consensus}) — low band corroborated")


def run_lowband_audit(low_rows: list, grade_fn) -> list:
    """Audit each low-band row. `grade_fn(key) -> (audit_band, audit_score)` is the
    priors-excluded re-read (injected, so this is testable without a provider)."""
    out = []
    for r in low_rows:
        band, score = grade_fn(r["key"])
        flag, reason = audit_verdict(r["consensus"], score)
        out.append({
            "key": r["key"], "consensus": r["consensus"],
            "audit_band": band, "audit_score": score,
            "undergrade_suspected": flag, "audit_reason": reason,
        })
    return out


def _read_consensus(path: Path) -> list:
    rows = []
    for row in csv.DictReader(path.open(encoding="utf-8")):
        try:
            rows.append({"key": row["key"], "consensus": float(row["consensus"])})
        except (KeyError, ValueError):
            continue
    return rows


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(
        description="HG-6 low-band benefit-of-the-doubt audit (#192 Sprint 4). Re-reads "
                    "low-band submissions with priors EXCLUDED; flags undergrade_suspected "
                    "on an upward disagreement. Never moves a score.")
    ap.add_argument("--challenge-dir", required=True, help="e.g. grading/kc3")
    ap.add_argument("--rubric", required=True, help="Checkability-tagged RUBRIC.md")
    ap.add_argument("--config", default=None, help="config.yml (for band_to_score).")
    ap.add_argument("--frac", type=float, default=0.25, help="Bottom fraction = low band (0.25).")
    ap.add_argument("--provider", default="anthropic")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    args = ap.parse_args()

    challenge = (resolve_challenge_dir(args.challenge_dir, verb="auditing")
                 if resolve_challenge_dir else Path(args.challenge_dir))
    fb = Path(challenge) / "feedback"
    consensus_path = fb / "_consensus.csv"
    if not consensus_path.exists():
        print(f"No {consensus_path} — run grader_consensus.py first.", file=sys.stderr)
        return 1
    rows = _read_consensus(consensus_path)
    low = [r for r in rows if r["key"] in set(low_band_keys(rows, args.frac))]
    if not low:
        print("No low-band submissions to audit (no cohort spread, or none in the bottom "
              f"{int(args.frac * 100)}%).")
        return 0

    rubric_text = Path(args.rubric).read_text(encoding="utf-8")
    deid_dir = Path(challenge) / "submissions_deid"

    from grader_grade import (_build_user_prompt, _parse_response, SYSTEM_PROMPT,
                              make_provider, _load_config)
    band_to_score = None
    if args.config:
        band_to_score = (_load_config(Path(args.config)) or {}).get("band_to_score")
    llm = make_provider(args.provider, args.model)

    def grade_fn(key: str):
        sub = deid_dir / f"{key}.md"
        if not sub.exists():
            return None, None
        # priors_block="" — the whole point: re-read WITHOUT the NLP priors.
        prompt = _build_user_prompt(
            pass_number=1, total_passes=1, rubric_text=rubric_text, voice_text="",
            course_context="", answer_key_text="", priors_block="",
            deid_submission=sub.read_text(encoding="utf-8"), band_to_score=band_to_score)
        parsed = _parse_response(llm.grade(SYSTEM_PROMPT, prompt, 0.2)) or {}
        band = parsed.get("band")
        score = parsed.get("score")
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = (band_to_score or {}).get(band)
        return band, score

    print(f"HG-6 low-band audit: re-reading {len(low)} low-band submission(s) with priors "
          "excluded (never moves a score)...")
    records = run_lowband_audit(low, grade_fn)

    out = fb / "_lowband_audit.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["key", "consensus", "audit_band", "audit_score",
                                          "undergrade_suspected", "audit_reason"])
        w.writeheader()
        w.writerows(records)

    flagged = [r for r in records if r["undergrade_suspected"]]
    if flagged:
        print(f"\n⚠️  {len(flagged)} UNDERGRADE-SUSPECTED (resolve toward the student):")
        for r in flagged:
            print(f"  {r['key']}: consensus {r['consensus']} → audit {r['audit_score']} — {r['audit_reason']}")
    else:
        print("\nNo undergrade suspected — every low-band tier was corroborated by the "
              "priors-excluded re-read.")
    print(f"\n-> {out}  ({len(records)} audited; never auto-moved a score)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

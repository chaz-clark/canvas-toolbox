#!/usr/bin/env python3
"""Parse a RUBRIC.md's checkability-tagged criteria table (Stage 0 — issue #192).

Every rubric criterion carries a CHECKABILITY tag so the hybrid grader can route it
to the layer that's authoritative for it (HG-1, route by checkability):

  - mechanical — binary / countable: "includes a thesis", "≥3 citations", "code runs".
                 NLP is authoritative (the LLM confirms).
  - coverage   — all-of-a-set present: "addresses all 5 prompts". NLP flags, LLM verifies.
  - judgment   — quality / insight: "critical insight", "synthesis". LLM only; NLP gives
                 at most weak hints — never force regex onto judgment.

The tags live INLINE in RUBRIC.md — single source of truth, so a rubric edit updates
the checks (no companion file to drift). This module reads the criteria-checkability
table; the evidence extractor (grader_signals.py, Sprint 1) derives per-criterion
term-banks / coverage from these rows.

"Frozen" (Stage 0) = a committed RUBRIC.md whose checkability_fingerprint is recorded;
if the fingerprint changes, the rubric was edited and downstream should re-freeze.

Usage:
    uv run python lib/tools/grader_rubric.py --rubric grading/<task>/RUBRIC.md
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

CHECKABILITY = ("mechanical", "coverage", "judgment")

_CRITERION_COLS = ("criterion", "criteria")
_CHECK_COLS = ("checkability", "check")
_HINT_COLS = ("evidence hint", "evidence", "hint")


def _cells(line: str) -> list:
    """`| a | b | c |` -> ['a', 'b', 'c']."""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator(cells: list) -> bool:
    non_empty = [c for c in cells if c]
    return bool(non_empty) and all(re.fullmatch(r":?-{2,}:?", c) for c in non_empty)


def _col_index(header: list, names: tuple) -> int | None:
    for n in names:
        if n in header:
            return header.index(n)
    return None


def parse_checkability(rubric_text: str) -> tuple:
    """Parse the criteria table that carries a `Checkability` column.

    Returns (rows, issues). rows = [{criterion, checkability, evidence_hint}].
    Extra columns (#, tier descriptors) are ignored; only Criterion + Checkability
    are required, Evidence hint is optional. `issues` is a list of human-readable
    problems (missing table, unknown tag) — a non-empty list means the freeze
    isn't clean.
    """
    rows: list = []
    issues: list = []
    lines = rubric_text.splitlines()

    header_idx = None
    header = None
    for i, ln in enumerate(lines):
        if "|" not in ln:
            continue
        lowered = [c.lower() for c in _cells(ln)]
        if any(c in _CHECK_COLS for c in lowered):
            header_idx, header = i, lowered
            break

    if header is None:
        issues.append("No criteria table with a 'Checkability' column found in RUBRIC.md. "
                      "Add one so each criterion is routed by checkability (mechanical / "
                      "coverage / judgment).")
        return rows, issues

    ci_crit = _col_index(header, _CRITERION_COLS)
    ci_check = _col_index(header, _CHECK_COLS)
    ci_hint = _col_index(header, _HINT_COLS)
    if ci_crit is None:
        issues.append("The checkability table has no 'Criterion' column.")
        return rows, issues

    for ln in lines[header_idx + 1:]:
        if "|" not in ln:
            break  # table ended
        cells = _cells(ln)
        if _is_separator(cells):
            continue
        if len(cells) <= max(ci_crit, ci_check):
            continue
        criterion = cells[ci_crit].strip().strip("*").strip()
        check = cells[ci_check].strip().lower()
        hint = cells[ci_hint].strip() if (ci_hint is not None and ci_hint < len(cells)) else ""
        if not criterion:
            continue
        if check not in CHECKABILITY:
            issues.append(f"{criterion!r}: unknown checkability {check!r} — "
                          f"use one of {', '.join(CHECKABILITY)}.")
            continue
        rows.append({
            "criterion": criterion,
            "checkability": check,
            "evidence_hint": hint if (hint and hint != "—") else None,
        })

    if not rows and not issues:
        issues.append("Checkability table found but no valid criterion rows parsed.")
    return rows, issues


def checkability_fingerprint(rows: list) -> str:
    """Stable 'frozen' marker: a hash of the (criterion, checkability) pairs.

    Order-insensitive (reordering criteria is not a rubric change), but changes the
    moment a criterion or its checkability tag changes — so drift from a frozen
    rubric is detectable.
    """
    pairs = sorted(f"{r['criterion'].strip().lower()}::{r['checkability']}" for r in rows)
    return hashlib.sha256("\n".join(pairs).encode("utf-8")).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Parse + validate a RUBRIC.md checkability table (Stage 0, #192).")
    ap.add_argument("--rubric", required=True, help="Path to RUBRIC.md")
    args = ap.parse_args()

    path = Path(args.rubric)
    if not path.is_file():
        print(f"No rubric at {path}", file=sys.stderr)
        return 1
    rows, issues = parse_checkability(path.read_text(encoding="utf-8"))

    for r in rows:
        hint = f"  ({r['evidence_hint']})" if r["evidence_hint"] else ""
        print(f"  [{r['checkability']:<10}] {r['criterion']}{hint}")
    by_tag = {t: sum(1 for r in rows if r["checkability"] == t) for t in CHECKABILITY}
    print(f"\n{len(rows)} criteria — " + ", ".join(f"{n} {t}" for t, n in by_tag.items()))
    if rows:
        print(f"checkability fingerprint (freeze marker): {checkability_fingerprint(rows)}")
    if issues:
        print("\nIssues:", file=sys.stderr)
        for it in issues:
            print(f"  ⛔ {it}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

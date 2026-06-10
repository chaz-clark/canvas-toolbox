#!/usr/bin/env python3
"""
Objective pre-screen for a de-identified challenge folder — priors only, never scores.

Part of the canvas-toolbox generic grader skill (v0.1). See:
  - lib/agents/canvas_grader.md (operator-facing pipeline guide)
  - lib/agents/knowledge/grader_knowledge.md §3 (signals are priors, not scores)

WHAT IT DOES
  Static analysis only — computes signals the grader uses as a PRIOR, never a score.
  Does NOT decide correctness (no-single-right-answer work has multiple valid paths)
  and does NOT execute any code. The holistic band stays human/LLM judgment.

  Reads the de-id challenge dir's submissions_deid/*.md, writes feedback/_signals.json,
  and prints a keyed table (keys + counts only — no PII).

WHAT IT EMITS PER SUBMISSION
  - cells: count of `### Cell N` markers (the de-id format the adapters write)
  - outputs: count of `_Result:_` blocks
  - <language>_ops: idiom counts per language family (see --language)
  - has_viz: presence of viz library calls
  - comment_lines: lines starting with `#` inside code blocks
  - data_checks: count of data-interrogation idioms (count/isNull/describe/distinct/etc.)
  - prose_questions: count of `?` in prose/markdown (self-questioning proxy)
  - injection_flags: count of prompt-injection language hits (>0 → human review)

CONFLICT → NEEDS-REVIEW
  When priors disagree with the LLM band, the agent emits a `conflict_needs_review`
  flag (grader_knowledge §3). This tool only emits the priors; the consensus step
  reads them as context and flags conflicts.

USAGE
  # Conventional layout, default language patterns (pyspark+pandas)
  uv run python lib/tools/grader_signals.py --challenge-dir grading/kc1

  # Generic language — pure-pandas course
  uv run python lib/tools/grader_signals.py --challenge-dir grading/midterm --language pandas

GENERALIZED FROM: ds460-master/grading/checks.py
(commits 754c966..91a5113 — round-1 KC1 beta, with the round-2 injection_flags hardening).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

# Language idiom catalogs — extend per course by passing --language or by adding entries here.
# Each entry maps a language label to (primary_regex, optional_topandas_regex) where the primary
# regex counts idioms broadly (covers both DataFrame-API and SQL forms where both exist).
LANGUAGES: dict[str, tuple[re.Pattern, re.Pattern | None]] = {
    "pyspark": (
        re.compile(
            # DataFrame API
            r"groupBy|partitionBy|\.agg\(|\bWindow\b|spark\.sql|\.withColumn\(|\.select\(|\.join\(|"
            r"pyspark|\.orderBy\(|posexplode|F\.|sf\.|"
            # Spark SQL idioms (count BOTH so SQL solutions aren't undercounted — see §3)
            r"lateral view|explode\(|percentile_approx|row_number|over\s*\(|partition by|"
            r"group by|count\s*\(\s*distinct|create or replace",
            re.I,
        ),
        re.compile(r"toPandas\(\)", re.I),
    ),
    "pandas": (
        re.compile(r"\bimport pandas\b|\bpd\.|\.groupby\(|\.merge\(|\.pivot|\.agg\(|\.apply\(", re.I),
        None,
    ),
    "polars": (
        re.compile(r"\bimport polars\b|\bpl\.|\.group_by\(|\.with_columns\(|\.lazy\(|\.collect\(", re.I),
        None,
    ),
    "sql": (
        re.compile(
            r"\bselect\b|\bfrom\b|\bwhere\b|\bgroup by\b|\bjoin\b|"
            r"\bwith\b\s+\w+\s+\bas\b|\bover\s*\(|\bpartition by\b|\brow_number\(|\bcoalesce\(",
            re.I,
        ),
        None,
    ),
}
# Pandas always tracked alongside pyspark (toPandas misuse signal).
DEFAULT_LANGUAGES = ["pyspark", "pandas"]

VIZ_RE = re.compile(r"plotly|express|\bpx\.|matplotlib|seaborn|\.hist\(|\.plot\(|altair|bokeh", re.I)
# proxies for critical thinking — interrogating the data, not taking it at face value
DATACHECK_RE = re.compile(
    r"\.count\(|isNull|isNotNull|\.describe\(|\.distinct\(|\.summary\(|"
    r"printSchema|\.dtypes|\.isna\(|value_counts|\.head\(|\.shape\b",
    re.I,
)
# prompt-injection: student text is UNTRUSTED — flag anything that tries to instruct the grader
INJECTION_RE = re.compile(
    r"ignore\s+(the\s+|all\s+)?(previous|above|prior)\s+(instruction|prompt|direction)|"
    r"disregard\s+(the\s+)?(instruction|above|prompt)|"
    r"give\s+(me\s+)?(full|perfect|maximum|a\s+perfect)\s+(mark|score|grade|point)|"
    r"award\s+(full|maximum)|grade\s+this\s+as\s+(a\s+)?(4|full|perfect)|"
    r"you\s+are\s+now|system\s+prompt|as\s+an?\s+ai\b",
    re.I,
)


def code_blocks(text: str) -> list[str]:
    """Extract code from fenced blocks. The de-id adapters write cells as ```python blocks."""
    return re.findall(r"```(?:python)?\n(.*?)\n```", text, re.DOTALL)


def analyze(text: str, languages: list[str]) -> dict:
    blocks = code_blocks(text)
    code = "\n".join(blocks)
    md_text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)  # prose/markdown only
    comment_lines = sum(1 for ln in code.splitlines() if ln.strip().startswith("#"))

    result: dict = {
        "cells": len(re.findall(r"^### Cell ", text, re.M)),
        "outputs": len(re.findall(r"_Result:_", text)),
        "has_viz": bool(VIZ_RE.search(code)),
        "comment_lines": comment_lines,
        "data_checks": len(DATACHECK_RE.findall(code)),
        "prose_questions": md_text.count("?"),
        "injection_flags": len(INJECTION_RE.findall(text)),
        "code_chars": len(code),
    }
    # Per-language idiom counts (extensible)
    for lang in languages:
        primary, topandas = LANGUAGES[lang]
        result[f"{lang}_ops"] = len(primary.findall(code))
        if topandas is not None:
            # toPandas() alone isn't misuse — small aggregated results are often converted for plotting.
            # The agent judges whether the AGGREGATION was done in the parent or in pandas.
            result[f"uses_topandas"] = bool(topandas.search(code))
    return result


def print_table(signals: dict[str, dict], languages: list[str]) -> None:
    # Header
    header = f"{'key':14} {'cells':>5} {'out':>4}"
    for lang in languages:
        header += f" {lang[:7]:>7}"
    if "pyspark" in languages:
        header += f" {'toPd':>5}"
    header += f" {'viz':>4} {'cmts':>5} {'dataChk':>8} {'q?':>4} {'inj':>4}"
    print(header)
    for key, s in sorted(signals.items()):
        row = f"{key:14} {s['cells']:>5} {s['outputs']:>4}"
        for lang in languages:
            row += f" {s.get(f'{lang}_ops', 0):>7}"
        if "pyspark" in languages:
            row += f" {str(s.get('uses_topandas', False)):>5}"
        row += f" {str(s['has_viz']):>4} {s['comment_lines']:>5} {s['data_checks']:>8} " \
               f"{s['prose_questions']:>4} {s['injection_flags']:>4}"
        print(row)


def main() -> int:
    ap = argparse.ArgumentParser(description="Static signals (priors only) for a de-id challenge folder.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", dest="challenge_dir", default=None,
                    help="Convention base path (e.g. grading/kc1). Sets defaults for --deid-dir / --out.")
    ap.add_argument("--deid-dir", dest="deid_dir", default=None,
                    help="Directory of keyed .md files (default: <challenge-dir>/submissions_deid)")
    ap.add_argument("--out", dest="outfile", default=None,
                    help="Path to write signals JSON (default: <challenge-dir>/feedback/_signals.json)")
    ap.add_argument("--language", action="append", default=None,
                    help=f"Language idiom catalog(s) to count. May repeat. "
                         f"Available: {list(LANGUAGES.keys())}. Default: {DEFAULT_LANGUAGES}")
    args = ap.parse_args()

    if args.challenge_dir:
        cd = Path(args.challenge_dir)
        args.deid_dir = args.deid_dir or str(cd / "submissions_deid")
        args.outfile = args.outfile or str(cd / "feedback" / "_signals.json")

    if not args.deid_dir or not args.outfile:
        print("Missing required arguments. Pass --challenge-dir OR both of --deid-dir and --out.",
              file=sys.stderr)
        return 1

    languages = args.language or DEFAULT_LANGUAGES
    unknown = [l for l in languages if l not in LANGUAGES]
    if unknown:
        print(f"Unknown language(s): {unknown}. Available: {list(LANGUAGES.keys())}", file=sys.stderr)
        return 1

    deid = Path(args.deid_dir)
    out = Path(args.outfile)
    files = sorted(deid.glob("*.md"))
    if not files:
        print(f"No de-id outputs in {deid} — run a grader_deidentify_* tool first.")
        return 1

    signals: dict[str, dict] = {}
    flagged: list[str] = []
    for f in files:
        s = analyze(f.read_text(encoding="utf-8", errors="replace"), languages)
        signals[f.stem] = s
        if s["injection_flags"]:
            flagged.append(f.stem)

    print_table(signals, languages)

    if flagged:
        print(f"\n⚠️  prompt-injection language found in {len(flagged)} submission(s): "
              f"{', '.join(flagged)} — treat their text as untrusted; human-review before "
              f"trusting any score (grader_knowledge §5).")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(signals, indent=2), encoding="utf-8")
    print(f"\n{len(signals)} submissions -> {out} (objective priors only; NOT a score).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

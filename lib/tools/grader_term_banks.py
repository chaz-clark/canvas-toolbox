#!/usr/bin/env python3
"""LLM-sampled term-bank builder — freeze-time scope alignment (issue #192, Sprint 1c).

WHY THIS EXISTS
  The deterministic extractor (grader_signals.py) derives a criterion's term-bank
  from the criterion's own words — a single, narrow guess. When that scope is off
  (a synonym or paraphrase the criterion didn't literally name), the NLP layer
  UNDER-detects, which drags the grade down on work the student actually did. That
  is the HG-6 misalignment at its source.

  This offsets it at BUILD time: sample the LLM N times (temperature-varied) for the
  words/phrases a student might actually use to satisfy each criterion, UNION the
  samples (benefit of the doubt — a wider net catches paraphrase), and write the
  result into the RUBRIC.md `Evidence hint` column. grader_signals.py (Sprint 1b)
  then extracts DETERMINISTICALLY against that richer, frozen term-bank.

  So grading stays deterministic, reproducible, and cheap — the LLM sampling happens
  ONCE, at freeze time, and the result is frozen + auditable in the rubric. It does
  not reintroduce the LLM into the grade-time deterministic layer; it uses sampling
  to ALIGN the deterministic scope. Priors still never score (HG-2). This is the
  build-time complement to HG-6's grade-time low-band audit — belt and suspenders.

WHAT IT DOES / DOESN'T TOUCH
  - Only `mechanical` / `coverage` rows (judgment rows get no term-bank — HG-1).
  - Only rows whose `Evidence hint` is EMPTY — never overwrites an instructor's hint.
  - Dry-run by default; --apply writes (fills empty cells / adds the column).

Usage:
    uv run python lib/tools/grader_term_banks.py --rubric grading/<task>/RUBRIC.md
    uv run python lib/tools/grader_term_banks.py --rubric ... --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from grader_rubric import parse_checkability
except ImportError:
    parse_checkability = None

_TEMPS = (0.3, 0.6, 0.9)
_TERM_CAP = 20

_SYSTEM = (
    "You expand a grading-rubric criterion into a SEARCH TERM-BANK: the words and "
    "short phrases a student's submission might actually use to satisfy it, including "
    "synonyms and paraphrases. You never judge or score — you only widen the vocabulary "
    "so a keyword search won't miss work that's phrased differently. Output ONLY a JSON "
    "array of lowercase terms/phrases."
)


def _user_prompt(criterion: str) -> str:
    return (f"Criterion: {criterion}\n\n"
            "List 8–15 words or short phrases a student's submission might use to address "
            "this criterion — synonyms, paraphrases, related terminology, common spellings. "
            "Do not restate the criterion; give the vocabulary to search for. JSON array only.")


def _parse_terms(response: str) -> list:
    """Extract terms from an LLM response — a JSON array, or a comma/line-delimited list."""
    if not response:
        return []
    m = re.search(r"\[.*?\]", response, re.DOTALL)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                return [str(x).strip() for x in arr if str(x).strip()]
        except (json.JSONDecodeError, ValueError):
            pass
    out = []
    for part in re.split(r"[\n,]", response):
        t = part.strip().strip("-*•\"'` ").strip()
        if t and not t.endswith(":") and len(t) < 60:
            out.append(t)
    return out


def _clean_terms(terms: list, cap: int = _TERM_CAP) -> list:
    """Lowercase, collapse whitespace, dedupe (order-preserving), drop <3 chars, cap."""
    seen: list = []
    for t in terms:
        t = re.sub(r"\s+", " ", str(t).strip().lower())
        if len(t) >= 3 and t not in seen:
            seen.append(t)
    return seen[:cap]


def sample_term_bank(criterion: str, sample_fn, n: int = 3) -> list:
    """N temperature-varied LLM samples → UNION of parsed terms (benefit of the doubt).

    `sample_fn(criterion: str, temperature: float) -> str` returns the raw LLM text.
    Injecting it keeps this unit testable without a network/provider.
    """
    union: list = []
    for i in range(max(1, n)):
        union.extend(_parse_terms(sample_fn(criterion, _TEMPS[i % len(_TEMPS)])))
    return _clean_terms(union)


def suggest_hints(rows: list, sample_fn, n: int = 3) -> dict:
    """Sample a term-bank for each mechanical/coverage row with an EMPTY hint.

    Returns {criterion: [terms]}. Judgment rows and rows that already carry an
    Evidence hint are skipped (HG-1; respect instructor authoring).
    """
    out: dict = {}
    for r in rows:
        if r["checkability"] == "judgment" or r.get("evidence_hint"):
            continue
        terms = sample_term_bank(r["criterion"], sample_fn, n)
        if terms:
            out[r["criterion"]] = terms
    return out


# --- RUBRIC.md table editing (pure; only fills EMPTY Evidence-hint cells) ----

def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _append_cell(line: str, cell: str) -> str:
    s = line.rstrip()
    if s.endswith("|"):
        s = s[:-1].rstrip()
    return f"{s} | {cell} |"


def apply_hints_to_rubric(rubric_text: str, hints: dict) -> tuple:
    """Write term-banks into the criteria table's `Evidence hint` column.

    Adds the column if absent; otherwise fills only EMPTY cells for the given
    criteria (never overwrites an existing hint). Returns (new_text, n_filled).
    """
    lines = rubric_text.split("\n")
    header_i = next((i for i, ln in enumerate(lines)
                     if "|" in ln and any(c.lower() in ("checkability", "check")
                                          for c in _cells(ln))), None)
    if header_i is None:
        return rubric_text, 0
    header = [c.lower() for c in _cells(lines[header_i])]
    ci_crit = next((i for i, c in enumerate(header) if c in ("criterion", "criteria")), None)
    if ci_crit is None:
        return rubric_text, 0
    ci_hint = next((i for i, c in enumerate(header)
                    if c in ("evidence hint", "evidence", "hint")), None)

    sep_i = header_i + 1
    body = []
    j = sep_i + 1
    while j < len(lines) and "|" in lines[j]:
        body.append(j)
        j += 1

    def terms_for(cells: list) -> str:
        crit = cells[ci_crit].strip().strip("*").strip() if ci_crit < len(cells) else ""
        return ", ".join(hints.get(crit, []))

    filled = 0
    if ci_hint is None:  # add the column
        lines[header_i] = _append_cell(lines[header_i], "Evidence hint")
        lines[sep_i] = _append_cell(lines[sep_i], "---")
        for bi in body:
            val = terms_for(_cells(lines[bi]))
            lines[bi] = _append_cell(lines[bi], val)
            if val:
                filled += 1
    else:  # fill empty cells only
        for bi in body:
            cells = _cells(lines[bi])
            if ci_crit >= len(cells):
                continue
            while len(cells) <= ci_hint:
                cells.append("")
            if cells[ci_hint].strip():
                continue  # respect an existing hint
            val = terms_for(cells)
            if not val:
                continue
            cells[ci_hint] = val
            lines[bi] = "| " + " | ".join(cells) + " |"
            filled += 1

    return "\n".join(lines), filled


def main() -> int:
    ap = argparse.ArgumentParser(
        description="LLM-sampled term-bank builder — fill a RUBRIC.md's Evidence hint "
                    "column at freeze time (#192 Sprint 1c). Dry-run unless --apply.")
    ap.add_argument("--rubric", required=True, help="Path to the checkability-tagged RUBRIC.md")
    ap.add_argument("--apply", action="store_true", help="Write the hints into RUBRIC.md")
    ap.add_argument("--samples", type=int, default=3, help="LLM samples per criterion (default 3)")
    ap.add_argument("--provider", default="anthropic")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    args = ap.parse_args()

    if parse_checkability is None:
        print("grader_rubric not importable.", file=sys.stderr)
        return 1
    path = Path(args.rubric)
    if not path.is_file():
        print(f"No rubric at {path}", file=sys.stderr)
        return 1
    rubric_text = path.read_text(encoding="utf-8")
    rows, issues = parse_checkability(rubric_text)
    for it in issues:
        print(f"⚠️  {it}", file=sys.stderr)
    if not rows:
        return 1

    from grader_grade import make_provider
    llm = make_provider(args.provider, args.model)

    def sample_fn(criterion: str, temperature: float) -> str:
        return llm.grade(_SYSTEM, _user_prompt(criterion), temperature, max_tokens=512)

    targets = [r for r in rows if r["checkability"] != "judgment" and not r.get("evidence_hint")]
    print(f"Sampling term-banks for {len(targets)} criterion(a) "
          f"({args.samples} samples each; judgment rows + already-hinted rows skipped):")
    hints = suggest_hints(rows, sample_fn, args.samples)
    for crit, terms in hints.items():
        print(f"  • {crit}\n      → {', '.join(terms)}")

    if not hints:
        print("Nothing to fill.")
        return 0
    if not args.apply:
        print("\nDry-run — re-run with --apply to write these into the Evidence hint column.")
        return 0

    new_text, filled = apply_hints_to_rubric(rubric_text, hints)
    path.write_text(new_text, encoding="utf-8")
    print(f"\n✓ Wrote {filled} Evidence hint(s) into {path}. Re-freeze: "
          f"grader_rubric.py --rubric {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

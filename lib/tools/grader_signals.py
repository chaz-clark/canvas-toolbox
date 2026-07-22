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
  - prose_evidence: (#192) a list of prose signals — word/section/paragraph counts,
    inline-APA / DOI / URL / References-section detection, readability — each tagged
    structural / evaluative / judgment-hint and framed as EVIDENCE TO VERIFY, never
    a met/unmet verdict. Sprint 1b maps these to the checkability-tagged rubric rows.

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

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import json
import re
import sys
from pathlib import Path
from _challenge_dir_guard import resolve_challenge_dir  # issue #44 FERPA guard

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

try:
    # #192 Sprint 1b — map evidence to the checkability-tagged rubric rows.
    from grader_rubric import parse_checkability
except ImportError:
    parse_checkability = None

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

# --- Prose/text evidence patterns (issue #192 Sprint 1a) --------------------
# Deterministic, criterion-INDEPENDENT signals for prose submissions (methodology,
# essays). Each is EVIDENCE to verify against the text, never a met/unmet verdict.
# Inline APA: (Author, 2020) / (Smith & Jones, 2021) / (Smith et al., 2019).
APA_INLINE_RE = re.compile(
    r"\([A-Z][A-Za-z'’.-]+"                        # first author surname
    r"(?:\s+(?:and|&)\s+[A-Z][A-Za-z'’.-]+)?"      # optional "& Lee" / "and Lee"
    r"(?:\s+et\s+al\.?)?"                          # optional "et al." (terminal, no name after)
    r"(?:\s*,\s*[A-Z][A-Za-z'’.-]+)*"              # optional extra comma-separated authors
    r",\s*(?:19|20)\d{2}[a-z]?\)"                  # , YEAR)
)
# A word-like token — excludes markdown markup (#, *, -) so a heading's `#` isn't a "word".
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’-]*")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
URL_RE = re.compile(r"https?://[^\s)>\]]+")
REFERENCES_RE = re.compile(r"^#{1,6}\s*(references|bibliography|works\s+cited|sources)\b",
                           re.I | re.M)
_SENTENCE_END_RE = re.compile(r"[.!?]+")


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
    result["prose_evidence"] = prose_evidence(text)  # #192 Sprint 1a
    return result


def _prose_only(text: str) -> str:
    """Strip fenced code blocks — prose signals must not count code as words/sections."""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def prose_evidence(text: str) -> list[dict]:
    """Deterministic prose/text evidence for #192's hybrid grader (Sprint 1a).

    Criterion-INDEPENDENT signals (Sprint 1b maps them to the checkability-tagged
    rubric rows). Each item is `{signal, value, tag, framing}`:
      - `tag` is the signal taxonomy — structural / evaluative / judgment-hint.
      - `framing` presents it as EVIDENCE TO VERIFY against the text, never a
        met/unmet verdict (HG-3) — e.g. "0 literal matches — check for paraphrase."
    """
    prose = _prose_only(text)
    wc = len(_WORD_RE.findall(prose))
    sections = len(re.findall(r"^#{1,6}\s", prose, re.M))
    paragraphs = len([b for b in re.split(r"\n\s*\n", prose.strip()) if b.strip()])
    apa = len(APA_INLINE_RE.findall(prose))
    doi = len(DOI_RE.findall(prose))
    urls = len(URL_RE.findall(prose))
    has_refs = bool(REFERENCES_RE.search(prose))
    questions = prose.count("?")
    sentences = max(1, len(_SENTENCE_END_RE.findall(prose)))
    avg_sentence_words = round(wc / sentences, 1)

    return [
        {"signal": "word_count", "value": wc, "tag": "structural",
         "framing": "prose word count (code excluded) — verify against the rubric's target length, if it sets one"},
        {"signal": "section_count", "value": sections, "tag": "structural",
         "framing": "markdown headings — a proxy for whether required sections exist; verify each required section by name, not by count"},
        {"signal": "paragraph_count", "value": paragraphs, "tag": "structural",
         "framing": "prose paragraphs (structure only)"},
        {"signal": "apa_inline_citations", "value": apa, "tag": "evaluative",
         "framing": f"{apa} literal (Author, YEAR) match(es) — before concluding uncited, check for DOI/URL/numbered or paraphrased attribution"},
        {"signal": "doi_references", "value": doi, "tag": "evaluative",
         "framing": f"{doi} DOI(s) present"},
        {"signal": "urls", "value": urls, "tag": "evaluative",
         "framing": f"{urls} URL(s) present — may be sources or just links; verify in context"},
        {"signal": "has_references_section", "value": has_refs, "tag": "evaluative",
         "framing": ("a References/Bibliography heading is present" if has_refs
                     else "no References/Bibliography heading — check for inline-only citations before concluding unsourced")},
        {"signal": "prose_questions", "value": questions, "tag": "judgment-hint",
         "framing": "count of '?' — a weak self-questioning proxy; NOT evidence of insight on its own"},
        {"signal": "avg_sentence_words", "value": avg_sentence_words, "tag": "judgment-hint",
         "framing": "average words per sentence — a readability proxy only, never a quality verdict"},
    ]


# --- Rubric-derived evidence (issue #192 Sprint 1b) -------------------------
# Option C: for each checkability-tagged criterion, DERIVE a term-bank from the
# criterion text by default; OVERRIDE with the Evidence hint column when present.
# Everything is EVIDENCE to verify (HG-3); a term-bank miss (paraphrase) is caught
# downstream by the LLM reading the corpus and the HG-6 low-band audit — never a
# score here.

# Function words + grading boilerplate that make poor search terms.
_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "at", "by",
    "from", "as", "is", "are", "be", "that", "this", "these", "those", "it", "its",
    "their", "them", "they", "which", "who", "whose", "what", "when", "where", "how",
    "not", "no", "any", "all", "each", "every", "some", "one", "two", "three", "four",
    "five", "least", "more", "than", "must", "should", "students", "student",
    "submission", "assignment", "rubric", "criterion", "criteria", "points", "point",
    "includes", "include", "including", "demonstrates", "demonstrate", "shows", "show",
    "uses", "use", "using", "provides", "provide", "contains", "contain", "states",
    "state", "addresses", "address", "present", "presents", "has", "have",
}


def derive_term_bank(criterion_text: str) -> list:
    """Content words of a criterion, as a search term-bank (Option C default).

    Lowercased, stopworded, deduped (order-preserving), length ≥3 — e.g.
    '≥3 scholarly citations (APA)' -> ['scholarly', 'citations', 'apa'].
    """
    seen = []
    for w in _WORD_RE.findall(criterion_text.lower()):
        if len(w) >= 3 and w not in _STOP and not w.isdigit() and w not in seen:
            seen.append(w)
    return seen


def parse_evidence_hint(hint: str | None) -> dict:
    """Extract structure from the optional Evidence hint cell.

    Returns {target, citation_types, coverage_items, terms}. Recognizes a numeric
    target (`≥3` / `target 3` / `at least 3`), citation types (APA/MLA/DOI/URL), an
    explicit coverage list (`prompts: a, b, c`), or otherwise comma/semicolon-
    separated override terms. All fields are optional.
    """
    out: dict = {"target": None, "citation_types": [], "coverage_items": [], "terms": []}
    if not hint:
        return out
    m = re.search(r"(?:≥|>=|target\s+|at\s+least\s+)\s*(\d+)", hint, re.I)
    if m:
        out["target"] = int(m.group(1))
    for ct in ("APA", "MLA", "DOI", "URL"):
        if re.search(rf"\b{ct}\b", hint, re.I):
            out["citation_types"].append(ct)
    m2 = re.search(r"(?:prompts?|items?|covers?|sections?|questions?|regulations?)\s*[:=]\s*(.+)",
                   hint, re.I)
    if m2:
        out["coverage_items"] = [s.strip() for s in re.split(r"[;,]", m2.group(1)) if s.strip()]
    else:
        parts = [s.strip() for s in re.split(r"[;,]", hint) if s.strip()]
        out["terms"] = [p for p in parts
                        if not re.fullmatch(r"(?:≥|>=|target|at least)?\s*\d+|apa|mla|doi|url",
                                            p, re.I)]
    return out


def _count_terms(prose: str, terms: list) -> int:
    return sum(len(re.findall(rf"\b{re.escape(t)}\b", prose, re.I)) for t in terms)


def criterion_evidence(row: dict, text: str) -> dict:
    """Per-criterion evidence for one checkability-tagged rubric row (#192 1b).

    Routes by checkability (HG-1): judgment → weak context only; mechanical/coverage
    → citation routing + term-bank hits + (coverage) per-item presence. Every item
    is framed as evidence to verify, never met/unmet.
    """
    crit, check = row["criterion"], row["checkability"]
    parsed = parse_evidence_hint(row.get("evidence_hint"))
    prose = _prose_only(text)
    ev: list = []

    if check == "judgment":
        ev.append({"signal": "judgment_row", "value": None, "tag": "judgment-hint",
                   "framing": f"'{crit}' is a judgment criterion — score it from the text itself. "
                              "NLP contributes no evidence here; readability/structure are context only."})
        return {"criterion": crit, "checkability": check, "evidence": ev}

    if parsed["citation_types"]:
        apa, doi, urls = (len(APA_INLINE_RE.findall(prose)),
                          len(DOI_RE.findall(prose)), len(URL_RE.findall(prose)))
        found = apa + doi + urls
        frame = f"citations found: {apa} APA + {doi} DOI + {urls} URL = {found}"
        if parsed["target"] is not None:
            frame += f"; target ≥{parsed['target']}"
        frame += " — verify format acceptability and paraphrased attribution before concluding uncited"
        ev.append({"signal": "citations", "value": found, "tag": "evaluative", "framing": frame})

    terms = parsed["terms"] or derive_term_bank(crit)
    if terms:
        hits = _count_terms(prose, terms)
        src = "hint" if parsed["terms"] else "derived from criterion"
        frame = (f"term-bank ({src}) {terms}: {hits} literal hit(s) — evidence the topic is "
                 "addressed; if low, check for paraphrase/synonyms before concluding absent")
        if parsed["target"] is not None and not parsed["citation_types"]:
            frame += f" (rubric target ≥{parsed['target']})"
        ev.append({"signal": "term_bank_hits", "value": hits, "tag": "evaluative", "framing": frame})

    if check == "coverage":
        items = parsed["coverage_items"]
        if items:
            missing = [it for it in items if _count_terms(prose, derive_term_bank(it) or [it]) == 0]
            found_n = len(items) - len(missing)
            frame = f"{found_n}/{len(items)} required items show literal evidence"
            if missing:
                frame += f"; NO literal hit for: {missing} — check for paraphrase before marking uncovered"
            ev.append({"signal": "coverage", "value": f"{found_n}/{len(items)}", "tag": "evaluative",
                       "framing": frame})
        else:
            ev.append({"signal": "coverage", "value": None, "tag": "evaluative",
                       "framing": "coverage criterion with no item list in the Evidence hint — the "
                                  "term-bank above is the only presence signal; list the required "
                                  "items in the hint for per-item coverage"})
    return {"criterion": crit, "checkability": check, "evidence": ev}


def rubric_evidence(rubric_text: str, submission_text: str) -> tuple:
    """Map every checkability-tagged criterion to its per-criterion evidence.

    Returns (criteria_evidence, issues). issues surfaces a missing/invalid rubric
    (the caller decides whether to proceed without per-criterion routing).
    """
    if parse_checkability is None:
        return [], ["grader_rubric not importable — per-criterion evidence skipped."]
    rows, issues = parse_checkability(rubric_text)
    return [criterion_evidence(r, submission_text) for r in rows], issues


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
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

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
    ap.add_argument("--rubric", default=None,
                    help="Path to a checkability-tagged RUBRIC.md (#192). When given, each "
                         "submission also gets per-criterion evidence (term-banks / coverage / "
                         "citations, routed by checkability) under a `criteria` key.")
    args = ap.parse_args()

    if args.challenge_dir:
        cd = resolve_challenge_dir(args.challenge_dir, verb="scanning")
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

    rubric_text = None
    if args.rubric:
        rp = Path(args.rubric)
        if not rp.is_file():
            print(f"--rubric {rp} not found.", file=sys.stderr)
            return 1
        rubric_text = rp.read_text(encoding="utf-8")

    signals: dict[str, dict] = {}
    flagged: list[str] = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        s = analyze(text, languages)
        if rubric_text is not None:
            criteria, r_issues = rubric_evidence(rubric_text, text)
            s["criteria"] = criteria
            if r_issues and f is files[0]:  # report rubric problems once
                for it in r_issues:
                    print(f"⚠️  rubric: {it}", file=sys.stderr)
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

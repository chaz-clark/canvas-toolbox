"""Unit tests — grader_term_banks LLM-sampled term-bank builder (issue #192, Sprint 1c).

The LLM is injected as a fake `sample_fn`, so these run with no network/provider.
Two things must hold: sampling UNIONs across passes (wider net = benefit of the
doubt), and the table editor only ever FILLS EMPTY cells (never clobbers an
instructor's hint), round-tripping through the Sprint 0/1b parsers.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_term_banks import (  # noqa: E402
    _parse_terms,
    sample_term_bank,
    suggest_hints,
    apply_hints_to_rubric,
)
from grader_rubric import parse_checkability  # noqa: E402
from grader_signals import parse_evidence_hint  # noqa: E402


# --- parsing + sampling ----------------------------------------------------

def test_parse_terms_json_array():
    assert _parse_terms('Here: ["reproducible", "seed", "deterministic"]') == \
        ["reproducible", "seed", "deterministic"]


def test_parse_terms_fallback_list():
    assert _parse_terms("- reproducible\n- random seed\n- deterministic") == \
        ["reproducible", "random seed", "deterministic"]


def test_sampling_unions_across_passes():
    """Different samples contribute different terms; the union is wider than any one."""
    responses = iter(['["reproducible", "seed"]',
                      '["seed", "replicable"]',
                      '["deterministic"]'])

    def fake(criterion, temperature):
        return next(responses)

    tb = sample_term_bank("Reproducible work", fake, n=3)
    assert set(tb) == {"reproducible", "seed", "replicable", "deterministic"}


def test_suggest_hints_skips_judgment_and_already_hinted():
    rows = [
        {"criterion": "Reproducible work", "checkability": "mechanical", "evidence_hint": None},
        {"criterion": "Critical insight", "checkability": "judgment", "evidence_hint": None},
        {"criterion": "Cited", "checkability": "mechanical", "evidence_hint": "APA; ≥3"},
    ]
    hints = suggest_hints(rows, lambda c, t: '["term-a", "term-b"]', n=1)
    assert set(hints) == {"Reproducible work"}  # judgment + hinted rows skipped


# --- table editor: only fills empty cells ----------------------------------

_RUBRIC_NO_HINT_COL = (
    "## Criteria\n\n"
    "| # | Criterion | Checkability |\n"
    "|---|-----------|--------------|\n"
    "| 1 | Reproducible work | mechanical |\n"
    "| 2 | Critical insight | judgment |\n"
)

_RUBRIC_WITH_HINTS = (
    "| Criterion | Checkability | Evidence hint |\n"
    "|---|---|---|\n"
    "| Reproducible work | mechanical |  |\n"
    "| Cited | mechanical | APA; target ≥3 |\n"
)


def test_adds_evidence_hint_column_when_absent():
    new, filled = apply_hints_to_rubric(_RUBRIC_NO_HINT_COL, {"Reproducible work": ["seed", "replicable"]})
    assert filled == 1
    assert "Evidence hint" in new
    rows, issues = parse_checkability(new)
    assert issues == []
    repro = next(r for r in rows if r["criterion"] == "Reproducible work")
    assert repro["evidence_hint"] == "seed, replicable"
    # round-trip through S1b's hint parser
    assert set(parse_evidence_hint(repro["evidence_hint"])["terms"]) == {"seed", "replicable"}


def test_fills_empty_cell_but_never_overwrites_existing_hint():
    new, filled = apply_hints_to_rubric(
        _RUBRIC_WITH_HINTS,
        {"Reproducible work": ["seed"], "Cited": ["should", "not", "appear"]})
    assert filled == 1  # only the empty Reproducible-work cell
    rows, _ = parse_checkability(new)
    assert next(r for r in rows if r["criterion"] == "Reproducible work")["evidence_hint"] == "seed"
    # the pre-existing APA hint is untouched
    assert next(r for r in rows if r["criterion"] == "Cited")["evidence_hint"] == "APA; target ≥3"


def test_no_checkability_table_is_a_noop():
    text = "# Rubric\n\njust prose\n"
    new, filled = apply_hints_to_rubric(text, {"X": ["y"]})
    assert new == text and filled == 0

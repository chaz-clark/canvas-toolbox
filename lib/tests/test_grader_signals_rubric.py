"""Unit tests — grader_signals rubric-derived evidence (issue #192, Sprint 1b).

Option C: per-criterion evidence derives a term-bank from the criterion text by
default and overrides with the Evidence hint. Routing is by checkability (HG-1):
judgment rows get NO term matching; mechanical/coverage get term-banks / coverage /
citations. Everything stays evidence-to-verify (HG-3).
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_signals import (  # noqa: E402
    derive_term_bank,
    parse_evidence_hint,
    criterion_evidence,
    rubric_evidence,
)


# --- derive_term_bank ------------------------------------------------------

def test_term_bank_keeps_content_drops_boilerplate_and_numbers():
    tb = derive_term_bank("≥3 scholarly citations (APA)")
    assert "scholarly" in tb and "citations" in tb and "apa" in tb
    assert "3" not in tb and "includes" not in tb


def test_term_bank_drops_grading_verbs():
    tb = derive_term_bank("Demonstrates a reproducible workflow")
    assert "reproducible" in tb and "workflow" in tb
    assert "demonstrates" not in tb and "a" not in tb


# --- parse_evidence_hint ---------------------------------------------------

def test_hint_target_and_citation_type():
    h = parse_evidence_hint("APA (Author, YEAR); target ≥3")
    assert h["target"] == 3
    assert "APA" in h["citation_types"]


def test_hint_coverage_item_list():
    h = parse_evidence_hint("prompts: sampling, cleaning, visualization")
    assert h["coverage_items"] == ["sampling", "cleaning", "visualization"]


def test_hint_plain_terms():
    h = parse_evidence_hint("monte carlo, random seed")
    assert h["terms"] == ["monte carlo", "random seed"]
    assert h["coverage_items"] == []


# --- criterion_evidence: routing by checkability ---------------------------

def test_judgment_row_gets_no_term_matching():
    row = {"criterion": "Demonstrates critical insight", "checkability": "judgment"}
    out = criterion_evidence(row, "Some deep text about insight and synthesis.")
    sigs = [e["signal"] for e in out["evidence"]]
    assert sigs == ["judgment_row"]
    assert out["evidence"][0]["value"] is None  # never an NLP verdict on judgment


def test_mechanical_row_derives_term_bank_and_counts_hits():
    row = {"criterion": "Reproducible workflow stated", "checkability": "mechanical"}
    text = "The workflow is reproducible: seeds and a reproducible pipeline are given."
    out = criterion_evidence(row, text)
    tb = next(e for e in out["evidence"] if e["signal"] == "term_bank_hits")
    assert tb["value"] >= 2  # 'reproducible' x2 + 'workflow' x1
    assert "paraphrase" in tb["framing"].lower()  # evidence-to-verify, not verdict


def test_citation_criterion_routes_to_citation_counts():
    row = {"criterion": "At least 3 citations", "checkability": "mechanical",
           "evidence_hint": "APA; target ≥3"}
    text = "See (Smith, 2020), (Jones, 2021), and (Lee et al., 2019)."
    out = criterion_evidence(row, text)
    cit = next(e for e in out["evidence"] if e["signal"] == "citations")
    assert cit["value"] == 3 and "target ≥3" in cit["framing"]


def test_coverage_reports_missing_items():
    row = {"criterion": "Addresses all steps", "checkability": "coverage",
           "evidence_hint": "items: sampling, cleaning, visualization"}
    text = "We did sampling and cleaning carefully."   # visualization missing
    out = criterion_evidence(row, text)
    cov = next(e for e in out["evidence"] if e["signal"] == "coverage")
    assert cov["value"] == "2/3"
    assert "visualization" in cov["framing"]


def test_coverage_without_item_list_notes_the_gap():
    row = {"criterion": "Covers the required analysis", "checkability": "coverage"}
    out = criterion_evidence(row, "some analysis text")
    cov = next(e for e in out["evidence"] if e["signal"] == "coverage")
    assert cov["value"] is None and "item list" in cov["framing"]


# --- rubric_evidence end-to-end --------------------------------------------

def test_rubric_evidence_maps_every_criterion():
    rubric = ("| Criterion | Checkability |\n|---|---|\n"
              "| Includes a thesis | mechanical |\n"
              "| Critical insight | judgment |\n")
    out, issues = rubric_evidence(rubric, "A clear thesis is stated. Insightful too.")
    assert issues == []
    assert [c["criterion"] for c in out] == ["Includes a thesis", "Critical insight"]
    assert [c["checkability"] for c in out] == ["mechanical", "judgment"]


def test_rubric_evidence_surfaces_a_missing_table():
    out, issues = rubric_evidence("# Rubric\n\nno table\n", "text")
    assert out == [] and issues

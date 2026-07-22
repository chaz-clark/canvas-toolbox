"""Unit tests — grader_signals prose evidence (issue #192, Sprint 1a).

The prose signal pool is criterion-independent EVIDENCE (Sprint 1b maps it to the
rubric). Two things must hold: the counts are right, and every item is framed as
evidence-to-verify + carries a valid taxonomy tag (never a met/unmet verdict — HG-3).
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_signals import prose_evidence, analyze  # noqa: E402

_VALID_TAGS = {"structural", "evaluative", "judgment-hint"}


def _by_signal(text):
    return {e["signal"]: e for e in prose_evidence(text)}


def test_every_item_is_tagged_and_framed_as_evidence():
    ev = prose_evidence("# Intro\n\nSome prose with a question? Yes.\n")
    assert ev, "expected evidence items"
    for e in ev:
        assert e["tag"] in _VALID_TAGS, e
        assert e["framing"] and isinstance(e["framing"], str)
        # framing must not read as a verdict
        assert "met" not in e["framing"].lower().split() and "unmet" not in e["framing"].lower()


def test_word_count_excludes_code():
    text = "# Title\n\nfour words in prose\n\n```python\nthis code should not count at all\n```\n"
    wc = _by_signal(text)["word_count"]["value"]
    # "Title four words in prose" = 5 words; code block excluded
    assert wc == 5


def test_apa_inline_citations_detected():
    text = "As shown (Smith, 2020) and (Jones & Lee, 2021) and (Doe et al., 2019), the trend holds."
    assert _by_signal(text)["apa_inline_citations"]["value"] == 3


def test_zero_citations_framing_points_to_paraphrase_not_verdict():
    e = _by_signal("No citations here at all.")["apa_inline_citations"]
    assert e["value"] == 0
    assert "paraphrase" in e["framing"].lower()  # evidence-to-verify, not "criterion unmet"


def test_doi_url_and_references_section():
    text = ("See https://example.com/x and doi 10.1000/abc123.\n\n"
            "## References\n\n- Smith 2020\n")
    by = _by_signal(text)
    assert by["urls"]["value"] >= 1
    assert by["doi_references"]["value"] == 1
    assert by["has_references_section"]["value"] is True


def test_no_references_heading_flags_for_verification():
    e = _by_signal("Body with an inline (Smith, 2020) but no heading.")["has_references_section"]
    assert e["value"] is False
    assert "inline" in e["framing"].lower()


def test_sections_and_paragraphs_counted():
    text = "# A\n\npara one\n\n## B\n\npara two\n\npara three\n"
    by = _by_signal(text)
    assert by["section_count"]["value"] == 2
    assert by["paragraph_count"]["value"] >= 3


def test_analyze_includes_prose_evidence():
    """Wiring guard: analyze() must carry prose_evidence into the signals dict
    that gets written to _signals.json."""
    result = analyze("# H\n\nsome prose (Smith, 2020).\n", ["pandas"])
    assert "prose_evidence" in result
    assert any(e["signal"] == "apa_inline_citations" for e in result["prose_evidence"])

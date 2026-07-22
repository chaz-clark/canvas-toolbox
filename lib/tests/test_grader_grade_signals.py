"""Unit tests — grader_grade signal injection (issue #192, Sprint 2).

--with-signals (rich=True) must inject the S1a/S1b evidence with its framing so the
passes read it as evidence, not verdicts. Default (rich=False) stays cheap: compact
scalar signals only, and the nested structures must NOT dump as raw dicts.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_grade import _format_priors  # noqa: E402

_PRIORS = {"KC3-A": {
    "cells": 3, "outputs": 2, "injection_flags": 0,
    "prose_evidence": [
        {"signal": "apa_inline_citations", "value": 0, "tag": "evaluative",
         "framing": "0 literal matches — check for paraphrase"},
    ],
    "criteria": [
        {"criterion": "Includes a thesis", "checkability": "mechanical",
         "evidence": [{"signal": "term_bank_hits", "value": 1, "tag": "evaluative",
                       "framing": "term-bank (derived): 1 hit — check paraphrase if low"}]},
    ],
}}


def _fmt(rich):
    return _format_priors({"KC3-A": _PRIORS["KC3-A"]}, rich=rich)


def test_empty_priors_render_to_empty_string():
    assert _format_priors(None) == ""
    assert _format_priors({}) == ""


def test_default_is_scalar_only_no_raw_dicts():
    out = _fmt(rich=False)
    assert "cells=3" in out and "outputs=2" in out
    # the nested evidence is NOT injected, and never dumps as a raw dict
    assert "check for paraphrase" not in out
    assert "criterion" not in out
    assert "prose_evidence=" not in out and "criteria=" not in out


def test_rich_injects_framed_prose_and_criterion_evidence():
    out = _fmt(rich=True)
    assert "cells=3" in out                                   # scalars still there
    assert "check for paraphrase" in out                      # prose evidence framing
    assert '"Includes a thesis"' in out and "mechanical" in out
    assert "term-bank" in out                                 # per-criterion evidence framing


def test_rich_evidence_is_framed_not_a_verdict():
    out = _fmt(rich=True)
    # framing language, not met/unmet verdicts
    low = out.lower()
    assert " unmet" not in low and "met criterion" not in low

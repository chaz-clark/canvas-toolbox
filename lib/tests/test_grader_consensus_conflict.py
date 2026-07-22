"""Unit tests — grader_consensus tier-vs-priors conflict audit (issue #192, Sprint 3).

The deterministic audit routes CONFLICTS to a human (HG-4) and never moves a score.
Two directions must fire: top-band-but-thin-evidence (too generous) and
bottom-band-but-evidence-present (possible undergrade — the HG-6 direction).
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_consensus import conflict_check, _criterion_is_weak  # noqa: E402


def _crit(name, tag, *values):
    return {"criterion": name, "checkability": tag,
            "evidence": [{"signal": f"s{i}", "value": v, "tag": "evaluative", "framing": ""}
                         for i, v in enumerate(values)]}


# --- _criterion_is_weak ----------------------------------------------------

def test_weak_when_all_numeric_evidence_is_zero():
    assert _criterion_is_weak(_crit("X", "mechanical", 0, 0)) is True


def test_not_weak_with_any_hit():
    assert _criterion_is_weak(_crit("X", "mechanical", 0, 2)) is False


def test_coverage_zero_over_n_is_weak():
    assert _criterion_is_weak(_crit("X", "coverage", "0/3")) is True
    assert _criterion_is_weak(_crit("X", "coverage", "2/3")) is False


def test_judgment_never_weak():
    assert _criterion_is_weak(_crit("X", "judgment")) is False


def test_boolean_presence_signal_does_not_make_weak():
    # has_references_section=False alone is presence info, not a zero-strength count
    assert _criterion_is_weak(_crit("X", "mechanical", False)) is False


# --- conflict_check --------------------------------------------------------

_STRONG = {"criteria": [_crit("A", "mechanical", 3), _crit("B", "coverage", "3/3")]}
_THIN = {"criteria": [_crit("A", "mechanical", 0), _crit("B", "coverage", "0/3"),
                      _crit("C", "mechanical", 0)]}


def test_top_band_but_thin_evidence_conflicts():
    flag, reason = conflict_check(4.0, lo=1.0, hi=4.0, submission_evidence=_THIN)
    assert flag is True and "top-band" in reason


def test_bottom_band_but_evidence_present_conflicts_hg6():
    flag, reason = conflict_check(1.0, lo=1.0, hi=4.0, submission_evidence=_STRONG)
    assert flag is True and "undergrade" in reason.lower()


def test_mid_band_no_conflict():
    flag, _ = conflict_check(2.5, lo=1.0, hi=4.0, submission_evidence=_THIN)
    assert flag is False


def test_no_band_spread_no_conflict():
    assert conflict_check(4.0, lo=4.0, hi=4.0, submission_evidence=_THIN)[0] is False


def test_no_evidence_no_conflict():
    assert conflict_check(4.0, lo=1.0, hi=4.0, submission_evidence={})[0] is False


def test_only_judgment_rows_no_conflict():
    ev = {"criteria": [_crit("Insight", "judgment")]}
    assert conflict_check(1.0, lo=1.0, hi=4.0, submission_evidence=ev)[0] is False

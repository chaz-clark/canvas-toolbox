"""Tier 1 unit tests — grader_competency_grade pure-logic helpers.

Source: lib/tools/grader_competency_grade.py (#60 — competency-based
grading layered on top of `grader_reconcile`'s completion counts).

  - evaluate_tier_thresholds: all counts >= thresholds? returns (ok, missing[])
  - assign_band: highest tier with ALL thresholds met wins; below-tier rules
    iterate in order with `else` catch-all.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_competency_grade import (  # noqa: E402
    evaluate_tier_thresholds,
    assign_band,
)


# ---------------------------------------------------------------------------
# evaluate_tier_thresholds
# ---------------------------------------------------------------------------

def test_thresholds_all_met():
    ok, missing = evaluate_tier_thresholds(
        counts={"core": 5, "stretch": 2},
        thresholds={"core": 3, "stretch": 1},
    )
    assert ok is True
    assert missing == []


def test_thresholds_one_short():
    ok, missing = evaluate_tier_thresholds(
        counts={"core": 2, "stretch": 1},
        thresholds={"core": 3, "stretch": 1},
    )
    assert ok is False
    assert missing == ["core 2<3"]


def test_thresholds_multiple_short():
    ok, missing = evaluate_tier_thresholds(
        counts={"core": 0, "stretch": 0},
        thresholds={"core": 3, "stretch": 1},
    )
    assert ok is False
    assert set(missing) == {"core 0<3", "stretch 0<1"}


def test_thresholds_missing_count_treated_as_zero():
    """An element absent from `counts` is treated as count=0 (not crash)."""
    ok, missing = evaluate_tier_thresholds(
        counts={"core": 5},  # no `stretch` key
        thresholds={"core": 3, "stretch": 1},
    )
    assert ok is False
    assert "stretch 0<1" in missing


def test_thresholds_empty_requirements_always_ok():
    ok, missing = evaluate_tier_thresholds(counts={}, thresholds={})
    assert ok is True
    assert missing == []


# ---------------------------------------------------------------------------
# assign_band — tier + below rules
# ---------------------------------------------------------------------------

_TIERS = [
    {"grade": "A", "score": 4.0, "thresholds": {"core": 5, "stretch": 2}},
    {"grade": "B", "score": 3.0, "thresholds": {"core": 4, "stretch": 1}},
    {"grade": "C", "score": 2.0, "thresholds": {"core": 3}},
]

_BELOW = [
    {"grade": "D", "score": 1.0, "when": {"core": ">=1"}},
    {"grade": "F", "score": 0.0, "when": "else"},
]


def test_assign_band_top_tier():
    g, s, r = assign_band({"core": 6, "stretch": 3}, _TIERS, _BELOW)
    assert g == "A"
    assert s == 4.0
    assert "meets A fully" in r


def test_assign_band_middle_tier():
    g, s, r = assign_band({"core": 4, "stretch": 1}, _TIERS, _BELOW)
    assert g == "B"


def test_assign_band_bottom_tier():
    g, s, _ = assign_band({"core": 3, "stretch": 0}, _TIERS, _BELOW)
    assert g == "C"
    assert s == 2.0


def test_assign_band_below_tier_d():
    """Below C threshold (core<3) but at least 1 core → D rule fires."""
    g, s, r = assign_band({"core": 1, "stretch": 0}, _TIERS, _BELOW)
    assert g == "D"
    assert s == 1.0
    assert "did not meet C" in r


def test_assign_band_else_falls_to_f():
    g, s, r = assign_band({"core": 0, "stretch": 0}, _TIERS, _BELOW)
    assert g == "F"
    assert s == 0.0


def test_assign_band_no_below_rules_defaults_to_f():
    """When no below rules match (and no else), fall through to F."""
    g, s, _ = assign_band({"core": 0}, _TIERS, below=[])
    assert g == "F"
    assert s == 0.0


def test_assign_band_empty_tiers():
    """With no tiers at all, no below match → F default."""
    g, s, _ = assign_band({"core": 99}, tiers=[], below=[])
    assert g == "F"
    assert s == 0.0

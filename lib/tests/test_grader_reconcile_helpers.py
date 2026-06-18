"""Tier 1 unit tests — grader_reconcile pure-logic helpers.

Source: lib/tools/grader_reconcile.py::_is_complete_under_basis (#59 —
completion_basis per dimension: submitted / nonzero / full_credit).
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_reconcile import (  # noqa: E402
    _is_complete_under_basis,
    _is_at_full_ratio,
    _resolve_at_full_ratio,
)


# basis = "submitted" — only `submitted` flag matters
def test_submitted_basis_true_when_submitted():
    assert _is_complete_under_basis({"submitted": True}, 10.0, "submitted") is True


def test_submitted_basis_false_when_not_submitted():
    assert _is_complete_under_basis({"submitted": False}, 10.0, "submitted") is False


def test_submitted_basis_missing_field_is_false():
    assert _is_complete_under_basis({}, 10.0, "submitted") is False


# basis = "nonzero" — score must be present AND > 0
def test_nonzero_basis_positive_score():
    assert _is_complete_under_basis({"score": 5.0}, 10.0, "nonzero") is True


def test_nonzero_basis_zero_score():
    assert _is_complete_under_basis({"score": 0.0}, 10.0, "nonzero") is False


def test_nonzero_basis_none_score():
    """None score never counts as complete — submitted_at alone is not enough."""
    assert _is_complete_under_basis({"score": None}, 10.0, "nonzero") is False


def test_nonzero_basis_unparseable_score():
    assert _is_complete_under_basis({"score": "garbage"}, 10.0, "nonzero") is False


# basis = "full_credit" — score must equal points_possible exactly
def test_full_credit_basis_exact_match():
    assert _is_complete_under_basis({"score": 10.0}, 10.0, "full_credit") is True


def test_full_credit_basis_partial_score():
    assert _is_complete_under_basis({"score": 9.0}, 10.0, "full_credit") is False


def test_full_credit_basis_none_points_possible():
    """Can't compute full-credit without knowing the max."""
    assert _is_complete_under_basis({"score": 10.0}, None, "full_credit") is False


def test_full_credit_basis_floating_point_tolerance():
    """`abs(score - max) < 1e-9` — defends against float drift in
    score arithmetic. A delta of 1e-10 (well inside the tolerance) must
    still register as complete."""
    assert _is_complete_under_basis({"score": 10.0 + 1e-10}, 10.0, "full_credit") is True


# Unknown basis — always False
def test_unknown_basis_returns_false():
    assert _is_complete_under_basis({"score": 10.0}, 10.0, "no_such_basis") is False


# ---------------------------------------------------------------------------
# _is_at_full_ratio — issue #47 — specs-grading "@100%" / "@N%" check
# ---------------------------------------------------------------------------

def test_at_full_ratio_strict_100_pct_match():
    """ratio=1.0 + score == points_possible → True."""
    assert _is_at_full_ratio({"score": 4.0}, 4.0, 1.0) is True


def test_at_full_ratio_below_threshold():
    """ratio=1.0 + score < points_possible → False (classic specs-grading
    "3/4 doesn't count as @100%" case)."""
    assert _is_at_full_ratio({"score": 3.0}, 4.0, 1.0) is False


def test_at_full_ratio_90_pct_threshold_passes():
    """ratio=0.9 + score=3.6 / 4.0 (= 90%) → True (>=, not >)."""
    assert _is_at_full_ratio({"score": 3.6}, 4.0, 0.9) is True


def test_at_full_ratio_90_pct_threshold_fails():
    """ratio=0.9 + score=3.5 / 4.0 (= 87.5%) → False."""
    assert _is_at_full_ratio({"score": 3.5}, 4.0, 0.9) is False


def test_at_full_ratio_none_score():
    """None score never counts (parallel to _is_complete_under_basis)."""
    assert _is_at_full_ratio({"score": None}, 4.0, 1.0) is False


def test_at_full_ratio_none_points_possible():
    """Without points_possible we can't compute the threshold → False."""
    assert _is_at_full_ratio({"score": 4.0}, None, 1.0) is False


def test_at_full_ratio_unparseable_score():
    assert _is_at_full_ratio({"score": "garbage"}, 4.0, 1.0) is False


def test_at_full_ratio_float_drift_tolerance():
    """1e-9 tolerance: a score 1e-10 BELOW the threshold still passes."""
    assert _is_at_full_ratio({"score": 4.0 - 1e-10}, 4.0, 1.0) is True


# ---------------------------------------------------------------------------
# _resolve_at_full_ratio — config syntax resolution (issue #47 syntax options)
# ---------------------------------------------------------------------------

def test_resolve_explicit_at_full_ratio():
    """Preferred syntax: explicit `at_full_ratio: 0.9`."""
    assert _resolve_at_full_ratio({"at_full_ratio": 0.9}) == 0.9


def test_resolve_at_full_ratio_defaults_to_one():
    """Explicit `at_full_ratio: 1.0` is the strict full-credit case."""
    assert _resolve_at_full_ratio({"at_full_ratio": 1.0}) == 1.0


def test_resolve_count_mode_full_credit_alias():
    """`count_mode: full_credit` (alias from issue body) → ratio=1.0."""
    assert _resolve_at_full_ratio({"count_mode": "full_credit"}) == 1.0


def test_resolve_count_mode_at_ratio_alias():
    """`count_mode: at_ratio` + explicit `at_ratio` → that ratio."""
    assert _resolve_at_full_ratio({"count_mode": "at_ratio", "at_ratio": 0.85}) == 0.85


def test_resolve_count_mode_at_ratio_defaults_to_one_when_no_ratio():
    """`count_mode: at_ratio` with no explicit ratio → 1.0."""
    assert _resolve_at_full_ratio({"count_mode": "at_ratio"}) == 1.0


def test_resolve_omitted_returns_none():
    """No at_full_ratio + no count_mode → None (column is omitted)."""
    assert _resolve_at_full_ratio({"dimension": "methods", "source": "gradebook"}) is None


def test_resolve_unparseable_at_full_ratio_returns_none():
    """Garbage in the float field returns None — caller skips the column
    rather than producing nonsense."""
    assert _resolve_at_full_ratio({"at_full_ratio": "not-a-number"}) is None

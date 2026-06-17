"""Tier 1 unit tests — grader_reconcile pure-logic helpers.

Source: lib/tools/grader_reconcile.py::_is_complete_under_basis (#59 —
completion_basis per dimension: submitted / nonzero / full_credit).
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_reconcile import _is_complete_under_basis  # noqa: E402


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

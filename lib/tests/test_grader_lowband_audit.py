"""Unit tests — grader_lowband_audit (issue #192, Sprint 4, HG-6).

The audit re-reads low-band submissions with priors excluded and flags only UPWARD
disagreements (resolve toward the student). It must never lower a grade, never
auto-raise one, and only ever fire on the low band. The LLM is injected as
`grade_fn`, so these run with no provider.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_lowband_audit import low_band_keys, audit_verdict, run_lowband_audit  # noqa: E402


def _rows(*pairs):
    return [{"key": k, "consensus": c} for k, c in pairs]


# --- low_band_keys ---------------------------------------------------------

def test_selects_bottom_fraction():
    rows = _rows(("a", 1.0), ("b", 2.0), ("c", 3.0), ("d", 4.0))
    # range 1..4, thresh = 1 + 0.25*3 = 1.75 → only 'a'
    assert low_band_keys(rows, frac=0.25) == ["a"]


def test_no_spread_no_low_band():
    assert low_band_keys(_rows(("a", 3.0), ("b", 3.0))) == []


def test_empty_rows():
    assert low_band_keys([]) == []


# --- audit_verdict: never lowers, fires only upward -------------------------

def test_upward_disagreement_flags_undergrade():
    flag, reason = audit_verdict(consensus=2.0, audit_score=3.0)
    assert flag is True and "toward the student" in reason


def test_equal_or_lower_audit_corroborates_not_flags():
    assert audit_verdict(2.0, 2.0)[0] is False       # equal → corroborated
    assert audit_verdict(2.0, 1.0)[0] is False       # lower → never lowers, no flag


def test_missing_audit_score_does_not_flag():
    flag, reason = audit_verdict(2.0, None)
    assert flag is False and "manually" in reason


# --- run_lowband_audit with an injected grader -----------------------------

def test_run_audit_flags_only_the_undergraded():
    low = _rows(("a", 1.0), ("b", 1.0))
    # 'a' re-reads higher (undergrade), 'b' re-reads the same (corroborated)
    grades = {"a": ("Meets", 3.0), "b": ("Developing", 1.0)}
    records = run_lowband_audit(low, lambda k: grades[k])
    by = {r["key"]: r for r in records}
    assert by["a"]["undergrade_suspected"] is True
    assert by["b"]["undergrade_suspected"] is False
    # never mutates the consensus
    assert by["a"]["consensus"] == 1.0 and by["a"]["audit_score"] == 3.0


def test_run_audit_records_shape():
    records = run_lowband_audit(_rows(("a", 1.0)), lambda k: ("Meets", 4.0))
    r = records[0]
    assert set(r) == {"key", "consensus", "audit_band", "audit_score",
                      "undergrade_suspected", "audit_reason"}

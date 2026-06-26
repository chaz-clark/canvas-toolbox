"""Tier 1 unit tests — student_quiz_time_extension pure-logic helpers.

Source: lib/tools/student_quiz_time_extension.py
  - compute_extra_minutes   (multiplier → extra minutes, ceil)
  - filter_timed_quizzes    (skip untimed quizzes)
  - resolve_user_id_from_master  (CSV lookup, PII-aware)
  - build_extension_payload (POST body construction)

No Canvas API calls. Pure functions in/out.
"""
import csv
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from student_quiz_time_extension import (  # noqa: E402
    build_extension_payload,
    compute_extra_minutes,
    filter_timed_quizzes,
    resolve_user_id_from_master,
)


# ---------------------------------------------------------------------------
# compute_extra_minutes — multiplier to extra minutes
# ---------------------------------------------------------------------------

def test_extra_minutes_15x_on_60min_quiz():
    """1.5x on a 60-minute quiz → 30 extra minutes (50% of 60)."""
    assert compute_extra_minutes(60, 1.5) == 30


def test_extra_minutes_20x_on_60min_quiz():
    """2.0x on a 60-minute quiz → 60 extra minutes (double time)."""
    assert compute_extra_minutes(60, 2.0) == 60


def test_extra_minutes_125x_on_60min_quiz():
    """1.25x on a 60-minute quiz → 15 extra minutes."""
    assert compute_extra_minutes(60, 1.25) == 15


def test_extra_minutes_ceils_partial_minute():
    """1.5x on a 45-minute quiz → 22.5 → ceil → 23 minutes.
    Always round UP so the student never gets less than promised."""
    assert compute_extra_minutes(45, 1.5) == 23


def test_extra_minutes_ceils_one_third():
    """1.33x on a 60-minute quiz → 19.8 → 20 minutes."""
    assert compute_extra_minutes(60, 1.33) == 20


def test_extra_minutes_none_for_untimed_quiz():
    """time_limit is None (untimed quiz) → return None so caller skips."""
    assert compute_extra_minutes(None, 1.5) is None


def test_extra_minutes_none_for_zero_time_limit():
    """A time_limit of 0 (or negative) is meaningless → return None."""
    assert compute_extra_minutes(0, 1.5) is None
    assert compute_extra_minutes(-5, 1.5) is None


def test_extra_minutes_zero_at_multiplier_1():
    """1.0x = no extension → 0 extra minutes (caller may skip)."""
    assert compute_extra_minutes(60, 1.0) == 0


def test_extra_minutes_zero_at_multiplier_less_than_1():
    """Multiplier < 1 doesn't make sense for accommodations; return 0
    rather than negative. (CLI validates > 1.0 before getting here, but
    the helper is defensive.)"""
    assert compute_extra_minutes(60, 0.5) == 0


# ---------------------------------------------------------------------------
# filter_timed_quizzes — skip untimed quizzes
# ---------------------------------------------------------------------------

def test_filter_keeps_quiz_with_time_limit():
    quizzes = [{"id": 1, "time_limit": 60}]
    assert len(filter_timed_quizzes(quizzes)) == 1


def test_filter_drops_quiz_with_null_time_limit():
    """Untimed quizzes don't need an extension."""
    quizzes = [{"id": 1, "time_limit": None}]
    assert filter_timed_quizzes(quizzes) == []


def test_filter_drops_quiz_with_missing_time_limit_key():
    """Defensive: time_limit key absent entirely."""
    quizzes = [{"id": 1}]
    assert filter_timed_quizzes(quizzes) == []


def test_filter_drops_quiz_with_zero_time_limit():
    quizzes = [{"id": 1, "time_limit": 0}]
    assert filter_timed_quizzes(quizzes) == []


def test_filter_mixed_set():
    quizzes = [
        {"id": 1, "time_limit": 60},   # keep
        {"id": 2, "time_limit": None}, # drop
        {"id": 3, "time_limit": 30},   # keep
        {"id": 4},                      # drop
        {"id": 5, "time_limit": 0},    # drop
    ]
    out = filter_timed_quizzes(quizzes)
    assert sorted(q["id"] for q in out) == [1, 3]


# ---------------------------------------------------------------------------
# resolve_user_id_from_master — CSV lookup (duplicated helper)
# ---------------------------------------------------------------------------

def _write_master(tmp_path: Path) -> Path:
    p = tmp_path / ".deid_master.csv"
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["deid_code", "user_id",
                                            "sortable_name", "withdrawn"])
        w.writeheader()
        w.writerow({"deid_code": "S-95DBB6", "user_id": "173819",
                    "sortable_name": "Ahlstrom, Sydney", "withdrawn": "0"})
    return p


def test_resolve_basic(tmp_path):
    p = _write_master(tmp_path)
    assert resolve_user_id_from_master(p, "S-95DBB6") == 173819


def test_resolve_case_insensitive(tmp_path):
    p = _write_master(tmp_path)
    assert resolve_user_id_from_master(p, "s-95dbb6") == 173819


def test_resolve_missing_master_points_at_builder(tmp_path):
    nope = tmp_path / "absent.csv"
    with pytest.raises(FileNotFoundError) as exc_info:
        resolve_user_id_from_master(nope, "S-X")
    assert "build_deid_master" in str(exc_info.value)


def test_resolve_missing_code(tmp_path):
    p = _write_master(tmp_path)
    with pytest.raises(KeyError):
        resolve_user_id_from_master(p, "S-NOTHERE")


# ---------------------------------------------------------------------------
# build_extension_payload — POST body
# ---------------------------------------------------------------------------

def test_payload_includes_user_id():
    payload = build_extension_payload(user_id=173819, extra_time_minutes=30)
    assert payload["quiz_extensions[][user_id]"] == 173819


def test_payload_includes_extra_time():
    payload = build_extension_payload(user_id=1, extra_time_minutes=30)
    assert payload["quiz_extensions[][extra_time]"] == 30


def test_payload_canvas_array_syntax():
    """Canvas requires array-suffix keys ([]) for quiz_extensions.
    If we ever drop them, the API silently ignores the extension."""
    payload = build_extension_payload(user_id=1, extra_time_minutes=30)
    for key in payload:
        assert "[]" in key, f"missing array syntax in key: {key}"

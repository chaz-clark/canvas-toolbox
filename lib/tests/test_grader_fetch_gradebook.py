"""Unit tests — grader_fetch_gradebook pure logic (the de-identified gradebook mirror).

Covers the matrix build (de-identification + Test-Student exclusion + duplicate-column
disambiguation) and the freshness check that lets skills reuse a cache instead of
re-hitting Canvas.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_fetch_gradebook import build_matrix, is_fresh  # noqa: E402

_ASN = [
    {"id": 10, "name": "KC1", "points_possible": 4, "position": 1},
    {"id": 11, "name": "KC2", "points_possible": 4, "position": 2},
]


def test_build_matrix_is_deidentified_and_user_keyed():
    """Rows are keyed by user_id with scores — never a name column (the whole point:
    Zone-1, LLM-safe)."""
    scores = {501: {10: 4, 11: 3}, 502: {10: 2}}
    header, rows = build_matrix(_ASN, scores, exclude=set())
    assert header == ["user_id", "KC1", "KC2"]
    assert rows == [[501, 4, 3], [502, 2, ""]]   # missing score → blank, sorted by uid


def test_build_matrix_excludes_test_student():
    scores = {501: {10: 4}, 999: {10: 1}}
    _, rows = build_matrix(_ASN, scores, exclude={999})
    assert [r[0] for r in rows] == [501]


def test_build_matrix_disambiguates_duplicate_assignment_names():
    asn = [{"id": 10, "name": "Quiz", "points_possible": 1, "position": 1},
           {"id": 11, "name": "Quiz", "points_possible": 1, "position": 2}]
    header, _ = build_matrix(asn, {501: {10: 1, 11: 0}}, exclude=set())
    assert header == ["user_id", "Quiz", "Quiz (11)"]


def test_build_matrix_preserves_given_column_order():
    """build_matrix follows the assignment order it's handed (fetch_assignments
    already position-sorts upstream); cells align to that column order."""
    asn = [{"id": 10, "name": "First", "points_possible": 1, "position": 1},
           {"id": 11, "name": "Second", "points_possible": 1, "position": 2}]
    header, rows = build_matrix(asn, {501: {11: 2, 10: 1}}, exclude=set())
    assert header == ["user_id", "First", "Second"]
    assert rows == [[501, 1, 2]]  # cell for id 10 under First, id 11 under Second


def _write_meta(tmp_path, fetched_at):
    p = tmp_path / ".fetch_meta.json"
    p.write_text(json.dumps({"fetched_at": fetched_at}), encoding="utf-8")
    return p


def test_is_fresh_true_when_recent():
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _write_meta(Path(d), (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        assert is_fresh(p, 6.0, now) is True


def test_is_fresh_false_when_stale():
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _write_meta(Path(d), (now - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        assert is_fresh(p, 6.0, now) is False


def test_is_fresh_false_when_missing_or_malformed(tmp_path):
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    assert is_fresh(tmp_path / "nope.json", 6.0, now) is False
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert is_fresh(bad, 6.0, now) is False

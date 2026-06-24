"""Tier 1 unit tests — grader_push pure-logic helpers.

Source: lib/tools/grader_push.py
  - extract_hold_token (#72 — HOLD_<DIM> grade-hold pattern)
  - comment_has_resubmit_language (#63 — resubmit-aware availability gating)
  - collision_warnings_for_submission (#62 — pre-push collision guard)
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_push import (  # noqa: E402
    extract_hold_token,
    comment_has_resubmit_language,
    collision_warnings_for_submission,
    consensus_gate_status,
)


# ---------------------------------------------------------------------------
# extract_hold_token — read HOLD_<DIM> from top-of-file heading
# ---------------------------------------------------------------------------

def test_extract_hold_token_finds_marker(tmp_path):
    f = tmp_path / "feedback.md"
    f.write_text(
        "# KC1-A1B2C3 · 4 · PUSH · HOLD_HOURS\n"
        "\n"
        "## Score\n"
        "4/5\n",
        encoding="utf-8",
    )
    assert extract_hold_token(str(f)) == "HOLD_HOURS"


def test_extract_hold_token_no_marker(tmp_path):
    f = tmp_path / "feedback.md"
    f.write_text(
        "# KC1-A1B2C3 · 4 · PUSH\n"
        "\n"
        "## Score\n4/5\n",
        encoding="utf-8",
    )
    assert extract_hold_token(str(f)) is None


def test_extract_hold_token_missing_file_returns_none(tmp_path):
    assert extract_hold_token(str(tmp_path / "does_not_exist.md")) is None


def test_extract_hold_token_empty_path_returns_none():
    assert extract_hold_token("") is None


def test_extract_hold_token_only_scans_first_three_headings(tmp_path):
    """The marker must be at the TOP of the file — past the 3rd heading,
    later HOLD_ tokens in the body are ignored."""
    f = tmp_path / "feedback.md"
    f.write_text(
        "# Title\n"
        "## Heading 2\n"
        "### Heading 3\n"
        "### Heading 4 · HOLD_LATE\n"  # past the 3-heading scan window
        "\nbody text · HOLD_FAKE\n",
        encoding="utf-8",
    )
    assert extract_hold_token(str(f)) is None


def test_extract_hold_token_dim_uppercase_required(tmp_path):
    """The pattern requires `HOLD_[A-Z][A-Z0-9_]*` — lowercase doesn't match."""
    f = tmp_path / "feedback.md"
    f.write_text("# KC1-A1B2C3 · 4 · PUSH · hold_hours\n", encoding="utf-8")
    assert extract_hold_token(str(f)) is None


# ---------------------------------------------------------------------------
# comment_has_resubmit_language — detect resubmit instructions in comments
# ---------------------------------------------------------------------------

def test_resubmit_language_detected_simple():
    assert comment_has_resubmit_language("Please resubmit with corrections.") is True


def test_resubmit_language_detected_case_insensitive():
    assert comment_has_resubmit_language("PLEASE RESUBMIT") is True


def test_resubmit_language_negative_cases():
    assert comment_has_resubmit_language("Good work overall.") is False
    assert comment_has_resubmit_language("") is False
    assert comment_has_resubmit_language(None) is False  # type: ignore[arg-type]


def test_resubmit_language_correct_version_phrase():
    """`\\bcorrect\\s+version\\b` — explicitly part of the resubmit vocabulary."""
    assert comment_has_resubmit_language("upload the correct version") is True


# ---------------------------------------------------------------------------
# collision_warnings_for_submission — recent-others + latest-overall
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)


def _comment(role: str, days_ago: float, text: str = "x") -> dict:
    dt = _NOW - timedelta(days=days_ago)
    return {
        "author_role": role,
        "created_at": dt.isoformat().replace("+00:00", "Z"),
        "comment": text,
    }


def test_collision_warnings_recent_others_inside_window():
    """Comments from non-self authors within window → flagged."""
    comments = [
        _comment("teacher", days_ago=2),
        _comment("ta", days_ago=1),
        _comment("self", days_ago=0.5),  # student reply — NOT flagged
    ]
    others, latest = collision_warnings_for_submission(
        comments, window_days=7, now=_NOW,
    )
    assert len(others) == 2
    roles = {c["author_role"] for c in others}
    assert roles == {"teacher", "ta"}


def test_collision_warnings_excludes_outside_window():
    """Old non-self comments are excluded; only recent ones flag."""
    comments = [
        _comment("teacher", days_ago=30),
        _comment("ta", days_ago=2),
    ]
    others, _ = collision_warnings_for_submission(
        comments, window_days=7, now=_NOW,
    )
    assert len(others) == 1
    assert others[0]["author_role"] == "ta"


def test_collision_warnings_latest_overall_includes_self():
    """latest_comment_overall returns the most-recent comment regardless
    of role — used by --skip-if-student-replied."""
    comments = [
        _comment("teacher", days_ago=5, text="initial review"),
        _comment("self", days_ago=0.5, text="student replied last"),
    ]
    others, latest = collision_warnings_for_submission(
        comments, window_days=7, now=_NOW,
    )
    assert latest is not None
    assert latest["author_role"] == "self"
    assert latest["comment"] == "student replied last"


def test_collision_warnings_empty_thread():
    others, latest = collision_warnings_for_submission(
        [], window_days=7, now=_NOW,
    )
    assert others == []
    assert latest is None


def test_collision_warnings_skips_unparseable_created_at():
    """Garbage created_at values are silently skipped, not crashed on."""
    comments = [
        {"author_role": "teacher", "created_at": "not-a-date", "comment": "x"},
        _comment("teacher", days_ago=1),
    ]
    others, latest = collision_warnings_for_submission(
        comments, window_days=7, now=_NOW,
    )
    assert len(others) == 1  # only the parseable one


# ---------------------------------------------------------------------------
# consensus_gate_status — issue #95 (3-pass consensus enforced at push seam)
# ---------------------------------------------------------------------------

def test_consensus_gate_missing(tmp_path):
    """No _consensus.csv → 'missing'; the gate refuses the push."""
    (tmp_path / "_grader1.csv").write_text("key,score\nA1,4\n", encoding="utf-8")
    status, grader_csvs = consensus_gate_status(tmp_path)
    assert status == "missing"
    assert [g.name for g in grader_csvs] == ["_grader1.csv"]


def test_consensus_gate_missing_zero_graders(tmp_path):
    """Empty fbdir → 'missing' (no consensus, no graders); refuse."""
    status, grader_csvs = consensus_gate_status(tmp_path)
    assert status == "missing"
    assert grader_csvs == []


def test_consensus_gate_ok_with_fresh_consensus(tmp_path):
    """Consensus newer than all grader passes → 'ok'."""
    (tmp_path / "_grader1.csv").write_text("k,s\nA,4\n", encoding="utf-8")
    (tmp_path / "_grader2.csv").write_text("k,s\nA,3\n", encoding="utf-8")
    (tmp_path / "_grader3.csv").write_text("k,s\nA,4\n", encoding="utf-8")
    consensus = tmp_path / "_consensus.csv"
    consensus.write_text("k,s,consensus,spread\nA,4|3|4,4,1\n", encoding="utf-8")
    # bump consensus mtime to 60s after the graders so it's unambiguously newer
    import os
    newest = max(
        (tmp_path / f"_grader{n}.csv").stat().st_mtime for n in (1, 2, 3)
    )
    os.utime(consensus, (newest + 60, newest + 60))
    status, grader_csvs = consensus_gate_status(tmp_path)
    assert status == "ok"
    assert len(grader_csvs) == 3


def test_consensus_gate_ok_with_equal_mtime(tmp_path):
    """Consensus mtime == newest grader mtime is OK (not strictly older)."""
    import os
    g = tmp_path / "_grader1.csv"
    g.write_text("k,s\nA,4\n", encoding="utf-8")
    c = tmp_path / "_consensus.csv"
    c.write_text("k,s,consensus,spread\nA,4,4,0\n", encoding="utf-8")
    mt = g.stat().st_mtime
    os.utime(c, (mt, mt))
    status, _ = consensus_gate_status(tmp_path)
    assert status == "ok"


def test_consensus_gate_stale_when_consensus_older(tmp_path):
    """A grader pass re-run AFTER consensus → 'stale'; rerun consensus."""
    import os
    consensus = tmp_path / "_consensus.csv"
    consensus.write_text("k,s,consensus,spread\nA,4,4,0\n", encoding="utf-8")
    grader = tmp_path / "_grader1.csv"
    grader.write_text("k,s\nA,4\n", encoding="utf-8")
    # bump grader mtime to 60s after the consensus to simulate re-run
    base = consensus.stat().st_mtime
    os.utime(grader, (base + 60, base + 60))
    status, grader_csvs = consensus_gate_status(tmp_path)
    assert status == "stale"
    assert [g.name for g in grader_csvs] == ["_grader1.csv"]


def test_consensus_gate_stale_uses_newest_grader_mtime(tmp_path):
    """When multiple grader passes exist, the gate must compare to the NEWEST one.
    A stale grader1 doesn't unstale a fresh consensus if grader3 is freshest."""
    import os
    consensus = tmp_path / "_consensus.csv"
    consensus.write_text("k,s,consensus,spread\nA,4,4,0\n", encoding="utf-8")
    g1 = tmp_path / "_grader1.csv"
    g1.write_text("k,s\nA,4\n", encoding="utf-8")
    g2 = tmp_path / "_grader2.csv"
    g2.write_text("k,s\nA,3\n", encoding="utf-8")
    g3 = tmp_path / "_grader3.csv"
    g3.write_text("k,s\nA,4\n", encoding="utf-8")
    base = consensus.stat().st_mtime
    # g1 + g2 older than consensus; g3 newer → overall newest is newer → stale
    os.utime(g1, (base - 120, base - 120))
    os.utime(g2, (base - 60, base - 60))
    os.utime(g3, (base + 60, base + 60))
    status, _ = consensus_gate_status(tmp_path)
    assert status == "stale"


def test_consensus_gate_ok_when_consensus_present_but_no_graders(tmp_path):
    """Edge case: consensus.csv present, no _grader*.csv files. The freshness
    check requires at least one grader file to compare against; with none,
    the gate doesn't have evidence of a stale consensus and returns 'ok'.
    (In practice this branch is unreachable from --mark-reviewed because
    consensus.py itself refuses to write _consensus.csv without grader passes;
    documenting the behavior so a future refactor doesn't accidentally
    reverse it.)"""
    (tmp_path / "_consensus.csv").write_text(
        "k,s,consensus,spread\nA,4,4,0\n", encoding="utf-8"
    )
    status, grader_csvs = consensus_gate_status(tmp_path)
    assert status == "ok"
    assert grader_csvs == []

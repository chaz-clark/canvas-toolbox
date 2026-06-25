"""Tier 1 unit tests — grader_reidentify pure-logic helpers.

Source: lib/tools/grader_reidentify.py
  - build_user_to_keys (#100 — user_id → submission keys)
  - pick_group_representatives_from_context (#100 — rep selection from fetch_log)
  - mirror_group_rows (#100 — group-mate row mirroring in .review.csv)

These tests do NOT exercise the main() / file-system flow; they hit the
pure helpers directly so the mirror logic is validated without simulating
the full keymap + fetch_log + feedback pipeline.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_reidentify import (  # noqa: E402
    build_user_to_keys,
    pick_group_representatives_from_context,
    mirror_group_rows,
)


# ---------------------------------------------------------------------------
# build_user_to_keys — issue #100 (keymap inversion)
# ---------------------------------------------------------------------------

def test_build_user_to_keys_basic():
    """One uid, one file → one key in the value list."""
    keymap = {"KC1-A1B2C3": "kc1_12345.docx"}
    out = build_user_to_keys(keymap)
    assert out == {12345: ["KC1-A1B2C3"]}


def test_build_user_to_keys_multiple_users():
    """Multiple uids each get their own list."""
    keymap = {
        "KC1-A1": "kc1_111.docx",
        "KC1-B2": "kc1_222.docx",
        "KC1-C3": "kc1_333.docx",
    }
    out = build_user_to_keys(keymap)
    assert set(out.keys()) == {111, 222, 333}
    assert out[111] == ["KC1-A1"]


def test_build_user_to_keys_multi_attachment_per_user():
    """A user with multiple attachment files has multiple keys."""
    keymap = {
        "KC1-A1": "kc1_111_a.docx",
        "KC1-B2": "kc1_111_b.docx",
    }
    out = build_user_to_keys(keymap)
    assert 111 in out
    assert len(out[111]) == 2
    assert set(out[111]) == {"KC1-A1", "KC1-B2"}


def test_build_user_to_keys_handles_unparseable_filenames():
    """Files that don't match the <prefix>_<uid>.<ext> pattern are skipped."""
    keymap = {
        "KC1-A1": "kc1_111.docx",          # ok
        "KC1-B2": "weird-filename.html",    # skipped
        "KC1-C3": "kc1_222.pdf",            # ok
    }
    out = build_user_to_keys(keymap)
    assert set(out.keys()) == {111, 222}


def test_build_user_to_keys_empty_map():
    """Empty keymap → empty dict."""
    assert build_user_to_keys({}) == {}


# ---------------------------------------------------------------------------
# pick_group_representatives_from_context — issue #100
# ---------------------------------------------------------------------------

def test_pick_reps_from_context_smallest_submitter_wins():
    """Rep is the smallest submitting user_id in the group."""
    ctx = {
        "user_to_group": {
            "1": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2, 3]},
            "2": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2, 3]},
            "3": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2, 3]},
        }
    }
    user_to_keys = {2: ["X-AAA"], 3: ["X-BBB"]}  # uid 1 didn't submit
    reps = pick_group_representatives_from_context(ctx, user_to_keys)
    assert reps == {10: 2}


def test_pick_reps_from_context_skips_groups_with_no_submitters():
    """A group with no submitting members is absent from the result."""
    ctx = {
        "user_to_group": {
            "1": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
        }
    }
    user_to_keys: dict = {}
    reps = pick_group_representatives_from_context(ctx, user_to_keys)
    assert reps == {}


def test_pick_reps_from_context_multi_group():
    """Multiple groups → one rep per group."""
    ctx = {
        "user_to_group": {
            "1": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
            "2": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
            "3": {"group_id": 20, "group_name": "B", "member_user_ids": [3, 4]},
            "4": {"group_id": 20, "group_name": "B", "member_user_ids": [3, 4]},
        }
    }
    user_to_keys = {1: ["X-A"], 2: ["X-B"], 3: ["X-C"], 4: ["X-D"]}
    reps = pick_group_representatives_from_context(ctx, user_to_keys)
    assert reps == {10: 1, 20: 3}


# ---------------------------------------------------------------------------
# mirror_group_rows — issue #100 (the actual mirror behavior)
# ---------------------------------------------------------------------------

def _row(key, score="(not graded)", reason="", fb=""):
    """Test helper: build a review row in the shape main() builds."""
    return {
        "submission_file": f"unused_{key}.docx",
        "key": key,
        "recommended_score": score,
        "reason": reason,
        "feedback_file": fb,
        "final_grade": "",
    }


def test_mirror_group_rows_no_context_stamps_empty_column(tmp_path):
    """No group_context → no mirroring; all rows get empty group_mirror_of."""
    rows = [_row("X-1"), _row("X-2")]
    out = mirror_group_rows(rows, None, {}, {}, tmp_path)
    for r in out:
        assert r["group_mirror_of"] == ""


def test_mirror_group_rows_individual_mode_no_mirror(tmp_path):
    """grade_group_students_individually=True → no mirroring even when
    group_context is present."""
    rows = [_row("X-1"), _row("X-2")]
    ctx = {
        "grade_group_students_individually": True,
        "user_to_group": {
            "1": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
            "2": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
        },
    }
    out = mirror_group_rows(rows, ctx, {1: ["X-1"], 2: ["X-2"]}, {}, tmp_path)
    for r in out:
        assert r["group_mirror_of"] == ""


def test_mirror_group_rows_shared_mode_mirrors_score(tmp_path):
    """Shared-grade group assignment: mirrored member's row gets the rep's
    score + reason + feedback_file."""
    rep_fb = tmp_path / "X-REP.md"
    rep_fb.write_text("rep feedback content", encoding="utf-8")
    rows = [
        _row("X-REP"),
        _row("X-MIRROR"),
    ]
    ctx = {
        "grade_group_students_individually": False,
        "user_to_group": {
            "1": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
            "2": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
        },
    }
    user_to_keys = {1: ["X-REP"], 2: ["X-MIRROR"]}
    summary = {"X-REP": {"score": "3.5", "one_line_reason": "good work"}}
    out = mirror_group_rows(rows, ctx, user_to_keys, summary, tmp_path)
    # Find each by key
    rep_row = next(r for r in out if r["key"] == "X-REP")
    mirror_row = next(r for r in out if r["key"] == "X-MIRROR")
    # Rep row is the source — group_mirror_of is empty for it
    assert rep_row["group_mirror_of"] == ""
    # Mirror row inherits the rep's score + reason
    assert mirror_row["recommended_score"] == "3.5"
    assert mirror_row["reason"] == "good work"
    assert mirror_row["group_mirror_of"] == "X-REP"
    # Mirror row's feedback file points to the rep's
    assert "X-REP.md" in mirror_row["feedback_file"]


def test_mirror_group_rows_missing_rep_feedback_shows_missing(tmp_path):
    """If the rep's feedback .md doesn't exist on disk, mirror_group_rows
    marks the feedback as (missing) — doesn't fabricate a path."""
    rows = [_row("X-REP"), _row("X-MIRROR")]
    ctx = {
        "grade_group_students_individually": False,
        "user_to_group": {
            "1": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
            "2": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
        },
    }
    user_to_keys = {1: ["X-REP"], 2: ["X-MIRROR"]}
    summary = {"X-REP": {"score": "3.5", "one_line_reason": "ok"}}
    # Don't write rep_fb — it's missing
    out = mirror_group_rows(rows, ctx, user_to_keys, summary, tmp_path)
    mirror_row = next(r for r in out if r["key"] == "X-MIRROR")
    assert mirror_row["feedback_file"] == "(missing)"
    assert mirror_row["group_mirror_of"] == "X-REP"  # still mirrored


def test_mirror_group_rows_no_summary_for_rep_keeps_original(tmp_path):
    """If the rep wasn't graded yet (no row in _summary.csv), mirroring
    is a no-op — don't overwrite with empty data."""
    rows = [_row("X-REP"), _row("X-MIRROR", score="placeholder")]
    ctx = {
        "grade_group_students_individually": False,
        "user_to_group": {
            "1": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
            "2": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
        },
    }
    user_to_keys = {1: ["X-REP"], 2: ["X-MIRROR"]}
    summary: dict = {}  # rep not yet graded
    out = mirror_group_rows(rows, ctx, user_to_keys, summary, tmp_path)
    mirror_row = next(r for r in out if r["key"] == "X-MIRROR")
    # Original score preserved; group_mirror_of NOT set (no rep data to point at)
    assert mirror_row["recommended_score"] == "placeholder"
    assert mirror_row["group_mirror_of"] == ""


def test_mirror_group_rows_multi_group_handled_independently(tmp_path):
    """Each group's mirroring is isolated — rep of group 10 doesn't affect
    rows in group 20."""
    (tmp_path / "X-REP10.md").write_text("a", encoding="utf-8")
    (tmp_path / "X-REP20.md").write_text("b", encoding="utf-8")
    rows = [
        _row("X-REP10"),
        _row("X-MIRROR10"),
        _row("X-REP20"),
        _row("X-MIRROR20"),
    ]
    ctx = {
        "grade_group_students_individually": False,
        "user_to_group": {
            "1": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
            "2": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
            "3": {"group_id": 20, "group_name": "B", "member_user_ids": [3, 4]},
            "4": {"group_id": 20, "group_name": "B", "member_user_ids": [3, 4]},
        },
    }
    user_to_keys = {1: ["X-REP10"], 2: ["X-MIRROR10"], 3: ["X-REP20"], 4: ["X-MIRROR20"]}
    summary = {
        "X-REP10": {"score": "3.0", "one_line_reason": "g10"},
        "X-REP20": {"score": "4.0", "one_line_reason": "g20"},
    }
    out = mirror_group_rows(rows, ctx, user_to_keys, summary, tmp_path)
    by_key = {r["key"]: r for r in out}
    assert by_key["X-MIRROR10"]["recommended_score"] == "3.0"
    assert by_key["X-MIRROR10"]["group_mirror_of"] == "X-REP10"
    assert by_key["X-MIRROR20"]["recommended_score"] == "4.0"
    assert by_key["X-MIRROR20"]["group_mirror_of"] == "X-REP20"


def test_mirror_group_rows_non_group_member_unaffected(tmp_path):
    """A row whose user_id isn't in any group → group_mirror_of stays empty,
    score preserved."""
    rows = [_row("X-REP"), _row("X-MIRROR"), _row("X-SOLO", score="2.5")]
    ctx = {
        "grade_group_students_individually": False,
        "user_to_group": {
            "1": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
            "2": {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
            # uid 99 (X-SOLO) is NOT in any group
        },
    }
    user_to_keys = {1: ["X-REP"], 2: ["X-MIRROR"], 99: ["X-SOLO"]}
    summary = {"X-REP": {"score": "3.5", "one_line_reason": "x"},
               "X-SOLO": {"score": "2.5", "one_line_reason": "y"}}
    out = mirror_group_rows(rows, ctx, user_to_keys, summary, tmp_path)
    solo_row = next(r for r in out if r["key"] == "X-SOLO")
    assert solo_row["recommended_score"] == "2.5"
    assert solo_row["group_mirror_of"] == ""

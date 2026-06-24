"""Tier 1 unit tests — grader_fetch pure-logic helpers.

Source: lib/tools/grader_fetch.py
  - existing_grades_rows (#96 part 3 — re-grade detection upstream)
  - write_existing_grades_csv (#96 part 3 — keyed FERPA-safe CSV emit)

These tests verify the file-walk + filter + key-derivation parity with the
de-id adapters. They do NOT exercise Canvas API calls (the `subs` argument
is a hand-rolled list of dicts).
"""
import csv
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_fetch import (  # noqa: E402
    existing_grades_rows,
    write_existing_grades_csv,
)
from grader_deidentify_databricks import key_for  # noqa: E402


def _touch(d: Path, name: str) -> Path:
    p = d / name
    p.write_text("", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# existing_grades_rows — issue #96 part 3
# ---------------------------------------------------------------------------

def test_existing_grades_rows_filters_to_graded_only(tmp_path):
    """workflow_state != 'graded' rows are absent from the output."""
    _touch(tmp_path, "KC1_111.docx")
    _touch(tmp_path, "KC1_222.docx")
    _touch(tmp_path, "KC1_333.docx")
    subs = [
        {"user_id": 111, "grade": "3.75", "score": 3.75, "workflow_state": "graded"},
        {"user_id": 222, "grade": None, "score": None, "workflow_state": "pending_review"},
        {"user_id": 333, "grade": "0", "score": 0.0, "workflow_state": "unsubmitted"},
    ]
    rows = existing_grades_rows(tmp_path, subs, "KC1")
    assert len(rows) == 1
    assert rows[0]["existing_grade"] == "3.75"
    assert rows[0]["workflow_state"] == "graded"


def test_existing_grades_rows_key_matches_key_for(tmp_path):
    """The key written matches the deterministic SHA-256 derivation used by
    every de-id adapter — so the agent's view of these keys lines up with
    the keys in their de-identified submissions later in the pipeline."""
    _touch(tmp_path, "KC1_12345.docx")
    subs = [{"user_id": 12345, "grade": "3.5", "score": 3.5, "workflow_state": "graded"}]
    rows = existing_grades_rows(tmp_path, subs, "KC1")
    assert len(rows) == 1
    expected_key = key_for("KC1_12345.docx", "KC1")
    assert rows[0]["key"] == expected_key


def test_existing_grades_rows_handles_none_grade_and_score(tmp_path):
    """A graded submission with a stringified zero / explicit None values
    must not blow up the CSV writer."""
    _touch(tmp_path, "KC1_111.docx")
    subs = [{"user_id": 111, "grade": None, "score": None, "workflow_state": "graded"}]
    rows = existing_grades_rows(tmp_path, subs, "KC1")
    assert len(rows) == 1
    assert rows[0]["existing_grade"] == ""
    assert rows[0]["existing_score"] == ""


def test_existing_grades_rows_skips_files_with_wrong_prefix(tmp_path):
    """Stale files from a prior cohort under a different prefix don't pollute
    the output. The legacy stale-prefix detector in the de-id adapter handles
    them separately; this helper just skips."""
    _touch(tmp_path, "OLD_111.docx")
    _touch(tmp_path, "KC1_222.docx")
    subs = [
        {"user_id": 111, "grade": "3.0", "score": 3.0, "workflow_state": "graded"},
        {"user_id": 222, "grade": "4.0", "score": 4.0, "workflow_state": "graded"},
    ]
    rows = existing_grades_rows(tmp_path, subs, "KC1")
    assert len(rows) == 1
    assert rows[0]["existing_grade"] == "4.0"


def test_existing_grades_rows_skips_files_without_matching_submission(tmp_path):
    """A file on disk whose uid doesn't appear in the subs list (e.g. a
    leftover from a different assignment) is silently skipped — no row, no
    crash."""
    _touch(tmp_path, "KC1_111.docx")
    _touch(tmp_path, "KC1_999.docx")  # no matching sub
    subs = [{"user_id": 111, "grade": "3.5", "score": 3.5, "workflow_state": "graded"}]
    rows = existing_grades_rows(tmp_path, subs, "KC1")
    assert len(rows) == 1


def test_existing_grades_rows_empty_raw_dir_returns_empty(tmp_path):
    """No files in raw_dir → no rows. The caller still writes a header-only
    CSV — that's the fetch-completion signal."""
    subs = [{"user_id": 111, "grade": "3.5", "score": 3.5, "workflow_state": "graded"}]
    rows = existing_grades_rows(tmp_path, subs, "KC1")
    assert rows == []


def test_existing_grades_rows_handles_multi_attachment_suffix(tmp_path):
    """Submissions with multiple attachments produce filenames like
    `KC1_111_b.docx`. Each file is its own key — same student, multiple
    keys, all reporting the same existing grade."""
    _touch(tmp_path, "KC1_111_a.docx")
    _touch(tmp_path, "KC1_111_b.docx")
    subs = [{"user_id": 111, "grade": "3.75", "score": 3.75, "workflow_state": "graded"}]
    rows = existing_grades_rows(tmp_path, subs, "KC1")
    assert len(rows) == 2
    assert {r["existing_grade"] for r in rows} == {"3.75"}
    # Each multi-attachment row has a DISTINCT key (different filenames hash
    # to different keys)
    assert len({r["key"] for r in rows}) == 2


def test_existing_grades_rows_letter_grade_preserved(tmp_path):
    """Letter grades pass through verbatim — the push-side regression check
    knows how to parse them; this layer doesn't need to."""
    _touch(tmp_path, "KC1_111.docx")
    subs = [{"user_id": 111, "grade": "B+", "score": 87.0, "workflow_state": "graded"}]
    rows = existing_grades_rows(tmp_path, subs, "KC1")
    assert rows[0]["existing_grade"] == "B+"
    assert rows[0]["existing_score"] == 87.0


def test_existing_grades_rows_pass_fail_preserved(tmp_path):
    """'complete' / 'incomplete' pass through verbatim too."""
    _touch(tmp_path, "KC1_111.docx")
    _touch(tmp_path, "KC1_222.docx")
    subs = [
        {"user_id": 111, "grade": "complete", "score": 100.0, "workflow_state": "graded"},
        {"user_id": 222, "grade": "incomplete", "score": 0.0, "workflow_state": "graded"},
    ]
    rows = existing_grades_rows(tmp_path, subs, "KC1")
    by_grade = {r["existing_grade"] for r in rows}
    assert by_grade == {"complete", "incomplete"}


# ---------------------------------------------------------------------------
# write_existing_grades_csv — issue #96 part 3
# ---------------------------------------------------------------------------

def test_write_existing_grades_csv_writes_header_when_empty(tmp_path):
    """Empty rows still write a header-only CSV — the file's presence is
    the fetch-completion signal, regardless of whether prior grades exist."""
    out = write_existing_grades_csv(tmp_path, [])
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert content.startswith("key,existing_grade,existing_score,workflow_state")
    # Exactly one line — the header
    assert content.strip().count("\n") == 0


def test_write_existing_grades_csv_writes_rows(tmp_path):
    """Rows round-trip through DictWriter cleanly."""
    rows = [
        {"key": "KC1-A1B2C3", "existing_grade": "3.75", "existing_score": 3.75,
         "workflow_state": "graded"},
        {"key": "KC1-D4E5F6", "existing_grade": "B+", "existing_score": 87.0,
         "workflow_state": "graded"},
    ]
    out = write_existing_grades_csv(tmp_path, rows)
    parsed = list(csv.DictReader(out.open(encoding="utf-8")))
    assert len(parsed) == 2
    assert parsed[0]["key"] == "KC1-A1B2C3"
    assert parsed[1]["existing_grade"] == "B+"


def test_write_existing_grades_csv_overwrites(tmp_path):
    """Re-running fetch on the same challenge dir overwrites the file
    rather than appending — the current state of Canvas is what's
    authoritative; stale rows from a prior fetch would mislead the agent."""
    out_path = tmp_path / "_existing_grades.csv"
    out_path.write_text("stale,header,row\nA,1,2\n", encoding="utf-8")
    rows = [{"key": "KC1-NEW", "existing_grade": "4.0", "existing_score": 4.0,
             "workflow_state": "graded"}]
    write_existing_grades_csv(tmp_path, rows)
    content = out_path.read_text(encoding="utf-8")
    assert "stale" not in content
    assert "KC1-NEW" in content

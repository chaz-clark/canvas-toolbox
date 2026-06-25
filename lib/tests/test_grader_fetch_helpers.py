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
    extract_task_page_url,
    render_assignment_spec,
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


# ---------------------------------------------------------------------------
# extract_task_page_url — issue #102 (task page link detection)
# ---------------------------------------------------------------------------

def test_extract_task_page_url_keyword_match():
    """The DS 250 U4T3 canonical case: link text says 'Open Task Page →'."""
    desc = (
        '<p>Work through this task on the course site. When complete, submit '
        'a screenshot of your code and output. '
        '<a href="https://byui.github.io/ds250-onln-master/u04/show_me.html">'
        'Open Task Page →</a></p>'
    )
    url = extract_task_page_url(desc)
    assert url == "https://byui.github.io/ds250-onln-master/u04/show_me.html"


def test_extract_task_page_url_view_task_text():
    """Alternative link-text patterns: 'View Task', 'Task Page'."""
    desc = '<p>Spec: <a href="https://course.site/t1">View Task</a></p>'
    assert extract_task_page_url(desc) == "https://course.site/t1"


def test_extract_task_page_url_no_keyword_falls_back_to_external_link():
    """If no keyword matches but there's an outbound (non-Canvas) link,
    use it as a fallback candidate — operator confirms via the produced
    assignment_spec.md."""
    desc = '<p>See <a href="https://example.edu/syllabus.html">syllabus</a>.</p>'
    assert extract_task_page_url(desc) == "https://example.edu/syllabus.html"


def test_extract_task_page_url_skips_canvas_internal_links():
    """Canvas-internal links (instructure.com, /courses/...) don't count
    as task pages — they're the assignment's own context, not the spec."""
    desc = (
        '<p>See <a href="https://byui.instructure.com/courses/1/files/2">'
        'syllabus</a>.</p>'
    )
    assert extract_task_page_url(desc) is None


def test_extract_task_page_url_skips_anchor_and_mailto():
    """Anchor links and mailto: don't count."""
    desc = (
        '<p><a href="#top">back</a> <a href="mailto:prof@x.edu">email me</a></p>'
    )
    assert extract_task_page_url(desc) is None


def test_extract_task_page_url_empty_and_none():
    """Empty / None description → None, no crash."""
    assert extract_task_page_url("") is None
    assert extract_task_page_url(None) is None


def test_extract_task_page_url_keyword_beats_canvas_internal():
    """Keyword match wins even if there's a Canvas-internal link first."""
    desc = (
        '<p><a href="https://byui.instructure.com/courses/1">course home</a> · '
        '<a href="https://course.site/spec">Task Page</a></p>'
    )
    assert extract_task_page_url(desc) == "https://course.site/spec"


def test_extract_task_page_url_first_keyword_wins():
    """When multiple keyword-matching links exist, the FIRST one in the
    HTML order is used (operator can edit assignment_spec.md if wrong)."""
    desc = (
        '<a href="https://a.com">View Task</a> '
        '<a href="https://b.com">Open Task</a>'
    )
    assert extract_task_page_url(desc) == "https://a.com"


# ---------------------------------------------------------------------------
# render_assignment_spec — issue #102 (the spec file content)
# ---------------------------------------------------------------------------

def test_render_assignment_spec_includes_source_of_truth_preamble():
    """The header preamble naming this as source of truth must appear in
    every rendered spec — that's the anchor for the agent's grading rule."""
    out = render_assignment_spec("<p>desc</p>", None, None)
    assert "Source of truth" in out
    assert "REQUIRED" in out
    assert "OPTIONAL" in out


def test_render_assignment_spec_with_no_link_says_so():
    """When no task page URL is detected, the spec explicitly notes that
    the Canvas description IS the complete spec — no silent default."""
    out = render_assignment_spec("<p>The full spec</p>", None, None)
    assert "No Linked Task Page" in out


def test_render_assignment_spec_with_link_and_text():
    """When task page URL + fetched text are both present, both render
    + the URL is named so the operator can verify the source."""
    out = render_assignment_spec(
        "<p>pointer</p>",
        "https://course.site/spec",
        "## Task\n\nDo X. Submit Y.",
    )
    assert "https://course.site/spec" in out
    assert "Do X. Submit Y." in out


def test_render_assignment_spec_with_link_but_failed_fetch():
    """URL detected but fetch failed → URL named + a warning that the
    operator should review the link manually."""
    out = render_assignment_spec("<p>pointer</p>", "https://course.site/spec", None)
    assert "https://course.site/spec" in out
    assert "manually" in out


def test_render_assignment_spec_with_empty_description():
    """Empty Canvas description still renders — but flagged as such."""
    out = render_assignment_spec("", None, None)
    assert "empty Canvas description" in out

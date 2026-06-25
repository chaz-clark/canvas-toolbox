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
    is_group_assignment,
    grades_individually,
    build_group_map,
    pick_group_representatives,
    render_unique_group_memos_md,
    group_context_for_fetch_log,
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


# ---------------------------------------------------------------------------
# is_group_assignment / grades_individually — issue #100 (group detection)
# ---------------------------------------------------------------------------

def test_is_group_assignment_true_when_gcat_set():
    """group_category_id present (non-zero) → group assignment."""
    assert is_group_assignment({"group_category_id": 42}) is True


def test_is_group_assignment_false_when_gcat_missing_or_zero():
    """No group_category_id (or zero) → not a group assignment."""
    assert is_group_assignment({}) is False
    assert is_group_assignment({"group_category_id": None}) is False
    assert is_group_assignment({"group_category_id": 0}) is False


def test_grades_individually_default_is_false():
    """Canvas default for grade_group_students_individually is false
    (shared grade for the whole group)."""
    assert grades_individually({}) is False
    assert grades_individually({"grade_group_students_individually": False}) is False


def test_grades_individually_true_when_set():
    """Explicit true → each member grades independently."""
    assert grades_individually({"grade_group_students_individually": True}) is True


# ---------------------------------------------------------------------------
# build_group_map — issue #100 (user_id → group context)
# ---------------------------------------------------------------------------

def test_build_group_map_basic():
    """Two groups, three members each → map has 6 user_id entries."""
    groups = [
        {"id": 10, "name": "Group A"},
        {"id": 20, "name": "Group B"},
    ]
    members_by_group = {
        10: [{"id": 1}, {"id": 2}, {"id": 3}],
        20: [{"id": 4}, {"id": 5}, {"id": 6}],
    }
    m = build_group_map(groups, members_by_group)
    assert len(m) == 6
    assert m[1]["group_id"] == 10
    assert m[1]["group_name"] == "Group A"
    assert m[1]["member_user_ids"] == [1, 2, 3]
    assert m[4]["group_id"] == 20
    assert m[4]["member_user_ids"] == [4, 5, 6]


def test_build_group_map_default_name_when_missing():
    """Group without a name → falls back to 'Group <id>'."""
    groups = [{"id": 99}]
    members_by_group = {99: [{"id": 1}]}
    m = build_group_map(groups, members_by_group)
    assert m[1]["group_name"] == "Group 99"


def test_build_group_map_empty_group_skipped():
    """A group with no members produces no map entries (no error)."""
    groups = [{"id": 10, "name": "Empty"}]
    members_by_group = {10: []}
    m = build_group_map(groups, members_by_group)
    assert m == {}


def test_build_group_map_handles_non_integer_ids():
    """Garbage id values are silently skipped (Canvas-string-id mode)."""
    groups = [{"id": "abc", "name": "Bad"}, {"id": 10, "name": "Good"}]
    members_by_group = {10: [{"id": "not-an-int"}, {"id": 5}]}
    m = build_group_map(groups, members_by_group)
    assert 5 in m
    assert len(m) == 1


# ---------------------------------------------------------------------------
# pick_group_representatives — issue #100
# ---------------------------------------------------------------------------

def test_pick_group_representatives_smallest_submitter_wins():
    """Rep is the smallest user_id among submitters in the group."""
    group_map = {
        1: {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2, 3]},
        2: {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2, 3]},
        3: {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2, 3]},
    }
    submitters = {2, 3}  # uid 1 didn't submit
    reps = pick_group_representatives(group_map, submitters)
    assert reps == {10: 2}


def test_pick_group_representatives_no_submitter_skipped():
    """Group with no submitting members is absent from the result."""
    group_map = {
        1: {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
    }
    submitters: set = set()
    reps = pick_group_representatives(group_map, submitters)
    assert reps == {}


def test_pick_group_representatives_multi_group():
    """Multiple groups → one rep per group."""
    group_map = {
        1: {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
        2: {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
        3: {"group_id": 20, "group_name": "B", "member_user_ids": [3, 4]},
        4: {"group_id": 20, "group_name": "B", "member_user_ids": [3, 4]},
    }
    submitters = {1, 2, 3, 4}
    reps = pick_group_representatives(group_map, submitters)
    assert reps == {10: 1, 20: 3}


def test_pick_group_representatives_deterministic():
    """Re-running with the same inputs returns the same reps — critical for
    workflow repeatability."""
    group_map = {
        1: {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2, 3]},
        2: {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2, 3]},
        3: {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2, 3]},
    }
    submitters = {3, 1, 2}  # order varies
    reps1 = pick_group_representatives(group_map, submitters)
    reps2 = pick_group_representatives(group_map, submitters)
    assert reps1 == reps2 == {10: 1}


# ---------------------------------------------------------------------------
# render_unique_group_memos_md — issue #100
# ---------------------------------------------------------------------------

def test_render_unique_group_memos_md_marks_representative():
    """The rep submitter is explicitly named as 'grade this one'."""
    group_map = {
        1: {"group_id": 10, "group_name": "Survey Team Alpha", "member_user_ids": [1, 2, 3]},
        2: {"group_id": 10, "group_name": "Survey Team Alpha", "member_user_ids": [1, 2, 3]},
        3: {"group_id": 10, "group_name": "Survey Team Alpha", "member_user_ids": [1, 2, 3]},
    }
    submitters = {1, 2, 3}
    reps = {10: 1}
    out = render_unique_group_memos_md(group_map, submitters, reps, False, "ce162lab")
    assert "Representative submitter (grade this one):" in out
    assert "user_id=1" in out
    assert "Survey Team Alpha" in out


def test_render_unique_group_memos_md_lists_mirrored_members():
    """Non-rep submitters in the same group are listed as mirrored."""
    group_map = {
        1: {"group_id": 10, "group_name": "Alpha", "member_user_ids": [1, 2, 3]},
        2: {"group_id": 10, "group_name": "Alpha", "member_user_ids": [1, 2, 3]},
        3: {"group_id": 10, "group_name": "Alpha", "member_user_ids": [1, 2, 3]},
    }
    submitters = {1, 2, 3}
    reps = {10: 1}
    out = render_unique_group_memos_md(group_map, submitters, reps, False, "lab")
    assert "Mirrored submitters" in out
    assert "user_id=2" in out
    assert "user_id=3" in out


def test_render_unique_group_memos_md_lists_non_submitters():
    """Members who didn't submit get their own line — important for the
    shared-grade case where they still receive the grade via Canvas."""
    group_map = {
        1: {"group_id": 10, "group_name": "Alpha", "member_user_ids": [1, 2, 3]},
        2: {"group_id": 10, "group_name": "Alpha", "member_user_ids": [1, 2, 3]},
        3: {"group_id": 10, "group_name": "Alpha", "member_user_ids": [1, 2, 3]},
    }
    submitters = {1}  # uid 2 + 3 didn't submit
    reps = {10: 1}
    out = render_unique_group_memos_md(group_map, submitters, reps, False, "lab")
    assert "Non-submitting members" in out


def test_render_unique_group_memos_md_lists_groups_without_submissions():
    """Groups with zero submitters from any member appear in a separate
    'Groups with no submissions' section."""
    group_map = {
        1: {"group_id": 10, "group_name": "Alpha", "member_user_ids": [1]},
        2: {"group_id": 20, "group_name": "Beta", "member_user_ids": [2]},
    }
    submitters = {1}  # uid 2 (Beta's only member) didn't submit
    reps = {10: 1}
    out = render_unique_group_memos_md(group_map, submitters, reps, False, "lab")
    assert "Groups with no submissions" in out
    assert "Beta" in out


def test_render_unique_group_memos_md_marks_individual_mode():
    """grade_individually=True → output names the mode explicitly so the
    operator/agent knows NOT to collapse rows at push time."""
    group_map = {
        1: {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
        2: {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]},
    }
    submitters = {1, 2}
    reps = {10: 1}
    out_shared = render_unique_group_memos_md(group_map, submitters, reps, False, "lab")
    out_individ = render_unique_group_memos_md(group_map, submitters, reps, True, "lab")
    assert "individual grades per member" in out_individ
    assert "shared grade per group" in out_shared


# ---------------------------------------------------------------------------
# group_context_for_fetch_log — issue #100
# ---------------------------------------------------------------------------

def test_group_context_for_fetch_log_none_when_no_groups():
    """Empty group_map → None (no 'group_context' key gets embedded)."""
    assert group_context_for_fetch_log({}, 42, False) is None


def test_group_context_for_fetch_log_basic_shape():
    """Returns the expected shape — gcat_id, mode flag, and the
    user_id-keyed user_to_group map (JSON-serializable string keys)."""
    group_map = {
        1: {"group_id": 10, "group_name": "Alpha", "member_user_ids": [1, 2]},
        2: {"group_id": 10, "group_name": "Alpha", "member_user_ids": [1, 2]},
    }
    out = group_context_for_fetch_log(group_map, 42, False)
    assert out is not None
    assert out["group_category_id"] == 42
    assert out["grade_group_students_individually"] is False
    assert set(out["user_to_group"].keys()) == {"1", "2"}
    assert out["user_to_group"]["1"]["group_id"] == 10
    assert out["user_to_group"]["1"]["group_name"] == "Alpha"
    assert out["user_to_group"]["1"]["member_user_ids"] == [1, 2]


def test_group_context_for_fetch_log_handles_string_gcat():
    """Canvas-string-id mode might pass '42' as a string; coerce safely."""
    group_map = {1: {"group_id": 10, "group_name": "A", "member_user_ids": [1]}}
    out = group_context_for_fetch_log(group_map, "42", False)
    assert out["group_category_id"] == 42


def test_group_context_for_fetch_log_serializable():
    """The output must round-trip through json.dumps (since we embed it
    into .fetch_log.json)."""
    import json as _json
    group_map = {1: {"group_id": 10, "group_name": "A", "member_user_ids": [1, 2]}}
    out = group_context_for_fetch_log(group_map, 42, True)
    s = _json.dumps(out)
    assert "group_category_id" in s
    assert "grade_group_students_individually" in s

"""Tier 1 unit tests — grader_fetch_nq_responses pure-logic helpers.

Source: lib/tools/grader_fetch_nq_responses.py (#87 — pull per-student
responses from a New Quiz via the Reporting API).

Tests cover the parse layer (no Canvas API calls):
  - parse_filename_date: extract dates from screenshot filenames
  - parse_canvas_ts: parse the student_analysis CSV timestamp format
  - parse_student_analysis_csv: full CSV → uid-keyed dict
"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_fetch_nq_responses import (  # noqa: E402
    parse_filename_date,
    parse_canvas_ts,
    parse_student_analysis_csv,
)


# ---------------------------------------------------------------------------
# parse_filename_date — pattern coverage for the 4 known screenshot styles
# ---------------------------------------------------------------------------

def test_filename_date_mac_default():
    """macOS screenshot: 'Screenshot 2026-06-05 at 11.36.00 AM.png'"""
    assert parse_filename_date("Screenshot 2026-06-05 at 11.36.00 AM.png") == date(2026, 6, 5)


def test_filename_date_windows_default():
    """Windows screenshot: 'Screenshot 2026-06-06 164807.png'"""
    assert parse_filename_date("Screenshot 2026-06-06 164807.png") == date(2026, 6, 6)


def test_filename_date_snipping_tool():
    """Snipping Tool: 'Screenshot_select-area_20260606233450.png'"""
    assert parse_filename_date("Screenshot_select-area_20260606233450.png") == date(2026, 6, 6)


def test_filename_date_generic_iso_at_word_boundary():
    """\\bYYYY-MM-DD\\b matches when surrounded by non-word chars. `\\b`
    does NOT match between underscores (underscore is a word char), so
    `standup_2026-06-04_final.png` would NOT match — which is fine: those
    user-renamed files fall back to TRUST_GRADE via submitted_at in the
    consuming tool."""
    assert parse_filename_date("submission 2026-06-04.png") == date(2026, 6, 4)
    assert parse_filename_date("2026-06-04 standup.png") == date(2026, 6, 4)


def test_filename_date_none_when_no_pattern():
    """User-renamed without date (the ~30% TRUST_GRADE fallback case)."""
    assert parse_filename_date("Check_weather_DAG_3.png") is None


def test_filename_date_none_for_empty():
    assert parse_filename_date("") is None
    assert parse_filename_date(None) is None  # type: ignore[arg-type]


def test_filename_date_invalid_date_skipped():
    """Pattern matches but YYYY-13-32 isn't a real date → falls through."""
    assert parse_filename_date("file_2026-13-45_x.png") is None


# ---------------------------------------------------------------------------
# parse_canvas_ts — student_analysis CSV's '... UTC' format + ISO variants
# ---------------------------------------------------------------------------

def test_canvas_ts_student_analysis_format():
    """The format Canvas's student_analysis CSV uses."""
    got = parse_canvas_ts("2026-06-05 15:45:21 UTC")
    assert got == datetime(2026, 6, 5, 15, 45, 21, tzinfo=timezone.utc)


def test_canvas_ts_iso_8601():
    got = parse_canvas_ts("2026-06-05T15:45:21Z")
    assert got == datetime(2026, 6, 5, 15, 45, 21, tzinfo=timezone.utc)


def test_canvas_ts_iso_with_micros():
    got = parse_canvas_ts("2026-06-05T15:45:21.123456Z")
    assert got is not None
    assert got.year == 2026


def test_canvas_ts_empty_returns_none():
    assert parse_canvas_ts("") is None
    assert parse_canvas_ts(None) is None  # type: ignore[arg-type]


def test_canvas_ts_garbage_returns_none():
    assert parse_canvas_ts("not-a-timestamp") is None


# ---------------------------------------------------------------------------
# parse_student_analysis_csv — uid-keyed parse with file-upload + answer cols
# ---------------------------------------------------------------------------

# Synthetic CSV modeled on the real Canvas student_analysis shape.
# One file-upload question (Q1) + one numeric question (Q2).
_SYNTHETIC_CSV = (
    "Name,ID,Submitted,Attempt,Item ID,Item Type,Q1: upload your screenshot,Earned Points,Status,"
    "Item ID,Item Type,Q2: hours worked,Earned Points,Status\n"
    'Doe Jane,11111,2026-06-05 15:45:21 UTC,1,q-aaa,file-upload,'
    '"Screenshot 2026-06-05 at 11.36.00 AM.png",2.0,complete,'
    'q-bbb,numeric,8,1.0,complete\n'
    'Smith John,22222,2026-06-06 09:00:00 UTC,1,q-aaa,file-upload,'
    'Check_weather_DAG_3.png,2.0,complete,'
    'q-bbb,numeric,10,1.0,complete\n'
)


def test_parse_returns_uid_keyed_dict():
    result = parse_student_analysis_csv(_SYNTHETIC_CSV)
    assert set(result.keys()) == {11111, 22222}


def test_parse_extracts_submitted_at():
    result = parse_student_analysis_csv(_SYNTHETIC_CSV)
    assert result[11111]["submitted_at"] == "2026-06-05T15:45:21+00:00"


def test_parse_extracts_filenames_for_file_upload_question():
    result = parse_student_analysis_csv(_SYNTHETIC_CSV)
    assert result[11111]["filenames"] == ["Screenshot 2026-06-05 at 11.36.00 AM.png"]
    assert result[22222]["filenames"] == ["Check_weather_DAG_3.png"]


def test_parse_extracts_filename_dates_when_requested():
    result = parse_student_analysis_csv(_SYNTHETIC_CSV, extract_filename_dates=True)
    # Jane's screenshot has a parseable date; John's user-renamed file does not.
    assert result[11111]["filename_dates"] == ["2026-06-05"]
    assert result[22222]["filename_dates"] == []


def test_parse_filename_dates_absent_by_default():
    """Default mode omits the filename_dates field (FERPA-minimal payload)."""
    result = parse_student_analysis_csv(_SYNTHETIC_CSV)
    assert "filename_dates" not in result[11111]


def test_parse_records_per_question_answer_and_score():
    result = parse_student_analysis_csv(_SYNTHETIC_CSV)
    jane = result[11111]
    assert "q-aaa" in jane["answers"]
    assert jane["answers"]["q-aaa"]["type"] == "file-upload"
    assert jane["answers"]["q-aaa"]["score"] == 2.0
    assert jane["answers"]["q-bbb"]["value"] == "8"
    assert jane["answers"]["q-bbb"]["score"] == 1.0


def test_parse_includes_name_field():
    """The parse layer keeps name; the CLI is responsible for stripping
    it when --include-names is not passed."""
    result = parse_student_analysis_csv(_SYNTHETIC_CSV)
    assert result[11111]["name"] == "Doe Jane"
    assert result[22222]["name"] == "Smith John"


def test_parse_empty_csv_returns_empty_dict():
    assert parse_student_analysis_csv("") == {}


def test_parse_raises_when_id_column_missing():
    bad = "Name,Submitted\nDoe Jane,2026-06-05 15:45:21 UTC\n"
    try:
        parse_student_analysis_csv(bad)
    except ValueError as e:
        assert "ID" in str(e)
    else:
        raise AssertionError("Expected ValueError on missing ID column")


def test_parse_skips_row_with_non_integer_id():
    csv_text = (
        "Name,ID,Submitted,Attempt,Item ID,Item Type,Q1,Earned Points,Status\n"
        "Doe Jane,11111,2026-06-05 15:45:21 UTC,1,q-aaa,numeric,5,1.0,complete\n"
        "Test Student,,2026-06-05 15:45:21 UTC,1,q-aaa,numeric,5,1.0,complete\n"
    )
    result = parse_student_analysis_csv(csv_text)
    assert set(result.keys()) == {11111}  # the empty-ID row dropped silently

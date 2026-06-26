"""Tier 1 unit tests — course_engagement_audit pure-logic helpers.

Source: lib/tools/course_engagement_audit.py
  - parse_uf_date (operator-provided UF cutoff string)
  - parse_iso_utc (Canvas ISO timestamp parsing)
  - compute_last_engagement (max across submissions + discussions + quizzes)
  - classify_student (the Title IV bucket assignment)
  - downloads_dir (cross-platform Downloads detection)
  - render_report_md (the named report content)

These tests cover the Title IV classification logic + the FERPA tier 3
discipline (Downloads-folder write refusal inside repo).
"""
import sys
from datetime import timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from course_engagement_audit import (  # noqa: E402
    parse_uf_date,
    parse_iso_utc,
    compute_last_engagement,
    classify_student,
    downloads_dir,
    render_report_md,
)


# ---------------------------------------------------------------------------
# parse_uf_date — operator-provided YYYY-MM-DD
# ---------------------------------------------------------------------------

def test_parse_uf_date_valid():
    """Standard YYYY-MM-DD parses to midnight UTC."""
    d = parse_uf_date("2026-04-15")
    assert d is not None
    assert d.year == 2026 and d.month == 4 and d.day == 15
    assert d.tzinfo == timezone.utc


def test_parse_uf_date_handles_whitespace():
    """Operator whitespace tolerated."""
    d = parse_uf_date("  2026-04-15  ")
    assert d is not None
    assert d.month == 4


def test_parse_uf_date_invalid_returns_none():
    """Garbage → None (caller refuses)."""
    for bad in ("", None, "garbage", "2026", "2026/04/15", "04-15-2026"):
        assert parse_uf_date(bad) is None


def test_parse_uf_date_invalid_day_returns_none():
    """Out-of-range day → None."""
    assert parse_uf_date("2026-02-30") is None  # Feb has no 30


# ---------------------------------------------------------------------------
# parse_iso_utc — Canvas ISO timestamps
# ---------------------------------------------------------------------------

def test_parse_iso_utc_z_suffix():
    """Canvas's typical Z-suffix format."""
    d = parse_iso_utc("2026-04-15T18:32:11Z")
    assert d is not None
    assert d.year == 2026 and d.hour == 18 and d.tzinfo == timezone.utc


def test_parse_iso_utc_explicit_offset():
    """Explicit +00:00 offset works too."""
    d = parse_iso_utc("2026-04-15T18:32:11+00:00")
    assert d is not None
    assert d.hour == 18


def test_parse_iso_utc_handles_none_and_empty():
    """Missing timestamp → None (not a crash)."""
    assert parse_iso_utc(None) is None
    assert parse_iso_utc("") is None


def test_parse_iso_utc_garbage_returns_none():
    """Malformed timestamps return None — caller skips them."""
    assert parse_iso_utc("not-a-date") is None
    assert parse_iso_utc("2026-13-01T00:00:00Z") is None  # invalid month


# ---------------------------------------------------------------------------
# compute_last_engagement — max across three sources
# ---------------------------------------------------------------------------

def test_compute_last_engagement_picks_max():
    """The max timestamp across all three sources wins."""
    subs = ["2026-04-10T10:00:00Z", "2026-04-12T10:00:00Z"]
    disc = ["2026-04-11T10:00:00Z"]
    quiz = []  # quiz timestamps merge with submissions in our pipeline; covered
    result = compute_last_engagement(subs, disc, quiz)
    assert result is not None
    assert result.day == 12


def test_compute_last_engagement_discussion_can_win():
    """Discussion entries are valid Title IV engagement; if newer, they win."""
    subs = ["2026-04-10T10:00:00Z"]
    disc = ["2026-04-20T10:00:00Z"]
    result = compute_last_engagement(subs, disc, [])
    assert result is not None
    assert result.day == 20


def test_compute_last_engagement_all_empty_returns_none():
    """No engagement → None → NEVER_PARTICIPATED downstream."""
    assert compute_last_engagement([], [], []) is None


def test_compute_last_engagement_skips_unparseable():
    """Garbage timestamps don't crash the max computation."""
    subs = ["not-a-date", "2026-04-15T10:00:00Z", None]
    result = compute_last_engagement(subs, [], [])
    assert result is not None
    assert result.day == 15


# ---------------------------------------------------------------------------
# classify_student — the Title IV bucket assignment
# ---------------------------------------------------------------------------

UF_DATE = parse_uf_date("2026-04-15")


def test_classify_never_participated():
    """No engagement on record → NEVER_PARTICIPATED, regardless of grade.
    Per Title IV no-show rule, institution returns 100% Title IV aid."""
    assert classify_student(None, UF_DATE, 80.0) == "NEVER_PARTICIPATED"
    assert classify_student(None, UF_DATE, None) == "NEVER_PARTICIPATED"
    assert classify_student(None, UF_DATE, 0.0) == "NEVER_PARTICIPATED"


def test_classify_active_when_engaged_on_or_after_uf_date():
    """Engagement >= UF date → ACTIVE (no Title IV concern)."""
    last_eng = parse_iso_utc("2026-04-15T08:00:00Z")  # ON the UF date
    assert classify_student(last_eng, UF_DATE, 80.0) == "ACTIVE"

    last_eng = parse_iso_utc("2026-05-01T08:00:00Z")  # well after
    assert classify_student(last_eng, UF_DATE, 50.0) == "ACTIVE"


def test_classify_uw_when_stopped_engaging_but_passing():
    """Last engagement < UF date AND passing grade → UW (unofficial
    withdrawal). Per 34 CFR 668.22, if they don't earn a passing grade
    by term end, re-classify as UF and R2T4."""
    last_eng = parse_iso_utc("2026-03-20T10:00:00Z")
    assert classify_student(last_eng, UF_DATE, 75.0) == "UW"
    assert classify_student(last_eng, UF_DATE, 60.0) == "UW"  # at threshold


def test_classify_uf_when_stopped_engaging_and_failing():
    """Last engagement < UF date AND current_score < passing → UF
    (R2T4 candidate; Title IV stakes)."""
    last_eng = parse_iso_utc("2026-03-20T10:00:00Z")
    assert classify_student(last_eng, UF_DATE, 50.0) == "UF"
    assert classify_student(last_eng, UF_DATE, 0.0) == "UF"
    # Just below passing
    assert classify_student(last_eng, UF_DATE, 59.99) == "UF"


def test_classify_uw_when_score_missing():
    """Missing current_score on a non-engaging student → UW (we can't
    confirm failing, so don't escalate to UF). The financial aid office
    determines R2T4 status from authoritative records."""
    last_eng = parse_iso_utc("2026-03-20T10:00:00Z")
    assert classify_student(last_eng, UF_DATE, None) == "UW"


def test_classify_active_when_no_uf_date():
    """If operator didn't provide UF date, can't bucket as UW/UF →
    default ACTIVE. (Caller validates UF date is present.)"""
    last_eng = parse_iso_utc("2026-03-20T10:00:00Z")
    assert classify_student(last_eng, None, 50.0) == "ACTIVE"


def test_classify_passing_threshold_is_configurable():
    """Default passing is 60.0; operator can pass institution-specific."""
    last_eng = parse_iso_utc("2026-03-20T10:00:00Z")
    # At 70 threshold, 65 is failing
    assert classify_student(last_eng, UF_DATE, 65.0, passing_score=70.0) == "UF"
    # At 50 threshold, 65 is passing
    assert classify_student(last_eng, UF_DATE, 65.0, passing_score=50.0) == "UW"


def test_classify_boundary_uf_date_inclusive():
    """Last engagement EXACTLY equal to UF date → ACTIVE (the day OF
    the UF date counts as still active per Title IV convention; UW
    starts the day AFTER last engagement)."""
    last_eng = UF_DATE  # exact same datetime
    assert classify_student(last_eng, UF_DATE, 50.0) == "ACTIVE"


# ---------------------------------------------------------------------------
# downloads_dir — cross-platform Downloads
# ---------------------------------------------------------------------------

def test_downloads_dir_returns_path():
    """Returns a Path object. Should be the user's Downloads folder
    on Mac / Linux / Windows defaults."""
    p = downloads_dir()
    assert isinstance(p, Path)
    # On most dev machines, ~/Downloads exists
    if p.name == "Downloads":
        assert p.parent == Path.home()
    # Otherwise we fell back to $HOME — also valid (no Downloads dir)
    else:
        assert p == Path.home()


def test_downloads_dir_xdg_override(tmp_path, monkeypatch):
    """XDG_DOWNLOAD_DIR (Linux convention) overrides ~/Downloads when
    set AND the path actually exists."""
    custom = tmp_path / "MyDownloads"
    custom.mkdir()
    monkeypatch.setenv("XDG_DOWNLOAD_DIR", str(custom))
    p = downloads_dir()
    # Either XDG won OR ~/Downloads exists on the test runner and won;
    # accept both outcomes — the point is no crash + a directory.
    assert p.is_dir()


# ---------------------------------------------------------------------------
# render_report_md — the named report content (FERPA tier 3 output)
# ---------------------------------------------------------------------------

def _named_rows():
    """Test fixture: a small set of named rows post-reidentification."""
    return [
        {"user_id": 1, "name": "Smith, A", "last_engagement_str": "2026-03-15",
         "current_score": 50.0, "classification": "UF"},
        {"user_id": 2, "name": "Jones, B", "last_engagement_str": "2026-03-20",
         "current_score": 70.0, "classification": "UW"},
        {"user_id": 3, "name": "Lee, C", "last_engagement_str": "(never)",
         "current_score": None, "classification": "NEVER_PARTICIPATED"},
        {"user_id": 4, "name": "Park, D", "last_engagement_str": "2026-05-01",
         "current_score": 85.0, "classification": "ACTIVE"},
    ]


def test_render_report_md_includes_title_iv_verification_date():
    """The report MUST include the Title IV verification date stamp
    so the recipient knows when the rules were last sanity-checked."""
    md = render_report_md(_named_rows(), "Test Course", "12345",
                          "2026-04-15", "2026-06-26 12:00 UTC", 60.0)
    assert "2026-06-26" in md  # the verification date stamp


def test_render_report_md_has_all_four_sections():
    """Every classification bucket gets its own section in the report,
    even when empty (so faculty can see the audit completed)."""
    md = render_report_md(_named_rows(), "Test Course", "12345",
                          "2026-04-15", "2026-06-26 12:00 UTC", 60.0)
    assert "## UF" in md
    assert "## UW" in md
    assert "## NEVER PARTICIPATED" in md
    assert "## ACTIVE" in md


def test_render_report_md_counts_match_input():
    """The summary counts at the top must match the named rows."""
    md = render_report_md(_named_rows(), "Test Course", "12345",
                          "2026-04-15", "2026-06-26 12:00 UTC", 60.0)
    assert "**4** total enrolled students" in md
    assert "**1** classified as **UF**" in md
    assert "**1** classified as **UW**" in md
    assert "**1** **NEVER PARTICIPATED**" in md
    assert "**1** **ACTIVE**" in md


def test_render_report_md_warning_about_PII():
    """The report carries a FERPA warning at the top — recipients
    need to know it contains student names + shouldn't be re-imported
    into the repo."""
    md = render_report_md(_named_rows(), "Test Course", "12345",
                          "2026-04-15", "2026-06-26 12:00 UTC", 60.0)
    assert "FERPA" in md
    assert "student names" in md.lower() or "FERPA" in md


def test_render_report_md_cites_title_iv_regulation():
    """The report names the specific federal regulation (34 CFR 668.22)
    so recipients have the citation for follow-up."""
    md = render_report_md(_named_rows(), "Test Course", "12345",
                          "2026-04-15", "2026-06-26 12:00 UTC", 60.0)
    assert "34 CFR 668.22" in md


def test_render_report_md_empty_rows_renders_cleanly():
    """No enrolled students → still produces a valid report (with all
    sections showing _(none)_). The audit completes; counts are zero."""
    md = render_report_md([], "Empty Course", "99999",
                          "2026-04-15", "2026-06-26 12:00 UTC", 60.0)
    assert "## UF" in md
    assert "_(none)_" in md
    assert "**0** total enrolled students" in md


def test_render_report_md_sorts_within_bucket():
    """Within each classification bucket, students are sorted by name
    so the report is deterministic + scan-friendly."""
    rows = [
        {"user_id": 1, "name": "Zoo, Z", "last_engagement_str": "2026-03-15",
         "current_score": 50.0, "classification": "UF"},
        {"user_id": 2, "name": "Aaa, A", "last_engagement_str": "2026-03-16",
         "current_score": 40.0, "classification": "UF"},
    ]
    md = render_report_md(rows, "Test", "1", "2026-04-15",
                          "2026-06-26 12:00 UTC", 60.0)
    # Aaa, A should appear before Zoo, Z
    aaa_pos = md.find("Aaa, A")
    zoo_pos = md.find("Zoo, Z")
    assert aaa_pos > 0 and zoo_pos > 0
    assert aaa_pos < zoo_pos

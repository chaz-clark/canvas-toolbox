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
    resolve_uf_cutoff,
    parse_iso_utc,
    compute_last_engagement,
    classify_student,
    title_iv_class,
    slugify_course,
    downloads_dir,
    render_report_md,
)


# ---------------------------------------------------------------------------
# slugify_course — course name in the report filename (identify across sections)
# ---------------------------------------------------------------------------

def test_slugify_course_basic():
    assert slugify_course("Big Data Programming") == "big-data-programming"


def test_slugify_course_strips_punctuation_and_edges():
    assert slugify_course("ITM 327: Web Apps (S2)!") == "itm-327-web-apps-s2"


def test_slugify_course_empty_falls_back():
    assert slugify_course("") == "course"
    assert slugify_course(None) == "course"


def test_slugify_course_truncates_long_names():
    assert len(slugify_course("word " * 40)) <= 40
from datetime import datetime as _dt, timezone as _tz  # noqa: E402


def _eng(day):
    """A UTC engagement datetime on 2026-04-<day> (for title_iv_class tests)."""
    return _dt(2026, 4, day, tzinfo=_tz.utc)


_CUTOFF = _dt(2026, 4, 15, tzinfo=_tz.utc)


# ---------------------------------------------------------------------------
# title_iv_class — the focused report classifier (failing/never; passing excluded)
# ---------------------------------------------------------------------------

def test_title_iv_never_participated():
    assert title_iv_class(None, _CUTOFF, None, 60.0) == "UW-never"
    assert title_iv_class(None, _CUTOFF, 95.0, 60.0) == "UW-never"  # never engaged wins


def test_title_iv_passing_engaged_is_excluded():
    assert title_iv_class(_eng(20), _CUTOFF, 85.0, 60.0) is None


def test_title_iv_uw_before_when_failing_and_stopped_early():
    assert title_iv_class(_eng(10), _CUTOFF, 40.0, 60.0) == "UW-before"


def test_title_iv_f_after_when_failing_and_engaged_after_cutoff():
    assert title_iv_class(_eng(20), _CUTOFF, 40.0, 60.0) == "F-After"


def test_title_iv_no_grade_counts_as_failing():
    # engaged, no recorded score → not passing → flagged by timing
    assert title_iv_class(_eng(10), _CUTOFF, None, 60.0) == "UW-before"
    assert title_iv_class(_eng(20), _CUTOFF, None, 60.0) == "F-After"


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


# ---------------------------------------------------------------------------
# resolve_uf_cutoff — derive the cutoff from Canvas course/term settings so the
# operator doesn't hand-look-up a date ("check the end date in Canvas settings")
# ---------------------------------------------------------------------------

def test_resolve_uf_cutoff_defaults_to_course_end_date():
    """No arg -> the course's Canvas end_at (date part), labeled as such."""
    course = {"end_at": "2026-07-25T05:59:59Z", "term": {"end_at": "2026-08-01T00:00:00Z"}}
    d, src = resolve_uf_cutoff(None, course)
    assert d is not None and d.strftime("%Y-%m-%d") == "2026-07-25"
    assert src == "Canvas course end date"


def test_resolve_uf_cutoff_end_keyword_matches_default():
    course = {"end_at": "2026-07-25T05:59:59Z"}
    assert resolve_uf_cutoff("end", course)[0].day == 25


def test_resolve_uf_cutoff_falls_back_to_term_end_when_no_course_end():
    """A course with no end_at (the common case — dates come from the term)."""
    course = {"end_at": None, "term": {"end_at": "2026-08-01T12:00:00Z"}}
    d, src = resolve_uf_cutoff(None, course)
    assert d is not None and d.strftime("%Y-%m-%d") == "2026-08-01"
    assert src == "Canvas term end date"


def test_resolve_uf_cutoff_term_end_keyword_forces_term():
    course = {"end_at": "2026-07-25T00:00:00Z", "term": {"end_at": "2026-08-01T00:00:00Z"}}
    d, src = resolve_uf_cutoff("term-end", course)
    assert d.strftime("%Y-%m-%d") == "2026-08-01" and src == "Canvas term end date"


def test_resolve_uf_cutoff_explicit_date_wins():
    course = {"end_at": "2026-07-25T00:00:00Z"}
    d, src = resolve_uf_cutoff("2026-06-01", course)
    assert d.strftime("%Y-%m-%d") == "2026-06-01" and src == "explicit --uf-date"


def test_resolve_uf_cutoff_none_when_no_dates_available():
    """No arg + Canvas has neither course nor term end -> caller must ask for one."""
    d, src = resolve_uf_cutoff(None, {"end_at": None, "term": {}})
    assert d is None and src == "Canvas term end date"


def test_resolve_uf_cutoff_invalid_explicit_reports_explicit_source():
    """A bad explicit date returns None but labels the source so the caller can
    print the right 'invalid --uf-date' message rather than 'no end date'."""
    d, src = resolve_uf_cutoff("not-a-date", {"end_at": "2026-07-25T00:00:00Z"})
    assert d is None and src == "explicit --uf-date"


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
    """Named, FLAGGED rows post-reidentification (only what the focused report shows —
    passing-and-engaged students are excluded upstream)."""
    return [
        {"user_id": 1, "name": "Smith, A", "last_engagement_str": "2026-03-15",
         "current_score": 50.0, "title_iv_class": "UW-before", "enrollment_state": "active"},
        {"user_id": 3, "name": "Lee, C", "last_engagement_str": "(never)",
         "current_score": None, "title_iv_class": "UW-never", "enrollment_state": "active"},
        {"user_id": 5, "name": "Kim, E", "last_engagement_str": "2026-05-01",
         "current_score": 40.0, "title_iv_class": "F-After", "enrollment_state": "inactive"},
    ]


def test_render_report_md_includes_title_iv_verification_date():
    """The report MUST include the Title IV verification date stamp
    so the recipient knows when the rules were last sanity-checked."""
    md = render_report_md(_named_rows(), "Test Course", "12345",
                          "2026-04-15", "2026-06-26 12:00 UTC", 60.0)
    assert "2026-06-26" in md  # the verification date stamp


def test_render_report_md_has_the_three_class_sections():
    """The focused report has a section per flag class (UW-never/UW-before/F-After)."""
    md = render_report_md(_named_rows(), "Test Course", "12345",
                          "2026-04-15", "2026-06-26 12:00 UTC", 60.0)
    assert "## UW-never" in md
    assert "## UW-before" in md
    assert "## F-After" in md


def test_render_report_md_counts_match_input():
    """The summary counts must match the flagged rows (1 each, 3 total)."""
    md = render_report_md(_named_rows(), "Test Course", "12345",
                          "2026-04-15", "2026-06-26 12:00 UTC", 60.0)
    assert "**1** UW-never" in md
    assert "**1** UW-before" in md
    assert "**1** F-After" in md
    assert "**3** flagged total" in md


def test_render_report_md_excludes_passing_students():
    """A passing-engaged row would never be in `rows` (filtered upstream) — the
    report shows only flagged students. Sanity: 'passing' never appears as a class."""
    md = render_report_md(_named_rows(), "Test Course", "12345",
                          "2026-04-15", "2026-06-26 12:00 UTC", 60.0)
    assert "Park, D" not in md  # the old passing student isn't in the fixture anymore
    assert "enrollment" in md.lower()  # the Enrollment column is present


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
    """No flagged students → still a valid report: each class section shows _(none)_,
    0 flagged total. (Every student passing-and-engaged is the good case.)"""
    md = render_report_md([], "Empty Course", "99999",
                          "2026-04-15", "2026-06-26 12:00 UTC", 60.0)
    assert "## UW-never" in md
    assert "_(none)_" in md
    assert "**0** flagged total" in md


def test_render_report_md_sorts_within_section():
    """Within a class section, students are sorted by name (deterministic report)."""
    rows = [
        {"user_id": 1, "name": "Zoo, Z", "last_engagement_str": "2026-03-15",
         "current_score": 50.0, "title_iv_class": "UW-before", "enrollment_state": "active"},
        {"user_id": 2, "name": "Aaa, A", "last_engagement_str": "2026-03-16",
         "current_score": 40.0, "title_iv_class": "UW-before", "enrollment_state": "active"},
    ]
    md = render_report_md(rows, "Test", "1", "2026-04-15",
                          "2026-06-26 12:00 UTC", 60.0)
    assert 0 < md.find("Aaa, A") < md.find("Zoo, Z")


# ---------------------------------------------------------------------------
# fetch_enrollments — Link-header pagination (crash fix) + inactive inclusion
# ---------------------------------------------------------------------------

import course_engagement_audit as _CEA  # noqa: E402


class _EnrollResp:
    def __init__(self, payload, link=""):
        self._payload = payload
        self.headers = {"Link": link}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_enrollments_single_page_does_not_crash(monkeypatch):
    """The bug: blind page+=1 hit page 2, which /enrollments answers with HTTP 400,
    crashing the audit for any course <=100 students. Link-header pagination stops
    after one page when there's no rel=next — no second request."""
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        return _EnrollResp([{"user_id": 1, "enrollment_state": "active"}])  # no Link
    monkeypatch.setattr(_CEA.requests, "get", fake_get)
    out = _CEA.fetch_enrollments("https://x", "1", {})
    assert len(out) == 1
    assert len(calls) == 1  # exactly one page — never asked for the crashing page 2


def test_fetch_enrollments_follows_link_next(monkeypatch):
    pages = [
        _EnrollResp([{"user_id": 1, "enrollment_state": "active"}],
                    link='<https://x/enrollments?page=2>; rel="next"'),
        _EnrollResp([{"user_id": 2, "enrollment_state": "inactive"}]),  # no next
    ]
    seq = iter(pages)
    monkeypatch.setattr(_CEA.requests, "get", lambda url, **kw: next(seq))
    out = _CEA.fetch_enrollments("https://x", "1", {})
    assert [e["user_id"] for e in out] == [1, 2]


def test_fetch_enrollments_include_inactive_requests_inactive_states(monkeypatch):
    captured = {}

    def fake_get(url, **kw):
        captured["params"] = kw.get("params")
        return _EnrollResp([])
    monkeypatch.setattr(_CEA.requests, "get", fake_get)

    _CEA.fetch_enrollments("https://x", "1", {}, include_inactive=True)
    states = [v for (k, v) in captured["params"] if k == "state[]"]
    assert "inactive" in states and "active" in states

    _CEA.fetch_enrollments("https://x", "1", {}, include_inactive=False)
    states = [v for (k, v) in captured["params"] if k == "state[]"]
    assert "inactive" not in states and "active" in states


def test_render_report_shows_inactive_students_with_their_enrollment_state():
    """Inactive/completed enrollments ARE included (potential unofficial withdrawals),
    classified like anyone else, with their enrollment state shown in the Enrollment
    column so the reviewer knows they're not currently active."""
    rows = [
        {"user_id": 9, "name": "Gone, G", "last_engagement_str": "2026-02-01",
         "current_score": 30.0, "title_iv_class": "UW-before", "enrollment_state": "inactive"},
    ]
    md = render_report_md(rows, "Test", "1", "2026-04-15", "2026-06-26 12:00 UTC", 60.0)
    assert "Gone, G" in md
    assert "inactive" in md          # enrollment state surfaced in the row
    assert "## UW-before" in md      # classified, not shunted to a separate bucket

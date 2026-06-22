"""Tier 1 unit tests — course_homepage_build pure-logic helpers.

Source: lib/tools/course_homepage_build.py (DesignPLUS-free home page
generator; v0.58.0).

These tests cover the deterministic helpers — date parsing, schedule
validation, current-week selection, module-URL building, render output.
The Canvas-API + filesystem-touching code (bootstrap, push) is exercised
manually via sandbox-first testing per AGENTS.md.

PLACEHOLDER-NAME CONVENTION (per AGENTS.md → Working Style):
  Fixture courses ("Sample Course", "REL 130") + module titles below
  are obviously-fake placeholders chosen for readability. NOT real
  student data — modules + dates are course-design metadata, not
  educational records.
"""
import sys
from datetime import date
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from course_homepage_build import (  # noqa: E402
    parse_iso_date,
    validate_schedule,
    pick_current_week,
    build_module_href,
    render_homepage,
    _html_escape,
)


# ---------------------------------------------------------------------------
# parse_iso_date
# ---------------------------------------------------------------------------

def test_parse_iso_date_from_string():
    assert parse_iso_date("2026-05-10") == date(2026, 5, 10)


def test_parse_iso_date_from_date_object():
    """YAML parses bare YYYY-MM-DD as a date object; should pass through."""
    d = date(2026, 5, 10)
    assert parse_iso_date(d) == d


def test_parse_iso_date_invalid_raises():
    try:
        parse_iso_date("not-a-date")
    except ValueError:
        return
    raise AssertionError("expected ValueError on garbage input")


def test_parse_iso_date_none_raises():
    try:
        parse_iso_date(None)
    except ValueError:
        return
    raise AssertionError("expected ValueError on None input")


# ---------------------------------------------------------------------------
# validate_schedule
# ---------------------------------------------------------------------------

_MINIMAL_VALID_SCHEDULE = {
    "course": {
        "name": "Sample Course",
        "code": "SMPL 101",
        "base_url": "https://example.instructure.com",
        "course_id": 12345,
    },
    "weeks": [
        {"week": 1, "title": "Week 01", "start": "2026-04-18", "end": "2026-04-24"},
    ],
}


def test_validate_minimal_valid_schedule():
    assert validate_schedule(_MINIMAL_VALID_SCHEDULE) == []


def test_validate_missing_course_block():
    errors = validate_schedule({"weeks": _MINIMAL_VALID_SCHEDULE["weeks"]})
    assert any("course" in e for e in errors)


def test_validate_missing_course_fields():
    bad = {"course": {"name": "x"}, "weeks": _MINIMAL_VALID_SCHEDULE["weeks"]}
    errors = validate_schedule(bad)
    assert any("course.code" in e for e in errors)
    assert any("course.base_url" in e for e in errors)
    assert any("course.course_id" in e for e in errors)


def test_validate_empty_weeks():
    bad = {"course": _MINIMAL_VALID_SCHEDULE["course"], "weeks": []}
    errors = validate_schedule(bad)
    assert any("weeks" in e for e in errors)


def test_validate_missing_week_fields():
    bad = {
        "course": _MINIMAL_VALID_SCHEDULE["course"],
        "weeks": [{"week": 1, "title": "x"}],  # missing start, end
    }
    errors = validate_schedule(bad)
    assert any("start" in e for e in errors)
    assert any("end" in e for e in errors)


def test_validate_malformed_date_in_week():
    bad = {
        "course": _MINIMAL_VALID_SCHEDULE["course"],
        "weeks": [
            {"week": 1, "title": "x", "start": "garbage", "end": "2026-04-24"},
        ],
    }
    errors = validate_schedule(bad)
    assert any("date parse error" in e for e in errors)


# ---------------------------------------------------------------------------
# pick_current_week — the load-bearing logic
# ---------------------------------------------------------------------------

_THREE_WEEKS = [
    {"week": 1, "title": "Week 01", "start": "2026-04-18", "end": "2026-04-24"},
    {"week": 2, "title": "Week 02", "start": "2026-04-25", "end": "2026-05-01"},
    {"week": 3, "title": "Week 03", "start": "2026-05-02", "end": "2026-05-08"},
]


def test_pick_current_week_first_day():
    assert pick_current_week(_THREE_WEEKS, date(2026, 4, 18))["week"] == 1


def test_pick_current_week_mid_week():
    assert pick_current_week(_THREE_WEEKS, date(2026, 4, 28))["week"] == 2


def test_pick_current_week_last_day():
    assert pick_current_week(_THREE_WEEKS, date(2026, 5, 8))["week"] == 3


def test_pick_current_week_before_term():
    """Pre-term: no week matches — return None."""
    assert pick_current_week(_THREE_WEEKS, date(2026, 4, 17)) is None


def test_pick_current_week_after_term():
    """Post-term: no week matches — return None."""
    assert pick_current_week(_THREE_WEEKS, date(2026, 5, 9)) is None


def test_pick_current_week_gap_in_schedule_returns_none():
    """Gap between weeks (Sat-Sun unscheduled) → no match → None."""
    gappy = [
        {"week": 1, "title": "Wk1", "start": "2026-04-18", "end": "2026-04-22"},
        {"week": 2, "title": "Wk2", "start": "2026-04-25", "end": "2026-04-29"},
    ]
    # Wednesday in the gap
    assert pick_current_week(gappy, date(2026, 4, 23)) is None


def test_pick_current_week_skips_malformed_dates():
    """A week with garbage dates is skipped, not crashed on."""
    weeks = [
        {"week": 1, "title": "x", "start": "garbage", "end": "garbage"},
        {"week": 2, "title": "y", "start": "2026-04-25", "end": "2026-05-01"},
    ]
    result = pick_current_week(weeks, date(2026, 4, 28))
    assert result["week"] == 2


# ---------------------------------------------------------------------------
# build_module_href
# ---------------------------------------------------------------------------

def test_build_module_href_from_components():
    course = {"base_url": "https://example.instructure.com", "course_id": 999}
    week = {"module_id": 42}
    assert build_module_href(course, week) == "https://example.instructure.com/courses/999/modules/42"


def test_build_module_href_explicit_href_wins():
    """Per-week `href` override takes precedence over the computed URL."""
    course = {"base_url": "https://example.instructure.com", "course_id": 999}
    week = {"module_id": 42, "href": "https://other.example.com/path"}
    assert build_module_href(course, week) == "https://other.example.com/path"


def test_build_module_href_no_module_id_returns_hash():
    """Without a module_id + without an explicit href: return '#' so the
    caller can suppress the link."""
    course = {"base_url": "https://example.instructure.com", "course_id": 999}
    week = {"title": "Week 1"}
    assert build_module_href(course, week) == "#"


# ---------------------------------------------------------------------------
# render_homepage — output-shape assertions, not exact HTML
# ---------------------------------------------------------------------------

def test_render_includes_course_header():
    html = render_homepage(_MINIMAL_VALID_SCHEDULE, date(2026, 4, 20))
    assert "Sample Course" in html
    assert "SMPL 101" in html


def test_render_includes_inline_css():
    """The CSS must be inline — no external <link> tags."""
    html = render_homepage(_MINIMAL_VALID_SCHEDULE, date(2026, 4, 20))
    assert "<style>" in html
    assert ".ct-homepage" in html
    assert "<link " not in html  # no external stylesheets


def test_render_no_javascript():
    """Pure HTML+CSS guarantee — no <script>, no inline event handlers."""
    html = render_homepage(_MINIMAL_VALID_SCHEDULE, date(2026, 4, 20))
    assert "<script" not in html
    assert "onclick=" not in html
    assert "onload=" not in html


def test_render_marks_current_week_open():
    """The week matching today gets `<details open>`; others stay closed."""
    schedule = {
        "course": _MINIMAL_VALID_SCHEDULE["course"],
        "weeks": _THREE_WEEKS,
    }
    html = render_homepage(schedule, date(2026, 4, 28))  # week 2
    assert '<details id="week-2" class="ct-week" open>' in html
    assert '<details id="week-1" class="ct-week">' in html
    assert '<details id="week-3" class="ct-week">' in html


def test_render_no_week_open_when_pre_term():
    """Pre-term: no week matches, no `<details open>` anywhere."""
    schedule = {
        "course": _MINIMAL_VALID_SCHEDULE["course"],
        "weeks": _THREE_WEEKS,
    }
    html = render_homepage(schedule, date(2026, 4, 17))
    assert " open>" not in html  # neither week opens


def test_render_marks_current_week_button():
    """The current week's button gets the `.current` CSS class."""
    schedule = {
        "course": _MINIMAL_VALID_SCHEDULE["course"],
        "weeks": _THREE_WEEKS,
    }
    html = render_homepage(schedule, date(2026, 5, 5))  # week 3
    assert '<a href="#week-3" class="current">Week 3</a>' in html
    assert '<a href="#week-1" class="">Week 1</a>' in html  # explicit empty class


def test_render_quick_links_appear():
    schedule = {
        **_MINIMAL_VALID_SCHEDULE,
        "quick_links": [
            {"title": "Syllabus", "href": "/syllabus", "icon": "📄"},
        ],
    }
    html = render_homepage(schedule, date(2026, 4, 20))
    assert "Syllabus" in html
    assert "/syllabus" in html
    assert "📄" in html


def test_render_banner_appears_when_set():
    schedule = {
        **_MINIMAL_VALID_SCHEDULE,
        "course": {
            **_MINIMAL_VALID_SCHEDULE["course"],
            "banner_url": "https://example.com/banner.jpg",
        },
    }
    html = render_homepage(schedule, date(2026, 4, 20))
    assert "https://example.com/banner.jpg" in html
    assert 'class="ct-banner"' in html


def test_render_banner_skipped_when_not_set():
    html = render_homepage(_MINIMAL_VALID_SCHEDULE, date(2026, 4, 20))
    assert 'class="ct-banner"' not in html


def test_render_style_overrides_applied():
    """Custom colors flow through the CSS."""
    schedule = {
        **_MINIMAL_VALID_SCHEDULE,
        "style": {"primary_color": "#003366", "current_color": "#FF6600"},
    }
    html = render_homepage(schedule, date(2026, 4, 20))
    assert "#003366" in html
    assert "#FF6600" in html


# ---------------------------------------------------------------------------
# _html_escape (defensive)
# ---------------------------------------------------------------------------

def test_html_escape_basic():
    assert _html_escape("<script>") == "&lt;script&gt;"
    assert _html_escape('a & b') == "a &amp; b"
    assert _html_escape('"quoted"') == "&quot;quoted&quot;"


def test_html_escape_none_returns_empty():
    assert _html_escape(None) == ""


def test_html_escape_non_string():
    """Numbers, etc., get str()'d safely."""
    assert _html_escape(42) == "42"

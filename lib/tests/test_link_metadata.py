"""Unit tests for `lib/tools/_link_metadata.py` — pure HTML normalization.

No Canvas API needed; runs in isolation (does not import conftest sandbox
fixtures). Verifies the helper that defends against issue #42 (Canvas leaving
stale `data-api-*` attributes on `<a>` tags after an `href` swap).
"""

import sys
from pathlib import Path

# Make lib/tools importable without installing the package
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _link_metadata import (  # noqa: E402
    strip_stale_link_metadata,
    find_stale_link_metadata,
    _canonical_target,
    _same_target,
)


# ---------------------------------------------------------------------------
# _canonical_target — URL parsing
# ---------------------------------------------------------------------------

def test_canonical_target_ui_url():
    assert _canonical_target(
        "https://byui.instructure.com/courses/100/pages/foo"
    ) == ("100", "pages/foo")


def test_canonical_target_api_url():
    assert _canonical_target(
        "https://byui.instructure.com/api/v1/courses/100/pages/foo"
    ) == ("100", "pages/foo")


def test_canonical_target_external_url():
    assert _canonical_target("https://video.byui.edu/media/t/1_k2ct971x") is None


def test_canonical_target_strips_query_and_fragment():
    assert _canonical_target(
        "https://byui.instructure.com/courses/100/pages/foo?wrap=1#section"
    ) == ("100", "pages/foo")


def test_canonical_target_empty():
    assert _canonical_target("") is None


# ---------------------------------------------------------------------------
# _same_target — matching logic
# ---------------------------------------------------------------------------

def test_same_target_matching_pair():
    assert _same_target(
        "https://byui.instructure.com/courses/100/pages/foo",
        "https://byui.instructure.com/api/v1/courses/100/pages/foo",
    ) is True


def test_same_target_external_href_never_matches():
    assert _same_target(
        "https://video.byui.edu/media/t/1_k2ct971x",
        "https://byui.instructure.com/api/v1/courses/100/discussion_topics/123",
    ) is False


def test_same_target_different_resource_type():
    assert _same_target(
        "https://byui.instructure.com/courses/100/pages/foo",
        "https://byui.instructure.com/api/v1/courses/100/assignments/123",
    ) is False


def test_same_target_different_course():
    assert _same_target(
        "https://byui.instructure.com/courses/100/pages/foo",
        "https://byui.instructure.com/api/v1/courses/200/pages/foo",
    ) is False


# ---------------------------------------------------------------------------
# strip_stale_link_metadata — normalization
# ---------------------------------------------------------------------------

def test_no_anchors_unchanged():
    html = "<p>just text and <strong>bold</strong></p>"
    assert strip_stale_link_metadata(html) == (html, 0)


def test_empty_string():
    assert strip_stale_link_metadata("") == ("", 0)


def test_anchor_without_data_api_endpoint_unchanged():
    html = '<a href="https://example.com">click</a>'
    out, n = strip_stale_link_metadata(html)
    assert out == html
    assert n == 0


def test_matching_pair_left_alone():
    """Canvas-internal href + matching data-api-endpoint → no change."""
    html = (
        '<a href="https://byui.instructure.com/courses/100/pages/foo" '
        'data-api-endpoint="https://byui.instructure.com/api/v1/courses/100/pages/foo" '
        'data-api-returntype="Page">x</a>'
    )
    out, n = strip_stale_link_metadata(html)
    assert out == html
    assert n == 0


def test_itm327_lab_walkthrough_case():
    """Verbatim from issue #42: external Kaltura href, stale Canvas discussion metadata."""
    html = (
        '<a class="inline" '
        'href="https://video.byui.edu/media/t/1_k2ct971x" '
        'target="_blank" '
        'data-api-endpoint="https://byui.instructure.com/api/v1/courses/415320/discussion_topics/10066500" '
        'data-api-returntype="Discussion">Lab 1 Walkthrough</a>'
    )
    out, n = strip_stale_link_metadata(html)
    assert n == 1
    assert "data-api-endpoint" not in out
    assert "data-api-returntype" not in out
    # Surrounding context preserved
    assert 'href="https://video.byui.edu/media/t/1_k2ct971x"' in out
    assert 'class="inline"' in out
    assert 'target="_blank"' in out
    assert ">Lab 1 Walkthrough</a>" in out


def test_different_canvas_resource_strips():
    """Href -> /pages/foo but data-api -> /assignments/123 → strip."""
    html = (
        '<a href="https://byui.instructure.com/courses/100/pages/foo" '
        'data-api-endpoint="https://byui.instructure.com/api/v1/courses/100/assignments/123" '
        'data-api-returntype="Assignment">x</a>'
    )
    out, n = strip_stale_link_metadata(html)
    assert n == 1
    assert "data-api-endpoint" not in out


def test_idempotent():
    """Run twice → identical result, second pass count=0."""
    html = (
        '<a href="https://video.byui.edu/foo" '
        'data-api-endpoint="https://byui.instructure.com/api/v1/courses/1/pages/x" '
        'data-api-returntype="Page">y</a>'
    )
    once, n1 = strip_stale_link_metadata(html)
    twice, n2 = strip_stale_link_metadata(once)
    assert once == twice
    assert n1 == 1
    assert n2 == 0


def test_multiple_anchors_only_stale_touched():
    """One matching anchor + one stale anchor → only the stale one is normalized."""
    html = (
        "<p>"
        '<a href="https://byui.instructure.com/courses/100/pages/foo" '
        'data-api-endpoint="https://byui.instructure.com/api/v1/courses/100/pages/foo">match</a> '
        '<a href="https://video.byui.edu/x" '
        'data-api-endpoint="https://byui.instructure.com/api/v1/courses/100/pages/foo">stale</a>'
        "</p>"
    )
    out, n = strip_stale_link_metadata(html)
    assert n == 1
    # The matching anchor retains its data-api-endpoint
    assert out.count("data-api-endpoint") == 1


def test_single_quote_attributes():
    """Same logic should work for single-quoted attributes."""
    html = (
        "<a href='https://video.byui.edu/x' "
        "data-api-endpoint='https://byui.instructure.com/api/v1/courses/1/pages/x' "
        "data-api-returntype='Page'>y</a>"
    )
    out, n = strip_stale_link_metadata(html)
    assert n == 1
    assert "data-api-endpoint" not in out
    assert "data-api-returntype" not in out


# ---------------------------------------------------------------------------
# find_stale_link_metadata — read-only audit
# ---------------------------------------------------------------------------

def test_find_returns_empty_for_clean_html():
    html = '<a href="https://example.com">x</a>'
    assert find_stale_link_metadata(html) == []


def test_find_returns_one_for_stale_anchor():
    html = (
        '<a href="https://video.byui.edu/x" '
        'data-api-endpoint="https://byui.instructure.com/api/v1/courses/1/pages/foo" '
        'data-api-returntype="Page">y</a>'
    )
    findings = find_stale_link_metadata(html)
    assert len(findings) == 1
    f = findings[0]
    assert f["href"] == "https://video.byui.edu/x"
    assert "courses/1/pages/foo" in f["data_api_endpoint"]
    assert f["data_api_returntype"] == "Page"


def test_find_skips_matching_pairs():
    html = (
        '<a href="https://byui.instructure.com/courses/100/pages/foo" '
        'data-api-endpoint="https://byui.instructure.com/api/v1/courses/100/pages/foo" '
        'data-api-returntype="Page">x</a>'
    )
    assert find_stale_link_metadata(html) == []


def test_find_skips_anchors_without_data_api():
    html = '<a href="https://video.byui.edu/x">y</a>'
    assert find_stale_link_metadata(html) == []

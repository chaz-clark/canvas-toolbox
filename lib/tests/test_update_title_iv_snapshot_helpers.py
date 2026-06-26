"""Tier 1 unit tests — update_title_iv_snapshot pure-logic helpers.

Source: lib/tools/update_title_iv_snapshot.py
  - extract_text (HTML → readable text via regex; deterministic)
  - render_snapshot_md (cached snapshot file content)

These tests cover the regex-extraction pipeline that turns canonical
Title IV HTML into token-cheap local snapshots.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from update_title_iv_snapshot import (  # noqa: E402
    TitleIVSource,
    extract_text,
    render_snapshot_md,
)


# ---------------------------------------------------------------------------
# extract_text — HTML → readable text via regex
# ---------------------------------------------------------------------------

def test_extract_text_strips_scripts():
    """JavaScript tags must not bleed into the snapshot — they're
    huge + meaningless + token-expensive."""
    html = """
    <html>
      <body>
        <p>Real content here.</p>
        <script>var foo = 'do not include this';</script>
        <p>More content.</p>
      </body>
    </html>
    """
    text = extract_text(html)
    assert "Real content" in text
    assert "More content" in text
    assert "var foo" not in text
    assert "do not include" not in text


def test_extract_text_strips_styles():
    """<style> blocks (CSS) are also noise."""
    html = "<style>.foo { color: red; }</style><p>Text</p>"
    text = extract_text(html)
    assert "color: red" not in text
    assert "Text" in text


def test_extract_text_strips_html_comments():
    """HTML comments don't belong in the snapshot."""
    html = "<!-- secret note --><p>Visible content</p><!-- another -->"
    text = extract_text(html)
    assert "secret note" not in text
    assert "another" not in text
    assert "Visible content" in text


def test_extract_text_strips_nav_and_footer():
    """Site chrome (nav + footer + aside) is noise for Title IV
    content extraction."""
    html = """
    <nav>Site Navigation Menu</nav>
    <main>
      <p>Actual rule text.</p>
    </main>
    <footer>Copyright stuff</footer>
    <aside>Sidebar widget</aside>
    """
    text = extract_text(html)
    assert "Site Navigation" not in text
    assert "Copyright stuff" not in text
    assert "Sidebar widget" not in text
    assert "Actual rule text" in text


def test_extract_text_decodes_entities():
    """Common HTML entities → plaintext (so the regex grep works
    cleanly downstream)."""
    html = "<p>Title IV &amp; R2T4 &nbsp; rules &lt;effective&gt; 2026</p>"
    text = extract_text(html)
    assert "Title IV & R2T4" in text
    assert "<effective>" in text


def test_extract_text_decodes_numeric_entities():
    """Numeric entities (&#8211; em-dash, etc.) decoded too."""
    html = "<p>Section A &#8211; Withdrawals</p>"
    text = extract_text(html)
    assert "Section A" in text
    # &#8211; is the en-dash (U+2013)
    assert chr(8211) in text


def test_extract_text_converts_block_tags_to_newlines():
    """Paragraph-level + heading-level tags become newlines so the
    extracted text is human-readable, not one big run-on."""
    html = "<h1>Title</h1><p>Para 1.</p><p>Para 2.</p>"
    text = extract_text(html)
    assert "Title" in text
    assert "Para 1." in text
    assert "Para 2." in text
    # The lines should be separated, not one blob
    assert "Para 1.Para 2." not in text


def test_extract_text_collapses_excessive_whitespace():
    """Multiple blank lines collapse to at most one — keeps the
    snapshot tight."""
    html = "<p>Line 1</p>\n\n\n\n\n<p>Line 2</p>"
    text = extract_text(html)
    # No run of 3+ blank lines
    assert "\n\n\n" not in text


def test_extract_text_handles_empty_input():
    """None / empty string → empty output (no crash)."""
    assert extract_text("") == ""
    assert extract_text(None) == ""


def test_extract_text_uses_body_regex_when_provided():
    """When a per-site body_regex is provided, extract only the matching
    section — this is how we scope to a Cornell Law CFR text without
    pulling the entire wrapper page."""
    html = """
    <html>
      <header>Header noise</header>
      <div id="content">
        <p>Only this content matters.</p>
      </div>
      <footer>Footer noise</footer>
    </html>
    """
    body_regex = r'<div[^>]*id="content"[^>]*>(.*?)</div>'
    text = extract_text(html, body_regex=body_regex)
    assert "Only this content matters" in text
    assert "Header noise" not in text
    assert "Footer noise" not in text


def test_extract_text_falls_back_when_body_regex_no_match():
    """If body_regex doesn't match (e.g., site re-themed), fall back
    to extracting from the whole HTML — better than empty."""
    html = "<p>Some content that doesn't match the regex.</p>"
    body_regex = r'<div class="nonexistent">(.*?)</div>'
    text = extract_text(html, body_regex=body_regex)
    assert "Some content" in text


def test_extract_text_deterministic():
    """Same HTML input → identical text output. This is the basis for
    the sha256 content-hash diff in the manifest."""
    html = "<p>Title IV final rules</p><script>noise</script><p>R2T4</p>"
    text1 = extract_text(html)
    text2 = extract_text(html)
    assert text1 == text2


# ---------------------------------------------------------------------------
# render_snapshot_md — the cached snapshot file content
# ---------------------------------------------------------------------------

def test_render_snapshot_md_includes_metadata_header():
    """The rendered snapshot must include the URL, fetch date, and
    source id so a future reader knows what they're looking at."""
    source = TitleIVSource(
        id="test-source",
        url="https://example.gov/title-iv/rule",
        label="Test Title IV Rule",
    )
    text = "The full text of the rule goes here."
    md = render_snapshot_md(source, text, "2026-06-26T12:00:00Z")
    assert "Test Title IV Rule" in md
    assert "https://example.gov/title-iv/rule" in md
    assert "2026-06-26T12:00:00Z" in md
    assert "test-source" in md


def test_render_snapshot_md_includes_body_text():
    """The extracted body text is the bulk of the snapshot."""
    source = TitleIVSource(
        id="t", url="https://example.gov/t", label="T",
    )
    text = "The unique body content that must appear."
    md = render_snapshot_md(source, text, "2026-06-26T12:00:00Z")
    assert "The unique body content that must appear" in md


def test_render_snapshot_md_includes_provenance_note():
    """The snapshot names itself as auto-generated + tells the reader
    how to refresh — defends against confusion later."""
    source = TitleIVSource(id="t", url="https://example.gov/t", label="T")
    md = render_snapshot_md(source, "body", "2026-06-26T12:00:00Z")
    assert "update_title_iv_snapshot.py" in md
    assert "regex" in md.lower()  # explains the extraction method

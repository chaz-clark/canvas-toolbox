"""Tier 1 unit tests — clo_catalog_import pure helpers.

Covers the text-normalization + parsing helpers that don't touch the network:
_clean (catalog value -> clean, nbsp-free), _norm (HTML description -> plain
words for change-detection), _next_link (Link-header pagination), and
default_institution (env / CANVAS_BASE_URL inference). The catalog + Canvas
I/O paths are exercised live, not unit-tested here.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import clo_catalog_import as C  # noqa: E402


def test_clean_strips_nbsp_entities_and_collapses():
    # internal non-breaking space is the bug that stored &nbsp; in Canvas.
    assert C._clean("Explore and interpret  data") == "Explore and interpret data"
    assert C._clean("SQL &amp; ELT ") == "SQL & ELT"
    assert C._clean("  padded \n line  ") == "padded line"


def test_norm_treats_nbsp_and_space_as_equal_and_strips_tags():
    # &nbsp; vs a plain space normalize equal — why a re-run reports "unchanged".
    assert C._norm("interpret&nbsp;distributed") == C._norm("interpret distributed")
    assert C._norm("<p>hello <b>world</b></p>") == "hello world"


def test_next_link_parses_rel_next():
    h = '<https://x/api?page=1>; rel="current", <https://x/api?page=2>; rel="next"'
    assert C._next_link(h) == "https://x/api?page=2"
    assert C._next_link('<https://x/api?page=3>; rel="last"') is None
    assert C._next_link("") is None


def test_default_institution_prefers_env(monkeypatch):
    monkeypatch.setenv("CANVAS_INSTITUTION", "acme")
    assert C.default_institution() == "acme"


def test_default_institution_infers_from_base_url(monkeypatch):
    monkeypatch.delenv("CANVAS_INSTITUTION", raising=False)
    monkeypatch.setattr(C, "CANVAS_BASE_URL", "https://byui.instructure.com")
    assert C.default_institution() == "byui"

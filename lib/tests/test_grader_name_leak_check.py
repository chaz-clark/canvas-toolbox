"""Tier 1 unit tests — grader_name_leak_check heuristic pass.

Source: lib/tools/grader_name_leak_check.py (issue #94 — heuristic safety
net for off-roster greeting-position names).

These tests cover the PURE-LOGIC helper `heuristic_greeting_hits()` only.
The CLI main() loop is exercised end-to-end via the existing sprint
tests (gated on CANVAS_SANDBOX_ID) and via manual end-to-end runs.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_name_leak_check import heuristic_greeting_hits  # noqa: E402


# ---------------------------------------------------------------------------
# The headline regression test for #94 — a name NOT in the roster but
# present in greeting position MUST be flagged by the heuristic.
# ---------------------------------------------------------------------------

def test_heuristic_catches_off_roster_greeting_name():
    """The precipitating #94 bug: a name absent from .known_names.txt that
    survives the scrub MUST still be caught by the heuristic pass."""
    text = "Excellent work, Sarah!"
    hits = heuristic_greeting_hits(text)
    assert "Sarah" in hits


def test_heuristic_catches_multiple_greetings():
    """Multiple greeting hits in one body — all reported."""
    text = "Hi Alex, great work. Excellent work, Maya!"
    hits = heuristic_greeting_hits(text)
    assert "Alex" in hits
    assert "Maya" in hits
    assert len(hits) == 2


def test_heuristic_clean_text_returns_empty():
    """No greeting + no capitalized-after-greeting → no hits."""
    text = "Submission processed. All counts match the gradebook."
    assert heuristic_greeting_hits(text) == []


def test_heuristic_no_match_without_greeting():
    """A capitalized name NOT preceded by a greeting phrase is NOT flagged.
    Heuristic is greeting-anchored deliberately."""
    text = "Worked with Spark and Pandas all week."
    hits = heuristic_greeting_hits(text)
    # Neither Spark nor Pandas should match (no greeting prefix)
    assert "Spark" not in hits
    assert "Pandas" not in hits


def test_heuristic_lowercase_greeting_case_insensitive():
    """Greeting phrase is case-insensitive; 'hi sarah' wouldn't capture
    'sarah' (lowercase fails the name shape) but 'hi Sarah' should."""
    assert "Sarah" in heuristic_greeting_hits("hi Sarah, well done")
    # lowercase name not caught — that's the design (avoid over-scrubbing
    # every word; rely on the roster for lowercase variants)
    assert heuristic_greeting_hits("hi sarah, well done") == []


def test_heuristic_handles_empty_and_none():
    """Defensive: empty + None inputs return empty list, never crash."""
    assert heuristic_greeting_hits("") == []
    assert heuristic_greeting_hits(None) == []  # type: ignore[arg-type]


def test_heuristic_over_redaction_documented():
    """Documents the accepted trade — 'Hi There,' yields 'There' as a hit.
    A leaked name is the larger harm; an occasional false-positive on a
    capitalized non-name in greeting position is acceptable."""
    text = "Hi There, your code is fine"
    assert "There" in heuristic_greeting_hits(text)

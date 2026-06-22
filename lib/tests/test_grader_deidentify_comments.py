"""Tier 1 unit tests — grader_deidentify_comments::scrub_comment.

Source: lib/tools/grader_deidentify_comments.py (#65 — FERPA-safe
de-identification of Canvas submission_comments before they enter the
grader's view).

scrub_comment(body, extra_names) returns (scrubbed_body, total_scrubs).
It runs name-aware (word-bounded) substitution for roster names + emails
+ user-paths, plus secret-prefix scrubbing.

PLACEHOLDER-NAME CONVENTION (per AGENTS.md → Working Style):
  ALL names appearing in test fixture strings below (Sarah, Alex, Maya,
  Jamie, Jordan, Pat, Riley, Lee, Casey, Morgan, Sam, Maria, There,
  Spark, etc.) are OBVIOUSLY-FAKE placeholders chosen for readability,
  the way "Alice/Bob" are used in crypto examples. They are NOT real
  students. Quotes are omitted INSIDE the test strings because the
  tests assert against literal grading-comment shapes; the convention
  is documented HERE so reviewers don't mistake them for real names.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_deidentify_comments import scrub_comment  # noqa: E402


# ---------------------------------------------------------------------------
# Email scrubbing
# ---------------------------------------------------------------------------

def test_scrub_email_redacts():
    out, n = scrub_comment("Contact jane@example.com for details.", [])
    assert "jane@example.com" not in out
    assert "[REDACTED]" in out
    assert n >= 1


def test_scrub_multiple_emails():
    out, n = scrub_comment(
        "Email a@b.com or c@d.org for help.", [],
    )
    assert "a@b.com" not in out
    assert "c@d.org" not in out
    assert n >= 2


# ---------------------------------------------------------------------------
# Roster-name scrubbing (word-bounded)
# ---------------------------------------------------------------------------

def test_scrub_roster_name():
    out, n = scrub_comment("Great job, Jane!", ["Jane Doe"])
    # The first name should be redacted; word-bounded so 'janet' wouldn't be
    assert "Jane" not in out
    assert n >= 1


def test_scrub_word_boundary_preserves_unrelated_substrings():
    """`Jane` in roster should NOT match the substring `janet`."""
    out, _ = scrub_comment("Janet sent feedback.", ["Jane Doe"])
    assert "Janet" in out  # word-boundary protected


def test_scrub_clean_text_unchanged():
    """Body with no PII / secrets / known names → unchanged, n=0."""
    out, n = scrub_comment("Good submission. Solid work overall.", [])
    assert out == "Good submission. Solid work overall."
    assert n == 0


# ---------------------------------------------------------------------------
# Secret scrubbing
# ---------------------------------------------------------------------------

def test_scrub_secret_prefix_redacted():
    """SECRET_PREFIX_RE matches well-known credential prefixes (github_pat_,
    gh[opsru]_, AKIA<16>, xox[bapr]s-)."""
    # Synthetic github PAT string — no real credential
    body = "My key is github_pat_AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKKLL"
    out, n = scrub_comment(body, [])
    assert "github_pat_AAAA" not in out
    assert "REDACTED-SECRET" in out
    assert n >= 1


def test_scrub_secret_assign_redacted():
    """SECRET_ASSIGN_RE matches `token = "<value>"` style assignments."""
    body = 'config: api_key = "abcdef1234567890"'
    out, n = scrub_comment(body, [])
    assert "abcdef1234567890" not in out
    assert "REDACTED-SECRET" in out
    assert n >= 1


def test_scrub_returns_tuple_shape():
    """Contract: returns (str, int)."""
    result = scrub_comment("Plain text.", [])
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], int)


# ---------------------------------------------------------------------------
# Issue #94 — greeting-position name scrub (FERPA safety net)
# The precipitating incident: a TA comment "Excellent work, Sarah!" where
# Sarah was a dropped student not in the active roster. Without the greeting
# scrub, "Sarah" leaks past the roster pass AND the leak check (which uses
# the same roster) reports a false "clean."
# ---------------------------------------------------------------------------

def test_scrub_greeting_off_roster_name():
    """The precipitating bug — name NOT in roster, leaked via greeting position."""
    body = "Excellent work, Sarah!"
    out, n = scrub_comment(body, extra_names=[])  # Sarah NOT in roster
    assert "Sarah" not in out
    assert "[REDACTED]" in out
    assert "Excellent work" in out  # greeting prefix preserved
    assert n >= 1


def test_scrub_greeting_preserves_greeting_text():
    """The greeting phrase + separator stays; only the name is redacted."""
    out, _ = scrub_comment("Hi Jamie, great submission.", extra_names=[])
    assert out.startswith("Hi ")  # greeting + space preserved
    assert "[REDACTED]" in out
    assert "Jamie" not in out
    assert "great submission" in out  # downstream content untouched


def test_scrub_greeting_lowercase_greeting_still_caught():
    """Greeting is case-INSENSITIVE; common 'hi sarah' shape works too."""
    out, _ = scrub_comment("hi Maya, well done", extra_names=[])
    assert "Maya" not in out
    assert "[REDACTED]" in out


def test_scrub_greeting_lowercase_name_not_caught():
    """The name MUST be capitalized — lowercase 'sarah' is not flagged.
    Caught by the roster path when the roster has the name (the canonical
    case); the greeting heuristic is the safety net for capitalized names."""
    out, _ = scrub_comment("hi sarah, well done", extra_names=[])
    # sarah remains because it's lowercase + not in any roster terms here
    assert "sarah" in out


def test_scrub_greeting_no_match_without_greeting():
    """A capitalized name NOT in greeting position + NOT in the roster is
    NOT scrubbed by this heuristic. The heuristic is greeting-anchored on
    purpose — broader 'redact every capitalized word' would over-scrub the
    body massively."""
    out, _ = scrub_comment("Worked through the Spark exercise.", extra_names=[])
    assert "Spark" in out  # not in greeting position; safe


def test_scrub_greeting_over_redaction_accepted():
    """Reporter explicitly accepted over-redacting capitalized non-names in
    greeting position (e.g., 'Hi There,' → 'There' redacted). The trade is
    intentional: a leaked name is the larger harm. This test documents the
    accepted behavior so it doesn't drift."""
    out, _ = scrub_comment("Hi There, your code is good", extra_names=[])
    assert "There" not in out
    assert "[REDACTED]" in out


def test_scrub_greeting_all_greeting_phrases():
    """Verify each greeting phrase from the reporter's list works."""
    phrases = [
        ("Hi Sarah!", "Sarah"),
        ("Hey Alex,", "Alex"),
        ("Hello Maria,", "Maria"),
        ("Dear Sam,", "Sam"),
        ("Nice work, Jordan!", "Jordan"),
        ("Great work, Pat!", "Pat"),
        ("Excellent work, Sarah!", "Sarah"),
        ("Good work, Riley!", "Riley"),
        ("Good job, Lee!", "Lee"),
        ("Well done, Casey!", "Casey"),
        ("Nicely done, Morgan!", "Morgan"),
    ]
    for body, name in phrases:
        out, _ = scrub_comment(body, extra_names=[])
        assert name not in out, f"{name!r} leaked past greeting scrub in {body!r}"
        assert "[REDACTED]" in out, f"no redaction marker in {body!r} → {out!r}"

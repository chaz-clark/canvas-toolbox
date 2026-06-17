"""Tier 1 unit tests — grader_deidentify_comments::scrub_comment.

Source: lib/tools/grader_deidentify_comments.py (#65 — FERPA-safe
de-identification of Canvas submission_comments before they enter the
grader's view).

scrub_comment(body, extra_names) returns (scrubbed_body, total_scrubs).
It runs name-aware (word-bounded) substitution for roster names + emails
+ user-paths, plus secret-prefix scrubbing.
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

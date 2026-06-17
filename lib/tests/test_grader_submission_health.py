"""Tier 1 unit tests — grader_submission_health::classify_submission.

Source: lib/tools/grader_submission_health.py (#64 — pre-grade submission
health audit that flags likely-empty uploads, unexpected content types,
empty text entries / URLs, and "submitted but nothing" cases).

Genuinely-unsubmitted (no submitted_at AND no content) returns [] — that's
not broken, it's just unsubmitted. Distinguish carefully from
'submitted_but_nothing' (submitted_at IS set but the payload is empty).
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_submission_health import classify_submission  # noqa: E402


# ---------------------------------------------------------------------------
# Genuinely-unsubmitted — clean (no flags)
# ---------------------------------------------------------------------------

def test_genuinely_unsubmitted_returns_empty_list():
    sub = {"submitted_at": None, "attachments": [], "body": "", "url": ""}
    assert classify_submission(sub, ["online_upload"]) == []


# ---------------------------------------------------------------------------
# Likely-empty upload (size < _NEAR_ZERO_BYTES = 100)
# ---------------------------------------------------------------------------

def test_likely_empty_upload_flagged():
    sub = {
        "submitted_at": "2026-06-17T00:00:00Z",
        "attachments": [{"size": 12, "content-type": "text/plain"}],
    }
    flags = classify_submission(sub, ["online_upload"])
    assert any("likely_empty_upload" in f for f in flags)


def test_normal_size_upload_not_flagged():
    sub = {
        "submitted_at": "2026-06-17T00:00:00Z",
        "attachments": [{"size": 50000, "content-type": "text/html"}],
    }
    flags = classify_submission(sub, ["online_upload"])
    assert not any("likely_empty_upload" in f for f in flags)


# ---------------------------------------------------------------------------
# Unexpected content type (.exe-class binaries when course wants documents)
# ---------------------------------------------------------------------------

def test_unexpected_content_type_flagged():
    sub = {
        "submitted_at": "2026-06-17T00:00:00Z",
        "attachments": [
            {"size": 50000, "content-type": "application/x-msdownload"},
        ],
    }
    flags = classify_submission(sub, ["online_upload"])
    assert any("unexpected_content_type" in f for f in flags)


# ---------------------------------------------------------------------------
# Empty text entry / URL
# ---------------------------------------------------------------------------

def test_empty_text_entry_flagged():
    sub = {
        "submitted_at": "2026-06-17T00:00:00Z",
        "submission_type": "online_text_entry",
        "body": "",
    }
    flags = classify_submission(sub, ["online_text_entry"])
    assert "empty_text_entry" in flags


def test_filled_text_entry_not_flagged():
    sub = {
        "submitted_at": "2026-06-17T00:00:00Z",
        "submission_type": "online_text_entry",
        "body": "Here is my response.",
    }
    flags = classify_submission(sub, ["online_text_entry"])
    assert "empty_text_entry" not in flags


def test_empty_url_flagged():
    sub = {
        "submitted_at": "2026-06-17T00:00:00Z",
        "submission_type": "online_url",
        "url": "",
    }
    flags = classify_submission(sub, ["online_url"])
    assert "empty_url" in flags


# ---------------------------------------------------------------------------
# "Submitted but nothing" — submitted_at set, all payload fields empty
# ---------------------------------------------------------------------------

def test_submitted_but_nothing_flagged():
    sub = {
        "submitted_at": "2026-06-17T00:00:00Z",
        "submission_type": None,
        "attachments": [],
        "body": "",
        "url": "",
    }
    flags = classify_submission(sub, ["online_upload"])
    assert "submitted_but_nothing" in flags


def test_submitted_but_nothing_not_double_flagged():
    """If a type-specific flag (empty_text_entry / empty_url / empty_upload)
    already caught the case, don't ALSO emit 'submitted_but_nothing'."""
    sub = {
        "submitted_at": "2026-06-17T00:00:00Z",
        "submission_type": "online_text_entry",
        "body": "",
    }
    flags = classify_submission(sub, ["online_text_entry"])
    assert "submitted_but_nothing" not in flags  # empty_text_entry covered it
    assert "empty_text_entry" in flags

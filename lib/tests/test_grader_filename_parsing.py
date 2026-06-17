"""Tier 1 unit tests — filename → user_id resolution.

Covers three pure-function helpers that all parse user_ids out of
submission filenames. They share regex DNA (#73 — three conventions:
grader_fetch / _external / Canvas bulk download) but live in two source
modules — keep them in sync.

Source modules:
  - lib/tools/grader_join.py::extract_uid
  - lib/tools/grader_meta_summary.py::_uid_from_filename
  - lib/tools/grader_meta_summary.py::_row_uid
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_join import extract_uid  # noqa: E402
from grader_meta_summary import _uid_from_filename, _row_uid  # noqa: E402


# ---------------------------------------------------------------------------
# extract_uid — returns (uid, is_external) | None
# ---------------------------------------------------------------------------

def test_extract_uid_grader_fetch_convention():
    """`<prefix>_<uid>.<ext>` — uid right before extension."""
    assert extract_uid("kc1_33619.html") == (33619, False)


def test_extract_uid_external_marker():
    """`<prefix>_<uid>_external.<ext>` — same uid; is_external=True."""
    assert extract_uid("kc1_33619_external.md") == (33619, True)


def test_extract_uid_canvas_bulk_download():
    """`lastfirst_<uid>_<subid>_<title>.ext` — uid is the first 3+ digit
    block flanked by underscores."""
    uid, is_external = extract_uid("smithj_33619_42_my-submission.docx")
    assert uid == 33619
    assert is_external is False  # bulk-download never marks external


def test_extract_uid_tolerates_whitespace():
    """The fetch regex tolerates `_ <uid>.ext` (operators occasionally
    paste a space)."""
    assert extract_uid("kc1_ 33619.html") == (33619, False)


def test_extract_uid_no_match_returns_none():
    assert extract_uid("README.md") is None
    assert extract_uid("kc1_abc.html") is None
    assert extract_uid("") is None


def test_extract_uid_empty_input():
    assert extract_uid(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _uid_from_filename — same conventions, returns int | None (no is_external)
# ---------------------------------------------------------------------------

def test_uid_from_filename_fetch_convention():
    assert _uid_from_filename("kc1_33619.html") == 33619


def test_uid_from_filename_external_strips_marker():
    assert _uid_from_filename("kc1_33619_external.md") == 33619


def test_uid_from_filename_bulk_download():
    assert _uid_from_filename("smithj_33619_42_my-submission.docx") == 33619


def test_uid_from_filename_no_match_returns_none():
    assert _uid_from_filename("README.md") is None
    assert _uid_from_filename("") is None


# Cross-check: the two helpers must agree on the uid for every filename
# convention they both recognize (issue #73 — keep them in sync).
def test_filename_helpers_agree_on_uid():
    fixtures = [
        "kc1_33619.html",
        "kc1_33619_external.md",
        "smithj_33619_42_my-submission.docx",
        "kc1_ 33619.html",
    ]
    for f in fixtures:
        a = extract_uid(f)
        b = _uid_from_filename(f)
        assert a is not None and b is not None, f
        assert a[0] == b, f"Disagreement on {f!r}: extract_uid→{a[0]} vs _uid_from_filename→{b}"


# ---------------------------------------------------------------------------
# _row_uid — score-CSV row → uid via key map, fall back to user_id column
# ---------------------------------------------------------------------------

def test_row_uid_key_lookup_wins():
    """`key`-keyed rows resolve via the keymap (the canonical path —
    grader_consensus / grader_grade output)."""
    keymap = {"KC1-A1B2C3": 33619}
    row = {"key": "KC1-A1B2C3", "user_id": ""}
    assert _row_uid(row, keymap) == 33619


def test_row_uid_user_id_fallback_for_multi_surface_synthesis():
    """Multi-surface synthesis CSVs (#70 / m119 `_combined/feedback/_grader1.csv`)
    are `user_id`-keyed. When `key` is missing/unmappable, fall back."""
    keymap = {}  # no key map
    row = {"key": "", "user_id": "33619"}
    assert _row_uid(row, keymap) == 33619


def test_row_uid_returns_none_when_neither_resolves():
    keymap = {}
    row = {"key": "", "user_id": ""}
    assert _row_uid(row, keymap) is None


def test_row_uid_returns_none_when_user_id_not_digit():
    keymap = {}
    row = {"key": "", "user_id": "not-a-number"}
    assert _row_uid(row, keymap) is None


def test_row_uid_unmapped_key_falls_back_to_user_id():
    """`key` is present but not in the keymap — fall back to user_id column
    rather than returning None outright."""
    keymap = {"DIFFERENT-KEY": 99999}
    row = {"key": "KC1-A1B2C3", "user_id": "33619"}
    assert _row_uid(row, keymap) == 33619

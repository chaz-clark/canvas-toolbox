"""Unit tests — grader_rubric checkability parser + freeze fingerprint (Stage 0, #192).

The whole hybrid pipeline routes on the per-criterion checkability tag, so parsing
the RUBRIC.md table correctly (and detecting a bad/missing one) is load-bearing. The
fingerprint is the "frozen rubric" marker — it must be stable under cosmetic edits
but change the instant a criterion's routing changes.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_rubric import (  # noqa: E402
    parse_checkability,
    checkability_fingerprint,
    CHECKABILITY,
)

RUBRIC = """# Some Assignment — Rubric

## Criteria

| # | Criterion | Checkability | What "Meets" looks like |
|---|-----------|--------------|--------------------------|
| 1 | **Includes a thesis** | mechanical | a claim is stated up front |
| 2 | Addresses all 5 prompts | coverage | every prompt answered |
| 3 | Demonstrates critical insight | judgment | goes beyond summary |

## Holistic banding

Score against the named band as a single judgment.
"""


def test_parses_criterion_and_tag_ignoring_extra_columns():
    rows, issues = parse_checkability(RUBRIC)
    assert issues == []
    assert [r["criterion"] for r in rows] == [
        "Includes a thesis", "Addresses all 5 prompts", "Demonstrates critical insight"]
    assert [r["checkability"] for r in rows] == ["mechanical", "coverage", "judgment"]
    # bold markup and the leading '#' / tier-descriptor columns are stripped/ignored
    assert all(r["checkability"] in CHECKABILITY for r in rows)


def test_stops_at_end_of_table():
    """Prose after the table (holistic banding) must not be parsed as rows."""
    rows, _ = parse_checkability(RUBRIC)
    assert len(rows) == 3


def test_missing_table_is_an_issue():
    rows, issues = parse_checkability("# Rubric\n\nNo table here, just prose.\n")
    assert rows == []
    assert issues and "Checkability" in issues[0]


def test_unknown_tag_is_flagged_not_silently_dropped():
    bad = ("| Criterion | Checkability |\n|---|---|\n"
           "| Good row | mechanical |\n| Bad row | vibes |\n")
    rows, issues = parse_checkability(bad)
    assert [r["criterion"] for r in rows] == ["Good row"]
    assert any("vibes" in it for it in issues)


def test_optional_evidence_hint_column():
    txt = ("| Criterion | Checkability | Evidence hint |\n|---|---|---|\n"
           "| ≥3 citations | mechanical | APA (Author, YEAR); target ≥3 |\n"
           "| Critical insight | judgment | — |\n")
    rows, issues = parse_checkability(txt)
    assert issues == []
    assert rows[0]["evidence_hint"] == "APA (Author, YEAR); target ≥3"
    assert rows[1]["evidence_hint"] is None  # an em-dash means "no hint"


# --- fingerprint (the freeze marker) ---------------------------------------

def test_fingerprint_is_stable_under_reordering():
    a = [{"criterion": "X", "checkability": "mechanical"},
         {"criterion": "Y", "checkability": "judgment"}]
    b = list(reversed(a))
    assert checkability_fingerprint(a) == checkability_fingerprint(b)


def test_fingerprint_changes_when_a_tag_changes():
    base = [{"criterion": "X", "checkability": "mechanical"}]
    moved = [{"criterion": "X", "checkability": "judgment"}]
    assert checkability_fingerprint(base) != checkability_fingerprint(moved)


def test_fingerprint_changes_when_a_criterion_is_added():
    one = [{"criterion": "X", "checkability": "coverage"}]
    two = one + [{"criterion": "Y", "checkability": "coverage"}]
    assert checkability_fingerprint(one) != checkability_fingerprint(two)

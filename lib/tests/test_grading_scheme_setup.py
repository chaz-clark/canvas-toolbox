"""Unit tests — grading scheme creation (#302).

The dangerous failure here is not "refused to create" — it's a scheme Canvas
ACCEPTS and then renders wrong. A gap under the lowest tier leaves scores with no
letter at all, and an out-of-order scale silently reassigns every grade in the
course. So the validation cases carry more weight than the happy path.
"""
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grading_scheme_setup import (  # noqa: E402
    entries_match,
    parse_tiers,
    validate_tiers,
)

_TIERS = "Leading:90,Strong:80,Solid:70,Building:60,Insufficient:0"


# --- parsing ----------------------------------------------------------------

def test_parses_name_and_lower_bound():
    t = parse_tiers(_TIERS)
    assert [x["name"] for x in t] == ["Leading", "Strong", "Solid", "Building",
                                      "Insufficient"]
    assert [x["percent"] for x in t] == [90, 80, 70, 60, 0]


def test_tier_names_may_contain_a_colon():
    """rpartition on the LAST colon, so "Tier A: Leading:90" keeps its label."""
    assert parse_tiers("Tier A: Leading:90,Rest:0")[0]["name"] == "Tier A: Leading"


def test_whitespace_and_trailing_commas_are_tolerated():
    assert len(parse_tiers(" Pass:60 , Fail:0 ,")) == 2


@pytest.mark.parametrize("spec, fragment", [
    ("", "no tiers"),
    ("Leading", "expected NAME:PERCENT"),
    (":90,Rest:0", "missing tier name"),
    ("Leading:high,Rest:0", "not a number"),
])
def test_malformed_specs_are_refused(spec, fragment):
    with pytest.raises(ValueError, match=fragment):
        parse_tiers(spec)


# --- validation (the ones that matter) --------------------------------------

def test_a_well_formed_scale_passes():
    validate_tiers(parse_tiers(_TIERS))


def test_scale_not_reaching_zero_is_refused():
    """Canvas accepts this and then has no letter for 0-59%, which renders blank
    in the gradebook rather than failing loudly."""
    with pytest.raises(ValueError, match="lowest tier must start at 0"):
        validate_tiers(parse_tiers("Leading:90,Strong:80,Building:60"))


def test_ascending_scale_is_refused():
    """Listed low-to-high, every tier boundary lands on the wrong letter."""
    with pytest.raises(ValueError, match="high to low"):
        validate_tiers(parse_tiers("Insufficient:0,Solid:70,Leading:90"))


def test_repeated_bound_is_refused():
    with pytest.raises(ValueError, match="high to low"):
        validate_tiers(parse_tiers("Leading:90,Strong:90,Rest:0"))


def test_duplicate_names_are_refused():
    with pytest.raises(ValueError, match="duplicate tier name"):
        validate_tiers(parse_tiers("Pass:90,Pass:60,Fail:0"))


@pytest.mark.parametrize("spec", ["Over:101,Rest:0", "Under:-5,Rest:0"])
def test_bounds_outside_zero_to_hundred_are_refused(spec):
    with pytest.raises(ValueError, match="outside 0-100"):
        validate_tiers(parse_tiers(spec))


def test_a_two_tier_pass_fail_scale_is_valid():
    """Specifications grading is a legitimate shape, not an error."""
    validate_tiers(parse_tiers("Pass:80,Fail:0"))


# --- read-back comparison ---------------------------------------------------

def _canvas_echo(*pairs):
    return {"grading_scheme_entry": [{"name": n, "value": v} for n, v in pairs]}


def test_read_back_matches_when_canvas_echoes_fractions():
    """Percent goes out, fraction comes back — the comparison has to convert."""
    assert entries_match(_canvas_echo(("Pass", 0.8), ("Fail", 0.0)),
                         parse_tiers("Pass:80,Fail:0"))


def test_read_back_tolerates_canvas_rounding():
    assert entries_match(_canvas_echo(("Pass", 0.80001), ("Fail", 0.0)),
                         parse_tiers("Pass:80,Fail:0"))


def test_read_back_detects_a_changed_bound():
    """The failure this guards: Canvas answers 200, stores something else."""
    assert not entries_match(_canvas_echo(("Pass", 0.7), ("Fail", 0.0)),
                             parse_tiers("Pass:80,Fail:0"))


def test_read_back_detects_a_dropped_tier():
    assert not entries_match(_canvas_echo(("Pass", 0.8)),
                             parse_tiers("Pass:80,Fail:0"))


def test_read_back_detects_a_renamed_tier():
    assert not entries_match(_canvas_echo(("Passing", 0.8), ("Fail", 0.0)),
                             parse_tiers("Pass:80,Fail:0"))


def test_read_back_of_an_empty_response_is_not_a_match():
    """A create that silently did nothing must not read as success."""
    assert not entries_match({}, parse_tiers("Pass:80,Fail:0"))

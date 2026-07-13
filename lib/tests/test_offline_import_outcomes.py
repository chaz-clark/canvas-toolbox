"""Tier 1 — offline_import.parse_learning_outcomes.

Canvas exports course-OWNED outcomes into course_settings/learning_outcomes.xml;
this parser turns them into canvas_sync's _outcomes.json shape so the loader +
CLO/alignment audits read a .imscc source and an API pull identically.
"""
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import offline_import as O  # noqa: E402

_XML = """<?xml version="1.0"?>
<learningOutcomes xmlns="http://canvas.instructure.com/xsd/cccv1p0">
  <learningOutcome identifier="g126">
    <title>DS250 CLO 1</title>
    <description>Use functions &amp; data structures.</description>
    <calculation_method>standard_decaying_average</calculation_method>
  </learningOutcome>
  <learningOutcome identifier="g0e1">
    <title>DS250 CLO 2</title>
    <description>Load data.</description>
  </learningOutcome>
</learningOutcomes>"""


def test_parse_shape_and_entity_unescape():
    got = O.parse_learning_outcomes(_XML)
    assert len(got) == 2
    assert got[0] == {
        "id": "g126", "title": "DS250 CLO 1",
        "description": "Use functions & data structures.",  # &amp; unescaped
        "display_name": "DS250 CLO 1",
    }
    assert got[1]["title"] == "DS250 CLO 2"


def test_parse_empty_or_absent():
    assert O.parse_learning_outcomes("") == []
    assert O.parse_learning_outcomes(None) == []

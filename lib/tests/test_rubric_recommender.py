"""
Unit tests for rubric_recommender.py

Tests the YAML teaching sheet generation (Feature 3 - NGAI Integration).
"""

import sys
from pathlib import Path

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from rubric_recommender import _to_yaml_teaching_sheet


def test_yaml_teaching_sheet_structure():
    """YAML teaching sheet should have correct top-level structure"""
    recs = [
        {
            "assignment_id": 123,
            "assignment_name": "Test Assignment",
            "assignment_bloom": "analyze",
            "points_possible": 100,
            "matched_clo_count": 2,
            "source": "criteria derived from matched course outcomes (alignment built in)",
            "rubric": {
                "title": "Recommended rubric — Test Assignment",
                "criteria": [
                    {
                        "description": "Analyze data patterns",
                        "long_description": "Student analyzes data patterns using appropriate methods.",
                        "points": 50,
                        "clo_bloom": "analyze",
                        "ratings": [
                            {"description": "Exemplary", "long_description": "Exceeds expectations", "points": 50},
                            {"description": "Proficient", "long_description": "Meets expectations", "points": 37.5},
                            {"description": "Developing", "long_description": "Partially meets", "points": 25},
                            {"description": "Beginning", "long_description": "Does not meet", "points": 0},
                        ]
                    }
                ]
            },
            "notes": ["Scaffold only — refine for context"]
        }
    ]

    yaml_output = _to_yaml_teaching_sheet("12345", "Test Course", recs, 5, "2026-06-29 12:00 UTC")
    data = yaml.safe_load(yaml_output)

    assert data["tool"] == "rubric_recommender"
    assert data["format"] == "teaching_sheet"
    assert data["run_at"] == "2026-06-29 12:00 UTC"
    assert data["course"]["id"] == "12345"
    assert data["course"]["name"] == "Test Course"
    assert data["outcomes_available"] == 5
    assert "teaching_sheets" in data
    assert len(data["teaching_sheets"]) == 1


def test_yaml_teaching_sheet_content():
    """YAML teaching sheet should preserve assignment and criteria content"""
    recs = [
        {
            "assignment_id": 456,
            "assignment_name": "Data Analysis Task",
            "assignment_bloom": "evaluate",
            "points_possible": 80,
            "matched_clo_count": 3,
            "source": "criteria derived from matched course outcomes (alignment built in)",
            "rubric": {
                "title": "Recommended rubric — Data Analysis Task",
                "criteria": [
                    {
                        "description": "Evaluate statistical methods",
                        "long_description": "Evaluates the appropriateness of statistical methods for the given data.",
                        "points": 40,
                        "clo_bloom": "evaluate",
                        "ratings": [
                            {"description": "Exemplary", "long_description": "Sophisticated evaluation", "points": 40},
                            {"description": "Proficient", "long_description": "Sound evaluation", "points": 30},
                        ]
                    },
                    {
                        "description": "Analyze trends",
                        "long_description": "Identifies and analyzes key trends in the dataset.",
                        "points": 40,
                        "clo_bloom": "analyze",
                        "ratings": [
                            {"description": "Exemplary", "long_description": "Comprehensive analysis", "points": 40},
                            {"description": "Proficient", "long_description": "Adequate analysis", "points": 30},
                        ]
                    }
                ]
            },
            "notes": ["Note 1", "Note 2"]
        }
    ]

    yaml_output = _to_yaml_teaching_sheet("67890", "Advanced Analytics", recs, 8, "2026-06-29 12:00 UTC")
    data = yaml.safe_load(yaml_output)

    sheet = data["teaching_sheets"][0]
    assert sheet["assignment_id"] == 456
    assert sheet["assignment_name"] == "Data Analysis Task"
    assert sheet["bloom_level"] == "evaluate"
    assert sheet["points_possible"] == 80
    assert sheet["matched_clo_count"] == 3
    assert sheet["source"] == "criteria derived from matched course outcomes (alignment built in)"
    assert len(sheet["evaluation_criteria"]) == 2
    assert sheet["notes"] == ["Note 1", "Note 2"]


def test_yaml_teaching_sheet_criteria_levels():
    """YAML teaching sheet should correctly format evaluation criteria and levels"""
    recs = [
        {
            "assignment_id": 789,
            "assignment_name": "Essay",
            "assignment_bloom": "create",
            "points_possible": 100,
            "matched_clo_count": 1,
            "source": "criteria derived from matched course outcomes (alignment built in)",
            "rubric": {
                "title": "Recommended rubric — Essay",
                "criteria": [
                    {
                        "description": "Create a coherent argument",
                        "long_description": "Constructs a well-reasoned, evidence-based argument.",
                        "points": 100,
                        "clo_bloom": "create",
                        "ratings": [
                            {"description": "Exemplary", "long_description": "Exceptional argument with novel insights", "points": 100},
                            {"description": "Proficient", "long_description": "Solid argument with adequate support", "points": 75},
                            {"description": "Developing", "long_description": "Argument present but weak support", "points": 50},
                            {"description": "Beginning", "long_description": "No coherent argument", "points": 0},
                        ]
                    }
                ]
            },
            "notes": []
        }
    ]

    yaml_output = _to_yaml_teaching_sheet("11111", "Writing Course", recs, 4, "2026-06-29 12:00 UTC")
    data = yaml.safe_load(yaml_output)

    criterion = data["teaching_sheets"][0]["evaluation_criteria"][0]
    assert criterion["criterion"] == "Create a coherent argument"
    assert criterion["description"] == "Constructs a well-reasoned, evidence-based argument."
    assert criterion["points"] == 100
    assert criterion["clo_bloom"] == "create"
    assert len(criterion["levels"]) == 4

    # Check first level
    assert criterion["levels"][0]["rating"] == "Exemplary"
    assert criterion["levels"][0]["points"] == 100
    assert criterion["levels"][0]["description"] == "Exceptional argument with novel insights"

    # Check last level
    assert criterion["levels"][3]["rating"] == "Beginning"
    assert criterion["levels"][3]["points"] == 0
    assert criterion["levels"][3]["description"] == "No coherent argument"


def test_yaml_teaching_sheet_multiple_assignments():
    """YAML teaching sheet should handle multiple assignments"""
    recs = [
        {
            "assignment_id": 1,
            "assignment_name": "Assignment 1",
            "assignment_bloom": "apply",
            "points_possible": 50,
            "matched_clo_count": 1,
            "source": "criteria derived from matched course outcomes (alignment built in)",
            "rubric": {
                "title": "Rubric 1",
                "criteria": [
                    {
                        "description": "Criterion 1",
                        "long_description": "Description 1",
                        "points": 50,
                        "clo_bloom": "apply",
                        "ratings": [
                            {"description": "High", "long_description": "High desc", "points": 50},
                            {"description": "Low", "long_description": "Low desc", "points": 0},
                        ]
                    }
                ]
            },
            "notes": []
        },
        {
            "assignment_id": 2,
            "assignment_name": "Assignment 2",
            "assignment_bloom": "analyze",
            "points_possible": 75,
            "matched_clo_count": 2,
            "source": "criteria derived from matched course outcomes (alignment built in)",
            "rubric": {
                "title": "Rubric 2",
                "criteria": [
                    {
                        "description": "Criterion 2",
                        "long_description": "Description 2",
                        "points": 75,
                        "clo_bloom": "analyze",
                        "ratings": [
                            {"description": "High", "long_description": "High desc", "points": 75},
                            {"description": "Low", "long_description": "Low desc", "points": 0},
                        ]
                    }
                ]
            },
            "notes": []
        }
    ]

    yaml_output = _to_yaml_teaching_sheet("22222", "Multi Course", recs, 6, "2026-06-29 12:00 UTC")
    data = yaml.safe_load(yaml_output)

    assert len(data["teaching_sheets"]) == 2
    assert data["teaching_sheets"][0]["assignment_id"] == 1
    assert data["teaching_sheets"][1]["assignment_id"] == 2


def test_yaml_teaching_sheet_no_clo_bloom():
    """YAML teaching sheet should handle missing clo_bloom gracefully"""
    recs = [
        {
            "assignment_id": 999,
            "assignment_name": "Generic Assignment",
            "assignment_bloom": None,
            "points_possible": 100,
            "matched_clo_count": 0,
            "source": "generic scaffold (no CLO matched)",
            "rubric": {
                "title": "Generic Rubric",
                "criteria": [
                    {
                        "description": "Generic criterion",
                        "long_description": "GENERIC scaffold",
                        "points": 100,
                        # clo_bloom may be missing
                        "ratings": [
                            {"description": "Exemplary", "long_description": "High", "points": 100},
                            {"description": "Beginning", "long_description": "Low", "points": 0},
                        ]
                    }
                ]
            },
            "notes": ["No CLO match"]
        }
    ]

    yaml_output = _to_yaml_teaching_sheet("33333", "Test", recs, 0, "2026-06-29 12:00 UTC")
    data = yaml.safe_load(yaml_output)

    sheet = data["teaching_sheets"][0]
    assert sheet["bloom_level"] is None
    assert sheet["matched_clo_count"] == 0

    criterion = sheet["evaluation_criteria"][0]
    assert criterion["clo_bloom"] is None or "clo_bloom" in criterion


if __name__ == "__main__":
    # Run tests
    test_yaml_teaching_sheet_structure()
    test_yaml_teaching_sheet_content()
    test_yaml_teaching_sheet_criteria_levels()
    test_yaml_teaching_sheet_multiple_assignments()
    test_yaml_teaching_sheet_no_clo_bloom()
    print("✅ All Feature 3 unit tests passed")

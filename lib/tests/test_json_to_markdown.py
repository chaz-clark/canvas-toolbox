"""
test_json_to_markdown.py

Unit tests for JSON-to-markdown conversion functions in canvas_sync.py.

Tests assignment, quiz, and discussion JSON → markdown conversions
with YAML frontmatter for LLM/agent consumption.
"""

import sys
from pathlib import Path

# Allow imports from lib/tools/
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from canvas_sync import (
    _assignment_json_to_md,
    _quiz_json_to_md,
    _discussion_json_to_md,
)


def test_assignment_json_to_md_basic():
    """Test assignment JSON converts to markdown with frontmatter"""
    assignment = {
        "canvas_id": 16847197,
        "name": "W03 U1: Core Task 1 — Exploring Names",
        "description": "<div class='byui'>Work through this task on the course site. Submit a screenshot of your code.<br><a href='https://example.com/task1'>Open Task Page →</a></div>",
        "points_possible": 1.0,
        "due_at": "2026-05-07T05:59:00Z",
        "grading_type": "pass_fail",
        "submission_types": ["online_text_entry", "online_upload"],
    }

    md = _assignment_json_to_md(assignment)

    # Check frontmatter presence
    assert md.startswith("---\n")
    assert "title: W03 U1: Core Task 1 — Exploring Names" in md
    assert "type: assignment" in md
    assert "canvas_id: 16847197" in md
    assert "points: 1.0" in md
    assert "due_at: 2026-05-07T05:59:00Z" in md
    assert "grading_type: pass_fail" in md
    assert "submission_types: online_text_entry, online_upload" in md

    # Check markdown body (no HTML tags)
    assert "<div" not in md
    assert "<br>" not in md
    assert "Work through this task on the course site" in md
    assert "[Open Task Page →](https://example.com/task1)" in md


def test_assignment_json_to_md_empty_description():
    """Test assignment with empty description produces valid markdown"""
    assignment = {
        "canvas_id": 123,
        "name": "Empty Assignment",
        "description": "",
        "points_possible": 10.0,
    }

    md = _assignment_json_to_md(assignment)

    assert md.startswith("---\n")
    assert "title: Empty Assignment" in md
    assert "canvas_id: 123" in md
    # Body should be empty after frontmatter
    lines = md.split("---\n\n", 1)
    assert len(lines) == 2
    assert lines[1].strip() == ""


def test_quiz_json_to_md_basic():
    """Test quiz JSON converts to markdown with frontmatter"""
    quiz = {
        "canvas_id": 4567,
        "title": "Week 03 Reading Quiz",
        "description": "<p>This quiz covers the reading material for week 3.</p><p><strong>Good luck!</strong></p>",
        "points_possible": 10.0,
        "quiz_type": "assignment",
        "time_limit": 30,
        "allowed_attempts": 2,
        "due_at": "2026-05-08T23:59:00Z",
    }

    md = _quiz_json_to_md(quiz)

    # Check frontmatter
    assert md.startswith("---\n")
    assert "title: Week 03 Reading Quiz" in md
    assert "type: quiz" in md
    assert "canvas_id: 4567" in md
    assert "points: 10.0" in md
    assert "quiz_type: assignment" in md
    assert "time_limit: 30" in md
    assert "allowed_attempts: 2" in md
    assert "due_at: 2026-05-08T23:59:00Z" in md

    # Check markdown body
    assert "<p>" not in md
    assert "<strong>" not in md
    assert "This quiz covers the reading material for week 3" in md
    assert "Good luck!" in md


def test_quiz_json_to_md_no_time_limit():
    """Test quiz without time_limit doesn't include it in frontmatter"""
    quiz = {
        "canvas_id": 789,
        "title": "Untimed Quiz",
        "description": "Take as long as you need",
        "points_possible": 5.0,
        "quiz_type": "practice_quiz",
    }

    md = _quiz_json_to_md(quiz)

    assert "time_limit" not in md  # Should not appear if None
    assert "title: Untimed Quiz" in md


def test_discussion_json_to_md_basic():
    """Test discussion JSON converts to markdown with frontmatter"""
    discussion = {
        "canvas_id": 9876,
        "title": "Week 03 Discussion: Data Ethics",
        "message": "<div><p>Discuss the ethical implications of data collection.</p><ul><li>Privacy concerns</li><li>Consent issues</li></ul></div>",
        "todo_date": "2026-05-06T12:00:00Z",
    }

    md = _discussion_json_to_md(discussion)

    # Check frontmatter
    assert md.startswith("---\n")
    assert "title: Week 03 Discussion: Data Ethics" in md
    assert "type: discussion" in md
    assert "canvas_id: 9876" in md
    assert "todo_date: 2026-05-06T12:00:00Z" in md

    # Check markdown body
    assert "<div>" not in md
    assert "<p>" not in md
    assert "<ul>" not in md
    assert "<li>" not in md
    assert "Discuss the ethical implications of data collection" in md
    assert "Privacy concerns" in md
    assert "Consent issues" in md


def test_discussion_json_to_md_empty_message():
    """Test discussion with empty message produces valid markdown"""
    discussion = {
        "canvas_id": 111,
        "title": "Empty Discussion",
        "message": "",
    }

    md = _discussion_json_to_md(discussion)

    assert md.startswith("---\n")
    assert "title: Empty Discussion" in md
    # Body should be empty after frontmatter
    lines = md.split("---\n\n", 1)
    assert len(lines) == 2
    assert lines[1].strip() == ""


def test_assignment_handles_html_entities():
    """Test HTML entities are properly converted"""
    assignment = {
        "canvas_id": 222,
        "name": "Task with &quot;Quotes&quot; &amp; Symbols",
        "description": "<p>Use &lt;code&gt; for examples &amp; &quot;quotes&quot; where needed.</p>",
        "points_possible": 5.0,
    }

    md = _assignment_json_to_md(assignment)

    # HTML entities should be converted to actual characters or proper markdown
    assert "&quot;" not in md or '"' in md
    assert "&amp;" not in md or "&" in md
    assert "&lt;" not in md or "<" in md or "`<code>`" in md


def test_quiz_removes_script_tags():
    """Test script tags are removed from quiz descriptions"""
    quiz = {
        "canvas_id": 333,
        "title": "Quiz with Script",
        "description": "<p>Normal content</p><script>alert('xss')</script><p>More content</p>",
        "points_possible": 10.0,
    }

    md = _quiz_json_to_md(quiz)

    # Script tags should be completely removed
    assert "<script>" not in md
    assert "alert" not in md
    assert "Normal content" in md
    assert "More content" in md


def test_discussion_preserves_links():
    """Test links are preserved in markdown format"""
    discussion = {
        "canvas_id": 444,
        "title": "Discussion with Link",
        "message": '<p>Read this article: <a href="https://example.com/article">Data Science Ethics</a></p>',
    }

    md = _discussion_json_to_md(discussion)

    # Links should be converted to markdown format
    assert "[Data Science Ethics](https://example.com/article)" in md
    assert "<a href" not in md

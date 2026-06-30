"""
Unit tests for content_fetch.py

Tests the solution filtering logic (Feature 1 - NGAI Integration).
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from content_fetch import filter_solution_markers


def test_filter_html_comment_blocks():
    """Should remove <!-- SOLUTION -->...<!-- /SOLUTION --> blocks"""
    html = """
    <p>This is visible content.</p>
    <!-- SOLUTION -->
    <p>This is the answer key that students should not see.</p>
    <!-- /SOLUTION -->
    <p>More visible content.</p>
    """

    filtered, removed = filter_solution_markers(html)

    assert "This is visible content" in filtered
    assert "More visible content" in filtered
    assert "answer key" not in filtered
    assert len(removed) == 1
    assert "HTML comment block" in removed[0]


def test_filter_data_solution_attribute():
    """Should remove elements with data-solution attribute"""
    html = """
    <div>
        <p>Question: What is 2+2?</p>
        <div data-solution="true">
            <p>Answer: 4</p>
        </div>
        <p>Next question...</p>
    </div>
    """

    filtered, removed = filter_solution_markers(html)

    assert "Question: What is 2+2?" in filtered
    assert "Next question" in filtered
    assert "Answer: 4" not in filtered
    assert len(removed) == 1
    assert "data-solution element" in removed[0]


def test_filter_solution_class():
    """Should remove elements with solution/answer-key classes"""
    html = """
    <div>
        <p>Problem statement</p>
        <div class="solution">
            <h3>Solution</h3>
            <p>Step 1: ...</p>
            <p>Step 2: ...</p>
        </div>
        <p>Another problem</p>
    </div>
    """

    filtered, removed = filter_solution_markers(html)

    assert "Problem statement" in filtered
    assert "Another problem" in filtered
    assert "Step 1" not in filtered
    assert "Step 2" not in filtered
    assert len(removed) == 1
    assert "solution class element" in removed[0]


def test_filter_answer_key_class():
    """Should remove elements with answer-key class"""
    html = """
    <section>
        <h2>Exercise 1</h2>
        <p>Solve for x.</p>
        <section class="answer-key">
            <p>x = 42</p>
        </section>
    </section>
    """

    filtered, removed = filter_solution_markers(html)

    assert "Exercise 1" in filtered
    assert "Solve for x" in filtered
    assert "x = 42" not in filtered
    assert len(removed) == 1


def test_filter_heading_delimited_solution():
    """Should remove content after 'Solution' or 'Answer Key' headings"""
    html = """
    <div>
        <h2>Problem 1</h2>
        <p>What is the capital of France?</p>
        <h2>Solution</h2>
        <p>The capital of France is Paris.</p>
        <p>Additional info about Paris...</p>
        <h2>Problem 2</h2>
        <p>What is the capital of Germany?</p>
    </div>
    """

    filtered, removed = filter_solution_markers(html)

    assert "Problem 1" in filtered
    assert "What is the capital of France?" in filtered
    assert "Problem 2" in filtered
    assert "What is the capital of Germany?" in filtered
    assert "capital of France is Paris" not in filtered
    assert "Additional info about Paris" not in filtered
    assert len(removed) >= 1
    assert any("heading-delimited" in r for r in removed)


def test_filter_answer_key_heading():
    """Should remove content after 'Answer Key' heading"""
    html = """
    <div>
        <h3>Questions</h3>
        <p>Q1: ...</p>
        <p>Q2: ...</p>
        <h3>Answer Key</h3>
        <p>A1: ...</p>
        <p>A2: ...</p>
    </div>
    """

    filtered, removed = filter_solution_markers(html)

    assert "Questions" in filtered
    assert "Q1" in filtered
    assert "Q2" in filtered
    assert "A1" not in filtered
    assert "A2" not in filtered


def test_filter_multiple_markers():
    """Should handle multiple solution markers in same document"""
    html = """
    <div>
        <p>Problem 1</p>
        <!-- SOLUTION -->
        <p>Answer 1</p>
        <!-- /SOLUTION -->
        <p>Problem 2</p>
        <div data-solution="true">
            <p>Answer 2</p>
        </div>
        <p>Problem 3</p>
        <div class="solution">
            <p>Answer 3</p>
        </div>
    </div>
    """

    filtered, removed = filter_solution_markers(html)

    assert "Problem 1" in filtered
    assert "Problem 2" in filtered
    assert "Problem 3" in filtered
    assert "Answer 1" not in filtered
    assert "Answer 2" not in filtered
    assert "Answer 3" not in filtered
    assert len(removed) == 3


def test_filter_preserves_non_solution_content():
    """Should preserve all non-solution content exactly"""
    html = """
    <div>
        <h1>Course Material</h1>
        <p>This is important content for students.</p>
        <ul>
            <li>Point 1</li>
            <li>Point 2</li>
        </ul>
        <img src="diagram.png" alt="Diagram" />
    </div>
    """

    filtered, removed = filter_solution_markers(html)

    assert "Course Material" in filtered
    assert "important content" in filtered
    assert "Point 1" in filtered
    assert "Point 2" in filtered
    assert "diagram.png" in filtered
    assert len(removed) == 0


def test_filter_empty_html():
    """Should handle empty HTML gracefully"""
    html = ""
    filtered, removed = filter_solution_markers(html)
    assert filtered == ""
    assert removed == []


def test_filter_no_markers():
    """Should handle HTML with no solution markers"""
    html = "<p>Normal content without solutions.</p>"
    filtered, removed = filter_solution_markers(html)
    assert "Normal content" in filtered
    assert len(removed) == 0


def test_filter_case_insensitive():
    """Solution markers should be case-insensitive"""
    html = """
    <div>
        <h2>SOLUTION</h2>
        <p>Answer here</p>
    </div>
    """

    filtered, removed = filter_solution_markers(html)
    assert "Answer here" not in filtered
    assert len(removed) >= 1


def test_filter_nested_solution_markers():
    """Should handle nested solution markers"""
    html = """
    <div>
        <p>Question</p>
        <div class="solution">
            <div data-solution="true">
                <p>Nested answer</p>
            </div>
        </div>
    </div>
    """

    filtered, removed = filter_solution_markers(html)
    assert "Question" in filtered
    assert "Nested answer" not in filtered


def test_filter_partial_heading_match():
    """Should match headings containing solution/answer keywords"""
    html = """
    <div>
        <h2>Problem</h2>
        <p>Statement</p>
        <h2>Solution Approach</h2>
        <p>Should be removed</p>
        <h2>Answer Discussion</h2>
        <p>Also removed</p>
    </div>
    """

    filtered, removed = filter_solution_markers(html)
    assert "Problem" in filtered
    assert "Statement" in filtered
    assert "Should be removed" not in filtered
    assert "Also removed" not in filtered


if __name__ == "__main__":
    # Run tests
    test_filter_html_comment_blocks()
    test_filter_data_solution_attribute()
    test_filter_solution_class()
    test_filter_answer_key_class()
    test_filter_heading_delimited_solution()
    test_filter_answer_key_heading()
    test_filter_multiple_markers()
    test_filter_preserves_non_solution_content()
    test_filter_empty_html()
    test_filter_no_markers()
    test_filter_case_insensitive()
    test_filter_nested_solution_markers()
    test_filter_partial_heading_match()
    print("✅ All Feature 1 unit tests passed")

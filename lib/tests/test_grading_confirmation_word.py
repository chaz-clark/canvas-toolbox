"""Guard — the phrase an instructor types to confirm a grading write (#483).

Each sanctioned grading writer asks the instructor to type `update canvas` at an
interactive terminal before it writes (HG-5). It was `push` until 2.12.4; the
instructor's own words for this are "update Canvas", not "push". This pins the
phrase and the number of gates per writer, so a reword can't silently drop a
gate or bring the old word back.
"""
import ast
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
WORD = "update canvas"

# writer -> number of typed-confirmation gates
EXPECTED = {
    "grader_push.py": 3,           # roster comment-only, --test-user, main run
    "grader_push_comments.py": 1,
    "grader_standing.py": 1,
    "grader_correct.py": 1,
    "grader_letter_comments.py": 1,
}


def confirmation_gates(source: str, word: str = WORD) -> int:
    """Comparisons against `word`, plus require_typed_confirmation(_, word) calls."""
    def is_word(node):
        return isinstance(node, ast.Constant) and node.value == word
    n = 0
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare) and any(is_word(c) for c in node.comparators):
            n += 1
        elif (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "require_typed_confirmation"
              and len(node.args) == 2 and is_word(node.args[1])):
            n += 1
    return n


def _src(f):
    return (TOOLS / f).read_text(encoding="utf-8")


def test_each_grading_writer_asks_the_instructor_to_type_update_canvas():
    assert {f: confirmation_gates(_src(f)) for f in EXPECTED} == EXPECTED


def test_no_gate_still_expects_the_old_word():
    assert {f: confirmation_gates(_src(f), "push") for f in EXPECTED} == dict.fromkeys(EXPECTED, 0)


def test_the_prompt_names_the_phrase_to_type():
    for f in EXPECTED:
        assert f"Type '{WORD}'" in _src(f), f

"""Guard — the word an instructor types to confirm a grading write stays `push` (#483).

#483 rewords grading messages from "push" to "update grades in Canvas", but
the typed confirmation word is the instructor's own review gate (HG-5): the
behaviour must stay byte-for-byte the same. Renaming the messages must never
change what the instructor types, or how many writers ask for it.

Counts every comparison or require_typed_confirmation() call whose expected
word is the string "push", per sanctioned grading writer.
"""
import ast
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"

# writer -> number of typed-confirmation gates expecting "push"
EXPECTED = {
    "grader_push.py": 3,           # roster comment-only, --test-user, main run
    "grader_push_comments.py": 1,
    "grader_standing.py": 1,
    "grader_correct.py": 1,
    "grader_letter_comments.py": 1,
}


def _is_push(node) -> bool:
    return isinstance(node, ast.Constant) and node.value == "push"


def confirmation_gates(source: str) -> int:
    n = 0
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare) and any(_is_push(c) for c in node.comparators):
            n += 1
        elif (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "require_typed_confirmation"
              and len(node.args) == 2 and _is_push(node.args[1])):
            n += 1
    return n


def test_each_grading_writer_still_asks_the_instructor_to_type_push():
    found = {f: confirmation_gates((TOOLS / f).read_text(encoding="utf-8")) for f in EXPECTED}
    assert found == EXPECTED


def test_the_prompt_still_names_the_word_to_type():
    for f in EXPECTED:
        assert "Type 'push'" in (TOOLS / f).read_text(encoding="utf-8"), f

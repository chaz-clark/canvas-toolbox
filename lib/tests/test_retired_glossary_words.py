"""Guard — tool strings must not bring back words the glossary retired (#479).

knowledge/glossary.md gives each concept one word and lists the rest under
_Avoid_. The toolkit is renaming its own messages one PR at a time (#480-#483);
without this guard a new tool or message can bring a retired word back the day
after it was removed.

What is scanned: every string literal in lib/tools/*.py except docstrings.
Not only print() arguments: a refusal the guardian RETURNS, a gate message kept
in a constant, and a typed confirmation prompt all reach the user too.
Identifiers (grader_push.py, --push, load_zone2) and the .claude/ferpa_zone2.txt
filename are out of scope; #480 and #483 decide those.

ALLOWLIST is today's count per (tool, word). A new use fails. A rename that
removes uses must lower its count in the same PR, so the list can't go stale.
Some uses are meant to stay (a regex parsing an old log line, a typed
confirmation word); they stay in the list.
"""
import ast
import re
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS = REPO_ROOT / "lib" / "tools"
GLOSSARY = REPO_ROOT / "knowledge" / "glossary.md"

# Retired word -> (pattern, the glossary term to use instead).
RETIRED = {
    "Zone 1": (re.compile(r"\bzone[ -]?1\b", re.I), "AI-readable"),
    "Zone 2": (re.compile(r"\bzone[ -]?2\b", re.I), "local only"),
    "course repo": (re.compile(r"\bcourse repo", re.I), "course folder"),
    # A Canvas write. "git push", "pre-push" and the --push flag are git or
    # identifiers, not the retired word.
    "push": (re.compile(r"(?<!git )(?<!pre-)(?<!--)\bpush(?:ed|es|ing)?\b", re.I),
             'update Canvas / update grades in Canvas (write "git push" when it is git)'),
}

# Today's uses, per (tool, word). Lower a count when a rename removes uses;
# never raise one to make a new use pass.
ALLOWLIST = {
    ('_env_loader.py', 'push'): 1,
    ('blueprint_exception_report.py', 'push'): 2,
    ('blueprint_sync.py', 'push'): 4,
    ('canvas_quiz_questions.py', 'push'): 1,
    ('canvas_sync.py', 'push'): 23,
    ('cb_flatten.py', 'push'): 1,
    ('cb_secure_token.py', 'course repo'): 1,
    ('cb_update.py', 'course repo'): 7,
    ('cb_update.py', 'push'): 1,
    ('course_homepage_build.py', 'push'): 4,
    ('course_mirror.py', 'push'): 3,
    ('course_quality_check.py', 'push'): 2,
    ('ferpa_pre_push.py', 'push'): 4,
    ('grade_guardian.py', 'course repo'): 1,
    ('grade_guardian.py', 'push'): 4,
    ('grader_consensus.py', 'push'): 3,
    ('grader_correct.py', 'push'): 4,
    ('grader_export.py', 'push'): 1,
    ('grader_fetch.py', 'push'): 3,
    ('grader_fetch_resubmissions.py', 'push'): 1,
    ('grader_letter_comments.py', 'push'): 3,
    ('grader_push.py', 'push'): 51,
    ('grader_push_comments.py', 'push'): 11,
    ('grader_standing.py', 'push'): 8,
    ('merge_cleanup.py', 'course repo'): 1,
    ('merge_cleanup.py', 'push'): 3,
    ('sandbox_new_quiz_fixtures.py', 'push'): 1,
    ('sync_grading_protocol.py', 'course repo'): 1,
    ('sync_grading_protocol.py', 'push'): 1,
}


def _docstring_nodes(tree: ast.AST) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def scan_source(source: str) -> Counter:
    """Count retired words in a module's non-docstring string literals."""
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    counts: Counter = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            for word, (pattern, _) in RETIRED.items():
                counts[word] += len(pattern.findall(node.value))
    return +counts


def scan_tools() -> dict:
    found = {}
    for path in sorted(TOOLS.glob("*.py")):
        for word, n in scan_source(path.read_text(encoding="utf-8")).items():
            found[(path.name, word)] = n
    return found


# --- the scanner itself ------------------------------------------------------

def test_scanner_catches_a_new_retired_word():
    assert scan_source('print("pushing to Canvas")') == {"push": 1}
    assert scan_source('x = f"see the {n} Zone-2 files"') == {"Zone 2": 1}
    assert scan_source('raise SystemExit("not a course repo")') == {"course repo": 1}


def test_scanner_ignores_git_identifiers_and_docstrings():
    src = ('"""Docstrings explain code: push, Zone 2, course repo."""\n'
           'def f():\n    """push."""\n'
           '    print("run git push, then the pre-push hook")\n'
           '    print("pass --push to grader_push.py")\n'
           '    return ".claude/ferpa_zone2.txt"\n')
    assert scan_source(src) == {}


def test_every_retired_word_is_on_a_glossary_avoid_list():
    """The list here must come from the glossary, not drift from it."""
    avoid = " ".join(line.lower() for line in GLOSSARY.read_text(encoding="utf-8").splitlines()
                     if line.startswith("_Avoid_:"))
    for word in RETIRED:
        assert word.lower() in avoid, f"{word!r} is not on any _Avoid_ line in {GLOSSARY.name}"


# --- the guard ---------------------------------------------------------------

def test_tool_strings_use_no_retired_word_beyond_the_allowlist():
    found = scan_tools()
    problems = []
    for key in sorted(set(found) | set(ALLOWLIST)):
        tool, word = key
        now, allowed = found.get(key, 0), ALLOWLIST.get(key, 0)
        if now > allowed:
            problems.append(f"lib/tools/{tool}: {now} use(s) of {word!r} (allowlist {allowed}). "
                            f"Use the glossary term: {RETIRED[word][1]}.")
        elif now < allowed:
            problems.append(f"lib/tools/{tool}: {word!r} is down to {now} (allowlist {allowed}). "
                            f"Lower ALLOWLIST[{key!r}] to {now} in this PR so it can't creep back.")
    assert not problems, "\n".join(problems)

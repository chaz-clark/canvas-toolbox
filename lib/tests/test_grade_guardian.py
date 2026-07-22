"""Unit + integration tests — grade_guardian PreToolUse hook (issue #213).

The hook is the harness-level seam that catches what in-tool gates can't: a direct
Canvas grade write that never goes through grader_push.py. These tests pin the two
things that matter — it DENIES the bypass paths, and it does NOT get in the way of
the sanctioned tools / ordinary work (a guardrail that cries wolf gets disabled).
"""
import json
import subprocess
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grade_guardian import evaluate, ensure_hook  # noqa: E402

HOOK = _TOOLS_DIR / "grade_guardian.py"


# --- ensure_hook: idempotent, non-clobbering settings.json merge -----------

def test_ensure_hook_adds_to_empty_settings():
    new, changed = ensure_hook({})
    assert changed is True
    cmds = [h["command"] for e in new["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert any("grade_guardian" in c for c in cmds)


def test_ensure_hook_is_idempotent():
    once, _ = ensure_hook({})
    twice, changed = ensure_hook(once)
    assert changed is False
    assert twice == once  # no duplicate entry


def test_ensure_hook_preserves_existing_settings():
    """Must not clobber a course repo's existing permissions/other hooks."""
    existing = {"permissions": {"allow": ["Bash(git status)"]},
                "hooks": {"PreToolUse": [{"matcher": "Read",
                                          "hooks": [{"type": "command", "command": "other.sh"}]}]}}
    new, changed = ensure_hook(existing)
    assert changed is True
    assert new["permissions"] == existing["permissions"]          # untouched
    cmds = [h["command"] for e in new["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert "other.sh" in cmds and any("grade_guardian" in c for c in cmds)


def test_ensure_hook_does_not_mutate_input():
    original = {}
    ensure_hook(original)
    assert original == {}  # deepcopy, not in-place


# --- DENY: the paths the #213 incident used --------------------------------

def test_denies_curl_put_to_submissions():
    cmd = ("curl -X PUT https://byui.instructure.com/api/v1/courses/1/assignments/"
           "2/submissions/3 -d submission[posted_grade]=90")
    assert evaluate("Bash", {"command": cmd}) is not None


def test_denies_inline_python_requests_put():
    cmd = ("python -c 'import requests; requests.put(\"https://x.instructure.com/"
           "api/v1/courses/1/assignments/2/submissions/3\", "
           "data={\"submission[posted_grade]\": \"90\"})'")
    assert evaluate("Bash", {"command": cmd}) is not None


def test_denies_writing_the_bypass_script_at_creation():
    """The core catch: a Bash hook can't see inside `python /tmp/push.py`, but the
    Write hook sees the file contents as the script is created."""
    body = ('import requests\n'
            'requests.put("https://x.instructure.com/api/v1/courses/1/assignments/2/'
            'submissions/3", data={"submission[posted_grade]": "90"})\n')
    reason = evaluate("Write", {"file_path": "/tmp/push_kc_grades.py", "file_contents": body})
    assert reason is not None
    assert "grader_push.py" in reason  # the denial redirects to the safe path


def test_denies_edit_that_introduces_a_canvas_write():
    body = 'requests.post("https://x.instructure.com/api/v1/courses/1/assignments/2/submissions/3")'
    assert evaluate("Edit", {"file_path": "grading/kc3/hack.py", "new_string": body}) is not None


def test_denies_reading_ferpa_zone2_files():
    for p in ("grading/.deid_master.csv", "grading/kc3/.keymap.json",
              "grading/kc3/submissions_raw/foo.ipynb"):
        assert evaluate("Read", {"file_path": p}) is not None, p


# --- ALLOW: the sanctioned tool + ordinary work ----------------------------

def test_allows_running_grader_push():
    for cmd in (
        "uv run python canvas-toolbox/lib/tools/grader_push.py --challenge-dir grading/kc3 --push",
        "python lib/tools/grader_push.py --challenge-dir grading/kc3 --mark-reviewed",
    ):
        assert evaluate("Bash", {"command": cmd}) is None, cmd


def test_allows_ordinary_bash():
    for cmd in ("git status", "ls grading/", "curl https://api.github.com/repos/x/y",
                "uv run pytest lib/tests/ -q"):
        assert evaluate("Bash", {"command": cmd}) is None, cmd


def test_allows_editing_the_toolkit_source():
    """The tools legitimately contain requests.put to Canvas — editing them is the
    reviewed path, not a bypass."""
    body = 'requests.put(f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions/{uid}")'
    assert evaluate("Write", {"file_path": "/repo/lib/tools/grader_push.py",
                              "file_contents": body}) is None


def test_allows_docs_with_example_code():
    """A design doc that shows the bad pattern as an EXAMPLE is prose, not a script."""
    body = "Bad: `requests.put('.../submissions/3', data={'submission[posted_grade]':'90'})`"
    assert evaluate("Write", {"file_path": "docs/grading_enforcement_A3.md",
                              "file_contents": body}) is None


def test_allows_feedback_and_non_ferpa_reads():
    for p in ("grading/kc3/feedback/KC3-ABC.md", "README.md", "grading/kc3/config.json"):
        assert evaluate("Read", {"file_path": p}) is None, p


def test_payload_mention_without_a_write_verb_is_allowed():
    """Guard against over-blocking: prose/config that merely names `posted_grade`
    without an actual write call must pass."""
    assert evaluate("Bash", {"command": "grep posted_grade grading/kc3/config.json"}) is None


# --- Integration: drive the real hook exactly as Claude Code does ----------

def _run_hook(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOK)],
                          input=json.dumps(payload), capture_output=True, text=True)


def test_hook_exits_2_and_redirects_on_a_bypass_write():
    r = _run_hook({"tool_name": "Write",
                   "tool_input": {"file_path": "/tmp/push.py",
                                  "file_contents": 'requests.put("https://x.instructure.com/'
                                  'api/v1/courses/1/assignments/2/submissions/3")'}})
    assert r.returncode == 2
    assert "grader_push.py" in r.stderr


def test_hook_exits_0_on_allowed_call():
    r = _run_hook({"tool_name": "Bash", "tool_input": {"command": "git status"}})
    assert r.returncode == 0


def test_hook_fails_open_on_garbage_stdin():
    """A guardrail must never brick the session — malformed input → allow (exit 0)."""
    r = subprocess.run([sys.executable, str(HOOK)], input="not json",
                       capture_output=True, text=True)
    assert r.returncode == 0

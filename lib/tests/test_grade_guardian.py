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

from grade_guardian import (evaluate, ensure_hook, hook_command,  # noqa: E402
                            _extract_script_paths)

_BYPASS_BODY = ('import requests\n'
                'requests.put("https://x.instructure.com/api/v1/courses/1/assignments/2/'
                'submissions/3", data={"submission[posted_grade]": "90"})\n')

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


# --- hook_command: FAIL OPEN on a missing script (never brick a session) ----

def test_hook_command_fails_open_when_script_missing(tmp_path):
    """A wrong path / uninstalled toolkit must ALLOW the tool (exit 0), not block
    it. Regression for the standalone doubled-path brick: a bare `python3 <missing>`
    exits 2 (= deny) and locks out every tool, including the Read/Edit to fix it."""
    import os
    cmd = hook_command()  # $CLAUDE_PROJECT_DIR/canvas-toolbox/lib/tools/grade_guardian.py
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}  # no canvas-toolbox/ here
    r = subprocess.run(cmd, shell=True, env=env, input="{}", capture_output=True, text=True)
    assert r.returncode == 0  # missing script -> fail OPEN


def test_hook_command_propagates_deny_when_script_present(tmp_path):
    """When the guardian IS present, its exit code must propagate unchanged — a
    deny (exit 2) must not be swallowed by the fail-open wrapper."""
    import os
    d = tmp_path / "canvas-toolbox" / "lib" / "tools"
    d.mkdir(parents=True)
    (d / "grade_guardian.py").write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    r = subprocess.run(hook_command(), shell=True, env=env, input="{}", capture_output=True, text=True)
    assert r.returncode == 2  # present + denies -> deny propagates


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
    Write hook sees the file contents as the script is created. Claude Code's Write
    tool sends the body as `content` — reading the wrong key silently blinded this
    catch and let a hand-written push script through (the guardian field-name bug)."""
    body = ('import requests\n'
            'requests.put("https://x.instructure.com/api/v1/courses/1/assignments/2/'
            'submissions/3", data={"submission[posted_grade]": "90"})\n')
    reason = evaluate("Write", {"file_path": "/tmp/push_kc_grades.py", "content": body})
    assert reason is not None
    assert "grader_push.py" in reason  # the denial redirects to the safe path


def test_denies_bypass_script_regardless_of_body_key():
    """Regression: the guard must read the body from whatever key the client uses —
    `content` (Claude Code Write), `file_contents` (legacy/alt), `new_string` (Edit)."""
    body = ('requests.put("https://x.instructure.com/api/v1/courses/1/assignments/2/'
            'submissions/3", data={"submission[posted_grade]": "90"})')
    for key in ("content", "file_contents", "new_string"):
        assert evaluate("Write", {"file_path": "/tmp/p.py", key: body}) is not None, key


def test_denies_edit_that_introduces_a_canvas_write():
    body = 'requests.post("https://x.instructure.com/api/v1/courses/1/assignments/2/submissions/3")'
    assert evaluate("Edit", {"file_path": "grading/kc3/hack.py", "new_string": body}) is not None


# --- DENY: RUNNING an existing bypass script (the run-catch, third leg) --------

def test_extract_script_paths_finds_py_tokens_not_dot_python():
    paths = _extract_script_paths("uv run python ./g/fix_push.py --course S1")
    assert "./g/fix_push.py" in paths
    # `python` / `.python` must NOT be captured as a script path
    assert not any(p.endswith("python") for p in _extract_script_paths("python3 foo"))


def test_denies_running_existing_bypass_script(tmp_path):
    """The gap that stacked comments + graded Test Student in the field: an already-
    existing hand-written push script, RUN via `python x.py`. The command string has
    no write verb; the write is inside the file. The guard reads it and blocks."""
    script = tmp_path / "fix_push.py"
    script.write_text(_BYPASS_BODY, encoding="utf-8")
    reason = evaluate("Bash", {"command": f"uv run python {script} --course S1"})
    assert reason is not None
    assert "grader_push.py" in reason


def test_denies_running_bypass_script_via_relative_path(tmp_path, monkeypatch):
    """Relative script paths resolve against CLAUDE_PROJECT_DIR (how Claude Code
    runs commands from the repo root)."""
    (tmp_path / "grading").mkdir()
    (tmp_path / "grading" / "push.py").write_text(_BYPASS_BODY, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert evaluate("Bash", {"command": "python grading/push.py"}) is not None


def test_allows_running_ordinary_python_script(tmp_path):
    """A non-Canvas script (no write signature) runs freely — no over-blocking."""
    script = tmp_path / "analyze.py"
    script.write_text("import pandas as pd\nprint('hello')\n", encoding="utf-8")
    assert evaluate("Bash", {"command": f"python {script}"}) is None


def test_run_catch_fails_open_on_unreadable_script():
    """A path that doesn't resolve → can't read the body → ALLOW (fail open); the
    guard must never brick a session because a path didn't exist."""
    assert evaluate("Bash", {"command": "python /nope/does_not_exist.py"}) is None


def test_run_catch_does_not_reread_grader_push(tmp_path, monkeypatch):
    """grader_push.py under lib/tools/ legitimately contains Canvas writes — running
    it must stay exempt (the run-catch skips lib/tools/ before reading)."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert evaluate("Bash", {"command":
        "uv run python canvas-toolbox/lib/tools/grader_push.py --push"}) is None


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
                              "content": body}) is None


def test_allows_docs_with_example_code():
    """A design doc that shows the bad pattern as an EXAMPLE is prose, not a script."""
    body = "Bad: `requests.put('.../submissions/3', data={'submission[posted_grade]':'90'})`"
    assert evaluate("Write", {"file_path": "docs/grading_enforcement_A3.md",
                              "content": body}) is None


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
                                  "content": 'requests.put("https://x.instructure.com/'
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

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
                            _extract_script_paths, ask_reason, _grader_push_checkpoint,
                            load_zone2, compile_zone2, zone2_summary)

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


# --- ASK layer (#264, #265): force an in-chat prompt at BOTH AI-drafted checkpoints ---

def test_asks_on_ai_drafted_push():
    """grader_push --push writing AI-drafted comments → the guardian asks (the human
    review gate moved here now that --yes is honored, so no terminal keystroke)."""
    cmd = "uv run python canvas-toolbox/lib/tools/grader_push.py --challenge-dir grading/kc3 --push"
    assert _grader_push_checkpoint(cmd) == "push"
    assert ask_reason("Bash", {"command": cmd}) is not None


def test_asks_on_mark_reviewed():
    """#265: --mark-reviewed must ALSO prompt — else an agent runs `--mark-reviewed
    --yes` and self-attests review without ever showing the human _all_comments.md."""
    cmd = "uv run python canvas-toolbox/lib/tools/grader_push.py --challenge-dir grading/kc3 --mark-reviewed --yes"
    assert _grader_push_checkpoint(cmd) == "review"
    assert ask_reason("Bash", {"command": cmd}) is not None


def test_asks_on_comments_only_push():
    """--comments-only --push posts AI-drafted comments to students → it MUST trip the
    guardian pop-up like any other AI-drafted push (it is NOT the value-only path)."""
    cmd = "uv run python canvas-toolbox/lib/tools/grader_push.py --challenge-dir grading/kc3 --comments-only --push"
    assert _grader_push_checkpoint(cmd) == "push"
    assert ask_reason("Bash", {"command": cmd}) is not None


def test_asks_on_roster_csv_push():
    """--roster-csv --push posts comments to students (incl. non-submitters) → it MUST
    trip the guardian pop-up (it's a comment write on the AI-drafted path)."""
    cmd = "uv run python canvas-toolbox/lib/tools/grader_push.py --challenge-dir grading/fpr --roster-csv ns.csv --assignment-id 5 --push"
    assert _grader_push_checkpoint(cmd) == "push"
    assert ask_reason("Bash", {"command": cmd}) is not None


def test_no_ask_on_dry_run():
    """No --push / --mark-reviewed (dry-run) is not a checkpoint — no prompt. A
    --comments-only dry-run (no --push) likewise doesn't write, so no prompt."""
    for cmd in (
        "uv run python canvas-toolbox/lib/tools/grader_push.py --challenge-dir grading/kc3 --assignment-id 5",
        "uv run python canvas-toolbox/lib/tools/grader_push.py --challenge-dir grading/kc3 --comments-only",
    ):
        assert _grader_push_checkpoint(cmd) is None, cmd
        assert ask_reason("Bash", {"command": cmd}) is None, cmd


def test_no_ask_on_value_only_and_test_and_retract():
    """Value-only (--grade-only), test-student (--test-user), and retract (--retract)
    are not AI-drafted-comment checkpoints — they keep the frictionless --yes path,
    at both --push and --mark-reviewed."""
    for verb in ("--push", "--mark-reviewed"):
        base = f"python lib/tools/grader_push.py --challenge-dir grading/kc3 {verb}"
        for extra in ("--grade-only", "--test-user 1234", "--retract"):
            assert ask_reason("Bash", {"command": f"{base} {extra}"}) is None, f"{verb} {extra}"


def test_no_ask_on_non_grader_push_or_other_tools():
    assert ask_reason("Bash", {"command": "git push origin main"}) is None  # --push, not grader
    assert ask_reason("Write", {"file_path": "x.py", "content": "grader_push --push"}) is None


def test_hook_emits_ask_json_on_ai_drafted_push():
    """End-to-end: the real hook prints permissionDecision 'ask' (exit 0) so Claude
    Code prompts the instructor — the in-chat attestation that replaced the terminal."""
    for cmd in (
        "uv run python canvas-toolbox/lib/tools/grader_push.py --challenge-dir grading/kc3 --push",
        "uv run python canvas-toolbox/lib/tools/grader_push.py --challenge-dir grading/kc3 --mark-reviewed --yes",
    ):
        r = _run_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
        assert r.returncode == 0, cmd
        out = json.loads(r.stdout)
        assert out["hookSpecificOutput"]["permissionDecision"] == "ask", cmd
        assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert out["hookSpecificOutput"]["permissionDecisionReason"]


# --- FERPA Zone-2 reads in the SHELL (#270): close the `cat .keymap.json` hole ---

def test_bash_blocks_raw_read_of_zone2():
    """Reading a Zone-2 file in the shell (cat/head/tail/open) is blocked — the Read-tool
    block doesn't cover `cat`, and reading the keymap reconstructs identity."""
    for cmd in (
        "cat grading/kc3/.keymap.json",
        "head -5 grading/.deid_master.csv",
        "tail grading/kc3/.review.csv",
        "python3 -c \"import json; print(json.load(open('grading/kc3/.keymap.json')))\"",
    ):
        assert evaluate("Bash", {"command": cmd}) is not None, cmd


def test_bash_allows_metadata_and_filtered_zone2_access():
    """The constitution PERMITS wc/ls/stat and the filtered `grep <code> … | cut -f1,2`
    verification — none dump raw rows, so they must still pass. And git HEAD is not `head`."""
    for cmd in (
        "wc -l grading/.deid_master.csv",
        "ls -la grading/kc3/submissions_raw/",
        "grep S-95DBB6 grading/.deid_master.csv | cut -d',' -f1,2",
        "git log HEAD..main -- grading/.deid_master.csv",   # HEAD != head; metadata verb
    ):
        assert evaluate("Bash", {"command": cmd}) is None, cmd


def test_bash_exempts_sanctioned_reidentify_reading_keymap():
    """grader_reidentify legitimately reads the keymap internally — invoking it (a
    lib/tools/ script) with a Zone-2 path as an arg must not be blocked."""
    cmd = ("uv run python canvas-toolbox/lib/tools/grader_reidentify.py "
           "--challenge-dir grading/kc3 --map grading/kc3/.keymap.json")
    assert evaluate("Bash", {"command": cmd}) is None


# --- Zone-2 pattern set: one source, two forms, course-local extension (#278) ---

def test_both_zone2_forms_derive_from_one_list_and_cannot_drift():
    """They were two hand-maintained regexes with a 'kept in sync by hand' comment,
    and had already drifted (case sensitivity, `.*` vs `[^/\\]*`). Same source now."""
    entries, invalid = load_zone2(Path("/nonexistent"))
    assert invalid == []
    path_re, file_re = compile_zone2(entries)
    for stem in (".deid_master.csv", ".known_names.txt", ".keymap.json",
                 ".fetch_log.json", ".review.csv"):
        assert path_re.search(f"grading/{stem}"), stem      # anchored form
        assert file_re.search(f"cat grading/{stem}"), stem  # shell form


def test_zone2_path_form_is_case_insensitive():
    """It used to be case-sensitive while the shell form wasn't, so on a
    case-insensitive filesystem `Read .DEID_MASTER.csv` passed a block `cat` caught."""
    path_re, _ = compile_zone2(load_zone2(Path("/nonexistent"))[0])
    assert path_re.search("grading/.DEID_MASTER.CSV")


def test_course_local_patterns_extend_the_set(tmp_path):
    """The Brightspace case (#278): a non-Canvas consumer's name-bearing files have
    ZERO overlap with the Canvas defaults, so the hook enforced an empty set."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "ferpa_zone2.txt").write_text(
        "# a Brightspace course's name-bearing files\n"
        "\n"
        r"_all_posts\.md" "\n"
        r"_roster\.json" "\n"
        r"/txt_full/" "\n",
        encoding="utf-8")
    entries, invalid = load_zone2(tmp_path)
    assert invalid == []
    path_re, file_re = compile_zone2(entries)
    assert path_re.search("discussions/m3/_all_posts.md")
    assert file_re.search("cat discussions/m3/_roster.json")
    assert file_re.search("head discussions/txt_full/x.txt")
    assert path_re.search("grading/.keymap.json")     # defaults still enforced


def test_invalid_course_patterns_are_dropped_but_reported(tmp_path):
    """A typo must not brick the session — but a silently ignored pattern is the
    false sense of coverage this issue is about, so it has to surface."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "ferpa_zone2.txt").write_text(
        "_all_posts\\.md\n[unclosed\n", encoding="utf-8")
    entries, invalid = load_zone2(tmp_path)
    assert invalid == ["[unclosed"]
    compile_zone2(entries)                            # the good ones still compile
    assert zone2_summary(tmp_path)["invalid"] == ["[unclosed"]


def test_zone2_summary_reports_counts_and_source(tmp_path):
    bare = zone2_summary(tmp_path)
    assert bare["extra"] == 0 and bare["source"] is None   # nothing to mislead about
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "ferpa_zone2.txt").write_text("_all_posts\\.md\n", encoding="utf-8")
    s = zone2_summary(tmp_path)
    assert s["default"] > 0 and s["extra"] == 1 and s["source"].endswith("ferpa_zone2.txt")


def test_missing_or_unreadable_extension_file_is_silent(tmp_path):
    """Absent file is the overwhelmingly common case (every Canvas repo) — no noise,
    no failure."""
    assert load_zone2(tmp_path) == (load_zone2(Path("/nonexistent"))[0], [])


def test_hook_process_actually_blocks_a_course_local_zone2_file(tmp_path):
    """End-to-end through the REAL hook process, because that's the only thing that
    proves the extension point works. The pure-function tests above can all pass
    while `evaluate()` still consults a stale module-level regex — the same class of
    self-confirming test that let #277 ship. Run the hook the way Claude Code does:
    tool call on stdin, CLAUDE_PROJECT_DIR set, exit 2 = blocked."""
    import os
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "ferpa_zone2.txt").write_text(r"_all_posts\.md" "\n",
                                                          encoding="utf-8")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}

    def run(payload):
        return subprocess.run([sys.executable, str(HOOK)], env=env, text=True,
                              input=json.dumps(payload), capture_output=True)

    blocked = run({"tool_name": "Read",
                   "tool_input": {"file_path": "discussions/m3/_all_posts.md"}})
    assert blocked.returncode == 2, blocked.stderr
    assert "FERPA" in blocked.stderr

    # the shell form too — `cat` was the #270 hole, and it must cover extras as well
    shell = run({"tool_name": "Bash",
                 "tool_input": {"command": "cat discussions/m3/_all_posts.md"}})
    assert shell.returncode == 2, shell.stderr

    # and a file NOT in either set still passes — the extension must not over-block
    ok = run({"tool_name": "Read", "tool_input": {"file_path": "README.md"}})
    assert ok.returncode == 0


def test_hook_process_without_course_patterns_still_enforces_defaults(tmp_path):
    """No extension file (every Canvas repo) — defaults must be untouched."""
    import os
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    r = subprocess.run([sys.executable, str(HOOK)], env=env, text=True, capture_output=True,
                       input=json.dumps({"tool_name": "Read",
                                         "tool_input": {"file_path": "grading/.keymap.json"}}))
    assert r.returncode == 2, r.stderr


def test_classlist_export_is_blocked_out_of_the_box(tmp_path):
    """The sharpest artifact from #278's follow-up: a D2L Classlist export is the
    complete identity join for a section (name + username + email + institutional id,
    one row per student). Shipped as a default rather than left to config, because an
    unconfigured consumer is exactly the 'installed and enforcing nothing' case the
    issue is about. `Classlist_Export` is D2L's invariant export naming — the course
    code, term and timestamp around it vary, that substring doesn't."""
    import os
    real = "DAT 300 Data Mining 25EW6_Classlist_Export_2026-08-04-120000.csv"
    path_re, file_re = compile_zone2(load_zone2(Path("/nonexistent"))[0])
    assert path_re.search(f"rosters/{real}")
    assert file_re.search(f"cat '~/Downloads/{real}'")     # where it actually lands

    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}   # NO config file
    r = subprocess.run([sys.executable, str(HOOK)], env=env, text=True, capture_output=True,
                       input=json.dumps({"tool_name": "Read",
                                         "tool_input": {"file_path": f"rosters/{real}"}}))
    assert r.returncode == 2, r.stderr


# --- credentials (#288) -----------------------------------------------------
#
# Zone-2 protected student data; nothing protected the API token. Consolidating it
# into ~/.canvas/config made that sharper: five repo-local gitignored files became
# ONE well-known path holding the single credential for every course.

def test_global_credential_file_is_blocked_for_read_and_shell():
    """It holds a credential and nothing else, so blocking it costs nothing —
    load_env() reads it in-process, which is never a tool call."""
    assert evaluate("Read", {"file_path": "/Users/x/.canvas/config"}) is not None
    assert evaluate("Bash", {"command": "cat ~/.canvas/config"}) is not None


def test_env_blocks_shell_display_but_not_read():
    """Graded deliberately. Blocking Read on .env would also block Edit — the
    harness requires a read first — leaving only blind whole-file overwrite, which
    is worse than the leak it prevents. .env also holds course ids and settings an
    agent legitimately works with."""
    assert evaluate("Bash", {"command": "cat .env"}) is not None
    assert evaluate("Bash", {"command": "head -5 ds460-master/.env"}) is not None
    assert evaluate("Read", {"file_path": "ds460-master/.env"}) is None


def test_blocks_the_python_read_form_that_actually_leaked_a_token():
    """The real incident this is built from: not `cat`, but a script printing the
    file. Any mistake-proofing that only covers cat/head misses how it happens."""
    cmd = ("python3 -c \"from pathlib import Path; "
           "print(Path('ds460-master/.env').read_text())\"")
    assert evaluate("Bash", {"command": cmd}) is not None


def test_key_name_inspection_still_works():
    """The escape hatch. Checking WHICH keys are configured is legitimate and
    frequent; it lists no values and isn't a raw-display verb."""
    assert evaluate("Bash", {"command": "grep -o '^[A-Z_]*=' .env"}) is None


def test_templates_and_direnv_are_not_credentials():
    """Pure friction if blocked — neither carries a secret."""
    assert evaluate("Bash", {"command": "cat .env.example"}) is None
    assert evaluate("Bash", {"command": "cat .envrc"}) is None
    assert evaluate("Read", {"file_path": "scaffold/.env.example"}) is None


def test_credential_denial_says_where_the_value_comes_from_instead():
    """A denial that doesn't name the alternative gets worked around."""
    msg = evaluate("Read", {"file_path": "/Users/x/.canvas/config"})
    assert "load_env" in msg and "grep" in msg

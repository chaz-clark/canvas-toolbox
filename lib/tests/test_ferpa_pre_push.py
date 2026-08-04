"""Unit + integration tests — the pre-push FERPA guard (#285).

The agent-layer guardian can't see `git push`, and a push cannot be undone. These
pin the two things that matter: it BLOCKS Zone-2 data reaching a remote, and it does
not get in the way of ordinary work (a guard that cries wolf gets `--no-verify`'d).

The end-to-end tests drive the real hook process in a real git repo, because the
range logic is where this can silently do nothing — a pattern-only assertion is what
let #277 ship.
"""
import subprocess
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from ferpa_pre_push import (  # noqa: E402
    _UID_NAME_MAP,
    _dirs_of,
    ensure_pre_push_hook,
    format_block,
    match_paths,
    parse_push_specs,
    range_args,
)
from grade_guardian import compile_zone2, load_zone2  # noqa: E402

HOOK = _TOOLS_DIR / "ferpa_pre_push.py"
_NULL = "0" * 40


def _git(repo, *args, **kw):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, **kw)


def _repo(tmp_path):
    """A real git repo with an origin it can push to (a bare remote)."""
    bare = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-q", str(bare))
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", ".")
    _git(work, "config", "user.email", "t@t.t")
    _git(work, "config", "user.name", "T")
    _git(work, "remote", "add", "origin", str(bare))
    (work / "README.md").write_text("hi\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "init")
    return work


# --- stdin parsing + range resolution ---------------------------------------

def test_parse_push_specs_skips_a_branch_deletion():
    """A deletion publishes nothing — blocking it would be pure obstruction."""
    text = (f"refs/heads/x {_NULL} refs/heads/x abc123\n"
            f"refs/heads/y def456 refs/heads/y {_NULL}\n")
    assert parse_push_specs(text) == [("def456", _NULL)]


def test_parse_push_specs_ignores_malformed_lines():
    assert parse_push_specs("garbage\n\n") == []


def test_range_args_handles_a_new_branch():
    """The case a naive `remote..local` gets wrong. With no base, exclude what's
    already published anywhere rather than walking all history and blocking on an
    ancient commit that isn't being pushed."""
    assert range_args("abc", _NULL) == ["abc", "--not", "--remotes"]
    assert range_args("abc", "def") == ["def..abc"]


# --- path matching -----------------------------------------------------------

def test_match_paths_uses_the_shared_zone2_list(tmp_path):
    """One pattern source, not two. A second list would drift — the bug 1.16.0 fixed
    a layer down after the guardian's own two regexes had already diverged."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "ferpa_zone2.txt").write_text(r"_all_posts\.md" "\n",
                                                          encoding="utf-8")
    path_re, _ = compile_zone2(load_zone2(tmp_path)[0])
    hits = match_paths(
        ["README.md", "grading/.deid_master.csv", "discussions/m3/_all_posts.md"],
        path_re)
    assert hits == ["grading/.deid_master.csv", "discussions/m3/_all_posts.md"]


def test_uid_name_map_pattern_catches_serializations_but_not_prose():
    for carrier in ('{"806485": "Jane Doe"}', "806485 = 'Jane Doe'",
                    '1395396,"Farmer, Andrew"'):
        assert _UID_NAME_MAP.search(carrier), carrier
    for benign in ("version = '1.18.0'", "see RFC 2119", "{'count': 42}"):
        assert not _UID_NAME_MAP.search(benign), benign


# --- output never leaks a filename ------------------------------------------

def test_output_withholds_leaf_filenames():
    """A matched FILENAME may itself be a student name. Directories only — the whole
    point of the guard is undone if the denial prints what it caught."""
    hits = ["grading/kc3/submissions_raw/Lastname_Firstname_9912.docx"]
    assert _dirs_of(hits) == ["grading/kc3/submissions_raw/"]
    msg = format_block(hits, [], scanned_content=True)
    assert "Lastname" not in msg and "Firstname" not in msg
    assert "grading/kc3/submissions_raw/" in msg


def test_block_message_leads_with_the_non_destructive_fix():
    """A blocked push lands on someone trying to share their work, and 'rewrite
    history' is beyond most faculty. A message that only says what's wrong produces
    --no-verify."""
    msg = format_block(["grading/.deid_master.csv"], [], scanned_content=True)
    assert msg.index("git switch -c clean-work") < msg.index("filter-repo")
    assert "--no-verify" in msg and "cannot be undone" in msg
    assert "FALSE POSITIVE" in msg          # and how to narrow it


def test_block_message_says_when_content_scanning_is_off():
    """Never silently degrade — a guard that quietly does less is the same false
    confidence #278 was filed about."""
    off = format_block(["grading/.deid_master.csv"], [], scanned_content=False)
    assert "content scanning is OFF" in off
    on = format_block(["grading/.deid_master.csv"], [], scanned_content=True)
    assert "content scanning is OFF" not in on


# --- installer ---------------------------------------------------------------

def test_installs_to_git_hooks_not_hookspath(tmp_path):
    """NOT core.hooksPath: git consults that INSTEAD OF .git/hooks/, so setting it
    silently disables an existing .git/hooks/pre-commit — and `pre-commit install`
    then refuses to run. That would recreate the very failure #278 was about."""
    repo = _repo(tmp_path)
    assert ensure_pre_push_hook(repo, "canvas-toolbox", apply=False) == "would-install"
    assert not (repo / ".git" / "hooks" / "pre-push").exists()
    assert ensure_pre_push_hook(repo, "canvas-toolbox", apply=True) == "installed"
    hook = repo / ".git" / "hooks" / "pre-push"
    assert hook.is_file() and hook.stat().st_mode & 0o111       # executable
    assert ensure_pre_push_hook(repo, "canvas-toolbox", apply=True) == "present"
    assert _git(repo, "config", "--get", "core.hooksPath").stdout.strip() == ""


def test_pre_commit_framework_hook_survives_install(tmp_path):
    """The concrete regression: canvas-toolbox itself drives ruff/actionlint through
    the pre-commit framework at .git/hooks/pre-commit. Installing must not touch it."""
    repo = _repo(tmp_path)
    pc = repo / ".git" / "hooks" / "pre-commit"
    pc.write_text("#!/bin/sh\n# pre-commit framework\nexit 0\n", encoding="utf-8")
    ensure_pre_push_hook(repo, "canvas-toolbox", apply=True)
    assert "pre-commit framework" in pc.read_text(encoding="utf-8")


def test_never_clobbers_a_foreign_pre_push_hook(tmp_path):
    repo = _repo(tmp_path)
    hook = repo / ".git" / "hooks" / "pre-push"
    hook.write_text("#!/bin/sh\necho theirs\n", encoding="utf-8")
    assert ensure_pre_push_hook(repo, "canvas-toolbox", apply=True) == "skip-foreign"
    assert "theirs" in hook.read_text(encoding="utf-8")


def test_reports_no_git_outside_a_repo(tmp_path):
    assert ensure_pre_push_hook(tmp_path, "canvas-toolbox", apply=True) == "no-git"


# --- end to end, through the real hook process -------------------------------

def _run_hook(repo, local_sha, remote_sha):
    return subprocess.run(
        [sys.executable, str(HOOK)], cwd=str(repo), text=True, capture_output=True,
        input=f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n")


def test_clean_history_passes(tmp_path):
    repo = _repo(tmp_path)
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    r = _run_hook(repo, sha, _NULL)
    assert r.returncode == 0, r.stderr


def test_a_zone2_file_in_the_range_blocks(tmp_path):
    repo = _repo(tmp_path)
    (repo / "grading").mkdir()
    (repo / "grading" / ".deid_master.csv").write_text(
        "deid_code,user_id\nS-A,1\n", encoding="utf-8")
    _git(repo, "add", "-f", "grading/.deid_master.csv")
    _git(repo, "commit", "-qm", "oops")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    r = _run_hook(repo, sha, _NULL)
    assert r.returncode == 1
    assert "PUSH BLOCKED" in r.stderr
    assert "grading/" in r.stderr


def test_deleting_the_file_later_still_blocks(tmp_path):
    """History is what gets published. A later commit removing the file does not
    unpublish it — checking the worktree instead of the range would miss this."""
    repo = _repo(tmp_path)
    (repo / "grading").mkdir()
    (repo / "grading" / ".keymap.json").write_text("{}", encoding="utf-8")
    _git(repo, "add", "-f", "grading/.keymap.json")
    _git(repo, "commit", "-qm", "add")
    _git(repo, "rm", "-q", "grading/.keymap.json")
    _git(repo, "commit", "-qm", "remove")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    r = _run_hook(repo, sha, _NULL)
    assert r.returncode == 1, "worktree is clean but history still carries it"


def test_course_local_pattern_blocks_through_the_real_hook(tmp_path):
    """The Brightspace case end-to-end: a consumer's own name-bearing file, at a
    path no shipped pattern knows, blocked because the git layer reads the same
    .claude/ferpa_zone2.txt the agent layer does."""
    repo = _repo(tmp_path)
    (repo / ".claude").mkdir()
    (repo / ".claude" / "ferpa_zone2.txt").write_text(r"_all_posts\.md" "\n",
                                                      encoding="utf-8")
    (repo / "discussions").mkdir()
    (repo / "discussions" / "_all_posts.md").write_text("post\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "posts")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    r = _run_hook(repo, sha, _NULL)
    assert r.returncode == 1
    assert "discussions/" in r.stderr
    assert "_all_posts.md" not in r.stderr        # leaf withheld even here


def test_content_scan_is_off_by_default_and_catches_when_enabled(tmp_path):
    """A uid->name map at an unremarkable path: invisible to path checks, which is
    exactly why the scan exists. Opt-in because surname scanning false-positives."""
    repo = _repo(tmp_path)
    (repo / "notes.md").write_text('{"806485": "Jane Doe"}\n', encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "notes")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    assert _run_hook(repo, sha, _NULL).returncode == 0        # default: path only
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "ferpa_scan_content").write_text("", encoding="utf-8")
    r = _run_hook(repo, sha, _NULL)
    assert r.returncode == 1 and "CONTENT" in r.stderr
    assert "Jane" not in r.stderr                             # never echoes the name


def test_fails_open_on_unparseable_stdin(tmp_path):
    """A guardrail must never brick a repo."""
    repo = _repo(tmp_path)
    r = subprocess.run([sys.executable, str(HOOK)], cwd=str(repo), text=True,
                       capture_output=True, input="not a push spec\n")
    assert r.returncode == 0


def test_installed_hook_actually_runs_on_a_real_push(tmp_path):
    """The whole point. Install it the way cb_update does, then run a real
    `git push` and assert git refuses."""
    repo = _repo(tmp_path)
    toolkit = repo / "canvas-toolbox" / "lib" / "tools"
    toolkit.mkdir(parents=True)
    for mod in ("ferpa_pre_push.py", "grade_guardian.py"):
        (toolkit / mod).write_text((_TOOLS_DIR / mod).read_text(encoding="utf-8"),
                                   encoding="utf-8")
    ensure_pre_push_hook(repo, "canvas-toolbox", apply=True)
    (repo / "grading").mkdir()
    (repo / "grading" / ".known_names.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-f", "grading/.known_names.txt", "canvas-toolbox")
    _git(repo, "commit", "-qm", "leak")

    r = _git(repo, "push", "origin", "HEAD:refs/heads/main")
    assert r.returncode != 0, "git push should have been refused"
    assert "PUSH BLOCKED" in (r.stdout + r.stderr)


# --- the GUI rendering contract (genchi genbutsu, then jidoka) ---------------
#
# Verified by reading VS Code's git extension (dist/main.js) and running a real
# blocked push. Its error path is, verbatim:
#
#   b = (stderr || stdout || message).replace(/^error: /mi,"")
#         .split(/[\r\n]/).filter(s => !!s)
#   msg = stdout ? b[b.length-1] : b[0]
#   showErrorMessage(msg, {modal: true}, "Open Git Log", "Show Command Output")
#
# So a faculty member pushing from VS Code gets a MODAL dialog containing ONE line
# of ours — and the full text only behind a button. Two properties make that line
# the right one, and both are silent to break. These are the andon cord.

def _vscode_modal_line(stderr: str, stdout: str) -> str:
    """Port of the algorithm above. If VS Code changes, this test is where we find
    out — better here than in front of an instructor."""
    import re
    b = re.sub(r"^error: ", "", stderr, flags=re.I | re.M)
    lines = [s for s in re.split(r"[\r\n]", b) if s]
    if not lines:
        return "Git error"
    return lines[-1] if stdout else lines[0]


def test_vscode_modal_states_the_actual_reason(tmp_path):
    """PROPERTY 1: the first non-empty stderr line must stand alone. VS Code shows
    b[0] and hides the rest behind 'Show Command Output'. Add a preamble to stderr
    and the instructor's modal reads that instead — which is how a carefully written
    denial becomes an unexplained wall."""
    repo = _repo(tmp_path)
    (repo / "grading").mkdir()
    (repo / "grading" / ".deid_master.csv").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-f", "grading/.deid_master.csv")
    _git(repo, "commit", "-qm", "leak")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    r = _run_hook(repo, sha, _NULL)

    modal = _vscode_modal_line(r.stderr, r.stdout)
    assert "PUSH BLOCKED" in modal and "FERPA" in modal, modal
    assert "failed to push" not in modal


def test_hook_writes_nothing_to_stdout(tmp_path):
    """PROPERTY 2: VS Code switches to the LAST line when stdout is non-empty — and
    git appends its own 'error: failed to push some refs' last. So a single stray
    print() to stdout silently replaces the whole denial with git's generic message.
    Everything this hook says must go to stderr."""
    repo = _repo(tmp_path)
    (repo / "grading").mkdir()
    (repo / "grading" / ".keymap.json").write_text("{}", encoding="utf-8")
    _git(repo, "add", "-f", "grading/.keymap.json")
    _git(repo, "commit", "-qm", "leak")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    r = _run_hook(repo, sha, _NULL)
    assert r.stdout == "", f"stdout must stay empty; got {r.stdout!r}"

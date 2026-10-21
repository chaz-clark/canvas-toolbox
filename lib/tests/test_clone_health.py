"""clone_health: real temp git repos, no mocks (#415)."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from clone_health import clone_health  # noqa: E402


def _git(cwd, *a):
    subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True,
                   env={**__import__("os").environ, "GIT_AUTHOR_NAME": "t",
                        "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t"})


def _upstream(tmp_path):
    up = tmp_path / "up"
    up.mkdir()
    _git(up, "init", "-q", "-b", "main")
    (up / "f.txt").write_text("x")
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "init")
    return up


def test_plain_folder_is_not_a_repo(tmp_path):
    d = tmp_path / "tb"
    d.mkdir()
    assert clone_health(d)[0] == "not-a-repo"


def test_git_init_with_no_commits_is_the_colleagues_case(tmp_path):
    d = tmp_path / "tb"
    d.mkdir()
    (d / "f.txt").write_text("x")
    _git(d, "init", "-q")
    status, msg = clone_health(d)
    assert status == "no-commits"
    assert "reset --hard origin/main" in msg and "full access" in msg


def test_commits_but_no_origin(tmp_path):
    d = tmp_path / "tb"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    (d / "f.txt").write_text("x")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "c")
    assert clone_health(d)[0] == "no-origin"


def test_origin_but_no_upstream_branch(tmp_path):
    up = _upstream(tmp_path)
    d = tmp_path / "tb"
    _git(tmp_path, "clone", "-q", str(up), str(d))
    _git(d, "branch", "--unset-upstream")
    assert clone_health(d)[0] == "no-upstream"


def test_real_clone_is_ok_even_on_a_private_fork_url(tmp_path):
    up = _upstream(tmp_path)
    d = tmp_path / "tb"
    _git(tmp_path, "clone", "-q", str(up), str(d))
    assert clone_health(d) == ("ok", "")


def test_no_commits_repair_adds_origin_when_missing(tmp_path):
    d = tmp_path / "tb"
    d.mkdir()
    _git(d, "init", "-q")
    assert "remote add origin" in clone_health(d)[1]
    _git(d, "remote", "add", "origin", "https://example.com/x.git")
    assert "remote add origin" not in clone_health(d)[1]


def test_dubious_ownership_is_not_reported_as_no_commits(tmp_path, monkeypatch):
    """Real behaviour verified on Windows (repo owned by another user); a fake git
    call stands in because a different-owner repo can't be made portably."""
    import clone_health as ch
    d = tmp_path / "tb"
    (d / ".git").mkdir(parents=True)
    ok = subprocess.CompletedProcess([], 0, "git version 2", "")
    bad = subprocess.CompletedProcess([], 128, "", "fatal: detected dubious ownership in repository")
    monkeypatch.setattr(ch, "_git", lambda p, *a: ok if a == ("--version",) else bad)
    status, msg = ch.clone_health(d)
    assert status == "unsafe-owner" and "safe.directory" in msg

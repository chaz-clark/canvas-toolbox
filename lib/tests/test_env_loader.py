"""Unit tests — credential resolution, including the global fallback (#288).

Canvas expires API tokens every 29 days across all institutions, so an operator with
N course repos was editing N `.env` files a month and 401'ing silently on the one
they forgot. `~/.canvas/config` makes that one edit.

The safety property under test is that the global file can supply the TOKEN and
never the COURSE ID. `canvas_course_guard` (#27) exists because a stale course id
sends writes to the wrong course; a global course id would manufacture that.

Every test monkeypatches GLOBAL_CONFIG — without it these would read, and the
migration tests would write, the developer's real ~/.canvas/config.
"""
import os
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import _env_loader  # noqa: E402
from _env_loader import (  # noqa: E402
    GLOBAL_KEYS,
    _check_commit_hygiene,
    _check_toolkit_staleness,
    _COMMIT_CHECK_MARKER,
    _STALENESS_MARKER,
    global_config_problems,
    load_env,
)

_CANVAS_VARS = ("CANVAS_API_TOKEN", "CANVAS_BASE_URL", "CANVAS_COURSE_ID")


def _clean_env(monkeypatch):
    for v in _CANVAS_VARS:
        monkeypatch.delenv(v, raising=False)


def _global(tmp_path, monkeypatch, text):
    cfg = tmp_path / "home" / ".canvas" / "config"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(text, encoding="utf-8")
    cfg.chmod(0o600)
    monkeypatch.setattr(_env_loader, "GLOBAL_CONFIG", cfg)
    return cfg


def _repo(tmp_path, monkeypatch, env_text):
    repo = tmp_path / "course"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / ".env").write_text(env_text, encoding="utf-8")
    monkeypatch.chdir(repo)
    return repo


def test_global_fills_a_token_the_repo_env_lacks(tmp_path, monkeypatch):
    """The whole point: rotate in one place, every course repo picks it up."""
    _clean_env(monkeypatch)
    _global(tmp_path, monkeypatch, "CANVAS_API_TOKEN=GLOBAL_tok\n")
    _repo(tmp_path, monkeypatch, "CANVAS_COURSE_ID=12345\n")
    load_env()
    assert os.environ["CANVAS_API_TOKEN"] == "GLOBAL_tok"
    assert os.environ["CANVAS_COURSE_ID"] == "12345"     # still per-repo


def test_an_empty_scaffolded_token_does_not_shadow_the_global(tmp_path, monkeypatch):
    """cb_init scaffolds a bare `CANVAS_API_TOKEN=` into every new repo. Treating
    that as a value would make each new repo shadow the global file with an empty
    string and break on day one."""
    _clean_env(monkeypatch)
    _global(tmp_path, monkeypatch, "CANVAS_API_TOKEN=GLOBAL_tok\n")
    _repo(tmp_path, monkeypatch, "CANVAS_API_TOKEN=\nCANVAS_COURSE_ID=1\n")
    load_env()
    assert os.environ["CANVAS_API_TOKEN"] == "GLOBAL_tok"


def test_a_real_repo_token_still_wins(tmp_path, monkeypatch):
    """Per-repo override survives — a sandbox token, a service account, a colleague
    running one repo as themselves."""
    _clean_env(monkeypatch)
    _global(tmp_path, monkeypatch, "CANVAS_API_TOKEN=GLOBAL_tok\n")
    _repo(tmp_path, monkeypatch, "CANVAS_API_TOKEN=REPO_tok\n")
    load_env()
    assert os.environ["CANVAS_API_TOKEN"] == "REPO_tok"


def test_an_existing_environment_variable_beats_both(tmp_path, monkeypatch):
    """Highest precedence, unchanged. Demoting it — as the issue proposed — would
    break CI and one-off `CANVAS_API_TOKEN=x uv run …` overrides."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("CANVAS_API_TOKEN", "ENV_tok")
    _global(tmp_path, monkeypatch, "CANVAS_API_TOKEN=GLOBAL_tok\n")
    _repo(tmp_path, monkeypatch, "CANVAS_API_TOKEN=REPO_tok\n")
    load_env()
    assert os.environ["CANVAS_API_TOKEN"] == "ENV_tok"


def test_the_global_file_can_never_supply_a_course_id(tmp_path, monkeypatch):
    """THE safety property. A global course id means a repo with a missing or
    partial .env silently inherits whichever course was configured last — and
    pushes grades there. Allowlist, not denylist: a denylist would need extending
    for every future per-course key."""
    _clean_env(monkeypatch)
    _global(tmp_path, monkeypatch,
            "CANVAS_API_TOKEN=GLOBAL_tok\nCANVAS_COURSE_ID=99999\nS1_COURSE_ID=88\n")
    _repo(tmp_path, monkeypatch, "CANVAS_BASE_URL=https://x.instructure.com\n")
    load_env()
    assert os.environ["CANVAS_API_TOKEN"] == "GLOBAL_tok"
    assert "CANVAS_COURSE_ID" not in os.environ
    assert "S1_COURSE_ID" not in os.environ
    assert "CANVAS_COURSE_ID" not in GLOBAL_KEYS


def test_a_course_id_in_the_global_file_is_reported_not_swallowed(tmp_path, monkeypatch):
    """Ignoring it silently would leave someone convinced it's configured."""
    _clean_env(monkeypatch)
    _global(tmp_path, monkeypatch, "CANVAS_API_TOKEN=t\nCANVAS_COURSE_ID=99999\n")
    problems = " ".join(global_config_problems())
    assert "CANVAS_COURSE_ID" in problems and "IGNORED" in problems
    assert "configured last" in problems          # says the CONSEQUENCE, not just "no"


def test_world_readable_credentials_are_flagged(tmp_path, monkeypatch):
    """It holds an API token. ~/.ssh refuses outright; this warns with the exact
    command, since blocking a faculty member out of their own tools is worse."""
    cfg = _global(tmp_path, monkeypatch, "CANVAS_API_TOKEN=t\n")
    cfg.chmod(0o644)
    problems = " ".join(global_config_problems())
    assert "readable by other users" in problems and "chmod 600" in problems
    cfg.chmod(0o600)
    assert not any("readable" in p for p in global_config_problems())


def test_export_prefixes_and_quotes_are_parsed(tmp_path, monkeypatch):
    """python-dotenv, not a hand-rolled split. `export KEY="v#al"` defeats
    startswith(), keeps the quotes, and truncates at the `#` — each silently."""
    _clean_env(monkeypatch)
    _global(tmp_path, monkeypatch, 'export CANVAS_API_TOKEN="1234~ab#cd"\n')
    _repo(tmp_path, monkeypatch, "CANVAS_COURSE_ID=1\n")
    load_env()
    assert os.environ["CANVAS_API_TOKEN"] == "1234~ab#cd"


def test_absent_global_file_changes_nothing(tmp_path, monkeypatch):
    """The overwhelmingly common case today — must be a silent no-op."""
    _clean_env(monkeypatch)
    monkeypatch.setattr(_env_loader, "GLOBAL_CONFIG", tmp_path / "nope" / "config")
    _repo(tmp_path, monkeypatch, "CANVAS_API_TOKEN=REPO_tok\n")
    assert load_env() is not None
    assert os.environ["CANVAS_API_TOKEN"] == "REPO_tok"
    assert global_config_problems() == []


# ---------------------------------------------------------------------------
# Weekly toolkit staleness check (v2, #317 Phase 6). FAILS OPEN: none of these
# may ever raise out of _check_toolkit_staleness — it must be safe to call from
# inside load_env(), which ~94 tools call on every invocation.
# ---------------------------------------------------------------------------

import subprocess  # noqa: E402


def _git(d: Path, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)


def _origin_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q")
    (origin / "f.txt").write_text("x", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    course_root = tmp_path / "course"
    course_root.mkdir()
    subprocess.run(["git", "clone", "-q", str(origin), str(course_root / ".canvas-toolbox")],
                   check=True, capture_output=True)
    return origin, course_root


def test_staleness_check_no_op_without_a_hidden_clone(tmp_path, capsys):
    _check_toolkit_staleness(tmp_path)          # no .canvas-toolbox/ at all
    assert capsys.readouterr().err == ""


def test_staleness_check_writes_marker_and_is_silent_when_up_to_date(tmp_path, capsys):
    _origin, course_root = _origin_and_clone(tmp_path)
    _check_toolkit_staleness(course_root)
    assert (course_root / ".canvas-toolbox" / _STALENESS_MARKER).is_file()
    assert capsys.readouterr().err == ""        # local == remote — nothing to say


def test_staleness_check_notices_when_behind(tmp_path, capsys):
    origin, course_root = _origin_and_clone(tmp_path)
    (origin / "f.txt").write_text("y", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "update")
    _check_toolkit_staleness(course_root)
    assert "update is available" in capsys.readouterr().err


def test_staleness_check_skips_network_when_marker_is_fresh(tmp_path, monkeypatch):
    _origin, course_root = _origin_and_clone(tmp_path)
    marker = course_root / ".canvas-toolbox" / _STALENESS_MARKER
    marker.write_text("", encoding="utf-8")     # just written — fresh

    def _boom(*a, **k):
        raise AssertionError("must not shell out when the marker is fresh")
    monkeypatch.setattr(subprocess, "run", _boom)
    _check_toolkit_staleness(course_root)       # would raise if it reached subprocess.run


def test_staleness_check_rechecks_after_the_interval(tmp_path):
    import os as _os
    import time
    origin, course_root = _origin_and_clone(tmp_path)
    marker = course_root / ".canvas-toolbox" / _STALENESS_MARKER
    marker.write_text("", encoding="utf-8")
    old = time.time() - (_env_loader._STALENESS_CHECK_INTERVAL_DAYS + 1) * 86400
    _os.utime(marker, (old, old))
    (origin / "f.txt").write_text("y", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "update")
    _check_toolkit_staleness(course_root)
    assert marker.stat().st_mtime > old         # clock was reset


def test_staleness_check_never_raises_on_a_broken_clone(tmp_path):
    """A .canvas-toolbox/ that isn't a real git repo (partial vendoring, corrupted
    checkout) must degrade to silence, never an exception in a caller that can't
    afford one (load_env() itself)."""
    course_root = tmp_path / "course"
    (course_root / ".canvas-toolbox").mkdir(parents=True)
    _check_toolkit_staleness(course_root)       # must not raise


# ---------------------------------------------------------------------------
# Weekly commit-hygiene check. Found the need for this by a real survey across
# six *-master course repos, not assumed — see _env_loader.py's own comment.
# Same fail-open contract as the staleness check above.
# ---------------------------------------------------------------------------

def _course_repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """A course repo that is itself a git clone of some origin — the shape
    _check_commit_hygiene actually inspects, distinct from _origin_and_clone's
    course_root/.canvas-toolbox/ toolkit clone above."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q")
    (origin / "f.txt").write_text("x", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    course_root = tmp_path / "course"
    subprocess.run(["git", "clone", "-q", str(origin), str(course_root)],
                   check=True, capture_output=True)
    return origin, course_root


def test_commit_hygiene_no_op_without_a_git_repo(tmp_path, capsys):
    _check_commit_hygiene(tmp_path)             # no .git/ at all
    assert capsys.readouterr().err == ""


def test_commit_hygiene_never_nags_a_local_only_repo(tmp_path, capsys):
    """No remote configured — the documented, deliberate exception
    (behavioral_discipline.md, point 2). Never nag for a real choice."""
    course_root = tmp_path / "course"
    course_root.mkdir()
    _git(course_root, "init", "-q")
    (course_root / "f.txt").write_text("x", encoding="utf-8")
    _check_commit_hygiene(course_root)
    assert capsys.readouterr().err == ""


def test_commit_hygiene_silent_when_clean_and_pushed(tmp_path, capsys):
    _origin, course_root = _course_repo_with_remote(tmp_path)
    _check_commit_hygiene(course_root)
    assert (course_root / ".git" / _COMMIT_CHECK_MARKER).is_file()
    assert capsys.readouterr().err == ""


def test_commit_hygiene_notices_a_dirty_working_tree(tmp_path, capsys):
    _origin, course_root = _course_repo_with_remote(tmp_path)
    (course_root / "new_file.md").write_text("uncommitted", encoding="utf-8")
    _check_commit_hygiene(course_root)
    assert "uncommitted or unpushed" in capsys.readouterr().err


def test_commit_hygiene_notices_unpushed_commits(tmp_path, capsys):
    origin, course_root = _course_repo_with_remote(tmp_path)
    (course_root / "f.txt").write_text("y", encoding="utf-8")
    _git(course_root, "add", "-A")
    _git(course_root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "local only")
    _check_commit_hygiene(course_root)
    assert "uncommitted or unpushed" in capsys.readouterr().err


def test_commit_hygiene_skips_network_when_marker_is_fresh(tmp_path, monkeypatch):
    _origin, course_root = _course_repo_with_remote(tmp_path)
    marker = course_root / ".git" / _COMMIT_CHECK_MARKER
    marker.write_text("", encoding="utf-8")     # just written — fresh

    def _boom(*a, **k):
        raise AssertionError("must not shell out when the marker is fresh")
    monkeypatch.setattr(subprocess, "run", _boom)
    _check_commit_hygiene(course_root)          # would raise if it reached subprocess.run


def test_commit_hygiene_rechecks_after_the_interval(tmp_path):
    import os as _os
    import time
    _origin, course_root = _course_repo_with_remote(tmp_path)
    marker = course_root / ".git" / _COMMIT_CHECK_MARKER
    marker.write_text("", encoding="utf-8")
    old = time.time() - (_env_loader._COMMIT_CHECK_INTERVAL_DAYS + 1) * 86400
    _os.utime(marker, (old, old))
    (course_root / "dirty.md").write_text("x", encoding="utf-8")
    _check_commit_hygiene(course_root)
    assert marker.stat().st_mtime > old         # clock was reset


def test_commit_hygiene_never_raises_when_course_root_is_not_a_repo(tmp_path):
    course_root = tmp_path / "course"
    (course_root / ".git").mkdir(parents=True)  # present but not a real repo
    _check_commit_hygiene(course_root)          # must not raise

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
from _env_loader import GLOBAL_KEYS, global_config_problems, load_env  # noqa: E402

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

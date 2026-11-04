"""cb_secure_token — token moves to ~/.canvas/config, .env is stripped, nothing leaks.

GLOBAL_CONFIG is always monkeypatched to tmp_path so no test touches the real
~/.canvas/config. Runs on Mac, Linux and Windows (CI matrix); the Windows branch is
also exercised by mocking sys.platform and the icacls call.
"""
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import _env_loader  # noqa: E402
import cb_secure_token as cst  # noqa: E402

TOKEN = "1234~SECRETVALUE"
URL = "https://example.instructure.com"


@pytest.fixture
def paths(tmp_path, monkeypatch):
    glob = tmp_path / "home" / ".canvas" / "config"
    monkeypatch.setattr(_env_loader, "GLOBAL_CONFIG", glob)
    monkeypatch.setattr(cst, "verify_token", lambda t, b: True)
    env = tmp_path / ".env"
    env.write_bytes(f"CANVAS_API_TOKEN={TOKEN}\r\nCANVAS_BASE_URL={URL}\r\n"
                    f"CANVAS_COURSE_ID=999\r\n# keep me\r\n".encode())
    return env, glob


def test_dry_run_changes_nothing_and_prints_no_secret(paths, capsys):
    env, glob = paths
    before = env.read_bytes()
    assert cst.run(env, apply=False, replace=False) == 0
    assert env.read_bytes() == before and not glob.exists()
    assert TOKEN not in capsys.readouterr().out


def test_apply_moves_keys_keeps_course_id_and_crlf(paths, capsys):
    env, glob = paths
    assert cst.run(env, apply=True, replace=False) == 0
    out = env.read_bytes()
    assert out == b"CANVAS_COURSE_ID=999\r\n# keep me\r\n"
    g = glob.read_text()
    assert f"export CANVAS_API_TOKEN={TOKEN}" in g and f"export CANVAS_BASE_URL={URL}" in g
    assert "COURSE_ID" not in g.replace("CANVAS_COURSE_ID here is IGNORED", "")
    assert TOKEN not in capsys.readouterr().out
    assert _env_loader._global_values()[0]["CANVAS_API_TOKEN"] == TOKEN  # loader reads it
    if sys.platform != "win32":
        assert glob.stat().st_mode & 0o077 == 0


def test_failed_verification_leaves_everything_untouched(paths, monkeypatch):
    env, glob = paths
    monkeypatch.setattr(cst, "verify_token", lambda t, b: False)
    before = env.read_bytes()
    assert cst.run(env, apply=True, replace=False) == 1
    assert env.read_bytes() == before and not glob.exists()


def test_conflicting_global_value_refused_unless_replace(paths):
    env, glob = paths
    cst.write_global(glob, {"CANVAS_API_TOKEN": "other", "CANVAS_BASE_URL": URL})
    before = env.read_bytes()
    assert cst.run(env, apply=True, replace=False) == 2
    assert env.read_bytes() == before and "other" in glob.read_text()
    assert cst.run(env, apply=True, replace=True) == 0
    assert TOKEN in glob.read_text()


def test_idempotent_second_run_is_noop(paths):
    env, _ = paths
    assert cst.run(env, apply=True, replace=False) == 0
    assert cst.run(env, apply=True, replace=False) == 0


def test_windows_branch_uses_icacls(paths, monkeypatch):
    _, glob = paths
    calls = []
    monkeypatch.setattr(cst.sys, "platform", "win32")
    monkeypatch.setenv("USERNAME", "faculty")
    monkeypatch.setattr(cst.subprocess, "run",
                        lambda cmd, **k: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    note = cst.write_global(glob, {"CANVAS_API_TOKEN": TOKEN, "CANVAS_BASE_URL": URL})
    assert "icacls" in note and calls[0][0] == "icacls" and "faculty:F" in calls[0]


def test_loader_does_not_false_warn_on_windows(paths, monkeypatch):
    _, glob = paths
    cst.write_global(glob, {"CANVAS_API_TOKEN": TOKEN, "CANVAS_BASE_URL": URL})
    glob.chmod(0o666)
    monkeypatch.setattr(_env_loader.sys, "platform", "win32")
    assert not any("readable by other users" in p for p in _env_loader.global_config_problems())

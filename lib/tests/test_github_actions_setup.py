"""Tests for the secret-safe GitHub Actions setup helper."""

import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import github_actions_setup as setup  # noqa: E402


@pytest.fixture(autouse=True)
def no_global_config(monkeypatch):
    """Keep the developer's real ~/.canvas/config out of every test."""
    monkeypatch.setattr(setup, "_global_values", lambda: ({}, []))


def test_read_settings_selects_required_values_only(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        'CANVAS_API_TOKEN="secret-token"\n'
        "CANVAS_BASE_URL=https://canvas.example.edu\n"
        "CANVAS_COURSE_ID=12345\n"
        "UNRELATED=value\n",
        encoding="utf-8",
    )
    assert setup.read_settings(env) == {
        "CANVAS_API_TOKEN": "secret-token",
        "CANVAS_BASE_URL": "https://canvas.example.edu",
        "CANVAS_COURSE_ID": "12345",
    }


def test_read_settings_rejects_missing_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text("CANVAS_BASE_URL=https://canvas.example.edu\n", encoding="utf-8")
    with pytest.raises(ValueError, match="CANVAS_API_TOKEN"):
        setup.read_settings(env)


def test_dry_run_never_passes_values_to_gh(monkeypatch, capsys, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "CANVAS_API_TOKEN=secret-token\n"
        "CANVAS_BASE_URL=https://canvas.example.edu\n"
        "CANVAS_COURSE_ID=12345\n",
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(setup, "resolve_repo", lambda _: "owner/course")
    monkeypatch.setattr(setup, "_run_gh", lambda *args: calls.append(args))
    monkeypatch.setattr(sys, "argv", ["github_actions_setup.py", "--env", str(env)])
    assert setup.main() == 0
    assert calls == []
    output = capsys.readouterr().out
    assert "secret-token" not in output
    assert "canvas.example.edu" not in output


def test_apply_sends_values_as_stdin_and_not_argv(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "CANVAS_API_TOKEN=secret-token\n"
        "CANVAS_BASE_URL=https://canvas.example.edu\n"
        "CANVAS_COURSE_ID=12345\n",
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(setup, "resolve_repo", lambda _: "owner/course")
    monkeypatch.setattr(setup, "_run_gh", lambda args, value=None: calls.append((args, value)))
    monkeypatch.setattr(sys, "argv", [
        "github_actions_setup.py", "--env", str(env), "--apply", "--yes"
    ])
    assert setup.main() == 0
    assert calls == [
        (["secret", "set", "CANVAS_API_TOKEN", "--repo", "owner/course"], "secret-token"),
        (["secret", "set", "CANVAS_BASE_URL", "--repo", "owner/course"],
         "https://canvas.example.edu"),
        (["variable", "set", "CANVAS_COURSE_ID", "--repo", "owner/course"], "12345"),
    ]


def test_blank_env_values_fall_back_to_global_config(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("CANVAS_API_TOKEN=\nCANVAS_COURSE_ID=12345\n", encoding="utf-8")
    monkeypatch.setattr(setup, "_global_values", lambda: (
        {"CANVAS_API_TOKEN": "global-token", "CANVAS_BASE_URL": "https://canvas.example.edu"},
        [],
    ))
    assert setup.read_settings(env) == {
        "CANVAS_API_TOKEN": "global-token",
        "CANVAS_BASE_URL": "https://canvas.example.edu",
        "CANVAS_COURSE_ID": "12345",
    }


def test_course_env_wins_over_global_config(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "CANVAS_API_TOKEN=course-token\nCANVAS_BASE_URL=https://course.example.edu\n"
        "CANVAS_COURSE_ID=12345\n", encoding="utf-8")
    monkeypatch.setattr(setup, "_global_values", lambda: (
        {"CANVAS_API_TOKEN": "global-token", "CANVAS_BASE_URL": "https://global.example.edu"},
        [],
    ))
    assert setup.read_settings(env)["CANVAS_API_TOKEN"] == "course-token"


def test_course_id_never_comes_from_global_config(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("CANVAS_API_TOKEN=t\nCANVAS_BASE_URL=https://c.example.edu\n",
                   encoding="utf-8")
    monkeypatch.setattr(setup, "_global_values", lambda: ({"CANVAS_COURSE_ID": "999"}, []))
    with pytest.raises(ValueError, match="CANVAS_COURSE_ID"):
        setup.read_settings(env)


def test_dry_run_reports_origin_without_values(monkeypatch, capsys, tmp_path):
    env = tmp_path / ".env"
    env.write_text("CANVAS_COURSE_ID=12345\n", encoding="utf-8")
    monkeypatch.setattr(setup, "_global_values", lambda: (
        {"CANVAS_API_TOKEN": "global-token", "CANVAS_BASE_URL": "https://canvas.example.edu"},
        [],
    ))
    monkeypatch.setattr(setup, "resolve_repo", lambda _: "owner/course")
    monkeypatch.setattr(sys, "argv", ["github_actions_setup.py", "--env", str(env)])
    assert setup.main() == 0
    out = capsys.readouterr().out
    assert "CANVAS_API_TOKEN  <- ~/.canvas/config" in out
    assert "CANVAS_COURSE_ID  <- " + str(env) in out
    assert "global-token" not in out and "canvas.example.edu" not in out

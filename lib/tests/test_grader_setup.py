"""grader_setup.py — the grading on-ramp (#440)."""
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import grader_setup as gs  # noqa: E402


def test_grading_dir_check_only_writes_nothing(tmp_path):
    assert gs.step_grading_dir(tmp_path, apply=False)[1] == "todo"
    assert not (tmp_path / "grading").exists()


def test_grading_dir_apply_creates_an_ignored_folder_and_is_idempotent(tmp_path):
    assert gs.step_grading_dir(tmp_path, apply=True)[1] == "ok"
    gi = (tmp_path / "grading" / ".gitignore").read_text(encoding="utf-8")
    assert "*" in gi.splitlines()
    assert gs.step_grading_dir(tmp_path, apply=False)[1] == "ok"


def test_master_present_is_ok_without_touching_canvas(tmp_path, monkeypatch):
    (tmp_path / "grading").mkdir()
    (tmp_path / "grading" / ".deid_master.csv").write_text("deid_code,user_id\n")
    assert gs.step_master(tmp_path, apply=True)[1] == "ok"


def test_master_missing_check_only_is_todo(tmp_path):
    assert gs.step_master(tmp_path, apply=False)[1] == "todo"


def test_master_missing_without_credentials_needs_you(tmp_path, monkeypatch):
    import grader_fetch
    monkeypatch.setattr(grader_fetch, "_env_canvas", lambda _c: ("", "", ""))
    assert gs.step_master(tmp_path, apply=True)[1] == "needs you"


@pytest.mark.parametrize("built,expected", [("built", "ok"), ("failed", "needs you")])
def test_master_apply_reports_the_build_result(tmp_path, monkeypatch, built, expected):
    import grader_fetch
    monkeypatch.setattr(grader_fetch, "_env_canvas", lambda _c: ("t", "1", "https://x"))
    monkeypatch.setattr(grader_fetch, "ensure_deid_master", lambda *a: built)
    assert gs.step_master(tmp_path, apply=True)[1] == expected


def test_voice_is_optional_when_absent_and_ok_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(gs.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    assert gs.step_voice(tmp_path)[1] == "optional"
    (tmp_path / "grading").mkdir()
    (tmp_path / "grading" / gs.VOICE_FILE).write_text("voice")
    assert gs.step_voice(tmp_path)[1] == "ok"


def test_package_unapproved_needs_you_then_approved_ok(tmp_path):
    from capability_consent import record_approval
    assert gs.step_package(tmp_path)[1] == "needs you"
    record_approval(tmp_path, "grading", {"canvas_writers": []}, "instructor")
    assert gs.step_package(tmp_path)[1] == "ok"


def test_package_in_nested_layout_has_no_separate_approval(tmp_path):
    guardian = tmp_path / gs.NESTED_DIR / "lib" / "tools" / "grade_guardian.py"
    guardian.parent.mkdir(parents=True)
    guardian.write_text("")
    assert gs.step_package(tmp_path)[1] == "ok"


def _stub_steps(monkeypatch, **status):
    defaults = {"token": "ok", "hook": "ok", "zone2": "ok", "master": "ok", "package": "ok"}
    defaults.update(status)
    monkeypatch.setattr(gs, "step_token", lambda: ("Canvas token", defaults["token"], "d"))
    monkeypatch.setattr(gs, "step_hook", lambda r, a: ("Guardian hook", defaults["hook"], "d"))
    monkeypatch.setattr(gs, "step_zone2", lambda r: ("Zone-2", defaults["zone2"], "d"))
    monkeypatch.setattr(gs, "step_master", lambda r, a: ("De-id master", defaults["master"], "d"))
    monkeypatch.setattr(gs, "step_package", lambda r: ("Grading package", defaults["package"], "d"))


def test_run_ready_exits_zero(tmp_path, monkeypatch, capsys):
    _stub_steps(monkeypatch)
    assert gs.run(tmp_path, apply=True) == 0
    assert "Ready to grade." in capsys.readouterr().out


def test_run_blocked_exits_one_and_names_the_step(tmp_path, monkeypatch, capsys):
    _stub_steps(monkeypatch, token="needs you")
    assert gs.run(tmp_path, apply=True) == 1
    out = capsys.readouterr().out
    assert "needs you: Canvas token" in out and "Ready to grade" not in out


def test_run_pending_in_check_mode_is_not_ready_but_not_an_error(tmp_path, monkeypatch, capsys):
    _stub_steps(monkeypatch, master="todo")
    assert gs.run(tmp_path, apply=False) == 0
    out = capsys.readouterr().out
    assert "re-run with --apply" in out and "Ready to grade" not in out


def test_cb_init_grading_step_is_skipped_unless_requested(tmp_path, monkeypatch):
    import cb_init
    monkeypatch.setattr(gs, "run", lambda *a, **k: pytest.fail("must not run"))
    assert cb_init.step_15_grading(course_root=tmp_path, check_only=False, with_grading=False)


@pytest.mark.parametrize("check_only", [True, False])
def test_cb_init_grading_step_runs_setup_and_respects_check(tmp_path, monkeypatch, check_only):
    import cb_init
    seen = {}
    monkeypatch.setattr(gs, "run", lambda root, apply: seen.update(root=root, apply=apply) or 0)
    assert cb_init.step_15_grading(course_root=tmp_path, check_only=check_only, with_grading=True)
    assert seen == {"root": tmp_path, "apply": not check_only}

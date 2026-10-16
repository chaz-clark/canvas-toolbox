"""Tests for _challenge_dir_guard — issue #44 guard, flat-layout fix #392."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import _challenge_dir_guard as guard  # noqa: E402


def _fake_tools_dir(root: Path) -> Path:
    tools = root / "lib" / "tools"
    tools.mkdir(parents=True)
    return tools / "_challenge_dir_guard.py"


def _patch_file(monkeypatch, fake_file: Path):
    monkeypatch.setattr(guard, "__file__", str(fake_file))


def test_nested_layout_refuses_grading_inside_clone(tmp_path, monkeypatch):
    clone = tmp_path / "canvas-toolbox"
    _patch_file(monkeypatch, _fake_tools_dir(clone))
    with pytest.raises(SystemExit) as exc:
        guard.resolve_challenge_dir(str(clone / "grading" / "a1"))
    assert exc.value.code == guard.FERPA_GUARD_REFUSED_EXIT


def test_flat_layout_allows_grading_at_course_root(tmp_path, monkeypatch):
    (tmp_path / ".canvas-toolbox").mkdir()
    _patch_file(monkeypatch, _fake_tools_dir(tmp_path))
    out = guard.resolve_challenge_dir(str(tmp_path / "grading" / "a1"))
    assert out == (tmp_path / "grading" / "a1").resolve()


def test_flat_layout_still_refuses_hidden_clone(tmp_path, monkeypatch):
    (tmp_path / ".canvas-toolbox").mkdir()
    _patch_file(monkeypatch, _fake_tools_dir(tmp_path))
    with pytest.raises(SystemExit) as exc:
        guard.resolve_challenge_dir(str(tmp_path / ".canvas-toolbox" / "grading" / "a1"))
    assert exc.value.code == guard.FERPA_GUARD_REFUSED_EXIT

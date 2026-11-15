"""Unit tests — module_settings_sync's write gates.

The tool changes what students must do to move on, so the gates are what is under test:
the course guard runs on every invocation (write mode only with --apply, and --allow-enrolled
is passed through, never assumed); without --yes the APPLY prompt still decides; --yes skips
only the prompt, never the guard; a plain run stays read-only.
"""
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import module_settings_sync as mss  # noqa: E402


@pytest.fixture
def run(monkeypatch):
    seen = {"guard": [], "applied": 0, "prompted": 0}
    monkeypatch.setattr(mss, "CANVAS_BASE_URL", "https://canvas.example")
    monkeypatch.setattr(mss, "CANVAS_API_TOKEN", "fake")
    monkeypatch.setattr(mss, "build_plan", lambda *a: {"plan": True})
    monkeypatch.setattr(mss, "print_plan", lambda r: 3)
    monkeypatch.setattr(mss, "apply_plan", lambda r: seen.__setitem__("applied", seen["applied"] + 1))
    monkeypatch.setattr(mss.guard, "enforce", lambda **kw: seen["guard"].append(kw))

    def go(argv, typed=""):
        def fake_input(prompt):
            seen["prompted"] += 1
            return typed
        monkeypatch.setattr("builtins.input", fake_input)
        monkeypatch.setattr(sys, "argv", ["module_settings_sync.py", "--target", "123", *argv])
        mss.main()
        return seen
    return go


def test_plain_run_is_read_only_and_guarded_in_read_mode(run):
    s = run([])
    assert s["applied"] == 0 and s["prompted"] == 0
    assert s["guard"][0]["mode"] == "read" and s["guard"][0]["course_id"] == "123"


def test_apply_without_yes_still_needs_typed_APPLY(run):
    s = run(["--apply"], typed="nope")
    assert s["prompted"] == 1 and s["applied"] == 0


def test_apply_with_typed_APPLY_writes(run):
    s = run(["--apply"], typed="APPLY")
    assert s["applied"] == 1 and s["guard"][0]["mode"] == "write"


def test_yes_skips_only_the_prompt_never_the_guard(run):
    s = run(["--apply", "--yes"])
    assert s["prompted"] == 0 and s["applied"] == 1
    assert s["guard"][0]["mode"] == "write" and s["guard"][0]["allow_override"] is False


def test_allow_enrolled_is_passed_through_not_assumed(run):
    s = run(["--apply", "--yes", "--allow-enrolled"])
    assert s["guard"][0]["allow_override"] is True


def test_guard_refusal_stops_before_any_write(run, monkeypatch):
    def refuse(**kw):
        raise SystemExit(3)
    monkeypatch.setattr(mss.guard, "enforce", refuse)
    monkeypatch.setattr(mss, "apply_plan", lambda r: pytest.fail("wrote after the guard refused"))
    with pytest.raises(SystemExit):
        run(["--apply", "--yes"])

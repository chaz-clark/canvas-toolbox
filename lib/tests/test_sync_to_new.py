"""Regression test — sync_to_new.py's assignment-group create payload (#351).

Caught by chance while sandbox-testing an unrelated tool (canvas_shell_create.py):
create_assignment_group() wrapped its payload in an "assignment_group" key, matching
the convention every other creation function in this file uses (modules, pages,
assignments). Canvas's Assignment Groups API is the one endpoint that doesn't accept
that shape — a wrapped POST returns 200 but silently creates a group named
"Assignments" with group_weight 0, ignoring every field sent. Untested until now.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import sync_to_new as stn  # noqa: E402


def test_create_assignment_group_sends_flat_payload_not_wrapped(monkeypatch):
    seen = {}

    def fake_post(url, payload, token):
        seen["payload"] = payload
        return {"success": True, "data": {"id": 1, **payload}}

    monkeypatch.setattr(stn, "_post", fake_post)
    group_data = {"name": "Homework", "group_weight": 40.0, "position": 1}
    stn.create_assignment_group("https://x", "1", group_data, "tok")

    assert seen["payload"] == group_data
    assert "assignment_group" not in seen["payload"]


# --- course guard + .env loading actually wired (regression) -------------------

def test_load_env_and_course_guard_are_the_real_ones_not_import_fallbacks():
    """sync_to_new imported two names canvas_course_guard never had, and the except
    ImportError fallback silently swapped in a no-op load_env and a no-op guard — so
    .env was never loaded and the course-safety guard never ran."""
    import _env_loader
    import canvas_course_guard
    assert stn.load_env is _env_loader.load_env
    assert stn._course_guard is canvas_course_guard.enforce


def test_main_runs_the_guard_in_read_mode_for_preview_and_write_mode_for_apply(monkeypatch):
    calls = []
    monkeypatch.setattr(stn, "_load_config", lambda: ("https://x", "9", "tok"))
    monkeypatch.setattr(stn, "_course_guard",
                        lambda base, headers, cid, mode: calls.append((cid, mode)))
    monkeypatch.setattr(stn, "load_course_content", lambda *a, **k: {})   # main stops here
    for argv, mode in ((["sync_to_new.py"], "read"), (["sync_to_new.py", "--apply"], "write")):
        monkeypatch.setattr(sys, "argv", argv)
        assert stn.main() == 1
        assert calls[-1] == ("9", mode)


def test_main_does_not_ask_a_human_to_type_yes(monkeypatch):
    """The old stub made every target 'PRODUCTION' and blocked on input()."""
    monkeypatch.setattr(stn, "_load_config", lambda: ("https://x", "9", "tok"))
    monkeypatch.setattr(stn, "_course_guard", lambda *a, **k: None)
    monkeypatch.setattr(stn, "load_course_content", lambda *a, **k: {})
    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(AssertionError("prompted")))
    monkeypatch.setattr(sys, "argv", ["sync_to_new.py"])
    assert stn.main() == 1

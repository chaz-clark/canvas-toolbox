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

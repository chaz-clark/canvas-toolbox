"""Tests for the PreToolUse hook that blocks an AI agent from reaching Canvas.

The hook is the SECOND enforcement layer. The first is structural: the Canvas API
token lives in a file the agent is denied, so a Canvas tool it runs has no
credential and Canvas returns 401. The hook makes the refusal loud, explains the
workflow, and appends to an audit log a reviewer can inspect.

The matcher must key on the toolkit ENTRYPOINTS and the token file — never on any
string that merely contains their names. A hook that fires on harmless commands
is one the operator learns to disable, and then there is neither a hook nor an
honest story to tell.

The hook ships in scaffold/ (adopters copy it to .claude/hooks/), so it is loaded
from there.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

HOOK = (
    Path(__file__).resolve().parents[2]
    / "scaffold" / "claude" / "hooks" / "block_canvas.py"
)
spec = importlib.util.spec_from_file_location("block_canvas", HOOK)
block_canvas = importlib.util.module_from_spec(spec)
sys.modules["block_canvas"] = block_canvas
spec.loader.exec_module(block_canvas)

is_canvas_command = block_canvas.is_canvas_command


@pytest.mark.parametrize(
    "cmd",
    [
        "uv run python lib/tools/canvas_sync.py --pull",
        "uv run python lib/tools/course_audit.py --course-id 111111",
        "uv run python lib/tools/clo_quality_audit.py",
        "uv run python lib/tools/grader_push.py",
        "uv run python lib/tools/blueprint_sync.py",
        "uv run python lib/tools/canvas_run.py pull",
        "python lib/tools/apply_sas_accommodations.py",
        "pwsh -File bin/canvas-run.ps1 pull",
        "./bin/canvas-run.sh pull",
        "curl -H 'Authorization: Bearer x' https://school.instructure.com/api/v1/courses",
        "Invoke-WebRequest https://school.instructure.com/api/v1/courses/111111",
        "cat .env.canvas",
        "Get-Content .env.canvas",
        # No leading path — an entrypoint invoked from inside its own directory.
        "canvas_sync.py --push",
        # The faculty launcher is a front-end for the gate. An agent that runs it
        # reaches Canvas BY PROXY. A convenience wrapper around a gated tool
        # silently widens the gate unless the block list learns about it — this is
        # the boundary's standing failure mode, so it gets explicit tests.
        "powershell -File bin/canvas-menu.ps1",
        "pwsh -NoProfile -File bin/canvas-menu.ps1",
        "./bin/canvas-menu.sh",
        "bash bin/canvas-menu.sh",
        "cmd /c bin\\Canvas.cmd",
        "./bin/Canvas.command",
        "start bin/Canvas.cmd",
    ],
)
def test_canvas_touching_commands_are_blocked(cmd):
    assert is_canvas_command(cmd) is True


@pytest.mark.parametrize(
    "cmd",
    [
        "uv run pytest lib/tests -v",
        "git status",
        "ls lib/tools",
        "cat .env.example",
        "grep -rn 'canvas' docs/",
        "git log --oneline -5",
        "uv run ruff check lib/tools",
    ],
)
def test_local_only_commands_are_allowed(cmd):
    assert is_canvas_command(cmd) is False


# Regression: the matcher keys on the ENTRYPOINT, not on any string containing
# its name. Each of these is a local read — no network, no credential — and each
# was blocked before the guards were added.
@pytest.mark.parametrize(
    "cmd",
    [
        # The gate's own audit log — the artifact a reviewer inspects.
        "cat .canvas/canvas-run.log",
        "tail -20 .canvas/canvas-run.log",
        "cat .canvas/claude-canvas-block.log",
        # The boundary's own unit tests, run by name.
        "uv run pytest lib/tests/test_canvas_run.py",
        "uv run pytest lib/tests/test_block_canvas_hook.py",
        "uv run pytest lib/tests/test_clo_quality_audit.py",
        "uv run pytest lib/tests/test_blueprint_orphan_pages_plan.py",
        # The audit REPORT is a local file; only the audit TOOL is blocked.
        "cat audit.md",
        "cat .canvas/audit/111111.json",
    ],
)
def test_local_reads_of_canvas_named_artifacts_are_allowed(cmd):
    assert is_canvas_command(cmd) is False


def test_direct_http_to_canvas_is_blocked_even_without_the_toolkit():
    """The toolkit is not the only way to reach Canvas."""
    assert is_canvas_command("wget https://school.instructure.com/api/v1/courses") is True

#!/usr/bin/env python3
"""PreToolUse hook — block Claude Code from reaching Canvas.

WORKED EXAMPLE for split-agent mode (see docs/split-agent-access.md). Copy to
`.claude/hooks/block_canvas.py` in your course repo, alongside the
`.claude/settings.json` in scaffold/claude/.

This example blocks CLAUDE and routes Canvas access to an approved agent. If
your institution approved the other way around, the same structure inverts —
the gate itself (lib/tools/canvas_run.py) names no vendor.

This hook is the SECOND enforcement layer. The FIRST is structural: the Canvas
API token lives in `.env.canvas`, which the blocked agent is denied, so a Canvas
tool it runs has no credential and Canvas returns 401 unauthenticated. The hook
makes the refusal loud, explains the alternative, and appends to an audit log an
institutional reviewer can inspect — positive evidence of enforcement, rather
than an absence of records.

Exit 2 = block the tool call and show stderr to the agent.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from pathlib import Path

LOG_PATH = Path(".canvas") / "claude-canvas-block.log"

# Canvas-touching toolkit entrypoints, plus the gate itself (the blocked agent
# must not launder a call through it) and the token file.
#
# NOTE the matcher keys on real entrypoints and the token file — NOT on the
# substring "canvas". `grep -rn 'canvas' docs/` must stay allowed. A hook that
# fires on harmless commands is a hook the operator learns to disable, and then
# you have neither the hook nor the honesty.
BLOCKED = re.compile(
    r"""
      canvas_sync\.py
    | canvas_run\.py
    | canvas-run(\.ps1|\.sh)?
    | canvas_api_tool\.py
    | canvas_quiz_questions\.py
    | course_mirror\.py
    | blueprint_\w+\.py
    | grader_(fetch|push|import|export)\.py
    | apply_\w+\.py
    | student_\w+_(accommodation|extension)\.py
    | build_deid_master\.py
    | \w*_audit\.py
    | course_quality_check\.py
    | \.env\.canvas
    """,
    re.VERBOSE,
)

# Direct HTTP to a Canvas host, bypassing the toolkit entirely.
# Adjust the host pattern if your Canvas is self-hosted.
DIRECT_HTTP = re.compile(
    r"(curl|wget|http|Invoke-WebRequest|Invoke-RestMethod)\b.*instructure\.com",
    re.IGNORECASE,
)


def is_canvas_command(command: str) -> bool:
    """True if this shell command could reach Canvas or read the token."""
    return bool(BLOCKED.search(command) or DIRECT_HTTP.search(command))


def log(command: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp}\tBLOCKED\t{command}\n")


REFUSAL = """\
BLOCKED by the split-agent Canvas policy.

This agent does not access Canvas in this repo. Canvas access runs through the
approved agent, via the gate:

    uv run python lib/tools/canvas_run.py pull

Your half of the workflow is everything local: the course mirror, drafts,
audits already written to disk, docs and plans.

(Note: this command would have failed anyway — the Canvas token is not in any
file this agent can read, and Canvas returns 401. See
docs/split-agent-access.md.)
"""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # malformed input — never block on our own bug

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "")

    if not command or not is_canvas_command(command):
        return 0

    log(command)
    print(REFUSAL, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

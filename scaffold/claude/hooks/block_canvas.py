#!/usr/bin/env python3
"""PreToolUse hook — block Claude from reaching Canvas.

WORKED EXAMPLE. Copy to `.claude/hooks/block_canvas.py` in your course repo,
alongside the `.claude/settings.json` in scaffold/claude/.
See docs/canvas-access-boundary.md.

For institutions that have not approved an AI tool for authenticated access to
their Canvas instance. Canvas access becomes `lib/tools/canvas_run.py` — a plain
script the INSTRUCTOR runs. The AI works only on local files and holds no Canvas
credential.

This example blocks Claude Code specifically, but the pattern is agent-neutral:
`canvas_run.py` names no vendor, so the same structure works for whichever agent
your institution needs to keep away from Canvas.

This hook is the SECOND enforcement layer. The first is structural: the Canvas
API token lives in `.env.canvas`, which Claude is denied, so a Canvas tool run
by Claude has no credential and Canvas returns 401. The hook makes the refusal
loud, explains what to do instead, and appends to an audit log an IT reviewer
can inspect — positive evidence of enforcement, rather than an absence of
records.

Exit 2 = block the tool call and show stderr to Claude.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from pathlib import Path

LOG_PATH = Path(".canvas") / "claude-canvas-block.log"

# Canvas-touching toolkit entrypoints, plus the gate itself (the agent must not
# launder a call through it) and the token file. Keyed on real entrypoints —
# NOT on the substring "canvas" — so that a grep over the docs is not blocked.
#
# Two guards keep the match on the ENTRYPOINT rather than on any string that
# merely CONTAINS its name. Both exist because the hook fired on harmless local
# reads, and a hook that fires on harmless commands is one the operator learns to
# disable — at which point you have neither the hook nor an honest story to tell:
#
#   (?<![\w-])  the name must not be the tail of a longer identifier. Without it,
#               `pytest lib/tests/test_canvas_run.py` matched `canvas_run.py` —
#               the gate's own unit tests could not be run by name.
#   (?!test_)   `\w*_audit\.py` is deliberately open-prefixed (course_audit,
#               clo_quality_audit, ...), so on its own it also swallowed
#               `test_clo_quality_audit.py`.
#
# The shim extension is likewise REQUIRED: a bare `canvas-run` also matched
# `.canvas/canvas-run.log` — so reading the gate's own audit log, the artifact an
# IT reviewer inspects, was refused as though it were a Canvas call.
BLOCKED = re.compile(
    r"""
    (?<![\w-]) (?!test_) (?:
      canvas_sync\.py
    | canvas_run\.py
    | canvas-run\.(ps1|sh)
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
    )
    """,
    re.VERBOSE,
)

# Direct HTTP to a Canvas host, bypassing the toolkit entirely.
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
BLOCKED by the Canvas access policy.

No AI tool accesses Canvas in this repo. Canvas access is a plain script, run by
the instructor:

    uv run python lib/tools/canvas_run.py pull

Ask the instructor to run it. Then read the results from disk: the mirror in
course/, and the audit report in audit.md / .canvas/audit/.

Your half of the workflow is everything local — the course mirror, drafts,
audits already written to disk, docs and plans. That is where the work is, and
none of it requires Canvas access.

(Note: this command would have failed anyway — the Canvas token is not in any
file you can read, and Canvas returns 401. See docs/canvas-access-boundary.md.)
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

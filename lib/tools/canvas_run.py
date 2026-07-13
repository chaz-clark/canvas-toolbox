#!/usr/bin/env python3
"""canvas_run.py — the split-agent Canvas gate.

WHY THIS EXISTS
  Some institutions approve one AI vendor for access to university systems and
  not another — often with no judgment implied about either tool, just an
  approval queue that hasn't finished.

  That collides with how this toolkit is built. It assumes ONE agent does
  everything: the same agent that reasons about course design also runs
  `canvas_sync.py --pull`, which authenticates to Canvas. There is no seam
  between "thinking about the course" and "calling the Canvas API" — so a policy
  that cuts between those two activities forces an all-or-nothing choice.

  This tool cuts the seam. It lets an operator split the workflow at the network
  boundary: an APPROVED agent runs this gate to talk to Canvas, while an agent
  that is NOT approved for Canvas works only on the local mirror and never
  authenticates.

  The gate is deliberately AGENT-NEUTRAL. It names no vendor. It enforces "only
  this process holds the token"; which agent sits on which side is a matter of
  local configuration, so the same structure serves the opposite institutional
  decision.

HOW IT ENFORCES THAT
  1. This is the ONLY process that reads the token file (default `.env.canvas`).
     The token is deliberately NOT in `.env`. Every toolkit tool reads the token
     via os.environ.get("CANVAS_API_TOKEN"), and python-dotenv's load_dotenv()
     does not override variables already in the process environment — so the gate
     can inject it and every tool honors it, while a tool invoked OUTSIDE the
     gate finds no token in any file it loads.

     The block is therefore STRUCTURAL, not merely policy. Remove every hook and
     ignore every instruction, and the non-approved agent still cannot reach
     Canvas: it has no credential, and Canvas answers 401 unauthenticated.

  2. Default-deny. Only named subcommands resolve. The caller never composes a
     raw `python lib/tools/...` command line, so there is no argument-injection
     surface to police.

  3. Writes are gated on an explicit `--confirm-course <id>` matching the target
     course, so an agent cannot push to a live course on inference alone. On a
     live course, a grading change re-scores real student work the moment it
     lands — Canvas has no draft state.

  4. Every decision, allow or refuse, is appended to `.canvas/canvas-run.log`.

HONEST LIMITS
  This is a guardrail against drift and accident, not a defense against an
  adversarial agent with shell access. A determined agent — or human — with a
  shell can defeat any client-side control. What this DOES guarantee is narrower
  and verifiable: the credential is not present, and refusals are logged.

  An institution that needs a hard guarantee should scope the control at the
  Canvas end: issue the API token to the approved workflow only, and rotate it.

  See docs/split-agent-access.md.

SETUP
  1. Move CANVAS_API_TOKEN out of `.env` into `.env.canvas` (see
     scaffold/env.canvas.example). Gitignore it — and verify with
     `git check-ignore -v .env.canvas` BEFORE writing the secret to disk.
  2. Restrict the non-approved agent (see scaffold/claude/ for a worked example).
  3. Point the approved agent at this gate.

USAGE
  uv run python lib/tools/canvas_run.py pull
  uv run python lib/tools/canvas_run.py audit
  uv run python lib/tools/canvas_run.py push --confirm-course <course_id>
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from _env_loader import load_env
except ImportError:  # pragma: no cover - python-dotenv absent
    def load_env():
        return None


class GateRefusal(Exception):
    """The gate declined to run the requested command."""


# Read-only. No confirmation required.
FREE: dict[str, list[str]] = {
    "pull": ["lib/tools/canvas_sync.py", "--pull"],
    "status": ["lib/tools/canvas_sync.py", "--status"],
    "audit": [
        "lib/tools/course_audit.py",
        "--full",
        "--course-id",
        "{course_id}",
        "--report",
        "audit.md",
    ],
    "quality": ["lib/tools/course_quality_check.py"],
}

# Writes to Canvas. Require --confirm-course matching the target course.
GATED: dict[str, list[str]] = {
    "push": ["lib/tools/canvas_sync.py", "--push"],
}

TOKEN_FILE = os.environ.get("CANVAS_TOKEN_FILE", ".env.canvas")
LOG_PATH = Path(".canvas") / "canvas-run.log"


def resolve_command(
    subcommand: str, *, confirm_course: str | None, course_id: str
) -> list[str]:
    """Map a named subcommand to exactly one toolkit invocation.

    Raises GateRefusal for anything unlisted, and for a gated (write) command
    whose --confirm-course is absent or does not match the target course.
    """
    if subcommand in FREE:
        template = FREE[subcommand]
    elif subcommand in GATED:
        if confirm_course is None:
            raise GateRefusal(
                f"'{subcommand}' writes to Canvas. Re-run with "
                f"--confirm-course {course_id} to proceed."
            )
        if confirm_course != course_id:
            raise GateRefusal(
                f"--confirm-course {confirm_course} does not match the target "
                f"course {course_id}. Refusing."
            )
        template = GATED[subcommand]
    else:
        allowed = ", ".join(sorted([*FREE, *GATED]))
        raise GateRefusal(
            f"'{subcommand}' is not on the allowlist. Allowed: {allowed}"
        )

    return [part.replace("{course_id}", course_id) for part in template]


def read_token(token_file: str = TOKEN_FILE) -> str:
    """Read CANVAS_API_TOKEN from the isolated token file."""
    path = Path(token_file)
    if not path.exists():
        raise GateRefusal(
            f"Token file {token_file} not found. It holds CANVAS_API_TOKEN and "
            f"is the only file this gate reads. See docs/split-agent-access.md."
        )
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("CANVAS_API_TOKEN="):
            token = line.split("=", 1)[1].strip().strip('"').strip("'")
            if token:
                return token
    raise GateRefusal(f"{token_file} does not define a non-empty CANVAS_API_TOKEN.")


def log(verdict: str, subcommand: str, detail: str = "") -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp}\t{verdict}\t{subcommand}\t{detail}\n")


def main() -> int:
    load_env()  # brings in CANVAS_BASE_URL / CANVAS_COURSE_ID (non-secret)

    parser = argparse.ArgumentParser(
        prog="canvas_run.py",
        description=(
            "Split-agent Canvas gate — the only process that holds the token."
        ),
    )
    parser.add_argument(
        "subcommand", help=f"One of: {', '.join(sorted([*FREE, *GATED]))}"
    )
    parser.add_argument(
        "--confirm-course",
        metavar="ID",
        help="Required for write subcommands; must match the target course id.",
    )
    args = parser.parse_args()

    course_id = os.environ.get("CANVAS_COURSE_ID", "")
    if not course_id:
        print("ERROR: CANVAS_COURSE_ID is not set in .env.", file=sys.stderr)
        return 2

    try:
        argv = resolve_command(
            args.subcommand,
            confirm_course=args.confirm_course,
            course_id=course_id,
        )
        token = read_token()
    except GateRefusal as exc:
        log("REFUSED", args.subcommand, str(exc))
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["CANVAS_API_TOKEN"] = token

    log("ALLOWED", args.subcommand, " ".join(argv))
    print(f"canvas-run: {args.subcommand} -> {' '.join(argv)}", file=sys.stderr)

    completed = subprocess.run([sys.executable, *argv], env=env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

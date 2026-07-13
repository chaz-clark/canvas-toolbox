#!/usr/bin/env python3
"""canvas_run.py — the Canvas access boundary. A plain CLI. No AI involved.

WHY THIS EXISTS
  Campus IT has not approved AI tools for authenticated access to the university
  Canvas instance. That policy is easy to honor once you notice that NOTHING at
  the Canvas boundary needs intelligence: pulling a course is fetch-and-write-
  files, auditing it is read-and-write-a-report, pushing is post. It is
  deterministic work, and a script does it.

  So: **no AI tool touches Canvas. This script does, run by the instructor.**
  Claude Code works only on the local mirror — reading the files this script
  writes — and holds no Canvas credential.

  The audit output is a FILE. That is the whole trick. An AI agent never needs to
  sit at the network boundary to help with course design; it just reads the file
  the script produced.

HOW THE BOUNDARY IS ENFORCED
  1. This is the ONLY process that reads the token file (default `.env.canvas`).
     The token is deliberately NOT in `.env`. Every toolkit tool reads the token
     via os.environ.get("CANVAS_API_TOKEN"), and python-dotenv's load_dotenv()
     does not override the process environment — so this script can inject it and
     every tool honors it, while a tool invoked OUTSIDE this script finds no token
     in any file it loads.

     The block is therefore STRUCTURAL, not policy. An AI agent denied
     `.env.canvas` has no credential, and Canvas answers 401 unauthenticated.
     Enforcement does not depend on the agent's cooperation.

  2. Default-deny: only named subcommands resolve. No raw command-line
     composition, so there is no argument-injection surface.

  3. Writes are gated on an explicit `--confirm-course <id>` matching the target
     course. On a live course a grading change re-scores real student work the
     moment it lands — Canvas has no draft state.

  4. Every decision is appended to `.canvas/canvas-run.log`.

HONEST LIMITS
  A guardrail against drift and accident, not a sandbox. Anyone with shell access
  can bypass any client-side control. What IS guaranteed: the credential is not
  present in any file the AI tool can read, and every refusal is logged.
  See docs/canvas-access-boundary.md.

USAGE — run this yourself. It is a script; it does not need an agent.
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
            f"is the only file this gate reads. "
            f"See docs/canvas-access-boundary.md."
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
        description="Canvas access boundary — the only process that holds the token.",
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

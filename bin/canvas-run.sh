#!/bin/sh
# Canvas access boundary — POSIX shim. A plain CLI; no AI involved.
#
# The real logic (allowlist, write-confirmation, token injection, audit log)
# lives in lib/tools/canvas_run.py. This file only resolves the repo root and
# forwards arguments, so there is one place to review the security decisions.
#
# See docs/canvas-access-boundary.md.
set -eu
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"
exec uv run python lib/tools/canvas_run.py "$@"

# Split-agent Canvas gate — Windows shim.
#
# The real logic (allowlist, write-confirmation, token injection, audit log)
# lives in lib/tools/canvas_run.py. This file only resolves the repo root and
# forwards arguments, so there is one place to review the security decisions.
#
# See docs/split-agent-access.md.
#Requires -Version 5.1
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    uv run python lib/tools/canvas_run.py @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}

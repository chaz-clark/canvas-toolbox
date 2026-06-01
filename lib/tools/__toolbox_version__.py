"""Single source of truth for the canvas-toolbox version.

Canonical scheme is the v0.x semver line (matches `git describe` and the
AGENTS.md Active Context). A separate `v1.x` git tag series exists in
history; it is NOT part of the v0.x line and is not maintained — treat v0.x
as canonical going forward.

Keep `__version__` in lockstep with the annotated git tag (`vX.Y.Z`) at
release. Downstream repos that vendor `lib/tools/` can print it via any
primary sync tool's `--version` flag to detect drift from upstream:

    uv run python canvas_toolbox/lib/tools/canvas_sync.py --version

If the printed version is behind the upstream tag, re-sync with
`cd canvas_toolbox && git pull` — never patch the vendored copy in place.
"""

__version__ = "0.27.2"

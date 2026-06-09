"""Single source of truth for the canvas-toolbox version.

Canonical version lives in the repo's [project].version field of
`pyproject.toml`. This module exposes it as `__version__` for the existing
imports (`from __toolbox_version__ import __version__`) across all tools.

Resolution order (first match wins):
  1. `importlib.metadata.version("canvas-toolbox")` — works when the package
     is installed (e.g. `uv pip install -e .` or downstream consumer's venv).
  2. Parse the local `pyproject.toml` directly — works when the script is
     run from source via `uv run python lib/tools/<tool>.py`, which is the
     dominant operator pattern.
  3. Hardcoded fallback `"0.0.0+unknown"` — only if both above fail (vendored
     copy missing pyproject.toml; manual file copy out of repo).

Canonical scheme is the v0.x semver line (matches `git describe` and the
AGENTS.md Active Context). A separate `v1.x` git tag series exists in
history; it is NOT part of the v0.x line and is not maintained — treat v0.x
as canonical going forward.

Downstream repos that vendor `lib/tools/` can print the version via any
primary sync tool's `--version` flag to detect drift from upstream:

    uv run python canvas_toolbox/lib/tools/canvas_sync.py --version

If the printed version is behind the upstream tag, re-sync with
`cd canvas_toolbox && git pull` — never patch the vendored copy in place.
"""
from __future__ import annotations

from importlib.metadata import version as _pkg_version, PackageNotFoundError


def _read_pyproject_version() -> str | None:
    """Parse the version out of `pyproject.toml` without requiring `tomllib`
    (avoids a stdlib version dependency mismatch in vendored consumers).
    Returns None if pyproject.toml isn't found or doesn't contain a
    parseable `version = "X.Y.Z"` line."""
    import re
    from pathlib import Path
    # `__file__` is .../lib/tools/__toolbox_version__.py — pyproject is two dirs up.
    pyproject = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        text = pyproject.read_text(encoding="utf-8")
    except Exception:
        return None
    m = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else None


try:
    __version__ = _pkg_version("canvas-toolbox")
except PackageNotFoundError:
    __version__ = _read_pyproject_version() or "0.0.0+unknown"

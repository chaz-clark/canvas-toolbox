"""
Shared fixtures for canvas_toolbox regression tests.
All tests run against CANVAS_SANDBOX_ID — never the production course.
Requires CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_SANDBOX_ID in .env or environment.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from dotenv import dotenv_values

# ---------------------------------------------------------------------------
# Load env — .env file takes precedence, then environment
# ---------------------------------------------------------------------------
_env = {**os.environ, **dotenv_values(".env")}

CANVAS_API_TOKEN = _env.get("CANVAS_API_TOKEN", "")
CANVAS_BASE_URL = _env.get("CANVAS_BASE_URL", "").rstrip("/")
CANVAS_SANDBOX_ID = _env.get("CANVAS_SANDBOX_ID", "")

if not CANVAS_BASE_URL.startswith("http"):
    CANVAS_BASE_URL = "https://" + CANVAS_BASE_URL

MISSING = [k for k, v in {
    "CANVAS_API_TOKEN": CANVAS_API_TOKEN,
    "CANVAS_BASE_URL": CANVAS_BASE_URL,
    "CANVAS_SANDBOX_ID": CANVAS_SANDBOX_ID,
}.items() if not v]


def pytest_configure(config):
    """Poka-yoke: fail the session fast + loud when the tests run under an
    interpreter that lacks the repo's dependencies.

    The recurring foot-gun: `python -m pytest` uses the SYSTEM interpreter, which
    has none of canvas-toolbox's deps. The failure surfaces as a confusing
    `ModuleNotFoundError: markdownify` deep inside a `canvas_sync --pull`
    subprocess (three separate incidents), with no hint that the real fix is to
    run through uv. Catch it here, at session start, with the recovery hint.
    `markdownify` is the canary — a declared dependency unlikely to be installed
    system-wide, so its absence means "wrong environment."
    """
    import importlib.util
    if importlib.util.find_spec("markdownify") is None:
        raise pytest.UsageError(
            f"canvas-toolbox test dependencies are not importable under this "
            f"interpreter:\n    {sys.executable}\n\n"
            f"You're almost certainly running bare `python -m pytest`. Run the "
            f"tests through uv so the project venv (with all deps) is used:\n\n"
            f"    uv run pytest\n\n"
            f"If the venv is stale, run `uv sync` first."
        )


def _skip_if_sandbox_unset():
    """Skip the calling test if Canvas sandbox env vars aren't set.

    Called per-fixture, NOT at module load (issue caught in v0.54.0 CI:
    a module-level `pytest.skip(allow_module_level=True)` killed the
    WHOLE test collection — including pure-logic unit tests that don't
    need Canvas at all — when running on remote CI without creds).
    Sprint tests reference the fixtures below; unit tests don't, so
    they're unaffected by this gate."""
    if MISSING:
        pytest.skip(
            f"Sandbox env vars not set: {', '.join(MISSING)} — sprint test skipped",
            allow_module_level=False,
        )


# ---------------------------------------------------------------------------
# Fixtures (gated on Canvas sandbox env vars)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sandbox_env():
    """Environment dict with CANVAS_COURSE_ID pointed at the sandbox."""
    _skip_if_sandbox_unset()
    env = dict(_env)
    env["CANVAS_COURSE_ID"] = CANVAS_SANDBOX_ID
    return env


@pytest.fixture(scope="session")
def sandbox_pull(sandbox_env, tmp_path_factory):
    """Run a full --pull against the sandbox once per session. Returns index."""
    result = subprocess.run(
        [sys.executable, "lib/tools/canvas_sync.py", "--pull", "--quiet"],
        env=sandbox_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Sandbox pull failed:\n{result.stderr}"
    index = json.loads(Path(".canvas/index.json").read_text())
    return index


@pytest.fixture(scope="session")
def canvas_headers():
    _skip_if_sandbox_unset()
    return {
        "Authorization": f"Bearer {CANVAS_API_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def canvas_get(path: str) -> dict:
    """GET from Canvas API. Returns parsed JSON."""
    import requests
    url = f"{CANVAS_BASE_URL}/api/v1{path}"
    r = requests.get(url, headers={
        "Authorization": f"Bearer {CANVAS_API_TOKEN}",
    })
    r.raise_for_status()
    return r.json()

"""Tests for the root Agent Plugins manifest (v2, #317 Phase 5).

Phase 5's gate requires plugin updates to "require a version bump" — that only
means something if plugin.json's version can't silently drift from the toolkit's
actual version. This pins the two together so a release that bumps one without
the other fails here instead of shipping a stale or premature plugin version.
"""
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import package_validate as pv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PLUGIN_JSON = REPO_ROOT / "plugin.json"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_plugin_json_validates_against_the_vendored_schema():
    document, load_issues = pv._load_json(PLUGIN_JSON)
    assert load_issues == []
    schema, schema_issues = pv.load_schema(pv.PLUGIN_SCHEMA)
    assert schema_issues == []
    assert pv.schema_issues(document, schema, "plugin.json") == []


def test_plugin_json_version_matches_pyproject_toml():
    plugin = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    pyproject_version = re.search(
        r'^version = "([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.MULTILINE
    ).group(1)
    assert plugin["version"] == pyproject_version, (
        "plugin.json's version must move with pyproject.toml's — otherwise a "
        "capability or content change can ship without the version bump a plugin "
        "consumer relies on to detect an update"
    )

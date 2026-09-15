"""Tests for the v2 runtime-neutral package manifest validator."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import package_validate as pv  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "package_manifests"


def _schema(path: Path) -> dict:
    schema, issues = pv.load_schema(path)
    assert issues == []
    assert schema is not None
    return schema


def _write_valid_tree(root: Path) -> dict:
    (root / "agent-packages/example").mkdir(parents=True)
    (root / "agent-packages/example/AGENT.md").write_text("# Synthetic agent\n", encoding="utf-8")
    (root / "skills/fixture-skill").mkdir(parents=True)
    (root / "skills/fixture-skill/SKILL.md").write_text(
        "---\nname: fixture-skill\ndescription: Synthetic test skill.\n---\n\n# Fixture\n",
        encoding="utf-8",
    )
    (root / "lib/tools").mkdir(parents=True)
    (root / "lib/tools/read_fixture.py").write_text("# synthetic\n", encoding="utf-8")
    return {
        "schema_version": 1,
        "id": "example",
        "version": "2.0.0",
        "name": "Example",
        "description": "Synthetic valid package.",
        "entry_prompt": "agent-packages/example/AGENT.md",
        "requires_course_folder": False,
        "skills": [{"id": "fixture-skill", "path": "skills/fixture-skill"}],
        "tools": [
            {
                "id": "read-fixture",
                "command": "lib/tools/read_fixture.py",
                "effect": "read",
                "data_class": "none",
                "approval": "none",
            }
        ],
        "data_access": {
            "classes": ["none"],
            "ferpa_zone_2": "deny",
            "student_names_in_evaluations": "deny",
        },
        "credentials": [],
        "network": ["none"],
        "ships": True,
    }


def _codes(issues: list[pv.Issue]) -> set[str]:
    return {issue.code for issue in issues}


def test_all_three_json_schemas_are_valid():
    for path in (pv.PACKAGE_SCHEMA, pv.DISTRIBUTION_SCHEMA, pv.PLUGIN_SCHEMA):
        _schema(path)


def test_valid_package_passes(tmp_path):
    document = _write_valid_tree(tmp_path)
    tracked = {
        "agent-packages/example/AGENT.md",
        "skills/fixture-skill/SKILL.md",
        "lib/tools/read_fixture.py",
    }
    issues = pv.validate_package_document(
        document,
        source="manifest.yaml",
        repo_root=tmp_path,
        tracked=tracked,
        schema=_schema(pv.PACKAGE_SCHEMA),
    )
    assert issues == []


def test_malformed_yaml_fixture_fails_without_echoing_content():
    document, issues = pv._load_yaml(FIXTURES / "malformed.yaml")
    assert document is None
    assert _codes(issues) == {"invalid-yaml"}
    assert "skills" not in issues[0].message


def test_unknown_tool_fixture_is_rejected(tmp_path):
    document = yaml.safe_load((FIXTURES / "unknown-tool.yaml").read_text(encoding="utf-8"))
    _write_valid_tree(tmp_path)
    issues = pv.validate_package_document(
        document,
        source="unknown-tool.yaml",
        repo_root=tmp_path,
        tracked=set(),
        schema=_schema(pv.PACKAGE_SCHEMA),
    )
    assert "unknown-tool" in _codes(issues)


def test_missing_path_fixture_is_rejected(tmp_path):
    document = yaml.safe_load((FIXTURES / "missing-path.yaml").read_text(encoding="utf-8"))
    _write_valid_tree(tmp_path)
    issues = pv.validate_package_document(
        document,
        source="missing-path.yaml",
        repo_root=tmp_path,
        tracked=set(),
        schema=_schema(pv.PACKAGE_SCHEMA),
    )
    assert "missing-path" in _codes(issues)


def test_constitutional_writer_requires_writer_effect_and_always_approval(tmp_path):
    document = yaml.safe_load(
        (FIXTURES / "undeclared-writer.yaml").read_text(encoding="utf-8")
    )
    _write_valid_tree(tmp_path)
    (tmp_path / "lib/tools/grader_push.py").write_text("# synthetic writer\n", encoding="utf-8")
    issues = pv.validate_package_document(
        document,
        source="undeclared-writer.yaml",
        repo_root=tmp_path,
        tracked=set(),
        schema=_schema(pv.PACKAGE_SCHEMA),
    )
    assert {"writer-effect"} <= _codes(issues)


def test_any_canvas_writer_requires_always_approval(tmp_path):
    document = _write_valid_tree(tmp_path)
    document["tools"][0].update(
        effect="canvas_content_write", data_class="course_content", approval="confirm"
    )
    issues = pv.validate_package_document(
        document,
        source="manifest.yaml",
        repo_root=tmp_path,
        tracked=set(),
        schema=_schema(pv.PACKAGE_SCHEMA),
    )
    assert "writer-approval" in _codes(issues)


def test_forbidden_zone_2_path_is_rejected_before_existence_check(tmp_path):
    document = yaml.safe_load((FIXTURES / "forbidden-path.yaml").read_text(encoding="utf-8"))
    _write_valid_tree(tmp_path)
    issues = pv.validate_package_document(
        document,
        source="forbidden-path.yaml",
        repo_root=tmp_path,
        tracked=set(),
        schema=_schema(pv.PACKAGE_SCHEMA),
    )
    entry_issues = [issue for issue in issues if issue.location == "$.entry_prompt"]
    assert [issue.code for issue in entry_issues] == ["forbidden-path"]


def test_forbidden_patterns_are_derived_from_grade_guardian_zone2(tmp_path):
    # Regression for a hand-copied forbidden list once missing Classlist_Export*.csv,
    # one of grade_guardian's _ZONE2_DEFAULT patterns (#278: ONE PATTERN LIST, NOT TWO).
    # Deriving from load_zone2() means every current and future default is covered
    # without a second hand-maintained copy.
    assert pv.forbidden_pattern("grading/Classlist_Export_F26.csv") is not None


def test_env_example_is_not_forbidden(tmp_path):
    # grade_guardian's credential pattern deliberately excludes ".env.example" (a
    # template, no secret); the validator must not be stricter than the source it
    # derives from.
    assert pv.forbidden_pattern("scaffold/.env.example") is None


def test_duplicate_skill_and_tool_ids_are_rejected(tmp_path):
    document = _write_valid_tree(tmp_path)
    document["skills"].append(dict(document["skills"][0]))
    document["tools"].append(dict(document["tools"][0]))
    issues = pv.validate_package_document(
        document,
        source="manifest.yaml",
        repo_root=tmp_path,
        tracked=set(),
        schema=_schema(pv.PACKAGE_SCHEMA),
    )
    assert [issue.code for issue in issues].count("duplicate-id") == 2


def test_distribution_rejects_duplicate_paths_unknown_package_and_untracked_path(tmp_path):
    (tmp_path / "README.md").write_text("synthetic\n", encoding="utf-8")
    document = {
        "schema_version": 1,
        "version": "2.0.0",
        "packages": ["missing-package"],
        "entries": [
            {"path": "README.md", "kind": "file", "install": "copy"},
            {"path": "README.md", "kind": "file", "install": "copy"},
        ],
    }
    issues = pv.validate_distribution_document(
        document,
        source="distribution.yaml",
        repo_root=tmp_path,
        tracked={"some-other-file"},
        schema=_schema(pv.DISTRIBUTION_SCHEMA),
        package_ids=set(),
    )
    assert {"duplicate-path", "unknown-package", "untracked-path"} <= _codes(issues)


def test_official_plugin_schema_rejects_canvas_specific_top_level_fields():
    plugin = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": "canvas-toolbox",
        "data_access": {"ferpa_zone_2": "deny"},
    }
    issues = pv.schema_issues(plugin, _schema(pv.PLUGIN_SCHEMA), "plugin.json")
    assert _codes(issues) == {"schema"}


def test_json_report_is_stable_and_contains_no_document_content():
    result = pv.ValidationResult(
        packages=0,
        distributions=0,
        plugins=0,
        issues=[pv.Issue("b", "z", "$", "second"), pv.Issue("a", "a", "$", "first")],
    )
    rendered = json.dumps(result.as_dict(), sort_keys=True)
    assert rendered.index('"source": "a"') < rendered.index('"source": "b"')
    assert '"ok": false' in rendered


def test_current_phase_two_repository_validates_with_allow_empty():
    result = pv.validate_repository(pv.REPO_ROOT, allow_empty=True)
    assert result.ok, pv.render_human(result)

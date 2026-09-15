#!/usr/bin/env python3
"""Validate Canvas Toolbox v2 package and distribution manifests without writes.

The portable Agent Plugins manifest stays governed by its published 1.0.0 schema.
Canvas-specific effects, approvals, data boundaries, credentials, and distribution
ownership live in separate manifests validated here.

The validator never reads a path after it matches a forbidden FERPA/secret/output
pattern. Validation is read-only and deterministic; errors are sorted for stable CI
and agent output.

Usage:
  uv run python lib/tools/package_validate.py
  uv run python lib/tools/package_validate.py --allow-empty
  uv run python lib/tools/package_validate.py --json
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from grade_guardian import CREDENTIAL_PATTERNS, load_zone2

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_ROOT = REPO_ROOT / "schemas"
PACKAGE_SCHEMA = SCHEMA_ROOT / "agent-packages" / "package-manifest.schema.json"
DISTRIBUTION_SCHEMA = SCHEMA_ROOT / "agent-packages" / "distribution-manifest.schema.json"
PLUGIN_SCHEMA = (
    SCHEMA_ROOT / "vendor" / "agent-plugins" / "1.0.0" / "plugin.schema.json"
)

PACKAGE_GLOB = "agent-packages/*/manifest.yaml"
DEFAULT_DISTRIBUTION = Path("distribution/manifest.yaml")
DEFAULT_PLUGIN = Path("plugin.json")

CANVAS_EFFECTS = frozenset(
    {
        "canvas_content_write",
        "canvas_grade_comment_write",
        "canvas_student_intervention",
    }
)

# These two are constitutional: grades and comments may reach Canvas only through
# these sanctioned writers. Other Canvas writers are inventoried in package manifests
# during Phase 3, but they can never be reclassified as grade/comment writers.
CONSTITUTIONAL_WRITERS = {
    "lib/tools/grader_push.py": "canvas_grade_comment_write",
    "lib/tools/grader_standing.py": "canvas_grade_comment_write",
    # Verified by reading each tool's actual Canvas write calls (v2, #317 Phase 3) —
    # AGENTS.md previously named only the two above; these four are equally
    # sanctioned grade/comment writers and belong under the same protection, or a
    # manifest could mis-declare one as effect: read and this validator would miss it.
    "lib/tools/grader_push_comments.py": "canvas_grade_comment_write",
    "lib/tools/grader_letter_comments.py": "canvas_grade_comment_write",
    "lib/tools/grader_audit_workflow.py": "canvas_grade_comment_write",
    "lib/tools/grader_quiz_clear_pending.py": "canvas_grade_comment_write",
}

# FERPA Zone 2 (never read) plus the credential-store patterns, both derived from
# grade_guardian's single canonical list rather than hand-copied here. grade_guardian
# and ferpa_pre_push already share ONE pattern list for this exact reason (#278): two
# independently maintained Zone-2 lists drifted apart once (one caught .keymap.json,
# the other didn't). Deriving instead of retyping means Classlist_Export*.csv and any
# future addition to _ZONE2_DEFAULT are covered here automatically.
_ZONE2_PATTERNS = [
    (re.compile(pattern + ("$" if anchored else ""), re.IGNORECASE), pattern)
    for pattern, anchored in load_zone2(REPO_ROOT)[0]
]
_CREDENTIAL_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE), pattern) for pattern in CREDENTIAL_PATTERNS
]

# Zone-2-ADJACENT generated grading output (AGENTS.md: legitimately readable, but a
# name must never sit beside an evaluation) plus generic secret file extensions. These
# have no canonical pattern list elsewhere in the toolkit — they are specific to what a
# package manifest may declare as a prompt/skill/reference/tool path, not to what an
# operator may read directly, so they stay local to the validator.
FORBIDDEN_GLOB_PATTERNS = (
    "**/*.pem",
    "**/*.key",
    "grading/*/_computed_grades.csv",
    "grading/*/_gradebook_canvas.csv",
    "grading/*/_actual_grades.csv",
    "grading/*/FINAL_REVIEW_COMMENTS_*.md",
)


@dataclass(frozen=True)
class Issue:
    source: str
    code: str
    location: str
    message: str


@dataclass
class ValidationResult:
    packages: int
    distributions: int
    plugins: int
    issues: list[Issue]

    @property
    def ok(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "counts": {
                "packages": self.packages,
                "distributions": self.distributions,
                "plugins": self.plugins,
            },
            "issues": [asdict(issue) for issue in sorted_issues(self.issues)],
        }


def sorted_issues(issues: Iterable[Issue]) -> list[Issue]:
    return sorted(issues, key=lambda item: (item.source, item.location, item.code, item.message))


def _display(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _load_json(path: Path) -> tuple[Any | None, list[Issue]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except OSError as exc:
        return None, [Issue(path.as_posix(), "read-error", "$", str(exc))]
    except json.JSONDecodeError as exc:
        return None, [
            Issue(
                path.as_posix(),
                "invalid-json",
                f"line {exc.lineno}, column {exc.colno}",
                exc.msg,
            )
        ]


def _load_yaml(path: Path) -> tuple[Any | None, list[Issue]]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")), []
    except OSError as exc:
        return None, [Issue(path.as_posix(), "read-error", "$", str(exc))]
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f"line {mark.line + 1}, column {mark.column + 1}" if mark else "$"
        problem = getattr(exc, "problem", None) or "invalid YAML"
        return None, [Issue(path.as_posix(), "invalid-yaml", location, problem)]


def load_schema(path: Path) -> tuple[dict[str, Any] | None, list[Issue]]:
    document, issues = _load_json(path)
    if issues:
        return None, issues
    if not isinstance(document, dict):
        return None, [Issue(path.as_posix(), "invalid-schema", "$", "schema must be an object")]
    try:
        Draft202012Validator.check_schema(document)
    except SchemaError as exc:
        return None, [Issue(path.as_posix(), "invalid-schema", "$", exc.message)]
    return document, []


def _json_location(parts: Iterable[Any]) -> str:
    rendered = "$"
    for part in parts:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}"
    return rendered


def schema_issues(document: Any, schema: dict[str, Any], source: str) -> list[Issue]:
    validator = Draft202012Validator(schema)
    return [
        Issue(source, "schema", _json_location(error.absolute_path), error.message)
        for error in sorted(validator.iter_errors(document), key=lambda err: list(err.absolute_path))
    ]


def is_safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    pure = PurePosixPath(value)
    return not pure.is_absolute() and all(part not in {"", ".", ".."} for part in pure.parts)


def forbidden_pattern(value: str) -> str | None:
    normalized = value.lstrip("./")
    for regex, source in (*_ZONE2_PATTERNS, *_CREDENTIAL_PATTERNS):
        if regex.search(normalized):
            return source
    for pattern in FORBIDDEN_GLOB_PATTERNS:
        if fnmatch.fnmatchcase(normalized, pattern):
            return pattern
    return None


def tracked_paths(repo_root: Path) -> tuple[set[str], list[Issue]]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return set(), [Issue("git", "git-ls-files", "$", str(exc))]
    return {item for item in result.stdout.split("\0") if item}, []


def _is_tracked(value: str, tracked: set[str]) -> bool:
    return value in tracked or any(item.startswith(value.rstrip("/") + "/") for item in tracked)


def _validate_reference(
    *,
    value: Any,
    location: str,
    source: str,
    repo_root: Path,
    tracked: set[str],
    expected: str | None = None,
) -> list[Issue]:
    if not is_safe_relative_path(value):
        return [Issue(source, "unsafe-path", location, "path must be a safe repository-relative path")]
    assert isinstance(value, str)
    pattern = forbidden_pattern(value)
    if pattern:
        return [
            Issue(source, "forbidden-path", location, f"path matches forbidden pattern {pattern!r}")
        ]

    path = repo_root / value
    root_resolved = repo_root.resolve()
    try:
        resolved = path.resolve()
        contained = resolved.is_relative_to(root_resolved)
    except OSError:
        contained = False
    if not contained:
        return [Issue(source, "path-escape", location, "resolved path leaves the repository root")]
    if not path.exists():
        return [Issue(source, "missing-path", location, f"referenced path does not exist: {value}")]
    if expected == "file" and not path.is_file():
        return [Issue(source, "wrong-path-kind", location, f"expected a file: {value}")]
    if expected == "tree" and not path.is_dir():
        return [Issue(source, "wrong-path-kind", location, f"expected a directory: {value}")]
    if tracked and not _is_tracked(value, tracked):
        return [Issue(source, "untracked-path", location, f"referenced path is not tracked: {value}")]
    return []


def _duplicate_id_issues(items: Any, source: str, location: str) -> list[Issue]:
    if not isinstance(items, list):
        return []
    seen: set[str] = set()
    issues: list[Issue] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        item_id = item["id"]
        if item_id in seen:
            issues.append(
                Issue(source, "duplicate-id", f"{location}[{index}].id", f"duplicate id: {item_id}")
            )
        seen.add(item_id)
    return issues


def _skill_frontmatter_issues(
    skill_path: Path, skill_id: str, source: str, location: str
) -> list[Issue]:
    skill_file = skill_path / "SKILL.md"
    if not skill_file.is_file():
        return [Issue(source, "missing-skill", location, f"missing {skill_file.as_posix()}")]
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError as exc:
        return [Issue(source, "read-error", location, str(exc))]
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return [Issue(source, "skill-frontmatter", location, "SKILL.md needs YAML frontmatter")]
    frontmatter = text[4:text.index("\n---\n", 4)]
    try:
        data = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        return [Issue(source, "skill-frontmatter", location, "SKILL.md frontmatter is invalid YAML")]
    name = data.get("name") if isinstance(data, dict) else None
    issues: list[Issue] = []
    if name != skill_id:
        issues.append(
            Issue(source, "skill-name", location, f"SKILL.md name {name!r} does not match id {skill_id!r}")
        )
    if skill_path.name != skill_id:
        issues.append(
            Issue(
                source,
                "skill-directory",
                location,
                f"skill directory {skill_path.name!r} does not match id {skill_id!r}",
            )
        )
    return issues


def validate_package_document(
    document: Any,
    *,
    source: str,
    repo_root: Path,
    tracked: set[str],
    schema: dict[str, Any],
) -> list[Issue]:
    issues = schema_issues(document, schema, source)
    if not isinstance(document, dict):
        return issues

    issues.extend(_duplicate_id_issues(document.get("skills"), source, "$.skills"))
    issues.extend(_duplicate_id_issues(document.get("tools"), source, "$.tools"))

    entry_prompt = document.get("entry_prompt")
    issues.extend(
        _validate_reference(
            value=entry_prompt,
            location="$.entry_prompt",
            source=source,
            repo_root=repo_root,
            tracked=tracked,
            expected="file",
        )
    )

    for index, skill in enumerate(document.get("skills", [])):
        if not isinstance(skill, dict):
            continue
        value = skill.get("path")
        location = f"$.skills[{index}].path"
        path_issues = _validate_reference(
            value=value,
            location=location,
            source=source,
            repo_root=repo_root,
            tracked=tracked,
            expected="tree",
        )
        issues.extend(path_issues)
        if not path_issues and isinstance(skill.get("id"), str):
            issues.extend(
                _skill_frontmatter_issues(repo_root / value, skill["id"], source, location)
            )

    for field in ("prompts", "references", "assets"):
        for index, value in enumerate(document.get(field, [])):
            issues.extend(
                _validate_reference(
                    value=value,
                    location=f"$.{field}[{index}]",
                    source=source,
                    repo_root=repo_root,
                    tracked=tracked,
                )
            )

    for index, tool in enumerate(document.get("tools", [])):
        if not isinstance(tool, dict):
            continue
        command = tool.get("command")
        location = f"$.tools[{index}]"
        issues.extend(
            _validate_reference(
                value=command,
                location=f"{location}.command",
                source=source,
                repo_root=repo_root,
                tracked=tracked,
                expected="file",
            )
        )
        if isinstance(command, str) and not command.startswith("lib/tools/"):
            issues.append(
                Issue(source, "unknown-tool", f"{location}.command", "tool must be under lib/tools/")
            )
        effect = tool.get("effect")
        approval = tool.get("approval")
        if effect in CANVAS_EFFECTS and approval != "always":
            issues.append(
                Issue(
                    source,
                    "writer-approval",
                    f"{location}.approval",
                    "Canvas writers require approval: always",
                )
            )
        required_effect = CONSTITUTIONAL_WRITERS.get(command)
        if required_effect and effect != required_effect:
            issues.append(
                Issue(
                    source,
                    "writer-effect",
                    f"{location}.effect",
                    f"{command} must declare effect: {required_effect}",
                )
            )
    return sorted_issues(issues)


def validate_distribution_document(
    document: Any,
    *,
    source: str,
    repo_root: Path,
    tracked: set[str],
    schema: dict[str, Any],
    package_ids: set[str],
) -> list[Issue]:
    issues = schema_issues(document, schema, source)
    if not isinstance(document, dict):
        return issues

    seen: set[str] = set()
    for index, entry in enumerate(document.get("entries", [])):
        if not isinstance(entry, dict):
            continue
        value = entry.get("path")
        location = f"$.entries[{index}].path"
        if isinstance(value, str) and value in seen:
            issues.append(Issue(source, "duplicate-path", location, f"duplicate path: {value}"))
        if isinstance(value, str):
            seen.add(value)
        issues.extend(
            _validate_reference(
                value=value,
                location=location,
                source=source,
                repo_root=repo_root,
                tracked=tracked,
                expected=entry.get("kind"),
            )
        )

    for index, package_id in enumerate(document.get("packages", [])):
        if isinstance(package_id, str) and package_id not in package_ids:
            issues.append(
                Issue(
                    source,
                    "unknown-package",
                    f"$.packages[{index}]",
                    f"package is not declared: {package_id}",
                )
            )
    return sorted_issues(issues)


def validate_repository(repo_root: Path, *, allow_empty: bool = False) -> ValidationResult:
    root = repo_root.resolve()
    issues: list[Issue] = []
    tracked, git_issues = tracked_paths(root)
    issues.extend(git_issues)

    package_schema, package_schema_issues = load_schema(
        root / PACKAGE_SCHEMA.relative_to(REPO_ROOT)
    )
    distribution_schema, distribution_schema_issues = load_schema(
        root / DISTRIBUTION_SCHEMA.relative_to(REPO_ROOT)
    )
    plugin_schema, plugin_schema_issues = load_schema(root / PLUGIN_SCHEMA.relative_to(REPO_ROOT))
    issues.extend(package_schema_issues + distribution_schema_issues + plugin_schema_issues)

    package_paths = sorted(root.glob(PACKAGE_GLOB))
    package_documents: list[tuple[Path, Any]] = []
    package_ids: set[str] = set()
    for path in package_paths:
        source = _display(path, root)
        document, load_issues = _load_yaml(path)
        issues.extend(
            Issue(source, item.code, item.location, item.message) for item in load_issues
        )
        if load_issues:
            continue
        package_documents.append((path, document))
        if isinstance(document, dict) and isinstance(document.get("id"), str):
            package_id = document["id"]
            if package_id in package_ids:
                issues.append(Issue(source, "duplicate-package", "$.id", package_id))
            package_ids.add(package_id)
        if package_schema:
            issues.extend(
                validate_package_document(
                    document,
                    source=source,
                    repo_root=root,
                    tracked=tracked,
                    schema=package_schema,
                )
            )

    if not package_paths and not allow_empty:
        issues.append(Issue(PACKAGE_GLOB, "no-packages", "$", "no package manifests found"))

    distribution_count = 0
    distribution_path = root / DEFAULT_DISTRIBUTION
    if distribution_path.is_file():
        distribution_count = 1
        source = _display(distribution_path, root)
        document, load_issues = _load_yaml(distribution_path)
        issues.extend(Issue(source, item.code, item.location, item.message) for item in load_issues)
        if not load_issues and distribution_schema:
            issues.extend(
                validate_distribution_document(
                    document,
                    source=source,
                    repo_root=root,
                    tracked=tracked,
                    schema=distribution_schema,
                    package_ids=package_ids,
                )
            )

    plugin_count = 0
    plugin_path = root / DEFAULT_PLUGIN
    if plugin_path.is_file():
        plugin_count = 1
        source = _display(plugin_path, root)
        document, load_issues = _load_json(plugin_path)
        issues.extend(Issue(source, item.code, item.location, item.message) for item in load_issues)
        if not load_issues and plugin_schema:
            issues.extend(schema_issues(document, plugin_schema, source))

    return ValidationResult(
        packages=len(package_documents),
        distributions=distribution_count,
        plugins=plugin_count,
        issues=sorted_issues(issues),
    )


def render_human(result: ValidationResult) -> str:
    if result.ok:
        return (
            "package validation: PASS "
            f"({result.packages} packages, {result.distributions} distribution manifests, "
            f"{result.plugins} portable plugins)"
        )
    lines = [f"package validation: FAIL ({len(result.issues)} issues)"]
    for issue in sorted_issues(result.issues):
        lines.append(
            f"  {issue.source}:{issue.location} [{issue.code}] {issue.message}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="allow Phase 2 repositories with no package manifests yet",
    )
    parser.add_argument("--json", action="store_true", help="emit stable JSON")
    args = parser.parse_args(argv)

    result = validate_repository(args.repo_root, allow_empty=args.allow_empty)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        print(render_human(result))
    return 0 if result.ok else 2


if __name__ == "__main__":
    sys.exit(main())

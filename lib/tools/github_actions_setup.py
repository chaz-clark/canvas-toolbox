#!/usr/bin/env python3
"""
github_actions_setup.py — copy Canvas connection settings into GitHub Actions.

Reads only the named values from a course repo's .env:
  CANVAS_API_TOKEN  -> GitHub Actions repository secret
  CANVAS_BASE_URL   -> GitHub Actions repository secret
  CANVAS_COURSE_ID  -> GitHub Actions repository variable

The default is a dry run. `--apply --yes` is required to change GitHub. Secret
values are passed to the GitHub CLI over stdin, never as command-line
arguments, stdout, stderr, or a generated file.

Usage:
  uv run python lib/tools/github_actions_setup.py --repo OWNER/COURSE
  uv run python lib/tools/github_actions_setup.py --repo OWNER/COURSE \
      --env .env --apply --yes
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

from __toolbox_version__ import __version__

SECRET_KEYS = ("CANVAS_API_TOKEN", "CANVAS_BASE_URL")
VARIABLE_KEYS = ("CANVAS_COURSE_ID",)


def read_settings(path: Path) -> dict[str, str]:
    """Read only the setup keys, rejecting missing or blank values."""
    try:
        raw = dotenv_values(path)
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    settings = {key: str(raw.get(key) or "").strip()
                for key in (*SECRET_KEYS, *VARIABLE_KEYS)}
    missing = [key for key, value in settings.items() if not value]
    if missing:
        raise ValueError(f"missing or blank .env value(s): {', '.join(missing)}")
    return settings


def _run_gh(args: list[str], value: str | None = None) -> None:
    """Run gh without exposing a secret in argv or captured output."""
    result = subprocess.run(
        ["gh", *args],
        input=(value + "\n") if value is not None else None,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed (exit {result.returncode})")


def resolve_repo(explicit: str | None) -> str:
    if explicit:
        return explicit
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        raise ValueError("could not determine the GitHub repository; pass --repo OWNER/REPO")
    return result.stdout.strip()


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(
        description="Set Canvas .env values as GitHub Actions secrets/variables.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--env", type=Path, default=Path(".env"),
                    help="Course .env file (default: .env).")
    ap.add_argument("--repo", help="GitHub OWNER/REPO (default: current repo).")
    ap.add_argument("--apply", action="store_true", help="Write settings to GitHub.")
    ap.add_argument("--yes", action="store_true",
                    help="Confirm the GitHub write; requires --apply.")
    args = ap.parse_args()

    if args.yes and not args.apply:
        ap.error("--yes requires --apply")

    try:
        settings = read_settings(args.env)
        repo = resolve_repo(args.repo)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"repository: {repo}")
    print(f"source: {args.env}")
    print("secrets: CANVAS_API_TOKEN, CANVAS_BASE_URL")
    print("variables: CANVAS_COURSE_ID")
    if not args.apply:
        print("DRY RUN — re-run with --apply --yes to save these settings to GitHub.")
        return 0
    if not args.yes:
        print("ERROR: refusing to write without --yes.", file=sys.stderr)
        return 2

    try:
        for key in SECRET_KEYS:
            _run_gh(["secret", "set", key, "--repo", repo], settings[key])
        for key in VARIABLE_KEYS:
            _run_gh(["variable", "set", key, "--repo", repo], settings[key])
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("GitHub Actions settings saved. Secret values were not displayed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

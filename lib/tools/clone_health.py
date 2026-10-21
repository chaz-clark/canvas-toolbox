#!/usr/bin/env python3
"""Is this toolkit folder a real, updatable git clone?  (#415)

`git pull` needs a commit, an `origin` remote and an upstream branch. A folder that was
copied, unzipped, or `git init`ed over extracted files has none of them, and the update
dies with a raw git error ("master has no upstream"). This turns that into a status plus
a plain-language next step. Detect and message only — it never repairs: `reset --hard`
overwrites files, and the nested toolkit may be dev-edited.

The remote URL is NOT checked: adopters legitimately point `origin` at a private fork.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

OK = "ok"
DEFAULT_REMOTE = "https://github.com/chaz-clark/canvas-toolbox.git"


def _git(path: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", str(path), *args], capture_output=True,
                              text=True, encoding="utf-8", timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _repair(p: str, has_origin: bool) -> str:
    add = "" if has_origin else f"git -C {p} remote add origin {DEFAULT_REMOTE} && "
    return (add + f"git -C {p} fetch origin && git -C {p} reset --hard origin/main && "
            f"git -C {p} branch -M main && git -C {p} branch -u origin/main")


def clone_health(path: Path) -> tuple[str, str]:
    """Return (status, message). status is "ok" or one of: no-git, not-a-repo,
    no-commits, no-origin, no-upstream. message is "" when ok."""
    p = str(path)
    probe = _git(path, "--version")
    if probe is None or probe.returncode != 0:
        return ("no-git", "Git is not installed (or not on PATH). Install Git "
                "(Windows: `winget install --id Git.Git -e`; Mac: `xcode-select --install`), "
                "then re-run. Do not substitute a ZIP download or `git init`.")
    if not (path / ".git").exists():
        return ("not-a-repo", f"{p} is not a git clone, so it cannot be updated. "
                "Re-clone the toolkit; do not run `git init` over the files.")
    if (r := _git(path, "rev-parse", "--verify", "HEAD")) is None or r.returncode != 0:
        return ("no-commits", f"{p} is a git repo with no commits — it was set up with "
                "`git init` (or an interrupted clone), not `git clone`, so there is nothing "
                "to pull. If you have not hand-edited the toolkit, repair it with: "
                + _repair(p, (_git(path, "remote", "get-url", "origin") or probe).returncode == 0)
                + ". Needs write access to the folder (full access, outside "
                "any AI sandbox).")
    if (r := _git(path, "remote", "get-url", "origin")) is None or r.returncode != 0:
        return ("no-origin", f"{p} has no `origin` remote, so it cannot find updates. Ask "
                "the toolkit maintainer for the repository URL, then "
                f"`git -C {p} remote add origin <url>`.")
    if (r := _git(path, "rev-parse", "--abbrev-ref", "@{u}")) is None or r.returncode != 0:
        return ("no-upstream", f"The current branch in {p} does not track a remote branch. "
                f"Fix with: git -C {p} fetch origin && git -C {p} branch -u origin/main")
    return (OK, "")

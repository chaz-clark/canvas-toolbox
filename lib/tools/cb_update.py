#!/usr/bin/env python3
"""cb_update.py — the "cb re-init": bring an OLD course-repo init current.

cb_init bootstraps a NEW course repo. But a `git pull` only refreshes the vendored
toolkit code — it can't update a consumer's own course-root files, and it can't make
new toolkit standards active. So repos initialized months ago drift: the field audit
found the six operating-mode skills active in **0 of 9** consumer repos, and a stale
grading-protocol pointer (to a since-renamed heading) in **6 of 9**.

cb_update closes that gap idempotently and NON-destructively:

  1. Skills — symlink `<course-root>/.claude/skills/<skill>` → the vendored
     `canvas-toolbox/.claude/skills/<skill>` for each toolkit skill, so Claude Code
     discovers them at the course root (it only looks there, not in the vendored
     subdir) AND they auto-track future `git pull`s (a symlink, not a copy that
     drifts). A course's own same-named skill is left untouched.
  2. Pointer — refresh the sentinel-delimited canvas-toolbox pointer block in the
     course AGENTS.md (constitution + skills index), healing a stale block in place
     without touching surrounding course-specific content.
  3. Version — report the vendored toolkit version and nudge `git pull` if it looks
     behind.

Dry-run by default; --apply writes. Run from the course root (or its
canvas-toolbox/ subdir). `--pull` first `git pull`s the vendored toolkit (in the
right repo) then updates — the one-command "update canvas-toolbox" so agents stop
hand-typing `cd` + `git pull` into the wrong repo.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

from cb_init import detect_course_context, REPO_ROOT
from sync_grading_protocol import inject_grading_pointer

SKILLS = ["grading", "course-build", "audit", "accommodations", "ferpa-deid", "title-iv"]


def plan_skill_symlinks(course_root: Path, toolkit_subdir: str,
                        skills: list[str]) -> list[tuple[Path, str]]:
    """(link_path, relative_target) for each skill — pure, testable."""
    skills_root = course_root / ".claude" / "skills"
    out = []
    for s in skills:
        link = skills_root / s
        target_abs = course_root / toolkit_subdir / ".claude" / "skills" / s
        out.append((link, os.path.relpath(target_abs, skills_root)))
    return out


def install_skill_symlinks(plan: list[tuple[Path, str]], apply: bool) -> list[tuple[str, str]]:
    """Create/refresh each skill symlink. Never clobbers a course-owned real dir.
    Returns [(skill, status)] where status ∈ present/would-link/linked/copied/
    skip-course-owns."""
    results = []
    for link, rel in plan:
        name = link.name
        if link.is_symlink():
            if os.readlink(link) == rel:
                results.append((name, "present"))
                continue          # already correct
        elif link.exists():
            results.append((name, "skip-course-owns"))  # a real dir/file — don't touch
            continue
        if not apply:
            results.append((name, "would-link"))
            continue
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(rel)
            results.append((name, "linked"))
        except OSError:
            # Windows / no-symlink-permission fallback: copy the skill dir.
            target = (link.parent / rel).resolve()
            if link.exists():
                shutil.rmtree(link, ignore_errors=True)
            if target.is_dir():
                shutil.copytree(target, link)
                results.append((name, "copied"))
            else:
                results.append((name, "missing-target"))
    return results


def ensure_gitignore(course_root: Path, apply: bool) -> str:
    """Make sure `.claude/skills/` is gitignored (the symlinks/copies point at the
    gitignored vendored toolkit; re-created by this tool, not committed)."""
    gi = course_root / ".gitignore"
    line = ".claude/skills/"
    existing = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    if line in existing.splitlines():
        return "present"
    if not apply:
        return "would-add"
    with gi.open("a", encoding="utf-8") as fh:
        if existing and not existing.endswith("\n"):
            fh.write("\n")
        fh.write(f"# canvas-toolbox skills (symlinks into the vendored toolkit)\n{line}\n")
    return "added"


def refresh_pointer(course_root: Path, apply: bool) -> tuple[str, str]:
    """Refresh the constitution+skills pointer block in the course AGENTS.md (or
    CLAUDE.md). Returns (filename, status ∈ missing/present/refreshed/would-refresh)."""
    path = course_root / "AGENTS.md"
    if not path.is_file():
        alt = course_root / "CLAUDE.md"
        path = alt if alt.is_file() else path
    if not path.is_file():
        return (path.name, "missing")
    text = path.read_text(encoding="utf-8")
    new, changed = inject_grading_pointer(text)
    if not changed:
        return (path.name, "present")
    if not apply:
        return (path.name, "would-refresh")
    path.write_text(new, encoding="utf-8")
    return (path.name, "refreshed")


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(
        description="Bring an old canvas-toolbox course init current (skills + pointer).")
    ap.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    ap.add_argument("--pull", action="store_true",
                    help="first `git pull` the VENDORED toolkit (the right repo), then "
                         "update — the one-command 'update canvas-toolbox'.")
    args = ap.parse_args()

    course_root, is_subdir = detect_course_context()
    if not is_subdir:
        print("Standalone canvas-toolbox — skills already live at .claude/skills/; "
              "nothing to re-init. cb_update is for consumer course repos.")
        return 0
    toolkit_subdir = REPO_ROOT.name  # e.g. 'canvas-toolbox'

    if args.pull:
        # Pull the VENDORED toolkit in its own dir — never the course repo, never a
        # hand-typed `cd`. Then re-exec the freshly-pulled tool (no --pull) so its
        # updated logic + pointer text apply this run, not next.
        toolkit_dir = course_root / toolkit_subdir
        print(f"Pulling {toolkit_subdir}/ (the vendored toolkit) …")
        r = subprocess.run(["git", "-C", str(toolkit_dir), "pull", "--ff-only"],
                           capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip()
        print("  " + (out.splitlines()[-1] if out else "pulled"))
        os.execv(sys.executable,
                 [sys.executable, str(Path(__file__).resolve()),
                  *[a for a in sys.argv[1:] if a != "--pull"]])

    print(f"cb_update (re-init) for course repo: {course_root}")
    print(f"  vendored toolkit: {toolkit_subdir}/ @ v{__version__}")
    print(f"  {'APPLYING' if args.apply else 'DRY RUN — pass --apply to write'}\n")

    plan = plan_skill_symlinks(course_root, toolkit_subdir, SKILLS)
    print("Skills → .claude/skills/ (so Claude Code activates them here):")
    for name, status in install_skill_symlinks(plan, args.apply):
        print(f"  {status:16} {name}")
    print(f"  gitignore .claude/skills/: {ensure_gitignore(course_root, args.apply)}")

    fname, status = refresh_pointer(course_root, args.apply)
    print(f"\nConstitution+skills pointer in {fname}: {status}")

    print("\nReminder: `cd " + toolkit_subdir + " && git pull` keeps the toolkit "
          "(and the symlinked skills) current.")
    if not args.apply:
        print("Re-run with --apply to make the changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

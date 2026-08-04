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
import json
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

try:
    from grade_guardian import ensure_hook as _ensure_guardian_hook
    from grade_guardian import zone2_summary as _zone2_summary
    from grade_guardian import _ZONE2_EXTRA_FILE
except ImportError:
    _ensure_guardian_hook = None
    _zone2_summary = None
    _ZONE2_EXTRA_FILE = ".claude/ferpa_zone2.txt"

SKILLS = ["grading", "course-build", "audit", "accommodations", "ferpa-deid",
          "title-iv", "voicing", "improve"]


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


_MARKER = ".cb_managed"  # dropped in a Windows copy so re-runs know it's ours to refresh


def _managed_copy(link: Path) -> bool:
    """True if `link` is a real dir we previously copied (Windows symlink fallback) —
    so a re-run REFRESHES it instead of mistaking it for a course-owned skill."""
    return link.is_dir() and not link.is_symlink() and (link / _MARKER).is_file()


def install_skill_symlinks(plan: list[tuple[Path, str]], apply: bool) -> list[tuple[str, str]]:
    """Create/refresh each skill link. Never clobbers a course-OWNED real dir (one
    without our marker). Returns [(skill, status)] where status ∈ present/
    would-install/linked/copied/skip-course-owns/missing-target."""
    results = []
    for link, rel in plan:
        name = link.name
        if link.is_symlink() and os.readlink(link) == rel:
            results.append((name, "present"))
            continue                                   # correct symlink — done
        if link.exists() and not link.is_symlink() and not _managed_copy(link):
            results.append((name, "skip-course-owns"))  # real dir, no marker — theirs
            continue
        # absent, a stale/wrong symlink, or OUR prior copy → (re)install
        if not apply:
            results.append((name, "would-install"))
            continue
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or (link.exists() and not link.is_dir()):
            link.unlink()
        elif link.is_dir():
            shutil.rmtree(link, ignore_errors=True)   # our stale copy
        try:
            link.symlink_to(rel)
            results.append((name, "linked"))
        except OSError:
            # Windows / no-symlink-permission fallback: copy + mark it ours.
            target = (link.parent / rel).resolve()
            if target.is_dir():
                shutil.copytree(target, link)
                (link / _MARKER).write_text(
                    "Managed by cb_update (Windows copy fallback); refreshed on re-run.\n",
                    encoding="utf-8")
                results.append((name, "copied"))
            else:
                results.append((name, "missing-target"))
    return results


_BLANKET = ".claude/skills/"   # what we used to write — too broad (see below)
_GI_HEADER = "# canvas-toolbox skills (symlinks into the vendored toolkit)"


def ensure_gitignore(course_root: Path, skills: list[str], apply: bool) -> str:
    """Gitignore the toolkit's OWN skills by name — never the whole directory.

    The symlinks/copies point at the gitignored vendored toolkit and are re-created
    by this tool, so they shouldn't be committed. But `install_skill_symlinks()`
    already knows a course can own a skill of its own in that same folder
    (`skip-course-owns`), and the old blanket `.claude/skills/` line gitignored those
    too. Quietly: .gitignore doesn't affect tracked files, so nothing broke at apply
    time — it bit the NEXT course-owned skill added, which `git add -A` and
    `git status` then silently skipped (#271, #272).

    Ignoring `SKILLS` by name makes the ignore set exactly what this tool creates, so
    a course-owned skill is protected by construction.

    **NO TRAILING SLASH on the emitted lines.** In gitignore a trailing slash matches
    DIRECTORIES ONLY, and what this tool creates is a *symlink* — which git treats as
    a file. 1.14.1 shipped `.claude/skills/<s>/` and so matched nothing it creates:
    every toolkit skill flipped to untracked on migration, and a `git add -A` would
    have committed symlinks pointing into the gitignored vendored toolkit (#277). A
    slashless pattern matches both the symlink AND the real directory of the Windows
    copy fallback, so it stays correct on either path. Tests assert against real git,
    on a real symlink — a pattern-only assertion cannot see this class of bug.

    Returns present/would-add/added/would-migrate/migrated ("migrate" = legacy lines
    were replaced in place: 1.13-and-earlier's blanket `.claude/skills/`, or 1.14.1's
    trailing-slash per-skill lines. Without that, repos already updated by an older
    cb_update would keep the broken lines forever)."""
    gi = course_root / ".gitignore"
    existing = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    lines = existing.splitlines()
    wanted = [f".claude/skills/{s}" for s in skills]        # no trailing slash — see above
    legacy = {_BLANKET, *(f"{w}/" for w in wanted)}         # blanket, and 1.14.1's slashed

    if any(ln in legacy for ln in lines):
        if not apply:
            return "would-migrate"
        out, replaced = [], False
        for ln in lines:
            if ln not in legacy:
                out.append(ln)
            elif not replaced:                    # first legacy line → the corrected set
                out.extend(w for w in wanted if w not in lines)
                replaced = True                   # any further legacy lines just drop
        gi.write_text("\n".join(out) + "\n", encoding="utf-8")
        return "migrated"

    missing = [w for w in wanted if w not in lines]
    if not missing:
        return "present"
    if not apply:
        return "would-add"
    with gi.open("a", encoding="utf-8") as fh:
        if existing and not existing.endswith("\n"):
            fh.write("\n")
        fh.write(_GI_HEADER + "\n" + "".join(f"{w}\n" for w in missing))
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


def ensure_guardian_hook(course_root: Path, toolkit_subdir: str, apply: bool) -> str:
    """Install the grade_guardian PreToolUse hook into the course's
    `.claude/settings.json` if missing — THE most important safety piece. A repo
    init'd before the hook feature (and only ever `cb_update`d for skills) has none,
    so its agents can hand-write Canvas writes and route around gates freely — the
    'one repo without the hook does everything differently' situation. Idempotent,
    non-clobbering, guarded on the vendored guardian script existing. Returns
    present/would-install/installed/skipped-no-script/bad-json."""
    if _ensure_guardian_hook is None:
        return "skipped-no-script"
    guardian = course_root / toolkit_subdir / "lib" / "tools" / "grade_guardian.py"
    if not guardian.is_file():
        return "skipped-no-script"
    settings_path = course_root / ".claude" / "settings.json"
    try:
        existing = (json.loads(settings_path.read_text(encoding="utf-8"))
                    if settings_path.exists() else {})
    except (OSError, ValueError):
        return "bad-json"                     # never clobber an unparseable settings file
    new_settings, changed = _ensure_guardian_hook(existing)
    if not changed:
        return "present"
    if not apply:
        return "would-install"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(new_settings, indent=2) + "\n", encoding="utf-8")
    return "installed"


def canvas_configured(course_root: Path) -> bool:
    """Whether this repo has a Canvas course wired up. Checks the environment and
    the course `.env` for a non-empty CANVAS_COURSE_ID."""
    if os.environ.get("CANVAS_COURSE_ID", "").strip():
        return True
    try:
        text = (course_root / ".env").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("CANVAS_COURSE_ID") and "=" in line:
            if line.split("=", 1)[1].strip().strip("'\""):
                return True
    return False


def print_lms_mode(course_root: Path) -> None:
    """Name the third repo shape (#279): vendored into a course with NO Canvas.

    cb_init/cb_update modelled exactly two — vendored-into-Canvas and standalone —
    so a consumer on another LMS ran in an undeclared mode and had to infer, tool by
    tool, which parts applied to them. Most of what the toolkit offers doesn't touch
    the Canvas API at all.

    Deliberately reports what was OBSERVED rather than asserting a mode: absent
    credentials are not proof a course isn't on Canvas (creds live elsewhere, a fresh
    clone hasn't been configured yet), and telling someone their tools are inert when
    they aren't is its own failure."""
    if canvas_configured(course_root):
        return
    print("\nNo Canvas course configured here (no CANVAS_COURSE_ID in the environment "
          "or .env).")
    print("  ↳ If that's expected — a course on another LMS — the Canvas-API tools "
          "(canvas_sync, grader_fetch, grader_push, grader_standing) are inert, but "
          "the constitution, the skills, grade_guardian, the FERPA zone discipline, "
          "and the N-pass consensus grading method don't need Canvas and all apply.")
    print("     Build the de-id master without credentials: "
          "build_deid_master.py --roster-json <path>")
    print("     Add your own name-bearing files to " + _ZONE2_EXTRA_FILE + ".")


def print_zone2_coverage(course_root: Path) -> None:
    """Report WHAT the guardian's FERPA set actually covers, not just that the hook
    is wired. `grade_guardian hook: present` was true and misleading in the same
    breath for a non-Canvas consumer: the hook was installed and enforcing a set of
    Canvas filenames that matched none of their name-bearing files (#278). "Present"
    reads as "covered." Printing the counts — and naming the extension file when a
    repo has none — keeps that from being an inference the operator has to make."""
    if _zone2_summary is None:
        return
    s = _zone2_summary(course_root)
    extra = f" + {s['extra']} course-local" if s["extra"] else ""
    print(f"  FERPA Zone-2 patterns: {s['default']} built-in{extra}")
    if s["invalid"]:
        print(f"  ⚠ {len(s['invalid'])} pattern(s) in {_ZONE2_EXTRA_FILE} are not valid "
              f"regex and are being IGNORED — you are not covered on those:")
        for bad in s["invalid"]:
            print(f"      {bad}")
    elif not s["source"]:
        print(f"  ↳ built-ins are Canvas filenames. If this course keeps names in files "
              f"of its own, list them in {_ZONE2_EXTRA_FILE} (one regex per line) — "
              f"otherwise the hook is installed but not covering them.")


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
    gi_status = ensure_gitignore(course_root, SKILLS, args.apply)
    print(f"  gitignore (toolkit skills, by name): {gi_status}")
    if gi_status in ("migrated", "would-migrate"):
        print("  ↳ replaced a blanket `.claude/skills/` ignore, which also hid the "
              "course's OWN skills from git (#271). Course-owned skills are now visible.")

    fname, status = refresh_pointer(course_root, args.apply)
    print(f"\nConstitution+skills pointer in {fname}: {status}")

    hook_status = ensure_guardian_hook(course_root, toolkit_subdir, args.apply)
    print(f"grade_guardian hook (.claude/settings.json): {hook_status}")
    if hook_status in ("installed", "would-install"):
        print("  ↳ this repo was missing the guardian — agents could hand-write "
              "Canvas writes / bypass gates. Now enforced at create/edit/run.")
    print_zone2_coverage(course_root)
    print_lms_mode(course_root)

    print("\nReminder: `cd " + toolkit_subdir + " && git pull` keeps the toolkit "
          "(and the symlinked skills) current.")
    if not args.apply:
        print("Re-run with --apply to make the changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

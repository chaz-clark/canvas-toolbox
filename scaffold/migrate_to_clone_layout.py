#!/usr/bin/env python3
"""
migrate_to_clone_layout.py — consumer-side repo restructure.

Convert a Canvas course repo that vendors canvas-toolbox as a git SUBTREE
(committed into the consumer's history) into the new convention where
canvas-toolbox is its own gitignored CLONE, and scaffold the other convention
folders (local handoffs/, optional sister-repo clones).

Run this from the CONSUMER's repo root (e.g., m119-master/, itm327-master/).
DRY-RUN by default — prints the migration plan but changes nothing. Pass
--apply to actually execute.

Examples:
    # see what it would do, without changing anything
    python canvas-toolbox/scaffold/migrate_to_clone_layout.py

    # do the migration; prompt per sister repo
    python canvas-toolbox/scaffold/migrate_to_clone_layout.py --apply

    # do everything, auto-clone all sister repos
    python canvas-toolbox/scaffold/migrate_to_clone_layout.py --apply --scaffold-folders=all

Stdlib only (subprocess + pathlib) — runnable on a consumer that hasn't yet
set up `uv` for canvas-toolbox.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Convention constants
# ---------------------------------------------------------------------------

CANONICAL_NAME = "canvas-toolbox"  # hyphen — fleet-canonical (ds250 + itm327
                                   # explicitly renamed from underscore to this).
CANVAS_TOOLBOX_URL = "https://github.com/chaz-clark/canvas-toolbox.git"

SISTER_REPOS: list[tuple[str, str]] = [
    ("handoff",          "https://github.com/chaz-clark/handoff.git"),
    ("Make-AI-Agents",   "https://github.com/chaz-clark/Make-AI-Agents.git"),
    ("gh-issues-agent",  "https://github.com/chaz-clark/gh-issues-agent.git"),
]

GITIGNORE_BLOCK = [
    "# canvas-toolbox (clone, gitignored — pull updates via `cd canvas-toolbox && git pull`)",
    "/canvas-toolbox/",
    "/canvas_toolbox/",
    "",
    "# Convention scaffolding — sister-repo clones (each is its own git repo)",
    "/handoff/",
    "/Make-AI-Agents/",
    "/make-ai-agents/",
    "/gh-issues-agent/",
    "",
    "# Local handoffs scratch (per-repo, never committed)",
    "/handoffs/",
    "",
    "# Secrets",
    ".env",
]

# ---------------------------------------------------------------------------
# State enums (return codes from detect_state)
# ---------------------------------------------------------------------------

STATE_A = "A — subtree-vendored (OLD; tracked in parent, no inner .git/)"
STATE_B = "B — clone present but still tracked in parent (.gitignore needs fix)"
STATE_C = "C — already correct (clone + gitignored)"
STATE_D = "D — no canvas-toolbox folder at all (fresh clone needed)"
STATE_E = "E — ambiguous / local divergence (manual review required)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: Path | None = None, check: bool = True,
         capture: bool = False) -> subprocess.CompletedProcess:
    """Wrap subprocess.run for git + shell calls. Captures text when capture=True."""
    return subprocess.run(
        cmd, cwd=cwd, check=check,
        capture_output=capture, text=capture,
    )


def _is_tracked(repo_root: Path, name: str) -> bool:
    """Does the parent git index list any files under `name`?"""
    r = _run(["git", "ls-files", "--", name], cwd=repo_root,
             check=False, capture=True)
    return bool(r.stdout.strip())


# ---------------------------------------------------------------------------
# Pre-flight + state detection
# ---------------------------------------------------------------------------

def preflight(repo_root: Path) -> list[str]:
    """Read-only sanity checks. Returns a list of warning strings."""
    warns: list[str] = []
    if not (repo_root / ".git").exists():
        warns.append("FATAL: not in a git repository (the consumer must be a git repo).")
        return warns
    r = _run(["git", "status", "--porcelain"], cwd=repo_root,
             check=False, capture=True)
    dirty = [ln for ln in r.stdout.splitlines() if ln.strip()]
    if dirty:
        warns.append(
            f"working tree is dirty ({len(dirty)} paths) — commit/stash first to avoid mixing this migration with other work."
        )
    if Path.cwd().name == CANONICAL_NAME and (Path.cwd() / "lib" / "tools").exists():
        warns.append("you appear to be inside canvas-toolbox itself — run from the CONSUMER repo's root.")
    return warns


def detect_state(repo_root: Path) -> tuple[str, Path | None, dict]:
    """Identify which vendored layout the consumer is in."""
    candidates = [repo_root / "canvas-toolbox", repo_root / "canvas_toolbox"]
    present = [p for p in candidates if p.is_dir()]

    if not present:
        return STATE_D, None, {}

    if len(present) > 1:
        return STATE_E, present[0], {
            "both_present": [p.name for p in present],
            "note": "Both 'canvas-toolbox/' and 'canvas_toolbox/' exist — pick one canonical and remove the other manually before re-running.",
        }

    folder = present[0]
    has_inner_git = (folder / ".git").exists()
    tracked = _is_tracked(repo_root, folder.name)

    if has_inner_git and not tracked:
        return STATE_C, folder, {}
    if has_inner_git and tracked:
        return STATE_B, folder, {"note": "Folder is a clone but parent still tracks it — needs untrack + .gitignore."}
    if not has_inner_git and tracked:
        return STATE_A, folder, {"note": "Vendored as a subtree (committed history). Will untrack, back up, remove, then clone fresh."}
    # not has_inner_git AND not tracked: orphan dir on disk
    return STATE_E, folder, {"orphan_dir": str(folder.relative_to(repo_root))}


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

Step = tuple[str, list[str]]  # (description, command-or-internal-op)


def build_plan(state: str, folder: Path | None, repo_root: Path,
               sisters_to_clone: list[str], upstream_url: str) -> list[Step]:
    """Return ordered list of steps for the detected state. No I/O here."""
    steps: list[Step] = []
    target = CANONICAL_NAME  # always migrate INTO the canonical (hyphen) name

    if state == STATE_C:
        return steps

    # Subtree migration: untrack → backup → delete on-disk → fresh clone
    if state == STATE_A:
        rel = folder.name
        backup = Path("/tmp") / f"canvas-toolbox-vendored-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        steps.append((f"untrack vendored '{rel}/' in the consumer index (keep working tree)",
                      ["git", "rm", "-r", "--cached", rel]))
        steps.append((f"back up current vendored content → {backup}/  (so local mods aren't lost)",
                      ["__internal_backup__", str(folder), str(backup)]))
        steps.append((f"remove on-disk '{rel}/' (will be re-created as a fresh clone)",
                      ["__internal_rmtree__", str(folder)]))
        # if the old name was the underscore variant, normalize to hyphen here
        steps.append((f"clone canvas-toolbox fresh into '{target}/' (canonical name)",
                      ["git", "clone", upstream_url, target]))

    # Half-converted: clone already on disk, just untrack from parent
    elif state == STATE_B:
        rel = folder.name
        steps.append((f"untrack the existing clone '{rel}/' in the consumer index",
                      ["git", "rm", "-r", "--cached", rel]))
        if rel != target:
            steps.append((f"normalize folder name '{rel}/' → '{target}/' (canonical hyphen)",
                          ["__internal_move__", str(folder), str(repo_root / target)]))

    # Missing: just clone fresh
    elif state == STATE_D:
        steps.append((f"clone canvas-toolbox fresh into '{target}/'",
                      ["git", "clone", upstream_url, target]))

    # .gitignore patch (idempotent — common to all migration paths)
    steps.append(("ensure .gitignore covers the canonical convention block",
                  ["__internal_gitignore_patch__"]))

    # Local handoffs/ folder (always — convention)
    if not (repo_root / "handoffs").exists():
        steps.append(("create local handoffs/ folder + .gitkeep (convention)",
                      ["__internal_mkdir_gitkeep__", str(repo_root / "handoffs")]))

    # Optional sister-repo clones
    for sister in sisters_to_clone:
        url = next((u for n, u in SISTER_REPOS if n == sister), None)
        if not url or (repo_root / sister).exists():
            continue
        steps.append((f"clone sister repo '{sister}/' (gitignored)",
                      ["git", "clone", url, sister]))

    # One commit at the end
    steps.append(("stage + commit the migration",
                  ["__internal_commit__"]))

    return steps


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def apply_step(desc: str, cmd: list[str], repo_root: Path) -> bool:
    """Execute one step. Returns True on success, False to abort the plan."""
    op = cmd[0]

    if op == "__internal_backup__":
        src, dst = Path(cmd[1]), Path(cmd[2])
        if src.exists():
            shutil.copytree(src, dst)
        return True

    if op == "__internal_rmtree__":
        p = Path(cmd[1])
        if p.exists():
            shutil.rmtree(p)
        return True

    if op == "__internal_move__":
        src, dst = Path(cmd[1]), Path(cmd[2])
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))
        return True

    if op == "__internal_mkdir_gitkeep__":
        d = Path(cmd[1])
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
        # stage the .gitkeep so the empty dir survives in git
        try:
            _run(["git", "add", str(d / ".gitkeep")], cwd=repo_root)
        except subprocess.CalledProcessError:
            pass  # if the dir is gitignored that's fine — .gitkeep won't be tracked
        return True

    if op == "__internal_gitignore_patch__":
        gi = repo_root / ".gitignore"
        existing_lines = gi.read_text().splitlines() if gi.exists() else []
        existing_set = {ln.strip() for ln in existing_lines
                        if ln.strip() and not ln.strip().startswith("#")}
        to_add = [ln for ln in GITIGNORE_BLOCK
                  if ln == "" or ln.startswith("#") or ln not in existing_set]
        # Don't re-add the block if everything's already present (de-dup by data lines).
        new_data_lines = [ln for ln in to_add
                          if ln and not ln.startswith("#")]
        if not new_data_lines:
            return True  # nothing to add
        with gi.open("a") as f:
            if existing_lines and existing_lines[-1] != "":
                f.write("\n")
            f.write("\n".join(to_add))
            f.write("\n")
        _run(["git", "add", ".gitignore"], cwd=repo_root)
        return True

    if op == "__internal_commit__":
        # Only commit if there's something staged.
        r = _run(["git", "diff", "--cached", "--quiet"], cwd=repo_root,
                 check=False, capture=False)
        if r.returncode == 0:
            print("    (nothing staged — skipping commit)")
            return True
        try:
            _run(["git", "commit", "-m",
                  "chore: migrate canvas-toolbox subtree → gitignored clone + scaffold convention dirs"],
                 cwd=repo_root)
        except subprocess.CalledProcessError as e:
            print(f"    ❌ commit failed: {e}")
            return False
        return True

    # Default: a normal external command
    try:
        _run(cmd, cwd=repo_root)
        return True
    except subprocess.CalledProcessError as e:
        print(f"    ❌ step failed (exit {e.returncode}): {' '.join(cmd)}")
        return False


# ---------------------------------------------------------------------------
# Post-flight
# ---------------------------------------------------------------------------

def postflight(repo_root: Path) -> None:
    """Final report — state recheck + pyproject reference detect-and-report."""
    state, folder, info = detect_state(repo_root)
    if state == STATE_C and folder is not None:
        print(f"  ✅ canvas-toolbox now at '{folder.relative_to(repo_root)}/' — clone + gitignored.")
    else:
        print(f"  ⚠️  Postflight state: {state}")
        for k, v in info.items():
            print(f"     {k}: {v}")

    pp = repo_root / "pyproject.toml"
    if pp.exists():
        content = pp.read_text()
        flagged = [name for name in ("canvas_toolbox", "canvas-toolbox")
                   if (f'"{name}/' in content) or (f"'{name}/" in content)
                   or f"= {{ path = \"{name}" in content
                   or f"= {{ path = '{name}" in content]
        if flagged:
            print(f"  ⚠️  pyproject.toml references vendored path(s): {flagged}.")
            print("     Review manually — this script does not auto-edit pyproject.toml.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Consumer-side: migrate a vendored-subtree canvas-toolbox to a "
                    "gitignored clone + scaffold the convention folders. "
                    "Dry-run by default.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--apply", action="store_true",
                    help="Actually execute. Default is dry-run (print plan, change nothing).")
    ap.add_argument("--scaffold-folders", choices=("all", "none", "prompt"),
                    default="prompt",
                    help="Sister-repo clones: all (auto), none (skip), prompt (ask per-sister, default).")
    ap.add_argument("--upstream-url", default=CANVAS_TOOLBOX_URL,
                    help=f"canvas-toolbox clone URL (default: {CANVAS_TOOLBOX_URL}).")
    ap.add_argument("--repo-root", type=Path, default=Path("."),
                    help="Consumer repo root. Default: current directory.")
    args = ap.parse_args()

    repo_root = args.repo_root.resolve()

    print(f"Consumer repo:   {repo_root}")
    print(f"Mode:            {'APPLY' if args.apply else 'DRY-RUN (no changes will be made)'}")
    print(f"Canonical name:  '{CANONICAL_NAME}/' (hyphen — fleet-canonical)")
    print(f"Upstream URL:    {args.upstream_url}")
    print()

    # 1. Preflight
    warns = preflight(repo_root)
    fatal = [w for w in warns if w.startswith("FATAL")]
    for w in fatal:
        print(f"❌ {w}")
    if fatal:
        sys.exit(2)
    for w in warns:
        print(f"⚠️  {w}")
    if warns and args.apply:
        print("\nRefusing --apply while warnings are unresolved. Address them, then re-run.")
        sys.exit(2)
    if warns:
        print()

    # 2. State detection
    state, folder, info = detect_state(repo_root)
    print(f"State detected:  {state}")
    if folder:
        print(f"Vendored at:     '{folder.relative_to(repo_root)}/'")
    for k, v in info.items():
        print(f"  {k}: {v}")
    print()

    if state == STATE_C:
        print("✅ Already on the new layout. Nothing to do.")
        sys.exit(0)
    if state == STATE_E:
        print("🛑 Halting — manual review needed (see info above). No safe automated migration.")
        sys.exit(1)

    # 3. Determine which sister repos to clone
    sisters_to_clone: list[str] = []
    available_sisters = [(n, u) for n, u in SISTER_REPOS if not (repo_root / n).exists()]

    if args.scaffold_folders == "all":
        sisters_to_clone = [n for n, _ in available_sisters]
    elif args.scaffold_folders == "none":
        sisters_to_clone = []
    elif args.scaffold_folders == "prompt":
        if args.apply:
            for n, _ in available_sisters:
                ans = input(f"  clone sister repo '{n}/'? [y/N] ").strip().lower()
                if ans in ("y", "yes"):
                    sisters_to_clone.append(n)
        else:
            # dry-run: list what would be prompted for
            if available_sisters:
                print("Sister repos that would be PROMPTED in --apply mode:")
                for n, _ in available_sisters:
                    print(f"  - {n}/")
                print()

    # 4. Build the plan
    steps = build_plan(state, folder, repo_root, sisters_to_clone, args.upstream_url)
    if not steps:
        print("✅ No steps needed.")
        sys.exit(0)

    print("Plan:")
    for i, (desc, _cmd) in enumerate(steps, 1):
        print(f"  {i}. {desc}")
    print()

    if not args.apply:
        print("(Dry-run — no changes made. Re-run with --apply to execute.)")
        sys.exit(0)

    # 5. Execute
    print("Executing:")
    for i, (desc, cmd) in enumerate(steps, 1):
        print(f"  {i}. {desc} …")
        if not apply_step(desc, cmd, repo_root):
            print(f"\n🛑 Aborted at step {i}. Repo may be in a partial state — `git status` to inspect.")
            sys.exit(2)
    print()

    # 6. Postflight
    print("Verifying …")
    postflight(repo_root)

    print()
    print("Next steps:")
    print(f"  1. Set up .env (start from canvas-toolbox/scaffold/gitignore + add CANVAS_API_TOKEN/BASE_URL/COURSE_ID/SANDBOX_ID).")
    print("  2. cd canvas-toolbox && uv sync && cd ..")
    print("  3. Use your AI agent with the prompt in canvas-toolbox/README.md → Step 3 → Option A.")


if __name__ == "__main__":
    main()

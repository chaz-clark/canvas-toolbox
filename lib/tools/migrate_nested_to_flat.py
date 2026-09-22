#!/usr/bin/env python3
"""migrate_nested_to_flat.py — one-time migration from the OLD nested
`<course-root>/canvas-toolbox/` layout to the flat `.canvas-toolbox/` hidden-
clone layout (v2, #317 Phase 8 / docs/proposals/flat-layout-and-agents-
merge.md Phase 7).

WHAT THE NESTED LAYOUT LOOKS LIKE (the thing being migrated FROM)

    course-root/
    ├── canvas-toolbox/        # a full, separate git clone (has its own .git)
    ├── .claude/
    │   ├── skills/<skill>/    # SYMLINKS into canvas-toolbox/.claude/skills/<skill>
    │   └── CLAUDE.md          # symlink (or Windows copy) -> ../AGENTS.md
    ├── AGENTS.md              # pointer-only: "see canvas-toolbox/AGENTS.md"
    └── .env, course/, grading/, handoffs/   # course-owned, untouched by this tool

THE MIGRATION, IN ORDER (never reordered — each step's safety depends on the
one before it)

  1. relocate_nested_clone()   — a LOCAL git clone of canvas-toolbox/ into
                                  .canvas-toolbox/, origin repointed at the
                                  real remote. The OLD canvas-toolbox/ is left
                                  fully intact — nothing is deleted yet.
  2. remove_stale_skill_links() — unlink the OLD symlinks at .claude/skills/<s>
                                  (and any Windows copy-fallback). Left in
                                  place, cb_flatten's own file-by-file copy
                                  would write THROUGH a symlinked directory
                                  into canvas-toolbox/ — which is about to be
                                  removed — instead of creating real local
                                  files.
  3. cb_flatten's own flow      — resolve_distribution() + apply_sync() copies
     (imported, not reimplemented) the real flattened files; plan_agents_md_merge()
                                  /apply_agents_md_step() back up AGENTS.md to
                                  AGENTS.merge.md and drop in the fresh
                                  constitution (never a blind overwrite — see
                                  cb_flatten.py's own module docstring).
  4. fix_stale_guardian_hook()  — grade_guardian.ensure_hook() never rewrites
                                  an EXISTING hook (by design, for the ordinary
                                  flatten case — a customized hook is left
                                  alone). During migration that default is
                                  wrong: the existing hook, if any, references
                                  the NESTED path (canvas-toolbox/lib/tools/
                                  grade_guardian.py) which the finalize step
                                  is about to delete — installed, but about to
                                  go silently inert exactly like the flat-mode
                                  bug fixed in Phase 6. This step detects and
                                  replaces ONLY a hook whose path point at the
                                  nested subdirectory; a hook already pointing
                                  somewhere else (a course's own customization)
                                  is left untouched.
  5. verification_report()      — cb_flatten's own 7-check report. Migration
     (imported, not reimplemented) is not reported complete if this fails.
  6. finalize_migration()       — ONLY on explicit --finalize (never bundled
                                  with --apply): removes the OLD canvas-toolbox/
                                  directory. This is the sole irreversible step
                                  in the whole tool, and it is separated from
                                  every other step on purpose.

ROLLBACK

  Before --finalize, rollback is simple by construction: canvas-toolbox/ was
  never touched, so rollback() removes .canvas-toolbox/ and every path the
  distribution resolved (the exact set apply_sync() just wrote), and restores
  AGENTS.merge.md -> AGENTS.md if a merge was left mid-flight. After
  --finalize, the old nested clone is gone — rollback() then reconstructs it
  by cloning .canvas-toolbox/ (which carries the same history) back out under
  the canvas-toolbox/ name, but the newly-flattened root files are NOT
  removed at that point (they are now the only copy of the toolkit files, and
  removing them would leave the course without a working toolkit at all).

USAGE
  uv run python lib/tools/migrate_nested_to_flat.py --course-root PATH
  uv run python lib/tools/migrate_nested_to_flat.py --course-root PATH --apply
  uv run python lib/tools/migrate_nested_to_flat.py --course-root PATH --finalize
  uv run python lib/tools/migrate_nested_to_flat.py --course-root PATH --rollback
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import cb_flatten as flat
from cb_update import SKILLS, _managed_copy, _managed_shim

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

NESTED_DIR_NAME = "canvas-toolbox"


def _rmtree(path: Path) -> None:
    """shutil.rmtree, but tolerant of git's read-only pack/object files.

    FOUND ON REAL WINDOWS. Git marks .git/objects/pack/* read-only on every
    platform, but only Windows' os.unlink() actually honors that bit — POSIX
    deletion is governed by the directory's write permission, not the file's,
    so this never surfaced there. shutil.rmtree(nested) on a real git clone
    raised PermissionError on first contact with a pack file. Clear the
    read-only attribute on retry instead of failing the whole finalize."""
    def _on_error(func, target, _exc_info):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    shutil.rmtree(path, onexc=_on_error)


# ---------------------------------------------------------------------------
# Layout detection
# ---------------------------------------------------------------------------

def detect_layout(course_root: Path) -> str:
    """One of: standalone, flat, nested, non-canvas, unknown.

    Order matters: a repo can carry a stray old nested directory alongside an
    already-completed flat migration (e.g. a half-finished --finalize) — flat
    is checked FIRST so that case reads as "flat" (finish finalizing) rather
    than "nested" (re-migrate something already migrated)."""
    if (course_root / flat.CLONE_DIR / ".git").is_dir():
        return "flat"
    if (course_root / NESTED_DIR_NAME / ".git").is_dir():
        return "nested"
    if (course_root / "lib" / "tools").is_dir() and (course_root / "AGENTS.md").is_file():
        return "standalone"
    return "unknown"


def is_canvas_configured(course_root: Path) -> bool:
    """Reused from cb_update.py rather than reimplemented — the same
    non-Canvas-consumer detection (#279): CANVAS_COURSE_ID in the environment
    or the course .env."""
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


def plan_migration(course_root: Path) -> dict:
    """Read-only description of what migration would do. Never writes."""
    layout = detect_layout(course_root)
    return {
        "layout": layout,
        "canvas_configured": is_canvas_configured(course_root) if layout != "unknown" else None,
        "steps": [
            "relocate canvas-toolbox/ -> .canvas-toolbox/ (local clone, history preserved, "
            "origin repointed at the real remote; canvas-toolbox/ is NOT deleted yet)",
            "remove stale .claude/skills/<skill> symlinks (and Windows copy-fallback dirs)",
            "flatten the distribution set from .canvas-toolbox/ to the course root",
            "merge AGENTS.md (backup to AGENTS.merge.md, fresh constitution copied in — "
            "the merge SKILL and merge_cleanup.py still finish this, same as any other update)",
            "replace a stale nested-path grade_guardian hook with the flat-path one",
            "run the 7-check verification report",
            "(separate step, --finalize only) remove the old canvas-toolbox/ directory",
        ] if layout == "nested" else [],
    }


# ---------------------------------------------------------------------------
# Step 1 — relocate the nested clone
# ---------------------------------------------------------------------------

def relocate_nested_clone(course_root: Path, apply: bool) -> str:
    """present/DIRTY/no-nested-clone/would-relocate/relocated.

    A LOCAL clone (not a rename) — the old canvas-toolbox/ stays fully intact
    so rollback before --finalize never has to reconstruct anything."""
    nested = course_root / NESTED_DIR_NAME
    dest = course_root / flat.CLONE_DIR
    if dest.is_dir():
        return "present"
    if not nested.is_dir() or not (nested / ".git").is_dir():
        return "no-nested-clone"
    if not flat.clone_is_pristine(nested):
        return "DIRTY"
    if not apply:
        return "would-relocate"
    remote_url = subprocess.run(
        ["git", "-C", str(nested), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    subprocess.run(["git", "clone", "--quiet", str(nested), str(dest)], check=True)
    if remote_url:
        subprocess.run(["git", "-C", str(dest), "remote", "set-url", "origin", remote_url],
                       check=True)
    return "relocated"


# ---------------------------------------------------------------------------
# Step 2 — remove stale skill symlinks (and the Windows copy-fallback)
# ---------------------------------------------------------------------------

def remove_stale_skill_links(course_root: Path, apply: bool) -> list[tuple[str, str]]:
    """[(skill, status)] where status is one of: absent/course-owned/would-
    remove/removed. A real directory WITHOUT the `.cb_managed` marker
    (`_managed_copy()`, shared with cb_update.py) is a course's OWN
    same-named skill — never touched, matching the ownership rule everywhere
    else in this toolkit."""
    results: list[tuple[str, str]] = []
    skills_root = course_root / ".claude" / "skills"
    for skill in SKILLS:
        link = skills_root / skill
        if not link.exists() and not link.is_symlink():
            results.append((skill, "absent"))
            continue
        if link.is_symlink() or _managed_copy(link):
            if not apply:
                results.append((skill, "would-remove"))
                continue
            if link.is_symlink():
                link.unlink()
            else:
                shutil.rmtree(link, ignore_errors=True)
            results.append((skill, "removed"))
        else:
            results.append((skill, "course-owned"))
    return results


def remove_stale_claude_shim(course_root: Path, apply: bool) -> str:
    """absent/course-owned/would-remove/removed.

    Not part of Phase 6's flat design at all — Claude Code reads AGENTS.md
    natively (confirmed working throughout Phase 5/6's own sessions), so the
    shim is dead weight once flattened, not a hazard. Removed anyway rather
    than left: leaving a generated file whose purpose no longer applies is
    exactly the kind of stale-instruction drift AGENTS.md warns about
    elsewhere (canvas_course_expert.md's .imscc contradiction, Phase 3)."""
    link = course_root / ".claude" / "CLAUDE.md"
    if not link.exists() and not link.is_symlink():
        return "absent"
    if not (link.is_symlink() or _managed_shim(link)):
        return "course-owned"
    if not apply:
        return "would-remove"
    link.unlink()
    return "removed"


# ---------------------------------------------------------------------------
# Step 4 — replace a stale nested-path guardian hook
# ---------------------------------------------------------------------------

_HOOK_PATH_RE = re.compile(r"\$\{?CLAUDE_PROJECT_DIR\}?/([^\"]*grade_guardian\.py)")


def fix_stale_guardian_hook(course_root: Path, apply: bool) -> str:
    """absent/already-flat/course-customized/bad-json/would-fix/fixed.

    grade_guardian.ensure_hook() deliberately never rewrites an existing hook
    (a course's own customization is left alone) — correct for an ordinary
    flatten, wrong here: the hook, if any, points at the nested subdirectory
    that finalize_migration() is about to delete. Only a hook whose path
    resolves under canvas-toolbox/ is replaced; anything else (including a
    course's genuinely different customization) is left untouched, matching
    "never rewrite arbitrary course prose without an explicit reviewed plan.\""""
    settings_path = course_root / ".claude" / "settings.json"
    if not settings_path.is_file():
        return "absent"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "bad-json"

    pre = settings.get("hooks", {}).get("PreToolUse", [])
    stale_entry = None
    for entry in pre:
        for h in entry.get("hooks", []):
            command = h.get("command") or ""
            if "grade_guardian" not in command:
                continue
            match = _HOOK_PATH_RE.search(command)
            if match and match.group(1).startswith(f"{NESTED_DIR_NAME}/"):
                stale_entry = entry
            elif match and match.group(1) == "lib/tools/grade_guardian.py":
                return "already-flat"          # the expected steady state — nothing to fix
            else:
                return "course-customized"     # a grade_guardian hook, but neither of the above
    if stale_entry is None:
        return "absent"
    if not apply:
        return "would-fix"

    settings["hooks"]["PreToolUse"] = [e for e in pre if e is not stale_entry]
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    flat.ensure_guardian_hook(course_root, apply=True)
    return "fixed"


# ---------------------------------------------------------------------------
# Step 6 — finalize (the one irreversible step) / rollback
# ---------------------------------------------------------------------------

def finalize_migration(course_root: Path) -> str:
    """no-flat-clone/nested-already-gone/not-verified/finalized/
    finalized-merge-pending.

    Requires the SAME 7-check verification report cb_flatten.py's own --apply
    uses to pass before removing anything — "the operation is not reported as
    complete if a required verification fails" applies here at its highest
    stakes, since this step cannot be undone by this tool.

    Deleting the old nested clone is safe even with an unresolved AGENTS.md
    merge: merge_cleanup.py reads its source from .canvas-toolbox/, never from
    the nested canvas-toolbox/ this step removes, so a pending
    AGENTS.merge.md stays exactly as completable after finalize as before it
    — nothing here makes that recoverable state any less recoverable. But
    "finalized" alone would read as "fully done," so a pending merge gets its
    own status rather than silently folding into the clean case."""
    nested = course_root / NESTED_DIR_NAME
    clone = course_root / flat.CLONE_DIR
    if not clone.is_dir():
        return "no-flat-clone"
    if not nested.is_dir():
        return "nested-already-gone"
    results = flat.verification_report(course_root, clone, [])
    if not all(ok for ok, _ in results):
        return "not-verified"
    _rmtree(nested)
    if (course_root / "AGENTS.merge.md").is_file():
        return "finalized-merge-pending"
    return "finalized"


def rollback(course_root: Path) -> str:
    """no-flat-clone/rolled-back-pre-finalize/rolled-back-post-finalize.

    Pre-finalize: canvas-toolbox/ was never touched, so this only needs to
    undo what THIS tool wrote — remove .canvas-toolbox/, and if a merge was
    left mid-flight, restore AGENTS.merge.md -> AGENTS.md. The newly-
    flattened root files (lib/, skills/, etc.) are left in place: they are
    toolkit-owned and replaceable by construction, and removing them here
    would just be redone identically by the next flatten.

    Post-finalize: canvas-toolbox/ is gone, so it is reconstructed by cloning
    .canvas-toolbox/ back out under that name (same history) — but the
    flattened root files are NOT removed, since they are now the only copy of
    the toolkit and removing them would leave the course broken rather than
    merely un-migrated."""
    clone = course_root / flat.CLONE_DIR
    nested = course_root / NESTED_DIR_NAME
    if not clone.is_dir():
        return "no-flat-clone"
    backup = course_root / "AGENTS.merge.md"
    target = course_root / "AGENTS.md"
    if nested.is_dir():
        _rmtree(clone)
        if backup.is_file():
            if target.is_file():
                target.unlink()
            backup.rename(target)
        return "rolled-back-pre-finalize"
    subprocess.run(["git", "clone", "--quiet", str(clone), str(nested)], check=True)
    return "rolled-back-post-finalize"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--course-root", type=Path, required=True)
    ap.add_argument("--apply", action="store_true", help="write (else dry-run)")
    ap.add_argument("--finalize", action="store_true",
                    help="remove the old canvas-toolbox/ directory — the one "
                         "irreversible step. Requires verification to pass first.")
    ap.add_argument("--rollback", action="store_true")
    args = ap.parse_args()
    root: Path = args.course_root

    if args.rollback:
        print(f"rollback: {rollback(root)}")
        return 0

    if args.finalize:
        status = finalize_migration(root)
        print(f"finalize: {status}")
        if status == "finalized-merge-pending":
            print("  ↳ the old canvas-toolbox/ is removed, but AGENTS.merge.md is still "
                  "here — an earlier merge_cleanup run didn't pass. Finish it: run the merge "
                  "skill, then `uv run python lib/tools/merge_cleanup.py`. Nothing was lost.")
            return 0
        return 0 if status == "finalized" else 2

    layout = detect_layout(root)
    print(f"layout: {layout}")
    if layout != "nested":
        print("nothing to migrate — this tool only handles the nested layout.")
        return 0 if layout in ("flat", "standalone") else 1

    print(f"Canvas configured: {is_canvas_configured(root)}")

    reloc = relocate_nested_clone(root, args.apply)
    print(f"relocate canvas-toolbox/ -> {flat.CLONE_DIR}/: {reloc}")
    if reloc == "DIRTY":
        print("  🔴 the nested clone has local modifications — inspect and reset it first.",
              file=sys.stderr)
        return 2
    if reloc == "would-relocate":
        print("  (dry-run: nothing else can be planned until the clone is relocated)")
        return 0

    for skill, status in remove_stale_skill_links(root, args.apply):
        print(f"  skill symlink {skill}: {status}")
    print(f"CLAUDE.md shim: {remove_stale_claude_shim(root, args.apply)}")

    clone = root / flat.CLONE_DIR
    old_gi = (root / ".gitignore").read_text(encoding="utf-8") if (root / ".gitignore").is_file() else ""
    old_manifest = flat.parse_gitignore_block(old_gi)
    try:
        new_manifest, packages = flat.resolve_distribution(clone)
    except flat.DistributionError as exc:
        print(f"  🔴 {exc}", file=sys.stderr)
        return 2
    to_copy, to_delete = flat.plan_sync(old_manifest, new_manifest)
    print(f"distribution: {len(to_copy)} to copy, {len(to_delete)} to remove, "
          f"packages: {', '.join(packages) or '(legacy)'}")
    counts = flat.apply_sync(clone, root, to_copy, to_delete, args.apply,
                             previously_owned=old_manifest)
    print(f"{'wrote' if args.apply else 'would write'}: {counts['copied']} copied, "
          f"{counts['deleted']} removed")
    if counts["backed_up"]:
        backup_verb = "backed up" if args.apply else "would back up"
        print(f"  🟡 {counts['backed_up']} course file(s) collided with a toolkit path — "
              f"{backup_verb} rather than overwritten: {counts['backed_up_paths']}")

    # FOUND FOR REAL, first time a pilot tried to commit a migrated course:
    # this step was missing entirely. cb_flatten.py's own --apply writes the
    # gitignore block right after apply_sync(); this function read the block
    # (old_manifest, above) but never wrote it back. Left as-is, a migrated
    # course's .gitignore never gains an ignore entry for ANY of the 280+
    # flattened toolkit files or for .canvas-toolbox/ itself — `git add -A`
    # would track the whole toolkit into the course's own history and create
    # a gitlink for the hidden clone, exactly backwards from the nested
    # layout's "toolkit code isn't part of course version control" model this
    # is supposed to preserve.
    gi_path = root / ".gitignore"
    updated_gi = flat.splice_gitignore(old_gi, flat.render_gitignore_block(to_copy))
    if updated_gi != old_gi:
        if args.apply:
            gi_path.write_text(updated_gi, encoding="utf-8")
        print(f"gitignore block: {'updated' if args.apply else 'would update'} "
              f"({len(to_copy)} exact paths)")
    else:
        print("gitignore block: present")

    agents_status = flat.apply_agents_md_step(root, clone, args.apply)
    print(f"AGENTS.md: {agents_status}")

    hook_status = fix_stale_guardian_hook(root, args.apply)
    print(f"guardian hook: {hook_status}")
    if hook_status == "absent":
        install_status = flat.ensure_guardian_hook(root, args.apply)
        print(f"  no hook existed at all — {install_status}")

    if not args.apply:
        print("\nDRY RUN — re-run with --apply to write.")
        return 0

    print("\nverification:")
    results = flat.verification_report(root, clone, to_delete)
    for ok, msg in results:
        print(f"  {'✓' if ok else '✗'} {msg}")
    if not all(ok for ok, _ in results):
        print("\n🔴 migration applied, but verification FAILED — see ✗ above. "
              "canvas-toolbox/ was NOT removed; nothing is lost. Fix the issue "
              "and re-run, or use --rollback.", file=sys.stderr)
        return 2

    print(f"\nVerified. canvas-toolbox/ is preserved until you run --finalize. "
          f"{flat.RELOAD_NOTICE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

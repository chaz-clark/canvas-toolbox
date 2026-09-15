#!/usr/bin/env python3
"""cb_flatten.py — flatten the toolkit into the course root, updated from a
hidden pristine clone (proposal Phases 1-2).

THE SHAPE

    DS250/                       # the course repo — you work HERE
    ├── .canvas-toolbox/         # hidden pristine clone (gitignored) — never edited
    ├── lib/ bin/ docs/ knowledge/   # flattened FROM that clone
    ├── pyproject.toml uv.lock
    ├── AGENTS.md  .env  course/  grading/     # course-owned
    └── .gitignore               # carries a generated block for the flattened set

WHY A HIDDEN CLONE RATHER THAN JUST COPYING FILES

  The clone is never edited and never executed from, so `git pull` inside it can
  never conflict. That buys three things that would otherwise be bespoke code:

    * a clean update            — pull into a tree with no local changes
    * the ownership manifest    — `git ls-files` IS the list of toolkit files,
                                  so "is this path ours?" needs no bookkeeping
    * deletion tracking         — what we flattened LAST time, minus the
                                  manifest now, is exactly the set removed
                                  upstream. A set difference, not a diff engine.

WHAT GETS FLATTENED — OWNERSHIP VS. DISTRIBUTION (v2, #317 Phase 4)

  `git ls-files` answers "is this toolkit-owned?" — every tracked file, including
  lib/tests/, docs/proposals/, .github/, and the rest of the toolkit's own
  development surface. That is a different question from "should this land in
  every course repo?" `resolve_distribution()` answers the second, narrower
  question from `distribution/manifest.yaml` in the clone — an explicit,
  schema-validated allowlist (docs/proposals/v2-agent-packaging-plan.md section 8).

  A clone at a commit before Phase 4 has no distribution manifest — that is the
  LEGACY case, not an error: `resolve_distribution()` falls back to the full
  `git ls-files` set, reproducing the old (wasteful, but not broken) behavior. A
  manifest that EXISTS but is malformed, or whose declared paths resolve to zero
  tracked files, IS an error: refuse loudly and write nothing, rather than
  silently flattening less than the manifest intended.

  The "before" side is read from the .gitignore block this tool writes, NOT
  re-derived from the clone. Reading both sides off the clone only holds if our
  own --pull is the sole way it ever changes; it isn't (someone pulls by hand, a
  sync dies mid-way), and then the before-state is gone, the diff is empty, and
  a file deleted upstream survives at the course root forever. A 381-file smoke
  test found exactly that. The block is the durable record of what we wrote, so
  it is the honest source — and still no separate state file to fall out of sync.

WHAT IS NOT FLATTENED

  Two files are HYBRID — part toolkit, part course — and a blind copy would
  destroy the course's half:

    AGENTS.md   toolkit constitution + the course's HERMES learning. Handled by
                the merge skill + merge_cleanup.py (Phase 3), never by this tool.
    .gitignore  the toolkit's own ignores + the course's. This tool only rewrites
                its own sentinel-delimited block and leaves the rest alone.

  `.git/` is excluded for the obvious reason. Everything else in the manifest is
  toolkit-owned and replaced wholesale.

WHY THE FLATTENED SET IS GITIGNORED, NOT COMMITTED

  Rollback does not require the course repo to track 377 toolkit files: the
  hidden clone holds the full history, so `git -C .canvas-toolbox reset --hard
  <sha>` followed by a re-sync restores any prior state deterministically. Git
  still controls the update — it is just the clone's git. The course repo stays
  about the course.

  The ignore block lists EXACT PATHS, never a directory blanket. #271 is the
  reason: a blanket `.claude/skills/` also hid the course's OWN skills, and
  `git add -A` then silently skipped them. Ignoring exactly what this tool
  writes means a course-owned file is protected by construction.

  KNOWN EXCEPTION — one file stays git-visible, and it cannot be fixed here.
  `scaffold/grading/.gitignore` is the FERPA gate template and carries
  `!answer_keys/README.md`. In git a NEGATION in a deeper .gitignore outranks an
  ignore rule in a shallower one, so the root block cannot re-exclude that path.
  It is one template README; nothing is committed unless someone runs
  `git add -A`, and then it is a template. Accepted, and pinned by a test so the
  count cannot grow silently.

USAGE
  uv run python lib/tools/cb_flatten.py                 # dry-run
  uv run python lib/tools/cb_flatten.py --apply
  uv run python lib/tools/cb_flatten.py --pull --apply  # update, then re-sync
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

CLONE_DIR = ".canvas-toolbox"
DEFAULT_REMOTE = "https://github.com/chaz-clark/canvas-toolbox.git"
DISTRIBUTION_MANIFEST = "distribution/manifest.yaml"

#: Paths the flatten never writes. AGENTS.md and .gitignore are HYBRID — the
#: course owns part of each — so copying them over would destroy course content.
HYBRID = frozenset({"AGENTS.md", ".gitignore"})

GI_START = "# >>> canvas-toolbox flattened files (generated — do not edit) >>>"
GI_END = "# <<< canvas-toolbox flattened files <<<"

#: Artifacts the FLATTENED toolkit creates when it runs. The toolkit's own
#: .gitignore covers these, but it is hybrid and deliberately never flattened,
#: so the course would otherwise see __pycache__ churn in `git status`.
RUNTIME_IGNORES = ("__pycache__/", "*.pyc", "*.pyo", ".venv/")


# ---------------------------------------------------------------------------
# Pure helpers — no filesystem writes, no subprocess. Unit-testable.
# ---------------------------------------------------------------------------

def plan_sync(old_manifest: set[str], new_manifest: set[str],
              exclude: frozenset[str] = HYBRID) -> tuple[list[str], list[str]]:
    """(to_copy, to_delete) for one sync.

    to_delete is `old - new`: paths that existed in the toolkit before the pull
    and do not after, i.e. removed upstream. Without this a stale tool lingers
    at the course root forever and an agent can still find and run it.

    Both lists are sorted so a dry-run diff is stable and reviewable."""
    to_copy = sorted(p for p in new_manifest if p not in exclude)
    to_delete = sorted(p for p in (old_manifest - new_manifest) if p not in exclude)
    return to_copy, to_delete


def render_gitignore_block(paths: list[str]) -> str:
    """The sentinel-delimited ignore block — EXACT paths, never a blanket.

    A blanket directory ignore is what #271 shipped, and it also hid files the
    COURSE owned inside those directories; `git add -A` then skipped them
    silently. Listing exactly what this tool writes keeps the ignore set equal
    to the toolkit's own footprint, so anything else is visible by construction.

    Manifest paths are anchored with a leading `/` — that is also what makes the
    block re-readable as the record of what was last flattened (see
    parse_gitignore_block). The unanchored RUNTIME_IGNORES are patterns, not
    paths, and are skipped by that parser."""
    body = "\n".join(list(RUNTIME_IGNORES) + [f"/{p}" for p in sorted(paths)])
    return f"{GI_START}\n{body}\n{GI_END}\n"


def parse_gitignore_block(existing: str) -> set[str]:
    """The manifest paths currently in the block — i.e. WHAT WAS FLATTENED LAST
    TIME.

    This is the "before" side of deletion tracking, and it has to come from here
    rather than from the clone. Reading both sides off the clone only works if
    this tool's own `--pull` is the sole way the clone ever changes — it isn't.
    Someone pulls it by hand, or a sync dies between the pull and the copy, and
    the "before" state is gone: the manifest diff comes back empty and a file
    deleted upstream silently survives at the course root forever. Found exactly
    that way in a real 381-file smoke test.

    The block is the durable record of what this tool wrote, so it is the honest
    source. No extra state file to fall out of sync."""
    if GI_START not in existing or GI_END not in existing:
        return set()
    inner = existing[existing.index(GI_START) + len(GI_START):existing.index(GI_END)]
    return {ln.strip().lstrip("/") for ln in inner.splitlines()
            if ln.strip().startswith("/")}


def splice_gitignore(existing: str, block: str) -> str:
    """Replace our block in place, or append it. Everything outside the sentinels
    is the course's and is preserved byte for byte."""
    if GI_START in existing and GI_END in existing:
        head = existing[:existing.index(GI_START)]
        tail = existing[existing.index(GI_END) + len(GI_END):].lstrip("\n")
        return f"{head}{block}{tail}"
    sep = "" if (not existing or existing.endswith("\n")) else "\n"
    joiner = "\n" if existing else ""
    return f"{existing}{sep}{joiner}{block}"


# ---------------------------------------------------------------------------
# Git-backed manifest
# ---------------------------------------------------------------------------

def _git(clone: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(clone), *args],
                          capture_output=True, text=True, check=True).stdout


def manifest(clone: Path) -> set[str]:
    """The toolkit's own file list at the clone's current HEAD — this IS the
    ownership boundary. A path in here is toolkit-owned and replaceable; a path
    at the course root that is not is course-owned and never touched."""
    return {ln for ln in _git(clone, "ls-files").splitlines() if ln.strip()}


class DistributionError(Exception):
    """distribution/manifest.yaml exists but cannot be resolved. Raised rather than
    silently falling back — a broken manifest must refuse loudly, not quietly
    flatten a smaller-than-intended (or empty) set. Never raised for an ABSENT
    manifest; that is the legacy pre-Phase-4 case and falls back to the full
    tracked-file set instead."""


def resolve_distribution(clone: Path) -> tuple[set[str], list[str]]:
    """(course-facing file set, package ids) resolved from
    `distribution/manifest.yaml` against the clone's tracked files.

    `git ls-files` answers "is this toolkit-owned?" — every tracked file, including
    lib/tests/, docs/proposals/, .github/, and the rest of the toolkit's own
    development surface. That is NOT the same question as "should this land in
    every course repo?" (docs/proposals/v2-agent-packaging-plan.md section 8). This
    resolves the second, narrower question from the distribution manifest.

    LEGACY FALLBACK: a clone at a commit before Phase 4 has no
    distribution/manifest.yaml. That is not an error — it is the pre-Phase-4
    toolkit, which never drew this distinction, so falling back to the full
    tracked-file set reproduces its old (if wasteful) behavior instead of flattening
    nothing. A manifest that EXISTS but is malformed or resolves an entry to zero
    files IS an error (DistributionError) — a broken manifest never silently
    installs less than intended."""
    path = clone / DISTRIBUTION_MANIFEST
    if not path.is_file():
        return manifest(clone), []

    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DistributionError(f"{DISTRIBUTION_MANIFEST}: cannot read/parse: {exc}") from exc
    if not isinstance(doc, dict):
        raise DistributionError(f"{DISTRIBUTION_MANIFEST}: must be a YAML mapping")

    tracked = manifest(clone)
    resolved: set[str] = set()
    for i, entry in enumerate(doc.get("entries") or []):
        if not isinstance(entry, dict) or "path" not in entry or "kind" not in entry:
            raise DistributionError(f"{DISTRIBUTION_MANIFEST}: entries[{i}] missing path/kind")
        entry_path, kind = entry["path"], entry["kind"]
        if kind == "file":
            matches = {entry_path} if entry_path in tracked else set()
        elif kind == "tree":
            prefix = entry_path.rstrip("/") + "/"
            matches = {p for p in tracked if p.startswith(prefix)}
        else:
            raise DistributionError(f"{DISTRIBUTION_MANIFEST}: entries[{i}] unknown kind {kind!r}")
        if not matches:
            raise DistributionError(
                f"{DISTRIBUTION_MANIFEST}: entries[{i}] ({entry_path!r}) resolved to "
                f"zero tracked files — stale or misspelled path"
            )
        resolved |= matches

    packages = doc.get("packages") or []
    if not isinstance(packages, list):
        raise DistributionError(f"{DISTRIBUTION_MANIFEST}: 'packages' must be a list")
    return resolved, packages


def clone_is_pristine(clone: Path) -> bool:
    """The clone must never be edited — that is what makes `git pull` unable to
    conflict. A dirty clone means someone worked in the wrong directory."""
    return not _git(clone, "status", "--porcelain").strip()


def ensure_clone(course_root: Path, remote: str, apply: bool) -> str:
    """present / would-clone / cloned / DIRTY."""
    clone = course_root / CLONE_DIR
    if (clone / ".git").is_dir():
        return "present" if clone_is_pristine(clone) else "DIRTY"
    if not apply:
        return "would-clone"
    subprocess.run(["git", "clone", "--quiet", remote, str(clone)], check=True)
    return "cloned"


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_sync(clone: Path, course_root: Path,
               to_copy: list[str], to_delete: list[str], apply: bool) -> dict:
    """Copy the toolkit's files to the course root and remove what upstream
    deleted. Returns counts; never touches a path outside the two lists."""
    counts = {"copied": 0, "deleted": 0, "missing": 0}
    for rel in to_delete:
        dst = course_root / rel
        if not dst.exists():
            continue
        if apply:
            dst.unlink()
            _prune_empty_dirs(dst.parent, course_root)
        counts["deleted"] += 1
    for rel in to_copy:
        src, dst = clone / rel, course_root / rel
        if not src.is_file():
            counts["missing"] += 1
            continue
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        counts["copied"] += 1
    return counts


def _prune_empty_dirs(start: Path, stop: Path) -> None:
    """A file removed upstream can leave an empty directory behind; an empty
    `lib/tools/` at the course root reads as 'the toolkit is installed'."""
    cur = start
    while cur != stop and cur.is_dir() and not any(cur.iterdir()):
        cur.rmdir()
        cur = cur.parent


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(
        description="Flatten the toolkit into the course root from a hidden clone.")
    ap.add_argument("--course-root", type=Path, default=Path.cwd())
    ap.add_argument("--remote", default=DEFAULT_REMOTE)
    ap.add_argument("--pull", action="store_true",
                    help="git pull the hidden clone first, then re-sync")
    ap.add_argument("--apply", action="store_true", help="write (else dry-run)")
    args = ap.parse_args()

    root: Path = args.course_root
    clone = root / CLONE_DIR

    status = ensure_clone(root, args.remote, args.apply)
    print(f"hidden clone {CLONE_DIR}/: {status}")
    if status == "DIRTY":
        print("  🔴 the clone has local modifications. It must stay pristine so a "
              "pull cannot conflict.\n     Inspect it, then reset it — do not "
              "edit files in there.", file=sys.stderr)
        return 2
    if status == "would-clone":
        print("  (dry-run: nothing else can be planned until the clone exists)")
        return 0

    if args.pull:
        print(f"pulling {CLONE_DIR}/ …")
        if args.apply:
            out = _git(clone, "pull", "--ff-only")
            print("  " + (out.strip().splitlines()[-1] if out.strip() else "pulled"))
        else:
            print("  (dry-run: not pulling)")

    gi = root / ".gitignore"
    existing = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    # The "before" side is what we flattened LAST time, read from the ignore
    # block — not re-derived from the clone, which may have moved underneath us.
    old = parse_gitignore_block(existing)
    try:
        new, packages = resolve_distribution(clone)
    except DistributionError as exc:
        # Refuse loudly and write nothing — the prior install and the hidden clone
        # both stay exactly as they were. A broken distribution manifest must never
        # result in a partial or empty flatten.
        print(f"  🔴 {exc}", file=sys.stderr)
        return 2

    to_copy, to_delete = plan_sync(old, new)
    print(f"\npackages: {', '.join(packages) if packages else '(legacy full manifest — no distribution/manifest.yaml in clone)'}")
    print(f"plan: {len(to_copy)} to copy, {len(to_delete)} to remove "
          f"(upstream deletions), {len(HYBRID)} hybrid files skipped "
          f"({', '.join(sorted(HYBRID))})")
    for rel in to_delete:
        print(f"  remove  {rel}")
    for pkg_id in packages:
        pkg_path = clone / "agent-packages" / pkg_id / "manifest.yaml"
        if not pkg_path.is_file():
            continue
        pkg = yaml.safe_load(pkg_path.read_text(encoding="utf-8"))
        canvas_writes = sum(1 for t in pkg.get("tools", []) if t.get("effect", "").startswith("canvas_"))
        print(f"  package {pkg_id}: {len(pkg.get('tools', []))} tools "
              f"({canvas_writes} touch Canvas, always-confirmed)")

    counts = apply_sync(clone, root, to_copy, to_delete, args.apply)
    verb = "wrote" if args.apply else "would write"
    print(f"{verb}: {counts['copied']} copied, {counts['deleted']} removed"
          + (f", {counts['missing']} missing from clone" if counts["missing"] else ""))

    updated = splice_gitignore(existing, render_gitignore_block(to_copy))
    if updated != existing:
        if args.apply:
            gi.write_text(updated, encoding="utf-8")
        print(f"gitignore block: {'updated' if args.apply else 'would update'} "
              f"({len(to_copy)} exact paths — never a directory blanket, see #271)")
    else:
        print("gitignore block: present")

    if not args.apply:
        print("\nDRY RUN — re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

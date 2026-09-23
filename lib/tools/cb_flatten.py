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

  Four files are HYBRID — part toolkit, part course — and a blind copy would
  destroy the course's half:

    AGENTS.md         toolkit constitution + the course's HERMES learning.
                       Handled by the merge skill + merge_cleanup.py (Phase 3),
                       never by this tool.
    .gitignore         the toolkit's own ignores + the course's. This tool only
                       rewrites its own sentinel-delimited block and leaves the
                       rest alone.
    pyproject.toml     the host repo's own project identity (name, version,
    uv.lock            description, license, authors) plus its own dependency
                       set. A course repo consuming canvas-toolbox is never the
                       same project AS canvas-toolbox — copying the toolkit's
                       own pyproject.toml/uv.lock wholesale replaces the host's
                       identity outright (found for real in the m119-master
                       pilot: `uv run` started identifying the whole course
                       repo as "canvas-toolbox"). This tool never overwrites
                       an EXISTING host pyproject.toml — report_pyproject_deps()
                       only reports which of the toolkit's dependencies are
                       missing, for a human to add by hand and re-run `uv lock`.
                       When there is no host pyproject.toml AT ALL (nothing to
                       protect), it writes a minimal one instead of leaving a
                       fresh install with no way to `uv sync` at all; uv.lock is
                       still never written directly — cb_init.py's `uv sync`
                       step generates it.

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
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

from merge_cleanup import (
    COURSE_END,
    COURSE_MARKER,
    HARD_FLAG_LINES,
    RELOAD_NOTICE,
    SOFT_WARN_LINES,
    default_course_content,
    split_merged,
)

# Reused rather than reimplemented — architecture-agnostic (operate on .env text
# or a token/URL pair, not on the nested-vs-flat distinction).
from cb_init import env_stub_content, smoke_test_canvas

# The CLAUDE.md shim — cb_update.py's own main() already installs this on every
# UPDATE. FOUND FOR REAL auditing the fresh-install path (#317 follow-up): this
# tool's own main() never called it, so a course bootstrapped by cb_flatten.py
# alone (no cb_update.py run yet) had an AGENTS.md Claude Code would never read —
# not just missing course content, the WHOLE constitution invisible at session
# start. No circular import: cb_update.py does not import this module.
from cb_update import CLAUDE_SHIM, install_claude_shim, plan_claude_shim

from capability_consent import (
    capability_diff,
    compute_fingerprint,
    has_grown,
    load_approvals,
    record_approval,
    render_install_summary,
)

try:
    from grade_guardian import ensure_hook as _ensure_guardian_hook
except ImportError:
    _ensure_guardian_hook = None

try:
    from _env_loader import _global_values as _global_credential_values
except ImportError:
    _global_credential_values = None

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
#: pyproject.toml/uv.lock are HYBRID too, for the same reason but a sharper
#: failure mode: overwriting them destroys the HOST REPO'S OWN project identity
#: (name, version, dependencies), not just some course content within a
#: toolkit-owned file. See report_pyproject_deps().
HYBRID = frozenset({"AGENTS.md", ".gitignore", "pyproject.toml", "uv.lock"})

GI_START = "# >>> canvas-toolbox flattened files (generated — do not edit) >>>"
GI_END = "# <<< canvas-toolbox flattened files <<<"

#: Artifacts the FLATTENED toolkit creates when it runs. The toolkit's own
#: .gitignore covers these, but it is hybrid and deliberately never flattened,
#: so the course would otherwise see __pycache__ churn in `git status`.
#:
#: FOUND FOR REAL, first time a pilot actually tried to commit a flattened
#: course: CLONE_DIR (.canvas-toolbox/) was never in this list, despite this
#: module's own header comment claiming it is "gitignored". It has its own
#: .git — `git add -A` on an ignorant repo creates a gitlink (mode 160000)
#: pointing at whatever commit the clone happened to be on, not a real
#: submodule, and a plain `git clone` of the course repo afterward gets an
#: EMPTY .canvas-toolbox/ directory instead of the toolkit. Listed by name
#: (not CLONE_DIR the variable) so a stale rendered block in an old course's
#: .gitignore still reads correctly without needing this module to run.
RUNTIME_IGNORES = ("__pycache__/", "*.pyc", "*.pyo", ".venv/", ".canvas-toolbox/")


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
                          capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout


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
               to_copy: list[str], to_delete: list[str], apply: bool,
               previously_owned: set[str] | None = None) -> dict:
    """Copy the toolkit's files to the course root and remove what upstream
    deleted. Returns counts; never touches a path outside the two lists.

    previously_owned: paths this tool is on record as having written before
    (read from the course's own gitignore block — see parse_gitignore_block).
    A path in to_copy that is NOT in this set is landing at this course root
    for the first time. If something already sits there and its content
    differs from the toolkit's own copy, that is not a toolkit file being
    updated — it is real, pre-existing course content that happens to share
    the toolkit's path. FOUND FOR REAL during the m119-master pilot:
    knowledge/behavioral_discipline.md was the course's own tracked file,
    silently replaced with the toolkit's same-named one. Back the collision
    up instead of destroying it; a path already in previously_owned is an
    ordinary toolkit-file update and is still always overwritten. Passing
    None (the default) preserves the old unconditional-overwrite behavior —
    only main()'s real apply path opts into the protection, since that is the
    only caller with an actual provenance record to check against."""
    counts = {"copied": 0, "deleted": 0, "missing": 0, "backed_up": 0}
    backed_up: list[str] = []
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
        is_new_path = previously_owned is not None and rel not in previously_owned
        if is_new_path and dst.is_file() and dst.read_bytes() != src.read_bytes():
            backed_up.append(rel)
            if apply:
                dst.rename(dst.with_name(dst.name + ".pre-flatten-backup"))
            counts["backed_up"] += 1
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        counts["copied"] += 1
    counts["backed_up_paths"] = backed_up
    return counts


def _prune_empty_dirs(start: Path, stop: Path) -> None:
    """A file removed upstream can leave an empty directory behind; an empty
    `lib/tools/` at the course root reads as 'the toolkit is installed'."""
    cur = start
    while cur != stop and cur.is_dir() and not any(cur.iterdir()):
        cur.rmdir()
        cur = cur.parent


_DEP_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _dependency_names(deps: list[str]) -> set[str]:
    """PEP 508 requirement strings -> bare package names, normalized like PyPI
    does (case-insensitive, `_`/`.` treated as `-`) so `Python-Dotenv` in one
    file matches `python-dotenv` in the other."""
    names = set()
    for dep in deps:
        match = _DEP_NAME_RE.match(dep)
        if match:
            names.add(match.group(1).lower().replace("_", "-").replace(".", "-"))
    return names


def render_fresh_pyproject(course_root: Path, clone_toml: dict) -> str:
    """A minimal host pyproject.toml for a course with NONE yet — pure, no I/O.

    Never used when a host file already exists (that's the HYBRID overwrite
    bug this whole function family exists to avoid, #327/m119-master) — only
    when there is nothing to protect. Carries canvas-toolbox's own runtime
    dependencies + dev group + requires-python (what `uv sync --group dev` and
    `pre-commit install` in cb_init.py's later steps need to actually work);
    deliberately NOT the toolkit's own ruff/lint config, which is a style
    preference for canvas-toolbox's own codebase, not something to impose on
    every course repo. `name` is slugified from the course root's folder name —
    never "canvas-toolbox" (the exact identity-clobber #327 fixed)."""
    project = clone_toml.get("project", {})
    deps = project.get("dependencies", [])
    dev_deps = clone_toml.get("dependency-groups", {}).get("dev", [])
    requires_python = project.get("requires-python", ">=3.11")
    slug = re.sub(r"[^a-z0-9]+", "-", course_root.name.lower()).strip("-") or "course"

    lines = [
        "[project]",
        f'name = "{slug}"',
        'version = "0.1.0"',
        f'requires-python = "{requires_python}"',
        "dependencies = [",
        *(f'    "{d}",' for d in deps),
        "]",
        "",
        "[dependency-groups]",
        "dev = [",
        *(f'    "{d}",' for d in dev_deps),
        "]",
        "",
    ]
    return "\n".join(lines)


def report_pyproject_deps(course_root: Path, clone: Path, apply: bool) -> tuple[bool, str]:
    """pyproject.toml/uv.lock are HYBRID (see HYBRID) and this never overwrites
    an EXISTING host file — that's the identity-clobber #327 fixed. But "don't
    overwrite" only protects something that exists; when there is truly nothing
    yet, leaving a human to hand-copy 14 dependency strings is real, avoidable
    friction for exactly the fresh-install case this function otherwise reports
    on and does nothing about. So: write one, only when none exists at all.

    Always ok=True: a missing dependency (when a host file DOES exist and is
    just incomplete) is real work for a human, not a failed flatten."""
    clone_pyproject = clone / "pyproject.toml"
    if not clone_pyproject.is_file():
        return True, "clone has no pyproject.toml — nothing to check"
    clone_toml = tomllib.loads(clone_pyproject.read_text(encoding="utf-8"))
    clone_deps = _dependency_names(clone_toml.get("project", {}).get("dependencies", []))
    host_pyproject = course_root / "pyproject.toml"
    if not host_pyproject.is_file():
        if not apply:
            return True, (f"would write a fresh pyproject.toml — {len(clone_deps)} "
                          "canvas-toolbox dependencies, then `uv sync` locks it")
        host_pyproject.write_text(render_fresh_pyproject(course_root, clone_toml),
                                  encoding="utf-8")
        return True, (f"wrote a fresh pyproject.toml — {len(clone_deps)} canvas-toolbox "
                      "dependencies; cb-init's `uv sync` step locks it")
    host_deps = _dependency_names(
        tomllib.loads(host_pyproject.read_text(encoding="utf-8"))
        .get("project", {}).get("dependencies", [])
    )
    missing = sorted(clone_deps - host_deps)
    if not missing:
        return True, "host pyproject.toml already covers all of canvas-toolbox's dependencies"
    return True, (f"{len(missing)} canvas-toolbox dependencies missing from host "
                  f"pyproject.toml — add by hand, then `uv lock`: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Capability consent (v2, #317 Phase 7). See capability_consent.py for the
# fingerprint/diff/approval design; this is only the orchestration glue that
# decides, for THIS run, whether --apply may proceed.
# ---------------------------------------------------------------------------

def check_capability_consent(
    clone: Path, root: Path, package_ids: list[str], approve: set[str], approve_all: bool,
) -> tuple[bool, list[str], list[tuple[str, dict, str]]]:
    """(ok, messages, pending_approvals).

    ok=False means refuse --apply: unapproved capability growth exists and
    neither `--approve <id>` nor `--approve-all` covers it. `pending_approvals`
    is [(package_id, fingerprint, approved_by)] to persist via record_approval()
    AFTER a successful apply — never before, so a refused/failed run records
    nothing.

    `--approve`/`--approve-all` require an interactive terminal (#343). Same
    reasoning as grader_push.py's require_typed_confirmation (HG-5, #241): a
    flag an agent can pass on its own isn't evidence a human is present — a
    `sys.stdin.isatty()` pipe/redirect/heredoc isn't a person. This ONLY gates
    growth that's actually being approved this run; a package with no growth
    is unaffected (an unattended `cb_flatten.py --apply` with nothing new to
    approve keeps working — this is about the capability-*install* decision,
    not about blocking unattended runs wholesale)."""
    human_present = sys.stdin.isatty()
    approvals = load_approvals(root)
    messages: list[str] = []
    pending: list[tuple[str, dict, str]] = []
    blocking = False
    for pkg_id in package_ids:
        pkg_path = clone / "agent-packages" / pkg_id / "manifest.yaml"
        if not pkg_path.is_file():
            continue
        package = yaml.safe_load(pkg_path.read_text(encoding="utf-8"))
        new_fp = compute_fingerprint(package)
        old_entry = approvals.get(pkg_id)
        old_fp = old_entry["fingerprint"] if isinstance(old_entry, dict) else None
        diff = capability_diff(old_fp, new_fp)
        first_approval = old_fp is None
        if has_grown(diff):
            claims_approval = pkg_id in approve or approve_all
            if claims_approval and not human_present:
                messages.append(
                    f"REFUSED (no interactive terminal) — {pkg_id}:\n"
                    + render_install_summary(package, diff, first_approval)
                    + "\n  --approve/--approve-all only count from a real terminal "
                      "(#343) — a pipe, redirect, or unattended/scheduled run isn't "
                      "a human approving this. Relay the summary above to the "
                      "instructor and re-run interactively once they say yes."
                )
                blocking = True
            elif claims_approval:
                messages.append(f"approved — {pkg_id}:\n"
                                + render_install_summary(package, diff, first_approval))
                pending.append((pkg_id, new_fp, "operator (relayed via --approve)"))
            else:
                messages.append(f"NEEDS APPROVAL — {pkg_id}:\n"
                                + render_install_summary(package, diff, first_approval))
                blocking = True
        else:
            # No growth: proceed without asking (checklist: "do not require
            # special approval for wording-only or capability-reducing
            # updates"), but still refresh the stored baseline so the NEXT
            # diff is computed against current reality, not a stale one.
            pending.append((pkg_id, new_fp, "auto (no capability growth)"))
    return (not blocking), messages, pending


# ---------------------------------------------------------------------------
# Fresh-install bootstrap (v2, #317 Phase 6): the steps a flat install needs
# beyond copying files. `cb_init.py`'s equivalent steps assume the OLD nested
# `<course-root>/canvas-toolbox/` layout (a separate git clone with its own
# pre-commit hooks, `.env` migration from a v1.5 location, etc.) — none of
# that applies here, so this is a deliberately smaller set:
#   included: credentials/.env, a read-only Canvas smoke test, the
#     grade_guardian PreToolUse hook (the most important safety piece).
#   NOT included: pre-commit installation. cb_init's step assumed the vendored
#     toolkit was itself a separate, dev-editable git clone with its own
#     .pre-commit-config.yaml. The flat model's .canvas-toolbox/ must stay
#     PRISTINE — installing a commit hook there is either meaningless (nothing
#     is ever committed inside it) or actively wrong (it would invite editing
#     the one directory that must never be edited). .pre-commit-config.yaml is
#     also deliberately excluded from distribution/manifest.yaml as toolkit-
#     dev-only. There is no course-repo equivalent of "lint the toolkit."
# ---------------------------------------------------------------------------

def _parse_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.is_file():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def _resolve_credentials(course_root: Path) -> tuple[dict[str, str], dict[str, str]]:
    """(values, sources) for CANVAS_API_TOKEN/CANVAS_BASE_URL — the ONE place
    this per-key merge happens. `credentials_resolve()`, `ensure_env_stub()`,
    and `canvas_smoke_test()` all need this same answer; before this they
    each read it their own way, and `canvas_smoke_test()`'s version never
    checked ~/.canvas/config at all — found by a real rehearsal against a
    live sandbox where the token lived there and the smoke test reported
    "not set" for a course that had just been audited successfully.

    PER-KEY merge across environment -> this course's .env -> ~/.canvas/config
    (the same precedence and per-key semantics `_env_loader.load_env()` uses,
    documented there as "Applied key-by-key rather than via load_dotenv() on
    the file") — NOT a per-SOURCE check (does source X have both keys?).
    CANVAS_BASE_URL in the course's own .env and CANVAS_API_TOKEN in the
    global config is a legitimate, common split (the whole point of the
    global file is holding the token ONCE for every course); a per-source
    check misses it entirely.

    Deliberately reads course_root directly rather than reusing cb_init's
    credentials_already_resolve(), which resolves via _env_loader.load_env()'s
    CWD-anchored upward walk — cb_flatten takes an explicit --course-root that
    need not be the process's CWD, so a CWD-based check could silently answer
    for the wrong repo."""
    import os
    file_values = _parse_env_file(course_root / ".env")
    global_values: dict[str, str] = {}
    if _global_credential_values is not None:
        global_values, _ = _global_credential_values()

    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for required in ("CANVAS_API_TOKEN", "CANVAS_BASE_URL"):
        if os.environ.get(required):
            values[required], sources[required] = os.environ[required], "environment"
        elif file_values.get(required):
            values[required] = file_values[required]
            sources[required] = str(course_root / ".env")
        elif global_values.get(required):
            values[required] = global_values[required]
            sources[required] = str(Path.home() / ".canvas" / "config")
    return values, sources


def credentials_resolve(course_root: Path) -> tuple[bool, str]:
    """(resolved, where) — does CANVAS_API_TOKEN + CANVAS_BASE_URL resolve via
    _resolve_credentials()'s per-key merge?"""
    values, sources = _resolve_credentials(course_root)
    if "CANVAS_API_TOKEN" not in values or "CANVAS_BASE_URL" not in values:
        return False, ""
    token_src, url_src = sources["CANVAS_API_TOKEN"], sources["CANVAS_BASE_URL"]
    where = token_src if token_src == url_src else f"{token_src} + {url_src}"
    return True, where


def ensure_env_stub(course_root: Path, apply: bool) -> str:
    """present/resolved-elsewhere/blank/would-write/written.

    Checks `credentials_resolve()` (the per-key merge) FIRST, regardless of
    whether a .env file exists — a course whose .env holds CANVAS_BASE_URL
    while CANVAS_API_TOKEN comes from ~/.canvas/config is fully resolved and
    must not be reported as blank just because neither source alone has both
    keys."""
    env_path = course_root / ".env"
    resolved, where = credentials_resolve(course_root)
    if resolved:
        if env_path.is_file():
            return f"credentials resolve ({where}) — .env present, nothing to add"
        return f"credentials already resolve from {where} — no .env needed"
    if env_path.is_file():
        return ("exists, but CANVAS_API_TOKEN/CANVAS_BASE_URL don't fully resolve from "
                "any source (environment, this .env, or ~/.canvas/config) — fill in "
                "whichever is missing")
    if not apply:
        return f"would write a stub to {env_path}"
    # scaffold/.env.example, not cb_init's own default (REPO_ROOT/.env.example) —
    # that default resolves relative to wherever cb_init.py itself is running
    # FROM, which in flattened-course invocation is the course root, and the
    # course-facing template lives under scaffold/, not at the course root.
    env_path.write_text(
        env_stub_content(course_root / "scaffold" / ".env.example"), encoding="utf-8"
    )
    return f"wrote a stub to {env_path} — fill CANVAS_API_TOKEN/CANVAS_BASE_URL, then re-run"


def canvas_smoke_test(course_root: Path) -> tuple[bool, str]:
    """Read-only GET /users/self. (True, msg) even when skipped — a course with
    no Canvas configured yet (or on another LMS entirely) is not a failure.

    Uses the same _resolve_credentials() merge ensure_env_stub() does — this
    used to check only the .env file and the environment, never
    ~/.canvas/config, so a token that resolved everywhere else in the toolkit
    still reported "not set" here."""
    values, _ = _resolve_credentials(course_root)
    token, base_url = values.get("CANVAS_API_TOKEN", ""), values.get("CANVAS_BASE_URL", "")
    if not token or not base_url:
        return True, "CANVAS_API_TOKEN or CANVAS_BASE_URL not set — skipped"
    if not base_url.startswith("http"):
        base_url = "https://" + base_url
    return smoke_test_canvas(token, base_url)


def ensure_guardian_hook(course_root: Path, apply: bool) -> str:
    """Wire the grade_guardian PreToolUse hook into .claude/settings.json.
    present/would-install/installed/skipped-no-script/bad-json — matching
    cb_init/cb_update's existing status vocabulary for this exact action."""
    if _ensure_guardian_hook is None:
        return "skipped-no-script"
    guardian = course_root / "lib" / "tools" / "grade_guardian.py"
    if not guardian.is_file():
        return "skipped-no-script"
    settings_path = course_root / ".claude" / "settings.json"
    try:
        existing = (json.loads(settings_path.read_text(encoding="utf-8"))
                   if settings_path.is_file() else {})
    except (OSError, ValueError):
        return "bad-json"
    # toolkit_subdir="" — the flat layout has no <course-root>/canvas-toolbox/
    # subdirectory; grade_guardian.py is flattened directly at lib/tools/. The
    # nested-layout default would point the hook at a path that never exists
    # here, and hook_command()'s own fail-open guard means it would silently
    # do nothing — installed, but inert.
    new_settings, changed = _ensure_guardian_hook(existing, toolkit_subdir="")
    if not changed:
        return "present"
    if not apply:
        return "would-install"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(new_settings, indent=2) + "\n", encoding="utf-8")
    return "installed"


# ---------------------------------------------------------------------------
# AGENTS.md merge orchestration (v2, #317 Phase 6 / flat-layout-and-agents-
# merge.md Phase 3). AGENTS.md is HYBRID and excluded from plain copying for
# exactly this reason: a course's constitution carries HERMES learning a blind
# overwrite would destroy.
#
# THE SPLIT — deterministic here, judgment in a skill, gated by a script:
#   THIS does steps 1-2 only: back up, then drop in the fresh constitution.
#   Deciding what course content is still true and worth keeping needs an LLM —
#   that is a session-level action (the merge skill), not something a function
#   here can do.
#   merge_cleanup.py is the mandatory gate AFTER the skill runs — it decides
#   whether the result may be kept, not this tool and not the skill itself (an
#   agent grading its own homework was the earlier design's flaw).
# ---------------------------------------------------------------------------

def plan_agents_md_merge(course_root: Path, clone: Path) -> str:
    """Decide what AGENTS.md needs, without writing anything. One of:
      no-clone-agents-md   the clone has no AGENTS.md — nothing to do
      fresh                no course AGENTS.md yet — write the clone's directly
      up-to-date           toolkit half already matches the clone — no merge needed
      merge-pending        AGENTS.merge.md already exists from a prior, unfinished
                            merge — do NOT overwrite it with a second backup
      merge-needed         course AGENTS.md exists and its toolkit half differs
    """
    source = clone / "AGENTS.md"
    if not source.is_file():
        return "no-clone-agents-md"
    if (course_root / "AGENTS.merge.md").is_file():
        return "merge-pending"
    target = course_root / "AGENTS.md"
    if not target.is_file():
        return "fresh"
    toolkit_half, _ = split_merged(target.read_text(encoding="utf-8"))
    if toolkit_half.rstrip() == source.read_text(encoding="utf-8").rstrip():
        return "up-to-date"
    return "merge-needed"


def apply_agents_md_step(course_root: Path, clone: Path, apply: bool) -> str:
    """Act on plan_agents_md_merge()'s verdict.

    "fresh" and "merge-needed" get a `would-` prefix in dry-run. Every other
    verdict needs no write either way, so it passes through unchanged."""
    status = plan_agents_md_merge(course_root, clone)
    if status in ("no-clone-agents-md", "up-to-date", "merge-pending"):
        return status
    if not apply:
        return f"would-{status}"
    source_text = (clone / "AGENTS.md").read_text(encoding="utf-8")
    target = course_root / "AGENTS.md"
    if status == "fresh":
        # No prior course AGENTS.md exists, so there is nothing to MERGE — but
        # "nothing to merge" is not "no course section at all". FOUND FOR REAL
        # (#317 follow-up): a fresh flat install got the bare toolkit constitution
        # with no course half whatsoever, silently losing the Toyota quality-
        # discipline block, the grading pointer, the vendored-tools reminder, and
        # the HERMES Course Context stub — content nested installs had always
        # gotten via cb_init.py's step_12. Restored via the ONE shared body
        # (merge_cleanup.default_course_content) both paths now draw from.
        course_half = default_course_content(flat=True)
        target.write_text(
            f"{source_text.rstrip()}\n\n{COURSE_MARKER}\n\n{course_half}\n{COURSE_END}\n",
            encoding="utf-8",
        )
        return "fresh"
    # merge-needed: back up the old file, THEN drop in the fresh constitution —
    # never the other order, or a crash between the two steps loses the course's
    # only copy of its own learning.
    target.rename(course_root / "AGENTS.merge.md")
    target.write_text(source_text, encoding="utf-8")
    return "merge-needed"


# ---------------------------------------------------------------------------
# Verification report (v2, #317 Phase 6 / flat-layout-and-agents-merge.md
# Phase 5). "The operation is not reported as complete if a required
# verification fails" — this is what backs that claim with evidence instead of
# an assumption that the copy loop above succeeded.
# ---------------------------------------------------------------------------

def verify_agents_md(course_root: Path, clone: Path) -> tuple[bool, str]:
    """Toolkit half of the course's AGENTS.md is byte-identical to the clone's —
    the same contract `merge_cleanup.py` enforces right after a merge, checked
    here on every update so drift is caught even outside a merge cycle."""
    target = course_root / "AGENTS.md"
    source = clone / "AGENTS.md"
    if not target.is_file():
        return True, "no course AGENTS.md yet — nothing to verify"
    if not source.is_file():
        return False, "clone has no AGENTS.md to verify against"
    toolkit_half, _ = split_merged(target.read_text(encoding="utf-8"))
    src_text = source.read_text(encoding="utf-8")
    intact = toolkit_half.rstrip() == src_text.rstrip()
    return intact, (
        "constitution is byte-identical to source" if intact
        else "CONSTITUTION ALTERED — course AGENTS.md's toolkit half does not "
             "match the clone's"
    )


def verify_course_learning(course_root: Path, clone: Path) -> tuple[bool, str]:
    """Reports the PRESENCE of a pending merge, never its correctness.

    That distinction matters: `apply_agents_md_step()` performs only the
    backup-and-replace half of a merge (deterministic) — the LLM-driven curation
    and the strict "did it actually preserve course content" gate are
    `merge_cleanup.py`'s job, run separately once the merge skill finishes. A
    backup that still exists right after `apply_agents_md_step()` ran is the
    NORMAL, EXPECTED outcome of that step, not a defect of this update — so this
    can never independently fail. Only `merge_cleanup.py` may refuse a merge."""
    backup_path = course_root / "AGENTS.merge.md"
    if not backup_path.is_file():
        return True, "no pending merge (AGENTS.merge.md absent)"
    return True, ("merge pending — AGENTS.merge.md exists. Run the merge skill, then "
                  "`uv run python lib/tools/merge_cleanup.py` to finish (mandatory gate; "
                  "it decides whether the merge may be kept, not this report)")


def verify_token_budget(course_root: Path) -> tuple[bool, str]:
    target = course_root / "AGENTS.md"
    if not target.is_file():
        return True, "no course AGENTS.md yet"
    n = len(target.read_text(encoding="utf-8").splitlines())
    if n >= HARD_FLAG_LINES:
        return False, (f"OVER AUTO-INCLUDE LIMIT — {n} lines (>= {HARD_FLAG_LINES}); "
                       f"file will not load at session start")
    if n >= SOFT_WARN_LINES:
        return True, f"{n} lines — over the {SOFT_WARN_LINES}-line soft warn"
    return True, f"{n} lines — within budget"


def verify_skills_present(course_root: Path, clone: Path) -> tuple[bool, str]:
    skills_dir = clone / "skills"
    if not skills_dir.is_dir():
        return True, "clone ships no canonical skills/ — nothing to verify"
    expected = sorted(p.name for p in skills_dir.iterdir() if p.is_dir())
    missing = [s for s in expected
              if not (course_root / ".claude" / "skills" / s / "SKILL.md").is_file()]
    if missing:
        return False, f"missing at .claude/skills/: {', '.join(missing)}"
    return True, f"all {len(expected)} skills present at .claude/skills/"


def verify_guardian_hook(course_root: Path) -> tuple[bool, str]:
    """Not just "is some hook present" — a hook whose referenced script path
    doesn't resolve here (e.g. installed for the nested layout, but this is a
    flat course) FAILS OPEN per hook_command()'s own design: installed, but
    silently inert. "Present" must mean it actually does something."""
    settings_path = course_root / ".claude" / "settings.json"
    try:
        existing = (json.loads(settings_path.read_text(encoding="utf-8"))
                   if settings_path.is_file() else {})
    except (OSError, ValueError):
        return False, f"{settings_path} exists but is not valid JSON"

    commands = [
        h.get("command", "")
        for entry in existing.get("hooks", {}).get("PreToolUse", [])
        for h in entry.get("hooks", [])
        if "grade_guardian" in (h.get("command") or "")
    ]
    if not commands:
        return False, ("grade_guardian hook is NOT wired — Canvas grade/comment "
                       "writes would not be blocked at the harness")

    import re
    for command in commands:
        match = re.search(r'\$\{?CLAUDE_PROJECT_DIR\}?/([^"]*grade_guardian\.py)', command)
        if match and (course_root / match.group(1)).is_file():
            return True, "grade_guardian hook wired and its script path resolves"
    return False, ("grade_guardian hook is wired but its script path does not "
                   "resolve here — installed, but inert (fails open, silently)")


def verify_manifest_clean(course_root: Path, to_delete: list[str]) -> tuple[bool, str]:
    """No file from the previous manifest still lingers after an apply — an
    orphan is a stale tool an agent could still find and run."""
    orphans = [rel for rel in to_delete if (course_root / rel).exists()]
    if orphans:
        return False, f"{len(orphans)} orphaned path(s) survived removal: {orphans[:5]}"
    return True, f"no orphaned paths ({len(to_delete)} upstream deletions all removed)"


def verify_no_pending_collisions(course_root: Path) -> tuple[bool, str]:
    """Same shape as the AGENTS.md merge-pending check: a *.pre-flatten-backup
    left by apply_sync()'s collision protection needs a human decision (keep
    the toolkit's file, restore the course's own, or merge by hand) — this
    reports it rather than deciding, exactly like merge_cleanup.py is the
    actual gate for AGENTS.md rather than this report."""
    found = sorted(
        str(p.relative_to(course_root)) for p in course_root.rglob("*.pre-flatten-backup")
        if CLONE_DIR not in p.relative_to(course_root).parts
    )
    if not found:
        return True, "no pending collision backups (*.pre-flatten-backup)"
    return True, (f"{len(found)} pending collision backup(s) need review: "
                  f"{found[:5]} — see apply_sync()'s collision-protection note")


def verification_report(course_root: Path, clone: Path,
                        to_delete: list[str]) -> list[tuple[bool, str]]:
    """[(ok, message)] for every check — pure given its inputs; callers do the
    printing. Mirrors merge_cleanup.verify()'s shape deliberately."""
    return [
        verify_agents_md(course_root, clone),
        verify_course_learning(course_root, clone),
        verify_token_budget(course_root),
        verify_skills_present(course_root, clone),
        verify_guardian_hook(course_root),
        verify_manifest_clean(course_root, to_delete),
        verify_no_pending_collisions(course_root),
    ]


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
    ap.add_argument(
        "--approve", action="append", default=[], metavar="PACKAGE_ID",
        help="approve capability growth for this package (repeatable). Relay the "
             "printed summary to the instructor first — this flag is how an agent "
             "records that consent, not a substitute for asking.",
    )
    ap.add_argument(
        "--approve-all", action="store_true",
        help="approve capability growth for every package this run touches.",
    )
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

    consent_ok, consent_messages, pending_approvals = check_capability_consent(
        clone, root, packages, set(args.approve), args.approve_all
    )
    if consent_messages:
        print("\ncapability consent:")
        for msg in consent_messages:
            for line in msg.splitlines():
                print(f"  {line}")
    if not consent_ok:
        print(
            "\n🔴 capability growth needs approval before this can proceed — see "
            "NEEDS APPROVAL above.\n   AGENT: relay each summary to the instructor in "
            "chat. On their explicit yes, re-run with `--approve <package-id>` (or "
            "`--approve-all`).\n   Nothing was written.",
            file=sys.stderr,
        )
        return 2

    counts = apply_sync(clone, root, to_copy, to_delete, args.apply, previously_owned=old)
    verb = "wrote" if args.apply else "would write"
    print(f"{verb}: {counts['copied']} copied, {counts['deleted']} removed"
          + (f", {counts['missing']} missing from clone" if counts["missing"] else ""))
    if counts["backed_up"]:
        backup_verb = "backed up" if args.apply else "would back up"
        print(f"\n🟡 {counts['backed_up']} course file(s) collided with a toolkit path — "
              f"{backup_verb} rather than overwritten:")
        for rel in counts["backed_up_paths"]:
            suffix = ".pre-flatten-backup" if args.apply else ""
            print(f"  {rel}{(' -> ' + rel + suffix) if suffix else ''}")
        print("  Review each: keep the toolkit's version, restore your own "
              "(remove the .pre-flatten-backup suffix), or merge by hand.")

    updated = splice_gitignore(existing, render_gitignore_block(to_copy))
    if updated != existing:
        if args.apply:
            gi.write_text(updated, encoding="utf-8")
        print(f"gitignore block: {'updated' if args.apply else 'would update'} "
              f"({len(to_copy)} exact paths — never a directory blanket, see #271)")
    else:
        print("gitignore block: present")

    _, pyproject_msg = report_pyproject_deps(root, clone, args.apply)
    print(f"pyproject.toml (existing host identity never overwritten): {pyproject_msg}")

    print("\nAGENTS.md:", end=" ")
    agents_status = apply_agents_md_step(root, clone, args.apply)
    print(agents_status)
    if agents_status in ("merge-needed", "would-merge-needed"):
        print("    ↳ AGENTS.merge.md carries the old course constitution. AGENT: "
              "read it against the fresh AGENTS.md, curate what course-specific "
              "content is still true (the merge skill), then run `uv run python "
              "lib/tools/merge_cleanup.py` — it decides whether the merge may be "
              "kept, not you.")
    elif agents_status == "merge-pending":
        print("    ↳ an earlier merge never finished. Resolve AGENTS.merge.md "
              "(same instructions as above) before this repo is considered current.")

    print("\nbootstrap:")
    env_status = ensure_env_stub(root, args.apply)
    print(f"  .env: {env_status}")
    hook_status = ensure_guardian_hook(root, args.apply)
    print(f"  grade_guardian hook (.claude/settings.json): {hook_status}")
    if hook_status == "installed":
        print("    ↳ Canvas grade/comment writes must now go through "
              "grader_push.py / grader_standing.py — enforced at the harness.")
    shim_link, shim_rel = plan_claude_shim(root)
    shim_status = install_claude_shim(shim_link, shim_rel, args.apply)
    print(f"  {CLAUDE_SHIM} shim -> {shim_rel}: {shim_status}")
    if shim_status in ("linked", "copied", "would-install"):
        print("    ↳ Claude Code does NOT read AGENTS.md — it reads CLAUDE.md. "
              "Without this shim the constitution you just wrote never loads.")
    elif shim_status == "missing-target":
        print("    ↳ AGENTS.md wasn't written above — the shim will point at "
              "nothing until that's resolved.")
    if not args.apply:
        print("  Canvas API smoke test: (dry-run — not calling the network)")
        print("\nDRY RUN — re-run with --apply to write.")
        return 0

    smoke_ok, smoke_msg = canvas_smoke_test(root)
    print(f"  Canvas API smoke test: {smoke_msg}")
    if not smoke_ok:
        print("    ↳ check CANVAS_API_TOKEN / CANVAS_BASE_URL in .env — this does "
              "not block the install, only the token check.")

    print("\nverification:")
    results = verification_report(root, clone, to_delete)
    for ok, msg in results:
        print(f"  {'✓' if ok else '✗'} {msg}")
    if not all(ok for ok, _ in results):
        print("\n🔴 update applied, but verification FAILED — see ✗ above. "
              "Not reporting this as complete.", file=sys.stderr)
        return 2

    # Record approvals only now — after every write succeeded and verification
    # passed. A refused or failed run must never persist an approval; the next
    # attempt should see the same pending consent it saw this time.
    for pkg_id, fingerprint, approved_by in pending_approvals:
        record_approval(root, pkg_id, fingerprint, approved_by)

    if to_copy or to_delete:
        print(f"\n{RELOAD_NOTICE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

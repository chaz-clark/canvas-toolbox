#!/usr/bin/env python3
"""merge_cleanup.py — the mandatory gate that closes an AGENTS.md merge.

WHY THIS IS A SCRIPT AND NOT A SKILL STEP
  The AGENTS.md merge needs an LLM: deciding which HERMES learning is still true
  of the course, what to compress, what to drop. That judgment cannot be scripted.
  But "did the merge actually preserve the constitution, and is it safe to delete
  the backup?" is a *deterministic* question, and leaving it to the same agent that
  just did the merge means the agent grades its own homework — it can decide cleanup
  happened, self-attest, and move on.

  So the split is: the skill merges, THIS decides whether the merge is acceptable.
  It is not optional and it is not the agent's call. `AGENTS.merge.md` is deleted
  only when every check passes; on any failure the backup stays on disk and the exit
  code is non-zero, so the broken state is visible and recoverable.

THE CONTRACT BEING VERIFIED
  A merged AGENTS.md is: the toolkit constitution VERBATIM, then a sentinel-marked
  course section. The toolkit half is copied byte-for-byte — never paraphrased,
  reordered, or summarized — because it carries the FERPA Zone-2 rules and the
  Canvas-write doctrine. Judgment applies to the course half only. That contract is
  what makes an LLM-driven merge acceptable on a safety-critical file, and it is
  exactly what the hash check below enforces.

CHECKS
  1. toolkit half is byte-identical to the source constitution
  2. course learning survived — if the backup carried course content, the merged
     file has a non-empty course section (catches a silent drop)
  3. token budget — under the AGENTS-QC-010 soft warn; hard-fails past the flag,
     because a file over the auto-include limit stops loading at session start,
     which silently undoes the entire point of the merge

USAGE
  uv run python lib/tools/merge_cleanup.py                  # run the gate, act
  uv run python lib/tools/merge_cleanup.py --check          # verify only, never delete

  Idempotent: with no AGENTS.merge.md present it verifies the current file and
  exits 0, so a re-run after a successful merge is a clean no-op.

EXIT CODES
  0  verified (backup removed, or nothing to do)
  2  verification failed — backup retained, merge must be redone
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

COURSE_MARKER = "<!-- canvas-toolbox:course-content -->"
COURSE_END = "<!-- /canvas-toolbox:course-content -->"

SOFT_WARN_LINES = 800
HARD_FLAG_LINES = 1200

BACKUP_NAME = "AGENTS.merge.md"
TARGET_NAME = "AGENTS.md"
DEFAULT_SOURCE = Path(".canvas-toolbox") / "AGENTS.md"


# ---------------------------------------------------------------------------
# Pure helpers — no filesystem, no argv
# ---------------------------------------------------------------------------

def split_merged(text: str) -> tuple[str, str | None]:
    """Split a merged AGENTS.md into (toolkit_half, course_half).

    course_half is None when the marker is absent — which is a legitimate state
    (a course with no HERMES learning yet), not an error.
    """
    idx = text.find(COURSE_MARKER)
    if idx == -1:
        return text, None
    toolkit = text[:idx]
    course = text[idx + len(COURSE_MARKER):]
    end = course.find(COURSE_END)
    if end != -1:
        course = course[:end]
    return toolkit, course


def historical_lines(clone: Path) -> set[str]:
    """Every line that has EVER appeared in the toolkit's own AGENTS.md.

    WHY THIS IS NEEDED. A stale course copy of the constitution is an OLD
    REVISION of this file — not course content. Comparing only against current
    HEAD classifies those old lines as "course learning about to be dropped",
    so the gate refuses, and it refuses FOREVER on exactly the repos that most
    need updating. Worse: forcing past it reinstates whatever the old revision
    said.

    Found on a real repo. Migrating a course repo whose constitution was a
    stale copy, the lines flagged as "course content" were the identifier and
    placeholder-name strings that the #307 FERPA scrub had replaced — i.e. the
    gate was refusing to drop the very lines that scrub existed to remove.

    118 revisions / ~2.9k unique lines, so this is a few hundred ms. Best
    effort: on any git failure return empty and fall back to the HEAD-only
    comparison, which errs toward refusing — never toward silently dropping."""
    try:
        shas = subprocess.run(
            ["git", "-C", str(clone), "log", "--format=%H", "--", "AGENTS.md"],
            capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return set()
    seen: set[str] = set()
    for sha in shas:
        try:
            body = subprocess.run(
                ["git", "-C", str(clone), "show", f"{sha}:AGENTS.md"],
                capture_output=True, text=True, check=True).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        seen.update(ln.strip() for ln in body.splitlines() if ln.strip())
    return seen


def course_content_lines(backup: str, source: str,
                         known: frozenset[str] | set[str] = frozenset()) -> list[str]:
    """Lines in the backup that the COURSE authored — i.e. not in the current
    constitution and not in any past revision of it (`known`).

    Answers one question: did the OLD file carry course-specific content that a
    merge must preserve? Over-counting is safe (it can only demand a section a
    curation pass would keep anyway); under-counting would let real HERMES
    learning be dropped silently, so the fallback when `known` is empty is the
    stricter HEAD-only comparison."""
    src = {ln.strip() for ln in source.splitlines() if ln.strip()}
    return [ln for ln in backup.splitlines()
            if ln.strip() and ln.strip() not in src and ln.strip() not in known]


def verify(merged: str, source: str, backup: str | None,
           known: frozenset[str] | set[str] = frozenset()) -> list[tuple[bool, str]]:
    """Return [(ok, message)] for every check. Pure — callers do the I/O."""
    results: list[tuple[bool, str]] = []

    toolkit_half, course_half = split_merged(merged)

    # 1. Constitution intact, byte for byte.
    intact = toolkit_half.rstrip() == source.rstrip()
    results.append((
        intact,
        "constitution is byte-identical to source" if intact
        else "CONSTITUTION ALTERED — toolkit half does not match the source file",
    ))

    # 2. Course learning survived.
    if backup is not None:
        had = course_content_lines(backup, source, known)
        if had:
            kept = bool(course_half and course_half.strip())
            results.append((
                kept,
                f"course learning preserved ({len(had)} candidate lines in backup)"
                if kept else
                f"COURSE LEARNING DROPPED — backup had {len(had)} course lines, "
                f"merged file has no course section",
            ))
        else:
            results.append((True, "backup carried no course content — nothing to preserve"))

    # 3. Token budget. Past the hard flag the file stops auto-loading, which
    #    silently defeats the merge, so that is a failure and not a warning.
    n = len(merged.splitlines())
    if n >= HARD_FLAG_LINES:
        results.append((False, f"OVER AUTO-INCLUDE LIMIT — {n} lines (>= {HARD_FLAG_LINES}); "
                               f"file will not load at session start"))
    elif n >= SOFT_WARN_LINES:
        results.append((True, f"{n} lines — over the {SOFT_WARN_LINES}-line soft warn, "
                              f"course half needs pruning soon"))
    else:
        results.append((True, f"{n} lines — within budget"))

    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(
        description="Mandatory verification gate closing an AGENTS.md merge.")
    ap.add_argument("--course-root", type=Path, default=Path.cwd(),
                    help="course repo root (default: cwd)")
    ap.add_argument("--source", type=Path, default=None,
                    help=f"source constitution (default: <root>/{DEFAULT_SOURCE})")
    ap.add_argument("--check", action="store_true",
                    help="verify only — never delete the backup")
    args = ap.parse_args()

    root: Path = args.course_root
    target = root / TARGET_NAME
    backup_path = root / BACKUP_NAME
    source_path = args.source or (root / DEFAULT_SOURCE)

    if not target.is_file():
        print(f"🔴 merge_cleanup: no {TARGET_NAME} at {root}", file=sys.stderr)
        return 2
    if not source_path.is_file():
        print(f"🔴 merge_cleanup: no source constitution at {source_path}. "
              f"Is the vendored clone present?", file=sys.stderr)
        return 2

    merged = target.read_text(encoding="utf-8")
    source = source_path.read_text(encoding="utf-8")
    backup = backup_path.read_text(encoding="utf-8") if backup_path.is_file() else None

    if backup is None:
        print(f"merge_cleanup: no {BACKUP_NAME} — verifying current {TARGET_NAME}.")

    known = historical_lines(source_path.parent)
    results = verify(merged, source, backup, known)
    for ok, msg in results:
        print(f"  {'✓' if ok else '✗'} {msg}")
    sys.stdout.flush()   # keep the checks above the stderr verdict below

    if not all(ok for ok, _ in results):
        print(f"\n🔴 merge_cleanup: verification FAILED. {BACKUP_NAME} retained at "
              f"{backup_path if backup else '(none)'} — redo the merge; nothing was lost.",
              file=sys.stderr)
        return 2

    if backup is None:
        print("\n✓ merge_cleanup: verified. Nothing to clean up.")
        return 0

    if args.check:
        print(f"\n✓ merge_cleanup: verified. --check set, {BACKUP_NAME} left in place.")
        return 0

    backup_path.unlink()
    print(f"\n✓ merge_cleanup: verified and {BACKUP_NAME} removed.")
    print("  Restart your AI session (new chat, reload the extension, or restart the "
          "IDE) — AGENTS.md is read once at session start.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

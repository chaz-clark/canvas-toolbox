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

try:
    # Same single source of truth cb_init.py uses (#207) — nested-mode course
    # content gets the identical grading pointer either tool writes it.
    from sync_grading_protocol import POINTER_BLOCK as GRADING_POINTER_BLOCK
except ImportError:
    GRADING_POINTER_BLOCK = (
        "<!-- canvas-toolbox:grading-protocol-pointer -->\n\n"
        "## ⚠️ Grading — HG-5: the instructor decides\n\n"
        "AI-assisted grading is decision support, not autonomy. Never push AI-drafted "
        "grades without human review. Full protocol: canvas-toolbox/AGENTS.md → "
        '"AI Grading Protocol — HG-5".\n\n'
        "<!-- /canvas-toolbox:grading-protocol-pointer -->"
    )

COURSE_MARKER = "<!-- canvas-toolbox:course-content -->"
COURSE_END = "<!-- /canvas-toolbox:course-content -->"

SOFT_WARN_LINES = 800
HARD_FLAG_LINES = 1200

BACKUP_NAME = "AGENTS.merge.md"
TARGET_NAME = "AGENTS.md"
DEFAULT_SOURCE = Path(".canvas-toolbox") / "AGENTS.md"

# ONE canonical string (flat-layout-and-agents-merge.md Phase 6) — not a per-tool
# if/else. cb_flatten.py prints this too, after any successful apply that changed
# files, not only after a merge; both import this constant rather than each
# carrying their own copy.
RELOAD_NOTICE = (
    "Restart your AI session (new chat, reload the extension, or restart the IDE) "
    "for the update to take effect — AGENTS.md and skills are read once at "
    "session start."
)


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


def default_course_content(*, flat: bool) -> str:
    """The starter course-half body for a FIRST-TIME AGENTS.md — no prior course
    content exists to merge, so `apply_agents_md_step`'s "fresh" case (cb_flatten.py)
    and `step_12_generate_agents_md`'s nested stub (cb_init.py) both need SOMETHING
    here, not an empty course section.

    ONE canonical body (RELOAD_NOTICE's own comment states this project's rule:
    "not a per-tool if/else") — found missing entirely for the flat "fresh" case: a
    brand-new flat install's AGENTS.md ended up as the bare toolkit constitution,
    silently losing the Toyota quality-discipline block, the grading pointer, the
    vendored-tools reminder, and the HERMES Course Context stub that nested installs
    had always gotten via `step_12`. Restored here as the one shared source, so flat
    and nested can never drift into two different "first course section" experiences
    again.

    `flat=True` drops the `canvas-toolbox/` path prefix nested installs need — in
    flat layout the toolkit's own files sit directly at the course root, not under a
    visible subdirectory."""
    if flat:
        pointer = (
            "## ⚠️ Using canvas-toolbox — constitution + skills\n\n"
            "This course uses **canvas-toolbox**, flattened into this repo from a "
            "hidden pristine clone (`.canvas-toolbox/`). Its always-on rules — FERPA "
            "discipline, the Canvas-write safety doctrine + the `grade_guardian` hook, "
            "and behavioral principles — live above, in this same file's constitution "
            "half. Mode-specific procedure lives in **operating-mode skills** under "
            "`.claude/skills/`: `grading`, `course-build`, `audit`, `accommodations`, "
            "`ferpa-deid`, `title-iv`, `voicing`, `improve`. Load the skill that "
            "matches your task.\n\n"
            "**Grading is HG-5 — the instructor decides.** AI grading is decision "
            "support, not autonomy: grade → **show the feedback in chat** → "
            "`grader_push.py --mark-reviewed --yes` → `--push --yes`. `--yes` is "
            "honored (no terminal — never send faculty to a shell), but the "
            "`grade_guardian` hook fires an in-chat **permission pop-up** at BOTH the "
            "review and the push: the instructor clicks to approve — an agent cannot "
            "skip it or self-attest. When a gate blocks you, get the human — never "
            "stack `--force`/`--regrade` to route around it, and never hand-write a "
            "Canvas write (the `grade_guardian` hook blocks that at create/edit/run)."
        )
        tools_reminder = (
            "## ⚠️ Use the vendored tools — don't reimplement them\n\n"
            "Before implementing **any** Canvas operation, search `lib/tools/` first — "
            "use the tool if it exists, propose one if it doesn't, and **never "
            "hand-write a Canvas API script**. The toolkit was generalized *from* "
            "course scripts, so a local copy silently misses every safety fix the "
            "vendored tool has gained (the duplicate-comment, empty-comment, and "
            "stuck-workflow-state bugs all came from custom scripts). Full rationale + "
            "the custom→vendored **migration map**: "
            "`lib/agents/knowledge/toolkit_reuse_knowledge.md`. The `grade_guardian` "
            "hook (installed by `cb-init`) enforces this at the harness."
        )
        run_line = "uv run python lib/tools/course_audit.py --help"
    else:
        pointer = GRADING_POINTER_BLOCK
        tools_reminder = (
            "## ⚠️ Use the vendored tools — don't reimplement them\n\n"
            "Before implementing **any** Canvas operation, search "
            "`canvas-toolbox/lib/tools/` first — use the tool if it exists, propose "
            "one if it doesn't, and **never hand-write a Canvas API script**. The "
            "toolkit was generalized *from* course scripts, so a local copy silently "
            "misses every safety fix the vendored tool has gained (the "
            "duplicate-comment, empty-comment, and stuck-workflow-state bugs all came "
            "from custom scripts). Full rationale + the custom→vendored **migration "
            "map**: `canvas-toolbox/lib/agents/knowledge/toolkit_reuse_knowledge.md`. "
            "The `grade_guardian` hook (installed by `cb-init`) enforces this at the "
            "harness."
        )
        run_line = "uv run python canvas-toolbox/lib/tools/course_audit.py --help"

    return f"""{pointer}

---

## Quality Discipline (Toyota Production System)

AI agents working on this course follow three core quality principles:

### 1. Genchi Gembutsu (現地現物) - Go and See

**Don't assume, verify with real data:**
- Test with REAL course data, not synthetic fixtures
- When uncertain about format, examine actual files
- Verify in Canvas sandbox, don't trust docs alone
- Read actual code before claiming understanding

**Behavioral trigger**: When you catch yourself saying "probably" or "should" → STOP and verify

### 2. Jidoka (自働化) - Built-in Quality / Stop on Defect

**Build quality in, stop when defect detected:**
- Write tests WITH code, not after
- Red tests block progress - fix immediately, don't defer
- Validation runs automatically (not manual step)
- Can't push to Canvas with errors (blocked by design)

**Behavioral trigger**: When you want to say "we'll fix this later" → STOP and fix now

### 3. Poka-yoke (ポカヨケ) - Mistake-Proofing

**Design so mistakes can't happen:**
- Automate validation (no manual steps)
- Use pre-commit hooks to catch errors
- Type hints catch errors at write-time
- Block operations that would create defects

**Behavioral trigger**: When manual verification required → Design it out

**Quality Loop**: Prevent (Poka-yoke) → Detect (Jidoka) → Verify (Genchi Gembutsu)

When you find a defect:
1. **Fix it** (Jidoka - stop and correct)
2. **Verify the fix** (Genchi Gembutsu - test with real data)
3. **Prevent recurrence** (Poka-yoke - add automated check)

---

{tools_reminder}

---

Run tools from the course root, e.g.:
```bash
{run_line}
```

---

## Course Context

[Add course-specific context here as you work]

**HERMES Learning:** This section grows as you chat with Claude about your course.
- Teaching approach
- Grading workflows
- Course-specific Canvas patterns
- Student cohort notes
"""


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
            capture_output=True, text=True, encoding="utf-8", check=True).stdout.split()
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
        return set()
    seen: set[str] = set()
    for sha in shas:
        try:
            body = subprocess.run(
                ["git", "-C", str(clone), "show", f"{sha}:AGENTS.md"],
                capture_output=True, text=True, encoding="utf-8", check=True).stdout
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
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
    print(f"  {RELOAD_NOTICE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

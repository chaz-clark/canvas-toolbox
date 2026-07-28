#!/usr/bin/env python3
"""Ensure a course repo's AGENTS.md carries the canonical HG-5 grading-protocol
pointer (issue #207).

WHY THIS EXISTS
  cb_init generates the pointer into NEW course AGENTS.md stubs, but it never
  overwrites an EXISTING AGENTS.md (`if agents_md_path.exists(): skipping`). So
  every course repo initialized before #207 has no pointer, and each has diverged
  independently — there's no way to push a protocol update out to them. The KC3
  grading incident (issue #207) was exactly a "policy in docs, not enforced,
  docs out of sync" failure. This tool closes the docs half: it injects (or
  reports) the pointer idempotently so the safety protocol is discoverable in
  every course repo, without clobbering the course-specific content around it.

WHAT IT IS (and isn't)
  A POINTER, not a copy. The canonical protocol lives once in
  canvas-toolbox/AGENTS.md; this drops a short sentinel-delimited block that
  links to it. That keeps N course repos from drifting on the wording — a
  protocol revision updates one file, and this tool re-points the rest.

USAGE
  Dry-run (default) against the current course root:
    uv run python canvas-toolbox/lib/tools/sync_grading_protocol.py
  Apply to several course repos at once:
    uv run python .../sync_grading_protocol.py ../ds460-master ../ds250-onln-master --apply

  Idempotent: re-running is a no-op once the sentinel marker is present.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

POINTER_MARKER = "<!-- canvas-toolbox:grading-protocol-pointer -->"
POINTER_END = "<!-- /canvas-toolbox:grading-protocol-pointer -->"

# The canonical pointer block. Single source of truth — cb_init imports this so a
# freshly-init'd repo and a retrofitted one carry the identical, marker-delimited
# block (the marker is how this tool detects "already present").
POINTER_BLOCK = f"""{POINTER_MARKER}

## ⚠️ Using canvas-toolbox — constitution + skills

This course uses **canvas-toolbox**. Its always-on rules — FERPA discipline, the
Canvas-write safety doctrine + the `grade_guardian` hook, and behavioral principles —
live in **`canvas-toolbox/AGENTS.md`** (the constitution). Read it. Mode-specific
procedure lives in **operating-mode skills** under `.claude/skills/`: `grading`,
`course-build`, `audit`, `accommodations`, `ferpa-deid`, `title-iv`. Load the skill
that matches your task.

**Grading is HG-5 — the instructor decides.** AI grading is decision support, not
autonomy: grade → review the feedback → `grader_push.py --mark-reviewed` (type
`reviewed`) → `--push` (type `push`). `--yes` does **not** bypass review on the
AI-drafted path — enforced in code (#207). When a gate blocks you, do the review —
never stack `--force`/`--regrade`/`--yes` to route around it, and never hand-write a
Canvas write (the `grade_guardian` hook blocks that at create/edit/run).

**Updating the toolkit — run ONE command, don't improvise git.** When the instructor
says any of these (all mean the same thing):
"update cb", "git pull cb", "pull cb", "update canvas-toolbox", "pull canvas-toolbox",
"update the toolkit", "refresh cb", "upgrade canvas-toolbox", "sync the toolkit",
"get the latest cb" — run exactly:
`uv run python canvas-toolbox/lib/tools/cb_update.py --pull --apply`. That pulls the
**vendored** toolkit in the right place and activates skills + heals this pointer. Do
**NOT** `cd` into a repo and `git pull` by hand — that pulls the wrong repo (the
course repo, or the toolkit dev clone) instead of *this* course's vendored copy.

{POINTER_END}"""


def inject_grading_pointer(text: str) -> tuple[str, bool]:
    """Return (new_text, changed).

    Idempotent AND self-healing: if the marker block is already present and CURRENT,
    returns unchanged; if present but STALE (older wording — e.g. a pre-constitution
    pointer to a heading that has since been renamed), it REFRESHES the block in
    place. If absent, inserts POINTER_BLOCK just after the file's first top-level
    `# ` heading (or prepends it if there's none). Course-specific content around the
    block is never touched.
    """
    block = POINTER_BLOCK.strip("\n")

    if POINTER_MARKER in text and POINTER_END in text:
        start = text.index(POINTER_MARKER)
        end = text.index(POINTER_END) + len(POINTER_END)
        if text[start:end] == block:
            return text, False              # already current — no-op
        return text[:start] + block + text[end:], True   # stale → refresh in place

    lines = text.splitlines(keepends=True)
    idx = next((i for i, ln in enumerate(lines) if ln.startswith("# ")), None)

    if idx is None:
        return f"{block}\n\n{text}", True

    head = lines[: idx + 1]
    tail = lines[idx + 1 :]
    if head and not head[-1].endswith("\n"):
        head[-1] += "\n"
    return "".join(head) + f"\n{block}\n\n" + "".join(tail), True


def process_agents_file(path: Path, apply: bool) -> str:
    """Inject the pointer into one AGENTS.md. Returns a one-word status:
    'missing' (no file), 'present' (already has the pointer), 'injected'
    (written), or 'would-inject' (dry-run)."""
    if not path.is_file():
        print(f"  ✗ {path} — no AGENTS.md here")
        return "missing"

    text = path.read_text(encoding="utf-8")
    new, changed = inject_grading_pointer(text)
    if not changed:
        print(f"  ✓ {path} — pointer already present")
        return "present"

    if apply:
        path.write_text(new, encoding="utf-8")
        print(f"  ＋ {path} — pointer INJECTED")
        return "injected"

    print(f"  ~ {path} — pointer MISSING (dry-run; pass --apply to write). Would insert:")
    for ln in POINTER_BLOCK.strip("\n").splitlines():
        print(f"      | {ln}")
    return "would-inject"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Ensure course AGENTS.md files carry the HG-5 grading-protocol "
                    "pointer (issue #207). Dry-run by default; --apply to write.")
    ap.add_argument("course_roots", nargs="*", default=["."],
                    help="Course-root directories (each should contain an AGENTS.md). "
                         "Default: the current directory.")
    ap.add_argument("--apply", action="store_true",
                    help="Write the injection. Without it, this is a dry-run that shows "
                         "what would change.")
    args = ap.parse_args()

    roots = args.course_roots or ["."]
    print(f"Grading-protocol pointer sync ({'APPLY' if args.apply else 'dry-run'}):")
    statuses = [process_agents_file(Path(r) / "AGENTS.md", args.apply) for r in roots]

    injected = statuses.count("injected")
    would = statuses.count("would-inject")
    present = statuses.count("present")
    missing = statuses.count("missing")
    print(f"\nSummary: {injected} injected, {would} would-inject, "
          f"{present} already present, {missing} missing.")
    if would and not args.apply:
        print("Re-run with --apply to write the missing pointer(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

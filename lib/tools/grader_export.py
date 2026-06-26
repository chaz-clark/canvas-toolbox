#!/usr/bin/env python3
"""
grader_export.py — bundle a course's grader artifacts for cross-faculty sharing.

Part of the canvas-toolbox cross-faculty sharing pattern (v0.67.0+). See:
  - lib/agents/knowledge/grader_voice_knowledge.md §5 (three-layer pitfalls)
  - lib/agents/knowledge/grader_knowledge.md (the operational pipeline this rides on)

WHY THIS EXISTS
  Faculty A teaches Course X. They invest hours in rubrics, task specs,
  per-challenge config, and (optionally) course-level voice pitfalls.
  Faculty B is going to teach the same Course X next semester. Today
  Faculty B starts from scratch. This tool exports Faculty A's
  COURSE-LEVEL substrate (NOT their per-instructor voice — that's
  protected by the voice-preservation contract) so Faculty B starts
  from where Faculty A finished.

WHAT'S IN THE EXPORT
  Per-challenge (one entry per challenge dir):
    - RUBRIC.md or similar rubric files
    - assignment_spec.md (issue #102 student-facing task definition)
    - config.json / config.yml (the per-assignment grader config)
    - voice_pitfalls.md (optional, NEW v0.67.0 — course-level common
      mistakes, NOT instructor voice)
    - Any custom scripts the course wrote

  Course-level (at the share root):
    - share-manifest.yml — canvas-toolbox version, course label,
      what's included/excluded
    - READ_ME_BEFORE_IMPORT.md — plain-text instructions for the
      receiving faculty

WHAT'S NEVER IN THE EXPORT (FERPA + voice-preservation)
  - submissions_raw/ / submissions_deid/        — student work
  - feedback/                                    — per-student feedback
  - .keymap.json / .fetch_log.json               — identity bridges
  - .review.csv / .review*.csv                   — reviewer-facing identity
  - .push_log.md                                 — push audit trail
  - _existing_grades.csv / _consensus.csv        — per-cohort grading data
  - _summary.csv / _all_comments.md              — per-cohort grading data
  - student_feedback_voice_*.md                  — voice-preservation
  - _corpus/                                      — TA-comment archives

USAGE
  # Export the whole grading/ tree
  uv run python lib/tools/grader_export.py \\
    --course-label "DS 250 — Data Science for Business" \\
    --out ds250-share-2026-06.zip

  # Export specific challenges only
  uv run python lib/tools/grader_export.py \\
    --course-label "DS 460 — Big Data" \\
    --challenges grading/kc1 grading/kc2 grading/mid_review \\
    --out ds460-share-2026-06.zip

  # Dry-run — show what WOULD ship without writing the ZIP
  uv run python lib/tools/grader_export.py \\
    --course-label "DS 250" --dry-run

DESIGNED BY
  Parking-lot Idea B + operator decisions 2026-06-26. See
  AGENTS.md Active Context for the four scoping decisions baked in.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

# yaml is a stdlib-adjacent dep in canvas-toolbox (pyyaml>=6.0.3 in pyproject)
try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


# Whitelist: which files PER CHALLENGE DIR are shareable
_PER_CHALLENGE_WHITELIST: tuple[str, ...] = (
    "RUBRIC.md",
    "assignment_spec.md",
    "voice_pitfalls.md",
    "config.json",
    "config.yml",
    "config.yaml",
    "README.md",
)

# Blacklist: filename patterns that must NEVER ship (defense in depth)
# Anything matching these patterns is excluded even if the whitelist would
# allow it — belt and suspenders for FERPA.
_BLACKLIST_PATTERNS: tuple[str, ...] = (
    "submissions_raw",
    "submissions_deid",
    "_raw",
    "_deid",
    "feedback",
    ".keymap.json",
    ".fetch_log.json",
    ".known_names.txt",
    ".review.csv",
    ".review",
    ".push_log.md",
    ".reviewed",
    ".calibrated",
    "_existing_grades.csv",
    "_consensus.csv",
    "_summary.csv",
    "_all_comments.md",
    "_gradebook_actuals.csv",
    "UNIQUE_GROUP_MEMOS.md",  # may name students by group; conservative exclude
    "student_feedback_voice_",  # any per-instructor voice file
    "_corpus",  # TA-comment archives
)


def is_blacklisted(rel_path: str) -> bool:
    """Issue: cross-faculty sharing — defense-in-depth FERPA check.

    Returns True if the given relative path contains any blacklisted
    pattern (case-insensitive substring match). Used as a hard refusal
    AFTER the whitelist check, so a misconfigured whitelist still can't
    leak FERPA-protected files.
    """
    p = rel_path.lower()
    return any(pat.lower() in p for pat in _BLACKLIST_PATTERNS)


def whitelist_files_in_challenge(challenge_dir: Path) -> list[Path]:
    """Issue: cross-faculty sharing — walk a challenge dir, return the
    files that match the whitelist AND don't match the blacklist.

    Top-level files only (no recursion into subdirectories — that's where
    the FERPA-protected per-student files live). Returns sorted list of
    absolute paths for deterministic output.
    """
    if not challenge_dir.is_dir():
        return []
    out: list[Path] = []
    for entry in sorted(challenge_dir.iterdir()):
        if not entry.is_file():
            continue
        if entry.name not in _PER_CHALLENGE_WHITELIST:
            continue
        rel = entry.relative_to(challenge_dir.parent).as_posix()
        if is_blacklisted(rel):
            continue
        out.append(entry)
    return out


def build_manifest(
    course_label: str,
    challenges: list[Path],
    files_by_challenge: dict[str, list[str]],
    toolbox_version: str,
    exported_at: str,
) -> dict:
    """Issue: cross-faculty sharing — produce the share-manifest.yml content.

    Captures: canvas-toolbox version, course label, when exported, what's
    included per challenge, and the EXPLICIT exclusion list so the receiver
    can verify (and any auditor knows what was deliberately left out).

    `exported_at` is passed in (not computed) so the function is pure +
    deterministic for tests.
    """
    return {
        "canvas_toolbox_version": toolbox_version,
        "exported_at": exported_at,
        "course_label": course_label,
        "what_is_included": [
            "rubrics (RUBRIC.md per challenge)",
            "task specs (assignment_spec.md per challenge, issue #102)",
            "per-challenge config (config.json / config.yml)",
            "course-level voice pitfalls (voice_pitfalls.md per challenge, optional)",
            "per-challenge READMEs (when present)",
        ],
        "what_is_excluded_for_ferpa_or_voice": [
            "submissions_raw/ + submissions_deid/ (student work — FERPA)",
            "feedback/ (per-student feedback — FERPA)",
            ".keymap.json + .fetch_log.json (identity bridges — FERPA)",
            ".review.csv* + .push_log.md (reviewer + push audit — FERPA)",
            "_existing_grades.csv + _consensus.csv + _summary.csv + _all_comments.md (per-cohort grading data — FERPA)",
            "UNIQUE_GROUP_MEMOS.md (per-cohort group rosters — FERPA-adjacent)",
            "student_feedback_voice_<instructor>.md (per-instructor voice — voice-preservation contract)",
            "_corpus/ (TA-comment archives — FERPA + voice-bias)",
        ],
        "challenges": [
            {
                "name": ch.name,
                "files": files_by_challenge.get(ch.name, []),
            }
            for ch in sorted(challenges, key=lambda p: p.name)
        ],
    }


def render_readme(manifest: dict) -> str:
    """Issue: cross-faculty sharing — produce the
    READ_ME_BEFORE_IMPORT.md content at the ZIP root.

    This is the receiver's first read after unzipping. Plain English,
    no jargon, names the contract + next steps.
    """
    course = manifest.get("course_label", "(unknown course)")
    version = manifest.get("canvas_toolbox_version", "unknown")
    exported_at = manifest.get("exported_at", "unknown")
    challenge_count = len(manifest.get("challenges", []))
    challenge_names = [c["name"] for c in manifest.get("challenges", [])]
    return f"""# Read me before importing

You've received a canvas-toolbox grader export package.

**Course:** {course}
**Exported:** {exported_at}
**canvas-toolbox version (at export time):** {version}
**Challenges included:** {challenge_count} ({", ".join(challenge_names) if challenge_names else "none"})

## What's in this ZIP

Per-challenge artifacts (rubric, task spec, config, optional voice pitfalls).
See `share-manifest.yml` at the ZIP root for the full inclusion + exclusion list.

## What's NOT in this ZIP (intentionally)

- **No student work, feedback, or grades** — FERPA-protected; never shared.
- **No per-instructor voice file** — the sending faculty has their own voice;
  yours is yours. The export does NOT include `student_feedback_voice_*.md`
  by design. You'll build your own voice file from scratch (see step 4 below).

## What to do after importing

1. **Verify the import landed where you expected.** The `grader_import.py`
   tool extracts into your repo's `grading/` directory by default. Check
   that `grading/<challenge>/` has the rubric, task spec, and config you
   expect.

2. **Update canvas-toolbox if needed.** The export was built on canvas-toolbox
   {version}. If your local canvas-toolbox is older, `grader_import.py` will
   refuse the import and tell you the exact command to update first.

3. **Review the rubrics + task specs.** They were built by another faculty
   member for the same course — they're a STARTING POINT, not a contract.
   Read them. Edit as needed to match your own pedagogy. Especially: if
   any rubric tier descriptor reads like it's anchored to the sending
   faculty's specific examples, generalize it.

4. **Build YOUR voice file.** Run the voice articulation interview from
   `lib/agents/knowledge/voice_coaching_knowledge.md §5` (~30 minutes).
   This produces a starter `student_feedback_voice_<your-name>.md` that
   the canvas-toolbox edit roundtrip can refine across your first 1-2
   cohorts. Do NOT use the sending faculty's voice file even if you can
   find one — your voice is the asset.

5. **Read the voice pitfalls file (if present).** The per-challenge
   `voice_pitfalls.md` captures patterns the sending faculty observed
   that are about the COURSE CONTENT (not their voice). E.g., "students
   often misuse X tool; redirect to Y." These are usually generalizable.

6. **Run a calibration cohort.** Pick 5-10 students, grade them with the
   imported rubric + your voice file, review the agent's output, edit
   the comments to match your voice, sync the edits back. This is the
   standard canvas-toolbox roundtrip from `grader_voice_knowledge.md §4`.

## Questions

The sending faculty's contact info isn't in this ZIP (privacy). Reach out
through whatever channel you received this from. For canvas-toolbox issues,
see https://github.com/chaz-clark/canvas-toolbox/issues.
"""


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Bundle a course's grader artifacts for cross-faculty sharing "
                    "(v0.67.0+). Excludes all FERPA-protected data + per-instructor "
                    "voice files by design.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--course-label", required=True,
                    help="Human-readable course label (e.g. 'DS 250 — Data Science for Business'). "
                         "Stored in the manifest + named in the receiver's READ_ME.")
    ap.add_argument("--challenges", nargs="+", default=None,
                    help="Specific challenge dirs to include (e.g. grading/kc1 grading/kc2). "
                         "If omitted, all subdirectories of grading/ are included.")
    ap.add_argument("--grading-root", default="grading",
                    help="Root directory of challenge dirs. Default: grading/")
    ap.add_argument("--out", default=None,
                    help="Output ZIP path. Default: <course-label-slug>-share-<YYYY-MM-DD>.zip "
                         "in the current directory.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Don't write the ZIP — print the manifest + included file list to stdout.")
    ap.add_argument("--exported-at", default=None,
                    help="Override the exported_at timestamp (test/reproducibility). "
                         "Default: current UTC time in ISO 8601 with Z suffix.")
    args = ap.parse_args()

    if yaml is None:
        print("ERROR: pyyaml is required for grader_export. Install via:", file=sys.stderr)
        print("  uv pip install pyyaml", file=sys.stderr)
        return 1

    grading_root = Path(args.grading_root)
    if not grading_root.is_dir():
        print(f"ERROR: grading root {grading_root!r} doesn't exist.", file=sys.stderr)
        return 1

    # Resolve challenge list
    if args.challenges:
        challenges = [Path(c) for c in args.challenges]
        for ch in challenges:
            if not ch.is_dir():
                print(f"ERROR: challenge dir {ch!r} doesn't exist.", file=sys.stderr)
                return 1
    else:
        challenges = sorted(d for d in grading_root.iterdir() if d.is_dir())
        if not challenges:
            print(f"ERROR: no challenge dirs found under {grading_root!r}.", file=sys.stderr)
            return 1

    # Walk + whitelist each challenge
    files_by_challenge: dict[str, list[str]] = {}
    total_files = 0
    for ch in challenges:
        files = whitelist_files_in_challenge(ch)
        files_by_challenge[ch.name] = [f.name for f in files]
        total_files += len(files)

    if total_files == 0:
        print("ERROR: no shareable files found in any challenge dir.", file=sys.stderr)
        print("  Expected at least one of: " + ", ".join(_PER_CHALLENGE_WHITELIST),
              file=sys.stderr)
        return 1

    # Build manifest + README
    if args.exported_at is None:
        # Defer importing datetime so dry-run + tests stay deterministic
        # when --exported-at is provided.
        from datetime import datetime, timezone
        exported_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        exported_at = args.exported_at

    manifest = build_manifest(
        course_label=args.course_label,
        challenges=challenges,
        files_by_challenge=files_by_challenge,
        toolbox_version=__version__,
        exported_at=exported_at,
    )
    readme = render_readme(manifest)
    manifest_yaml = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)

    # Summary
    print(f"Course: {args.course_label}")
    print(f"canvas-toolbox version: {__version__}")
    print(f"Challenges: {len(challenges)} ({', '.join(c.name for c in challenges)})")
    print(f"Files: {total_files}")
    for ch in challenges:
        ch_files = files_by_challenge.get(ch.name, [])
        print(f"  {ch.name}/  ({len(ch_files)} files)")
        for f in ch_files:
            print(f"    {f}")

    if args.dry_run:
        print("\n--- share-manifest.yml ---")
        print(manifest_yaml)
        print("--- Dry run: no ZIP written. ---")
        return 0

    # Resolve output path
    if args.out:
        out_path = Path(args.out)
    else:
        # Slugify course label for filename
        slug = "".join(c if c.isalnum() else "-" for c in args.course_label.lower())
        slug = "-".join(s for s in slug.split("-") if s)[:60]
        date_part = exported_at[:10]  # YYYY-MM-DD
        out_path = Path(f"{slug}-share-{date_part}.zip")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Write ZIP
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Manifest + README at root
        zf.writestr("share-manifest.yml", manifest_yaml)
        zf.writestr("READ_ME_BEFORE_IMPORT.md", readme)
        # Per-challenge files
        for ch in challenges:
            for src in whitelist_files_in_challenge(ch):
                arcname = f"{ch.name}/{src.name}"
                # Final defense-in-depth: re-check blacklist on the
                # arcname just before writing. If anything slips through
                # the whitelist due to a bug, this catches it.
                if is_blacklisted(arcname):
                    print(f"  ⚠️  refused to write {arcname!r} (FERPA blacklist)",
                          file=sys.stderr)
                    continue
                zf.write(src, arcname=arcname)

    size_kb = out_path.stat().st_size / 1024
    print(f"\n✅ Wrote {out_path} ({size_kb:.1f} KB)")
    print(f"   Share with the receiving faculty along with the import command:")
    print(f"     uv run python lib/tools/grader_import.py --zip {out_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

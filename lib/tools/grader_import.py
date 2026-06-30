#!/usr/bin/env python3
"""
grader_import.py — receive a grader_export.py share ZIP and stage it locally.

Companion to `grader_export.py` (v0.67.0+). See:
  - lib/agents/knowledge/grader_voice_knowledge.md §5 (three-layer pitfalls)
  - lib/tools/grader_export.py (the sending half of this pair)

WHAT IT DOES
  1. Reads the share-manifest.yml from the ZIP root
  2. Validates manifest shape + canvas-toolbox version compatibility
     (HARD REFUSE if local version < export version — prompts upgrade)
  3. Shows the receiver exactly what's about to land + what's
     intentionally excluded
  4. Asks for explicit confirmation (operator types 'import' — no
     --yes shortcut on first-import for safety)
  5. Extracts into `<target>/grading/<challenge>/` for each challenge
     in the manifest
  6. Prints the next-steps reminder (build YOUR voice file; run a
     calibration cohort; etc.) per voice-preservation contract

USAGE
  # Default: import into the current working directory
  uv run python lib/tools/grader_import.py --zip ds250-share-2026-06.zip

  # Specify target directory (e.g. a fresh course repo)
  uv run python lib/tools/grader_import.py \\
    --zip ds250-share-2026-06.zip \\
    --into ~/Documents/GitHub/my-ds250-fork

  # Dry-run: show what WOULD extract without writing files
  uv run python lib/tools/grader_import.py --zip ds250-share-2026-06.zip --dry-run

VERSION COMPATIBILITY
  Hard refuse if local canvas-toolbox is OLDER than the export. The
  receiver gets a clear error with the exact commands to upgrade.
  Same-or-newer is fine.

DESIGNED BY
  Parking-lot Idea B + operator decisions 2026-06-26.
"""
from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import sys
import zipfile
from pathlib import Path

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


def parse_semver(version_str: str | None) -> tuple[int, int, int] | None:
    """Issue: cross-faculty sharing — parse a semver string into a (major,
    minor, patch) tuple for comparison. Tolerant of '+suffix' / '-pre'
    annotations (e.g., '0.66.0+unknown', '1.0.0-rc1'). Returns None on
    anything unparseable so the caller can fall back to a strict-string
    comparison or refuse with a clear error.
    """
    if not version_str or not isinstance(version_str, str):
        return None
    # Strip pre-release / build annotations
    core = version_str.split("+", 1)[0].split("-", 1)[0].strip()
    parts = core.split(".")
    if len(parts) < 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except (TypeError, ValueError):
        return None


def is_version_compatible(local_version: str, export_version: str) -> tuple[bool, str]:
    """Issue: cross-faculty sharing — return (ok, reason).

    Hard rule: local >= export. If local is older, refuse the import
    and tell the receiver to upgrade. If either version is unparseable,
    fall back to a loud warning + allow proceed (we don't want to
    refuse just because version-string parsing is fussy).

    Returns:
      (True,  'ok') — local is same or newer than export
      (False, reason) — local is older; refuse + show the reason text
    """
    local = parse_semver(local_version)
    export = parse_semver(export_version)
    if local is None or export is None:
        return True, (
            f"could not parse version(s) (local={local_version!r}, "
            f"export={export_version!r}); proceeding without compatibility check"
        )
    if local < export:
        return False, (
            f"local canvas-toolbox {local_version} is older than the export's "
            f"required {export_version}. Upgrade first, then re-run the import."
        )
    return True, "ok"


def validate_manifest(manifest: object) -> tuple[bool, list[str]]:
    """Issue: cross-faculty sharing — basic shape check on the loaded
    share-manifest.yml content.

    Returns (ok, errors). Required fields:
      - canvas_toolbox_version (str)
      - course_label           (str)
      - challenges             (list of dicts with name + files)

    Doesn't check FERPA exclusion list (that's documentation, not
    enforcement). The actual file-extraction step re-applies the
    blacklist as a defense-in-depth check.
    """
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return False, ["manifest is not a dict (corrupt ZIP?)"]
    required = ("canvas_toolbox_version", "course_label", "challenges")
    for key in required:
        if key not in manifest:
            errors.append(f"missing required field: {key!r}")
    if "challenges" in manifest:
        challenges = manifest.get("challenges")
        if not isinstance(challenges, list):
            errors.append("'challenges' is not a list")
        else:
            for i, ch in enumerate(challenges):
                if not isinstance(ch, dict):
                    errors.append(f"challenges[{i}] is not a dict")
                    continue
                if "name" not in ch or "files" not in ch:
                    errors.append(f"challenges[{i}] missing 'name' or 'files'")
    return (len(errors) == 0), errors


# Same blacklist as grader_export — defense-in-depth on the receiving end too
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
    "UNIQUE_GROUP_MEMOS.md",
    "student_feedback_voice_",
    "_corpus",
)


def is_blacklisted(rel_path: str) -> bool:
    """Same defense-in-depth check as grader_export.is_blacklisted — but
    enforced on the RECEIVING side too. If a sending faculty's export
    somehow contained a blacklisted file (manual zip, old version with
    bugs, malicious archive), this catches it on import."""
    p = rel_path.lower()
    return any(pat.lower() in p for pat in _BLACKLIST_PATTERNS)


def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Import a grader_export.py share ZIP into the current "
                    "canvas-toolbox repo (v0.67.0+). Hard-refuses if local "
                    "canvas-toolbox version < export version; defense-in-depth "
                    "FERPA blacklist enforced on file extraction.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--zip", required=True,
                    help="Path to the share ZIP produced by grader_export.py.")
    ap.add_argument("--into", default=".",
                    help="Target directory. Default: current working directory. "
                         "The ZIP's `<challenge>/` dirs land at `<into>/grading/<challenge>/`.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what WOULD extract without writing any files.")
    ap.add_argument("--yes", action="store_true",
                    help="Skip the 'Type import to confirm' interactive prompt. NOT "
                         "recommended for first-import — the prompt is there so the "
                         "receiver actually reads the manifest + READ_ME first.")
    args = ap.parse_args()

    if yaml is None:
        print("ERROR: pyyaml is required for grader_import. Install via:", file=sys.stderr)
        print("  uv pip install pyyaml", file=sys.stderr)
        return 1

    zip_path = Path(args.zip)
    if not zip_path.is_file():
        print(f"ERROR: ZIP not found at {zip_path!r}.", file=sys.stderr)
        return 1

    into = Path(args.into).resolve()
    if not into.is_dir():
        print(f"ERROR: target directory {into!r} doesn't exist.", file=sys.stderr)
        return 1

    # Read + validate manifest
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if "share-manifest.yml" not in zf.namelist():
                print(f"ERROR: {zip_path.name} doesn't contain share-manifest.yml. "
                      f"Was it produced by grader_export.py?", file=sys.stderr)
                return 1
            manifest_yaml = zf.read("share-manifest.yml").decode("utf-8")
            manifest = yaml.safe_load(manifest_yaml)
    except zipfile.BadZipFile:
        print(f"ERROR: {zip_path!r} isn't a valid ZIP file.", file=sys.stderr)
        return 1
    except (yaml.YAMLError, OSError) as e:
        print(f"ERROR: failed to read manifest from {zip_path.name}: {e}",
              file=sys.stderr)
        return 1

    ok, errors = validate_manifest(manifest)
    if not ok:
        print(f"ERROR: invalid manifest in {zip_path.name}:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    course_label = manifest.get("course_label", "(unlabeled)")
    export_version = manifest.get("canvas_toolbox_version", "unknown")
    exported_at = manifest.get("exported_at", "unknown")
    challenges = manifest.get("challenges", [])

    # Version compat — HARD REFUSE if local is older
    compat_ok, compat_reason = is_version_compatible(__version__, export_version)
    if not compat_ok:
        print()
        print("=" * 78, file=sys.stderr)
        print("⛔ canvas-toolbox version too old to safely import this package.",
              file=sys.stderr)
        print("=" * 78, file=sys.stderr)
        print(f"  {compat_reason}", file=sys.stderr)
        print(file=sys.stderr)
        print("  To upgrade (if installed via git):", file=sys.stderr)
        print("    cd $(python -c 'import canvas_toolbox; "
              "print(canvas_toolbox.__file__)' 2>/dev/null | xargs dirname) && git pull",
              file=sys.stderr)
        print("  OR re-clone canvas-toolbox to a fresh dir at the right version:",
              file=sys.stderr)
        print("    git clone https://github.com/chaz-clark/canvas-toolbox.git", file=sys.stderr)
        print(file=sys.stderr)
        print("  Then re-run this import.", file=sys.stderr)
        print("=" * 78, file=sys.stderr)
        return 1
    if compat_reason != "ok":
        # Unparseable version → warn but proceed
        print(f"⚠️  {compat_reason}", file=sys.stderr)

    # Summary
    print()
    print("=" * 78)
    print(f"  Course: {course_label}")
    print(f"  Exported: {exported_at}")
    print(f"  canvas-toolbox version (export): {export_version}")
    print(f"  canvas-toolbox version (local):  {__version__}")
    print(f"  Target directory: {into}")
    print(f"  Challenges: {len(challenges)}")
    print("=" * 78)
    print()

    # Show what WOULD land
    print("Files that will land:")
    files_to_extract: list[tuple[str, str]] = []  # (arcname, target_rel_path)
    for ch in challenges:
        name = ch.get("name", "")
        files = ch.get("files", []) or []
        if not name or not isinstance(files, list):
            continue
        print(f"  grading/{name}/")
        for fname in files:
            arcname = f"{name}/{fname}"
            if is_blacklisted(arcname):
                # Should never happen if export was clean, but defense-in-depth
                print(f"    ⛔ {fname}  (REFUSED — FERPA blacklist match)")
                continue
            target = f"grading/{name}/{fname}"
            files_to_extract.append((arcname, target))
            print(f"    {fname}")
    print()
    print("FERPA-protected files that will NOT extract (per the manifest):")
    excluded = manifest.get("what_is_excluded_for_ferpa_or_voice", [])
    if isinstance(excluded, list):
        for item in excluded[:4]:
            print(f"  - {item}")
        if len(excluded) > 4:
            print(f"  - …and {len(excluded) - 4} more (see share-manifest.yml)")
    print()

    if args.dry_run:
        print("--- Dry run: no files written. ---")
        return 0

    # Confirmation prompt
    if not args.yes:
        print("Before you proceed:")
        print("  - Read READ_ME_BEFORE_IMPORT.md in the ZIP (preview below).")
        print("  - The sending faculty's voice file is NOT in this package by design.")
        print("    You will build your own voice file separately (see step 4 in the README).")
        print()
        # Preview the README
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                if "READ_ME_BEFORE_IMPORT.md" in zf.namelist():
                    readme = zf.read("READ_ME_BEFORE_IMPORT.md").decode("utf-8")
                    # Print first 30 lines as a preview
                    preview = "\n".join(readme.splitlines()[:30])
                    print("--- READ_ME_BEFORE_IMPORT.md (first 30 lines) ---")
                    print(preview)
                    print("--- end preview; full text in the ZIP ---")
                    print()
        except (zipfile.BadZipFile, OSError):
            pass
        if input("Type 'import' to confirm extraction: ").strip().lower() != "import":
            print("Aborted.")
            return 1

    # Extract — defense-in-depth blacklist check at write time
    grading_root = into / "grading"
    grading_root.mkdir(parents=True, exist_ok=True)
    extracted = 0
    refused = 0
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for arcname, target_rel in files_to_extract:
                if is_blacklisted(arcname):
                    refused += 1
                    continue
                target_path = into / target_rel
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(arcname) as src, target_path.open("wb") as dst:
                    dst.write(src.read())
                extracted += 1
                print(f"  ✓ {target_rel}")
    except (zipfile.BadZipFile, OSError) as e:
        print(f"ERROR during extraction: {e}", file=sys.stderr)
        return 2

    print()
    print(f"✅ Extracted {extracted} file(s) into {grading_root}.")
    if refused:
        print(f"   {refused} file(s) refused (FERPA blacklist — defense-in-depth).")
    print()
    print("Next steps (from READ_ME_BEFORE_IMPORT.md):")
    print("  1. Review the imported rubrics + task specs — edit to match your pedagogy.")
    print("  2. Read voice_pitfalls.md (per challenge, if present) — course-content insights.")
    print("  3. Build YOUR voice file by running the articulation interview in")
    print("     lib/agents/knowledge/voice_coaching_knowledge.md §5 (~30 min).")
    print("  4. Run a calibration cohort (5-10 students) per the standard roundtrip in")
    print("     grader_voice_knowledge.md §4.")
    print()
    print("Your voice is the asset. The imported substrate is a starting point.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

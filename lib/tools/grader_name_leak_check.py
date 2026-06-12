#!/usr/bin/env python3
"""
FERPA leak self-check on de-identified outputs.

Part of the canvas-toolbox generic grader skill (v1.0). See:
  - grading_readme.md (faculty-facing pipeline + canonical layout)
  - lib/agents/canvas_grader.md (agent-facing pipeline)
  - lib/agents/knowledge/grader_knowledge.md (FERPA architecture, §1)

WHAT IT DOES
  Reads two sources of name tokens:

  1. .known_names.txt — the roster (populated by grader_fetch.py's roster
     pre-fetch + by deid runs accumulating submitter names). Each entry is
     DECOMPOSED into full name + each individual part ≥3 chars (same as the
     deid scrub since #47), so prose mentions of first-name-only or
     last-name-only also get caught.

  2. The original Canvas-download filename (LEGACY path) — when the filename
     follows the old Canvas pattern `<lastnamefirstname>_<subid>_<attid>_<title>.<ext>`
     (4+ underscore-separated parts), the first field is a real name. Tokens
     ≥4 chars from that field are added to the search set.

     For new-style `grader_fetch.py` filenames (`<prefix>_<userid>.<ext>` —
     exactly 2 underscore-separated parts, second part numeric; or 3 parts
     for multi-attachment `_a`/`_b` suffix), the filename carries NO name —
     the roster from .known_names.txt is the only authority. The prefix
     token extraction is SKIPPED for those files (issue #49 fix — pre-fix,
     a prefix like `p1t1-cohesive` would extract "cohesive" as a token and
     match every submission's body, generating uniform false positives).

  Scrubs are checked with WORD-BOUNDARY MATCHING (same regex as #47's
  name_aware_subn) — so "Sam" doesn't match "Samsung", "Sam" doesn't match
  "samurai", etc. Pre-#49 the check used bare `text.count()` substring
  matching, which would re-introduce false positives after #47.

  Prints ONLY keys + counts to stdout — never a name — so it's safe to run
  in a shared terminal / with an AI watching. A "possible hit" means the
  agent should STOP and the operator should review that file locally
  (the operator knows the keymap; the AI does not).

  This is the gate before any cloud step. If any flag fires, STOP (P-003).
  Exit code 2 on any flagged file; 1 on missing-only; 0 on clean.

USAGE
  # Conventional layout
  uv run python lib/tools/grader_name_leak_check.py --challenge-dir grading/<asg>

  # Explicit (for non-conventional layouts)
  uv run python lib/tools/grader_name_leak_check.py \\
    --map <keymap.json> --deid-dir <submissions_deid/> --names <.known_names.txt>

GENERALIZED FROM: ds460-master/grading/check_name_leak.py
(commits 754c966..91a5113 — round-1 KC1 beta).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _challenge_dir_guard import resolve_challenge_dir  # issue #44 FERPA guard

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

# Reuse the helpers from the scrub-source-of-truth — keeps name decomposition
# + word-boundary matching consistent across deid AND leak check (issue #49).
from grader_deidentify_databricks import (  # noqa: E402
    expand_name_terms,
    name_aware_count,
)

# Common boilerplate tokens that aren't names. Adding course-specific extras
# via --stop is OK (legacy filename-token path only — the roster path is
# already an explicit allowlist).
DEFAULT_STOP = {
    "html", "late", "the", "and", "submission", "ipynb", "copy", "final", "key",
    "challenge", "groupby", "partitionby", "pyspark", "databricks", "personal",
    "docx", "review", "midreview", "performance",
}


def is_grader_fetch_naming(filename: str) -> bool:
    """True iff the filename matches grader_fetch.py's `<prefix>_<userid>.<ext>`
    shape — no student name in the filename; the roster is the authority.

    Patterns we recognize as grader_fetch shape:
      - <prefix>_<digits>.<ext>      (2 underscore parts; e.g. p1t1_280379.html)
      - <prefix>_<digits>_<a-z>.<ext> (3 parts, single-letter 3rd for multi-attachment)

    Old Canvas downloads have the shape `<name>_<subid>_<attid>_<title>.<ext>`
    (4+ parts), so they're distinguishable and keep the legacy name-extraction
    path.
    """
    stem = Path(filename).stem
    parts = stem.split("_")
    if len(parts) == 2:
        return parts[1].isdigit()
    if len(parts) == 3:
        # multi-attachment suffix: <prefix>_<userid>_a (or _b, _c, …)
        return parts[1].isdigit() and len(parts[2]) == 1 and parts[2].isalpha()
    return False  # 4+ parts → old Canvas naming with a real name field


def filename_tokens(filename: str, stop: set[str]) -> list[str]:
    """Extract name-candidate tokens from the original filename's name field.
    Returns [] for grader_fetch-naming-convention files — the roster is the
    authority there. Only fires on legacy Canvas downloads (4+ parts).

    Old Canvas filename shape: `lastnamefirstname_subid_attid_title.html`.
    """
    if is_grader_fetch_naming(filename):
        return []
    name_field = Path(filename).stem.split("_", 1)[0]
    return [t for t in re.split(r"[^A-Za-z]+", name_field)
            if len(t) >= 4 and t.lower() not in stop]


def load_known_names(path: Path) -> list[str]:
    """Read .known_names.txt — one name per line, comments (#) skipped."""
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def build_search_terms(fname: str, known_names: list[str], stop: set[str]) -> list[str]:
    """Combine roster terms (decomposed via expand_name_terms — first/last/full,
    parts ≥3 chars) with legacy filename tokens (only for old Canvas naming).
    Returns a deduplicated, length-sorted list (longest-first, so longer
    overlapping matches are found before shorter ones during counting)."""
    terms: set[str] = set()
    # Primary: roster, decomposed into parts (issue #49)
    terms.update(expand_name_terms(known_names))
    # Secondary: legacy Canvas filename tokens (issue #49 — empty for new naming)
    terms.update(filename_tokens(fname, stop))
    # Drop stopwords (mostly redundant — expand_name_terms already filters by
    # length, and filename_tokens filters by stop; this catches edge cases
    # like a single-letter operator-supplied stop)
    terms = {t for t in terms if t and t.lower() not in stop}
    return sorted(terms, key=len, reverse=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="FERPA leak self-check on de-id'd outputs. Reads "
                    ".known_names.txt (primary roster, decomposed) + filename "
                    "tokens (legacy Canvas naming only). Word-boundary matching. "
                    "Counts only, no names ever printed.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", dest="challenge_dir", default=None,
                    help="Convention base path (e.g. grading/kc1). Sets defaults for "
                         "--map / --deid-dir / --names.")
    ap.add_argument("--map", dest="mapfile", default=None,
                    help="Path to .keymap.json (default: <challenge-dir>/.keymap.json)")
    ap.add_argument("--deid-dir", dest="deid_dir", default=None,
                    help="Directory of keyed .md files (default: <challenge-dir>/submissions_deid)")
    ap.add_argument("--names", dest="namesfile", default=None,
                    help="Path to .known_names.txt — the roster (default: "
                         "<challenge-dir>/.known_names.txt). If absent, the leak "
                         "check falls back to filename-only tokens (legacy "
                         "Canvas-download path).")
    ap.add_argument("--stop", action="append", default=[],
                    help="Additional stop tokens for the legacy filename-token "
                         "path (course/format-specific). Has no effect on the "
                         "roster path. May be repeated.")
    args = ap.parse_args()

    if args.challenge_dir:
        cd = resolve_challenge_dir(args.challenge_dir, verb="leak-checking")
        args.mapfile = args.mapfile or str(cd / ".keymap.json")
        args.deid_dir = args.deid_dir or str(cd / "submissions_deid")
        args.namesfile = args.namesfile or str(cd / ".known_names.txt")

    if not args.mapfile or not args.deid_dir:
        print("Missing required arguments. Pass --challenge-dir OR both of --map "
              "and --deid-dir.", file=sys.stderr)
        return 1

    mapfile = Path(args.mapfile)
    deid_dir = Path(args.deid_dir)
    if not mapfile.exists():
        print(f"No key map at {mapfile} — run a grader_deidentify_* tool first.")
        return 1

    keymap = json.loads(mapfile.read_text(encoding="utf-8")).get("map", {})

    # Load roster — primary source of search terms (issue #49)
    known_names: list[str] = []
    if args.namesfile:
        known_names = load_known_names(Path(args.namesfile))

    stop = DEFAULT_STOP | {s.lower() for s in args.stop}

    # Report what we're checking against (counts only — names not printed)
    roster_term_count = len(expand_name_terms(known_names))
    print(f"Checking against {len(known_names)} roster name(s) "
          f"({roster_term_count} decomposed terms after first/last split) "
          f"+ filename tokens for legacy-named files.", file=sys.stderr)

    clean = flagged = missing = 0
    for key, fname in sorted(keymap.items()):
        md = deid_dir / f"{key}.md"
        if not md.exists():
            print(f"  {key}: no de-id output")
            missing += 1
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        terms = build_search_terms(fname, known_names, stop)
        # Word-boundary count per term (issue #49 — replaces text.count() which
        # was bare substring matching and would re-introduce false positives
        # after #47 even before #49's other fixes).
        hits = sum(name_aware_count(text, t) for t in terms)
        if hits:
            print(f"  {key}: {hits} possible name hit(s) — review this file locally")
            flagged += 1
        else:
            clean += 1

    # Counts only — no names ever to stdout
    print(f"\n{clean} clean, {flagged} to review, {missing} missing (of {len(keymap)} keys).")
    # P-003 stop-on-defect: exit 2 if any flag, 1 if missing-only, 0 if clean
    if flagged:
        return 2
    if missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

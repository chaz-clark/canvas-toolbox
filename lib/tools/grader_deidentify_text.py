#!/usr/bin/env python3
"""
grader_deidentify_text.py — FERPA de-identification for plain-text submissions.

Part of the canvas-toolbox generic grader skill (v1.0). See:
  - grading_readme.md (faculty-facing pipeline + canonical layout)
  - lib/agents/canvas_grader.md (agent-facing pipeline)
  - lib/agents/knowledge/grader_knowledge.md §1 (FERPA two-zone architecture)

WHAT IT DOES
  Handles three submission flavors that don't fit the docx / Databricks-HTML
  adapters:

  - **online_text_entry** (Canvas's "type your answer in the box" submission
    type). `grader_fetch.py` writes these to submissions_raw/<prefix>_<userid>.html
    as bare HTML body wrapping. This adapter strips the HTML and extracts the
    text body.

  - **.txt** plain-text submissions (lab reports, code listings, transcripts).
    Decodes with encoding fallback: UTF-8 → CP1252 → Latin-1.

  - **.md** Markdown submissions (technical writeups, reflection journals).
    Decoded as UTF-8; Markdown is preserved as-is (the grader reads it
    rendered as MD anyway).

  Reuses the secret/email/userpath regex from grader_deidentify_databricks
  (single source of truth — pattern improvements land in one place).

FERPA BOUNDARY
  Same contract as the other deid adapters:
  - submissions_raw/ has names; submissions_deid/ does not
  - .keymap.json (key↔filename bridge) is local-only, never read by AI
  - Console prints keys + counts only, NEVER a name to stdout/stderr
  - .known_names.txt drives peer-mention scrub (populated by grader_fetch's
    roster pre-fetch; can be appended manually too)

USAGE
  # Conventional layout (challenge-dir)
  uv run python lib/tools/grader_deidentify_text.py \\
    --challenge-dir grading/<asg> --prefix <PREFIX>

  # Explicit paths (when not using the conventional layout)
  uv run python lib/tools/grader_deidentify_text.py \\
    --in <dir> --out <dir> --map <file> --prefix <PREFIX>

GENERALIZED FROM: the online_text_entry adapter gap surfaced in m119's
pause handoff (2026-06-10) + the UniversalGrader docx (2026-06-11) which
documented the UTF-8 → CP1252 → Latin-1 encoding fallback pattern.
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

# Single source of truth for secret/identity patterns — reuse from the
# Databricks adapter so any pattern improvement lands in one place.
from grader_deidentify_databricks import (  # noqa: E402
    EMAIL_RE,
    USERPATH_RE,
    SECRET_PREFIX_RE,
    SECRET_ASSIGN_RE,
    key_for,
)

# File extensions this adapter accepts. .html is here because Canvas wraps
# online_text_entry bodies in HTML (grader_fetch writes them as .html).
_ACCEPT_EXTS = (".txt", ".md", ".html", ".htm")
_ENCODINGS = ("utf-8", "cp1252", "latin-1")


def read_text_with_fallback(path: Path) -> tuple[str, str]:
    """Decode a file trying UTF-8 → CP1252 → Latin-1. Returns (text, encoding_used).
    Latin-1 always succeeds (every byte is a valid Latin-1 codepoint), so this
    function never raises — but earlier successes are preferred."""
    raw = path.read_bytes()
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    # Latin-1 above will succeed; we won't reach here. Defensive return.
    return raw.decode("latin-1", errors="replace"), "latin-1"


def strip_html(text: str) -> str:
    """Strip HTML tags from an online_text_entry body. Canvas wraps the
    student's typed answer in basic HTML (<p>, <br>, <em>, <strong>, lists).
    Uses BeautifulSoup for robust handling of malformed markup."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, "html.parser")
    # Replace <br> with newlines, <p>/<li>/<div> with double newlines, before extracting text
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(["p", "li", "div", "h1", "h2", "h3", "h4", "h5", "h6"]):
        block.insert_after("\n\n")
    return soup.get_text(separator="").strip()


def build_scrub_terms(stem: str, body: str, extra_names: list[str]) -> list[str]:
    """Terms to redact: operator-supplied names, emails harvested from the body,
    userpaths, and (when filename matches Canvas's name-in-filename pattern)
    name halves split from the lastnamefirstname token. Mirrors the Databricks
    adapter's logic so peer-mention scrubbing is consistent across formats."""
    terms = set(extra_names)
    terms.update(EMAIL_RE.findall(body))
    terms.update(USERPATH_RE.findall(body))
    # If the file came in via the OLD manual-download workflow, the filename
    # has the lastname+firstname token before the first underscore. The new
    # grader_fetch.py uses <prefix>_<userid>.<ext>, so this only fires for
    # operator-renamed files. We still split halves and check for word-boundary
    # matches in the body — defense in depth.
    name_field = stem.split("_", 1)[0].lower()
    body_l = body.lower()
    if len(name_field) >= 4 and name_field not in {"html", "txt", "md", "late", "new"}:
        terms.add(name_field)
        for i in range(3, len(name_field) - 2):
            left, right = name_field[:i], name_field[i:]
            if (re.search(rf"\b{re.escape(left)}\b", body_l)
                    and re.search(rf"\b{re.escape(right)}\b", body_l)):
                terms.add(left)
                terms.add(right)
    return sorted((t for t in terms if t), key=len, reverse=True)


def scrub(text: str, terms: list[str]) -> tuple[str, int]:
    """Apply name-term scrub + the same belt-and-suspenders email/userpath/secret
    sweep used by the Databricks adapter."""
    n = 0
    for t in terms:
        pat = re.compile(re.escape(t), re.IGNORECASE)
        text, k = pat.subn("[REDACTED]", text)
        n += k
    text, k1 = EMAIL_RE.subn("[REDACTED]", text)
    text, k2 = USERPATH_RE.subn("[REDACTED]", text)
    text, k3 = SECRET_PREFIX_RE.subn("[REDACTED-SECRET]", text)
    text, k4 = SECRET_ASSIGN_RE.subn(r"\1=[REDACTED-SECRET]", text)
    return text, n + k1 + k2 + k3 + k4


def main() -> int:
    ap = argparse.ArgumentParser(
        description="FERPA de-identify plain-text / Markdown / online_text_entry "
                    "(HTML-wrapped) submissions. Decodes with UTF-8 → CP1252 → "
                    "Latin-1 fallback; strips HTML tags from online_text_entry "
                    "bodies; runs the standard secret/email/name scrub.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", dest="challenge_dir", default=None,
                    help="Convention base path (e.g. grading/p2t1_ai_log).")
    ap.add_argument("--in", dest="indir", default=None,
                    help="Raw submissions directory (default: <challenge-dir>/submissions_raw)")
    ap.add_argument("--out", dest="outdir", default=None,
                    help="Output directory for keyed .md files (default: <challenge-dir>/submissions_deid)")
    ap.add_argument("--map", dest="mapfile", default=None,
                    help="Path to .keymap.json (default: <challenge-dir>/.keymap.json)")
    ap.add_argument("--names", dest="namesfile", default=None,
                    help="Optional gitignored file of known student names to scrub, one per line "
                         "(default: <challenge-dir>/.known_names.txt)")
    ap.add_argument("--prefix", default=None,
                    help="Key prefix (e.g. P2T1_AI_LOG). Default: uppercased basename of --challenge-dir.")
    args = ap.parse_args()

    if args.challenge_dir:
        cd = resolve_challenge_dir(args.challenge_dir, verb="deidentifying (text) to")
        args.indir = args.indir or str(cd / "submissions_raw")
        args.outdir = args.outdir or str(cd / "submissions_deid")
        args.mapfile = args.mapfile or str(cd / ".keymap.json")
        args.namesfile = args.namesfile or str(cd / ".known_names.txt")
        args.prefix = args.prefix or cd.name.upper().replace("_", "-")

    missing = [a for a in ("indir", "outdir", "mapfile", "prefix") if not getattr(args, a)]
    if missing:
        print(f"Missing required arguments: {missing}. Pass --challenge-dir OR all of "
              f"--in/--out/--map/--prefix.", file=sys.stderr)
        return 1

    indir = Path(args.indir)
    outdir = Path(args.outdir)
    mapfile = Path(args.mapfile)
    outdir.mkdir(parents=True, exist_ok=True)

    extra_names: list[str] = []
    nf = Path(args.namesfile) if args.namesfile else None
    if nf and nf.exists():
        extra_names = [ln.strip() for ln in nf.read_text(encoding="utf-8").splitlines()
                       if ln.strip() and not ln.lstrip().startswith("#")]

    files = sorted(p for p in indir.iterdir()
                   if p.is_file() and p.suffix.lower() in _ACCEPT_EXTS)
    if not files:
        print(f"No {'/'.join(_ACCEPT_EXTS)} files in {indir}/ — nothing to do.",
              file=sys.stderr)
        return 1

    keymap: dict[str, str] = {}
    if mapfile.exists():
        try:
            keymap = json.loads(mapfile.read_text(encoding="utf-8")).get("map", {})
        except Exception:
            pass  # corrupt map — overwrite

    ok = fail = 0
    for f in files:
        key = key_for(f.name, args.prefix)
        try:
            raw_text, enc = read_text_with_fallback(f)
            # For HTML extensions, strip tags. For .txt / .md, treat as-is.
            if f.suffix.lower() in (".html", ".htm"):
                body = strip_html(raw_text)
            else:
                body = raw_text
            if not body.strip():
                print(f"  {key}: SKIP — empty body after extraction")
                fail += 1
                continue
            terms = build_scrub_terms(f.stem, body, extra_names)
            scrubbed, redactions = scrub(body, terms)
            out = outdir / f"{key}.md"
            header = f"# Submission {key}\n\n_Source format: {f.suffix.lower()} (decoded as {enc})_\n\n"
            out.write_text(header + scrubbed + "\n", encoding="utf-8")
            keymap[key] = f.name
            ok += 1
            # FERPA: print key + counts ONLY — never the name/email/filename body
            print(f"  {key}: {len(body)} chars, {redactions} redactions -> {out.name}")
        except Exception as e:
            # FERPA: never let a traceback print the filename — report by key only
            print(f"  {key}: SKIP — error ({type(e).__name__})")
            fail += 1

    mapfile.write_text(json.dumps(
        {"_warning": "FERPA — do NOT commit, do NOT let an AI read this. "
                     "Local re-identification only.",
         "map": keymap}, indent=2), encoding="utf-8")
    print(f"\n{ok} de-identified, {fail} skipped. "
          f"Map ({len(keymap)} keys) -> {mapfile} (gitignored, never read by AI).")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

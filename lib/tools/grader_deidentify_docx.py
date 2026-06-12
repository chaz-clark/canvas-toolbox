#!/usr/bin/env python3
"""
FERPA de-identification for Word (.docx) self-review submissions.

Part of the canvas-toolbox generic grader skill (v0.1). See:
  - lib/agents/canvas_grader.md (operator-facing pipeline guide)
  - lib/agents/knowledge/grader_knowledge.md (FERPA architecture, §1)

WHAT IT DOES
  Students fill a template whose top line is `Name: <their name>`. This reads each
  .docx (paragraphs AND table cells, in document order), pulls the name from that
  header, replaces it with the student's opaque key, scrubs the name (and emails
  / secrets / signatures) throughout, and writes one keyed .md the grader can
  safely read. The name↔key map stays local and is never read by the AI.

FERPA — same boundary as the Databricks adapter
  * Prints keys + counts only (never names).
  * The `Name:` field is replaced with the key; the `Signature:` value is
    redacted unconditionally (a signature can differ from the filename-derived
    name — e.g. nicknames, typos).
  * Name scrubbing uses word-boundary lookarounds so a short name ("Sam"/"Den")
    doesn't redact ordinary words ("same"/"evidence").
  * Structured identifiers (email, /Users path, secrets) are scrubbed BEFORE
    name tokens — else a name inside an email leaves the domain behind.

DEPENDENCIES
  Requires `python-docx`. Install via:
    uv add python-docx
  or run with `--with python-docx`:
    uv run --with python-docx python lib/tools/grader_deidentify_docx.py ...

USAGE
  # Conventional layout
  uv run python lib/tools/grader_deidentify_docx.py \\
    --challenge-dir grading/mid_review --prefix MR

  # Explicit paths
  uv run python lib/tools/grader_deidentify_docx.py \\
    --in <dir> --out <dir> --map <file> --prefix MR

GENERALIZED FROM: ds460-master/grading/deidentify_docx.py
(commit 8f7814b — round-2 Mid Performance Review beta).
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

# Reuse the scrub regexes + key_for from the databricks adapter (single source of truth).
sys.path.insert(0, str(Path(__file__).parent))
from grader_deidentify_databricks import (  # noqa: E402
    EMAIL_RE,
    USERPATH_RE,
    SECRET_PREFIX_RE,
    SECRET_ASSIGN_RE,
    key_for,
    expand_name_terms,  # issue #47 — decompose roster names into parts
)

NAME_RE = re.compile(r"^\s*name\s*[:\-]\s*(.+?)\s*$", re.I | re.M)
# Signatures are a name by definition — redact the value regardless of spelling.
SIG_RE = re.compile(r"^(\s*signature\s*[:\-]\s*).+$", re.I | re.M)


def docx_lines(path: Path) -> list[str]:
    """Text from paragraphs + table cells, in document order."""
    try:
        from docx import Document
        from docx.oxml.table import CT_Tbl
        from docx.oxml.text.paragraph import CT_P
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as e:
        print("Missing dependency: python-docx. Install via `uv add python-docx` or "
              "`uv run --with python-docx python ...`.", file=sys.stderr)
        raise

    doc = Document(str(path))
    out = []
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            t = Paragraph(child, doc).text
            if t.strip():
                out.append(t)
        elif isinstance(child, CT_Tbl):
            for row in Table(child, doc).rows:
                for cell in row.cells:
                    t = cell.text
                    if t.strip():
                        out.append(t)
    return out


def extract_name(lines: list[str]) -> str | None:
    for ln in lines[:20]:  # the Name: header is near the top
        m = NAME_RE.match(ln)
        if m and len(m.group(1).strip()) >= 2:
            return m.group(1).strip()
    return None


def scrub(text: str, name: str | None, extra_names: list[str]) -> tuple[str, int]:
    # issue #47 — decompose roster names too (not just the extracted Name: field).
    # Free-form prose in a docx can still reference peers/students by first
    # name only, so the full-name-only matching pre-#47 missed those.
    terms = set(expand_name_terms(extra_names))
    if name:
        terms.add(name)
        for part in re.split(r"[^A-Za-z]+", name):
            if len(part) >= 3:
                terms.add(part)  # first/last individually, for prose mentions
    # Structured identifiers FIRST — a name inside an email must be caught as a whole email before
    # the name-token pass leaves the domain behind.
    text, k1 = EMAIL_RE.subn("[REDACTED]", text)
    text, k2 = USERPATH_RE.subn("[REDACTED]", text)
    text, k3 = SECRET_PREFIX_RE.subn("[REDACTED-SECRET]", text)
    text, k4 = SECRET_ASSIGN_RE.subn(r"\1=[REDACTED-SECRET]", text)
    n = 0
    for t in sorted((t for t in terms if t), key=len, reverse=True):
        # word-boundary lookarounds so a short name (e.g. "Sam"/"Den") doesn't corrupt
        # ordinary words ("same"/"evidence").
        text, k = re.compile(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])", re.I).subn("[REDACTED]", text)
        n += k
    return text, n + k1 + k2 + k3 + k4


def main() -> int:
    ap = argparse.ArgumentParser(description="FERPA de-identify .docx self-reviews.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", dest="challenge_dir", default=None,
                    help="Convention base path (e.g. grading/mid_review). Sets defaults for "
                         "--in/--out/--map/--names under it.")
    ap.add_argument("--in", dest="indir", default=None,
                    help="Raw submissions directory (default: <challenge-dir>/submissions_raw)")
    ap.add_argument("--out", dest="outdir", default=None,
                    help="Output directory for keyed .md files (default: <challenge-dir>/submissions_deid)")
    ap.add_argument("--map", dest="mapfile", default=None,
                    help="Path to .keymap.json (default: <challenge-dir>/.keymap.json)")
    ap.add_argument("--names", dest="namesfile", default=None,
                    help="Optional gitignored full-roster file (default: <challenge-dir>/.known_names.txt)")
    ap.add_argument("--prefix", default=None,
                    help="Key prefix (e.g. MR). Default: uppercased basename of --challenge-dir.")
    args = ap.parse_args()

    if args.challenge_dir:
        cd = resolve_challenge_dir(args.challenge_dir, verb="deidentifying (docx) to")
        args.indir = args.indir or str(cd / "submissions_raw")
        args.outdir = args.outdir or str(cd / "submissions_deid")
        args.mapfile = args.mapfile or str(cd / ".keymap.json")
        args.namesfile = args.namesfile or str(cd / ".known_names.txt")
        args.prefix = args.prefix or cd.name.upper().replace("_", "-")

    missing = [a for a in ("indir", "outdir", "mapfile", "prefix") if not getattr(args, a)]
    if missing:
        print(f"Missing required arguments: {missing}. "
              f"Pass --challenge-dir OR all of --in/--out/--map/--prefix.", file=sys.stderr)
        return 1

    indir, outdir, mapfile = Path(args.indir), Path(args.outdir), Path(args.mapfile)
    outdir.mkdir(parents=True, exist_ok=True)
    files = sorted(indir.glob("*.docx"))
    if not files:
        print(f"No .docx files in {indir}/ — drop the uploaded reviews there first.")
        return 1

    extra: list[str] = []
    nf = Path(args.namesfile) if args.namesfile else None
    if nf and nf.exists():
        extra = [ln.strip() for ln in nf.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#")]

    keymap = json.loads(mapfile.read_text(encoding="utf-8")).get("map", {}) if mapfile.exists() else {}
    ok = fail = no_name = 0
    for f in files:
        key = key_for(f.name, args.prefix)
        try:
            lines = docx_lines(f)
        except ImportError:
            return 1  # error already printed
        except Exception as e:
            print(f"  {key}: SKIP — could not read .docx ({type(e).__name__})")
            fail += 1
            continue
        name = extract_name(lines)
        if not name:
            no_name += 1
        body = "\n".join(lines)
        if name:  # show the key where the name was
            body = NAME_RE.sub(f"Name: {key}", body, count=1)
        body = SIG_RE.sub(r"\1[REDACTED]", body)  # blank any signature value
        scrubbed, redactions = scrub(body, name, extra)
        out = outdir / f"{key}.md"
        out.write_text(f"# Submission {key}\n\n{scrubbed}\n", encoding="utf-8")
        keymap[key] = f.name  # the ONLY place the real filename is stored
        ok += 1
        # FERPA: print key + counts + whether Name header was found — NEVER the name
        print(f"  {key}: {len(lines)} lines, name {'found' if name else 'NOT FOUND'}, "
              f"{redactions} redactions -> {out.name}")

    mapfile.write_text(json.dumps(
        {"_warning": "FERPA — do NOT commit, do NOT let an AI read this. Local re-identification only.",
         "map": keymap}, indent=2), encoding="utf-8")
    print(f"\n{ok} de-identified, {fail} skipped, {no_name} with NO 'Name:' header (check those). "
          f"Map ({len(keymap)} keys) -> {mapfile} (gitignored, never read by AI).")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

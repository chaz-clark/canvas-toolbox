#!/usr/bin/env python3
"""
grader_deidentify_pdf.py — FERPA de-identification for PDF submissions.

Part of the canvas-toolbox generic grader skill (v1.0). See:
  - grading_readme.md (faculty-facing pipeline + canonical layout)
  - lib/agents/canvas_grader.md (agent-facing pipeline)
  - lib/agents/knowledge/grader_knowledge.md §1 (FERPA two-zone architecture)

WHAT IT DOES
  Extracts text from PDF submissions (scanned reports, lab writeups, problem
  sets exported to PDF) via pdfplumber's text layer, scrubs PDF metadata
  (Author / Title / Subject / Creator / Producer often carry student
  identity), runs the standard secret/email/name scrub, and writes a keyed
  markdown file with one page per section.

  Image-only PDFs (scanned-then-not-OCR'd) have no text layer; this tool
  loudly warns and writes a placeholder. Operator decides whether to OCR
  manually or skip the submission.

FERPA BOUNDARY
  Same contract as the other deid adapters:
  - submissions_raw/ has names (in filenames AND in PDF metadata AND in
    body content); submissions_deid/ does not
  - .keymap.json (key↔filename bridge) is local-only, never read by AI
  - Console prints keys + counts only, NEVER a name to stdout/stderr
  - **PDF metadata scrub** — pdfplumber exposes /Author, /Title, /Subject,
    /Creator, /Producer. We don't include any of these in the deid output;
    they're discarded.

WHY THIS EXISTS
  Real assignment formats that submit as PDF: lab reports, problem set
  scans, design documents, anything where a student exports their work to
  PDF (often from Word, often with their name in the document properties
  and the file name). Canvas doesn't normalize PDFs the way it normalizes
  text submissions, so the FERPA-clean path needs an adapter.

USAGE
  # Conventional layout
  uv run python lib/tools/grader_deidentify_pdf.py \\
    --challenge-dir grading/<asg> --prefix <PREFIX>

  # Explicit paths
  uv run python lib/tools/grader_deidentify_pdf.py \\
    --in <dir> --out <dir> --map <file> --prefix <PREFIX>

DEPENDENCIES
  Requires `pdfplumber` (shipped in pyproject.toml deps as of v0.33+).
  Falls back with a clear install hint if missing.
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

from grader_deidentify_databricks import (  # noqa: E402
    EMAIL_RE,
    USERPATH_RE,
    SECRET_PREFIX_RE,
    SECRET_ASSIGN_RE,
    key_for,
    expand_name_terms,  # issue #47 — decompose roster names into parts
    name_aware_subn,    # issue #47 — word-boundary scrub
)

_MAX_PAGES = 200  # safety cap — a 200pp student submission is already extreme
_TRUNCATE_PAGE_AT = 50_000  # per-page character cap (huge pages → giant prompts)


def extract_pdf_text(path: Path) -> tuple[list[str], dict, bool]:
    """Extract per-page text via pdfplumber. Returns (pages, metadata, has_text).

    has_text=False when the PDF has no extractable text layer (image-only /
    scanned-not-OCR'd). The caller surfaces this loudly so the operator
    knows to either OCR manually or skip the submission."""
    try:
        import pdfplumber
    except ImportError:
        print("Missing dependency: pdfplumber. Install via `uv add pdfplumber` "
              "or `uv sync` (it's in pyproject.toml deps).", file=sys.stderr)
        raise

    pages: list[str] = []
    metadata: dict = {}
    any_text = False
    with pdfplumber.open(str(path)) as pdf:
        metadata = dict(pdf.metadata or {})
        for i, page in enumerate(pdf.pages[:_MAX_PAGES]):
            text = page.extract_text() or ""
            if text.strip():
                any_text = True
            if len(text) > _TRUNCATE_PAGE_AT:
                text = text[:_TRUNCATE_PAGE_AT] + "\n…(page truncated)"
            pages.append(text)
    return pages, metadata, any_text


def build_scrub_terms(stem: str, body: str, metadata: dict, extra_names: list[str]) -> list[str]:
    """Terms to redact: operator-supplied names, ALL pdf metadata string values
    (Author/Title/Subject/Creator/Producer often carry the student's name),
    emails + userpaths harvested from the body, and (when filename matches
    Canvas's name-in-filename pattern) name halves."""
    terms = set(expand_name_terms(extra_names))  # issue #47 — decompose roster names
    # Metadata values are the strongest name signal in a PDF — Word/Pages
    # writes the document author's name into /Author by default.
    for v in metadata.values():
        if isinstance(v, str) and v.strip():
            # Only add metadata strings that look name-like (alpha + space + alpha)
            if re.match(r"^[A-Za-z][A-Za-z\s.'\-]{2,80}$", v.strip()):
                terms.add(v.strip())
    terms.update(EMAIL_RE.findall(body))
    terms.update(USERPATH_RE.findall(body))
    name_field = stem.split("_", 1)[0].lower()
    body_l = body.lower()
    if len(name_field) >= 4 and name_field not in {"pdf", "report", "submission"}:
        terms.add(name_field)
        for i in range(3, len(name_field) - 2):
            left, right = name_field[:i], name_field[i:]
            if (re.search(rf"\b{re.escape(left)}\b", body_l)
                    and re.search(rf"\b{re.escape(right)}\b", body_l)):
                terms.add(left)
                terms.add(right)
    return sorted((t for t in terms if t), key=len, reverse=True)


def scrub(text: str, terms: list[str]) -> tuple[str, int]:
    n = 0
    for t in terms:
        # issue #47 — word-boundary lookarounds so 'Sam' doesn't match 'Samsung'
        text, k = name_aware_subn(text, t)
        n += k
    text, k1 = EMAIL_RE.subn("[REDACTED]", text)
    text, k2 = USERPATH_RE.subn("[REDACTED]", text)
    text, k3 = SECRET_PREFIX_RE.subn("[REDACTED-SECRET]", text)
    text, k4 = SECRET_ASSIGN_RE.subn(r"\1=[REDACTED-SECRET]", text)
    return text, n + k1 + k2 + k3 + k4


def main() -> int:
    ap = argparse.ArgumentParser(
        description="FERPA de-identify PDF submissions. Extracts text via "
                    "pdfplumber, scrubs metadata + body, warns on image-only "
                    "PDFs that need OCR.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", dest="challenge_dir", default=None,
                    help="Convention base path (e.g. grading/lab_report).")
    ap.add_argument("--in", dest="indir", default=None,
                    help="Raw submissions directory (default: <challenge-dir>/submissions_raw)")
    ap.add_argument("--out", dest="outdir", default=None,
                    help="Output directory for keyed .md files (default: <challenge-dir>/submissions_deid)")
    ap.add_argument("--map", dest="mapfile", default=None,
                    help="Path to .keymap.json (default: <challenge-dir>/.keymap.json)")
    ap.add_argument("--names", dest="namesfile", default=None,
                    help="Optional gitignored file of known names (default: <challenge-dir>/.known_names.txt)")
    ap.add_argument("--prefix", default=None,
                    help="Key prefix (e.g. LAB1). Default: uppercased basename of --challenge-dir.")
    args = ap.parse_args()

    if args.challenge_dir:
        cd = resolve_challenge_dir(args.challenge_dir, verb="deidentifying (pdf) to")
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

    files = sorted(indir.glob("*.pdf"))
    if not files:
        print(f"No .pdf files in {indir}/ — nothing to do.", file=sys.stderr)
        return 1

    keymap: dict[str, str] = {}
    if mapfile.exists():
        try:
            keymap = json.loads(mapfile.read_text(encoding="utf-8")).get("map", {})
        except Exception:
            pass

    ok = fail = image_only = 0
    for f in files:
        key = key_for(f.name, args.prefix)
        try:
            pages, metadata, has_text = extract_pdf_text(f)
            if not has_text:
                # Image-only PDF — write a placeholder + warn loudly
                placeholder = (f"# Submission {key}\n\n"
                               f"⚠ **NO TEXT LAYER** — this PDF appears to be image-only "
                               f"(scanned, not OCR'd). The grader cannot read it. The "
                               f"operator should either:\n"
                               f"1. OCR the original locally (e.g., Adobe Acrobat or "
                               f"`ocrmypdf`), re-place into submissions_raw/, and re-run "
                               f"this adapter.\n"
                               f"2. Skip this submission and grade manually.\n\n"
                               f"_(File had {len(pages)} pages, no extractable text.)_\n")
                out = outdir / f"{key}.md"
                out.write_text(placeholder, encoding="utf-8")
                keymap[key] = f.name
                image_only += 1
                # FERPA: warn by KEY, never by filename body
                print(f"  {key}: WARN — image-only PDF (no text layer); placeholder written")
                continue

            # Combine pages into one body for scrub-term harvesting
            body = "\n\n".join(pages)
            terms = build_scrub_terms(f.stem, body, metadata, extra_names)

            # Scrub per-page and write with page markers preserved
            page_blocks = []
            total_redactions = 0
            for i, page_text in enumerate(pages, 1):
                if not page_text.strip():
                    continue
                scrubbed, n = scrub(page_text, terms)
                total_redactions += n
                page_blocks.append(f"## Page {i}\n\n{scrubbed}")

            out = outdir / f"{key}.md"
            header = f"# Submission {key}\n\n_Source: PDF ({len(pages)} pages, metadata scrubbed)_\n\n"
            out.write_text(header + "\n\n".join(page_blocks) + "\n", encoding="utf-8")
            keymap[key] = f.name
            ok += 1
            # FERPA: print KEY + counts only
            print(f"  {key}: {len(pages)} pages, {total_redactions} redactions -> {out.name}")
        except Exception as e:
            print(f"  {key}: SKIP — error ({type(e).__name__})")
            fail += 1

    mapfile.write_text(json.dumps(
        {"_warning": "FERPA — do NOT commit, do NOT let an AI read this. "
                     "Local re-identification only.",
         "map": keymap}, indent=2), encoding="utf-8")
    print(f"\n{ok} de-identified, {image_only} image-only (placeholder written, "
          f"needs OCR), {fail} skipped. "
          f"Map ({len(keymap)} keys) -> {mapfile} (gitignored, never read by AI).")
    if image_only:
        print(f"\n⚠ {image_only} PDF(s) had no text layer. Investigate the "
              f"placeholder files in {outdir}/ before grading.", file=sys.stderr)
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

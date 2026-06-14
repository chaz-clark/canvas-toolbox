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
    check_stale_prefix_files,
    expand_name_terms,  # issue #47 — decompose roster names into parts
)

NAME_RE = re.compile(r"^\s*name\s*[:\-]\s*(.+?)\s*$", re.I | re.M)
# Signatures are a name by definition — redact the value regardless of spelling.
SIG_RE = re.compile(r"^(\s*signature\s*[:\-]\s*).+$", re.I | re.M)

# issue #50 — sign-off + letterhead name detection (free-form letters with no Name: header)
# The ds250 mid-letter leak case: letter ends "From,\n<Firstname Lastname>" or opens
# with a "To: <prof> / From: <name>" letterhead. Old code missed both → silent leak.

# Sign-off keyword as the ENTIRE line (with optional trailing comma/period). The typed
# name is on the following line. Single-line "Sincerely, Jane" doesn't match (since the
# name is on the same line); FROM_RE / NAME_RE handle that shape via value extraction.
SIGN_OFF_RE = re.compile(
    r"^\s*(sincerely|sincerely yours|regards|best regards|best wishes|best|"
    r"thanks|thank you|thanks again|from|respectfully|respectfully yours|"
    r"warm regards|kind regards|cheers|yours truly|yours)\s*[,.]?\s*$",
    re.I,
)

# "From: <name>" letterhead line — value-bearing, treat like NAME_RE.
FROM_RE = re.compile(r"^\s*from\s*[:\-]\s*(.+?)\s*$", re.I | re.M)

# A name candidate looks like 1-4 alpha tokens (with optional hyphen/apostrophe).
# Used to filter what the sign-off / letterhead heuristics emit so we don't add
# arbitrary prose ("Best regards to my classmates") as a scrub term.
_NAME_CANDIDATE_RE = re.compile(r"^[A-Za-z][A-Za-z\-'. ]{1,79}$")


def _looks_like_name(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if not _NAME_CANDIDATE_RE.match(s):
        return False
    return 1 <= len(s.split()) <= 4


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
    """Find the canonical `Name: <value>` header (the template-form path)."""
    for ln in lines[:20]:  # the Name: header is near the top
        m = NAME_RE.match(ln)
        if m and len(m.group(1).strip()) >= 2:
            return m.group(1).strip()
    return None


def extract_letterhead_names(lines: list[str]) -> list[str]:
    """Find names following 'From: <name>' letterhead lines. Issue #50 —
    letters that open with a To:/From: block put the student name on the From line."""
    names: list[str] = []
    for ln in lines[:30]:  # letterheads are near the top
        m = FROM_RE.match(ln)
        if m:
            candidate = m.group(1).strip()
            if _looks_like_name(candidate):
                names.append(candidate)
    return names


def extract_sign_off_names(lines: list[str]) -> list[str]:
    """Find names following common sign-offs. Issue #50 — a letter that ends
    'Sincerely,\\n<Firstname Lastname>' or 'From,\\n<name>' lands the typed
    name on the line AFTER the sign-off keyword. docx_lines() already filters
    empty lines, so lines[i+1] IS the next non-empty content line."""
    names: list[str] = []
    for i, ln in enumerate(lines):
        if SIGN_OFF_RE.match(ln) and i + 1 < len(lines):
            candidate = lines[i + 1].strip()
            if _looks_like_name(candidate):
                names.append(candidate)
    return names


def collect_structural_names(lines: list[str]) -> list[str]:
    """Union of all structural name-detection paths. Used by main() to (a) feed
    the scrub-term list AND (b) decide whether to quarantine the file: if NO
    structural path catches a name, confidence is too low to ship without
    operator review (issue #50 quarantine trigger)."""
    out: list[str] = []
    header = extract_name(lines)
    if header:
        out.append(header)
    out.extend(extract_letterhead_names(lines))
    out.extend(extract_sign_off_names(lines))
    # Dedup while preserving order (insertion order)
    seen = set()
    uniq = []
    for n in out:
        if n.lower() not in seen:
            seen.add(n.lower())
            uniq.append(n)
    return uniq


def scrub(text: str, structural_names: list[str], extra_names: list[str]) -> tuple[str, int]:
    # issue #47 — decompose roster names too (not just the extracted Name: field).
    # Free-form prose in a docx can still reference peers/students by first
    # name only, so the full-name-only matching pre-#47 missed those.
    # issue #50 — structural_names now includes ALL detected names (Name: header,
    # From: letterhead, sign-off-then-next-line). Each gets decomposed too so
    # 'Jane Smith' caught from a sign-off also scrubs 'Jane' alone elsewhere.
    terms = set(expand_name_terms(extra_names))
    for n in structural_names:
        terms.add(n)
        for part in re.split(r"[^A-Za-z]+", n):
            if len(part) >= 3:
                terms.add(part)  # first/last individually, for prose mentions
    # Structured identifiers FIRST — a name inside an email must be caught as a whole email before
    # the name-token pass leaves the domain behind.
    text, k1 = EMAIL_RE.subn("[REDACTED]", text)
    text, k2 = USERPATH_RE.subn("[REDACTED]", text)
    text, k3 = SECRET_PREFIX_RE.subn("[REDACTED-SECRET]", text)
    text, k4 = SECRET_ASSIGN_RE.subn(r"\1=[REDACTED-SECRET]", text)
    n_count = 0
    for t in sorted((t for t in terms if t), key=len, reverse=True):
        # word-boundary lookarounds so a short name (e.g. "Sam"/"Den") doesn't corrupt
        # ordinary words ("same"/"evidence").
        text, k = re.compile(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])", re.I).subn("[REDACTED]", text)
        n_count += k
    return text, n_count + k1 + k2 + k3 + k4


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
    ap.add_argument("--cleanup-legacy", action="store_true",
                    help="Issue #54 sub-D: when stale `<OTHER-PREFIX>-HASH.md` files from a prior run "
                         "live in the output dir, remove them instead of refusing to run.")
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

    # Issue #54 sub-D: refuse to write a second prefix family into this dir.
    check_stale_prefix_files(outdir, args.prefix, cleanup=args.cleanup_legacy)
    # issue #50 — quarantine directory for files with no structural name detected.
    # The agent's pipeline reads submissions_deid/<KEY>.md; quarantined files land
    # in submissions_deid/_REVIEW/<KEY>.md so they're isolated from the agent's
    # read path until the operator hand-clears them.
    review_dir = outdir / "_REVIEW"

    files = sorted(indir.glob("*.docx"))
    if not files:
        print(f"No .docx files in {indir}/ — drop the uploaded reviews there first.")
        return 1

    extra: list[str] = []
    nf = Path(args.namesfile) if args.namesfile else None
    if nf and nf.exists():
        extra = [ln.strip() for ln in nf.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#")]

    # issue #50 — roster-completeness warning. The .known_names.txt roster is the
    # safety net for the no-structural-name case; if it's missing or short
    # relative to submission count, names will leak through for unlisted students.
    if not extra:
        print(f"  ⚠  WARNING: .known_names.txt is empty or missing. The "
              f"roster-based peer-mention scrub is OFF. If any submission lacks "
              f"a structural name (Name:/From:/sign-off), names of unlisted "
              f"students WILL leak. Run grader_fetch.py with roster pre-fetch "
              f"(default ON) or populate {nf} manually.", file=sys.stderr)
    elif len(extra) < len(files) * 0.8:
        print(f"  ⚠  WARNING: .known_names.txt has {len(extra)} name(s) but "
              f"{len(files)} submission(s) — roster may be incomplete. Names of "
              f"unlisted students will leak through if their submissions lack a "
              f"structural name header. Consider re-running grader_fetch.py with "
              f"--no-roster removed (default ON).", file=sys.stderr)

    keymap = json.loads(mapfile.read_text(encoding="utf-8")).get("map", {}) if mapfile.exists() else {}
    ok = fail = quarantined = 0
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

        # issue #50 — collect ALL structural names: Name: header + From: letterhead
        # + sign-off-then-next-line. Any non-empty result = "we caught at least one
        # structural name path"; empty = quarantine.
        structural_names = collect_structural_names(lines)
        header_name = extract_name(lines)  # for the NAME_RE.sub key-replacement below

        body = "\n".join(lines)
        if header_name:  # show the key where the Name: header was
            body = NAME_RE.sub(f"Name: {key}", body, count=1)
        body = SIG_RE.sub(r"\1[REDACTED]", body)  # blank any signature value
        scrubbed, redactions = scrub(body, structural_names, extra)

        # Decide output path: normal vs. quarantine
        if structural_names:
            out = outdir / f"{key}.md"
            ok += 1
            status = f"name found ({len(structural_names)} structural)"
        else:
            review_dir.mkdir(parents=True, exist_ok=True)
            out = review_dir / f"{key}.md"
            quarantined += 1
            status = "NO STRUCTURAL NAME → QUARANTINED"

        out.write_text(f"# Submission {key}\n\n{scrubbed}\n", encoding="utf-8")
        keymap[key] = f.name  # the ONLY place the real filename is stored
        # FERPA: print key + counts + structural-name status — NEVER the name
        print(f"  {key}: {len(lines)} lines, {status}, {redactions} redactions "
              f"-> {out.relative_to(outdir.parent) if out.is_relative_to(outdir.parent) else out.name}")

    mapfile.write_text(json.dumps(
        {"_warning": "FERPA — do NOT commit, do NOT let an AI read this. Local re-identification only.",
         "map": keymap}, indent=2), encoding="utf-8")

    print(f"\n{ok} de-identified, {fail} skipped, {quarantined} quarantined to "
          f"_REVIEW/. Map ({len(keymap)} keys) -> {mapfile} (gitignored, never read by AI).")

    if quarantined:
        print(f"\n⛔ {quarantined} file(s) lack any structural name pattern "
              f"(Name:/From:/sign-off). They have been written to:", file=sys.stderr)
        print(f"     {review_dir}", file=sys.stderr)
        print(f"   These files HAVE been scrubbed against the roster but might "
              f"still contain inline name mentions the roster missed. The "
              f"operator MUST manually review each before moving it to "
              f"{outdir} for grading. The agent pipeline (grader_fetch.py "
              f"chain) will STOP here because this exit is non-zero.",
              file=sys.stderr)
        return 2

    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

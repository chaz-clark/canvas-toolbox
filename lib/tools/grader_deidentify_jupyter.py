#!/usr/bin/env python3
"""
grader_deidentify_jupyter.py — FERPA de-identification for Jupyter (.ipynb)
submissions.

Part of the canvas-toolbox generic grader skill (v1.0). See:
  - grading_readme.md (faculty-facing pipeline + canonical layout)
  - lib/agents/canvas_grader.md (agent-facing pipeline)
  - lib/agents/knowledge/grader_knowledge.md §1 (FERPA two-zone architecture)

WHAT IT DOES
  Jupyter notebooks (.ipynb) are the standardized open-format equivalent of
  Databricks's proprietary notebook model. The file is a JSON document with
  a top-level `cells` array; each cell has `cell_type` (markdown / code /
  raw), `source` (the cell body), and `outputs` (for code cells — stream
  outputs, execute results, errors).

  This adapter extracts per-cell content in document order with the same
  `### Cell N` heading shape the Databricks adapter uses, so the grader
  reads .ipynb submissions the same way it reads Databricks HTML exports.
  Reuses the secret/identity scrub patterns from grader_deidentify_databricks
  (single source of truth).

  Notebook metadata (kernel info, language version, etc.) is NOT included
  in the deid output — those fields can carry the student's kernel-spec
  user path or other identifying info.

FERPA BOUNDARY
  Same contract as the other deid adapters:
  - submissions_raw/ has names (in filenames AND in notebook metadata AND
    in cell content); submissions_deid/ does not
  - .keymap.json (key↔filename bridge) is local-only, never read by AI
  - Console prints keys + counts only, NEVER a name to stdout/stderr
  - Per-cell embedded images (base64 .png/.jpg) are dropped — both for size
    and because they could be screenshots containing identifying info
  - Per-cell stdout/stderr text outputs are kept but length-capped

WHY THIS IS A SEPARATE ADAPTER FROM `text`
  The text adapter would treat the .ipynb file as raw JSON and either fail
  cleanly or produce gibberish output. Jupyter notebooks need structured
  cell-aware extraction to be gradeable.

  Could a future shared "structured-notebook" helper merge with the
  Databricks model-decode logic? Yes — both formats encode the same
  "cells with sources and outputs" shape. For now they stay separate so
  each can evolve independently; consolidation is parking-lot if the
  duplication starts hurting.

USAGE
  # Conventional layout
  uv run python lib/tools/grader_deidentify_jupyter.py \\
    --challenge-dir grading/<asg> --prefix <PREFIX>

  # Explicit paths
  uv run python lib/tools/grader_deidentify_jupyter.py \\
    --in <dir> --out <dir> --map <file> --prefix <PREFIX>
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
    check_stale_prefix_files,
    expand_name_terms,  # issue #47 — decompose roster names into parts
    name_aware_subn,    # issue #47 — word-boundary scrub
)

MAX_OUTPUT_CHARS = 1200  # per-cell output cap (small results kept; giant dumps trimmed)


def _cell_source(cell: dict) -> str:
    """Cell source is sometimes a list of strings, sometimes a single string."""
    s = cell.get("source", "")
    return "".join(s) if isinstance(s, list) else (s or "")


def _cell_text_outputs(cell: dict) -> str:
    """Extract readable text from code-cell outputs; drop images and base64 blobs.
    Length-capped per cell so a giant table doesn't bloat the deid output."""
    chunks: list[str] = []
    for o in cell.get("outputs", []):
        ot = o.get("output_type")
        if ot == "stream":
            t = o.get("text", "")
            chunks.append("".join(t) if isinstance(t, list) else t)
        elif ot in ("execute_result", "display_data"):
            data = o.get("data", {})
            tp = data.get("text/plain")
            if tp:
                chunks.append("".join(tp) if isinstance(tp, list) else tp)
            # text/html, image/png, application/json — dropped on purpose:
            # html may carry styling/scripts; images may be screenshots with PII;
            # json is rarely useful in human-readable form for grading.
        elif ot == "error":
            ename = o.get("ename", "")
            evalue = o.get("evalue", "")
            chunks.append(f"[error] {ename}: {evalue}")
            # traceback can carry /Users/... paths — but those get scrubbed
            # by the standard USERPATH_RE pass downstream.
            tb = o.get("traceback", [])
            if tb:
                chunks.append("\n".join(str(t) for t in tb))
    out = "\n".join(c for c in chunks if c).strip()
    if len(out) > MAX_OUTPUT_CHARS:
        return out[:MAX_OUTPUT_CHARS] + "\n…(truncated)"
    return out


def extract_cells(notebook: dict) -> list[dict]:
    """Return cells in document order, each as {type, source, output}."""
    cells = []
    for cell in notebook.get("cells", []):
        ct = cell.get("cell_type", "")
        src = _cell_source(cell).strip()
        if not src and ct == "code":
            # skip empty code cells but keep empty markdown cells out too
            continue
        cells.append({
            "type": ct,
            "source": src,
            "output": _cell_text_outputs(cell) if ct == "code" else "",
        })
    return cells


def build_scrub_terms(stem: str, body: str, notebook: dict, extra_names: list[str]) -> list[str]:
    """Terms to redact: operator-supplied names, notebook metadata strings,
    emails + userpaths from the body, and (when filename matches Canvas's
    name-in-filename pattern) name halves."""
    terms = set(expand_name_terms(extra_names))  # issue #47 — decompose roster names
    # Notebook metadata can carry user paths (kernel.path), Databricks-style
    # author fields, or arbitrary author-set fields. Pull any string value
    # that's email-shaped or userpath-shaped from the full metadata blob.
    meta_blob = json.dumps(notebook.get("metadata", {}) or {}, ensure_ascii=False)
    terms.update(EMAIL_RE.findall(meta_blob))
    terms.update(USERPATH_RE.findall(meta_blob))
    # And from the body (which is the cell sources + outputs concatenated)
    terms.update(EMAIL_RE.findall(body))
    terms.update(USERPATH_RE.findall(body))
    # Filename-token splits (legacy Canvas-download naming — new grader_fetch
    # uses <prefix>_<userid>.ipynb so this only fires for renamed files)
    name_field = stem.split("_", 1)[0].lower()
    body_l = body.lower()
    if len(name_field) >= 4 and name_field not in {"ipynb", "notebook", "untitled"}:
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
        description="FERPA de-identify Jupyter (.ipynb) submissions. Parses "
                    "the notebook JSON, extracts per-cell content in document "
                    "order, drops embedded images/HTML/base64 outputs, scrubs "
                    "metadata + body.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", dest="challenge_dir", default=None,
                    help="Convention base path (e.g. grading/kc1).")
    ap.add_argument("--in", dest="indir", default=None,
                    help="Raw submissions directory (default: <challenge-dir>/submissions_raw)")
    ap.add_argument("--out", dest="outdir", default=None,
                    help="Output directory for keyed .md files (default: <challenge-dir>/submissions_deid)")
    ap.add_argument("--map", dest="mapfile", default=None,
                    help="Path to .keymap.json (default: <challenge-dir>/.keymap.json)")
    ap.add_argument("--names", dest="namesfile", default=None,
                    help="Optional gitignored file of known names (default: <challenge-dir>/.known_names.txt)")
    ap.add_argument("--prefix", default=None,
                    help="Key prefix. Default: uppercased basename of --challenge-dir.")
    ap.add_argument("--cleanup-legacy", action="store_true",
                    help="Issue #54 sub-D: when stale `<OTHER-PREFIX>-HASH.md` files from a prior run "
                         "live in the output dir, remove them instead of refusing to run.")
    args = ap.parse_args()

    if args.challenge_dir:
        cd = resolve_challenge_dir(args.challenge_dir, verb="deidentifying (jupyter) to")
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

    # Issue #54 sub-D: refuse to write a second prefix family into this dir.
    check_stale_prefix_files(outdir, args.prefix, cleanup=args.cleanup_legacy)

    extra_names: list[str] = []
    nf = Path(args.namesfile) if args.namesfile else None
    if nf and nf.exists():
        extra_names = [ln.strip() for ln in nf.read_text(encoding="utf-8").splitlines()
                       if ln.strip() and not ln.lstrip().startswith("#")]

    files = sorted(indir.glob("*.ipynb"))
    if not files:
        print(f"No .ipynb files in {indir}/ — nothing to do.", file=sys.stderr)
        return 1

    keymap: dict[str, str] = {}
    if mapfile.exists():
        try:
            keymap = json.loads(mapfile.read_text(encoding="utf-8")).get("map", {})
        except Exception:
            pass

    ok = fail = 0
    for f in files:
        key = key_for(f.name, args.prefix)
        try:
            nb = json.loads(f.read_text(encoding="utf-8", errors="replace"))
            cells = extract_cells(nb)
            if not cells:
                print(f"  {key}: SKIP — no non-empty cells in notebook")
                fail += 1
                continue
            # Build the full body once for term harvesting
            body_blob = "\n".join(c["source"] + "\n" + c["output"] for c in cells)
            terms = build_scrub_terms(f.stem, body_blob, nb, extra_names)
            # Render cell-by-cell with scrubbing
            blocks = []
            total_redactions = 0
            for i, cell in enumerate(cells, 1):
                src_scrubbed, n1 = scrub(cell["source"], terms)
                total_redactions += n1
                fence = "```python" if cell["type"] == "code" else "```"
                block = [f"### Cell {i} ({cell['type']})", fence, src_scrubbed, "```"]
                if cell["output"]:
                    out_scrubbed, n2 = scrub(cell["output"], terms)
                    total_redactions += n2
                    block += ["", "_Output:_", "```", out_scrubbed, "```"]
                blocks.append("\n".join(block))
            out = outdir / f"{key}.md"
            out.write_text(
                f"# Submission {key}\n\n_Source: Jupyter notebook ({len(cells)} cells)_\n\n"
                + "\n\n".join(blocks) + "\n",
                encoding="utf-8",
            )
            keymap[key] = f.name
            ok += 1
            # FERPA: print KEY + counts only
            print(f"  {key}: {len(cells)} cells, {total_redactions} redactions -> {out.name}")
        except json.JSONDecodeError as e:
            print(f"  {key}: SKIP — invalid JSON ({type(e).__name__})")
            fail += 1
        except Exception as e:
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

#!/usr/bin/env python3
"""
grader_prep_answer_key.py — secret-scrub an instructor's .ipynb answer key
into a clean markdown reference the grader can read.

Part of the canvas-toolbox generic grader skill (v1.0). See:
  - grading_readme.md (faculty-facing pipeline guide + canonical layout)
  - lib/agents/canvas_grader.md (agent-facing pipeline guide)
  - lib/agents/knowledge/grader_knowledge.md §3 (signals are priors; the
    answer key is a *reference*, not a gate)

WHAT IT DOES
  Reads a raw instructor `.ipynb` answer key, extracts markdown + code +
  TEXT outputs (drops embedded images so the file stays small), secret-
  scrubs hardcoded tokens / PATs / API keys, and writes a clean
  `key_clean.md` next to the source.

  The answer key is the INSTRUCTOR's own work (not student data), so this
  scrubs SECRETS, not names. The raw `.ipynb` stays gitignored (per the
  `scaffold/grading/.gitignore` convention) and the clean `.md` is
  gitignored too — answer keys never leave the local machine.

WHY THIS EXISTS
  Code/notebook take-home assessments (Key Challenges, lab exercises,
  homework problem sets) need a reference key the grader can ground per-
  question feedback against. Instructor notebooks often hardcode tokens
  (Databricks PATs, GitHub PATs, API keys, S3 secrets) for testing —
  pasting that raw notebook into a cloud LLM context is a credential leak.
  This tool deletes the leak surface before grading starts.

FERPA / SECURITY BOUNDARY
  * Scrubs SECRETS only — there are no student names in the instructor's
    own answer key. (For student work, use `grader_deidentify_*` instead.)
  * Output sits next to the source by default at `<input>.with_name(
    "key_clean.md")`, so the answer-keys folder convention is preserved:
        grading/answer_keys/<assignment>/<key>.ipynb        (raw, gitignored)
        grading/answer_keys/<assignment>/key_clean.md       (scrubbed, gitignored)
  * The raw `.ipynb` is NEVER read by the grading AI. The grader reads
    `key_clean.md` only.
  * **Revoke the hardcoded token regardless** — scrubbing protects the
    cloud hop, not the token itself.

USAGE
  # Conventional layout (answer-keys folder)
  uv run python lib/tools/grader_prep_answer_key.py \\
    grading/answer_keys/kc1/kc1_key.ipynb

  # The output is written alongside as key_clean.md:
  #   grading/answer_keys/kc1/key_clean.md

GENERALIZED FROM: ds460-master/grading/prep_answer_key.py (round-1 KC1 +
KC2 beta; instructor's own work, secret-scrubbed for cloud-safe grading
reference).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

# Single source of truth for the secret/email patterns — reuse from the
# de-id pipeline so any pattern improvement lands in one place.
from grader_deidentify_databricks import (  # noqa: E402
    EMAIL_RE,
    USERPATH_RE,
    SECRET_PREFIX_RE,
    SECRET_ASSIGN_RE,
)

MAX_OUTPUT_CHARS = 2000  # cap per-cell output so a giant table doesn't bloat the reference


def scrub_secrets(text: str) -> tuple[str, int]:
    """Run the secret/email/userpath patterns; return (scrubbed_text, count)."""
    n = 0
    text, k = SECRET_PREFIX_RE.subn("[REDACTED-SECRET]", text); n += k
    text, k = SECRET_ASSIGN_RE.subn(r"\1=[REDACTED-SECRET]", text); n += k
    text, k = EMAIL_RE.subn("[REDACTED]", text); n += k
    text, k = USERPATH_RE.subn("[REDACTED]", text); n += k
    return text, n


def src(cell: dict) -> str:
    s = cell.get("source", "")
    return "".join(s) if isinstance(s, list) else (s or "")


def text_outputs(cell: dict) -> str:
    """Pull readable text from code-cell outputs; skip images / base64 / huge dumps."""
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
        elif ot == "error":
            chunks.append(f"[error] {o.get('ename','')}: {o.get('evalue','')}")
    out = "\n".join(c for c in chunks if c).strip()
    if len(out) > MAX_OUTPUT_CHARS:
        return out[:MAX_OUTPUT_CHARS] + "\n…(truncated)"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Secret-scrub an instructor .ipynb answer key into a clean "
                    "key_clean.md grading reference (markdown + code + text outputs; "
                    "images dropped; tokens/PATs redacted).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("key", help="Path to the raw .ipynb answer key (instructor's own work)")
    ap.add_argument("--out", default=None,
                    help="Output path (default: <key>.with_name('key_clean.md') — "
                         "sits next to the source per the answer-keys convention)")
    args = ap.parse_args()

    nb_path = Path(args.key)
    if not nb_path.exists():
        print(f"not found: {nb_path}", file=sys.stderr)
        return 1
    if nb_path.suffix.lower() != ".ipynb":
        print(f"expected .ipynb, got {nb_path.suffix}", file=sys.stderr)
        return 1

    try:
        nb = json.loads(nb_path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        print(f"could not parse {nb_path.name} as JSON: {e}", file=sys.stderr)
        return 1

    body: list[str] = []
    redactions = 0
    ncells = 0
    for cell in nb.get("cells", []):
        ct = cell.get("cell_type")
        s = src(cell).strip()
        if not s and ct == "code":
            continue
        ncells += 1
        if ct == "markdown":
            s2, k = scrub_secrets(s); redactions += k
            body.append(s2)
        elif ct == "code":
            s2, k = scrub_secrets(s); redactions += k
            block = ["```python", s2, "```"]
            out = text_outputs(cell)
            if out:
                out2, k2 = scrub_secrets(out); redactions += k2
                block += ["", "_Output:_", "```", out2, "```"]
            body.append("\n".join(block))

    out_path = Path(args.out) if args.out else nb_path.with_name("key_clean.md")
    header = (f"# Answer key (reference) — {nb_path.parent.name}\n\n"
              "_Secret-scrubbed; code + text outputs only (images dropped). "
              "Reference, not a gate._\n\n")
    out_path.write_text(header + "\n\n".join(body) + "\n", encoding="utf-8")
    size_kb = max(1, out_path.stat().st_size // 1024)

    # Console output: counts only. (The path is operator's own work — not student PII —
    # so printing the input filename is fine; this is symmetric with the deidentify
    # tools where the equivalent print would be PII and is forbidden.)
    print(f"{nb_path.name}: {ncells} cells, {redactions} secret/email redactions "
          f"-> {out_path.name} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

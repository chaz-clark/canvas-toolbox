#!/usr/bin/env python3
"""
FERPA de-identification + extraction for Databricks .html submissions.

Part of the canvas-toolbox generic grader skill (v0.1). See:
  - lib/agents/canvas_grader.md (operator-facing pipeline guide)
  - lib/agents/knowledge/grader_knowledge.md (FERPA architecture, §1)

WHAT IT DOES
  Reads raw Databricks HTML exports (filenames + content carry student identity),
  decodes the embedded __DATABRICKS_NOTEBOOK_MODEL, extracts the notebook cells
  (markdown + code + results), scrubs identity + secrets, and writes ONE clean
  keyed markdown file per submission that an AI grader can safely read.

FERPA BOUNDARY — read this before changing anything
  * The raw input folder and the key map are the ONLY places real names live.
    Both must be gitignored in the consumer course repo. Do NOT commit them.
    Do NOT let an AI read them.
  * This script NEVER prints a student name, email, or original filename to
    stdout/stderr — only opaque keys and counts. (The operator reads the
    console; an agent may read it too.) Keep it that way.
  * Re-identification happens locally, by the operator, using the key map —
    never in the cloud and never by the grading agent.

USAGE
  # Conventional layout (challenge-dir + standard subpaths)
  uv run python lib/tools/grader_deidentify_databricks.py \\
    --challenge-dir grading/kc1 \\
    --prefix KC1

  # Explicit paths (when not using the conventional layout)
  uv run python lib/tools/grader_deidentify_databricks.py \\
    --in <dir> --out <dir> --map <file> --prefix KC1

GENERALIZED FROM: ds460-master/grading/deidentify_databricks.py
(commits 754c966..91a5113 — round-1 KC1 beta).
"""
from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import base64
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path
from _challenge_dir_guard import resolve_challenge_dir  # issue #44 FERPA guard

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

MODEL_RE = re.compile(r"__DATABRICKS_NOTEBOOK_MODEL\s*=\s*(['\"])(.*?)\1", re.DOTALL)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
USERPATH_RE = re.compile(r"/Users/[^/\s\"']+")
# Credentials that must never reach the cloud (not FERPA, but students hardcode tokens/keys)
SECRET_PREFIX_RE = re.compile(r"\b(?:github_pat_[A-Za-z0-9_]+|gh[opsru]_[A-Za-z0-9]+|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]+)\b")
SECRET_ASSIGN_RE = re.compile(
    r"""(?i)\b(token|api[_-]?key|census[_-]?key|secret|password|passwd|pwd|pat|bearer)\b\s*[:=]\s*(['"])[^'"\n]{8,}\2""")
# identity-bearing keys inside the Databricks model that we drop wholesale
IDENTITY_KEYS = {"user", "userId", "userName", "displayName", "email", "tags",
                 "notebookPath", "orgId", "guid", "origId"}

MAX_RESULT_CHARS = 1200  # cap per-cell output: keep small results (counts, tables), drop giant data dumps


def decode_model(raw: str) -> dict | None:
    """Databricks encodes the model as base64 (sometimes URI-wrapped) JSON. Try strategies."""
    candidates = []
    # Databricks: base64( uri-encoded( JSON ) ) — so b64-decode FIRST, then unquote.
    try:
        b64 = base64.b64decode(raw).decode("utf-8", "replace")
        candidates.append(urllib.parse.unquote(b64))
        candidates.append(b64)
    except Exception:
        pass
    # fallbacks for other export variants
    for transform in (lambda s: s, urllib.parse.unquote, urllib.parse.unquote_plus):
        s = transform(raw)
        candidates.append(s)
        try:
            candidates.append(base64.b64decode(s).decode("utf-8", "replace"))
        except Exception:
            pass
    for c in candidates:
        c = c.strip()
        if not c:
            continue
        start = c.find("{")
        if start == -1:
            continue
        try:
            return json.loads(c[start:])
        except Exception:
            continue
    return None


def strip_identity(obj):
    """Recursively drop identity-bearing keys from the model before extraction."""
    if isinstance(obj, dict):
        return {k: strip_identity(v) for k, v in obj.items() if k not in IDENTITY_KEYS}
    if isinstance(obj, list):
        return [strip_identity(v) for v in obj]
    return obj


def result_text(cmd: dict) -> str:
    """Pull a readable, length-capped text rendering of a command's results, if any."""
    res = cmd.get("results")
    if not isinstance(res, dict):
        return ""
    data = res.get("data")
    out = ""
    if isinstance(data, str):
        out = data
    elif isinstance(data, list):
        parts = []
        for row in data[:30]:
            if isinstance(row, list):
                parts.append("\t".join(str(x) for x in row))
            elif isinstance(row, dict):
                d = row.get("data", row)
                parts.append(d if isinstance(d, str) else str(d))
            else:
                parts.append(str(row))
        out = "\n".join(parts)
    return out[:MAX_RESULT_CHARS] + ("\n…(truncated)" if len(out) > MAX_RESULT_CHARS else "")


def extract_cells(model: dict) -> list[dict]:
    cmds = model.get("commands") or []
    cells = []
    for c in sorted(cmds, key=lambda x: x.get("position", 0)):
        src = (c.get("command") or "").strip()
        if not src:
            continue
        cells.append({"source": src, "result": result_text(c).strip()})
    return cells


# ---------------------------------------------------------------------------
# Shared scrub helpers — used by every grader_deidentify_* adapter.
#
# expand_name_terms(): the fix for issue #47 (ds250-onln-master 2026-06-12 —
#   free-form prose Quarto letters slipped name mentions past the deid scrub
#   because .known_names.txt has FULL display names but students often sign
#   off with FIRST NAME ONLY). For each roster entry, decompose into the
#   full name + each individual part (first/last/middle) ≥3 chars so prose
#   mentions of either token alone get caught. The 3-char floor prevents
#   collateral damage on ordinary words ('Li' matching 'climate' / 'plus').
#
# name_aware_subn(): word-boundary lookaround scrub — '(?<![A-Za-z]){term}(?![A-Za-z])'
#   so 'Sam' doesn't corrupt 'same'/'Samsung' and 'Liu' doesn't corrupt 'plus'.
#   Case-insensitive (matches title/upper/lower-case variants in prose).
# ---------------------------------------------------------------------------

def expand_name_terms(extra_names) -> list[str]:
    """Decompose roster names into [full name + each part ≥3 chars]. For
    free-form prose where a student signs 'Best, Sarah' but the roster has
    'Sarah Wilson'."""
    out = set()
    for n in (extra_names or ()):
        n = (n or "").strip()
        if not n:
            continue
        out.add(n)
        for part in re.split(r"[^A-Za-z]+", n):
            if len(part) >= 3:
                out.add(part)
    return sorted(out, key=len, reverse=True)


def name_aware_subn(text: str, term: str) -> tuple[str, int]:
    """One name-term scrub with word-boundary lookarounds. Case-insensitive."""
    pat = re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", re.IGNORECASE)
    return pat.subn("[REDACTED]", text)


def name_aware_count(text: str, term: str) -> int:
    """Count word-bounded matches of `term` in `text` (case-insensitive). Same
    regex as name_aware_subn; used by grader_name_leak_check.py where the
    substituted text isn't needed (issue #49 fix — counts only, no scrub)."""
    pat = re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", re.IGNORECASE)
    return len(pat.findall(text))


def build_scrub_terms(stem: str, decoded_blob: str, extra_names: list[str] = ()) -> list[str]:
    """Terms to redact from cell text: emails, /Users paths, filename tokens, and
    operator-supplied names (decomposed into full + parts via expand_name_terms)."""
    terms = set(expand_name_terms(extra_names))  # issue #47 — decompose roster names
    terms.update(EMAIL_RE.findall(decoded_blob))
    terms.update(USERPATH_RE.findall(decoded_blob))
    # Canvas download names are "{lastname}{firstname}_{subid}_{attid}_{title}.html" — the name
    # is the concatenated field before the FIRST underscore. Split it and keep halves that ALSO
    # appear as whole words elsewhere in the file (e.g., the email metadata usually has them).
    name_field = stem.split("_", 1)[0].lower()
    blob_l = decoded_blob.lower()
    if len(name_field) >= 4 and name_field not in {"html", "late", "new", "notebook"}:
        terms.add(name_field)
        for i in range(3, len(name_field) - 2):
            left, right = name_field[:i], name_field[i:]
            if (re.search(rf"\b{re.escape(left)}\b", blob_l)
                    and re.search(rf"\b{re.escape(right)}\b", blob_l)):
                terms.add(left)
                terms.add(right)
    return sorted((t for t in terms if t), key=len, reverse=True)


def scrub(text: str, terms: list[str]) -> tuple[str, int]:
    n = 0
    for t in terms:
        # issue #47 — word-boundary lookarounds so 'Sam' doesn't match 'Samsung'
        text, k = name_aware_subn(text, t)
        n += k
    # belt-and-suspenders: any residual email/userpath
    text, k1 = EMAIL_RE.subn("[REDACTED]", text)
    text, k2 = USERPATH_RE.subn("[REDACTED]", text)
    # credentials students hardcode — never send to the cloud
    text, k3 = SECRET_PREFIX_RE.subn("[REDACTED-SECRET]", text)
    text, k4 = SECRET_ASSIGN_RE.subn(r"\1=[REDACTED-SECRET]", text)
    return text, n + k1 + k2 + k3 + k4


def key_for(filename: str, prefix: str) -> str:
    """Order-free opaque key (hash, not sequence — sequence would leak alphabetical order)."""
    h = hashlib.sha256(filename.encode("utf-8")).hexdigest()[:6].upper()
    return f"{prefix}-{h}"


# Issue #54 sub-D: re-run prefix duality. If a prior deid pass on the same
# submissions_raw/ used a different prefix shape (legacy underscore vs new
# hyphen, or a renamed challenge dir), both prefix families end up in the
# same submissions_deid/ + .keymap.json. Leak check then mis-flags the
# legacy filenames. This helper scans the output dir for files NOT matching
# the current prefix and exits non-zero with a clean cleanup message. Each
# deid adapter imports + calls it before any write.
_STALE_KEY_RE = re.compile(r"^(?P<prefix>.+)-[0-9A-F]{6}\.md$")


def check_stale_prefix_files(outdir, current_prefix: str, *, cleanup: bool = False):
    """Scan `outdir` for `<PREFIX>-<6 HEX>.md` files whose prefix doesn't
    match `current_prefix`. If found:
      - cleanup=False → print stale list + raise SystemExit(3) (caller's
        adapter exits cleanly with code 3 so the chain stops)
      - cleanup=True  → remove the stale files (operator opted in)

    Issue #54 sub-D. Idempotent: no stale files → no-op."""
    from pathlib import Path as _Path
    p = _Path(outdir)
    if not p.is_dir():
        return
    stale: list[_Path] = []
    for f in p.glob("*.md"):
        m = _STALE_KEY_RE.match(f.name)
        if not m:
            continue
        if m.group("prefix") != current_prefix:
            stale.append(f)
    if not stale:
        return
    if cleanup:
        for f in stale:
            f.unlink()
            print(f"  removed stale file from prior prefix: {f.name}")
        return
    print(f"\n🔴 Stale deid output from a prior run with a different prefix.", file=sys.stderr)
    print(f"   {len(stale)} file(s) in {outdir} don't match current prefix "
          f"'{current_prefix}':", file=sys.stderr)
    for f in stale[:5]:
        print(f"     {f.name}", file=sys.stderr)
    if len(stale) > 5:
        print(f"     ... +{len(stale) - 5} more", file=sys.stderr)
    print(f"\n   Re-running deid here would leave BOTH prefix families in the "
          f"keymap, and grader_name_leak_check would mis-flag the legacy "
          f"filenames as roster hits.", file=sys.stderr)
    print(f"\n   Fix:  uv run python lib/tools/grader_deidentify_<adapter>.py "
          f"--challenge-dir <dir> --cleanup-legacy", file=sys.stderr)
    print(f"   (or delete the stale files by hand, then re-run.)\n", file=sys.stderr)
    raise SystemExit(3)


def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(description="FERPA de-identify Databricks HTML submissions.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", dest="challenge_dir", default=None,
                    help="Convention base path (e.g. grading/kc1). Sets --in/--out/--map/--names defaults under it. "
                         "If omitted, --in/--out/--map are required.")
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
                    help="Key prefix (e.g. KC1, MR). Default: uppercased basename of --challenge-dir.")
    ap.add_argument("--cleanup-legacy", action="store_true",
                    help="Issue #54 sub-D: when stale `<OTHER-PREFIX>-HASH.md` files from a prior run "
                         "live in the output dir, remove them instead of refusing to run.")
    args = ap.parse_args()

    # Resolve conventional paths from --challenge-dir if not explicitly set
    if args.challenge_dir:
        cd = resolve_challenge_dir(args.challenge_dir, verb="deidentifying (databricks) to")
        args.indir = args.indir or str(cd / "submissions_raw")
        args.outdir = args.outdir or str(cd / "submissions_deid")
        args.mapfile = args.mapfile or str(cd / ".keymap.json")
        args.namesfile = args.namesfile or str(cd / ".known_names.txt")
        args.prefix = args.prefix or cd.name.upper().replace("_", "-")

    missing = [a for a in ("indir", "outdir", "mapfile", "prefix") if not getattr(args, a)]
    if missing:
        print(f"Missing required arguments: {missing}. Pass --challenge-dir OR all of --in/--out/--map/--prefix.",
              file=sys.stderr)
        return 1

    indir, outdir = Path(args.indir), Path(args.outdir)
    mapfile = Path(args.mapfile)
    outdir.mkdir(parents=True, exist_ok=True)

    # Issue #54 sub-D: refuse to write a second prefix family into this dir.
    check_stale_prefix_files(outdir, args.prefix, cleanup=args.cleanup_legacy)

    extra_names: list[str] = []
    nf = Path(args.namesfile) if args.namesfile else None
    if nf and nf.exists():
        extra_names = [ln.strip() for ln in nf.read_text(encoding="utf-8").splitlines()
                       if ln.strip() and not ln.lstrip().startswith("#")]

    files = sorted(indir.glob("*.html"))
    if not files:
        print(f"No .html files in {indir}/ — drop the downloaded submissions there first.")
        return 1

    keymap: dict[str, str] = {}
    if mapfile.exists():
        keymap = json.loads(mapfile.read_text(encoding="utf-8")).get("map", {})

    ok = fail = 0
    for f in files:
        key = key_for(f.name, args.prefix)
        try:
            raw = f.read_text(encoding="utf-8", errors="replace")
            m = MODEL_RE.search(raw)
            if not m:
                print(f"  {key}: SKIP — no Databricks notebook model found")
                fail += 1
                continue
            model = decode_model(m.group(2))
            if not model:
                print(f"  {key}: SKIP — could not decode notebook model")
                fail += 1
                continue
            # Harvest scrub terms from the FULL decoded model (emails/paths live in user/tags)
            # BEFORE stripping identity, so the student's own email/path is redacted everywhere.
            full_json = json.dumps(model, ensure_ascii=False)
            terms = build_scrub_terms(f.stem, full_json, extra_names)
            cells = extract_cells(strip_identity(model))
            body, redactions = [], 0
            for i, cell in enumerate(cells, 1):
                s_src, n1 = scrub(cell["source"], terms)
                block = [f"### Cell {i}", "```", s_src, "```"]
                if cell["result"]:
                    s_res, n2 = scrub(cell["result"], terms)
                    block += ["", "_Result:_", "```", s_res, "```"]
                    redactions += n2
                redactions += n1
                body.append("\n".join(block))
            out = outdir / f"{key}.md"
            out.write_text(f"# Submission {key}\n\n" + "\n\n".join(body) + "\n", encoding="utf-8")
            keymap[key] = f.name  # the ONLY place the real filename is stored
            ok += 1
            # FERPA: print key + counts only — NEVER the name/email/filename
            print(f"  {key}: {len(cells)} cells, {redactions} redactions -> {out.name}")
        except Exception as e:
            # FERPA: never let a traceback print the filename/path — report by key only
            print(f"  {key}: SKIP — error ({type(e).__name__})")
            fail += 1

    mapfile.write_text(json.dumps(
        {"_warning": "FERPA — do NOT commit, do NOT let an AI read this. Local re-identification only.",
         "map": keymap}, indent=2), encoding="utf-8")
    print(f"\n{ok} de-identified, {fail} skipped. "
          f"Map ({len(keymap)} keys) -> {mapfile} (gitignored, never read by AI).")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

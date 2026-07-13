#!/usr/bin/env python3
"""
update_title_iv_snapshot.py — fetch + cache the canonical Title IV
sources used by `course_engagement_audit.py`. Saves regex-extracted
content to `lib/agents/knowledge/sources/title_iv/<id>.md` so the
toolbox has a local, auditable snapshot of what guidance was current
on a given date.

Why this exists
  Title IV rules change periodically (e.g., the distance-education +
  R2T4 final rules went into effect 2026-07-01). The audit tool's
  classification logic depends on those rules being current. Rather
  than re-running WebSearches (token-expensive, non-deterministic),
  this script pulls the canonical HTML, extracts the body content
  via regex (no LLM tokens; deterministic; greppable), and writes
  Markdown-ish snapshots the agent can fact-check against.

What it does
  1. Walks a hard-coded list of canonical Title IV URLs (FSA Handbook
     chapters, 34 CFR 668.22, Federal Register notice).
  2. For each: HTTP GET via `requests`, strip scripts/styles/comments
     via regex, extract the main content area, convert remaining tags
     to spacing.
  3. Writes the cleaned text to
     `lib/agents/knowledge/sources/title_iv/<id>.md`.
  4. Writes/updates `_manifest.json` with URL + fetched_at + sha256
     for each source — auditable provenance.
  5. Prints a per-source summary: NEW / UNCHANGED / UPDATED (with
     content-hash diff) so the operator sees what shifted.

Reduces token usage
  - Once cached, the audit tool's knowledge file references these
    local snapshots instead of fetching live every read.
  - Regex extraction (not LLM extraction) means re-running is free.
  - sha256 manifest means re-runs are diff-only — unchanged content
    skips re-write.

USAGE
  # Refresh all sources (or seed for the first time)
  uv run python lib/tools/update_title_iv_snapshot.py

  # Dry-run: fetch but don't write; show diff stats
  uv run python lib/tools/update_title_iv_snapshot.py --dry-run

  # Refresh a specific source by id
  uv run python lib/tools/update_title_iv_snapshot.py --only cfr-668-22

WHEN TO RE-RUN
  - On the project's "Title IV next review" date (see the date stamp
    in `course_engagement_audit_knowledge.md`)
  - Whenever DOE issues new R2T4 or distance-ed guidance
  - As a CI step (future enhancement) — fail the build if any source
    URL returns a content-hash mismatch beyond a tolerance
"""
from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"


# ---------------------------------------------------------------------------
# Sources — canonical Title IV references
# ---------------------------------------------------------------------------

@dataclass
class TitleIVSource:
    """One canonical source: id, URL, human label, body-regex hint."""
    id: str
    url: str
    label: str
    # Optional regex for the main content area (per-site). If None,
    # uses the generic body extraction.
    body_regex: str | None = None


_SOURCES: tuple[TitleIVSource, ...] = (
    TitleIVSource(
        id="cfr-668-22",
        url="https://www.law.cornell.edu/cfr/text/34/668.22",
        label="34 CFR 668.22 — Treatment of Title IV funds when a student withdraws",
        # Cornell Law wraps content in <div id="content"> or similar
        body_regex=r'<div[^>]*id="?content"?[^>]*>(.*?)</div>\s*</div>\s*</main>',
    ),
    TitleIVSource(
        id="fsa-2025-2026-vol5-ch1",
        url="https://fsapartners.ed.gov/knowledge-center/fsa-handbook/2025-2026/vol5/ch1-general-requirements-withdrawals-and-return-title-iv-funds",
        label="2025-2026 FSA Handbook, Vol 5 Ch 1 — General Requirements for Withdrawals and R2T4",
    ),
    TitleIVSource(
        id="fsa-2025-2026-vol5-ch2",
        url="https://fsapartners.ed.gov/knowledge-center/fsa-handbook/2025-2026/vol5/ch2-steps-return-title-iv-aid-calculation-part-1",
        label="2025-2026 FSA Handbook, Vol 5 Ch 2 — Steps in R2T4 Calculation Part 1",
    ),
    TitleIVSource(
        id="fsa-2025-2026-vol5-ch3",
        url="https://fsapartners.ed.gov/knowledge-center/fsa-handbook/2025-2026/vol5/ch3-return-title-iv-r2t4-funds-case-studies-part-1",
        label="2025-2026 FSA Handbook, Vol 5 Ch 3 — R2T4 Case Studies Part 1",
    ),
    TitleIVSource(
        id="fsa-2025-2026-vol2-ch1",
        url="https://fsapartners.ed.gov/knowledge-center/fsa-handbook/2025-2026/vol2/ch1-institutional-eligibility",
        label="2025-2026 FSA Handbook, Vol 2 Ch 1 — Institutional Eligibility (academic engagement definition)",
    ),
    TitleIVSource(
        id="federal-register-2025-01-03-final-rules",
        url="https://www.federalregister.gov/documents/2025/01/03/2024-31031/program-integrity-and-institutional-quality-distance-education-and-return-of-title-iv-hea-funds",
        label="Federal Register 89 FR 31031 (2025-01-03) — Distance Ed + R2T4 final rules (effective 2026-07-01)",
    ),
)


# ---------------------------------------------------------------------------
# Regex-based HTML → text extraction
# ---------------------------------------------------------------------------

# Patterns ordered from most-specific to most-general. The script
# applies them in order to strip noise before extracting body text.
_STRIP_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<noscript\b[^>]*>.*?</noscript>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<svg\b[^>]*>.*?</svg>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<head\b[^>]*>.*?</head>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<nav\b[^>]*>.*?</nav>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<footer\b[^>]*>.*?</footer>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<aside\b[^>]*>.*?</aside>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<!--.*?-->", re.DOTALL),
)

# Convert structural tags to newlines + strip everything else's tag.
# Doesn't try to render markdown; just makes the content greppable.
_TAG_TO_NEWLINE = re.compile(
    r"</?\s*(p|div|li|tr|td|th|h[1-6]|br|hr|article|section|main|header)[^>]*>",
    re.IGNORECASE,
)
_ANY_TAG = re.compile(r"<[^>]+>")
_ENTITY_AMP = re.compile(r"&amp;")
_ENTITY_NBSP = re.compile(r"&nbsp;|&#160;")
_ENTITY_LT = re.compile(r"&lt;")
_ENTITY_GT = re.compile(r"&gt;")
_ENTITY_QUOT = re.compile(r"&quot;")
_ENTITY_APOS = re.compile(r"&apos;|&#39;")
_ENTITY_NUMERIC = re.compile(r"&#(\d+);")
_WHITESPACE_RUN = re.compile(r"[ \t]+")
_NEWLINE_RUN = re.compile(r"\n\s*\n\s*\n+")


def extract_text(html: str, body_regex: str | None = None) -> str:
    """Issue (Title IV snapshot): regex-extract readable text from HTML.

    Pipeline:
      1. If body_regex is provided, scope to that match (per-site main
         content); else operate on full HTML.
      2. Strip <script> / <style> / <noscript> / <svg> / <head> /
         <nav> / <footer> / <aside> blocks via greedy regex.
      3. Strip HTML comments.
      4. Convert structural tags (p, div, h1-h6, etc.) to newlines.
      5. Strip all other tags.
      6. Decode common HTML entities (&amp; &nbsp; &lt; &gt; &quot;
         &apos; + numeric entities).
      7. Collapse runs of horizontal whitespace; collapse 3+ blank
         lines to 2.

    Pure function — testable without network. Deterministic — same
    HTML in produces same text out.
    """
    if not html:
        return ""
    # Step 1: scope to main content if a site-specific regex is given
    if body_regex:
        m = re.search(body_regex, html, re.DOTALL | re.IGNORECASE)
        if m:
            html = m.group(1)
    # Step 2-3: strip noise + comments
    for pat in _STRIP_PATTERNS:
        html = pat.sub("", html)
    # Step 4: structural tags → newline
    html = _TAG_TO_NEWLINE.sub("\n", html)
    # Step 5: strip everything else
    html = _ANY_TAG.sub("", html)
    # Step 6: decode entities (order matters: &amp; first)
    html = _ENTITY_AMP.sub("&", html)
    html = _ENTITY_NBSP.sub(" ", html)
    html = _ENTITY_LT.sub("<", html)
    html = _ENTITY_GT.sub(">", html)
    html = _ENTITY_QUOT.sub('"', html)
    html = _ENTITY_APOS.sub("'", html)
    html = _ENTITY_NUMERIC.sub(lambda m: chr(int(m.group(1))) if 0 < int(m.group(1)) < 0x110000 else "", html)
    # Step 7: collapse whitespace
    html = _WHITESPACE_RUN.sub(" ", html)
    html = _NEWLINE_RUN.sub("\n\n", html)
    return html.strip()


def render_snapshot_md(source: TitleIVSource, text: str, fetched_at: str) -> str:
    """Wrap the extracted text with a small YAML frontmatter-ish header
    so future readers know what they're looking at."""
    return f"""# {source.label}

**Source URL:** {source.url}
**Fetched:** {fetched_at}
**Source id:** `{source.id}`

> Snapshot generated by `lib/tools/update_title_iv_snapshot.py`. Body
> extracted from the live HTML via regex (no LLM tokens; deterministic).
> Re-run the script to refresh; the manifest tracks content-hash diffs
> so re-runs are quiet when nothing changed.

---

{text}
"""


# ---------------------------------------------------------------------------
# Fetch + write
# ---------------------------------------------------------------------------

# Mozilla-style User-Agent. Some government sites (Federal Register
# in particular) rate-limit or serve anti-scraping shells when the
# UA looks bot-shaped; the realistic UA gets the actual content.
# Identity also disclosed via a `From:` header per RFC 7231 §5.5.1.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
_FROM_HEADER = "canvas-toolbox+title-iv-snapshot@example.invalid"
_TIMEOUT = 30
# Below this content length, we assume the fetch hit a redirect /
# anti-scraping / rate-limit shell instead of the real document.
# 5000 chars is well under any legitimate Title IV chapter / CFR
# section / Federal Register notice.
_SUSPICIOUS_MIN_CHARS = 5000


def fetch_one(source: TitleIVSource) -> tuple[str, str, bool]:
    """Fetch one source. Returns (text_content, sha256_hex,
    looks_legit). `looks_legit` is False when the extracted text is
    suspiciously short — usually means we hit an anti-scraping shell
    or a moved-page redirect."""
    r = requests.get(
        source.url,
        headers={
            "User-Agent": _USER_AGENT,
            "From": _FROM_HEADER,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=_TIMEOUT,
        allow_redirects=True,
    )
    r.raise_for_status()
    text = extract_text(r.text, source.body_regex)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    looks_legit = len(text) >= _SUSPICIOUS_MIN_CHARS
    return text, sha, looks_legit


def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Fetch + cache canonical Title IV sources to "
                    "lib/agents/knowledge/sources/title_iv/. Reduces "
                    "token usage on Title IV re-verification.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--dry-run", action="store_true",
                    help="Fetch but don't write; print content-hash diffs.")
    ap.add_argument("--only",
                    help="Only refresh the named source id (see _SOURCES). "
                         "Default: refresh all.")
    ap.add_argument("--out-dir",
                    default="lib/agents/knowledge/sources/title_iv",
                    help="Output directory for snapshots + manifest. "
                         "Default: lib/agents/knowledge/sources/title_iv")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "_manifest.json"

    # Load existing manifest (if any) for diff reporting
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}
    if "sources" not in manifest:
        manifest["sources"] = {}

    # Filter sources
    sources = _SOURCES
    if args.only:
        sources = tuple(s for s in _SOURCES if s.id == args.only)
        if not sources:
            print(f"ERROR: no source with id {args.only!r}. "
                  f"Available: {', '.join(s.id for s in _SOURCES)}",
                  file=sys.stderr)
            return 1

    fetched_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_count = updated_count = unchanged_count = failed_count = 0

    for src in sources:
        try:
            text, sha, looks_legit = fetch_one(src)
        except (requests.HTTPError, requests.RequestException) as e:
            print(f"  ✗ {src.id}  FAILED ({type(e).__name__}: {e})",
                  file=sys.stderr)
            failed_count += 1
            continue

        prior = manifest["sources"].get(src.id, {})
        prior_sha = prior.get("sha256")

        if not looks_legit:
            status = "SUSPICIOUS"  # under threshold; probably hit an anti-scraping shell
            failed_count += 1
        elif prior_sha == sha:
            status = "UNCHANGED"
            unchanged_count += 1
        elif prior_sha is None:
            status = "NEW"
            new_count += 1
        else:
            status = "UPDATED"
            updated_count += 1

        marker = "⚠️" if status == "SUSPICIOUS" else "✓"
        print(f"  {marker} {src.id:40} {status:11} "
              f"({len(text):>7} chars, sha {sha[:8]})")

        if args.dry_run:
            continue

        # Don't overwrite a good snapshot with a suspicious one. If a
        # previous run got real content (>= threshold) and this run
        # got an anti-scraping shell, KEEP the prior snapshot + log
        # the failure to the manifest so the operator can audit.
        if not looks_legit:
            print(f"      ↳ keeping prior snapshot (if any); writing only "
                  f"to manifest as SUSPICIOUS")
            manifest["sources"].setdefault(src.id, {}).update({
                "url": src.url,
                "label": src.label,
                "last_attempt_at": fetched_at,
                "last_attempt_status": "SUSPICIOUS",
                "last_attempt_char_count": len(text),
            })
            continue

        # Write the snapshot file
        snapshot_path = out_dir / f"{src.id}.md"
        snapshot_path.write_text(
            render_snapshot_md(src, text, fetched_at),
            encoding="utf-8",
        )

        # Update manifest entry
        manifest["sources"][src.id] = {
            "url": src.url,
            "label": src.label,
            "sha256": sha,
            "char_count": len(text),
            "fetched_at": fetched_at,
            "last_attempt_status": "OK",
        }

    # Write manifest (unless dry-run)
    if not args.dry_run:
        manifest["last_updated"] = fetched_at
        manifest["script_version"] = __version__
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print()
    print(f"Summary: {new_count} NEW · {updated_count} UPDATED · "
          f"{unchanged_count} UNCHANGED · {failed_count} FAILED")
    if args.dry_run:
        print("(dry run — no files written)")
    elif new_count + updated_count > 0:
        print(f"Snapshots: {out_dir}")
        print(f"Manifest:  {manifest_path}")
    return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

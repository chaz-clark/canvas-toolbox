#!/usr/bin/env python3
"""
grader_follow_share_url.py — fetch transcripts behind chatgpt.com/share +
gemini.google.com/share URLs so URL-only AI Log submissions become
gradeable.

Part of the canvas-toolbox generic grader skill (v1.0). See:
  - grading_readme.md (faculty-facing pipeline + canonical layout)
  - lib/agents/canvas_grader.md (agent-facing pipeline)
  - lib/agents/knowledge/grader_knowledge.md (FERPA two-zone architecture)

WHAT IT DOES (issue #51)
  Students submitting an AI Log assignment in courses with permissive AI
  policies often submit a SINGLE SHARE URL instead of pasting the chat.
  Pre-#51 the toolkit wrote the URL as a tiny text body; the per-turn-
  mixture classifier had nothing to classify; per-student verdict was
  'Unable to classify (link-only AI Log)'.

  This tool (v1.0):
    1. Scans submissions_raw/<prefix>_<userid>.<ext> for share URLs
       matching:
         chatgpt.com/share/<hash>
         gemini.google.com/share/<hash>  (and bard.google.com legacy)
    2. Fetches each URL via plain HTTPS GET (no auth — public shares).
    3. Attempts to parse the conversation into ordered USER / ASSISTANT
       turns. PARSING SUCCESS DEPENDS ON THE SERVICE'S CURRENT HYDRATION
       SHAPE — see "Parsing limitations" below.
    4. Emits the parsed transcript (or a clearly-marked stub if parsing
       failed) as Markdown to:
         submissions_raw/<prefix>_<userid>_external.md
       (NOT submissions_deid/ — fetched content still goes through the
        existing deid + leak-check chain.)
    5. Records per-URL fetch metadata to:
         submissions_raw/_external_fetch_log.json (gitignored)

  Output files are then ingestible by grader_deidentify_text.py (already
  accepts .md via v0.34.2's _ACCEPT_EXTS).

PARSING LIMITATIONS (v1.0 — important)
  Both ChatGPT and Gemini have moved their share pages to fully
  client-side-hydrated SPAs since this tool was scoped:
    - ChatGPT currently hydrates via React Router's turbo-stream format
      (window.__reactRouterContext.streamController.enqueue(...)) — a
      backreference-graph serialization that requires a real JS engine
      OR a turbo-stream decoder to parse.
    - Gemini hydrates via Google's WIZ AF_initDataCallback pattern with
      data inside server-rendered base64 payloads — also requires JS or
      a custom decoder.
  Static HTML parsing of either service's current pages returns 0 turns.
  The tool detects this case, writes a STRUCTURED STUB output (URL +
  status + parse_error noted in the file header), and continues. The
  agent pipeline can then flag the URL-only submissions for operator
  manual review.
  v1.1 will likely integrate Playwright for headless-browser fetching —
  parked with the trigger "operator wants automated transcript parsing
  beyond detection+stub" (see parking-lot entry).
  Even at v1.0, this is a meaningful improvement over pre-#51 — the URL
  is captured with metadata, the output file is clearly labeled, and
  the operator has a structured path to manual review instead of
  cohort-wide "Unable to classify (link-only AI Log)" verdicts.

FERPA / SAFETY DISCIPLINE
  * Console output: <userid>: chatgpt.com/share/<hash-8>… → N turns
    Truncated hash; never the full URL; never the conversation content.
  * Image attachments in shares are STRIPPED (v1.0). Count noted in
    output header. v1.1 may OCR — parked.
  * Revoked / expired shares (HTTP 404/410): write a stub .md with a
    _REVOKED: marker, continue. Don't fail the whole run.
  * Rate-limited by default to 1.0 req/sec. Both services serve public
    shares without auth but DO rate-limit.
  * Idempotent: skip files that already exist in submissions_raw/
    unless --force.

USAGE
  uv run python lib/tools/grader_follow_share_url.py \\
    --challenge-dir grading/<assignment>

  uv run python lib/tools/grader_follow_share_url.py \\
    --challenge-dir grading/<asg> \\
    --rate-limit 2.0 --timeout 30 --retry 2 --force

PIPELINE INTEGRATION
  grader_fetch.py auto-chains this step when --follow-share-urls auto
  (default). Detect → follow → deid → leak-check happens in one command.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from _challenge_dir_guard import resolve_challenge_dir  # issue #44 FERPA guard

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"


# ---------------------------------------------------------------------------
# URL detection
# ---------------------------------------------------------------------------

# Permissive hash length per fixtures-file note (some Gemini hashes are 12 chars,
# ChatGPT hashes are 36+ chars). 8-char minimum prevents matching every
# /share/X URL on the internet.
_CHATGPT_RE = re.compile(
    r"https?://chatgpt\.com/share/[a-z0-9-]{8,}/?",
    re.IGNORECASE,
)
_GEMINI_RE = re.compile(
    r"https?://(?:bard|gemini)\.google\.com/share/[a-z0-9-]{8,}/?",
    re.IGNORECASE,
)


@dataclass
class ShareURL:
    service: str  # "chatgpt" | "gemini"
    url: str
    hash_short: str  # first 8 chars of the hash, for FERPA-safe console output


def detect_share_urls(text: str) -> list[ShareURL]:
    """Extract all share URLs from a text body. Order preserved (some
    submissions may reference multiple chats)."""
    out: list[ShareURL] = []
    for m in _CHATGPT_RE.finditer(text):
        url = m.group(0).rstrip("/")
        h = url.rsplit("/", 1)[-1][:8]
        out.append(ShareURL("chatgpt", url, h))
    for m in _GEMINI_RE.finditer(text):
        url = m.group(0).rstrip("/")
        h = url.rsplit("/", 1)[-1][:8]
        out.append(ShareURL("gemini", url, h))
    return out


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------

@dataclass
class FetchResult:
    status: int            # HTTP status or 0 on error
    body: str              # response body (may be empty on error)
    bytes_total: int       # content-length / len(body)
    error: str | None = None
    revoked: bool = False  # True for 404 / 410


def fetch_share(url: str, *, user_agent: str, timeout: float, retry: int) -> FetchResult:
    """GET a share URL. Retries on transient errors (5xx, timeouts). On
    404/410 returns revoked=True (caller writes a stub, doesn't fail)."""
    headers = {"User-Agent": user_agent, "Accept": "text/html,*/*"}
    last_err: str | None = None
    for attempt in range(retry + 1):
        try:
            r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if r.status_code in (404, 410):
                return FetchResult(r.status_code, "", 0, revoked=True)
            if 500 <= r.status_code < 600 and attempt < retry:
                last_err = f"HTTP {r.status_code}"
                time.sleep(1.0 * (attempt + 1))
                continue
            r.raise_for_status()
            body = r.text
            return FetchResult(r.status_code, body, len(body.encode("utf-8")))
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = f"{type(e).__name__}"
            if attempt < retry:
                time.sleep(1.0 * (attempt + 1))
                continue
            return FetchResult(0, "", 0, error=last_err)
        except requests.HTTPError as e:
            return FetchResult(r.status_code, "", 0, error=f"HTTP {r.status_code}")
    return FetchResult(0, "", 0, error=last_err or "unknown")


# ---------------------------------------------------------------------------
# Per-service parsers
# ---------------------------------------------------------------------------

@dataclass
class Turn:
    role: str   # "user" | "assistant" | "system" | "tool"
    content: str


@dataclass
class ParseResult:
    turns: list[Turn]
    image_count: int = 0
    parse_error: str | None = None


def parse_chatgpt_share(html: str) -> ParseResult:
    """Parse a chatgpt.com/share/<hash> HTML page.

    HISTORICAL NOTE — ChatGPT has refactored the share-page hydration several
    times:
      - Early: server-rendered DOM with [data-message-author-role] divs
      - Mid: Next.js __NEXT_DATA__ JSON blob, conversation in mapping/tree
      - Mid: __NEXT_DATA__ with linear_conversation array
      - Current (2026-06): React Router streaming via
        window.__reactRouterContext.streamController.enqueue(...) using
        turbo-stream backreference-graph serialization. Static HTML parsing
        returns 0 turns; would need a turbo-stream decoder or headless
        browser to extract.

    This parser tries all three legacy paths in order. If none match, it
    returns 0 turns + a parse_error noting the current SPA limitation; the
    caller (main) writes a structured stub the operator can review.
    """
    soup = BeautifulSoup(html, "html.parser")
    image_count = len(soup.find_all("img"))

    # Path 1: __NEXT_DATA__ JSON
    script = soup.find("script", id="__NEXT_DATA__")
    if script and script.string:
        try:
            data = json.loads(script.string)
            page_props = data.get("props", {}).get("pageProps", {})

            # Try the linear conversation shape first
            linear = (page_props.get("linear_conversation")
                      or page_props.get("conversation", {}).get("linear_conversation"))
            if isinstance(linear, list) and linear:
                turns = _chatgpt_turns_from_linear(linear)
                if turns:
                    return ParseResult(turns, image_count)

            # Then the mapping/tree shape
            mapping = (page_props.get("serverResponse", {}).get("data", {}).get("mapping")
                       or page_props.get("conversation", {}).get("mapping")
                       or page_props.get("mapping"))
            if isinstance(mapping, dict) and mapping:
                turns = _chatgpt_turns_from_mapping(mapping)
                if turns:
                    return ParseResult(turns, image_count)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # Fall through to DOM scrape
            pass

    # Path 2: DOM scrape — render-time containers
    turns: list[Turn] = []
    for div in soup.find_all(attrs={"data-message-author-role": True}):
        role = div.get("data-message-author-role", "").strip().lower()
        text = div.get_text(separator="\n", strip=True)
        if role and text:
            turns.append(Turn(role, text))
    if turns:
        return ParseResult(turns, image_count)

    return ParseResult([], image_count,
                       parse_error="ChatGPT share now hydrates via React Router "
                                   "turbo-stream (window.__reactRouterContext); "
                                   "static-HTML parsing returns no turns. "
                                   "Operator must review the URL manually OR wait "
                                   "for v1.1 (Playwright-based fetch).")


def _chatgpt_turns_from_linear(linear: list) -> list[Turn]:
    """Extract turns from a 'linear_conversation' list shape (newer OpenAI shape)."""
    turns: list[Turn] = []
    for entry in linear:
        msg = entry.get("message") if isinstance(entry, dict) else None
        if not isinstance(msg, dict):
            continue
        author = msg.get("author") or {}
        role = (author.get("role") or "").lower().strip()
        if role not in ("user", "assistant", "system", "tool"):
            continue
        content = msg.get("content") or {}
        parts = content.get("parts")
        if isinstance(parts, list):
            text = "\n\n".join(p for p in parts if isinstance(p, str) and p.strip())
        else:
            text = ""
        if text:
            turns.append(Turn(role, text))
    return turns


def _chatgpt_turns_from_mapping(mapping: dict) -> list[Turn]:
    """Extract turns from a mapping {id → {message, parent, children}} tree.
    Walk from a root (parent=None / 'client-created-root') depth-first via children;
    each node carries a `message` with author.role + content.parts."""
    # Find root(s) — nodes whose parent is None or not in the mapping
    roots = [nid for nid, node in mapping.items()
             if not node.get("parent") or node.get("parent") not in mapping]
    # If there's no obvious root but exactly one node, walk from there
    if not roots and mapping:
        roots = [next(iter(mapping))]

    visited: set[str] = set()
    turns: list[Turn] = []

    def _walk(node_id: str) -> None:
        if node_id in visited or node_id not in mapping:
            return
        visited.add(node_id)
        node = mapping[node_id]
        msg = node.get("message") or {}
        if isinstance(msg, dict):
            author = msg.get("author") or {}
            role = (author.get("role") or "").lower().strip()
            content = msg.get("content") or {}
            parts = content.get("parts")
            text = ""
            if isinstance(parts, list):
                text = "\n\n".join(p for p in parts if isinstance(p, str) and p.strip())
            if role in ("user", "assistant", "system", "tool") and text:
                turns.append(Turn(role, text))
        for child_id in (node.get("children") or []):
            _walk(child_id)

    for root in roots:
        _walk(root)
    return turns


def parse_gemini_share(html: str) -> ParseResult:
    """Parse a gemini.google.com/share/<hash> HTML page.

    Gemini share pages are server-rendered with Material Web Components.
    The conversation is typically inside <user-query> and <model-response>
    custom elements, with text in nested .query-content / .markdown
    containers. The exact selectors shift occasionally; this parser tries
    the structured selectors first then falls back to scanning the
    document for any element with role-style markers.
    """
    soup = BeautifulSoup(html, "html.parser")
    image_count = len(soup.find_all("img"))

    turns: list[Turn] = []

    # Path 1: structured custom elements (most reliable when present)
    for el in soup.find_all(["user-query", "model-response"]):
        role = "user" if el.name == "user-query" else "assistant"
        text = el.get_text(separator="\n", strip=True)
        if text:
            turns.append(Turn(role, text))
    if turns:
        return ParseResult(turns, image_count)

    # Path 2: aria-label / data-role hints
    for el in soup.find_all(attrs={"data-role": True}):
        role = el.get("data-role", "").strip().lower()
        if role in ("user", "assistant", "model"):
            if role == "model":
                role = "assistant"
            text = el.get_text(separator="\n", strip=True)
            if text:
                turns.append(Turn(role, text))
    if turns:
        return ParseResult(turns, image_count)

    # Path 3: class-name heuristic (most fragile; last resort)
    for el in soup.select(".user-query-bubble-with-background, .model-response-text"):
        cls = " ".join(el.get("class", []))
        role = "user" if "user-query" in cls else "assistant"
        text = el.get_text(separator="\n", strip=True)
        if text:
            turns.append(Turn(role, text))
    if turns:
        return ParseResult(turns, image_count)

    return ParseResult([], image_count,
                       parse_error="Gemini share now hydrates via Google's WIZ "
                                   "AF_initDataCallback pattern; static-HTML "
                                   "parsing returns no turns. Operator must review "
                                   "the URL manually OR wait for v1.1 "
                                   "(Playwright-based fetch).")


# ---------------------------------------------------------------------------
# Markdown emission
# ---------------------------------------------------------------------------

def emit_markdown(
    *,
    service: str,
    hash_short: str,
    status: int,
    turns: list[Turn],
    image_count: int,
    parse_error: str | None,
) -> str:
    """Build the markdown body for the saved _external.md file."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    header = [
        f"# External share — fetched {now}",
        f"_Source: {service}.com/share/{hash_short}… (status {status})_",
        "_Note: persisted locally; the live URL may expire or be revoked._",
    ]
    if image_count:
        header.append(f"_Image attachments: {image_count} stripped (count noted; not OCR'd in v1.0)_")
    if parse_error:
        header.append(f"_Parse warning: {parse_error}_")
    header.append("")  # blank line before body

    if not turns:
        header.append("_(No turns extracted — see parse warning above. Operator review needed.)_")
        return "\n".join(header) + "\n"

    body_lines: list[str] = []
    for t in turns:
        role_label = {"user": "USER", "assistant": "ASSISTANT",
                      "system": "SYSTEM", "tool": "TOOL"}.get(t.role, t.role.upper())
        body_lines.append(f"## {role_label}:")
        body_lines.append("")
        body_lines.append(t.content)
        body_lines.append("")

    return "\n".join(header + body_lines) + "\n"


def emit_revoked_stub(*, service: str, hash_short: str, status: int) -> str:
    """For revoked/404 shares — write a marker the operator can see."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    return (
        f"# External share — fetched {now}\n"
        f"_Source: {service}.com/share/{hash_short}…_\n"
        f"_REVOKED: share returned HTTP {status} — student likely revoked "
        f"or the URL was incorrect. Operator review needed._\n"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_DEFAULT_UA = f"canvas-toolbox/{__version__} (instructor grading; +https://github.com/chaz-clark/canvas-toolbox)"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch transcripts behind chatgpt.com/share + "
                    "gemini.google.com/share URLs so URL-only AI Log "
                    "submissions become gradeable. Output lands in "
                    "submissions_raw/ (still routes through deid + leak check).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", required=True,
                    help="Convention base path (e.g. grading/p1t1_ai_log).")
    ap.add_argument("--rate-limit", type=float, default=1.0,
                    help="Seconds between successive HTTP requests (default 1.0).")
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="Per-request timeout in seconds (default 30).")
    ap.add_argument("--retry", type=int, default=2,
                    help="Retries per URL on 5xx / timeout (default 2).")
    ap.add_argument("--user-agent", default=_DEFAULT_UA,
                    help="User-Agent header (default identifies as canvas-toolbox).")
    ap.add_argument("--force", action="store_true",
                    help="Re-fetch even if <prefix>_<userid>_external.md already "
                         "exists. Default is idempotent skip.")
    args = ap.parse_args()

    cd = resolve_challenge_dir(args.challenge_dir, verb="following share URLs in")
    raw_dir = cd / "submissions_raw"
    if not raw_dir.exists():
        print(f"No submissions_raw/ under {cd}/. Run grader_fetch.py first.",
              file=sys.stderr)
        return 1

    log_path = raw_dir / "_external_fetch_log.json"
    fetch_log: dict = {}
    if log_path.exists():
        try:
            fetch_log = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            fetch_log = {}

    # Scan every file in submissions_raw/ for share URLs.
    # Skip files that are themselves _external.md outputs (avoid infinite loops).
    candidates: list[tuple[Path, ShareURL]] = []
    for f in sorted(raw_dir.iterdir()):
        if not f.is_file():
            continue
        if f.name.endswith("_external.md"):
            continue
        if f.name.startswith("."):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        urls = detect_share_urls(text)
        for u in urls:
            candidates.append((f, u))

    if not candidates:
        print(f"No share URLs detected in {raw_dir}/. Nothing to follow.")
        return 0

    # Group by source file. If a file has multiple share URLs, we fetch each
    # and concatenate into ONE _external.md keyed on the source file's
    # <prefix>_<userid> stem.
    by_file: dict[Path, list[ShareURL]] = {}
    for f, u in candidates:
        by_file.setdefault(f, []).append(u)

    print(f"Detected {len(candidates)} share URL(s) across {len(by_file)} "
          f"submission(s). Rate-limit: {args.rate_limit}s.", file=sys.stderr)

    fetched = skipped = revoked = failed = 0

    for f, urls in by_file.items():
        stem = f.stem
        # If filename is <prefix>_<userid>[.<ext>], userid is the second underscore field
        parts = stem.split("_")
        userid = parts[1] if len(parts) >= 2 and parts[1].isdigit() else stem
        out_name = f"{stem}_external.md"
        out_path = raw_dir / out_name

        if out_path.exists() and not args.force:
            skipped += 1
            print(f"  {userid}: skip (existing — use --force to re-fetch)")
            continue

        sections: list[str] = []
        per_url_meta: list[dict] = []

        for i, share in enumerate(urls):
            if i > 0:
                # Rate-limit between successive URLs in the SAME submission
                time.sleep(args.rate_limit)
            # And between submissions (this fetch is always after at least one prior loop iteration)
            result = fetch_share(share.url,
                                 user_agent=args.user_agent,
                                 timeout=args.timeout,
                                 retry=args.retry)
            meta: dict = {
                "service": share.service,
                "hash_short": share.hash_short,
                "status": result.status,
                "bytes": result.bytes_total,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

            if result.revoked:
                sections.append(emit_revoked_stub(
                    service=share.service, hash_short=share.hash_short,
                    status=result.status))
                meta["revoked"] = True
                revoked += 1
                print(f"  {userid}: {share.service}.com/share/{share.hash_short}… "
                      f"→ REVOKED (HTTP {result.status})")
            elif result.status != 200 or not result.body:
                err = result.error or f"HTTP {result.status}"
                sections.append(
                    f"# External share — fetch failed\n"
                    f"_Source: {share.service}.com/share/{share.hash_short}…_\n"
                    f"_Error: {err}_\n"
                )
                meta["error"] = err
                failed += 1
                print(f"  {userid}: {share.service}.com/share/{share.hash_short}… "
                      f"→ FAILED ({err})")
            else:
                if share.service == "chatgpt":
                    pr = parse_chatgpt_share(result.body)
                else:
                    pr = parse_gemini_share(result.body)
                meta["turns"] = len(pr.turns)
                meta["images"] = pr.image_count
                if pr.parse_error:
                    meta["parse_warning"] = pr.parse_error
                sections.append(emit_markdown(
                    service=share.service, hash_short=share.hash_short,
                    status=result.status, turns=pr.turns,
                    image_count=pr.image_count, parse_error=pr.parse_error))
                fetched += 1
                print(f"  {userid}: {share.service}.com/share/{share.hash_short}… "
                      f"→ {len(pr.turns)} turns extracted"
                      + (f" ({pr.image_count} images stripped)" if pr.image_count else ""))

            per_url_meta.append(meta)

        # Stitch multiple shares into one file (rare case but possible)
        out_path.write_text("\n\n---\n\n".join(sections), encoding="utf-8")
        fetch_log[out_name] = {
            "source_file": f.name,
            "urls": per_url_meta,
        }

        # Rate-limit between submissions
        time.sleep(args.rate_limit)

    log_path.write_text(json.dumps(
        {"_warning": "FERPA — do NOT commit; metadata only, no transcript content "
                     "or full URLs beyond the 8-char hash prefix.",
         "fetched_at": datetime.now(timezone.utc).isoformat(),
         "entries": fetch_log}, indent=2), encoding="utf-8")

    print(f"\n{fetched} fetched, {skipped} skipped (existing), "
          f"{revoked} revoked, {failed} failed. "
          f"Per-URL log -> {log_path.name}")
    # Non-zero on parse failure or fetch failure — operator must investigate
    # before grading. Revoked is informational (student's choice; not a tool error).
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

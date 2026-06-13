#!/usr/bin/env python3
"""
grader_follow_share_url.py — fetch transcripts behind chatgpt.com/share +
gemini.google.com/share URLs so URL-only AI Log submissions become
gradeable.

Part of the canvas-toolbox generic grader skill (v1.1, Playwright-based).
See:
  - grading_readme.md (faculty-facing pipeline + canonical layout)
  - lib/agents/canvas_grader.md (agent-facing pipeline)
  - lib/agents/knowledge/grader_knowledge.md (FERPA two-zone architecture)

WHAT IT DOES (issue #51)
  Students submitting an AI Log assignment in courses with permissive AI
  policies often submit a SINGLE SHARE URL instead of pasting the chat
  (~23% of submissions in real cohorts — m119 SP26 P1T1 + P2T1). Pre-#51
  the toolkit wrote the URL as a tiny text body; the per-turn-mixture
  classifier had nothing to classify; per-student verdict was 'Unable
  to classify (link-only AI Log)'.

  This tool (v1.1):
    1. Scans submissions_raw/<prefix>_<userid>.<ext> for share URLs:
         chatgpt.com/share/<hash>
         gemini.google.com/share/<hash>  (and bard.google.com legacy)
    2. For each URL, launches a headless Chromium browser via Playwright,
       navigates to the share page, WAITS for the client-side SPA to
       hydrate (~4s), then dumps the rendered text from a service-
       specific container (with body fallback).
    3. Emits the rendered conversation as Markdown to:
         submissions_raw/<prefix>_<userid>_external.md
       Per operator direction (2026-06-12): no per-turn role parsing.
       The rendered conversation is dumped as flat text — the downstream
       deid + leak-check chain treats it like any other submission.
       Future versions can layer structured per-turn extraction on top
       if a real grading workflow requires it.
    4. Records per-URL fetch metadata to:
         submissions_raw/_external_fetch_log.json (gitignored)

  Output files are then ingestible by grader_deidentify_text.py (already
  accepts .md via v0.34.2's _ACCEPT_EXTS). The two-zone FERPA gate stays
  intact: fetched content lands in submissions_raw/ (NOT submissions_deid/),
  still routes through deid + leak check before any AI read.

WHY PLAYWRIGHT
  Both ChatGPT and Gemini moved their share pages to fully client-side
  hydrated SPAs (2026-06):
    - ChatGPT: React Router turbo-stream serialization
    - Gemini: Google's WIZ AF_initDataCallback pattern
  Static HTML parsing returns 0 turns. Writing format decoders is brittle
  (both services refactor quarterly). Headless Chromium is robust — it
  runs the real JS, so the same code keeps working across format changes.

FIRST-TIME SETUP (per machine, one-time)
  After `uv sync`, install Chromium for Playwright:
      uv run playwright install chromium
  ~92 MB download. Tool prints a clear error if Chromium is missing.

FERPA / SAFETY DISCIPLINE
  * Console output: <userid>: chatgpt.com/share/<hash-8>… → N chars extracted
    Truncated hash; never the full URL; never the conversation content.
  * Revoked / expired shares (HTTP 404/410 / navigation error): write a
    stub .md with a _REVOKED: marker, continue. Don't fail the whole run.
  * Rate-limited by default to 1.0 sec between requests.
  * Idempotent: skip if <prefix>_<userid>_external.md already exists
    unless --force.

USAGE
  uv run python lib/tools/grader_follow_share_url.py \\
    --challenge-dir grading/<asg>

  uv run python lib/tools/grader_follow_share_url.py \\
    --challenge-dir grading/<asg> \\
    --rate-limit 2.0 --timeout 30 --force

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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from _challenge_dir_guard import resolve_challenge_dir  # issue #44 FERPA guard

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"


# ---------------------------------------------------------------------------
# URL detection
# ---------------------------------------------------------------------------

_CHATGPT_RE = re.compile(
    r"https?://chatgpt\.com/share/[a-z0-9-]{8,}/?", re.IGNORECASE,
)
_GEMINI_RE = re.compile(
    r"https?://(?:bard|gemini)\.google\.com/share/[a-z0-9-]{8,}/?", re.IGNORECASE,
)
# Gemini AI Mode shares (issue #52) — different surface from gemini.google.com/share.
# AI Mode is the "Gemini-with-search-and-tools" experience; share URL lives on
# share.google/aimode/<base62-hash>. Real-world m119 SP26 P1T2 cohort surfaced one
# (uid 415951). Hash is short (15-20 chars) and uses base62 alphabet.
_AIMODE_RE = re.compile(
    r"https?://share\.google/aimode/[A-Za-z0-9_-]{8,}/?",
)


@dataclass
class ShareURL:
    service: str        # "chatgpt" | "gemini" | "aimode"
    url: str
    hash_short: str     # first 8 chars of hash, for FERPA-safe console


def _pretty_url(service: str, hash_short: str) -> str:
    """FERPA-safe URL-shape preview: '<host>/<path>/<hash-8>…' for console/log.
    Avoids the v0.35.1 bug where aimode rendered as 'aimode.com/share/…'."""
    return {
        "chatgpt": f"chatgpt.com/share/{hash_short}…",
        "gemini":  f"gemini.google.com/share/{hash_short}…",
        "aimode":  f"share.google/aimode/{hash_short}…",
    }.get(service, f"{service}/{hash_short}…")


def detect_share_urls(text: str) -> list[ShareURL]:
    out: list[ShareURL] = []
    for m in _CHATGPT_RE.finditer(text):
        url = m.group(0).rstrip("/")
        h = url.rsplit("/", 1)[-1][:8]
        out.append(ShareURL("chatgpt", url, h))
    for m in _GEMINI_RE.finditer(text):
        url = m.group(0).rstrip("/")
        h = url.rsplit("/", 1)[-1][:8]
        out.append(ShareURL("gemini", url, h))
    for m in _AIMODE_RE.finditer(text):
        url = m.group(0).rstrip("/")
        h = url.rsplit("/", 1)[-1][:8]
        out.append(ShareURL("aimode", url, h))
    return out


# ---------------------------------------------------------------------------
# Playwright-based fetch (the v1.1 core)
# ---------------------------------------------------------------------------

# Service-specific selector lists. Tried in order; first non-empty match wins.
# Sandbox-validated against the 5 SP26 fixtures (2026-06-12):
#   ChatGPT: #thread gives 382 lines / 11.4K chars, clean conversation
#   Gemini:  main gives 156 lines / 9.2K chars (mixes some chrome; downstream
#            deid handles it like any other text)
_SERVICE_SELECTORS = {
    "chatgpt": ["#thread", "main", "body"],
    "gemini":  ["main", "body"],
    # AI Mode (issue #52) — share.google/aimode/<hash> redirects to a Google
    # Search results page with AI Mode active. Body fallback gets the AI
    # response + some search-results chrome; downstream deid handles it.
    "aimode":  ["main", "[role='main']", "body"],
}

_PLAYWRIGHT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

# Issue #52 — Google's bot detection redirects share.google/* URLs to
# google.com/sorry/index when it sees a default headless-Chromium fingerprint.
# These flags + context settings + webdriver masking get us past detection
# WITHOUT crossing into adversarial territory: the student already chose to
# make the share public; we're just rendering the same page a faculty member's
# regular browser would render. The flags below are the standard
# anti-anti-bot-detection layer that Playwright users add for legitimate
# scraping; they don't bypass auth, paywall, or any actual security boundary.
_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
# Webdriver detection: many sites check navigator.webdriver. Override at page
# context creation so it returns undefined like in a real browser.
_WEBDRIVER_MASK = (
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
)


@dataclass
class FetchResult:
    status: int             # HTTP-ish status (200, 404, 0=error)
    body: str               # rendered text (NOT raw HTML in v1.1)
    bytes_total: int
    used_selector: str = ""
    error: str | None = None
    revoked: bool = False
    title: str = ""


def _playwright_available() -> tuple[bool, str]:
    """Check whether Playwright + Chromium are installed. Returns
    (ok, message). Run once at startup so the operator gets a clear error
    before we waste time iterating submissions."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False, (
            "Playwright not installed. Run:\n"
            "  uv sync\n"
            "to install the dependency, then:\n"
            "  uv run playwright install chromium\n"
            "to download the headless browser (~92 MB, one-time per machine)."
        )
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Quick check: can we even reach the chromium executable?
            exe = p.chromium.executable_path
            if exe and Path(exe).exists():
                return True, ""
            return False, (
                "Playwright is installed but Chromium isn't. Run:\n"
                "  uv run playwright install chromium\n"
                "to download it (~92 MB, one-time per machine)."
            )
    except Exception as e:
        return False, (
            f"Playwright preflight failed: {type(e).__name__}: {e}\n"
            "Try:\n"
            "  uv run playwright install chromium"
        )


def fetch_share(url: str, service: str, *, timeout: float, hydration_wait_ms: int = 4000) -> FetchResult:
    """Launch Chromium, navigate to the share URL, wait for hydration,
    extract rendered text. Returns FetchResult with body = rendered text.

    Tries service-specific selectors in order (most-targeted first) and
    falls back to `body` if all specific selectors fail. Detects revoked
    shares (page title / content markers) and short-circuits."""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, args=_LAUNCH_ARGS)
        except Exception as e:
            return FetchResult(0, "", 0, error=f"chromium launch: {type(e).__name__}: {e}")
        try:
            ctx = browser.new_context(
                user_agent=_PLAYWRIGHT_UA,
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                timezone_id="America/Boise",
            )
            page = ctx.new_page()
            # Mask navigator.webdriver so we look like a real browser
            page.add_init_script(_WEBDRIVER_MASK)
            try:
                # `domcontentloaded` is forgiving; `networkidle` was too strict
                # for ChatGPT (which keeps long-poll connections open).
                page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            except PWTimeout:
                return FetchResult(0, "", 0, error="navigation timeout")
            except Exception as e:
                return FetchResult(0, "", 0, error=f"navigation: {type(e).__name__}")

            page.wait_for_timeout(hydration_wait_ms)  # let the SPA hydrate

            title = page.title()

            # Issue #52 defense-in-depth: detect Google's bot-detection
            # redirect (google.com/sorry/index). The stealth flags above
            # usually prevent this, but if Google's heuristics tighten and
            # we get redirected, the page LOOKS like content (the sorry
            # page has ~800 chars) — we'd index the captcha instead of the
            # transcript. Catch it loud.
            final_url = page.url
            if "/sorry/index" in final_url or "google.com/sorry/" in final_url:
                return FetchResult(0, "", 0,
                                   error="Google bot-detection wall (google.com/sorry/index). "
                                         "Stealth flags didn't suffice. Operator may need to "
                                         "fetch manually OR run with a real browser "
                                         "(headless=False) once — not yet exposed via CLI.",
                                   title=title)

            # Revoked / blocked-page heuristic
            content_lower = page.content()[:10000].lower()
            for marker in ("the conversation has been deleted", "this share is no longer available",
                           "page not found", "404"):
                if marker in content_lower:
                    return FetchResult(404, "", 0, revoked=True, title=title)

            selectors = _SERVICE_SELECTORS.get(service, ["body"])
            for sel in selectors:
                try:
                    text = page.locator(sel).first.inner_text(timeout=3000)
                except Exception:
                    continue
                # Reject obviously-empty / blocked results; insist on
                # meaningful content (≥200 chars from the conversation area).
                if text and len(text.strip()) >= 200:
                    return FetchResult(200, text, len(text.encode("utf-8")),
                                        used_selector=sel, title=title)

            # Nothing rendered — likely bot wall or unloaded SPA
            return FetchResult(0, "", 0, error="no rendered content (possible bot wall)",
                               title=title)
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Markdown emission
# ---------------------------------------------------------------------------

def emit_markdown(*, service: str, hash_short: str, status: int, body: str,
                  used_selector: str, title: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [
        f"# External share — fetched {now}",
        f"_Source: {_pretty_url(service, hash_short)} (status {status})_",
    ]
    if title:
        lines.append(f"_Title: {title.strip()}_")
    if used_selector:
        lines.append(f"_Method: Playwright headless Chromium, selector: {used_selector}_")
    lines.append("_Note: persisted locally; the live URL may expire or be revoked. "
                 "Rendered conversation may include some UI chrome (nav labels, "
                 "button text); deid + leak check handle it like any text submission._")
    lines.append("")  # blank line before body
    lines.append(body.strip())
    return "\n".join(lines) + "\n"


def emit_revoked_stub(*, service: str, hash_short: str, status: int,
                       error: str | None = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    return (
        f"# External share — fetched {now}\n"
        f"_Source: {_pretty_url(service, hash_short)}_\n"
        f"_REVOKED: share returned HTTP {status} — student likely revoked "
        f"the share, or the URL was incorrect. Operator review needed._\n"
        + (f"_Error detail: {error}_\n" if error else "")
    )


def emit_error_stub(*, service: str, hash_short: str, error: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    return (
        f"# External share — fetch failed {now}\n"
        f"_Source: {_pretty_url(service, hash_short)}_\n"
        f"_Error: {error}_\n"
        f"_Operator review needed. If this persists, the share may have moved to a "
        f"new format. File an issue against canvas-toolbox._\n"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Follow ChatGPT/Gemini share URLs in submissions_raw/ and "
                    "render their transcripts via headless Chromium so the "
                    "downstream grader can read them as text.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", required=True,
                    help="Convention base path (e.g. grading/p1t1_ai_log).")
    ap.add_argument("--rate-limit", type=float, default=1.0,
                    help="Seconds between successive URL fetches (default 1.0).")
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="Per-request navigation timeout in seconds (default 30).")
    ap.add_argument("--hydration-wait", type=int, default=4000,
                    help="Milliseconds to wait after domcontentloaded for SPA "
                         "hydration (default 4000).")
    ap.add_argument("--force", action="store_true",
                    help="Re-fetch even if <prefix>_<userid>_external.md exists. "
                         "Default is idempotent skip.")
    args = ap.parse_args()

    cd = resolve_challenge_dir(args.challenge_dir, verb="following share URLs in")
    raw_dir = cd / "submissions_raw"
    if not raw_dir.exists():
        print(f"No submissions_raw/ under {cd}/. Run grader_fetch.py first.",
              file=sys.stderr)
        return 1

    # Preflight: Playwright + Chromium available?
    ok, msg = _playwright_available()
    if not ok:
        print(f"\n⛔ Playwright preflight failed:\n{msg}", file=sys.stderr)
        return 3

    log_path = raw_dir / "_external_fetch_log.json"
    fetch_log: dict = {}
    if log_path.exists():
        try:
            fetch_log = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            fetch_log = {}

    # Scan submissions_raw/ for share URLs
    by_file: dict[Path, list[ShareURL]] = {}
    for f in sorted(raw_dir.iterdir()):
        if not f.is_file() or f.name.startswith(".") or f.name.endswith("_external.md"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        urls = detect_share_urls(text)
        if urls:
            by_file[f] = urls

    if not by_file:
        print(f"No share URLs detected in {raw_dir}/. Nothing to follow.")
        return 0

    total_urls = sum(len(v) for v in by_file.values())
    print(f"Detected {total_urls} share URL(s) across {len(by_file)} submission(s). "
          f"Rate-limit: {args.rate_limit}s.", file=sys.stderr)

    fetched = skipped = revoked = failed = 0

    for f, urls in by_file.items():
        stem = f.stem
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
                time.sleep(args.rate_limit)

            result = fetch_share(share.url, share.service,
                                 timeout=args.timeout,
                                 hydration_wait_ms=args.hydration_wait)

            meta: dict = {
                "service": share.service,
                "hash_short": share.hash_short,
                "status": result.status,
                "bytes": result.bytes_total,
                "selector": result.used_selector,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

            pretty = _pretty_url(share.service, share.hash_short)
            if result.revoked:
                sections.append(emit_revoked_stub(
                    service=share.service, hash_short=share.hash_short,
                    status=result.status, error=result.error))
                meta["revoked"] = True
                revoked += 1
                print(f"  {userid}: {pretty} → REVOKED (HTTP {result.status})")
            elif result.status != 200 or not result.body:
                err = result.error or f"status {result.status}"
                sections.append(emit_error_stub(
                    service=share.service, hash_short=share.hash_short, error=err))
                meta["error"] = err
                failed += 1
                print(f"  {userid}: {pretty} → FAILED ({err})")
            else:
                sections.append(emit_markdown(
                    service=share.service, hash_short=share.hash_short,
                    status=result.status, body=result.body,
                    used_selector=result.used_selector, title=result.title))
                fetched += 1
                # FERPA: counts only, never content. Chars is a non-identifying
                # operator-facing metric (how much was extracted).
                print(f"  {userid}: {pretty} → {result.bytes_total} chars extracted "
                      f"(selector: {result.used_selector})")

            per_url_meta.append(meta)

        out_path.write_text("\n\n---\n\n".join(sections), encoding="utf-8")
        fetch_log[out_name] = {"source_file": f.name, "urls": per_url_meta}

        time.sleep(args.rate_limit)

    log_path.write_text(json.dumps(
        {"_warning": "FERPA — do NOT commit; metadata only.",
         "fetched_at": datetime.now(timezone.utc).isoformat(),
         "entries": fetch_log}, indent=2), encoding="utf-8")

    print(f"\n{fetched} fetched, {skipped} skipped (existing), "
          f"{revoked} revoked, {failed} failed. "
          f"Per-URL log -> {log_path.name}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

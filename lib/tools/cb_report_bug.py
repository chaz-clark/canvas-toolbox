#!/usr/bin/env python3
"""
Report a canvas-toolbox bug WITHOUT needing a GitHub account, the `gh`
CLI, a browser, or a PAT.

The CLI bundles local context (toolkit version, last command run, working
dir SANITIZED, env summary, an optional log / stack trace), opens
`$EDITOR` for the operator to add a description, scrubs PII, and POSTs
the rendered markdown to the canvas-toolbox bug-intake Cloudflare Worker.
The Worker files the GitHub issue using the maintainer's PAT and returns
the issue URL.

Per the canvas-toolbox#54 umbrella + the 2026-06-12 design conversation
(parking lot entry). Pairs with `infra/bug-intake-worker/`.

ARCHITECTURE
  faculty machine                    Cloudflare Worker             GitHub
  ┌──────────────────┐  POST /bug   ┌────────────────────┐  Issues  ┌──────────┐
  │ cb_report_bug.py │ ───────────▶ │ canvas-toolbox-bugs│ ───────▶ │ chaz-... │
  │ (scrubs locally) │              │ (rate-limit + scrub│          │ /toolbox │
  └──────────────────┘  issue URL   │  + file via PAT)   │          └──────────┘
                       ◀─────────── └────────────────────┘

  Faculty side: zero auth.
  Maintainer side: one PAT, stored as a Worker secret.
  Cost: $0.

FERPA
  - Body scrubbed CLIENT-SIDE before the network call using the same
    `expand_name_terms` + `name_aware_subn` helpers the deid adapters
    use. The Worker scrubs AGAIN server-side as defense in depth.
  - Console prints the issue URL on success. NO names, NO student data
    in any code path.
  - Working directory is replaced with `~/...` shorthand in the
    rendered body. Stack-trace paths under `/Users/<name>/` or
    `/home/<name>/` are auto-redacted.

USAGE
  # Interactive — opens $EDITOR for the description, prompts for title
  uv run python lib/tools/cb_report_bug.py

  # Auto-bundle a log file
  uv run python lib/tools/cb_report_bug.py \\
      --from grading/<task>/feedback/error.log \\
      --title "bug: grader_grade 4xx on KC1"

  # Headless / scripted
  uv run python lib/tools/cb_report_bug.py \\
      --title "enhancement: <short title>" --body "<markdown body>"

  # Show what would be sent without posting
  uv run python lib/tools/cb_report_bug.py --dry-run

TITLE-PREFIX CONVENTION
  - `bug: ...`         — toolkit deviated from documented behavior, exit
                         code surprised the agent, output looks wrong.
  - `enhancement: ...` — operator wants something the tool doesn't yet
                         do; or a recurring friction crossed the Hermes
                         promotion threshold (captured twice in
                         `lib/agents/knowledge/learned/`).
  - `share: ...`       — operator BUILT something locally and wants
                         to contribute it back. Body should describe
                         what they built, what use case it solves, +
                         a link to a gist/diff/branch OR a paste of
                         the code/config. Maintainer triages these
                         differently from `enhancement:` (asks for it)
                         vs `share:` (already built it).
  The maintainer triages on these prefixes. The CLI doesn't require
  them, but agents calling this tool SHOULD include one. See
  `AGENTS.md → Continuous improvement` for the DO / DO-NOT calibration.
  The `cb-share` alias in `bin/` invokes this same tool — use it when
  the prefix is `share:` for self-documenting CLI invocations.

EXIT CODES
  0  filed (or printed in --dry-run)
  1  user aborted or empty body
  2  network / worker / GitHub error
"""
from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

# Reuse the canonical scrub helpers — single source of truth.
try:
    from grader_deidentify_databricks import (  # noqa: E402
        EMAIL_RE,
        USERPATH_RE,
        expand_name_terms,
        name_aware_subn,
    )
except ImportError:
    EMAIL_RE = None
    USERPATH_RE = None
    expand_name_terms = lambda *_: []  # noqa: E731
    name_aware_subn = lambda t, _: (t, 0)  # noqa: E731

# ----------------------------------------------------------------------------
# CONFIG — bug-intake worker endpoint
# ----------------------------------------------------------------------------
# Production endpoint, deployed 2026-06-15. The worker source + deploy
# notes live in infra/bug-intake-worker/. Override via --endpoint for
# testing against a preview deployment.
_ENDPOINT: str | None = "https://canvas-toolbox-bugs.tylerchaz5.workers.dev/bug"

_USER_AGENT = f"canvas-toolbox-bug-reporter/{__version__}"
_TIMEOUT = 30


# ----------------------------------------------------------------------------
# Context bundling
# ----------------------------------------------------------------------------

def _local_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""


def _sanitize_path(p: str, local_user: str) -> str:
    """Replace `/Users/<u>` or `/home/<u>` with `~/...` shorthand."""
    if not p:
        return p
    if local_user:
        for prefix in (f"/Users/{local_user}", f"/home/{local_user}"):
            if p.startswith(prefix):
                return "~" + p[len(prefix):]
    return p


def _bundle_context(args, local_user: str) -> dict[str, str]:
    """Toolkit version + machine summary + cwd shorthand + optional log."""
    cwd = _sanitize_path(str(Path.cwd().resolve()), local_user)
    py = sys.version.split()[0]
    plat = f"{platform.system()} {platform.release()}"

    log_excerpt = ""
    if args.from_log:
        try:
            text = Path(args.from_log).read_text(encoding="utf-8", errors="replace")
            # Tail — last ~150 lines is usually the actionable part
            lines = text.splitlines()
            log_excerpt = "\n".join(lines[-150:])
        except Exception as e:
            log_excerpt = f"(could not read {args.from_log}: {type(e).__name__}: {e})"

    return {
        "toolkit_version": __version__,
        "python": py,
        "platform": plat,
        "cwd": cwd,
        "log_excerpt": log_excerpt,
    }


def _render_body(description: str, ctx: dict[str, str]) -> str:
    """Compose the markdown issue body. Description first; metadata in a
    collapsible footer block so the issue is human-skimmable at the top."""
    parts: list[str] = []
    parts.append(description.strip() or "(no description provided)")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("<details><summary>Environment</summary>")
    parts.append("")
    parts.append(f"- canvas-toolbox: `{ctx['toolkit_version']}`")
    parts.append(f"- python: `{ctx['python']}`")
    parts.append(f"- platform: `{ctx['platform']}`")
    parts.append(f"- cwd: `{ctx['cwd']}`")
    parts.append("")
    parts.append("</details>")
    if ctx.get("log_excerpt"):
        parts.append("")
        parts.append("<details><summary>Log excerpt (last 150 lines)</summary>")
        parts.append("")
        parts.append("```")
        parts.append(ctx["log_excerpt"])
        parts.append("```")
        parts.append("")
        parts.append("</details>")
    return "\n".join(parts)


# ----------------------------------------------------------------------------
# Scrub — defense in depth before the network call
# ----------------------------------------------------------------------------

def _scrub_body(text: str, extra_names: list[str]) -> tuple[str, int]:
    """Apply the canonical deid scrub against the body before posting."""
    if not text:
        return "", 0
    n = 0
    # Roster names (if a .known_names.txt happens to be in cwd)
    for term in expand_name_terms(extra_names):
        text, k = name_aware_subn(text, term)
        n += k
    # Belt-and-suspenders email + path
    if EMAIL_RE is not None:
        text, k1 = EMAIL_RE.subn("[REDACTED-EMAIL]", text)
        n += k1
    if USERPATH_RE is not None:
        text, k2 = USERPATH_RE.subn("[REDACTED-PATH]", text)
        n += k2
    # Local username (covers Windows paths + casual mentions)
    local_user = _local_user()
    if local_user and len(local_user) >= 4:
        text, k3 = name_aware_subn(text, local_user)
        n += k3
    return text, n


def _load_local_roster() -> list[str]:
    """If the operator happens to be inside a challenge dir with a
    .known_names.txt, scrub against THAT roster too. Best-effort —
    silent on absence."""
    nf = Path.cwd() / ".known_names.txt"
    if not nf.exists():
        # Walk up a couple levels — they might be one dir deeper
        for parent in Path.cwd().parents[:3]:
            candidate = parent / ".known_names.txt"
            if candidate.exists():
                nf = candidate
                break
        else:
            return []
    try:
        return [ln.strip() for ln in nf.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")]
    except Exception:
        return []


# ----------------------------------------------------------------------------
# Editor — fallback through a chain of options
# ----------------------------------------------------------------------------

_DESCRIPTION_TEMPLATE = """\
# Describe the bug

(Replace this section with what happened, what you expected, and what
the toolkit actually did. Lines starting with `#` are kept as headings —
that's fine. Save and close this editor to submit.)


# How to reproduce (if known)

1.
2.
3.


# Anything else

(Optional — feature ask, related issue, the assignment id you were
working on, etc. Nothing student-identifying. The toolkit scrubs
emails / paths / known names locally before sending; redact anything
else manually before saving.)
"""


def _open_in_editor() -> str:
    editor = (os.environ.get("VISUAL") or os.environ.get("EDITOR")
              or shutil.which("nano") or shutil.which("vim") or "")
    if not editor:
        print("No $EDITOR / $VISUAL / nano / vim found. Pass --body \"...\" or "
              "set $EDITOR.", file=sys.stderr)
        return ""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(_DESCRIPTION_TEMPLATE)
        tmp = f.name
    try:
        subprocess.run([editor, tmp], check=False)
        return Path(tmp).read_text(encoding="utf-8")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ----------------------------------------------------------------------------
# Network
# ----------------------------------------------------------------------------

def _post_to_worker(endpoint: str, title: str, body: str) -> tuple[int, dict]:
    payload = {
        "title": title,
        "body": body,
        "toolkit_version": __version__,
        "user_agent": _USER_AGENT,
    }
    r = requests.post(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/json; charset=utf-8",
        },
        timeout=_TIMEOUT,
    )
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {"raw": r.text}


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Report a canvas-toolbox bug without needing a GitHub account "
                    "or the `gh` CLI. Posts to the bug-intake worker; the worker "
                    "files the GitHub issue.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--title", default=None,
                    help="One-line issue title. Prompted if omitted.")
    ap.add_argument("--body", default=None,
                    help="Issue body (markdown). Opens $EDITOR if omitted (and --from is unused).")
    ap.add_argument("--from", dest="from_log", default=None,
                    help="Path to a log / stack trace to attach. Last 150 lines included.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what WOULD be sent (title + scrubbed body). Don't POST.")
    ap.add_argument("--endpoint", default=None,
                    help="Override the worker endpoint URL (advanced; default reads "
                         "the constant in this file).")
    args = ap.parse_args()

    endpoint = args.endpoint or _ENDPOINT

    # Title
    title = (args.title or "").strip()
    if not title and not args.dry_run:
        try:
            title = input("Bug title (one line): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.", file=sys.stderr)
            return 1
    if not title:
        title = "(no title)"

    # Body
    body_src = args.body
    if body_src is None:
        body_src = _open_in_editor()
    if not (body_src or "").strip():
        print("Empty body — nothing to report. Aborted.", file=sys.stderr)
        return 1

    # Bundle context + render
    local_user = _local_user()
    ctx = _bundle_context(args, local_user)
    rendered = _render_body(body_src, ctx)

    # Scrub (defense in depth — worker scrubs again)
    roster = _load_local_roster()
    scrubbed, n_scrubs = _scrub_body(rendered, roster)
    scrubbed_title, _ = _scrub_body(title, roster)

    if args.dry_run:
        print("=== DRY RUN — not posting ===")
        print(f"title: {scrubbed_title}")
        print(f"endpoint: {endpoint or '(unset — see infra/bug-intake-worker/README.md)'}")
        print(f"body length: {len(scrubbed)} chars  (after {n_scrubs} redaction(s))")
        print()
        print(scrubbed)
        return 0

    if not endpoint:
        print("⛔ _ENDPOINT not set. The bug-intake worker hasn't been deployed yet, "
              "or the URL hasn't been wired into this file. See "
              "infra/bug-intake-worker/README.md for the one-time setup. "
              "Until then, file the bug at "
              "https://github.com/chaz-clark/canvas-toolbox/issues/new", file=sys.stderr)
        return 2

    print(f"  scrubbed {n_scrubs} sensitive token(s) from the body. Posting...")
    t0 = time.monotonic()
    try:
        status, payload = _post_to_worker(endpoint, scrubbed_title, scrubbed)
    except requests.RequestException as e:
        print(f"⛔ network error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    dt = time.monotonic() - t0

    if 200 <= status < 300:
        url = (payload or {}).get("url")
        num = (payload or {}).get("number")
        if url:
            print(f"✓ filed: {url}  ({dt:.1f}s)")
            if num:
                print(f"  (issue #{num} on chaz-clark/canvas-toolbox)")
            print("  Thank you. The maintainer will triage shortly.")
            return 0
        print(f"✓ worker accepted (status {status}, no URL returned): {payload}")
        return 0

    if status == 429:
        print(f"⛔ rate-limited (status 429): {payload}", file=sys.stderr)
        print("   Wait a bit and try again. Or use the GitHub web UI: "
              "https://github.com/chaz-clark/canvas-toolbox/issues/new", file=sys.stderr)
        return 2

    print(f"⛔ worker rejected (status {status}): {payload}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""
Single source of truth for loading .env across canvas-toolbox tools.

Closes issue #43 — the prior pattern `Path(__file__).parent.parent / ".env"`
resolves to `canvas-toolbox/lib/.env` under the documented clone-in-subdir
layout, which is two levels too deep from where the README tells the
operator to put `.env` (the course-repo root). Every tool that called that
pattern silently missed the `.env` and exited with "Missing required env
variables" — the operator's only escape was the `uv run --env-file .env`
workaround.

This helper resolves `.env` robustly regardless of where the tool is
invoked from. Resolution order (first match wins):

  1. **find_dotenv(usecwd=True)** — python-dotenv's built-in upward walk
     starting at the CWD. Handles the documented invocation pattern
     (`uv run python canvas-toolbox/lib/tools/<tool>.py` from course-repo
     root) AND deep-nested invocations (e.g. running from a sub-cohort
     folder). Stops at the filesystem root or the first `.env` it finds.

  2. **__file__-walk** — fallback for unusual layouts where CWD doesn't
     contain `.env` in any ancestor (e.g. tool invoked from outside the
     repo tree). Walks up from this file's location until `.env` is
     found or filesystem root.

USAGE - load_env()
  Tools should call this once near the top of their module:

      try:
          from _env_loader import load_env
          load_env()
      except ImportError:
          pass  # python-dotenv not installed — let the env-var checks
                # downstream complain with the proper error

  load_env() returns the Path it loaded from (for logging if needed) or
  None if no .env was found anywhere.

USAGE - force_utf8_console()
  Tools that print Unicode glyphs (✓, —, ⏭, emoji) should call this at the
  top of main() to prevent UnicodeEncodeError on Windows cp1252 consoles:

      from _env_loader import force_utf8_console

      def main():
          force_utf8_console()
          # ... rest of main

  Closes issue #123 — Windows console crashes on glyph output.

WHY A HELPER VS. INLINING
  Twelve tools had three different inline patterns (two of them buggy).
  A single helper means a future improvement (e.g. multi-file precedence,
  per-tool .env overrides) lands in ONE place instead of twelve. It also
  forces consistency — a new tool that copies the helper-call pattern
  inherits the fix automatically.
"""
from __future__ import annotations

import sys
from pathlib import Path


GLOBAL_CONFIG = Path.home() / ".canvas" / "config"

# What the GLOBAL file is allowed to supply. An allowlist, not a denylist: a
# denylist would have to be extended for every future per-course key (S3_COURSE_ID,
# the next one nobody has thought of), and the cost of missing one is a grade pushed
# to the wrong course.
#
# CANVAS_COURSE_ID is excluded ON PURPOSE and this is the whole safety property.
# canvas_course_guard (#27) exists because "a stale or hand-edited .env can silently
# point CANVAS_COURSE_ID at the wrong course". If a course id could come from a
# global file, a repo with a missing or partial .env would silently inherit whichever
# course was configured last — manufacturing exactly that failure. The token is
# per-USER and rotates; the course id is per-REPO and doesn't. Only the first belongs
# in a shared file.
GLOBAL_KEYS = ("CANVAS_API_TOKEN", "CANVAS_BASE_URL")


def _global_values() -> tuple[dict, list[str]]:
    """(allowed values, rejected key names) from ~/.canvas/config.

    Parsed with python-dotenv, not by hand. `export CANVAS_API_TOKEN="1234~ab#cd"`
    is a real line shape: a naive `line.startswith(KEY)` misses the export prefix
    entirely, a naive split keeps the quotes, and a naive comment-strip truncates at
    the `#`. Each of those fails SILENTLY — you get "no token found" while the token
    sits in the file."""
    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}, []
    if not GLOBAL_CONFIG.is_file():
        return {}, []
    try:
        raw = dotenv_values(GLOBAL_CONFIG)
    except (OSError, ValueError):
        return {}, []
    allowed = {k: v for k, v in raw.items() if k in GLOBAL_KEYS and v}
    rejected = [k for k in raw if k not in GLOBAL_KEYS]
    return allowed, rejected


def global_config_problems() -> list[str]:
    """Human-readable warnings about ~/.canvas/config — for tools to surface rather
    than swallow. Never raises; a credential file problem must not brick a tool."""
    out = []
    if not GLOBAL_CONFIG.is_file():
        return out
    try:
        mode = GLOBAL_CONFIG.stat().st_mode
        if mode & 0o077:
            out.append(f"{GLOBAL_CONFIG} is readable by other users. "
                       f"It holds an API token — run: chmod 600 {GLOBAL_CONFIG}")
    except OSError:
        pass
    _, rejected = _global_values()
    for k in rejected:
        if "COURSE_ID" in k.upper():
            out.append(f"{GLOBAL_CONFIG} sets {k} — IGNORED. A course id must live in "
                       f"the course's own .env; a global one silently sends writes to "
                       f"whichever course was configured last.")
        else:
            out.append(f"{GLOBAL_CONFIG} sets {k} — ignored (only {', '.join(GLOBAL_KEYS)} "
                       f"are read from the global file).")
    return out


def load_env() -> Path | None:
    """Resolve and load the nearest .env, then fill gaps from ~/.canvas/config.

    Precedence, highest first:
      1. an already-set environment variable  (CI, one-off `TOKEN=x uv run …`)
      2. the repo's .env                       (per-repo override)
      3. ~/.canvas/config                      (the shared, rotating secret)

    Canvas expires API tokens every 29 days, so an operator running N course repos was
    editing N .env files a month — and the one they forgot 401'd silently until a
    grading run failed. The global file makes that one edit.

    EMPTY COUNTS AS ABSENT. cb_init scaffolds a bare `CANVAS_API_TOKEN=` into every new
    repo's .env; treating that as a value would mean each new repo shadows the global
    file with an empty string and breaks on day one. Only a REAL value overrides.

    Returns the .env path loaded (unchanged contract — 90 tools call this), or None."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return None

    loaded: Path | None = None

    # 1. CWD-anchored upward walk (python-dotenv's built-in)
    #    Documented invocation pattern: operator runs from course-repo root,
    #    .env lives there, find_dotenv finds it immediately.
    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found)
        loaded = Path(found)
    else:
        # 2. __file__-anchored upward walk (fallback for unusual layouts)
        #    Catches the case where the tool is invoked from outside the repo
        #    tree (e.g. an absolute-path invocation from a different CWD).
        p = Path(__file__).resolve()
        for parent in p.parents:
            candidate = parent / ".env"
            if candidate.exists():
                load_dotenv(candidate)
                loaded = candidate
                break

    # 3. Global fallback — only for keys still missing or empty, and only the
    #    allowlisted ones. Applied key-by-key rather than via load_dotenv() on the
    #    file, so an unexpected key in there can never reach the environment.
    import os
    allowed, _ = _global_values()
    for key in GLOBAL_KEYS:
        if not os.environ.get(key) and allowed.get(key):
            os.environ[key] = allowed[key]

    return loaded


def token_source() -> str:
    """Where the token in the current environment came from — for reporting.
    'env'/'repo .env'/'~/.canvas/config'/'none'. Best-effort, never raises."""
    import os
    if not os.environ.get("CANVAS_API_TOKEN"):
        return "none"
    allowed, _ = _global_values()
    if os.environ["CANVAS_API_TOKEN"] == allowed.get("CANVAS_API_TOKEN"):
        return str(GLOBAL_CONFIG)
    return "repo .env or environment"


def force_utf8_console() -> None:
    """
    Force UTF-8 encoding on stdout/stderr for Windows cp1252 consoles.

    On Windows, CPython encodes stdout using the locale code page (cp1252 by
    default) unless UTF-8 mode is enabled. Unicode glyphs (✓, —, ⏭, emoji)
    aren't representable in cp1252, causing UnicodeEncodeError crashes.

    This function reconfigures sys.stdout and sys.stderr to UTF-8 on Windows
    (no-op on other platforms) to prevent these crashes.

    Call this at the top of main() in any tool that prints Unicode glyphs.

    Fixes issue #123 — Windows console crashes with UnicodeEncodeError.
    """
    if sys.platform != "win32":
        return  # No-op on non-Windows platforms

    # Reconfigure stdout and stderr to UTF-8 encoding
    # This mirrors the behavior of PYTHONUTF8=1 environment variable
    import io

    if sys.stdout is not None:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
    if sys.stderr is not None:
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )

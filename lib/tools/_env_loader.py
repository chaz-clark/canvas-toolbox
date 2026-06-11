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

USAGE
  Tools should call this once near the top of their module:

      try:
          from _env_loader import load_env
          load_env()
      except ImportError:
          pass  # python-dotenv not installed — let the env-var checks
                # downstream complain with the proper error

  load_env() returns the Path it loaded from (for logging if needed) or
  None if no .env was found anywhere.

WHY A HELPER VS. INLINING
  Twelve tools had three different inline patterns (two of them buggy).
  A single helper means a future improvement (e.g. multi-file precedence,
  per-tool .env overrides) lands in ONE place instead of twelve. It also
  forces consistency — a new tool that copies the helper-call pattern
  inherits the fix automatically.
"""
from __future__ import annotations

from pathlib import Path


def load_env() -> Path | None:
    """Resolve and load the nearest .env. Returns the path loaded, or None."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return None

    # 1. CWD-anchored upward walk (python-dotenv's built-in)
    #    Documented invocation pattern: operator runs from course-repo root,
    #    .env lives there, find_dotenv finds it immediately.
    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found)
        return Path(found)

    # 2. __file__-anchored upward walk (fallback for unusual layouts)
    #    Catches the case where the tool is invoked from outside the repo
    #    tree (e.g. an absolute-path invocation from a different CWD).
    p = Path(__file__).resolve()
    for parent in p.parents:
        candidate = parent / ".env"
        if candidate.exists():
            load_dotenv(candidate)
            return candidate

    return None

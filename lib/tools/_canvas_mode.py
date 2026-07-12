"""
Canvas mode helper — single source of truth for online vs offline operation.

Part of offline mode (Sprint 1). Faculty who cannot obtain a Canvas API token
(IT policy) run tools in "offline" mode: data comes from Canvas UI
download/upload (gradebook CSV, .imscc) instead of the REST API. Every
mode-aware tool calls get_canvas_mode() / check_mode_requirements() at startup
and branches on the result.

Design decisions (see docs/offline_mode.md):
  - EXPLICIT flag, not auto-detection (commit 0b39cbb). CANVAS_MODE in .env
    controls it; default "online" preserves current behavior for every existing
    tool that never sets it.
  - The token variable is CANVAS_API_TOKEN — matching the rest of the toolbox
    and lib/tests/conftest.py. (The early design docs said "CANVAS_TOKEN"; that
    was never the real variable name.)
  - Unknown CANVAS_MODE values fail loud (ValueError) rather than silently
    falling back to online — a typo shouldn't quietly hit the API.

USAGE
    from _canvas_mode import check_mode_requirements, is_offline_mode

    def main():
        mode = check_mode_requirements()   # raises if online without a token
        if is_offline_mode():
            ...  # read from local files
        else:
            ...  # call the Canvas API
"""
import os

ONLINE = "online"
OFFLINE = "offline"
_VALID_MODES = (ONLINE, OFFLINE)


def get_canvas_mode(env=None) -> str:
    """Return the configured Canvas mode: "online" (default) or "offline".

    Reads CANVAS_MODE from `env` (defaults to os.environ), case- and
    whitespace-insensitive. An unset/empty value means "online" so existing
    tools keep working unchanged. Any other value raises ValueError.
    """
    env = os.environ if env is None else env
    raw = (env.get("CANVAS_MODE") or ONLINE).strip().lower()
    if raw not in _VALID_MODES:
        raise ValueError(
            f"CANVAS_MODE={raw!r} is invalid; expected one of {_VALID_MODES}. "
            f"Leave it unset for online mode."
        )
    return raw


def is_online_mode(env=None) -> bool:
    """True when operating against the Canvas API (the default)."""
    return get_canvas_mode(env) == ONLINE


def is_offline_mode(env=None) -> bool:
    """True when operating from Canvas UI downloads (no API token)."""
    return get_canvas_mode(env) == OFFLINE


def check_mode_requirements(env=None) -> str:
    """Validate that the environment satisfies the selected mode; return it.

    online  → CANVAS_API_TOKEN must be present (API calls 401 without it).
    offline → no token required (data comes from local files).

    Raises ValueError with actionable guidance when online mode lacks a token.
    """
    env = os.environ if env is None else env
    mode = get_canvas_mode(env)
    if mode == ONLINE and not (env.get("CANVAS_API_TOKEN") or "").strip():
        raise ValueError(
            "CANVAS_MODE=online requires CANVAS_API_TOKEN. "
            "Set the token in .env, or switch to CANVAS_MODE=offline to work "
            "from Canvas UI downloads (gradebook CSV / .imscc)."
        )
    return mode

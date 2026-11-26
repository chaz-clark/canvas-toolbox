"""Canvas calls that survive a dropped connection without duplicating work (#445).

Instructors report the Canvas connection dropping during long tasks. Two rules:

  * A read or an update (every method but POST: GET, PUT, PATCH, DELETE, HEAD)
    gives the same result however
    many times it's sent (a repeated DELETE that had landed comes back
    "not found"), so a dropped connection, a timeout, or a "slow down" /
    "busy" answer (429, 502, 503, 504) is retried after a pause: up to 4
    attempts, waiting 2, 5 and 15 seconds, or as long as Canvas's Retry-After
    asks (at most 60).

  * A create (POST) may already have happened on Canvas when the connection
    drops or the gateway gives up (502/504). Sending it again is how
    announcements and assignments got duplicated (lesson L34). So it is retried
    only when Canvas certainly never received it: the connection was never made,
    or Canvas refused with 429/503 (Canvas's own "slow down" and "unavailable"
    answers; a proxy that answers 503 after forwarding would be the rare
    exception). Otherwise UnsureWrite is raised: the caller
    reports it as unsure and says to check Canvas before running it again.

    Pass safe_to_repeat=True for a POST that creates nothing new (an upload
    token request, a search).

Each retry prints one plain line to stderr, so a long run shows why it paused.
"""
from __future__ import annotations

import sys
import time

import requests

_WAITS = (2, 5, 15)            # seconds before attempts 2, 3 and 4
_RETRY_STATUS = {429, 502, 503, 504}
_NOT_RECEIVED_STATUS = {429, 503}  # Canvas refused it: nothing was created
_MAX_RETRY_AFTER = 60


# A dropped or cut connection. A reply cut off partway (ChunkedEncodingError,
# ContentDecodingError) means Canvas did receive the request.
_DROPPED = (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError, requests.exceptions.ContentDecodingError)


class UnsureWrite(Exception):
    """A create may or may not have reached Canvas; it was not sent again."""


def _never_sent(exc: Exception) -> bool:
    """True when the request certainly never reached Canvas."""
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return True
    if isinstance(exc, requests.exceptions.ConnectionError):
        text = repr(exc)
        return any(s in text for s in ("NewConnectionError", "NameResolutionError",
                                       "Failed to establish a new connection",
                                       "Connection refused"))
    return False


def _retry_after(resp) -> float | None:
    try:
        return max(0.0, min(float(resp.headers.get("Retry-After", "")), _MAX_RETRY_AFTER))
    except (TypeError, ValueError):
        return None


def _note(why: str, wait: float, failed: int) -> None:
    """`failed` is the 0-based attempt that just failed; the next is failed + 2 of N."""
    print(f"  Canvas {why}; trying again in {wait:g} s "
          f"(attempt {failed + 2} of {len(_WAITS) + 1}).", file=sys.stderr)


def request(method: str, url: str, *, safe_to_repeat: bool | None = None,
            sleep=None, client=None, **kwargs):
    """requests.request with the retry rules above. Returns the final response;
    raises the last connection error after the last attempt, or UnsureWrite.
    `client` is the caller's requests module (so the caller's stubs apply)."""
    http = client or requests
    method = method.upper()
    repeatable = (method != "POST") if safe_to_repeat is None else safe_to_repeat
    sleep = sleep or time.sleep
    last = len(_WAITS)
    for attempt in range(last + 1):
        try:
            # requests.get/put/post/... by name (the same request as requests.request),
            # so callers' and tests' stubs of those functions still apply.
            resp = getattr(http, method.lower())(url, **kwargs)
        except _DROPPED as exc:
            if not repeatable and not _never_sent(exc):
                raise UnsureWrite(
                    f"the connection to Canvas dropped during a create ({type(exc).__name__}); "
                    f"Canvas may have done it already, so it was not sent again. Check "
                    f"Canvas before running it again.") from exc
            if attempt == last:
                raise
            _note(f"connection dropped ({type(exc).__name__})", _WAITS[attempt], attempt)
            sleep(_WAITS[attempt])
            continue
        if resp.status_code in _RETRY_STATUS:
            if not repeatable and resp.status_code not in _NOT_RECEIVED_STATUS:
                raise UnsureWrite(
                    f"Canvas answered a create with HTTP {resp.status_code}; it may have "
                    f"done it already, so it was not sent again. Check Canvas before "
                    f"running it again.")
            if attempt < last:
                wait = _retry_after(resp) or _WAITS[attempt]
                why = ("asked to slow down (HTTP 429)" if resp.status_code == 429
                       else f"was busy (HTTP {resp.status_code})")
                _note(why, wait, attempt)
                sleep(wait)
                continue
        return resp
    return resp  # pragma: no cover - the loop always returns or raises

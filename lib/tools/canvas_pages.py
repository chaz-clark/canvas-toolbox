"""Shared idempotent Canvas wiki-Page helpers.

Used by blueprint_sync.py and course_mirror.py. Pure functions — they take the
base URL and auth headers as arguments and do not depend on either caller's
module globals.

Root cause this module fixes (issue #26): both sync tools used to POST a new
Page on every --push with no "does this title already exist in the target?"
check. Canvas auto-suffixes the URL on a title collision (-2/-4/-5/-6...) and a
fresh module item is added each run, so the same page duplicated 4x across
master/blueprint/sections over multiple sync runs. upsert_page() makes the
create idempotent; page_in_module() guards the module-item link.
"""

from typing import Optional

import requests

_TIMEOUT = 20


def _paginated_get(base_url: str, headers: dict, endpoint: str, params: dict = None) -> list:
    """GET a list endpoint, following Link rel="next". Returns [] on first error."""
    url = f"{base_url}/api/v1{endpoint}"
    out: list = []
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=_TIMEOUT)
        if resp.status_code >= 400:
            return out
        data = resp.json()
        if isinstance(data, list):
            out.extend(data)
        else:
            return [data]
        url = None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        params = None
    return out


def find_pages_by_title(base_url: str, headers: dict, course_id: str, title: str) -> list:
    """Pages in course_id whose title EXACTLY matches `title` (case-insensitive,
    trimmed). Canvas's search_term is a partial match on title/body, so the
    exact filter is applied client-side."""
    want = (title or "").strip().lower()
    if not want:
        return []
    pages = _paginated_get(
        base_url, headers, f"/courses/{course_id}/pages",
        params={"search_term": title, "per_page": 100},
    )
    return [p for p in pages if (p.get("title") or "").strip().lower() == want]


def upsert_page(
    base_url: str,
    headers: dict,
    course_id: str,
    title: str,
    body: str,
    published: bool = True,
) -> tuple[Optional[str], str]:
    """Idempotently ensure a Page with `title` exists in course_id with the
    given body/published state.

    Returns (page_url, action) where action is one of:
      - "updated"   exactly one existing page matched → PUT in place
      - "created"   no existing page matched → POST new
      - "ambiguous" >1 existing page matched → NO write (corrupted-state guard,
                    pairs with #23 manual_review); page_url is None
      - "error:<detail>" the Canvas write failed; page_url is None
    """
    matches = find_pages_by_title(base_url, headers, course_id, title)

    if len(matches) > 1:
        return None, "ambiguous"

    if len(matches) == 1:
        page_url = matches[0].get("url")
        resp = requests.put(
            f"{base_url}/api/v1/courses/{course_id}/pages/{page_url}",
            headers=headers,
            json={"wiki_page": {"body": body, "published": published}},
            timeout=_TIMEOUT,
        )
        if resp.status_code >= 400:
            return None, f"error:{resp.text[:150]}"
        return page_url, "updated"

    resp = requests.post(
        f"{base_url}/api/v1/courses/{course_id}/pages",
        headers=headers,
        json={"wiki_page": {"title": title, "body": body, "published": published}},
        timeout=_TIMEOUT,
    )
    if resp.status_code >= 400:
        return None, f"error:{resp.text[:150]}"
    return resp.json().get("url"), "created"


def page_in_module(
    base_url: str,
    headers: dict,
    course_id: str,
    module_id,
    page_url: str,
) -> bool:
    """True if a Page module-item with this page_url is already linked in the
    module. Guards against re-adding the same page as a duplicate module item."""
    items = _paginated_get(
        base_url, headers,
        f"/courses/{course_id}/modules/{module_id}/items",
        params={"per_page": 100},
    )
    for it in items:
        if it.get("type") == "Page" and it.get("page_url") == page_url:
            return True
    return False

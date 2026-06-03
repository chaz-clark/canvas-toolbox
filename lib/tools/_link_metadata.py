"""Strip Canvas's stale data-api-endpoint / data-api-returntype attributes
from <a> tags whose href no longer matches the metadata target.

Background (issue #42)
----------------------
Canvas auto-injects `data-api-endpoint` and `data-api-returntype` attributes
on Canvas-internal links inside Page/Assignment/Quiz/Discussion descriptions.
When the `href` is later swapped (to a different Canvas resource OR an
external URL), Canvas does NOT update or strip those attributes — they keep
pointing at the original target.

The link clicks correctly (browsers follow `href`, not `data-api-*`), but:
  - Hovercard / preview UI tries to fetch the stale target.
  - Audit tools reading `data-api-endpoint` misreport where the link points.
  - Description hashes / diffs become noisy.

This helper detects the mismatch and strips both `data-api-*` attrs.
Idempotent: matching pairs are left untouched. Stdlib-only (regex).
"""

from __future__ import annotations

import re

# Match the canonical Canvas path /courses/{id}/{type}/{id-or-slug}
# Resource types we care about (the ones Canvas auto-injects data-api-* on).
_COURSE_PATH_RE = re.compile(
    r"^/courses/(\d+)/(assignments|pages|quizzes|discussion_topics|files|modules)/([\w\-]+)"
)

# Locate opening <a ...> tags. Doesn't try to parse nested HTML — anchor opening
# tags don't contain '>' in their attributes in well-formed Canvas content, and
# Canvas's editor produces well-formed tags.
_ANCHOR_OPEN_RE = re.compile(r"(<a\b[^>]*>)", re.IGNORECASE)

# Capture an attribute name + quoted value. Names may include hyphens (data-*).
_ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*(["\'])(.*?)\2', re.DOTALL)

# Strip the data-api-endpoint / data-api-returntype attribute (incl. leading
# whitespace) from a tag string.
_STRIP_DATA_API_RE = re.compile(
    r'\s+data-api-(?:endpoint|returntype)\s*=\s*"[^"]*"',
    re.IGNORECASE,
)
_STRIP_DATA_API_SINGLE_QUOTE_RE = re.compile(
    r"\s+data-api-(?:endpoint|returntype)\s*=\s*'[^']*'",
    re.IGNORECASE,
)


def _canonical_target(url: str) -> tuple[str, str] | None:
    """Extract (course_id, 'resource_type/id_or_slug') from a Canvas URL.

    Handles both UI URLs (`/courses/.../pages/foo`) and API URLs
    (`/api/v1/courses/.../pages/foo`). Returns None for external URLs or
    Canvas paths not matching the expected resource pattern.
    """
    if not url:
        return None
    idx = url.find("/courses/")
    if idx < 0:
        return None
    path = url[idx:]
    for sep in ("?", "#"):
        i = path.find(sep)
        if i > 0:
            path = path[:i]
    m = _COURSE_PATH_RE.match(path)
    if not m:
        return None
    return (m.group(1), f"{m.group(2)}/{m.group(3)}")


def _same_target(href: str, data_api_endpoint: str) -> bool:
    """True iff both URLs resolve to the same Canvas course resource."""
    a = _canonical_target(href)
    b = _canonical_target(data_api_endpoint)
    if a is None or b is None:
        return False
    return a == b


def _parse_attrs(tag: str) -> dict[str, str]:
    """Return a lowercase-keyed dict of attributes parsed from an opening tag."""
    return {m.group(1).lower(): m.group(3) for m in _ATTR_RE.finditer(tag)}


def _normalize_anchor(opening_tag: str) -> tuple[str, bool]:
    """Given a single `<a ...>` opening tag, return (normalized_tag, modified)."""
    attrs = _parse_attrs(opening_tag)
    dae = attrs.get("data-api-endpoint", "")
    if not dae:
        return opening_tag, False
    href = attrs.get("href", "")
    if _same_target(href, dae):
        return opening_tag, False
    new_tag = _STRIP_DATA_API_RE.sub("", opening_tag)
    new_tag = _STRIP_DATA_API_SINGLE_QUOTE_RE.sub("", new_tag)
    return new_tag, (new_tag != opening_tag)


def strip_stale_link_metadata(html: str) -> tuple[str, int]:
    """Normalize `<a>` tags by dropping `data-api-endpoint` and
    `data-api-returntype` when those attrs no longer point at the link's
    current `href` target.

    Returns ``(normalized_html, count_of_anchors_normalized)``.

    Idempotent: calling on already-clean HTML returns it unchanged with
    count=0. Matching pairs (href and data-api-endpoint pointing at the same
    Canvas resource) are left untouched — no false positives.
    """
    if not html or "data-api-endpoint" not in html:
        return html, 0
    count = 0

    def _replace(match: re.Match) -> str:
        nonlocal count
        original = match.group(1)
        new_tag, modified = _normalize_anchor(original)
        if modified:
            count += 1
        return new_tag

    return _ANCHOR_OPEN_RE.sub(_replace, html), count


def find_stale_link_metadata(html: str) -> list[dict]:
    """Read-only audit variant. Return one dict per anchor with stale metadata.

    Each dict contains: ``{"href": str, "data_api_endpoint": str,
    "data_api_returntype": str, "tag": str}``. Returns an empty list when no
    anchors have stale metadata (or input is empty).
    """
    if not html or "data-api-endpoint" not in html:
        return []
    findings = []
    for m in _ANCHOR_OPEN_RE.finditer(html):
        tag = m.group(1)
        attrs = _parse_attrs(tag)
        dae = attrs.get("data-api-endpoint", "")
        if not dae:
            continue
        href = attrs.get("href", "")
        if _same_target(href, dae):
            continue
        findings.append({
            "href": href,
            "data_api_endpoint": dae,
            "data_api_returntype": attrs.get("data-api-returntype", ""),
            "tag": tag,
        })
    return findings

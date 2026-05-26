#!/usr/bin/env python3
"""
syllabus_outcomes.py — shared, DOM-aware parser for a syllabus's Learning
Outcomes section. Pure functions on HTML (no Canvas API calls).

Consolidates the three code paths that previously each touched syllabus
outcomes (issue #31): syllabus_audit's presence check, rubric_quality_audit's
fetch_course_outcomes fallback, and rubric_recommender (which imports the
latter). The old fallback matched a learning-outcome *marker* per line, which
captured the section STEM ("By the end of this course you will be able to:")
and unrelated deadline sentences ("…Slack invite by the end of Week 1") while
missing every real, verb-first outcome (issue #30).

Real CLOs are written as **[heading/stem] + [list of verb-first items]**. The
markers identify the stem; the list ITEMS are the outcomes. So this parser:
  1. locates the outcomes section by its heading or stem (the anchor),
  2. collects the <li> items that follow it, up to the next heading,
  3. treats the stem/heading as a delimiter — never as an outcome,
  4. falls back to verb-first lines only when there is no list.

Public API:
  detect_outcomes_section(html) -> dict | None   # "is there an outcomes section?"
  extract_outcomes(html)        -> list[str]     # the outcome items themselves
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

# A heading that introduces outcomes (h1-h6 or a bold/para acting as one).
_HEADING_RE = re.compile(
    r"\b(?:(?:course|student|program)\s+)?learning\s+outcomes?\b"
    r"|\bcourse\s+outcomes?\b"
    r"|\b(?:learning|course)\s+objectives?\b"
    r"|\bstudent\s+learning\s+outcomes?\b",
    re.IGNORECASE,
)

# A stem that precedes the list ("By the end of this course you will be able to:").
_STEM_RE = re.compile(
    r"(?:by\s+the\s+end\s+of|upon\s+(?:completion|finishing)|after\s+completing)"
    r".{0,80}?(?:will\s+be\s+able|you\s+will|students?\s+will|learners?\s+will)"
    r"|(?:students?|learners?|you)\s+will\s+be\s+able\s+to\s*:?\s*$"
    r"|will\s+be\s+able\s+to\s*:\s*$",
    re.IGNORECASE,
)

# Observable / Bloom verbs — used ONLY for the no-list fallback (verb-first lines).
_OBSERVABLE_VERBS = {
    # remember/understand
    "define", "describe", "explain", "identify", "list", "label", "name", "state",
    "summarize", "classify", "discuss", "report", "review", "recognize",
    # apply
    "apply", "implement", "demonstrate", "use", "solve", "operate", "execute",
    "perform", "administer", "calculate", "illustrate", "interpret", "prepare",
    # analyze
    "analyze", "compare", "contrast", "differentiate", "examine", "distinguish",
    "categorize", "diagram", "investigate", "test",
    # evaluate
    "evaluate", "assess", "argue", "defend", "judge", "justify", "critique",
    "appraise", "recommend", "determine",
    # create
    "create", "design", "build", "construct", "develop", "produce", "compose",
    "formulate", "plan", "generate", "model",
}

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_MIN_ITEM_LEN = 10
_MAX_ITEMS = 40


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _looks_like_heading(el) -> bool:
    """True if `el` is a heading-ish element whose text introduces outcomes."""
    if el.name in _HEADING_TAGS:
        return bool(_HEADING_RE.search(el.get_text(" ", strip=True)))
    # A short bold/strong run acting as a heading (common in pasted syllabi).
    if el.name in ("strong", "b"):
        t = el.get_text(" ", strip=True)
        return len(t) <= 60 and bool(_HEADING_RE.search(t))
    return False


def _find_anchor(soup: BeautifulSoup):
    """Return (element, kind) for the outcomes-section anchor, or (None, None).
    Prefers a heading; falls back to a stem element."""
    # Pass 1: a heading that names outcomes.
    for el in soup.find_all(_HEADING_TAGS + ("strong", "b")):
        if _looks_like_heading(el):
            return el, "heading"
    # Pass 2: a stem line ("...will be able to:") in a paragraph/list-intro.
    for el in soup.find_all(["p", "div", "li", "span"]):
        t = el.get_text(" ", strip=True)
        if t and _STEM_RE.search(t):
            return el, "stem"
    return None, None


def _li_own_text(li) -> str:
    """Text of an <li> excluding any nested <li> (avoids parent/child double-count)."""
    if li.find("li") is not None:
        return ""  # container li — its leaves are collected separately
    return _clean(li.get_text(" ", strip=True))


def _collect_after(anchor) -> list[str]:
    """Walk document order after `anchor`, collecting outcome items until the
    next (non-outcomes) heading. Prefers <li> items; falls back to verb-first
    lines when no list is present in the window."""
    li_items: list[str] = []
    text_lines: list[str] = []

    for el in anchor.find_all_next():
        # Stop at the next real heading that ISN'T another outcomes heading.
        if el.name in _HEADING_TAGS and not _looks_like_heading(el):
            break
        if el.name == "li":
            t = _li_own_text(el)
            if len(t) >= _MIN_ITEM_LEN:
                li_items.append(t)
        elif el.name in ("p", "div"):
            # Candidate verb-first line for the no-list fallback.
            t = _clean(el.get_text(" ", strip=True))
            if t:
                text_lines.append(t)
        if len(li_items) >= _MAX_ITEMS:
            break

    if li_items:
        # De-dup preserving order.
        seen, out = set(), []
        for t in li_items:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    # No list — fallback to verb-first paragraph lines (excludes the stem,
    # which does not start with an observable verb).
    out = []
    for line in text_lines:
        if _STEM_RE.search(line):
            continue
        first = re.split(r"[\s,:]", line, 1)[0].lower().strip("•-–*0123456789.) ")
        if first in _OBSERVABLE_VERBS and len(line) >= _MIN_ITEM_LEN:
            out.append(line)
        if len(out) >= _MAX_ITEMS:
            break
    return out


def detect_outcomes_section(html: str) -> dict | None:
    """Is there a Learning Outcomes section? Returns {anchor_text, kind} or None.
    DOM-aware: matches a heading or a stem, not an arbitrary keyword occurrence."""
    if not html or not html.strip():
        return None
    soup = BeautifulSoup(html, "lxml")
    anchor, kind = _find_anchor(soup)
    if anchor is None:
        return None
    return {"anchor_text": _clean(anchor.get_text(" ", strip=True))[:120], "kind": kind}


def extract_outcomes(html: str) -> list[str]:
    """The outcome items under the outcomes heading/stem. Empty list if no
    outcomes section is found or no items follow it. Treats the stem/heading
    as a delimiter, never as an outcome (fixes #30)."""
    if not html or not html.strip():
        return []
    soup = BeautifulSoup(html, "lxml")
    anchor, _ = _find_anchor(soup)
    if anchor is None:
        return []
    return _collect_after(anchor)

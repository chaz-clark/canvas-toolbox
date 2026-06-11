#!/usr/bin/env python3
"""
accessibility_audit.py — read-only WCAG 2.1 AA audit of Canvas course content.

╔════════════════════════════════════════════════════════════════════════════╗
║ LEGAL DISCLAIMER — READ FIRST                                              ║
║                                                                            ║
║ This tool ASSISTS with WCAG 2.1 AA review. It does NOT certify compliance, ║
║ does NOT guarantee it flags every violation, and does NOT replace          ║
║ comprehensive accessibility testing.                                       ║
║                                                                            ║
║ Specifically, this tool:                                                   ║
║   - Catches statically-detectable HTML patterns (a defined subset of       ║
║     WCAG checks listed in WHAT IT CHECKS below)                            ║
║   - Cannot verify runtime accessibility (keyboard navigation, focus order, ║
║     dynamic content, JavaScript-driven interactions)                       ║
║   - Cannot verify accessibility on EXTERNAL services (YouTube captions,    ║
║     embedded LTI tool content, third-party documents)                      ║
║   - Cannot replace manual testing with assistive technology (screen        ║
║     readers, keyboard-only navigation, voice control)                      ║
║                                                                            ║
║ Operators retain full responsibility for accessibility compliance.         ║
║ Findings here are REVIEW PROMPTS, not a compliance certificate. For full   ║
║ WCAG 2.1 AA coverage, also run UDoIt (BYUI) / Siteimprove / EquidoxScan /  ║
║ equivalent + manual testing with assistive technology + user testing with  ║
║ disability community representatives where possible.                       ║
║                                                                            ║
║ This disclaimer appears in every report this tool generates.               ║
╚════════════════════════════════════════════════════════════════════════════╝

Closes BYUI Course Design Standard 6.3 (Web Accessibility), which is a LEGAL
requirement for higher-ed accessibility in the US (Section 504, ADA Title II,
WCAG 2.1 AA per the DOJ's 2024 rule for state/local government entities).

WHAT IT CHECKS (covers BOTH sensory AND cognitive/learning accessibility)

  SENSORY (vision, hearing) — Level A + AA:
    1. IMAGES MISSING ALT-TEXT          (WCAG 1.1.1 Non-text Content)
       Every <img> must have a non-empty alt attribute, OR an empty
       alt="" when the image is decorative.
    2. VIDEOS WITHOUT CAPTIONING INDICATOR  (WCAG 1.2.2 Captions)
       <iframe> embeds pointing at YouTube / Vimeo / Kaltura / Canvas
       Studio: flagged for caption verification (can't programmatically
       verify external-service captions).
    3. VIDEOS WITHOUT TRANSCRIPT LINK   (WCAG 1.2.3 Audio Description /
                                         Media Alternative)
       Detect a "transcript" link/text near each video embed. Transcripts
       benefit deaf/HoH users AND learning-disability students who need
       to read at their own pace OR translate content.
    4. NON-DESCRIPTIVE LINK TEXT        (WCAG 2.4.4 Link Purpose in Context)
       Empty / "click here" / "read more" / bare URLs / single character.

  COGNITIVE / LEARNING DISABILITIES — Level A + AA + AAA:
    5. HEADING HIERARCHY SKIPS          (WCAG 1.3.1 Info and Relationships)
       Skipped heading levels (h1→h3) break screen-reader navigation AND
       cognitive structure of the page.
    6. DOCUMENT LANGUAGE MISSING        (WCAG 3.1.1 Language of Page)
       The `lang` attribute lets assistive tech pronounce content
       correctly. Canvas-served HTML often inherits course language but
       per-page <html lang> can be missing in embedded content.
    7. READING LEVEL HIGHER THAN TARGET (WCAG 3.1.5 Reading Level — AAA)
       Flesch-Kincaid grade-level estimation. Content above the
       configurable target (default: 14 = college sophomore) is flagged as
       review-worthy. Helps learning-disability + ESL + cognitive-
       accessibility users. AAA-level; advisory, not auto-fail.
    8. COLOR-ONLY SIGNALING              (WCAG 1.4.1 Use of Color)
       Heuristic: detects inline-styled colored text (red/green) with
       meaning-laden words ("required" / "warning" / "important") and no
       non-color indicator (asterisk, "*", or text equivalent). Critical
       for color-blind users.
    9. DISTRACTING / AUTO-PLAYING / AUTO-REFRESHING CONTENT
                                         (WCAG 2.2.1 + 2.2.2)
       - `<marquee>` tag (deprecated; flag as critical)
       - `autoplay` attribute on `<video>` or `<audio>`
       - `<meta http-equiv="refresh">` auto-refresh
       - Animated `.gif` images (heuristic on file extension — surface
         for review since some are intentional/important)
       All compromise focus + cognitive accessibility.

OUT OF SCOPE (operator MUST run UDoIt / Siteimprove / equivalent + manual
testing for the full picture — see the disclaimer at the top):

  - Color contrast computation (WCAG 1.4.3) — requires CSS parsing +
    contrast-ratio math; would need to parse Canvas themed styles too
  - Table accessibility (WCAG 1.3.1) — <th> with scope, captions, complex
    headers
  - Form labels (WCAG 1.3.1, 4.1.2) — embedded forms
  - Keyboard accessibility (WCAG 2.1.1) — runtime
  - Focus indicators (WCAG 2.4.7) — runtime
  - Screen reader compatibility (full ARIA review) — runtime / manual
  - User testing with disabled community members — irreplaceable

WHERE IT LOOKS

  - Course syllabus body (GET /courses/:id?include[]=syllabus_body)
  - All published Canvas pages (GET /courses/:id/pages, then per-page body)
  - All published assignment descriptions
    (GET /courses/:id/assignments, body in `description`)

  The audit surfaces a per-violation list with surface location + sample
  HTML snippet so the operator can navigate to the exact spot to fix.

ENDPOINTS (all GET, read-only):
  GET /courses/:id?include[]=syllabus_body                       (syllabus)
  GET /courses/:id?include[]=total_students                      (safety guard)
  GET /courses/:id/blueprint_subscriptions                       (safety guard)
  GET /courses/:id/pages                                         (page list)
  GET /courses/:id/pages/:url                                    (per-page content)
  GET /courses/:id/assignments                                   (with descriptions)

EXIT CODES
  0  no violations
  1  violations present
  2  configuration error

USAGE
  uv run python canvas_toolbox/lib/tools/accessibility_audit.py --course-id 402262
  uv run python canvas_toolbox/lib/tools/accessibility_audit.py --target CANVAS_SANDBOX_ID
  uv run python canvas_toolbox/lib/tools/accessibility_audit.py --course-id 402262 \\
    --skip-pages --report /tmp/itm327_accessibility.md
  uv run python canvas_toolbox/lib/tools/accessibility_audit.py --course-id 402262 \\
    --emit-json | jq '.findings.images_missing_alt'

ANCHORS
  - course_design_standards_knowledge.md standard 6.3 (Web Accessibility — the
    institutional anchor; this tool closes the named OPEN gap)
  - WCAG 2.1 AA: https://www.w3.org/TR/WCAG21/

PAIRS WITH
  - course_audit.py (umbrella — could consume this tool's JSON for the
    per-standard accessibility roll-up)
  - syllabus_audit.py (the syllabus's accessibility findings show up here too)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

import canvas_course_guard as guard
from __toolbox_version__ import __version__

# BeautifulSoup is already a canvas-toolbox dependency
from bs4 import BeautifulSoup

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url
_TIMEOUT = 30

# Non-descriptive link-text patterns (lowercased + stripped)
_NON_DESCRIPTIVE_LINK_TEXTS = {
    "click here", "here", "read more", "more", "link", "this",
    "this link", "click", "go", "go here", "view", "view this",
    "more info", "info", "details", "see", "see here", "see more",
    "learn more", "read", "click for more",
}
# Pattern: bare URL as link text (e.g., <a>https://...</a>)
_BARE_URL_RE = re.compile(r"^\s*https?://", re.I)
# Pattern: link text is single character, punctuation, or empty
_PUNCT_OR_EMPTY_RE = re.compile(r"^[\s\W_]*$")

# Video embed domains we check for captioning indicators
_VIDEO_EMBED_DOMAINS = {
    "youtube.com", "youtu.be", "youtube-nocookie.com",
    "vimeo.com", "player.vimeo.com",
    "kaltura.com", "kaf.kaltura.com",
    "byui.instructuremedia.com", "instructuremedia.com",  # Canvas Studio
    "echo360.com", "echo360.org",
    "panopto.com",
}


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(path: str, params: dict | None = None) -> object:
    url = f"{CANVAS_BASE_URL}/api/v1{path}"
    try:
        r = requests.get(url, headers=_headers(), params=params or {}, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"WARN: GET {path} failed ({type(e).__name__}): {e}", file=sys.stderr)
        return None


def _get_paged(path: str, params: dict | None = None) -> list:
    out: list = []
    url = f"{CANVAS_BASE_URL}/api/v1{path}"
    base_params = {**(params or {}), "per_page": 100}
    while url:
        try:
            r = requests.get(url, headers=_headers(),
                             params=base_params if "?" not in url else None,
                             timeout=_TIMEOUT)
            r.raise_for_status()
            page = r.json()
            if isinstance(page, list):
                out.extend(page)
            else:
                return [page]
            link_hdr = r.headers.get("Link", "")
            m = re.search(r'<([^>]+)>;\s*rel="next"', link_hdr)
            url = m.group(1) if m else None
            base_params = None
        except Exception as e:
            print(f"WARN: GET {path} paged failed ({type(e).__name__}): {e}", file=sys.stderr)
            break
    return out


# ---------------------------------------------------------------------------
# The four checks (each runs over one HTML body; returns a list of findings)
# ---------------------------------------------------------------------------

def check_images_alt(soup: BeautifulSoup, surface_label: str) -> list[dict]:
    findings = []
    for img in soup.find_all("img"):
        alt = img.get("alt")
        src = img.get("src", "")
        # Snippet for the operator — first 100 chars of the img tag
        snippet = str(img)[:200]
        if alt is None:
            # No alt attribute at all — CRITICAL violation (WCAG 1.1.1 A)
            findings.append({
                "surface": surface_label,
                "violation": "image_missing_alt",
                "severity": "CRITICAL",
                "wcag": "1.1.1",
                "src": src,
                "snippet": snippet,
                "note": "No alt attribute. Add alt='descriptive text' for content images or alt='' for decorative.",
            })
        elif alt == "":
            # Empty alt — might be decorative-correct OR might be missing.
            # Flag for review with lower severity (operator decides if decorative).
            findings.append({
                "surface": surface_label,
                "violation": "image_empty_alt_review",
                "severity": "REVIEW",
                "wcag": "1.1.1",
                "src": src,
                "snippet": snippet,
                "note": "Empty alt — OK if decorative; needs descriptive alt if conveying content.",
            })
    return findings


def check_video_embeds(soup: BeautifulSoup, surface_label: str) -> list[dict]:
    findings = []
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "")
        if not src:
            continue
        # Match against known video-embed domains
        is_video = any(domain in src.lower() for domain in _VIDEO_EMBED_DOMAINS)
        if not is_video:
            continue
        findings.append({
            "surface": surface_label,
            "violation": "video_embed_review_captions",
            "severity": "REVIEW",
            "wcag": "1.2.2",
            "src": src,
            "snippet": str(iframe)[:200],
            "note": "Video embed detected. Verify captions are present on the external service. "
                    "Cannot be programmatically confirmed by this tool.",
        })
    # Also check <video> elements (rare in Canvas but legal)
    for video in soup.find_all("video"):
        # If has <track kind="captions"> child, OK
        has_captions = bool(video.find("track", kind="captions"))
        snippet = str(video)[:200]
        if not has_captions:
            findings.append({
                "surface": surface_label,
                "violation": "video_no_track_element",
                "severity": "CRITICAL",
                "wcag": "1.2.2",
                "src": video.get("src", ""),
                "snippet": snippet,
                "note": "<video> element without <track kind='captions'> child. Add captions.",
            })
    return findings


def check_link_text(soup: BeautifulSoup, surface_label: str) -> list[dict]:
    findings = []
    for a in soup.find_all("a"):
        text = (a.get_text() or "").strip().lower()
        href = a.get("href", "")
        # Skip anchors without href (e.g., named anchors)
        if not href:
            continue
        # Skip in-page anchors (less critical)
        if href.startswith("#"):
            continue
        violation = None
        if not text or _PUNCT_OR_EMPTY_RE.match(text):
            violation = "link_text_empty_or_punctuation"
        elif text in _NON_DESCRIPTIVE_LINK_TEXTS:
            violation = "link_text_non_descriptive"
        elif _BARE_URL_RE.match(text):
            # Bare URL as link text — accessibility issue for screen readers
            violation = "link_text_bare_url"
        elif len(text) == 1:
            violation = "link_text_single_character"
        if violation:
            findings.append({
                "surface": surface_label,
                "violation": violation,
                "severity": "CRITICAL",
                "wcag": "2.4.4",
                "href": href,
                "text": (a.get_text() or "").strip()[:80],
                "snippet": str(a)[:200],
                "note": "Link text should describe the destination/action in context. "
                        "Avoid 'click here', 'read more', bare URLs.",
            })
    return findings


def check_heading_hierarchy(soup: BeautifulSoup, surface_label: str) -> list[dict]:
    """Check heading levels don't skip (h1→h3 = skip)."""
    findings = []
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    if not headings:
        return findings  # No headings is its own check, not run here
    prev_level = 0
    for h in headings:
        try:
            level = int(h.name[1])
        except (TypeError, ValueError):
            continue
        if prev_level == 0:
            # First heading — if it's not h1, soft signal (Canvas page title is usually outside body)
            if level > 2:
                findings.append({
                    "surface": surface_label,
                    "violation": "heading_first_level_too_deep",
                    "severity": "REVIEW",
                    "wcag": "1.3.1",
                    "text": h.get_text().strip()[:80],
                    "level": f"h{level}",
                    "snippet": str(h)[:200],
                    "note": f"First heading in body is h{level}. Canvas page titles are usually h2 — "
                            f"verify the heading-level entry point is sane.",
                })
        else:
            if level > prev_level + 1:
                findings.append({
                    "surface": surface_label,
                    "violation": "heading_level_skipped",
                    "severity": "HIGH",
                    "wcag": "1.3.1",
                    "text": h.get_text().strip()[:80],
                    "level": f"h{level}",
                    "prev_level": f"h{prev_level}",
                    "snippet": str(h)[:200],
                    "note": f"Heading skipped from h{prev_level} → h{level}. "
                            f"Add intermediate level(s) or restructure.",
                })
        prev_level = level
    return findings


# ---------------------------------------------------------------------------
# Cognitive / learning-accessibility checks (added per operator direction
# 2026-06-10: WCAG aid for learning-impaired users)
# ---------------------------------------------------------------------------

_VOWELS = "aeiouy"


def _count_syllables(word: str) -> int:
    """Heuristic syllable counter (accurate within ~10-15% for English).

    Used for Flesch-Kincaid grade-level estimation. Not perfect (e.g.,
    'fire' = 1 actual / counted; 'diamond' = 3 actual / heuristic counts 2)
    but good enough for the document-level average we need.
    """
    word = word.lower()
    if len(word) <= 3:
        return 1
    if word.endswith("e") and not word.endswith("le"):
        word = word[:-1]
    count = 0
    prev_was_vowel = False
    for ch in word:
        is_vowel = ch in _VOWELS
        if is_vowel and not prev_was_vowel:
            count += 1
        prev_was_vowel = is_vowel
    return max(1, count)


_SENTENCE_END_RE = re.compile(r"[.!?]+")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def _flesch_kincaid_grade(text: str) -> tuple[float, int, int, int]:
    """Compute Flesch-Kincaid grade level. Returns (grade, words, sentences, syllables)."""
    sentences = [s for s in _SENTENCE_END_RE.split(text) if s.strip()]
    words = _WORD_RE.findall(text)
    if not sentences or not words:
        return (0.0, 0, 0, 0)
    syllables = sum(_count_syllables(w) for w in words)
    n_words = len(words)
    n_sentences = len(sentences)
    grade = (0.39 * (n_words / n_sentences)) + (11.8 * (syllables / n_words)) - 15.59
    return (max(0.0, grade), n_words, n_sentences, syllables)


def check_reading_level(soup: BeautifulSoup, surface_label: str,
                        target_grade: float, min_words: int = 100) -> list[dict]:
    """Compute Flesch-Kincaid grade level on the page's prose; flag if higher than target."""
    text = soup.get_text(separator=" ")
    grade, n_words, n_sentences, n_syllables = _flesch_kincaid_grade(text)
    if n_words < min_words:
        return []  # Too little prose to estimate meaningfully
    if grade <= target_grade:
        return []
    return [{
        "surface": surface_label,
        "violation": "reading_level_high",
        "severity": "REVIEW",
        "wcag": "3.1.5",
        "grade_estimate": round(grade, 1),
        "target_grade": target_grade,
        "word_count": n_words,
        "sentence_count": n_sentences,
        "snippet": "",
        "note": f"Flesch-Kincaid grade level estimate: {grade:.1f} (target ≤{target_grade}). "
                f"High reading level can exclude learning-disability + ESL + cognitively-"
                f"impaired users. Plain-language revision or a simplified summary at the top "
                f"of the page can mitigate. AAA-level (Reading Level); advisory.",
    }]


def check_video_transcripts(soup: BeautifulSoup, surface_label: str) -> list[dict]:
    """For each video embed, check if a 'transcript' link/text exists in the same page."""
    findings: list[dict] = []
    iframes = soup.find_all("iframe")
    video_iframes = [
        ifr for ifr in iframes
        if ifr.get("src") and any(d in ifr.get("src", "").lower() for d in _VIDEO_EMBED_DOMAINS)
    ]
    if not video_iframes:
        return []
    # Look for "transcript" anywhere in the page text — operator-best-practice
    # is to provide a transcript link or downloadable file near each video.
    page_text = soup.get_text(separator=" ").lower()
    has_transcript_indicator = "transcript" in page_text
    if has_transcript_indicator:
        return []
    # No transcript-keyword anywhere → flag each video for transcript review
    for ifr in video_iframes:
        findings.append({
            "surface": surface_label,
            "violation": "video_no_transcript_link",
            "severity": "REVIEW",
            "wcag": "1.2.3",
            "src": ifr.get("src", ""),
            "snippet": str(ifr)[:200],
            "note": "Video embed without any 'transcript' keyword on the page. Transcripts "
                    "benefit deaf/HoH users AND learning-disability/ESL students who need to "
                    "read at their own pace. Add a transcript link or downloadable file near "
                    "the video.",
        })
    return findings


def check_document_language(soup: BeautifulSoup, surface_label: str) -> list[dict]:
    """Check for lang attribute on <html> or <body>."""
    # Canvas page bodies are usually fragments without <html>, so check <body> or top wrapper
    has_lang = False
    html_tag = soup.find("html")
    body_tag = soup.find("body")
    for tag in (html_tag, body_tag):
        if tag and tag.get("lang"):
            has_lang = True
            break
    # If the soup has no html/body wrapper (likely — Canvas serves fragments), check the
    # top-level element if any
    if not has_lang and not html_tag and not body_tag:
        # Iterate immediate children; if any top-level div has lang, count it
        for child in soup.find_all(True, recursive=False):
            if child.get("lang"):
                has_lang = True
                break
    if has_lang:
        return []
    # Canvas-page-level: lang missing on the fragment isn't necessarily a violation —
    # the parent course's `default_view` HTML may provide it. Surface as REVIEW.
    return [{
        "surface": surface_label,
        "violation": "document_language_missing",
        "severity": "REVIEW",
        "wcag": "3.1.1",
        "snippet": "",
        "note": "No `lang` attribute on the page fragment. Canvas usually inherits from the "
                "course-level HTML, but explicit `lang` on embedded content (especially "
                "non-English passages) helps assistive tech pronunciation. Verify the "
                "course's default language is set + any non-default-language passages have "
                "explicit `lang` attributes.",
    }]


_COLOR_SIGNAL_RE = re.compile(
    r"color\s*:\s*(red|#[fF]{2}[0-9a-fA-F]{2}[0-9a-fA-F]{2}|#[fF]00|"
    r"green|#0[fF]{2}[0-9a-fA-F]{2}|#0[fF]0|"
    r"orange|yellow|#[fF]{2}[a-fA-F]+00|"
    r"rgb\s*\(\s*(255|2[3-5]\d)\s*,\s*[0-9]+\s*,\s*[0-9]+\s*\))",
    re.I,
)
_MEANING_WORD_RE = re.compile(
    r"\b(required|warning|important|critical|note|caution|attention|do not|don't|must|alert|"
    r"forbidden|prohibited|never|always|deadline)\b",
    re.I,
)
_INDICATOR_RE = re.compile(r"(\*|!|REQUIRED|WARNING|IMPORTANT|CAUTION|NOTE:|⚠)", re.I)


def check_color_only_signaling(soup: BeautifulSoup, surface_label: str) -> list[dict]:
    """Detect colored text with meaning-laden words but no non-color indicator.

    Heuristic: find any element with inline `style` containing a "warning-y" color +
    text containing a meaning-word + no asterisk/REQUIRED/etc. as a fallback indicator.
    """
    findings: list[dict] = []
    for el in soup.find_all(style=True):
        style = el.get("style", "")
        if not _COLOR_SIGNAL_RE.search(style):
            continue
        text = el.get_text() or ""
        if not _MEANING_WORD_RE.search(text):
            continue
        # Has color signal + meaning word. Now check for a non-color indicator.
        if _INDICATOR_RE.search(text):
            continue
        findings.append({
            "surface": surface_label,
            "violation": "color_only_signaling",
            "severity": "HIGH",
            "wcag": "1.4.1",
            "snippet": str(el)[:200],
            "text": text.strip()[:120],
            "note": "Colored text used to signal meaning ('required', 'warning', 'important') "
                    "without a non-color indicator (e.g., '*', 'REQUIRED:', '⚠'). Color-blind "
                    "users will miss the signal. Add a textual indicator alongside the color.",
        })
    return findings


def check_distracting_elements(soup: BeautifulSoup, surface_label: str) -> list[dict]:
    """Detect distracting / auto-playing / auto-refreshing elements."""
    findings: list[dict] = []
    # 1. <marquee> tag — deprecated but flag if present
    for m in soup.find_all("marquee"):
        findings.append({
            "surface": surface_label,
            "violation": "distracting_marquee",
            "severity": "CRITICAL",
            "wcag": "2.2.2",
            "snippet": str(m)[:200],
            "note": "<marquee> is deprecated AND violates WCAG 2.2.2 (moving content with no "
                    "pause/stop control). Replace with static text.",
        })
    # 2. autoplay attribute on <video> or <audio>
    for media in soup.find_all(["video", "audio"]):
        if media.get("autoplay") is not None:
            findings.append({
                "surface": surface_label,
                "violation": "distracting_autoplay",
                "severity": "HIGH",
                "wcag": "2.2.2",
                "snippet": str(media)[:200],
                "tag": media.name,
                "note": f"<{media.name} autoplay> violates WCAG 2.2.2 if it plays for >5 seconds "
                        f"without a pause/stop control. Remove autoplay or provide explicit "
                        f"controls. Auto-playing media also disorients screen-reader users.",
            })
    # 3. <meta http-equiv="refresh"> — auto-refresh page
    for meta in soup.find_all("meta", attrs={"http-equiv": re.compile(r"^refresh$", re.I)}):
        findings.append({
            "surface": surface_label,
            "violation": "distracting_meta_refresh",
            "severity": "HIGH",
            "wcag": "2.2.1",
            "snippet": str(meta)[:200],
            "note": "<meta http-equiv='refresh'> auto-refreshes the page. Violates WCAG 2.2.1 "
                    "(Timing Adjustable) unless the user can disable, adjust, or extend the "
                    "timing. Remove or convert to an opt-in mechanism.",
        })
    # 4. Animated .gif images (heuristic on extension)
    for img in soup.find_all("img"):
        src = (img.get("src") or "").lower()
        if src.endswith(".gif") or ".gif?" in src or ".gif#" in src:
            findings.append({
                "surface": surface_label,
                "violation": "distracting_animated_gif_review",
                "severity": "REVIEW",
                "wcag": "2.2.2",
                "snippet": str(img)[:200],
                "src": img.get("src", ""),
                "note": "Image with .gif extension may be animated. Animated GIFs that loop > "
                        "5 seconds with no pause control violate WCAG 2.2.2. Verify: if static, "
                        "no action; if animated and >5s, replace with a static image OR add "
                        "pause/stop control OR convert to <video> with controls.",
            })
    return findings


def audit_html(html: str, surface_label: str, target_grade: float) -> list[dict]:
    """Run all checks against one HTML body. Returns a flat list of findings."""
    if not html or not html.strip():
        return []
    soup = BeautifulSoup(html, "html.parser")
    findings: list[dict] = []
    # Sensory checks
    findings += check_images_alt(soup, surface_label)
    findings += check_video_embeds(soup, surface_label)
    findings += check_video_transcripts(soup, surface_label)
    findings += check_link_text(soup, surface_label)
    # Cognitive / learning-accessibility checks
    findings += check_heading_hierarchy(soup, surface_label)
    findings += check_document_language(soup, surface_label)
    findings += check_reading_level(soup, surface_label, target_grade)
    findings += check_color_only_signaling(soup, surface_label)
    findings += check_distracting_elements(soup, surface_label)
    return findings


# ---------------------------------------------------------------------------
# The audit (orchestrates the surface-walking)
# ---------------------------------------------------------------------------

def audit_course(
    course_id: str,
    skip_syllabus: bool, skip_pages: bool, skip_assignments: bool,
    target_grade: float,
) -> dict:
    course = _get(f"/courses/{course_id}", params={"include[]": "syllabus_body"}) or {}
    if not isinstance(course, dict):
        return {"error": f"Could not load course {course_id}"}
    course_name = course.get("name", "<unknown course>")
    all_findings: list[dict] = []
    surfaces_checked = []

    # Syllabus
    if not skip_syllabus:
        body = course.get("syllabus_body") or ""
        if body:
            print(f"  Auditing syllabus...", file=sys.stderr)
            all_findings += audit_html(body, "syllabus", target_grade)
        surfaces_checked.append("syllabus")

    # Pages
    if not skip_pages:
        pages_list = _get_paged(f"/courses/{course_id}/pages", params={"published": True})
        print(f"  Auditing {len(pages_list)} pages...", file=sys.stderr)
        for p in pages_list:
            page_url = p.get("url")
            if not page_url:
                continue
            page = _get(f"/courses/{course_id}/pages/{page_url}") or {}
            body = page.get("body") or ""
            if body:
                all_findings += audit_html(body, f"page:{page.get('title', page_url)}",
                                           target_grade)
        surfaces_checked.append(f"pages ({len(pages_list)})")

    # Assignments
    if not skip_assignments:
        assignments = _get_paged(f"/courses/{course_id}/assignments")
        published = [a for a in assignments if a.get("workflow_state") == "published"]
        print(f"  Auditing {len(published)} published assignments...", file=sys.stderr)
        for a in published:
            description = a.get("description") or ""
            if description:
                all_findings += audit_html(description,
                                           f"assignment:{a.get('name', a.get('id'))}",
                                           target_grade)
        surfaces_checked.append(f"assignments ({len(published)})")

    # Aggregate by violation type
    by_violation: dict[str, list[dict]] = {}
    for f in all_findings:
        by_violation.setdefault(f["violation"], []).append(f)
    # Aggregate by severity
    by_severity: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "REVIEW": 0}
    for f in all_findings:
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1

    # Verdict
    if by_severity["CRITICAL"] == 0 and by_severity["HIGH"] == 0:
        verdict = "compliant" if by_severity["REVIEW"] == 0 else "compliant_with_review"
    elif by_severity["CRITICAL"] > 0:
        verdict = "non_compliant"
    else:
        verdict = "partial_compliant"

    return {
        "course_name": course_name,
        "course_id": course_id,
        "surfaces_checked": surfaces_checked,
        "findings": all_findings,
        "by_violation": by_violation,
        "by_severity": by_severity,
        "total_findings": len(all_findings),
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_VIOLATION_LABELS = {
    # Sensory
    "image_missing_alt": "Images missing alt-text (WCAG 1.1.1)",
    "image_empty_alt_review": "Images with empty alt — review if decorative (WCAG 1.1.1)",
    "video_embed_review_captions": "Video embeds — verify captioning (WCAG 1.2.2)",
    "video_no_track_element": "Native <video> without <track> captions (WCAG 1.2.2)",
    "video_no_transcript_link": "Video embeds without a transcript on the page (WCAG 1.2.3)",
    "link_text_empty_or_punctuation": "Links with empty / punctuation-only text (WCAG 2.4.4)",
    "link_text_non_descriptive": "Links with non-descriptive text ('click here' etc.) (WCAG 2.4.4)",
    "link_text_bare_url": "Links with bare URL as text (WCAG 2.4.4)",
    "link_text_single_character": "Links with single-character text (WCAG 2.4.4)",
    # Cognitive / learning
    "heading_first_level_too_deep": "First heading deeper than h2 (review — WCAG 1.3.1)",
    "heading_level_skipped": "Heading level skipped (WCAG 1.3.1)",
    "document_language_missing": "Document language attribute missing (WCAG 3.1.1)",
    "reading_level_high": "Reading level above target grade (WCAG 3.1.5 — AAA, advisory)",
    "color_only_signaling": "Color-only meaning signaling (WCAG 1.4.1)",
    "distracting_marquee": "<marquee> deprecated + violates pause control (WCAG 2.2.2)",
    "distracting_autoplay": "Auto-playing media (WCAG 2.2.2)",
    "distracting_meta_refresh": "Auto-refreshing page (WCAG 2.2.1)",
    "distracting_animated_gif_review": "Animated GIF — review if >5s loop (WCAG 2.2.2)",
}


_DISCLAIMER_BLOCK = """> **⚠ DISCLAIMER — READ FIRST.** This audit ASSISTS with WCAG 2.1 AA review.
> It does **NOT** certify compliance, does NOT guarantee it flags every
> violation, and does NOT replace comprehensive accessibility testing.
>
> Specifically, this tool catches statically-detectable HTML patterns at
> the heuristic layer. It cannot verify: runtime accessibility (keyboard
> navigation, focus order, JavaScript-driven interactions); external-service
> content (captions on YouTube, embedded LTI tool accessibility); or screen-
> reader / keyboard-only / voice-control user experience. The reading-level
> + color-only-signaling + distracting-element heuristics may produce false
> positives **and** false negatives.
>
> **Operators retain full responsibility for accessibility compliance.**
> Findings here are review prompts, not a compliance certificate. For full
> WCAG 2.1 AA coverage, also run UDoIt (BYUI) / Siteimprove / EquidoxScan
> / equivalent + manual testing with assistive technology + user testing
> with disability community representatives where possible."""


def _render_markdown(res: dict, ts: str) -> list[str]:
    L: list[str] = []
    L.append(f"# Accessibility Audit (WCAG 2.1 AA) — {res['course_name']}")
    L.append("")
    L.append(_DISCLAIMER_BLOCK)
    L.append("")
    L.append(f"**Course ID:** {res['course_id']}")
    L.append(f"**Generated:** {ts}")
    L.append(f"**Tool:** accessibility_audit.py (canvas-toolbox {__version__})")
    L.append(f"**Standard:** BYUI Course Design Standard 6.3 (Web Accessibility) — "
             "legal requirement under ADA Title II + Section 504; WCAG 2.1 AA")
    L.append("")
    icon = {"compliant": "✅", "compliant_with_review": "✅",
            "partial_compliant": "⚠", "non_compliant": "⛔"}[res["verdict"]]
    L.append(f"**Verdict:** {icon} **{res['verdict']}**")
    L.append("")
    bs = res["by_severity"]
    L.append(f"**Findings:** {res['total_findings']} total — "
             f"⛔ {bs['CRITICAL']} CRITICAL, "
             f"⚠ {bs['HIGH']} HIGH, "
             f"ℹ {bs['REVIEW']} review")
    L.append("")
    L.append(f"**Surfaces checked:** {', '.join(res['surfaces_checked'])}")
    L.append("")
    L.append("> **Scope:** sensory (vision/hearing — alt-text, captions, transcripts, link "
             "text) + cognitive (heading hierarchy, document language, reading level, color-"
             "only signaling, distracting elements). Out of scope: color contrast computation, "
             "table accessibility, form labels, keyboard accessibility, focus indicators, "
             "screen-reader compatibility. **See the disclaimer at top — this is an aid, "
             "not a compliance certificate.**")
    L.append("")

    if res["total_findings"] == 0:
        L.append("## ✅ No findings")
        L.append("")
        L.append("This course passes the 4 v0.1 WCAG 2.1 AA checks. "
                 "Run UDoIt (or equivalent) for the broader compliance check.")
        return L

    # Per-violation summary table
    L.append("## Findings summary by violation type")
    L.append("")
    L.append("| Severity | Violation | Count |")
    L.append("|---|---|---:|")
    severity_order = {"CRITICAL": 0, "HIGH": 1, "REVIEW": 2}
    sev_icon = {"CRITICAL": "⛔", "HIGH": "⚠", "REVIEW": "ℹ"}
    sorted_violations = sorted(
        res["by_violation"].items(),
        key=lambda kv: (severity_order.get(kv[1][0]["severity"], 9), -len(kv[1])),
    )
    for vname, fs in sorted_violations:
        sev = fs[0]["severity"]
        label = _VIOLATION_LABELS.get(vname, vname)
        L.append(f"| {sev_icon[sev]} {sev} | {label} | {len(fs)} |")
    L.append("")

    # Per-violation detail sections
    for vname, fs in sorted_violations:
        sev = fs[0]["severity"]
        label = _VIOLATION_LABELS.get(vname, vname)
        L.append(f"## {sev_icon[sev]} {sev} — {label}")
        L.append("")
        if fs:
            L.append(f"_{fs[0]['note']}_")
            L.append("")
        # Group by surface
        by_surface: dict[str, list[dict]] = {}
        for f in fs:
            by_surface.setdefault(f["surface"], []).append(f)
        for surface_name in sorted(by_surface):
            items = by_surface[surface_name]
            L.append(f"**{surface_name}** ({len(items)} finding{'s' if len(items) > 1 else ''}):")
            for f in items[:10]:  # cap per surface to keep report manageable
                if vname.startswith("image"):
                    L.append(f"- `src=\"{f.get('src', '')[:80]}\"`")
                elif vname.startswith("video"):
                    L.append(f"- `{f.get('src', '')[:80]}`")
                elif vname.startswith("link"):
                    L.append(f"- text: `{f.get('text', '')}` → `{f.get('href', '')[:80]}`")
                elif vname.startswith("heading"):
                    text = f.get('text', '')
                    if 'prev_level' in f:
                        L.append(f"- skip {f['prev_level']} → {f['level']}: `{text}`")
                    else:
                        L.append(f"- {f.get('level', '?')}: `{text}`")
                else:
                    L.append(f"- {f.get('snippet', '')[:150]}")
            if len(items) > 10:
                L.append(f"- _...and {len(items) - 10} more in this surface_")
            L.append("")

    # Audit tag
    L.append("---")
    L.append("")
    L.append("## Audit tag")
    L.append("")
    L.append(f"`accessibility`: **{res['verdict']}** "
             f"(critical={bs['CRITICAL']}, high={bs['HIGH']}, review={bs['REVIEW']})")
    L.append("")
    L.append("**Recommended next step:** for full WCAG 2.1 AA coverage, run UDoIt "
             "(BYUI's accessibility scanner) or equivalent. This tool's v0.1 catches "
             "the 4 highest-leverage statically-checkable issues; UDoIt covers color "
             "contrast, tables, forms, keyboard accessibility, and other dimensions "
             "this tool deliberately doesn't.")
    return L


def _render_json(res: dict, ts: str) -> dict:
    return {
        "tool": "accessibility_audit",
        "version": __version__,
        "generated": ts,
        "_disclaimer": (
            "This audit ASSISTS with WCAG 2.1 AA review. It does NOT certify compliance, "
            "does NOT guarantee it flags every violation, and does NOT replace comprehensive "
            "accessibility testing. Findings are review prompts, not a compliance certificate. "
            "Operators retain full responsibility for accessibility compliance. For full "
            "coverage also run UDoIt / Siteimprove / EquidoxScan / equivalent + manual testing "
            "with assistive technology + user testing with disability community representatives."
        ),
        "course_id": res["course_id"],
        "course_name": res["course_name"],
        "standard": "BYUI Course Design Standard 6.3 — Web Accessibility (WCAG 2.1 AA)",
        "verdict": res["verdict"],
        "accessibility": res["verdict"],
        "summary": {
            "total_findings": res["total_findings"],
            "by_severity": res["by_severity"],
            "surfaces_checked": res["surfaces_checked"],
        },
        "by_violation": {
            vname: {
                "label": _VIOLATION_LABELS.get(vname, vname),
                "severity": fs[0]["severity"],
                "count": len(fs),
            }
            for vname, fs in res["by_violation"].items()
        },
        "findings": res["findings"],
    }


def _write_report(path: Path, body: str) -> None:
    path.write_text(body + "\n", encoding="utf-8")
    print(f"\nReport written to {path}", file=sys.stderr)
    if path.suffix.lower() in (".md", ".markdown"):
        try:
            from _md_to_pdf import render_pair
            render_pair(path)
        except ImportError:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Read-only accessibility audit — WCAG 2.1 AA highest-leverage checks (BYUI Standard 6.3).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--course-id", help="Canvas course id.")
    grp.add_argument("--target", default="CANVAS_COURSE_ID",
                     help="Env var to read the course id from. Default CANVAS_COURSE_ID.")
    ap.add_argument("--report", help=".md path to write the report (with .pdf sibling if Chrome).")
    ap.add_argument("--emit-json", action="store_true",
                    help="Emit JSON to stdout instead of human-readable markdown.")
    ap.add_argument("--skip-syllabus", action="store_true",
                    help="Skip auditing the syllabus body (default: included).")
    ap.add_argument("--skip-pages", action="store_true",
                    help="Skip auditing Canvas pages (default: included).")
    ap.add_argument("--skip-assignments", action="store_true",
                    help="Skip auditing assignment descriptions (default: included).")
    ap.add_argument("--target-grade", type=float, default=14.0,
                    help="Target Flesch-Kincaid grade level (WCAG 3.1.5 reading level). "
                         "Pages above this grade are flagged for review (advisory). "
                         "Default 14.0 = college sophomore. Lower for general-ed; higher for "
                         "graduate. Set to 0 to disable.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Bypass canvas_course_guard advisory for enrolled-course reads.")
    args = ap.parse_args()

    if not CANVAS_API_TOKEN or not CANVAS_BASE_URL:
        print("ERROR: CANVAS_API_TOKEN and CANVAS_BASE_URL must be set in .env.", file=sys.stderr)
        return 2
    course_id = args.course_id or os.environ.get(args.target, "")
    if not course_id:
        print(f"ERROR: course ID not found. Pass --course-id <id> or set {args.target}.",
              file=sys.stderr)
        return 2

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="read", allow_override=args.allow_enrolled, label="audit target")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"Auditing course {course_id}...", file=sys.stderr)
    # target_grade=0 disables the reading-level check; we treat anything <=0 as disabled
    effective_target = args.target_grade if args.target_grade > 0 else 999.0
    res = audit_course(course_id,
                       skip_syllabus=args.skip_syllabus,
                       skip_pages=args.skip_pages,
                       skip_assignments=args.skip_assignments,
                       target_grade=effective_target)

    if "error" in res:
        print(f"ERROR: {res['error']}", file=sys.stderr)
        return 2

    if args.emit_json:
        body = json.dumps(_render_json(res, ts), indent=2, ensure_ascii=False)
        print(body)
        if args.report:
            _write_report(Path(args.report), body)
    else:
        lines = _render_markdown(res, ts)
        print("\n".join(lines))
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    return 0 if res["total_findings"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

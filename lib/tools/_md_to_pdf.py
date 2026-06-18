"""Shared MD → PDF renderer for canvas-toolbox audit/report tools.

Uses Chrome headless to render an HTML version of the report to PDF — chosen
because it works on macOS without native deps (weasyprint and xhtml2pdf both
require cairo / pango / pycairo, which aren't pre-installed on most operator
Macs; Chrome ships with macOS development environments and most operators
have it installed already).

The function gracefully degrades: if Chrome isn't found, it warns and returns
None, leaving the MD as the only artifact (operators can render manually via
any markdown-to-PDF tool).

Usage:
    from _md_to_pdf import render_pair
    pdf_path = render_pair(Path("report.md"), title="Course Audit")
    # → writes report.html (intermediate, auto-removed) and report.pdf
    # → returns Path("report.pdf") or None on failure
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


# Chrome binary candidates by platform
_CHROME_PATHS_DARWIN = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
_CHROME_PATHS_LINUX = [
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/snap/bin/chromium",
    "/usr/bin/microsoft-edge",
]
_CHROME_PATHS_WIN32 = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def find_chrome() -> str | None:
    """Locate a Chromium-family browser binary. Returns absolute path or None."""
    if sys.platform == "darwin":
        candidates = _CHROME_PATHS_DARWIN
    elif sys.platform == "win32":
        candidates = _CHROME_PATHS_WIN32
    else:
        candidates = _CHROME_PATHS_LINUX
    for path in candidates:
        if Path(path).is_file():
            return path
    # Final fallback: $PATH lookup
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        located = shutil.which(name)
        if located:
            return located
    return None


_DEFAULT_CSS = """
@page { size: Letter; margin: 0.55in 0.6in; }
body { font-family: -apple-system, Helvetica, Arial, sans-serif; font-size: 9.5pt;
       line-height: 1.42; color: #222; max-width: 7.2in; margin: 0 auto; }
h1 { font-size: 22pt; color: #1a3556; border-bottom: 2px solid #1a3556;
     padding-bottom: 4px; margin-top: 4px; }
h2 { font-size: 14.5pt; color: #1a3556; border-bottom: 1px solid #ccc;
     padding-bottom: 3px; margin-top: 22px; page-break-after: avoid; }
h3 { font-size: 11.5pt; color: #2a4a6e; margin-top: 16px; page-break-after: avoid;
     background: #f0f4f8; padding: 5px 9px; border-left: 3px solid #2a4a6e;
     border-radius: 2px; }
h4 { font-size: 10.5pt; color: #444; }
table { border-collapse: collapse; width: 100%; margin: 7px 0 14px; font-size: 8.5pt;
        page-break-inside: avoid; }
th, td { border: 1px solid #bbb; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #e8eef5; font-weight: 600; }
tr:nth-child(even) { background: #fafbfd; }
code { background: #f3f3f3; padding: 1px 4px; border-radius: 3px; font-size: 8.5pt;
       font-family: ui-monospace, monospace; }
blockquote { border-left: 3px solid #ccc; padding: 4px 12px; color: #555; margin: 6px 0;
             font-style: italic; font-size: 9pt; background: #fafafa; }
hr { border: none; border-top: 1px solid #ddd; margin: 18px 0; }
strong { color: #1a3556; }
em { color: #666; }
"""


def md_to_html(md_text: str, title: str = "Report", css: str = _DEFAULT_CSS) -> str:
    """Convert markdown text to a fully-styled HTML document string.

    Uses the `markdown` library (pip-installable via uv --with markdown).
    Falls back to a minimal HTML wrapper if `markdown` isn't importable
    (operator can install it via `uv pip install markdown`).
    """
    try:
        import markdown as _md  # noqa: PLC0415
    except ImportError:
        # Minimal fallback — escape HTML and wrap in <pre> so it at least renders
        import html as _html  # noqa: PLC0415
        body = "<pre>" + _html.escape(md_text) + "</pre>"
        return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
                f"<title>{title}</title><style>{css}</style></head><body>"
                f"{body}</body></html>")
    body = _md.markdown(md_text, extensions=["tables", "fenced_code"])
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>{title}</title><style>{css}</style></head><body>"
            f"{body}</body></html>")


def render_pair(md_path: Path, title: str | None = None,
                 css: str | None = None) -> Path | None:
    """Given an existing markdown file, write a sibling .pdf via Chrome headless.

    Args:
        md_path: Path to an existing .md file.
        title: PDF title (HTML <title>). Defaults to the file stem.
        css: Optional CSS string to override the default style.

    Returns:
        Path to the produced .pdf, or None if Chrome wasn't found or render failed.

    Side effects:
        Writes a temporary .html sibling and removes it after the PDF is produced.
        Prints status to stderr (non-blocking — caller can still use the .md).
    """
    if not md_path.is_file():
        print(f"  (skip PDF: source MD not found at {md_path})", file=sys.stderr)
        return None

    chrome = find_chrome()
    if not chrome:
        print(f"  (skip PDF: no Chromium-family browser found — install Chrome / "
              f"Brave / Edge, or render the .md manually)", file=sys.stderr)
        return None

    pdf_path = md_path.with_suffix(".pdf")
    html_path = md_path.with_suffix(".html")

    md_text = md_path.read_text(encoding="utf-8")
    html_doc = md_to_html(md_text, title=title or md_path.stem,
                           css=css or _DEFAULT_CSS)
    html_path.write_text(html_doc, encoding="utf-8")

    try:
        # Run Chrome headless. Filter known-noisy stderr lines.
        result = subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf_path}", f"file://{html_path.resolve()}"],
            capture_output=True, text=True, timeout=60,
        )
        if not pdf_path.is_file():
            print(f"  (PDF render failed; Chrome stderr:\n{result.stderr[:500]})",
                  file=sys.stderr)
            return None
        print(f"  PDF → {pdf_path}", file=sys.stderr)
        return pdf_path
    except subprocess.TimeoutExpired:
        print(f"  (PDF render timed out after 60s — leaving the .md as the only artifact)",
              file=sys.stderr)
        return None
    except Exception as e:
        print(f"  (PDF render failed: {e})", file=sys.stderr)
        return None
    finally:
        # Clean up the intermediate HTML
        try:
            if html_path.is_file():
                html_path.unlink()
        except Exception:
            pass

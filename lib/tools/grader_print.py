#!/usr/bin/env python3
"""Print student work that needs manual review — Word files converted to PDF first.

The TOOL prints; the agent never reads the files. Output is counts and file types,
never file names or contents, so nothing student-identifying enters the transcript.
The instructor reads the paper.

  uv run python lib/tools/grader_print.py --list-printers
  uv run python lib/tools/grader_print.py PATH [PATH ...] --printer "NAME"          # dry run
  uv run python lib/tools/grader_print.py PATH [PATH ...] --printer "NAME" --apply  # print

PATH is a file or a folder (searched recursively). Word/Office files do not print
directly, so each is converted to PDF in a temp folder first (deleted afterward), then
the PDF is sent to the printer.

Converters, in order: LibreOffice (`soffice`, Mac/Windows/Linux) -> Microsoft Word via
PowerShell (Windows) -> `textutil` + Chrome (Mac, no install needed; plainer layout).
Printing: `lp` on Mac/Linux; SumatraPDF on Windows if installed, else the PDF app's
"PrintTo" verb. If nothing can convert or print, the tool says what to install.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env_loader import force_utf8_console  # noqa: E402

PDF_EXT = {".pdf"}
OFFICE_EXT = {".docx", ".doc", ".odt", ".rtf", ".pptx", ".ppt"}
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

_SOFFICE_PATHS = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]
_SUMATRA_PATHS = [
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\SumatraPDF\SumatraPDF.exe"),
]


def _first_existing(names: list[str], paths: list[str]) -> str | None:
    for n in names:
        found = shutil.which(n)
        if found:
            return found
    return next((p for p in paths if Path(p).is_file()), None)


def collect(paths: list[Path]) -> list[Path]:
    """Files under the given paths, sorted, hidden files skipped."""
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out += [f for f in sorted(p.rglob("*"))
                    if f.is_file() and not any(part.startswith(".") for part in f.parts[len(p.parts):])]
        elif p.is_file():
            out.append(p)
    return out


def classify(files: list[Path]) -> tuple[list[Path], list[Path], dict[str, int]]:
    """(pdfs, office files, {extension: count} of unsupported)."""
    pdfs, office, skipped = [], [], {}
    for f in files:
        ext = f.suffix.lower()
        if ext in PDF_EXT:
            pdfs.append(f)
        elif ext in OFFICE_EXT:
            office.append(f)
        else:
            skipped[ext or "(none)"] = skipped.get(ext or "(none)", 0) + 1
    return pdfs, office, skipped


def list_printers() -> list[str]:
    try:
        if IS_WIN:
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "Get-Printer | Select-Object -ExpandProperty Name"],
                               capture_output=True, text=True, timeout=30)
            return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
        r = subprocess.run(["lpstat", "-e"], capture_output=True, text=True, timeout=30)
        return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except (OSError, subprocess.SubprocessError):
        return []


def convert_to_pdf(src: Path, outdir: Path) -> tuple[Path | None, str]:
    """Convert one Office file to PDF in outdir. Returns (pdf or None, reason)."""
    target = outdir / (src.stem + ".pdf")
    soffice = _first_existing(["soffice", "libreoffice"], _SOFFICE_PATHS)
    attempts: list[str] = []
    if soffice:
        try:
            subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir",
                            str(outdir), str(src)], capture_output=True, timeout=180)
            if target.is_file():
                return target, "libreoffice"
        except (OSError, subprocess.SubprocessError):
            pass
        attempts.append("libreoffice failed")
    if IS_WIN:
        ps = ("$w=New-Object -ComObject Word.Application;$w.Visible=$false;"
              f"$d=$w.Documents.Open('{src}',$false,$true);"
              f"$d.ExportAsFixedFormat('{target}',17);$d.Close($false);$w.Quit()")
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, timeout=180)
            if target.is_file():
                return target, "word"
        except (OSError, subprocess.SubprocessError):
            pass
        attempts.append("Word not available")
    if IS_MAC and src.suffix.lower() in {".docx", ".doc", ".rtf", ".odt"}:
        try:
            from _md_to_pdf import find_chrome as _find_chrome
            chrome = _find_chrome()
        except Exception:  # noqa: BLE001
            chrome = None
        if chrome and shutil.which("textutil"):
            html = outdir / (src.stem + ".html")
            try:
                subprocess.run(["textutil", "-convert", "html", "-output", str(html), str(src)],
                               capture_output=True, timeout=120)
                subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                                f"--print-to-pdf={target}", html.as_uri()],
                               capture_output=True, timeout=120)
                html.unlink(missing_ok=True)
                if target.is_file():
                    return target, "textutil+chrome"
            except (OSError, subprocess.SubprocessError):
                pass
        attempts.append("textutil+Chrome failed")
    return None, "; ".join(attempts) or "no converter found (install LibreOffice)"


def print_pdf(pdf: Path, printer: str) -> tuple[bool, str]:
    try:
        if not IS_WIN:
            r = subprocess.run(["lp", "-d", printer, str(pdf)], capture_output=True,
                               text=True, timeout=60)
            return r.returncode == 0, (r.stderr.strip() or "ok")
        sumatra = _first_existing(["SumatraPDF"], _SUMATRA_PATHS)
        if sumatra:
            r = subprocess.run([sumatra, "-print-to", printer, "-silent", str(pdf)],
                               capture_output=True, text=True, timeout=120)
            return r.returncode == 0, "sumatra"
        ps = (f"Start-Process -FilePath '{pdf}' -Verb PrintTo "
              f"-ArgumentList '\"{printer}\"' -PassThru -Wait")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0, "PrintTo (install SumatraPDF if this fails)"
    except (OSError, subprocess.SubprocessError) as e:
        return False, type(e).__name__


def run(paths: list[Path], printer: str | None, apply: bool) -> int:
    files = collect(paths)
    pdfs, office, skipped = classify(files)
    print(f"Found {len(files)} file(s): {len(pdfs)} PDF, {len(office)} Word/Office "
          f"(will convert to PDF), {sum(skipped.values())} unsupported.")
    if skipped:
        print("Unsupported types (not printed): "
              + ", ".join(f"{e} x{n}" for e, n in sorted(skipped.items())))
    if not pdfs and not office:
        return 1
    if not printer:
        print("No --printer given. Use --list-printers to see names.")
        return 1
    known = list_printers()
    if known and printer not in known:
        print(f"Printer {printer!r} not found. Available: {', '.join(known)}")
        return 1
    if not apply:
        print(f"Dry run: would print {len(pdfs) + len(office)} document(s) to {printer!r}. "
              "Re-run with --apply.")
        return 0

    done = failed = 0
    with tempfile.TemporaryDirectory(prefix="cb_print_") as tmp:
        for i, f in enumerate(pdfs + office, 1):
            pdf = f
            if f.suffix.lower() not in PDF_EXT:
                pdf, how = convert_to_pdf(f, Path(tmp))
                if pdf is None:
                    print(f"  [{i}] {f.suffix.lower()} NOT converted: {how}")
                    failed += 1
                    continue
            ok, msg = print_pdf(pdf, printer)
            print(f"  [{i}] {f.suffix.lower()} {'sent' if ok else 'FAILED: ' + msg}")
            done += ok
            failed += not ok
    print(f"Done: {done} sent to {printer!r}, {failed} failed.")
    return 0 if not failed else 1


def main(argv: list[str] | None = None) -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="*", type=Path, help="files or folders to print")
    ap.add_argument("--printer", help="printer name (see --list-printers)")
    ap.add_argument("--list-printers", action="store_true")
    ap.add_argument("--apply", action="store_true", help="actually print (default: dry run)")
    args = ap.parse_args(argv)
    if args.list_printers:
        names = list_printers()
        print("\n".join(names) if names else "No printers found.")
        return 0
    if not args.paths:
        ap.error("give at least one file or folder, or use --list-printers")
    return run(args.paths, args.printer, args.apply)


if __name__ == "__main__":
    sys.exit(main())

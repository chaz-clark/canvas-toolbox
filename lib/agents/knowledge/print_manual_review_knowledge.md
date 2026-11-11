---
name: print_manual_review_knowledge
version: '1.0'
last_updated: '2026-11-11'
description: How the toolkit prints student work for manual review — Word to PDF conversion, printer selection, and per-OS printing behavior and failure modes.
skill_type: knowledge
shape: reference
consumed_by:
- skills/printing
---

# Printing student work for manual review

## Why PDF first
Word files cannot be sent to a printer by a script the way a PDF can: there is no
reliable command-line print for `.docx`. Converting to PDF first gives one predictable
print path on every OS and fixes the layout the instructor sees on paper.

## Conversion paths (tried in order)
| Converter | Platforms | Notes |
|---|---|---|
| LibreOffice `soffice --headless --convert-to pdf` | Mac, Windows, Linux | Best fidelity; free. Recommended install. |
| Microsoft Word via PowerShell COM (`ExportAsFixedFormat`, format 17) | Windows | Needs desktop Word installed; opens read-only. |
| `textutil` then Chrome headless `--print-to-pdf` | Mac | No install, but plainer layout (tables/images may differ). |

## Printing paths
- **Mac/Linux:** `lp -d <printer> file.pdf`. Printer names come from `lpstat -e`.
- **Windows:** SumatraPDF `-print-to "<printer>" -silent`. Without it, PowerShell
  `Start-Process -Verb PrintTo` depends on the default PDF app supporting that verb;
  Edge does not, Adobe Reader usually does. "Microsoft Print to PDF" prompts for a
  save location, so it is not a useful test printer for silent printing.

## FERPA
The tool prints in-process and outputs counts and types only. Converted PDFs live in a
temp folder removed when the run ends. The agent must not read the files; the
instructor reads the paper. The printed pages carry whatever the student file contains.

## Not supported (reported and skipped)
Notebooks, source code, images, spreadsheets. Ask the instructor how to print those.

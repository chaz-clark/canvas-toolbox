---
name: printing
description: Use when the instructor wants student work printed on paper for manual review, alone or alongside the AI grader — "print these submissions", "print the ones that need a manual look", "send them to the printer". Word files do not print directly, so this converts them to PDF first, then prints to a named printer. The tool prints; you never read the files.
---

# Printing student work for manual review

The instructor names a **printer**; `grader_print.py` does the rest. This is a
convenience for paper review, not a grading step: nothing it does reaches a student or
Canvas.

> **FERPA:** you never open, read, or `cat` the files being printed (they are Zone 2).
> The script reads and prints them in-process and reports only counts and file *types*,
> never names or contents. The instructor reads the paper. Keep it that way: do not
> list file names back to the chat.

## Steps

1. **Which work?** A folder (searched recursively) or specific files the instructor
   names, typically the submissions marked for manual review. If they say "the ones
   that need review", ask which students or which folder; do not guess.
2. **Which printer?** Run `uv run python lib/tools/grader_print.py --list-printers` and
   let the instructor pick. Printer names are exact; a wrong one is rejected.
3. **Dry run first:**
   `uv run python lib/tools/grader_print.py <paths> --printer "<name>"` reports how many
   PDFs, how many Word/Office files (to be converted), and any unsupported types.
4. **Confirm the count with the instructor, then** add `--apply`. Printing is physical
   and cannot be undone, so confirm the number of documents and the printer first.
5. Report the tool's final line (sent / failed). If conversions failed, relay the reason.

## Word and Office files

`.docx`, `.doc`, `.odt`, `.rtf`, `.pptx` do not print directly. The tool converts each to
PDF in a temp folder (deleted afterward) and prints the PDF. Converter order:
LibreOffice -> Word via PowerShell (Windows) -> `textutil` + Chrome (Mac; plainer
layout). If none is available it says so: install **LibreOffice** (free, works on Mac
and Windows) and re-run.

## Printing on each OS

- **Mac / Linux:** uses `lp -d <printer>`.
- **Windows:** uses SumatraPDF if installed (silent, reliable); otherwise the PDF app's
  "PrintTo" action, which depends on the default PDF viewer. If printing fails,
  install SumatraPDF.

Notebooks, code, images and other types are reported as unsupported and skipped; for
those, ask the instructor how they want them printed.

Details and troubleshooting: [`lib/agents/knowledge/print_manual_review_knowledge.md`](../../lib/agents/knowledge/print_manual_review_knowledge.md).

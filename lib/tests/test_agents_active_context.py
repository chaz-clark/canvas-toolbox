"""Guards AGENTS.md → Active Context size (the rotating latest-5 rule).

Active Context is the project's first-read context section. It must stay
current-state-only — the latest few releases — and NOT accumulate into an
append-only release log (that history lives in CHANGELOG.md). Capping the
entry count keeps AGENTS.md readable in one pass by any agent/tool (a 180 KB
AGENTS.md once blew past host-tool read limits — the failure this guards).

When you ship a release: add the new `### ` entry at the top of Active
Context and rotate the oldest out into CHANGELOG.md so the count stays <= 5.

Local enforcement of the threshold proposed upstream in Make-AI-Agents#17.
"""

from pathlib import Path

MAX_ACTIVE_CONTEXT_ENTRIES = 5
AGENTS_MD = Path(__file__).resolve().parents[2] / "AGENTS.md"


def _active_context_entries(text):
    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if ln.strip() == "## Active Context"), None
    )
    assert start is not None, "AGENTS.md is missing its '## Active Context' section"
    entries = []
    for ln in lines[start + 1 :]:
        if ln.startswith("## "):  # next top-level section ends Active Context
            break
        if ln.startswith("### "):
            entries.append(ln)
    return entries


def test_active_context_within_rotating_limit():
    entries = _active_context_entries(AGENTS_MD.read_text(encoding="utf-8"))
    assert len(entries) <= MAX_ACTIVE_CONTEXT_ENTRIES, (
        f"AGENTS.md Active Context has {len(entries)} entries "
        f"(max {MAX_ACTIVE_CONTEXT_ENTRIES}). Rotate the oldest entries into "
        "CHANGELOG.md to keep the first-read context small.\nEntries:\n  "
        + "\n  ".join(entries)
    )

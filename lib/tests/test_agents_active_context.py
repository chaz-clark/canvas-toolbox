"""Guards AGENTS.md size + Active Context shape.

Local implementation of the make_AGENTS quality checks (canvas-toolbox is a
downstream consumer of that framework):

- **AGENTS-QC-011** — Active Context is current-state-only, not an append-only
  release log. Flag when it has >5 dated entries OR >150 lines. (Full release
  history lives in CHANGELOG.md.)
- **AGENTS-QC-010** — total file size within readable limits. Hard cap ~25,000
  tokens: the common host-tool Read limit, beyond which AGENTS.md can't be read
  in one pass (the failure this guards — it once hit 182 KB / ~32k tokens).

Release workflow: add the new `### ` entry on top of Active Context, rotate the
oldest out to CHANGELOG.md, keeping each entry a brief highlight (full detail in
CHANGELOG).
"""

from pathlib import Path

MAX_ACTIVE_CONTEXT_ENTRIES = 5
MAX_ACTIVE_CONTEXT_LINES = 150
HARD_MAX_TOKENS = 25_000  # AGENTS-QC-010 hard cap (host Read-tool limit)

AGENTS_MD = Path(__file__).resolve().parents[2] / "AGENTS.md"


def _active_context_block(text):
    """Return the lines of the Active Context section (header excluded)."""
    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if ln.strip() == "## Active Context"), None
    )
    assert start is not None, "AGENTS.md is missing its '## Active Context' section"
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return lines[start + 1 : end]


def test_active_context_entry_count():
    block = _active_context_block(AGENTS_MD.read_text(encoding="utf-8"))
    entries = [ln for ln in block if ln.startswith("### ")]
    assert len(entries) <= MAX_ACTIVE_CONTEXT_ENTRIES, (
        f"AGENTS.md Active Context has {len(entries)} entries "
        f"(max {MAX_ACTIVE_CONTEXT_ENTRIES}). Rotate the oldest into CHANGELOG.md.\n  "
        + "\n  ".join(entries)
    )


def test_active_context_line_count():
    block = _active_context_block(AGENTS_MD.read_text(encoding="utf-8"))
    assert len(block) <= MAX_ACTIVE_CONTEXT_LINES, (
        f"AGENTS.md Active Context is {len(block)} lines (max "
        f"{MAX_ACTIVE_CONTEXT_LINES}). Condense entries to brief highlights — "
        "full detail belongs in CHANGELOG.md (AGENTS-QC-011)."
    )


def test_agents_md_total_size_under_read_limit():
    text = AGENTS_MD.read_text(encoding="utf-8")
    est_tokens = len(text) // 4  # rough char/4 heuristic
    assert est_tokens <= HARD_MAX_TOKENS, (
        f"AGENTS.md is ~{est_tokens} tokens (hard cap {HARD_MAX_TOKENS}). It can "
        "no longer be read in one pass — trim Active Context / move long-form docs "
        "to README/docs/ and domain knowledge to knowledge/ (AGENTS-QC-010)."
    )

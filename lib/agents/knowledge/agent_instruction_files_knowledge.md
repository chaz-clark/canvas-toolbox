---
name: agent_instruction_files_knowledge
version: "1.0"
last_updated: 2026-09-11
description: Which agentic tools read which project instruction file. Claude Code does NOT read AGENTS.md — it reads CLAUDE.md. The symlink fix, the full support matrix, and the measurements behind both.
skill_type: knowledge
shape: reference
scope: "Where a repo's agent instructions must live for each tool to load them at session start. Covers AGENTS.md, CLAUDE.md, GEMINI.md and the config-gated cases."
consumed_by:
  - cb_init.py
  - cb_update.py
provenance:
  sources:
    - "Controlled measurement, Claude Code 2.0.37, 2026-09-11 (see Measurements)"
    - "Anthropic Agent SDK docs (cached: Make-AI-Agents/source-docs/anthropic_agent_sdk.md:318)"
    - "https://agents.md — official supported-tools list"
    - "Google managed-agents docs (cached: Make-AI-Agents/source-docs/google_managed_agents.md:143)"
runtime_strategy: read_at_runtime
metadata: { knowledge_id: agent_instruction_files_knowledge }
---

# Agent instruction files — who reads what

**Read this before changing where a repo's instructions live, or before
"fixing" an `AGENTS.md` that isn't loading. The question has been settled
empirically; do not re-litigate it from priors.**

---

## The headline

**Claude Code does not read `AGENTS.md`.** It reads `CLAUDE.md` (or
`.claude/CLAUDE.md`). A repo whose only instruction file is `AGENTS.md` gives
Claude Code sessions **nothing** — silently, with no warning, at any nesting depth.

This is not a bug in the repo layout and it is not caused by vendoring, nesting,
or directory structure. It is a filename gap, and it is fixed by one symlink.

---

## The fix

```
AGENTS.md                          ← the one real file; source of truth
.claude/CLAUDE.md  → ../AGENTS.md  ← symlink (Claude Code reads this)
```

One file on disk, two names. No duplication, no sync, no drift. `AGENTS.md`
keeps its tool-agnostic name for the 20+ tools that read it natively; the shim
lives inside the vendor's own dot-directory rather than cluttering the root.

`ln -s AGENTS.md CLAUDE.md` at the root also works and is the community's
standard workaround — the `.claude/` placement is just tidier.

**Windows:** symlinks need Developer Mode. Fall back to a marked copy, the same
`_managed_copy` + marker-file pattern `cb_update` already uses for skills.

---

## Support matrix

| Tool | Reads repo-root `AGENTS.md` | Action needed |
|---|---|---|
| **Claude Code** | **NO** | **symlink `CLAUDE.md` → `AGENTS.md`** |
| Codex · Cursor · Windsurf · Zed · Amp · VS Code | yes | none |
| Jules · Factory · goose · opencode · Warp · Devin · Junie · RooCode · Kilo Code · Phoenix · Semgrep · Ona · Augment · Copilot Coding Agent · UiPath | yes | none |
| **Aider** | config-gated | `.aider.conf.yml` → `read: AGENTS.md` |
| **Gemini CLI** | config-gated | `.gemini/settings.json` → `contextFileName: AGENTS.md` (defaults to `GEMINI.md`) |

Claude Code is **not listed on agents.md at all**, while 20+ other tools are.
It is the outlier, not the rule — `AGENTS.md` remains the right canonical
filename.

---

## Measurements

Controlled probes, Claude Code 2.0.37, unique sentinel strings, `claude -p
--tools ""` (tools disabled so the answer can only come from session-start
context), each in a fresh git repo:

| Layout | Sentinel in context |
|---|---|
| root `CLAUDE.md` only | **YES** |
| root `AGENTS.md` only | **NO** |
| both, side by side | only the `CLAUDE.md` one |
| root `CLAUDE.md` containing `@AGENTS.md` | **NO** — import does not expand at project level |
| root `CLAUDE.md` → symlink → `AGENTS.md` | **YES** |
| `.claude/CLAUDE.md` → symlink → `../AGENTS.md` | **YES** |

Corroborated by two live sessions in real repos (`ds460-master` nested,
`ds295r-ai-engineering` flat): both loaded **only** the two global files
(`~/.claude/CLAUDE.md`, `~/.claude/RTK.md`); neither loaded its project
`AGENTS.md`, despite `ds460-master/AGENTS.md:37` containing the probe string.

**Note the `@import` result.** Some published workarounds claim
`@AGENTS.md` inside `CLAUDE.md` works. It does **not** at project level on
2.0.37 — only the global `~/.claude/CLAUDE.md` expands imports. Use the symlink.

---

## What this is NOT

Two hypotheses were tested and **disproved** — do not revisit them:

- **"Nesting buries the file."** No. `ds460-master` (nested `canvas-toolbox/`
  with symlinked skills) and `ds295r-ai-engineering` (fully flattened) failed
  **identically**. Flattening a repo does not fix this and is not worth doing
  for this reason.
- **"Skills don't load from a nested toolkit."** No. Both layouts surfaced all
  eight toolkit skills. `cb_update`'s skill-symlink approach is validated and
  working. Skill *bodies* load only on invoke — names and descriptions in
  context is correct behavior, not a gap.

---

## Provenance of the original error

`Make-AI-Agents/README.md` listed Claude Code under *"Automatic — just open the
repo."* That row is wrong and is where the assumption entered: it propagated
into canvas-toolbox's own `AGENTS.md`, into the CLAUDE.md→AGENTS.md migration
rationale, and out into 23 repos whose instructions were never loading.

Of the three rows in that table checkable against vendor documentation, **none**
supported plain repo-root `AGENTS.md`: Anthropic documents `CLAUDE.md`, Google
documents `.agents/AGENTS.md` *mounted into a sandbox*, and Copilot needs
`chat.useAgentsMdFile: true`. Corrected upstream via handoff
`2026-09-11_claude-code-does-not-read-agents-md`.

---

## Related

- `deid_master_knowledge.md` — a constitution that never loads enforces nothing;
  this is why the FERPA rules weren't reaching sessions.
- `docs/proposals/flat-layout-and-agents-merge.md` — the flat-migration plan this
  finding retired.

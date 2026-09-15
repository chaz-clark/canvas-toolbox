# ADR-001: Runtime-neutral agent packages

**Status:** discovery in progress  
**Date:** 2026-09-14  
**Branch:** `feat/v2-agent-packaging`  
**Plan:** [`../proposals/v2-agent-packaging-plan.md`](../proposals/v2-agent-packaging-plan.md)

## Context

Canvas Toolbox 2.0 needs one canonical set of agent skills that works with subscription-backed
VS Code agents without making Codex, Claude Code, GitHub Copilot, or an API-key model runtime a
dependency. The package must also retain the existing deterministic FERPA and Canvas-write
controls when a host does not support portable plugins.

Agent Plugins 1.0 standardizes a root `plugin.json`, immediate child skills under `skills/`,
and an optional root `mcp.json`. It does not standardize constitutions, specialized agents, or
hooks. The standard also requires plugin-contained paths, so it cannot replace the flattened
course installation or reach into the hidden `.canvas-toolbox/` update clone.

This ADR remains open until the VS Code and host matrix is complete. It records measured behavior
so implementation does not silently turn documentation assumptions into architecture.

## Safety invariants

- Root `AGENTS.md` remains the always-on constitution.
- The flattened course installation remains the safety-complete baseline.
- Agent Plugins and host adapters may improve discovery but never authorize access.
- No probe contains an MCP server, hook, script, credential, Canvas operation, or course data.
- No Canvas-write MCP server is considered during this discovery phase.
- A successful response after searching for `SKILL.md` is filesystem fallback, not native skill
  discovery.

## Test environment

| Component | Measured version |
|---|---|
| macOS architecture | Apple Silicon (`arm64`) |
| VS Code | `1.137.0` |
| Codex CLI | `0.153.4` |
| Codex VS Code extension | `openai.chatgpt@26.908.40401` |
| Claude Code | `2.1.270` from the installed VS Code extension |
| GitHub Copilot chat host | VS Code `1.137.0` built-in host, activated in temporary profile |
| Agent Plugins specification | `1.0.0`, rechecked 2026-09-14 |

Official OpenAI documentation did not establish whether the Codex VS Code extension consumes VS
Code-installed Agent Plugins 1.0 packages. The installed Codex runtime exposes a separate Codex
plugin format and project-level skill discovery. In the ordinary VS Code profile, Agent Plugins
commands and the customization UI were absent because the Copilot chat host was not active. A
temporary profile activated VS Code's built-in Copilot host and exposed the documented plugin UI.
That profile did not include the Codex or Claude Code extensions, so it establishes Copilot
consumption of the portable package, not cross-extension sharing.

## Disposable probe

The temporary probe contained:

```text
probe/
├── AGENTS.md
├── plugin.json
├── skills/canvas-toolbox-packaging-probe/SKILL.md
├── .agents/skills/agents-discovery-probe/SKILL.md
├── .codex/skills/codex-discovery-probe/SKILL.md
└── .claude/skills/claude-discovery-probe/SKILL.md
```

The portable manifest used the canonical schema identifier:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "canvas-toolbox-packaging-probe",
  "version": "0.0.1",
  "description": "Harmless discovery fixture for Canvas Toolbox runtime packaging tests."
}
```

Each skill returned a unique inert marker and explicitly prohibited tools, Canvas access, course
data reads, and file changes.

## Measured results

| Host/path | Result | Evidence and interpretation |
|---|---|---|
| Codex root `AGENTS.md` | pass | A fresh ephemeral session returned the marker supplied only by the root constitution. |
| Codex `.agents/skills/` | pass | The skill was present in host metadata and could be invoked by its `$skill-name`. |
| Codex `.codex/skills/` | pass | The skill was present in host metadata; using both Codex paths would create duplicate discovery. |
| Codex root `skills/` as an ordinary workspace | fallback only | Codex searched for and opened `SKILL.md`; the root portable directory was not supplied as native project-skill metadata. |
| Codex `.claude/skills/` | not discovered | The Claude-specific probe was absent from Codex's host-supplied skill metadata. |
| Codex real-directory `.agents/skills/` adapter | pass | Direct named invocation loaded the generated skill. |
| Codex in-repository symlink under `.agents/skills/` | pass on macOS | Direct named invocation loaded the canonical target; Windows still requires real copied directories. |
| Codex VS Code `.agents/skills/` adapter | pass | A new chat rendered the named skill as skill context and returned its inert marker without filesystem search. |
| Codex-specific `.codex-plugin/plugin.json` scaffold | validation pass | The supplied Codex plugin and Agent Skill validators accepted the skills-only fixture. |
| Codex-specific marketplace install | install pass, runtime fail | Codex installed and listed the plugin, but invocation resolved `SKILL.md` from a cache path missing the plugin-name segment. The exact temporary plugin and marketplace were removed after the failed test. |
| Claude `.claude/skills/` | pass | Direct `/claude-discovery-probe` invocation succeeded with tools disabled. |
| Claude Agent Plugins root `skills/` through `--plugin-dir` | pass | Direct `/canvas-toolbox-packaging-probe` invocation succeeded with tools disabled. This establishes CLI session loading, not VS Code source-install behavior. |
| Claude Code VS Code `.claude/skills/` adapter | pass | A fresh session invoked `/claude-discovery-probe` and identified `.claude/skills/` as its loaded source while rejecting `.agents/skills/` as undiscovered. |
| VS Code Agent Plugins UI in ordinary profile | host inactive | `Chat: Install Plugin From Source`, `Chat: Open Customizations`, and all plugin commands were absent when the Copilot chat host was not active. |
| VS Code Agent Plugins local source install | pass | In a temporary profile with the built-in Copilot host active, `Chat: Install Plugin from Source` accepted a local Git repository path. Agent Customizations showed the package as `Local`, enabled, with one skill. The `file://` form was inconclusive because the Extensions view remained stale; the plain local path is the measured pass. |
| GitHub Copilot portable skill list | pass | Agent Customizations listed `canvas-toolbox-packaging-probe` under the read-only Plugins skill group with the manifest description. |
| GitHub Copilot portable skill invocation | pass | Chat suggested `/canvas-toolbox-packaging-probe`; direct slash invocation returned the inert plugin marker with no tools. A natural-language request instead followed the root `AGENTS.md` marker, confirming the constitution remained active but not proving automatic skill selection. |
| VS Code visible skill evidence | pass for local adapters | Codex rendered the `.agents` skill as skill context; Claude exposed and invoked the `.claude` slash skill. This does not establish portable-plugin sharing between extension webviews. |
| GitHub Copilot workspace skill discovery | mixed | Its Skills UI discovered `.agents/skills/` and `.claude/skills/` as workspace skills, but not `.codex/skills/`. Plugin invocation was tested through the separate portable root skill. |

### Codex plugin defect

The Codex-specific plugin installed at:

```text
~/.codex/plugins/cache/canvas-toolbox-probe/
  canvas-toolbox-codex-probe/0.1.0/
```

The fresh session attempted to load:

```text
~/.codex/plugins/cache/canvas-toolbox-probe/
  0.1.0/skills/canvas-toolbox-codex-plugin-probe/SKILL.md
```

Because the second path omitted `canvas-toolbox-codex-probe/`, the skill metadata appeared but
the instructions could not load. This result blocks Codex marketplace packaging from becoming
the baseline in the measured version. It does not block the project-level `.agents/skills/`
adapter, which passed.

## Representative consumer layouts

These are structural fixtures. Recording them requires no student data or FERPA Zone-2 reads.

### Fresh 2.0 target

```text
course/
├── .canvas-toolbox/       # pristine hidden update clone
├── AGENTS.md              # constitution plus course-owned learning
├── plugin.json            # portable Agent Plugins metadata
├── skills/                # canonical portable Agent Skills
├── .agents/skills/        # generated Codex/generic workspace adapter
├── .claude/skills/        # generated Claude Code adapter
├── agent-packages/
├── lib/
├── course/
├── grading/
├── .env
└── .gitignore
```

### Nested 1.x consumer

```text
course/
├── canvas-toolbox/        # vendored toolkit clone
├── AGENTS.md              # course stub/pointer
├── .claude/skills/        # symlinks or managed Windows copies into nested toolkit
├── .env
├── course/
└── grading/
```

### Already-flat 1.x consumer

```text
course/
├── .canvas-toolbox/       # pristine hidden update clone
├── AGENTS.md              # hybrid constitution/course content
├── .claude/skills/        # real flattened skill directories
├── lib/
├── course/
├── grading/
├── .env
└── .gitignore             # exact generated toolkit-owned paths
```

The migration matrix will build synthetic versions of all three layouts first. Any later test
against an approved real course repository must use path-only structural checks and must not read
FERPA Zone-2 files.

## Provisional decision

Pending the remaining cross-extension and Windows measurements:

1. Keep root `skills/` as the canonical Agent Skills source and Agent Plugins 1.0 component path.
2. Keep root `plugin.json` as the portable, closed-schema plugin manifest.
3. Generate or flatten real skill directories into `.agents/skills/` for Codex workspace
   discovery. Do not also ship `.codex/skills/` unless a later measurement requires it.
4. Generate `.claude/skills/` for Claude Code workspace discovery.
5. Generate a separate `.codex-plugin/plugin.json` only as a Codex-specific distribution adapter;
   it cannot replace the portable root manifest and is not currently the safety baseline.
6. Keep root `AGENTS.md` and deterministic tools in the flattened course payload for every host.
7. Keep the first portable plugin skills-only. Omit `mcp.json` entirely until a separate MCP
   threat model and approval design pass.
8. Treat Agent Plugins 1.0 as an additional portable distribution output with measured Copilot
   support, not the subscription-extension baseline. Codex and Claude Code retain their generated
   workspace adapters until those extensions are observed consuming VS Code-installed portable
   plugins.
9. Treat VS Code profiles as optional onboarding aids after packaging works without them.

## Consequences

- Canonical skills remain runtime-neutral, but workspace adapters are generated copies or links.
- Windows correctness depends on real-directory generation rather than symlink support.
- Codex and Claude Code have reliable flattened paths even when VS Code's Agent Plugins UI is
  unavailable or only feeds its Copilot chat host.
- The repository may carry two different plugin manifests because they implement different,
  incompatible schemas. Generation and validation must prevent drift.
- Agent Plugins updates and Codex plugin updates are separate channels; neither may silently
  broaden capabilities.

## Remaining gate measurements

- Repeat installation from a remote HTTPS Git URL; the local Git repository path passed.
- Compare source installation with `chat.pluginLocations` registration in the Copilot host.
- Test enable, disable, update, and uninstall behavior in the temporary profile.
- Test whether Codex and Claude Code extension webviews consume the installed portable plugin, or
  confirm that only Copilot chat does.
- Record Continue.dev, Cline, Antigravity, and Positron only where an extension is actually
  available.
- Retest Codex-specific marketplace installation on a newer Codex build before release.

## Sources

- [VS Code Agent Plugins](https://code.visualstudio.com/docs/agent-customization/agent-plugins)
- [Agent Plugins 1.0 specification](https://github.com/agentplugins/agent-plugins-spec/blob/main/spec/1.0.0.md)
- [Agent Plugins manifest](https://agent-plugins.org/plugin-authors/manifest)
- [Agent Skills specification](https://agentskills.io/specification)

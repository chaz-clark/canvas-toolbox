# Canvas Toolbox 2.0 — Runtime-Neutral Agent Packaging Plan

**Status:** planned  
**Implementation branch:** `feat/v2-agent-packaging`  
**Current baseline:** Canvas Toolbox `1.22.0` plus the flattened-install work from #315
and the merge-cleanup gate from #316  
**Target release:** `2.0.0`  
**Primary supported experience:** Visual Studio Code + Codex authenticated through the
BYU-Idaho CES ChatGPT workspace  
**Portability requirement:** the canonical package must not depend on Codex, OpenAI,
OpenWorker, Claude, Gemini, Copilot, or any other model/runtime  
**Portable VS Code distribution target:** Agent Plugins 1.0, subject to measured Codex
compatibility in Phase 1

---

## 1. Outcome

Canvas Toolbox 2.0 will package its agent behavior as validated, runtime-neutral bundles.
Each bundle will declare its skills, deterministic tools, data-access boundary, Canvas-write
surface, and installation requirements. Host-specific files for Codex, Claude Code, GitHub
Copilot, and other VS Code agents will be generated adapters rather than independent sources
of truth.

The faculty experience remains simple:

1. Open an empty course folder in VS Code.
2. Use the AI extension covered by the instructor's existing subscription. Codex is the
   BYU-Idaho reference path because it can use the CES ChatGPT agreement.
3. Ask the agent to install Canvas Toolbox.
4. The agent runs the flattened initializer, collects Canvas configuration, and verifies the
   installation.
5. Every supported agent sees the same constitution, skills, tools, and safety boundaries.

The architecture must preserve these invariants:

- The course repository is the working surface.
- `.canvas-toolbox/` is the pristine, hidden update source.
- Local course files are the source of truth; Canvas is a sync target.
- FERPA Zone-2 content never enters an LLM context.
- Canvas grades/comments use only sanctioned writers.
- Canvas writes retain deterministic guards and explicit human confirmation.
- A package manifest describes access; it does not replace enforcement in hooks and tools.
- A provider-specific adapter may improve discovery, but safety must never depend on a model
  following a prompt correctly.

---

## 2. Why this is a major release

This work changes public contracts rather than only reorganizing internal files:

- where canonical agent instructions and skills live;
- how runtime-specific instruction files are generated;
- how `cb_init`, `cb_update`, and `cb_flatten` install and update the toolkit;
- which repository files are distributed into a course repository;
- how package capabilities and capability growth are presented to the instructor;
- how existing nested and already-flattened course repositories migrate;
- how downstream tools locate shared knowledge and templates.

Backward migration support is required, but permanent preservation of the 1.x directory
layout is not. The version remains on the 1.x line during development and changes to `2.0.0`
only after all release gates in Phase 11 pass.

---

## 3. Decisions already made

- [x] Keep Visual Studio Code as the primary faculty surface.
- [x] Make Codex the first and most thoroughly tested adapter for BYU-Idaho.
- [x] Remain agent-, runtime-, model-, and provider-agnostic at the canonical layer.
- [x] Do not adopt OpenWorker as a runtime dependency.
- [x] Borrow OpenWorker's useful packaging ideas: self-describing bundles, strict manifests,
      explicit capability sets, provenance, and re-consent when capabilities grow.
- [x] Treat the open Agent Plugins 1.0 format as a first-class portable distribution output.
- [x] Keep the flattened course installation as the safety-complete baseline until Agent
      Plugins support is verified in Codex and every required deterministic gate has a home.
- [x] Keep the root `AGENTS.md` as the always-on constitution.
- [x] Keep deterministic Canvas and FERPA enforcement below the prompt layer.
- [x] Keep the hidden pristine clone and flattened course-root installation model.
- [x] Preserve dry-run-first and verification-after-write behavior.
- [x] Separate packages by trust boundary, not merely by historical agent filename.

### Non-goals

- Building a new desktop application.
- Making a VS Code profile the canonical distribution or safety mechanism.
- Requiring an API key for an AI model.
- Bundling or forking OpenWorker.
- Replacing Canvas Toolbox tools with model-generated API calls.
- Rewriting working Python tools solely to adopt a new folder style.
- Guaranteeing identical UI features across every VS Code agent extension.
- Moving secrets into manifests, prompts, skill files, or course content.

### Agent Plugins 1.0 and VS Code profiles

Agent Plugins 1.0 is a better packaging target than a VS Code profile:

- it is an open format rather than a user-specific editor snapshot;
- it defines portable `skills/` and `mcp.json` components;
- it can be installed directly from a Git repository;
- it allows client-specific additions in reverse-domain namespaces without making those
  additions canonical;
- installed plugin customizations coexist with workspace-local customizations.

A VS Code profile may be offered later as an optional onboarding convenience that recommends
extensions and settings. It must not carry the Canvas Toolbox constitution, FERPA rules,
write authorization, secrets, or the only copy of any skill.

Agent Plugins 1.0 does not make specialized agents or hooks portable. Those remain
client-specific. Plugin MCP servers and hooks can execute code on the user's machine, and VS
Code treats plugin MCP servers as trusted with the plugin installation. Therefore:

- the first Agent Plugin prototype is **skills-only**;
- no Canvas-write MCP server is added before a separate threat model and approval design;
- the flattened installation remains responsible for the root constitution, course context,
  deterministic hooks, and course-local tools;
- Codex compatibility is measured in the actual Codex VS Code extension rather than inferred
  from VS Code's Copilot-focused documentation.

### Cross-repository alignment review

The completed `life-pm` proposal at
`docs/proposals/vscode-agent-packaging-plan.md` was reviewed on 2026-09-14. It independently
reached the same skills-first hybrid architecture. The repositories will share neutral
conventions, but neither repository will depend on, import from, or release-lock the other.

- [x] Obtain and read the completed `life-pm` plan.
- [x] Compare package names, manifest fields, skill layout, adapter generation, provenance,
      update semantics, and capability-consent behavior.
- [x] Reuse genuinely domain-neutral conventions where they fit both repositories.
- [x] Keep FERPA, Canvas-write, grading, and per-student fields Canvas-specific.
- [ ] Preserve the accepted and deliberately different conventions in the Phase 1 ADR after
      runtime discovery measurements are complete.

Shared conventions:

| Concern | Shared convention |
|---|---|
| Canonical policy | Root `AGENTS.md` is the always-on constitution; local overlays may add context but never weaken it. |
| Portable plugin surface | Root `plugin.json` plus canonical root `skills/`; root `mcp.json` contains only reviewed, intentionally shipped servers. |
| Internal packages | `agent-packages/registry.yaml`, a versioned schema, and one `manifest.yaml` per trust-boundary package. Package ids remain domain-specific. |
| Common manifest core | `schema_version`, stable `id`, package `version`, `name`, `description`, `entry_prompt`, `skills`, declared effects/approvals, `data_access`, and credential names without values. Domain schemas extend this core instead of pretending Agent Plugins defines it. |
| Host support | Codex in VS Code is the reference adapter; Claude Code and GitHub Copilot are measured next; a generic constitution/deterministic path remains available. |
| Adapter generation | Host files are generated from canonical content, carry source/schema provenance, regenerate idempotently, and fail CI on drift. |
| Distribution | A schema-validated exact allowlist decides the install/release payload; `git ls-files` proves ownership but does not choose the payload. |
| Consent and updates | Installation is a trust event; added or broadened MCP/write/data capability is a capability change that must be shown and re-consented to before enablement. |
| Profiles | VS Code profiles are optional, minimal onboarding aids only; they are not policy, authentication, distribution, or safety boundaries. |
| Enforcement | Manifests describe and validate intent; deterministic tools, hooks, tests, and host gates enforce it. |

Deliberate differences:

| Canvas Toolbox | `life-pm` | Reason |
|---|---|---|
| Flat course-root install backed by a pristine `.canvas-toolbox/` clone is the baseline. | Public/private payload separation and preservation of a private operator overlay are central. | Canvas Toolbox is installed into many course repositories; `life-pm` is separating a personal operating system from a public package. |
| Packages are `course-design`, `grading`, and `student-support`. | Packages are `core`, `research-memory`, `work-home-bridge`, and `scheduled-routines`. | Package names follow each domain's trust boundaries, not a shared taxonomy. |
| Schema extends the common core with FERPA zones, student-data classes, sanctioned Canvas writers, and course scope. | Schema extends it with connectors, account attribution, OAuth classes, schedules, and public/private data boundaries. | These controls are meaningful only in their source domain. |
| The first plugin prototype is skills-only; Canvas-write MCP is excluded until a separate threat model and approval design pass. | Reviewed connectors may enter `mcp.json` after install-time trust and capability-consent review. | Canvas writes and student records require the stricter existing sanctioned-tool boundary. |
| A profile remains optional because the flattened initializer already provides the supported setup path. | Profile value is evaluated after the canonical package works and may be retained if it materially reduces setup friction. | Both are non-canonical, but the current onboarding baselines differ. |
| Release ends in a tested `2.0.0` migration from supported 1.x layouts. | Release proceeds through private alpha and a separate public publication decision. | Canvas Toolbox is an existing public toolkit; `life-pm` is preparing a private system for possible public distribution. |

No cross-repository handoff is required for this comparison because the maintainer supplied the
completed proposal directly. A later implementation handoff still follows the repository's
handoff lifecycle rules.

---

## 4. Current-state baseline

### Already built

- [x] `cb_flatten.py` creates/uses `.canvas-toolbox/` as a pristine hidden clone.
- [x] The flattened file set is recorded as exact paths in the course `.gitignore`.
- [x] Upstream deletions are detected from the previously installed set.
- [x] `AGENTS.md` and `.gitignore` are treated as hybrid files.
- [x] `merge_cleanup.py` deterministically protects the constitution/course-learning merge.
- [x] Tests cover flatten ownership, deletion tracking, and merge-cleanup behavior.

### Not yet complete in the 1.x flattened workflow

- [ ] Make flat installation the default fresh-install path in `cb_init`.
- [ ] Consolidate `cb_update` around the hidden clone rather than the nested skill-symlink
      workflow.
- [ ] Complete the AGENTS merge skill/orchestration described in
      `flat-layout-and-agents-merge.md`.
- [ ] Add the weekly, fail-open update notice.
- [ ] Run the full migration matrix against representative consumer repositories.

### Structural problems 2.0 must resolve

- Agent specifications live in `lib/agents/*.md`, operating skills in `.claude/skills/`,
  deterministic tools in `lib/tools/`, templates in `lib/agents/templates/`, and host commands
  in `scaffold/.claude/commands/`. Their relationships are implied by prose.
- `.claude/skills/` is a runtime-branded canonical location even though the toolkit promises
  runtime neutrality.
- Agent frontmatter is descriptive but not validated as an executable capability contract.
- `git ls-files` currently means both "owned by the toolkit" and "should be installed into
  every course." Those are related but different decisions.
- Generated or copied host instructions can drift because no source-to-adapter check exists.
- Some older agent guides still describe deprecated workflows. For example,
  `canvas_course_expert.md` says `.imscc` parsing is deprecated and then instructs the agent to
  parse an export ZIP a few lines later.

---

## 5. Target repository architecture

Names below are targets; Phase 1 may refine names, but not the separation of concerns.

```text
canvas-toolbox/
├── AGENTS.md                         # constitutional source; runtime-neutral
├── plugin.json                       # Agent Plugins 1.0 portable manifest
├── skills/                           # canonical portable Agent Skills
│   ├── audit/SKILL.md
│   ├── course-build/SKILL.md
│   ├── improve/SKILL.md
│   ├── grading/SKILL.md
│   ├── ferpa-deid/SKILL.md
│   ├── voicing/SKILL.md
│   ├── accommodations/SKILL.md
│   └── title-iv/SKILL.md
├── .agents/skills/                   # generated Codex workspace adapter
├── .claude/skills/                   # generated Claude Code workspace adapter
├── .codex-plugin/
│   └── plugin.json                   # generated Codex plugin adapter, not canonical
├── mcp.json                          # absent/empty until the MCP safety gate passes
├── agent-packages/
│   ├── registry.yaml                 # package inventory + compatibility status
│   ├── schema/
│   │   └── package-manifest.schema.json
│   ├── course-design/
│   │   ├── manifest.yaml
│   │   ├── AGENT.md                  # package mission/prompt
│   │   └── assets/
│   ├── grading/
│   │   ├── manifest.yaml
│   │   ├── AGENT.md
│   │   └── assets/
│   ├── student-support/
│   │   ├── manifest.yaml
│   │   └── AGENT.md
│   └── shared/
│       ├── knowledge/
│       └── templates/
├── runtime-adapters/
│   ├── codex/
│   ├── claude-code/
│   ├── vscode-agent-plugin/
│   └── generic/
├── com.github.copilot/               # generated Agent Plugin namespace
├── distribution/
│   ├── manifest.yaml                 # what is installed into course repos
│   └── schema/
│       └── distribution.schema.json
├── lib/
│   ├── tools/                        # sanctioned deterministic tools remain stable
│   └── tests/
└── docs/
```

### Installed course architecture

```text
course-repo/
├── .canvas-toolbox/                  # pristine hidden clone; never edited/executed
├── AGENTS.md                         # constitution + curated course-specific learning
├── agent-packages/                   # flattened runtime-neutral packages
├── skills/                           # portable skills; exact discovery verified in Phase 1
├── .agents/skills/                   # generated real directories for Codex discovery
├── .claude/skills/                   # generated real directories for Claude discovery
├── <other runtime discovery paths>   # generated/local adapters where still required
├── lib/                              # deterministic Canvas tools
├── course/                           # local course mirror/source
├── grading/                          # protected grading workspace
├── .env                              # course id and non-global configuration
└── .gitignore                        # exact installed paths + course-owned rules
```

The repository-root `plugin.json` and `skills/` make the Git repository directly installable
as an Agent Plugins 1.0 source. The internal package manifests add Canvas-specific safety and
distribution metadata that the open plugin standard does not model. Neither format replaces
the other.

---

## 6. Package boundaries

### `course-design`

Purpose: course construction, synchronization, quality audits, instructional-design analysis,
and improvement tracking.

- Default data boundary: course content and course configuration; no student submission data.
- Reads: course mirror, Canvas course structure, outcomes, rubrics, modules, dates.
- Writes: sanctioned course-build tools only, with plan/confirmation/verification gates.
- Skills: `audit`, `course-build`, `improve`.

### `grading`

Purpose: FERPA-safe preparation, review, and delivery of assignment grades and feedback.

- Default data boundary: deidentified student work only.
- Zone 2: denied to LLMs unconditionally.
- Writes: only `grader_push.py` and `grader_standing.py` for grades/comments.
- Skills: `grading`, `ferpa-deid`, `voicing`.
- Install/update summary must display that this package handles student evaluation data.

### `student-support`

Purpose: accommodations and Title IV engagement workflows involving individual students.

- Default data boundary: opaque `user_id`/`deid_code`; names excluded from agent output.
- Writes: sanctioned accommodation dispatchers only, with per-student confirmation.
- Skills: `accommodations`, `title-iv`.
- Install/update summary must display its per-student access and intervention capability.

Shared knowledge and templates may be referenced by multiple packages but must remain
single-sourced.

---

## 7. Runtime-neutral package manifest

The schema will be developed test-first. A representative shape is:

```yaml
schema_version: 1
id: canvas-grading
version: "2.0"
name: Canvas Grading
description: FERPA-safe grading preparation, review, and sanctioned delivery.
entry_prompt: AGENT.md
requires_course_folder: true

skills:
  - id: grading
    path: skills/grading
  - id: ferpa-deid
    path: skills/ferpa-deid
  - id: voicing
    path: skills/voicing

tools:
  - id: grader-fetch
    command: lib/tools/grader_fetch.py
    effect: read
    data_class: student_submission
  - id: grader-push
    command: lib/tools/grader_push.py
    effect: canvas_write
    data_class: student_evaluation
    approval: always

data_access:
  ferpa_zone_2: deny
  student_names_in_evaluations: deny
  deidentified_submissions: allow

credentials:
  - CANVAS_API_TOKEN
  - CANVAS_BASE_URL

network:
  - canvas_base_url_only

ships: true
```

### Manifest rules

- Every id is unique, stable, lowercase, and filesystem-safe.
- Every referenced path exists and is tracked.
- Every command resolves to a sanctioned toolkit tool.
- Every Canvas-writing tool declares `effect: canvas_write` and `approval: always`.
- Every student-data tool declares a data class.
- Manifests contain credential names only, never credential values.
- Unknown keys fail validation unless explicitly reserved for forward compatibility.
- Unknown tool ids, skill ids, data classes, or approval modes fail validation.
- Package version changes are independent of the repository version but are recorded in the
  package registry.
- Provider/model recommendations do not belong in the canonical package manifest.
- Runtime compatibility is recorded in the package registry or adapter metadata, not used to
  alter safety behavior.

---

## 8. Distribution model

The hidden clone remains the authoritative update source. The distribution manifest becomes
the authoritative answer to "which tracked files should be installed into a course?"

`git ls-files` will continue to provide:

- proof that distributed files are version controlled;
- source ownership and provenance;
- a complete set against which the distribution manifest can be validated.

The resolved distribution manifest will provide:

- the exact files copied into a course;
- package/adaptor selection;
- hybrid-file declarations;
- the installed capability set;
- paths that should disappear when removed upstream.

The course `.gitignore` sentinel block remains the durable record of the exact previously
installed set. Update deletion remains:

```text
previous installed set - newly resolved distribution set = paths to remove
```

### Distribution safety rules

- No broad directory deletion.
- No target outside the validated course root.
- No Zone-2 path may appear in a distribution manifest.
- No `.env`, credential store, raw submission, review, or keymap file may be distributed.
- `AGENTS.md` and `.gitignore` remain hybrid and are never blindly overwritten.
- Course-owned files remain untouched even when they share a parent directory with adapters.
- Expanding the capability set is displayed before apply and requires explicit approval.
- A same-or-smaller capability update may use the ordinary update confirmation.
- Failed validation leaves the prior installation and hidden clone recoverable.

---

## 9. Runtime adapters

Adapters only translate canonical packages into files a host can discover. They must not copy
or fork the substantive safety rules.

### Priority order

1. **Codex in VS Code** — reference adapter and BYU-Idaho acceptance gate.
2. **Claude Code in VS Code** — supported adapter, including its required instruction shim.
3. **GitHub Copilot in VS Code** — supported after its actual instruction/skill discovery
   behavior is tested.
4. **Generic VS Code agent** — root `AGENTS.md`, explicit package index, deterministic CLIs.
5. Continue.dev, Cline, Antigravity, and Positron are compatibility tests after the first
   three paths are stable.

### Adapter rules

- Generated files contain a marker naming their canonical source and generator version.
- Re-running generation is byte-for-byte idempotent.
- CI regenerates adapters and fails if the working tree changes.
- Adapter removal is handled as an upstream deletion during flattened update.
- A host-specific file may point to canonical content but may not weaken it.
- No adapter may authorize a Canvas write, FERPA read, shell command, or connector that the
  canonical manifest denies.
- Runtime-specific model names are optional test metadata, never package requirements.
- Discovery claims must be verified in the real extension; documentation alone is not enough.

---

## 10. Implementation phases and checklists

Every phase is separately reviewable and ends with tests. Stop at the first failed gate.

### Phase 0 — Branch and baseline

- [x] Create `feat/v2-agent-packaging` from working `main`.
- [x] Add this plan without changing runtime behavior.
- [x] Push the branch and open draft PR #317 for continuous visibility.
- [x] Record baseline test count and runtime: **1374 passed in 246.34 seconds** on
      2026-09-14.
- [x] Run `uv run pytest lib/tests -q` on the unmodified product baseline plus this docs-only
      plan.
- [x] Record representative fresh/nested/flat consumer layouts without reading FERPA Zone-2
      files.
- [x] Confirm no local commits exist on `main` that are absent from remotes.

**Gate:** plan reviewed by the maintainer; baseline green; no product behavior changed.

### Phase 1 — Runtime discovery spike and architecture decision record

- [x] Verify root `AGENTS.md` loading in fresh Codex CLI and VS Code sessions.
- [x] Verify Codex project skill discovery: `.agents/skills/` and `.codex/skills/` pass; root
      `skills/` is filesystem fallback as an ordinary workspace, while plugin-based discovery
      remains a separate host test.
- [x] Build a disposable, skills-only Agent Plugins 1.0 fixture with a root `plugin.json` and
      one harmless probe skill.
- [x] Install the fixture from a local Git repository path in a temporary VS Code profile; the
      Copilot-hosted Agent Customizations UI showed it enabled with one skill.
- [ ] Repeat direct source installation from a remote HTTPS Git URL; the `file://` form was
      inconclusive and the plain local path is the measured pass.
- [x] Verify the Codex VS Code extension discovers and invokes the generated
      `.agents/skills/` adapter.
- [ ] Verify whether the Codex VS Code extension consumes a VS Code-installed portable plugin;
      the measured installation lacks the Agent Plugins host UI without GitHub Copilot.
- [x] Verify the same fixture with GitHub Copilot in VS Code: the skill appeared in the Plugins
      skill group, was offered as `/canvas-toolbox-packaging-probe`, and returned its marker.
- [ ] Compare direct Git installation, `chat.pluginLocations`, and flattened workspace-local
      skill discovery; the local Git path and workspace-local Codex and Claude paths pass, while
      the remote Git URL and `chat.pluginLocations` remain unmeasured.
- [x] Confirm plugin enable/disable and uninstall behavior without relying on it for safety; the
      visible Skills count and Plugins group changed immediately with enablement, and uninstall
      removed the package from the installed list.
- [ ] Confirm plugin update behavior and capability-change presentation without relying on it for
      safety.
- [x] Verify Claude Code CLI discovery for `.claude/skills/` and an Agent Plugins root loaded
      through `--plugin-dir`.
- [x] Repeat workspace-local discovery in the Claude Code VS Code extension; `.claude/skills/`
      passes and `.agents/skills/` is not discovered there.
- [ ] Repeat portable-plugin discovery in Claude Code after the VS Code plugin host is available.
- [x] Repeat the VS Code discovery test for GitHub Copilot in a temporary profile.
- [ ] Record Continue.dev/Cline/Antigravity/Positron as tested, degraded, or unsupported.
- [x] Test Codex project skills as flat real directories and in-repository symlinks on macOS.
- [ ] Test generated pointer files where a runtime requires them and real copied directories on
      Windows.
- [x] Verify root `AGENTS.md` loading after a fresh ephemeral session; repeat after a VS Code
      reload.
- [x] Verify generated workspace skills appear in Codex and Claude Code UI: Codex rendered named
      skill context and Claude exposed the slash skill and reported its `.claude/skills/` source.
- [x] Verify the portable skill in GitHub Copilot's visible Plugins skill list.
- [x] Create `docs/architecture/adr-001-runtime-neutral-agent-packages.md` and maintain its
      measured support matrix; finalize adapter paths when the remaining host tests pass.
- [x] Review the completed `life-pm` OpenWorker/package plan before freezing shared conventions.
- [x] Record preliminary shared and domain-specific conventions in this plan; preserve the
      final measured decisions in the Phase 1 ADR.
- [x] Update this plan with the initial measurements that disproved native Codex discovery from
      a workspace root `skills/`; continue updating it if later measurements change the path.

**Gate:** Codex, Claude Code, and Copilot adapter paths are based on observed behavior. Codex
passes every required discovery check. The ADR explicitly decides whether Agent Plugins 1.0 is
the primary VS Code package, an additional adapter, or Copilot-only in practice. Current measured
decision: it is an additional portable output with measured Copilot support; Codex and Claude Code
use generated workspace adapters. Remote-URL, `chat.pluginLocations`, update, cross-extension, and
Windows measurements still hold the gate open.

### Phase 2 — Manifest schemas and validator

- [ ] Add the package-manifest JSON Schema.
- [ ] Add the distribution-manifest JSON Schema.
- [ ] Add controlled vocabularies for effects, data classes, approvals, and credential names.
- [ ] Adopt Agent Plugins 1.0's `plugin.json` schema directly for portable metadata; do not
      duplicate its standard fields in a custom schema without a documented reason.
- [ ] Define Canvas-specific package metadata separately rather than placing non-portable
      security fields into `plugin.json`.
- [ ] Implement a read-only `package_validate.py` tool.
- [ ] Validate unique ids and filesystem-safe paths.
- [ ] Validate that declared skills, prompts, tools, references, and assets exist.
- [ ] Validate that distributed paths are tracked by the hidden clone.
- [ ] Validate that every known Canvas writer is declared and approval-gated.
- [ ] Reject Zone-2, secret, raw-submission, and generated grading-output paths.
- [ ] Emit stable JSON and concise human-readable output.
- [ ] Add malformed-manifest, unknown-tool, missing-path, undeclared-writer, and forbidden-path
      fixtures.
- [ ] Add the validator to CI and pre-commit.

**Gate:** invalid packages fail loudly; current behavior is otherwise unchanged.

### Phase 3 — Create canonical agent packages

- [ ] Create `course-design`, `grading`, and `student-support` package directories.
- [ ] Move/copy the eight operating skills into the canonical root `skills/` location required
      by Agent Plugins 1.0.
- [ ] Ensure every skill directory name exactly matches its `SKILL.md` frontmatter name.
- [ ] Consolidate the useful content from historical `lib/agents/*.md` files into package
      `AGENT.md` files.
- [ ] Remove deprecated export-era instructions and self-references.
- [ ] Move shared knowledge and templates to their final single-source location, or document
      a deliberate compatibility location if moving them creates unnecessary risk.
- [ ] Declare every deterministic tool used by each package.
- [ ] Classify every declared tool as read, local write, Canvas content write, grade/comment
      write, or per-student intervention.
- [ ] Declare FERPA/data boundaries for every package.
- [ ] Add a generated package registry and human-readable package catalog.
- [ ] Preserve temporary compatibility pointers from old paths for the migration window.
- [ ] Update all internal links and test them.

**Gate:** manifests validate; package content is single-sourced; no tool behavior changes; all
existing tests pass.

### Phase 4 — Distribution manifest and flattened resolver

- [ ] Add `distribution/manifest.yaml` covering the course-facing payload.
- [ ] Implement deterministic resolution to an exact sorted path set.
- [ ] Change `cb_flatten` to copy the resolved distribution set instead of every tracked file.
- [ ] Keep the prior `.gitignore` block as the before-state for deletion tracking.
- [ ] Show added/removed packages, paths, and capabilities in dry-run output.
- [ ] Verify that developer-only tests, research sources, and internal proposal files are not
      installed unless deliberately listed.
- [ ] Preserve `AGENTS.md` and `.gitignore` hybrid handling.
- [ ] Add recovery behavior for invalid manifests and interrupted updates.
- [ ] Add an explicit legacy-full-manifest migration test.

**Gate:** a fresh flattened install contains exactly the declared distribution; upstream
deletions are removed; course-owned files survive.

### Phase 5 — Agent Plugin package and runtime adapters

- [ ] Implement one deterministic adapter generator.
- [ ] Add a schema-valid root `plugin.json` for Agent Plugins 1.0.
- [ ] Keep portable skills in the root `skills/` directory.
- [ ] Start with no MCP server, or a read-only local probe server, until the MCP threat model is
      reviewed.
- [ ] If an MCP server is proposed, document every exposed tool, subprocess, credential,
      writable path, network destination, and approval path before implementation.
- [ ] Never expose raw Canvas REST write primitives over MCP.
- [ ] Add Copilot-specific agents, rules, commands, or hooks only under the
      `com.github.copilot` namespace.
- [ ] Verify plugin installation directly from the Canvas Toolbox Git repository.
- [ ] Verify plugin updates require a version bump and do not silently grow capabilities.
- [ ] Generate the Codex reference adapter first.
- [ ] Generate the Claude Code adapter and instruction shim.
- [ ] Generate the GitHub Copilot namespace from the same package registry.
- [ ] Generate the generic package index/fallback instructions.
- [ ] Add provenance markers and generator/schema versions.
- [ ] Add idempotency and stale-generated-file tests.
- [ ] Add CI regeneration check.
- [ ] Confirm no adapter duplicates the constitutional FERPA or Canvas-write text.
- [ ] Complete real VS Code smoke tests from Phase 1 for generated output.

**Gate:** one canonical edit regenerates all adapters; the Git repository installs as a valid
Agent Plugin; Codex passes the reference workflow through either the open plugin or its
measured adapter; other clients cannot gain undeclared capabilities.

### Phase 6 — Unify initialization and updates

- [ ] Make the flattened hidden-clone flow the default fresh-install path.
- [ ] Integrate package validation before any flatten apply.
- [ ] Integrate adapter generation/installation.
- [ ] If Phase 1 proves Codex supports Agent Plugins 1.0, offer direct Git plugin installation
      as a convenience while retaining the flattened safety-complete workspace.
- [ ] If an agent does not support Agent Plugins 1.0, continue through the measured local
      adapter path without reducing capability or safety.
- [ ] Do not silently enable a plugin, MCP server, or executable hook merely because VS Code
      supports workspace recommendations.
- [ ] Integrate the AGENTS merge workflow and mandatory `merge_cleanup` gate.
- [ ] Consolidate `cb_update` around `.canvas-toolbox/` and the distribution resolver.
- [ ] Preserve dry-run output before changes.
- [ ] Preserve Canvas credential resolution and token checks.
- [ ] Preserve hook installation and FERPA pattern-count reporting.
- [ ] Add the canonical reload notice after a successful update.
- [ ] Add the weekly fail-open staleness check.
- [ ] Remove obsolete nested/symlink branches only after migration tests pass.
- [ ] Keep setup fully agent-operated; do not send faculty terminal commands.

**Gate:** fresh install and update both finish with a deterministic verification report; no
manual file placement is required.

### Phase 7 — Capability consent and change detection

- [ ] Render a concise install summary for each selected package.
- [ ] Show Canvas-write tools, student-data classes, credential names, and network scope.
- [ ] Persist the approved package/capability fingerprint without storing secrets.
- [ ] Compare installed versus proposed capability sets during update.
- [ ] Require explicit approval when capabilities grow.
- [ ] Do not require special approval for wording-only or capability-reducing updates.
- [ ] Ensure a package cannot approve itself or modify the stored approval.
- [ ] Add tests for added writer, added data class, added connector/network scope, removal, and
      wording-only changes.
- [ ] Make clear that tool/hook enforcement remains authoritative.

**Gate:** capability growth cannot be installed silently.

### Phase 8 — Compatibility and migration tooling

- [ ] Detect standalone toolkit, nested 1.x consumer, already-flat consumer, and non-Canvas
      consumer modes.
- [ ] Add dry-run migrations for each supported source layout.
- [ ] Preserve course-owned `AGENTS.md` learning through the merge gate.
- [ ] Preserve course-owned skills and host configuration.
- [ ] Rewrite old toolkit paths only inside toolkit-owned/generated content.
- [ ] Never rewrite arbitrary course prose without an explicit reviewed plan.
- [ ] Preserve `.env`, global Canvas credentials, course mirrors, grading data, and handoffs.
- [ ] Keep old toolkit clone/content until all post-migration verification passes.
- [ ] Provide a recoverable rollback to the previous hidden-clone commit and installed set.
- [ ] Add migration fixtures for Windows copy fallback and symlink-free environments.

**Gate:** every supported 1.x layout migrates without losing course-owned content or exposing
protected data.

### Phase 9 — Safety regression suite

- [ ] Run all FERPA Zone-2 read-block fixtures.
- [ ] Run pre-push FERPA path and optional content-scan fixtures.
- [ ] Verify `grader_push.py` and `grader_standing.py` remain the only grade/comment writers.
- [ ] Verify direct Canvas write bypass scripts remain blocked.
- [ ] Verify Test Student exclusion and duplicate-comment gates.
- [ ] Verify master/blueprint/section scope confirmation.
- [ ] Verify manifest declarations cannot weaken deterministic enforcement.
- [ ] Verify adapters cannot enable undeclared writes.
- [ ] Verify an unrecognized package/tool fails closed.
- [ ] Verify offline/local audits still run without network access.
- [ ] Run `uv run pytest lib/tests -q` and stop on the first failure.

**Gate:** every constitutional safety invariant has an automated passing test.

### Phase 10 — Faculty-facing acceptance tests

- [ ] Fresh macOS setup in VS Code + Codex using ChatGPT/CES sign-in.
- [ ] Fresh Windows setup in VS Code + Codex using ChatGPT/CES sign-in.
- [ ] Repeat the core setup/audit flow with Claude Code.
- [ ] Repeat the core setup/audit flow with GitHub Copilot where supported.
- [ ] Verify a faculty user never has to understand Git, Python, `uv`, manifests, adapters, or
      `.env` internals.
- [ ] Verify setup clearly requests only Canvas URL, course ID, and Canvas token when needed.
- [ ] Verify the BYU-Idaho-only CES login video remains clearly labeled.
- [ ] Test direct Git installation and update of the Canvas Toolbox Agent Plugin.
- [ ] Test disabling the plugin and confirm the flattened toolkit still gives the agent the
      constitution and safe deterministic commands.
- [ ] Decide whether an optional `.code-profile` materially reduces onboarding steps; reject it
      if it duplicates plugin/adapter state or overwrites user preferences.
- [ ] Test: initialize, restart session, pull course, run read-only audit, edit locally, review a
      push plan, decline, approve in sandbox, update toolkit, and restart again.
- [ ] Record friction and revise setup text/videos before release.

**Gate:** a non-technical tester completes the reference workflow without developer help or
copy-pasting terminal commands.

### Phase 11 — Release candidate and migration rehearsal

- [ ] Update README architecture/setup documentation.
- [ ] Update `docs/UPGRADING.md` with the 1.x-to-2.0 migration.
- [ ] Update the tool catalog and agent-package catalog.
- [ ] Add a 2.0 changelog entry with breaking changes and recovery steps.
- [ ] Remove or clearly mark stale 1.x documentation.
- [ ] Run package/link/schema validation.
- [ ] Run lint and the full test suite.
- [ ] Produce a `2.0.0-rc1` test commit/tag only if the repository release process supports
      prereleases safely.
- [ ] Rehearse fresh install and update against disposable local fixtures.
- [ ] Rehearse migration on approved representative consumer repositories, one at a time.
- [ ] Confirm no local-only commits remain.
- [ ] Keep the PR in draft until every release gate is checked.

**Gate:** release candidate is green, documented, recoverable, and approved by the maintainer.

### Phase 12 — Release `2.0.0`

- [ ] Change `pyproject.toml` version to `2.0.0` in the release PR.
- [ ] Confirm the version is not changed in a docs-only or incomplete checkpoint commit.
- [ ] Mark every required checklist item complete or explicitly move it to a documented 2.x
      follow-up that does not weaken the release contract.
- [ ] Convert the draft PR to ready for review.
- [ ] Review the final diff by trust boundary, not only by file count.
- [ ] Squash-merge through the repository's normal protected-branch workflow.
- [ ] Confirm the automatic `v2.0.0` tag/release workflow succeeds.
- [ ] Verify a fresh install resolves `2.0.0` as latest.
- [ ] Run one post-release fresh-install smoke test.
- [ ] Run one post-release 1.x migration smoke test.
- [ ] Delete the feature branch after successful verification.

**Gate:** `main` is green, `v2.0.0` exists, fresh installs use the new architecture, and the
documented migration works.

---

## 11. Required test matrix

| Scenario | Codex | Claude Code | Copilot | Generic |
|---|---:|---:|---:|---:|
| Agent Plugins 1.0 direct Git install | required discovery test | compatibility test | required | n/a |
| Fresh flat install | required | required | required where supported | required |
| Existing flat 1.x update | required | required | smoke | required |
| Nested 1.x migration | required | required | smoke | required |
| Windows without symlinks | required | required | smoke | required |
| Offline/local audit | required | required | smoke | required |
| Canvas sandbox plan/decline/apply | required | required | smoke | required |
| Grading safety gates | required | required | safety smoke | required |
| Capability-growth update | required | required | required | required |

"Generic" means the deterministic toolkit remains usable even when a host offers no native
skill-discovery mechanism. It does not mean every agent extension is certified.

---

## 12. Verification report contract

Every successful install, migration, or update must report:

- toolkit source commit and version;
- package schema and distribution schema versions;
- installed package ids and versions;
- installed adapter ids and compatibility level;
- constitution integrity result;
- course-learning preservation result;
- skills present and resolvable;
- hook installation result;
- FERPA pattern count;
- credential reachability without credential values;
- added/removed capability summary;
- orphaned toolkit path count;
- test/smoke checks run and any checks skipped.

The operation is not reported as complete if a required verification fails.

---

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Runtime-neutral package becomes Codex-specific in practice | Canonical schema forbids provider requirements; Codex behavior lives in a generated adapter and compatibility tests. |
| Agent Plugins documentation is mistaken for Codex support | Test the actual Codex VS Code extension; retain flattened/local discovery until observed support passes. |
| Plugin installation is mistaken for full course setup | Plugin supplies portable skills/MCP only; course constitution, configuration, files, and deterministic guards remain explicit. |
| Plugin MCP server gains broad local or Canvas access | Skills-only first release; threat model and manifest declaration before any MCP; never expose raw Canvas writes. |
| A VS Code profile changes unrelated user settings | Keep profiles optional and minimal; do not use them as the canonical package or safety layer. |
| Moving skills breaks discovery | Phase 1 measures each runtime first; compatibility files remain until real smoke tests pass. |
| Manifest is mistaken for a security boundary | Constitution and schemas state that deterministic hooks/tools are authoritative; regression tests try to bypass them. |
| Distribution manifest omits a needed runtime file | Fresh-install fixtures compare expected package/tool availability and fail before release. |
| Distribution manifest includes internal or sensitive files | Allowlisted payload plus explicit forbidden-path validation. |
| Capability growth arrives silently | Fingerprint comparison and explicit re-consent gate. |
| Generated adapters drift | One generator, provenance markers, idempotency tests, CI regeneration check. |
| Flatten migration overwrites course content | Exact installed set, hybrid-file handling, dry run, merge backup, deterministic cleanup gate. |
| Old paths linger and agents invoke stale instructions | Previous-installed-set subtraction removes upstream deletions; orphan verification must be zero. |
| Cross-platform path/symlink differences | Real Windows tests and copy-based adapters; no correctness dependency on symlinks. |
| Scope expands into a Python rewrite | Existing `lib/tools` paths stay stable until packaging requires a measured change. |
| Large long-lived branch becomes unreviewable | One phase per focused commit; continuously pushed draft PR; phase gates and recorded test evidence. |

---

## 14. Rollback

Before every migration/update apply:

1. Record the hidden clone commit.
2. Record the exact currently installed path set from the course `.gitignore` block.
3. Preserve `AGENTS.merge.md` until `merge_cleanup.py` passes.
4. Preserve old nested toolkit content until all migration verification passes.
5. Never alter `.env`, grading data, course mirrors, or course-owned skills as rollback
   bookkeeping.

Rollback restores the hidden clone to the recorded commit and resolves/reinstalls that
commit's distribution set. Rollback must be dry-run-capable and must report files it will add,
replace, and remove.

---

## 15. Definition of done

Canvas Toolbox 2.0 is done only when:

- [ ] Canonical agent packages are runtime-neutral and schema-valid.
- [ ] The repository is a schema-valid Agent Plugins 1.0 source with portable skills.
- [ ] Agent Plugins support in Codex is recorded as measured support or measured non-support;
      the release does not assume it.
- [ ] Codex in VS Code is the fully passing reference adapter.
- [ ] Claude Code and GitHub Copilot have measured, documented adapters.
- [ ] The generic deterministic path works without native skill discovery.
- [ ] Fresh initialization uses the flattened hidden-clone architecture.
- [ ] Updates use an explicit distribution manifest and remove stale toolkit files.
- [ ] Capability growth requires renewed approval.
- [ ] All FERPA and Canvas-write safeguards remain deterministic and tested.
- [ ] Nested and already-flat 1.x course repositories migrate safely.
- [ ] A non-technical faculty tester completes the reference workflow.
- [ ] Documentation and videos match the shipped workflow.
- [ ] Full tests, lint, schema validation, and smoke tests pass.
- [ ] `pyproject.toml`, changelog, and upgrade documentation identify `2.0.0`.
- [ ] The release is merged through a reviewed PR and verified after tagging.

---

## 16. References

- [VS Code: Agent plugins](https://code.visualstudio.com/docs/agent-customization/agent-plugins)
  — Agent Plugins 1.0 layout, installation, updates, client namespaces, and trust notes.
- [OpenWorker persona manifest](https://github.com/andrewyng/openworker/blob/main/coworker/personas/builtin/security/manifest.md)
  — representative self-describing specialist bundle.
- [OpenWorker manifest parser](https://github.com/andrewyng/openworker/blob/main/coworker/personas/manifest.py)
  — strict parsing and capability declarations.
- [OpenWorker capability consent](https://github.com/andrewyng/openworker/blob/main/coworker/personas/loading.py)
  — install summary and capability-growth comparison.
- [`flat-layout-and-agents-merge.md`](flat-layout-and-agents-merge.md) — prerequisite
  flattened installation and AGENTS merge design.

Sources were reviewed on 2026-09-14. External formats must be rechecked before Phase 1 and
again before the release candidate because they may evolve during the 2.0 implementation.

---

## 17. Progress log

Add one entry after each completed phase. Do not mark a phase complete without its gate
evidence.

| Date | Phase | Commit/PR | Evidence | Decision or follow-up |
|---|---|---|---|---|
| 2026-09-14 | Plan created | `d754cca` / #317 | Current code and flatten proposal reviewed; 1374 tests passed in 246.34s | Added Agent Plugins 1.0 as a measured, skills-first portable target; compare `life-pm` before schema freeze |
| 2026-09-14 | Cross-repository alignment review | pending / #317 | Completed `life-pm` proposal read in full and compared against Canvas package, schema, adapter, distribution, consent, profile, and update decisions | Share the neutral architecture vocabulary without coupling releases; retain domain-specific safety schemas; carry final measured choices into the Phase 1 ADR |
| 2026-09-14 | Phase 0 complete | pending / #317 | Branch and draft PR verified; 1374-test baseline green; fresh, nested, and flat structural fixtures recorded without reading course or Zone-2 data | Begin runtime discovery; product behavior remains unchanged |
| 2026-09-14 | Runtime discovery spike (partial) | pending / #317 | Codex root constitution, project paths, real directories, and symlinks measured; Claude project/plugin paths measured; disposable Codex plugin validated; marketplace runtime path defect reproduced and cleaned up | Use root `skills/` as canonical, generate `.agents/skills/` and `.claude/skills/`, keep both plugin manifests thin, and hold Phase 2 until VS Code/Copilot measurements finish |
| 2026-09-14 | VS Code extension discovery (partial) | pending / #317 | Codex invoked the generated `.agents/skills/` probe; Claude Code invoked and identified `.claude/skills/`; Agent Plugins commands/UI were absent without GitHub Copilot, so no portable plugin was installed | Keep workspace adapters as the subscription-extension baseline; treat Agent Plugins 1.0 as an additional portable/Copilot-hosted output pending an approved Copilot profile test |
| 2026-09-14 | Copilot Agent Plugin discovery (partial) | pending / #317 | A temporary profile activated the built-in Copilot host; local source installation passed; the plugin and its one skill were visible; `/canvas-toolbox-packaging-probe` returned the expected marker; root `AGENTS.md` remained active | Agent Plugins 1.0 has measured Copilot support but remains an additional output; retain Codex and Claude workspace adapters and finish remote-source, lifecycle, cross-extension, and Windows checks |
| 2026-09-14 | Copilot Agent Plugin lifecycle (partial) | pending / #317 | Disable changed the visible Skills count from 25 to 24 and removed the Plugins group; re-enable restored both; uninstall changed Installed to zero; all four exact disposable probe/profile paths were removed | Enable, disable, and uninstall are measured passes; update and capability-change presentation remain release-gate measurements |

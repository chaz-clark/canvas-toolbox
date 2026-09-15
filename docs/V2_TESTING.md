# Canvas Toolbox 2.0 Testing Guide

This is the maintainer-facing acceptance path for Canvas Toolbox 2.0. It turns the implementation
plan into small tests that can be run without risking an existing course repository or writing to
Canvas.

The detailed architecture and engineering checklist remain in
[`docs/proposals/v2-agent-packaging-plan.md`](proposals/v2-agent-packaging-plan.md). Measured runtime
behavior is recorded in
[`docs/architecture/adr-001-runtime-neutral-agent-packages.md`](architecture/adr-001-runtime-neutral-agent-packages.md).

## Current readiness

_Last updated: 2026-09-15, after Phase 9 (safety regression suite)._

| Test stage | Status | May use an existing `*-master` repository? |
|---|---|---|
| Runtime discovery and architecture review | Complete | No course repository is needed. |
| **Stage 1** — Automated repository tests | **Complete** | No. |
| **Stage 2** — Disposable local repositories | **Partially ready** — see note | No. |
| **Stage 3** — Canvas sandbox, read-only first | Not ready | No — needs a Canvas sandbox connection, not yet run. |
| **Stage 4** — One selected `*-master` pilot | Not ready | No. |
| **Stage 5** — Additional master repositories | Not ready | No. |
| **Stage 6** — Faculty beta and release | Not ready | No. |

**Do not migrate a real course while its stage says "Not ready."** A checked implementation task is
not enough by itself; the preceding gate must pass and this table must be updated in the same pull
request.

**Stage 1, in full:** schema/validator (Phase 2), package classification (Phase 3), the
distribution resolver (Phase 4), Agent Plugin + generated adapters (Phase 5), flat init/update
orchestration (Phase 6), capability consent (Phase 7), nested-to-flat migration tooling (Phase 8),
and the cross-cutting safety regression suite (Phase 9) — 1492 automated tests, all passing, no
course repository touched. Two real, previously-undetected safety gaps were found and fixed along
the way (a flat-mode guardian hook silently inert due to a hardcoded nested path — Phase 6; a
bypass-detection regex blind to the quiz-score write mechanism — Phase 9, also ported to `main`).

**Stage 2, what's done vs. outstanding:** every item in this stage's own bullet list was run
against real git and real synthetic fixtures — fresh installation, repeat installation and update,
migration from nested and already-flattened layouts, course-owned-file preservation, stale-file
removal, and rollback after an interrupted or invalid update — repeatedly, with defects found and
fixed by the fixtures themselves rather than assumed away (see the Phase 4, 6, 7, and 8 progress
log entries). The one bullet NOT done: **"Codex, Claude Code, Copilot, and generic workspace
adapter discovery where available"** — this requires an actual VS Code session with each extension
installed and cannot be performed by an agent working non-interactively. Phase 1's ADR already
carries the closest available evidence (a disposable probe fixture, not the real package). Stage 2
cannot close until this one item is run by the maintainer.

**Stage 3 onward are entirely gated on human hands** — a live Canvas sandbox connection, real VS
Code + Codex/Claude Code/Copilot sessions on macOS and Windows, and a maintainer-selected pilot
repository. None of these can be completed or simulated by an agent alone; this file's own Stage 4
rollback/approval design (Phase 8's `migrate_nested_to_flat.py`) is ready and tested, but running it
against a real repository is exactly what these stages exist to gate.

## Testing ladder

Each stage must pass before the next begins.

### Stage 1 — Automated repository tests

The agent runs schema, validator, package-resolution, adapter-generation, flattening, migration,
and safety-regression tests in this repository. A failure stops the build. This stage never reads a
course repository or contacts Canvas.

### Stage 2 — Disposable local repositories

The agent creates temporary empty repositories and representative synthetic 1.x layouts. It tests:

- fresh installation;
- repeat installation and update;
- migration from nested and already-flattened layouts;
- preservation of course-owned files;
- removal of stale toolkit-owned files;
- rollback after an interrupted or invalid update;
- Codex, Claude Code, Copilot, and generic workspace adapter discovery where available.

Fixtures use visibly fake course content and no Canvas credentials. Temporary directories are
listed before deletion and removed after their results are recorded.

### Stage 3 — Canvas sandbox, read-only first

After the disposable tests pass, the agent installs the candidate in a new private test repository
connected only to the configured Canvas sandbox. The first acceptance run is read-only: initialize,
verify credentials, pull the sandbox course, and run a course audit. No Canvas content, grade,
comment, or accommodation write is part of this stage.

Any later Canvas write test requires its own explicit scope confirmation and the existing sanctioned
tool. The v2 packaging work does not weaken or replace those gates.

### Stage 4 — One selected `*-master` pilot

The maintainer chooses one low-risk course repository. The agent then:

1. verifies the repository and working tree before changing anything;
2. creates a dedicated migration branch;
3. records the installed 1.x layout and hidden-clone revision;
4. runs the migration in dry-run mode;
5. explains every proposed local file addition, replacement, and removal;
6. waits for explicit approval before applying the local migration;
7. runs the deterministic verification report and read-only course workflow;
8. leaves Canvas unchanged;
9. provides the exact rollback point and a reviewable diff.

One passing pilot does not authorize migrating the rest of the course fleet.

### Stage 5 — Additional master repositories

Additional `*-master` repositories are migrated one at a time after the first pilot is reviewed.
Each gets its own branch, dry run, verification report, and approval. Repositories with local layout
differences become explicit migration fixtures before the fleet continues.

### Stage 6 — Faculty beta and release

The README setup walkthrough and videos are tested by a non-technical user on fresh macOS and
Windows installations. The user should be able to complete setup by talking to their chosen VS Code
agent without copying terminal commands or understanding Git, Python, `uv`, manifests, adapters, or
`.env` internals.

Only after this passes does the release branch change the package version to `2.0.0` and make the
new README workflow the default.

## Prompt for the current development stage

Use this prompt only in the Canvas Toolbox repository—not in a course repository:

> Continue the Canvas Toolbox 2.0 plan on `feat/v2-agent-packaging`. Read `AGENTS.md`,
> `docs/V2_TESTING.md`, the v2 packaging plan, and ADR-001 before acting. Work only on the next
> unchecked implementation phase whose prerequisites pass. Run the required automated and
> disposable tests, stop on the first defect, update the checklist and progress log with measured
> evidence, and do not access an existing course repository or perform a Canvas write.

## Prompt for a future course pilot

This prompt becomes active only when the selected-master stage above says **Ready**:

> Help me test Canvas Toolbox 2.0 in this course repository. Read the v2 testing guide first. Verify
> that this stage is marked Ready, confirm the repository and branch, and run the migration dry run.
> Explain the proposed file changes and rollback point before applying anything. Do not write to
> Canvas. Stop and report any failed gate instead of working around it.

## Recording results

Every completed stage records:

- date and exact commit;
- operating system, VS Code version, and agent extension/version;
- fresh install, update, or migration source layout;
- commands performed by the agent;
- tests and observable result;
- temporary data created and cleanup status;
- defects or degraded behavior;
- decision and next gate.

Repository-level results go in the v2 plan’s progress log. A course pilot records only non-sensitive
structural evidence; Canvas tokens, student data, course-specific institutional facts, and FERPA
Zone-2 files never enter the public Canvas Toolbox repository.

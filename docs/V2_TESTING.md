# Canvas Toolbox 2.0 Testing Guide

This is the maintainer-facing acceptance path for Canvas Toolbox 2.0. It turns the implementation
plan into small tests that can be run without risking an existing course repository or writing to
Canvas.

The detailed architecture and engineering checklist remain in
[`docs/proposals/v2-agent-packaging-plan.md`](proposals/v2-agent-packaging-plan.md). Measured runtime
behavior is recorded in
[`docs/architecture/adr-001-runtime-neutral-agent-packages.md`](architecture/adr-001-runtime-neutral-agent-packages.md).

## Current readiness

| Test stage | Status | May use an existing `*-master` repository? |
|---|---|---|
| Runtime discovery and architecture review | Complete | No course repository is needed. |
| Package schemas and validator | Not ready | No. |
| Canonical packages and generated adapters | Not ready | No. |
| Disposable fresh installation | Not ready | No. |
| Disposable 1.x-to-2.0 migration | Not ready | No. |
| Selected `*-master` pilot | Not ready | No. |
| General faculty beta | Not ready | No. |

**Do not migrate a real course while its stage says “Not ready.”** A checked implementation task is
not enough by itself; the preceding gate must pass and this table must be updated in the same pull
request.

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

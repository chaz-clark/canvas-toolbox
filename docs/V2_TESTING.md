# Canvas Toolbox 2.0 Testing Guide

This is the maintainer-facing acceptance path for Canvas Toolbox 2.0. It turns the implementation
plan into small tests that can be run without risking an existing course repository or writing to
Canvas.

The detailed architecture and engineering checklist remain in
[`docs/proposals/v2-agent-packaging-plan.md`](proposals/v2-agent-packaging-plan.md). Measured runtime
behavior is recorded in
[`docs/architecture/adr-001-runtime-neutral-agent-packages.md`](architecture/adr-001-runtime-neutral-agent-packages.md).

## Current readiness

_Last updated: 2026-09-15, after real rehearsals against a live, verified-empty Canvas sandbox
(macOS) and native Windows 11 (Parallels)._

| Test stage | Status | May use an existing `*-master` repository? |
|---|---|---|
| Runtime discovery and architecture review | Complete | No course repository is needed. |
| **Stage 1** — Automated repository tests | **Complete** | No. |
| **Stage 2** — Disposable local repositories | **Partially ready** — see note | No. |
| **Stage 3** — Canvas sandbox, read-only first | **Rehearsed — real evidence, not a fixture** — see note | No — ran against a disposable `demo-master` repo, not an existing `*-master`. |
| **Stage 4** — One selected `*-master` pilot | Not ready — mechanics rehearsed on both macOS and Windows, not on a real repo | No. |
| **Stage 5** — Additional master repositories | Not ready | No. |
| **Stage 6** — Faculty beta and release | Not ready | No. |

**Do not migrate a real course while its stage says "Not ready."** A checked implementation task is
not enough by itself; the preceding gate must pass and this table must be updated in the same pull
request.

**Stage 1, in full:** schema/validator (Phase 2), package classification (Phase 3), the
distribution resolver (Phase 4), Agent Plugin + generated adapters (Phase 5), flat init/update
orchestration (Phase 6), capability consent (Phase 7), nested-to-flat migration tooling (Phase 8),
and the cross-cutting safety regression suite (Phase 9) — 1500 automated tests, all passing, no
course repository touched. Two real, previously-undetected safety gaps were found and fixed along
the way (a flat-mode guardian hook silently inert due to a hardcoded nested path — Phase 6; a
bypass-detection regex blind to the quiz-score write mechanism — Phase 9, also ported to `main`).

**Stage 2, what's done vs. outstanding:** every item in this stage's own bullet list was run
against real git and real synthetic fixtures — fresh installation, repeat installation and update,
migration from nested and already-flattened layouts, course-owned-file preservation, stale-file
removal, and rollback after an interrupted or invalid update — repeatedly, with defects found and
fixed by the fixtures themselves rather than assumed away. The one bullet NOT done: **"Codex, Claude
Code, Copilot, and generic workspace adapter discovery where available"** — this requires an actual
VS Code session with each extension installed and cannot be performed by an agent working
non-interactively. Stage 2 cannot close until this one item is run by the maintainer.

**Stage 3 — what actually happened, not a simulation.** The maintainer confirmed a real Canvas
sandbox course (427808), verified with real evidence — not just its name — as carrying 0 enrolled
students via `canvas_course_guard.check_course_safety()` (an actual, read-only `GET /courses/:id`
call) before it was used for anything. A disposable `demo-master` repository was built as a nested
1.x layout (a real local clone of `canvas-toolbox` at `main`, matching what an actual course repo
has today) and pointed at that sandbox. Then, for real, not simulated:

- `migrate_nested_to_flat.py` ran end to end against it — dry run, apply, the AGENTS.md merge and
  `merge_cleanup.py` gate, `--finalize` — while `main` still lacks `distribution/manifest.yaml`, so
  this also proved the documented legacy-fallback behavior for real (385 files copied, not the
  curated ~280 — expected, and a genuine finding about what a pilot run *today*, before this branch
  merges, would actually get).
- The hidden clone was then switched to `feat/v2-agent-packaging` and re-flattened — a real
  first-time capability-consent prompt fired (all three packages, correctly listing every
  Canvas-write tool by name), was approved, and recorded to `.canvas-toolbox-approvals.json`.
- `course_audit.py` ran twice against the live sandbox — a real authenticated API call, a real
  audit artifact, real findings (missing rubrics, an incomplete syllabus) — and the weekly
  staleness check fired correctly against a real `git ls-remote`.

**This rehearsal found and fixed a real bug that no synthetic fixture had exercised**:
`credentials_resolve()` and `canvas_smoke_test()` each checked one credential source at a time for
both required keys, so a real, legitimate, common split (`CANVAS_BASE_URL` in the course's own
`.env`, `CANVAS_API_TOKEN` in `~/.canvas/config`) was reported as unresolved even though
`_env_loader.load_env()` — and every actual tool — handled it correctly. Fixed with one shared
per-key merge helper, both functions now use it, and the real sandbox call succeeded after the fix.

**What this does and does not close:** this is real Canvas-sandbox evidence, not a fixture — Stage
3's read-only acceptance criteria were genuinely exercised. It is **not** Stage 4, because
`demo-master` is a disposable rehearsal repo, not one of the six real `*-master` repositories — the
mechanics are now proven, but "one maintainer-selected `*-master` repository" still means an actual
one. Stages 5–6 remain entirely gated on real VS Code sessions (macOS and Windows), real
non-technical faculty, and real additional repositories — none of which an agent can perform or
substitute for.

**Native Windows rehearsal — Phase 8's Windows checklist item, closed with real evidence.**
Every prior migration test had run on macOS, including fixtures written to simulate Windows path
and symlink behavior. This rehearsal ran the real thing: a Parallels-hosted Windows 11 VM, driven
non-interactively via `prlctl exec`. Setup — `uv`, Python 3.14 (via `uv python install`), and Git
for Windows 2.47.0 — then a fresh `C:\demo-master\` nested-layout fixture: a real `git clone` of
`canvas-toolbox` at `main`, all 8 skill symlinks created explicitly, a demo-labeled `AGENTS.md`
(deliberately with no Canvas `.env` — this fixture is file-operations-only, not a second Canvas
connection test), then checked out to `feat/v2-agent-packaging`.

`migrate_nested_to_flat.py --apply` ran clean on the first try: layout detection, symlink removal,
the curated 282-file distribution copy (matching the macOS result exactly), and guardian-hook
installation with Windows-appropriate paths all passed their verification checks. But the two steps
after that each hit a real, previously-undetected, Windows-only bug that no macOS-based fixture —
real or simulated — had ever exercised:

- **`merge_cleanup.py` crashed reading `AGENTS.md`'s own git history.** It ran `git log`/`git show`
  through `subprocess.run(text=True)`, which decodes stdout using the platform's default
  encoding — cp1252 on Windows, not UTF-8. A past revision containing a character outside cp1252
  (this toolkit's own tool output uses "✓" and em dashes throughout) raised `UnicodeDecodeError`
  inside git's stdout reader thread; that exception isn't propagated by `subprocess.run`, so the
  call silently returned `stdout=None` and the tool crashed with an unhandled `AttributeError`
  instead of its own documented best-effort fallback. Fixed by decoding as UTF-8 explicitly
  (`lib/tools/merge_cleanup.py`, `lib/tools/cb_flatten.py`'s identical `_git()` helper).
- **`--finalize` crashed deleting the old nested clone.** Git marks `.git/objects/pack/*` read-only
  on every platform, but only Windows' `os.unlink()` actually enforces that bit against the
  caller — POSIX deletion permission comes from the containing directory, not the file's own mode,
  so `shutil.rmtree()` on a real git clone had never failed this way on macOS or Linux. Fixed with a
  wrapper that clears the read-only attribute and retries (`lib/tools/migrate_nested_to_flat.py`).

Both fixes were pushed, pulled into the live VM, and the failing step was re-run from the point of
failure — not just re-run from scratch — confirming each fix against the exact real failure it was
written for. The rehearsal then completed for real: `merge_cleanup.py` passed its full
constitution-intact / course-learning-preserved / line-budget verification once the fixture's course
content was curated into a marked section, and `--finalize` removed the nested clone cleanly,
leaving `.canvas-toolbox/` as the sole hidden clone and no leftover `AGENTS.merge.md`.

Neither bug could have been caught by a fixture built or run on macOS — one is a platform-default
text-decoding difference, the other a platform difference in what a file's own permission bits
control. This is the specific gap real cross-platform testing exists to close, and it closed it
twice in one rehearsal.

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

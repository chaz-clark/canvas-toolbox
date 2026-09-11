# Flat Layout + AGENTS.md Merge Skill — Implementation Plan

**Status:** proposal · **Supersedes:** the v1.6 course-centric (nested `canvas-toolbox/`) layout

---

## The problem, with evidence

The nested layout mirrors *some* of the toolkit to the course root and points at the rest.
Four of the five things that make the toolkit usable already work nested; one does not.

| Surface | Nested today | Mechanism |
|---|---|---|
| Skills | ✅ works | `cb_update` symlinks `<root>/.claude/skills/<s>` → vendored |
| Hooks | ✅ works | `.claude/settings.json` → `canvas-toolbox/lib/tools/grade_guardian.py` |
| Tools | ✅ works | invoked by path |
| Knowledge | ✅ works | read by path |
| **AGENTS.md content** | ❌ **pointer only** | sentinel block says *"the constitution lives in `canvas-toolbox/AGENTS.md`. Read it."* |

The cost of bridging that gap is **893 lines** (`cb_update.py` 709 + `sync_grading_protocol.py` 184):
symlink management, Windows copy-fallback, per-skill gitignore, sentinel-block healing.

`ds295r-ai-engineering` is a forced-flat install and proves flat solves the one real gap —
its root `AGENTS.md` is the constitution verbatim, fully auto-loaded. It also proves the two
costs of doing flat *without* a plan:

1. **Course learning was dropped.** Frontmatter reads `name: canvas-toolbox-agents`,
   `repo: canvas-toolbox`. No HERMES section exists. That repo's agent is generic.
2. **It cannot be updated.** `origin` is `chaz-clark/ds295r-ai-engineering` — no toolkit
   upstream. It is 350 lines vs the toolkit's current 356: frozen *before* the
   `--allow-enrolled` carve-out (#308). That fix cannot reach it.

**Goal:** flat's full-constitution loading, without losing course learning or updateability.

---

## Target layout

```
DS250/                         # the course repo
├── .canvas-toolbox/           # hidden pristine git clone — update source (gitignored)
├── .claude/
│   ├── settings.json          # hook wiring
│   ├── skills/                # flattened from toolkit (real dirs, not symlinks)
│   └── commands/              # flattened from toolkit
├── lib/  bin/  docs/  knowledge/   # flattened toolkit
├── pyproject.toml  uv.lock  .python-version
├── AGENTS.md                  # toolkit constitution + merged HERMES learning
├── .env  .canvas/             # course
├── course/  course_ref/  grading/  # course
└── .gitignore                 # generated: toolkit paths + course-local paths
```

`AGENTS.merge.md` exists **only during an update** — see Phase 3.

### Ownership rule

`git -C .canvas-toolbox ls-files` is the authoritative manifest.

- Path **in** the manifest → toolkit-owned, replaced wholesale on update.
- Path **not in** the manifest → course-owned, never touched.
- `AGENTS.md` is the **single exception** (hybrid) — merge skill, never wholesale replace.

Nothing else is hybrid. This is what keeps the update logic small.

---

## Phase 1: The hidden clone

`.canvas-toolbox/` is a pristine checkout, never edited, never executed from. It exists to:

- give `git pull` something clean to pull into (no conflicts — nothing local ever changes)
- provide the manifest for free (`git ls-files`)
- provide deletion tracking for free (manifest before vs. after)

### Success criteria
- `git -C .canvas-toolbox status --porcelain` is always empty.
- `git -C .canvas-toolbox pull` never conflicts.
- Clone is gitignored from the course repo.

---

## Phase 2: Flatten / sync

```
old_manifest = git ls-files @ current HEAD
git pull
new_manifest = git ls-files @ new HEAD

deleted = old_manifest - new_manifest      → remove from root
for f in new_manifest, f != AGENTS.md:     → copy to root (overwrite)
```

Deletion tracking is a set difference, not bespoke logic — that is the whole reason the
hidden clone is worth keeping.

### Collision rule (must be decided before build)

The toolkit ships `README.md`, `CHANGELOG.md`, `LICENSE`. `ds460-master` has its **own**
`README.md` *and* `README_CLARK.md`. Flattening overwrites the course's `README.md` —
this is a real, demonstrated collision, not hypothetical.

**Proposed:** toolkit `README.md` / `CHANGELOG.md` / `LICENSE` are **excluded from the
flatten manifest**. They are toolkit-repo artifacts with no function in a course repo —
the constitution is `AGENTS.md`, not `README.md`. Course keeps its own.

### Success criteria
- A file deleted upstream disappears from the course root on next update.
- No course-owned path is ever written.
- `README.md` in a course repo survives an update untouched.

---

## Phase 3: The AGENTS.md merge skill

### Flow

1. `mv AGENTS.md AGENTS.merge.md` (old file, carries HERMES learning)
2. copy `.canvas-toolbox/AGENTS.md` → `AGENTS.md` (fresh constitution)
3. invoke the **merge skill**
4. verify (Phase 5)
5. delete `AGENTS.merge.md` **only after verification passes**

If the skill never runs or aborts, `AGENTS.merge.md` persists next to a generic
`AGENTS.md` — a detectable broken state, healed on the next update run. Nothing is lost.

### Merge skill contract

**Hard rule — the toolkit half is copied byte-for-byte.** The skill applies judgment to
the *course* half only. Constitutional safety text (FERPA Zone-2, Canvas-write doctrine)
is never paraphrased, reordered, or summarized. This is what makes an LLM-driven merge
acceptable on a safety-critical file.

The skill:
1. Diffs `AGENTS.merge.md` against `.canvas-toolbox/AGENTS.md` to isolate course-specific content.
2. Curates that content **with a fresh lens** — drop stale entries, compress redundant ones,
   keep what is still true of the course. This is the part a script cannot do.
3. Appends it under a clearly-marked course section.

### Token budget

| | Lines |
|---|---|
| Toolkit constitution | ~356 |
| Course half budget | **≤ 400** |
| Total target | **< 800** (AGENTS-QC-010 soft warn) |
| Hard flag | 1200 |

Current course files: itm327 466 · ds460 425 · ds250 532. All have course halves that fit
the budget after curation; ds250 will need the most pruning.

### Success criteria
- Toolkit half of the merged file is byte-identical to `.canvas-toolbox/AGENTS.md`.
- If `AGENTS.merge.md` had course content, the merged file has a non-empty course section.
- Merged file < 800 lines.
- Re-running the merge on an already-merged file is a no-op.

---

## Phase 4: Weekly staleness check

**Not a `SessionStart` hook** — those are Claude-Code-only, and the supported surface is
VS Code + Claude Code / Codex / Copilot / Continue.dev / Cline, plus Antigravity and Positron.

Put it in `_env_loader.load_env()` — **94 of 120 tools already import it** (#304/#305 made
that routing universal). It fires below the agent layer, so it is tool-agnostic by construction.

```
read .canvas-toolbox/.update_check   # cheap path, no network
if age < 7 days: return
git ls-remote origin main            # lighter than fetch; short timeout
if behind: one line to stderr
always: wrap in try/except — never break a tool run
```

Timestamp lives per-clone so five course repos don't suppress each other's notices.
Fail-open matches `canvas_course_guard`'s existing rule: a check must never break a tool.

### Success criteria
- No network call on the common path.
- Offline / timeout / git-missing → silent, tool still runs.
- Notice appears at most once per 7 days per course repo.

---

## Phase 5: Verification (TBP — non-negotiable)

Every update ends with a check that reports pass/fail:

| Check | Method |
|---|---|
| Toolkit half intact | hash `AGENTS.md` toolkit section vs `.canvas-toolbox/AGENTS.md` |
| Course learning survived | course section non-empty when `.merge.md` had content |
| Token budget | line count < 800 |
| Skills present | every toolkit skill resolves at `.claude/skills/` |
| Hook wired | `grade_guardian` present in `.claude/settings.json` |
| Manifest clean | no orphaned files from the previous manifest |

An update that cannot verify its own result reports **failed**, not "done."

---

## Phase 6: Reload notice

One canonical, single-sourced, tool-agnostic string — same idiom as `POINTER_BLOCK`,
never a per-tool if/else:

> **Updated.** Restart your AI session (new chat, reload the extension, or restart the IDE)
> for the refreshed constitution to take effect — `AGENTS.md` is read once at session start.

---

## Phase 7: Migrating the six nested repos

`cse450-master · ds250-onln-master · ds460-master · itm327-master · m119-master · mathcourses-master`

One-time `cb_flatten`, dry-run by default:

1. Create `.canvas-toolbox/` from the existing nested `canvas-toolbox/` (preserve remote + HEAD).
2. Flatten manifest files to root (honoring the Phase 2 collision rule).
3. Replace skill **symlinks** with real flattened directories.
4. `mv AGENTS.md AGENTS.merge.md` → run the merge skill (their existing course AGENTS.md
   is exactly the HERMES input this is designed for).
5. Rewrite `canvas-toolbox/lib/...` → `lib/...` in `.claude/settings.json` and course docs.
6. Regenerate `.gitignore`.
7. Remove `canvas-toolbox/` **only after verification passes**.

`ds295r-ai-engineering` migrates differently — it is already flat but has **no upstream**
and **no course content**. It needs `.canvas-toolbox/` added and re-pointed at the toolkit
remote; there is no HERMES content to preserve.

### Success criteria
- Dry-run diff reviewed per repo before `--apply`.
- Post-migration verification (Phase 5) passes in all six.
- A fresh session in each repo sees the constitution and the toolkit skills.

---

## Risks

| Risk | Mitigation |
|---|---|
| LLM merge is non-deterministic on a safety-critical file | Toolkit half copied verbatim + hash-verified. Judgment applies to course content only. |
| Merge skill never runs → broken intermediate state | `.merge.md` persists; state is detectable and healed on next run. Nothing lost. |
| Flatten clobbers a course file | Manifest-scoped writes + explicit README/CHANGELOG/LICENSE exclusion. |
| Course repo `git status` floods with toolkit files | Generated `.gitignore` from the manifest, regenerated every update. |
| Skills discovery at course root is assumed, not proven | **Open — see below.** |

---

## Open question to resolve first

Tests cover symlink *creation*; nothing verifies the agent actually *discovers* skills at a
course root. The claim rests on `cb_update`'s docstring. Before building Phase 7, open a
session in `ds460-master` and confirm the toolkit's eight skills appear in the listing and
the agent knows the FERPA rules unprompted.

If nested discovery already works, flat is a simplification (delete 893 lines of bridging).
If it does not, flat is a **fix**, and the migration is more urgent.

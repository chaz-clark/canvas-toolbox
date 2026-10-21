# Clone health + install testing plan

_Created 2026-10-21. Status: in progress. Trigger: a Windows colleague's update failed twice
(Codex sandbox write block, then a toolkit folder that was a `git init` repo with no commits)._

## What happened

- **Codex sandbox (fixed, #410, 2.1.4):** on Windows, Codex runs commands as a hidden
  `CodexSandboxOffline` account that can read the repo but not write `.git`, so `git pull`
  died on `FETCH_HEAD`. `cb_flatten --pull` now prints a "rerun with full access" hint.
- **Half-updated state (fixed, #414, 2.1.6):** consent is checked after `--pull`, so a refusal
  left the clone updated and nothing copied. The refusal now says so. (Part of #413; the
  chat-verifiable approval question stays open there.)
- **Not a real clone (this plan):** her toolkit folder was on `master` with no commits and no
  upstream — what `git init` produces. A real clone is on `main` tracking `origin/main`. Git
  was not installed when she first asked for an update, so the folder was never made by
  `git clone`. The README setup prompt assumes Git exists and the clone works; nothing checks.

## Part 1 — Changes (one PR, 2.1.7)

| # | Change | Where |
|---|---|---|
| A | Clone-health check returning `ok`, `no-git`, `not-a-repo`, `no-commits`, `no-origin`, `no-upstream` (no wrong-remote check: adopters may use a private fork), each with a plain-language message and the exact repair steps. Detect and message only — no auto-repair (`reset --hard` overwrites files; the nested toolkit may be dev-edited). | shared helper; called from `cb_update --pull`, `cb_flatten --pull`, `cb_init` |
| B | Preflight in setup: check Git first; install it (`winget` on Windows, Xcode tools on Mac) if missing; never substitute a ZIP download or `git init`; on a permission block, ask for full access. | README setup prompt, `cb_init.py` |
| C | Extend the Codex sandbox learned note with the `git init` finding and the no-Git case. | `lib/agents/knowledge/learned/` |

Tests for A use real temporary git repos (init-only, wrong remote, healthy clone), not mocks.

## Part 2 — Test matrix (Mac and Windows/Parallels)

"Me" = scripted fixture and checks. "You" = a real IDE session an agent can't drive.

| # | Scenario | Mac | Windows | Who |
|---|---|---|---|---|
| 1 | Fresh install from the README prompt, Git present | yes | yes | You |
| 2 | Fresh install with no Git (Mac: strip Git from PATH; Windows: clean snapshot) | yes | yes (the real one) | You |
| 3 | Update from a `git init` folder with no commits; health message appears, repair steps work | scripted | scripted | Me |
| 4 | No-origin and no-upstream variants | scripted | scripted | Me |
| 5 | Consent refused after pull (#414 notice), then the finish command | scripted | scripted | Me |
| 6 | Update blocked by the Codex sandbox (#410 hint), retry with full access | to check (Codex's Mac sandbox may also restrict `.git` writes — unverified) | required | You |
| 7 | Repo owned by a different user ("dubious ownership") | skip | yes | Me |
| 8 | Folder path with spaces, or inside OneDrive/Documents | quick | yes | You |
| 9 | Adapter discovery in Codex, Claude Code, Copilot (the open V2_TESTING bullet) | yes | yes | You |
| 10 | Nested v2.0.22 to flat migration, rerun with current fixes | yes | yes | Me |

## Order

1. Issue + A, B, C with tests; full suite before push.
2. Scripted rows (3, 4, 5, 7, 10) on Mac, then on the VM.
3. Real-session rows (1, 2, 6, 8, 9) on the VM from a clean no-Git snapshot.
4. Record results in `docs/V2_TESTING.md`.

**Exit criteria:** every row passes on both platforms, or has a filed issue and a stated reason.

## Results

_2026-10-21, scripted rows, real fixtures, branch `feat/clone-health-check` (#415)._

| # | Mac | Windows 11 (Parallels, `prlctl exec` as SYSTEM) | Notes |
|---|---|---|---|
| 3 | pass | pass | `git init` folder -> `no-commits` + repair incl. `remote add origin`. Found + fixed: it used to read as DIRTY first ("inspect and reset it"); health check now runs before that. |
| 4 | pass (no-origin) | pass (no-origin) | no-upstream covered by unit test (real temp repos) on both. |
| 5 | pass | not run | 2026-10-21, real run: clone pulled 2.1.5 -> 2.1.8, consent refused (rc 2), "clone already updated, no files copied" notice printed, 0 files copied to the course root. The notice's finish command (`--apply --approve`) refuses from a non-terminal and does not re-pull (as designed; #343/#413). |
| 7 | skip | pass | Reproduced "dubious ownership" for real; it was being misreported as `no-commits`. Added `unsafe-owner` status + `safe.directory` fix. |
| 10 | pass | not run | 2026-10-21: nested clone at v2.0.22 on `main` -> `migrate_nested_to_flat --apply` (295 copied, all verification checks green) -> `--finalize`; course-owned files (.env, course/) intact; migrated clone health = ok and tracks main; next `--pull` works. **Finding:** migration records no capability approvals, so the first `cb_flatten` update after it stops at NEEDS APPROVAL for every package (needs a real terminal). Design question, not changed here. A detached-HEAD fixture (tag checkout) also confirmed `no-upstream` on a real clone. |

**Not run — need a real IDE session (you):** 1, 2, 6, 8, 9. Rows 5 and 10 also still need a Windows VM run. The VM has no snapshots, so the
clean no-Git snapshot for row 2 still has to be created.

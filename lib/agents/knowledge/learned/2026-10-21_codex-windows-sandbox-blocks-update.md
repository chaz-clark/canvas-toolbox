---
name: codex-windows-sandbox-blocks-update
description: On Windows, Codex runs commands as a hidden sandbox account that cannot write .git, so the toolkit update fails with a permission error. Re-run outside the sandbox.
version: "1.0"
author: chaz-clark
license: MIT
metadata:
  topic: windows-codex-update
  precipitating-event: 2026-10-21 faculty colleague on Windows, update via Codex
  affects: Codex users on Windows running cb_update / cb_flatten --pull
---

# Codex on Windows: update fails with a permission error

**Symptom.** "Update could not complete": git missing, then (after installing git)
"cannot write `.git\FETCH_HEAD`", with the repo owned by the faculty's own account and
the runner shown as `<MACHINE>\CodexSandboxOffline`.

**Cause.** Codex runs commands as a hidden local sandbox account. It can read the repo
but not write inside `.git`, so `git pull` fails. Git and the remote are fine. The
faculty member never signs in as that account.

**Fix.** Re-run the same update outside the sandbox: have the user tell Codex to run
`uv run python lib/tools/cb_update.py --pull --apply` with full access and approve the
prompt. No terminal, no second account. `cb_flatten.py --pull` now prints this guidance
itself on a permission failure.

**Don't.** Don't grant the sandbox account write access to the course folder as a first
move — it holds `.env` (the Canvas token). Don't ask faculty to open a terminal.

**If git is missing entirely.** Tell the agent to install Git for Windows
(`winget install --id Git.Git -e`), then retry.

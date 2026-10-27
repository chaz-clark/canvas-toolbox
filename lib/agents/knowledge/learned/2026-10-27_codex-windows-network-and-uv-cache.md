---
name: codex-windows-network-and-uv-cache
description: On Windows, Codex's default :workspace profile has no network and blocks uv's cache (os error 5). Use a network-enabled custom profile plus a dedicated UV_CACHE_DIR.
version: "1.0"
author: chaz-clark
license: MIT
metadata:
  topic: windows-codex-network
  precipitating-event: 2026-10-27 faculty colleague on Windows, token check unreachable (#429)
  affects: Codex users on Windows running any toolkit command that needs Canvas
---

# Codex on Windows: no network, then `uv` "Access is denied (os error 5)"

**Symptom 1.** `cb_update.py` reports the Canvas token check as unreachable; even
unrelated HTTPS requests fail. Runner is `<MACHINE>\CodexSandboxOffline` and
`CODEX_SANDBOX_NETWORK_DISABLED=1` is set. Cause: Codex's built-in `:workspace`
permission profile disables outbound network by design. It is not a university
firewall and not CrowdStrike.

**Symptom 2 (after enabling network).** `uv` dies before Python starts:
`Failed to query Python interpreter` / `Access is denied. (os error 5)`. Cause: under
the Windows MXC sandbox, uv tries to persist interpreter metadata under the sandbox
TEMP directory, which is not writable.

**Fix** (Codex `config.toml`; replace `<username>`), then fully restart VS Code:

```toml
default_permissions = "workspace-online"

[windows]
sandbox = "mxc"

[permissions.workspace-online]
extends = ":workspace"

[permissions.workspace-online.network]
enabled = true

[permissions.workspace-online.filesystem]
"C:/Users/<username>/.codex/cache/uv" = "write"

[shell_environment_policy.set]
UV_CACHE_DIR = 'C:\Users\<username>\.codex\cache\uv'
```

Verified by a genuinely new agent: normal user identity, flag absent, HTTP 200,
`token check: valid`, no elevation.

**Don't.** Don't grant the sandbox write access to the course folder (it holds `.env`).
Grant only the uv cache directory.

**Bug reporting.** `cb_report_bug.py` redacts Windows home paths as of 2.1.11 (before
that it leaked the username and course folder in the bundled cwd). If `uv run` can't
start at all, run the reporter with a Python that has `requests` installed.

Source: faculty report, issue #429 (Travis Ferrell, with Codex's help).

---
name: secret-in-agent-context-rotate-immediately
description: If a secret (PAT, API key, password) appears in agent conversation context — via system-reminder, tool output, file content read, or any other channel — rotate it the same session. The terminal-only paste flow is the preferred ongoing pattern.
version: "1.0"
author: chaz-clark
license: MIT
metadata:
  topic: secrets-handling
  precipitating-event: 2026-06-15 bug-intake worker setup
  affects: any agent-assisted session that handles secrets
---

# Secret in agent context → rotate immediately

## What happened

During the bug-intake worker setup on 2026-06-15, a fine-grained GitHub
PAT (`github_pat_…`) was pasted into `.env.local` at the repo root. The
agent (Claude) had the file open in its working set; when the user
saved the file, a `system-reminder` surfaced the new contents to the
agent context — including the literal PAT value.

The PAT was already narrowly scoped (canvas-toolbox / Issues:RW only /
90-day expiration), so blast radius was limited. But the principle
applies regardless of scope: **once a secret has been visible in agent
context, treat it as exposed.**

Same-day rotation was performed via `wrangler secret put GITHUB_PAT`
(terminal-only — the new value never touched disk).

## The general pattern

Any of these paths puts a secret in agent context:

1. **Reading a file that contains the secret** (`Read` tool, `cat` via
   Bash, `grep` that surfaces it).
2. **A `system-reminder` showing the file was modified** with the
   secret as the new content — even if the agent didn't request the
   read. The reminder reproduces the changed lines.
3. **An error message** containing the secret (e.g., a curl command
   that printed the Authorization header).
4. **Tool output** that includes the secret (e.g., `env | grep PAT`).
5. **A user message** that pastes the secret to "show me what I'm
   working with."

All five expose the secret to the model's context for the rest of the
session at minimum, and potentially to anywhere the conversation
transcript is logged.

## What to apply (operator + agent)

### Default rules for handling secrets

- **Don't read secret files.** If a file is named `.env*`, `*.pem`,
  `*_token*`, `*_secret*`, `*credentials*` — don't `Read` it unless
  the operator explicitly asks.
- **Don't echo secrets in Bash.** Even with `echo $SECRET` — that
  pipes through tool output → agent context. Prefer file-redirect or
  interactive prompts.
- **Prefer the terminal-only paste flow for one-shot secret handoffs.**
  `wrangler secret put NAME` (interactive prompt; secret goes from
  clipboard → wrangler stdin → Cloudflare; never touches disk).
  Avoid `.env.local` + redirect when a terminal-only path exists.

### When a secret HAS appeared in agent context

Rotate it immediately, same session:

1. Generate a new value (regenerate the PAT, rotate the API key, etc.).
2. Push the new value to wherever it's used (Cloudflare secret store,
   .env on a server, deployment config).
3. Verify the new value works (smoke test).
4. Revoke the old value if the rotation flow didn't auto-revoke it.

Don't wait until the next scheduled rotation. The exposure happened;
the rotation closes the window.

### The terminal-only paste flow (canonical)

For Cloudflare Worker secrets specifically:

```bash
cd path/to/worker
wrangler secret put SECRET_NAME
# wrangler prompts: "Enter a secret value:"
# paste; press Enter
# wrangler reports success; PAT never written to disk
```

The PAT goes clipboard → wrangler's stdin → Cloudflare's encrypted
secret store. It doesn't pass through any file the agent could read.

If you absolutely must use a tempfile (scripted rotation, CI):

```bash
# Write to /tmp (outside repo, no backup tools, no agent-visible)
echo "$NEW_PAT" > /tmp/pat.txt
wrangler secret put SECRET_NAME < /tmp/pat.txt
rm /tmp/pat.txt
```

`/tmp` is preferred over `.env*` in the repo because:
- macOS clears `/tmp` periodically
- No backup tool (Time Machine, Dropbox, iCloud) covers `/tmp`
- No other agent or editor sync touches `/tmp`
- `git add` literally cannot reach `/tmp`

## Cross-references

- [`infra/bug-intake-worker/MAINTENANCE.local.md`](../../../../infra/bug-intake-worker/MAINTENANCE.local.md)
  — operator runbook with the terminal-only flow as canonical;
  `.env.local` path documented as fallback only.
- [`SECURITY.md`](../../../../SECURITY.md) — vulnerability reporting
  policy. A leaked PAT *is* a security issue (even when narrowly
  scoped); follow that policy if the exposure was on a public
  surface, not just same-session context.

## When this lesson promotes

Promote to first-class knowledge file if a SECOND session captures a
similar exposure (Hermes promotion rule). At that point the pattern is
recurring enough to warrant a permanent home. Until then it lives here
as the learned-once-already record.

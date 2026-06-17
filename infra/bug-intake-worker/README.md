# canvas-toolbox bug-intake worker

The Cloudflare Worker that backs `lib/tools/cb_report_bug.py`. Faculty
run the Python CLI; the CLI POSTs to this worker; the worker files a
GitHub issue against `chaz-clark/canvas-toolbox` using the maintainer's
PAT. Faculty never holds a PAT, never sees a browser auth flow, never
needs a GitHub account.

This is one-way (faculty → worker → GitHub). Nothing reads back; the
worker doesn't keep state beyond an optional per-IP rate-limit counter.

---

## One-time setup (maintainer, ~20 min)

You only do this once. Steps 1–3 are the Cloudflare side; 4–6 are the
GitHub PAT + wrangler glue; 7–8 are the smoke test.

### 1. Create a Cloudflare account (skip if you already have one)

- https://dash.cloudflare.com/sign-up — free tier is enough.
- No credit card required for `workers.dev` deployments.
- Verify the email confirmation; pick any account name.

### 2. Install / use `wrangler`

You have two options:

```bash
# (a) global install — recommended if you'll deploy more than once
npm install -g wrangler

# (b) npx — no install, slightly slower per-command
#     just prefix every wrangler command below with `npx`
```

Both call the same Cloudflare CLI.

### 3. Authenticate wrangler with your Cloudflare account

```bash
cd infra/bug-intake-worker
wrangler login
```

A browser tab opens; sign in to Cloudflare; click **Allow**. Wrangler
stores an OAuth token under `~/.config/.wrangler/`. One-time only.

### 4. Create a fine-grained GitHub PAT

In a browser: https://github.com/settings/tokens?type=beta → **Generate
new token** (fine-grained).

- **Name:** `canvas-toolbox bug-intake worker (Cloudflare)`
- **Expiration:** 90 days. Rotate quarterly (see "PAT rotation" below).
- **Resource owner:** your own account (`chaz-clark`).
- **Repository access:** **Only select repositories** → `canvas-toolbox`.
- **Permissions** (repository):
  - **Issues** → **Read and write**.
  - Everything else stays at "No access".
- Click **Generate token** → **copy the token string** (starts with
  `github_pat_...`). You can't see it again after closing the page.

### 5. Set the PAT as a Worker secret

```bash
wrangler secret put GITHUB_PAT
```

Wrangler prompts; paste the PAT; press enter. The PAT is now stored
encrypted in Cloudflare and accessible only as `env.GITHUB_PAT` inside
the Worker. It is NEVER written to `wrangler.toml`, NEVER committed to
git, NEVER returned by any HTTP response.

### 6. (Recommended for v1.0) Enable per-IP rate limiting

The Worker ships with rate-limiting code (5 issues per IP per hour) that
activates automatically when a `RATE_LIMIT_KV` binding is present.
Without the binding, the rate-limit code returns "ok" for every request
(useful for dev, but ship with it on).

```bash
wrangler kv:namespace create RATE_LIMIT_KV
```

Wrangler prints something like:

```
🌀 Creating namespace with title "canvas-toolbox-bugs-RATE_LIMIT_KV"
✨ Success!
Add the following to your configuration file in your kv_namespaces array:
[[kv_namespaces]]
binding = "RATE_LIMIT_KV"
id = "abc123def456..."
```

Uncomment the `[[kv_namespaces]]` block at the bottom of
`wrangler.toml` and paste the `id`. Then deploy.

### 7. Deploy

```bash
wrangler deploy
```

On success you'll see:

```
Uploaded canvas-toolbox-bugs (X.XX sec)
Published canvas-toolbox-bugs (X.XX sec)
  https://canvas-toolbox-bugs.<your-account>.workers.dev
```

Copy that URL. That's the endpoint.

### 8. Wire the URL into the CLI

Open `lib/tools/cb_report_bug.py` and update the `_ENDPOINT` constant
at the top:

```python
_ENDPOINT = "https://canvas-toolbox-bugs.<your-account>.workers.dev/bug"
```

Commit the change.

### 9. Smoke test

```bash
# Dry-run first — shows what would be sent, doesn't post:
uv run python lib/tools/cb_report_bug.py --dry-run \
    --title "test — please close" --body "smoke test from cb_report_bug.py"

# Real submission:
uv run python lib/tools/cb_report_bug.py \
    --title "test — please close" --body "smoke test from cb_report_bug.py"
```

Expected: prints the new GitHub issue URL. Open it; verify it landed
with the `agent-submitted` label. Close it.

---

## Faculty side (post-deploy, zero setup)

```bash
uv run python canvas-toolbox/lib/tools/cb_report_bug.py
```

That's the whole faculty-facing contract. The CLI bundles local context
(toolkit version, last command, stack trace if provided), opens
`$EDITOR` for the operator to add a description, scrubs the body
client-side, POSTs to the worker, prints the resulting issue URL. No
auth, no `gh`, no browser, no GitHub account.

---

## Operations

### Maintainer notifications (issue #84 — decision logged 2026-06-17)

**Channel: GitHub Mobile push notifications. Zero workflow code.**

Every issue filed through this worker is opened against
`chaz-clark/canvas-toolbox` by the maintainer's PAT. GitHub natively
pushes a notification to the GitHub Mobile app (and the GitHub web
UI / desktop email digest, depending on your watch settings) the
moment the issue lands. No SMTP, no Slack/Discord webhook, no
secrets to rotate.

**Tradeoffs accepted (per #84 design conversation):**
- No `[URGENT]` subject-line escalation for FERPA / security keywords
  — every agent-submitted issue gets the same standard notification.
  Mitigation: the worker's body footer includes `_Filed via
  canvas-toolbox bug-intake worker._` so the source is unmissable in
  the issue title preview, and FERPA-class language in the body
  (`PII leak`, `name leak`, `scrub bypass`, `PAT exposure`) is
  visible in the GitHub Mobile preview.
- No phone-app channel separate from GitHub itself — relies on
  having GitHub Mobile installed + the repo on your watch list.

**Setup required:**
- Install GitHub Mobile on your phone (one-time)
- Confirm `chaz-clark/canvas-toolbox` is on your watched repos list
  (default for repos you own — verify at
  https://github.com/notifications/subscriptions)
- That's it.

**Liveness check (manual):** if `agent-submitted` issues stop
arriving for >2 weeks while consumer repos are actively grading,
something's wrong — `wrangler tail` (below) confirms whether the
worker is receiving requests.

If the zero-code path stops being enough (e.g. you adopt the toolkit
beyond personal use and need an escalation tier or a Slack/Discord
team channel), reopen #84 — the design conversation captured the
viable alternatives.

### Tail the worker logs

```bash
wrangler tail
```

Watches the running Worker; shows every request + response + console.log
in real time. Useful when triaging "did my bug report land?".

### Backup account access (recommended, ~5 min — closes a real DR gap)

The worker lives in ONE Cloudflare account. If that account is locked,
compromised, or deprecated, the worker is orphaned — no way to rotate
the PAT, redeploy, or take it offline from outside.

**Mitigation:** invite a second member with `Super Administrator` role
on a **different recovery path** from the primary (different SSO /
different 2FA recovery device / institutional vs personal email).

Cloudflare dashboard → top-right account dropdown → **Members** →
**Invite** → backup email → role **Super Administrator** → send.
The backup confirms via emailed link + sets a Cloudflare password.

Smoke-test the backup from a different machine or incognito window:

```bash
wrangler logout
wrangler login    # OAuth as the backup
wrangler whoami   # confirms the backup has access
```

The backup can do everything the primary can — `wrangler secret put`,
`wrangler deploy`, `wrangler delete`. Document the backup email in
your local `MAINTENANCE.local.md` (gitignored).

### PAT rotation (~5 min, every 90 days)

GitHub fine-grained PATs expire on the schedule you set (recommended:
90 days). To rotate:

1. https://github.com/settings/tokens → regenerate the PAT (same name +
   scope as the original).
2. `cd infra/bug-intake-worker && wrangler secret put GITHUB_PAT`,
   paste the new token.
3. Smoke test (step 9 above).

The old token can be deleted from GitHub once the new one is in place.

### Cost reality

- Cloudflare account: **$0**
- Worker free tier (100K req/day, actual usage ~10/month): **$0**
- KV free tier (100K reads + 1K writes/day, far above our usage): **$0**
- `workers.dev` subdomain: **$0**
- GitHub PAT: **$0**
- Custom domain: NOT REQUIRED (the `workers.dev` URL is HTTPS-by-default
  and a real domain).

**Total ongoing cost: $0.** Ongoing maintenance: ~5 min/quarter for PAT
rotation.

### If you ever want to take it offline

```bash
wrangler delete --name canvas-toolbox-bugs
```

The CLI tool will then fail with a connection error, which is a
clean failure mode — the existing `gh issue create` path always
remains as the developer-facing fallback.

---

## Security model

This is a one-way intake channel. Threat-model-wise:

| Threat | Mitigation |
|---|---|
| Embedded PAT extraction | PAT lives in Worker secret store; never sent client-side. |
| Drive-by abuse / spam issues | Required UA prefix (script-kiddie filter) + per-IP rate limit (5/hr). |
| Body-bomb DoS | 64 KB hard cap on POST body; 50 KB on the rendered issue body. |
| PII leak via stack trace | Client-side scrub (`cb_report_bug.py` runs the existing `expand_name_terms` / `name_aware_subn` helpers) + server-side scrub (email + userpath regexes) as defense in depth. |
| Issue-tracker pollution | `agent-submitted` label means filed issues are filterable; manual triage burden is on the maintainer. |
| Compromised Worker | PAT scope is narrow (`canvas-toolbox` only + Issues:RW only + 90 day expiration). Worst case: someone uses it to file spam issues for ~90 days until the PAT expires; no read access to anything; no ability to push code. |

The maintainer accepts the operational burden (one PAT rotation per
quarter; manual triage of `agent-submitted` issues) in exchange for
**zero faculty-side auth**.

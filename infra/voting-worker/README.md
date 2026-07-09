# canvas-toolbox voting worker

The Cloudflare Worker that backs `lib/tools/vote_feature.py`. Faculty run
the Python CLI; the CLI POSTs to this worker; the worker stores votes in a
D1 database and returns the current vote count. This enables community-driven
prioritization of roadmap features without requiring GitHub accounts.

This is a read-write system (faculty → worker → D1 database, and faculty ←
worker ← D1 database for vote counts).

---

## One-time setup (maintainer, ~25 min)

You only do this once. Steps 1–3 are the Cloudflare side; 4–5 are the D1
database setup; 6–7 are deployment; 8 is the smoke test.

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
cd infra/voting-worker
wrangler login
```

A browser tab opens; sign in to Cloudflare; click **Allow**. Wrangler
stores an OAuth token under `~/.config/.wrangler/`. One-time only.

### 4. Create the D1 database

```bash
wrangler d1 create canvas-toolbox-votes
```

Wrangler prints something like:

```
✅ Successfully created DB 'canvas-toolbox-votes' in region WNAM
Created your database using D1's new storage backend.

[[d1_databases]]
binding = "VOTES_DB"
database_name = "canvas-toolbox-votes"
database_id = "abc123def456..."
```

Copy the `database_id` and update it in `wrangler.toml`:

```toml
[[d1_databases]]
binding = "VOTES_DB"
database_name = "canvas-toolbox-votes"
database_id = "abc123def456..."  # paste your ID here
```

### 5. Initialize the database schema

```bash
wrangler d1 execute canvas-toolbox-votes --file=./schema.sql
```

This creates the `votes` table and indexes. You should see:

```
🌀 Mapping SQL input into an array of statements
🌀 Executing on remote database canvas-toolbox-votes (abc123def456...):
🌀 To execute on your local DB, remove the --remote flag and execute this again.
🚣 Executed 3 commands in 0.123ms
```

### 6. (Optional) Enable per-IP rate limiting

The Worker ships with rate-limiting code (10 votes per IP per hour) that
activates automatically when a `RATE_LIMIT_KV` binding is present. Without
the binding, the rate-limit code returns "ok" for every request (useful for
dev, but ship with it on).

```bash
wrangler kv:namespace create RATE_LIMIT_KV
```

Wrangler prints something like:

```
🌀 Creating namespace with title "canvas-toolbox-vote-RATE_LIMIT_KV"
✨ Success!
Add the following to your configuration file in your kv_namespaces array:
[[kv_namespaces]]
binding = "RATE_LIMIT_KV"
id = "abc123def456..."
```

Uncomment the `[[kv_namespaces]]` block at the bottom of `wrangler.toml`
and paste the `id`.

### 7. Deploy

```bash
wrangler deploy
```

On success you'll see:

```
Uploaded canvas-toolbox-vote (X.XX sec)
Published canvas-toolbox-vote (X.XX sec)
  https://canvas-toolbox-vote.<your-account>.workers.dev
```

Copy that URL. That's the endpoint.

### 8. Wire the URL into the CLI

Open `lib/tools/vote_feature.py` and update the `_ENDPOINT` constant
at the top:

```python
_ENDPOINT = "https://canvas-toolbox-vote.<your-account>.workers.dev/vote"
```

Commit the change.

### 9. Smoke test

```bash
# Dry-run first — shows what would be sent, doesn't post:
uv run python lib/tools/vote_feature.py --feature "grade forecast" --dry-run

# Real vote:
uv run python lib/tools/vote_feature.py --feature "grade forecast"

# Check vote counts:
uv run python lib/tools/vote_feature.py --list
```

Expected: prints "Vote recorded" with current vote count. Running the same
command again should return "You already voted for this feature" (idempotent).

---

## Faculty side (post-deploy, zero setup)

```bash
# List all roadmap features and their vote counts
uv run python lib/tools/vote_feature.py --list

# Vote for a feature
uv run python lib/tools/vote_feature.py --feature "student grade forecast"

# Vote using feature ID
uv run python lib/tools/vote_feature.py --feature-id grade-forecast
```

That's the whole faculty-facing contract. The CLI generates an anonymous
user hash (based on machine ID + username), posts to the worker, and prints
the updated vote count. No auth, no GitHub account, no browser.

---

## Operations

### Query the database directly

```bash
# View all votes
wrangler d1 execute canvas-toolbox-votes --command="SELECT * FROM votes ORDER BY voted_at DESC LIMIT 20"

# Vote counts by feature
wrangler d1 execute canvas-toolbox-votes --command="SELECT feature_id, COUNT(*) as count FROM votes GROUP BY feature_id ORDER BY count DESC"

# Total votes
wrangler d1 execute canvas-toolbox-votes --command="SELECT COUNT(*) as total_votes FROM votes"
```

### Tail the worker logs

```bash
wrangler tail
```

Watches the running Worker; shows every request + response + console.log
in real time. Useful when triaging "did my vote land?".

### Update the roadmap with vote counts

Create a script (future work) that queries GET /votes and updates
ROADMAP.md with current vote counts. This could be run manually or via
GitHub Actions on a schedule.

Example script outline:
```python
# lib/tools/update_roadmap_votes.py
# 1. Fetch vote counts from GET https://canvas-toolbox-vote.workers.dev/votes
# 2. Parse ROADMAP.md
# 3. Update feature lines with vote counts (e.g., "⭐ 42 votes")
# 4. Write updated ROADMAP.md
```

### Backup account access (recommended)

Same process as bug-intake-worker (see ../bug-intake-worker/README.md
"Backup account access" section). Invite a second member with Super
Administrator role on a different recovery path.

### Cost reality

- Cloudflare account: **$0**
- Worker free tier (100K req/day, actual usage ~50/month): **$0**
- D1 database free tier (5 GB storage, 5M row reads/day, 100K row writes/day):
  **$0** (we'll use ~0.1% of free tier limits)
- KV free tier (100K reads + 1K writes/day): **$0**
- `workers.dev` subdomain: **$0**

**Total ongoing cost: $0.** Ongoing maintenance: ~5 min to update ROADMAP.md
with vote counts (could be automated).

### If you ever want to take it offline

```bash
wrangler delete --name canvas-toolbox-vote
wrangler d1 delete canvas-toolbox-votes
```

The CLI tool will then fail with a connection error. Faculty can still
manually comment on GitHub issues or file enhancement requests via the
bug-intake worker.

---

## Security model

This is a read-write voting system. Threat-model-wise:

| Threat | Mitigation |
|---|---|
| Vote spam / ballot stuffing | Deduplication by (user_hash, feature_id) — one vote per user per feature. |
| Drive-by abuse | Required UA prefix (script-kiddie filter) + per-IP rate limit (10 votes/hr total). |
| Body-bomb DoS | 16 KB hard cap on POST body. |
| Database pollution | Feature IDs validated server-side against VALID_FEATURES set (synced with ROADMAP.md). |
| PII leak | No student data collected. user_hash is anonymized (SHA256 of machine_id + username). |
| Compromised Worker | Worst case: someone uses it to spam votes for ~1 hour (rate limit) until you notice via `wrangler tail` and redeploy. No secrets to leak (no PAT, no API keys). Database can be reset via `wrangler d1 execute --command="DELETE FROM votes"`. |

The maintainer accepts the operational burden (manual ROADMAP.md updates;
occasional vote-count queries) in exchange for **zero faculty-side auth**.

---

## Future enhancements

1. **Web form voting**: Deploy a simple HTML form (as a Pages site) that
   POSTs to this same endpoint. Allows non-CLI users to vote.

2. **Agent voting behavior**: Add logic to AI agents to detect roadmap
   interest in conversation and offer to vote on user's behalf.

3. **Auto-update ROADMAP.md**: GitHub Actions workflow that runs
   `update_roadmap_votes.py` daily and commits vote count updates.

4. **Analytics integration**: Track when features move from roadmap to
   implementation, measure time-to-ship for voted features.

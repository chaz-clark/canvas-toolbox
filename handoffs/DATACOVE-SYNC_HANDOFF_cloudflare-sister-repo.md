---
direction: request
status: open
topic: cloudflare-sister-repo
author: byui-db/datacove-sync (Chaz + Claude)
from_repo: byui-db/datacove-sync
to_repo: chaz-clark/canvas-toolbox
date_created: 2026-07-12
last_updated: 2026-07-12
origin: byui-db/datacove-sync
origin_commit: 24e38aa
priority: medium
trigger: datacove-sync needs a heartbeat monitor; graduate canvas-toolbox's Cloudflare infra into its own sister repo
companions: []
---

# Handoff (request): Cloudflare sister repo + reusable heartbeat worker

**To**: canvas-toolbox (cb) — owner of the Cloudflare dev environment
**From**: byui-db/datacove-sync
**Purpose**: Graduate the Cloudflare infra out of canvas-toolbox into its own **sister repo**
(the way you split out `itm327-master-course`, and how `handoff/` is cloned per
`AGENTS.md:146`), and stand up a **reusable heartbeat/monitoring Worker** on your Cloudflare
account that datacove-sync (and your other jobs) can ping.

---

## Context

- **datacove-sync** is a new on-server ingestion pipeline (Yahoo → Mongo stocks, Finnhub →
  SFTP news) that runs on `datacove` via systemd user timers. Repo: `byui-db/datacove-sync`
  (private), origin commit `24e38aa`.
- It **already emits heartbeat pings**: `sync.py` pings `HEARTBEAT_URL` on success and
  `HEARTBEAT_URL/fail` on failure (healthchecks.io semantics — see `sync.py:_ping` and the
  README "Monitoring" section). It just needs an endpoint to point at.
- **canvas-toolbox is the Cloudflare dev home** (wrangler conventions, account/auth,
  `infra/bug-intake-worker`, `infra/voting-worker`). Rather than build the monitor *inside*
  canvas-toolbox, we want the CF infra to become its own sister repo.

## Requests (per-item approval; this is `request` direction, not auto-apply)

### 1. Create a dedicated Cloudflare **sister repo**
- New repo — suggested name `chaz-clark/cf-workers` or `chaz-clark/edge-infra` (your call).
- House Cloudflare Workers there. `infra/bug-intake-worker` + `infra/voting-worker` can migrate
  when convenient (not required to start).
- Wire it as a **sister repo** canvas-toolbox imports the way it clones the `handoff` tool
  (local clone, gitignored — see `AGENTS.md:146`). Document the import in canvas-toolbox
  `AGENTS.md`.

### 2. Build a reusable `heartbeat-worker` in that repo
Follow your `bug-intake-worker` conventions (`wrangler.toml` `[vars]`, secrets via
`wrangler secret put`, KV or D1 for state, `[observability]` on, README in your
deployment-checklist style):

- **`GET /ping/<job>`** → record `last_seen[job] = now` (KV or D1).
- **`GET /ping/<job>/fail`** → record a failure and alert immediately.
- **Cron trigger** (e.g. `crons = ["*/15 * * * *"]`) → any job whose `last_seen` is older than
  its configured max-interval → alert.
- **Alert = file a GitHub issue**, reusing your `bug-intake-worker` → GitHub Issues pattern
  (PAT secret), labeled `pipeline-down`. This catches **"job never ran / server down"**, which
  server email can't.
- **Config**: per-job `{name, max_interval}` in `[vars]` or a D1 table, so it's reusable for the
  few jobs you run — not datacove-only.

### 3. Deliver the ping URL back
Reply with a **`deliver`-direction handoff** into `datacove-sync/handoffs/<date>_cloudflare-sister-repo.md`
containing the deployed worker URL, so we set
`HEARTBEAT_URL=https://<worker>.workers.dev/ping/datacove-sync` in datacove-sync's `.env`.

## Acceptance

- `curl https://<worker>.workers.dev/ping/datacove-sync` → `200`, updates `last_seen`.
- No ping past the interval → a `pipeline-down` GitHub issue is filed.
- datacove-sync's `sync.py` pings green on success and `/fail` on failure (already implemented —
  no datacove-sync change needed beyond setting `HEARTBEAT_URL`).

## References

- **datacove-sync**: `byui-db/datacove-sync` @ `24e38aa` — see `sync.py` (`_ping`, HEARTBEAT_URL),
  README "Monitoring", and `tools/checkup.py` (the complementary pull-based weekly checkup).
- **Pattern to reuse**: `canvas-toolbox/infra/bug-intake-worker` (Worker → GitHub issue).
- **Heartbeat model**: healthchecks.io semantics (success ping + `/fail`).

## Lifecycle marker

- 2026-07-12 — authored (`Status: open`). Set `Status: applied` when the worker deploys, and
  send the `deliver` handoff back to datacove-sync with the URL.

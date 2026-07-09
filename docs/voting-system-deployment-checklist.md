# Voting System Deployment Checklist

**Date Created:** 2026-07-08
**Status:** Code-complete, not yet deployed
**Purpose:** Step-by-step guide to deploy the canvas-toolbox voting system

---

## What Was Built (All 4 Components)

### ✅ 1. CLI Voting Tool
**File:** `lib/tools/vote_feature.py` (350+ lines)

**Features:**
- Vote for roadmap features by name or ID
- List all features with current vote counts
- Dry-run mode
- Anonymous voting via user hash (SHA256 of machine_id + username)
- Fuzzy matching for feature names
- Clear error messages when endpoint not configured

**Test commands:**
```bash
# List all roadmap features
uv run python lib/tools/vote_feature.py --list

# Vote for a feature (dry-run)
uv run python lib/tools/vote_feature.py --feature "grade forecast" --dry-run

# Actual vote (endpoint must be configured)
uv run python lib/tools/vote_feature.py --feature-id grade-forecast
```

### ✅ 2. Cloudflare Worker Infrastructure
**Directory:** `infra/voting-worker/`

**Files created:**
- `src/worker.ts` (250+ lines) - Main worker with POST /vote and GET /votes endpoints
- `schema.sql` - D1 database schema with deduplication
- `wrangler.toml` - Cloudflare Workers config
- `README.md` (280+ lines) - Full deployment guide
- `.gitignore` - Excludes .wrangler/ directory

**Features:**
- D1 database for vote storage
- Deduplication by (user_hash, feature_id) - one vote per user per feature
- Rate limiting (10 votes/hour per IP) via KV
- User-Agent validation
- CORS support for future web voting
- Idempotent voting (returns current count if already voted)

### ✅ 3. Vote Aggregation Script
**File:** `lib/tools/update_roadmap_votes.py` (200+ lines)

**Features:**
- Fetches vote counts from Cloudflare Worker
- Updates ROADMAP.md with vote badges
- Dry-run mode by default
- Can show vote counts without updating file
- Designed for manual or GitHub Actions automation

**Test commands:**
```bash
# Show current votes (endpoint must be configured)
uv run python lib/tools/update_roadmap_votes.py --show

# Update ROADMAP.md (dry-run)
uv run python lib/tools/update_roadmap_votes.py

# Apply changes
uv run python lib/tools/update_roadmap_votes.py --apply
```

### ✅ 4. Agent Voting Behavior
**File:** `AGENTS.md` (updated lines 308-348)

**Added:** "Roadmap voting — community prioritization" section

**Agent behavior:**
- Detects when operator mentions roadmap feature
- Offers to vote on their behalf
- Lists all feature IDs for reference
- Integrates with continuous improvement workflow

**Example conversation:**
```
User: "I often get asked by students what they need to pass the class"

Agent: "That feature is on the roadmap: 'Student grade forecast' (Phase 1, HIGH DEMAND).
Would you like me to vote for this feature to signal demand?
I can run: uv run python lib/tools/vote_feature.py --feature-id grade-forecast"
```

---

## Documentation Updates

### ✅ ROADMAP.md (lines 338-381)
Added "Voting & Prioritization" section explaining:
- How to vote (CLI commands)
- Anonymous voting mechanics
- Voting through AI agents
- How voting affects prioritization
- Infrastructure components

### ✅ README.md (lines 566-589)
Updated "Sharing back with the project" section:
- Added voting row to table (4th action)
- Added "Vote directly on roadmap features" subsection
- Clear examples of voting commands

---

## Architecture

```
Faculty CLI (vote_feature.py)
    ↓ POST /vote {feature_id, user_hash, source}
Cloudflare Worker (voting-worker/src/worker.ts)
    ↓ INSERT INTO votes
D1 Database (votes table)
    ↑ SELECT COUNT(*) GROUP BY feature_id
Cloudflare Worker
    ↑ GET /votes
Aggregation Script (update_roadmap_votes.py)
    ↓ writes vote counts
ROADMAP.md (updated with "(42 votes)" badges)
```

---

## Deployment Steps (Maintainer Only)

### Prerequisites
- [ ] Cloudflare account (already have from bug-intake-worker)
- [ ] `wrangler` installed (`npm install -g wrangler`)
- [ ] Authenticated to Cloudflare (`wrangler login`)

### Step 1: Create D1 Database
```bash
cd infra/voting-worker
wrangler d1 create canvas-toolbox-votes
```

**Expected output:**
```
✅ Successfully created DB 'canvas-toolbox-votes' in region WNAM

[[d1_databases]]
binding = "VOTES_DB"
database_name = "canvas-toolbox-votes"
database_id = "abc123def456..."
```

- [ ] Copy the `database_id` from output
- [ ] Update `wrangler.toml` line 15: `database_id = "abc123def456..."`

### Step 2: Initialize Database Schema
```bash
wrangler d1 execute canvas-toolbox-votes --file=./schema.sql
```

**Expected output:**
```
🌀 Executing on remote database canvas-toolbox-votes:
🚣 Executed 3 commands in 0.123ms
```

**Verify schema:**
```bash
wrangler d1 execute canvas-toolbox-votes --command="SELECT name FROM sqlite_master WHERE type='table'"
```

Should show: `votes` table

### Step 3: Create KV Namespace (Rate Limiting - Optional but Recommended)
```bash
wrangler kv:namespace create RATE_LIMIT_KV
```

**Expected output:**
```
🌀 Creating namespace with title "canvas-toolbox-vote-RATE_LIMIT_KV"
✨ Success!
[[kv_namespaces]]
binding = "RATE_LIMIT_KV"
id = "abc123def456..."
```

- [ ] Uncomment lines 24-26 in `wrangler.toml`
- [ ] Paste the KV namespace `id` into `wrangler.toml`

**Note:** Without this, rate limiting is disabled (ok for initial testing, but ship with it enabled)

### Step 4: Deploy Worker
```bash
wrangler deploy
```

**Expected output:**
```
Uploaded canvas-toolbox-vote (X.XX sec)
Published canvas-toolbox-vote (X.XX sec)
  https://canvas-toolbox-vote.<your-account>.workers.dev
```

- [ ] Copy the worker URL from output
- [ ] Test endpoint: `curl https://canvas-toolbox-vote.<your-account>.workers.dev/`
  - Should return: "canvas-toolbox voting worker — POST /vote with JSON, GET /votes for counts."

### Step 5: Wire Endpoint into CLI Tools
**File 1:** `lib/tools/vote_feature.py` (line 126)
```python
# Before:
_ENDPOINT: str | None = None

# After:
_ENDPOINT: str | None = "https://canvas-toolbox-vote.<your-account>.workers.dev/vote"
```

**File 2:** `lib/tools/update_roadmap_votes.py` (line 58)
```python
# Before:
_ENDPOINT: str | None = None

# After:
_ENDPOINT: str | None = "https://canvas-toolbox-vote.<your-account>.workers.dev/votes"
```

- [ ] Update both files with your worker URL
- [ ] Commit the changes

### Step 6: Smoke Test
```bash
# Test 1: Vote for a feature
uv run python lib/tools/vote_feature.py --feature-id grade-forecast

# Expected output:
# Voting for: Student grade forecast
# ✓ Vote recorded (X.Xs)
#   Current votes for 'Student grade forecast': 1

# Test 2: Vote again (should be idempotent)
uv run python lib/tools/vote_feature.py --feature-id grade-forecast

# Expected output:
# ✓ Vote recorded (X.Xs)
#   Current votes for 'Student grade forecast': 1
# (or "You already voted for this feature" depending on implementation)

# Test 3: Check all vote counts
uv run python lib/tools/vote_feature.py --list

# Should show grade-forecast with 1 vote

# Test 4: Fetch votes via aggregation script
uv run python lib/tools/update_roadmap_votes.py --show

# Should show grade-forecast: 1 vote
```

- [ ] All smoke tests pass
- [ ] Vote count is correct (1 vote after first vote, same count after second)

### Step 7: Update ROADMAP.md with First Vote Counts
```bash
uv run python lib/tools/update_roadmap_votes.py --apply
git diff docs/ROADMAP.md  # verify changes look correct
git add docs/ROADMAP.md lib/tools/vote_feature.py lib/tools/update_roadmap_votes.py
git commit -m "deploy: wire voting worker endpoint into CLI tools"
git push
```

### Step 8: Monitor Worker Logs (Optional)
```bash
wrangler tail
```

Watch live requests to the worker. Useful for debugging.

---

## Testing Checklist

### CLI Tool Tests
- [ ] `--list` shows all roadmap features
- [ ] `--feature "grade forecast"` resolves to grade-forecast ID
- [ ] `--feature-id grade-forecast` posts vote successfully
- [ ] `--dry-run` shows what would be sent without posting
- [ ] Voting twice for same feature is idempotent
- [ ] Invalid feature ID returns clear error
- [ ] Missing endpoint shows helpful error message

### Worker Tests
- [ ] GET / returns info page
- [ ] GET /votes returns vote counts JSON
- [ ] POST /vote records vote in D1
- [ ] POST /vote returns updated count
- [ ] Deduplication works (same user_hash + feature_id)
- [ ] Rate limiting works (11th vote in 1 hour blocked)
- [ ] Invalid feature_id rejected with 400
- [ ] Missing User-Agent rejected with 400

### Aggregation Script Tests
- [ ] `--show` displays current vote counts
- [ ] Dry-run mode shows what would be updated
- [ ] `--apply` updates ROADMAP.md correctly
- [ ] Vote count format: "Feature Name (42 votes)"
- [ ] Updates existing counts (doesn't duplicate)

### Agent Behavior Tests
- [ ] Agent offers voting when user mentions "what do I need to pass"
- [ ] Agent uses `--feature-id` (not `--feature`)
- [ ] Agent doesn't offer voting for non-roadmap features
- [ ] Agent shows updated vote count after voting

---

## Post-Deployment

### Regular Maintenance
1. **Update ROADMAP.md with vote counts** (manual or automated)
   - Run weekly or after significant vote activity
   - `uv run python lib/tools/update_roadmap_votes.py --apply`
   - Commit and push changes

2. **Monitor vote activity** (optional)
   ```bash
   wrangler d1 execute canvas-toolbox-votes --command="
     SELECT feature_id, COUNT(*) as votes
     FROM votes
     GROUP BY feature_id
     ORDER BY votes DESC
   "
   ```

3. **Check for spam** (if abuse detected)
   ```bash
   # View recent votes
   wrangler d1 execute canvas-toolbox-votes --command="
     SELECT * FROM votes
     ORDER BY voted_at DESC
     LIMIT 20
   "
   ```

### Future Enhancements (Not Required for v1)
- [ ] GitHub Actions workflow to auto-update ROADMAP.md daily
- [ ] Web form voting (Cloudflare Pages)
- [ ] Analytics integration (track feature implementation vs votes)
- [ ] Email notification when feature gets N votes

---

## Troubleshooting

### "Voting endpoint not yet deployed"
- Check `_ENDPOINT` is set in `vote_feature.py` and `update_roadmap_votes.py`
- Verify worker is deployed: `wrangler whoami` and check dashboard

### "Rate limit: max 10 votes per IP per hour"
- Expected behavior if testing from same machine
- Wait 1 hour or deploy without KV binding for testing

### "Invalid feature_id"
- Check feature ID matches VALID_FEATURES set in `worker.ts`
- Update worker if ROADMAP.md feature list changed

### Worker returns 500 error
- Check D1 database is bound correctly in `wrangler.toml`
- View logs: `wrangler tail`
- Verify schema was initialized: `wrangler d1 execute canvas-toolbox-votes --command="SELECT * FROM votes LIMIT 1"`

---

## Files Modified Summary

### New Files (8)
1. `lib/tools/vote_feature.py` - CLI voting tool
2. `lib/tools/update_roadmap_votes.py` - Aggregation script
3. `infra/voting-worker/src/worker.ts` - Cloudflare Worker
4. `infra/voting-worker/schema.sql` - D1 database schema
5. `infra/voting-worker/wrangler.toml` - Worker config
6. `infra/voting-worker/README.md` - Deployment guide
7. `infra/voting-worker/.gitignore` - Wrangler state exclusion
8. `docs/voting-system-deployment-checklist.md` - This file

### Modified Files (3)
1. `AGENTS.md` - Added roadmap voting section (lines 308-348)
2. `docs/ROADMAP.md` - Added "Voting & Prioritization" section (lines 338-381)
3. `README.md` - Updated "Sharing back" section with voting (lines 566-589)

---

## Cost Reality

- Cloudflare Worker: **$0** (free tier: 100K req/day)
- D1 Database: **$0** (free tier: 5GB storage, 5M reads/day, 100K writes/day)
- KV Namespace: **$0** (free tier: 100K reads/day, 1K writes/day)
- Total ongoing cost: **$0**

Expected usage:
- ~50 votes/month (well under free tier limits)
- Database size: ~5KB for 100 votes (negligible)

---

## Next Steps After Deployment

1. Announce voting system to current users
2. Monitor vote activity for 1-2 weeks
3. Update ROADMAP.md with first real vote counts
4. Consider GitHub Actions automation if votes are frequent

---

**Deployment completed by:** _________________
**Deployment date:** _________________
**Worker URL:** https://canvas-toolbox-vote.__________.workers.dev
**First vote recorded:** _________________

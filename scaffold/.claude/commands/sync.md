---
description: Single-course Canvas sync (pull/push/build)
---

# Canvas Sync Tool

**What it does:** Mirrors a Canvas course to local files, lets you edit locally, and pushes changes back to Canvas.

**Common operations:**
```bash
# Pull course content from Canvas
uv run python lib/tools/canvas_sync.py --pull

# Check what would be pushed (dry-run)
uv run python lib/tools/canvas_sync.py --push

# Push changes to Canvas (after reviewing dry-run)
uv run python lib/tools/canvas_sync.py --push --apply

# Full workflow: pull → edit → push
uv run python lib/tools/canvas_sync.py --pull
# ... edit files in course/ ...
uv run python lib/tools/canvas_sync.py --push --apply
```

**Safety features:**
- Startup guard (#27) refuses writes to enrolled courses (bypass with `--allow-enrolled`)
- Default is dry-run (requires `--apply` to actually push)

**Need help?** See full documentation in [lib/tools/README.md](../../lib/tools/README.md#core-sync-tools)

---

What would you like to do with the sync tool?

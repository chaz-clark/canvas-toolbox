---
description: Master → Blueprint sync (content + settings)
---

# Blueprint Sync Tool

**What it does:** One-way sync from master course to Blueprint course (content, settings, dates, published state). For online programs using Canvas Blueprint architecture.

**Common usage:**
```bash
# Check what would sync (dry-run)
uv run python lib/tools/blueprint_sync.py

# Sync master → blueprint
uv run python lib/tools/blueprint_sync.py --apply
```

**What it syncs:**
- Course settings (homepage, syllabus)
- Pages, Assignments, Discussions, Quiz content
- Published state
- Due dates

**What it does NOT sync:**
- Module structure
- Item order
- Module completion requirements

Use `/module-settings` for module structure reconciliation.

**Safety features:**
- Startup guard (#27) checks both source (MASTER_COURSE_ID) and target (BLUEPRINT_COURSE_ID)
- Bypass with `--allow-enrolled` if needed
- Page creation is idempotent (title-upsert)

**Need help?** See [lib/tools/README.md](../../lib/tools/README.md#blueprint-tools)

---

Would you like to sync master → blueprint?

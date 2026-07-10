---
description: Module prerequisite/completion reconciliation
---

# Module Settings Sync Tool

**What it does:** Reconciles module prerequisites and completion requirements (prerequisite chain, "complete all" mode, per-item requirements).

**Common usage:**
```bash
# Check what would change (dry-run, default)
uv run python lib/tools/module_settings_sync.py --plan

# Apply changes (confirmation-gated)
uv run python lib/tools/module_settings_sync.py --apply

# Target specific course (default: MASTER_COURSE_ID)
uv run python lib/tools/module_settings_sync.py --target CANVAS_COURSE_ID --plan

# Custom module prefix (default: sprint-)
uv run python lib/tools/module_settings_sync.py --module-prefix week- --plan
```

**Two policies:**
1. **chain-complete** (default): Each module requires completing previous module + all items
2. **graded-work-only** (opt-in): Only graded items require completion

**Example (ITM-327 original behavior):**
```bash
uv run python lib/tools/module_settings_sync.py --policy graded-work-only --rename-match "performance review" --apply
```

**Course-agnostic:** No hardcoded course IDs or module names - works with any course structure.

**Need help?** See [lib/tools/README.md](../../lib/tools/README.md#module-tools)

---

Would you like to reconcile module settings?

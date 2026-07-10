---
description: Post-Blueprint-sync validation (drift + exceptions)
---

# Blueprint Validation Tools

**What they do:** After a Canvas Blueprint sync, validate that sections stayed in sync and understand why items were skipped.

**Two complementary tools:**

### 1. validate_blueprint_sync.py (STATE-DIFF)
**Checks:** Section drift, field drift (lock_at, allowed_extensions, submission_types), duplicates, locked prerequisites

```bash
# Check current state vs. blueprint
uv run python lib/tools/validate_blueprint_sync.py

# Generate markdown report
uv run python lib/tools/validate_blueprint_sync.py --report validation.md
```

### 2. blueprint_exception_report.py (SYNC-LOG)
**Checks:** Why items were skipped during sync (content changes, deletions, settings drift)

```bash
# Analyze most recent Blueprint sync
uv run python lib/tools/blueprint_exception_report.py

# Generate markdown report with lock suggestions
uv run python lib/tools/blueprint_exception_report.py --report exceptions.md --suggest-locks

# Check specific migration
uv run python lib/tools/blueprint_exception_report.py --migration-id 12345
```

**Verdict levels:**
- **PASS:** Due dates, availability dates (expected drift)
- **WARN:** Points, state, settings (review needed)
- **FAIL:** Content changes, deletions (requires attention)

**When to use:** After EVERY Canvas Blueprint sync (run both tools together)

**Need help?** See [lib/tools/README.md](../../lib/tools/README.md#blueprint-tools)

---

Would you like to validate a Blueprint sync?

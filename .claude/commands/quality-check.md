---
description: Post-push structural audit (duplicates, floating items, dates)
---

# Course Quality Check Tool

**What it does:** Post-push structural validation - finds duplicates, floating items, empty modules, broken dates, and alignment issues.

**Common usage:**
```bash
# Default: structural check (duplicates, floating items, empty modules, dates)
uv run python lib/tools/course_quality_check.py

# Check Canvas Files (orphans, broken refs, duplicates)
uv run python lib/tools/course_quality_check.py --files

# Check outcome alignment (Course → Module → Rubric chain)
uv run python lib/tools/course_quality_check.py --alignment

# Validate date windows and ordering
uv run python lib/tools/course_quality_check.py --validate-dates
```

**Four audit modes** (mode-switching, not combined):
1. **Structural** (default): Duplicates, floating items, empty modules, date window
2. **Files** (`--files`): Orphaned files, broken references, duplicates
3. **Alignment** (`--alignment`): Course Outcome → Module Outcome → Rubric breaks
4. **Date validation** (`--validate-dates`): Out-of-window, ordering, duplicate due dates

**When to use:** After every push to any course. Run `--files`, `--alignment`, `--validate-dates` on demand.

**Need help?** See [lib/tools/README.md](../../lib/tools/README.md#quality--audit-tools)

---

Which quality check would you like to run?

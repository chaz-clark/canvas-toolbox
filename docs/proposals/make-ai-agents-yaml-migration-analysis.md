# Make-AI-Agents YAML Migration Analysis for canvas-toolbox

**Date:** 2026-07-07
**Context:** Make-AI-Agents recently migrated from MD+JSON pairs to MD+YAML frontmatter pattern
**Reference:** `~/Documents/GitHub/Make-AI-Agents/knowledge/json_to_yaml_migration.md`

---

## Make-AI-Agents Recent Changes

### What Changed (July 2026)

**5 commits** migrating from JSON companion files to YAML frontmatter:

1. **Purged stale JSON files** - Removed 8-week-old JSON companions
2. **Added YAML frontmatter to all templates** - Following Anthropic Agent Skills pattern
3. **Updated AGENTS.md** - Documented new YAML-first approach
4. **Created migration guide** - `knowledge/json_to_yaml_migration.md`
5. **Special case: canvas-toolbox** - Explicitly called out as "DO NOT MIGRATE"

### Industry Standard Pattern

**All major platforms use YAML frontmatter or MD-only:**

| Platform | Pattern | Notes |
|----------|---------|-------|
| **Anthropic Agent Skills** | MD + YAML frontmatter | `---\nname: pdf\nversion: 1.0\n---` |
| **agentskills.io** | MD + YAML frontmatter | Community standard |
| **Google ADK** | MD only | No frontmatter needed |
| **Hermes Agent** | TXT only | `/llms.txt` pattern |
| ~~Make-AI-Agents (old)~~ | ~~MD + JSON~~ | ❌ Deprecated |
| **Make-AI-Agents (new)** | MD + YAML frontmatter | ✅ Current |

**Zero major platforms use separate JSON files.**

---

## canvas-toolbox Current State

### JSON File Audit

Ran staleness audit (2026-07-07):

```bash
lib/agents/canvas_blueprint_sync.json: 4 weeks behind MD
lib/agents/canvas_content_sync.json: 4 weeks behind MD
lib/agents/canvas_course_expert.json: 0 weeks behind MD ✅
lib/agents/canvas_grader.json: 0 weeks behind MD ✅
lib/agents/canvas_schedule_auditor.json: 4 weeks behind MD
lib/agents/canvas_semester_setup.json: 4 weeks behind MD
lib/agents/ira_program_alignment.json: 4 weeks behind MD
```

**Interpretation:**
- **2 agents current** (canvas_grader, canvas_course_expert) - actively maintained
- **5 agents stale** (4 weeks behind) - migration candidates per Make-AI-Agents threshold

### Tooling Dependencies

**Found 1 active JSON dependency:**

```python
# lib/tools/canvas_api_tool.py (3 references)
config_path = Path(__file__).parent.parent / "agents" / "canvas_course_expert.json"
```

**What it reads:**
- Audit rules (`config["primary_data"]["audit_rules"]`)
- BYUI standards (`config["primary_data"]["byui_standards"]`)
- LLM configuration (`config["implementation"]["llm_agent"]`)

**Verdict:** `canvas_course_expert.json` is **actively used by tooling** → **KEEP**

### AGENTS.md Status

**Already migrated** ✅

```yaml
---
name: canvas-toolbox-agents
description: AGENTS.md for the `canvas-toolbox` repo...
version: "0.1"
author: chaz-clark
license: MIT
metadata:
  repo: canvas-toolbox
  spec-source: Make-AI-Agents/make_AGENTS
---
```

canvas-toolbox AGENTS.md already uses YAML frontmatter (current with Make-AI-Agents standards).

---

## Migration Recommendations

### Decision Matrix

| Agent | JSON Age | Tooling Refs | Recommendation | Rationale |
|-------|----------|--------------|----------------|-----------|
| **canvas_course_expert** | 0 weeks | **YES** (canvas_api_tool.py) | **KEEP JSON** | Actively used by Python tooling |
| **canvas_grader** | 0 weeks | No | **KEEP for now** | Current, no urgency |
| canvas_blueprint_sync | 4 weeks | No | **MIGRATE** | At staleness threshold |
| canvas_content_sync | 4 weeks | No | **MIGRATE** | At staleness threshold |
| canvas_schedule_auditor | 4 weeks | No | **MIGRATE** | At staleness threshold |
| canvas_semester_setup | 4 weeks | No | **MIGRATE** | At staleness threshold |
| ira_program_alignment | 4 weeks | No | **MIGRATE** | At staleness threshold |

---

## Proposed Migration Plan

### Phase 1: Migrate 5 Stale Agents (Low Risk)

**Candidates:**
1. `canvas_blueprint_sync.md/.json`
2. `canvas_content_sync.md/.json`
3. `canvas_schedule_auditor.md/.json`
4. `canvas_semester_setup.md/.json`
5. `ira_program_alignment.md/.json`

**Steps per agent:**

1. **Extract metadata from JSON**:
   ```json
   {
     "_metadata": {
       "template_version": "3.1",
       "last_updated": "2026-05-13",
       "description": "..."
     }
   }
   ```

2. **Add YAML frontmatter to MD**:
   ```markdown
   ---
   name: canvas_blueprint_sync
   version: "3.1"
   last_updated: 2026-05-13
   description: Syncs master course to Canvas Blueprint
   complexity: standard
   agent_type: workflow
   ---

   # Canvas Blueprint Sync Agent Guide
   ...
   ```

3. **Convert any validation rules to inline checklists**:
   ```markdown
   ## Validation Checklist

   - [ ] Blueprint course exists
   - [ ] Master has index.json
   - [ ] No pending local edits
   ```

4. **Delete JSON file**:
   ```bash
   git rm lib/agents/canvas_blueprint_sync.json
   ```

5. **Commit**:
   ```bash
   git commit -m "Migrate canvas_blueprint_sync to YAML frontmatter

   Consolidates metadata into .md file following Anthropic Agent Skills pattern.
   JSON file was 4 weeks stale with zero tooling references."
   ```

**Estimated effort:** 2-3 hours (30 min per agent × 5 agents)

---

### Phase 2: Keep Active Agents As-Is (No Action)

**Agents:**
- `canvas_course_expert.md/.json` - **KEEP** (used by canvas_api_tool.py)
- `canvas_grader.md/.json` - **KEEP** (current, no urgency)

**Rationale:**
- `canvas_course_expert.json` is actively read by Python code
- `canvas_grader.json` is current (0 weeks stale)
- Migration guide explicitly says: "If tooling reads it: Keep JSON OR update tooling first"

**Future action:** If `canvas_grader.json` becomes stale (>4 weeks), revisit.

---

### Phase 3: Optional - Update canvas_api_tool.py (If Desired)

**If we want to eliminate ALL JSON dependencies:**

**Option A: Parse YAML frontmatter instead**

```python
import yaml

def load_agent_config(agent_name: str) -> dict:
    """Load agent config from YAML frontmatter."""
    agent_path = Path(__file__).parent.parent / "agents" / f"{agent_name}.md"

    with open(agent_path) as f:
        content = f.read()

    # Extract YAML frontmatter
    if content.startswith("---"):
        yaml_end = content.find("---", 3)
        frontmatter = yaml.safe_load(content[3:yaml_end])
        return frontmatter

    raise ValueError(f"No YAML frontmatter in {agent_path}")

# Usage
config = load_agent_config("canvas_course_expert")
rules = config["audit_rules"]
```

**Option B: Keep JSON but stop maintaining MD+JSON pairs**

Keep `canvas_course_expert.json` as the "schema/config file" but don't maintain a parallel `.md` file. Treat JSON as a separate config file, not a companion.

**Option C: Leave as-is**

If MD+JSON maintenance works, keep it. Not everything needs to follow the new pattern.

**Estimated effort:** 3-4 hours (update parser + test)

---

## Risks and Mitigation

### Risk 1: Breaking Canvas API Tool

**Risk:** Migrating `canvas_course_expert.json` breaks `canvas_api_tool.py`

**Mitigation:** Phase 2 explicitly keeps this file. No migration until code is updated.

### Risk 2: Lost Metadata

**Risk:** JSON files contain structured data not easily expressed in YAML frontmatter

**Mitigation:**
- Audit each JSON before migration (extract metadata)
- Keep validation rules as inline checklists
- If JSON has complex schemas, keep the JSON file

### Risk 3: Consumer Expectations

**Risk:** Other repos or scripts expect JSON files

**Mitigation:**
- Search codebase for JSON references (already done - only 1 found)
- Phase 1 only migrates files with zero tooling dependencies

---

## Non-Migration Updates (Recommended)

### Update 1: Document JSON Maintenance Policy

Add to `lib/agents/README.md`:

```markdown
## Agent File Patterns

### MD + YAML Frontmatter (Preferred)

canvas-toolbox follows the industry-standard markdown-with-YAML-frontmatter pattern:

```markdown
---
name: agent_name
version: "1.0"
last_updated: 2026-07-07
description: One-sentence description
---

# Agent Name
...
```

### MD + JSON (Legacy)

**Two agents still use JSON files:**

- `canvas_course_expert.json` - **ACTIVE** (used by canvas_api_tool.py for audit rules/standards)
- `canvas_grader.json` - **CURRENT** (actively maintained)

**Maintenance policy:**
- If JSON becomes >4 weeks stale → migrate to YAML frontmatter
- If new tooling needs config → use YAML frontmatter, not JSON
- Keep JSON only when Python code actively reads it
```

### Update 2: Add YAML Frontmatter to Non-Migrated Agents

Even if keeping JSON files, add YAML frontmatter to the MD files for consistency:

```markdown
---
name: canvas_grader
version: "3.1"
last_updated: 2026-06-10
description: FERPA-safe AI-assisted grading pipeline
complexity: complex
agent_type: workflow
companion_json: canvas_grader.json
see_also:
  - knowledge/grader_knowledge.md
  - knowledge/grader_voice_knowledge.md
  - knowledge/grader_setup_knowledge.md
---

# Canvas Grader Agent Guide
...
```

**Benefit:** Consistent pattern across all agents, easier for tools to parse metadata.

**Estimated effort:** 30 minutes (add frontmatter to 2 files)

---

## Implementation Timeline

### Week 1: Low-Risk Migration
- [ ] Audit 5 stale agents (canvas_blueprint_sync, canvas_content_sync, etc.)
- [ ] Add YAML frontmatter to each MD file
- [ ] Delete JSON files
- [ ] Commit + push each agent individually
- [ ] **Estimated:** 2-3 hours

### Week 2: Documentation
- [ ] Add JSON maintenance policy to `lib/agents/README.md`
- [ ] Document which agents still use JSON and why
- [ ] **Estimated:** 1 hour

### Future (Optional):
- [ ] Update canvas_api_tool.py to parse YAML frontmatter
- [ ] Migrate canvas_grader.json if it becomes stale
- [ ] Fully eliminate JSON dependencies

---

## Success Criteria

After migration:

✅ **5 agents migrated** (canvas_blueprint_sync, canvas_content_sync, canvas_schedule_auditor, canvas_semester_setup, ira_program_alignment)
✅ **2 agents keep JSON** (canvas_course_expert, canvas_grader) with documented rationale
✅ **Zero breaking changes** (no tooling reads deleted JSON files)
✅ **Aligned with Make-AI-Agents** (YAML frontmatter standard)
✅ **Policy documented** (when to keep JSON vs migrate)

---

## Appendix: Make-AI-Agents Special Case for canvas-toolbox

From `Make-AI-Agents/knowledge/json_to_yaml_migration.md`:

> ### Case 1: canvas-toolbox Agents
>
> **Current state**: canvas-toolbox has 7 agents with maintained MD+JSON pairs.
>
> **Recommendation**: **DO NOT MIGRATE**
>
> **Why**:
> - JSON files are current (last updated 2026-05-13)
> - Pattern is working (maintained consistently)
> - All 7 pairs are in sync
> - No staleness detected
>
> **When to revisit**:
> - JSON files become stale (>4 weeks old)
> - Maintenance burden increases
> - Tooling stops reading JSON files

**Status update (2026-07-07):** 5/7 agents are now 4 weeks stale → **time to revisit**.

---

## Decision

**Recommendation:** **PROCEED WITH PHASE 1 MIGRATION**

**Rationale:**
1. Make-AI-Agents has proven the YAML pattern works
2. 5 agents are at staleness threshold (4 weeks)
3. Zero tooling reads these 5 JSON files
4. Low risk, high alignment with industry standards
5. Reduces maintenance burden (1 file instead of 2)

**Do NOT migrate:**
- `canvas_course_expert.json` (used by Python code)
- `canvas_grader.json` (current, no urgency)

**Next step:** Get user approval, then execute Phase 1 migration (2-3 hours).

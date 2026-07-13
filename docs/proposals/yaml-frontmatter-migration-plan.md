# YAML Frontmatter Migration Plan — canvas-toolbox Agents

**Date:** 2026-07-07
**Status:** Planning complete, ready for implementation
**Goal:** Migrate all 7 agents from MD+JSON pairs to MD+YAML frontmatter (industry standard)

---

## Executive Summary

**Current state:** 7 agents with MD+JSON companion files
**Target state:** 7 agents with MD+YAML frontmatter only
**Blocker identified:** `canvas_api_tool.py` reads JSON for runtime configuration

**Migration strategy:**
1. Embed structured data in YAML code blocks within markdown
2. Update parser to extract YAML blocks from markdown
3. Migrate all agents using consistent pattern
4. Delete all JSON files

---

## Audit Results

### JSON Usage in canvas_api_tool.py

**File:** `lib/tools/canvas_api_tool.py` (1053 lines)

**3 JSON read locations identified:**

1. **Line 573** (analyze_cognitive_load function):
   ```python
   config_path = Path(__file__).parent.parent / "agents" / "canvas_course_expert.json"
   config = json.load(f)
   rules = config["primary_data"]["audit_rules"]  # 10 rules
   ```

2. **Line 758** (fetch_byui_resources function):
   ```python
   config_path = Path(__file__).parent.parent / "agents" / "canvas_course_expert.json"
   config = json.load(f)
   standards = config["primary_data"]["byui_standards"]  # 6 standards
   ```

3. **Line 792** (run_agent function):
   ```python
   config_path = Path(__file__).parent.parent / "agents" / "canvas_course_expert.json"
   config = json.load(f)
   llm_cfg = config["implementation"]["llm_agent"]  # model, system_prompt, tools, mcp_servers, parameters
   ```

### Data Structures to Preserve

From `canvas_course_expert.json` (1254 lines):

1. **audit_rules** (10 rules, ~100 lines):
   - Each rule: rule_id, name, load_type, hattie_phase, severity, condition, recommendation, canvas_resource, threshold

2. **byui_standards** (6 standards, ~30 lines):
   - Each standard: key, standard, source

3. **llm_agent config** (~300 lines):
   - model, system_prompt (long), tools (array of 15+ tool definitions), mcp_servers, parameters

---

## YAML Frontmatter Design

### Option A: All data in frontmatter (REJECTED)
**Problem:** 1254 lines of frontmatter is unreadable, violates "frontmatter should be metadata" principle

### Option B: Separate YAML files (REJECTED)
**Problem:** Violates industry standard (one file per agent), increases maintenance burden

### Option C: Hybrid — metadata in frontmatter, data in markdown YAML blocks (SELECTED)

**Structure:**
```markdown
---
name: canvas_course_expert
version: "3.6"
last_updated: 2026-07-07
description: Canvas course audit agent using cognitive load theory
complexity: complex
agent_type: llm_agent
model: claude-opus-4-6
runtime_data:
  audit_rules: see_markdown_section
  byui_standards: see_markdown_section
  llm_config: see_markdown_section
---

# Canvas Course Expert Agent Guide

[Narrative content here...]

## Runtime Configuration

### Audit Rules

```yaml
audit_rules:
  - rule_id: CL-001
    name: Module Item Count
    load_type: extraneous
    hattie_phase: surface
    severity: warning
    condition: Module contains more than 7 items
    threshold: 7
    recommendation: Split module into two sub-modules...
    canvas_resource: module

  - rule_id: CL-002
    name: Missing Module Overview
    # ... (10 rules total)
```

### BYUI Standards

```yaml
byui_standards:
  - key: module_structure
    standard: Standard BYUI module structure...
    source: BYUI Course Design Standards

  - key: module_naming
    # ... (6 standards total)
```

### LLM Agent Configuration

```yaml
llm_agent:
  model: claude-opus-4-6
  system_prompt: |
    You are a Canvas LMS Course Expert for BYU-Idaho...
    [long system prompt]
  tools:
    - name: parse_course_export
      description: Extracts and parses...
      parameters: {...}
    # ... (15+ tools)
  mcp_servers:
    - type: url
      url: http://localhost:3000/mcp
      name: canvas
  parameters:
    temperature: 0.1
    max_tokens: 8192
```

---

## Parser Implementation

### New Function: `load_agent_config(agent_name: str) -> dict`

**Location:** `lib/tools/canvas_api_tool.py` (new helper function)

**Implementation:**

```python
import yaml
from pathlib import Path
import re

def load_agent_config(agent_name: str) -> dict:
    """
    Load agent configuration from markdown file with YAML frontmatter + embedded YAML blocks.

    Returns a dict matching the old JSON structure:
    {
        "primary_data": {
            "audit_rules": [...],
            "byui_standards": [...]
        },
        "implementation": {
            "llm_agent": {...}
        }
    }
    """
    agent_path = Path(__file__).parent.parent / "agents" / f"{agent_name}.md"

    if not agent_path.exists():
        raise FileNotFoundError(f"Agent file not found: {agent_path}")

    content = agent_path.read_text(encoding="utf-8")

    # Extract YAML frontmatter
    frontmatter = {}
    if content.startswith("---"):
        yaml_end = content.find("---", 3)
        if yaml_end != -1:
            frontmatter = yaml.safe_load(content[3:yaml_end])

    # Extract YAML code blocks from markdown body
    config_data = {
        "primary_data": {},
        "implementation": {}
    }

    # Pattern: ```yaml\n[content]\n```
    yaml_blocks = re.findall(r'```yaml\n(.*?)\n```', content, re.DOTALL)

    for block_text in yaml_blocks:
        block = yaml.safe_load(block_text)
        if not block:
            continue

        # Identify block by its keys
        if "audit_rules" in block:
            config_data["primary_data"]["audit_rules"] = block["audit_rules"]
        elif "byui_standards" in block:
            config_data["primary_data"]["byui_standards"] = block["byui_standards"]
        elif "llm_agent" in block:
            config_data["implementation"]["llm_agent"] = block["llm_agent"]

    return config_data
```

### Update 3 Call Sites

**Before:**
```python
config_path = Path(__file__).parent.parent / "agents" / "canvas_course_expert.json"
with open(config_path) as f:
    config = json.load(f)
```

**After:**
```python
config = load_agent_config("canvas_course_expert")
```

**Changes:**
- Line 573-577 (analyze_cognitive_load): Replace JSON load with `load_agent_config()`
- Line 758-762 (fetch_byui_resources): Replace JSON load with `load_agent_config()`
- Line 792-796 (run_agent): Replace JSON load with `load_agent_config()`

---

## Agent-by-Agent Migration Plan

### Phase 1: canvas_course_expert (complex agent with runtime data)

**Files:**
- Input: `canvas_course_expert.json` (1254 lines), `canvas_course_expert.md`
- Output: `canvas_course_expert.md` (with frontmatter + YAML blocks)

**Steps:**
1. Read canvas_course_expert.md (current narrative)
2. Extract metadata from JSON `_metadata` section → YAML frontmatter
3. Append "## Runtime Configuration" section to markdown
4. Add 3 YAML code blocks: audit_rules, byui_standards, llm_agent
5. Test with updated canvas_api_tool.py parser
6. Delete canvas_course_expert.json

**Estimated time:** 45 minutes

### Phase 2: canvas_grader (complex agent, no tooling dependency)

**Files:**
- Input: `canvas_grader.json`, `canvas_grader.md`
- Output: `canvas_grader.md` (with frontmatter only)

**Structure:**
```yaml
---
name: canvas_grader
version: "3.1"
last_updated: 2026-06-10
description: FERPA-safe AI-assisted grading pipeline
complexity: complex
agent_type: workflow
ferpa_zone: zone_1_pii
see_also:
  - knowledge/grader_knowledge.md
  - knowledge/grader_voice_knowledge.md
  - knowledge/grader_setup_knowledge.md
---
```

**Note:** canvas_grader.json has no runtime tooling dependency, so all data goes in frontmatter.

**Estimated time:** 20 minutes

### Phase 3-7: Remaining 5 agents (standard agents)

**Agents:**
1. canvas_blueprint_sync
2. canvas_content_sync
3. canvas_schedule_auditor
4. canvas_semester_setup
5. ira_program_alignment

**Pattern (consistent across all 5):**
```yaml
---
name: {agent_name}
version: "3.1"
last_updated: {date from JSON}
description: {from JSON._metadata.description}
complexity: standard
agent_type: workflow
validation_checklist:
  - {extracted from JSON validation section}
---
```

**Steps per agent:**
1. Extract metadata from JSON
2. Add YAML frontmatter to existing MD file
3. Convert validation rules to markdown checklist (if present)
4. Delete JSON file

**Estimated time:** 15 minutes each × 5 agents = 75 minutes

---

## Total Timeline

| Phase | Agent(s) | Time | Cumulative |
|-------|----------|------|------------|
| 0. Parser update | canvas_api_tool.py | 30 min | 30 min |
| 1. Complex (runtime) | canvas_course_expert | 45 min | 75 min |
| 2. Complex (no runtime) | canvas_grader | 20 min | 95 min |
| 3-7. Standard | 5 agents | 75 min | 170 min |
| 8. Test + commit | All agents | 20 min | 190 min |

**Total estimated time:** ~3 hours

---

## Testing Plan

### Test 1: Parser function
```bash
# Add test to canvas_api_tool.py
python -c "from lib.tools.canvas_api_tool import load_agent_config; cfg = load_agent_config('canvas_course_expert'); print(len(cfg['primary_data']['audit_rules']))"
# Expected output: 10
```

### Test 2: Existing smoke tests
```bash
python lib/tools/canvas_api_tool.py --test
# All tests should pass (unchanged behavior)
```

### Test 3: Actual course audit
```bash
# If user has a test IMSCC export
python lib/tools/canvas_api_tool.py --audit /path/to/export.imscc --dry-run
# Should work identically to JSON-based version
```

### Test 4: Verify JSON files deleted
```bash
find lib/agents -name "*.json" -not -path "*/pre_knowledge/*"
# Expected output: (empty)
```

---

## Rollback Plan

If parser breaks:

1. **Immediate:** Revert canvas_api_tool.py to JSON-loading version
2. **Preserve work:** Keep new .md files, restore .json files from git
3. **Debug:** Fix parser, re-test Test 1-3, try again

**Rollback safety:** All changes are in a single commit, can `git revert` atomically.

---

## Success Criteria

✅ **All 7 agents migrated to YAML frontmatter**
✅ **Zero JSON files in lib/agents/ (except pre_knowledge/)**
✅ **canvas_api_tool.py smoke tests pass**
✅ **Markdown files are human-readable** (no >100-line frontmatter blocks)
✅ **Aligned with Make-AI-Agents + Anthropic Agent Skills standard**
✅ **No breaking changes to tool functionality**

---

## Implementation Order

1. ✅ Audit complete (identified 3 call sites, 1254 lines of data)
2. ⏭ Implement `load_agent_config()` parser
3. ⏭ Update 3 call sites in canvas_api_tool.py
4. ⏭ Test parser with existing JSON file (pre-migration validation)
5. ⏭ Migrate canvas_course_expert (complex)
6. ⏭ Test canvas_api_tool.py --test (validate no regression)
7. ⏭ Migrate canvas_grader
8. ⏭ Migrate remaining 5 agents in batch
9. ⏭ Delete all 7 JSON files
10. ⏭ Final smoke test + commit

---

## Next Step

Proceed with implementing `load_agent_config()` parser in canvas_api_tool.py.

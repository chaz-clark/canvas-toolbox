**Date:** 2026-06-29
**Author:** Claude Code agent + ngai-n8n repo
**Direction:** request
**Status:** delivered
**Origin:** NGAI platform architecture design pass identified 7 canvas-toolbox features needed for peer/QC/orchestrator layer functionality
**Origin-Commit:** 1472ac7 (design/features.md and design/strategy.md establish platform requirements)
**Topic:** canvas-toolbox-features

---

# Feature request: NGAI Platform Integration Features

## What features

Seven new canvas-toolbox capabilities to enable NGAI (Non-General AI) platform integration:

1. **Differential Content Access** (student-view vs instructor-view) - CRITICAL
2. **Quiz Differential Fetch** (questions with/without answers) - CRITICAL
3. **Teaching Sheet Pseudo-Generation** (LLM-based evaluation criteria) - CRITICAL
4. **Multi-Submission Tracker** - HIGH
5. **Remedial Assignment Cloning** (academic integrity) - HIGH
6. **Course Design Gap Analysis** - MEDIUM
7. **Real-Time Comment De-Identification** - LOW

## Why this lives in canvas-toolbox

Canvas-toolbox owns the Canvas API integration layer and grading workflow patterns. NGAI platform needs:
- **Canvas permission model expertise** - student-view vs instructor-view requires Canvas API knowledge canvas-toolbox already has
- **Grading workflow patterns** - teaching sheet generation extends canvas-toolbox's existing rubric/feedback patterns
- **Canvas data access** - quiz API, submissions API, assignments API - all canvas-toolbox's domain
- **Tool-agnostic CLI pattern** - NGAI n8n workflows call canvas-toolbox via Execute Command node, need structured JSON output

NGAI platform could reimplement Canvas API calls, but that duplicates canvas-toolbox's core competency and breaks the symbiotic relationship.

## How ngai-n8n would use it

### Use Case 1: Peer Agent Fetches Student-View Content
```bash
# Peer workflow calls canvas-toolbox for module content WITHOUT answer keys
uv run python lib/tools/module_fetch.py \
  --module-id 123 \
  --access-mode student_view \
  --output json

# Returns: module content, quiz questions (no answers), assignments (no solutions)
```

### Use Case 2: QC Agent Validates Quiz Answers
```bash
# QC workflow gets questions WITH answers to validate student responses
uv run python lib/tools/quiz_fetch.py \
  --quiz-id 789 \
  --mode questions_with_answers \
  --output json

# Returns: questions + correct_answer + correct_comments
```

### Use Case 3: QC Generates Teaching Sheet
```bash
# Orchestrator generates teaching evaluation criteria from module content
uv run python lib/tools/teaching_sheet_generate.py \
  --module-id 123 \
  --output yaml

# Returns: YAML rubric with teaching criteria, evaluation rubric
```

### Use Case 4: QC Creates Remedial Assignment
```bash
# When student can-do-but-can't-teach, clone assignment with modifications
uv run python lib/tools/remedial_clone.py \
  --assignment-id 456 \
  --student-id 123 \
  --strategy change_values \
  --output json

# Returns: new assignment ID, modifications applied, unpublished status
```

## Suggested shape

**n8n Integration Requirements** (all features):
- ✅ CLI flags for all parameters (no interactive prompts - breaks n8n automation)
- ✅ Structured output to stdout: JSON or YAML only (parseable by n8n)
- ✅ Exit codes: 0 = success, non-zero = error
- ✅ Errors to stderr (keeps stdout clean for n8n parsing)
- ✅ `--help` flag with parameter docs

**Detailed Specs**: See companion document (next section)

## Companion Documentation

Full feature specifications with acceptance criteria, technical requirements, and examples:

**Location**: ngai-n8n repo → `handoff/canvas-toolbox-requirements.md` (mistakenly committed to handoff/ repo - will be moved to proper location)

**Content Summary**:
- 7 features with user stories
- Input/output specifications
- Acceptance criteria per feature
- Complexity estimates
- Implementation suggestions
- Feature dependency graph
- Timeline: Phase 1 (4-6 weeks MVP), Phase 2 (8-10 weeks production)

**Note**: That document was incorrectly placed in the handoff/ repo itself. The canonical version should be referenced from ngai-n8n/design/ or extracted here.

## What we've ruled out

### Alternative 1: NGAI reimplements Canvas API calls
**Rejected because**:
- Duplicates canvas-toolbox's core competency
- Loses canvas-toolbox's grading workflow patterns and voice knowledge
- Breaks institutional knowledge transfer (canvas-toolbox team understands Canvas quirks)
- Can't leverage canvas-toolbox's existing error handling, rate limiting, de-identification

### Alternative 2: Canvas-toolbox as REST microservice instead of CLI
**Deferred to V2**:
- MVP uses Execute Command node (simpler, uses existing CLI pattern)
- Production may wrap canvas-toolbox in FastAPI for better n8n integration
- CLI-first approach validates features before investing in service wrapper

### Alternative 3: Build as n8n custom nodes (JavaScript/TypeScript rewrite)
**Rejected because**:
- Significant dev effort to rewrite working Python code
- Loses updates from canvas-toolbox upstream
- canvas-toolbox is multi-tool (works with Claude Code, Cursor, Aider), n8n nodes lock it to n8n only

## Acceptance check

For each feature, canvas-toolbox provides:
1. ✅ CLI tool works when called from n8n Execute Command node
2. ✅ Returns clean JSON/YAML to stdout (parseable by n8n Code node)
3. ✅ Exit code 0 on success, non-zero on error
4. ✅ `--help` documentation exists
5. ✅ Unit tests pass (pytest)
6. ✅ Integration test against Canvas sandbox instance
7. ✅ Example usage in feature documentation

NGAI team verifies:
1. ✅ n8n workflow successfully calls canvas-toolbox tool
2. ✅ Peer agent receives student-view content without answers (Feature 1 & 2)
3. ✅ QC agent auto-grades using canvas-toolbox + teaching sheets (Feature 3)
4. ✅ Multi-submission handling works (Feature 4)
5. ✅ Remedial assignment created and assigned to specific student (Feature 5)
6. ✅ End-to-end: student → peer → QC → orchestrator → Canvas write

## Priority & Timeline

**Phase 1 (MVP - 4-6 weeks)**:
- Feature 1: Differential Content Access (CRITICAL)
- Feature 2: Quiz Differential Fetch (CRITICAL)
- Feature 3: Teaching Sheet Generation (CRITICAL)
- Feature 4: Multi-Submission Tracker (HIGH)

**Phase 2 (Production - 8-10 weeks)**:
- Feature 5: Remedial Assignment Cloning (HIGH)
- Feature 6: Course Gap Analysis (MEDIUM)
- Feature 7: Comment De-Identification (LOW - nice-to-have)

**Blocking**: NGAI pilot (10-20 students, 1 module) cannot run without Phase 1 features.

## Next Steps

1. **Canvas-toolbox team reviews** this handoff + companion specs
2. **Technical questions** clarified via handoff response document
3. **Implementation begins** on Phase 1 features (parallel with NGAI workflow development)
4. **Weekly sync** (optional) to unblock questions, coordinate Canvas sandbox testing
5. **Feature delivery** via GitHub PRs + release tags
6. **NGAI integration testing** as features become available

---

## Lifecycle

- 2026-06-29: Authored (Status: draft)

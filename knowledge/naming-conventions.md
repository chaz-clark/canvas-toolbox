# Naming Conventions

**Purpose:** Document file and variable naming standards used throughout canvas-toolbox.

---

## File Naming

Follow ecosystem-specific conventions based on file type:

### Python Files (.py)

**Convention:** `snake_case` (underscores)

**Rationale:**
- Python community standard (PEP 8)
- Required for importable modules (hyphens break Python imports)
- Consistency with Python stdlib and ecosystem

**Examples:**
- `student_late_accommodation.py`
- `submit_on_behalf.py`
- `_override_recalc_helper.py`

### Markdown Files (.md)

**Convention:** `kebab-case` (hyphens)

**Rationale:**
- Web and documentation standard
- URL-friendly (hyphens preferred over underscores in URLs)
- SEO best practice
- Cross-language convention

**Examples:**
- `course-design-workflow.md`
- `grading-readme.md`
- `submit-on-behalf-findings.md`
- `accommodation-recalc-findings.md`

**Exceptions:** Special files use UPPERCASE:
- `README.md`
- `AGENTS.md`
- `CHANGELOG.md`
- `ROADMAP.md`
- `UPGRADING.md`

### Rust Files (.rs)

**Convention:** `snake_case` (underscores)

**Rationale:**
- Rust community standard (rustfmt default)
- Cargo expects snake_case for modules and binaries

**Examples:**
- `engagement_audit.rs`
- `main.rs`

### Configuration Files

**Convention:** `kebab-case` (hyphens)

**Rationale:**
- Industry standard for config files
- Cross-platform compatibility

**Examples:**
- `pyproject.toml`
- `wrangler.jsonc`
- `.pre-commit-config.yaml`

---

## Directory Naming

**Convention:** `snake_case` (underscores)

**Rationale:**
- Python package/module compatibility
- Consistency with file naming for importable directories

**Examples:**
- `lib/tools/`
- `lib/agents/`
- `grading/`
- `engagement_audit_rs/`

---

## Variable and Function Naming

Follow language-specific conventions:

### Python

**Variables and functions:** `snake_case`
```python
def force_recalc_for_student(student_id, assignment_id):
    user_overrides = get_overrides(student_id)
```

**Classes:** `PascalCase`
```python
class AssignmentOverride:
    pass
```

**Constants:** `UPPER_SNAKE_CASE`
```python
DEFAULT_MASTER = Path("grading/.deid_master.csv")
MAX_RETRIES = 3
```

### Rust

**Variables and functions:** `snake_case`
```rust
fn calculate_engagement_score(student_id: i64) -> f64 {
    let page_views = get_page_views(student_id);
}
```

**Structs and Enums:** `PascalCase`
```rust
struct EngagementMetrics {
    page_views: u32,
}
```

**Constants:** `UPPER_SNAKE_CASE`
```rust
const MAX_CACHE_SIZE: usize = 1000;
```

---

## User-Facing Output Formatting

**Convention:** Use natural English with spaces and proper capitalization for all user-facing output.

**Rationale:**
- Terminal output is for humans, not parsers
- Readability over technical field names
- Consistent with modern CLI tool conventions (npm, cargo, git)

### General Principles

1. **Labels use natural language:** "User ID" not "user_id"
2. **Proper spacing:** Use `: ` between label and value
3. **Indentation for hierarchy:** Use 2 spaces per level
4. **Status indicators:** Use symbols (✓, ✗, ⚠) for visual scanning
5. **Error messages:** Start with "ERROR:" prefix, use stderr

### Good Examples

```python
# ✓ Natural English labels
print(f"Course: {course_name}")
print(f"Course ID: {course_id}")
print(f"Assignment: {assignment_name}")
print(f"User ID: {user_id}")
print(f"Submitted at: {timestamp}")
print(f"Workflow state: {state}")

# ✓ Hierarchical output
print("Classification:")
print(f"  Active:      {counts['active']:3d}")
print(f"  Withdrawn:   {counts['withdrawn']:3d}")
print(f"  Total:       {counts['total']:3d}")

# ✓ Status indicators
print(f"  ✓ Uploaded (Canvas file ID: {file_id})")
print(f"  ✗ Upload failed: {error}")
print(f"  ⚠ Warning: {warning}")

# ✓ Dry-run mode
print("[DRY RUN] Would perform these actions:")
print(f"  1. Upload file: {filename}")
print(f"  2. Submit on behalf of user {user_id}")

# ✓ Error messages
print("ERROR: Missing Canvas credentials", file=sys.stderr)
print(f"ERROR: File not found: {path}", file=sys.stderr)
```

### Bad Examples (Avoid)

```python
# ✗ Technical field names
print(f"user_id={user_id}")          # Use "User ID: 123"
print(f"file_id: {file_id}")         # Inconsistent casing
print(f"override id={override_id}")  # Missing capitalization

# ✗ Inconsistent formatting
print(f"Course:{course_name}")       # Missing space after colon
print(f"user_id = {user_id}")        # Using = instead of :

# ✗ No status indicators
print(f"Uploaded file_id {file_id}") # Unclear if success/fail
print(f"Failed to upload {file}")    # Use ✗ symbol

# ✗ Mixed conventions in same tool
print(f"Course: {course_name}")      # Good
print(f"assignment_id={aid}")        # Bad - switch to "Assignment ID: {aid}"
```

### CLI Argument Names

**Convention:** Use `kebab-case` for all CLI flags and arguments.

**Rationale:**
- Standard across modern CLI tools
- More readable than underscores in flags
- Consistent with argparse conventions

```python
# ✓ Good CLI arguments
parser.add_argument("--assignment-id")
parser.add_argument("--force-recalc")
parser.add_argument("--deid-code")
parser.add_argument("--uf-date")

# ✗ Bad CLI arguments
parser.add_argument("--assignment_id")  # Use hyphens, not underscores
parser.add_argument("--forceRecalc")    # Use kebab-case, not camelCase
```

### Log Prefixes

Use consistent prefixes for different message types:

```python
# Status messages (stdout)
print(f"student user_id={uid} | scope: assignment {aid} | ADD accommodation | APPLY")

# Progress indicators
print(f"  [recalc] Forcing override recalculation...")
print(f"  [recalc] ✓ Recalculated {count} override(s)")

# Error messages (stderr)
print("ERROR: Missing required argument", file=sys.stderr)
print(f"ERROR: {exception}", file=sys.stderr)

# Warnings (stderr)
print(f"  ⚠ Warning: {warning_message}", file=sys.stderr)

# Debug/Dry-run
print("[DRY RUN] Would perform action")
print(f"  [DRY] {action_description}")
```

### Alignment and Padding

For tabular output, align values consistently:

```python
# ✓ Right-aligned numbers
print(f"  Active:      {counts['active']:3d}")
print(f"  Withdrawn:   {counts['withdrawn']:3d}")

# ✓ Left-aligned labels, right-aligned values
print(f"  Course:             {course_name}")
print(f"  Course ID:          {course_id}")
print(f"  UF cutoff:          {uf_date}")
```

### JSON/Structured Output

For machine-parseable output, use snake_case field names:

```python
# ✓ Structured output (JSON, CSV, etc.)
output = {
    "course_id": 407908,
    "user_id": 173819,
    "assignment_id": 16958677,
    "submitted_at": "2026-07-08T12:00:00Z"
}
print(json.dumps(output, indent=2))

# ✓ CSV headers
csv_writer.writerow(["user_id", "assignment_id", "submitted_at"])
```

**Rule:** Use `snake_case` for structured data, natural English for human-readable output.

---

## Why Ecosystem-Specific Conventions?

**Alternative considered:** Force one convention everywhere (all kebab-case or all snake_case).

**Rejected because:**
- Python imports break with hyphens (`import student-late-accommodation` is syntax error)
- Markdown files with underscores look wrong in URLs
- Fighting ecosystem conventions creates friction for contributors

**Decision:** Follow each ecosystem's established conventions. This:
- Maximizes compatibility with language tooling
- Reduces cognitive load for developers familiar with each ecosystem
- Aligns with open-source best practices

---

## Enforcement

**Pre-commit hooks:** Check naming conventions (future - not yet implemented)

**Code review:** AI agents should flag naming violations when suggesting changes

**Migration:** When renaming existing files:
1. Use `git mv` to preserve history
2. Update all references (grep for old name)
3. Test that imports still work
4. Commit rename + reference updates together

---

## References

- Python PEP 8: https://peps.python.org/pep-0008/
- Rust API Guidelines: https://rust-lang.github.io/api-guidelines/naming.html
- Web naming conventions: https://developers.google.com/style/filenames

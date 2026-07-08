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

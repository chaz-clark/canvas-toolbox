# 3-Phase Rust Migration Strategy (Option C)

**Approved approach:** Gradual migration from Python-only to Rust-required, with dual implementation in between.

**Version strategy:** v1.x (Python-only) → v2.x (Python + Rust hybrid) → v3.x (Rust-required)

**Date:** 2026-07-06 (for implementation starting 2026-07-07)

---

## Phase 1: Dual Implementation (v2.0.0 - Now to +3 months)

**Goal:** Introduce Rust as optional, maintain both implementations, gather data.

### Version: v2.0.0
**Major version bump signals:** Rust support added, but backward compatible (Python fallback exists).

### Implementation Architecture

```
lib/tools/
  # Public interface (unchanged for users)
  fix_group_override_recalc.py          # Runtime dispatcher

  # Implementation layers
  _fix_group_override_recalc_python.py  # Python-only implementation
  _fix_group_override_recalc_rust.py    # Rust wrapper
  fix_override_recalc_rs/               # Rust binary
    src/main.rs
    Cargo.toml
    target/release/fix-override-recalc
```

### Dispatcher Logic
```python
#!/usr/bin/env python3
"""fix_group_override_recalc.py - Runtime dispatcher (v2.x)"""

import sys
from pathlib import Path

def has_rust_binary() -> bool:
    rust_bin = Path(__file__).parent / "fix_override_recalc_rs" / "target" / "release" / "fix-override-recalc"
    return rust_bin.exists()

def main() -> int:
    # Load .env once (shared by both implementations)
    try:
        from _env_loader import load_env
        load_env()
    except ImportError:
        pass

    # Choose implementation at runtime
    if has_rust_binary():
        from _fix_group_override_recalc_rust import main as rust_main
        return rust_main()
    else:
        print("⚠️  Using Python fallback (10-100x slower for large courses)")
        print("   Install Rust for speedup: cb-init --with-rust")
        print("   Estimated: 5-10 min → 5-15 sec for 100+ assignments")
        print()
        from _fix_group_override_recalc_python import main as python_main
        return python_main()

if __name__ == "__main__":
    sys.exit(main())
```

### cb-init Changes
```python
# New optional step in cb-init
parser.add_argument("--with-rust", action="store_true",
                    help="Install Rust toolchain and build high-performance binaries (opt-in)")

def step_5_rust_optional(*, auto_yes: bool, check_only: bool, with_rust: bool) -> bool:
    if not with_rust:
        print("Step 5/9: ⏭  Rust installation skipped (use --with-rust to enable).")
        print("          Python fallbacks will work but be slower for large courses.")
        return True

    # Install Rust + build binaries (same as auto-install plan)
    ...
```

### What We Maintain in Phase 1
- ✅ Both Python and Rust implementations
- ✅ Feature parity (or document differences)
- ✅ Tests for both paths
- ✅ Performance benchmarks
- ✅ Usage telemetry (which path is users hitting?)

### Success Criteria for Phase 1 → Phase 2
After 3 months, evaluate:
1. **Rust adoption rate:** % of users who run `--with-rust`
2. **Performance satisfaction:** Complaints about Python fallback being too slow?
3. **Rust stability:** Any issues with Rust toolchain/builds?
4. **Additional Rust candidates:** 2+ more tools proven to benefit?

**Decision gate:**
- If >50% adopt Rust + 2+ tools benefit → proceed to Phase 2
- If <25% adopt Rust + stable → keep Phase 1 longer
- If Rust unstable/problematic → abort, remove Rust

---

## Phase 2: Rust as Default (v2.5.0 - Months 3-6)

**Goal:** Make Rust the default, Python becomes the fallback for edge cases only.

### Version: v2.5.0
**Minor version bump signals:** Default behavior changes (Rust becomes recommended), but still backward compatible.

### cb-init Changes
```python
# Rust becomes default (with prompt)
def step_5_rust_default(*, auto_yes: bool, check_only: bool) -> bool:
    if is_rust_installed():
        print("Step 5/9: ✓ Rust already installed — skipping.")
        return True

    print("Step 5/9: Rust not installed. Rust is recommended for large courses.")
    print("          ~500MB download, 2-5 min install. Enables 10-100x speedup.")

    if not prompt_y_n("Install Rust via rustup?", default_yes=True, auto_yes=auto_yes):
        print("  ⚠️  Skipped. Python fallback will be used (slower for 100+ assignments).")
        print("     Install later with: cb-init --with-rust")
        return True  # non-fatal

    # Install Rust...
```

### Messaging Changes
```python
# Python fallback becomes more explicit
def main() -> int:
    if has_rust_binary():
        from _fix_group_override_recalc_rust import main as rust_main
        return rust_main()
    else:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("⚠️  PERFORMANCE WARNING: Rust not installed")
        print()
        print("This tool will use Python fallback (10-100x slower).")
        print("For courses with 100+ assignments, this may take 5-10 minutes.")
        print()
        print("To install Rust (recommended): cb-init --with-rust")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print()

        from _fix_group_override_recalc_python import main as python_main
        return python_main()
```

### Documentation Updates
**README.md:**
```markdown
## Performance Requirements

Canvas-toolbox v2.5+ uses Rust for high-performance Canvas API operations.

**Rust is recommended for:**
- Courses with 50+ students
- Courses with 100+ assignments
- Bulk accommodation workflows
- Large course audits

**Installation:**
```bash
cb-init --with-rust  # Installs Rust + builds binaries (~600MB, one-time)
```

Python fallbacks exist but are 10-100x slower for large courses.
```

### Success Criteria for Phase 2 → Phase 3
After 3 more months (6 months total), evaluate:
1. **Rust adoption rate:** >75% of users running Rust version?
2. **Python fallback usage:** <10% of operations use Python fallback?
3. **Issue reports:** Any "Python fallback too slow" complaints?
4. **Rust ecosystem:** 3+ tools now using Rust implementations?

**Decision gate:**
- If >75% Rust + 3+ tools → proceed to Phase 3 (remove Python)
- If 50-75% Rust → extend Phase 2, keep monitoring
- If <50% Rust → stay in Phase 2 indefinitely (maybe Python is "good enough")

---

## Phase 3: Rust Required (v3.0.0 - Months 6-12)

**Goal:** Remove Python fallbacks, Rust becomes required dependency.

### Version: v3.0.0
**Major version bump signals:** Breaking change (Rust required, Python implementations removed).

### Architecture Changes
```
lib/tools/
  fix_group_override_recalc.py          # Now a thin wrapper, no fallback
  fix_override_recalc_rs/               # Rust implementation (only version)
    src/main.rs
    Cargo.toml

  # REMOVED:
  # _fix_group_override_recalc_python.py   ❌
  # _fix_group_override_recalc_rust.py     ❌ (merged into main script)
```

### Simplified Script
```python
#!/usr/bin/env python3
"""fix_group_override_recalc.py - Rust wrapper (v3.x)"""

import subprocess
import sys
from pathlib import Path

def main() -> int:
    """Thin wrapper around Rust binary. Rust is required in v3.x."""
    rust_bin = Path(__file__).parent / "fix_override_recalc_rs" / "target" / "release" / "fix-override-recalc"

    if not rust_bin.exists():
        print("ERROR: Rust binary not found.")
        print()
        print("canvas-toolbox v3.x requires Rust. Install with:")
        print("  cb-init --with-rust")
        print()
        print("Or upgrade Rust components:")
        print("  cb-upgrade-rust")
        print()
        print("For Python-only version, downgrade to v2.x:")
        print("  See docs/UPGRADING.md for migration guide")
        return 2

    # Execute Rust binary (no fallback)
    result = subprocess.run([str(rust_bin)] + sys.argv[1:])
    return result.returncode

if __name__ == "__main__":
    sys.exit(main())
```

### cb-init Changes (Rust Required)
```python
def step_5_rust_required(*, auto_yes: bool, check_only: bool) -> bool:
    """Install Rust (REQUIRED in v3.x)."""
    if is_rust_installed() and are_all_rust_binaries_built():
        print("Step 5/9: ✓ Rust + binaries already installed — skipping.")
        return True

    if not is_rust_installed():
        print("Step 5/9: Rust is REQUIRED for canvas-toolbox v3.x.")
        print("          ~500MB download, 2-5 min install.")

        if not prompt_y_n("Install Rust via rustup?", default_yes=True, auto_yes=auto_yes):
            print("  ✗ Rust installation declined.")
            print("    canvas-toolbox v3.x cannot proceed without Rust.")
            print()
            print("  Options:")
            print("    1. Install Rust manually: https://rustup.rs/")
            print("    2. Downgrade to v2.x: pip install 'canvas-toolbox<3.0'")
            return False  # FATAL - can't proceed

        # Install Rust...

    # Build binaries (required)
    print("  Building Rust binaries (required for v3.x)...")
    if not build_rust_binaries():
        print("  ✗ Rust binary build failed.")
        print("    canvas-toolbox v3.x requires working Rust binaries.")
        return False  # FATAL

    print("  ✓ Rust installed + binaries built.")
    return True
```

### Upgrade Script: `cb-upgrade-rust`

**Purpose:** Help v2.x → v3.x migration (Python fallback → Rust required).

```python
#!/usr/bin/env python3
"""cb-upgrade-rust - Migrate from v2.x (Rust optional) to v3.x (Rust required)"""

import subprocess
import sys
from pathlib import Path

def check_rust_installed() -> bool:
    """Check if Rust is already installed."""
    return shutil.which("cargo") is not None

def check_rust_binaries_built() -> bool:
    """Check if all Rust binaries are built."""
    # Check each expected binary...
    pass

def main() -> int:
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("canvas-toolbox v2.x → v3.x upgrade")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print("What's changing:")
    print("  • v2.x: Rust optional, Python fallback available")
    print("  • v3.x: Rust REQUIRED, Python fallback removed")
    print()
    print("Why the change:")
    print("  • 75%+ of users now use Rust version")
    print("  • Python fallback is 10-100x slower")
    print("  • Maintaining both implementations is costly")
    print()

    # Check current state
    if check_rust_installed() and check_rust_binaries_built():
        print("✓ You're already running Rust - no action needed!")
        print()
        print("You can upgrade to v3.x anytime:")
        print("  pip install --upgrade canvas-toolbox")
        return 0

    if not check_rust_installed():
        print("⚠️  Rust not installed")
        print()
        print("To upgrade to v3.x, you must install Rust.")
        print()
        if not prompt_y_n("Install Rust now (~500MB, 2-5 min)?"):
            print()
            print("Upgrade declined. You can:")
            print("  1. Stay on v2.x (Python fallback still works)")
            print("  2. Install Rust manually: https://rustup.rs/")
            print("  3. Run this script again: cb-upgrade-rust")
            return 1

        # Install Rust
        print("Installing Rust...")
        if not install_rust():
            print("✗ Rust installation failed")
            return 1
        print("✓ Rust installed")

    # Build binaries
    print()
    print("Building Rust binaries...")
    if not build_all_rust_binaries():
        print("✗ Binary build failed")
        return 1

    print("✓ Rust binaries built")
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("✓ Upgrade preparation complete!")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print("You can now upgrade to v3.x:")
    print("  pip install --upgrade canvas-toolbox")
    print()
    print("Or stay on v2.x (Rust will be used automatically)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

### Migration Guide: `docs/UPGRADING.md`

```markdown
# Upgrading to canvas-toolbox v3.0

## What Changed

**v2.x → v3.x: Rust becomes required**

- **v2.x:** Rust optional, Python fallback available (slower)
- **v3.x:** Rust required, Python fallback removed

## Why the Change

After 6 months of v2.x:
- 75%+ of users adopted Rust
- Python fallback was 10-100x slower (5-10 min vs 5-15 sec for large courses)
- Maintaining both implementations was costly

## Upgrade Steps

### Option 1: Automatic (Recommended)

```bash
# Check if you're ready for v3.x
cb-upgrade-rust

# If ready, upgrade
pip install --upgrade canvas-toolbox
```

### Option 2: Manual

```bash
# 1. Install Rust (if not already installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# 2. Build Rust binaries
cd canvas-toolbox/lib/tools/fix_override_recalc_rs
cargo build --release

# 3. Upgrade canvas-toolbox
pip install --upgrade canvas-toolbox
```

### Option 3: Stay on v2.x

If you can't install Rust:

```bash
# Pin to v2.x (Python fallback still works)
pip install 'canvas-toolbox>=2.0,<3.0'
```

v2.x will receive security patches but no new features after v3.0 release.

## Rollback

If v3.x causes issues:

```bash
# Downgrade to v2.x
pip install 'canvas-toolbox==2.5.0'
```

## Breaking Changes

1. **Rust required** - tools error if Rust not installed
2. **Python implementations removed** - no fallback
3. **cb-init requires Rust** - step 5/9 is no longer optional

## Tools Affected

v3.0 ships with Rust implementations for:
- `fix_group_override_recalc.py` (40-120x faster)
- [Future tools as they're rewritten]

## Questions?

See docs/proposals/rust-migration-3-phase-strategy.md for full timeline.
File issues: https://github.com/chaz-clark/canvas-toolbox/issues
```

---

## Timeline Summary

### Phase 1: v2.0.0 (Month 0-3)
- **Status:** Rust optional, Python fallback available
- **cb-init:** `--with-rust` flag (opt-in)
- **Focus:** Gather adoption data, build more Rust tools
- **Exit criteria:** >50% Rust adoption, 2+ tools benefit

### Phase 2: v2.5.0 (Month 3-6)
- **Status:** Rust recommended, Python fallback discouraged
- **cb-init:** Rust prompts by default (can decline)
- **Focus:** Strong messaging toward Rust, monitor fallback usage
- **Exit criteria:** >75% Rust adoption, <10% fallback usage

### Phase 3: v3.0.0 (Month 6-12)
- **Status:** Rust required, Python fallback removed
- **cb-init:** Rust installation is mandatory (can't proceed without it)
- **Focus:** Clean up dual implementations, full Rust stack
- **Exit criteria:** Stable Rust-only codebase

---

## Maintenance Burden by Phase

### Phase 1 (Dual Implementation)
**Effort per tool:** ~2x (maintain Python + Rust)
**Mitigations:**
- Only critical bug fixes in Python version
- New features can be Rust-only
- Clear docs: "For best experience, use Rust"

**Estimated overhead:** +30% maintenance time for affected tools

### Phase 2 (Rust Default)
**Effort per tool:** ~1.5x (Rust is primary, Python is minimal maintenance)
**Mitigations:**
- Python fallback is frozen (security patches only)
- All new development in Rust
- Fewer Python tests needed

**Estimated overhead:** +15% maintenance time

### Phase 3 (Rust Only)
**Effort per tool:** 1x (single implementation)
**Benefits:**
- No dual maintenance
- Cleaner codebase
- Faster CI (only Rust builds)
- Better performance for all users

**Estimated overhead:** 0% (back to baseline)

---

## Testing Strategy

### Phase 1 & 2: Dual Testing

```python
# tests/test_fix_override_recalc.py
import pytest

def test_python_implementation():
    """Test Python fallback directly."""
    from _fix_group_override_recalc_python import main
    # Test cases...

def test_rust_implementation():
    """Test Rust wrapper directly."""
    from _fix_group_override_recalc_rust import main
    # Test cases...

def test_dispatcher_logic():
    """Test runtime dispatcher chooses correct impl."""
    # Mock rust binary presence/absence
    # Verify correct implementation is called

@pytest.mark.parametrize("implementation", ["python", "rust"])
def test_feature_parity(implementation):
    """Verify both implementations have same behavior."""
    # Run same test cases against both
    # Assert outputs match
```

### Phase 3: Rust-Only Testing

```python
# tests/test_fix_override_recalc.py
def test_rust_implementation():
    """Test Rust implementation (only version in v3.x)."""
    # Test cases for Rust binary
    # No Python version to test

def test_error_when_rust_missing():
    """Verify helpful error when Rust binary not found."""
    # Remove rust binary temporarily
    # Run tool
    # Assert clear error message with cb-upgrade-rust hint
```

---

## Rollout Communication

### v2.0.0 Announcement
```
🚀 canvas-toolbox v2.0.0 - Rust Support (Optional)

NEW: High-performance Rust implementations for API-heavy operations.

• fix_group_override_recalc: 40-120x faster (5-10 min → 5-15 sec)
• Install Rust: cb-init --with-rust (~600MB, one-time)
• Python fallback: Works without Rust (slower for large courses)

Try it: cb-init --with-rust
Read more: docs/proposals/rust-migration-3-phase-strategy.md
```

### v2.5.0 Announcement
```
⚡ canvas-toolbox v2.5.0 - Rust Now Recommended

Rust is now the default for new installations.

• 60% of users already using Rust
• 10-100x performance improvement proven
• Python fallback still available (discouraged)

Upgrade: cb-init --with-rust (if you haven't already)
Stay on Python: Continue using v2.x (works but slower)

Next: v3.0 will require Rust (6 months from now)
```

### v3.0.0 Announcement
```
🎯 canvas-toolbox v3.0.0 - Rust Required

BREAKING: Rust is now required (Python fallback removed).

• 80% of users already running Rust
• Cleaner codebase, faster development
• Better performance for everyone

Upgrade guide: docs/UPGRADING.md
Check readiness: cb-upgrade-rust
Questions: File an issue or see migration docs
```

---

## Risk Mitigation

### Risk: Users can't install Rust
**Mitigation:**
- Phase 1-2: Python fallback works (6-12 months)
- Clear documentation for restricted environments
- Option to stay on v2.x indefinitely

### Risk: Rust builds fail on exotic platforms
**Mitigation:**
- Test on ubuntu/macos/windows before release
- Provide pre-built binaries for common platforms
- Document manual build process for edge cases

### Risk: Maintenance burden too high in Phase 1-2
**Mitigation:**
- Freeze Python version (security only, no features)
- Focus all dev effort on Rust
- Shorten Phase 1-2 if burden becomes excessive

### Risk: Adoption slower than expected
**Mitigation:**
- Don't force Phase 3 until >75% adoption
- Keep Phase 2 running longer if needed
- Option to abandon and stay Python-only (abort mission)

---

## Success Metrics

Track monthly:
1. **Rust installation rate:** % of cb-init runs with `--with-rust`
2. **Runtime path usage:** % of tool executions using Rust vs Python
3. **Performance satisfaction:** User complaints about slowness
4. **Build success rate:** % of Rust builds that succeed
5. **Issue volume:** Rust-related bugs vs Python-related bugs

**Dashboard (hypothetical):**
```
Month 1:  Rust: 15% | Python: 85% | Issues: 2 (Rust build)
Month 2:  Rust: 30% | Python: 70% | Issues: 1 (Python slowness)
Month 3:  Rust: 50% | Python: 50% | Issues: 0
→ PROCEED TO PHASE 2

Month 4:  Rust: 65% | Python: 35% | Issues: 1 (Rust deprecation warning)
Month 5:  Rust: 75% | Python: 25% | Issues: 0
Month 6:  Rust: 80% | Python: 20% | Issues: 1 (request for v3.0)
→ PROCEED TO PHASE 3

Month 7:  Rust: 100% | Python: 0% (v3.0 released)
```

---

## Decision Log

### Decision 1: Option C Approved (2026-07-06)
- 3-phase migration over 6-12 months
- v2.x = Rust optional, v3.x = Rust required
- Dual implementation maintained during transition

### Decision 2: [TBD] Phase 1 → Phase 2 Gate (Month 3)
Based on metrics:
- Rust adoption: __%
- Python fallback complaints: __
- Additional Rust tools: __

### Decision 3: [TBD] Phase 2 → Phase 3 Gate (Month 6)
Based on metrics:
- Rust adoption: __%
- Python fallback usage: __%
- Rust stability: __

---

## Open Questions for Tomorrow

1. **Phase 1 feature parity:** Do we maintain full feature parity, or let Python be MVP?
2. **Async Python:** Worth trying asyncio rewrite to improve fallback before committing?
3. **Pre-built binaries:** Should we ship pre-compiled Rust binaries to avoid build step?
4. **Windows story:** Manual install only, or invest in PowerShell automation?
5. **Version timing:** Start Phase 1 immediately, or wait for 2-3 more Rust candidates?

---

## Next Steps (Morning 2026-07-07)

1. Review this strategy document
2. Answer open questions
3. Implement Phase 1:
   - Merge PR #136 with dispatcher pattern
   - Add `--with-rust` flag to cb-init
   - Update README with Rust optional documentation
   - Set up metrics tracking (if possible)
4. Start identifying next Rust candidates (canvas_sync, engagement_audit)
5. Set 3-month review date to evaluate Phase 1 → Phase 2

**Estimated time:** 3-4 hours for Phase 1 implementation

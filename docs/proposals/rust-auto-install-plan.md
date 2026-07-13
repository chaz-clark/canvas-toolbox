# Rust Auto-Install Plan for cb-init

**Context:** PR #136 adds Rust implementation of `fix_group_override_recalc` for 10-100x speedup. Need to add Rust auto-install to cb-init.

**Date:** 2026-07-06
**For review:** Morning 2026-07-07

---

## Proposed Implementation

### New Step 5: Install Rust & Build Binaries

Insert between current Step 4 (uv sync) and Step 5 (Playwright), shifting all subsequent steps +1.

```python
def step_5_install_rust(*, auto_yes: bool, check_only: bool) -> bool:
    """Install Rust via rustup, then build canvas-toolbox Rust binaries."""

    # Check if already installed
    if is_rust_installed():
        # Rust present - verify binaries are built
        if are_all_rust_binaries_built():
            print("Step 5/9: ✓ Rust + binaries already built — skipping.")
            return True
        else:
            # Rust installed but binaries missing - just build
            print("Step 5/9: ✓ Rust installed — building binaries...")
            return build_rust_binaries(check_only)

    # Windows - manual install required (same as uv)
    if platform.system() == "Windows":
        print("Step 5/9: Rust not installed. On Windows, install manually:")
        print("           Download rustup-init.exe from https://rustup.rs/")
        print("         Then re-run cb-init.")
        return False

    # Check mode - show what would happen
    if check_only:
        print("Step 5/9: would install Rust via rustup (~500MB, 2-5 min).")
        print("          then build Rust binaries (~1 min).")
        return False

    # Prompt for install
    if not prompt_y_n(
        "Step 5/9: Rust not installed. Install via rustup (~500MB, 2-5 min)? "
        "Enables 10-100x speedup for large courses.",
        auto_yes=auto_yes,
    ):
        print("  ⚠ Skipped. High-performance tools will use Python fallback (slower).")
        return True  # non-fatal - Python fallback exists

    # Install Rust
    print("  Installing Rust toolchain (~500MB, 2-5 min)...")
    if not run_subprocess(
        ["sh", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"],
        timeout=600
    ):
        print("  ✗ Rust installation failed.")
        return False

    # Check if on PATH (might need shell restart)
    if not is_rust_installed():
        print("  ✓ Rust installed but not yet on this shell's PATH.")
        print("    Open a new terminal (or source ~/.cargo/env),")
        print("    then re-run cb-init to build binaries.")
        return False

    print("  ✓ Rust installed.")

    # Build binaries
    return build_rust_binaries(check_only=False)

def build_rust_binaries(check_only: bool) -> bool:
    """Build all Rust binaries in lib/tools/*/src/"""
    rust_projects = [
        REPO_ROOT / "lib" / "tools" / "fix_override_recalc_rs"
    ]

    for project_dir in rust_projects:
        if not project_dir.exists():
            continue

        project_name = project_dir.name.replace("_rs", "")
        print(f"  Building {project_name}...")

        if not run_subprocess(
            ["cargo", "build", "--release"],
            cwd=project_dir,
            timeout=300
        ):
            print(f"  ⚠ {project_name} build failed (will use Python fallback)")
            # Don't fail - non-fatal

    print("  ✓ Rust binaries built.")
    return True
```

---

## Issues to Check

### 1. **Shell Restart Detection**
**Problem:** Rust adds `~/.cargo/bin` to PATH via shell RC files. Current shell doesn't pick it up.

**Current uv handling:**
```python
if not is_uv_installed():
    print("  ✓ uv installed but not yet on this shell's PATH.")
    print("    Open a new terminal (or `source ~/.zshrc` / `~/.bashrc`),")
    print("    then re-run cb-init.")
    return False
```

**Proposed Rust handling:** Same pattern - detect if not on PATH after install, tell user to restart shell.

**Edge case:** What if user runs `source ~/.cargo/env` in same shell? Works for uv, should work for Rust.

**Action:** Test manually on fresh macOS/Linux install.

---

### 2. **Windows Manual Install UX**
**Problem:** Windows doesn't support curl-pipe-sh. Both uv and Rust require manual `.exe` installer.

**Current uv handling:**
```python
if platform.system() == "Windows":
    print("Step 1/8: uv not on PATH. On Windows, install manually:")
    print("           irm https://astral.sh/uv/install.ps1 | iex")
    return False
```

**Proposed Rust handling:**
```python
if platform.system() == "Windows":
    print("Step 5/9: Rust not installed. On Windows, install manually:")
    print("           Download rustup-init.exe from https://rustup.rs/")
    return False
```

**Question:** Should we support PowerShell auto-install like uv does?
```powershell
irm https://win.rustup.rs/x86_64 | iex
```

**Decision needed:** Manual only (safer), or add PowerShell option?

---

### 3. **Cargo Build Failures**
**Problem:** `cargo build --release` can fail for many reasons:
- Missing system dependencies (OpenSSL on Linux)
- Outdated Rust version (edition2021 requires Rust 1.56+)
- Disk space issues
- Network issues fetching crates

**Current handling in PR #136:**
```python
if not rust_bin.exists():
    print(f"ERROR: Rust binary not found at {rust_bin}\n"
          f"Build it first:\n"
          f"  cd {script_dir / 'fix_override_recalc_rs'} && cargo build --release")
    return 2
```

**Proposed cb-init handling:**
- Make build failures **non-fatal** (like Playwright)
- Print helpful error message
- Document Python fallback exists
- Tool gracefully falls back at runtime

**Question:** Should we cache successful build state to avoid re-attempting failed builds?

---

### 4. **Multiple Rust Projects**
**Current state:** Only one Rust project (`fix_override_recalc_rs`)

**Future state:** More Rust rewrites coming (grader_fetch, canvas_sync, etc.)

**Proposed solution:**
```python
def find_rust_projects() -> list[Path]:
    """Find all Rust projects under lib/tools/*_rs/"""
    rust_dirs = []
    tools_dir = REPO_ROOT / "lib" / "tools"
    for item in tools_dir.iterdir():
        if item.is_dir() and item.name.endswith("_rs"):
            cargo_toml = item / "Cargo.toml"
            if cargo_toml.exists():
                rust_dirs.append(item)
    return rust_dirs
```

**Build strategy:**
- Sequential builds (simpler, easier to debug)
- OR parallel builds (faster but harder to debug failures)

**Decision needed:** Start sequential, parallelize later if it's a bottleneck?

---

### 5. **CI/CD Impact**
**Current CI:** `smoke-and-unit` job compiles all Python but doesn't build Rust

**Proposed CI changes:**
1. Install Rust in CI (via rustup)
2. Cache Rust toolchain (~500MB) between runs
3. Build all Rust binaries in CI
4. Run Rust binaries in smoke tests

**GitHub Actions example:**
```yaml
- name: Install Rust
  uses: dtolnay/rust-toolchain@stable

- name: Cache Rust
  uses: actions/cache@v3
  with:
    path: |
      ~/.cargo/bin/
      ~/.cargo/registry/index/
      ~/.cargo/registry/cache/
      ~/.cargo/git/db/
      target/
    key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}

- name: Build Rust binaries
  run: |
    cd lib/tools/fix_override_recalc_rs && cargo build --release
```

**Time impact:**
- First run: +2-3 minutes (install + build)
- Cached runs: +30 seconds (incremental build)

**Decision needed:** Add to existing smoke-and-unit job or create separate rust-build job?

---

### 6. **Disk Space Requirements**
**Rust toolchain:** ~500MB
**Cargo cache:** ~50-200MB (grows with dependencies)
**Build artifacts:** ~10-50MB per project (release builds)

**Total:** ~600-750MB

**Question:** Should we add disk space check before install?

**Comparison:**
- uv: ~20MB
- Python 3.14: ~50MB
- Playwright Chromium: ~92MB
- Rust: ~600MB

**Decision needed:** Worth the space for 10-100x speedup?

---

### 7. **Version Management**
**Rust versions:** rustup handles this (installs stable by default)

**Rust edition in Cargo.toml:**
```toml
[package]
edition = "2021"  # Requires Rust 1.56+ (Oct 2021)
```

**Current PR #136:** Uses edition 2021 (well-supported, stable since 2021)

**Question:** Should cb-init verify minimum Rust version (1.56+)?

**Proposed check:**
```python
def get_rust_version() -> str:
    try:
        r = subprocess.run(["rustc", "--version"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            # Output: "rustc 1.96.1 (stable)"
            return r.stdout.strip().split()[1]
    except:
        return ""
    return ""

def is_rust_version_compatible() -> bool:
    version = get_rust_version()
    if not version:
        return False
    # Parse "1.96.1" -> (1, 96, 1)
    major, minor, patch = map(int, version.split('.'))
    return (major, minor) >= (1, 56)  # Minimum for edition2021
```

---

### 8. **Network Failures**
**Rust install:** Downloads ~500MB from `https://sh.rustup.rs`
**Cargo build:** Downloads crates from `crates.io`

**Failure modes:**
- Firewall blocks rustup.rs
- Firewall blocks crates.io
- Slow/unreliable network (timeout)
- Partial download corruption

**Current handling:** 10-minute timeout on install, 5-minute timeout on build

**Question:** Should we add retry logic? Or just fail fast and tell user to retry manually?

---

### 9. **Idempotency**
**Key requirement:** Re-running cb-init should be fast no-op

**Proposed flow:**
```
First run:  Install Rust + build binaries (~6 min)
Second run: "✓ Rust + binaries already built — skipping" (~0 sec)
```

**Checks needed:**
1. `is_rust_installed()` - check for `cargo` on PATH
2. `are_all_rust_binaries_built()` - check for `target/release/<binary>` for each project
3. If Rust installed but binaries missing → just build (don't re-install)

---

### 10. **User Experience Flow**
**Scenario 1: Fresh install (no Rust)**
```
Step 5/9: Rust not installed. Install via rustup (~500MB, 2-5 min)?
          Enables 10-100x speedup for large courses. [Y/n] y
  Installing Rust toolchain (~500MB, 2-5 min)...
  ✓ Rust installed.
  Building fix-override-recalc...
  ✓ Rust binaries built.
```

**Scenario 2: Rust installed, binaries missing**
```
Step 5/9: ✓ Rust installed — building binaries...
  Building fix-override-recalc...
  ✓ Rust binaries built.
```

**Scenario 3: Everything already done**
```
Step 5/9: ✓ Rust + binaries already built — skipping.
```

**Scenario 4: User declines install**
```
Step 5/9: Rust not installed. Install via rustup (~500MB, 2-5 min)? [Y/n] n
  ⚠ Skipped. High-performance tools will use Python fallback (slower).
```

**Question:** Does this flow feel right? Any confusing states?

---

### 11. **Documentation Updates Needed**

**Files to update:**
1. `README.md` - mention Rust as optional but recommended
2. `AGENTS.md` - update Common Tasks if needed
3. `docs/UPGRADING.md` - note for existing users (one-time Rust install)
4. `.github/workflows/ci.yml` - add Rust installation + caching
5. `lib/tools/fix_override_recalc_rs/README.md` - note cb-init handles build

**Example README addition:**
```markdown
### Performance note

Some tools have Rust implementations for 10-100x speedup on large courses:
- `fix_group_override_recalc.py` - override recalculation

cb-init will prompt to install Rust (~500MB, one-time). If you decline,
Python fallbacks work but are slower for courses with 100+ assignments.
```

---

### 12. **Rollback Plan**
**If Rust auto-install causes problems:**

**Option A: Make it opt-in via flag**
```
cb-init --skip-rust    # Don't install Rust
cb-init --with-rust    # Explicitly install Rust
```

**Option B: Revert to manual-only**
- Remove auto-install from cb-init
- Update README with manual install instructions
- Keep Python fallbacks working

**Option C: Add escape hatch**
```
# If Rust install fails repeatedly
export CANVAS_TOOLBOX_NO_RUST=1
cb-init  # Will skip Rust entirely
```

**Decision needed:** Which rollback feels safest?

---

## Testing Plan

### Manual Testing Needed (Morning 2026-07-07)

1. **Fresh macOS install** (no Rust)
   - Run cb-init, accept Rust install
   - Verify binary builds
   - Re-run cb-init (should skip)

2. **macOS with Rust already installed**
   - Run cb-init
   - Should detect Rust, just build binaries

3. **macOS, decline Rust install**
   - Run cb-init, decline at prompt
   - Verify Python fallback works
   - Try running fix_group_override_recalc.py (should show helpful error)

4. **Windows** (if possible)
   - Should show manual install instructions
   - After manual install, verify cb-init builds binaries

5. **Simulated failures**
   - Kill network during Rust install (test timeout)
   - Corrupt Cargo.toml (test build failure handling)
   - Fill disk (test space issues)

### CI Testing

1. Add Rust to CI workflow
2. Verify builds pass on all platforms (ubuntu-latest, macos-latest, windows-latest)
3. Check caching works (second run should be faster)

---

## Open Questions for Morning Review

1. **Windows PowerShell auto-install?** Manual only, or add `irm | iex` support?
2. **Build parallelization?** Sequential vs parallel for multiple Rust projects?
3. **CI strategy?** Separate job or add to smoke-and-unit?
4. **Disk space pre-check?** Worth adding before ~600MB install?
5. **Rust version check?** Verify 1.56+ or trust rustup installs compatible version?
6. **Network retry logic?** Fast-fail or retry on timeout?
7. **Rollback mechanism?** Flag-based opt-out or environment variable?

---

## Implementation Checklist

- [ ] Add `is_rust_installed()` function
- [ ] Add `are_all_rust_binaries_built()` function
- [ ] Add `find_rust_projects()` function
- [ ] Add `build_rust_binaries()` function
- [ ] Add `step_5_install_rust()` function
- [ ] Update step numbering (5→6, 6→7, 7→8, 8→9)
- [ ] Update docstring (8 steps → 9 steps)
- [ ] Update CI workflow with Rust
- [ ] Update README.md
- [ ] Update AGENTS.md if needed
- [ ] Update docs/UPGRADING.md
- [ ] Test on fresh macOS (no Rust)
- [ ] Test on macOS with Rust
- [ ] Test Windows manual flow
- [ ] Test decline-install path
- [ ] Test Python fallback works
- [ ] Merge PR #136 first (prerequisite)
- [ ] Create PR for cb-init changes
- [ ] Update version number in CHANGELOG

---

## Timeline

**Tonight (2026-07-06):**
- ✓ Created this plan
- ✓ Identified open questions
- ✓ Outlined testing needed

**Morning (2026-07-07):**
- Review this plan
- Decide on open questions
- Manual testing on macOS
- Implement cb-init changes
- Update CI
- Update docs
- Create PR

**Estimated time:** 2-3 hours (implementation + testing + docs)

---

## Risk Assessment

**Low risk:**
- Non-fatal step (can skip)
- Python fallback exists
- Well-tested pattern (same as uv)
- Clear rollback path

**Medium risk:**
- ~600MB download (some users on slow connections)
- 5-10 min total time (install + build)
- Windows manual install friction

**Mitigation:**
- Make skippable (non-fatal)
- Clear progress messages
- Document Python fallback
- Add --skip-rust flag if needed

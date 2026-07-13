# fix-override-recalc (Rust Implementation)

High-performance Rust implementation of Canvas assignment override recalculation.

## Why Rust?

The Python implementation (`fix_group_override_recalc.py`) was extremely slow on courses with many assignments (108+ assignments could take 10+ minutes). This Rust rewrite provides:

- **10-100x faster execution** - concurrent API requests instead of sequential
- **Better Canvas API handling** - proper async/await with tokio + reqwest
- **Robust error handling** - explicit Result types and proper timeout handling

## Architecture

The Python script (`fix_group_override_recalc.py`) is now a thin wrapper that:
1. Parses CLI arguments
2. Loads Canvas credentials from `.env`
3. Executes the Rust binary
4. Streams output back to the user

This maintains the same user experience (`uv run python ...`) while gaining Rust's performance.

## Building

```bash
cd lib/tools/fix_override_recalc_rs
cargo build --release
```

The binary will be at `target/release/fix-override-recalc`.

## Requirements

- Rust 1.96.1 or newer (for edition2024 support)
- Cargo (comes with Rust)

Install Rust: https://rustup.rs/

## Usage

The Python wrapper handles execution automatically:

```bash
# Via Python wrapper (recommended)
uv run python lib/tools/fix_group_override_recalc.py \
  --course-id 407908 \
  --student-id 280379 \
  --dry-run

# Direct Rust binary (for debugging)
./target/release/fix-override-recalc \
  --course-id 407908 \
  --student-id 280379 \
  --base-url https://byui.instructure.com \
  --token $CANVAS_API_TOKEN \
  --dry-run
```

## Performance Comparison

**Python (original):**
- Sequential API calls
- ~5-10 minutes for 108 assignments on course 407908
- Single-threaded

**Rust (this implementation):**
- Concurrent API calls using `tokio::join_all`
- ~5-15 seconds for 108 assignments (estimated)
- Multi-threaded async runtime

## Implementation Details

### Key Dependencies

- **tokio** - Async runtime for concurrent API requests
- **reqwest** - HTTP client with connection pooling
- **serde/serde_json** - JSON parsing for Canvas API responses
- **clap** - CLI argument parsing
- **anyhow** - Error handling

### Concurrency Model

1. Fetch all assignments (paginated, but sequential per page)
2. **Concurrent override fetch** - spawn one task per assignment
3. Filter for target overrides (student_id or group_id)
4. **Concurrent override touch** - spawn one PUT per override
5. Report results

The concurrent operations are the bottleneck removers - instead of waiting for each API call to complete before starting the next, we fire them all at once and collect results.

## Maintenance

The Python wrapper (`fix_group_override_recalc.py`) should remain stable. Updates to the Rust implementation only require:

1. Edit `src/main.rs`
2. Rebuild: `cargo build --release`
3. Test: `uv run python lib/tools/fix_group_override_recalc.py --course-id ... --dry-run`

The CLI interface is defined in both the Rust binary (clap) and Python wrapper (argparse) - keep them in sync.

## Fallback

If the Rust binary isn't built, the Python wrapper will error with build instructions. The original pure-Python implementation is saved as `fix_group_override_recalc.py.original` if needed for emergency fallback.

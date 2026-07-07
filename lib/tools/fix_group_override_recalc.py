#!/usr/bin/env python3
"""
fix_group_override_recalc.py — Force Canvas to recalculate assignment overrides
when they're not applying correctly.

WHY THIS EXISTS
  Canvas doesn't always automatically trigger SubmissionLifecycleManager.recompute_users_for_course
  when overrides are created or modified via the REST API.

  Two common scenarios:

  1. **Group membership changes via API**: Remove/re-add a user to a Canvas group via REST API
     (DELETE /groups/:id/memberships/:membership_id then POST /groups/:id/memberships)
     → Assignment overrides for that group don't apply to the user

  2. **Student accommodations via API**: Apply individual student overrides via accommodation tools
     (student_late_accommodation.py, student_quiz_time_extension.py, apply_sas_accommodations.py)
     → Override is created but sometimes doesn't take effect immediately

  The Canvas UI handles recalculation automatically, but bare API calls don't always trigger it.

THE FIX
  "Touch" the assignment override by performing a no-op PUT (re-set the same values).
  This triggers Canvas's assignment_override_updated event and forces recalculation.

  For a given group OR student:
  1. Find all assignments that have overrides targeting the group/student
  2. For each override, perform a no-op PUT (re-set the same values)
  3. This triggers Canvas's internal recalculation logic
  4. The user can now submit

USAGE
  # Fix overrides for a specific group
  uv run python lib/tools/fix_group_override_recalc.py \\
    --course-id 407908 \\
    --group-id 1885662

  # Fix overrides for a specific student
  uv run python lib/tools/fix_group_override_recalc.py \\
    --course-id 407908 \\
    --student-id 280379

  # Check what overrides would be updated (dry run)
  uv run python lib/tools/fix_group_override_recalc.py \\
    --course-id 407908 \\
    --student-id 280379 \\
    --dry-run

REQUIRES in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL

WHEN TO USE THIS
  Use this tool as a "force refresh" when:
  - An accommodation was applied but the student still can't submit
  - A group override exists but members can't access the assignment
  - You changed group membership via API and overrides aren't working
  - Any scenario where an override should work but doesn't

  This is a safe troubleshooting tool - it only touches existing overrides,
  never creates new ones, and preserves all values.

INTEGRATION WITH ACCOMMODATION TOOLS
  This tool is designed to work AFTER accommodation tools have been used:
  - student_late_accommodation.py
  - student_quiz_time_extension.py
  - apply_sas_accommodations.py

  If accommodations are applied but still not working, run this tool to
  force Canvas to recalculate.

IMPLEMENTATION NOTE (v1.5.1+)
  This tool uses a dispatcher pattern to choose between Rust and Python implementations:

  **Rust (recommended)**: 10-100x faster (5-10 min → 5-15 sec for 100+ assignments)
    - Uses concurrent HTTP requests (tokio + reqwest)
    - Install via: cb-init --with-rust
    - Or manually: cd lib/tools/fix_override_recalc_rs && cargo build --release

  **Python (fallback)**: Automatic fallback when Rust binary not available
    - Sequential HTTP requests (slower but reliable)
    - No additional setup required
    - Same functionality, just takes longer

  The tool automatically detects which implementation is available and uses the
  fastest one. If Rust binary is missing, it warns you and falls back to Python
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    # Fallback if _env_loader isn't available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Force Canvas to recalculate assignment overrides",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Mutually exclusive: group OR student
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--group-id", type=int, help="Canvas group ID")
    target.add_argument("--student-id", type=int, help="Canvas student user ID")

    ap.add_argument("--course-id", type=int, required=True, help="Canvas course ID")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )

    args = ap.parse_args()

    # Get env vars
    base_url = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base_url and not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"

    token = os.environ.get("CANVAS_API_TOKEN", "")

    if not base_url or not token:
        print(
            "ERROR: CANVAS_BASE_URL and CANVAS_API_TOKEN must be set in .env",
            file=sys.stderr,
        )
        return 2

    # Find the Rust binary
    script_dir = Path(__file__).parent
    rust_bin = script_dir / "fix_override_recalc_rs" / "target" / "release" / "fix-override-recalc"

    if not rust_bin.exists():
        # Rust binary not found - fall back to Python implementation
        print(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            file=sys.stderr,
        )
        print("⚠ Rust binary not found — falling back to Python", file=sys.stderr)
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", file=sys.stderr)
        print(file=sys.stderr)
        print("Python fallback is SLOW for large courses (5-10 min for 100+ assignments).", file=sys.stderr)
        print("For 10-100x speedup, install Rust:", file=sys.stderr)
        print("  cb-init --with-rust", file=sys.stderr)
        print(file=sys.stderr)
        print("Or manually:", file=sys.stderr)
        print(f"  cd {script_dir / 'fix_override_recalc_rs'} && cargo build --release", file=sys.stderr)
        print(file=sys.stderr)
        print("Proceeding with Python fallback...", file=sys.stderr)
        print(file=sys.stderr)

        # Import and run Python fallback
        try:
            from _fix_group_override_recalc_python import run_python_fallback
        except ImportError as e:
            print(f"ERROR: Failed to import Python fallback: {e}", file=sys.stderr)
            return 2

        return run_python_fallback(
            course_id=args.course_id,
            base_url=base_url,
            token=token,
            student_id=args.student_id,
            group_id=args.group_id,
            dry_run=args.dry_run,
            quiet=False,
        )

    # Build command args
    cmd = [
        str(rust_bin),
        "--course-id", str(args.course_id),
        "--base-url", base_url,
        "--token", token,
    ]

    if args.group_id:
        cmd.extend(["--group-id", str(args.group_id)])
    elif args.student_id:
        cmd.extend(["--student-id", str(args.student_id)])

    if args.dry_run:
        cmd.append("--dry-run")

    # Execute Rust binary and stream output
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except FileNotFoundError:
        print(
            f"ERROR: Failed to execute Rust binary at {rust_bin}",
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())

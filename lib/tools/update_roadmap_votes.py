#!/usr/bin/env python3
"""
Update ROADMAP.md with current vote counts from the voting worker.

Usage:
    # Show current vote counts (no file changes)
    uv run python lib/tools/update_roadmap_votes.py --show

    # Dry-run (show what would be updated)
    uv run python lib/tools/update_roadmap_votes.py

    # Apply changes to ROADMAP.md
    uv run python lib/tools/update_roadmap_votes.py --apply

This script fetches vote counts from the Cloudflare Worker and updates feature
names in docs/ROADMAP.md to include vote counts like "Feature Name (42 votes)".
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict

try:
    import requests
except ImportError:
    print("Error: requests library not found. Install with: uv pip install requests")
    sys.exit(1)


# Voting endpoint (set after deployment)
_ENDPOINT: str | None = "https://canvas-toolbox-vote.tylerchaz5.workers.dev/votes"

# Feature ID to human-readable name mapping (must match vote_feature.py)
_FEATURES: Dict[str, str] = {
    # Phase 1: High-Value, Low-Complexity
    "grade-forecast": "Student grade forecast",
    "engagement-early-warning": "Student engagement early warning system",
    "bulk-reminder": "Bulk assignment reminder sender",
    "group-override-manager": "Group override manager",
    # Phase 2: Medium-Value, Moderate-Complexity
    "assignment-performance-analyzer": "Assignment performance analyzer",
    "accommodation-notifier": "Accommodation notification tool",
    "weekly-announcements": "Weekly announcement publisher",
    "ta-grading-status": "TA grading status & voice coaching",
    "course-restore": "Course restoration from local repo",
    # Phase 3: Nice-to-Have
    "module-scheduler": "Module release scheduler",
    "rubric-library": "Rubric template library",
    "grade-audit-trail": "Grading audit trail exporter",
    "random-groups": "Random group generator",
}

_ROADMAP_PATH = Path("docs/ROADMAP.md")


def fetch_votes() -> Dict[str, int]:
    """Fetch vote counts from Cloudflare Worker."""
    if not _ENDPOINT:
        print("Voting endpoint not yet deployed (maintainer only).")
        return {}

    try:
        response = requests.get(_ENDPOINT, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching votes: {e}")
        return {}


def show_votes():
    """Display current vote counts."""
    votes = fetch_votes()

    if not votes:
        print("No votes recorded yet (or endpoint not deployed).")
        return

    print("Current vote counts:\n")
    for feature_id, count in sorted(votes.items(), key=lambda x: x[1], reverse=True):
        feature_name = _FEATURES.get(feature_id, feature_id)
        vote_str = f"vote{'s' if count != 1 else ''}"
        print(f"  {count:3} {vote_str:5} — {feature_name} ({feature_id})")


def update_roadmap(dry_run: bool = True):
    """Update ROADMAP.md with vote counts."""
    if not _ROADMAP_PATH.exists():
        print(f"Error: {_ROADMAP_PATH} not found")
        sys.exit(1)

    votes = fetch_votes()

    if not votes:
        print("No votes to update (endpoint not deployed or no votes yet).")
        return

    # Read roadmap
    content = _ROADMAP_PATH.read_text()
    original_content = content

    # Update feature names with vote counts
    # Pattern: "**FeatureName**" → "**FeatureName (N votes)**"
    for feature_id, feature_name in _FEATURES.items():
        count = votes.get(feature_id, 0)

        if count == 0:
            continue  # Don't add "(0 votes)" noise

        vote_str = f"vote{'s' if count != 1 else ''}"

        # Remove existing vote count if present
        pattern_with_votes = re.escape(f"**{feature_name}") + r" \(\d+ votes?\)\*\*"
        content = re.sub(pattern_with_votes, f"**{feature_name}**", content)

        # Add new vote count
        pattern_plain = re.escape(f"**{feature_name}**")
        replacement = f"**{feature_name} ({count} {vote_str})**"
        content = re.sub(pattern_plain, replacement, content)

    # Show diff summary
    if content == original_content:
        print("No changes needed (vote counts already up-to-date).")
        return

    changes = sum(1 for a, b in zip(original_content.splitlines(), content.splitlines()) if a != b)
    print(f"Would update {changes} lines in {_ROADMAP_PATH}")

    if dry_run:
        print("\n[DRY-RUN] Use --apply to write changes.")
        return

    # Write changes
    _ROADMAP_PATH.write_text(content)
    print(f"✓ Updated {_ROADMAP_PATH}")


def main():
    parser = argparse.ArgumentParser(
        description="Update ROADMAP.md with vote counts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show current vote counts (no file changes)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to ROADMAP.md (default is dry-run)",
    )

    args = parser.parse_args()

    if args.show:
        show_votes()
    else:
        update_roadmap(dry_run=not args.apply)


if __name__ == "__main__":
    main()

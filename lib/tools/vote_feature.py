#!/usr/bin/env python3
"""
Vote for canvas-toolbox roadmap features.

Usage:
    # List all roadmap features with current vote counts
    uv run python lib/tools/vote_feature.py --list

    # Vote for a feature by name (fuzzy match)
    uv run python lib/tools/vote_feature.py --feature "student grade forecast"

    # Vote using feature ID (recommended — unambiguous)
    uv run python lib/tools/vote_feature.py --feature-id grade-forecast

    # Dry-run (show what would be sent)
    uv run python lib/tools/vote_feature.py --feature-id grade-forecast --dry-run

Voting is anonymous (uses hashed machine ID + username for deduplication).
Votes are idempotent (voting again returns current count without duplication).
"""

import argparse
import hashlib
import json
import platform
import sys
import time
import uuid
from typing import Dict

try:
    import requests
except ImportError:
    print("Error: requests library not found. Install with: uv pip install requests")
    sys.exit(1)


# Voting endpoint (set after deployment)
_ENDPOINT: str | None = "https://canvas-toolbox-vote.tylerchaz5.workers.dev/vote"

# Feature ID to human-readable name mapping
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
    # Phase 3: Nice-to-Have
    "module-scheduler": "Module release scheduler",
    "rubric-library": "Rubric template library",
    "grade-audit-trail": "Grading audit trail exporter",
    "random-groups": "Random group generator",
}


def _get_user_hash() -> str:
    """
    Generate anonymous user hash for deduplication.
    Uses machine ID + username (hashed with SHA256).
    """
    try:
        # Try to get machine ID (varies by platform)
        machine_id = str(uuid.getnode())  # MAC address
    except Exception:
        machine_id = platform.node()  # Hostname fallback

    username = platform.node()  # Use hostname as proxy for username
    raw_identifier = f"{machine_id}:{username}"
    return hashlib.sha256(raw_identifier.encode()).hexdigest()


def _fuzzy_match_feature(query: str) -> str | None:
    """
    Fuzzy match feature name to feature ID.
    Returns feature_id if match found, None otherwise.
    """
    query_lower = query.lower().strip()

    # Exact ID match
    if query_lower in _FEATURES:
        return query_lower

    # Partial name match
    for feature_id, feature_name in _FEATURES.items():
        if query_lower in feature_name.lower():
            return feature_id

    return None


def list_features():
    """List all roadmap features with current vote counts."""
    if not _ENDPOINT:
        print("Voting endpoint not yet deployed (maintainer only).")
        print("\nRoadmap features:")
        for feature_id, feature_name in _FEATURES.items():
            print(f"  {feature_id:35} {feature_name}")
        return

    # Fetch vote counts
    try:
        votes_endpoint = _ENDPOINT.replace("/vote", "/votes")
        response = requests.get(votes_endpoint, timeout=10)
        response.raise_for_status()
        votes = response.json()
    except requests.RequestException as e:
        print(f"Error fetching vote counts: {e}")
        print("\nRoadmap features:")
        for feature_id, feature_name in _FEATURES.items():
            print(f"  {feature_id:35} {feature_name}")
        return

    print("Roadmap features (current vote counts):\n")
    for feature_id, feature_name in _FEATURES.items():
        count = votes.get(feature_id, 0)
        vote_str = f"({count} vote{'s' if count != 1 else ''})"
        print(f"  {feature_id:35} {feature_name:45} {vote_str}")


def vote(feature_id: str, dry_run: bool = False):
    """Vote for a feature."""
    if feature_id not in _FEATURES:
        print(f"Error: Unknown feature_id '{feature_id}'")
        print("\nValid feature IDs:")
        for fid in _FEATURES.keys():
            print(f"  {fid}")
        sys.exit(1)

    feature_name = _FEATURES[feature_id]
    user_hash = _get_user_hash()

    payload = {
        "feature_id": feature_id,
        "user_hash": user_hash,
        "source": "cli",
    }

    if dry_run:
        print(f"[DRY-RUN] Would vote for: {feature_name}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        return

    if not _ENDPOINT:
        print(f"Voting endpoint not yet deployed (maintainer only).")
        print(f"\nYou wanted to vote for: {feature_name} ({feature_id})")
        print("Once deployed, your vote will be recorded anonymously.")
        return

    print(f"Voting for: {feature_name}")

    try:
        start = time.time()
        response = requests.post(
            _ENDPOINT,
            json=payload,
            headers={"User-Agent": "canvas-toolbox-vote-cli/1.0"},
            timeout=10,
        )
        elapsed = time.time() - start
        response.raise_for_status()

        result = response.json()
        count = result.get("count", "?")
        print(f"✓ Vote recorded ({elapsed:.1f}s)")
        print(f"  Current votes for '{feature_name}': {count}")

    except requests.HTTPError as e:
        if e.response.status_code == 429:
            print("✗ Rate limit exceeded (max 10 votes per hour per IP)")
        elif e.response.status_code == 400:
            error_msg = e.response.json().get("error", "Bad request")
            print(f"✗ Invalid request: {error_msg}")
        else:
            print(f"✗ HTTP error: {e}")
        sys.exit(1)

    except requests.RequestException as e:
        print(f"✗ Network error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Vote for canvas-toolbox roadmap features",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all roadmap features with vote counts",
    )
    parser.add_argument(
        "--feature",
        type=str,
        help="Feature name (fuzzy match)",
    )
    parser.add_argument(
        "--feature-id",
        type=str,
        help="Feature ID (exact match, recommended)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be sent without posting",
    )

    args = parser.parse_args()

    if args.list:
        list_features()
        return

    if not args.feature and not args.feature_id:
        parser.print_help()
        sys.exit(1)

    # Resolve feature ID
    if args.feature_id:
        feature_id = args.feature_id
    else:
        feature_id = _fuzzy_match_feature(args.feature)
        if not feature_id:
            print(f"Error: No feature matching '{args.feature}'")
            print("\nUse --list to see all features, or --feature-id for exact match")
            sys.exit(1)

    vote(feature_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

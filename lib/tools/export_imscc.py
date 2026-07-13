#!/usr/bin/env python3
"""Export Canvas course as Common Cartridge (.imscc) file.

Usage:
    CANVAS_COURSE_ID=145706 uv run python lib/tools/export_imscc.py --output /tmp/course.imscc
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()


def export_course(course_id: str, output_path: Path, base_url: str, token: str) -> bool:
    """Export Canvas course as .imscc file.

    Args:
        course_id: Canvas course ID
        output_path: Where to save the .imscc file
        base_url: Canvas base URL
        token: Canvas API token

    Returns:
        True if successful, False otherwise
    """
    # Trigger export
    print(f"Requesting export for course {course_id}...")
    resp = requests.post(
        f"{base_url}/api/v1/courses/{course_id}/content_exports",
        headers={"Authorization": f"Bearer {token}"},
        json={"export_type": "common_cartridge"},
        timeout=30
    )

    if resp.status_code >= 400:
        print(f"Error: {resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        return False

    export = resp.json()
    export_id = export["id"]
    print(f"✓ Export started (ID: {export_id})")
    print(f"  Status: {export.get('workflow_state', 'unknown')}")

    # Poll for completion
    print("\nWaiting for export to complete...")
    for i in range(60):  # Wait up to 5 minutes
        time.sleep(5)

        resp = requests.get(
            f"{base_url}/api/v1/courses/{course_id}/content_exports/{export_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )

        export = resp.json()
        state = export.get("workflow_state", "unknown")

        print(f"  [{i*5}s] Status: {state}")

        if state == "exported":
            print("\n✓ Export complete!")
            download_url = export.get("attachment", {}).get("url", "N/A")

            # Download the file
            print("\nDownloading .imscc file...")
            resp = requests.get(download_url, timeout=300)

            output_path.write_bytes(resp.content)

            print(f"✓ Downloaded to: {output_path}")
            print(f"  Size: {len(resp.content):,} bytes")

            return True

        elif state == "failed":
            print(f"\n✗ Export failed", file=sys.stderr)
            return False

    print("\n⚠ Timeout waiting for export", file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export Canvas course as Common Cartridge (.imscc)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/course_export.imscc"),
        help="Output path for .imscc file (default: /tmp/course_export.imscc)"
    )

    args = parser.parse_args()

    # Get config
    course_id = os.environ.get("CANVAS_COURSE_ID")
    token = os.environ.get("CANVAS_TOKEN")
    base_url = os.environ.get("CANVAS_BASE_URL", "https://byui.instructure.com")

    if not course_id:
        print("ERROR: CANVAS_COURSE_ID environment variable required", file=sys.stderr)
        return 1

    if not token:
        print("ERROR: CANVAS_TOKEN not found in environment", file=sys.stderr)
        return 1

    # Export
    success = export_course(course_id, args.output, base_url, token)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

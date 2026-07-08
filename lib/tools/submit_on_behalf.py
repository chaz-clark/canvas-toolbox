#!/usr/bin/env python3
"""
submit_on_behalf.py — Submit assignment files on behalf of students via Canvas API.

THE SLACK/EMAIL SUBMISSION PROBLEM
  Students DM files via Slack or email them instead of submitting through Canvas:
  - "I couldn't figure out how to submit"
  - "The assignment was closed"
  - "I had technical issues"

  Result: instructor has files in Downloads/ or Slack, but they're not in Canvas.
  Manual fix: Open SpeedGrader, upload on behalf of each student (slow, tedious).

WHAT THIS TOOL DOES
  Automates the "submit on behalf of student" workflow via Canvas API:
  1. Upload file to Canvas (get file_id)
  2. POST submission with file_id and student user_id
  3. Canvas marks as submitted, triggers grading notifications
  4. Audit trail shows "submitted by instructor on behalf of student"

PII-FREE LOOKUP
  --deid-code S-95DBB6    looked up in grading/.deid_master.csv
  --user-id 123456        bare Canvas user_id (for testing)

USAGE — dry-run by default (use --apply to actually submit)
  # Preview: submit essay.pdf for student S-95DBB6 on assignment 12345
  uv run python lib/tools/submit_on_behalf.py \\
    --deid-code S-95DBB6 \\
    --assignment-id 12345 \\
    --file ~/Downloads/essay.pdf

  # Actually submit (triggers grading notification)
  uv run python lib/tools/submit_on_behalf.py \\
    --deid-code S-95DBB6 \\
    --assignment-id 12345 \\
    --file ~/Downloads/essay.pdf \\
    --apply

  # Submit with a comment
  uv run python lib/tools/submit_on_behalf.py \\
    --deid-code S-95DBB6 \\
    --assignment-id 12345 \\
    --file ~/Downloads/essay.pdf \\
    --comment "Submitted via Slack on student's behalf due to Canvas access issue" \\
    --apply

REQUIRES in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID

KNOWN LIMITATIONS
  Canvas "Submit on behalf of student" permission may be disabled at institutional level:
  - BYUI: API submissions blocked with 403 Forbidden (tested 2026-07-08)
  - File upload still works (returns file_id)
  - Workaround: Use uploaded file_id to manually attach in SpeedGrader
  - Some assignments return 400 Bad Request instead of 403 (different validation)

NOTIFICATIONS (when submission succeeds)
  This triggers Canvas's standard submission workflow:
  - Assignment appears in SpeedGrader "Needs Grading"
  - Shows in instructor To Do list
  - Student sees submission with "submitted by instructor" note
  - Timestamps show actual submission time
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import requests

try:
    from _env_loader import force_utf8_console
    force_utf8_console()
except ImportError:
    pass


_DEFAULT_MASTER = Path("grading/.deid_master.csv")
_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def resolve_deid_to_user_id(deid_code: str, master_path: Path = _DEFAULT_MASTER) -> int:
    """Look up Canvas user_id from deid_code.

    Reads ONLY the user_id column (sortable_name is never read).
    """
    if not master_path.exists():
        raise FileNotFoundError(
            f"deid master not found at {master_path}. "
            f"Build it first with: "
            f"uv run python lib/tools/build_deid_master.py"
        )
    target = deid_code.strip().upper()
    with master_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["deid_code"].strip().upper() == target:
                return int(row["user_id"])
    raise KeyError(
        f"deid_code {deid_code!r} not found in {master_path}. "
        f"Did you rebuild the master after a roster change?"
    )


# ---------------------------------------------------------------------------
# Canvas API
# ---------------------------------------------------------------------------

def upload_file_to_canvas(
    base_url: str,
    course_id: str,
    file_path: Path,
    token: str
) -> int:
    """Upload a file to Canvas and return the file_id.

    Canvas file upload is a 3-step process:
    1. POST to get upload URL and parameters
    2. POST file to upload URL
    3. Confirm upload (returns file object with ID)

    Returns:
        Canvas file_id (integer)
    """
    headers = {"Authorization": f"Bearer {token}"}

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Step 1: Request upload URL
    r = requests.post(
        f"{base_url}/api/v1/courses/{course_id}/files",
        headers=headers,
        data={
            "name": file_path.name,
            "size": file_path.stat().st_size,
            "content_type": "application/octet-stream",
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    upload_info = r.json()

    # Step 2: Upload file to Canvas storage
    upload_url = upload_info["upload_url"]
    upload_params = upload_info["upload_params"]

    with file_path.open("rb") as f:
        upload_response = requests.post(
            upload_url,
            data=upload_params,
            files={"file": f},
            timeout=_TIMEOUT * 2,  # File uploads can be slow
        )
    upload_response.raise_for_status()

    # Step 3: Confirm upload (returns file object)
    file_data = upload_response.json()

    # Canvas returns file ID in the response
    if "id" in file_data:
        return file_data["id"]

    # Some Canvas instances return a location to GET the file object
    if "location" in file_data:
        confirm_response = requests.get(
            file_data["location"],
            headers=headers,
            timeout=_TIMEOUT,
        )
        confirm_response.raise_for_status()
        return confirm_response.json()["id"]

    raise ValueError(f"Unexpected upload response format: {file_data}")


def submit_on_behalf(
    base_url: str,
    course_id: str,
    assignment_id: int,
    user_id: int,
    file_id: int,
    comment: str | None,
    token: str
) -> dict:
    """Submit an assignment on behalf of a student.

    Args:
        base_url: Canvas base URL
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        user_id: Canvas student user ID
        file_id: Canvas file ID (from upload_file_to_canvas)
        comment: Optional submission comment
        token: Canvas API token

    Returns:
        Submission object from Canvas API
    """
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "submission[submission_type]": "online_upload",
        "submission[file_ids][]": file_id,
        "submission[user_id]": user_id,
    }

    if comment:
        payload["comment[text_comment]"] = comment

    r = requests.post(
        f"{base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions",
        headers=headers,
        data=payload,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_assignment(base_url: str, course_id: str, assignment_id: int, token: str) -> dict:
    """Fetch assignment details from Canvas."""
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"{base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}",
        headers=headers,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Submit assignment files on behalf of students (Slack/email submissions)",
        epilog=(
            "Common workflow: Student Slacks file → you save to Downloads/ → "
            "run this tool to submit it in Canvas on their behalf."
        ),
    )

    # Student identification (PII-free)
    id_group = ap.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--deid-code", help="Student deid code (e.g., S-95DBB6)")
    id_group.add_argument("--user-id", type=int, help="Canvas user_id (testing only)")

    # Assignment identification
    ap.add_argument(
        "--assignment-id",
        type=int,
        required=True,
        help="Canvas assignment ID",
    )

    # File to submit
    ap.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to file to submit (e.g., ~/Downloads/essay.pdf)",
    )

    # Optional comment
    ap.add_argument(
        "--comment",
        help="Submission comment (e.g., 'Submitted via Slack on student behalf')",
    )

    # Execution control
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually submit (without this, dry-run preview)",
    )

    ap.add_argument(
        "--master",
        type=Path,
        default=_DEFAULT_MASTER,
        help=f"deid master path (default {str(_DEFAULT_MASTER)!r})",
    )

    args = ap.parse_args()

    # Load .env from current directory
    try:
        from dotenv import load_dotenv
        load_dotenv(Path.cwd() / ".env")
    except ImportError:
        pass

    # Resolve student user_id
    if args.deid_code:
        try:
            uid = resolve_deid_to_user_id(args.deid_code, args.master)
            print(f"Resolved {args.deid_code} → user_id {uid}")
        except (FileNotFoundError, KeyError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
    else:
        uid = args.user_id
        print(f"Using user_id {uid}")

    # Load Canvas credentials
    base_url = os.getenv("CANVAS_BASE_URL", "").rstrip("/")
    # Ensure base_url has a scheme (some .env files omit https://)
    if base_url and not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"
    course_id = os.getenv("CANVAS_COURSE_ID", "")
    token = os.getenv("CANVAS_API_TOKEN", "")

    if not all([base_url, course_id, token]):
        print(
            "ERROR: Missing Canvas credentials. Set in .env:\n"
            "  CANVAS_BASE_URL=https://byui.instructure.com\n"
            "  CANVAS_COURSE_ID=123456\n"
            "  CANVAS_API_TOKEN=...",
            file=sys.stderr,
        )
        return 1

    # Validate file exists
    file_path = args.file.expanduser().resolve()
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        return 1

    # Fetch assignment details
    print(f"\nFetching assignment {args.assignment_id}...")
    try:
        assignment = get_assignment(base_url, course_id, args.assignment_id, token)
        print(f"Assignment: {assignment['name']}")
    except requests.HTTPError as e:
        print(f"ERROR: Failed to fetch assignment: {e}", file=sys.stderr)
        return 1

    # Preview mode
    if not args.apply:
        print("\n[DRY RUN] Would perform these actions:")
        print(f"  1. Upload file: {file_path.name} ({file_path.stat().st_size} bytes)")
        print(f"  2. Submit on behalf of user {uid}")
        print(f"     Assignment: {assignment['name']} (ID {args.assignment_id})")
        if args.comment:
            print(f"     Comment: {args.comment}")
        print("\nRe-run with --apply to execute.")
        return 0

    # Apply mode: Upload and submit
    print(f"\nUploading {file_path.name}...")
    try:
        file_id = upload_file_to_canvas(base_url, course_id, file_path, token)
        print(f"  ✓ Uploaded (Canvas file_id: {file_id})")
    except Exception as e:
        print(f"  ✗ Upload failed: {e}", file=sys.stderr)
        return 1

    print(f"\nSubmitting on behalf of user {uid}...")
    try:
        submission = submit_on_behalf(
            base_url,
            course_id,
            args.assignment_id,
            uid,
            file_id,
            args.comment,
            token,
        )
        print(f"  ✓ Submitted (submission_id: {submission['id']})")
        print(f"     Submitted at: {submission.get('submitted_at', 'N/A')}")
        print(f"     Workflow state: {submission.get('workflow_state', 'N/A')}")
        if args.comment:
            print(f"     Comment added: {args.comment}")
        print("\n✓ Submission complete! Assignment now appears in SpeedGrader.")
    except Exception as e:
        print(f"  ✗ Submission failed: {e}", file=sys.stderr)
        print(
            "\nFile was uploaded but submission failed. "
            "You may need to submit manually in SpeedGrader.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

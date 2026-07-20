#!/usr/bin/env python3
"""
grader_fetch_resubmissions.py — Detect and report Canvas resubmissions needing grading.

Part of the canvas-toolbox generic grader skill (v1.7.12+). See:
  - grading_readme.md (faculty-facing pipeline)
  - lib/agents/canvas_grader.md (agent-facing pipeline)
  - lib/agents/knowledge/grader_knowledge.md (FERPA two-zone architecture)

WHY THIS EXISTS
  Canvas marks submissions as "needs grading" when a student resubmits AFTER
  receiving a grade. This happens when:
    - Student receives "incomplete" or low grade
    - Student fixes issues and resubmits
    - Canvas detects submitted_at > graded_at → "needs grading" flag

  Problem: These resubmissions are easy to overlook because:
    1. They already have a grade (so don't show as "ungraded")
    2. Canvas's needs_grading_count includes them but doesn't explain WHY
    3. No built-in "show me resubmissions" filter in Canvas UI

  Real-world impact: In ITM327 Spring 2026, 21 resubmissions across 10
  assignments went unnoticed for weeks because only new/ungraded submissions
  were being checked. This tool prevents that.

WHAT IT DOES
  1. Queries Canvas Submissions API for a course or specific assignment
  2. Identifies submissions where:
     - submitted_at > graded_at (resubmitted after grading), OR
     - submitted but never graded (graded_at is null)
  3. Generates a review report with:
     - User IDs (no names — FERPA Zone 2)
     - Submission timestamps
     - Current grade status
     - SpeedGrader links for review
  4. Optionally scans ALL assignments with needs_grading_count > 0

OUTPUT
  Markdown file: `resubmissions_report_<assignment_id>.md` or
                 `resubmissions_report_all.md`

  Contains:
    - Summary table of resubmissions by assignment
    - Per-student breakdown
    - SpeedGrader URLs for instructor review
    - Grade decision template (JSON format for grader_push.py)

FERPA / SECURITY BOUNDARY
  * Output files use user_id only (Canvas internal DB ID, not directory info)
  * No student names in filenames, console output, or reports
  * SpeedGrader links are safe (require Canvas login + instructor role)
  * Review reports are FERPA Zone 2 compliant

WORKFLOW (with grader_push.py)
  1. Fetch resubmissions:
       python grader_fetch_resubmissions.py --course-id 415322 --all

  2. Review submissions in Canvas SpeedGrader (links in report)

  3. Create grades JSON:
       {
         "assignment_id": 16858475,
         "grades": [
           {"user_id": 12345, "grade": "complete", "comment": "Good work."}
         ]
       }

  4. Push grades with AI disclosure (v1.7.12+):
       python grader_push.py --grades-file grades.json

USAGE
  # Check specific assignment
  python grader_fetch_resubmissions.py \\
    --course-id 415322 \\
    --assignment-id 16858475

  # Check all assignments with needs_grading_count > 0
  python grader_fetch_resubmissions.py \\
    --course-id 415322 \\
    --all

  # Output to specific directory
  python grader_fetch_resubmissions.py \\
    --course-id 415322 \\
    --all \\
    --output-dir grading/resubmissions

DESIGN NOTES
  * Queries submissions API (not gradebook) for real-time status
  * Handles Canvas's inconsistent needs_grading_count (reports actual state)
  * No auto-grading (manual review required for resubmissions)
  * Compatible with grader_push.py for grade submission
"""

import os
import sys
import argparse
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

# Canvas API setup
BASE_URL_DEFAULT = 'https://byui.instructure.com'


def get_canvas_config():
    """Get Canvas API token and base URL from environment."""
    token = os.getenv('CANVAS_API_TOKEN')
    if not token:
        print("Error: CANVAS_API_TOKEN environment variable not set", file=sys.stderr)
        print("Set it with: export CANVAS_API_TOKEN='your-token-here'", file=sys.stderr)
        sys.exit(1)

    base_url = os.getenv('CANVAS_BASE_URL', BASE_URL_DEFAULT)
    return token, base_url


def fetch_assignment_info(course_id: int, assignment_id: int, headers: dict, base_url: str) -> Dict:
    """Fetch assignment name and metadata."""
    url = f'{base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}'
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching assignment {assignment_id}: {e}", file=sys.stderr)
        return {'name': f'Unknown Assignment {assignment_id}', 'id': assignment_id}


def fetch_resubmissions(course_id: int, assignment_id: int, headers: dict, base_url: str) -> List[Dict]:
    """
    Fetch all resubmissions for an assignment.

    Returns submissions where:
    - submitted_at > graded_at (resubmitted after grading), OR
    - submitted but never graded (graded_at is null)
    """
    url = f'{base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions'
    params = {'per_page': 100}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching submissions: {e}", file=sys.stderr)
        return []

    submissions = response.json()
    resubmissions = []

    for s in submissions:
        submitted_at = s.get('submitted_at')
        graded_at = s.get('graded_at')

        if not submitted_at or s.get('workflow_state') != 'submitted':
            continue

        # Case 1: Submitted but never graded
        if not graded_at:
            resubmissions.append({
                'user_id': s['user_id'],
                'submitted_at': submitted_at,
                'graded_at': None,
                'current_grade': s.get('grade'),
                'workflow_state': s.get('workflow_state'),
                'attempt': s.get('attempt'),
                'reason': 'Never graded'
            })
            continue

        # Case 2: Resubmitted after being graded
        try:
            sub_time = datetime.fromisoformat(submitted_at.replace('Z', '+00:00'))
            grade_time = datetime.fromisoformat(graded_at.replace('Z', '+00:00'))

            if sub_time > grade_time:
                resubmissions.append({
                    'user_id': s['user_id'],
                    'submitted_at': submitted_at,
                    'graded_at': graded_at,
                    'current_grade': s.get('grade'),
                    'workflow_state': s.get('workflow_state'),
                    'attempt': s.get('attempt'),
                    'reason': 'Resubmitted after grading'
                })
        except (ValueError, TypeError):
            # Invalid timestamp format - skip
            continue

    return resubmissions


def get_assignments_needing_grading(course_id: int, headers: dict, base_url: str) -> List[Dict]:
    """Fetch all assignments with needs_grading_count > 0."""
    url = f'{base_url}/api/v1/courses/{course_id}/assignments'
    params = {'per_page': 100}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching assignments: {e}", file=sys.stderr)
        return []

    assignments = response.json()

    needs_grading = []
    for a in assignments:
        count = a.get('needs_grading_count', 0)
        if count > 0:
            needs_grading.append({
                'id': a['id'],
                'name': a['name'],
                'needs_grading_count': count,
                'due_at': a.get('due_at'),
                'points_possible': a.get('points_possible')
            })

    return needs_grading


def generate_report(course_id: int, assignment_id: int, assignment_name: str,
                   resubmissions: List[Dict], base_url: str) -> str:
    """Generate Markdown report for instructor review."""

    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    report = f"""# Resubmissions Needing Grading

**Assignment**: {assignment_name} ({assignment_id})
**Course ID**: {course_id}
**Generated**: {timestamp}
**Resubmissions Found**: {len(resubmissions)}

---

## Summary

This assignment has {len(resubmissions)} resubmission(s) where students submitted AFTER receiving a grade.
Canvas marks these as "needs grading" but they require manual review.

"""

    if not resubmissions:
        report += "✅ No resubmissions found. All submissions are up to date.\n"
        return report

    report += "## Resubmissions\n\n"

    for r in resubmissions:
        report += f"""### user_id {r['user_id']}

- **Reason**: {r['reason']}
- **Submitted**: {r['submitted_at']}
- **Last graded**: {r['graded_at'] or 'NEVER'}
- **Current grade**: {r['current_grade'] or 'None'}
- **Attempt**: {r['attempt']}
- **SpeedGrader**: {base_url}/courses/{course_id}/gradebook/speed_grader?assignment_id={assignment_id}&student_id={r['user_id']}

"""

    report += """---

## Next Steps

1. **Review each submission** using the SpeedGrader links above
2. **Determine new grades** based on the resubmission
3. **Create grades JSON** for grader_push.py:

```json
{
  "assignment_id": """ + str(assignment_id) + """,
  "assignment_name": \"""" + assignment_name + """\",
  "grades": [
"""

    for i, r in enumerate(resubmissions):
        comma = "," if i < len(resubmissions) - 1 else ""
        report += f"""    {{"user_id": {r['user_id']}, "grade": "complete", "comment": ""}}{comma}
"""

    report += """  ]
}
```

4. **Push grades** with AI disclosure (v1.7.12+):
   ```bash
   python grader_push.py --grades-file grades.json
   ```

---

**FERPA Zone 2**: This report uses user_id only (no names).
**Canvas-Toolbox**: v1.7.12+ compatible
"""

    return report


def main():
    parser = argparse.ArgumentParser(
        description='Detect Canvas resubmissions needing grading',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check specific assignment
  python grader_fetch_resubmissions.py --course-id 415322 --assignment-id 16858475

  # Check all assignments with needs_grading_count > 0
  python grader_fetch_resubmissions.py --course-id 415322 --all

  # Custom output directory
  python grader_fetch_resubmissions.py --course-id 415322 --all --output-dir grading/resubmissions
        """
    )

    parser.add_argument('--course-id', type=int, required=True,
                       help='Canvas course ID')
    parser.add_argument('--assignment-id', type=int,
                       help='Specific assignment ID to check')
    parser.add_argument('--all', action='store_true',
                       help='Check all assignments with needs_grading_count > 0')
    parser.add_argument('--output-dir', type=str, default='.',
                       help='Output directory for reports (default: current directory)')
    parser.add_argument('--base-url', type=str,
                       help=f'Canvas base URL (default: {BASE_URL_DEFAULT} or CANVAS_BASE_URL env var)')

    args = parser.parse_args()

    if not args.assignment_id and not args.all:
        parser.error('Must specify either --assignment-id or --all')

    # Get Canvas API config
    token, base_url = get_canvas_config()
    if args.base_url:
        base_url = args.base_url

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_resubmissions = 0

    if args.all:
        print(f"Fetching all assignments with ungraded submissions (course {args.course_id})...")
        assignments = get_assignments_needing_grading(args.course_id, headers, base_url)

        if not assignments:
            print("No assignments found with needs_grading_count > 0")
            return

        print(f"\nFound {len(assignments)} assignments to check:\n")

        for a in assignments:
            print(f"Checking: {a['name']} ({a['id']})...")
            resubmissions = fetch_resubmissions(args.course_id, a['id'], headers, base_url)

            if resubmissions:
                total_resubmissions += len(resubmissions)
                print(f"  ✓ {len(resubmissions)} resubmission(s) found")

                report = generate_report(args.course_id, a['id'], a['name'], resubmissions, base_url)
                report_file = output_dir / f"resubmissions_{a['id']}_{a['name'].replace(' ', '_').replace(':', '')[:50]}.md"
                report_file.write_text(report)
                print(f"  → Report: {report_file}")
            else:
                print(f"  • No resubmissions")

            print()

        print(f"Total resubmissions across all assignments: {total_resubmissions}")
        print(f"Reports saved to: {output_dir}/")

    else:
        # Single assignment
        assignment_info = fetch_assignment_info(args.course_id, args.assignment_id, headers, base_url)
        assignment_name = assignment_info['name']

        print(f"Checking: {assignment_name} ({args.assignment_id})...")
        resubmissions = fetch_resubmissions(args.course_id, args.assignment_id, headers, base_url)

        if resubmissions:
            print(f"\n✓ Found {len(resubmissions)} resubmission(s):")
            for r in resubmissions:
                print(f"  - user_id {r['user_id']}: {r['reason']}")

            report = generate_report(args.course_id, args.assignment_id, assignment_name,
                                   resubmissions, base_url)
            report_file = output_dir / f"resubmissions_{args.assignment_id}_{assignment_name.replace(' ', '_').replace(':', '')[:50]}.md"
            report_file.write_text(report)
            print(f"\nReport: {report_file}")
        else:
            print("\n• No resubmissions found")

    print("\nDone.")


if __name__ == '__main__':
    main()

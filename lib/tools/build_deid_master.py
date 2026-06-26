#!/usr/bin/env python3
"""
build_deid_master.py — Build the course-wide de-identification master CSV.

The MISSING PRIMITIVE that sits underneath all keyed / FERPA workflows.

Today, the canvas-toolbox uses:
  - per-assignment keymaps (a student gets a DIFFERENT key per assignment),
  - a flat `.known_names.txt` roster for the scrub pass.

Both work, but they don't give the operator a single, stable, course-wide
identity surface. This tool fixes that — one CSV, one row per enrolled
student, with a stable opaque code the operator can hand to other tools
WITHOUT ever speaking the student's name to the agent or the cloud LLM.

THE 4-COLUMN CONTRACT
  deid_code     — stable opaque code, e.g. S-95DBB6 (sha256(user_id)[:6])
  user_id       — Canvas numeric user_id, the source of truth
  sortable_name — "Lastname, Firstname" (NEVER read by tools unless explicit)
  withdrawn     — 1 if enrollment state is inactive/completed/deleted else 0

The `sortable_name` column lets the OPERATOR look up a student in their
LOCAL gitignored file ("find Sydney → S-95DBB6") and hand the agent / tool
only the code. The tool resolves code → user_id reading ONLY that column.

WHY `withdrawn` MATTERS
  The default Canvas People view shows ACTIVE students only. Final-grade
  analysis, last-engagement audits, and accommodations frequently need
  visibility into students who DROPPED mid-semester (state: inactive /
  completed / deleted). In one pilot: 30 active → 37 total → 7 withdrawn.

FERPA — TIER 2 GITIGNORED
  This file LIVES in the repo but is GITIGNORED. To make that bulletproof,
  the tool writes a `grading/.gitignore` (containing `*`) the first time
  it creates the directory — so even if the operator forgets to add
  `grading/` to their main .gitignore, the directory's own .gitignore
  prevents any tracked commits.

USAGE
  # Build / refresh the master (writes to ./grading/.deid_master.csv)
  uv run python lib/tools/build_deid_master.py

  # Custom prefix (default S-)
  uv run python lib/tools/build_deid_master.py --prefix DS-

  # Custom output location
  uv run python lib/tools/build_deid_master.py --out /path/to/master.csv

  # Refuse to overwrite an existing master without --force
  uv run python lib/tools/build_deid_master.py --force

  # Dry-run: print the rows that would be written, don't touch the file
  uv run python lib/tools/build_deid_master.py --dry-run

  # If a collision is detected (very rare under ~1000 students), re-run
  # with a longer hash. Default is 6 hex chars; --hash-bits 8 doubles the
  # collision-free range.
  uv run python lib/tools/build_deid_master.py --hash-bits 8

COLLISION MATH (sha256, first N hex chars uppercase, ~birthday paradox)
  6 hex (16M codes): 50 students → 0.007% | 200 → 0.12% | 500 → 0.7% | 1000 → 3%
  8 hex (4B codes):  1000 students → 0.01% | 5000 → 0.3% | 10000 → 1.2%
  10 hex: practically collision-free at any class size.

REQUIRES in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID

Resolves issue #109 — course-wide de-id master + per-student
accommodation primitives (the accommodation tool consumes this CSV).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


_DEFAULT_PREFIX = "S-"
_DEFAULT_HASH_BITS = 6
_DEFAULT_OUT = Path("grading/.deid_master.csv")
_WITHDRAWN_STATES = {"inactive", "completed", "deleted"}
_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Pure helpers (no I/O — easy to unit-test)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StudentRow:
    """One row of the de-id master CSV."""
    deid_code: str
    user_id: int
    sortable_name: str
    withdrawn: int  # 0 or 1


def deid_code_for(user_id: int, prefix: str = _DEFAULT_PREFIX,
                  hash_bits: int = _DEFAULT_HASH_BITS) -> str:
    """Compute the stable opaque code for a Canvas user_id.

    Format: {prefix}{first N hex chars of sha256(user_id), uppercased}
    Deterministic: same user_id always yields the same code.
    """
    h = hashlib.sha256(str(int(user_id)).encode("utf-8")).hexdigest()
    return f"{prefix}{h[:hash_bits].upper()}"


def is_withdrawn(enrollments: list[dict]) -> int:
    """Withdrawn=1 if any enrollment is in {inactive, completed, deleted}.

    A student with BOTH an active enrollment and a dropped enrollment is
    NOT withdrawn (active wins). The check is order-free: presence of any
    "still active" enrollment overrides the presence of a withdrawn one.
    """
    if not enrollments:
        return 0
    states = {e.get("enrollment_state") for e in enrollments}
    if "active" in states or "invited" in states:
        return 0
    return 1 if states & _WITHDRAWN_STATES else 0


def student_to_row(user: dict, prefix: str, hash_bits: int) -> StudentRow:
    """Build one StudentRow from a Canvas /users response item."""
    uid = int(user["id"])
    return StudentRow(
        deid_code=deid_code_for(uid, prefix, hash_bits),
        user_id=uid,
        sortable_name=user.get("sortable_name") or user.get("name") or "",
        withdrawn=is_withdrawn(user.get("enrollments") or []),
    )


def detect_collisions(rows: list[StudentRow]) -> list[tuple[str, list[int]]]:
    """Return [(deid_code, [user_id, user_id, ...])] for every code that
    appears more than once. Empty list = no collisions.
    """
    by_code: dict[str, list[int]] = {}
    for r in rows:
        by_code.setdefault(r.deid_code, []).append(r.user_id)
    return [(code, uids) for code, uids in by_code.items() if len(uids) > 1]


def render_csv_rows(rows: list[StudentRow]) -> list[list[str]]:
    """Build the CSV body (header + rows). Sorted by sortable_name for
    deterministic output across runs."""
    header = ["deid_code", "user_id", "sortable_name", "withdrawn"]
    sorted_rows = sorted(rows, key=lambda r: r.sortable_name.lower())
    return [header] + [
        [r.deid_code, str(r.user_id), r.sortable_name, str(r.withdrawn)]
        for r in sorted_rows
    ]


def render_known_names_lines(rows: list[StudentRow]) -> list[str]:
    """Render the auto-derived `.known_names.txt` content from the master.

    Path A (v0.71.0) — making the de-id master the source of truth for
    the scrub-pass name roster. Previously, grader_fetch.py populated
    .known_names.txt with display names per submitter; now the file is
    derived from the course-wide master so a single rebuild keeps the
    scrub roster in sync with the People view.

    Emits BOTH sortable ('Lastname, Firstname') and display ('Firstname
    Lastname') forms per student — submission text might say either,
    and the scrub matches whichever appears literally.

    Sorted + deduped (case-insensitive) for deterministic output.
    """
    out = [
        "# Auto-derived by build_deid_master.py from .deid_master.csv.",
        "# Do NOT hand-edit — changes will be overwritten on next build.",
        "# Peer-mention scrub roster. Gitignored. Never read by the AI.",
    ]
    seen: set[str] = set()
    for row in sorted(rows, key=lambda r: r.sortable_name.lower()):
        sortable = row.sortable_name.strip()
        if not sortable:
            continue
        if "," in sortable:
            last, first = (s.strip() for s in sortable.split(",", 1))
            display = f"{first} {last}".strip()
        else:
            display = sortable
        for form in (sortable, display):
            key = form.lower()
            if form and key not in seen:
                seen.add(key)
                out.append(form)
    return out


# ---------------------------------------------------------------------------
# Canvas API
# ---------------------------------------------------------------------------

def fetch_all_students(base_url: str, course_id: str, token: str) -> list[dict]:
    """GET /courses/:id/users?enrollment_type[]=student with ALL enrollment
    states so withdrawn students are NOT silently dropped.

    Paginates over all pages (per_page=100).
    """
    headers = {"Authorization": f"Bearer {token}"}
    out: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{base_url}/api/v1/courses/{course_id}/users",
            headers=headers,
            params={
                "per_page": 100,
                "page": page,
                "enrollment_type[]": "student",
                "enrollment_state[]": [
                    "active", "invited", "inactive", "completed",
                ],
                "include[]": ["enrollments"],
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        page += 1
    return out


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def ensure_grading_gitignore(grading_dir: Path) -> None:
    """Make sure `<grading_dir>/.gitignore` exists with `*` content so the
    directory's contents are git-ignored even if the operator forgot to add
    `grading/` to their main .gitignore. Defense-in-depth for FERPA tier 2.
    """
    grading_dir.mkdir(parents=True, exist_ok=True)
    gi = grading_dir / ".gitignore"
    if not gi.exists():
        gi.write_text("# Auto-written by build_deid_master.py — FERPA tier 2\n"
                      "# Every file in this directory is gitignored EXCEPT\n"
                      "# this .gitignore itself. Commit only this file.\n"
                      "*\n!.gitignore\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--prefix", default=_DEFAULT_PREFIX,
                    help=f"deid_code prefix (default {_DEFAULT_PREFIX!r})")
    ap.add_argument("--hash-bits", type=int, default=_DEFAULT_HASH_BITS,
                    help=f"hex chars from sha256 (default {_DEFAULT_HASH_BITS}; "
                         "increase if a collision is detected)")
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT,
                    help=f"output path (default {str(_DEFAULT_OUT)!r}, relative to cwd)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing master without prompting")
    ap.add_argument("--dry-run", action="store_true",
                    help="print rows that would be written, don't touch the file")
    args = ap.parse_args()

    base_url = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base_url and not base_url.startswith("http"):
        base_url = "https://" + base_url
    course_id = os.environ.get("CANVAS_COURSE_ID", "")
    token = os.environ.get("CANVAS_API_TOKEN", "")
    if not (base_url and course_id and token):
        print("ERROR: CANVAS_BASE_URL / CANVAS_COURSE_ID / CANVAS_API_TOKEN "
              "must be set in .env or the environment.", file=sys.stderr)
        return 2

    if args.out.exists() and not args.force and not args.dry_run:
        print(f"ERROR: {args.out} already exists. Re-run with --force to overwrite.",
              file=sys.stderr)
        return 2

    print(f"Fetching all students (active + invited + inactive + completed)...")
    users = fetch_all_students(base_url, course_id, token)
    print(f"  {len(users)} student records returned")

    rows = [student_to_row(u, args.prefix, args.hash_bits) for u in users]
    collisions = detect_collisions(rows)
    if collisions:
        print("\nERROR: deid_code collision detected:", file=sys.stderr)
        for code, uids in collisions:
            print(f"  {code} ← user_ids {uids}", file=sys.stderr)
        print(f"\nRe-run with --hash-bits {args.hash_bits + 2} (or higher).",
              file=sys.stderr)
        return 2

    n_active = sum(1 for r in rows if r.withdrawn == 0)
    n_withdrawn = sum(1 for r in rows if r.withdrawn == 1)
    print(f"  {n_active} active, {n_withdrawn} withdrawn")

    csv_rows = render_csv_rows(rows)

    if args.dry_run:
        print("\n--- DRY RUN — would write the following rows ---")
        for row in csv_rows[:5]:
            print("  " + ",".join(row))
        if len(csv_rows) > 5:
            print(f"  ... and {len(csv_rows) - 5} more rows")
        print(f"\nWould write to: {args.out}")
        return 0

    ensure_grading_gitignore(args.out.parent)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerows(csv_rows)

    # Path A (v0.71.0): auto-derive .known_names.txt from the master so
    # the scrub-pass roster (used by every grader_deidentify_* tool)
    # stays in sync without a separate refresh step.
    names_path = args.out.parent / ".known_names.txt"
    names_path.write_text(
        "\n".join(render_known_names_lines(rows)) + "\n",
        encoding="utf-8",
    )

    print(f"\nWrote {len(rows)} rows to {args.out}")
    print(f"Auto-derived {names_path} for the peer-mention scrub")
    print("FERPA tier 2: both files are gitignored. Never commit them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

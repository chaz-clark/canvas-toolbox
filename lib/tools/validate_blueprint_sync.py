#!/usr/bin/env python3
"""
validate_blueprint_sync.py — post-Blueprint-sync validation (issue #24)

Queries Canvas API live to verify that a Blueprint sync landed correctly
across all configured sections. Four checks:

  1. Section drift    — items present in one section but missing from another
  2. Blueprint drift  — allowed_extensions, submission_types, or lock_at
                        diverge between Blueprint and a section
  3. Duplicates       — same assignment/quiz title appears more than once
                        in a section (direct-push + Blueprint overlap)
  4. Locked items     — must_submit/must_view items whose lock_at is in the
                        past (students locked out; prerequisite chain blocked)

Usage:
    uv run python canvas_toolbox/lib/tools/validate_blueprint_sync.py
    uv run python canvas_toolbox/lib/tools/validate_blueprint_sync.py --report

Requires in .env:
    CANVAS_API_TOKEN, CANVAS_BASE_URL, BLUEPRINT_COURSE_ID,
    and at least one S{N}_COURSE_ID  (S1_COURSE_ID, S2_COURSE_ID, …)
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

CANVAS_API_TOKEN   = os.environ.get("CANVAS_API_TOKEN", "")
CANVAS_BASE_URL    = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
BLUEPRINT_COURSE_ID = os.environ.get("BLUEPRINT_COURSE_ID", "")

# Fields compared per content type for Blueprint-vs-section drift
_DRIFT_FIELDS: dict[str, tuple[str, ...]] = {
    "assignments": ("allowed_extensions", "submission_types", "lock_at"),
    "quizzes":     ("lock_at", "time_limit", "allowed_attempts"),
}


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(endpoint: str, params: dict | None = None) -> list | dict | None:
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    results: list = []
    p: dict = {**(params or {}), "per_page": 100}
    while url:
        resp = requests.get(url, headers=_headers(), params=p, timeout=30)
        if resp.status_code >= 400:
            return None
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url = None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        p = {}
    return results


# ---------------------------------------------------------------------------
# Discovery and data fetching
# ---------------------------------------------------------------------------

def _discover_sections() -> dict[str, str]:
    """Return {label: course_id} for all S{n}_COURSE_ID vars in .env."""
    out: dict[str, str] = {}
    for key, val in os.environ.items():
        if key.startswith("S") and key.endswith("_COURSE_ID") and val:
            label = key[: -len("_COURSE_ID")].lower()  # S1_COURSE_ID → s1
            if len(label) >= 2 and label[1:].isdigit():
                out[label] = val
    return dict(sorted(out.items()))


def _fetch(course_id: str) -> dict:
    """Pull assignments, quizzes, pages, and modules (with items) live from Canvas."""
    assignments_raw = _get(f"/courses/{course_id}/assignments") or []
    quizzes_raw     = _get(f"/courses/{course_id}/quizzes") or []
    pages_raw       = _get(f"/courses/{course_id}/pages") or []
    modules_raw     = _get(f"/courses/{course_id}/modules", {"include[]": "items"}) or []

    # Exclude quiz-wrapper assignments (submission_types=["online_quiz"]) to avoid
    # double-counting with quizzes on the section/blueprint drift checks
    assignments = [a for a in assignments_raw if a.get("submission_types") != ["online_quiz"]]

    return {
        "assignments":       {a["name"]: a  for a in assignments},
        "assignments_list":  assignments,
        "assignments_by_id": {a["id"]: a    for a in assignments},
        "quizzes":           {q["title"]: q for q in quizzes_raw},
        "quizzes_list":      quizzes_raw,
        "quizzes_by_id":     {q["id"]: q   for q in quizzes_raw},
        "pages":             {p["title"]: p for p in pages_raw},
        "modules":           modules_raw,
    }


# ---------------------------------------------------------------------------
# Check 1 — Section drift
# ---------------------------------------------------------------------------

def check_section_drift(sections_data: dict[str, dict]) -> list[str]:
    """Items present in some sections but missing from others."""
    if len(sections_data) < 2:
        return []
    findings: list[str] = []
    for kind in ("assignments", "quizzes", "pages"):
        name_sets = {label: set(data[kind]) for label, data in sections_data.items()}
        all_names = set().union(*name_sets.values())
        for name in sorted(all_names):
            missing = [lbl for lbl, names in name_sets.items() if name not in names]
            if missing:
                present = [lbl for lbl in name_sets if lbl not in missing]
                findings.append(
                    f"  [{kind[:-1].title()}] '{name}' — in {present}, missing from {missing}"
                )
    return findings


# ---------------------------------------------------------------------------
# Check 2 — Blueprint drift
# ---------------------------------------------------------------------------

def check_blueprint_drift(bp_data: dict, sections_data: dict[str, dict]) -> list[str]:
    """Fields that diverge between Blueprint and a section."""
    findings: list[str] = []
    for kind, fields in _DRIFT_FIELDS.items():
        for name, bp_item in bp_data[kind].items():
            for label, sec_data in sections_data.items():
                sec_item = sec_data[kind].get(name)
                if sec_item is None:
                    continue  # absence handled by check 1
                for field in fields:
                    bp_val  = bp_item.get(field)
                    sec_val = sec_item.get(field)
                    if bp_val != sec_val:
                        findings.append(
                            f"  [{kind[:-1].title()}] '{name}' — {field}: "
                            f"Blueprint={bp_val!r}, {label}={sec_val!r}"
                        )
    return findings


# ---------------------------------------------------------------------------
# Check 3 — Duplicate detection
# ---------------------------------------------------------------------------

def check_duplicates(label: str, data: dict) -> list[str]:
    """Assignment or quiz title appearing more than once in the same section."""
    findings: list[str] = []

    by_name: dict[str, list] = defaultdict(list)
    for a in data["assignments_list"]:
        by_name[a["name"]].append(a["id"])
    for name, ids in sorted(by_name.items()):
        if len(ids) > 1:
            findings.append(
                f"  [Assignment] '{name}' — {len(ids)} copies in {label} (ids: {ids}). "
                "Run course_quality_check.py for Blueprint-aware resolution."
            )

    qby_name: dict[str, list] = defaultdict(list)
    for q in data["quizzes_list"]:
        qby_name[q["title"]].append(q["id"])
    for title, ids in sorted(qby_name.items()):
        if len(ids) > 1:
            findings.append(
                f"  [Quiz] '{title}' — {len(ids)} copies in {label} (ids: {ids}). "
                "Run course_quality_check.py for Blueprint-aware resolution."
            )

    return findings


# ---------------------------------------------------------------------------
# Check 4 — Locked item check
# ---------------------------------------------------------------------------

def check_locked_items(label: str, data: dict) -> list[str]:
    """must_submit/must_view items whose lock_at is in the past."""
    now = datetime.now(timezone.utc)
    findings: list[str] = []

    # Build a single content_id → item lookup across assignments and quizzes
    by_content_id: dict[int, dict] = {}
    by_content_id.update(data["assignments_by_id"])
    by_content_id.update(data["quizzes_by_id"])

    for module in data["modules"]:
        mod_name = module.get("name", f"id={module.get('id')}")
        for item in module.get("items") or []:
            cr = item.get("completion_requirement")
            if not cr or cr.get("type") not in ("must_submit", "must_view"):
                continue
            content = by_content_id.get(item.get("content_id"))
            if not content:
                continue
            lock_at_str = content.get("lock_at")
            if not lock_at_str:
                continue
            try:
                lock_at = datetime.fromisoformat(lock_at_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if lock_at < now:
                title   = item.get("title", f"id={item.get('content_id')}")
                cr_type = cr["type"]
                findings.append(
                    f"  [Module '{mod_name}'] '{title}' — lock_at {lock_at_str[:10]} passed; "
                    f"{cr_type} requirement blocks downstream prerequisites in {label}"
                )

    return findings


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _render_check(name: str, findings: list[str]) -> str:
    if findings:
        lines = [f"🔴 {name} ({len(findings)} issue{'s' if len(findings) != 1 else ''})"]
        lines.extend(findings)
    else:
        lines = [f"✅ {name}"]
    return "\n".join(lines)


def _write_report(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport written to {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate post-Blueprint-sync state across sections")
    parser.add_argument("--report", action="store_true", help="Write findings to blueprint_sync_validation.md")
    args = parser.parse_args()

    sections = _discover_sections()

    missing = []
    if not CANVAS_BASE_URL or CANVAS_BASE_URL == "https://":
        missing.append("CANVAS_BASE_URL")
    if not CANVAS_API_TOKEN:
        missing.append("CANVAS_API_TOKEN")
    if not BLUEPRINT_COURSE_ID:
        missing.append("BLUEPRINT_COURSE_ID")
    if not sections:
        missing.append("S1_COURSE_ID (at least one section required)")
    if missing:
        print("ERROR: Missing required configuration:")
        for m in missing:
            print(f"  {m}")
        print("\nSet these in your .env file.")
        sys.exit(1)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    section_list = ", ".join(f"{lbl} ({cid})" for lbl, cid in sections.items())
    header = [
        f"# Blueprint Sync Validation",
        f"",
        f"Blueprint: {BLUEPRINT_COURSE_ID}",
        f"Sections:  {section_list}",
        f"Run at:    {ts}",
        f"",
        "=" * 62,
    ]
    for line in header:
        print(line)

    print("\nFetching Blueprint data...")
    bp_data = _fetch(BLUEPRINT_COURSE_ID)
    sections_data: dict[str, dict] = {}
    for label, cid in sections.items():
        print(f"Fetching {label} ({cid})...")
        sections_data[label] = _fetch(cid)

    # Run checks
    drift_findings    = check_section_drift(sections_data)
    bp_drift_findings = check_blueprint_drift(bp_data, sections_data)
    dup_findings: list[str] = []
    locked_findings: list[str] = []
    for label, data in sections_data.items():
        dup_findings.extend(check_duplicates(label, data))
        locked_findings.extend(check_locked_items(label, data))

    print()
    results = [
        ("Check 1: Section drift",                          drift_findings),
        ("Check 2: Blueprint drift (fields)",               bp_drift_findings),
        ("Check 3: Duplicate assignments/quizzes",          dup_findings),
        ("Check 4: Locked items blocking prerequisites",    locked_findings),
    ]
    report_lines = list(header)
    for name, findings in results:
        block = _render_check(name, findings)
        print(block)
        print()
        report_lines.append(block)
        report_lines.append("")

    any_issues = any(f for _, f in results)
    if args.report:
        _write_report(Path("blueprint_sync_validation.md"), report_lines)

    sys.exit(1 if any_issues else 0)


if __name__ == "__main__":
    main()

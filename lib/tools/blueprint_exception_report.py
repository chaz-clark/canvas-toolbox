#!/usr/bin/env python3
"""
blueprint_exception_report.py — surface per-section Blueprint sync exceptions (#28)

After a Canvas Blueprint sync, Canvas reports `workflow_state: completed`
even when sections silently skipped items via exceptions (`content`,
`deleted`, `due_dates`, …). This tool reads the subscriber-side
migration-details endpoint for each associated section, groups exceptions
by type, emits a PASS / WARN / FAIL verdict per section + overall, and
(optionally) outputs a lock-and-resync script for items the operator
likely intended to push.

Pairs with validate_blueprint_sync.py:
  - validate_blueprint_sync.py: STATE-DIFF (what is — flags drift)
  - blueprint_exception_report.py: SYNC-LOG (what happened, why, fix)

Exception severity (#28 agreed split):
  PASS:  due_dates, availability_dates       (section-design-intentional)
  WARN:  points, state, settings             (case-by-case)
  FAIL:  content, deleted                    (lock + resync to fix)
  Unknown exception types are treated as WARN (surfaced, never silently dropped).

Exit codes:
  0  — PASS or WARN-only
  1  — at least one section FAIL
  2  — configuration error / cannot run

Endpoints used (all read-only, GET):
  GET /courses/:bp_id/blueprint_templates/default/migrations
  GET /courses/:section_id/blueprint_subscriptions
  GET /courses/:section_id/blueprint_subscriptions/:sub_id/migrations/:mig_id/details

Usage:
    uv run python canvas_toolbox/lib/tools/blueprint_exception_report.py
    uv run python canvas_toolbox/lib/tools/blueprint_exception_report.py --migration-id 2102739
    uv run python canvas_toolbox/lib/tools/blueprint_exception_report.py --suggest-locks
    uv run python canvas_toolbox/lib/tools/blueprint_exception_report.py --report

Requires in .env:
    CANVAS_API_TOKEN, CANVAS_BASE_URL, BLUEPRINT_COURSE_ID,
    and at least one S{N}_COURSE_ID

Verification note: end-to-end requires a live Canvas Blueprint with at least
one associated section that has completed a sync. canvas-toolbox itself has
no live course — static + argparse verification only when developed here.
"""

from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from __toolbox_version__ import __version__

load_dotenv()

CANVAS_API_TOKEN    = os.environ.get("CANVAS_API_TOKEN", "")
# Normalize the base URL: the .env convention is scheme-less; requests needs a
# scheme. Matches canvas_sync.py (see ITM327 2026-05-21 scheme bug).
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL     = _raw_url
BLUEPRINT_COURSE_ID = os.environ.get("BLUEPRINT_COURSE_ID", "")

# Exception conflicting-change type → severity (agreed #28 split)
EXCEPTION_SEVERITY: dict[str, str] = {
    "due_dates":          "PASS",
    "availability_dates": "PASS",
    "points":             "WARN",
    "state":              "WARN",
    "settings":           "WARN",
    "content":            "FAIL",
    "deleted":            "FAIL",
}
SEVERITY_RANK = {"PASS": 0, "WARN": 1, "FAIL": 2}
SEVERITY_ICON = {"PASS": "✅", "WARN": "⚠️", "FAIL": "🔴"}

# Canvas asset_type → restrict_item content_type (for --suggest-locks).
# Unknown asset_types fall through to a SKIP-SUGGEST comment rather than
# emitting a curl with the wrong content_type.
ASSET_TYPE_MAP: dict[str, str] = {
    "Assignment":          "assignment",
    "Quiz":                "quiz",
    "Quizzes::Quiz":       "quiz",
    "WikiPage":            "wiki_page",
    "DiscussionTopic":     "discussion_topic",
    "Attachment":          "attachment",
    "ContextExternalTool": "external_tool",
}


# ---------------------------------------------------------------------------
# API helpers (style matches validate_blueprint_sync.py)
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


def _discover_sections() -> dict[str, str]:
    """Return {label: course_id} for all S{n}_COURSE_ID vars in .env."""
    out: dict[str, str] = {}
    for key, val in os.environ.items():
        if key.startswith("S") and key.endswith("_COURSE_ID") and val:
            label = key[: -len("_COURSE_ID")].lower()
            if len(label) >= 2 and label[1:].isdigit():
                out[label] = val
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# Canvas Blueprint endpoints
# ---------------------------------------------------------------------------

def get_most_recent_migration(bp_id: str) -> tuple[int | None, str | None]:
    """Return (migration_id, created_at_iso) for the most recent Blueprint
    migration on `bp_id`, or (None, None) if no migrations exist."""
    migs = _get(f"/courses/{bp_id}/blueprint_templates/default/migrations") or []
    if not migs:
        return None, None
    # Canvas docs say returned newest-first; pick max defensively anyway.
    most = max(migs, key=lambda m: m.get("created_at") or "")
    return most.get("id"), most.get("created_at")


def get_subscription_id(section_id: str) -> int | None:
    """One subscription per associated section per the Canvas data model.
    Returns None if the section is not Blueprint-associated."""
    subs = _get(f"/courses/{section_id}/blueprint_subscriptions") or []
    if not subs:
        return None
    return subs[0].get("id")


def get_blueprint_associated_ids(bp_id: str) -> set[str]:
    """Course IDs the blueprint itself lists as associated — the authoritative
    topology (issue #33). Empty set on error (the cross-check then can't upgrade
    a 'not associated' to 'unreadable', which is the safe direction)."""
    rows = _get(f"/courses/{bp_id}/blueprint_templates/default/associated_courses") or []
    if not isinstance(rows, list):
        return set()
    return {str(r.get("id")) for r in rows if isinstance(r, dict) and r.get("id")}


def classify_subscription(section_id: str, associated_ids: set[str]) -> tuple[str, int | None]:
    """Distinguish the three real states (issue #33): a 403/empty subscription
    read does NOT mean 'not associated'. Returns (state, sub_id):
      - 'ok'             — subscription read; sub_id present
      - 'unreadable'     — associated per the blueprint, but the per-course read
                           failed (e.g. 403 token-scope) or came back empty
      - 'not_associated' — absent from the blueprint's associated_courses
    """
    url = f"{CANVAS_BASE_URL}/api/v1/courses/{section_id}/blueprint_subscriptions"
    associated = str(section_id) in associated_ids
    try:
        resp = requests.get(url, headers=_headers(), params={"per_page": 100}, timeout=30)
    except Exception:
        return ("unreadable" if associated else "not_associated", None)
    if resp.status_code < 400:
        try:
            subs = resp.json()
        except Exception:
            subs = []
        if isinstance(subs, list) and subs:
            return ("ok", subs[0].get("id"))
    # 4xx (e.g. 403) or 200-but-empty: associated → unreadable; else not associated.
    return ("unreadable" if associated else "not_associated", None)


def get_migration_details(section_id: str, sub_id: int, mig_id: int) -> list[dict]:
    """List of item records on the subscriber side for this migration.
    Each item carries `exceptions[].conflicting_changes` (list of type strings)."""
    return _get(
        f"/courses/{section_id}/blueprint_subscriptions/{sub_id}"
        f"/migrations/{mig_id}/details",
        params={"per_page": 200},
    ) or []


# ---------------------------------------------------------------------------
# Classification + verdict
# ---------------------------------------------------------------------------

def _classify(ex_type: str) -> str:
    """Unknown types -> WARN (surface, don't silently drop or auto-fail)."""
    return EXCEPTION_SEVERITY.get(ex_type, "WARN")


def _section_verdict(items: list[dict]) -> str:
    worst = "PASS"
    for it in items:
        for ex in it.get("exceptions") or []:
            for kind in ex.get("conflicting_changes") or []:
                sev = _classify(kind)
                if SEVERITY_RANK[sev] > SEVERITY_RANK[worst]:
                    worst = sev
    return worst


# ---------------------------------------------------------------------------
# Per-section rendering + --suggest-locks
# ---------------------------------------------------------------------------

def _format_lock_curl(bp_id: str, content_type: str, content_id) -> str:
    return (
        f'curl -X PUT "$CANVAS_BASE_URL/api/v1/courses/{bp_id}'
        f'/blueprint_templates/default/restrict_item" \\\n'
        f'    -H "Authorization: Bearer $CANVAS_API_TOKEN" \\\n'
        f'    -d "content_type={content_type}" \\\n'
        f'    -d "content_id={content_id}" \\\n'
        f'    -d "restricted=true" \\\n'
        f'    -d "restrictions[content]=true"'
    )


def build_section_block(
    label: str, section_id: str, items: list[dict],
    suggest_locks: bool, bp_id: str,
) -> tuple[str, list[str], list[str]]:
    """Return (verdict, output_lines, lock_script_lines)."""
    by_type: dict[str, list[tuple]] = defaultdict(list)
    for it in items:
        asset_name = it.get("asset_name") or "(unnamed)"
        asset_type = it.get("asset_type") or "?"
        asset_id   = it.get("asset_id")
        for ex in it.get("exceptions") or []:
            for kind in ex.get("conflicting_changes") or []:
                by_type[kind].append((asset_name, asset_type, asset_id))

    verdict = _section_verdict(items)
    icon = SEVERITY_ICON[verdict]
    lines = [f"## {icon} {label.upper()} (course {section_id}) — {verdict}"]
    if not by_type:
        lines.append("  No exceptions reported.")
        return verdict, lines, []

    total = sum(len(v) for v in by_type.values())
    lines.append(f"  {total} exception(s) across {len(by_type)} type(s):")
    for kind in sorted(by_type, key=lambda k: (-len(by_type[k]), k)):
        sev = _classify(kind)
        rows = by_type[kind]
        lines.append(f"  [{sev}] {kind} × {len(rows)}")
        for name, atype, aid in rows[:20]:
            lines.append(f"    - {name!r}  ({atype} id={aid})")
        if len(rows) > 20:
            lines.append(f"    … and {len(rows) - 20} more")

    lock_lines: list[str] = []
    if suggest_locks:
        for kind in ("content", "deleted"):
            for name, atype, aid in by_type.get(kind, []):
                ct = ASSET_TYPE_MAP.get(atype)
                if ct and aid is not None:
                    lock_lines.append(f"# [{label}] {kind} on {atype} '{name}' (id {aid})")
                    lock_lines.append(_format_lock_curl(bp_id, ct, aid))
                    lock_lines.append("")
                else:
                    lock_lines.append(
                        f"# [{label}] SKIP-SUGGEST (no asset_type mapping) — "
                        f"{atype} '{name}' id={aid}"
                    )
    return verdict, lines, lock_lines


def _write_report(path: Path, body: str) -> None:
    path.write_text(body + "\n", encoding="utf-8")
    print(f"\nReport written to {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Per-section Blueprint sync exception report (#28)"
    )
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    ap.add_argument("--migration-id", type=int, default=None,
                    help="inspect a specific migration id (default: most recent)")
    ap.add_argument("--suggest-locks", action="store_true",
                    help="emit a lock+resync script for content/deleted exceptions")
    ap.add_argument("--report", action="store_true",
                    help="write findings to blueprint_exception_report.md")
    args = ap.parse_args()

    # env check
    missing: list[str] = []
    if not CANVAS_BASE_URL or CANVAS_BASE_URL == "https://":
        missing.append("CANVAS_BASE_URL")
    if not CANVAS_API_TOKEN:
        missing.append("CANVAS_API_TOKEN")
    if not BLUEPRINT_COURSE_ID:
        missing.append("BLUEPRINT_COURSE_ID")
    sections = _discover_sections()
    if not sections:
        missing.append("S1_COURSE_ID (at least one section required)")
    if missing:
        print("ERROR: Missing required configuration:")
        for m in missing:
            print(f"  {m}")
        print("\nSet these in your .env file.")
        sys.exit(2)

    # resolve migration id
    if args.migration_id:
        mig_id = args.migration_id
        mig_created = "<--migration-id override>"
    else:
        mig_id, mig_created = get_most_recent_migration(BLUEPRINT_COURSE_ID)
        if not mig_id:
            print(f"ERROR: No Blueprint migrations found on course "
                  f"{BLUEPRINT_COURSE_ID}.\nHas a Blueprint sync ever been run?")
            sys.exit(2)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    section_list = ", ".join(f"{lbl} ({cid})" for lbl, cid in sections.items())
    header_lines = [
        "# Blueprint Sync Exception Report",
        "",
        f"Blueprint: {BLUEPRINT_COURSE_ID}",
        f"Migration: {mig_id}  (created {mig_created})",
        f"Sections:  {section_list}",
        f"Run at:    {ts}",
        "",
        "=" * 62,
    ]
    for line in header_lines:
        print(line)

    body_lines: list[str] = []
    lock_lines: list[str] = []
    overall = "PASS"
    # Authoritative association topology from the blueprint side (#33) — lets us
    # tell "not associated" from "associated but subscription unreadable (403)".
    associated_ids = get_blueprint_associated_ids(BLUEPRINT_COURSE_ID)
    for label, sid in sections.items():
        state, sub = classify_subscription(sid, associated_ids)
        if state == "not_associated":
            block = [
                f"## ⚪ {label.upper()} (course {sid}) — NOT ASSOCIATED",
                "  Absent from the blueprint's associated_courses list; skipped.",
            ]
            print("\n" + "\n".join(block))
            body_lines.extend(["", *block])
            continue
        if state == "unreadable":
            block = [
                f"## ⚠️  {label.upper()} (course {sid}) — SUBSCRIPTION UNREADABLE",
                "  Associated to the blueprint, but its subscription couldn't be read "
                "(HTTP 403 — token scope?). NOT detached; this section was skipped "
                "because the exception data is unavailable, not because it left the blueprint.",
            ]
            print("\n" + "\n".join(block))
            body_lines.extend(["", *block])
            if SEVERITY_RANK["WARN"] > SEVERITY_RANK[overall]:
                overall = "WARN"
            continue

        details = get_migration_details(sid, sub, mig_id)
        verdict, block, locks = build_section_block(
            label, sid, details, args.suggest_locks, BLUEPRINT_COURSE_ID
        )
        print("\n" + "\n".join(block))
        body_lines.extend(["", *block])
        lock_lines.extend(locks)
        if SEVERITY_RANK[verdict] > SEVERITY_RANK[overall]:
            overall = verdict

    icon = SEVERITY_ICON[overall]
    if overall == "FAIL":
        summary_msg = (
            "FAIL = at least one section has `content` or `deleted` exceptions "
            "that did not sync. Lock the listed items in the blueprint and "
            "trigger a resync to push them. Use --suggest-locks for the script."
        )
    elif overall == "WARN":
        summary_msg = (
            "WARN = section-local edits exist on points/state/settings — "
            "review case-by-case; not auto-failing."
        )
    else:
        summary_msg = (
            "PASS = exceptions are exclusively section-design-intentional "
            "(due_dates / availability_dates)."
        )
    summary = ["", "=" * 62, f"{icon} OVERALL: {overall}", "", summary_msg]
    for line in summary:
        print(line)
    body_lines.extend(summary)

    if args.suggest_locks and lock_lines:
        suggest = [
            "",
            "## --suggest-locks: lock + resync script",
            "",
            "# Pipe to sh after verifying. Requires CANVAS_BASE_URL and",
            "# CANVAS_API_TOKEN in your environment. After running, trigger",
            "# a Blueprint sync (Canvas UI or REST migrations endpoint) to",
            "# push the now-locked items into associated sections.",
            "",
            *lock_lines,
        ]
        print("\n" + "\n".join(suggest))
        body_lines.extend(suggest)

    if args.report:
        _write_report(
            Path("blueprint_exception_report.md"),
            "\n".join(header_lines + body_lines),
        )

    sys.exit(1 if overall == "FAIL" else 0)


if __name__ == "__main__":
    main()

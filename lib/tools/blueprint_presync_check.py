#!/usr/bin/env python3
"""
blueprint_presync_check.py — PRE-sync lock-readiness preflight (read-only, #36).

The pre-sync complement to blueprint_exception_report.py (#28, post-sync). Before you
run a Blueprint sync, it predicts which pending changes will be SILENTLY SKIPPED in a
section — blueprint items with a pending content change that are UNLOCKED and have been
LOCALLY EDITED in an associated section — and emits a --suggest-locks script to lock
them FIRST. Collapses the wasteful loop "edit → sync → discover skip → lock → resync"
into "edit → preflight (lock these) → sync once".

How it infers "locally edited" (confirmed empirically against blueprint 415130, #36):
  - `unsynced_changes` ChangeRecords do NOT carry `exceptions` pre-sync (Canvas computes
    those at migration-apply), so the preflight must infer local edits itself.
  - PAGES (wiki_page) — PRECISE: reuse the #32 revision-provenance primitive. A section
    page whose body hash matches SOME blueprint revision is merely *behind* (the sync will
    update it — not at risk). A hash matching NO blueprint revision is a *local edit* (the
    sync will skip it — AT RISK). This cleanly separates "behind" from "edited".
  - ASSIGNMENTS / QUIZZES / DISCUSSIONS — NOT pre-verifiable: these have no /revisions
    endpoint, and a pending change makes the section differ from blueprint-current by
    definition, so a naive diff can't tell "behind" from "locally edited". Rather than
    over-warn (it would flag clean items too), the preflight reports these honestly as
    "can't pre-verify" with the safe options. (v2: a snapshot baseline at sync time.)
  - LOCKED items are never at risk (Canvas force-overwrites) — only `locked == false`
    pending content changes are evaluated.

Endpoints (all GET, read-only):
  GET /courses/:bp/blueprint_templates/default/unsynced_changes      (pending + locked)
  GET /courses/:bp/blueprint_templates/default/associated_courses    (sections)
  GET /courses/:id/pages/:slug  + /pages/:slug/revisions/:rid?summary=false  (#32 primitive)

Verdict `presync` ∈ {ready, at_risk, review, nothing_pending}.

Exit codes: 0 ready/nothing_pending · 1 at_risk/review · 2 config / blueprint unreadable.

Usage:
  BLUEPRINT_COURSE_ID=415130 uv run python canvas_toolbox/lib/tools/blueprint_presync_check.py
  uv run python canvas_toolbox/lib/tools/blueprint_presync_check.py --bp 415130 --suggest-locks
  uv run python canvas_toolbox/lib/tools/blueprint_presync_check.py --bp 415130 --json

Reads: knowledge/canvas_api_lessons_learned.md (L8/L14 blueprint behaviors).
Reuses: blueprint_orphan_pages (revision-provenance, #32) + blueprint_exception_report
(asset_type→restrict_item map + lock-curl, #28).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

import canvas_course_guard as guard
from __toolbox_version__ import __version__
from blueprint_orphan_pages import get_page_revision_hashes, _hash, get_page_with_body
from blueprint_exception_report import ASSET_TYPE_MAP, _format_lock_curl

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url
_TIMEOUT = 30

# Pending change_types that carry content worth a skip-risk check.
_CONTENT_CHANGES = {"created", "updated"}
# Asset types we can evaluate precisely (pages) vs only flag honestly.
_PRECISE = {"wiki_page"}
_UNVERIFIABLE = {"assignment", "quiz", "quizzes::quiz", "discussiontopic", "discussion_topic"}


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(endpoint: str, params: dict | None = None) -> list | dict | None:
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    results: list = []
    p: dict = {**(params or {}), "per_page": 100}
    while url:
        try:
            resp = requests.get(url, headers=_headers(), params=p, timeout=_TIMEOUT)
        except Exception:
            return results or None
        if resp.status_code >= 400:
            return results or None
        try:
            data = resp.json()
        except Exception:
            return results or None
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


def get_unsynced_changes(bp_id: str) -> list | None:
    return _get(f"/courses/{bp_id}/blueprint_templates/default/unsynced_changes")


def get_section_ids(bp_id: str) -> list[str]:
    rows = _get(f"/courses/{bp_id}/blueprint_templates/default/associated_courses") or []
    if not isinstance(rows, list):
        return []
    return [str(r.get("id")) for r in rows if isinstance(r, dict) and r.get("id")]


def _slug_from(change: dict) -> str | None:
    """Page slug from the ChangeRecord html_url (.../pages/<slug>)."""
    url = change.get("html_url") or ""
    return url.split("/pages/")[-1] if "/pages/" in url else None


# ---------------------------------------------------------------------------
# Per-change analysis
# ---------------------------------------------------------------------------

def analyze_page(bp_id: str, slug: str, section_ids: list[str]) -> list[str]:
    """Sections whose copy is a LOCAL EDIT (hash matches no blueprint revision).
    Sections merely behind (hash matches a past revision) are NOT returned."""
    rev_hashes = get_page_revision_hashes(bp_id, slug)
    edited: list[str] = []
    for sid in section_ids:
        sec = get_page_with_body(sid, slug)
        if not sec:
            continue  # missing in section → sync will create it; not a skip risk
        sec_hash = _hash(sec.get("body"))
        if rev_hashes and sec_hash not in rev_hashes:
            edited.append(sid)
        # if rev_hashes is empty (revision fetch failed) we can't judge → skip silently
    return edited


def run_preflight(bp_id: str, section_ids: list[str]) -> dict:
    changes = get_unsynced_changes(bp_id)
    if changes is None:
        return {"verdict": "error"}
    if not changes:
        return {"verdict": "nothing_pending", "pending": 0,
                "at_risk": [], "unverifiable": [], "other": []}

    at_risk: list[dict] = []        # confirmed page local-edits
    unverifiable: list[dict] = []   # unlocked assignment/quiz/discussion content changes
    other: list[dict] = []          # locked, non-content, or non-evaluable types

    for c in changes:
        atype = (c.get("asset_type") or "").lower()
        ctype = (c.get("change_type") or "").lower()
        rec = {"asset_id": c.get("asset_id"), "asset_type": c.get("asset_type"),
               "asset_name": c.get("asset_name"), "change_type": c.get("change_type"),
               "locked": c.get("locked")}
        if c.get("locked"):
            rec["why"] = "locked — Canvas will force-overwrite (not at risk)"
            other.append(rec); continue
        if ctype not in _CONTENT_CHANGES:
            rec["why"] = f"change_type '{ctype}' — not a content overwrite"
            other.append(rec); continue
        if atype in _PRECISE:
            slug = _slug_from(c)
            edited = analyze_page(bp_id, slug, section_ids) if slug else []
            if edited:
                rec["sections_local_edit"] = edited
                rec["confidence"] = "confirmed (no revision provenance in these sections)"
                at_risk.append(rec)
            # else: all sections merely behind → will sync → not flagged
        elif atype in _UNVERIFIABLE:
            rec["why"] = "no /revisions trail — can't tell 'behind' from 'locally edited' pre-sync"
            unverifiable.append(rec)
        else:
            rec["why"] = f"asset_type '{atype}' — not content-evaluated"
            other.append(rec)

    if at_risk:
        verdict = "at_risk"
    elif unverifiable:
        verdict = "review"
    else:
        verdict = "ready"
    return {"verdict": verdict, "pending": len(changes),
            "at_risk": at_risk, "unverifiable": unverifiable, "other": other}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_GLYPH = {"ready": "✅", "at_risk": "🔴", "review": "⚠️", "nothing_pending": "✅"}


def _lock_lines(bp_id: str, recs: list[dict]) -> list[str]:
    out: list[str] = []
    for r in recs:
        ct = ASSET_TYPE_MAP.get(r["asset_type"])
        if ct:
            out.append(f"# lock '{r['asset_name']}' ({r['asset_type']} {r['asset_id']})")
            out.append(_format_lock_curl(bp_id, ct, r["asset_id"]))
        else:
            out.append(f"# (no restrict_item content_type for asset_type "
                       f"'{r['asset_type']}' — lock '{r['asset_name']}' in the UI)")
    return out


def _render(bp_id: str, r: dict, suggest: bool, ts: str) -> list[str]:
    v = r["verdict"]
    lines = [
        "# Blueprint Pre-Sync Lock-Readiness Check",
        "",
        f"Blueprint: {bp_id}",
        f"Run at:    {ts}",
        "",
        "=" * 62,
        "",
        f"Verdict: {_GLYPH[v]} {v.upper()}   ({r.get('pending', 0)} pending change(s))",
        "",
    ]
    if v == "nothing_pending":
        lines.append("No pending unsynced changes — nothing to sync, nothing at risk.")
        return lines

    if r["at_risk"]:
        lines.append("🔴 WILL BE SKIPPED (unlocked + locally edited in a section) — lock before syncing:")
        for x in r["at_risk"]:
            lines.append(f"  • {x['asset_name']}  ({x['asset_type']} {x['asset_id']})")
            lines.append(f"      local edits in section(s): {', '.join(x['sections_local_edit'])}")
        lines.append("")
    if r["unverifiable"]:
        lines.append("⚠️  CAN'T PRE-VERIFY (no revision trail for these asset types):")
        for x in r["unverifiable"]:
            lines.append(f"  • {x['asset_name']}  ({x['asset_type']} {x['asset_id']})")
        lines += [
            "    These WILL be skipped in any section that has locally edited them — but the",
            "    API can't tell pre-sync. Options: (1) lock them now to be safe (force-overwrite),",
            "    or (2) sync once, then run blueprint_exception_report.py to see actual skips.",
            "",
        ]
    if not r["at_risk"] and not r["unverifiable"]:
        lines.append("✅ No unlocked content changes at risk. Pending changes are locked, "
                     "non-content, or pages confirmed merely behind (will sync cleanly).")
        lines.append("")

    if r["other"]:
        lines.append(f"({len(r['other'])} pending change(s) not at risk: locked / non-content / "
                     "non-evaluated — see --json for detail.)")

    if suggest and (r["at_risk"] or r["unverifiable"]):
        lines += ["", "─" * 62, "# --suggest-locks: run these BEFORE syncing, then sync once.",
                  "# (Reuses the #28 restrict_item mapping. Confirmed-risk first, then precautionary.)"]
        lines += _lock_lines(bp_id, r["at_risk"])
        if r["unverifiable"]:
            lines.append("# precautionary (can't pre-verify — lock only if these were section-edited):")
            lines += _lock_lines(bp_id, r["unverifiable"])
    return lines


def _write_report(path: Path, body: str) -> None:
    path.write_text(body + "\n", encoding="utf-8")
    print(f"\nReport written to {path}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Pre-sync Blueprint lock-readiness preflight (read-only): predicts "
                    "which pending changes will be silently skipped + suggests locks.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--bp", "--blueprint", dest="bp", default=None,
                    help="Blueprint course ID (or set BLUEPRINT_COURSE_ID)")
    ap.add_argument("--suggest-locks", action="store_true",
                    help="Emit a restrict_item lock script for the at-risk items")
    ap.add_argument("--report", default=None, metavar="PATH", help="Write output to PATH")
    ap.add_argument("--json", action="store_true", dest="emit_json", help="Machine-readable JSON")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="(Read-only; advisory guard. Accepted for symmetry.)")
    args = ap.parse_args()

    if not CANVAS_BASE_URL or CANVAS_BASE_URL == "https://" or not CANVAS_API_TOKEN:
        print("ERROR: set CANVAS_BASE_URL and CANVAS_API_TOKEN in .env.")
        sys.exit(2)
    bp_id = (args.bp or os.environ.get("BLUEPRINT_COURSE_ID", "")).strip()
    if not bp_id:
        print("ERROR: blueprint course ID not set. Pass --bp <id> or set BLUEPRINT_COURSE_ID.")
        sys.exit(2)

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=bp_id,
                  mode="read", allow_override=args.allow_enrolled, label="blueprint")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    section_ids = get_section_ids(bp_id)
    if not section_ids:
        print(f"\nNo associated sections found for blueprint {bp_id} (or it's not a "
              "blueprint / unreadable).", file=sys.stderr)
        sys.exit(2)

    r = run_preflight(bp_id, section_ids)
    if r["verdict"] == "error":
        print(f"\nCould not read unsynced_changes for blueprint {bp_id}.", file=sys.stderr)
        sys.exit(2)

    if args.emit_json:
        payload = {"tool": "blueprint_presync_check", "tool_version": __version__,
                   "run_at": ts, "blueprint": bp_id, "sections": section_ids, **r}
        out = json.dumps(payload, indent=2, ensure_ascii=False)
        print(out)
        if args.report:
            _write_report(Path(args.report), out)
    else:
        lines = _render(bp_id, r, args.suggest_locks, ts)
        print("\n".join(lines))
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    sys.exit(0 if r["verdict"] in ("ready", "nothing_pending") else 1)


if __name__ == "__main__":
    main()

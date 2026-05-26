#!/usr/bin/env python3
"""
blueprint_orphan_pages.py — post-sync Page-level integrity audit (#29 Phase 1)

After a Canvas Blueprint sync, Canvas's UI sync can leave per-section
PAGES in two specific broken states the migration log does NOT report:

  Detector A — `-N` slug orphans:
    Canvas auto-suffixes a slug (`-2`, `-2-2`, `-N`…) when re-pushing a
    Blueprint-locked page into a section that previously deleted its
    copy. The new `-N` page holds canonical content; the unsuffixed slug
    (which the module item still points at) keeps stale section-local
    content. Students see stale; the canonical material exists but is
    unreachable via navigation. 5-point fingerprint:
      1. A has slug ending `-\\d+` (or `-\\d+-\\d+` for repeats); B is unsuffixed
      2. A and B share the same title
      3. A's body hash matches the blueprint's canonical body (at B's slug)
      4. B's body hash differs from blueprint's canonical body
      5. A is NOT linked from any module item; B IS

  Detector B — silent body reversion (no orphan slug):
    Observed 2026-05-20: a locked page's body in a section was silently
    overwritten with a body hash that does NOT exist in the blueprint's
    revision history (the "no provenance in blueprint" signal — points
    at cross-section contamination via the master-link). Migration log
    says state: completed, zero exceptions. Detector B reports section
    pages whose current body has no provenance in blueprint's revision
    history (the strongest signal); plain drift is left to
    validate_blueprint_sync.py.

When Detector B fires, an operator warning is printed: Canvas-side
behavior contradicts the public docs; do NOT run a Blueprint UI sync
that only carries lock-state metadata (no body diffs) — that is the
sync path observed to cause the reversion.

Phase 1 (this tool, now): READ-ONLY DETECTION. No --apply.
Phase 2 (deferred to a separate ticket): --apply for the orphan
unlock/write/re-lock cleanup. Cleanup touches Blueprint locks and a
mid-sequence failure could leave items half-unlocked; it should not
ship without first exercising Phase 1 detection against a real course.

Endpoints used (all GET, read-only):
  GET /courses/:bp_id/pages                                  (list)
  GET /courses/:bp_id/pages/:slug                            (body)
  GET /courses/:bp_id/pages/:slug/revisions                  (revision history)
  GET /courses/:section_id/pages                             (list)
  GET /courses/:section_id/pages/:slug                       (body)
  GET /courses/:section_id/modules?include[]=items           (linked slugs)

Exit codes:
  0  no findings
  1  at least one orphan or reversion finding
  2  configuration error / cannot run

Usage:
    uv run python canvas_toolbox/lib/tools/blueprint_orphan_pages.py
    uv run python canvas_toolbox/lib/tools/blueprint_orphan_pages.py --report

Requires in .env:
    CANVAS_API_TOKEN, CANVAS_BASE_URL, BLUEPRINT_COURSE_ID,
    and at least one S{N}_COURSE_ID

Verification note (honest): end-to-end requires a live Blueprint with at
least one associated section that has completed a sync. canvas-toolbox
itself has no live course — static + argparse verification only when
developed here.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
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

# A slug "ends with -N" or "-N-N" (Canvas's documented suffix patterns).
_N_SUFFIX_RE = re.compile(r"-\d+(?:-\d+)*$")


# ---------------------------------------------------------------------------
# API helpers (style matches validate_blueprint_sync / blueprint_exception_report)
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
    out: dict[str, str] = {}
    for key, val in os.environ.items():
        if key.startswith("S") and key.endswith("_COURSE_ID") and val:
            label = key[: -len("_COURSE_ID")].lower()
            if len(label) >= 2 and label[1:].isdigit():
                out[label] = val
    return dict(sorted(out.items()))


def _hash(body: str | None) -> str:
    """Match the issue's notation (sha256 first 10 hex chars)."""
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()[:10]


# ---------------------------------------------------------------------------
# Page + module fetchers
# ---------------------------------------------------------------------------

def list_pages(course_id: str) -> list[dict]:
    """Page list (metadata only — body NOT included; fetch per-page for body)."""
    return _get(f"/courses/{course_id}/pages") or []


def get_page_with_body(course_id: str, slug: str) -> dict | None:
    """Single page including body."""
    res = _get(f"/courses/{course_id}/pages/{slug}")
    return res if isinstance(res, dict) else None


def get_page_revision_hashes(course_id: str, slug: str) -> set[str]:
    """Hashes of every body in this page's revision history.

    The revisions LIST endpoint does NOT include `body` (it returns only
    edited_by / latest / revision_id / updated_at), so each revision's body
    must be fetched individually via the per-revision detail endpoint with
    `summary=false` (issue #32 — the LIST-only version always returned an
    empty set, which made Detector B mislabel every drift as a reversion).
    This is N+1 requests per divergent page, so it is only called on the
    divergence path. Empty set on error (defensive — never block on a
    revision fetch failure)."""
    revs = _get(f"/courses/{course_id}/pages/{slug}/revisions") or []
    hashes: set[str] = set()
    for r in revs:
        if not isinstance(r, dict):
            continue
        body = r.get("body")  # absent on the LIST endpoint; present if Canvas ever adds it
        if body is None:
            rid = r.get("revision_id")
            if rid is None:
                continue
            full = _get(
                f"/courses/{course_id}/pages/{slug}/revisions/{rid}",
                {"summary": "false"},
            )
            body = full.get("body") if isinstance(full, dict) else None
        if body is not None:
            hashes.add(_hash(body))
    return hashes


def get_module_linked_slugs(course_id: str) -> set[str]:
    """Set of Page slugs referenced from any module item in the course."""
    mods = _get(f"/courses/{course_id}/modules", {"include[]": "items"}) or []
    linked: set[str] = set()
    for m in mods:
        for it in m.get("items") or []:
            if it.get("type") == "Page":
                slug = it.get("page_url")
                if slug:
                    linked.add(slug)
    return linked


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def detect_orphan_n_slugs(
    bp_id: str, section_id: str,
    section_pages: list[dict], section_linked_slugs: set[str],
) -> list[dict]:
    """Detector A — 5-point fingerprint. Returns list of orphan findings."""
    findings: list[dict] = []
    by_title: dict[str, list[dict]] = defaultdict(list)
    for p in section_pages:
        by_title[p.get("title") or ""].append(p)

    for title, pages in by_title.items():
        if len(pages) < 2 or not title:
            continue

        suffixed = [p for p in pages if _N_SUFFIX_RE.search(p.get("url") or "")]
        unsuffixed = [p for p in pages
                      if not _N_SUFFIX_RE.search(p.get("url") or "")]
        # Unambiguous: exactly one of each
        if len(suffixed) != 1 or len(unsuffixed) != 1:
            findings.append({
                "kind": "ambiguous",
                "title": title,
                "section_id": section_id,
                "slugs": [p.get("url") for p in pages],
                "note": "title group has >1 suffixed or >1 unsuffixed page — "
                        "human review required (not a clean fingerprint).",
            })
            continue

        a = suffixed[0]    # orphan candidate
        b = unsuffixed[0]  # canonical-slug candidate
        a_full = get_page_with_body(section_id, a["url"])
        b_full = get_page_with_body(section_id, b["url"])
        bp_full = get_page_with_body(bp_id, b["url"])
        if not (a_full and b_full and bp_full):
            findings.append({
                "kind": "fetch_failed",
                "title": title,
                "section_id": section_id,
                "note": "could not fetch one of A/B/blueprint bodies for the check.",
            })
            continue

        a_hash = _hash(a_full.get("body"))
        b_hash = _hash(b_full.get("body"))
        bp_hash = _hash(bp_full.get("body"))

        check_a_matches_bp = (a_hash == bp_hash)
        check_b_differs_bp = (b_hash != bp_hash)
        check_a_not_in_mod = a["url"] not in section_linked_slugs
        check_b_in_mod     = b["url"] in section_linked_slugs

        all_match = all([check_a_matches_bp, check_b_differs_bp,
                          check_a_not_in_mod, check_b_in_mod])
        findings.append({
            "kind": "orphan_match" if all_match else "partial_match",
            "title": title,
            "section_id": section_id,
            "orphan_slug": a["url"],
            "canonical_slug": b["url"],
            "blueprint_slug": b["url"],
            "a_hash": a_hash, "b_hash": b_hash, "bp_hash": bp_hash,
            "checks": {
                "A_body_matches_blueprint": check_a_matches_bp,
                "B_body_differs_from_blueprint": check_b_differs_bp,
                "A_not_in_any_module": check_a_not_in_mod,
                "B_in_a_module": check_b_in_mod,
            },
        })
    return findings


def detect_body_reversions(
    bp_id: str, section_id: str, bp_pages: list[dict],
) -> list[dict]:
    """Detector B — section body has no provenance in blueprint's revision
    history (the strongest reversion signal). Plain drift (section differs
    from blueprint current but matches a past revision) is intentionally NOT
    reported here — validate_blueprint_sync covers that."""
    findings: list[dict] = []
    for bp_p in bp_pages:
        slug = bp_p.get("url")
        if not slug:
            continue
        sec_page = get_page_with_body(section_id, slug)
        if not sec_page:
            continue  # missing in section is drift (validate_blueprint_sync's beat)
        # Lock-status gate (issue #32 Bug 2). A "reversion" verdict is only
        # meaningful for a Blueprint-content-LOCKED page — there the section
        # body is supposed to track the blueprint, so losing that content is
        # the reversion signal (the 2026-05-20 W01 incident was content-locked).
        # On an UNLOCKED page the section legitimately owns its content and
        # divergence is expected (every course has a section-specific homepage),
        # so don't flag it.
        restrictions = sec_page.get("blueprint_item_restrictions") or {}
        content_locked = (bool(sec_page.get("restricted_by_master_course"))
                          and bool(restrictions.get("content")))
        if not content_locked:
            continue
        bp_full = get_page_with_body(bp_id, slug)
        if not bp_full:
            continue
        sec_hash = _hash(sec_page.get("body"))
        bp_hash  = _hash(bp_full.get("body"))
        if sec_hash == bp_hash:
            continue  # match — fine
        # Section differs from blueprint current. Check revision history.
        rev_hashes = get_page_revision_hashes(bp_id, slug)
        if sec_hash in rev_hashes:
            # historically derived from blueprint — drift, not reversion;
            # let validate_blueprint_sync own it
            continue
        # NO provenance in blueprint — the reversion signal
        findings.append({
            "kind": "reversion_no_provenance",
            "title": bp_p.get("title") or slug,
            "section_id": section_id,
            "slug": slug,
            "section_body_hash": sec_hash,
            "blueprint_current_hash": bp_hash,
            "blueprint_revision_count": len(rev_hashes),
        })
    return findings


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_orphans(label: str, section_id: str, findings: list[dict]) -> list[str]:
    out: list[str] = []
    matches = [f for f in findings if f.get("kind") == "orphan_match"]
    partials = [f for f in findings if f.get("kind") == "partial_match"]
    others   = [f for f in findings if f.get("kind") not in
                ("orphan_match", "partial_match")]

    if not findings:
        out.append(f"  Detector A — `-N` slug orphans: ✅ none")
        return out

    out.append(f"  Detector A — `-N` slug orphans: {len(matches)} match, "
               f"{len(partials)} partial, {len(others)} other")
    for m in matches:
        out.append(f"    🔴 ORPHAN '{m['title']}'")
        out.append(f"        orphan slug:    {m['orphan_slug']}  body={m['a_hash']}")
        out.append(f"        canonical slug: {m['canonical_slug']}  body={m['b_hash']}")
        out.append(f"        blueprint body:                          {m['bp_hash']}")
    for p in partials:
        out.append(f"    ⚠️  PARTIAL '{p['title']}' — fingerprint did not fully match:")
        out.append(f"        orphan={p['orphan_slug']} canonical={p['canonical_slug']}")
        out.append(f"        checks: {p['checks']}")
    for o in others:
        out.append(f"    ⚠️  {o['kind'].upper()} '{o['title']}' — {o.get('note', '')}")
    return out


def _render_reversions(label: str, section_id: str, findings: list[dict]) -> list[str]:
    out: list[str] = []
    if not findings:
        out.append("  Detector B — body reversion (no provenance in blueprint): ✅ none")
        return out
    out.append(f"  Detector B — body reversion (no provenance in blueprint): "
               f"🔴 {len(findings)} page(s)")
    for f in findings:
        out.append(f"    🔴 REVERTED '{f['title']}'  slug={f['slug']}")
        out.append(f"        section body hash:    {f['section_body_hash']}  "
                   f"(NOT in blueprint's {f['blueprint_revision_count']}-revision history)")
        out.append(f"        blueprint current:    {f['blueprint_current_hash']}")
    return out


def _operator_warning() -> list[str]:
    return [
        "",
        "=" * 62,
        "⚠️  OPERATOR WARNING (#29 follow-up evidence, 2026-05-20):",
        "",
        "Detector B fired — a Canvas Blueprint sync has overwritten a section",
        "page with a body that does NOT exist in the blueprint's revision",
        "history. This behavior contradicts the public Canvas docs",
        "('Changed content will always overwrite the existing content in the",
        "associated courses for all locked objects') and was reproduced",
        "deterministically on the lock-state-only sync path.",
        "",
        "Until Canvas's behavior is understood:",
        "  Do NOT run a Blueprint UI sync that only carries lock-state",
        "  metadata changes (no body diffs). Sync only when you intentionally",
        "  edited the blueprint body — that is the path observed to cause the",
        "  reversion.",
        "=" * 62,
    ]


def _write_report(path: Path, body: str) -> None:
    path.write_text(body + "\n", encoding="utf-8")
    print(f"\nReport written to {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Post-sync Page-level integrity audit: `-N` slug orphans "
                    "and silent body reversions (#29 Phase 1, read-only)"
    )
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    ap.add_argument("--report", action="store_true",
                    help="write findings to blueprint_orphan_pages.md")
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

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    section_list = ", ".join(f"{lbl} ({cid})" for lbl, cid in sections.items())
    header_lines = [
        "# Blueprint Orphan Pages — Phase 1 Audit",
        "",
        f"Blueprint: {BLUEPRINT_COURSE_ID}",
        f"Sections:  {section_list}",
        f"Run at:    {ts}",
        "",
        "Detector A — `-N` slug orphan fingerprint (5-point)",
        "Detector B — silent body reversion (no provenance in blueprint revisions)",
        "",
        "Phase 1 = READ-ONLY DETECTION. Cleanup (--apply) is deferred to Phase 2.",
        "",
        "=" * 62,
    ]
    for line in header_lines:
        print(line)

    bp_pages = list_pages(BLUEPRINT_COURSE_ID)
    if not bp_pages:
        print(f"\nNo pages found on Blueprint {BLUEPRINT_COURSE_ID} "
              "(or fetch failed). Nothing to check.")
        sys.exit(2)

    body_lines: list[str] = []
    any_findings = False
    any_reversions = False

    for label, sid in sections.items():
        body_lines.append("")
        section_header = f"## {label.upper()} (course {sid})"
        print("\n" + section_header)
        body_lines.append(section_header)

        section_pages = list_pages(sid)
        section_linked = get_module_linked_slugs(sid)

        orphan_findings = detect_orphan_n_slugs(
            BLUEPRINT_COURSE_ID, sid, section_pages, section_linked
        )
        for line in _render_orphans(label, sid, orphan_findings):
            print(line)
            body_lines.append(line)
        if any(f.get("kind") == "orphan_match" for f in orphan_findings):
            any_findings = True

        reversion_findings = detect_body_reversions(
            BLUEPRINT_COURSE_ID, sid, bp_pages
        )
        for line in _render_reversions(label, sid, reversion_findings):
            print(line)
            body_lines.append(line)
        if reversion_findings:
            any_findings = True
            any_reversions = True

    if any_reversions:
        warning = _operator_warning()
        for line in warning:
            print(line)
        body_lines.extend(warning)

    print("\n" + "=" * 62)
    if any_findings:
        print("🔴 Findings present. Phase 2 (--apply cleanup) is NOT yet "
              "implemented — manual remediation required.")
        print("    Orphan cleanup pattern (unlock → PUT canonical body onto "
              "unsuffixed slug → DELETE -N orphan → re-lock); see issue #29.")
        body_lines.append("")
        body_lines.append("=" * 62)
        body_lines.append("Findings present. Phase 2 cleanup deferred.")
    else:
        print("✅ No orphan or reversion findings.")
        body_lines.append("")
        body_lines.append("✅ No findings.")

    if args.report:
        _write_report(
            Path("blueprint_orphan_pages.md"),
            "\n".join(header_lines + body_lines),
        )

    sys.exit(1 if any_findings else 0)


if __name__ == "__main__":
    main()

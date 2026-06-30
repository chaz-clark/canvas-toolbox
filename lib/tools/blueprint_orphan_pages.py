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

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
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
MASTER_COURSE_ID    = os.environ.get("MASTER_COURSE_ID", "")

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
# Phase 2 — multi-suffix detection + executor (#40)
# ---------------------------------------------------------------------------
#
# Phase 1 (above) is read-only and emits "ambiguous" findings for the
# multi-suffix case (2+ `-N` siblings + 1 unsuffixed, often all linked). DS250's
# 2026-06-02 production run validated a content-aware cleanup for that case;
# Phase 2 generalizes that script. See:
#   - issue #40
#   - ds250-onln-master/tools/fix_overview_dupes.py (reference impl)
#   - handoffs/HANDOFF_ds250-onln-master-blueprint-orphan-phase2-review.md
#   - lib/tools/_orphan_phase2.py (planner — pure function, unit-tested)


def detect_multi_suffix_cleanable(
    master_id: str, target_id: str,
    target_pages: list[dict], target_linked_slugs: set[str],
    master_canonical_bodies: dict[str, str],
) -> list[dict]:
    """Phase 2 detection — runs against either Blueprint or Section.

    Emits `multi_suffix_cleanable` findings when:
      - same-title group has exactly 1 unsuffixed slug AND >= 1 suffixed slugs
      - Master has a canonical body for the title (titles without one are
        skipped — the W12 Teaching Notes pattern)

    The `unsuffixed_stale` sub-flag is True when the kept (unsuffixed) page's
    body differs from Master's canonical body. That sub-flag is exactly the
    #41 data-loss surface — the planner surfaces it distinctly so an operator
    can verify before apply.

    Distinct from Phase 1's `orphan_match`: Phase 1 requires the strict 5-point
    fingerprint (one suffixed orphan unlinked + canonical fingerprint match).
    Phase 2 is the looser case where multiple suffixed siblings exist and
    Phase 1 would call it `ambiguous`. Both can co-occur; the planner accepts
    either kind.
    """
    findings: list[dict] = []
    by_title: dict[str, list[dict]] = defaultdict(list)
    for p in target_pages:
        by_title[p.get("title") or ""].append(p)

    for title, pages in by_title.items():
        if not title or len(pages) < 2:
            continue
        if title not in master_canonical_bodies:
            # No Master canonical → skip. Instructor-only / non-blueprint-canonical
            # pages have no auto-fix candidate.
            continue

        suffixed = [p for p in pages if _N_SUFFIX_RE.search(p.get("url") or "")]
        unsuffixed = [p for p in pages
                      if not _N_SUFFIX_RE.search(p.get("url") or "")]
        if len(unsuffixed) != 1 or len(suffixed) < 1:
            # Phase 1's `ambiguous` covers 0 or >1 unsuffixed. Phase 2 won't
            # touch those — they need human review.
            continue

        keep_slug = unsuffixed[0]["url"]
        keep_full = get_page_with_body(target_id, keep_slug)
        if not keep_full:
            continue
        keep_hash = _hash(keep_full.get("body"))
        master_hash = _hash(master_canonical_bodies[title])
        unsuffixed_stale = (keep_hash != master_hash)

        findings.append({
            "kind": "multi_suffix_cleanable",
            "title": title,
            "section_id": target_id,
            "canonical_slug": keep_slug,
            "suffixed_slugs": [p["url"] for p in suffixed],
            "unsuffixed_stale": unsuffixed_stale,
            "keep_hash": keep_hash,
            "master_hash": master_hash,
            "all_slugs_linked": all(p["url"] in target_linked_slugs for p in pages),
        })
    return findings


def fetch_master_canonical_bodies(
    master_id: str, titles_of_interest: set[str] | None = None,
) -> dict[str, str]:
    """Build a title -> body dict from Master. If `titles_of_interest` is set,
    only fetch bodies for those titles (saves N+1 GETs across an 80-page Master).
    """
    out: dict[str, str] = {}
    if not master_id:
        return out
    master_pages = list_pages(master_id)
    for p in master_pages:
        t = p.get("title") or ""
        if not t:
            continue
        if titles_of_interest is not None and t not in titles_of_interest:
            continue
        full = get_page_with_body(master_id, p["url"])
        if full is None:
            continue
        # If Master has duplicates of a title (shouldn't, but guard), the last
        # one wins. That's a deliberate "trust Master to be clean" assumption
        # per #40 — Master is the canonical source.
        out[t] = full.get("body") or ""
    return out


def get_module_items_by_slug(
    course_id: str,
) -> dict[str, list[tuple[str, str, int]]]:
    """slug -> list of (module_id, item_id, position) for Page-type items."""
    mods = _get(f"/courses/{course_id}/modules", {"include[]": "items"}) or []
    out: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for m in mods:
        for it in m.get("items") or []:
            if it.get("type") != "Page":
                continue
            slug = it.get("page_url")
            if not slug:
                continue
            out[slug].append((m["id"], it["id"], it.get("position", 999)))
    return dict(out)


def apply_plan(
    plan: list, target_id: str, master_id: str,
    dry_run: bool, allow_enrolled: bool,
) -> dict:
    """Execute (or simulate) a Phase 2 plan against a single target course.

    Constraints (non-negotiable per #40):
      - Master is never modified — refuses to write if target_id == master_id.
      - `canvas_course_guard.enforce()` runs first; --allow-enrolled is required
        for courses with student enrollments (L12).
      - Per-op try/except. On 403/400 with "locked" in the response, the item
        is skipped+reported (NOT inline-unlocked — that dance is parked, see
        handoffs/parkinglot.md `blueprint_orphan_pages.py inline-unlock dance`).
      - Fault-tolerant: never half-corrupts. Each mutation is independently safe.

    Returns a report dict with counts + failure list.
    """
    if str(target_id) == str(master_id):
        raise RuntimeError(
            f"Refusing to apply against Master ({master_id}). Master is "
            f"the canonical source and must never be modified."
        )

    # Guard. Runs even on dry_run so the operator sees the verdict.
    try:
        from canvas_course_guard import enforce as _course_guard
        _course_guard(
            CANVAS_BASE_URL, _headers(), str(target_id),
            mode="write" if not dry_run else "read",
            allow_override=allow_enrolled,
            label=f"target course",
        )
    except SystemExit:
        # Guard refused. Propagate so the caller stops before any further work.
        raise

    counts = {
        "overwrite": 0,
        "delete_module_item": 0,
        "delete_page": 0,
        "cross_course_link_warning": 0,
        "skipped_locked": 0,
        "http_failure": 0,
    }
    failures: list[dict] = []

    for step in plan:
        if step.kind == "CrossCourseLinkWarning":
            counts["cross_course_link_warning"] += 1
            print(f"    ⚠ cross-course-link warning on {step.slug!r}: "
                  f"{step.cross_course_link_count} ref(s) to "
                  f"/courses/{step.cross_course_master_id}/… in canonical body. "
                  f"Sample: {step.cross_course_link_samples[:1]}")
            continue

        if step.kind == "OverwriteBody":
            label = f"PUT body {step.target_id}/pages/{step.slug}"
            if dry_run:
                counts["overwrite"] += 1
                print(f"    [dry-run] {label}  (overwrite with Master canonical)")
                continue
            try:
                r = requests.put(
                    f"{CANVAS_BASE_URL}/api/v1/courses/{step.target_id}/pages/{step.slug}",
                    headers=_headers(),
                    json={"wiki_page": {"body": step.body}},
                    timeout=30,
                )
                if r.status_code in (400, 403):
                    counts["skipped_locked"] += 1
                    failures.append({"step": label, "status": r.status_code,
                                     "note": "LOCKED (skip+report; unlock dance parked)"})
                    print(f"    ✗ LOCKED (needs unlock pass): {label}")
                    continue
                r.raise_for_status()
                counts["overwrite"] += 1
                print(f"    ✓ {label}")
            except requests.HTTPError as e:
                counts["http_failure"] += 1
                failures.append({"step": label, "status": e.response.status_code})
                print(f"    ✗ HTTP {e.response.status_code}: {label}")

        elif step.kind == "DeleteModuleItem":
            label = (f"DELETE module-item {step.target_id}/modules/"
                     f"{step.module_id}/items/{step.item_id}")
            if dry_run:
                counts["delete_module_item"] += 1
                print(f"    [dry-run] {label}  ({step.note})")
                continue
            try:
                r = requests.delete(
                    f"{CANVAS_BASE_URL}/api/v1/courses/{step.target_id}/modules/"
                    f"{step.module_id}/items/{step.item_id}",
                    headers=_headers(), timeout=20,
                )
                if r.status_code in (400, 403):
                    counts["skipped_locked"] += 1
                    failures.append({"step": label, "status": r.status_code,
                                     "note": "LOCKED (skip+report)"})
                    print(f"    ✗ LOCKED: {label}")
                    continue
                if r.status_code == 404:
                    print(f"    ⚬ already gone: {label}")
                    continue
                r.raise_for_status()
                counts["delete_module_item"] += 1
                print(f"    ✓ {label}")
            except requests.HTTPError as e:
                counts["http_failure"] += 1
                failures.append({"step": label, "status": e.response.status_code})
                print(f"    ✗ HTTP {e.response.status_code}: {label}")

        elif step.kind == "DeletePage":
            label = f"DELETE page {step.target_id}/pages/{step.slug}"
            if dry_run:
                counts["delete_page"] += 1
                print(f"    [dry-run] {label}  ({step.note})")
                continue
            try:
                r = requests.delete(
                    f"{CANVAS_BASE_URL}/api/v1/courses/{step.target_id}/pages/{step.slug}",
                    headers=_headers(), timeout=20,
                )
                if r.status_code in (400, 403):
                    counts["skipped_locked"] += 1
                    failures.append({"step": label, "status": r.status_code,
                                     "note": "LOCKED (skip+report)"})
                    print(f"    ✗ LOCKED: {label}")
                    continue
                if r.status_code == 404:
                    print(f"    ⚬ already gone: {label}")
                    continue
                r.raise_for_status()
                counts["delete_page"] += 1
                print(f"    ✓ {label}")
            except requests.HTTPError as e:
                counts["http_failure"] += 1
                failures.append({"step": label, "status": e.response.status_code})
                print(f"    ✗ HTTP {e.response.status_code}: {label}")

    return {"counts": counts, "failures": failures}


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
    # v0.32 — default-on PDF pair when output is markdown (faculty default).
    if path.suffix.lower() in (".md", ".markdown"):
        try:
            from _md_to_pdf import render_pair
            render_pair(path)
        except ImportError:
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _run_phase2_apply(args, sections: dict, scope_regex) -> None:
    """Phase 2 cleanup dispatch (#40). Targets: Blueprint + each section.
    Master is queried for canonical bodies but never modified.

    Apply order (per the DS250 design-review handoff): Blueprint first (canary
    — non-enrolled), then sections (enrolled, --allow-enrolled required).
    """
    from _orphan_phase2 import build_apply_plan, summarize_plan

    dry_run = not args.apply_write
    print("=" * 62)
    mode_label = "DRY-RUN" if dry_run else "APPLY (writes enabled)"
    print(f"Phase 2 — content-aware multi-suffix cleanup ({mode_label})")
    print(f"  Master (canonical, NEVER modified): {MASTER_COURSE_ID}")
    print(f"  Blueprint: {BLUEPRINT_COURSE_ID}")
    print(f"  Sections:  {', '.join(f'{lbl} ({cid})' for lbl, cid in sections.items())}")
    if scope_regex:
        print(f"  Scope filter: {scope_regex.pattern}")
    print("=" * 62)

    # Build the canonical-body cache once across the run. First pass: detect
    # what titles we care about by running Phase 2 detection against each
    # target with an empty canonical_bodies (which makes it skip all titles).
    # Second pass: fetch only the bodies for titles that actually have
    # multi-suffix groups somewhere in the fleet. Saves ~80 GETs on Master.
    pre_titles: set[str] = set()
    target_pages_cache: dict[str, list[dict]] = {}
    target_linked_cache: dict[str, set[str]] = {}
    targets = [("Blueprint", BLUEPRINT_COURSE_ID)] + list(sections.items())
    for label, tid in targets:
        pages = list_pages(tid)
        linked = get_module_linked_slugs(tid)
        target_pages_cache[tid] = pages
        target_linked_cache[tid] = linked
        # Identify multi-suffix candidate titles (don't need Master canonical
        # at this stage — just the structural signal).
        by_title: dict[str, list[dict]] = defaultdict(list)
        for p in pages:
            by_title[p.get("title") or ""].append(p)
        for title, group in by_title.items():
            if not title or len(group) < 2:
                continue
            suff = [p for p in group if _N_SUFFIX_RE.search(p.get("url") or "")]
            unsuff = [p for p in group
                       if not _N_SUFFIX_RE.search(p.get("url") or "")]
            if len(unsuff) == 1 and len(suff) >= 1:
                pre_titles.add(title)

    if not pre_titles:
        print("\n✓ No multi-suffix orphan groups detected across the fleet. "
              "Nothing to plan. Phase 2 is a no-op (idempotent).")
        return

    print(f"\nDetected {len(pre_titles)} candidate title(s) across the fleet. "
          f"Fetching Master canonicals...")
    canonical_bodies = fetch_master_canonical_bodies(
        MASTER_COURSE_ID, titles_of_interest=pre_titles,
    )
    print(f"  Master has canonical bodies for {len(canonical_bodies)} / "
          f"{len(pre_titles)} title(s). Skipping {len(pre_titles) - len(canonical_bodies)} "
          f"title(s) with no Master canonical (e.g. instructor-only pages).")

    # Per-target detection + planning + apply.
    combined = {"overwrite": 0, "delete_module_item": 0, "delete_page": 0,
                "cross_course_link_warning": 0}
    all_failures: list[dict] = []

    for label, tid in targets:
        print(f"\n--- {label} ({tid}) ---")
        findings = detect_multi_suffix_cleanable(
            MASTER_COURSE_ID, tid,
            target_pages_cache[tid], target_linked_cache[tid],
            canonical_bodies,
        )
        if not findings:
            print(f"  ✓ No multi-suffix cleanable groups in {label}.")
            continue
        items_by_slug = get_module_items_by_slug(tid)
        plan = build_apply_plan(
            tid, MASTER_COURSE_ID, findings,
            canonical_bodies, items_by_slug,
            scope_regex=scope_regex,
        )
        if not plan:
            print(f"  ✓ Detection found findings but all were filtered by "
                  f"scope_regex or no-Master-canonical rule.")
            continue
        per_target = summarize_plan(plan)
        print(f"  Plan: overwrite={per_target['overwrite']} pages, "
              f"delete {per_target['delete_module_item']} module-items, "
              f"delete {per_target['delete_page']} pages, "
              f"{per_target['cross_course_link_warning']} cross-course-link warning(s).")
        report = apply_plan(plan, tid, MASTER_COURSE_ID,
                            dry_run=dry_run, allow_enrolled=args.allow_enrolled)
        for k in combined:
            combined[k] += report["counts"].get(k, 0)
        all_failures.extend(report["failures"])

    print("\n" + "=" * 62)
    print("COMBINED TOTALS")
    print(f"  overwrite={combined['overwrite']} pages, "
          f"delete {combined['delete_module_item']} module-items, "
          f"delete {combined['delete_page']} pages")
    print(f"  cross-course-link warnings: {combined['cross_course_link_warning']}")
    if all_failures:
        print(f"\n⚠ {len(all_failures)} operation(s) failed or were skipped:")
        for f in all_failures[:20]:
            print(f"   [{f['status']}] {f['step']}"
                  + (f"   ({f.get('note')})" if f.get('note') else ""))
    print(f"\nMaster ({MASTER_COURSE_ID}) untouched."
          + ("  (dry-run — re-run with --apply --apply-write)" if dry_run else ""))


def main() -> None:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Post-sync Page-level integrity audit: `-N` slug orphans "
                    "and silent body reversions (#29 Phase 1, read-only) + "
                    "content-aware cleanup of multi-suffix orphans (#40 Phase 2)"
    )
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    ap.add_argument("--report", action="store_true",
                    help="write findings to blueprint_orphan_pages.md")
    ap.add_argument("--apply", action="store_true",
                    help="Phase 2 cleanup of multi-suffix orphans. Default: "
                         "dry-run. Pair with --apply-write to actually mutate "
                         "Canvas (otherwise --apply just plans + prints).")
    ap.add_argument("--apply-write", action="store_true",
                    help="Required with --apply to actually mutate Canvas. "
                         "Without this, --apply is a dry-run.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Override canvas_course_guard's enrollment block (L12). "
                         "Required when targeting a course with student "
                         "enrollments — most live sections.")
    ap.add_argument("--scope-titles", metavar="REGEX",
                    help="Limit Phase 2 cleanup to pages whose title matches "
                         "this regex (case-insensitive). Default: any title "
                         "Phase 2 detection surfaces that has a Master canonical.")
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
    if args.apply and not MASTER_COURSE_ID:
        missing.append("MASTER_COURSE_ID (required for --apply — canonical body source)")
    if missing:
        print("ERROR: Missing required configuration:")
        for m in missing:
            print(f"  {m}")
        print("\nSet these in your .env file.")
        sys.exit(2)

    # ----------------------------------------------------------------------
    # Phase 2 path — content-aware cleanup of multi-suffix orphans (#40).
    # Switches modes entirely: skips Phase 1 detection output. Default is
    # dry-run; --apply-write required to actually mutate Canvas.
    # ----------------------------------------------------------------------
    if args.apply:
        _run_phase2_apply(
            args, sections,
            scope_regex=re.compile(args.scope_titles, re.IGNORECASE)
            if args.scope_titles else None,
        )
        return

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

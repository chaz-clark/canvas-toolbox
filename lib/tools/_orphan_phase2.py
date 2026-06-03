"""Phase 2 of blueprint_orphan_pages (issue #40) — planner + step types.

This module is the *pure-function* half of Phase 2: take a list of Phase-2
detection findings + a per-title cache of Master canonical bodies, produce
an ordered list of Steps that an executor can run against Canvas.

By keeping the planner free of HTTP, it can be unit-tested against a captured
DS250 fixture (the gold-standard 2026-06-02 plan: overwrite=2, delete 40
module-items, delete 40 pages) without any Canvas API. The executor lives in
blueprint_orphan_pages.py where the existing API helpers already are.

Design constraints (from #40 + the DS250 design review handoff 2026-06-03):
  - Keep_slug is ALWAYS the single unsuffixed slug. Never falls back to
    position — that's exactly the #41 bug (BP dup at pos 1, canonical at pos 2).
  - Master is the canonical source of truth. Master is NEVER modified.
  - On stale unsuffixed keep_slug → OverwriteBody with Master's canonical body.
    Sub-flag `unsuffixed_stale` is the #41 data-loss surface — surfaced
    distinctly so operators can verify before apply.
  - Cross-course link scan: Master's body may contain /courses/{master}/…
    links. Overwriting injects them into a child. Emit a
    `CrossCourseLinkWarning` Step alongside any OverwriteBody whose body
    contains such links (the #39 surface — warn, don't block).
  - Whole-fleet scope is deliberately conservative: titles with no Master
    canonical are skipped (the W12 Teaching Notes pattern — instructor-only
    pages have no blueprint-canonical source so an OverwriteBody would be
    nonsensical).

What this module does NOT do:
  - No Canvas HTTP. The executor in blueprint_orphan_pages.py handles writes.
  - No lock-handling dance. v0.29.0 ships skip+report on 403/400; the inline
    unlock → write → re-lock dance is parked (see handoffs/parkinglot.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Step types
# ---------------------------------------------------------------------------

@dataclass
class Step:
    """One mutation step in a Phase 2 apply plan.

    `kind` is one of:
      - 'OverwriteBody'          — PUT canonical body onto kept page slug
      - 'DeleteModuleItem'       — DELETE one module item
      - 'DeletePage'             — DELETE a page (after its module items go)
      - 'CrossCourseLinkWarning' — non-mutating; emitted alongside OverwriteBody
                                   when Master's body contains /courses/{master}/
                                   refs (the #39 surface bleeding into #40)
    """
    kind: str
    target_id: str
    title: str
    slug: str | None = None
    module_id: str | None = None
    item_id: str | None = None
    position: int | None = None
    body: str | None = None
    cross_course_master_id: str | None = None
    cross_course_link_count: int = 0
    cross_course_link_samples: list[str] = field(default_factory=list)
    note: str | None = None


# ---------------------------------------------------------------------------
# Slug + body helpers
# ---------------------------------------------------------------------------

# A slug "ends with -N" or "-N-N" (Canvas's documented suffix patterns).
# Same as the existing blueprint_orphan_pages._N_SUFFIX_RE — kept local to
# avoid an import cycle with the main module.
_N_SUFFIX_RE = re.compile(r"-\d+(?:-\d+)*$")


def is_suffixed_slug(slug: str) -> bool:
    """True if the slug ends with -N or -N-N (Canvas's auto-suffix pattern)."""
    return bool(_N_SUFFIX_RE.search(slug or ""))


def scan_cross_course_links(body: str, master_id: str) -> tuple[int, list[str]]:
    """Find `/courses/{master_id}/...` references in `body`.

    Returns `(count, samples)` where `samples` is up to 3 URL paths for the
    finding note. Master's raw body is the source of truth for content but
    may carry course-id-stamped links — overwriting that body onto a child
    would inject those links (the #39 surface). We emit a warning, not a
    block — the operator decides what to do (typically: run the #39 remap
    afterward, or accept the warning for now).
    """
    if not body or not master_id:
        return 0, []
    pat = re.compile(rf"/courses/{re.escape(str(master_id))}/[^\s\"'<>)]*")
    matches = pat.findall(body)
    samples = list(dict.fromkeys(matches))[:3]  # dedupe + cap
    return len(matches), samples


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

def build_apply_plan(
    target_id: str,
    master_id: str,
    findings: list[dict],
    canonical_bodies: dict[str, str],
    module_items_by_slug: dict[str, list[tuple[str, str, int]]],
    scope_regex: re.Pattern | None = None,
) -> list[Step]:
    """Build an ordered list of Steps from Phase-2 findings.

    Args:
        target_id:           Course we are mutating (Blueprint or Section, never Master).
        master_id:           Master course id (NEVER mutated; used only as a marker).
        findings:            List of finding dicts from detect_multi_suffix_cleanable
                             (and/or detect_orphan_n_slugs `orphan_match` findings).
        canonical_bodies:    title -> Master's canonical body for that title.
                             Titles with no entry here are skipped (no-Master-canonical
                             rule — the W12 Teaching Notes pattern).
        module_items_by_slug: slug -> list of (module_id, item_id, position) for the
                              CURRENT target. Used to plan DeleteModuleItem steps for
                              each suffixed slug + the keep_slug's dup items.
        scope_regex:         If set, only titles matching this regex are included.

    Returns:
        Ordered list of Step objects. Order within a finding:
            1. CrossCourseLinkWarning (if any) — non-mutating, surfaced FIRST
            2. OverwriteBody (if unsuffixed_stale)
            3. DeleteModuleItem (for each suffixed slug's module items)
            4. DeletePage (for each suffixed slug)
            5. DeleteModuleItem (for kept slug's dup module items — collapse)

        Master safety: if `target_id == master_id`, raise ValueError (planner
        refuses to plan against Master).
    """
    if str(target_id) == str(master_id):
        raise ValueError(
            f"build_apply_plan refuses target_id={target_id} — Master must "
            f"never be modified. This is the non-negotiable Master-safety "
            f"assertion from #40."
        )

    plan: list[Step] = []
    for f in findings:
        kind = f.get("kind")
        if kind not in ("orphan_match", "multi_suffix_cleanable"):
            continue
        title = f.get("title") or ""
        if not title:
            continue
        if scope_regex and not scope_regex.search(title):
            continue
        # The DS250 design-review rule: no Master canonical -> skip (don't
        # invent an OverwriteBody from a non-blueprint source).
        canonical_body = canonical_bodies.get(title)
        if canonical_body is None:
            continue

        keep_slug = f.get("canonical_slug") or f.get("keep_slug")
        suffixed_slugs = f.get("suffixed_slugs") or (
            [f["orphan_slug"]] if f.get("orphan_slug") else []
        )
        # Defensive: keep_slug MUST be unsuffixed. Never silently fall back to
        # position — that's the #41 bug. If the finding doesn't have an
        # unsuffixed slug, refuse to plan it.
        if not keep_slug or is_suffixed_slug(keep_slug):
            continue

        # 1. Cross-course-link warning on the canonical body (Master's raw body).
        cc_count, cc_samples = scan_cross_course_links(canonical_body, master_id)
        if cc_count > 0:
            plan.append(Step(
                kind="CrossCourseLinkWarning",
                target_id=str(target_id),
                title=title,
                slug=keep_slug,
                cross_course_master_id=str(master_id),
                cross_course_link_count=cc_count,
                cross_course_link_samples=cc_samples,
                note=(
                    f"Master canonical body contains {cc_count} reference(s) to "
                    f"/courses/{master_id}/… — overwriting onto target {target_id} "
                    f"would inject these links. See #39."
                ),
            ))

        # 2. OverwriteBody if the kept slug is stale relative to canonical.
        if f.get("unsuffixed_stale"):
            plan.append(Step(
                kind="OverwriteBody",
                target_id=str(target_id),
                title=title,
                slug=keep_slug,
                body=canonical_body,
                note="kept slug body differs from Master canonical — overwrite with Master.",
            ))

        # 3 + 4. For each suffixed slug: delete its module items, then the page.
        for s in suffixed_slugs:
            for mod_id, item_id, position in module_items_by_slug.get(s, []):
                plan.append(Step(
                    kind="DeleteModuleItem",
                    target_id=str(target_id),
                    title=title,
                    slug=s,
                    module_id=str(mod_id),
                    item_id=str(item_id),
                    position=position,
                    note="suffixed orphan page's module item.",
                ))
            plan.append(Step(
                kind="DeletePage",
                target_id=str(target_id),
                title=title,
                slug=s,
                note="suffixed orphan page.",
            ))

        # 5. Collapse kept-slug dup module items: keep lowest position, delete the rest.
        keep_items = sorted(
            module_items_by_slug.get(keep_slug, []),
            key=lambda x: x[2] if x[2] is not None else 999,
        )
        for mod_id, item_id, position in keep_items[1:]:
            plan.append(Step(
                kind="DeleteModuleItem",
                target_id=str(target_id),
                title=title,
                slug=keep_slug,
                module_id=str(mod_id),
                item_id=str(item_id),
                position=position,
                note="kept slug has duplicate module item — keep lowest position.",
            ))

    return plan


# ---------------------------------------------------------------------------
# Plan summary (for dry-run output + sandbox-gate comparison)
# ---------------------------------------------------------------------------

def summarize_plan(plan: list[Step]) -> dict:
    """Return a counts dict matching the DS250 gold-standard format:
        overwrite_count, delete_module_item_count, delete_page_count,
        cross_course_link_warning_count.

    The DS250 2026-06-02 run reported across BP+S1+S2:
        overwrite=2 pages, delete 40 module-items, delete 40 pages.
    """
    return {
        "overwrite": sum(1 for s in plan if s.kind == "OverwriteBody"),
        "delete_module_item": sum(1 for s in plan if s.kind == "DeleteModuleItem"),
        "delete_page": sum(1 for s in plan if s.kind == "DeletePage"),
        "cross_course_link_warning": sum(
            1 for s in plan if s.kind == "CrossCourseLinkWarning"
        ),
    }

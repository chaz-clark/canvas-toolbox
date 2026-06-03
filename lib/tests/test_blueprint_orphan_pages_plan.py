"""Plan-builder tests for `_orphan_phase2.build_apply_plan`.

Pure-function tests (no Canvas API). The gold-standard fixture reconstructs
the DS250 2026-06-02 run captured in the design-review handoff:

    Combined dry-run (Blueprint + S1 + S2):
        overwrite=2 pages, delete 40 module-items, delete 40 pages
        Blueprint (415094):  overwrite=0, delete 8 items, delete 8 pages
        S1 (415194):         overwrite=1, delete 16 items, delete 16 pages
        S2 (415196):         overwrite=1, delete 16 items, delete 16 pages
    The 2 overwrites were `w01-u0-unit-overview` (stale in S1 and S2).

Idempotency is verified by re-running the planner against a "clean" state
(empty findings) — should produce zero Steps.
"""

import re
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _orphan_phase2 import (  # noqa: E402
    Step,
    build_apply_plan,
    scan_cross_course_links,
    summarize_plan,
    is_suffixed_slug,
)


# ---------------------------------------------------------------------------
# scan_cross_course_links — Master-link injection detector
# ---------------------------------------------------------------------------

def test_scan_cross_course_links_finds_master_refs():
    body = (
        '<p><a href="/courses/339374/pages/foo">A</a></p>'
        '<p><a href="/courses/339374/assignments/123">B</a></p>'
        '<p>plain text</p>'
    )
    count, samples = scan_cross_course_links(body, "339374")
    assert count == 2
    assert "/courses/339374/pages/foo" in samples
    assert "/courses/339374/assignments/123" in samples


def test_scan_cross_course_links_no_master_refs():
    body = '<p><a href="https://example.com">x</a></p>'
    count, samples = scan_cross_course_links(body, "339374")
    assert count == 0
    assert samples == []


def test_scan_cross_course_links_other_course_id_not_flagged():
    """Only the configured master_id is flagged. Other course IDs are not."""
    body = '<p><a href="/courses/415094/pages/foo">A</a></p>'
    count, _ = scan_cross_course_links(body, "339374")
    assert count == 0


def test_scan_cross_course_links_empty_body():
    assert scan_cross_course_links("", "339374") == (0, [])
    assert scan_cross_course_links(None, "339374") == (0, [])


# ---------------------------------------------------------------------------
# is_suffixed_slug
# ---------------------------------------------------------------------------

def test_is_suffixed_slug():
    assert is_suffixed_slug("w01-u0-unit-overview-2") is True
    assert is_suffixed_slug("w01-u0-unit-overview-3") is True
    assert is_suffixed_slug("w01-u0-unit-overview-2-2") is True
    assert is_suffixed_slug("w01-u0-unit-overview") is False
    assert is_suffixed_slug("sprint-1-setup-dag-demo-w01-w02") is False  # legit -w02 ending
    assert is_suffixed_slug("project-presentation-streamlit-app-w13-w14") is False


# ---------------------------------------------------------------------------
# Planner — Master safety
# ---------------------------------------------------------------------------

def test_planner_refuses_master_as_target():
    """Master is never mutated. Planner must raise."""
    with pytest.raises(ValueError, match="never be modified"):
        build_apply_plan(
            target_id="339374",
            master_id="339374",
            findings=[],
            canonical_bodies={},
            module_items_by_slug={},
        )


# ---------------------------------------------------------------------------
# Planner — orphan_match (Phase 1 5-point fingerprint)
# ---------------------------------------------------------------------------

def test_orphan_match_produces_clean_deletion_plan():
    """Classic Phase 1 orphan: one suffixed (not linked) + one unsuffixed (linked).
    Plan: delete 1 module item (none for suffixed since unlinked), delete 1 page."""
    findings = [{
        "kind": "orphan_match",
        "title": "Week 5 Unit Overview",
        "section_id": "415194",
        "orphan_slug": "w05-unit-overview-2",
        "canonical_slug": "w05-unit-overview",
        "blueprint_slug": "w05-unit-overview",
    }]
    canonical = {"Week 5 Unit Overview": "<p>canonical body</p>"}
    items = {"w05-unit-overview": [("mod-1", "item-100", 5)]}  # only unsuffixed linked
    plan = build_apply_plan("415194", "339374", findings, canonical, items)
    summary = summarize_plan(plan)
    assert summary["delete_page"] == 1
    assert summary["overwrite"] == 0          # orphan_match never claims unsuffixed_stale by default
    # No suffixed module items → 0 deletes for the suffixed slug. The kept
    # slug only has 1 module item → no collapse needed.
    assert summary["delete_module_item"] == 0


def test_orphan_match_with_linked_orphan_deletes_its_module_item():
    """If suffixed orphan IS linked (rare), its module item must also be deleted."""
    findings = [{
        "kind": "orphan_match",
        "title": "Week 5 Unit Overview",
        "section_id": "415194",
        "orphan_slug": "w05-unit-overview-2",
        "canonical_slug": "w05-unit-overview",
        "blueprint_slug": "w05-unit-overview",
    }]
    canonical = {"Week 5 Unit Overview": "<p>canonical body</p>"}
    items = {
        "w05-unit-overview":   [("mod-1", "item-100", 5)],
        "w05-unit-overview-2": [("mod-1", "item-200", 6)],  # orphan linked
    }
    plan = build_apply_plan("415194", "339374", findings, canonical, items)
    summary = summarize_plan(plan)
    assert summary["delete_page"] == 1
    assert summary["delete_module_item"] == 1


# ---------------------------------------------------------------------------
# Planner — multi_suffix_cleanable (Phase 2 multi-suffix case)
# ---------------------------------------------------------------------------

def test_multi_suffix_cleanable_with_unsuffixed_stale():
    """The W01 U0 case: parent is STALE, -2 and -3 both linked and canonical.
    Plan: overwrite kept page, delete 2 suffixed pages, delete 2 suffixed module items."""
    findings = [{
        "kind": "multi_suffix_cleanable",
        "title": "W01 U0 Unit Overview",
        "section_id": "415194",
        "canonical_slug": "w01-u0-unit-overview",
        "suffixed_slugs": ["w01-u0-unit-overview-2", "w01-u0-unit-overview-3"],
        "unsuffixed_stale": True,
    }]
    canonical = {"W01 U0 Unit Overview": "<p>canonical body from Master</p>"}
    items = {
        "w01-u0-unit-overview":   [("mod-1", "item-100", 2)],
        "w01-u0-unit-overview-2": [("mod-1", "item-200", 4)],
        "w01-u0-unit-overview-3": [("mod-1", "item-300", 6)],
    }
    plan = build_apply_plan("415194", "339374", findings, canonical, items)
    summary = summarize_plan(plan)
    assert summary["overwrite"] == 1
    assert summary["delete_module_item"] == 2  # the 2 suffixed slugs' items
    assert summary["delete_page"] == 2


def test_multi_suffix_cleanable_clean_unsuffixed():
    """The W07 U3 case: parent is canonical, just delete the suffixed copies."""
    findings = [{
        "kind": "multi_suffix_cleanable",
        "title": "W07 U3 Unit Overview",
        "section_id": "415094",
        "canonical_slug": "w07-u3-unit-overview",
        "suffixed_slugs": ["w07-u3-unit-overview-2"],
        "unsuffixed_stale": False,
    }]
    canonical = {"W07 U3 Unit Overview": "<p>canonical</p>"}
    items = {
        "w07-u3-unit-overview":   [("mod-7", "item-700", 2)],
        "w07-u3-unit-overview-2": [("mod-7", "item-701", 1)],  # at lower pos — the #41 case!
    }
    plan = build_apply_plan("415094", "339374", findings, canonical, items)
    summary = summarize_plan(plan)
    assert summary["overwrite"] == 0
    assert summary["delete_module_item"] == 1
    assert summary["delete_page"] == 1
    # Verify the kept slug really is the unsuffixed one — even though the
    # suffixed `-2` is at pos 1 (the #41 trap). The DeletePage step must
    # name the suffixed slug, NOT the unsuffixed one.
    delete_page_step = next(s for s in plan if s.kind == "DeletePage")
    assert delete_page_step.slug == "w07-u3-unit-overview-2"


def test_keep_unsuffixed_module_item_collapsed_to_lowest_position():
    """Kept slug with two module items: keep the lowest position, delete the rest."""
    findings = [{
        "kind": "multi_suffix_cleanable",
        "title": "Test",
        "section_id": "415094",
        "canonical_slug": "test",
        "suffixed_slugs": [],
        "unsuffixed_stale": False,
    }]
    canonical = {"Test": "<p>x</p>"}
    items = {"test": [
        ("mod-1", "item-100", 5),
        ("mod-1", "item-101", 3),
        ("mod-1", "item-102", 7),
    ]}
    plan = build_apply_plan("415094", "339374", findings, canonical, items)
    deletes = [s for s in plan if s.kind == "DeleteModuleItem"]
    # 2 of the 3 collapsed; item-101 (pos 3) is kept
    assert len(deletes) == 2
    kept_item_ids = {s.item_id for s in deletes}
    assert "item-101" not in kept_item_ids
    assert {"item-100", "item-102"} == kept_item_ids


# ---------------------------------------------------------------------------
# Planner — skip rules
# ---------------------------------------------------------------------------

def test_skip_when_no_master_canonical():
    """W12 Teaching Notes pattern: instructor-only page, no Master canonical → skip."""
    findings = [{
        "kind": "multi_suffix_cleanable",
        "title": "W12 Teaching Notes (Do NOT Publish)",
        "section_id": "415094",
        "canonical_slug": "w12-teaching-notes-do-not-publish",
        "suffixed_slugs": ["w12-teaching-notes-do-not-publish-2"],
        "unsuffixed_stale": False,
    }]
    canonical = {}  # NO Master canonical for this title
    items = {}
    plan = build_apply_plan("415094", "339374", findings, canonical, items)
    assert plan == []


def test_skip_when_scope_regex_does_not_match():
    findings = [{
        "kind": "orphan_match",
        "title": "Week 5 Unit Overview",
        "section_id": "415194",
        "orphan_slug": "w05-unit-overview-2",
        "canonical_slug": "w05-unit-overview",
    }]
    canonical = {"Week 5 Unit Overview": "<p>x</p>"}
    items = {}
    plan = build_apply_plan(
        "415194", "339374", findings, canonical, items,
        scope_regex=re.compile(r"Module \d+"),  # won't match
    )
    assert plan == []


def test_scope_regex_matches():
    findings = [{
        "kind": "orphan_match",
        "title": "Week 5 Unit Overview",
        "section_id": "415194",
        "orphan_slug": "w05-unit-overview-2",
        "canonical_slug": "w05-unit-overview",
    }]
    canonical = {"Week 5 Unit Overview": "<p>x</p>"}
    items = {}
    plan = build_apply_plan(
        "415194", "339374", findings, canonical, items,
        scope_regex=re.compile(r"overview", re.I),
    )
    assert len(plan) == 1
    assert plan[0].kind == "DeletePage"


def test_skip_when_keep_slug_is_suffixed():
    """Defensive: if a finding somehow names a suffixed slug as canonical,
    refuse to plan it. Never silently fall back to position — the #41 bug."""
    findings = [{
        "kind": "multi_suffix_cleanable",
        "title": "Bad",
        "section_id": "415094",
        "canonical_slug": "bad-slug-2",  # WRONG: suffixed slug as canonical
        "suffixed_slugs": ["bad-slug-3"],
        "unsuffixed_stale": False,
    }]
    canonical = {"Bad": "<p>x</p>"}
    items = {}
    plan = build_apply_plan("415094", "339374", findings, canonical, items)
    assert plan == []


# ---------------------------------------------------------------------------
# Planner — cross-course link scan
# ---------------------------------------------------------------------------

def test_cross_course_link_warning_emitted_when_canonical_has_master_links():
    findings = [{
        "kind": "multi_suffix_cleanable",
        "title": "W01 U0 Unit Overview",
        "section_id": "415194",
        "canonical_slug": "w01-u0-unit-overview",
        "suffixed_slugs": ["w01-u0-unit-overview-2"],
        "unsuffixed_stale": True,
    }]
    canonical = {
        "W01 U0 Unit Overview": (
            '<p>See <a href="/courses/339374/assignments/123">activity</a>.</p>'
        )
    }
    items = {"w01-u0-unit-overview": [], "w01-u0-unit-overview-2": []}
    plan = build_apply_plan("415194", "339374", findings, canonical, items)
    warnings = [s for s in plan if s.kind == "CrossCourseLinkWarning"]
    assert len(warnings) == 1
    assert warnings[0].cross_course_link_count == 1
    assert warnings[0].cross_course_master_id == "339374"
    # Warning appears BEFORE the OverwriteBody so an operator reading the plan
    # sees the caution alongside the write.
    overwrite_idx = next(i for i, s in enumerate(plan) if s.kind == "OverwriteBody")
    warning_idx = next(i for i, s in enumerate(plan) if s.kind == "CrossCourseLinkWarning")
    assert warning_idx < overwrite_idx


def test_no_cross_course_warning_when_canonical_is_clean():
    findings = [{
        "kind": "multi_suffix_cleanable",
        "title": "Clean",
        "section_id": "415194",
        "canonical_slug": "clean",
        "suffixed_slugs": ["clean-2"],
        "unsuffixed_stale": True,
    }]
    canonical = {"Clean": "<p>just text and <strong>bold</strong></p>"}
    items = {"clean": [], "clean-2": []}
    plan = build_apply_plan("415194", "339374", findings, canonical, items)
    assert not any(s.kind == "CrossCourseLinkWarning" for s in plan)


# ---------------------------------------------------------------------------
# Idempotency — empty findings produces empty plan
# ---------------------------------------------------------------------------

def test_empty_findings_produces_empty_plan():
    """The idempotency fixture: a clean course produces no findings,
    which produces no plan, which produces no writes."""
    plan = build_apply_plan("415094", "339374", [], {}, {})
    assert plan == []
    assert summarize_plan(plan) == {
        "overwrite": 0,
        "delete_module_item": 0,
        "delete_page": 0,
        "cross_course_link_warning": 0,
    }


# ---------------------------------------------------------------------------
# DS250 GOLD-STANDARD FIXTURE — the 2026-06-02 production run
# ---------------------------------------------------------------------------

def _ds250_findings_for_target(label: str, target_id: str, stale_titles: set[str]) -> list[dict]:
    """8 overview titles per course. Each has parent + `-2` (BP) or parent + `-2` + `-3` (sections).
    `stale_titles` is the set of titles whose unsuffixed slug holds stale content.
    """
    # The 8 unit-overview titles documented in the DS250 design-review reply.
    OVERVIEW_TITLES = [
        ("Course Overview",                "course-overview"),
        ("W01 U0 Unit Overview",           "w01-u0-unit-overview"),
        ("W03 U1 Unit Overview",           "w03-u1-unit-overview"),
        ("W05 U2 Unit Overview",           "w05-u2-unit-overview"),
        ("W07 U3 Unit Overview",           "w07-u3-unit-overview"),
        ("W09 U4 Unit Overview",           "w09-u4-unit-overview"),
        ("W11 U5 Unit Overview",           "w11-u5-unit-overview"),
        ("W13 U6 Unit Overview",           "w13-u6-unit-overview"),
    ]
    is_section = label.startswith("S")
    findings = []
    for title, base_slug in OVERVIEW_TITLES:
        if is_section:
            suffixed = [f"{base_slug}-2", f"{base_slug}-3"]
        else:
            suffixed = [f"{base_slug}-2"]
        findings.append({
            "kind": "multi_suffix_cleanable",
            "title": title,
            "section_id": target_id,
            "canonical_slug": base_slug,
            "suffixed_slugs": suffixed,
            "unsuffixed_stale": title in stale_titles,
        })
    return findings


def _ds250_module_items(target_label: str, findings: list[dict]) -> dict[str, list]:
    """All copies linked in modules, per the design-review note: 'all copies are
    linked in modules' on DS250. One module item per slug, position arbitrary."""
    items = {}
    pos = 1
    for f in findings:
        items[f["canonical_slug"]] = [("mod-x", f"item-{pos}", pos)]
        pos += 1
        for s in f["suffixed_slugs"]:
            items[s] = [("mod-x", f"item-{pos}", pos)]
            pos += 1
    return items


def test_ds250_gold_standard_total_matches_2026_06_02_run():
    """The algorithmic regression test: synthesizing the 2026-06-02 DS250 fleet
    state should produce the captured plan totals:

        Combined:  overwrite=2 pages, delete 40 module-items, delete 40 pages
        Blueprint (415094):  overwrite=0,  delete 8 items,  delete 8 pages
        S1 (415194):         overwrite=1,  delete 16 items, delete 16 pages
        S2 (415196):         overwrite=1,  delete 16 items, delete 16 pages

    The 2 overwrites were both `w01-u0-unit-overview` (stale in S1 and S2).
    """
    MASTER_ID = "339374"
    canonical_bodies = {
        "Course Overview":            "<p>Course Overview canonical</p>",
        "W01 U0 Unit Overview":       "<p>W01 U0 canonical</p>",
        "W03 U1 Unit Overview":       "<p>W03 U1 canonical</p>",
        "W05 U2 Unit Overview":       "<p>W05 U2 canonical</p>",
        "W07 U3 Unit Overview":       "<p>W07 U3 canonical</p>",
        "W09 U4 Unit Overview":       "<p>W09 U4 canonical</p>",
        "W11 U5 Unit Overview":       "<p>W11 U5 canonical</p>",
        "W13 U6 Unit Overview":       "<p>W13 U6 canonical</p>",
    }

    targets = [
        ("Blueprint", "415094", set()),                          # 0 stale
        ("S1",        "415194", {"W01 U0 Unit Overview"}),       # 1 stale
        ("S2",        "415196", {"W01 U0 Unit Overview"}),       # 1 stale
    ]

    combined = {"overwrite": 0, "delete_module_item": 0, "delete_page": 0}
    per_target = {}
    for label, tid, stale in targets:
        findings = _ds250_findings_for_target(label, tid, stale)
        items = _ds250_module_items(label, findings)
        plan = build_apply_plan(tid, MASTER_ID, findings, canonical_bodies, items)
        s = summarize_plan(plan)
        per_target[label] = s
        for k in ("overwrite", "delete_module_item", "delete_page"):
            combined[k] += s[k]

    assert per_target["Blueprint"] == {
        "overwrite": 0, "delete_module_item": 8, "delete_page": 8,
        "cross_course_link_warning": 0,
    }, per_target["Blueprint"]
    assert per_target["S1"] == {
        "overwrite": 1, "delete_module_item": 16, "delete_page": 16,
        "cross_course_link_warning": 0,
    }, per_target["S1"]
    assert per_target["S2"] == {
        "overwrite": 1, "delete_module_item": 16, "delete_page": 16,
        "cross_course_link_warning": 0,
    }, per_target["S2"]
    assert combined == {"overwrite": 2, "delete_module_item": 40, "delete_page": 40}

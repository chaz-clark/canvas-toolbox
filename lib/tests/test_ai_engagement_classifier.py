"""Tier 1 unit tests — ai_engagement_classifier.py.

All deterministic: the LLM only produces the ordered `sequence`; everything the tool
reports (distributions, 0-100 agency score, threshold gaps, transitions/route, archetype)
is computed in Python from that sequence, so it is tested here with no model call.

Covers: profile load + validation, the revert/swap to a different taxonomy (three_tier),
the aggregation math, transition (route) extraction, threshold gaps, the archetype rule
DSL for every archetype, and prompt assembly (student-turn numbering + fenced-JSON parse).
"""
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import ai_engagement_classifier as C  # noqa: E402


def _seq(*modes):
    return [{"index": i, "mode": m, "confidence": 0.9, "evidence": ""} for i, m in enumerate(modes)]


# ---------------------------------------------------------------------------
# profile loading + swap
# ---------------------------------------------------------------------------

def test_profiles_present_and_swappable():
    ids = C.list_profiles()
    assert "aimodes_placeholder" in ids
    assert "three_tier" in ids


def test_placeholder_profile_loads_and_is_labeled_placeholder():
    p = C.load_profile("aimodes_placeholder")
    assert p["profile_id"] == "aimodes_placeholder"
    assert p["status"] == "placeholder"
    assert "NOT Keith" in p["attribution"]           # honest boundary carried in every output
    assert len(p["modes"]) == 8
    assert {t["id"] for t in p["tiers"]} == {"passivity", "partnership", "agency"}


def test_profile_validation_rejects_dangling_tier(tmp_path, monkeypatch):
    bad = tmp_path
    (bad / "broken.json").write_text(
        '{"profile_id":"broken","tiers":[{"id":"a","order":1,"agency_weight":0}],'
        '"modes":[{"id":"m","tier":"NOPE","label":"M"}]}', encoding="utf-8")
    monkeypatch.setattr(C, "PROFILE_DIR", bad)
    with pytest.raises(SystemExit):
        C.load_profile("broken")


# ---------------------------------------------------------------------------
# aggregation math
# ---------------------------------------------------------------------------

def test_distributions_and_agency_score():
    p = C.load_profile("aimodes_placeholder")
    # 2 passivity, 2 partnership, 2 agency  ->  score = 33%*0 + 33%*50 + 33%*100 = 50
    body = C.aggregate(
        _seq("oracle", "oracle", "tutor", "collab_solver", "verification_agent", "problem_setter"), p)
    assert body["agency_score"] == 50
    assert body["tier_distribution"] == {"passivity": 0.3333, "partnership": 0.3333, "agency": 0.3333}
    assert body["mode_distribution"]["oracle"] == 0.3333
    # sums to ~1 (per-value 4dp rounding leaves a small residual — not exactly 1.0)
    assert abs(sum(body["mode_distribution"].values()) - 1.0) < 1e-3


def test_agency_score_extremes():
    p = C.load_profile("aimodes_placeholder")
    assert C.aggregate(_seq("oracle", "oracle"), p)["agency_score"] == 0          # all passivity
    assert C.aggregate(_seq("problem_setter", "critical_challenger"), p)["agency_score"] == 100  # all agency


def test_empty_sequence_is_safe():
    p = C.load_profile("aimodes_placeholder")
    body = C.aggregate([], p)
    assert body["agency_score"] == 0
    assert body["mode_distribution"] == {}
    assert body["transitions"] == []


# ---------------------------------------------------------------------------
# transitions (the route) + threshold gaps
# ---------------------------------------------------------------------------

def test_transitions_capture_ordered_route():
    p = C.load_profile("aimodes_placeholder")
    body = C.aggregate(_seq("oracle", "tutor", "oracle", "tutor"), p)
    trans = {(t["from"], t["to"]): t["count"] for t in body["transitions"]}
    assert trans[("oracle", "tutor")] == 2
    assert trans[("tutor", "oracle")] == 1


def test_threshold_gap_signed_correctly():
    p = C.load_profile("aimodes_placeholder")
    body = C.aggregate(_seq("oracle", "oracle", "oracle", "tutor"), p)  # oracle 0.75, target 0.10
    gap = next(g for g in body["threshold_gaps"] if g["mode"] == "oracle")
    assert gap["actual"] == 0.75 and gap["target"] == 0.10
    assert round(gap["gap"], 2) == 0.65
    # a mode never used shows a negative gap (below where the student should be)
    ps = next(g for g in body["threshold_gaps"] if g["mode"] == "problem_setter")
    assert ps["actual"] == 0.0 and ps["gap"] < 0


# ---------------------------------------------------------------------------
# archetype rule DSL — one case per archetype
# ---------------------------------------------------------------------------

def test_archetype_delegator():
    p = C.load_profile("aimodes_placeholder")
    assert C.aggregate(_seq("oracle", "oracle", "production_assistant"), p)["archetype"]["id"] == "delegator"


def test_archetype_learner_by_modal_mode():
    p = C.load_profile("aimodes_placeholder")
    assert C.aggregate(_seq("tutor", "tutor", "oracle"), p)["archetype"]["id"] == "learner"


def test_archetype_challenger():
    p = C.load_profile("aimodes_placeholder")
    assert C.aggregate(_seq("critical_challenger", "critical_challenger", "oracle"), p)["archetype"]["id"] == "challenger"


def test_archetype_explorer():
    p = C.load_profile("aimodes_placeholder")
    assert C.aggregate(_seq("creative_expander", "problem_setter", "oracle"), p)["archetype"]["id"] == "explorer"


def test_archetype_specialist():
    p = C.load_profile("aimodes_placeholder")
    # verification_agent 0.67 >= 0.40 but not challenger/explorer/learner/partner first
    assert C.aggregate(_seq("verification_agent", "verification_agent", "oracle"), p)["archetype"]["id"] == "specialist"


def test_archetype_falls_back_to_default_partner():
    p = C.load_profile("aimodes_placeholder")
    # balanced across tiers, no rule fires -> default
    body = C.aggregate(_seq("oracle", "tutor", "verification_agent"), p)
    assert body["archetype"]["id"] == "partner"
    assert body["archetype"]["rationale"] == "default"


# ---------------------------------------------------------------------------
# revert / swap taxonomy — same engine, coarse profile
# ---------------------------------------------------------------------------

def test_three_tier_swap_runs_same_engine():
    p = C.load_profile("three_tier")
    body = C.aggregate(_seq("passivity", "partnership", "agency"), p)
    assert body["agency_score"] == 50
    assert set(body["tier_distribution"]) == {"passivity", "partnership", "agency"}
    assert body["archetype"]["id"] in {"delegator", "partner", "driver"}


# ---------------------------------------------------------------------------
# prompt assembly + response parsing
# ---------------------------------------------------------------------------

def test_user_prompt_numbers_student_turns_only():
    msgs = [{"role": "student", "text": "q1"}, {"role": "assistant", "text": "a1"},
            {"role": "student", "text": "q2"}]
    prompt, n = C.build_user_prompt(msgs)
    assert n == 2
    assert "[Student turn 0]" in prompt and "[Student turn 1]" in prompt
    assert "[Student turn 2]" not in prompt


def test_parse_response_tolerates_code_fences():
    assert C._parse_response('```json\n{"sequence": []}\n```') == {"sequence": []}
    assert C._parse_response('noise {"sequence": [{"index":0,"mode":"oracle"}]} tail') \
        == {"sequence": [{"index": 0, "mode": "oracle"}]}
    assert C._parse_response("not json at all") is None


def test_system_prompt_lists_all_modes():
    p = C.load_profile("aimodes_placeholder")
    sysmsg = C.build_system_prompt(p)
    for m in p["modes"]:
        assert m["id"] in sysmsg

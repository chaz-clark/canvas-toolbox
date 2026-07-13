"""Tier 1 unit tests — syllabus_audit institution profile (college-agnostic).

Source: lib/tools/syllabus_audit.py — compute_verdict + default_institution.
The BYUI profile REQUIRES a generative-AI policy for a 'complete' verdict; other
institutions treat it as advisory (the AI policy is reported but doesn't drive
the verdict). Institution is inferred from the Canvas host, overridable by
CANVAS_INSTITUTION / --institution.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import syllabus_audit as S  # noqa: E402


def _all_detected():
    return [{"label": s["label"], "detected": True} for s in S.REQUIRED_SECTIONS]


def test_byui_profile_requires_ai_policy():
    v, missing = S.compute_verdict(_all_detected(), {"present": False}, 2000,
                                   ai_policy_required=True)
    assert v == "incomplete"
    assert any("AI Policy" in m for m in missing)


def test_generic_profile_treats_ai_policy_as_advisory():
    v, missing = S.compute_verdict(_all_detected(), {"present": False}, 2000,
                                   ai_policy_required=False)
    assert v == "complete"
    assert not any("AI Policy" in m for m in missing)


def test_missing_section_fails_regardless_of_profile():
    secs = _all_detected()
    secs[0]["detected"] = False
    for req in (True, False):
        v, _ = S.compute_verdict(secs, {"present": True}, 2000, ai_policy_required=req)
        assert v == "incomplete"


def test_institution_inferred_from_host(monkeypatch):
    monkeypatch.delenv("CANVAS_INSTITUTION", raising=False)
    monkeypatch.setattr(S, "CANVAS_BASE_URL", "https://byui.instructure.com")
    assert S.default_institution() == "byui"
    monkeypatch.setattr(S, "CANVAS_BASE_URL", "https://someschool.instructure.com")
    assert S.default_institution() == "generic"


def test_env_overrides_inference(monkeypatch):
    monkeypatch.setenv("CANVAS_INSTITUTION", "acme")
    monkeypatch.setattr(S, "CANVAS_BASE_URL", "https://byui.instructure.com")
    assert S.default_institution() == "acme"

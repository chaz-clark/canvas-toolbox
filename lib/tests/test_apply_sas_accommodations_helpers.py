"""Tier 1 unit tests — apply_sas_accommodations pure-logic helpers.

Source: lib/tools/apply_sas_accommodations.py
  - classify_key            (key → tier)
  - plan_one_accommodation  (single accommodation → DispatchPlan)
  - plan_entries            (full YAML structure → flat plan list)
  - render_audit_line       (audit-log format)

No subprocess calls. No file I/O. Pure dispatch logic.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from apply_sas_accommodations import (  # noqa: E402
    DispatchPlan,
    classify_key,
    plan_entries,
    plan_one_accommodation,
    render_audit_line,
)


# ---------------------------------------------------------------------------
# classify_key — the 3-tier classification (+ unknown)
# ---------------------------------------------------------------------------

def test_classify_canvas_keys():
    assert classify_key("extra_time_1.5x") == "canvas"
    assert classify_key("extra_time_2.0x") == "canvas"
    assert classify_key("occasional_extensions") == "canvas"
    assert classify_key("test_reschedule") == "canvas"


def test_classify_proctoring_keys():
    assert classify_key("proctorio_breaks") == "proctoring"
    assert classify_key("private_room_exams") == "proctoring"


def test_classify_policy_keys():
    assert classify_key("spelling_grammar") == "policy"
    assert classify_key("attendance_notification") == "policy"
    assert classify_key("recording_device") == "policy"
    assert classify_key("service_animal") == "policy"


def test_classify_unknown_key():
    assert classify_key("not_a_real_key") == "unknown"
    assert classify_key("") == "unknown"


# ---------------------------------------------------------------------------
# plan_one_accommodation — single accommodation dispatch
# ---------------------------------------------------------------------------

def test_plan_extra_time_15x():
    plan = plan_one_accommodation("S-95DBB6", {"key": "extra_time_1.5x"})
    assert plan.tier == "canvas"
    assert plan.command is not None
    assert "student_quiz_time_extension.py" in " ".join(plan.command)
    assert "--multiplier" in plan.command
    assert "1.5" in plan.command
    assert "--all-timed" in plan.command
    assert "--deid-code" in plan.command
    assert "S-95DBB6" in plan.command


def test_plan_extra_time_20x():
    plan = plan_one_accommodation("S-95DBB6", {"key": "extra_time_2.0x"})
    assert "2.0" in plan.command


def test_plan_occasional_extensions_defaults_to_all():
    """No scope key → --all."""
    plan = plan_one_accommodation("S-X", {"key": "occasional_extensions"})
    assert plan.tier == "canvas"
    assert "student_late_accommodation.py" in " ".join(plan.command)
    assert "--all" in plan.command


def test_plan_occasional_extensions_from_days_ago():
    plan = plan_one_accommodation("S-X", {
        "key": "occasional_extensions",
        "scope": "from_days_ago",
        "days": 14,
    })
    assert "--from-days-ago" in plan.command
    assert "14" in plan.command
    assert "--all" not in plan.command


def test_plan_occasional_extensions_from_date():
    plan = plan_one_accommodation("S-X", {
        "key": "occasional_extensions",
        "scope": "from",
        "from": "2026-04-01",
    })
    assert "--from" in plan.command
    assert "2026-04-01" in plan.command


def test_plan_test_reschedule_defaults_to_7_days():
    plan = plan_one_accommodation("S-X", {"key": "test_reschedule"})
    assert plan.tier == "canvas"
    assert "--shift-by-days" in plan.command
    assert "7" in plan.command
    assert "--all" in plan.command  # no assignment_id → all


def test_plan_test_reschedule_custom_days_and_assignment():
    plan = plan_one_accommodation("S-X", {
        "key": "test_reschedule",
        "shift_by_days": 14,
        "assignment_id": 12345,
    })
    assert "--shift-by-days" in plan.command
    assert "14" in plan.command
    assert "--assignment-id" in plan.command
    assert "12345" in plan.command


def test_plan_proctoring_no_command():
    plan = plan_one_accommodation("S-X", {"key": "proctorio_breaks"})
    assert plan.tier == "proctoring"
    assert plan.command is None
    assert "PROCTORING" in plan.note


def test_plan_policy_no_command():
    plan = plan_one_accommodation("S-X", {"key": "spelling_grammar"})
    assert plan.tier == "policy"
    assert plan.command is None
    assert "POLICY" in plan.note


def test_plan_unknown_key():
    plan = plan_one_accommodation("S-X", {"key": "fictional_accom"})
    assert plan.tier == "unknown"
    assert plan.command is None
    assert "UNKNOWN" in plan.note


def test_plan_missing_key_treated_as_unknown():
    """An entry with no 'key' field (typo in YAML?) → unknown tier."""
    plan = plan_one_accommodation("S-X", {})
    assert plan.tier == "unknown"


# ---------------------------------------------------------------------------
# plan_entries — full handoff structure
# ---------------------------------------------------------------------------

def test_plan_entries_flattens_two_students():
    entries = [
        {"deid_code": "S-AAA",
         "accommodations": [{"key": "extra_time_1.5x"}]},
        {"deid_code": "S-BBB",
         "accommodations": [{"key": "extra_time_2.0x"},
                            {"key": "occasional_extensions"}]},
    ]
    plans = plan_entries(entries)
    assert len(plans) == 3
    assert {p.deid_code for p in plans} == {"S-AAA", "S-BBB"}


def test_plan_entries_skips_entry_with_no_deid_code():
    entries = [
        {"accommodations": [{"key": "extra_time_1.5x"}]},  # no deid_code → skip
        {"deid_code": "S-X", "accommodations": [{"key": "extra_time_1.5x"}]},
    ]
    plans = plan_entries(entries)
    assert len(plans) == 1
    assert plans[0].deid_code == "S-X"


def test_plan_entries_handles_no_accommodations():
    """A student entry with no accommodations list emits no plans."""
    entries = [{"deid_code": "S-AAA"}]
    plans = plan_entries(entries)
    assert plans == []


def test_plan_entries_handles_empty_list():
    assert plan_entries([]) == []


def test_plan_entries_preserves_order():
    """Plans come out in document order so the audit log matches the YAML."""
    entries = [
        {"deid_code": "S-ONE",
         "accommodations": [{"key": "extra_time_1.5x"},
                            {"key": "spelling_grammar"}]},
    ]
    plans = plan_entries(entries)
    assert plans[0].key == "extra_time_1.5x"
    assert plans[1].key == "spelling_grammar"


# ---------------------------------------------------------------------------
# render_audit_line — audit log format
# ---------------------------------------------------------------------------

def test_audit_line_contains_all_fields():
    plan = DispatchPlan(
        deid_code="S-95DBB6",
        key="extra_time_1.5x",
        tier="canvas",
        command=["foo"],
        note="Canvas: +50% extra time.",
    )
    line = render_audit_line(plan, "APPLIED", "2026-06-26T12:00:00+00:00")
    assert "S-95DBB6" in line
    assert "extra_time_1.5x" in line
    assert "canvas" in line
    assert "APPLIED" in line
    assert "2026-06-26T12:00:00+00:00" in line


def test_audit_line_tab_separated():
    """Tab-separated so `cut -f` works on the log file."""
    plan = DispatchPlan("S-X", "extra_time_1.5x", "canvas", None, "note")
    line = render_audit_line(plan, "PLANNED", "ts")
    parts = line.split("\t")
    assert len(parts) == 6

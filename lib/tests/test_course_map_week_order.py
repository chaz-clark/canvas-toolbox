"""Tier 1 — course_map_build orders each week's items deterministically.

Canvas's raw /assignments order isn't reproducible from a local course/, so the
weekly map sorts each week by (due_at, name) — identical online and --local, and
clearer for a weekly plan.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import course_map_build as C  # noqa: E402


def test_each_week_sorted_by_due_then_name():
    start = datetime(2026, 9, 20, tzinfo=timezone.utc)
    asgs = [
        {"published": True, "name": "Zeta", "due_at": "2026-09-23T00:00:00Z"},
        {"published": True, "name": "Alpha", "due_at": "2026-09-23T00:00:00Z"},
        {"published": True, "name": "Beta", "due_at": "2026-09-22T00:00:00Z"},
    ]
    out = C.group_assignments_by_week(asgs, start)
    assert out, "expected at least one week bucket"
    for items in out.values():
        keys = [(a["due_at"], a["name"]) for a in items]
        assert keys == sorted(keys)  # due-date asc, name tiebreak

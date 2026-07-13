"""Tier 1 — formative_variety_audit offline-parity guard.

The --local path reads `.imscc`-derived dates, which are naive UTC, while the
API's are tz-aware (`...Z`). `_parse_due_at` coerces naive -> UTC so local and
online produce byte-identical timestamps (exact --local parity, verified live
against course 427808).
"""
import sys
from datetime import timezone
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import formative_variety_audit as F  # noqa: E402


def test_parse_due_at_coerces_naive_to_utc():
    naive = F._parse_due_at("2026-09-20T05:59:00")        # .imscc (naive UTC)
    aware = F._parse_due_at("2026-09-20T05:59:00Z")       # API (tz-aware)
    assert naive.tzinfo == timezone.utc
    assert naive == aware                                  # same instant
    assert naive.isoformat() == aware.isoformat()          # byte-identical output


def test_parse_due_at_none_and_bad():
    assert F._parse_due_at(None) is None
    assert F._parse_due_at("not-a-date") is None

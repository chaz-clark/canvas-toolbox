"""Tier 1 unit tests — offline-mode CANVAS_MODE flag helpers.

Source: lib/tools/_canvas_mode.py (Sprint 1)
  - get_canvas_mode          (default online; case/space insensitive; loud on typo)
  - is_online_mode / is_offline_mode
  - check_mode_requirements  (online requires CANVAS_API_TOKEN; offline does not)

Pure logic, no Canvas access — env is injected, so these never touch the network
and run regardless of sandbox creds.
"""
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _canvas_mode import (  # noqa: E402
    ONLINE,
    OFFLINE,
    get_canvas_mode,
    is_online_mode,
    is_offline_mode,
    check_mode_requirements,
)


# --- get_canvas_mode -------------------------------------------------------

def test_default_is_online_when_unset():
    assert get_canvas_mode({}) == ONLINE


def test_empty_string_is_online():
    assert get_canvas_mode({"CANVAS_MODE": ""}) == ONLINE


def test_explicit_offline():
    assert get_canvas_mode({"CANVAS_MODE": "offline"}) == OFFLINE


@pytest.mark.parametrize("raw", ["OFFLINE", " Offline ", "offline\n"])
def test_case_and_whitespace_insensitive(raw):
    assert get_canvas_mode({"CANVAS_MODE": raw}) == OFFLINE


@pytest.mark.parametrize("bad", ["ofline", "local", "api", "true", "0"])
def test_invalid_mode_raises(bad):
    with pytest.raises(ValueError):
        get_canvas_mode({"CANVAS_MODE": bad})


# --- is_online_mode / is_offline_mode --------------------------------------

def test_predicates_online():
    env = {"CANVAS_MODE": "online"}
    assert is_online_mode(env) is True
    assert is_offline_mode(env) is False


def test_predicates_offline():
    env = {"CANVAS_MODE": "offline"}
    assert is_offline_mode(env) is True
    assert is_online_mode(env) is False


# --- check_mode_requirements ----------------------------------------------

def test_online_without_token_raises():
    with pytest.raises(ValueError, match="CANVAS_API_TOKEN"):
        check_mode_requirements({"CANVAS_MODE": "online"})


def test_online_with_blank_token_raises():
    with pytest.raises(ValueError, match="CANVAS_API_TOKEN"):
        check_mode_requirements({"CANVAS_MODE": "online", "CANVAS_API_TOKEN": "   "})


def test_online_with_token_ok():
    env = {"CANVAS_MODE": "online", "CANVAS_API_TOKEN": "abc123"}
    assert check_mode_requirements(env) == ONLINE


def test_offline_needs_no_token():
    assert check_mode_requirements({"CANVAS_MODE": "offline"}) == OFFLINE


def test_default_unset_treated_as_online_and_needs_token():
    # No CANVAS_MODE at all → online → token still required.
    with pytest.raises(ValueError, match="CANVAS_API_TOKEN"):
        check_mode_requirements({})

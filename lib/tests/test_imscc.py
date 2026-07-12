"""Tier 1 unit tests — .imscc date-shift + validation (Sprint 4).

Source: lib/tools/_imscc.py (+ CLIs imscc_adjust_dates.py / validate_imscc.py)

Unit tests cover date shifting and constraint/identifier validation. Failure
injection builds intentionally-broken .imscc archives and asserts the validator
catches each mode. Gated integration shifts + validates the real DS 250 / DS 460
/ ITM 327 / M 119 exports in ~/Downloads.
"""
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _imscc import (  # noqa: E402
    shift_value,
    shift_dates_in_text,
    adjust_dates_in_imscc,
    validate_imscc,
    manifest_resource_identifiers,
)
import _file_finder  # noqa: E402

ADJUST_TOOL = _TOOLS_DIR / "imscc_adjust_dates.py"
VALIDATE_TOOL = _TOOLS_DIR / "validate_imscc.py"

GOOD_ID = "g" + "a" * 32
_MANIFEST = (
    '<?xml version="1.0"?><manifest><resources>'
    '<resource identifier="{rid}" type="webcontent"/>'
    "</resources></manifest>"
)


def _make_imscc(path, *, manifest_id=GOOD_ID, trigger=True, extra_xml=None):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("imsmanifest.xml", _MANIFEST.format(rid=manifest_id))
        if trigger:
            z.writestr("course_settings/canvas_export.txt", "Q\n")
        if extra_xml:
            for name, content in extra_xml.items():
                z.writestr(name, content)
    return path


# --- date shifting ---------------------------------------------------------

def test_shift_value_datetime_and_date():
    assert shift_value("2026-06-23T05:59:59", 365) == "2027-06-23T05:59:59"
    assert shift_value("2026-06-22", 365) == "2027-06-22"
    assert shift_value("2026-06-23T05:59:59", -365) == "2025-06-23T05:59:59"


def test_shift_value_leaves_offset_and_junk_untouched():
    # values with a tz offset aren't the naive Canvas form — don't touch them
    assert shift_value("2026-06-23T05:59:59-06:00", 365) == "2026-06-23T05:59:59-06:00"
    assert shift_value("complete", 365) == "complete"


def test_shift_dates_in_text_only_schedule_tags():
    xml = (
        "<a><due_at>2026-06-23T05:59:59</due_at>"
        "<created_at>2020-01-01T00:00:00</created_at>"  # must NOT move
        "<all_day_date>2026-06-22</all_day_date></a>"
    )
    out, n = shift_dates_in_text(xml, 365)
    assert n == 2
    assert "<due_at>2027-06-23T05:59:59</due_at>" in out
    assert "<all_day_date>2027-06-22</all_day_date>" in out
    assert "<created_at>2020-01-01T00:00:00</created_at>" in out  # untouched


def test_shift_is_reversible():
    xml = "<a><due_at>2026-06-23T05:59:59</due_at></a>"
    fwd, _ = shift_dates_in_text(xml, 365)
    back, _ = shift_dates_in_text(fwd, -365)
    assert back == xml


# --- validation: good + failure injection ----------------------------------

def test_valid_minimal_imscc(tmp_path):
    p = _make_imscc(tmp_path / "good.imscc")
    assert validate_imscc(p) == []


def test_catches_missing_trigger(tmp_path):
    p = _make_imscc(tmp_path / "notrigger.imscc", trigger=False)
    issues = validate_imscc(p)
    assert any("trigger" in i for i in issues)


def test_catches_human_readable_identifier(tmp_path):
    p = _make_imscc(tmp_path / "badid.imscc", manifest_id="assignment_week1")
    issues = validate_imscc(p)
    assert any("identifier" in i for i in issues)


def test_accepts_suffixed_and_i_prefixed_ids(tmp_path):
    for rid in ("g" + "b" * 32 + "_syllabus", "i" + "c" * 32):
        p = _make_imscc(tmp_path / "id.imscc", manifest_id=rid)
        assert validate_imscc(p) == [], rid


def test_catches_date_constraint_violation(tmp_path):
    bad = "<assignment><unlock_at>2026-06-30T00:00:00</unlock_at><due_at>2026-06-01T00:00:00</due_at></assignment>"
    p = _make_imscc(tmp_path / "baddate.imscc", extra_xml={"g111/assignment_settings.xml": bad})
    issues = validate_imscc(p)
    assert any("unlock_at is after due_at" in i for i in issues)


def test_catches_not_a_zip(tmp_path):
    p = tmp_path / "nope.imscc"
    p.write_text("not a zip", encoding="utf-8")
    assert any("ZIP" in i for i in validate_imscc(p))


# --- adjust round-trip (identifiers preserved) -----------------------------

def test_adjust_preserves_identifiers_and_shifts(tmp_path):
    src = _make_imscc(
        tmp_path / "src.imscc",
        extra_xml={"g1/assignment_settings.xml": "<a><due_at>2026-06-23T05:59:59</due_at></a>"},
    )
    out = tmp_path / "out.imscc"
    n = adjust_dates_in_imscc(src, out, 365)
    assert n == 1
    with zipfile.ZipFile(src) as za, zipfile.ZipFile(out) as zb:
        assert manifest_resource_identifiers(za.read("imsmanifest.xml").decode()) == \
               manifest_resource_identifiers(zb.read("imsmanifest.xml").decode())
        assert "2027-06-23T05:59:59" in zb.read("g1/assignment_settings.xml").decode()
    assert validate_imscc(out) == []


# --- CLI -------------------------------------------------------------------

def test_validate_cli_exit_codes(tmp_path):
    good = _make_imscc(tmp_path / "good.imscc")
    bad = _make_imscc(tmp_path / "bad.imscc", trigger=False)
    assert subprocess.run([sys.executable, str(VALIDATE_TOOL), str(good)]).returncode == 0
    assert subprocess.run([sys.executable, str(VALIDATE_TOOL), str(bad)]).returncode == 1


def test_adjust_cli(tmp_path):
    src = _make_imscc(
        tmp_path / "src.imscc",
        extra_xml={"g1/assignment_settings.xml": "<a><due_at>2026-06-23T05:59:59</due_at></a>"},
    )
    out = tmp_path / "out.imscc"
    r = subprocess.run(
        [sys.executable, str(ADJUST_TOOL), "--input", str(src), "--shift-days", "7", "--out", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    with zipfile.ZipFile(out) as z:
        assert "2026-06-30T05:59:59" in z.read("g1/assignment_settings.xml").decode()


# --- integration: real exports (gated, cross-course) -----------------------

def test_real_imscc_validate_and_shift_if_present(tmp_path):
    reals = _file_finder.list_imscc(name_hint="export")
    if not reals:
        pytest.skip("no real *_export.imscc in ~/Downloads — integration skipped")
    for real in reals:
        assert validate_imscc(real) == [], f"{real.name} should validate clean"
        out = tmp_path / f"shift_{real.name}"
        n = adjust_dates_in_imscc(real, out, 365)
        assert n > 0
        # identifiers preserved (so Canvas overwrites in place, not duplicates)
        with zipfile.ZipFile(real) as za, zipfile.ZipFile(out) as zb:
            assert manifest_resource_identifiers(za.read("imsmanifest.xml").decode("utf-8", "ignore")) == \
                   manifest_resource_identifiers(zb.read("imsmanifest.xml").decode("utf-8", "ignore"))
        assert validate_imscc(out) == []  # output still clean
        # reverse shift restores the original date count
        back = tmp_path / f"back_{real.name}"
        assert adjust_dates_in_imscc(out, back, -365) == n

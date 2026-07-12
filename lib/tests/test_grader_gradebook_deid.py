"""Tier 1 unit tests — gradebook de-identify / re-identify (Sprint 2).

Sources:
  lib/tools/grader_deidentify_gradebook.py  (build_reid_map, apply_deidentification)
  lib/tools/grader_reidentify_gradebook.py  (reidentify)

Verifies: codes reuse the toolbox-wide deid_code_for; PII is removed; re-ID is a
deterministic code lookup that exactly restores identity; scores edited while
de-identified survive re-ID; and a full CLI round-trip. Gated integration
round-trips the real DS 250 / DS 460 exports in ~/Downloads.
"""
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _csv_utils import read_canvas_gradebook_csv, write_canvas_gradebook_csv  # noqa: E402
from build_deid_master import deid_code_for  # noqa: E402
from grader_deidentify_gradebook import build_reid_map, apply_deidentification  # noqa: E402
from grader_reidentify_gradebook import reidentify  # noqa: E402
import _file_finder  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gradebook_sample.csv"
DEID_TOOL = _TOOLS_DIR / "grader_deidentify_gradebook.py"
REID_TOOL = _TOOLS_DIR / "grader_reidentify_gradebook.py"


def _deidentified():
    gb = read_canvas_gradebook_csv(FIXTURE)
    by_code = build_reid_map(gb, "S-", 6)
    apply_deidentification(gb, by_code, "S-", 6)
    return gb, by_code


# --- de-identification -----------------------------------------------------

def test_codes_reuse_toolbox_deid_code_for():
    gb = read_canvas_gradebook_csv(FIXTURE)
    by_code = build_reid_map(gb, "S-", 6)
    assert deid_code_for(2001) in by_code
    assert by_code[deid_code_for(2001)]["student"] == "Anon, Ada"
    assert by_code[deid_code_for(2002)]["sis_login_id"] == "student2002@example.edu"


def test_deid_replaces_name_and_blanks_pii():
    gb, _ = _deidentified()
    h = gb.header
    for s in gb.students:
        assert s.raw[h.index("Student")].startswith("S-")
        assert s.raw[h.index("ID")] == ""
        assert s.raw[h.index("SIS User ID")] == ""
        assert s.raw[h.index("SIS Login ID")] == ""
        assert s.raw[h.index("Section")] == "Section A2"  # not PII — kept


def test_deid_preserves_grades():
    gb, _ = _deidentified()
    # grades untouched by de-identification
    assert gb.students[0].get_grade("1001") == "95"
    assert gb.students[1].get_grade("1003") == "EX"


def test_deid_output_file_has_no_pii(tmp_path):
    gb, _ = _deidentified()
    out = tmp_path / "deid.csv"
    write_canvas_gradebook_csv(gb, out)
    text = out.read_text(encoding="utf-8")
    assert "Anon, Ada" not in text
    assert "student2001@example.edu" not in text
    assert "S-" in text


# --- re-identification -----------------------------------------------------

def test_deid_then_reid_restores_identity_exactly():
    original = [list(s.raw) for s in read_canvas_gradebook_csv(FIXTURE).students]
    gb, by_code = _deidentified()
    restored, unmatched = reidentify(gb, by_code)
    assert not unmatched
    assert restored == len(original)
    for s, orig in zip(gb.students, original):
        assert s.raw == orig  # byte-for-byte identity + grade restoration


def test_scores_edited_while_deidentified_survive_reid():
    gb, by_code = _deidentified()
    gb.students[1].set_grade("1001", "88")  # instructor edits against the code sheet
    reidentify(gb, by_code)
    assert gb.students[1].get_grade("1001") == "88"
    assert gb.students[1].student == "Byte, Ben"  # identity restored


def test_reid_reports_unmatched_codes():
    gb, _ = _deidentified()
    restored, unmatched = reidentify(gb, {})  # wrong/empty map
    assert restored == 0
    assert len(unmatched) == len(gb.students)


# --- CLI round-trip --------------------------------------------------------

def test_cli_roundtrip_and_no_names_printed(tmp_path):
    deid, mp, final = tmp_path / "deid.csv", tmp_path / "map.json", tmp_path / "final.csv"
    r1 = subprocess.run(
        [sys.executable, str(DEID_TOOL), "--input", str(FIXTURE), "--out", str(deid), "--map", str(mp)],
        capture_output=True, text=True,
    )
    assert r1.returncode == 0, r1.stderr
    assert "Anon, Ada" not in r1.stdout        # FERPA: never prints a name
    assert deid.exists() and mp.exists()

    r2 = subprocess.run(
        [sys.executable, str(REID_TOOL), "--input", str(deid), "--map", str(mp), "--out", str(final)],
        capture_output=True, text=True,
    )
    assert r2.returncode == 0, r2.stderr
    assert "Anon, Ada" not in r2.stdout
    gb_final = read_canvas_gradebook_csv(final)
    assert gb_final.students[0].student == "Anon, Ada"


def test_cli_reid_aborts_on_wrong_map(tmp_path):
    deid, mp, final = tmp_path / "deid.csv", tmp_path / "map.json", tmp_path / "final.csv"
    subprocess.run(
        [sys.executable, str(DEID_TOOL), "--input", str(FIXTURE), "--out", str(deid), "--map", str(mp)],
        capture_output=True, text=True, check=True,
    )
    empty = tmp_path / "empty.json"
    empty.write_text('{"by_code": {}}', encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(REID_TOOL), "--input", str(deid), "--map", str(empty), "--out", str(final)],
        capture_output=True, text=True,
    )
    assert r.returncode == 2
    assert not final.exists()


# --- integration: real exports (gated, cross-course) -----------------------

def test_real_gradebooks_roundtrip_if_present():
    reals = _file_finder.list_gradebook_csvs(name_hint="Grades")
    if not reals:
        pytest.skip("no real gradebook CSV in ~/Downloads — integration skipped")
    for real in reals:
        gb = read_canvas_gradebook_csv(real)
        original = [list(s.raw) for s in gb.students]
        by_code = build_reid_map(gb, "S-", 6)
        apply_deidentification(gb, by_code, "S-", 6)
        # PII actually gone from the in-memory rows
        si = gb.header.index("Student")
        assert all(s.raw[si].startswith("S-") for s in gb.students)
        restored, unmatched = reidentify(gb, by_code)
        assert not unmatched
        assert restored == len(original)
        for s, orig in zip(gb.students, original):
            assert s.raw == orig

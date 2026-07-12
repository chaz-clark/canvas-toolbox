"""Tier 1 unit tests — Canvas gradebook CSV parsing/writing (Sprint 1).

Source: lib/tools/_csv_utils.py
Fixture: lib/tests/fixtures/gradebook_sample.csv  (synthetic, mirrors the real
         120-col BYUI export structure at small scale — no PII).

Also includes a gated INTEGRATION test that parses the real export sitting in
~/Downloads (via _file_finder), skipped when it isn't present.
"""
import csv
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _csv_utils import (  # noqa: E402
    read_canvas_gradebook_csv,
    write_canvas_gradebook_csv,
    detect_csv_format,
    is_points_possible_row,
    IDENTITY_COLUMNS,
)
import _file_finder  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gradebook_sample.csv"


# --- detection -------------------------------------------------------------

def test_detect_true_on_gradebook():
    assert detect_csv_format(FIXTURE) is True


def test_detect_false_on_random_csv(tmp_path):
    p = tmp_path / "notes.csv"
    p.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    assert detect_csv_format(p) is False


def test_detect_false_on_missing(tmp_path):
    assert detect_csv_format(tmp_path / "nope.csv") is False


def test_is_points_possible_row_handles_leading_spaces():
    assert is_points_possible_row(["    Points Possible", "", ""]) is True
    assert is_points_possible_row(["Anon, Ada", "2001"]) is False


# --- parsing ---------------------------------------------------------------

def test_reads_identity_and_points_possible():
    gb = read_canvas_gradebook_csv(FIXTURE)
    assert gb.identity_columns == IDENTITY_COLUMNS
    assert gb.points_possible_row is not None
    assert gb.points_possible_row[0].strip() == "Points Possible"


def test_extracts_assignment_columns_only():
    gb = read_canvas_gradebook_csv(FIXTURE)
    ids = {a.assignment_id for a in gb.assignments}
    assert ids == {"1001", "1002", "1003"}
    hw = gb.assignment_by_id("1001")
    assert hw.name == "HW 1"
    assert hw.points_possible == "100"


def test_readonly_columns_classified():
    gb = read_canvas_gradebook_csv(FIXTURE)
    # group-total + 8 summary columns are read-only (not assignments)
    ro_headers = {gb.header[i] for i in gb.readonly_indices}
    assert "Current Score" in ro_headers
    assert "Final Grade" in ro_headers
    assert "Homework Current Score" in ro_headers
    # no assignment column leaked into read-only
    assert not any(h.endswith("(1001)") for h in ro_headers)


def test_student_rows_and_identity_access():
    gb = read_canvas_gradebook_csv(FIXTURE)
    assert len(gb.students) == 3
    ada = gb.students[0]
    assert ada.student == "Anon, Ada"      # comma preserved through CSV quoting
    assert ada.canvas_id == "2001"
    assert ada.section == "Section A2"


def test_get_grade_number_blank_and_excused():
    gb = read_canvas_gradebook_csv(FIXTURE)
    ada, ben, cid = gb.students
    assert ada.get_grade("1001") == "95"
    assert ben.get_grade("1001") == ""      # missing submission
    assert ben.get_grade("1003") == "EX"    # excused
    assert cid.get_grade("1002") == ""


# --- writing / round-trip --------------------------------------------------

def test_set_grade_updates_only_target_cell():
    gb = read_canvas_gradebook_csv(FIXTURE)
    ben = gb.students[1]
    before = list(ben.raw)
    ben.set_grade("1001", "88")
    assert ben.get_grade("1001") == "88"
    # every other cell untouched
    changed = [i for i, (a, b) in enumerate(zip(before, ben.raw)) if a != b]
    assert changed == [gb.assignment_by_id("1001").index]


def test_set_grade_rejects_unknown_assignment():
    gb = read_canvas_gradebook_csv(FIXTURE)
    with pytest.raises(KeyError):
        gb.students[0].set_grade("9999", "50")


def test_roundtrip_write_read_is_stable(tmp_path):
    gb = read_canvas_gradebook_csv(FIXTURE)
    out = tmp_path / "out.csv"
    write_canvas_gradebook_csv(gb, out)
    # raw cell grid identical after a read→write→read cycle
    gb2 = read_canvas_gradebook_csv(out)
    assert gb.to_rows() == gb2.to_rows()
    # and byte-identical rows to the original fixture
    orig = list(csv.reader(FIXTURE.open(newline="", encoding="utf-8-sig")))
    assert gb.to_rows() == orig


def test_edit_persists_through_write(tmp_path):
    gb = read_canvas_gradebook_csv(FIXTURE)
    gb.students[0].set_grade("1002", "10")
    out = tmp_path / "edited.csv"
    write_canvas_gradebook_csv(gb, out)
    reloaded = read_canvas_gradebook_csv(out)
    assert reloaded.students[0].get_grade("1002") == "10"


def test_writer_uses_lf_and_is_idempotent(tmp_path):
    # Canvas exports LF; csv default is CRLF. Writer must emit LF so an
    # unedited round-trip is byte-clean, and be stable across re-writes.
    gb = read_canvas_gradebook_csv(FIXTURE)
    a = tmp_path / "a.csv"
    write_canvas_gradebook_csv(gb, a)
    assert b"\r\n" not in a.read_bytes()
    b = tmp_path / "b.csv"
    write_canvas_gradebook_csv(read_canvas_gradebook_csv(a), b)
    assert a.read_bytes() == b.read_bytes()


def test_read_rejects_non_gradebook(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not look like a Canvas gradebook"):
        read_canvas_gradebook_csv(bad)


# --- adaptability: different identity layout + size (synthetic) ------------

def test_adapts_to_different_identity_layout_and_size(tmp_path):
    # 7 identity cols (incl. 'Integration ID'), 2 assignments, no group-totals,
    # 4 students — a shape unlike the fixture. Identity is DERIVED, not hardcoded.
    header = [
        "Student", "ID", "SIS User ID", "SIS Login ID", "Integration ID",
        "Root Account", "Section",
        "Essay (500)", "Final Exam (501)",
        "Current Score", "Final Score",
    ]
    pp = ["    Points Possible", "", "", "", "", "", "", "50", "100",
          "(read only)", "(read only)"]
    data = [
        [f"S{n}, T", str(9000 + n), f"i{n}", f"s{n}@e.edu", f"int{n}", "e.edu",
         "Section 1", str(40 + n), str(90 + n), "x", "x"]
        for n in range(4)
    ]
    p = tmp_path / "other.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header); w.writerow(pp)
        for r in data:
            w.writerow(r)

    gb = read_canvas_gradebook_csv(p)
    assert gb.identity_columns == header[:7]          # includes Integration ID
    assert "Integration ID" in gb.identity_columns
    assert {a.assignment_id for a in gb.assignments} == {"500", "501"}
    assert gb.assignment_by_id("501").name == "Final Exam"
    assert len(gb.students) == 4
    assert gb.students[0].get_grade("500") == "40"


# --- integration: ALL real exports in ~/Downloads (gated, cross-course) -----

def test_parses_all_real_exports_if_present():
    reals = _file_finder.list_gradebook_csvs(name_hint="Grades")
    if not reals:
        pytest.skip("no real gradebook CSV in ~/Downloads — integration skipped")
    for real in reals:  # e.g. DS 250 (120 cols) AND DS 460 (78 cols)
        gb = read_canvas_gradebook_csv(real)
        assert "Student" in gb.identity_columns and "ID" in gb.identity_columns
        assert gb.points_possible_row is not None
        assert len(gb.assignments) > 0
        assert len(gb.students) > 0
        assert all(a.assignment_id.isdigit() for a in gb.assignments)
        # assignment and read-only columns must never overlap
        assign_idx = {a.index for a in gb.assignments}
        assert assign_idx.isdisjoint(gb.readonly_indices)

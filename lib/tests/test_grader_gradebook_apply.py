"""Tier 1 unit tests — offline scores→gradebook apply (Sprint 3).

Source: lib/tools/grader_gradebook_apply.py
Resolves scores to gradebook rows by Canvas id / de-id code / name, applies them
to a target assignment column, and fails loud on any unresolved key. Gated
integration applies scores to the real DS 250 / DS 460 exports.
"""
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _csv_utils import read_canvas_gradebook_csv  # noqa: E402
from build_deid_master import deid_code_for  # noqa: E402
from grader_gradebook_apply import (  # noqa: E402
    resolve_target_assignment,
    build_roster_index,
    resolve_student,
    read_scores_csv,
    apply_scores,
)
import _file_finder  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gradebook_sample.csv"
TOOL = _TOOLS_DIR / "grader_gradebook_apply.py"


def _gb():
    return read_canvas_gradebook_csv(FIXTURE)


# --- assignment targeting --------------------------------------------------

def test_target_by_id_and_name():
    gb = _gb()
    assert resolve_target_assignment(gb, assignment_id="1002").name == "Quiz 1"
    assert resolve_target_assignment(gb, assignment_name="HW 1").assignment_id == "1001"


def test_target_unknown_or_missing_raises():
    gb = _gb()
    with pytest.raises(ValueError):
        resolve_target_assignment(gb, assignment_id="9999")
    with pytest.raises(ValueError):
        resolve_target_assignment(gb, None, None)


# --- key resolution (id / code / name) -------------------------------------

def test_resolve_by_three_key_forms():
    gb = _gb()
    idx = build_roster_index(gb)
    ada = gb.students[0]
    assert resolve_student("2001", idx) is ada                     # canvas id
    assert resolve_student(deid_code_for(2001), idx) is ada        # de-id code
    assert resolve_student("Anon, Ada", idx) is ada                # name
    assert resolve_student("nobody", idx) is None


# --- apply -----------------------------------------------------------------

def test_apply_sets_only_target_assignment():
    gb = _gb()
    idx = build_roster_index(gb)
    a = resolve_target_assignment(gb, assignment_id="1002")
    unresolved = apply_scores(gb, a, [("2001", "10"), ("2002", "7")], idx)
    assert unresolved == []
    assert gb.students[0].get_grade("1002") == "10"
    assert gb.students[1].get_grade("1002") == "7"
    # other assignments untouched
    assert gb.students[0].get_grade("1001") == "95"


def test_apply_reports_unresolved():
    gb = _gb()
    idx = build_roster_index(gb)
    a = resolve_target_assignment(gb, assignment_id="1001")
    unresolved = apply_scores(gb, a, [("2001", "5"), ("9999", "5")], idx)
    assert unresolved == ["9999"]


def test_read_scores_csv(tmp_path):
    p = tmp_path / "scores.csv"
    p.write_text("key,score\n2001,10\n2002,8\n\n", encoding="utf-8")
    assert read_scores_csv(p) == [("2001", "10"), ("2002", "8")]


# --- CLI -------------------------------------------------------------------

def test_cli_apply_by_id(tmp_path):
    scores = tmp_path / "scores.csv"
    scores.write_text("key,score\n2001,10\n2002,9\n2003,8\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    r = subprocess.run(
        [sys.executable, str(TOOL), "--scores", str(scores), "--assignment-id", "1002",
         "--gradebook", str(FIXTURE), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    gb = read_canvas_gradebook_csv(out)
    assert gb.students[0].get_grade("1002") == "10"
    assert gb.students[2].get_grade("1002") == "8"


def test_cli_aborts_on_unresolved(tmp_path):
    scores = tmp_path / "scores.csv"
    scores.write_text("key,score\n9999,10\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    r = subprocess.run(
        [sys.executable, str(TOOL), "--scores", str(scores), "--assignment-id", "1001",
         "--gradebook", str(FIXTURE), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 2
    assert not out.exists()


# --- integration: real gradebooks (gated) ----------------------------------

def test_apply_to_real_gradebooks_if_present():
    reals = _file_finder.list_gradebook_csvs(name_hint="Grades")
    if not reals:
        pytest.skip("no real gradebook CSV in ~/Downloads — integration skipped")
    for real in reals:
        gb = read_canvas_gradebook_csv(real)
        idx = build_roster_index(gb)
        target = gb.assignments[0]
        s0, s1 = gb.students[0], gb.students[1]
        # apply by real canvas id and by de-id code — both must land
        unresolved = apply_scores(
            gb, target,
            [(s0.canvas_id, "1"), (deid_code_for(int(s1.canvas_id)), "0")],
            idx,
        )
        assert unresolved == []
        assert s0.get_grade(target.assignment_id) == "1"
        assert s1.get_grade(target.assignment_id) == "0"

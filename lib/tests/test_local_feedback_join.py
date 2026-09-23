"""Unit tests — local_feedback_join.py (#339 Phase A).

The dangerous failures here are quiet ones: a name reaching stdout/stderr (the
agent running this tool would see it), a partial join written when a results
code doesn't match any roster row, and a display name that changes between
runs because collision detection was scoped to the wrong set of students.
"""
import csv
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import local_feedback_join as lfj  # noqa: E402
from local_feedback_join import (  # noqa: E402
    join_feedback,
    load_roster,
    resolve_display_names,
    write_output,
)

_ROSTER_HEADER = ["OrgDefinedId", "Username", "LastName", "FirstName", "Email"]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def _roster_csv(tmp_path: Path, rows: list[list[str]]) -> Path:
    p = tmp_path / "roster.csv"
    _write_csv(p, _ROSTER_HEADER, rows)
    return p


def _results_csv(tmp_path: Path, rows: list[list[str]]) -> Path:
    p = tmp_path / "results.csv"
    _write_csv(p, ["id", "text"], rows)
    return p


# --- load_roster / column validation --------------------------------------

def test_load_roster_reads_default_d2l_columns(tmp_path):
    p = _roster_csv(tmp_path, [["1001", "asmith", "Smith", "Alice", "a@x.edu"]])
    roster = load_roster(p, "OrgDefinedId", "FirstName", "LastName")
    assert roster == {"1001": {"first": "Alice", "last": "Smith"}}


def test_load_roster_missing_column_raises_with_actual_header(tmp_path):
    p = tmp_path / "bad.csv"
    _write_csv(p, ["StudentId", "Name"], [["1", "x"]])
    with pytest.raises(ValueError, match="OrgDefinedId") as exc_info:
        load_roster(p, "OrgDefinedId", "FirstName", "LastName")
    assert "StudentId" in str(exc_info.value)


def test_load_roster_skips_blank_id_rows(tmp_path):
    p = _roster_csv(tmp_path, [["", "x", "Y", "Z", "e@x.edu"],
                               ["1002", "bsmith", "Smith", "Bob", "b@x.edu"]])
    roster = load_roster(p, "OrgDefinedId", "FirstName", "LastName")
    assert list(roster.keys()) == ["1002"]


# --- resolve_display_names — collision handling -----------------------------

def test_unique_first_names_get_first_name_only():
    roster = {"1": {"first": "Alice", "last": "Smith"}, "2": {"first": "Bob", "last": "Jones"}}
    assert resolve_display_names(roster) == {"1": "Alice", "2": "Bob"}


def test_shared_first_name_gets_last_initial_for_both():
    roster = {"1": {"first": "Emma", "last": "Katz"}, "2": {"first": "Emma", "last": "Lopez"},
              "3": {"first": "Bob", "last": "Jones"}}
    names = resolve_display_names(roster)
    assert names == {"1": "Emma K.", "2": "Emma L.", "3": "Bob"}


def test_collision_is_case_insensitive():
    roster = {"1": {"first": "emma", "last": "Katz"}, "2": {"first": "Emma", "last": "Lopez"}}
    names = resolve_display_names(roster)
    assert names["1"] == "emma K." and names["2"] == "Emma L."


def test_collision_scope_is_whole_roster_not_just_results():
    """Stability property: a student's display name must not depend on which
    OTHER students happen to have results in a given run."""
    roster = {"1": {"first": "Emma", "last": "Katz"}, "2": {"first": "Emma", "last": "Lopez"},
              "3": {"first": "Bob", "last": "Jones"}}
    names = resolve_display_names(roster)
    # Even a join that only ever touches student "1" must still see the
    # collision, because it's computed from the roster, not from results.
    assert names["1"] == "Emma K."


def test_collision_without_last_name_falls_back_to_bare_first_name():
    """Can't disambiguate with an initial that doesn't exist — bare first name
    is the honest fallback, not a crash."""
    roster = {"1": {"first": "Emma", "last": ""}, "2": {"first": "Emma", "last": "Lopez"}}
    names = resolve_display_names(roster)
    assert names["1"] == "Emma"


def test_missing_first_name_never_silently_becomes_empty_string():
    roster = {"1": {"first": "", "last": "Smith"}}
    names = resolve_display_names(roster)
    assert names["1"] == "(no first name on file)"


# --- join_feedback -----------------------------------------------------------

def test_join_matches_by_code():
    roster = {"1": {"first": "Alice", "last": "Smith"}}
    results = [{"code": "1", "text": "Great work on the project."}]
    joined, unmatched = join_feedback(roster, results)
    assert unmatched == []
    assert joined == [{"code": "1", "name": "Alice", "text": "Great work on the project."}]


def test_join_flags_unmatched_results_code():
    roster = {"1": {"first": "Alice", "last": "Smith"}}
    results = [{"code": "1", "text": "ok"}, {"code": "999", "text": "mystery"}]
    joined, unmatched = join_feedback(roster, results)
    assert unmatched == ["999"]
    assert len(joined) == 1  # the matched row is still resolved


def test_roster_row_with_no_results_is_simply_absent_not_an_error():
    roster = {"1": {"first": "Alice", "last": "Smith"}, "2": {"first": "Bob", "last": "Jones"}}
    results = [{"code": "1", "text": "ok"}]
    joined, unmatched = join_feedback(roster, results)
    assert unmatched == []
    assert [r["code"] for r in joined] == ["1"]


# --- write_output -------------------------------------------------------------

def test_write_output_writes_the_named_csv(tmp_path):
    out = tmp_path / "out.csv"
    write_output(out, [{"code": "1", "name": "Alice", "text": "great job"}])
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert rows == [{"code": "1", "name": "Alice", "text": "great job"}]


# --- main(): the FERPA-critical property — no name ever reaches stdout/stderr -

def _run(monkeypatch, capsys, tmp_path, roster_rows, results_rows, extra_argv=()):
    roster = _roster_csv(tmp_path, roster_rows)
    results = _results_csv(tmp_path, results_rows)
    out = tmp_path / "out.csv"
    monkeypatch.setattr(sys, "argv", [
        "local_feedback_join.py", "--roster", str(roster), "--results", str(results),
        "--output", str(out), *extra_argv,
    ])
    rc = lfj.main()
    captured = capsys.readouterr()
    return rc, captured, out


def test_dry_run_writes_nothing_and_prints_no_name(monkeypatch, capsys, tmp_path):
    rc, cap, out = _run(monkeypatch, capsys, tmp_path,
                        [["1", "asmith", "Smith", "Alice", "a@x.edu"]],
                        [["1", "Great work, Alice — see the rubric notes."]])
    assert rc == 0
    assert not out.exists()
    assert "Alice" not in cap.out and "Alice" not in cap.err


def test_apply_writes_file_and_prints_no_name(monkeypatch, capsys, tmp_path):
    rc, cap, out = _run(monkeypatch, capsys, tmp_path,
                        [["1", "asmith", "Smith", "Alice", "a@x.edu"]],
                        [["1", "Great work, Alice."]], extra_argv=["--apply"])
    assert rc == 0
    assert out.exists()
    assert "Alice" not in cap.out and "Alice" not in cap.err
    # The name IS in the file — that's the point, the file is for the instructor.
    assert "Alice" in out.read_text(encoding="utf-8")


def test_apply_with_collision_prints_no_name_either(monkeypatch, capsys, tmp_path):
    rc, cap, out = _run(monkeypatch, capsys, tmp_path,
                        [["1", "ek", "Katz", "Emma", "e@x.edu"],
                         ["2", "el", "Lopez", "Emma", "e2@x.edu"]],
                        [["1", "good"], ["2", "good too"]], extra_argv=["--apply"])
    assert rc == 0
    assert "Emma" not in cap.out and "Emma" not in cap.err and "Katz" not in cap.out
    content = out.read_text(encoding="utf-8")
    assert "Emma K." in content and "Emma L." in content


def test_unmatched_code_refuses_and_writes_nothing(monkeypatch, capsys, tmp_path):
    rc, cap, out = _run(monkeypatch, capsys, tmp_path,
                        [["1", "asmith", "Smith", "Alice", "a@x.edu"]],
                        [["999", "mystery student"]], extra_argv=["--apply"])
    assert rc == 1
    assert not out.exists()
    assert "999" in cap.err  # the CODE is safe to print, unlike a name
    assert "ERROR" in cap.err


def test_missing_roster_column_exits_2(monkeypatch, capsys, tmp_path):
    bad_roster = tmp_path / "roster.csv"
    _write_csv(bad_roster, ["StudentId", "Name"], [["1", "x"]])
    results = _results_csv(tmp_path, [["1", "ok"]])
    monkeypatch.setattr(sys, "argv", [
        "local_feedback_join.py", "--roster", str(bad_roster), "--results", str(results),
        "--output", str(tmp_path / "out.csv"),
    ])
    assert lfj.main() == 2

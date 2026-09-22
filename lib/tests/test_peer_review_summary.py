"""Unit tests — peer rating summary (#331).

The quiet failures: counting the instructor's GRADING assessment as a peer rating,
counting a criterion with no rating as zero, mixing a yes/no and a 1-5 scale in one
average, and letting a name or a free-text comment reach the output.
"""
import csv
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import peer_review_summary as prs  # noqa: E402
from peer_review_summary import summarize  # noqa: E402

_CRIT = [{"id": "_a", "description": "Prepared?", "points": 1},
         {"id": "_b", "description": "Effort", "points": 5}]
_SUBS = {100: 11, 200: 22}                       # submission id -> user id


def _asm(sub, assessor, a=None, b=None, kind="peer_review", **extra):
    return {"assessment_type": kind, "artifact_id": sub, "assessor_id": assessor,
            "data": [{"criterion_id": "_a", "points": a}, {"criterion_id": "_b", "points": b}],
            **extra}


# --- summarize --------------------------------------------------------------

def test_averages_points_per_criterion_across_reviewers():
    r = summarize([_asm(100, 22, 1, 5), _asm(100, 33, 0, 3)], _CRIT, _SUBS)[11]
    assert r["n_peer"] == 2
    assert r["peer"] == {"_a": 0.5, "_b": 4.0}


def test_overall_weighs_a_yes_no_and_a_one_to_five_equally():
    """0.5 of a yes/no and 4/5 of a scale -> (0.5 + 0.8) / 2, not (0.5 + 4) / 6."""
    r = summarize([_asm(100, 22, 1, 5), _asm(100, 33, 0, 3)], _CRIT, _SUBS)[11]
    assert r["peer_pct"] == pytest.approx((0.5 + 0.8) / 2)


def test_grading_assessments_are_not_peer_ratings():
    rows = summarize([_asm(100, 999, 1, 5, kind="grading"),
                      _asm(100, 999, 1, 5, kind="provisional_grade")], _CRIT, _SUBS)
    assert rows == {}


def test_a_criterion_left_unrated_is_skipped_not_counted_as_zero():
    r = summarize([_asm(100, 22, None, 4)], _CRIT, _SUBS)[11]
    assert "_a" not in r["peer"] and r["peer"]["_b"] == 4.0
    assert r["peer_pct"] == pytest.approx(0.8)


def test_assessment_by_the_reviewee_is_self_not_peer():
    r = summarize([_asm(100, 11, 1, 5), _asm(100, 22, 0, 1)], _CRIT, _SUBS)[11]
    assert r["n_self"] == 1 and r["n_peer"] == 1
    assert r["self_pct"] == pytest.approx(1.0)
    assert r["peer_pct"] == pytest.approx((0 + 0.2) / 2)


def test_assessment_on_an_unknown_submission_is_ignored():
    assert summarize([_asm(999, 22, 1, 5)], _CRIT, _SUBS) == {}


def test_points_for_an_unknown_criterion_are_ignored():
    a = _asm(100, 22, 1, 5)
    a["data"].append({"criterion_id": "_zzz", "points": 50})
    assert summarize([a], _CRIT, _SUBS)[11]["peer"].keys() == {"_a", "_b"}


def test_each_reviewee_is_separate():
    rows = summarize([_asm(100, 22, 1, 5), _asm(200, 11, 0, 1)], _CRIT, _SUBS)
    assert rows[11]["n_peer"] == 1 and rows[22]["n_peer"] == 1
    assert rows[11]["peer_pct"] > rows[22]["peer_pct"]


# --- main(): mocked Canvas --------------------------------------------------

_LEAKS = ["Priscilla Wanderwell", "Ferdinand Oakhaven", "great teammate, Priscilla helped a lot"]


def _canvas(assessments=None, rubric_settings=True):
    def get_all(endpoint, params=None):
        if endpoint.endswith("/assignments") and params:
            return [{"id": 5, "name": "Prep ratings",
                     "rubric_settings": {"id": 8} if rubric_settings else None}]
        if endpoint.endswith("/assignments/5"):
            return {"id": 5, "name": "Prep ratings",
                    "rubric_settings": {"id": 8} if rubric_settings else None}
        if endpoint == "/courses/1/rubrics/8":
            return {"id": 8, "data": _CRIT,
                    "assessments": _default() if assessments is None else assessments}
        if endpoint.endswith("/submissions"):      # Canvas can return names here
            return [{"id": sid, "user_id": uid, "user": {"name": n}}
                    for (sid, uid), n in zip(_SUBS.items(), _LEAKS)]
        raise AssertionError(endpoint)
    return get_all


def _default():
    return [_asm(100, 22, 1, 5, assessor_name=_LEAKS[0],
                 data_comment=_LEAKS[2]),
            _asm(200, 11, 0, 2, assessor_name=_LEAKS[1])]


def _run(monkeypatch, capsys, get_all, argv=()):
    monkeypatch.setattr(prs, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(prs, "CANVAS_BASE_URL", "https://x")
    monkeypatch.setattr(prs.guard, "enforce", lambda **k: None)
    monkeypatch.setattr(prs, "_get_all", get_all)
    monkeypatch.setattr(sys, "argv", ["peer_review_summary.py", "--course-id", "1",
                                      "--assignment-id", "5", *argv])
    rc = prs.main()
    return rc, capsys.readouterr()


def test_report_lists_reviewees_by_user_id(monkeypatch, capsys):
    rc, out = _run(monkeypatch, capsys, _canvas())
    assert rc == 0 and "11" in out.out and "22" in out.out and "peer_overall" in out.out


def test_output_has_no_names_or_comments(monkeypatch, capsys):
    """Canvas returns assessor names and comment text; only points may reach output."""
    _, out = _run(monkeypatch, capsys, _canvas())
    text = out.out + out.err
    for leak in _LEAKS:
        assert leak not in text
        assert all(part not in text for part in leak.split() if len(part) > 5)


def test_csv_is_user_id_keyed_and_name_free(monkeypatch, capsys, tmp_path):
    path = tmp_path / "out.csv"
    _run(monkeypatch, capsys, _canvas(), ["--csv", str(path)])
    text = path.read_text(encoding="utf-8")
    rows = list(csv.reader(text.splitlines()))
    assert rows[0][0] == "user_id" and {r[0] for r in rows[1:]} == {"11", "22"}
    assert not any(leak in text for leak in _LEAKS)


def test_flags_rows_resting_on_fewer_than_three_ratings(monkeypatch, capsys):
    _, out = _run(monkeypatch, capsys, _canvas())
    assert "fewer than 3" in out.out


def test_no_assessments_yet_is_not_an_error(monkeypatch, capsys):
    rc, out = _run(monkeypatch, capsys, _canvas(assessments=[]))
    assert rc == 0 and "no peer assessments yet" in out.out


def test_assignment_without_a_rubric_exits_2(monkeypatch, capsys):
    rc, out = _run(monkeypatch, capsys, _canvas(rubric_settings=False))
    assert rc == 2 and "no rubric" in out.out


def test_unreadable_canvas_data_exits_1(monkeypatch, capsys):
    good = _canvas()
    rc, out = _run(monkeypatch, capsys,
                   lambda ep, p=None: None if ep.endswith("/submissions") else good(ep, p))
    assert rc == 1 and "could not read" in out.out


def test_tool_never_writes_to_canvas():
    """Read-only by construction: no HTTP mutation verb in the module."""
    src = (_TOOLS_DIR / "peer_review_summary.py").read_text(encoding="utf-8")
    assert "requests.post" not in src and "requests.put" not in src \
        and "requests.delete" not in src

"""Tier 1 unit tests — student_quiz_time_extension pure-logic helpers.

Source: lib/tools/student_quiz_time_extension.py
  - compute_extra_minutes   (multiplier → extra minutes, ceil)
  - filter_timed_quizzes    (skip untimed quizzes)
  - resolve_user_id_from_master  (CSV lookup, PII-aware)
  - build_extension_payload (POST body construction)

No Canvas API calls. Pure functions in/out.
"""
import csv
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from student_quiz_time_extension import (  # noqa: E402
    build_extension_payload,
    compute_extra_minutes,
    filter_timed_quizzes,
    resolve_user_id_from_master,
)


# ---------------------------------------------------------------------------
# compute_extra_minutes — multiplier to extra minutes
# ---------------------------------------------------------------------------

def test_extra_minutes_15x_on_60min_quiz():
    """1.5x on a 60-minute quiz → 30 extra minutes (50% of 60)."""
    assert compute_extra_minutes(60, 1.5) == 30


def test_extra_minutes_20x_on_60min_quiz():
    """2.0x on a 60-minute quiz → 60 extra minutes (double time)."""
    assert compute_extra_minutes(60, 2.0) == 60


def test_extra_minutes_125x_on_60min_quiz():
    """1.25x on a 60-minute quiz → 15 extra minutes."""
    assert compute_extra_minutes(60, 1.25) == 15


def test_extra_minutes_ceils_partial_minute():
    """1.5x on a 45-minute quiz → 22.5 → ceil → 23 minutes.
    Always round UP so the student never gets less than promised."""
    assert compute_extra_minutes(45, 1.5) == 23


def test_extra_minutes_ceils_one_third():
    """1.33x on a 60-minute quiz → 19.8 → 20 minutes."""
    assert compute_extra_minutes(60, 1.33) == 20


def test_extra_minutes_none_for_untimed_quiz():
    """time_limit is None (untimed quiz) → return None so caller skips."""
    assert compute_extra_minutes(None, 1.5) is None


def test_extra_minutes_none_for_zero_time_limit():
    """A time_limit of 0 (or negative) is meaningless → return None."""
    assert compute_extra_minutes(0, 1.5) is None
    assert compute_extra_minutes(-5, 1.5) is None


def test_extra_minutes_zero_at_multiplier_1():
    """1.0x = no extension → 0 extra minutes (caller may skip)."""
    assert compute_extra_minutes(60, 1.0) == 0


def test_extra_minutes_zero_at_multiplier_less_than_1():
    """Multiplier < 1 doesn't make sense for accommodations; return 0
    rather than negative. (CLI validates > 1.0 before getting here, but
    the helper is defensive.)"""
    assert compute_extra_minutes(60, 0.5) == 0


# ---------------------------------------------------------------------------
# filter_timed_quizzes — skip untimed quizzes
# ---------------------------------------------------------------------------

def test_filter_keeps_quiz_with_time_limit():
    quizzes = [{"id": 1, "time_limit": 60}]
    assert len(filter_timed_quizzes(quizzes)) == 1


def test_filter_drops_quiz_with_null_time_limit():
    """Untimed quizzes don't need an extension."""
    quizzes = [{"id": 1, "time_limit": None}]
    assert filter_timed_quizzes(quizzes) == []


def test_filter_drops_quiz_with_missing_time_limit_key():
    """Defensive: time_limit key absent entirely."""
    quizzes = [{"id": 1}]
    assert filter_timed_quizzes(quizzes) == []


def test_filter_drops_quiz_with_zero_time_limit():
    quizzes = [{"id": 1, "time_limit": 0}]
    assert filter_timed_quizzes(quizzes) == []


def test_filter_mixed_set():
    quizzes = [
        {"id": 1, "time_limit": 60},   # keep
        {"id": 2, "time_limit": None}, # drop
        {"id": 3, "time_limit": 30},   # keep
        {"id": 4},                      # drop
        {"id": 5, "time_limit": 0},    # drop
    ]
    out = filter_timed_quizzes(quizzes)
    assert sorted(q["id"] for q in out) == [1, 3]


# ---------------------------------------------------------------------------
# resolve_user_id_from_master — CSV lookup (duplicated helper)
# ---------------------------------------------------------------------------

def _write_master(tmp_path: Path) -> Path:
    p = tmp_path / ".deid_master.csv"
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["deid_code", "user_id",
                                            "sortable_name", "withdrawn"])
        w.writeheader()
        w.writerow({"deid_code": "S-68BC40", "user_id": "900001",
                    "sortable_name": "Anon, Ada", "withdrawn": "0"})
    return p


def test_resolve_basic(tmp_path):
    p = _write_master(tmp_path)
    assert resolve_user_id_from_master(p, "S-68BC40") == 900001


def test_resolve_case_insensitive(tmp_path):
    p = _write_master(tmp_path)
    assert resolve_user_id_from_master(p, "s-68bc40") == 900001


def test_resolve_missing_master_points_at_builder(tmp_path):
    nope = tmp_path / "absent.csv"
    with pytest.raises(FileNotFoundError) as exc_info:
        resolve_user_id_from_master(nope, "S-X")
    assert "build_deid_master" in str(exc_info.value)


def test_resolve_missing_code(tmp_path):
    p = _write_master(tmp_path)
    with pytest.raises(KeyError):
        resolve_user_id_from_master(p, "S-NOTHERE")


# ---------------------------------------------------------------------------
# build_extension_payload — POST body
# ---------------------------------------------------------------------------

def test_payload_includes_user_id():
    payload = build_extension_payload(user_id=900001, extra_time_minutes=30)
    assert payload["quiz_extensions[][user_id]"] == 900001


def test_payload_includes_extra_time():
    payload = build_extension_payload(user_id=1, extra_time_minutes=30)
    assert payload["quiz_extensions[][extra_time]"] == 30


def test_payload_canvas_array_syntax():
    """Canvas requires array-suffix keys ([]) for quiz_extensions.
    If we ever drop them, the API silently ignores the extension."""
    payload = build_extension_payload(user_id=1, extra_time_minutes=30)
    for key in payload:
        assert "[]" in key, f"missing array syntax in key: {key}"


# ---------------------------------------------------------------------------
# build_extension_payload — attempt / unlock / end_at options (#421)
# ---------------------------------------------------------------------------

def test_payload_time_only_unchanged():
    assert build_extension_payload(7, 30) == {
        "quiz_extensions[][user_id]": 7,
        "quiz_extensions[][extra_time]": 30,
    }


def test_payload_extra_attempts_only_omits_extra_time():
    p = build_extension_payload(7, extra_attempts=1)
    assert p == {
        "quiz_extensions[][user_id]": 7,
        "quiz_extensions[][extra_attempts]": 1,
    }


def test_payload_all_options():
    p = build_extension_payload(7, 30, extra_attempts=2,
                                manually_unlocked=True, extend_from_end_at=60)
    assert p["quiz_extensions[][extra_attempts]"] == 2
    assert p["quiz_extensions[][manually_unlocked]"] == "true"
    assert p["quiz_extensions[][extend_from_end_at]"] == 60
    assert p["quiz_extensions[][extra_time]"] == 30


# ---------------------------------------------------------------------------
# New Quizzes (#513): the per-quiz accommodations API
# ---------------------------------------------------------------------------

from student_quiz_time_extension import (  # noqa: E402
    accommodation_result,
    timed_new_quizzes,
)

# Shapes from GET /api/quiz/v1/courses/:id/quizzes and the accommodations POST,
# as the DS 250 sandbox returned them (2026-11-26).
_NQ_TIMED = {"id": "17741295", "title": "FIXTURE: New Quiz",
             "quiz_settings": {"has_time_limit": True, "session_time_limit_in_seconds": 600}}
_NQ_UNTIMED = {"id": "17741296", "title": "Untimed",
               "quiz_settings": {"has_time_limit": False, "session_time_limit_in_seconds": 0}}
_OK = {"message": "Accommodations processed", "successful": [{"user_id": 946791}], "failed": []}


def test_timed_new_quizzes_keeps_timed_ones_in_minutes():
    out = timed_new_quizzes([_NQ_TIMED, _NQ_UNTIMED, {"id": "3", "title": "no settings"}])
    assert out == [{"id": 17741295, "title": "FIXTURE: New Quiz", "time_limit": 10.0, "new_quiz": True}]


def test_new_quiz_extra_minutes_use_its_own_limit():
    q = timed_new_quizzes([_NQ_TIMED])[0]
    assert compute_extra_minutes(q["time_limit"], 1.5) == 5
    assert compute_extra_minutes(q["time_limit"], 2.0) == 10


def test_accommodation_counts_only_when_the_student_is_successful():
    assert accommodation_result(200, _OK, 946791) == (True, "")
    # A 200 can still list the student as failed: that is a failure.
    bad = {"message": "Accommodations processed", "successful": [],
           "failed": [{"user_id": 946791, "error": "User not found"}]}
    assert accommodation_result(200, bad, 946791) == (False, "User not found")
    assert accommodation_result(401, {"message": "User does not have permission"}, 946791)[0] is False
    assert accommodation_result(200, {"successful": [{"user_id": 1}], "failed": []}, 946791)[0] is False


def _run(monkeypatch, capsys, argv, classic=(), new=(), nq_reply=(200, _OK)):
    import student_quiz_time_extension as sqt
    sent = {"classic": [], "new": []}
    monkeypatch.setattr(sqt, "_course_guard", lambda *a, **k: None)
    monkeypatch.setattr(sqt, "fetch_timed_quizzes", lambda *a, **k: list(classic))
    monkeypatch.setattr(sqt, "fetch_new_quizzes", lambda *a, **k: list(new))
    monkeypatch.setattr(sqt, "post_extension", lambda b, c, qid, payload, t: sent["classic"].append((qid, payload)) or (200, {}))
    monkeypatch.setattr(sqt, "post_new_quiz_accommodation",
                        lambda b, c, aid, body, t: sent["new"].append((aid, body)) or nq_reply)
    for k, v in {"CANVAS_BASE_URL": "http://127.0.0.1:9", "CANVAS_COURSE_ID": "1", "CANVAS_API_TOKEN": "x"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "argv", ["student_quiz_time_extension.py", "--user-id", "946791", *argv])
    code = sqt.main()
    out = capsys.readouterr()
    return code, sent, out.out, out.err


def test_all_timed_covers_classic_and_new_quizzes(monkeypatch, capsys):
    classic = [{"id": 1, "title": "Classic", "time_limit": 30}]
    code, sent, out, err = _run(monkeypatch, capsys, ["--multiplier", "1.5", "--all-timed", "--apply",
                                                      "--no-force-recalc"], classic=classic, new=[_NQ_TIMED, _NQ_UNTIMED])
    assert code == 0
    assert [q for q, _ in sent["classic"]] == [1]
    assert sent["new"] == [(17741295, [{"user_id": 946791, "extra_time": 5}])]
    assert "Moderate" in out  # Canvas can't be asked whether it applied: say how to check


def test_all_timed_preview_lists_new_quizzes_and_sends_nothing(monkeypatch, capsys):
    code, sent, out, err = _run(monkeypatch, capsys, ["--multiplier", "2.0", "--all-timed"], new=[_NQ_TIMED])
    assert code == 0 and sent == {"classic": [], "new": []}
    assert "New Quiz 17741295" in out and "+10 min" in out


def test_a_failed_student_in_a_200_is_a_failure(monkeypatch, capsys):
    bad = (200, {"successful": [], "failed": [{"user_id": 946791, "error": "User not found"}]})
    code, sent, out, err = _run(monkeypatch, capsys, ["--multiplier", "1.5", "--all-timed", "--apply"],
                                new=[_NQ_TIMED], nq_reply=bad)
    assert code == 1 and "User not found" in out


def test_one_new_quiz_with_an_extra_attempt(monkeypatch, capsys):
    import student_quiz_time_extension as sqt
    monkeypatch.setattr(sqt, "fetch_new_quiz", lambda *a, **k: _NQ_TIMED)
    code, sent, out, err = _run(monkeypatch, capsys, ["--new-quiz-id", "17741295", "--multiplier", "1.5",
                                                      "--extra-attempts", "1", "--apply"])
    assert code == 0
    assert sent["new"] == [(17741295, [{"user_id": 946791, "extra_time": 5, "extra_attempts": 1}])]


def test_classic_only_options_are_refused_for_a_new_quiz(monkeypatch, capsys):
    for flag in (["--manually-unlock"], ["--extend-from-end-at", "10"]):
        code, sent, out, err = _run(monkeypatch, capsys, ["--new-quiz-id", "17741295", *flag, "--apply"])
        assert code == 2 and "classic quizzes only" in err and sent == {"classic": [], "new": []}

"""Unit tests — section_crosslist: course resolution, plan, and write gates.

Cross-listing moves enrollments between courses, so the gates are what is under test:
the course guard runs on the destination AND every source (write mode only with --apply),
a plain run writes nothing, --yes skips only the prompt, and a section already in the
destination is never re-posted.
"""
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import section_crosslist as sc  # noqa: E402


# ── course resolution ──────────────────────────────────────────────────────────

def test_courses_from_env_sorted_numerically_and_ignores_other_vars():
    env = {"S10_COURSE_ID": "10", "S2_COURSE_ID": "2", "S1_COURSE_ID": "1",
           "MASTER_COURSE_ID": "99", "S3_COURSE_ID": ""}
    assert sc.courses_from_env(env) == ["1", "2", "10"]


def test_first_course_is_destination_by_default():
    assert sc.resolve_courses("111,222,333", "") == ("111", ["222", "333"])


def test_into_picks_another_destination():
    assert sc.resolve_courses("111,222,333", "222") == ("222", ["111", "333"])


def test_into_outside_the_list_is_refused():
    with pytest.raises(SystemExit):
        sc.resolve_courses("111,222", "999")


def test_fewer_than_two_courses_is_refused():
    with pytest.raises(SystemExit):
        sc.resolve_courses("111", "")


def test_env_courses_used_when_none_passed(monkeypatch):
    monkeypatch.setenv("S1_COURSE_ID", "5")
    monkeypatch.setenv("S2_COURSE_ID", "6")
    monkeypatch.setenv("S3_COURSE_ID", "7")
    assert sc.resolve_courses("", "") == ("5", ["6", "7"])


# ── plan ───────────────────────────────────────────────────────────────────────

def _fake_get_all(by_endpoint):
    return lambda endpoint, params=None: by_endpoint[endpoint]


def test_plan_skips_sections_already_in_destination(monkeypatch):
    monkeypatch.setattr(sc, "_get_all", _fake_get_all({
        "/courses/1/sections": [{"id": 50}],
        "/courses/2/sections": [{"id": 50, "name": "A", "total_students": 3},
                                {"id": 60, "name": "B", "total_students": 4}],
    }))
    plan = sc.build_plan("1", ["2"])
    assert [(r["section_id"], r["action"]) for r in plan] == [(50, "skip"), (60, "crosslist")]


# ── main(): gates ──────────────────────────────────────────────────────────────

@pytest.fixture
def run(monkeypatch):
    seen = {"guard": [], "applied": 0, "prompted": 0}
    monkeypatch.setattr(sc, "CANVAS_BASE_URL", "https://canvas.example")
    monkeypatch.setattr(sc, "CANVAS_API_TOKEN", "fake")
    monkeypatch.setattr(sc, "build_plan", lambda d, s: [
        {"source": "2", "section_id": 60, "name": "B", "students": 4, "action": "crosslist"}])
    monkeypatch.setattr(sc, "apply_plan", lambda d, p: seen.__setitem__("applied", seen["applied"] + 1) or True)
    monkeypatch.setattr(sc.guard, "enforce", lambda **kw: seen["guard"].append(kw))

    def go(argv, typed=""):
        def fake_input(prompt):
            seen["prompted"] += 1
            return typed
        monkeypatch.setattr("builtins.input", fake_input)
        monkeypatch.setattr(sys, "argv", ["section_crosslist.py", "--courses", "1,2,3", *argv])
        sc.main()
        return seen
    return go


def test_plain_run_is_read_only_and_guards_every_course_in_read_mode(run):
    s = run([])
    assert s["applied"] == 0 and s["prompted"] == 0
    assert [g["course_id"] for g in s["guard"]] == ["1", "2", "3"]
    assert all(g["mode"] == "read" for g in s["guard"])


def test_apply_guards_destination_and_every_source_in_write_mode(run):
    s = run(["--apply", "--yes"])
    assert [g["course_id"] for g in s["guard"]] == ["1", "2", "3"]
    assert all(g["mode"] == "write" and g["allow_override"] is False for g in s["guard"])


def test_apply_without_yes_needs_typed_APPLY(run):
    s = run(["--apply"], typed="nope")
    assert s["prompted"] == 1 and s["applied"] == 0


def test_apply_with_typed_APPLY_writes(run):
    s = run(["--apply"], typed="APPLY")
    assert s["applied"] == 1


def test_yes_skips_only_the_prompt(run):
    s = run(["--apply", "--yes"])
    assert s["prompted"] == 0 and s["applied"] == 1


def test_allow_enrolled_is_passed_through_not_assumed(run):
    s = run(["--apply", "--yes", "--allow-enrolled"])
    assert all(g["allow_override"] is True for g in s["guard"])


def test_guard_refusal_stops_before_any_write(run, monkeypatch):
    def refuse(**kw):
        raise SystemExit(2)
    monkeypatch.setattr(sc.guard, "enforce", refuse)
    monkeypatch.setattr(sc, "apply_plan", lambda d, p: pytest.fail("wrote after the guard refused"))
    with pytest.raises(SystemExit):
        run(["--apply", "--yes"])


def test_nothing_pending_writes_nothing(run, monkeypatch):
    monkeypatch.setattr(sc, "build_plan", lambda d, s: [
        {"source": "2", "section_id": 60, "name": "B", "students": 4, "action": "skip"}])
    s = run(["--apply", "--yes"])
    assert s["applied"] == 0


# ── apply_plan: only pending sections are posted, then verified ────────────────

def test_apply_posts_only_pending_and_verifies(monkeypatch):
    posted = []

    class Resp:
        status_code = 200
        text = ""

    monkeypatch.setattr(sc, "CANVAS_BASE_URL", "https://canvas.example")
    monkeypatch.setattr(sc.requests, "post", lambda url, **kw: posted.append(url) or Resp())
    monkeypatch.setattr(sc, "_get_all", lambda e, p=None: [{"id": 50}, {"id": 60}])
    plan = [{"source": "2", "section_id": 50, "name": "A", "students": 1, "action": "skip"},
            {"source": "2", "section_id": 60, "name": "B", "students": 1, "action": "crosslist"}]
    assert sc.apply_plan("1", plan) is True
    assert posted == ["https://canvas.example/api/v1/sections/60/crosslist/1"]


def test_apply_reports_failure_when_section_did_not_land(monkeypatch):
    class Resp:
        status_code = 200
        text = ""

    monkeypatch.setattr(sc, "CANVAS_BASE_URL", "https://canvas.example")
    monkeypatch.setattr(sc.requests, "post", lambda url, **kw: Resp())
    monkeypatch.setattr(sc, "_get_all", lambda e, p=None: [{"id": 50}])  # 60 never showed up
    plan = [{"source": "2", "section_id": 60, "name": "B", "students": 1, "action": "crosslist"}]
    assert sc.apply_plan("1", plan) is False

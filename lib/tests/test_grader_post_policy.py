"""Unit tests — grader_post_policy (hold graded work hidden, then release).

The dangerous failures here are not "refused to run". They are: a hold that
reports success but leaves the assignment on AUTOMATIC (so the next push is
student-visible), a release that restores the policy after a FAILED post, and a
state file that remembers anything about students. So the failure paths carry
more weight than the happy path.
"""
import json
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import grader_post_policy as gpp  # noqa: E402

BASE, CID, AID, H = "https://canvas.test", "42", 7, {"Authorization": "Bearer x"}


class FakeResp:
    def __init__(self, status=200, body=None, links=None, text=""):
        self.status_code = status
        self._body = body if body is not None else {}
        self.links = links or {}
        self.text = text

    def json(self):
        return self._body


# --- Canvas helpers ---------------------------------------------------------

@pytest.mark.parametrize("field,expected", [(True, True), (False, False), (None, None)])
def test_get_post_manually_reads_field(monkeypatch, field, expected):
    monkeypatch.setattr(gpp.requests, "get",
                        lambda *a, **k: FakeResp(200, {"post_manually": field}))
    assert gpp.get_post_manually(BASE, CID, H, AID) is expected


def test_get_post_manually_unknown_is_never_automatic(monkeypatch):
    monkeypatch.setattr(gpp.requests, "get", lambda *a, **k: FakeResp(500))
    assert gpp.get_post_manually(BASE, CID, H, AID) is None

    def boom(*a, **k):
        raise OSError("down")
    monkeypatch.setattr(gpp.requests, "get", boom)
    assert gpp.get_post_manually(BASE, CID, H, AID) is None


def test_set_post_manually_sends_mutation(monkeypatch):
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, json=json)
        return FakeResp(200, {"data": {"setAssignmentPostPolicy": {"errors": None}}})
    monkeypatch.setattr(gpp.requests, "post", fake_post)
    assert gpp.set_post_manually(BASE, H, AID, True) == (True, "")
    assert sent["url"].endswith("/api/graphql")
    assert "setAssignmentPostPolicy" in sent["json"]["query"]
    assert sent["json"]["variables"] == {"a": "7", "m": True}


@pytest.mark.parametrize("resp", [
    FakeResp(200, {"data": {"setAssignmentPostPolicy": {"errors": [{"message": "nope"}]}}}),
    FakeResp(200, {"errors": [{"message": "not authorized"}]}),
    FakeResp(403, {}, text="forbidden"),
])
def test_set_post_manually_reports_errors(monkeypatch, resp):
    monkeypatch.setattr(gpp.requests, "post", lambda *a, **k: resp)
    ok, detail = gpp.set_post_manually(BASE, H, AID, True)
    assert ok is False and detail


def test_count_hidden_graded_follows_pages_and_counts_only_unposted(monkeypatch):
    pages = [
        FakeResp(200, [{"workflow_state": "graded", "posted_at": None},
                       {"workflow_state": "graded", "posted_at": "2026-10-19T00:00:00Z"},
                       {"workflow_state": "submitted", "posted_at": None}],
                 links={"next": {"url": "https://canvas.test/page2"}}),
        FakeResp(200, [{"workflow_state": "graded", "posted_at": None}]),
    ]
    monkeypatch.setattr(gpp.requests, "get", lambda *a, **k: pages.pop(0))
    assert gpp.count_hidden_graded(BASE, CID, H, AID) == 2


def test_count_hidden_graded_none_on_error(monkeypatch):
    monkeypatch.setattr(gpp.requests, "get", lambda *a, **k: FakeResp(500))
    assert gpp.count_hidden_graded(BASE, CID, H, AID) is None


# --- state ------------------------------------------------------------------

def test_state_holds_ids_and_a_boolean_only(tmp_path):
    p = gpp.state_path(tmp_path, CID, AID)
    gpp.write_state(p, CID, AID, False)
    data = json.loads(p.read_text())
    assert set(data) == {"course_id", "assignment_id", "previous_post_manually", "held_at"}
    assert data["previous_post_manually"] is False


# --- flows (Canvas calls faked at the module seam) --------------------------

class Canvas:
    """Records writes; models the policy so read-back is meaningful."""
    def __init__(self, manual, hidden=3, post_ok=True, sets_stick=True, hidden_after=0):
        self.manual, self.hidden, self.post_ok = manual, hidden, post_ok
        self.sets_stick, self.hidden_after = sets_stick, hidden_after
        self.sets, self.posts = [], 0

    def install(self, monkeypatch):
        monkeypatch.setattr(gpp, "get_post_manually", lambda *a: self.manual)
        monkeypatch.setattr(gpp, "set_post_manually", self._set)
        monkeypatch.setattr(gpp, "post_graded", self._post)
        monkeypatch.setattr(gpp, "count_hidden_graded", lambda *a: self.hidden)
        monkeypatch.setattr(gpp.time, "sleep", lambda s: None)
        monkeypatch.setattr(gpp, "_POLL_TRIES", 2)

    def _set(self, base, headers, aid, manual):
        self.sets.append(manual)
        if self.sets_stick:
            self.manual = manual
        return True, ""

    def _post(self, base, headers, aid):
        self.posts += 1
        if self.post_ok:
            self.hidden = self.hidden_after
            return True, ""
        return False, "HTTP 500"


def run(fn, cv, tmp_path, apply):
    return fn(BASE, CID, H, AID, gpp.state_path(tmp_path, CID, AID), apply)


def test_hold_dry_run_changes_nothing(monkeypatch, tmp_path):
    cv = Canvas(manual=False); cv.install(monkeypatch)
    assert run(gpp.do_hold, cv, tmp_path, False) == 0
    assert cv.sets == [] and not gpp.state_path(tmp_path, CID, AID).exists()


def test_hold_apply_sets_manual_and_records_previous(monkeypatch, tmp_path):
    cv = Canvas(manual=False); cv.install(monkeypatch)
    assert run(gpp.do_hold, cv, tmp_path, True) == 0
    assert cv.sets == [True] and cv.manual is True
    assert gpp.read_state(gpp.state_path(tmp_path, CID, AID))["previous_post_manually"] is False


def test_hold_readback_mismatch_fails_and_records_nothing(monkeypatch, tmp_path):
    cv = Canvas(manual=False, sets_stick=False); cv.install(monkeypatch)
    assert run(gpp.do_hold, cv, tmp_path, True) == 1
    assert not gpp.state_path(tmp_path, CID, AID).exists()


def test_hold_when_already_manual_does_not_write_and_remembers_manual(monkeypatch, tmp_path):
    cv = Canvas(manual=True); cv.install(monkeypatch)
    assert run(gpp.do_hold, cv, tmp_path, True) == 0
    assert cv.sets == []
    assert gpp.read_state(gpp.state_path(tmp_path, CID, AID))["previous_post_manually"] is True


def test_hold_unknown_policy_refuses_to_guess(monkeypatch, tmp_path):
    cv = Canvas(manual=None); cv.install(monkeypatch)
    assert run(gpp.do_hold, cv, tmp_path, True) == 1 and cv.sets == []


def test_release_without_hold_is_refused(monkeypatch, tmp_path):
    cv = Canvas(manual=True); cv.install(monkeypatch)
    assert run(gpp.do_release, cv, tmp_path, True) == 2
    assert cv.posts == 0 and cv.sets == []


def test_release_dry_run_posts_nothing(monkeypatch, tmp_path):
    cv = Canvas(manual=True); cv.install(monkeypatch)
    gpp.write_state(gpp.state_path(tmp_path, CID, AID), CID, AID, False)
    assert run(gpp.do_release, cv, tmp_path, False) == 0
    assert cv.posts == 0 and cv.sets == []


def test_release_posts_then_restores_automatic_and_clears_state(monkeypatch, tmp_path):
    cv = Canvas(manual=True); cv.install(monkeypatch)
    p = gpp.state_path(tmp_path, CID, AID)
    gpp.write_state(p, CID, AID, False)
    assert run(gpp.do_release, cv, tmp_path, True) == 0
    assert cv.posts == 1 and cv.sets == [False] and cv.manual is False
    assert not p.exists()


def test_release_failed_post_does_not_restore_and_keeps_state(monkeypatch, tmp_path):
    cv = Canvas(manual=True, post_ok=False); cv.install(monkeypatch)
    p = gpp.state_path(tmp_path, CID, AID)
    gpp.write_state(p, CID, AID, False)
    assert run(gpp.do_release, cv, tmp_path, True) == 1
    assert cv.sets == [] and cv.manual is True and p.exists()


def test_release_still_hidden_after_wait_does_not_restore(monkeypatch, tmp_path):
    cv = Canvas(manual=True, hidden_after=2); cv.install(monkeypatch)
    p = gpp.state_path(tmp_path, CID, AID)
    gpp.write_state(p, CID, AID, False)
    assert run(gpp.do_release, cv, tmp_path, True) == 1
    assert cv.sets == [] and p.exists()


def test_release_leaves_manual_if_it_was_manual_before(monkeypatch, tmp_path):
    cv = Canvas(manual=True); cv.install(monkeypatch)
    p = gpp.state_path(tmp_path, CID, AID)
    gpp.write_state(p, CID, AID, True)
    assert run(gpp.do_release, cv, tmp_path, True) == 0
    assert cv.posts == 1 and cv.sets == [] and cv.manual is True and not p.exists()


def test_restore_without_hold_is_refused(monkeypatch, tmp_path):
    cv = Canvas(manual=True); cv.install(monkeypatch)
    assert run(gpp.do_restore, cv, tmp_path, True) == 2 and cv.sets == []


def test_restore_puts_policy_back_without_posting(monkeypatch, tmp_path):
    cv = Canvas(manual=True); cv.install(monkeypatch)
    p = gpp.state_path(tmp_path, CID, AID)
    gpp.write_state(p, CID, AID, False)
    assert run(gpp.do_restore, cv, tmp_path, True) == 0
    assert cv.posts == 0 and cv.sets == [False] and not p.exists()


# --- CLI / guard ------------------------------------------------------------

def _cli(monkeypatch, tmp_path, argv, enforce_calls):
    monkeypatch.setattr(gpp, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(gpp, "CANVAS_BASE_URL", BASE)
    monkeypatch.setenv("CANVAS_COURSE_ID", CID)
    monkeypatch.setattr(gpp.guard, "enforce", lambda **k: enforce_calls.append(k))
    cv = Canvas(manual=False); cv.install(monkeypatch)
    rc = gpp.main(["--assignment-id", str(AID), "--state-dir", str(tmp_path), *argv])
    return rc, cv


def test_guard_runs_in_write_mode_only_when_applying_a_write(monkeypatch, tmp_path):
    calls = []
    _cli(monkeypatch, tmp_path, ["--hold", "--apply"], calls)
    assert calls[-1]["mode"] == "write"
    _cli(monkeypatch, tmp_path, ["--hold"], calls)          # dry run
    assert calls[-1]["mode"] == "read"
    _cli(monkeypatch, tmp_path, ["--status", "--apply"], calls)  # status never writes
    assert calls[-1]["mode"] == "read"


def test_allow_enrolled_is_passed_to_the_guard(monkeypatch, tmp_path):
    calls = []
    _cli(monkeypatch, tmp_path, ["--hold", "--apply", "--allow-enrolled"], calls)
    assert calls[-1]["allow_override"] is True


def test_modes_are_mutually_exclusive(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        _cli(monkeypatch, tmp_path, ["--hold", "--release"], [])


def test_missing_credentials_refuse_before_any_call(monkeypatch, tmp_path):
    monkeypatch.setattr(gpp, "CANVAS_API_TOKEN", "")
    assert gpp.main(["--assignment-id", "7", "--course-id", "42"]) == 2


def test_status_is_read_only_and_warns_on_automatic(monkeypatch, tmp_path, capsys):
    calls = []
    rc, cv = _cli(monkeypatch, tmp_path, ["--status"], calls)
    out = capsys.readouterr().out
    assert rc == 0 and cv.sets == [] and cv.posts == 0
    assert "AUTOMATIC" in out and "student-visible" in out

"""Unit tests — peer review pairing (#331).

Two things must never go wrong: a student's name reaching the output (Canvas returns
names on every member endpoint, so the tool has to drop them itself), and a re-run
duplicating or resurrecting pairings on a live course.
"""
import sys
from pathlib import Path


_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import peer_review_assign as pra  # noqa: E402
from peer_review_assign import existing_pairs, plan_pairs  # noqa: E402


def _subs(*users, state="submitted"):
    return {u: {"id": 1000 + u, "workflow_state": state} for u in users}


# --- plan_pairs -------------------------------------------------------------

def test_every_member_reviews_each_groupmate_but_not_self():
    p = plan_pairs({1: [10, 11, 12]}, {10, 11, 12}, _subs(10, 11, 12), set())
    pairs = {(r, e) for r, e, _ in p["create"]}
    assert pairs == {(10, 11), (10, 12), (11, 10), (11, 12), (12, 10), (12, 11)}
    assert p["counts"]["to_create"] == 6


def test_pairing_never_crosses_groups():
    p = plan_pairs({1: [10, 11], 2: [20, 21]}, {10, 11, 20, 21}, _subs(10, 11, 20, 21), set())
    assert all((r < 15) == (e < 15) for r, e, _ in p["create"])


def test_submission_id_is_the_reviewees():
    p = plan_pairs({1: [10, 11]}, {10, 11}, _subs(10, 11), set())
    assert {(r, e, s) for r, e, s in p["create"]} == {(10, 11, 1011), (11, 10, 1010)}


def test_existing_pairs_are_skipped_so_rerun_is_safe():
    first = plan_pairs({1: [10, 11, 12]}, {10, 11, 12}, _subs(10, 11, 12), set())
    have = {(r, e) for r, e, _ in first["create"]}
    again = plan_pairs({1: [10, 11, 12]}, {10, 11, 12}, _subs(10, 11, 12), have)
    assert again["create"] == [] and again["counts"]["already_paired"] == 6


def test_a_new_group_member_only_adds_that_members_pairs():
    have = {(r, e) for r, e, _ in
            plan_pairs({1: [10, 11]}, {10, 11}, _subs(10, 11), set())["create"]}
    p = plan_pairs({1: [10, 11, 12]}, {10, 11, 12}, _subs(10, 11, 12), have)
    assert {(r, e) for r, e, _ in p["create"]} == {(10, 12), (11, 12), (12, 10), (12, 11)}


def test_members_who_are_not_active_students_are_left_out():
    p = plan_pairs({1: [10, 11, 99]}, {10, 11}, _subs(10, 11, 99), set())
    assert all(99 not in (r, e) for r, e, _ in p["create"])
    assert p["counts"]["members_left_out"] == 1


def test_group_with_fewer_than_two_eligible_members_is_skipped():
    p = plan_pairs({1: [10], 2: [20, 99]}, {10, 20}, _subs(10, 20), set())
    assert p["create"] == [] and p["counts"]["groups_too_small"] == 2


def test_unsubmitted_reviewees_wait_by_default():
    subs = {10: {"id": 1, "workflow_state": "submitted"},
            11: {"id": 2, "workflow_state": "unsubmitted"}}
    p = plan_pairs({1: [10, 11]}, {10, 11}, subs, set())
    assert {(r, e) for r, e, _ in p["create"]} == {(11, 10)}
    assert p["counts"]["reviewees_not_submitted_yet"] == 1
    p2 = plan_pairs({1: [10, 11]}, {10, 11}, subs, set(), include_unsubmitted=True)
    assert len(p2["create"]) == 2


def test_reviewee_with_no_submission_record_is_counted_not_guessed():
    p = plan_pairs({1: [10, 11]}, {10, 11}, _subs(10), set())
    assert p["counts"]["reviewees_without_submission_record"] == 1


def test_pairs_from_students_who_left_a_group_are_reported_never_removed():
    p = plan_pairs({1: [10, 11]}, {10, 11}, _subs(10, 11), {(10, 50), (50, 10)})
    assert p["counts"]["existing_outside_groups"] == 2


def test_existing_pairs_reads_assessor_as_reviewer_and_user_as_reviewee():
    assert existing_pairs([{"assessor_id": 1, "user_id": 2, "asset_id": 9}]) == {(1, 2)}
    assert existing_pairs([{"assessor_id": None, "user_id": 2}]) == set()


# --- main(): mocked Canvas --------------------------------------------------

_NAMES = ["Zebulon Quillfeather", "Marigold Thistlewood", "Cornelius Abernathy"]
_IDS = [7781001, 7781002, 7781003]


class _Canvas:
    def __init__(self, assignment=None, post_ok=True, readback=True):
        self.posts, self.post_ok, self.readback = [], post_ok, readback
        self.assignment = assignment or {"id": 5, "name": "Prep ratings", "peer_reviews": True,
                                         "group_category_id": None}

    def get_all(self, endpoint, params=None):
        if endpoint.endswith("/assignments") and params:
            return [self.assignment]
        if endpoint.endswith("/assignments/5"):
            return self.assignment
        if endpoint == "/group_categories/3":
            return {"id": 3, "name": "Study groups", "self_signup": "enabled"}
        if endpoint == "/group_categories/3/groups":
            return [{"id": 30, "name": "Group A"}]
        if endpoint == "/groups/30/users":     # Canvas returns NAMES here
            return [{"id": i, "name": n, "sortable_name": n[::-1], "short_name": n}
                    for i, n in zip(_IDS, _NAMES)]
        if endpoint.endswith("/enrollments"):
            return [{"user_id": i, "user": {"name": n}} for i, n in zip(_IDS, _NAMES)]
        if endpoint.endswith("/submissions"):
            return [{"id": 100 + i % 10, "user_id": i, "workflow_state": "submitted"} for i in _IDS]
        if endpoint.endswith("/peer_reviews"):
            if self.readback and self.posts:
                return [{"assessor_id": int(f["user_id"]), "user_id": e}
                        for (_, f, e) in self.posts]
            return []
        raise AssertionError(endpoint)

    def post(self, endpoint, form):
        sid = int(endpoint.split("/submissions/")[1].split("/")[0])
        reviewee = next(i for i in _IDS if 100 + i % 10 == sid)
        self.posts.append((endpoint, form, reviewee))
        return (self.post_ok, "" if self.post_ok else "HTTP 400")


def _run(monkeypatch, capsys, argv, canvas=None):
    canvas = canvas or _Canvas()
    monkeypatch.setattr(pra, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(pra, "CANVAS_BASE_URL", "https://x")
    monkeypatch.setattr(pra.guard, "enforce", lambda **k: None)
    monkeypatch.setattr(pra, "_get_all", canvas.get_all)
    monkeypatch.setattr(pra, "_post", canvas.post)
    monkeypatch.setattr(sys, "argv", ["peer_review_assign.py", "--course-id", "1",
                                      "--assignment-id", "5", "--group-set-id", "3", *argv])
    rc = pra.main()
    return rc, canvas, capsys.readouterr()


def test_dry_run_writes_nothing(monkeypatch, capsys):
    rc, canvas, out = _run(monkeypatch, capsys, [])
    assert rc == 0 and canvas.posts == []
    assert "DRY RUN" in out.out and "6  pairs to create" in out.out


def test_apply_creates_each_pair_once_then_rerun_creates_none(monkeypatch, capsys):
    rc, canvas, _ = _run(monkeypatch, capsys, ["--apply"])
    assert rc == 0 and len(canvas.posts) == 6
    assert {f["user_id"] for _, f, _ in canvas.posts} == {str(i) for i in _IDS}


def test_output_has_no_student_names_or_ids(monkeypatch, capsys):
    """Canvas returns names on the member and enrollment endpoints. FERPA: counts only."""
    _, _, out = _run(monkeypatch, capsys, ["--apply"])
    text = out.out + out.err
    for n in _NAMES:
        assert n not in text and n.split()[0] not in text and n.split()[1] not in text
    for i in _IDS:
        assert str(i) not in text


def test_failures_are_counted_by_reason_not_by_student(monkeypatch, capsys):
    rc, _, out = _run(monkeypatch, capsys, ["--apply"], _Canvas(post_ok=False))
    assert rc == 1 and "6 × HTTP 400" in out.out
    assert not any(str(i) in out.out for i in _IDS)


def test_pairs_that_do_not_read_back_fail_the_run(monkeypatch, capsys):
    rc, _, out = _run(monkeypatch, capsys, ["--apply"], _Canvas(readback=False))
    assert rc == 1 and "did not read back" in out.out


def test_group_assignments_are_refused(monkeypatch, capsys):
    a = {"id": 5, "name": "Team task", "peer_reviews": True, "group_category_id": 44}
    rc, canvas, out = _run(monkeypatch, capsys, ["--apply"], _Canvas(assignment=a))
    assert rc == 2 and canvas.posts == [] and "GROUP assignment" in out.out


def test_assignment_without_peer_reviews_is_refused(monkeypatch, capsys):
    a = {"id": 5, "name": "Plain", "peer_reviews": False, "group_category_id": None}
    rc, canvas, out = _run(monkeypatch, capsys, ["--apply"], _Canvas(assignment=a))
    assert rc == 2 and canvas.posts == []


def test_unreadable_canvas_data_changes_nothing(monkeypatch, capsys):
    c = _Canvas()
    real = c.get_all
    c.get_all = lambda ep, params=None: None if ep.endswith("/enrollments") else real(ep, params)
    rc, canvas, out = _run(monkeypatch, capsys, ["--apply"], c)
    assert rc == 1 and canvas.posts == [] and "Nothing was changed" in out.out

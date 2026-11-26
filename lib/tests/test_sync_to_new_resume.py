"""Tests — sync_to_new survives a dropped connection without duplicating (#445).

sync_to_new builds a whole course in an empty target. Before this, a run that
stopped partway, then ran again, made everything a second time. Now each create
first claims a same-titled object already in the target (a re-run continues),
and a create that may have reached Canvas is settled by reading the target
again: there means done, absent means send once more, unclear means unsure.

The fake Canvas below keeps state: a create appears in the next list read.
"""
import sys
from pathlib import Path

import pytest
import requests

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import sync_to_new as stn  # noqa: E402

BASE = "https://x/api/v1/courses/9"


class _Resp:
    def __init__(self, status, body=None):
        self.status_code, self._b, self.headers, self.links = status, body, {}, {}
        self.text = "x" if body is not None else ""

    def json(self):
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeCanvas:
    """lists[url] is what GET returns; posts are recorded; `drop` makes the next
    POST to a URL land on Canvas but lose its reply."""

    def __init__(self, lists=None):
        self.lists = {k: list(v) for k, v in (lists or {}).items()}
        self.posts, self.puts, self.drop, self.next_id = [], [], {}, 100

    def get(self, url, **kw):
        return _Resp(200, list(self.lists.get(url, [])))

    def post(self, url, **kw):
        self.posts.append(url)
        body = kw.get("json") or kw.get("data") or {}
        inner = next(iter(body.values())) if body and isinstance(next(iter(body.values())), dict) else body
        title = inner.get("title") or inner.get("name")
        mode = self.drop.pop(url, None)
        if mode == "lost":           # Canvas never got it
            raise requests.exceptions.ReadTimeout("read timed out")
        self.next_id += 1
        obj = {"id": self.next_id, ("name" if "name" in inner else "title"): title}
        self.lists.setdefault(url, []).append(obj)
        if mode == "landed":         # Canvas made it, the reply was lost
            raise requests.exceptions.ReadTimeout("read timed out")
        return _Resp(201, obj)

    def put(self, url, **kw):
        self.puts.append(url)
        return _Resp(200, {})


@pytest.fixture
def canvas(monkeypatch):
    def make(lists=None):
        fake = FakeCanvas(lists)
        for m in ("get", "post", "put"):
            monkeypatch.setattr(stn.requests, m, getattr(fake, m))
        monkeypatch.setattr(stn, "_TARGET", stn._Target("tok", reuse=True))
        monkeypatch.setattr(stn, "RESULTS", {"created": [], "reused": [], "updated": [], "not_done": [], "unsure": []})
        monkeypatch.setattr(stn.time, "sleep", lambda s: None)
        monkeypatch.setattr(stn._cr.time, "sleep", lambda s: None)
        return fake
    return make


def test_a_rerun_reuses_what_the_first_run_made(canvas):
    fake = canvas({f"{BASE}/modules": [{"id": 1, "name": "Week 1"}]})
    out = stn.create_module("https://x", "9", {"name": "Week 1"}, "tok")
    assert out["id"] == 1 and fake.posts == []
    assert stn.RESULTS["reused"] == ["Week 1"]


def test_two_local_items_with_one_title_match_one_existing_each(canvas):
    fake = canvas({f"{BASE}/pages": [{"id": 1, "title": "Overview"}]})
    a = stn.create_page("https://x", "9", {"title": "Overview"}, "<p>a</p>", "tok")
    b = stn.create_page("https://x", "9", {"title": "Overview"}, "<p>b</p>", "tok")
    assert a["id"] == 1 and b["id"] != 1 and len(fake.posts) == 1


def test_a_create_that_landed_but_lost_its_reply_isnt_made_twice(canvas):
    """The issue's test, on the tool: Canvas made it, then the reply was lost."""
    fake = canvas()
    fake.drop[f"{BASE}/modules"] = "landed"
    out = stn.create_module("https://x", "9", {"name": "Week 2"}, "tok")
    assert out and len(fake.posts) == 1
    assert len([m for m in fake.lists[f"{BASE}/modules"] if m["name"] == "Week 2"]) == 1
    assert stn.RESULTS["created"] == ["Week 2"]


def test_a_create_that_never_landed_is_sent_once_more(canvas):
    fake = canvas()
    fake.drop[f"{BASE}/assignments"] = "lost"
    out = stn.create_assignment("https://x", "9", {"name": "Essay 1"}, "<p/>", "tok")
    assert out and len(fake.posts) == 2
    assert len(fake.lists[f"{BASE}/assignments"]) == 1


def test_it_reports_unsure_when_it_cant_tell(canvas, monkeypatch):
    fake = canvas()
    fake.drop[f"{BASE}/modules"] = "lost"

    def cant_read(self, url):
        raise requests.exceptions.ConnectionError("down")
    stn._TARGET._lists[f"{BASE}/modules"] = []           # first claim needs no read
    monkeypatch.setattr(stn._Target, "_fetch", cant_read)
    assert stn.create_module("https://x", "9", {"name": "Week 3"}, "tok") is None
    assert stn.RESULTS["unsure"] == ["Week 3"] and len(fake.posts) == 1


def test_the_default_assignments_group_is_reused_with_the_local_settings(canvas):
    fake = canvas({f"{BASE}/assignment_groups": [{"id": 5, "name": "Assignments"}]})
    out = stn.create_assignment_group("https://x", "9", {"name": "Assignments", "group_weight": 40}, "tok")
    assert out["id"] == 5 and fake.posts == [] and fake.puts == [f"{BASE}/assignment_groups/5"]


def test_without_apply_nothing_is_read_first(canvas, monkeypatch):
    fake = canvas()
    monkeypatch.setattr(stn, "_TARGET", None)
    stn.create_module("https://x", "9", {"name": "Week 4"}, "tok")
    assert len(fake.posts) == 1


def test_a_failed_settings_update_on_a_reused_group_is_reported(canvas, monkeypatch):
    fake = canvas({f"{BASE}/assignment_groups": [{"id": 5, "name": "Assignments"}]})
    monkeypatch.setattr(fake, "put", lambda url, **kw: (_ for _ in ()).throw(requests.exceptions.ConnectionError("down")))
    monkeypatch.setattr(stn.requests, "put", fake.put)
    out = stn.create_assignment_group("https://x", "9", {"name": "Assignments", "group_weight": 40}, "tok")
    assert out["id"] == 5  # still reused, not created again
    assert stn.RESULTS["not_done"] == ["Assignments (settings)"]


def test_two_new_items_with_one_title_settle_to_the_right_one(canvas):
    """mark(): after the first "Overview" is made, an unsure second one must not
    be mistaken for it."""
    fake = canvas()
    first = stn.create_page("https://x", "9", {"title": "Overview"}, "<p>a</p>", "tok")
    fake.drop[f"{BASE}/pages"] = "landed"
    second = stn.create_page("https://x", "9", {"title": "Overview"}, "<p>b</p>", "tok")
    assert second["id"] != first["id"] and len(fake.posts) == 2


def test_without_resume_only_the_unsure_path_reads_by_title(canvas, monkeypatch):
    fake = canvas({f"{BASE}/modules": [{"id": 1, "name": "Week 1"}]})
    monkeypatch.setattr(stn, "_TARGET", stn._Target("tok", reuse=False))
    stn.create_module("https://x", "9", {"name": "Week 1"}, "tok")
    assert len(fake.posts) == 1  # created, not reused: --resume wasn't given


def test_a_plain_assignment_never_claims_a_quiz_assignment(canvas):
    fake = canvas({f"{BASE}/assignments": [{"id": 7, "name": "Quiz 1", "is_quiz_assignment": True}]})
    out = stn.create_assignment("https://x", "9", {"name": "Quiz 1"}, "<p/>", "tok")
    assert out["id"] != 7 and len(fake.posts) == 1


def test_apply_without_resume_stops_on_a_course_that_isnt_empty(monkeypatch, capsys, tmp_path):
    fake = FakeCanvas({"https://x/api/v1/courses/9/modules": [{"id": 1, "name": "Week 1"}]})
    for m in ("get", "post", "put"):
        monkeypatch.setattr(stn.requests, m, getattr(fake, m))
    monkeypatch.setattr(stn, "_load_config", lambda: ("https://x", "9", "tok"))
    monkeypatch.setattr(stn, "_course_guard", lambda *a, **k: None)
    monkeypatch.setattr(stn, "load_course_content", lambda *a, **k: {
        "modules": [{"title": "Week 1", "slug": "w1"}], "files": {}, "source_course_id": "1"})
    monkeypatch.setattr(sys, "argv", ["sync_to_new.py", "--apply"])
    monkeypatch.chdir(tmp_path)
    assert stn.main() == 1
    err = capsys.readouterr().err
    assert "already has 1 module(s)" in err and "--resume" in err and fake.posts == []

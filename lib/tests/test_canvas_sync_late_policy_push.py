"""cmd_push must not PATCH a late policy that doesn't exist yet.

Canvas only accepts PATCH /courses/:id/late_policy once a late-policy record
exists; a course that never configured one returns 404 ("The specified resource
does not exist."). #189 narrowed the _course.json hash to late_policy, which made
an untouched course register as "changed" on the next --push — so every operator
who pulled #189 and pushed against a policy-free course hit that 404 on every
push, with the hash never updating (#205).

_push_late_policy GETs first: PATCH to update when a policy exists (200), POST to
create when it doesn't (non-200).
"""
import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("canvas_sync", TOOLS / "canvas_sync.py")
canvas_sync = importlib.util.module_from_spec(spec)
sys.modules["canvas_sync"] = canvas_sync
spec.loader.exec_module(canvas_sync)


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class _FakeRequests:
    """Records which verb the push used and with what payload."""

    def __init__(self, get_status):
        self._get_status = get_status
        self.calls = []  # list of (verb, url, json)

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("get", url, None))
        return _Resp(self._get_status)

    def patch(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("patch", url, json))
        return _Resp(200)

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("post", url, json))
        return _Resp(200)


def _install(monkeypatch, get_status):
    fake = _FakeRequests(get_status)
    monkeypatch.setattr(canvas_sync, "requests", fake)
    return fake


def test_patches_when_a_policy_already_exists(monkeypatch):
    fake = _install(monkeypatch, get_status=200)
    lp = {"late_submission_deduction": 10.0}

    resp, created = canvas_sync._push_late_policy(lp)

    verbs = [c[0] for c in fake.calls]
    assert verbs == ["get", "patch"]           # GET probes, then PATCH updates
    assert created is False
    assert resp.status_code == 200
    assert fake.calls[1][2] == {"late_policy": lp}


def test_posts_to_create_when_none_exists(monkeypatch):
    """The #205 bug: a 404-on-GET course must POST-create, never PATCH-404."""
    fake = _install(monkeypatch, get_status=404)
    lp = {"late_submission_deduction": 10.0}

    resp, created = canvas_sync._push_late_policy(lp)

    verbs = [c[0] for c in fake.calls]
    assert verbs == ["get", "post"]            # GET 404s, so POST creates
    assert "patch" not in verbs                # the old unconditional PATCH is gone
    assert created is True
    assert resp.status_code == 200
    assert fake.calls[1][2] == {"late_policy": lp}

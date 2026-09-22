"""Unit tests — cb_report_bug.py comment mode (#275).

The safety property lives server-side (the worker only accepts an issue number it
filed itself — see edge-infra/workers/bug-intake-worker). What the client must get
right: never send a title alongside an issue number, route to the right endpoint,
and surface the worker's refusal reasons (403 unknown issue, 503 no registry)
clearly instead of a generic "rejected".
"""
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import cb_report_bug as crb  # noqa: E402
from cb_report_bug import _bug_payload, _comment_payload  # noqa: E402


# --- payload shape -----------------------------------------------------------

def test_bug_payload_has_a_title_comment_payload_does_not():
    bug = _bug_payload("t", "b")
    comment = _comment_payload(5, "b")
    assert "title" in bug and "issue" not in bug
    assert "issue" in comment and "title" not in comment
    assert comment["issue"] == 5


def test_both_payloads_carry_version_and_user_agent():
    for p in (_bug_payload("t", "b"), _comment_payload(5, "b")):
        assert p["toolkit_version"] == crb.__version__
        assert p["user_agent"] == crb._USER_AGENT


# --- main(): argument handling ------------------------------------------------

def _run(monkeypatch, capsys, argv):
    monkeypatch.setattr(sys, "argv", ["cb_report_bug.py", *argv])
    rc = crb.main()
    return rc, capsys.readouterr()


def test_issue_and_title_together_is_refused_before_any_network_call(monkeypatch, capsys):
    monkeypatch.setattr(crb, "_post_to_worker", lambda *a, **k: pytest.fail("must not POST"))
    rc, out = _run(monkeypatch, capsys, ["--issue", "5", "--title", "t", "--body", "b"])
    assert rc == 1 and "mutually exclusive" in out.err


def test_non_positive_issue_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(crb, "_post_to_worker", lambda *a, **k: pytest.fail("must not POST"))
    for n in ("0", "-3"):
        rc, out = _run(monkeypatch, capsys, ["--issue", n, "--body", "b"])
        assert rc == 1 and "positive issue number" in out.err


def test_comment_mode_never_prompts_for_a_title(monkeypatch, capsys):
    """No --title, no stdin available for input() — must not hang or prompt."""
    monkeypatch.setattr(crb, "_post_to_worker", lambda *a, **k: (200, {"url": "https://x/c", "id": 1}))
    rc, _ = _run(monkeypatch, capsys, ["--issue", "5", "--body", "more detail"])
    assert rc == 0


def test_dry_run_comment_shows_issue_number_not_title(monkeypatch, capsys):
    rc, out = _run(monkeypatch, capsys, ["--dry-run", "--issue", "5", "--body", "b"])
    assert rc == 0 and "issue: #5" in out.out and "title:" not in out.out


def test_dry_run_bug_mode_unchanged(monkeypatch, capsys):
    rc, out = _run(monkeypatch, capsys, ["--dry-run", "--title", "t", "--body", "b"])
    assert rc == 0 and "title: t" in out.out


def test_comment_mode_posts_to_the_comment_endpoint_by_default(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(crb, "_post_to_worker",
                        lambda endpoint, payload: (seen.setdefault("endpoint", endpoint),
                                                   (200, {"url": "https://x/c", "id": 1}))[1])
    _run(monkeypatch, capsys, ["--issue", "5", "--body", "b"])
    assert seen["endpoint"] == crb._COMMENT_ENDPOINT


def test_bug_mode_still_posts_to_the_bug_endpoint(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(crb, "_post_to_worker",
                        lambda endpoint, payload: (seen.setdefault("endpoint", endpoint),
                                                   (200, {"url": "https://x/i", "number": 9}))[1])
    _run(monkeypatch, capsys, ["--title", "t", "--body", "b"])
    assert seen["endpoint"] == crb._ENDPOINT


def test_endpoint_override_applies_to_whichever_mode_is_selected(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(crb, "_post_to_worker",
                        lambda endpoint, payload: (seen.setdefault("endpoint", endpoint),
                                                   (200, {"url": "https://x/c", "id": 1}))[1])
    _run(monkeypatch, capsys, ["--issue", "5", "--body", "b", "--endpoint", "https://dev/comment"])
    assert seen["endpoint"] == "https://dev/comment"


def test_403_on_an_unfiled_issue_gets_a_clear_explanation(monkeypatch, capsys):
    monkeypatch.setattr(crb, "_post_to_worker",
                        lambda *a, **k: (403, {"error": "issue_not_filed_by_worker"}))
    rc, out = _run(monkeypatch, capsys, ["--issue", "999999", "--body", "b"])
    assert rc == 2 and "was not filed through this tool" in out.err


def test_503_when_worker_has_no_registry(monkeypatch, capsys):
    monkeypatch.setattr(crb, "_post_to_worker",
                        lambda *a, **k: (503, {"error": "comment_registry_unavailable"}))
    rc, out = _run(monkeypatch, capsys, ["--issue", "5", "--body", "b"])
    assert rc == 2 and "not ready to accept comments" in out.err


def test_successful_comment_prints_the_comment_url_not_an_issue_number(monkeypatch, capsys):
    monkeypatch.setattr(crb, "_post_to_worker",
                        lambda *a, **k: (200, {"url": "https://x/issues/5#issuecomment-1", "id": 1}))
    rc, out = _run(monkeypatch, capsys, ["--issue", "5", "--body", "b"])
    assert rc == 0 and "comment posted:" in out.out and "issuecomment" in out.out

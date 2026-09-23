"""Unit tests — Canvas quiz/assignment shell creation (#349).

The dangerous failures here are quiet ones: a payload Canvas's JSON parser silently
ignores every field of (form-encoded bracket keys sent as JSON — a real bug caught
before this ever hit a sandbox), a shell created published, and a re-run that
duplicates or edits an existing object.
"""
import json
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import canvas_shell_create as sc  # noqa: E402
from canvas_shell_create import (  # noqa: E402
    build_assignment_payload,
    build_module_item_payload,
    build_quiz_payload,
    find_existing,
    load_draft,
    validate_draft,
)

_QUIZ_DRAFT = {"kind": "quiz", "title": "Prep check", "points_possible": 5,
              "quiz_type": "assignment", "due_at": "2026-10-01T05:59:00Z"}
_ASSIGN_DRAFT = {"kind": "assignment", "title": "Reflection 1", "points_possible": 10}


# --- load_draft --------------------------------------------------------------

def test_load_draft_reads_json(tmp_path):
    p = tmp_path / "d.json"
    p.write_text(json.dumps(_QUIZ_DRAFT), encoding="utf-8")
    assert load_draft(str(p)) == _QUIZ_DRAFT


def test_load_draft_missing_file_raises_clean_error(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        load_draft(str(tmp_path / "nope.json"))


def test_load_draft_bad_json_raises_clean_error(tmp_path):
    p = tmp_path / "d.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_draft(str(p))


def test_load_draft_rejects_a_non_object_json_body(tmp_path):
    p = tmp_path / "d.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_draft(str(p))


# --- validate_draft ------------------------------------------------------------

def test_valid_quiz_and_assignment_drafts_pass():
    assert validate_draft(_QUIZ_DRAFT) == []
    assert validate_draft(_ASSIGN_DRAFT) == []


@pytest.mark.parametrize("bad", [
    {},
    {"kind": "page", "title": "x"},
    {"kind": "quiz"},
    {"kind": "quiz", "title": "  "},
    {"kind": "quiz", "title": "x", "points_possible": -1},
    {"kind": "quiz", "title": "x", "points_possible": "ten"},
    {"kind": "quiz", "title": "x", "grading_type": "vibes"},
    {"kind": "quiz", "title": "x", "quiz_type": "essay"},
    {"kind": "assignment", "title": "x", "submission_types": []},
    {"kind": "assignment", "title": "x", "submission_types": "online_text_entry"},
    {"kind": "quiz", "title": "x", "due_at": 12345},
])
def test_invalid_drafts_are_refused(bad):
    assert validate_draft(bad) != []


# --- payload building — the transport-format bug -----------------------------

def test_assignment_payload_is_nested_json_not_form_bracket_keys():
    """The real bug: canvas_sync.py's own _post()/_put() send json=payload (nested
    dicts). Bracket-style keys like "assignment[name]" are the FORM-ENCODED wire
    format and Canvas's JSON parser does not understand them — every field would be
    silently dropped."""
    payload = build_assignment_payload(_ASSIGN_DRAFT)
    assert list(payload.keys()) == ["assignment"]
    assert payload["assignment"]["name"] == "Reflection 1"
    assert not any("[" in k for k in payload["assignment"])


def test_quiz_payload_is_nested_json():
    payload = build_quiz_payload(_QUIZ_DRAFT)
    assert list(payload.keys()) == ["quiz"]
    assert payload["quiz"]["title"] == "Prep check"
    assert not any("[" in k for k in payload["quiz"])


def test_assignment_created_unpublished_always():
    assert build_assignment_payload(_ASSIGN_DRAFT)["assignment"]["published"] is False


def test_quiz_created_unpublished_always():
    assert build_quiz_payload(_QUIZ_DRAFT)["quiz"]["published"] is False


def test_assignment_defaults_submission_type_when_omitted():
    payload = build_assignment_payload({"kind": "assignment", "title": "x"})
    assert payload["assignment"]["submission_types"] == ["online_text_entry"]


def test_quiz_defaults_quiz_type_when_omitted():
    payload = build_quiz_payload({"kind": "quiz", "title": "x"})
    assert payload["quiz"]["quiz_type"] == "assignment"


def test_optional_fields_omitted_when_not_in_draft():
    payload = build_assignment_payload({"kind": "assignment", "title": "x"})
    assert "points_possible" not in payload["assignment"]
    assert "due_at" not in payload["assignment"]
    assert "assignment_group_id" not in payload["assignment"]


def test_dates_carried_through_on_both_kinds():
    draft = {**_ASSIGN_DRAFT, "due_at": "2026-10-01T05:59:00Z", "lock_at": "2026-10-02T05:59:00Z"}
    payload = build_assignment_payload(draft)["assignment"]
    assert payload["due_at"] == "2026-10-01T05:59:00Z"
    assert payload["lock_at"] == "2026-10-02T05:59:00Z"
    assert "unlock_at" not in payload


def test_module_item_payload_is_nested_and_typed_correctly():
    assert build_module_item_payload("quiz", 42, "Prep check") == {
        "module_item": {"title": "Prep check", "type": "Quiz", "content_id": 42}
    }
    assert build_module_item_payload("assignment", 7, "Reflection 1") == {
        "module_item": {"title": "Reflection 1", "type": "Assignment", "content_id": 7}
    }


# --- find_existing -------------------------------------------------------------

def test_find_existing_matches_exact_title(monkeypatch):
    monkeypatch.setattr(sc, "_get", lambda ep: [
        {"id": 1, "title": "Prep check extra"}, {"id": 2, "title": " Prep check "}])
    assert find_existing("1", "quiz", "Prep check")["id"] == 2


def test_find_existing_uses_name_field_for_assignments(monkeypatch):
    monkeypatch.setattr(sc, "_get", lambda ep: [{"id": 5, "name": "Reflection 1"}])
    assert find_existing("1", "assignment", "Reflection 1")["id"] == 5


def test_find_existing_none_when_no_match(monkeypatch):
    monkeypatch.setattr(sc, "_get", lambda ep: [{"id": 1, "title": "Other"}])
    assert find_existing("1", "quiz", "Prep check") is None


# --- create_shell — read-back verification ------------------------------------

def test_create_shell_verifies_title_and_unpublished(monkeypatch):
    monkeypatch.setattr(sc, "_post", lambda ep, form: ({"id": 9}, ""))
    monkeypatch.setattr(sc, "_get", lambda ep: {"id": 9, "title": "Prep check", "published": False})
    back, err = sc.create_shell("1", _QUIZ_DRAFT)
    assert back and back["id"] == 9 and err == ""


def test_create_shell_fails_if_title_did_not_read_back(monkeypatch):
    monkeypatch.setattr(sc, "_post", lambda ep, form: ({"id": 9}, ""))
    monkeypatch.setattr(sc, "_get", lambda ep: {"id": 9, "title": "Wrong Title", "published": False})
    back, err = sc.create_shell("1", _QUIZ_DRAFT)
    assert back is None and "did not read back" in err


def test_create_shell_fails_if_published(monkeypatch):
    monkeypatch.setattr(sc, "_post", lambda ep, form: ({"id": 9}, ""))
    monkeypatch.setattr(sc, "_get", lambda ep: {"id": 9, "title": "Prep check", "published": True})
    back, err = sc.create_shell("1", _QUIZ_DRAFT)
    assert back is None and "published" in err


def test_create_shell_propagates_post_error(monkeypatch):
    monkeypatch.setattr(sc, "_post", lambda ep, form: (None, "HTTP 422"))
    back, err = sc.create_shell("1", _QUIZ_DRAFT)
    assert back is None and err == "HTTP 422"


# --- main(): mocked Canvas -----------------------------------------------------

def _run(monkeypatch, tmp_path, argv, existing=None, post_ok=True, published_back=False):
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(_QUIZ_DRAFT), encoding="utf-8")
    calls = []
    monkeypatch.setattr(sc, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(sc, "CANVAS_BASE_URL", "https://x")
    monkeypatch.setattr(sc.guard, "enforce", lambda **k: None)
    monkeypatch.setattr(sc, "find_existing", lambda cid, kind, title: existing)

    def fake_post(ep, form):
        calls.append(ep)
        if not post_ok:
            return None, "HTTP 400"
        if "modules" in ep:
            return {"id": 1}, ""
        return {"id": 9}, ""

    def fake_get(ep):
        return {"id": 9, "title": _QUIZ_DRAFT["title"], "published": published_back}

    monkeypatch.setattr(sc, "_post", fake_post)
    monkeypatch.setattr(sc, "_get", fake_get)
    monkeypatch.setattr(sys, "argv", ["canvas_shell_create.py", "--course-id", "1",
                                      "--draft", str(draft_path), *argv])
    return sc.main(), calls


def test_dry_run_writes_nothing(monkeypatch, tmp_path):
    rc, calls = _run(monkeypatch, tmp_path, [])
    assert rc == 0 and calls == []


def test_apply_creates_and_verifies(monkeypatch, tmp_path):
    rc, calls = _run(monkeypatch, tmp_path, ["--apply"])
    assert rc == 0 and calls == ["/courses/1/quizzes"]


def test_apply_with_module_id_also_adds_the_item(monkeypatch, tmp_path):
    rc, calls = _run(monkeypatch, tmp_path, ["--apply", "--module-id", "77"])
    assert rc == 0
    assert calls == ["/courses/1/quizzes", "/courses/1/modules/77/items"]


def test_existing_title_is_reported_never_recreated(monkeypatch, tmp_path):
    rc, calls = _run(monkeypatch, tmp_path, ["--apply"], existing={"id": 5})
    assert rc == 0 and calls == []


def test_create_failure_exits_1(monkeypatch, tmp_path):
    rc, calls = _run(monkeypatch, tmp_path, ["--apply"], post_ok=False)
    assert rc == 1


def test_published_readback_exits_1(monkeypatch, tmp_path):
    rc, calls = _run(monkeypatch, tmp_path, ["--apply"], published_back=True)
    assert rc == 1


def test_invalid_draft_exits_2_before_any_network_call(monkeypatch, tmp_path):
    draft_path = tmp_path / "bad.json"
    draft_path.write_text(json.dumps({"kind": "quiz"}), encoding="utf-8")
    monkeypatch.setattr(sc, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(sc, "CANVAS_BASE_URL", "https://x")
    monkeypatch.setattr(sys, "argv", ["canvas_shell_create.py", "--course-id", "1",
                                      "--draft", str(draft_path)])
    assert sc.main() == 2

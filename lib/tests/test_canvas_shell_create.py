"""Unit tests — Canvas object shell creation (#349, #351).

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
    build_assignment_group_payload,
    build_assignment_payload,
    build_discussion_payload,
    build_module_item_payload,
    build_module_payload,
    build_page_payload,
    build_quiz_payload,
    find_existing,
    item_in_module,
    load_draft,
    place_in_modules,
    validate_draft,
)

_QUIZ_DRAFT = {"kind": "quiz", "title": "Prep check", "points_possible": 5,
              "quiz_type": "assignment", "due_at": "2026-10-01T05:59:00Z"}
_ASSIGN_DRAFT = {"kind": "assignment", "title": "Reflection 1", "points_possible": 10}
_PAGE_DRAFT = {"kind": "page", "title": "Week 3 overview", "description": "<p>hi</p>"}
_DISCUSSION_DRAFT = {"kind": "discussion", "title": "Week 3 discussion",
                     "description": "Discuss...", "is_announcement": False}
_MODULE_DRAFT = {"kind": "module", "title": "Week 3", "position": 3}
_AG_DRAFT = {"kind": "assignment_group", "title": "Homework", "group_weight": 20}


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

def test_valid_drafts_pass_for_every_kind():
    assert validate_draft(_QUIZ_DRAFT) == []
    assert validate_draft(_ASSIGN_DRAFT) == []
    assert validate_draft(_PAGE_DRAFT) == []
    assert validate_draft(_DISCUSSION_DRAFT) == []
    assert validate_draft(_MODULE_DRAFT) == []
    assert validate_draft(_AG_DRAFT) == []


@pytest.mark.parametrize("bad", [
    {},
    {"kind": "spreadsheet", "title": "x"},
    {"kind": "quiz"},
    {"kind": "quiz", "title": "  "},
    {"kind": "quiz", "title": "x", "points_possible": -1},
    {"kind": "quiz", "title": "x", "points_possible": "ten"},
    {"kind": "quiz", "title": "x", "grading_type": "vibes"},
    {"kind": "quiz", "title": "x", "quiz_type": "essay"},
    {"kind": "assignment", "title": "x", "submission_types": []},
    {"kind": "assignment", "title": "x", "submission_types": "online_text_entry"},
    {"kind": "quiz", "title": "x", "due_at": 12345},
    {"kind": "discussion", "title": "x", "is_announcement": "yes"},
    {"kind": "module", "title": "x", "position": 0},
    {"kind": "module", "title": "x", "position": "first"},
    {"kind": "module", "title": "x", "position": True},
    {"kind": "assignment_group", "title": "x", "group_weight": -5},
    {"kind": "assignment_group", "title": "x", "group_weight": "lots"},
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


def test_module_item_payload_uses_page_url_not_content_id_for_pages():
    """Canvas's module-item API is the one place Pages break the content_id pattern
    every other type uses — it takes page_url instead."""
    assert build_module_item_payload("page", "week-3-overview", "Week 3 overview") == {
        "module_item": {"title": "Week 3 overview", "type": "Page",
                        "page_url": "week-3-overview"}
    }


def test_module_item_payload_for_discussion():
    assert build_module_item_payload("discussion", 55, "Week 3 discussion") == {
        "module_item": {"title": "Week 3 discussion", "type": "Discussion", "content_id": 55}
    }


# --- payload building — the 4 new kinds (#351) --------------------------------

def test_page_payload_is_nested_and_unpublished():
    payload = build_page_payload(_PAGE_DRAFT)
    assert payload == {"wiki_page": {"title": "Week 3 overview", "body": "<p>hi</p>",
                                     "published": False}}


def test_discussion_payload_is_flat_not_wrapped():
    """The one kind that does NOT use a wrapper key — Canvas's Discussion Topics API
    takes flat params, matching canvas_sync.py's own _push_discussion()."""
    payload = build_discussion_payload(_DISCUSSION_DRAFT)
    assert "discussion_topic" not in payload
    assert payload == {"title": "Week 3 discussion", "message": "Discuss...",
                       "published": False, "is_announcement": False}


def test_discussion_payload_defaults_is_announcement_false():
    payload = build_discussion_payload({"kind": "discussion", "title": "x"})
    assert payload["is_announcement"] is False


def test_module_payload_is_nested_and_unpublished():
    payload = build_module_payload(_MODULE_DRAFT)
    assert payload == {"module": {"name": "Week 3", "published": False, "position": 3}}


def test_module_payload_omits_optional_fields_when_absent():
    payload = build_module_payload({"kind": "module", "title": "x"})
    assert "position" not in payload["module"]
    assert "unlock_at" not in payload["module"]


def test_assignment_group_payload_is_flat_not_wrapped():
    """The other kind (besides discussion) that does NOT use a wrapper key —
    confirmed on a sandbox: a wrapped {"assignment_group": {...}} POST returns 200
    but silently creates a group named "Assignments" with group_weight 0, ignoring
    every field sent."""
    payload = build_assignment_group_payload(_AG_DRAFT)
    assert payload == {"name": "Homework", "group_weight": 20}
    assert "assignment_group" not in payload
    assert "published" not in payload


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


def test_find_existing_uses_name_field_for_modules_and_assignment_groups(monkeypatch):
    monkeypatch.setattr(sc, "_get", lambda ep: [{"id": 3, "name": "Week 3"}])
    assert find_existing("1", "module", "Week 3")["id"] == 3
    monkeypatch.setattr(sc, "_get", lambda ep: [{"id": 4, "name": "Homework"}])
    assert find_existing("1", "assignment_group", "Homework")["id"] == 4


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


def test_create_shell_reads_back_pages_by_url_not_id(monkeypatch):
    """The one kind whose Canvas API path uses the url slug, not a numeric id."""
    monkeypatch.setattr(sc, "_post", lambda ep, form: (
        {"page_id": 9, "url": "week-3-overview"}, ""))
    seen_endpoints = []

    def fake_get(ep):
        seen_endpoints.append(ep)
        return {"url": "week-3-overview", "title": "Week 3 overview", "published": False}

    monkeypatch.setattr(sc, "_get", fake_get)
    back, err = sc.create_shell("1", _PAGE_DRAFT)
    assert back and err == ""
    assert seen_endpoints == ["/courses/1/pages/week-3-overview"]


def test_create_shell_skips_published_check_for_assignment_groups(monkeypatch):
    """Assignment groups have no publish state — a read-back with no 'published'
    key at all (as Canvas actually returns) must not be treated as a failure."""
    monkeypatch.setattr(sc, "_post", lambda ep, form: ({"id": 4}, ""))
    monkeypatch.setattr(sc, "_get", lambda ep: {"id": 4, "name": "Homework"})
    back, err = sc.create_shell("1", _AG_DRAFT)
    assert back and err == ""


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


def test_module_id_refused_for_module_kind(monkeypatch, tmp_path):
    """Modules are never module items themselves — Canvas has no such relationship."""
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(_MODULE_DRAFT), encoding="utf-8")
    monkeypatch.setattr(sc, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(sc, "CANVAS_BASE_URL", "https://x")
    monkeypatch.setattr(sys, "argv", ["canvas_shell_create.py", "--course-id", "1",
                                      "--draft", str(draft_path), "--module-id", "77"])
    assert sc.main() == 2


def test_module_id_refused_for_assignment_group_kind(monkeypatch, tmp_path):
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(_AG_DRAFT), encoding="utf-8")
    monkeypatch.setattr(sc, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(sc, "CANVAS_BASE_URL", "https://x")
    monkeypatch.setattr(sys, "argv", ["canvas_shell_create.py", "--course-id", "1",
                                      "--draft", str(draft_path), "--module-id", "77"])
    assert sc.main() == 2


def test_invalid_draft_exits_2_before_any_network_call(monkeypatch, tmp_path):
    draft_path = tmp_path / "bad.json"
    draft_path.write_text(json.dumps({"kind": "quiz"}), encoding="utf-8")
    monkeypatch.setattr(sc, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(sc, "CANVAS_BASE_URL", "https://x")
    monkeypatch.setattr(sys, "argv", ["canvas_shell_create.py", "--course-id", "1",
                                      "--draft", str(draft_path)])
    assert sc.main() == 2


# --- item_in_module -------------------------------------------------------------

def test_item_in_module_true_on_matching_type_and_content_id(monkeypatch):
    monkeypatch.setattr(sc, "_get", lambda ep: [
        {"type": "Page", "page_url": "other"}, {"type": "Quiz", "content_id": 42}])
    assert item_in_module("1", "77", "quiz", 42) is True


def test_item_in_module_false_when_not_present(monkeypatch):
    monkeypatch.setattr(sc, "_get", lambda ep: [{"type": "Quiz", "content_id": 99}])
    assert item_in_module("1", "77", "quiz", 42) is False


def test_item_in_module_matches_page_by_page_url_not_content_id(monkeypatch):
    monkeypatch.setattr(sc, "_get", lambda ep: [{"type": "Page", "page_url": "week-3"}])
    assert item_in_module("1", "77", "page", "week-3") is True
    assert item_in_module("1", "77", "page", "week-4") is False


# --- place_in_modules — attempts every module even after a failure -------------

def test_place_in_modules_all_succeed(monkeypatch, capsys):
    monkeypatch.setattr(sc, "item_in_module", lambda *a: False)
    monkeypatch.setattr(sc, "_post", lambda ep, form: ({"id": 1}, ""))
    ok = place_in_modules("1", "quiz", 42, "Prep check", ["77", "78"])
    assert ok is True
    out = capsys.readouterr().out
    assert "added to module 77" in out and "added to module 78" in out


def test_place_in_modules_skips_ones_already_placed(monkeypatch, capsys):
    monkeypatch.setattr(sc, "item_in_module", lambda cid, mid, kind, cont: mid == "77")
    posted = []
    monkeypatch.setattr(sc, "_post", lambda ep, form: (posted.append(ep) or {"id": 1}, ""))
    ok = place_in_modules("1", "quiz", 42, "Prep check", ["77", "78"])
    assert ok is True
    assert posted == ["/courses/1/modules/78/items"]
    assert "already in module 77" in capsys.readouterr().out


def test_place_in_modules_attempts_all_even_if_one_fails(monkeypatch, capsys):
    monkeypatch.setattr(sc, "item_in_module", lambda *a: False)

    def fake_post(ep, form):
        if "77" in ep:
            return None, "HTTP 400"
        return {"id": 1}, ""

    monkeypatch.setattr(sc, "_post", fake_post)
    ok = place_in_modules("1", "quiz", 42, "Prep check", ["77", "78"])
    assert ok is False  # overall failure...
    out = capsys.readouterr().out
    assert "ERROR adding to module 77" in out
    assert "added to module 78" in out  # ...but 78 was still attempted


# --- main(): --place mode -------------------------------------------------------

def _run_place(monkeypatch, argv, existing=None, in_module=False, post_ok=True):
    calls = []
    monkeypatch.setattr(sc, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(sc, "CANVAS_BASE_URL", "https://x")
    monkeypatch.setattr(sc.guard, "enforce", lambda **k: None)
    monkeypatch.setattr(sc, "find_existing", lambda cid, kind, title: existing)
    monkeypatch.setattr(sc, "item_in_module", lambda *a: in_module)

    def fake_post(ep, form):
        calls.append(ep)
        if not post_ok:
            return None, "HTTP 400"
        return {"id": 1}, ""

    monkeypatch.setattr(sc, "_post", fake_post)
    monkeypatch.setattr(sys, "argv", ["canvas_shell_create.py", "--course-id", "1", *argv])
    return sc.main(), calls


def test_place_dry_run_writes_nothing(monkeypatch):
    rc, calls = _run_place(monkeypatch,
                           ["--place", "quiz", "--title", "Prep check", "--module-id", "77"],
                           existing={"id": 9})
    assert rc == 0 and calls == []


def test_place_apply_places_existing_item(monkeypatch):
    rc, calls = _run_place(monkeypatch,
                           ["--place", "quiz", "--title", "Prep check", "--module-id", "77",
                            "--apply"],
                           existing={"id": 9})
    assert rc == 0 and calls == ["/courses/1/modules/77/items"]


def test_place_apply_into_two_modules(monkeypatch):
    """#355's core case: the same item placed into 2+ modules."""
    rc, calls = _run_place(monkeypatch,
                           ["--place", "quiz", "--title", "Prep check",
                            "--module-id", "77", "--module-id", "78", "--apply"],
                           existing={"id": 9})
    assert rc == 0
    assert calls == ["/courses/1/modules/77/items", "/courses/1/modules/78/items"]


def test_place_no_matching_item_exits_1(monkeypatch):
    rc, calls = _run_place(monkeypatch,
                           ["--place", "quiz", "--title", "Nonexistent", "--module-id", "77",
                            "--apply"],
                           existing=None)
    assert rc == 1 and calls == []


def test_place_requires_title(monkeypatch):
    rc, _ = _run_place(monkeypatch, ["--place", "quiz", "--module-id", "77"])
    assert rc == 2


def test_place_requires_at_least_one_module_id(monkeypatch):
    rc, _ = _run_place(monkeypatch, ["--place", "quiz", "--title", "Prep check"])
    assert rc == 2


def test_place_and_draft_are_mutually_exclusive(monkeypatch, tmp_path):
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(_QUIZ_DRAFT), encoding="utf-8")
    monkeypatch.setattr(sc, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(sc, "CANVAS_BASE_URL", "https://x")
    monkeypatch.setattr(sys, "argv", ["canvas_shell_create.py", "--course-id", "1",
                                      "--draft", str(draft_path),
                                      "--place", "quiz", "--title", "x", "--module-id", "77"])
    assert sc.main() == 2


def test_neither_draft_nor_place_exits_2(monkeypatch):
    monkeypatch.setattr(sc, "CANVAS_API_TOKEN", "t")
    monkeypatch.setattr(sc, "CANVAS_BASE_URL", "https://x")
    monkeypatch.setattr(sys, "argv", ["canvas_shell_create.py", "--course-id", "1"])
    assert sc.main() == 2


# --- main(): create mode — the "already exists" short-circuit fix (#355) -------

def test_existing_item_with_module_id_places_it_instead_of_only_reporting(monkeypatch, tmp_path):
    """The bug: hitting 'already exists' used to return immediately, so
    --module-id on a second run silently did nothing."""
    rc, calls = _run(monkeypatch, tmp_path, ["--apply", "--module-id", "77"],
                     existing={"id": 5})
    assert rc == 0
    assert calls == ["/courses/1/modules/77/items"]


def test_existing_item_with_module_id_dry_run_does_not_place(monkeypatch, tmp_path):
    rc, calls = _run(monkeypatch, tmp_path, ["--module-id", "77"], existing={"id": 5})
    assert rc == 0 and calls == []


def test_existing_item_without_module_id_still_just_reports(monkeypatch, tmp_path):
    """No regression on the ordinary already-exists path when no module is asked for."""
    rc, calls = _run(monkeypatch, tmp_path, ["--apply"], existing={"id": 5})
    assert rc == 0 and calls == []


def test_create_apply_into_two_modules(monkeypatch, tmp_path):
    """#355: --module-id is now repeatable at creation time too."""
    rc, calls = _run(monkeypatch, tmp_path,
                     ["--apply", "--module-id", "77", "--module-id", "78"])
    assert rc == 0
    assert calls == ["/courses/1/quizzes", "/courses/1/modules/77/items",
                     "/courses/1/modules/78/items"]

"""Tests for the v2 capability-consent gate (#317 Phase 7).

"A package cannot approve itself" is the property under test throughout: the
only function that writes approval state is record_approval(), and it takes
approved_by as a required, explicit argument — nothing here reads or infers
consent from package manifest content itself.
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import pytest

import capability_consent as cc  # noqa: E402


def _package(**overrides) -> dict:
    base = {
        "id": "grading",
        "version": "2.0.0",
        "name": "Grading",
        "description": "FERPA-safe grading.",
        "tools": [
            {"id": "grader-fetch", "command": "lib/tools/grader_fetch.py",
             "effect": "read", "data_class": "student_submission", "approval": "none"},
        ],
        "credentials": ["CANVAS_API_TOKEN", "CANVAS_BASE_URL"],
        "network": ["canvas_base_url_only"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# compute_fingerprint
# ---------------------------------------------------------------------------

def test_fingerprint_never_includes_a_credential_value():
    fp = cc.compute_fingerprint(_package())
    assert fp["credentials"] == ["CANVAS_API_TOKEN", "CANVAS_BASE_URL"]
    assert not any("=" in c or len(c) > 40 for c in fp["credentials"])  # names, not secrets


def test_fingerprint_is_order_independent():
    a = cc.compute_fingerprint(_package(credentials=["B", "A"]))
    b = cc.compute_fingerprint(_package(credentials=["A", "B"]))
    assert a == b


# ---------------------------------------------------------------------------
# capability_diff / has_grown — the five required scenarios
# ---------------------------------------------------------------------------

def test_a_never_approved_package_is_growth_by_definition():
    fp = cc.compute_fingerprint(_package())
    diff = cc.capability_diff(None, fp)
    assert cc.has_grown(diff)
    assert diff["credentials"] == ["CANVAS_API_TOKEN", "CANVAS_BASE_URL"]


def test_added_canvas_writer_is_growth():
    old = cc.compute_fingerprint(_package())
    new_pkg = _package(tools=_package()["tools"] + [
        {"id": "grader-push", "command": "lib/tools/grader_push.py",
         "effect": "canvas_grade_comment_write", "data_class": "student_evaluation",
         "approval": "always"},
    ])
    diff = cc.capability_diff(old, cc.compute_fingerprint(new_pkg))
    assert cc.has_grown(diff)
    assert "grader-push" in diff["canvas_writers"]
    assert "canvas_grade_comment_write" in diff["effects"]


def test_added_data_class_is_growth():
    old = cc.compute_fingerprint(_package())
    new_pkg = _package(tools=[
        {"id": "grader-fetch", "command": "lib/tools/grader_fetch.py",
         "effect": "read", "data_class": "student_submission", "approval": "none"},
        {"id": "grader-reidentify", "command": "lib/tools/grader_reidentify.py",
         "effect": "local_write", "data_class": "student_evaluation", "approval": "none"},
    ])
    diff = cc.capability_diff(old, cc.compute_fingerprint(new_pkg))
    assert cc.has_grown(diff)
    assert diff["data_classes"] == ["student_evaluation"]


def test_added_network_scope_is_growth():
    old = cc.compute_fingerprint(_package())
    new_pkg = _package(network=["canvas_base_url_only", "github_repository_only"])
    diff = cc.capability_diff(old, cc.compute_fingerprint(new_pkg))
    assert cc.has_grown(diff)
    assert diff["network"] == ["github_repository_only"]


def test_added_credential_is_growth():
    old = cc.compute_fingerprint(_package())
    new_pkg = _package(credentials=["CANVAS_API_TOKEN", "CANVAS_BASE_URL", "CANVAS_SANDBOX_ID"])
    diff = cc.capability_diff(old, cc.compute_fingerprint(new_pkg))
    assert cc.has_grown(diff)
    assert diff["credentials"] == ["CANVAS_SANDBOX_ID"]


def test_removing_a_capability_is_not_growth():
    old = cc.compute_fingerprint(_package(network=["canvas_base_url_only",
                                                    "github_repository_only"]))
    new_pkg = _package(network=["canvas_base_url_only"])
    diff = cc.capability_diff(old, cc.compute_fingerprint(new_pkg))
    assert not cc.has_grown(diff)


def test_wording_only_change_is_not_growth():
    old = cc.compute_fingerprint(_package())
    new_pkg = _package(version="2.0.1", description="Updated wording, same capabilities.")
    diff = cc.capability_diff(old, cc.compute_fingerprint(new_pkg))
    assert not cc.has_grown(diff)


def test_identical_fingerprint_is_not_growth():
    fp = cc.compute_fingerprint(_package())
    assert not cc.has_grown(cc.capability_diff(fp, fp))


# ---------------------------------------------------------------------------
# render_install_summary — concise, names not just counts
# ---------------------------------------------------------------------------

def test_summary_names_canvas_writers_not_just_a_count():
    pkg = _package(tools=[
        {"id": "grader-push", "command": "lib/tools/grader_push.py",
         "effect": "canvas_grade_comment_write", "data_class": "student_evaluation",
         "approval": "always"},
    ])
    summary = cc.render_install_summary(pkg)
    assert "grader-push" in summary
    assert "student_evaluation" in summary
    assert "CANVAS_API_TOKEN" in summary


def test_summary_shows_new_entries_when_a_diff_is_given():
    old = cc.compute_fingerprint(_package())
    new_pkg = _package(network=["canvas_base_url_only", "github_repository_only"])
    diff = cc.capability_diff(old, cc.compute_fingerprint(new_pkg))
    summary = cc.render_install_summary(new_pkg, diff)
    assert "NEW since last approval" in summary
    assert "github_repository_only" in summary


def test_summary_labels_a_never_approved_package_as_first_approval_not_new():
    """Found for real in the m119-master pilot: a package's very first v2
    consent run (no prior approval record at all — capability_diff(None, fp))
    read as "NEW since last approval" on every field, which misleadingly
    implies something used to be approved and changed. first_approval=True
    is exactly the old=None case."""
    pkg = _package()
    diff = cc.capability_diff(None, cc.compute_fingerprint(pkg))
    summary = cc.render_install_summary(pkg, diff, first_approval=True)
    assert "first approval" in summary
    assert "NEW since last approval" not in summary


# ---------------------------------------------------------------------------
# load_approvals / record_approval — the self-approval boundary
# ---------------------------------------------------------------------------

def test_load_approvals_is_empty_when_file_absent(tmp_path):
    assert cc.load_approvals(tmp_path) == {}


def test_load_approvals_fails_toward_requiring_consent_on_corrupt_file(tmp_path):
    (tmp_path / cc.APPROVALS_FILE).write_text("not json{{{", encoding="utf-8")
    assert cc.load_approvals(tmp_path) == {}


def test_record_approval_requires_an_explicit_approver(tmp_path):
    fp = cc.compute_fingerprint(_package())
    with pytest.raises(ValueError):
        cc.record_approval(tmp_path, "grading", fp, approved_by="")


def test_record_approval_persists_and_round_trips(tmp_path):
    fp = cc.compute_fingerprint(_package())
    cc.record_approval(tmp_path, "grading", fp, approved_by="instructor via chat")
    approvals = cc.load_approvals(tmp_path)
    assert approvals["grading"]["fingerprint"] == fp
    assert approvals["grading"]["approved_by"] == "instructor via chat"
    assert "approved_at" in approvals["grading"]


def test_record_approval_preserves_other_packages(tmp_path):
    fp_a = cc.compute_fingerprint(_package(id="course-design"))
    fp_b = cc.compute_fingerprint(_package(id="grading"))
    cc.record_approval(tmp_path, "course-design", fp_a, approved_by="op")
    cc.record_approval(tmp_path, "grading", fp_b, approved_by="op")
    approvals = cc.load_approvals(tmp_path)
    assert set(approvals) == {"course-design", "grading"}


def test_a_package_cannot_approve_itself_via_manifest_content(tmp_path):
    """Nothing in the manifest — however it's shaped — can cause an approval to
    be written. The schema doesn't even define an 'approved' key, and this
    asserts the loader doesn't honor one anyway if it somehow got through."""
    sneaky = _package()
    sneaky["approved"] = True                     # not a real schema field
    sneaky["pre_approved_by"] = "the package itself"
    # Merely computing a fingerprint / rendering a summary from a manifest that
    # tries to declare its own approval must never write anything.
    cc.compute_fingerprint(sneaky)
    cc.render_install_summary(sneaky)
    assert cc.load_approvals(tmp_path) == {}       # nothing was ever written


def test_record_approval_overwrites_only_the_named_package(tmp_path):
    fp1 = cc.compute_fingerprint(_package())
    cc.record_approval(tmp_path, "grading", fp1, approved_by="op")
    fp2 = cc.compute_fingerprint(_package(network=["canvas_base_url_only",
                                                    "github_repository_only"]))
    cc.record_approval(tmp_path, "grading", fp2, approved_by="op")
    approvals = cc.load_approvals(tmp_path)
    assert len(approvals) == 1
    assert approvals["grading"]["fingerprint"] == fp2

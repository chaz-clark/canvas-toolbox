"""Tests for canvas_run.py — the Canvas access boundary.

The gate is the ONLY process permitted to hold CANVAS_API_TOKEN. Its job is to
turn a named subcommand into exactly one toolkit invocation, refusing anything
it does not recognize (default-deny) and refusing writes that lack an explicit
per-course confirmation.

Course ids here are placeholders (111111 / 999999), not real courses.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
spec = importlib.util.spec_from_file_location("canvas_run", TOOLS / "canvas_run.py")
canvas_run = importlib.util.module_from_spec(spec)
sys.modules["canvas_run"] = canvas_run
spec.loader.exec_module(canvas_run)

resolve_command = canvas_run.resolve_command
GateRefusal = canvas_run.GateRefusal

COURSE = "111111"
OTHER_COURSE = "999999"


def test_pull_is_free_and_maps_to_canvas_sync():
    argv = resolve_command("pull", confirm_course=None, course_id=COURSE)
    assert argv == ["lib/tools/canvas_sync.py", "--pull"]


def test_status_is_free():
    argv = resolve_command("status", confirm_course=None, course_id=COURSE)
    assert argv == ["lib/tools/canvas_sync.py", "--status"]


def test_audit_is_free_and_interpolates_the_course_id():
    argv = resolve_command("audit", confirm_course=None, course_id=COURSE)
    assert argv == [
        "lib/tools/course_audit.py",
        "--full",
        "--course-id",
        COURSE,
        "--report",
        "audit.md",
    ]


def test_unlisted_subcommand_is_refused():
    """Default-deny is the core property. Anything not named is refused."""
    with pytest.raises(GateRefusal) as exc:
        resolve_command("rm-rf", confirm_course=None, course_id=COURSE)
    assert "not on the allowlist" in str(exc.value)


def test_push_without_confirmation_is_refused():
    with pytest.raises(GateRefusal) as exc:
        resolve_command("push", confirm_course=None, course_id=COURSE)
    assert "--confirm-course" in str(exc.value)


def test_push_with_mismatched_confirmation_is_refused():
    """Guards the wrong-course push — the expensive mistake."""
    with pytest.raises(GateRefusal) as exc:
        resolve_command("push", confirm_course=OTHER_COURSE, course_id=COURSE)
    assert "does not match" in str(exc.value)


def test_push_with_matching_confirmation_is_allowed():
    argv = resolve_command("push", confirm_course=COURSE, course_id=COURSE)
    assert argv == ["lib/tools/canvas_sync.py", "--push"]


def test_every_gated_subcommand_requires_confirmation():
    """A new entry in GATED must not be able to skip the confirmation gate."""
    for name in canvas_run.GATED:
        with pytest.raises(GateRefusal):
            resolve_command(name, confirm_course=None, course_id=COURSE)


# --- --allow-enrolled ------------------------------------------------------
#
# canvas_course_guard refuses a write to a course that has enrolled students
# unless --allow-enrolled is passed. Without a way to forward it, the gate had NO
# working write path on any live course: `push --confirm-course <id>` was refused
# by the guard every time. Found by running it against a live course.
#
# Forwarded for writes only, and it does not replace --confirm-course: a live
# push takes BOTH flags.


def test_push_forwards_allow_enrolled_when_asked():
    argv = resolve_command(
        "push", confirm_course=COURSE, course_id=COURSE, allow_enrolled=True
    )
    assert argv == ["lib/tools/canvas_sync.py", "--push", "--allow-enrolled"]


def test_push_omits_allow_enrolled_by_default():
    """Default stays safe: the guard refuses, which is the correct outcome
    unless the operator has explicitly said otherwise."""
    argv = resolve_command("push", confirm_course=COURSE, course_id=COURSE)
    assert "--allow-enrolled" not in argv


def test_allow_enrolled_does_not_bypass_confirm_course():
    """The override must not become a shortcut around the write confirmation."""
    with pytest.raises(GateRefusal) as exc:
        resolve_command(
            "push", confirm_course=None, course_id=COURSE, allow_enrolled=True
        )
    assert "--confirm-course" in str(exc.value)


def test_allow_enrolled_does_not_bypass_course_mismatch():
    with pytest.raises(GateRefusal) as exc:
        resolve_command(
            "push", confirm_course=OTHER_COURSE, course_id=COURSE, allow_enrolled=True
        )
    assert "does not match" in str(exc.value)


@pytest.mark.parametrize("name", sorted(canvas_run.FREE))
def test_allow_enrolled_is_refused_on_read_only_subcommands(name):
    """Refused, not ignored — so the flag never becomes muscle memory on the
    commands where it does nothing."""
    with pytest.raises(GateRefusal) as exc:
        resolve_command(
            name, confirm_course=None, course_id=COURSE, allow_enrolled=True
        )
    assert "WRITE override" in str(exc.value)


def test_gated_template_is_not_mutated_across_calls():
    """resolve_command must COPY the template. Appending to GATED[subcommand]
    itself would arm --allow-enrolled for every later push in the process."""
    resolve_command(
        "push", confirm_course=COURSE, course_id=COURSE, allow_enrolled=True
    )
    argv = resolve_command("push", confirm_course=COURSE, course_id=COURSE)
    assert argv == ["lib/tools/canvas_sync.py", "--push"]
    assert canvas_run.GATED["push"] == ["lib/tools/canvas_sync.py", "--push"]


def test_read_token_refuses_when_file_missing(tmp_path):
    missing = tmp_path / "nope.env"
    with pytest.raises(GateRefusal) as exc:
        canvas_run.read_token(str(missing))
    assert "not found" in str(exc.value)


def test_read_token_refuses_when_token_empty(tmp_path):
    token_file = tmp_path / ".env.canvas"
    token_file.write_text("CANVAS_API_TOKEN=\n", encoding="utf-8")
    with pytest.raises(GateRefusal) as exc:
        canvas_run.read_token(str(token_file))
    assert "non-empty" in str(exc.value)


def test_read_token_reads_the_value(tmp_path):
    token_file = tmp_path / ".env.canvas"
    token_file.write_text(
        "# a comment\nCANVAS_API_TOKEN=abc123\n", encoding="utf-8"
    )
    assert canvas_run.read_token(str(token_file)) == "abc123"

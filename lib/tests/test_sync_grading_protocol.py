"""Unit tests — sync_grading_protocol pointer injection (issue #207).

The retrofit tool must be idempotent (safe to re-run against every course repo)
and non-destructive (course-specific content around the pointer is preserved).
It shares POINTER_BLOCK with cb_init, so a freshly-init'd stub and a retrofitted
file must agree — that agreement is what keeps the tool from double-injecting.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from sync_grading_protocol import (  # noqa: E402
    inject_grading_pointer,
    process_agents_file,
    POINTER_MARKER,
    POINTER_BLOCK,
)


def test_injects_after_the_first_title():
    text = "# DS460\n\nSome intro.\n\n## Structure\n\ndetails\n"
    new, changed = inject_grading_pointer(text)
    assert changed is True
    assert POINTER_MARKER in new
    # inserted AFTER the title, BEFORE the first real section
    assert new.index("# DS460") < new.index(POINTER_MARKER) < new.index("## Structure")
    # original content is preserved verbatim
    assert "Some intro." in new and "## Structure" in new and "details" in new


def test_idempotent_when_marker_present():
    """Re-running against an already-pointed file is a no-op — the core safety
    property for a tool run across every course repo."""
    once, _ = inject_grading_pointer("# DS250\n\nbody\n")
    twice, changed = inject_grading_pointer(once)
    assert changed is False
    assert twice == once
    assert twice.count(POINTER_MARKER) == 1  # not doubled


def test_prepends_when_no_title():
    text = "just some notes, no heading\n"
    new, changed = inject_grading_pointer(text)
    assert changed is True
    assert new.startswith(POINTER_MARKER)
    assert new.rstrip().endswith("just some notes, no heading")


def test_cb_init_stub_block_is_recognized():
    """A file already carrying the shared POINTER_BLOCK (as cb_init emits into a
    fresh stub) must be treated as present — otherwise new repos double-inject."""
    stub = f"---\n\n{POINTER_BLOCK}\n\n---\n"
    _, changed = inject_grading_pointer(stub)
    assert changed is False


def test_process_reports_missing_file(tmp_path, capsys):
    status = process_agents_file(tmp_path / "AGENTS.md", apply=False)
    assert status == "missing"


def test_process_dry_run_does_not_write(tmp_path):
    p = tmp_path / "AGENTS.md"
    p.write_text("# Course\n\nbody\n", encoding="utf-8")
    status = process_agents_file(p, apply=False)
    assert status == "would-inject"
    assert POINTER_MARKER not in p.read_text(encoding="utf-8")  # untouched


def test_process_apply_writes_once(tmp_path):
    p = tmp_path / "AGENTS.md"
    p.write_text("# Course\n\nbody\n", encoding="utf-8")
    assert process_agents_file(p, apply=True) == "injected"
    assert POINTER_MARKER in p.read_text(encoding="utf-8")
    # second apply is a no-op
    assert process_agents_file(p, apply=True) == "present"
    assert p.read_text(encoding="utf-8").count(POINTER_MARKER) == 1

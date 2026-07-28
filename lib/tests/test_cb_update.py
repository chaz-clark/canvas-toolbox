"""Unit tests — cb_update ("cb re-init"): skill symlinks + pointer refresh.

The field audit found the 6 operating-mode skills active in 0/9 consumer repos and a
stale pointer in 6/9. These pin the two fixes: install skills at the course root
(non-clobbering) and refresh the pointer in place.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from cb_update import (  # noqa: E402
    plan_skill_symlinks,
    install_skill_symlinks,
    ensure_gitignore,
    refresh_pointer,
)


def _fake_course(tmp_path):
    """A course root with a vendored canvas-toolbox/.claude/skills/<name>/SKILL.md."""
    for s in ("grading", "audit"):
        d = tmp_path / "canvas-toolbox" / ".claude" / "skills" / s
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {s}\n---\n", encoding="utf-8")
    return tmp_path


def test_plan_targets_are_relative_and_point_into_the_toolkit():
    plan = plan_skill_symlinks(Path("/course"), "canvas-toolbox", ["grading"])
    link, rel = plan[0]
    assert link == Path("/course/.claude/skills/grading")
    # from <course>/.claude/skills/ up to <course>/ then into the toolkit
    assert rel == "../../canvas-toolbox/.claude/skills/grading"


def test_install_dry_run_writes_nothing(tmp_path):
    course = _fake_course(tmp_path)
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    res = install_skill_symlinks(plan, apply=False)
    assert res == [("grading", "would-link")]
    assert not (course / ".claude" / "skills" / "grading").exists()


def test_install_creates_symlink_that_resolves_to_the_toolkit_skill(tmp_path):
    course = _fake_course(tmp_path)
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    res = install_skill_symlinks(plan, apply=True)
    assert res == [("grading", "linked")]
    link = course / ".claude" / "skills" / "grading"
    assert link.is_symlink()
    assert (link / "SKILL.md").read_text(encoding="utf-8").startswith("---")  # resolves
    # re-run is idempotent
    assert install_skill_symlinks(plan, apply=True) == [("grading", "present")]


def test_install_never_clobbers_a_course_owned_skill(tmp_path):
    course = _fake_course(tmp_path)
    owned = course / ".claude" / "skills" / "grading"
    owned.mkdir(parents=True)
    (owned / "SKILL.md").write_text("course's own\n", encoding="utf-8")
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    assert install_skill_symlinks(plan, apply=True) == [("grading", "skip-course-owns")]
    assert (owned / "SKILL.md").read_text(encoding="utf-8") == "course's own\n"  # intact


def test_ensure_gitignore_adds_skills_line_once(tmp_path):
    assert ensure_gitignore(tmp_path, apply=True) == "added"
    assert ".claude/skills/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ensure_gitignore(tmp_path, apply=True) == "present"  # idempotent


def test_refresh_pointer_injects_into_course_agents(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# ITM327\n\nCourse context.\n", encoding="utf-8")
    fname, status = refresh_pointer(tmp_path, apply=True)
    assert (fname, status) == ("AGENTS.md", "refreshed")
    body = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert ".claude/skills" in body and "Course context." in body  # added, non-clobbering
    assert refresh_pointer(tmp_path, apply=True)[1] == "present"  # idempotent


def test_refresh_pointer_reports_missing_when_no_agents_file(tmp_path):
    assert refresh_pointer(tmp_path, apply=True)[1] == "missing"

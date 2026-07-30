"""Unit tests — cb_update ("cb re-init"): skill symlinks + pointer refresh.

The field audit found the 6 operating-mode skills active in 0/9 consumer repos and a
stale pointer in 6/9. These pin the two fixes: install skills at the course root
(non-clobbering) and refresh the pointer in place.
"""
import os
import subprocess
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import json  # noqa: E402
from cb_update import ensure_guardian_hook  # noqa: E402


def _fake_toolkit(tmp_path):
    """A course root with a vendored canvas-toolbox/lib/tools/grade_guardian.py."""
    g = tmp_path / "canvas-toolbox" / "lib" / "tools"
    g.mkdir(parents=True)
    (g / "grade_guardian.py").write_text("# guardian\n", encoding="utf-8")
    return tmp_path


def test_ensure_guardian_hook_installs_when_missing(tmp_path):
    """The CSE450 gap: a repo cb_update'd for skills but never given the guardian.
    cb_update now installs it (non-clobbering, idempotent)."""
    course = _fake_toolkit(tmp_path)
    assert ensure_guardian_hook(course, "canvas-toolbox", apply=False) == "would-install"
    assert not (course / ".claude" / "settings.json").exists()   # dry-run wrote nothing
    assert ensure_guardian_hook(course, "canvas-toolbox", apply=True) == "installed"
    settings = json.loads((course / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "grade_guardian" in json.dumps(settings)               # hook wired
    assert ensure_guardian_hook(course, "canvas-toolbox", apply=True) == "present"  # idempotent


def test_ensure_guardian_hook_skips_without_vendored_script(tmp_path):
    assert ensure_guardian_hook(tmp_path, "canvas-toolbox", apply=True) == "skipped-no-script"


def test_ensure_guardian_hook_refuses_unparseable_settings(tmp_path):
    course = _fake_toolkit(tmp_path)
    (course / ".claude").mkdir()
    (course / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
    assert ensure_guardian_hook(course, "canvas-toolbox", apply=True) == "bad-json"


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
    # from <course>/.claude/skills/ up to <course>/ then into the toolkit.
    # Normalize the separator so this holds on Windows (relpath yields '\\').
    assert rel.replace(os.sep, "/") == "../../canvas-toolbox/.claude/skills/grading"


def test_install_dry_run_writes_nothing(tmp_path):
    course = _fake_course(tmp_path)
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    res = install_skill_symlinks(plan, apply=False)
    assert res == [("grading", "would-install")]
    assert not (course / ".claude" / "skills" / "grading").exists()


def test_windows_copy_fallback_is_marked_and_refreshed(tmp_path, monkeypatch):
    """No-symlink environment (Windows w/o dev mode): fall back to a COPY, mark it
    ours, and REFRESH it on re-run — the bug was a re-run mistaking the copy for a
    course-owned skill and freezing it stale after every git pull."""
    course = _fake_course(tmp_path)
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    monkeypatch.setattr(Path, "symlink_to",
                        lambda self, target: (_ for _ in ()).throw(OSError("no symlink")))
    assert install_skill_symlinks(plan, apply=True) == [("grading", "copied")]
    link = course / ".claude" / "skills" / "grading"
    assert link.is_dir() and not link.is_symlink()
    assert (link / "SKILL.md").exists()          # copied content present
    assert (link / ".cb_managed").is_file()       # marked as ours
    # re-run REFRESHES the copy (does NOT skip it as course-owned)
    assert install_skill_symlinks(plan, apply=True) == [("grading", "copied")]


def test_course_owned_dir_without_marker_is_never_touched(tmp_path, monkeypatch):
    """A real skill dir the course made (no marker) is left alone even in the
    no-symlink path — we only refresh copies WE made."""
    course = _fake_course(tmp_path)
    owned = course / ".claude" / "skills" / "grading"
    owned.mkdir(parents=True)
    (owned / "SKILL.md").write_text("course's own\n", encoding="utf-8")  # no .cb_managed
    monkeypatch.setattr(Path, "symlink_to",
                        lambda self, target: (_ for _ in ()).throw(OSError("no symlink")))
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    assert install_skill_symlinks(plan, apply=True) == [("grading", "skip-course-owns")]
    assert (owned / "SKILL.md").read_text(encoding="utf-8") == "course's own\n"


def test_install_makes_the_skill_resolvable_and_stable(tmp_path):
    """OS-agnostic guarantee: after install the skill is readable at the course root
    (symlink where supported, copy on Windows), and a re-run is stable."""
    course = _fake_course(tmp_path)
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    status = install_skill_symlinks(plan, apply=True)[0][1]
    assert status in ("linked", "copied")     # symlink on posix, copy fallback on Windows
    link = course / ".claude" / "skills" / "grading"
    assert (link / "SKILL.md").read_text(encoding="utf-8").startswith("---")  # resolves
    # re-run is stable: a correct symlink → 'present'; a copy → refreshed
    assert install_skill_symlinks(plan, apply=True)[0][1] in ("present", "copied")


def test_install_never_clobbers_a_course_owned_skill(tmp_path):
    course = _fake_course(tmp_path)
    owned = course / ".claude" / "skills" / "grading"
    owned.mkdir(parents=True)
    (owned / "SKILL.md").write_text("course's own\n", encoding="utf-8")
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    assert install_skill_symlinks(plan, apply=True) == [("grading", "skip-course-owns")]
    assert (owned / "SKILL.md").read_text(encoding="utf-8") == "course's own\n"  # intact


def _gi_lines(tmp_path):
    return (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_ensure_gitignore_ignores_toolkit_skills_by_name_not_the_directory(tmp_path):
    """The blanket `.claude/skills/` also swallowed course-OWNED skills (#271).
    Ignore only the names this tool installs."""
    assert ensure_gitignore(tmp_path, ["grading", "audit"], apply=True) == "added"
    lines = _gi_lines(tmp_path)
    assert ".claude/skills/grading/" in lines and ".claude/skills/audit/" in lines
    assert ".claude/skills/" not in lines                   # never the whole directory
    assert ensure_gitignore(tmp_path, ["grading", "audit"], apply=True) == "present"


def test_ensure_gitignore_migrates_the_legacy_blanket_line(tmp_path):
    """Every repo an older cb_update already touched has the blanket line, and the
    old code returned 'present' on sight of it — so a changed emit alone would fix
    only fresh repos. Replace it in place."""
    (tmp_path / ".gitignore").write_text(
        "*.pyc\n.claude/skills/\n.env\n", encoding="utf-8")
    assert ensure_gitignore(tmp_path, ["grading"], apply=False) == "would-migrate"
    assert ".claude/skills/" in _gi_lines(tmp_path)          # dry-run wrote nothing
    assert ensure_gitignore(tmp_path, ["grading"], apply=True) == "migrated"
    lines = _gi_lines(tmp_path)
    assert lines == ["*.pyc", ".claude/skills/grading/", ".env"]  # in place, nothing lost
    assert ensure_gitignore(tmp_path, ["grading"], apply=True) == "present"  # idempotent


def test_ensure_gitignore_adds_only_newly_shipped_skills(tmp_path):
    ensure_gitignore(tmp_path, ["grading"], apply=True)
    assert ensure_gitignore(tmp_path, ["grading", "improve"], apply=True) == "added"
    assert _gi_lines(tmp_path).count(".claude/skills/grading/") == 1   # no duplicate


def test_course_owned_skill_stays_visible_to_git(tmp_path):
    """The bug as the consumer felt it: a course-authored skill added AFTER
    cb_update ran was untracked AND ignored, so `git add -A` silently skipped it."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    owned = tmp_path / ".claude" / "skills" / "my-course-skill"
    owned.mkdir(parents=True)
    (owned / "SKILL.md").write_text("course's own\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".claude/skills/\n", encoding="utf-8")  # legacy

    def ignored(rel):
        return subprocess.run(["git", "-C", str(tmp_path), "check-ignore", "-q", rel]
                              ).returncode == 0

    assert ignored(".claude/skills/my-course-skill/SKILL.md")      # the bug
    ensure_gitignore(tmp_path, ["grading"], apply=True)
    assert not ignored(".claude/skills/my-course-skill/SKILL.md")  # fixed
    assert ignored(".claude/skills/grading/")                      # toolkit's own still ignored
    status = subprocess.run(["git", "-C", str(tmp_path), "status", "--short", "-uall"],
                            capture_output=True, text=True).stdout
    assert "my-course-skill/SKILL.md" in status   # the consumer can finally commit it
    assert "skills/grading" not in status         # toolkit symlinks still stay out


def test_refresh_pointer_injects_into_course_agents(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# ITM327\n\nCourse context.\n", encoding="utf-8")
    fname, status = refresh_pointer(tmp_path, apply=True)
    assert (fname, status) == ("AGENTS.md", "refreshed")
    body = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert ".claude/skills" in body and "Course context." in body  # added, non-clobbering
    assert refresh_pointer(tmp_path, apply=True)[1] == "present"  # idempotent


def test_refresh_pointer_reports_missing_when_no_agents_file(tmp_path):
    assert refresh_pointer(tmp_path, apply=True)[1] == "missing"

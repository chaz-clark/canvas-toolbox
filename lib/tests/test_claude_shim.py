"""Tier 1 unit tests — the .claude/CLAUDE.md shim (cb_update).

Source: lib/tools/cb_update.py
  - plan_claude_shim     (pure: link path + relative target)
  - install_claude_shim  (create / refresh / never clobber course-owned)
  - ensure_gitignore     (the shim line, alongside the skills lines)

WHY THE SHIM EXISTS: Claude Code does not read AGENTS.md — it reads CLAUDE.md or
.claude/CLAUDE.md. A repo whose only instruction file is AGENTS.md hands it
nothing, silently. These tests pin the three behaviours that make the fix safe:
the link resolves to the real AGENTS.md content, a hand-written CLAUDE.md is
never clobbered, and the Windows copy fallback is re-detected on a later run
instead of being mistaken for course-owned content.

No network. Real symlinks on a real filesystem — a pattern-only assertion cannot
see the class of bug #277 was.
"""
import os
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


from cb_update import (  # noqa: E402
    CLAUDE_SHIM,
    ensure_gitignore,
    install_claude_shim,
    plan_claude_shim,
)

AGENTS = "# Constitution\n\nNever read grading/.deid_master.csv.\n"


def _repo(tmp_path: Path, agents: str | None = AGENTS) -> Path:
    if agents is not None:
        (tmp_path / "AGENTS.md").write_text(agents, encoding="utf-8")
    (tmp_path / ".claude").mkdir(exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# plan_claude_shim — pure
# ---------------------------------------------------------------------------

def test_plan_points_up_one_level(tmp_path):
    link, rel = plan_claude_shim(tmp_path)
    assert link == tmp_path / ".claude" / "CLAUDE.md"
    assert rel == os.path.join("..", "AGENTS.md")


def test_plan_target_is_relative_not_absolute(tmp_path):
    """A relative target survives the repo being cloned to another path."""
    _, rel = plan_claude_shim(tmp_path)
    assert not os.path.isabs(rel)


# ---------------------------------------------------------------------------
# install_claude_shim
# ---------------------------------------------------------------------------

def test_creates_symlink_that_resolves_to_agents_content(tmp_path):
    root = _repo(tmp_path)
    link, rel = plan_claude_shim(root)
    assert install_claude_shim(link, rel, apply=True) == "linked"
    assert link.is_symlink()
    # the point of the whole exercise: reading CLAUDE.md yields the constitution
    assert link.read_text(encoding="utf-8") == AGENTS


def test_dry_run_writes_nothing(tmp_path):
    root = _repo(tmp_path)
    link, rel = plan_claude_shim(root)
    assert install_claude_shim(link, rel, apply=False) == "would-install"
    assert not link.exists()


def test_rerun_on_correct_symlink_is_present(tmp_path):
    root = _repo(tmp_path)
    link, rel = plan_claude_shim(root)
    install_claude_shim(link, rel, apply=True)
    assert install_claude_shim(link, rel, apply=True) == "present"


def test_never_clobbers_a_hand_written_claude_md(tmp_path):
    """A course that authored its own CLAUDE.md keeps it — same protection
    install_skill_symlinks gives a course-owned skill."""
    root = _repo(tmp_path)
    link, rel = plan_claude_shim(root)
    link.write_text("# My own notes\n", encoding="utf-8")
    assert install_claude_shim(link, rel, apply=True) == "skip-course-owns"
    assert link.read_text(encoding="utf-8") == "# My own notes\n"
    assert not link.is_symlink()


def test_missing_agents_md_is_reported_not_crashed(tmp_path):
    root = _repo(tmp_path, agents=None)
    link, rel = plan_claude_shim(root)
    assert install_claude_shim(link, rel, apply=True) == "missing-target"
    assert not link.exists()


def test_stale_symlink_is_repointed(tmp_path):
    root = _repo(tmp_path)
    link, rel = plan_claude_shim(root)
    link.symlink_to(os.path.join("..", "SOMETHING_ELSE.md"))
    assert install_claude_shim(link, rel, apply=True) == "linked"
    assert os.readlink(link) == rel


# ---------------------------------------------------------------------------
# Windows copy fallback
# ---------------------------------------------------------------------------

def _no_symlinks(monkeypatch):
    def boom(self, *a, **kw):
        raise OSError("symlinks unavailable (simulated Windows)")
    monkeypatch.setattr(Path, "symlink_to", boom)


def test_copy_fallback_carries_the_content(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    link, rel = plan_claude_shim(root)
    _no_symlinks(monkeypatch)
    assert install_claude_shim(link, rel, apply=True) == "copied"
    body = link.read_text(encoding="utf-8")
    assert "Never read grading/.deid_master.csv." in body
    assert not link.is_symlink()


def test_copy_fallback_is_marked_so_a_rerun_refreshes_it(tmp_path, monkeypatch):
    """Without the marker, the next run would read our own copy as a
    hand-written CLAUDE.md and refuse to ever update it again."""
    root = _repo(tmp_path)
    link, rel = plan_claude_shim(root)
    _no_symlinks(monkeypatch)
    install_claude_shim(link, rel, apply=True)
    assert install_claude_shim(link, rel, apply=True) == "copied"   # refreshed, not skipped


def test_copy_fallback_refreshes_stale_content(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    link, rel = plan_claude_shim(root)
    _no_symlinks(monkeypatch)
    install_claude_shim(link, rel, apply=True)
    (root / "AGENTS.md").write_text(AGENTS + "\nNEW RULE\n", encoding="utf-8")
    install_claude_shim(link, rel, apply=True)
    assert "NEW RULE" in link.read_text(encoding="utf-8")


def test_marker_tells_a_reader_where_to_edit(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    link, rel = plan_claude_shim(root)
    _no_symlinks(monkeypatch)
    install_claude_shim(link, rel, apply=True)
    assert "edit AGENTS.md" in link.read_text(encoding="utf-8").splitlines()[0]


# ---------------------------------------------------------------------------
# gitignore — the shim rides alongside the skills lines
# ---------------------------------------------------------------------------

def test_gitignore_adds_the_shim_line(tmp_path):
    assert ensure_gitignore(tmp_path, ["grading"], apply=True) == "added"
    assert CLAUDE_SHIM in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_gitignore_shim_line_has_no_trailing_slash(tmp_path):
    """#277: a trailing slash matches DIRECTORIES ONLY, and what we create is a
    symlink — which git treats as a file. A slashed pattern matches nothing."""
    ensure_gitignore(tmp_path, ["grading"], apply=True)
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert CLAUDE_SHIM in lines
    assert f"{CLAUDE_SHIM}/" not in lines


def test_gitignore_is_idempotent(tmp_path):
    ensure_gitignore(tmp_path, ["grading"], apply=True)
    assert ensure_gitignore(tmp_path, ["grading"], apply=True) == "present"


def test_gitignore_migration_still_carries_the_shim(tmp_path):
    """Migrating off the legacy blanket ignore must not drop the new line."""
    (tmp_path / ".gitignore").write_text(".claude/skills/\n", encoding="utf-8")
    assert ensure_gitignore(tmp_path, ["grading"], apply=True) == "migrated"
    body = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert CLAUDE_SHIM in body
    assert ".claude/skills/\n" not in body


@pytest.mark.parametrize("applied", [False, True])
def test_gitignore_dry_run_writes_nothing(tmp_path, applied):
    status = ensure_gitignore(tmp_path, ["grading"], apply=applied)
    assert (tmp_path / ".gitignore").is_file() is applied
    assert status == ("added" if applied else "would-add")


# ---------------------------------------------------------------------------
# The real-git assertion (#277's lesson: patterns lie, git doesn't)
# ---------------------------------------------------------------------------

def test_git_actually_ignores_the_created_symlink(tmp_path):
    """Assert against real git on a real symlink. A pattern-only check cannot
    see the class of bug where the emitted line matches nothing it creates."""
    import subprocess
    root = _repo(tmp_path)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    link, rel = plan_claude_shim(root)
    install_claude_shim(link, rel, apply=True)
    ensure_gitignore(root, ["grading"], apply=True)
    out = subprocess.run(["git", "-C", str(root), "status", "--porcelain",
                          "--untracked-files=all"],
                         capture_output=True, text=True, check=True).stdout
    assert ".claude/CLAUDE.md" not in out, f"shim not ignored by real git:\n{out}"

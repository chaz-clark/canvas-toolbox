"""Unit tests — migrate_nested_to_flat.py (v2, #317 Phase 8).

The full integrated flow (relocate → flatten → merge → finalize → rollback,
against a real toolkit clone with real files) was verified by hand against
real git and real fixtures before writing this file — the same discipline
test_cb_flatten.py itself was built with. These tests cover each pure/state-
detection function individually so a future change gets a fast, specific
failure instead of only a slow end-to-end one.
"""
import json
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import migrate_nested_to_flat as mig  # noqa: E402


def _git(d: Path, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)


def _make_nested_clone(course_root: Path, dirty: bool = False) -> Path:
    """A minimal but real git repo standing in for the vendored nested
    canvas-toolbox/ clone — just enough for relocate_nested_clone()'s own
    checks (pristine, has .git, has an origin remote)."""
    nested = course_root / mig.NESTED_DIR_NAME
    nested.mkdir(parents=True)
    (nested / "AGENTS.md").write_text("CONSTITUTION\n", encoding="utf-8")
    _git(nested, "init", "-q")
    _git(nested, "remote", "add", "origin", "https://example.invalid/canvas-toolbox.git")
    _git(nested, "add", "-A")
    _git(nested, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    if dirty:
        (nested / "AGENTS.md").write_text("EDITED\n", encoding="utf-8")
    return nested


# ---------------------------------------------------------------------------
# detect_layout
# ---------------------------------------------------------------------------

def test_detect_layout_flat(tmp_path):
    (tmp_path / mig.flat.CLONE_DIR / ".git").mkdir(parents=True)
    assert mig.detect_layout(tmp_path) == "flat"


def test_detect_layout_nested(tmp_path):
    (tmp_path / mig.NESTED_DIR_NAME / ".git").mkdir(parents=True)
    assert mig.detect_layout(tmp_path) == "nested"


def test_detect_layout_flat_wins_over_a_stray_leftover_nested_dir(tmp_path):
    """A half-finished --finalize (flat exists, nested wasn't cleaned up yet)
    must read as flat — re-migrating something already migrated would be wrong."""
    (tmp_path / mig.flat.CLONE_DIR / ".git").mkdir(parents=True)
    (tmp_path / mig.NESTED_DIR_NAME / ".git").mkdir(parents=True)
    assert mig.detect_layout(tmp_path) == "flat"


def test_detect_layout_standalone(tmp_path):
    (tmp_path / "lib" / "tools").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("x", encoding="utf-8")
    assert mig.detect_layout(tmp_path) == "standalone"


def test_detect_layout_unknown(tmp_path):
    assert mig.detect_layout(tmp_path) == "unknown"


# ---------------------------------------------------------------------------
# is_canvas_configured
# ---------------------------------------------------------------------------

def test_is_canvas_configured_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CANVAS_COURSE_ID", raising=False)
    (tmp_path / ".env").write_text("CANVAS_COURSE_ID=12345\n", encoding="utf-8")
    assert mig.is_canvas_configured(tmp_path) is True


def test_is_canvas_configured_false_when_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("CANVAS_COURSE_ID", raising=False)
    assert mig.is_canvas_configured(tmp_path) is False


# ---------------------------------------------------------------------------
# plan_migration — read-only, never writes
# ---------------------------------------------------------------------------

def test_plan_migration_is_empty_for_non_nested_layouts(tmp_path):
    assert mig.plan_migration(tmp_path)["steps"] == []


def test_plan_migration_lists_steps_for_nested(tmp_path, monkeypatch):
    monkeypatch.delenv("CANVAS_COURSE_ID", raising=False)
    _make_nested_clone(tmp_path)
    plan = mig.plan_migration(tmp_path)
    assert plan["layout"] == "nested"
    assert plan["steps"]                     # non-empty
    assert not (tmp_path / mig.flat.CLONE_DIR).exists()   # never writes


# ---------------------------------------------------------------------------
# relocate_nested_clone
# ---------------------------------------------------------------------------

def test_relocate_no_nested_clone(tmp_path):
    assert mig.relocate_nested_clone(tmp_path, apply=True) == "no-nested-clone"


def test_relocate_refuses_a_dirty_clone(tmp_path):
    _make_nested_clone(tmp_path, dirty=True)
    assert mig.relocate_nested_clone(tmp_path, apply=True) == "DIRTY"
    assert not (tmp_path / mig.flat.CLONE_DIR).exists()


def test_relocate_dry_run_writes_nothing(tmp_path):
    _make_nested_clone(tmp_path)
    assert mig.relocate_nested_clone(tmp_path, apply=False) == "would-relocate"
    assert not (tmp_path / mig.flat.CLONE_DIR).exists()


def test_relocate_clones_locally_and_keeps_the_original(tmp_path):
    nested = _make_nested_clone(tmp_path)
    status = mig.relocate_nested_clone(tmp_path, apply=True)
    assert status == "relocated"
    assert nested.is_dir()                                     # original untouched
    dest = tmp_path / mig.flat.CLONE_DIR
    assert (dest / "AGENTS.md").read_text(encoding="utf-8") == "CONSTITUTION\n"
    remote = subprocess.run(["git", "-C", str(dest), "remote", "get-url", "origin"],
                            capture_output=True, text=True, check=True).stdout.strip()
    assert remote == "https://example.invalid/canvas-toolbox.git"   # repointed, not local path


def test_relocate_is_idempotent(tmp_path):
    _make_nested_clone(tmp_path)
    mig.relocate_nested_clone(tmp_path, apply=True)
    assert mig.relocate_nested_clone(tmp_path, apply=True) == "present"


# ---------------------------------------------------------------------------
# remove_stale_skill_links
# ---------------------------------------------------------------------------

def _nested_skill_symlink(course_root: Path, skill: str) -> Path:
    target_dir = course_root / mig.NESTED_DIR_NAME / ".claude" / "skills" / skill
    target_dir.mkdir(parents=True, exist_ok=True)
    link = course_root / ".claude" / "skills" / skill
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(Path("..", "..", mig.NESTED_DIR_NAME, ".claude", "skills", skill))
    return link


def test_remove_stale_skill_links_absent(tmp_path):
    results = dict(mig.remove_stale_skill_links(tmp_path, apply=True))
    assert all(status == "absent" for status in results.values())


def test_remove_stale_skill_links_removes_a_symlink(tmp_path):
    link = _nested_skill_symlink(tmp_path, "grading")
    results = dict(mig.remove_stale_skill_links(tmp_path, apply=True))
    assert results["grading"] == "removed"
    assert not link.exists() and not link.is_symlink()


def test_remove_stale_skill_links_dry_run_writes_nothing(tmp_path):
    link = _nested_skill_symlink(tmp_path, "grading")
    results = dict(mig.remove_stale_skill_links(tmp_path, apply=False))
    assert results["grading"] == "would-remove"
    assert link.is_symlink()


def test_remove_stale_skill_links_never_touches_a_course_owned_skill(tmp_path):
    """A REAL directory without the .cb_managed marker is the course's own —
    the ownership rule that holds everywhere else in this toolkit."""
    own = tmp_path / ".claude" / "skills" / "grading"
    own.mkdir(parents=True)
    (own / "SKILL.md").write_text("MINE", encoding="utf-8")
    results = dict(mig.remove_stale_skill_links(tmp_path, apply=True))
    assert results["grading"] == "course-owned"
    assert (own / "SKILL.md").read_text(encoding="utf-8") == "MINE"


def test_remove_stale_skill_links_removes_the_windows_copy_fallback(tmp_path):
    managed = tmp_path / ".claude" / "skills" / "grading"
    managed.mkdir(parents=True)
    (managed / ".cb_managed").write_text("x", encoding="utf-8")
    results = dict(mig.remove_stale_skill_links(tmp_path, apply=True))
    assert results["grading"] == "removed"
    assert not managed.exists()


# ---------------------------------------------------------------------------
# remove_stale_claude_shim
# ---------------------------------------------------------------------------

def test_remove_stale_claude_shim_absent(tmp_path):
    assert mig.remove_stale_claude_shim(tmp_path, apply=True) == "absent"


def test_remove_stale_claude_shim_removes_a_symlink(tmp_path):
    (tmp_path / "AGENTS.md").write_text("x", encoding="utf-8")
    link = tmp_path / ".claude" / "CLAUDE.md"
    link.parent.mkdir(parents=True)
    link.symlink_to(Path("..", "AGENTS.md"))
    assert mig.remove_stale_claude_shim(tmp_path, apply=True) == "removed"
    assert not link.exists() and not link.is_symlink()


def test_remove_stale_claude_shim_never_touches_a_course_owned_file(tmp_path):
    link = tmp_path / ".claude" / "CLAUDE.md"
    link.parent.mkdir(parents=True)
    link.write_text("a hand-written CLAUDE.md", encoding="utf-8")
    assert mig.remove_stale_claude_shim(tmp_path, apply=True) == "course-owned"
    assert link.is_file()


# ---------------------------------------------------------------------------
# fix_stale_guardian_hook
# ---------------------------------------------------------------------------

def _settings_with_hook(course_root: Path, command: str) -> Path:
    path = course_root / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Bash|Write|Edit|Read", "hooks": [{"type": "command", "command": command}]}
    ]}}), encoding="utf-8")
    return path


def test_fix_stale_guardian_hook_absent(tmp_path):
    assert mig.fix_stale_guardian_hook(tmp_path, apply=True) == "absent"


def test_fix_stale_guardian_hook_bad_json(tmp_path):
    path = tmp_path / ".claude" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json{{{", encoding="utf-8")
    assert mig.fix_stale_guardian_hook(tmp_path, apply=True) == "bad-json"


def test_fix_stale_guardian_hook_replaces_the_nested_path(tmp_path):
    (tmp_path / "lib" / "tools").mkdir(parents=True)
    (tmp_path / "lib" / "tools" / "grade_guardian.py").write_text("x", encoding="utf-8")
    nested_cmd = ('sh -c \'f="$CLAUDE_PROJECT_DIR/canvas-toolbox/lib/tools/grade_guardian.py"; '
                 '[ -f "$f" ] || exit 0; exec python3 "$f"\'')
    _settings_with_hook(tmp_path, nested_cmd)
    assert mig.fix_stale_guardian_hook(tmp_path, apply=True) == "fixed"
    new_settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [h["command"] for e in new_settings["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert any("canvas-toolbox/" not in c and "grade_guardian" in c for c in commands)


def test_fix_stale_guardian_hook_replaces_the_braced_nested_path(tmp_path):
    """THE BUG A REAL PILOT FOUND. `$CLAUDE_PROJECT_DIR/...` and
    `${CLAUDE_PROJECT_DIR}/...` are both valid, equivalent bash — the toolkit's
    own generator only ever writes the unbraced form, but a real course repo's
    hook used the braced one anyway. The detection regex only matched the
    unbraced form, so this fell through to "course-customized" (left alone)
    instead of being recognized as pointing at the nested path about to be
    deleted — verification then correctly failed with the hook installed but
    inert, exactly like the flat-mode bug Phase 6 fixed, on a real repo."""
    (tmp_path / "lib" / "tools").mkdir(parents=True)
    (tmp_path / "lib" / "tools" / "grade_guardian.py").write_text("x", encoding="utf-8")
    nested_cmd = 'python3 "${CLAUDE_PROJECT_DIR}/canvas-toolbox/lib/tools/grade_guardian.py"'
    _settings_with_hook(tmp_path, nested_cmd)
    assert mig.fix_stale_guardian_hook(tmp_path, apply=True) == "fixed"
    new_settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [h["command"] for e in new_settings["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert any("canvas-toolbox/" not in c and "grade_guardian" in c for c in commands)


def test_fix_stale_guardian_hook_dry_run_writes_nothing(tmp_path):
    nested_cmd = ('sh -c \'f="$CLAUDE_PROJECT_DIR/canvas-toolbox/lib/tools/grade_guardian.py"; '
                 '[ -f "$f" ] || exit 0; exec python3 "$f"\'')
    path = _settings_with_hook(tmp_path, nested_cmd)
    before = path.read_text(encoding="utf-8")
    assert mig.fix_stale_guardian_hook(tmp_path, apply=False) == "would-fix"
    assert path.read_text(encoding="utf-8") == before


def test_fix_stale_guardian_hook_leaves_an_already_flat_hook_alone(tmp_path):
    """The expected steady state — a hook already pointing at the standard
    flat path needs no fix, and must not be reported as though something is
    wrong with it."""
    from grade_guardian import hook_command
    path = _settings_with_hook(tmp_path, hook_command(toolkit_subdir=""))
    before = path.read_text(encoding="utf-8")
    assert mig.fix_stale_guardian_hook(tmp_path, apply=True) == "already-flat"
    assert path.read_text(encoding="utf-8") == before


def test_fix_stale_guardian_hook_leaves_a_course_customized_hook_alone(tmp_path):
    """A grade_guardian hook whose path is neither the stale nested one nor
    the standard flat one is a course's own customization — never rewrite
    arbitrary course configuration without an explicit reviewed plan."""
    custom_cmd = ('sh -c \'exec python3 "$CLAUDE_PROJECT_DIR/tools/'
                 'grade_guardian_custom_wrapper.py"\'')
    path = _settings_with_hook(tmp_path, custom_cmd)
    before = path.read_text(encoding="utf-8")
    assert mig.fix_stale_guardian_hook(tmp_path, apply=True) == "course-customized"
    assert path.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# finalize_migration
# ---------------------------------------------------------------------------

def test_finalize_no_flat_clone(tmp_path):
    assert mig.finalize_migration(tmp_path) == "no-flat-clone"


def test_finalize_nested_already_gone(tmp_path):
    (tmp_path / mig.flat.CLONE_DIR).mkdir()
    assert mig.finalize_migration(tmp_path) == "nested-already-gone"


def test_finalize_refuses_when_verification_fails(tmp_path):
    """No skills/, no grade_guardian.py, no AGENTS.md — verification_report()
    must fail, and finalize must not remove anything when it does."""
    (tmp_path / mig.flat.CLONE_DIR / ".git").mkdir(parents=True)
    nested = tmp_path / mig.NESTED_DIR_NAME
    nested.mkdir()
    (tmp_path / mig.flat.CLONE_DIR / "skills" / "audit").mkdir(parents=True)
    # a required skill is declared in the clone but never flattened -> fails
    assert mig.finalize_migration(tmp_path) == "not-verified"
    assert nested.is_dir()


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------

def test_rollback_no_flat_clone(tmp_path):
    assert mig.rollback(tmp_path) == "no-flat-clone"


def test_rollback_pre_finalize_removes_the_flat_clone_and_restores_agents_md(tmp_path):
    nested = _make_nested_clone(tmp_path)
    dest = tmp_path / mig.flat.CLONE_DIR
    dest.mkdir()
    (tmp_path / "AGENTS.md").write_text("FRESH", encoding="utf-8")
    (tmp_path / "AGENTS.merge.md").write_text("OLD COURSE CONTENT", encoding="utf-8")

    status = mig.rollback(tmp_path)

    assert status == "rolled-back-pre-finalize"
    assert not dest.exists()
    assert nested.is_dir()                          # never touched
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "OLD COURSE CONTENT"
    assert not (tmp_path / "AGENTS.merge.md").exists()


def test_rollback_post_finalize_reconstructs_the_nested_clone(tmp_path):
    """canvas-toolbox/ is gone (finalized already ran) — rollback must clone
    it back out from .canvas-toolbox/'s own history, and must NOT remove the
    now-only-copy flattened files."""
    nested = _make_nested_clone(tmp_path)
    dest = tmp_path / mig.flat.CLONE_DIR
    subprocess.run(["git", "clone", "-q", str(nested), str(dest)], check=True)
    import shutil
    shutil.rmtree(nested)                            # simulate finalize having run
    (tmp_path / "lib" / "tools").mkdir(parents=True)
    (tmp_path / "lib" / "tools" / "flattened_marker.py").write_text("x", encoding="utf-8")

    status = mig.rollback(tmp_path)

    assert status == "rolled-back-post-finalize"
    assert (tmp_path / mig.NESTED_DIR_NAME / ".git").is_dir()
    assert (tmp_path / "lib" / "tools" / "flattened_marker.py").is_file()  # not removed

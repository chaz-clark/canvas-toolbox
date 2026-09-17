"""Tier 1 unit tests — cb_flatten (proposal Phases 1-2).

Source: lib/tools/cb_flatten.py

The properties that make a flatten safe, and what breaks if each is missing:

  ownership      only paths in the clone's `git ls-files` are written. Anything
                 else at the course root is the course's and is never touched.
  deletion       a file removed upstream is removed at the course root, or a
                 stale tool lingers there and an agent can still run it.
  hybrids        AGENTS.md and .gitignore are part-course, part-toolkit. A blind
                 copy destroys the course's half.
  pristine clone a dirty clone means a pull can conflict — refuse, don't guess.
  exact ignores  never a directory blanket (#271 hid course-owned files that way).

Real git, real files. A pattern-only assertion cannot see the class of bug #277 was.
"""
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import cb_flatten as cf  # noqa: E402
from cb_flatten import (  # noqa: E402
    GI_END,
    GI_START,
    HYBRID,
    apply_sync,
    clone_is_pristine,
    ensure_clone,
    manifest,
    plan_sync,
    render_gitignore_block,
    report_pyproject_deps,
    splice_gitignore,
)


def _git(d: Path, *a): subprocess.run(["git", "-C", str(d), *a], check=True,
                                      capture_output=True)


def _toolkit(tmp_path: Path, files: dict[str, str]) -> Path:
    """A tiny stand-in for the toolkit repo, as a real git clone source."""
    src = tmp_path / "upstream"
    src.mkdir()
    _git(src, "init", "-q")
    for rel, body in files.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    _git(src, "add", "-A")
    _git(src, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return src


# ---------------------------------------------------------------------------
# plan_sync — pure
# ---------------------------------------------------------------------------

def test_copies_everything_in_the_new_manifest():
    to_copy, _ = plan_sync(set(), {"lib/a.py", "bin/b"})
    assert to_copy == ["bin/b", "lib/a.py"]          # sorted → stable dry-run diff


def test_deletes_what_upstream_removed():
    """old - new. Without this a tool deleted upstream stays at the course root
    and an agent can still find and run it."""
    _, to_delete = plan_sync({"lib/old.py", "lib/a.py"}, {"lib/a.py"})
    assert to_delete == ["lib/old.py"]


def test_hybrid_files_are_never_copied_or_deleted():
    to_copy, to_delete = plan_sync({"AGENTS.md", ".gitignore"},
                                   {"AGENTS.md", ".gitignore", "lib/a.py"})
    assert to_copy == ["lib/a.py"]
    assert to_delete == []


def test_hybrid_set_is_exactly_the_two_part_course_files():
    assert HYBRID == {"AGENTS.md", ".gitignore", "pyproject.toml", "uv.lock"}


def test_unchanged_manifest_deletes_nothing():
    _, to_delete = plan_sync({"lib/a.py"}, {"lib/a.py"})
    assert to_delete == []


# ---------------------------------------------------------------------------
# gitignore block
# ---------------------------------------------------------------------------

def test_block_lists_exact_paths_not_a_directory_blanket():
    """#271: a blanket `.claude/skills/` also hid the course's OWN skills, and
    `git add -A` silently skipped them. Exact paths keep the ignore set equal to
    what this tool writes."""
    block = render_gitignore_block(["lib/a.py", "lib/tools/b.py"])
    assert "/lib/a.py" in block and "/lib/tools/b.py" in block
    assert "/lib/\n" not in block and "lib/*" not in block


def test_splice_preserves_course_lines_around_the_block():
    existing = "# course\n.env\ncourse/\n"
    out = splice_gitignore(existing, render_gitignore_block(["lib/a.py"]))
    assert ".env" in out and "course/" in out and "/lib/a.py" in out


def test_splice_replaces_in_place_on_rerun():
    first = splice_gitignore(".env\n", render_gitignore_block(["lib/old.py"]))
    second = splice_gitignore(first, render_gitignore_block(["lib/new.py"]))
    assert second.count(GI_START) == 1 and second.count(GI_END) == 1
    assert "/lib/old.py" not in second and "/lib/new.py" in second
    assert ".env" in second                      # course content survived


def test_splice_is_idempotent():
    block = render_gitignore_block(["lib/a.py"])
    once = splice_gitignore(".env\n", block)
    assert splice_gitignore(once, block) == once


# ---------------------------------------------------------------------------
# manifest + pristine clone
# ---------------------------------------------------------------------------

def test_manifest_is_the_clones_tracked_files(tmp_path):
    src = _toolkit(tmp_path, {"lib/a.py": "x", "bin/b": "y"})
    assert manifest(src) == {"lib/a.py", "bin/b"}


def test_manifest_ignores_untracked_noise(tmp_path):
    """An untracked file in the clone is not toolkit-owned and must not be
    flattened out to the course root."""
    src = _toolkit(tmp_path, {"lib/a.py": "x"})
    (src / "scratch.txt").write_text("junk", encoding="utf-8")
    assert manifest(src) == {"lib/a.py"}


def test_clone_is_pristine_detects_an_edit(tmp_path):
    src = _toolkit(tmp_path, {"lib/a.py": "x"})
    assert clone_is_pristine(src) is True
    (src / "lib" / "a.py").write_text("edited", encoding="utf-8")
    assert clone_is_pristine(src) is False


def test_ensure_clone_reports_dirty_rather_than_guessing(tmp_path):
    """A dirty clone means a pull can conflict. Refuse loudly — the whole
    no-conflict guarantee rests on the clone never being edited."""
    root = tmp_path / "course"
    root.mkdir()
    src = _toolkit(tmp_path, {"lib/a.py": "x"})
    subprocess.run(["git", "clone", "-q", str(src), str(root / cf.CLONE_DIR)],
                   check=True, capture_output=True)
    (root / cf.CLONE_DIR / "lib" / "a.py").write_text("edited", encoding="utf-8")
    assert ensure_clone(root, str(src), apply=False) == "DIRTY"


def test_ensure_clone_creates_then_reports_present(tmp_path):
    root = tmp_path / "course"
    root.mkdir()
    src = _toolkit(tmp_path, {"lib/a.py": "x"})
    assert ensure_clone(root, str(src), apply=False) == "would-clone"
    assert not (root / cf.CLONE_DIR).exists()
    assert ensure_clone(root, str(src), apply=True) == "cloned"
    assert ensure_clone(root, str(src), apply=True) == "present"


# ---------------------------------------------------------------------------
# apply_sync
# ---------------------------------------------------------------------------

def test_apply_copies_into_the_course_root(tmp_path):
    src = _toolkit(tmp_path, {"lib/tools/a.py": "print(1)"})
    root = tmp_path / "course"; root.mkdir()
    apply_sync(src, root, ["lib/tools/a.py"], [], apply=True)
    assert (root / "lib" / "tools" / "a.py").read_text(encoding="utf-8") == "print(1)"


def test_apply_dry_run_writes_nothing(tmp_path):
    src = _toolkit(tmp_path, {"lib/a.py": "x"})
    root = tmp_path / "course"; root.mkdir()
    counts = apply_sync(src, root, ["lib/a.py"], [], apply=False)
    assert counts["copied"] == 1
    assert not (root / "lib").exists()


def test_apply_removes_upstream_deletions_and_prunes_the_empty_dir(tmp_path):
    """An empty `lib/tools/` left behind reads as 'the toolkit is installed'."""
    src = _toolkit(tmp_path, {"lib/a.py": "x"})
    root = tmp_path / "course"; root.mkdir()
    stale = root / "lib" / "tools" / "gone.py"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")
    apply_sync(src, root, [], ["lib/tools/gone.py"], apply=True)
    assert not stale.exists()
    assert not (root / "lib" / "tools").exists()


def test_apply_never_touches_a_course_owned_path(tmp_path):
    """The ownership boundary: not in the manifest → not ours → untouched."""
    src = _toolkit(tmp_path, {"lib/a.py": "x"})
    root = tmp_path / "course"; root.mkdir()
    (root / "course").mkdir()
    (root / "course" / "syllabus.md").write_text("MINE", encoding="utf-8")
    (root / ".env").write_text("CANVAS_API_TOKEN=secret", encoding="utf-8")
    to_copy, to_delete = plan_sync(set(), manifest(src))
    apply_sync(src, root, to_copy, to_delete, apply=True)
    assert (root / "course" / "syllabus.md").read_text(encoding="utf-8") == "MINE"
    assert "secret" in (root / ".env").read_text(encoding="utf-8")


def test_apply_does_not_clobber_a_course_agents_md(tmp_path):
    """AGENTS.md is hybrid — the course's HERMES learning lives in it."""
    src = _toolkit(tmp_path, {"AGENTS.md": "TOOLKIT", "lib/a.py": "x"})
    root = tmp_path / "course"; root.mkdir()
    (root / "AGENTS.md").write_text("COURSE LEARNING", encoding="utf-8")
    to_copy, to_delete = plan_sync(set(), manifest(src))
    apply_sync(src, root, to_copy, to_delete, apply=True)
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "COURSE LEARNING"


# ---------------------------------------------------------------------------
# End to end, against real git — including a real upstream deletion
# ---------------------------------------------------------------------------

def test_full_cycle_clone_flatten_upstream_delete_resync(tmp_path):
    src = _toolkit(tmp_path, {"lib/keep.py": "k", "lib/drop.py": "d"})
    root = tmp_path / "course"; root.mkdir()
    subprocess.run(["git", "clone", "-q", str(src), str(root / cf.CLONE_DIR)],
                   check=True, capture_output=True)
    clone = root / cf.CLONE_DIR

    old = manifest(clone)
    to_copy, to_delete = plan_sync(set(), old)
    apply_sync(clone, root, to_copy, to_delete, apply=True)
    assert (root / "lib" / "drop.py").is_file()

    # upstream removes a file, clone pulls it
    (src / "lib" / "drop.py").unlink()
    _git(src, "add", "-A")
    _git(src, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "drop")
    before = manifest(clone)
    _git(clone, "pull", "-q", "--ff-only")
    after = manifest(clone)

    to_copy, to_delete = plan_sync(before, after)
    assert to_delete == ["lib/drop.py"]
    apply_sync(clone, root, to_copy, to_delete, apply=True)
    assert not (root / "lib" / "drop.py").exists()
    assert (root / "lib" / "keep.py").is_file()


def test_real_git_ignores_the_flattened_set(tmp_path):
    """Assert against real git, not the pattern text — #277's lesson."""
    src = _toolkit(tmp_path, {"lib/a.py": "x", "bin/b": "y"})
    root = tmp_path / "course"; root.mkdir()
    _git(root, "init", "-q")
    subprocess.run(["git", "clone", "-q", str(src), str(root / cf.CLONE_DIR)],
                   check=True, capture_output=True)
    clone = root / cf.CLONE_DIR
    to_copy, _ = plan_sync(set(), manifest(clone))
    apply_sync(clone, root, to_copy, [], apply=True)
    (root / ".gitignore").write_text(
        splice_gitignore(f"/{cf.CLONE_DIR}/\n", render_gitignore_block(to_copy)),
        encoding="utf-8")
    (root / "syllabus.md").write_text("course-owned", encoding="utf-8")

    out = subprocess.run(["git", "-C", str(root), "status", "--porcelain",
                          "--untracked-files=all"],
                         capture_output=True, text=True, check=True).stdout
    assert "lib/a.py" not in out and "bin/b" not in out   # toolkit ignored
    assert "syllabus.md" in out                           # course file still visible


@pytest.mark.parametrize("hybrid", sorted(HYBRID))
def test_hybrid_files_stay_out_of_the_ignore_block(hybrid):
    """The course's own AGENTS.md / .gitignore must remain git-visible."""
    to_copy, _ = plan_sync(set(), {"lib/a.py", *HYBRID})
    assert hybrid not in render_gitignore_block(to_copy)


# ---------------------------------------------------------------------------
# The "before" side of deletion tracking — found by a real smoke test
# ---------------------------------------------------------------------------

def test_parse_block_round_trips_the_manifest():
    block = render_gitignore_block(["lib/a.py", "bin/b"])
    assert cf.parse_gitignore_block(splice_gitignore("", block)) == {"lib/a.py", "bin/b"}


def test_parse_block_skips_runtime_patterns():
    """__pycache__/ and friends are PATTERNS, not manifest paths — they must not
    come back as files to delete."""
    parsed = cf.parse_gitignore_block(
        splice_gitignore("", render_gitignore_block(["lib/a.py"])))
    assert parsed == {"lib/a.py"}
    for pat in cf.RUNTIME_IGNORES:
        assert pat not in parsed


def test_parse_block_absent_is_empty_not_an_error():
    """First run: nothing flattened yet, so nothing to delete."""
    assert cf.parse_gitignore_block(".env\ncourse/\n") == set()


def test_block_carries_runtime_ignores():
    """The flattened toolkit generates __pycache__ when it runs. The toolkit's
    own .gitignore covers that but is hybrid and never flattened, so the course
    would otherwise see pyc churn in `git status`."""
    block = render_gitignore_block(["lib/a.py"])
    for pat in cf.RUNTIME_IGNORES:
        assert pat in block


def test_deletion_is_detected_without_a_pull_in_the_same_run(tmp_path):
    """THE BUG A 381-FILE SMOKE TEST FOUND. Reading both manifests off the clone
    only works if this tool's own --pull is the only way the clone ever changes.
    It isn't — someone pulls by hand, or a sync dies mid-way — and then the
    'before' is gone, the diff is empty, and a file deleted upstream survives at
    the course root forever. The ignore block is the durable record instead."""
    src = _toolkit(tmp_path, {"lib/keep.py": "k", "lib/drop.py": "d"})
    root = tmp_path / "course"; root.mkdir()
    subprocess.run(["git", "clone", "-q", str(src), str(root / cf.CLONE_DIR)],
                   check=True, capture_output=True)
    clone = root / cf.CLONE_DIR

    # first sync
    to_copy, _ = plan_sync(set(), manifest(clone))
    apply_sync(clone, root, to_copy, [], apply=True)
    (root / ".gitignore").write_text(
        splice_gitignore("", render_gitignore_block(to_copy)), encoding="utf-8")
    assert (root / "lib" / "drop.py").is_file()

    # the clone changes by some OTHER path than our --pull
    (src / "lib" / "drop.py").unlink()
    _git(src, "add", "-A")
    _git(src, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "drop")
    _git(clone, "pull", "-q", "--ff-only")

    # "before" comes from the block, so the deletion is still visible
    old = cf.parse_gitignore_block((root / ".gitignore").read_text(encoding="utf-8"))
    to_copy, to_delete = plan_sync(old, manifest(clone))
    assert to_delete == ["lib/drop.py"]
    apply_sync(clone, root, to_copy, to_delete, apply=True)
    assert not (root / "lib" / "drop.py").exists()


def test_only_the_known_negation_escapes_the_ignore_block(tmp_path):
    """A nested .gitignore NEGATION outranks the root block — git precedence, not
    something this tool can override. scaffold/grading/.gitignore carries
    `!answer_keys/README.md`, so that one template README stays visible.

    Pinned so the count can't grow silently: a new negation slipping into a
    flattened .gitignore would start leaking toolkit files into `git status`,
    and eventually into a `git add -A`."""
    src = _toolkit(tmp_path, {
        "lib/a.py": "x",
        "scaffold/grading/.gitignore": "answer_keys/*/\n!answer_keys/README.md\n",
        "scaffold/grading/answer_keys/README.md": "convention",
    })
    root = tmp_path / "course"; root.mkdir()
    _git(root, "init", "-q")
    to_copy, _ = plan_sync(set(), manifest(src))
    apply_sync(src, root, to_copy, [], apply=True)
    (root / ".gitignore").write_text(
        splice_gitignore("", render_gitignore_block(to_copy)), encoding="utf-8")
    # the course's .gitignore is a TRACKED course file in a real repo
    _git(root, "add", ".gitignore")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "gi")

    out = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "-uall"],
                         capture_output=True, text=True, check=True).stdout
    escaped = [ln[3:] for ln in out.splitlines() if ln.startswith("??")]
    assert escaped == ["scaffold/grading/answer_keys/README.md"], (
        f"expected exactly the one known negation to escape, got: {escaped}")


# ---------------------------------------------------------------------------
# report_pyproject_deps — advisory only, never writes pyproject.toml/uv.lock
# (both HYBRID). Regression coverage for the m119-master pilot bug: the
# flatten used to copy the toolkit's own pyproject.toml wholesale, replacing
# the host repo's project identity (name/version/description) outright.
# ---------------------------------------------------------------------------

_CLONE_PYPROJECT = (
    '[project]\nname = "canvas-toolbox"\ndependencies = ["Requests>=2.0", "PyYAML>=6.0"]\n'
)


def test_report_pyproject_deps_never_writes_host_file(tmp_path):
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "pyproject.toml").write_text(_CLONE_PYPROJECT, encoding="utf-8")
    host = tmp_path / "pyproject.toml"
    host.write_text('[project]\nname = "m119-master"\nversion = "3.0.0"\n', encoding="utf-8")
    ok, msg = report_pyproject_deps(tmp_path, clone)
    assert ok
    assert host.read_text(encoding="utf-8") == '[project]\nname = "m119-master"\nversion = "3.0.0"\n'
    assert "requests" in msg and "pyyaml" in msg


def test_report_pyproject_deps_normalizes_names_and_finds_no_gap(tmp_path):
    """Case and separator differences (Requests vs requests, PyYAML vs pyyaml)
    must not read as missing dependencies."""
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "pyproject.toml").write_text(_CLONE_PYPROJECT, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "m119-master"\ndependencies = ["requests>=2.34", "pyyaml>=6.0.3"]\n',
        encoding="utf-8",
    )
    ok, msg = report_pyproject_deps(tmp_path, clone)
    assert ok
    assert "already covers" in msg


def test_report_pyproject_deps_no_host_file_yet(tmp_path):
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "pyproject.toml").write_text(_CLONE_PYPROJECT, encoding="utf-8")
    ok, msg = report_pyproject_deps(tmp_path, clone)
    assert ok
    assert "no host pyproject.toml yet" in msg
    assert not (tmp_path / "pyproject.toml").exists()

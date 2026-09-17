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
import json
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import cb_flatten as cf  # noqa: E402
from cb_flatten import (  # noqa: E402
    credentials_resolve,
    ensure_env_stub,
    DistributionError,
    GI_END,
    GI_START,
    HYBRID,
    apply_agents_md_step,
    apply_sync,
    clone_is_pristine,
    ensure_clone,
    manifest,
    plan_agents_md_merge,
    plan_sync,
    render_gitignore_block,
    report_pyproject_deps,
    resolve_distribution,
    splice_gitignore,
    verify_agents_md,
    verify_course_learning,
    verify_guardian_hook,
    verify_manifest_clean,
    verify_no_pending_collisions,
    verify_skills_present,
    verify_token_budget,
    verification_report,
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


# ---------------------------------------------------------------------------
# apply_sync — collision protection (THE BUG A REAL PILOT FOUND). A course's
# own file can share a path with something the toolkit ships (found for real:
# m119-master's knowledge/behavioral_discipline.md, its own tracked,
# hand-maintained file, silently replaced by the toolkit's same-named one).
# previously_owned is the provenance record (parsed from the gitignore block)
# that lets apply_sync tell "toolkit file being updated" from "this path is
# new here" — only the second case needs protecting.
# ---------------------------------------------------------------------------

def test_apply_backs_up_a_pre_existing_course_file_at_a_new_toolkit_path(tmp_path):
    src = _toolkit(tmp_path, {"knowledge/x.md": "toolkit version"})
    root = tmp_path / "course"; root.mkdir()
    dst = root / "knowledge" / "x.md"
    dst.parent.mkdir(parents=True)
    dst.write_text("real course content", encoding="utf-8")
    counts = apply_sync(src, root, ["knowledge/x.md"], [], apply=True,
                        previously_owned=set())
    assert counts["backed_up"] == 1
    assert counts["backed_up_paths"] == ["knowledge/x.md"]
    backup = root / "knowledge" / "x.md.pre-flatten-backup"
    assert backup.read_text(encoding="utf-8") == "real course content"
    assert dst.read_text(encoding="utf-8") == "toolkit version"


def test_apply_does_not_back_up_when_content_already_matches(tmp_path):
    """No real collision — the course happens to already have the exact
    toolkit content (e.g. a prior manual copy). Nothing to protect."""
    src = _toolkit(tmp_path, {"knowledge/x.md": "same"})
    root = tmp_path / "course"; root.mkdir()
    dst = root / "knowledge" / "x.md"
    dst.parent.mkdir(parents=True)
    dst.write_text("same", encoding="utf-8")
    counts = apply_sync(src, root, ["knowledge/x.md"], [], apply=True,
                        previously_owned=set())
    assert counts["backed_up"] == 0
    assert not (root / "knowledge" / "x.md.pre-flatten-backup").exists()


def test_apply_overwrites_without_backup_when_path_is_already_toolkit_owned(tmp_path):
    """The ordinary update case: the toolkit wrote this file last time (it's
    in previously_owned) and upstream changed it. Always overwrite — this is
    not a collision, it's an update."""
    src = _toolkit(tmp_path, {"lib/tools/a.py": "new upstream content"})
    root = tmp_path / "course"; root.mkdir()
    dst = root / "lib" / "tools" / "a.py"
    dst.parent.mkdir(parents=True)
    dst.write_text("old toolkit content", encoding="utf-8")
    counts = apply_sync(src, root, ["lib/tools/a.py"], [], apply=True,
                        previously_owned={"lib/tools/a.py"})
    assert counts["backed_up"] == 0
    assert dst.read_text(encoding="utf-8") == "new upstream content"


def test_apply_preserves_old_unconditional_overwrite_when_previously_owned_omitted(tmp_path):
    """Default (previously_owned=None) behavior is unchanged — only main()'s
    real apply path opts into collision protection, since it is the only
    caller with an actual provenance record to check against."""
    src = _toolkit(tmp_path, {"knowledge/x.md": "toolkit version"})
    root = tmp_path / "course"; root.mkdir()
    dst = root / "knowledge" / "x.md"
    dst.parent.mkdir(parents=True)
    dst.write_text("real course content", encoding="utf-8")
    counts = apply_sync(src, root, ["knowledge/x.md"], [], apply=True)
    assert counts["backed_up"] == 0
    assert dst.read_text(encoding="utf-8") == "toolkit version"


def test_apply_dry_run_reports_the_collision_without_writing(tmp_path):
    src = _toolkit(tmp_path, {"knowledge/x.md": "toolkit version"})
    root = tmp_path / "course"; root.mkdir()
    dst = root / "knowledge" / "x.md"
    dst.parent.mkdir(parents=True)
    dst.write_text("real course content", encoding="utf-8")
    counts = apply_sync(src, root, ["knowledge/x.md"], [], apply=False,
                        previously_owned=set())
    assert counts["backed_up"] == 1
    assert dst.read_text(encoding="utf-8") == "real course content"
    assert not (root / "knowledge" / "x.md.pre-flatten-backup").exists()


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


def test_hidden_clone_is_actually_gitignored(tmp_path):
    """THE BUG A REAL PILOT FOUND. This module's own header comment claims
    .canvas-toolbox/ is "gitignored", but RUNTIME_IGNORES never listed it — a
    course that ran `git add -A` after a real flatten would create a gitlink
    (mode 160000) pointing at whatever commit the clone happened to be on, and
    a fresh `git clone` of that course afterward gets an EMPTY .canvas-toolbox/
    instead of the toolkit. Assert the actual clone-dir NAME, not just that
    RUNTIME_IGNORES contains itself — a future rename of CLONE_DIR without a
    matching RUNTIME_IGNORES update must fail this."""
    block = render_gitignore_block(["lib/a.py"])
    assert f"{cf.CLONE_DIR}/" in block


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


# ---------------------------------------------------------------------------
# resolve_distribution — v2, #317 Phase 4: ownership (git ls-files) vs.
# distribution (what actually lands in a course repo) are different questions.
# ---------------------------------------------------------------------------

_DIST_MANIFEST = """\
schema_version: 1
version: "2.0.0"
packages: [course-design]
entries:
  - path: lib/tools
    kind: tree
    install: copy
  - path: pyproject.toml
    kind: file
    install: copy
"""


def test_resolve_distribution_absent_is_the_legacy_full_manifest(tmp_path):
    """THE MIGRATION CASE. A clone at a commit before Phase 4 has no
    distribution/manifest.yaml — that must not be treated as an error, or every
    course cloning an old toolkit commit would flatten nothing. Falls back to the
    full tracked-file set, reproducing the pre-Phase-4 behavior."""
    src = _toolkit(tmp_path, {"lib/tools/a.py": "x", "lib/tests/t.py": "y"})
    resolved, packages = resolve_distribution(src)
    assert resolved == manifest(src)
    assert packages == []


def test_resolve_distribution_scopes_to_declared_entries(tmp_path):
    src = _toolkit(tmp_path, {
        "lib/tools/a.py": "x",
        "lib/tools/b.py": "x",
        "lib/tests/t.py": "y",          # dev-only, NOT in any entry
        "docs/proposals/plan.md": "z",  # dev-only, NOT in any entry
        "pyproject.toml": "[project]",
        "distribution/manifest.yaml": _DIST_MANIFEST,
    })
    resolved, packages = resolve_distribution(src)
    assert resolved == {"lib/tools/a.py", "lib/tools/b.py", "pyproject.toml"}
    assert packages == ["course-design"]


def test_resolve_distribution_raises_on_malformed_yaml(tmp_path):
    src = _toolkit(tmp_path, {"distribution/manifest.yaml": "entries: [\n"})
    with pytest.raises(DistributionError):
        resolve_distribution(src)


def test_resolve_distribution_raises_on_stale_entry(tmp_path):
    """A misspelled or removed path must fail loudly, not silently ship less than
    the manifest declares."""
    src = _toolkit(tmp_path, {
        "lib/tools/a.py": "x",
        "distribution/manifest.yaml": (
            "schema_version: 1\nversion: \"2.0.0\"\npackages: []\n"
            "entries:\n  - path: lib/does-not-exist\n    kind: tree\n    install: copy\n"
        ),
    })
    with pytest.raises(DistributionError):
        resolve_distribution(src)


def test_resolve_distribution_raises_on_unknown_kind(tmp_path):
    src = _toolkit(tmp_path, {
        "lib/tools/a.py": "x",
        "distribution/manifest.yaml": (
            "schema_version: 1\nversion: \"2.0.0\"\npackages: []\n"
            "entries:\n  - path: lib/tools\n    kind: symlink\n    install: copy\n"
        ),
    })
    with pytest.raises(DistributionError):
        resolve_distribution(src)


def test_main_refuses_to_write_anything_on_a_broken_distribution_manifest(tmp_path, capsys, monkeypatch):
    """A broken manifest must leave the prior install and the clone untouched —
    never a partial flatten."""
    src = _toolkit(tmp_path, {"distribution/manifest.yaml": "entries: [\n"})
    root = tmp_path / "course"
    root.mkdir()
    subprocess.run(["git", "clone", "-q", str(src), str(root / cf.CLONE_DIR)],
                   check=True, capture_output=True)
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "argv", ["cb_flatten.py", "--apply"])
    rc = cf.main()
    assert rc != 0
    assert not (root / "lib").exists()


def test_legacy_full_manifest_migration_removes_now_excluded_paths(tmp_path):
    """THE EXPLICIT MIGRATION TEST. A course flattened under the pre-Phase-4
    "everything tracked" behavior has lib/tests/ and docs/proposals/ sitting at its
    root. The first sync against a toolkit commit that now ships a distribution
    manifest must remove exactly those newly-excluded paths and keep the narrower
    set — the same plan_sync() diff mechanism as an upstream deletion, no special
    case needed."""
    src = _toolkit(tmp_path, {
        "lib/tools/a.py": "x",
        "lib/tests/t.py": "y",
        "docs/proposals/plan.md": "z",
        "pyproject.toml": "[project]",
        "distribution/manifest.yaml": _DIST_MANIFEST,
    })
    root = tmp_path / "course"
    root.mkdir()
    # Simulate the old, fully-flattened install: everything was once tracked and
    # copied under the pre-Phase-4 "git ls-files == distribution" behavior.
    legacy_old = {"lib/tools/a.py", "lib/tests/t.py", "docs/proposals/plan.md",
                  "pyproject.toml"}
    for rel in legacy_old:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("stale", encoding="utf-8")

    new, packages = resolve_distribution(src)
    to_copy, to_delete = plan_sync(legacy_old, new)
    assert sorted(to_delete) == ["docs/proposals/plan.md", "lib/tests/t.py"]
    assert sorted(to_copy) == ["lib/tools/a.py"]
    apply_sync(src, root, to_copy, to_delete, apply=True)
    assert not (root / "lib" / "tests" / "t.py").exists()
    assert not (root / "docs" / "proposals" / "plan.md").exists()
    assert (root / "lib" / "tools" / "a.py").is_file()


# ---------------------------------------------------------------------------
# This repo's own distribution manifest
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_this_repos_distribution_excludes_developer_only_paths():
    """Distribution safety rule: developer-only tests, research sources, and
    internal proposal files are not installed unless deliberately listed."""
    resolved, packages = resolve_distribution(_REPO_ROOT)
    assert packages, "expected this repo's real distribution/manifest.yaml to be found"
    assert not any(p.startswith("lib/tests/") for p in resolved)
    assert not any(p.startswith("docs/proposals/") for p in resolved)
    assert not any(p.startswith("docs/research/") for p in resolved)
    assert not any(p.startswith(".github/") for p in resolved)


# ---------------------------------------------------------------------------
# verification_report — v2, #317 Phase 6: "the operation is not reported as
# complete if a required verification fails" needs evidence, not an assumption
# that the copy loop above succeeded.
# ---------------------------------------------------------------------------

def test_verify_agents_md_ok_when_no_course_agents_md_yet(tmp_path):
    ok, _ = verify_agents_md(tmp_path, tmp_path / "clone")
    assert ok


def test_verify_agents_md_passes_when_toolkit_half_matches(tmp_path):
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "AGENTS.md").write_text("CONSTITUTION", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("CONSTITUTION", encoding="utf-8")
    ok, _ = verify_agents_md(tmp_path, clone)
    assert ok


def test_verify_agents_md_fails_when_toolkit_half_altered(tmp_path):
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "AGENTS.md").write_text("CONSTITUTION", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("ALTERED", encoding="utf-8")
    ok, msg = verify_agents_md(tmp_path, clone)
    assert not ok and "ALTERED" in msg


def test_verify_course_learning_ok_with_no_pending_merge(tmp_path):
    ok, msg = verify_course_learning(tmp_path, tmp_path / "clone")
    assert ok and "no pending merge" in msg


def test_verify_course_learning_reports_pending_but_never_fails(tmp_path):
    """The correctness gate is merge_cleanup.py's job, invoked separately once
    the merge skill finishes — this report can only ever say a merge IS pending,
    never judge whether it was done right. A pending backup right after
    apply_agents_md_step() ran is the expected, normal outcome of that step, not
    a defect of this update."""
    (tmp_path / "AGENTS.merge.md").write_text("CONSTITUTION\nCOURSE LINE\n",
                                              encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("CONSTITUTION\n", encoding="utf-8")
    ok, msg = verify_course_learning(tmp_path, tmp_path / "clone")
    assert ok and "merge pending" in msg
    assert ok


def test_verify_token_budget_flags_over_the_hard_limit(tmp_path):
    (tmp_path / "AGENTS.md").write_text("\n" * 1300, encoding="utf-8")
    ok, msg = verify_token_budget(tmp_path)
    assert not ok and "OVER AUTO-INCLUDE LIMIT" in msg


def test_verify_token_budget_passes_within_budget(tmp_path):
    (tmp_path / "AGENTS.md").write_text("line\n" * 50, encoding="utf-8")
    ok, _ = verify_token_budget(tmp_path)
    assert ok


def test_verify_skills_present_ok_when_clone_ships_none(tmp_path):
    ok, _ = verify_skills_present(tmp_path, tmp_path / "clone")
    assert ok


def test_verify_skills_present_fails_on_a_missing_skill(tmp_path):
    clone = tmp_path / "clone"
    (clone / "skills" / "audit").mkdir(parents=True)
    ok, msg = verify_skills_present(tmp_path, clone)
    assert not ok and "audit" in msg


def test_verify_skills_present_passes_when_all_resolve(tmp_path):
    clone = tmp_path / "clone"
    (clone / "skills" / "audit").mkdir(parents=True)
    course_skill = tmp_path / ".claude" / "skills" / "audit"
    course_skill.mkdir(parents=True)
    (course_skill / "SKILL.md").write_text("x", encoding="utf-8")
    ok, _ = verify_skills_present(tmp_path, clone)
    assert ok


def test_verify_guardian_hook_fails_when_absent(tmp_path):
    ok, msg = verify_guardian_hook(tmp_path)
    assert not ok and "NOT wired" in msg


def test_verify_guardian_hook_passes_when_present_and_path_resolves(tmp_path):
    from grade_guardian import hook_command
    (tmp_path / "lib" / "tools").mkdir(parents=True)
    (tmp_path / "lib" / "tools" / "grade_guardian.py").write_text("x", encoding="utf-8")
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [
        {"hooks": [{"command": hook_command(toolkit_subdir="")}]}
    ]}}), encoding="utf-8")
    ok, _ = verify_guardian_hook(tmp_path)
    assert ok


def test_verify_guardian_hook_fails_when_path_does_not_resolve(tmp_path):
    """The exact bug this check exists to catch: a hook wired for the NESTED
    layout's canvas-toolbox/ subdirectory, installed into a FLAT course that
    has no such subdirectory — present in settings.json, but inert."""
    (tmp_path / "lib" / "tools").mkdir(parents=True)
    (tmp_path / "lib" / "tools" / "grade_guardian.py").write_text("x", encoding="utf-8")
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    nested_command = (
        "sh -c 'f=\"$CLAUDE_PROJECT_DIR/canvas-toolbox/lib/tools/grade_guardian.py\"; "
        "[ -f \"$f\" ] || exit 0; exec python3 \"$f\"'"
    )
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [
        {"hooks": [{"command": nested_command}]}
    ]}}), encoding="utf-8")
    ok, msg = verify_guardian_hook(tmp_path)
    assert not ok and "inert" in msg


def test_verify_guardian_hook_passes_with_the_braced_variable_form(tmp_path):
    """THE BUG A REAL PILOT FOUND. `$CLAUDE_PROJECT_DIR/x` and
    `${CLAUDE_PROJECT_DIR}/x` are both valid, equivalent bash, but the
    detection regex only matched the unbraced form. A real course repo's hook
    used the braced one and was reported as inert even though its path
    resolved fine."""
    (tmp_path / "lib" / "tools").mkdir(parents=True)
    (tmp_path / "lib" / "tools" / "grade_guardian.py").write_text("x", encoding="utf-8")
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [
        {"hooks": [{"command": 'python3 "${CLAUDE_PROJECT_DIR}/lib/tools/grade_guardian.py"'}]}
    ]}}), encoding="utf-8")
    ok, _ = verify_guardian_hook(tmp_path)
    assert ok


def test_verify_manifest_clean_fails_on_a_surviving_orphan(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "gone.py").write_text("x", encoding="utf-8")
    ok, msg = verify_manifest_clean(tmp_path, ["lib/gone.py"])
    assert not ok and "lib/gone.py" in msg


def test_verify_manifest_clean_passes_when_all_removed(tmp_path):
    ok, _ = verify_manifest_clean(tmp_path, ["lib/gone.py"])
    assert ok


def test_verify_no_pending_collisions_passes_when_none_exist(tmp_path):
    ok, msg = verify_no_pending_collisions(tmp_path)
    assert ok and "no pending" in msg


def test_verify_no_pending_collisions_reports_but_does_not_block(tmp_path):
    """Same shape as the AGENTS.md merge-pending check: ok=True even with a
    pending backup — this reports it, it does not decide for the maintainer."""
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "x.md.pre-flatten-backup").write_text("x", encoding="utf-8")
    ok, msg = verify_no_pending_collisions(tmp_path)
    assert ok and "knowledge/x.md.pre-flatten-backup" in msg


def test_verify_no_pending_collisions_ignores_the_hidden_clone(tmp_path):
    clone_dir = tmp_path / cf.CLONE_DIR / "knowledge"
    clone_dir.mkdir(parents=True)
    (clone_dir / "x.md.pre-flatten-backup").write_text("x", encoding="utf-8")
    ok, msg = verify_no_pending_collisions(tmp_path)
    assert ok and "no pending" in msg


def test_verification_report_returns_all_seven_checks(tmp_path):
    clone = tmp_path / "clone"; clone.mkdir()
    results = verification_report(tmp_path, clone, [])
    assert len(results) == 7
    assert all(isinstance(ok, bool) and isinstance(msg, str) for ok, msg in results)


# ---------------------------------------------------------------------------
# AGENTS.md merge orchestration — v2, #317 Phase 6. THIS does backup+replace
# only (deterministic); merge_cleanup.py is the separate, mandatory correctness
# gate invoked once the merge skill (an LLM, not this function) finishes.
# ---------------------------------------------------------------------------

def test_plan_agents_md_merge_no_clone_agents_md(tmp_path):
    assert plan_agents_md_merge(tmp_path, tmp_path / "clone") == "no-clone-agents-md"


def test_plan_agents_md_merge_fresh_when_course_has_none_yet(tmp_path):
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "AGENTS.md").write_text("CONSTITUTION", encoding="utf-8")
    assert plan_agents_md_merge(tmp_path, clone) == "fresh"


def test_plan_agents_md_merge_up_to_date_when_matching(tmp_path):
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "AGENTS.md").write_text("CONSTITUTION", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("CONSTITUTION", encoding="utf-8")
    assert plan_agents_md_merge(tmp_path, clone) == "up-to-date"


def test_plan_agents_md_merge_needed_when_toolkit_half_differs(tmp_path):
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "AGENTS.md").write_text("NEW CONSTITUTION", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("OLD CONSTITUTION + course stuff",
                                        encoding="utf-8")
    assert plan_agents_md_merge(tmp_path, clone) == "merge-needed"


def test_plan_agents_md_merge_pending_when_backup_already_exists(tmp_path):
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "AGENTS.md").write_text("CONSTITUTION", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("CONSTITUTION", encoding="utf-8")
    (tmp_path / "AGENTS.merge.md").write_text("old backup", encoding="utf-8")
    assert plan_agents_md_merge(tmp_path, clone) == "merge-pending"


def test_apply_agents_md_step_dry_run_writes_nothing(tmp_path):
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "AGENTS.md").write_text("CONSTITUTION", encoding="utf-8")
    status = apply_agents_md_step(tmp_path, clone, apply=False)
    assert status == "would-fresh"
    assert not (tmp_path / "AGENTS.md").exists()


def test_apply_agents_md_step_writes_fresh_constitution(tmp_path):
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "AGENTS.md").write_text("CONSTITUTION", encoding="utf-8")
    status = apply_agents_md_step(tmp_path, clone, apply=True)
    assert status == "fresh"
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "CONSTITUTION"


def test_apply_agents_md_step_backs_up_before_overwriting(tmp_path):
    """Order matters: backup THEN overwrite. A crash between the two must never
    be able to lose the course's only copy of its own learning."""
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "AGENTS.md").write_text("NEW CONSTITUTION", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("OLD CONSTITUTION + course stuff",
                                        encoding="utf-8")
    status = apply_agents_md_step(tmp_path, clone, apply=True)
    assert status == "merge-needed"
    assert (tmp_path / "AGENTS.merge.md").read_text(encoding="utf-8") == \
        "OLD CONSTITUTION + course stuff"
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "NEW CONSTITUTION"


def test_apply_agents_md_step_never_creates_a_second_backup(tmp_path):
    clone = tmp_path / "clone"; clone.mkdir()
    (clone / "AGENTS.md").write_text("CONSTITUTION", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("CONSTITUTION", encoding="utf-8")
    (tmp_path / "AGENTS.merge.md").write_text("earlier unfinished merge",
                                              encoding="utf-8")
    status = apply_agents_md_step(tmp_path, clone, apply=True)
    assert status == "merge-pending"
    assert (tmp_path / "AGENTS.merge.md").read_text(encoding="utf-8") == \
        "earlier unfinished merge"


# ---------------------------------------------------------------------------
# credentials_resolve / ensure_env_stub — per-key merge across environment,
# this course's .env, and ~/.canvas/config. Found by a real rehearsal against
# a live sandbox: neither had unit tests before, and a per-SOURCE check (does
# ONE source have both keys?) silently misreported a real, working, split
# configuration as unresolved.
# ---------------------------------------------------------------------------

def test_credentials_resolve_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("CANVAS_API_TOKEN", "tok")
    monkeypatch.setenv("CANVAS_BASE_URL", "x.instructure.com")
    resolved, where = credentials_resolve(tmp_path)
    assert resolved and where == "environment"


def test_credentials_resolve_from_env_file_alone(tmp_path, monkeypatch):
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    monkeypatch.delenv("CANVAS_BASE_URL", raising=False)
    (tmp_path / ".env").write_text(
        "CANVAS_API_TOKEN=tok\nCANVAS_BASE_URL=x.instructure.com\n", encoding="utf-8")
    resolved, where = credentials_resolve(tmp_path)
    assert resolved and where == str(tmp_path / ".env")


def test_credentials_resolve_merges_across_env_file_and_global_config(tmp_path, monkeypatch):
    """THE REAL BUG. CANVAS_BASE_URL in the course's own .env, CANVAS_API_TOKEN
    in ~/.canvas/config — a legitimate, common split (the whole point of the
    global file is holding the token once for every course) that a per-source
    check misses. A real sandbox rehearsal hit this exact configuration: the
    actual tools worked (they use _env_loader's own per-key merge), but
    ensure_env_stub() reported "blank, fill them in" on a working setup."""
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    monkeypatch.delenv("CANVAS_BASE_URL", raising=False)
    (tmp_path / ".env").write_text("CANVAS_BASE_URL=x.instructure.com\n", encoding="utf-8")
    monkeypatch.setattr(
        cf, "_global_credential_values", lambda: ({"CANVAS_API_TOKEN": "tok"}, [])
    )
    resolved, where = credentials_resolve(tmp_path)
    assert resolved is True
    assert str(tmp_path / ".env") in where and "canvas/config" in where


def test_credentials_resolve_false_when_a_key_is_missing_everywhere(tmp_path, monkeypatch):
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    monkeypatch.delenv("CANVAS_BASE_URL", raising=False)
    (tmp_path / ".env").write_text("CANVAS_BASE_URL=x.instructure.com\n", encoding="utf-8")
    monkeypatch.setattr(cf, "_global_credential_values", lambda: ({}, []))
    resolved, _ = credentials_resolve(tmp_path)
    assert resolved is False


def test_ensure_env_stub_reports_resolved_even_with_a_partial_env_file(tmp_path, monkeypatch):
    """The actual regression: a .env that exists but only has HALF the
    required keys must not be reported as blank if the other half resolves
    from the global config."""
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    monkeypatch.delenv("CANVAS_BASE_URL", raising=False)
    (tmp_path / ".env").write_text("CANVAS_BASE_URL=x.instructure.com\n", encoding="utf-8")
    monkeypatch.setattr(
        cf, "_global_credential_values", lambda: ({"CANVAS_API_TOKEN": "tok"}, [])
    )
    status = ensure_env_stub(tmp_path, apply=True)
    assert "resolve" in status and "blank" not in status


def test_ensure_env_stub_still_reports_blank_when_truly_unresolved(tmp_path, monkeypatch):
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    monkeypatch.delenv("CANVAS_BASE_URL", raising=False)
    (tmp_path / ".env").write_text("CANVAS_COURSE_ID=1\n", encoding="utf-8")
    monkeypatch.setattr(cf, "_global_credential_values", lambda: ({}, []))
    status = ensure_env_stub(tmp_path, apply=True)
    assert "don't fully resolve" in status


def test_canvas_smoke_test_skips_when_truly_unresolved(tmp_path, monkeypatch):
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    monkeypatch.delenv("CANVAS_BASE_URL", raising=False)
    monkeypatch.setattr(cf, "_global_credential_values", lambda: ({}, []))
    ok, msg = cf.canvas_smoke_test(tmp_path)
    assert ok is True and "not set" in msg


def test_canvas_smoke_test_finds_a_token_split_across_env_file_and_global_config(
    tmp_path, monkeypatch
):
    """The exact bug: canvas_smoke_test() used to check only the .env file and
    the environment, never ~/.canvas/config — a token that every other part of
    the toolkit resolved fine still reported "not set" here."""
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    monkeypatch.delenv("CANVAS_BASE_URL", raising=False)
    (tmp_path / ".env").write_text("CANVAS_BASE_URL=x.instructure.com\n", encoding="utf-8")
    monkeypatch.setattr(
        cf, "_global_credential_values", lambda: ({"CANVAS_API_TOKEN": "tok"}, [])
    )
    calls = {}
    monkeypatch.setattr(cf, "smoke_test_canvas",
                        lambda token, url: calls.update(token=token, url=url) or (True, "ok"))
    ok, _ = cf.canvas_smoke_test(tmp_path)
    assert ok is True
    assert calls == {"token": "tok", "url": "https://x.instructure.com"}


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

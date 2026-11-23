"""Tests — the course's local-only pattern file is renamed without losing a pattern (#480).

`.claude/ferpa_zone2.txt` becomes `.claude/local_only.txt`. The guardian and the
FERPA pre-push guard read the course's own patterns from it, so a rename that
drops even one pattern silently un-protects that course's student-data files.
These pin: the old name is still read, both names are read together if both
exist, and cb_update's copy keeps the exact same pattern count and keeps the
old file for clones of the course on an older toolkit.
"""
import subprocess
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from cb_update import migrate_local_only_file  # noqa: E402
from ferpa_pre_push import ensure_pre_push_hook  # noqa: E402
from grade_guardian import (_ZONE2_EXTRA_FILE, _ZONE2_LEGACY_FILE,  # noqa: E402
                            load_zone2, zone2_summary)

NEW, OLD = _ZONE2_EXTRA_FILE, _ZONE2_LEGACY_FILE
PATTERNS = "# our own name-bearing files\n_all_posts\\.md\nroster_[0-9]+\\.json\n!grading/x/RUBRIC\\.md\n"


def _git(repo, *args, **kw):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, **kw)


def _repo(tmp_path):
    bare = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-q", str(bare))
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", ".")
    _git(work, "config", "user.email", "t@t.t")
    _git(work, "config", "user.name", "T")
    _git(work, "remote", "add", "origin", str(bare))
    (work / "README.md").write_text("hi\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "init")
    return work


def _write(root, name, text=PATTERNS):
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(text, encoding="utf-8")


def test_the_new_name_is_the_glossary_word():
    assert NEW == ".claude/local_only.txt"
    assert OLD == ".claude/ferpa_zone2.txt"


def test_patterns_are_read_from_the_new_name(tmp_path):
    _write(tmp_path, NEW)
    assert zone2_summary(tmp_path)["extra"] == 2


def test_a_course_with_only_the_old_name_keeps_every_pattern(tmp_path):
    """A course that hasn't run cb_update since this release is still covered."""
    _write(tmp_path, OLD)
    s = zone2_summary(tmp_path)
    assert (s["extra"], s["exempt"]) == (2, 1)


def test_both_names_are_read_together_never_one_dropped(tmp_path):
    _write(tmp_path, NEW, "_all_posts\\.md\n")
    _write(tmp_path, OLD, "_all_posts\\.md\nroster_[0-9]+\\.json\n")
    entries, _ = load_zone2(tmp_path)
    extra = [p for p, _ in entries if p in ("_all_posts\\.md", "roster_[0-9]+\\.json")]
    assert extra == ["_all_posts\\.md", "roster_[0-9]+\\.json"]   # union, no duplicate


def test_migrate_copies_keeps_the_old_file_and_the_exact_pattern_count(tmp_path):
    """Copy, not move: a clone of this course on an older toolkit reads only the
    old name, so the old file has to stay for it."""
    _write(tmp_path, OLD)
    before = zone2_summary(tmp_path)
    assert migrate_local_only_file(tmp_path, apply=False) == "would-copy"
    assert not (tmp_path / NEW).exists()
    assert migrate_local_only_file(tmp_path, apply=True) == "copied"
    assert (tmp_path / NEW).read_text(encoding="utf-8") == PATTERNS
    assert (tmp_path / OLD).read_text(encoding="utf-8") == PATTERNS
    after = zone2_summary(tmp_path)
    assert (after["extra"], after["exempt"]) == (before["extra"], before["exempt"])
    assert after["sources"] == [NEW, OLD]
    assert migrate_local_only_file(tmp_path, apply=True) == "current"


def test_an_older_toolkit_still_sees_every_pattern_after_the_copy(tmp_path):
    """What an older toolkit reads: the old file alone."""
    _write(tmp_path, OLD)
    migrate_local_only_file(tmp_path, apply=True)
    assert (tmp_path / OLD).read_text(encoding="utf-8") == PATTERNS


def test_migrate_leaves_two_different_files_alone(tmp_path):
    _write(tmp_path, NEW, "a\n")
    _write(tmp_path, OLD, "b\n")
    assert migrate_local_only_file(tmp_path, apply=True) == "both-exist"
    assert (tmp_path / NEW).read_text(encoding="utf-8") == "a\n"
    assert (tmp_path / OLD).read_text(encoding="utf-8") == "b\n"


def test_migrate_with_neither_file_does_nothing(tmp_path):
    assert migrate_local_only_file(tmp_path, apply=True) == "absent"
    assert not (tmp_path / NEW).exists()


def test_a_directory_at_the_new_name_is_reported_not_trusted(tmp_path):
    _write(tmp_path, OLD)
    (tmp_path / NEW).mkdir()
    assert migrate_local_only_file(tmp_path, apply=True) == "not-a-file"
    assert zone2_summary(tmp_path)["extra"] == 2          # old file still read


def test_a_failed_copy_is_a_status_not_a_crash(tmp_path, monkeypatch):
    import cb_update
    _write(tmp_path, OLD)
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(cb_update.shutil, "copyfile", boom)
    assert migrate_local_only_file(tmp_path, apply=True) == "copy-failed"
    assert zone2_summary(tmp_path)["extra"] == 2


def test_a_real_push_is_still_refused_from_the_new_file(tmp_path):
    """The point of #480: the course's own pattern still blocks a real git push."""
    repo = _repo(tmp_path)
    toolkit = repo / "canvas-toolbox" / "lib" / "tools"
    toolkit.mkdir(parents=True)
    for mod in ("ferpa_pre_push.py", "grade_guardian.py"):
        (toolkit / mod).write_text((_TOOLS_DIR / mod).read_text(encoding="utf-8"),
                                   encoding="utf-8")
    ensure_pre_push_hook(repo, "canvas-toolbox", apply=True)
    _write(repo, OLD)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "toolkit + patterns")
    assert migrate_local_only_file(repo, apply=True) == "copied"
    (repo / OLD).unlink()            # the copy alone must carry the patterns
    (repo / "roster_2026.json").write_text("{}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "rename + leak")

    r = _git(repo, "push", "origin", "HEAD:refs/heads/main")
    assert r.returncode != 0, "git push should have been refused"
    assert "PUSH BLOCKED" in (r.stdout + r.stderr)

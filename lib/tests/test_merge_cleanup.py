"""Tier 1 unit tests — merge_cleanup, the mandatory AGENTS.md merge gate.

Source: lib/tools/merge_cleanup.py

The property under test is that the gate cannot be talked out of its verdict. The
merge itself is LLM judgment; this decides whether that judgment produced something
safe to keep, and deletes the backup ONLY then. The two failures that matter most:
a paraphrased constitution (safety rules silently reworded) and dropped HERMES
learning (the course's accumulated context quietly discarded).

No network. No LLM. Pure functions plus a tmp_path round-trip.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import merge_cleanup as mc  # noqa: E402
from merge_cleanup import (  # noqa: E402
    COURSE_END,
    COURSE_MARKER,
    course_content_lines,
    split_merged,
    verify,
)

SOURCE = "# Constitution\n\n## FERPA\nNever read Zone 2.\n"


def _merged(course: str | None = None, source: str = SOURCE) -> str:
    if course is None:
        return source
    return f"{source}\n{COURSE_MARKER}\n{course}\n{COURSE_END}\n"


# ---------------------------------------------------------------------------
# split_merged
# ---------------------------------------------------------------------------

def test_split_returns_none_course_when_no_marker():
    toolkit, course = split_merged(SOURCE)
    assert toolkit == SOURCE
    assert course is None


def test_split_separates_toolkit_from_course():
    toolkit, course = split_merged(_merged("## Course\nWe grade in sprints."))
    assert toolkit.rstrip() == SOURCE.rstrip()
    assert "We grade in sprints." in course


def test_split_stops_at_end_marker():
    text = _merged("kept") + "\ntrailing junk after the block\n"
    _, course = split_merged(text)
    assert "kept" in course
    assert "trailing junk" not in course


# ---------------------------------------------------------------------------
# course_content_lines
# ---------------------------------------------------------------------------

def test_course_lines_finds_content_absent_from_source():
    backup = SOURCE + "\n## Course Context\nStudents use Databricks.\n"
    extra = course_content_lines(backup, SOURCE)
    assert any("Databricks" in ln for ln in extra)


def test_course_lines_empty_when_backup_is_just_the_constitution():
    assert course_content_lines(SOURCE, SOURCE) == []


def test_course_lines_ignores_whitespace_only_differences():
    backup = SOURCE.replace("## FERPA", "  ## FERPA  ")
    assert course_content_lines(backup, SOURCE) == []


# ---------------------------------------------------------------------------
# verify — the checks that must not be negotiable
# ---------------------------------------------------------------------------

def _ok(results):
    return all(o for o, _ in results)


def test_clean_merge_passes():
    merged = _merged("## Course Context\nSprint-based grading.")
    backup = SOURCE + "\n## Course Context\nSprint-based grading.\n"
    assert _ok(verify(merged, SOURCE, backup))


def test_paraphrased_constitution_fails():
    """The whole reason an LLM merge is acceptable is that the toolkit half is
    copied, not rewritten. If it was reworded, the gate must refuse."""
    tampered = SOURCE.replace("Never read Zone 2.", "Avoid reading Zone 2 files.")
    results = verify(_merged("## Course\nx", source=tampered), SOURCE, None)
    assert not _ok(results)
    assert any("CONSTITUTION ALTERED" in m for _, m in results)


def test_reordered_constitution_fails():
    reordered = "## FERPA\nNever read Zone 2.\n\n# Constitution\n"
    results = verify(_merged("## Course\nx", source=reordered), SOURCE, None)
    assert not _ok(results)


def test_dropped_course_learning_fails():
    """Backup carried HERMES content; merged file has no course section."""
    backup = SOURCE + "\n## Course Context\nYears of accumulated notes.\n"
    results = verify(_merged(None), SOURCE, backup)
    assert not _ok(results)
    assert any("COURSE LEARNING DROPPED" in m for _, m in results)


def test_no_course_section_is_fine_when_backup_had_none():
    """A course with no HERMES learning yet is a legitimate state, not a failure."""
    results = verify(_merged(None), SOURCE, SOURCE)
    assert _ok(results)


def test_over_hard_flag_fails():
    """Past the auto-include limit the file stops loading at session start, which
    silently undoes the merge — a failure, not a warning."""
    bloat = "\n".join(f"line {i}" for i in range(mc.HARD_FLAG_LINES + 10))
    results = verify(_merged(bloat), SOURCE, None)
    assert not _ok(results)
    assert any("OVER AUTO-INCLUDE LIMIT" in m for _, m in results)


def test_over_soft_warn_passes_with_a_notice():
    n = mc.SOFT_WARN_LINES - len(SOURCE.splitlines()) + 5
    results = verify(_merged("\n".join(f"l{i}" for i in range(n))), SOURCE, None)
    assert _ok(results)
    assert any("soft warn" in m for _, m in results)


# ---------------------------------------------------------------------------
# main — the backup is deleted only on a pass
# ---------------------------------------------------------------------------

def _repo(tmp_path: Path, merged: str, backup: str | None) -> Path:
    (tmp_path / ".canvas-toolbox").mkdir()
    (tmp_path / ".canvas-toolbox" / "AGENTS.md").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(merged, encoding="utf-8")
    if backup is not None:
        (tmp_path / "AGENTS.merge.md").write_text(backup, encoding="utf-8")
    return tmp_path


def _run(monkeypatch, root: Path, *extra: str) -> int:
    monkeypatch.setattr(sys, "argv",
                        ["merge_cleanup.py", "--course-root", str(root), *extra])
    return mc.main()


def test_backup_removed_on_pass(tmp_path, monkeypatch):
    root = _repo(tmp_path, _merged("## Course\nkeep me"), SOURCE + "\n## Course\nkeep me\n")
    assert _run(monkeypatch, root) == 0
    assert not (root / "AGENTS.merge.md").exists()


def test_backup_retained_on_fail(tmp_path, monkeypatch):
    """Nothing is lost when the gate refuses — the state stays recoverable."""
    root = _repo(tmp_path, _merged(None), SOURCE + "\n## Course\nirreplaceable\n")
    assert _run(monkeypatch, root) == 2
    assert (root / "AGENTS.merge.md").exists()
    assert "irreplaceable" in (root / "AGENTS.merge.md").read_text(encoding="utf-8")


def test_check_mode_never_deletes(tmp_path, monkeypatch):
    root = _repo(tmp_path, _merged("## Course\nkeep"), SOURCE + "\n## Course\nkeep\n")
    assert _run(monkeypatch, root, "--check") == 0
    assert (root / "AGENTS.merge.md").exists()


def test_no_backup_is_an_idempotent_noop(tmp_path, monkeypatch):
    root = _repo(tmp_path, _merged("## Course\nalready merged"), None)
    assert _run(monkeypatch, root) == 0


def test_missing_source_clone_fails_loudly(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text(SOURCE, encoding="utf-8")
    assert _run(monkeypatch, tmp_path) == 2


def test_missing_agents_md_fails_loudly(tmp_path, monkeypatch):
    (tmp_path / ".canvas-toolbox").mkdir()
    (tmp_path / ".canvas-toolbox" / "AGENTS.md").write_text(SOURCE, encoding="utf-8")
    assert _run(monkeypatch, tmp_path) == 2


# ---------------------------------------------------------------------------
# Stale copies are an OLD REVISION of the constitution, not course content
# ---------------------------------------------------------------------------

def test_old_revision_lines_are_not_mistaken_for_course_content():
    """THE BUG A REAL MIGRATION FOUND. A course repo's AGENTS.md was a stale copy
    of the constitution, and the lines flagged as 'course learning about to be
    dropped' were the identifier/placeholder-name strings the #307 FERPA scrub had
    replaced. The gate was refusing to drop exactly what that scrub existed to
    remove — and would have refused forever on every repo carrying a stale copy.

    (The real values are deliberately NOT reproduced here. Quoting them in a
    comment about the scrub would undo the scrub — which is how they got back
    into this file the first time.)"""
    stale = 'Reopened for user_id 900003 (Cid Cole)'
    backup = SOURCE + f"\n{stale}\n"
    assert course_content_lines(backup, SOURCE) == [stale]          # HEAD-only: flagged
    assert course_content_lines(backup, SOURCE, {stale}) == []      # with history: not


def test_real_course_content_survives_the_history_filter():
    """The filter must not swallow genuine HERMES learning — that is the whole
    thing the gate protects."""
    backup = SOURCE + "\nDS460 grades in sprints.\n"
    assert course_content_lines(backup, SOURCE, {"an old toolkit line"}) == [
        "DS460 grades in sprints."]


def test_verify_passes_when_the_only_extra_lines_are_historical():
    stale = "an old constitution line"
    results = verify(_merged(None), SOURCE, SOURCE + f"\n{stale}\n", {stale})
    assert all(ok for ok, _ in results)


def test_verify_still_fails_when_real_course_content_would_be_dropped():
    results = verify(_merged(None), SOURCE, SOURCE + "\nreal course note\n",
                     {"unrelated historical line"})
    assert not all(ok for ok, _ in results)
    assert any("COURSE LEARNING DROPPED" in m for _, m in results)


def test_historical_lines_is_best_effort_on_a_non_repo(tmp_path):
    """Any git failure returns empty, which falls back to the stricter HEAD-only
    comparison — erring toward refusing, never toward silently dropping."""
    assert mc.historical_lines(tmp_path) == set()

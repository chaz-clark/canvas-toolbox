"""Zone-2 exemptions (#374): a directory listed as Zone-2 must not swallow the
instructor-authored rubric/spec inside it — and an exemption must never widen the
hole past the files it names."""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import grade_guardian as gg  # noqa: E402


def _course(tmp_path, *lines):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "ferpa_zone2.txt").write_text("\n".join(lines) + "\n",
                                                          encoding="utf-8")
    return tmp_path


def _matchers(root):
    entries, _ = gg.load_zone2(root)
    return gg.compile_zone2(entries, gg.load_zone2_exempt(root))


def test_directory_pattern_still_blocks_ordinary_files(tmp_path):
    path_re, _ = _matchers(_course(tmp_path, r"grading/kc1/"))
    assert path_re.search("grading/kc1/roster_notes.md")


def test_shipped_defaults_exempt_rubric_and_spec(tmp_path):
    path_re, file_re = _matchers(_course(tmp_path, r"grading/kc1/"))
    assert not path_re.search("grading/kc1/RUBRIC.md")
    assert not path_re.search("grading/kc1/assignment_spec.md")
    assert not file_re.search("sed -n 1,20p grading/kc1/RUBRIC.md")


def test_course_bang_line_exempts_a_file(tmp_path):
    root = _course(tmp_path, r"grading/kc1/", r"!grading/.*/answer_key\.md")
    path_re, _ = _matchers(root)
    assert not path_re.search("grading/kc1/answer_key.md")


def test_exemption_never_lifts_a_builtin(tmp_path):
    """A `!` line that matches a real name-bearing file changes nothing."""
    root = _course(tmp_path, r"!.*")
    path_re, file_re = _matchers(root)
    assert path_re.search("grading/.deid_master.csv")
    assert path_re.search("grading/S1/submissions_raw/a.docx")
    assert file_re.search("cat grading/.keymap.json")


def test_exempt_file_in_same_command_does_not_shield_a_sibling(tmp_path):
    """Token-level: naming RUBRIC.md must not exempt the roster next to it."""
    _, file_re = _matchers(_course(tmp_path, r"grading/kc1/"))
    assert file_re.search("cat grading/kc1/RUBRIC.md grading/kc1/roster.csv")


def test_exemption_must_end_at_the_filename(tmp_path):
    path_re, _ = _matchers(_course(tmp_path, r"grading/kc1/"))
    assert path_re.search("grading/kc1/RUBRIC.md/roster.csv")
    assert path_re.search("grading/kc1/RUBRIC.md.bak")


def test_invalid_bang_line_is_reported_and_dropped(tmp_path):
    root = _course(tmp_path, r"grading/kc1/", r"![unclosed")
    _, invalid = gg.load_zone2(root)
    assert "![unclosed" in invalid
    assert len(gg.load_zone2_exempt(root)) == len(gg._ZONE2_EXEMPT_DEFAULT)


def test_summary_counts_exemptions_separately(tmp_path):
    root = _course(tmp_path, r"grading/kc1/", r"!grading/.*/key\.md")
    s = gg.zone2_summary(root)
    assert s["extra"] == 1 and s["exempt"] == 1
    assert s["exempt_default"] == len(gg._ZONE2_EXEMPT_DEFAULT)

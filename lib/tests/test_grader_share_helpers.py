"""Tier 1 unit tests — grader_export + grader_import pure-logic helpers.

Source:
  - lib/tools/grader_export.py
      - is_blacklisted (FERPA defense-in-depth)
      - whitelist_files_in_challenge (per-challenge file selection)
      - build_manifest (share-manifest.yml content)
      - render_readme (READ_ME_BEFORE_IMPORT.md content)
  - lib/tools/grader_import.py
      - parse_semver (version-string → tuple)
      - is_version_compatible (hard-refuse on local < export)
      - validate_manifest (shape check on loaded YAML)
      - is_blacklisted (receiving-side defense-in-depth)

These tests cover the v0.67.0 cross-faculty sharing pattern (parking-lot
idea B, refined with operator decisions 2026-06-26).
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_export import (  # noqa: E402
    is_blacklisted as export_is_blacklisted,
    whitelist_files_in_challenge,
    build_manifest,
    render_readme,
)
from grader_import import (  # noqa: E402
    parse_semver,
    is_version_compatible,
    validate_manifest,
    is_blacklisted as import_is_blacklisted,
)


# ---------------------------------------------------------------------------
# is_blacklisted — defense-in-depth FERPA + voice-preservation check
# ---------------------------------------------------------------------------

def test_blacklist_catches_submissions_dirs():
    """The FERPA-protected per-student work dirs must never ship."""
    for p in ("submissions_raw/file.docx", "submissions_deid/key.md",
              "_raw/something", "_deid/anything"):
        assert export_is_blacklisted(p) is True, f"failed for {p!r}"
        assert import_is_blacklisted(p) is True, f"failed for {p!r}"


def test_blacklist_catches_feedback_paths():
    """feedback/ is FERPA-protected per-student grading data."""
    assert export_is_blacklisted("grading/kc1/feedback/KC1-A1B2C3.md") is True
    assert import_is_blacklisted("grading/kc1/feedback/_all_comments.md") is True


def test_blacklist_catches_identity_bridges():
    """The identity-bridging files map keys to names — FERPA."""
    for p in (".keymap.json", ".fetch_log.json", ".known_names.txt"):
        assert export_is_blacklisted(p) is True
        assert import_is_blacklisted(p) is True


def test_blacklist_catches_reviewer_and_push_artifacts():
    """The reviewer-facing + push-side audit files."""
    for p in (".review.csv", ".review_did_the_review.csv",
              ".push_log.md", ".reviewed", ".calibrated"):
        assert export_is_blacklisted(p) is True


def test_blacklist_catches_per_cohort_grading_data():
    """The grading artifacts that contain per-student scores."""
    for p in ("_existing_grades.csv", "_consensus.csv", "_summary.csv",
              "_all_comments.md", "_gradebook_actuals.csv"):
        assert export_is_blacklisted(p) is True
        assert import_is_blacklisted(p) is True


def test_blacklist_catches_voice_files_per_instructor():
    """The voice-preservation contract: per-instructor voice files
    must NEVER cross the export boundary."""
    for p in ("student_feedback_voice_chaz.md",
              "student_feedback_voice_alice_smith.md",
              "agents/knowledge/student_feedback_voice_someone.md"):
        assert export_is_blacklisted(p) is True, f"failed for {p!r}"
        assert import_is_blacklisted(p) is True, f"failed for {p!r}"


def test_blacklist_catches_corpus_dirs():
    """TA-comment corpora are FERPA + voice-bias risks."""
    assert export_is_blacklisted("grading/tasks/_corpus/unit1.md") is True


def test_blacklist_catches_unique_group_memos():
    """Per-cohort group rosters — FERPA-adjacent (user_ids, not names,
    but conservative exclude to avoid cohort identity leakage)."""
    assert export_is_blacklisted("grading/kc1/UNIQUE_GROUP_MEMOS.md") is True


def test_blacklist_allows_shareable_files():
    """The whitelisted shareable files must NOT match the blacklist."""
    for p in ("grading/kc1/RUBRIC.md", "grading/kc1/assignment_spec.md",
              "grading/kc1/config.json", "grading/kc1/voice_pitfalls.md",
              "grading/kc1/README.md"):
        assert export_is_blacklisted(p) is False, f"false positive on {p!r}"
        assert import_is_blacklisted(p) is False, f"false positive on {p!r}"


def test_blacklist_is_case_insensitive():
    """Pattern match is case-insensitive — uppercase variants of
    FERPA-protected paths still match."""
    assert export_is_blacklisted("SUBMISSIONS_RAW/file.docx") is True
    assert export_is_blacklisted("Feedback/student.md") is True


# ---------------------------------------------------------------------------
# whitelist_files_in_challenge — file selection per challenge
# ---------------------------------------------------------------------------

def test_whitelist_finds_rubric_and_spec(tmp_path):
    """Standard challenge dir with RUBRIC.md + assignment_spec.md."""
    challenge = tmp_path / "kc1"
    challenge.mkdir()
    (challenge / "RUBRIC.md").write_text("# Rubric\n", encoding="utf-8")
    (challenge / "assignment_spec.md").write_text("# Spec\n", encoding="utf-8")
    files = whitelist_files_in_challenge(challenge)
    assert len(files) == 2
    names = sorted(f.name for f in files)
    assert names == ["RUBRIC.md", "assignment_spec.md"]


def test_whitelist_includes_voice_pitfalls_when_present(tmp_path):
    """The new optional voice_pitfalls.md (v0.67.0 convention) is
    included when the course author created one."""
    challenge = tmp_path / "kc1"
    challenge.mkdir()
    (challenge / "RUBRIC.md").write_text("# Rubric\n", encoding="utf-8")
    (challenge / "voice_pitfalls.md").write_text("Course pitfalls.\n", encoding="utf-8")
    files = whitelist_files_in_challenge(challenge)
    names = sorted(f.name for f in files)
    assert "voice_pitfalls.md" in names


def test_whitelist_includes_config_variants(tmp_path):
    """config.json, config.yml, config.yaml all whitelisted."""
    challenge = tmp_path / "kc1"
    challenge.mkdir()
    (challenge / "config.json").write_text("{}", encoding="utf-8")
    (challenge / "config.yaml").write_text("x: 1\n", encoding="utf-8")
    files = whitelist_files_in_challenge(challenge)
    assert len(files) == 2


def test_whitelist_excludes_per_student_feedback(tmp_path):
    """FERPA-protected files in the challenge dir are excluded."""
    challenge = tmp_path / "kc1"
    challenge.mkdir()
    (challenge / "RUBRIC.md").write_text("# Rubric\n", encoding="utf-8")
    # These shouldn't ship even if they ended up at top-level
    (challenge / ".keymap.json").write_text("{}", encoding="utf-8")
    (challenge / ".review.csv").write_text("uid\n", encoding="utf-8")
    (challenge / "_consensus.csv").write_text("k,s\n", encoding="utf-8")
    files = whitelist_files_in_challenge(challenge)
    assert len(files) == 1
    assert files[0].name == "RUBRIC.md"


def test_whitelist_excludes_subdirectories(tmp_path):
    """Only top-level files in the challenge dir — no recursion.
    Subdirectories like feedback/ + submissions_raw/ are where FERPA-
    protected data lives; never walk into them."""
    challenge = tmp_path / "kc1"
    challenge.mkdir()
    (challenge / "RUBRIC.md").write_text("# Rubric\n", encoding="utf-8")
    (challenge / "feedback").mkdir()
    (challenge / "feedback" / "KC1-AAA.md").write_text("# student feedback", encoding="utf-8")
    (challenge / "submissions_raw").mkdir()
    (challenge / "submissions_raw" / "kc1_12345.docx").write_text("...", encoding="utf-8")
    files = whitelist_files_in_challenge(challenge)
    assert len(files) == 1
    assert files[0].name == "RUBRIC.md"


def test_whitelist_returns_sorted_for_determinism(tmp_path):
    """Output is sorted by filename so ZIP contents are reproducible."""
    challenge = tmp_path / "kc1"
    challenge.mkdir()
    (challenge / "config.json").write_text("{}", encoding="utf-8")
    (challenge / "RUBRIC.md").write_text("# Rubric\n", encoding="utf-8")
    (challenge / "assignment_spec.md").write_text("# Spec\n", encoding="utf-8")
    files = whitelist_files_in_challenge(challenge)
    assert [f.name for f in files] == sorted(f.name for f in files)


def test_whitelist_empty_dir_returns_empty(tmp_path):
    """No shareable files → empty list (caller treats as error)."""
    challenge = tmp_path / "kc1"
    challenge.mkdir()
    assert whitelist_files_in_challenge(challenge) == []


def test_whitelist_nonexistent_dir_returns_empty(tmp_path):
    """Defensive: missing dir returns [] rather than raising."""
    assert whitelist_files_in_challenge(tmp_path / "does_not_exist") == []


# ---------------------------------------------------------------------------
# build_manifest — share-manifest.yml content
# ---------------------------------------------------------------------------

def test_build_manifest_includes_required_fields(tmp_path):
    """Manifest has canvas_toolbox_version + course_label + challenges + timestamps."""
    challenge = tmp_path / "kc1"
    challenge.mkdir()
    m = build_manifest(
        course_label="DS 250 — Data Science",
        challenges=[challenge],
        files_by_challenge={"kc1": ["RUBRIC.md"]},
        toolbox_version="0.67.0",
        exported_at="2026-06-26T10:00:00Z",
    )
    assert m["canvas_toolbox_version"] == "0.67.0"
    assert m["course_label"] == "DS 250 — Data Science"
    assert m["exported_at"] == "2026-06-26T10:00:00Z"
    assert len(m["challenges"]) == 1
    assert m["challenges"][0]["name"] == "kc1"
    assert m["challenges"][0]["files"] == ["RUBRIC.md"]


def test_build_manifest_names_voice_preservation_explicitly(tmp_path):
    """The manifest's exclusion list must name the voice-preservation
    contract so receivers see WHY voice files aren't shipped."""
    m = build_manifest(
        course_label="X",
        challenges=[],
        files_by_challenge={},
        toolbox_version="0.67.0",
        exported_at="2026-06-26T10:00:00Z",
    )
    excluded = " ".join(m["what_is_excluded_for_ferpa_or_voice"]).lower()
    assert "voice" in excluded
    assert "ferpa" in excluded


def test_build_manifest_challenges_sorted_by_name(tmp_path):
    """Manifest challenge order is deterministic (sorted by name)."""
    kc2 = tmp_path / "kc2"
    kc2.mkdir()
    kc1 = tmp_path / "kc1"
    kc1.mkdir()
    m = build_manifest(
        course_label="X",
        challenges=[kc2, kc1],  # passed in reverse order
        files_by_challenge={"kc1": ["RUBRIC.md"], "kc2": ["RUBRIC.md"]},
        toolbox_version="0.67.0",
        exported_at="2026-06-26T10:00:00Z",
    )
    names = [c["name"] for c in m["challenges"]]
    assert names == ["kc1", "kc2"]


# ---------------------------------------------------------------------------
# render_readme — receiver-facing instructions
# ---------------------------------------------------------------------------

def test_render_readme_names_the_course_label():
    """The receiver's first read should name the course they're getting."""
    m = {
        "course_label": "DS 250 — Data Science for Business",
        "canvas_toolbox_version": "0.67.0",
        "exported_at": "2026-06-26T10:00:00Z",
        "challenges": [{"name": "kc1", "files": []}],
    }
    out = render_readme(m)
    assert "DS 250" in out


def test_render_readme_emphasizes_voice_preservation():
    """The receiver must understand voice files are NOT included by design."""
    m = {
        "course_label": "X",
        "canvas_toolbox_version": "0.67.0",
        "exported_at": "2026-06-26T10:00:00Z",
        "challenges": [],
    }
    out = render_readme(m)
    assert "voice" in out.lower()
    assert "NOT" in out or "not" in out.lower()


def test_render_readme_includes_next_steps():
    """The README has a numbered next-steps list — receiver knows what
    to do after extraction."""
    m = {
        "course_label": "X",
        "canvas_toolbox_version": "0.67.0",
        "exported_at": "2026-06-26T10:00:00Z",
        "challenges": [{"name": "kc1", "files": ["RUBRIC.md"]}],
    }
    out = render_readme(m)
    # Has at least 4 numbered steps (we wrote 6)
    assert "1." in out
    assert "2." in out
    assert "3." in out
    assert "4." in out


# ---------------------------------------------------------------------------
# parse_semver — version string → tuple
# ---------------------------------------------------------------------------

def test_parse_semver_basic():
    """Standard semver parses to a (major, minor, patch) tuple."""
    assert parse_semver("0.67.0") == (0, 67, 0)
    assert parse_semver("1.2.3") == (1, 2, 3)
    assert parse_semver("10.20.30") == (10, 20, 30)


def test_parse_semver_strips_build_metadata():
    """The '+suffix' build metadata is stripped before parsing."""
    assert parse_semver("0.67.0+unknown") == (0, 67, 0)
    assert parse_semver("1.0.0+build.123") == (1, 0, 0)


def test_parse_semver_strips_prerelease():
    """The '-pre' prerelease annotation is stripped before parsing."""
    assert parse_semver("1.0.0-rc1") == (1, 0, 0)
    assert parse_semver("2.0.0-alpha") == (2, 0, 0)


def test_parse_semver_unparseable_returns_none():
    """Garbage / partial strings return None — caller falls back."""
    assert parse_semver("") is None
    assert parse_semver(None) is None
    assert parse_semver("not-a-version") is None
    assert parse_semver("1.0") is None
    assert parse_semver("v1.0.0") is None  # leading 'v' breaks the int cast


# ---------------------------------------------------------------------------
# is_version_compatible — hard refuse on local < export
# ---------------------------------------------------------------------------

def test_version_compat_same_version_ok():
    """Local == export → ok."""
    ok, _ = is_version_compatible("0.67.0", "0.67.0")
    assert ok is True


def test_version_compat_local_newer_ok():
    """Local > export → ok (receiver has a newer canvas-toolbox)."""
    ok, _ = is_version_compatible("0.68.0", "0.67.0")
    assert ok is True
    ok, _ = is_version_compatible("1.0.0", "0.67.0")
    assert ok is True


def test_version_compat_local_older_refused():
    """Local < export → hard refuse. The DS 250 case at v0.50.5
    importing a v0.67.0 export would hit this."""
    ok, reason = is_version_compatible("0.66.0", "0.67.0")
    assert ok is False
    assert "older" in reason.lower()
    assert "0.66.0" in reason
    assert "0.67.0" in reason


def test_version_compat_local_much_older_refused():
    """Several minor versions behind → refused."""
    ok, _ = is_version_compatible("0.50.5", "0.67.0")
    assert ok is False


def test_version_compat_unparseable_proceeds_with_warning():
    """If we can't parse either version, fall through with a warning —
    don't refuse just because the string parsing is fussy."""
    ok, reason = is_version_compatible("garbage", "0.67.0")
    assert ok is True
    assert "could not parse" in reason.lower()


# ---------------------------------------------------------------------------
# validate_manifest — shape check on loaded YAML
# ---------------------------------------------------------------------------

def test_validate_manifest_minimal_ok():
    """Manifest with all required fields validates."""
    m = {
        "canvas_toolbox_version": "0.67.0",
        "course_label": "X",
        "challenges": [{"name": "kc1", "files": ["RUBRIC.md"]}],
    }
    ok, errors = validate_manifest(m)
    assert ok is True
    assert errors == []


def test_validate_manifest_missing_required_fields():
    """Missing canvas_toolbox_version / course_label / challenges → errors."""
    m = {"challenges": []}
    ok, errors = validate_manifest(m)
    assert ok is False
    assert any("canvas_toolbox_version" in e for e in errors)
    assert any("course_label" in e for e in errors)


def test_validate_manifest_challenges_must_be_list():
    """challenges field is required to be a list."""
    m = {
        "canvas_toolbox_version": "0.67.0",
        "course_label": "X",
        "challenges": "not a list",
    }
    ok, errors = validate_manifest(m)
    assert ok is False


def test_validate_manifest_challenge_entries_must_have_name_and_files():
    """Each challenge entry needs name + files."""
    m = {
        "canvas_toolbox_version": "0.67.0",
        "course_label": "X",
        "challenges": [{"name": "kc1"}],  # missing 'files'
    }
    ok, errors = validate_manifest(m)
    assert ok is False
    assert any("files" in e for e in errors)


def test_validate_manifest_not_a_dict_fails_cleanly():
    """Defensive: garbage YAML that doesn't parse to a dict fails
    with a clear error, not a crash."""
    ok, errors = validate_manifest("string-not-dict")
    assert ok is False
    assert any("dict" in e.lower() for e in errors)
    ok, errors = validate_manifest([1, 2, 3])
    assert ok is False

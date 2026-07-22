"""Tier 1 unit tests — grader_push pure-logic helpers.

Source: lib/tools/grader_push.py
  - extract_hold_token (#72 — HOLD_<DIM> grade-hold pattern)
  - comment_has_resubmit_language (#63 — resubmit-aware availability gating)
  - collision_warnings_for_submission (#62 — pre-push collision guard)
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_push import (  # noqa: E402
    extract_hold_token,
    comment_has_resubmit_language,
    collision_warnings_for_submission,
    consensus_gate_status,
    normalize_grade,
    regression_check,
    is_yes_refused_on_review,
    truncate_comment_preview,
    validate_grade_for_grading_type,
    is_group_mirror_row,
    filter_group_mirror_rows,
    append_disclosure_tag,
    DISCLOSURE_TAG,
    find_deprecated_disclosure_tags,
    DEPRECATED_DISCLOSURE_TAGS,
    push_precheck,
    comment_for,
    resolve_feedback_file,
    assignment_posts_manually,
    post_assignment_grades,
)


# ---------------------------------------------------------------------------
# extract_hold_token — read HOLD_<DIM> from top-of-file heading
# ---------------------------------------------------------------------------

def test_extract_hold_token_finds_marker(tmp_path):
    f = tmp_path / "feedback.md"
    f.write_text(
        "# KC1-A1B2C3 · 4 · PUSH · HOLD_HOURS\n"
        "\n"
        "## Score\n"
        "4/5\n",
        encoding="utf-8",
    )
    assert extract_hold_token(str(f)) == "HOLD_HOURS"


def test_extract_hold_token_no_marker(tmp_path):
    f = tmp_path / "feedback.md"
    f.write_text(
        "# KC1-A1B2C3 · 4 · PUSH\n"
        "\n"
        "## Score\n4/5\n",
        encoding="utf-8",
    )
    assert extract_hold_token(str(f)) is None


def test_extract_hold_token_missing_file_returns_none(tmp_path):
    assert extract_hold_token(str(tmp_path / "does_not_exist.md")) is None


def test_extract_hold_token_empty_path_returns_none():
    assert extract_hold_token("") is None


def test_extract_hold_token_only_scans_first_three_headings(tmp_path):
    """The marker must be at the TOP of the file — past the 3rd heading,
    later HOLD_ tokens in the body are ignored."""
    f = tmp_path / "feedback.md"
    f.write_text(
        "# Title\n"
        "## Heading 2\n"
        "### Heading 3\n"
        "### Heading 4 · HOLD_LATE\n"  # past the 3-heading scan window
        "\nbody text · HOLD_FAKE\n",
        encoding="utf-8",
    )
    assert extract_hold_token(str(f)) is None


def test_extract_hold_token_dim_uppercase_required(tmp_path):
    """The pattern requires `HOLD_[A-Z][A-Z0-9_]*` — lowercase doesn't match."""
    f = tmp_path / "feedback.md"
    f.write_text("# KC1-A1B2C3 · 4 · PUSH · hold_hours\n", encoding="utf-8")
    assert extract_hold_token(str(f)) is None


# ---------------------------------------------------------------------------
# comment_has_resubmit_language — detect resubmit instructions in comments
# ---------------------------------------------------------------------------

def test_resubmit_language_detected_simple():
    assert comment_has_resubmit_language("Please resubmit with corrections.") is True


def test_resubmit_language_detected_case_insensitive():
    assert comment_has_resubmit_language("PLEASE RESUBMIT") is True


def test_resubmit_language_negative_cases():
    assert comment_has_resubmit_language("Good work overall.") is False
    assert comment_has_resubmit_language("") is False
    assert comment_has_resubmit_language(None) is False  # type: ignore[arg-type]


def test_resubmit_language_correct_version_phrase():
    """`\\bcorrect\\s+version\\b` — explicitly part of the resubmit vocabulary."""
    assert comment_has_resubmit_language("upload the correct version") is True


# ---------------------------------------------------------------------------
# collision_warnings_for_submission — recent-others + latest-overall
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)


def _comment(role: str, days_ago: float, text: str = "x") -> dict:
    dt = _NOW - timedelta(days=days_ago)
    return {
        "author_role": role,
        "created_at": dt.isoformat().replace("+00:00", "Z"),
        "comment": text,
    }


def test_collision_warnings_recent_others_inside_window():
    """Comments from non-self authors within window → flagged."""
    comments = [
        _comment("teacher", days_ago=2),
        _comment("ta", days_ago=1),
        _comment("self", days_ago=0.5),  # student reply — NOT flagged
    ]
    others, latest = collision_warnings_for_submission(
        comments, window_days=7, now=_NOW,
    )
    assert len(others) == 2
    roles = {c["author_role"] for c in others}
    assert roles == {"teacher", "ta"}


def test_collision_warnings_excludes_outside_window():
    """Old non-self comments are excluded; only recent ones flag."""
    comments = [
        _comment("teacher", days_ago=30),
        _comment("ta", days_ago=2),
    ]
    others, _ = collision_warnings_for_submission(
        comments, window_days=7, now=_NOW,
    )
    assert len(others) == 1
    assert others[0]["author_role"] == "ta"


def test_collision_warnings_latest_overall_includes_self():
    """latest_comment_overall returns the most-recent comment regardless
    of role — used by --skip-if-student-replied."""
    comments = [
        _comment("teacher", days_ago=5, text="initial review"),
        _comment("self", days_ago=0.5, text="student replied last"),
    ]
    others, latest = collision_warnings_for_submission(
        comments, window_days=7, now=_NOW,
    )
    assert latest is not None
    assert latest["author_role"] == "self"
    assert latest["comment"] == "student replied last"


def test_collision_warnings_empty_thread():
    others, latest = collision_warnings_for_submission(
        [], window_days=7, now=_NOW,
    )
    assert others == []
    assert latest is None


def test_collision_warnings_skips_unparseable_created_at():
    """Garbage created_at values are silently skipped, not crashed on."""
    comments = [
        {"author_role": "teacher", "created_at": "not-a-date", "comment": "x"},
        _comment("teacher", days_ago=1),
    ]
    others, latest = collision_warnings_for_submission(
        comments, window_days=7, now=_NOW,
    )
    assert len(others) == 1  # only the parseable one


# ---------------------------------------------------------------------------
# consensus_gate_status — issue #95 (3-pass consensus enforced at push seam)
# ---------------------------------------------------------------------------

def test_consensus_gate_missing(tmp_path):
    """No _consensus.csv → 'missing'; the gate refuses the push."""
    (tmp_path / "_grader1.csv").write_text("key,score\nA1,4\n", encoding="utf-8")
    status, grader_csvs = consensus_gate_status(tmp_path)
    assert status == "missing"
    assert [g.name for g in grader_csvs] == ["_grader1.csv"]


def test_consensus_gate_missing_zero_graders(tmp_path):
    """Empty fbdir → 'missing' (no consensus, no graders); refuse."""
    status, grader_csvs = consensus_gate_status(tmp_path)
    assert status == "missing"
    assert grader_csvs == []


def test_consensus_gate_ok_with_fresh_consensus(tmp_path):
    """Consensus newer than all grader passes → 'ok'."""
    (tmp_path / "_grader1.csv").write_text("k,s\nA,4\n", encoding="utf-8")
    (tmp_path / "_grader2.csv").write_text("k,s\nA,3\n", encoding="utf-8")
    (tmp_path / "_grader3.csv").write_text("k,s\nA,4\n", encoding="utf-8")
    consensus = tmp_path / "_consensus.csv"
    consensus.write_text("k,s,consensus,spread\nA,4|3|4,4,1\n", encoding="utf-8")
    # bump consensus mtime to 60s after the graders so it's unambiguously newer
    import os
    newest = max(
        (tmp_path / f"_grader{n}.csv").stat().st_mtime for n in (1, 2, 3)
    )
    os.utime(consensus, (newest + 60, newest + 60))
    status, grader_csvs = consensus_gate_status(tmp_path)
    assert status == "ok"
    assert len(grader_csvs) == 3


def test_consensus_gate_ok_with_equal_mtime(tmp_path):
    """Consensus mtime == newest grader mtime is OK (not strictly older)."""
    import os
    g = tmp_path / "_grader1.csv"
    g.write_text("k,s\nA,4\n", encoding="utf-8")
    c = tmp_path / "_consensus.csv"
    c.write_text("k,s,consensus,spread\nA,4,4,0\n", encoding="utf-8")
    mt = g.stat().st_mtime
    os.utime(c, (mt, mt))
    status, _ = consensus_gate_status(tmp_path)
    assert status == "ok"


def test_consensus_gate_stale_when_consensus_older(tmp_path):
    """A grader pass re-run AFTER consensus → 'stale'; rerun consensus."""
    import os
    consensus = tmp_path / "_consensus.csv"
    consensus.write_text("k,s,consensus,spread\nA,4,4,0\n", encoding="utf-8")
    grader = tmp_path / "_grader1.csv"
    grader.write_text("k,s\nA,4\n", encoding="utf-8")
    # bump grader mtime to 60s after the consensus to simulate re-run
    base = consensus.stat().st_mtime
    os.utime(grader, (base + 60, base + 60))
    status, grader_csvs = consensus_gate_status(tmp_path)
    assert status == "stale"
    assert [g.name for g in grader_csvs] == ["_grader1.csv"]


def test_consensus_gate_stale_uses_newest_grader_mtime(tmp_path):
    """When multiple grader passes exist, the gate must compare to the NEWEST one.
    A stale grader1 doesn't unstale a fresh consensus if grader3 is freshest."""
    import os
    consensus = tmp_path / "_consensus.csv"
    consensus.write_text("k,s,consensus,spread\nA,4,4,0\n", encoding="utf-8")
    g1 = tmp_path / "_grader1.csv"
    g1.write_text("k,s\nA,4\n", encoding="utf-8")
    g2 = tmp_path / "_grader2.csv"
    g2.write_text("k,s\nA,3\n", encoding="utf-8")
    g3 = tmp_path / "_grader3.csv"
    g3.write_text("k,s\nA,4\n", encoding="utf-8")
    base = consensus.stat().st_mtime
    # g1 + g2 older than consensus; g3 newer → overall newest is newer → stale
    os.utime(g1, (base - 120, base - 120))
    os.utime(g2, (base - 60, base - 60))
    os.utime(g3, (base + 60, base + 60))
    status, _ = consensus_gate_status(tmp_path)
    assert status == "stale"


def test_consensus_gate_ok_when_consensus_present_but_no_graders(tmp_path):
    """Edge case: consensus.csv present, no _grader*.csv files. The freshness
    check requires at least one grader file to compare against; with none,
    the gate doesn't have evidence of a stale consensus and returns 'ok'.
    (In practice this branch is unreachable from --mark-reviewed because
    consensus.py itself refuses to write _consensus.csv without grader passes;
    documenting the behavior so a future refactor doesn't accidentally
    reverse it.)"""
    (tmp_path / "_consensus.csv").write_text(
        "k,s,consensus,spread\nA,4,4,0\n", encoding="utf-8"
    )
    status, grader_csvs = consensus_gate_status(tmp_path)
    assert status == "ok"
    assert grader_csvs == []


# ---------------------------------------------------------------------------
# normalize_grade — issue #96 (grade classification for regression check)
# ---------------------------------------------------------------------------

def test_normalize_grade_empty_variants():
    """None, empty string, '-', and 'EX' (excused) all classify as 'empty'."""
    for val in (None, "", "-", "EX", "ex", "Ex"):
        cls, rank = normalize_grade(val)
        assert cls == "empty", f"expected 'empty' for {val!r}, got {cls!r}"
        assert rank is None


def test_normalize_grade_numeric():
    """int, float, numeric strings, and percent strings parse as numeric."""
    assert normalize_grade(3.5) == ("numeric", 3.5)
    assert normalize_grade(4) == ("numeric", 4.0)
    assert normalize_grade("3.75") == ("numeric", 3.75)
    assert normalize_grade("  3.0  ") == ("numeric", 3.0)
    assert normalize_grade("92%") == ("numeric", 92.0)
    assert normalize_grade("0") == ("numeric", 0.0)


def test_normalize_grade_letter_grades():
    """Standard US letter scale F → A+ with full ordering."""
    cls, rank_F = normalize_grade("F")
    assert cls == "letter"
    cls, rank_A = normalize_grade("A")
    assert cls == "letter"
    cls, rank_Aplus = normalize_grade("A+")
    assert cls == "letter"
    cls, rank_Dminus = normalize_grade("D-")
    assert cls == "letter"
    # F is lowest, A+ is highest
    assert rank_F < rank_Dminus < rank_A < rank_Aplus


def test_normalize_grade_letter_case_insensitive():
    """Letter grades are uppercase-normalized at lookup."""
    assert normalize_grade("b+") == normalize_grade("B+")
    assert normalize_grade("c-") == normalize_grade("C-")
    assert normalize_grade("a") == normalize_grade("A")


def test_normalize_grade_pass_fail():
    """'complete' / 'incomplete' classify as pass_fail; case-insensitive."""
    assert normalize_grade("complete") == ("pass_fail", 1.0)
    assert normalize_grade("incomplete") == ("pass_fail", 0.0)
    assert normalize_grade("Complete") == ("pass_fail", 1.0)
    assert normalize_grade("INCOMPLETE") == ("pass_fail", 0.0)


def test_normalize_grade_unknown_strings_dont_silently_pass():
    """Strings that aren't numeric / letter / pass-fail return 'unknown'.
    Critical: a grade we can't classify is a grade we can't direction-check —
    callers MUST halt on this rather than allow the push."""
    for val in ("Meets", "Strong", "weird custom tag", "X", "pass", "fail"):
        cls, rank = normalize_grade(val)
        assert cls == "unknown", f"expected 'unknown' for {val!r}, got {cls!r}"
        assert rank is None


def test_normalize_grade_letter_grade_ordering_full_chain():
    """Verify the full F → A+ ordering is monotonically increasing.
    If a future edit accidentally reorders or drops a step, this test
    catches it before the ordering bug reaches the regression gate."""
    chain = ["F", "D-", "D", "D+", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"]
    ranks = [normalize_grade(g)[1] for g in chain]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(chain)  # no duplicates


# ---------------------------------------------------------------------------
# regression_check — issue #96 (existing vs new grade direction)
# ---------------------------------------------------------------------------

def test_regression_check_first_fill_when_existing_is_empty():
    """No existing grade → push proceeds as first-fill."""
    assert regression_check(None, "3.5") == "first_fill"
    assert regression_check("", "3.5") == "first_fill"
    assert regression_check("-", "B+") == "first_fill"
    assert regression_check("EX", 3.5) == "first_fill"


def test_regression_check_numeric_lower_is_regression():
    """The DS 460 scenario: 3.75 → 3.5 must be flagged."""
    assert regression_check("3.75", "3.5") == "regression"
    assert regression_check(3.75, 3.5) == "regression"
    assert regression_check("4.0", "0.0") == "regression"


def test_regression_check_numeric_raise_or_equal_is_ok():
    """Raising or matching the existing score is fine."""
    assert regression_check("3.5", "3.75") == "ok"
    assert regression_check("3.5", "3.5") == "ok"
    assert regression_check(3.0, 4.0) == "ok"


def test_regression_check_letter_grade_lower_is_regression():
    """A → B+ is a regression; F → A is not."""
    assert regression_check("A", "B+") == "regression"
    assert regression_check("A-", "F") == "regression"
    assert regression_check("B+", "B") == "regression"
    assert regression_check("D+", "D-") == "regression"


def test_regression_check_letter_grade_raise_is_ok():
    """F → A, C → B+, etc."""
    assert regression_check("F", "A") == "ok"
    assert regression_check("C", "B+") == "ok"
    assert regression_check("B+", "A-") == "ok"
    assert regression_check("D-", "D") == "ok"


def test_regression_check_pass_fail_lower_is_regression():
    """complete → incomplete is the pass/fail regression case."""
    assert regression_check("complete", "incomplete") == "regression"
    assert regression_check("Complete", "Incomplete") == "regression"


def test_regression_check_pass_fail_raise_is_ok():
    """incomplete → complete is the intended uplift."""
    assert regression_check("incomplete", "complete") == "ok"
    assert regression_check("Incomplete", "Complete") == "ok"


def test_regression_check_class_mismatch_halts():
    """numeric vs letter, letter vs pass-fail, etc. — can't direction-check.
    The push gate refuses these rows and asks the operator to review."""
    assert regression_check("3.5", "B+") == "mismatch"
    assert regression_check("B+", "3.5") == "mismatch"
    assert regression_check("A", "complete") == "mismatch"
    assert regression_check("complete", "92%") == "mismatch"


def test_regression_check_unknown_class_halts():
    """If either side is an unrecognized grade string, refuse + escalate.
    A grade we can't classify is a grade we can't direction-check."""
    assert regression_check("Meets", "Developing") == "unknown"
    assert regression_check("3.5", "Strong") == "unknown"
    assert regression_check("custom-tag", "B+") == "unknown"


def test_regression_check_new_empty_is_mismatch_not_silent():
    """If the new grade is empty/None, that shouldn't reach the push loop —
    but if it does, the gate treats it as 'mismatch' so the row surfaces
    explicitly rather than getting silently passed through."""
    assert regression_check("3.5", None) == "mismatch"
    assert regression_check("3.5", "") == "mismatch"
    assert regression_check("B+", None) == "mismatch"


# ---------------------------------------------------------------------------
# is_yes_refused_on_review — issue #97 (review-gate attestation)
# ---------------------------------------------------------------------------

def test_yes_refused_when_comment_files_exist():
    """LLM-comment review path + --yes → refused. The agent flow that
    motivated #97: write _all_comments.md + per-student .md files,
    then immediately --mark-reviewed --yes to self-attest. Now blocked."""
    fake_files = [Path("/tmp/KC1-A1B2C3.md")]
    assert is_yes_refused_on_review(fake_files, yes_flag=True) is True


def test_yes_allowed_when_no_comment_files():
    """Value-only / human-graded path (no LLM comment .md files) keeps
    --yes — the human IS the grader; --yes is a script convenience there."""
    assert is_yes_refused_on_review([], yes_flag=True) is False


def test_no_yes_allowed_regardless_of_path():
    """Without --yes, the interactive 'Type reviewed' prompt runs regardless
    of which sub-path; the helper returns False both times."""
    assert is_yes_refused_on_review([Path("/tmp/x.md")], yes_flag=False) is False
    assert is_yes_refused_on_review([], yes_flag=False) is False


def test_yes_refused_does_not_depend_on_file_count():
    """One comment file is enough to count as the LLM-comment path; the
    refusal isn't gated by N >= some-threshold (a single missed review
    is still a missed review)."""
    one_file = [Path("/tmp/KC1-A1B2C3.md")]
    assert is_yes_refused_on_review(one_file, yes_flag=True) is True
    many_files = [Path(f"/tmp/KC1-XXX{i}.md") for i in range(10)]
    assert is_yes_refused_on_review(many_files, yes_flag=True) is True


# ---------------------------------------------------------------------------
# find_deprecated_disclosure_tags — issue #207 (HG-5 disclosure validation)
# ---------------------------------------------------------------------------

def _write_fb(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_canonical_tag_is_not_flagged(tmp_path):
    """The false-positive guard: a comment carrying ONLY the canonical
    DISCLOSURE_TAG must pass — otherwise every legitimate push is blocked."""
    fb = _write_fb(tmp_path, "KC1-A1B2C3.md", f"Nice work.\n\n{DISCLOSURE_TAG}\n")
    assert find_deprecated_disclosure_tags([fb]) == []


def test_emoji_tag_is_flagged(tmp_path):
    """The exact format from the RCA (emoji, underscore-wrapped) is caught."""
    fb = _write_fb(tmp_path, "KC3-D4E5F6.md",
                   "Feedback body.\n\n_🤖 AI-drafted feedback, instructor-reviewed_\n")
    violations = find_deprecated_disclosure_tags([fb])
    assert len(violations) == 1
    assert violations[0][0] == "KC3-D4E5F6.md"


def test_generated_with_claude_code_is_flagged(tmp_path):
    fb = _write_fb(tmp_path, "KC1-XYZ.md", "text\n\n🤖 Generated with Claude Code\n")
    assert [v[0] for v in find_deprecated_disclosure_tags([fb])] == ["KC1-XYZ.md"]


def test_only_offending_files_are_reported(tmp_path):
    """Mixed batch: clean files pass, stale-tagged files are named."""
    good = _write_fb(tmp_path, "KC1-GOOD.md", f"ok\n\n{DISCLOSURE_TAG}\n")
    bad = _write_fb(tmp_path, "KC1-BAD.md", "ok\n\nAI-generated feedback\n")
    reported = [v[0] for v in find_deprecated_disclosure_tags([good, bad])]
    assert reported == ["KC1-BAD.md"]


def test_untagged_file_is_not_flagged(tmp_path):
    """A file with no disclosure tag at all isn't a deprecated-tag violation —
    append_disclosure_tag adds the canonical one at send-time. This validator
    only catches WRONG tags, not MISSING ones."""
    fb = _write_fb(tmp_path, "KC1-PLAIN.md", "Just feedback, no tag.\n")
    assert find_deprecated_disclosure_tags([fb]) == []


def test_every_deprecated_tag_constant_is_detected(tmp_path):
    """Guard the constant list itself: each entry in DEPRECATED_DISCLOSURE_TAGS
    must actually trigger a violation when present (no dead/typo entries)."""
    for i, dep in enumerate(DEPRECATED_DISCLOSURE_TAGS):
        fb = _write_fb(tmp_path, f"KC1-{i}.md", f"body\n\n{dep}\n")
        assert find_deprecated_disclosure_tags([fb]), f"not detected: {dep!r}"


# ---------------------------------------------------------------------------
# resolve_feedback_file — issue #228 (challenge-relative path resolution)
# ---------------------------------------------------------------------------

def test_bug228_challenge_relative_comment_was_empty_now_found(tmp_path):
    """The #228 silent bug: run from repo root, `.review.csv` stores
    `feedback/KC2-*.md` (challenge-relative), and comment_for's bare Path()
    resolved it against CWD -> empty comment -> grades pushed with NO feedback."""
    challenge = tmp_path / "grading" / "kc2"
    (challenge / "feedback").mkdir(parents=True)
    fb = challenge / "feedback" / "KC2-TESTXYZ.md"
    fb.write_text("## Comment to student\n\nGreat work on the joins.", encoding="utf-8")

    # BUG: the raw challenge-relative path is empty from a repo-root CWD
    assert comment_for("feedback/KC2-TESTXYZ.md") == ""
    # FIX: resolved against the challenge dir, the comment loads
    resolved = resolve_feedback_file(challenge, "feedback/KC2-TESTXYZ.md")
    assert resolved == str(fb)
    assert "Great work on the joins." in comment_for(resolved)


def test_resolve_feedback_file_passthroughs(tmp_path):
    # absolute path — unchanged
    absfile = tmp_path / "x.md"
    assert resolve_feedback_file(tmp_path / "grading", str(absfile)) == str(absfile)
    # empty — unchanged
    assert resolve_feedback_file(tmp_path, "") == ""


def test_resolve_feedback_file_keeps_a_path_that_already_exists(tmp_path, monkeypatch):
    """Run from inside the challenge dir: `feedback/x.md` already resolves against
    CWD, so it passes through (no double-prefixing)."""
    (tmp_path / "feedback").mkdir()
    (tmp_path / "feedback" / "x.md").write_text("## Comment to student\n\nok", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert resolve_feedback_file(tmp_path, "feedback/x.md") == "feedback/x.md"


# ---------------------------------------------------------------------------
# push_precheck — issue #213 Fix 2 (the review gate as one testable checkpoint)
# ---------------------------------------------------------------------------

def _setup_challenge(tmp_path, *, reviewed_mtime=None, files=None):
    """Build a challenge dir. `files` maps relative path -> mtime (int)."""
    import os
    challenge = tmp_path / "kc3"
    fbdir = challenge / "feedback"
    fbdir.mkdir(parents=True)
    for rel, mtime in (files or {}).items():
        p = challenge / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
        if mtime is not None:
            os.utime(p, (mtime, mtime))
    reviewed = challenge / ".reviewed"
    if reviewed_mtime is not None:
        reviewed.write_text("reviewed\n", encoding="utf-8")
        os.utime(reviewed, (reviewed_mtime, reviewed_mtime))
    return challenge, fbdir, reviewed


def test_precheck_blocks_without_reviewed_marker():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        challenge, fbdir, reviewed = _setup_challenge(
            Path(d), files={"feedback/KC3-A.md": 100})
        blockers, warnings = push_precheck(challenge, fbdir, "KC3", reviewed, "grading/kc3")
        assert blockers and "Review required" in blockers[0]


def test_precheck_passes_when_reviewed_and_fresh():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        challenge, fbdir, reviewed = _setup_challenge(
            Path(d), reviewed_mtime=2000,
            files={"feedback/KC3-A.md": 1000, "feedback/_consensus.csv": 1000})
        blockers, warnings = push_precheck(challenge, fbdir, "KC3", reviewed, "grading/kc3")
        assert blockers == [] and warnings == []


def test_precheck_blocks_when_review_surface_edited_after_marker():
    """The mtime re-lock: a comment file touched after .reviewed refuses the push."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        challenge, fbdir, reviewed = _setup_challenge(
            Path(d), reviewed_mtime=1000,
            files={"feedback/KC3-A.md": 5000, "feedback/_consensus.csv": 500})
        blockers, warnings = push_precheck(challenge, fbdir, "KC3", reviewed, "grading/kc3")
        assert blockers and "changed since you marked reviewed" in blockers[0]


def test_precheck_warns_on_missing_consensus_but_does_not_block():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        challenge, fbdir, reviewed = _setup_challenge(
            Path(d), reviewed_mtime=2000, files={"feedback/KC3-A.md": 1000})
        blockers, warnings = push_precheck(challenge, fbdir, "KC3", reviewed, "grading/kc3")
        assert blockers == []
        assert warnings and "_consensus.csv" in warnings[0]


# ---------------------------------------------------------------------------
# truncate_comment_preview — issue #98 (inline deid'd latest comment in skip)
# ---------------------------------------------------------------------------

def test_truncate_comment_preview_short_text_unchanged():
    """Short text below the limit passes through (whitespace-trimmed)."""
    assert truncate_comment_preview("ok thanks") == "ok thanks"
    assert truncate_comment_preview("  ok thanks  ") == "ok thanks"


def test_truncate_comment_preview_collapses_newlines():
    """Multi-line replies become single-line previews. The skip surface is
    a one-line skim; a 5-line student reply with embedded \\n would
    otherwise wreck the table-like print."""
    multi = "I fixed the bug.\nUploaded the new file.\nThanks!"
    out = truncate_comment_preview(multi)
    assert "\n" not in out
    assert out == "I fixed the bug. Uploaded the new file. Thanks!"


def test_truncate_comment_preview_collapses_carriage_returns():
    """Windows-newline replies (CRLF) get both characters normalized."""
    win = "I fixed it\r\nThanks!"
    out = truncate_comment_preview(win)
    assert "\r" not in out and "\n" not in out


def test_truncate_comment_preview_truncates_past_limit():
    """Text past the limit is ellipsized to fit within `limit` chars total."""
    long = "x" * 500
    out = truncate_comment_preview(long, limit=100)
    assert len(out) == 100
    assert out.endswith("…")
    assert out.startswith("x")


def test_truncate_comment_preview_default_limit_is_240():
    """The default limit is 240 chars (per the #98 issue acceptance)."""
    long = "y" * 300
    out = truncate_comment_preview(long)
    assert len(out) == 240
    assert out.endswith("…")


def test_truncate_comment_preview_none_and_empty():
    """None and empty string both return empty string, never crash."""
    assert truncate_comment_preview(None) == ""
    assert truncate_comment_preview("") == ""
    assert truncate_comment_preview("   ") == ""


# ---------------------------------------------------------------------------
# validate_grade_for_grading_type — issue #99 (Canvas grade-type coercion guard)
# ---------------------------------------------------------------------------

def test_validate_grade_blank_is_sentinel():
    """A blank grade is the result of an operator blanking final_grade to
    'hold' a row; the recommended_score fallback is what causes the lived
    silent-coerce. Catching blanks at the validator turns the operator's
    intent (hold) into the actual behavior (hold)."""
    status, _ = validate_grade_for_grading_type("", "pass_fail")
    assert status == "sentinel"
    status, _ = validate_grade_for_grading_type("   ", "pass_fail")
    assert status == "sentinel"
    status, _ = validate_grade_for_grading_type(None, "pass_fail")
    assert status == "sentinel"


def test_validate_grade_parenthesized_is_sentinel():
    """The exact DS 250 incident: `(held)` got coerced to incomplete on
    pass_fail. Anything in parens is suspicious operator notation."""
    for s in ("(held)", "(not graded)", "(skip)", "(pending)", "(TBD)"):
        status, _ = validate_grade_for_grading_type(s, "pass_fail")
        assert status == "sentinel", f"expected sentinel for {s!r}, got {status!r}"


def test_validate_grade_sentinel_keywords_caught_unboxed():
    """Bare keywords without parens — operator might type just 'held'
    rather than '(held)'. Same intent, same trap."""
    for s in ("held", "Hold", "NOT GRADED", "skip", "n/a", "TBD"):
        status, _ = validate_grade_for_grading_type(s, "pass_fail")
        assert status == "sentinel", f"expected sentinel for {s!r}, got {status!r}"


def test_validate_grade_pass_fail_ok():
    """Valid pass_fail grades pass."""
    for s in ("complete", "Complete", "INCOMPLETE", "pass", "fail"):
        status, _ = validate_grade_for_grading_type(s, "pass_fail")
        assert status == "ok", f"expected ok for {s!r}, got {status!r}"


def test_validate_grade_pass_fail_rejects_numeric():
    """Numeric on pass_fail is the inverse of the lived case — refuse it
    too. Canvas would coerce '3.5' on pass_fail to... whatever; we
    refuse explicitly."""
    status, reason = validate_grade_for_grading_type("3.5", "pass_fail")
    assert status == "invalid"
    assert "pass_fail" in reason


def test_validate_grade_pass_fail_rejects_letter():
    """Letter grade on pass_fail is also invalid."""
    status, _ = validate_grade_for_grading_type("B+", "pass_fail")
    assert status == "invalid"


def test_validate_grade_numeric_types_ok():
    """points / percent / gpa_scale accept numeric strings."""
    for gt in ("points", "percent", "gpa_scale"):
        status, _ = validate_grade_for_grading_type("3.5", gt)
        assert status == "ok"
        status, _ = validate_grade_for_grading_type("92%", "percent")
        assert status == "ok"
        status, _ = validate_grade_for_grading_type("0", gt)
        assert status == "ok"


def test_validate_grade_numeric_types_reject_non_numeric():
    """Letter on a points/percent/gpa_scale assignment is invalid."""
    for gt in ("points", "percent", "gpa_scale"):
        status, reason = validate_grade_for_grading_type("B+", gt)
        assert status == "invalid"
        assert "numeric" in reason


def test_validate_grade_letter_grade_ok():
    """letter_grade accepts F through A+."""
    for s in ("F", "D-", "D", "D+", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"):
        status, _ = validate_grade_for_grading_type(s, "letter_grade")
        assert status == "ok", f"expected ok for {s!r}, got {status!r}"


def test_validate_grade_letter_grade_case_insensitive():
    """Lowercase letter grades work."""
    status, _ = validate_grade_for_grading_type("b+", "letter_grade")
    assert status == "ok"


def test_validate_grade_letter_grade_rejects_invalid_letter():
    """'E' isn't on the US letter scale; 'P' could be pass-fail; both
    refused as letter grades."""
    for s in ("E", "P", "G"):
        status, _ = validate_grade_for_grading_type(s, "letter_grade")
        assert status == "invalid"


def test_validate_grade_not_graded_refuses_everything():
    """grading_type=not_graded means Canvas refuses grades at the source
    of truth. Don't even try."""
    status, reason = validate_grade_for_grading_type("3.5", "not_graded")
    assert status == "not_graded"
    assert "no grades" in reason or "no posts" in reason


def test_validate_grade_unknown_type_proceeds_with_warning():
    """Unfamiliar grading_type (e.g. a future Canvas grading mode) shouldn't
    block the push — return unknown_type and let the caller proceed with
    a one-time warning."""
    status, _ = validate_grade_for_grading_type("3.5", "some_future_type")
    assert status == "unknown_type"


def test_validate_grade_empty_type_is_unknown():
    """Missing grading_type (metadata fetch failed; default empty string)
    should fall through as unknown_type — don't block the push when the
    fetch genuinely failed."""
    status, _ = validate_grade_for_grading_type("3.5", "")
    assert status == "unknown_type"
    status, _ = validate_grade_for_grading_type("3.5", None)
    assert status == "unknown_type"


def test_validate_grade_pass_fail_aliases_pass_and_fail():
    """Canvas's pass_fail nominally returns 'complete'/'incomplete' but
    a few institutions configure 'pass'/'fail' as aliases. Both accepted."""
    status, _ = validate_grade_for_grading_type("pass", "pass_fail")
    assert status == "ok"
    status, _ = validate_grade_for_grading_type("fail", "pass_fail")
    assert status == "ok"


# ---------------------------------------------------------------------------
# is_group_mirror_row / filter_group_mirror_rows — issue #100 (group push)
# ---------------------------------------------------------------------------

def _push_row(key, group_mirror_of="", final_grade=""):
    """Test helper: build a .review.csv-shaped row."""
    return {
        "key": key,
        "group_mirror_of": group_mirror_of,
        "final_grade": final_grade,
        # Other columns omitted; not exercised by these helpers.
    }


def test_is_group_mirror_row_true_when_set():
    """Non-empty group_mirror_of → True."""
    assert is_group_mirror_row(_push_row("X", group_mirror_of="X-REP")) is True


def test_is_group_mirror_row_false_when_empty():
    """Blank / missing → False."""
    assert is_group_mirror_row(_push_row("X")) is False
    assert is_group_mirror_row(_push_row("X", group_mirror_of="")) is False
    assert is_group_mirror_row({"key": "X"}) is False  # column missing entirely


def test_is_group_mirror_row_strips_whitespace():
    """Whitespace-only group_mirror_of values count as empty (no mirror)."""
    assert is_group_mirror_row(_push_row("X", group_mirror_of="   ")) is False


def test_filter_group_mirror_no_context_pass_through():
    """No group_context → all rows kept, none dropped."""
    rows = [_push_row("A"), _push_row("B", group_mirror_of="A")]
    kept, dropped = filter_group_mirror_rows(rows, None)
    assert len(kept) == 2
    assert dropped == []


def test_filter_group_mirror_individual_mode_pass_through():
    """grade_group_students_individually=True → all rows kept (Canvas
    grades each member separately; no need to drop mirrors)."""
    ctx = {"grade_group_students_individually": True}
    rows = [_push_row("A"), _push_row("B", group_mirror_of="A")]
    kept, dropped = filter_group_mirror_rows(rows, ctx)
    assert len(kept) == 2
    assert dropped == []


def test_filter_group_mirror_shared_mode_drops_mirrors():
    """Shared-grade mode + mirror row with NO final_grade override →
    mirror row dropped (Canvas distributes from the rep)."""
    ctx = {"grade_group_students_individually": False}
    rows = [
        _push_row("REP"),
        _push_row("MIRROR-1", group_mirror_of="REP"),
        _push_row("MIRROR-2", group_mirror_of="REP"),
    ]
    kept, dropped = filter_group_mirror_rows(rows, ctx)
    kept_keys = {r["key"] for r in kept}
    dropped_keys = {r["key"] for r in dropped}
    assert kept_keys == {"REP"}
    assert dropped_keys == {"MIRROR-1", "MIRROR-2"}


def test_filter_group_mirror_keeps_explicit_override():
    """Operator set final_grade on a mirrored row → kept (individual
    override beats default mirror)."""
    ctx = {"grade_group_students_individually": False}
    rows = [
        _push_row("REP"),
        _push_row("MIRROR-OVERRIDE", group_mirror_of="REP", final_grade="3.0"),
        _push_row("MIRROR-DEFAULT", group_mirror_of="REP"),
    ]
    kept, dropped = filter_group_mirror_rows(rows, ctx)
    kept_keys = {r["key"] for r in kept}
    assert kept_keys == {"REP", "MIRROR-OVERRIDE"}
    assert [r["key"] for r in dropped] == ["MIRROR-DEFAULT"]


def test_filter_group_mirror_non_group_rows_kept_in_mixed():
    """A row with no group_mirror_of (non-group OR rep) is always kept,
    regardless of group_context state."""
    ctx = {"grade_group_students_individually": False}
    rows = [_push_row("REP-OR-SOLO"), _push_row("MIRROR", group_mirror_of="REP-OR-SOLO")]
    kept, dropped = filter_group_mirror_rows(rows, ctx)
    assert "REP-OR-SOLO" in {r["key"] for r in kept}


def test_filter_group_mirror_empty_rows():
    """Empty input is safe — empty kept + empty dropped."""
    kept, dropped = filter_group_mirror_rows([], {"grade_group_students_individually": False})
    assert kept == []
    assert dropped == []


def test_filter_group_mirror_whitespace_final_grade_treated_as_blank():
    """Operator put '   ' in final_grade → treated as no override, drop."""
    ctx = {"grade_group_students_individually": False}
    rows = [_push_row("REP"), _push_row("M", group_mirror_of="REP", final_grade="   ")]
    kept, dropped = filter_group_mirror_rows(rows, ctx)
    assert {r["key"] for r in kept} == {"REP"}
    assert {r["key"] for r in dropped} == {"M"}


# ---------------------------------------------------------------------------
# append_disclosure_tag — the no-opt-out AI-disclosure tag on every comment
# ---------------------------------------------------------------------------

def test_disclosure_tag_appended_to_a_comment():
    out = append_disclosure_tag("Great work on the SQL joins.")
    assert out.endswith(DISCLOSURE_TAG)
    assert out.startswith("Great work on the SQL joins.")


def test_disclosure_tag_is_idempotent():
    """Re-pushing an already-tagged comment must not double-tag it."""
    once = append_disclosure_tag("Nice analysis.")
    assert append_disclosure_tag(once) == once
    assert once.count(DISCLOSURE_TAG) == 1


def test_disclosure_tag_not_added_to_empty_or_whitespace():
    """Never invent a tag-only comment (a grade-only push has no comment)."""
    assert append_disclosure_tag("") == ""
    assert append_disclosure_tag("   ") == "   "


def test_disclosure_tag_wording_is_honest():
    """It must say AI *drafted* (not 'assisted') + instructor *reviewed*."""
    assert DISCLOSURE_TAG == "— AI drafted, instructor reviewed"


# ---------------------------------------------------------------------------
# #199 — manual posting policy detection + release. The push payload is correct
# (verified on Canvas); a MANUAL policy enters grades but leaves posted_at null
# (hidden -> reads "needs grading"). These mock the API layer.
# ---------------------------------------------------------------------------

import grader_push as _GP  # noqa: E402


class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_assignment_posts_manually_true(monkeypatch):
    monkeypatch.setattr(_GP.requests, "get", lambda *a, **k: _Resp(200, {"post_manually": True}))
    assert assignment_posts_manually("b", "c", {}, 1) is True


def test_assignment_posts_manually_false(monkeypatch):
    monkeypatch.setattr(_GP.requests, "get", lambda *a, **k: _Resp(200, {"post_manually": False}))
    assert assignment_posts_manually("b", "c", {}, 1) is False


def test_assignment_posts_manually_defaults_false_on_error(monkeypatch):
    """A failed lookup must not warn spuriously — default to False."""
    monkeypatch.setattr(_GP.requests, "get", lambda *a, **k: _Resp(500, None, "err"))
    assert assignment_posts_manually("b", "c", {}, 1) is False


def test_post_assignment_grades_ok(monkeypatch):
    monkeypatch.setattr(_GP.requests, "post", lambda *a, **k: _Resp(
        200, {"data": {"postAssignmentGrades": {"progress": {"_id": "9", "state": "queued"},
                                                "errors": None}}}))
    ok, detail = post_assignment_grades("b", "c", {}, 1)
    assert ok is True and "queued" in detail


def test_post_assignment_grades_reports_graphql_error(monkeypatch):
    monkeypatch.setattr(_GP.requests, "post", lambda *a, **k: _Resp(
        200, {"data": {"postAssignmentGrades": {"progress": None,
                                                "errors": [{"message": "not allowed"}]}}}))
    ok, detail = post_assignment_grades("b", "c", {}, 1)
    assert ok is False and "not allowed" in detail

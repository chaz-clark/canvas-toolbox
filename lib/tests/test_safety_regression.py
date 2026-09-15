"""Cross-cutting safety regression suite (v2, #317 Phase 9).

Most constitutional invariants already have fixtures scattered across the
suite (FERPA Zone-2 reads, bypass-script blocking, Test Student exclusion,
duplicate-comment gates, `canvas_course_guard` scope confirmation, offline
audits) — this file does not duplicate those. It covers the invariants that
are NEW in v2 and didn't have a home yet: the declared-writer set matching
code reality, and the layering guarantee that a package manifest or a
generated adapter can never weaken what `grade_guardian` enforces.
"""
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import yaml

import capability_consent as cc  # noqa: E402
import generate_adapters as ga  # noqa: E402
import grade_guardian as gg  # noqa: E402
import package_validate as pv  # noqa: E402

REPO_ROOT = pv.REPO_ROOT

# Deliberately NARROWER than grade_guardian's own _WRITE_VERB + _CANVAS_CTX.
# Those exist to flag anything NEAR a submissions endpoint as worth a human's
# scrutiny in a Bash command — correctly broad for that job, and it caught
# real false positives here when reused directly: exempt_by_date.py (writes
# `excused`, not a grade), submit_on_behalf.py (creates submission CONTENT,
# not a score), and grader_quiz_mirror.py (a docstring mentioning the
# `/assignments/:aid/submissions` shape as prose, not code) all matched
# _CANVAS_CTX without writing a grade or comment at all. Classification here
# needs the actual grade/comment PAYLOAD KEY, not just a submissions-shaped
# URL. `quiz_submissions.{0,400}score` covers grader_quiz_clear_pending.py's
# distinct mechanism (zeroing a Classic Quiz question's score) — found by
# this same cross-check to ALSO be missing from grade_guardian's own
# _CANVAS_CTX, and fixed there separately (see test_grade_guardian.py's
# test_denies_a_bypass_that_zeroes_quiz_scores_without_posted_grade).
_GRADE_PAYLOAD_RE = re.compile(
    r"posted_grade"
    r"|comment\[text_comment\]"
    r"|quiz_submissions.{0,400}score",
    re.IGNORECASE | re.DOTALL,
)


def _has_grade_write_signature(path: Path) -> bool:
    try:
        body = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return bool(gg._WRITE_VERB.search(body) and _GRADE_PAYLOAD_RE.search(body))


def _declared_grade_comment_writers() -> set[str]:
    declared = set(pv.CONSTITUTIONAL_WRITERS)
    for path in sorted(REPO_ROOT.glob(pv.PACKAGE_GLOB)):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for tool in doc.get("tools", []):
            if tool.get("effect") == "canvas_grade_comment_write":
                declared.add(tool["command"])
    return declared


# Two deliberate, documented exclusions from the scan below — not silent gaps:
#   grade_guardian.py     is the detector describing these exact payload keys in its
#                         own regex source and comments; scanning it flags itself.
#   submit_on_behalf.py   writes an operator-authored comment ("Submitted via Slack
#                         on student's behalf...") documenting an ACCOMMODATION
#                         ACTION, not grading feedback — it never carries AI-drafted
#                         content, never needs a disclosure tag, and doesn't touch a
#                         grade. It's already gated by its own per-student
#                         confirmation and canvas_student_intervention approval. The
#                         constitutional doctrine this test checks (HG-5 review,
#                         disclosure, duplicate-comment Andon) is specifically about
#                         grading comments; conflating the two would misclassify a
#                         narrower, separately-governed action into the wrong bucket.
_NOT_A_GRADE_COMMENT_WRITER = frozenset({
    "lib/tools/grade_guardian.py",
    "lib/tools/submit_on_behalf.py",
})


def test_every_grade_write_signature_in_lib_tools_is_declared():
    """No undeclared grade/comment writer: any lib/tools/*.py whose source
    grade_guardian's own hook would flag as a Canvas grade/comment write must
    be declared canvas_grade_comment_write somewhere (CONSTITUTIONAL_WRITERS
    or a package manifest) — an undeclared one is exactly the kind of thing a
    package's install summary (Phase 7) would then silently fail to surface."""
    declared = _declared_grade_comment_writers()
    undeclared = []
    for path in sorted((REPO_ROOT / "lib" / "tools").glob("*.py")):
        if path.name.startswith("_"):
            continue  # private helpers are invoked BY a public tool, not directly
        rel = f"lib/tools/{path.name}"
        if rel in _NOT_A_GRADE_COMMENT_WRITER:
            continue
        if _has_grade_write_signature(path) and rel not in declared:
            undeclared.append(rel)
    assert undeclared == [], f"undeclared Canvas grade/comment writer(s): {undeclared}"


def test_every_declared_grade_comment_writer_actually_writes_grades():
    """The reverse direction — a manifest cannot claim canvas_grade_comment_write
    for a tool that doesn't actually touch a grade/comment endpoint. Catches a
    copy-paste misclassification the schema itself can't (it only constrains
    the vocabulary, not whether the label matches the code)."""
    mislabeled = []
    for command in _declared_grade_comment_writers():
        path = REPO_ROOT / command
        if path.is_file() and not _has_grade_write_signature(path):
            mislabeled.append(command)
    assert mislabeled == [], (
        f"declared canvas_grade_comment_write but no grade-write signature found: {mislabeled}"
    )


def test_grade_guardian_would_catch_a_bypass_mimicking_every_sanctioned_writer():
    """The enforcement mechanism, not just manifest bookkeeping: if someone
    copy-pasted the write call from ANY of the 6 sanctioned grade/comment
    writers into a new file outside lib/tools/, grade_guardian.evaluate()
    must flag it. Proves _CANVAS_CTX actually covers every real mechanism in
    use, not just the posted_grade-shaped ones — this is exactly the check
    that found the quiz-score gap fixed in grade_guardian.py this phase."""
    for command in sorted(pv.CONSTITUTIONAL_WRITERS):
        path = REPO_ROOT / command
        body = path.read_text(encoding="utf-8")
        reason = gg.evaluate("Write", {"file_path": "/tmp/copy_of_sanctioned_tool.py",
                                       "content": body})
        assert reason is not None, f"a bypass mimicking {command} would NOT be caught"


def test_capability_consent_approval_never_weakens_grade_guardian(tmp_path):
    """Layer independence, proven, not asserted: approving a package's
    capabilities (Phase 7) has zero effect on grade_guardian's own decision.
    The manifest describes access; the hook enforces it — they must not be
    able to reach into each other."""
    package = {
        "id": "grading", "version": "9.9.9", "name": "Grading",
        "description": "x",
        "tools": [{"id": "grader-push", "command": "lib/tools/grader_push.py",
                  "effect": "canvas_grade_comment_write", "data_class": "student_evaluation",
                  "approval": "always"}],
        "credentials": [], "network": ["canvas_base_url_only"],
    }
    cc.record_approval(tmp_path, "grading", cc.compute_fingerprint(package),
                       approved_by="instructor via chat")
    assert cc.load_approvals(tmp_path)["grading"]["approved_by"] == "instructor via chat"

    # The approval above is entirely inert to grade_guardian — it never reads
    # capability_consent's state, and a hand-written bypass is still blocked.
    bypass_body = (
        'import requests\n'
        'requests.put(f"/api/v1/courses/1/assignments/1/submissions/1", '
        'json={"submission": {"posted_grade": "A"}})\n'
    )
    reason = gg.evaluate("Write", {"file_path": "/tmp/bypass.py", "content": bypass_body})
    assert reason is not None, "an approved package must not make a bypass script writable"


def test_generate_adapters_never_touches_hooks_or_settings(tmp_path):
    """An adapter is portable PROMPT CONTENT only — running the generator must
    never create or modify .claude/settings.json, which is the only place a
    Canvas-write capability is actually granted at the harness level."""
    (tmp_path / "skills" / "audit").mkdir(parents=True)
    (tmp_path / "skills" / "audit" / "SKILL.md").write_text(
        "---\nname: audit\n---\nbody", encoding="utf-8")
    settings_path = tmp_path / ".claude" / "settings.json"

    for target in (tmp_path / ".agents" / "skills", tmp_path / ".claude" / "skills"):
        ga.resync(target, ga.desired_files(tmp_path / "skills"), apply=True)

    assert not settings_path.exists()


def test_an_unrecognized_package_id_in_the_distribution_fails_closed(tmp_path):
    """A distribution manifest cannot reference a package that isn't declared
    anywhere — fails closed, not silently ignored."""
    doc = {
        "schema_version": 1, "version": "1.0.0",
        "packages": ["totally-unrecognized-package"],
        "entries": [{"path": "pyproject.toml", "kind": "file", "install": "copy"}],
    }
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    schema, issues = pv.load_schema(pv.DISTRIBUTION_SCHEMA)
    assert issues == []
    result = pv.validate_distribution_document(
        doc, source="distribution.yaml", repo_root=tmp_path, tracked=set(),
        schema=schema, package_ids=set(),   # nothing declared -> "totally-unrecognized..." fails
    )
    assert "unknown-package" in {i.code for i in result}


def test_an_unrecognized_tool_path_fails_closed():
    """Same property for tools: a command outside lib/tools/ is rejected, not
    silently trusted. (Already covered directly in test_package_validate.py's
    unknown-tool fixture — this is the safety-suite's own confirmation that
    the property holds, kept minimal rather than re-testing the fixture.)"""
    schema, _ = pv.load_schema(pv.PACKAGE_SCHEMA)
    document = {
        "schema_version": 1, "id": "x", "version": "1.0.0", "name": "X", "description": "x",
        "entry_prompt": "pyproject.toml", "requires_course_folder": False,
        "skills": [{"id": "x", "path": "lib"}],
        "tools": [{"id": "t", "command": "scripts/not-a-tool.py", "effect": "read",
                  "data_class": "none", "approval": "none"}],
        "data_access": {"classes": ["none"], "ferpa_zone_2": "deny",
                        "student_names_in_evaluations": "deny"},
        "credentials": [], "network": ["none"], "ships": True,
    }
    issues = pv.validate_package_document(
        document, source="m.yaml", repo_root=REPO_ROOT, tracked=set(), schema=schema,
    )
    assert "unknown-tool" in {i.code for i in issues}


def test_full_suite_baseline_is_recorded_and_run_in_ci():
    """The literal "run pytest and stop on first failure" checklist item is
    what ci.yml already does on every push (Tier 1: `pytest lib/tests/ -v -k
    "not sprint"`, before ruff, before actionlint — first failure stops the
    job). Encoded here as an assertion so a future edit to ci.yml that drops
    that step gets caught by the suite it would otherwise silently stop
    protecting."""
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pytest lib/tests" in ci

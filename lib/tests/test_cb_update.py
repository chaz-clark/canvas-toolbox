"""Unit tests — cb_update ("cb re-init"): skill symlinks + pointer refresh.

The field audit found the 6 operating-mode skills active in 0/9 consumer repos and a
stale pointer in 6/9. These pin the two fixes: install skills at the course root
(non-clobbering) and refresh the pointer in place.
"""
import os
import subprocess
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import json  # noqa: E402
from cb_update import ensure_guardian_hook  # noqa: E402


def _fake_toolkit(tmp_path):
    """A course root with a vendored canvas-toolbox/lib/tools/grade_guardian.py."""
    g = tmp_path / "canvas-toolbox" / "lib" / "tools"
    g.mkdir(parents=True)
    (g / "grade_guardian.py").write_text("# guardian\n", encoding="utf-8")
    return tmp_path


def test_ensure_guardian_hook_installs_when_missing(tmp_path):
    """The CSE450 gap: a repo cb_update'd for skills but never given the guardian.
    cb_update now installs it (non-clobbering, idempotent)."""
    course = _fake_toolkit(tmp_path)
    assert ensure_guardian_hook(course, "canvas-toolbox", apply=False) == "would-install"
    assert not (course / ".claude" / "settings.json").exists()   # dry-run wrote nothing
    assert ensure_guardian_hook(course, "canvas-toolbox", apply=True) == "installed"
    settings = json.loads((course / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "grade_guardian" in json.dumps(settings)               # hook wired
    assert ensure_guardian_hook(course, "canvas-toolbox", apply=True) == "present"  # idempotent


def test_ensure_guardian_hook_skips_without_vendored_script(tmp_path):
    assert ensure_guardian_hook(tmp_path, "canvas-toolbox", apply=True) == "skipped-no-script"


def test_ensure_guardian_hook_refuses_unparseable_settings(tmp_path):
    course = _fake_toolkit(tmp_path)
    (course / ".claude").mkdir()
    (course / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
    assert ensure_guardian_hook(course, "canvas-toolbox", apply=True) == "bad-json"


from cb_update import (  # noqa: E402
    plan_skill_symlinks,
    install_skill_symlinks,
    ensure_gitignore,
    print_zone2_coverage,
    print_lms_mode,
    print_ignore_coverage,
    count_sibling_course_repos,
    migrate_token_to_global,
    check_token,
    normalize_global_config,
    canvas_configured,
    refresh_pointer,
)


def _fake_course(tmp_path):
    """A course root with a vendored canvas-toolbox/.claude/skills/<name>/SKILL.md."""
    for s in ("grading", "audit"):
        d = tmp_path / "canvas-toolbox" / ".claude" / "skills" / s
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {s}\n---\n", encoding="utf-8")
    return tmp_path


def test_plan_targets_are_relative_and_point_into_the_toolkit():
    plan = plan_skill_symlinks(Path("/course"), "canvas-toolbox", ["grading"])
    link, rel = plan[0]
    assert link == Path("/course/.claude/skills/grading")
    # from <course>/.claude/skills/ up to <course>/ then into the toolkit.
    # Normalize the separator so this holds on Windows (relpath yields '\\').
    assert rel.replace(os.sep, "/") == "../../canvas-toolbox/.claude/skills/grading"


def test_install_dry_run_writes_nothing(tmp_path):
    course = _fake_course(tmp_path)
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    res = install_skill_symlinks(plan, apply=False)
    assert res == [("grading", "would-install")]
    assert not (course / ".claude" / "skills" / "grading").exists()


def test_windows_copy_fallback_is_marked_and_refreshed(tmp_path, monkeypatch):
    """No-symlink environment (Windows w/o dev mode): fall back to a COPY, mark it
    ours, and REFRESH it on re-run — the bug was a re-run mistaking the copy for a
    course-owned skill and freezing it stale after every git pull."""
    course = _fake_course(tmp_path)
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    monkeypatch.setattr(Path, "symlink_to",
                        lambda self, target: (_ for _ in ()).throw(OSError("no symlink")))
    assert install_skill_symlinks(plan, apply=True) == [("grading", "copied")]
    link = course / ".claude" / "skills" / "grading"
    assert link.is_dir() and not link.is_symlink()
    assert (link / "SKILL.md").exists()          # copied content present
    assert (link / ".cb_managed").is_file()       # marked as ours
    # re-run REFRESHES the copy (does NOT skip it as course-owned)
    assert install_skill_symlinks(plan, apply=True) == [("grading", "copied")]


def test_course_owned_dir_without_marker_is_never_touched(tmp_path, monkeypatch):
    """A real skill dir the course made (no marker) is left alone even in the
    no-symlink path — we only refresh copies WE made."""
    course = _fake_course(tmp_path)
    owned = course / ".claude" / "skills" / "grading"
    owned.mkdir(parents=True)
    (owned / "SKILL.md").write_text("course's own\n", encoding="utf-8")  # no .cb_managed
    monkeypatch.setattr(Path, "symlink_to",
                        lambda self, target: (_ for _ in ()).throw(OSError("no symlink")))
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    assert install_skill_symlinks(plan, apply=True) == [("grading", "skip-course-owns")]
    assert (owned / "SKILL.md").read_text(encoding="utf-8") == "course's own\n"


def test_install_makes_the_skill_resolvable_and_stable(tmp_path):
    """OS-agnostic guarantee: after install the skill is readable at the course root
    (symlink where supported, copy on Windows), and a re-run is stable."""
    course = _fake_course(tmp_path)
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    status = install_skill_symlinks(plan, apply=True)[0][1]
    assert status in ("linked", "copied")     # symlink on posix, copy fallback on Windows
    link = course / ".claude" / "skills" / "grading"
    assert (link / "SKILL.md").read_text(encoding="utf-8").startswith("---")  # resolves
    # re-run is stable: a correct symlink → 'present'; a copy → refreshed
    assert install_skill_symlinks(plan, apply=True)[0][1] in ("present", "copied")


def test_install_never_clobbers_a_course_owned_skill(tmp_path):
    course = _fake_course(tmp_path)
    owned = course / ".claude" / "skills" / "grading"
    owned.mkdir(parents=True)
    (owned / "SKILL.md").write_text("course's own\n", encoding="utf-8")
    plan = plan_skill_symlinks(course, "canvas-toolbox", ["grading"])
    assert install_skill_symlinks(plan, apply=True) == [("grading", "skip-course-owns")]
    assert (owned / "SKILL.md").read_text(encoding="utf-8") == "course's own\n"  # intact


def _gi_lines(tmp_path):
    return (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_ensure_gitignore_ignores_toolkit_skills_by_name_not_the_directory(tmp_path):
    """The blanket `.claude/skills/` also swallowed course-OWNED skills (#271).
    Ignore only the names this tool installs — and with NO trailing slash (#277),
    since a trailing slash matches directories only and these are symlinks."""
    assert ensure_gitignore(tmp_path, ["grading", "audit"], apply=True) == "added"
    lines = _gi_lines(tmp_path)
    assert ".claude/skills/grading" in lines and ".claude/skills/audit" in lines
    assert ".claude/skills/" not in lines                   # never the whole directory
    assert not any(ln.startswith(".claude/skills/") and ln.endswith("/") for ln in lines)
    assert ensure_gitignore(tmp_path, ["grading", "audit"], apply=True) == "present"


def test_ensure_gitignore_migrates_the_legacy_blanket_line(tmp_path):
    """Every repo an older cb_update already touched has the blanket line, and the
    old code returned 'present' on sight of it — so a changed emit alone would fix
    only fresh repos. Replace it in place."""
    (tmp_path / ".gitignore").write_text(
        "*.pyc\n.claude/skills/\n.env\n", encoding="utf-8")
    assert ensure_gitignore(tmp_path, ["grading"], apply=False) == "would-migrate"
    assert ".claude/skills/" in _gi_lines(tmp_path)          # dry-run wrote nothing
    assert ensure_gitignore(tmp_path, ["grading"], apply=True) == "migrated"
    lines = _gi_lines(tmp_path)
    assert lines == ["*.pyc", ".claude/skills/grading", ".env"]  # in place, nothing lost
    assert ensure_gitignore(tmp_path, ["grading"], apply=True) == "present"  # idempotent


def test_ensure_gitignore_migrates_1_14_1_trailing_slash_lines(tmp_path):
    """1.14.1/1.15.0 wrote directory-only patterns that match no symlink (#277).
    Those repos need migrating too, not just the pre-1.14 blanket ones."""
    (tmp_path / ".gitignore").write_text(
        "*.pyc\n.claude/skills/grading/\n.claude/skills/audit/\n.env\n", encoding="utf-8")
    assert ensure_gitignore(tmp_path, ["grading", "audit"], apply=False) == "would-migrate"
    assert ensure_gitignore(tmp_path, ["grading", "audit"], apply=True) == "migrated"
    # both slashed lines collapse to the corrected set, in place, nothing else lost
    assert _gi_lines(tmp_path) == [
        "*.pyc", ".claude/skills/grading", ".claude/skills/audit", ".env"]
    assert ensure_gitignore(tmp_path, ["grading", "audit"], apply=True) == "present"


def test_ensure_gitignore_adds_only_newly_shipped_skills(tmp_path):
    ensure_gitignore(tmp_path, ["grading"], apply=True)
    assert ensure_gitignore(tmp_path, ["grading", "improve"], apply=True) == "added"
    assert _gi_lines(tmp_path).count(".claude/skills/grading") == 1   # no duplicate


def _git(tmp_path, *args, **kw):
    return subprocess.run(["git", "-C", str(tmp_path), *args],
                          capture_output=True, text=True, **kw)


def _untracked(tmp_path):
    """What git sees under the COURSE-ROOT skills dir. Pathspec-scoped so the
    vendored `canvas-toolbox/.claude/skills/<s>/` originals (untracked in these
    fixtures) can't be mistaken for the symlinks that point at them."""
    return _git(tmp_path, "status", "--porcelain", "-uall", "--", ".claude/skills").stdout


def test_real_git_ignores_the_installed_symlink_not_just_the_pattern(tmp_path):
    """#277 — the regression a pattern-only assertion cannot see. `check-ignore`
    happily matches a trailing-slash pattern against a trailing-slash PATH, so the
    only honest check is to install the real artifact and ask git about the worktree.
    A symlink is a file to git; a directory-only pattern never matches it."""
    course = _fake_course(tmp_path)
    _git(course, "init", "-q", ".")
    status = install_skill_symlinks(
        plan_skill_symlinks(course, "canvas-toolbox", ["grading"]), apply=True)[0][1]
    assert status in ("linked", "copied")          # the real artifact now exists
    ensure_gitignore(course, ["grading"], apply=True)
    assert "skills/grading" not in _untracked(course)


def test_course_owned_skill_stays_visible_to_git(tmp_path):
    """The bug as the consumer felt it (#271): a course-authored skill added AFTER
    cb_update ran was untracked AND ignored, so `git add -A` silently skipped it.
    Asserted against a real worktree so it also covers #277 in the other direction —
    the toolkit's own symlink must actually disappear from `git status`."""
    course = _fake_course(tmp_path)
    _git(course, "init", "-q", ".")
    owned = course / ".claude" / "skills" / "my-course-skill"
    owned.mkdir(parents=True)
    (owned / "SKILL.md").write_text("course's own\n", encoding="utf-8")
    (course / ".gitignore").write_text(".claude/skills/\n", encoding="utf-8")  # legacy
    install_skill_symlinks(
        plan_skill_symlinks(course, "canvas-toolbox", ["grading"]), apply=True)

    assert "my-course-skill" not in _untracked(course)      # the bug: silently hidden
    assert ensure_gitignore(course, ["grading"], apply=True) == "migrated"
    after = _untracked(course)
    assert "my-course-skill/SKILL.md" in after   # the consumer can finally commit it
    assert "skills/grading" not in after         # toolkit's symlink still stays out


def test_refresh_pointer_injects_into_course_agents(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# ITM327\n\nCourse context.\n", encoding="utf-8")
    fname, status = refresh_pointer(tmp_path, apply=True)
    assert (fname, status) == ("AGENTS.md", "refreshed")
    body = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert ".claude/skills" in body and "Course context." in body  # added, non-clobbering
    assert refresh_pointer(tmp_path, apply=True)[1] == "present"  # idempotent


def test_refresh_pointer_reports_missing_when_no_agents_file(tmp_path):
    assert refresh_pointer(tmp_path, apply=True)[1] == "missing"


# --- guardian Zone-2 coverage reporting (#278) ------------------------------

def test_reports_zone2_coverage_and_names_the_extension_file(tmp_path, capsys):
    """`grade_guardian hook: present` was true and misleading for a non-Canvas
    consumer — installed, enforcing a Canvas-only set that matched none of their
    files. Coverage has to be stated, not inferred."""
    print_zone2_coverage(tmp_path)
    out = capsys.readouterr().out
    assert "Zone-2 patterns:" in out and "built-in" in out
    assert ".claude/ferpa_zone2.txt" in out          # tells them where to extend


def test_reports_course_local_pattern_count(tmp_path, capsys):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "ferpa_zone2.txt").write_text(
        "_all_posts\\.md\n_roster\\.json\n", encoding="utf-8")
    print_zone2_coverage(tmp_path)
    out = capsys.readouterr().out
    assert "2 course-local" in out
    assert "one regex per line" not in out           # already extended — no nag


def test_warns_loudly_about_invalid_patterns(tmp_path, capsys):
    """A dropped pattern is a silent hole — the exact false sense of coverage #278
    is about. It must be impossible to miss."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "ferpa_zone2.txt").write_text("[unclosed\n", encoding="utf-8")
    print_zone2_coverage(tmp_path)
    out = capsys.readouterr().out
    assert "not valid" in out and "IGNORED" in out and "[unclosed" in out


# --- the third repo shape: vendored into a NON-Canvas course (#279) ---------

def test_canvas_configured_reads_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CANVAS_COURSE_ID", raising=False)
    assert canvas_configured(tmp_path) is False              # no .env at all
    (tmp_path / ".env").write_text("CANVAS_BASE_URL=x\nCANVAS_COURSE_ID=\n",
                                   encoding="utf-8")
    assert canvas_configured(tmp_path) is False              # present but EMPTY
    (tmp_path / ".env").write_text('CANVAS_COURSE_ID="12345"\n', encoding="utf-8")
    assert canvas_configured(tmp_path) is True               # quoted value counts


def test_canvas_configured_prefers_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("CANVAS_COURSE_ID", "999")
    assert canvas_configured(tmp_path) is True               # no .env needed


def test_non_canvas_repo_is_told_what_still_applies(tmp_path, monkeypatch, capsys):
    """#279: the mode was undeclared, so a consumer had to infer tool by tool which
    parts applied. Most of the toolkit never touches the Canvas API."""
    monkeypatch.delenv("CANVAS_COURSE_ID", raising=False)
    print_lms_mode(tmp_path)
    out = capsys.readouterr().out
    assert "No Canvas course configured" in out
    assert "inert" in out                                     # what does NOT work
    for still_applies in ("constitution", "grade_guardian", "consensus grading"):
        assert still_applies in out                           # ...and what does
    assert "--roster-json" in out                             # the way through


def test_canvas_repo_gets_no_mode_noise(tmp_path, monkeypatch, capsys):
    """The overwhelmingly common case must stay silent — a guardrail that chatters
    at everyone gets tuned out."""
    monkeypatch.setenv("CANVAS_COURSE_ID", "12345")
    print_lms_mode(tmp_path)
    assert capsys.readouterr().out == ""


# --- ignore-coverage report (#285) ------------------------------------------

def _cov_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "grading" / "kc3" / "submissions_raw").mkdir(parents=True)
    (tmp_path / "grading" / ".deid_master.csv").write_text("x\n", encoding="utf-8")
    (tmp_path / "grading" / "kc3" / "submissions_raw" / "Last_First_9.docx").write_text(
        "x\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("ok\n", encoding="utf-8")
    return tmp_path


def test_reports_name_bearing_files_git_is_not_ignoring(tmp_path, capsys):
    """The near-miss: an ignore-rule restructure left three name-bearing paths
    uncovered at once, caught by checking rather than by design."""
    print_ignore_coverage(_cov_repo(tmp_path))
    out = capsys.readouterr().out
    assert "grading/" in out and "submissions_raw/" in out
    assert "Last_First_9.docx" not in out      # leaf withheld — it may BE a name


def test_coverage_report_is_silent_when_properly_ignored(tmp_path, capsys):
    """`git ls-files --others` lists IGNORED files unless --exclude-standard is
    passed, so without it this fires even on a covered repo — and a warning that
    always fires gets tuned out."""
    repo = _cov_repo(tmp_path)
    (repo / ".gitignore").write_text("grading/\n", encoding="utf-8")
    print_ignore_coverage(repo)
    assert capsys.readouterr().out == ""


def test_coverage_report_still_flags_an_already_TRACKED_zone2_file(tmp_path, capsys):
    """gitignore does not untrack. A committed Zone-2 file is exposed no matter what
    the ignore rules say, so it must still be reported."""
    repo = _cov_repo(tmp_path)
    (repo / ".gitignore").write_text("grading/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-f", "grading/.deid_master.csv"],
                   check=True, capture_output=True)
    print_ignore_coverage(repo)
    assert "grading/" in capsys.readouterr().out


def test_coverage_report_skips_a_non_git_directory(tmp_path, capsys):
    print_ignore_coverage(tmp_path)
    assert capsys.readouterr().out == ""


def test_zone2_nudge_is_silent_for_a_configured_canvas_repo(tmp_path, capsys, monkeypatch):
    """The built-ins cover a Canvas course completely, so nudging every Canvas repo
    to write ferpa_zone2.txt — on every run, forever — is homework they don't owe.
    A guardrail that chatters at everyone gets tuned out."""
    monkeypatch.setenv("CANVAS_COURSE_ID", "12345")
    print_zone2_coverage(tmp_path)
    out = capsys.readouterr().out
    assert "Zone-2 patterns:" in out          # the FACT still prints
    assert "one regex per line" not in out    # the homework doesn't


def test_zone2_nudge_still_fires_for_a_non_canvas_repo(tmp_path, capsys, monkeypatch):
    """Where it IS actionable — a consumer whose name-bearing files the built-ins
    cannot know about."""
    monkeypatch.delenv("CANVAS_COURSE_ID", raising=False)
    print_zone2_coverage(tmp_path)
    assert "one regex per line" in capsys.readouterr().out


def test_coverage_report_points_at_the_extension_file(tmp_path, capsys):
    """A Canvas repo that does keep its own name-bearing files gets pointed at
    ferpa_zone2.txt here — on evidence, rather than as a standing nag."""
    print_ignore_coverage(_cov_repo(tmp_path))
    assert ".claude/ferpa_zone2.txt" in capsys.readouterr().out


# --- global Canvas credentials (#288) ---------------------------------------
#
# EVERY test that reaches an apply path monkeypatches cb_update._GLOBAL_CONFIG.
# Without that these would write a token into the developer's real ~/.canvas/config.

import cb_update as _cbu  # noqa: E402


def _course(tmp_path, name, token="OLD_expired", n_siblings=0):
    root = tmp_path / name
    (root / "canvas-toolbox").mkdir(parents=True)
    (root / ".env").write_text(
        f"CANVAS_BASE_URL=https://x.instructure.com\n"
        f"CANVAS_API_TOKEN={token}\nCANVAS_COURSE_ID=12345\n", encoding="utf-8")
    for i in range(n_siblings):
        sib = tmp_path / f"sibling{i}-master"
        (sib / "canvas-toolbox").mkdir(parents=True)
        (sib / ".env").write_text("CANVAS_API_TOKEN=x\n", encoding="utf-8")
    return root


def test_multi_course_is_detected_from_siblings(tmp_path):
    """Counts DIRECTORIES only — never reads another repo's .env to make a
    convenience decision."""
    one, many = tmp_path / "one", tmp_path / "many"
    one.mkdir(); many.mkdir()
    assert count_sibling_course_repos(_course(one, "solo")) == 1
    assert count_sibling_course_repos(_course(many, "a", n_siblings=4)) == 5


def test_a_scaffold_without_env_is_not_a_course_repo(tmp_path):
    root = _course(tmp_path, "a")
    (tmp_path / "not-configured" / "canvas-toolbox").mkdir(parents=True)  # no .env
    assert count_sibling_course_repos(root) == 1


def test_single_course_never_touches_home(tmp_path, monkeypatch):
    """A repo tool writing secrets into $HOME needs positive evidence. One course
    gains nothing from a second location."""
    target = tmp_path / "home" / ".canvas" / "config"
    monkeypatch.setattr(_cbu, "_GLOBAL_CONFIG", target)
    root = _course(tmp_path, "solo")
    assert migrate_token_to_global(root, multi=False, apply=True) == "single-course"
    assert not target.exists()
    assert "CANVAS_API_TOKEN=OLD_expired" in (root / ".env").read_text(encoding="utf-8")


def test_multi_course_creates_the_global_file_and_comments_out_the_local(tmp_path, monkeypatch):
    """The 29-day rotation problem: N repos, N .env edits a month, a silent 401 on
    the one you forget."""
    target = tmp_path / "home" / ".canvas" / "config"
    monkeypatch.setattr(_cbu, "_GLOBAL_CONFIG", target)
    root = _course(tmp_path, "a", token="TOK_abc", n_siblings=4)

    assert migrate_token_to_global(root, multi=True, apply=False) == "would-create"
    assert not target.exists()                       # dry run wrote nothing

    assert migrate_token_to_global(root, multi=True, apply=True) == "created"
    assert "CANVAS_API_TOKEN=TOK_abc" in target.read_text(encoding="utf-8")
    assert target.stat().st_mode & 0o777 == 0o600    # it holds a token
    env = (root / ".env").read_text(encoding="utf-8")
    assert "# CANVAS_API_TOKEN=TOK_abc" in env       # commented, NOT deleted
    assert "CANVAS_COURSE_ID=12345" in env           # course id untouched


def test_migration_is_idempotent_and_self_consolidating(tmp_path, monkeypatch):
    """Run it in any repo, in any order, re-run freely — there's no list to track."""
    target = tmp_path / "home" / ".canvas" / "config"
    monkeypatch.setattr(_cbu, "_GLOBAL_CONFIG", target)
    root = _course(tmp_path, "a", n_siblings=4)
    migrate_token_to_global(root, multi=True, apply=True)
    assert migrate_token_to_global(root, multi=True, apply=True) == "present"


def test_a_second_repo_consolidates_rather_than_recreating(tmp_path, monkeypatch):
    target = tmp_path / "home" / ".canvas" / "config"
    monkeypatch.setattr(_cbu, "_GLOBAL_CONFIG", target)
    first = _course(tmp_path, "a", token="TOK_first", n_siblings=4)
    migrate_token_to_global(first, multi=True, apply=True)
    second = _course(tmp_path, "b", token="TOK_stale")
    assert migrate_token_to_global(second, multi=True, apply=True) == "consolidated"
    assert "TOK_first" in target.read_text(encoding="utf-8")   # first one wins, not clobbered
    assert "# CANVAS_API_TOKEN=TOK_stale" in (second / ".env").read_text(encoding="utf-8")


def test_migration_handles_an_export_prefixed_token(tmp_path, monkeypatch):
    target = tmp_path / "home" / ".canvas" / "config"
    monkeypatch.setattr(_cbu, "_GLOBAL_CONFIG", target)
    root = _course(tmp_path, "a", n_siblings=4)
    (root / ".env").write_text('export CANVAS_API_TOKEN="TOK_quoted"\n', encoding="utf-8")
    assert migrate_token_to_global(root, multi=True, apply=True) == "created"
    assert "CANVAS_API_TOKEN=TOK_quoted" in target.read_text(encoding="utf-8")


def test_scaffolds_an_empty_config_when_there_is_no_token_to_seed(tmp_path, monkeypatch):
    """The moment anyone consolidates is the moment their token expired — that's the
    reason they're here — so every local copy may be stale and there may be nothing
    worth seeding. An empty 0600 file to paste into beats 'no-token' and no guidance.
    (Real instance: a repo scaffolded with `CANVAS_API_TOKEN=` and never filled.)"""
    target = tmp_path / "home" / ".canvas" / "config"
    monkeypatch.setattr(_cbu, "_GLOBAL_CONFIG", target)
    root = _course(tmp_path, "a", token="", n_siblings=4)      # empty = absent

    assert migrate_token_to_global(root, multi=True, apply=False) == "would-scaffold"
    assert not target.exists()
    assert migrate_token_to_global(root, multi=True, apply=True) == "scaffolded"
    body = target.read_text(encoding="utf-8")
    assert body.rstrip().endswith("CANVAS_API_TOKEN=")         # ready to paste into
    assert target.stat().st_mode & 0o777 == 0o600              # perms set regardless
    assert "IGNORED" in body                                    # the course-id warning
    # once it exists, a repo with nothing to contribute is a no-op
    assert migrate_token_to_global(root, multi=True, apply=True) == "present"


def test_token_check_reports_no_token_without_a_network_call(tmp_path, monkeypatch):
    """Must isolate BOTH sources now that check_token resolves credentials properly —
    otherwise it reads the developer's real ~/.canvas/config and this passes or fails
    depending on whose machine runs it."""
    import _env_loader
    for v in ("CANVAS_API_TOKEN", "CANVAS_BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    # load_env()'s __file__-anchored fallback walks up from lib/tools/ and finds the
    # TOOLKIT's own .env before anything else — on a maintainer's machine that holds a
    # real token, so without this the test asserts against their credential.
    monkeypatch.setattr(_env_loader, "load_env", lambda: None)
    monkeypatch.setattr(_env_loader, "GLOBAL_CONFIG", tmp_path / "nope" / "config")
    assert check_token() == "no-token"


def test_token_check_distinguishes_rejected_from_unreachable(monkeypatch):
    """The distinction that matters. cb_update has always worked offline; reporting
    a network failure as a bad token would send someone to regenerate a perfectly
    good credential."""
    import urllib.error
    import urllib.request
    monkeypatch.setenv("CANVAS_API_TOKEN", "tok")
    monkeypatch.setenv("CANVAS_BASE_URL", "byui.instructure.com")

    def _401(*a, **kw):
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", _401)
    assert check_token() == "REJECTED"

    def _offline(*a, **kw):
        raise OSError("nodename nor servname provided")
    monkeypatch.setattr(urllib.request, "urlopen", _offline)
    assert check_token() == "unreachable"


def test_token_check_never_returns_the_token(monkeypatch):
    monkeypatch.setenv("CANVAS_API_TOKEN", "SECRET_tok")
    monkeypatch.setenv("CANVAS_BASE_URL", "byui.instructure.com")
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **kw: (_ for _ in ()).throw(OSError("x")))
    assert "SECRET" not in check_token()


def test_token_check_resolves_credentials_instead_of_reading_a_bare_environ(tmp_path, monkeypatch):
    """cb_update is not a Canvas tool and never called load_env(), so check_token()
    read an os.environ nothing had populated — it never looked at ~/.canvas/config.
    Five consumer repos reported a rejected token on the same day the operator's curl
    against that file returned 200. A check that tests something other than what the
    tools use is worse than no check."""
    import _env_loader
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    monkeypatch.delenv("CANVAS_BASE_URL", raising=False)
    cfg = tmp_path / ".canvas" / "config"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("CANVAS_API_TOKEN=GLOBAL_tok\n", encoding="utf-8")
    monkeypatch.setattr(_env_loader, "GLOBAL_CONFIG", cfg)
    repo = tmp_path / "course"
    repo.mkdir()
    (repo / ".env").write_text("CANVAS_BASE_URL=byui.instructure.com\n", encoding="utf-8")
    monkeypatch.chdir(repo)

    seen = {}
    import urllib.request

    def _capture(req, *a, **kw):
        seen["auth"] = req.get_header("Authorization")
        raise OSError("stop before the network")
    monkeypatch.setattr(urllib.request, "urlopen", _capture)

    check_token()
    assert seen.get("auth") == "Bearer GLOBAL_tok", \
        "check_token must test the credential the tools resolve, not a bare environ"


def test_global_config_is_written_with_export(tmp_path, monkeypatch):
    """A plain `KEY=value` sources into a SHELL variable that no child process
    inherits, so `source ~/.canvas/config && python script.py` silently finds
    nothing — two field agents did exactly that and concluded the token was
    missing. `export` makes sourcing work and python-dotenv still parses it."""
    target = tmp_path / "home" / ".canvas" / "config"
    monkeypatch.setattr(_cbu, "_GLOBAL_CONFIG", target)
    _cbu._write_global_config("TOK_abc")
    body = target.read_text(encoding="utf-8")
    assert "export CANVAS_API_TOKEN=TOK_abc" in body
    assert target.stat().st_mode & 0o777 == 0o600


def test_existing_config_without_export_is_normalized(tmp_path, monkeypatch):
    """Files written before this change lack the prefix. The toolkit never noticed
    (it parses the file directly) but every ad-hoc `source … && python …` got
    nothing."""
    target = tmp_path / "home" / ".canvas" / "config"
    target.parent.mkdir(parents=True)
    target.write_text("# comment\nCANVAS_API_TOKEN=TOK_abc\n", encoding="utf-8")
    monkeypatch.setattr(_cbu, "_GLOBAL_CONFIG", target)

    assert normalize_global_config(apply=False) == "would-fix"
    assert "export" not in target.read_text(encoding="utf-8")   # dry run wrote nothing
    assert normalize_global_config(apply=True) == "fixed"
    body = target.read_text(encoding="utf-8")
    assert "export CANVAS_API_TOKEN=TOK_abc" in body
    assert "# comment" in body                                   # comments preserved
    assert normalize_global_config(apply=True) == "present"      # idempotent


def test_normalize_ignores_commented_lines_and_missing_file(tmp_path, monkeypatch):
    target = tmp_path / "home" / ".canvas" / "config"
    monkeypatch.setattr(_cbu, "_GLOBAL_CONFIG", target)
    assert normalize_global_config(apply=True) == "absent"
    target.parent.mkdir(parents=True)
    target.write_text("# CANVAS_API_TOKEN=commented_out\n", encoding="utf-8")
    assert normalize_global_config(apply=True) == "present"      # a comment isn't a setting

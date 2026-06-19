"""Tier 1 tests for scripts/install.sh — Sprint 2B curl-pipe installer.

Bash scripts are harder to unit-test than Python, but two cheap checks
catch the bulk of real regressions:

  1. `bash -n` syntax parse — catches typos, unclosed quotes, missing
     `fi`/`done`, etc. Same role as `py_compile` for our Python tools.
  2. Dry-run end-to-end — `CANVAS_TOOLBOX_INSTALL_DRY_RUN=1 bash install.sh`
     runs the full script without network calls, real installs, or
     real clones. Asserts the planned sequence of operations prints
     correctly (git check, uv check, would-clone, would-cb-init).

End-to-end against a real clone is verified manually by the maintainer
on each release — see the v0.55.0 commit message for the validation
log. CI runs only the two cheap checks below.
"""
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_INSTALL_SH = _REPO_ROOT / "scripts" / "install.sh"


def test_install_sh_exists_and_is_executable():
    """install.sh must be tracked + chmod +x for `bash install.sh` to work."""
    assert _INSTALL_SH.is_file(), f"missing: {_INSTALL_SH}"
    mode = _INSTALL_SH.stat().st_mode
    assert mode & 0o100, f"not executable: {_INSTALL_SH} (mode={oct(mode)})"


def test_install_sh_passes_bash_syntax_check():
    """`bash -n` validates syntax without executing — catches typos +
    unclosed blocks. Equivalent to py_compile for Python tools."""
    r = subprocess.run(
        ["bash", "-n", str(_INSTALL_SH)],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, (
        f"bash -n failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    )


def test_install_sh_dry_run_prints_planned_sequence(tmp_path):
    """Dry-run end-to-end: no clone, no uv install, no cb-init invocation.
    Asserts the 4 phases each print their planned action: git check,
    uv check (or install), clone, cb-init."""
    r = subprocess.run(
        ["bash", str(_INSTALL_SH)],
        env={
            "CANVAS_TOOLBOX_INSTALL_DRY_RUN": "1",
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": str(tmp_path),
        },
        capture_output=True, text=True, timeout=30,
        cwd=str(tmp_path),
    )
    out = r.stdout + r.stderr
    assert r.returncode == 0, (
        f"dry-run failed (exit {r.returncode}):\n{out}"
    )

    assert "canvas-toolbox installer" in out
    assert "[dry-run mode" in out
    assert "git" in out
    assert "uv" in out
    assert "[dry-run] would clone" in out
    assert "canvas-toolbox.git" in out
    assert "[dry-run] would cd" in out
    assert "cb_init.py" in out
    assert "--yes" in out  # non-interactive flag for curl-pipe context


def test_install_sh_refuses_existing_clone_dir(tmp_path):
    """If `canvas-toolbox/` already exists in cwd, install.sh should bail
    with a recovery hint, not clobber existing state."""
    existing = tmp_path / "canvas-toolbox"
    existing.mkdir()
    (existing / "marker.txt").write_text("pre-existing", encoding="utf-8")

    r = subprocess.run(
        ["bash", str(_INSTALL_SH)],
        env={
            "CANVAS_TOOLBOX_INSTALL_DRY_RUN": "1",
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": str(tmp_path),
        },
        capture_output=True, text=True, timeout=10,
        cwd=str(tmp_path),
    )
    out = r.stdout + r.stderr

    assert r.returncode != 0, (
        f"install.sh should refuse pre-existing dir; got exit 0:\n{out}"
    )
    assert "already exists" in out
    assert "cb_init.py" in out  # recovery hint mentions the resume tool

    # Pre-existing file must be untouched
    assert (existing / "marker.txt").read_text(encoding="utf-8") == "pre-existing"


# ---------------------------------------------------------------------------
# bin/ wrappers — short-alias passthrough scripts (v0.56.0)
#
# Each wrapper is a 3-line bash script that execs `uv run python
# lib/tools/<tool>.py "$@"`. Tests assert the wrappers are present,
# executable, and parse cleanly. End-to-end behavior is exercised
# indirectly by the wrappers' --help passing (caught by Tier 0 CI smoke).
# ---------------------------------------------------------------------------

import pytest

_BIN_DIR = _REPO_ROOT / "bin"


@pytest.mark.parametrize("name", ["cb-init", "cb-report-bug", "cb-share"])
def test_bin_wrapper_exists_and_is_executable(name):
    """Every bin/ wrapper must be tracked + chmod +x."""
    p = _BIN_DIR / name
    assert p.is_file(), f"missing: {p}"
    mode = p.stat().st_mode
    assert mode & 0o100, f"not executable: {p} (mode={oct(mode)})"


@pytest.mark.parametrize("name", ["cb-init", "cb-report-bug", "cb-share"])
def test_bin_wrapper_passes_bash_syntax_check(name):
    """`bash -n` validates syntax without executing — catches typos +
    unclosed blocks in the 3-line wrappers."""
    r = subprocess.run(
        ["bash", "-n", str(_BIN_DIR / name)],
        capture_output=True, text=True, timeout=5,
    )
    assert r.returncode == 0, (
        f"bash -n failed for bin/{name}:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    )


@pytest.mark.parametrize("name,expected_target", [
    ("cb-init", "cb_init.py"),
    ("cb-report-bug", "cb_report_bug.py"),
    ("cb-share", "cb_report_bug.py"),  # cb-share is an alias for cb_report_bug
])
def test_bin_wrapper_targets_correct_tool(name, expected_target):
    """The wrapper must reference the right lib/tools/<tool>.py file.
    Catches typos that would have the wrapper exec the wrong tool."""
    content = (_BIN_DIR / name).read_text(encoding="utf-8")
    assert expected_target in content, (
        f"bin/{name} does not reference {expected_target}"
    )


# ---------------------------------------------------------------------------
# scripts/install.ps1 — Windows installer (v0.57.0)
#
# Bash-side can't run PowerShell to syntax-check; we keep these tests
# light — file exists, has the expected sections, references the right
# downstream tool. A maintainer with pwsh installed locally validates
# syntax + behavior before any release that touches install.ps1.
# ---------------------------------------------------------------------------

_INSTALL_PS1 = _REPO_ROOT / "scripts" / "install.ps1"


def test_install_ps1_exists():
    assert _INSTALL_PS1.is_file(), f"missing: {_INSTALL_PS1}"


def test_install_ps1_references_uv_installer():
    """The PS1 must shell out to Astral's official PowerShell installer."""
    content = _INSTALL_PS1.read_text(encoding="utf-8")
    assert "astral.sh/uv/install.ps1" in content


def test_install_ps1_references_cb_init():
    """The PS1 must end by invoking cb_init.py with --yes (matches the
    install.sh shape)."""
    content = _INSTALL_PS1.read_text(encoding="utf-8")
    assert "cb_init.py" in content
    assert "--yes" in content


def test_install_ps1_has_dry_run_branch():
    """The PS1 honors CANVAS_TOOLBOX_INSTALL_DRY_RUN parity with install.sh."""
    content = _INSTALL_PS1.read_text(encoding="utf-8")
    assert "CANVAS_TOOLBOX_INSTALL_DRY_RUN" in content
    assert "DryRun" in content


def test_install_ps1_refuses_existing_clone_dir_logic_present():
    """The PS1's idempotency check (Test-Path $CloneDir) must be present;
    mirrors install.sh's `[ -e "$CLONE_DIR" ]` guard."""
    content = _INSTALL_PS1.read_text(encoding="utf-8")
    assert "Test-Path $CloneDir" in content
    assert "already exists" in content


def test_install_ps1_references_cb_init_recovery_path():
    """When the clone dir exists, the PS1 must point at cb_init.py as the
    resume path — same UX as install.sh."""
    content = _INSTALL_PS1.read_text(encoding="utf-8")
    assert "cb_init.py" in content

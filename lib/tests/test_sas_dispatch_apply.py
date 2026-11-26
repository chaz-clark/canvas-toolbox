"""Tests — apply_sas_accommodations runs each tool, and with --apply when it was given it (#503).

Two faults hid behind tests that joined the command into one string. Every
command was `python lib/tools/ <tool>.py`, so Python ran the directory and failed,
and none carried --apply, so a tool that did run would only have previewed. The
end-to-end test proves both are fixed without a network: from a folder above
two courses, each tool's own course guard refuses, and the guard refuses only a
real write. So the refusal shows that the tool ran and that --apply reached it.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from apply_sas_accommodations import _CANVAS_KEYS, plan_entries, plan_one_accommodation  # noqa: E402

# One accommodation per Canvas-tier key, covering each scope the builder knows.
ACCS = [
    {"key": "extra_time_1.5x"},
    {"key": "extra_time_2.0x"},
    {"key": "occasional_extensions"},
    {"key": "occasional_extensions", "scope": "from_days_ago", "days": 14},
    {"key": "occasional_extensions", "scope": "from", "from": "2026-04-01"},
    {"key": "test_reschedule"},
    {"key": "test_reschedule", "shift_by_days": 14, "assignment_id": 12345},
]


def test_every_canvas_key_is_covered():
    assert {a["key"] for a in ACCS} == _CANVAS_KEYS


@pytest.mark.parametrize("acc", ACCS, ids=lambda a: "-".join(str(v) for v in a.values()))
def test_apply_is_on_the_command_exactly_when_given(acc):
    assert plan_one_accommodation("S-000001", acc, apply=True).command.count("--apply") == 1
    assert "--apply" not in plan_one_accommodation("S-000001", acc).command
    assert "--apply" not in plan_one_accommodation("S-000001", acc, apply=False).command


@pytest.mark.parametrize("acc", ACCS, ids=lambda a: "-".join(str(v) for v in a.values()))
def test_the_command_runs_a_tool_file_on_this_python(acc):
    cmd = plan_one_accommodation("S-000001", acc, apply=True).command
    assert cmd[0] == sys.executable
    assert Path(cmd[1]).is_file() and Path(cmd[1]).parent == _TOOLS_DIR


def test_plan_entries_passes_apply_through():
    entries = [{"deid_code": "S-000001", "accommodations": ACCS}]
    assert all("--apply" in p.command for p in plan_entries(entries, apply=True))
    assert not any("--apply" in p.command for p in plan_entries(entries))


def _run_dispatcher(tmp_path, *flags):
    """Run the dispatcher from a folder above two courses, Canvas at a dead address."""
    for name in ("course-a", "course-b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / ".env").write_text("CANVAS_COURSE_ID=1\n", encoding="utf-8")
    handoff = tmp_path / "sas.yml"
    handoff.write_text("- deid_code: S-000001\n"
                       "  accommodations:\n"
                       "    - key: extra_time_1.5x\n"
                       "    - key: occasional_extensions\n"
                       "    - key: spelling_grammar\n", encoding="utf-8")
    log = tmp_path / "applied.log"
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path),
           "CANVAS_API_TOKEN": "x", "CANVAS_BASE_URL": "http://127.0.0.1:9",
           "CANVAS_COURSE_ID": "423164"}
    r = subprocess.run([sys.executable, str(_TOOLS_DIR / "apply_sas_accommodations.py"),
                        "--file", str(handoff), "--audit-log", str(log), *flags],
                       capture_output=True, text=True, timeout=120, cwd=tmp_path, env=env)
    return r, log.read_text(encoding="utf-8")


def test_apply_reaches_each_tool_as_a_write(tmp_path):
    r, log = _run_dispatcher(tmp_path, "--apply")
    assert r.returncode == 1, (r.stdout, r.stderr)
    assert "__main__" not in r.stdout, "Python was handed a directory, not the tool"
    # Each tool's own guard refused a write, and the dispatcher logged it as one.
    assert r.stdout.count("REFUSING WRITE") == 2, r.stdout
    assert log.count("\tFAILED\t") == 2 and "\tAPPLIED\t" not in log
    assert log.count("\tFLAGGED\t") == 1


def test_a_dry_run_runs_nothing_and_says_planned(tmp_path):
    r, log = _run_dispatcher(tmp_path)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "REFUSING WRITE" not in r.stdout and "--apply" not in r.stdout
    assert log.count("\tPLANNED\t") == 2 and "\tAPPLIED\t" not in log

#!/usr/bin/env python3
"""PreToolUse guardrail — grades reach Canvas ONLY through grader_push.py (#213).

WHY THIS EXISTS
  Every in-tool safeguard (grader_push.py's HG-5 gate from #207/#214, and
  canvas_course_guard) lives INSIDE the tools, so they share one bypass: not
  calling the tool. In the KC1/KC2 incident an agent hand-wrote a
  `/tmp/push_kc_grades.py` that hit the Canvas API directly and every gate was
  moot. In-tool enforcement cannot catch "the tool was never used" — only a seam
  ABOVE the tools can. Claude Code PreToolUse hooks are that seam: harness-
  enforced, the model cannot disable them.

WHAT IT DENIES
  - Bash: a direct Canvas grade/comment write in the command string (a write verb
    — requests.put/post, curl/wget -X PUT/POST — aimed at a Canvas submissions
    endpoint or grade payload). Invocations of the sanctioned tools under
    lib/tools/ are exempt.
  - Write/Edit: creating/editing a file (outside lib/tools/) whose contents carry
    that same Canvas-write signature — this catches the bypass SCRIPT at creation,
    which is the only reliable catch (a Bash hook can't see inside `python x.py`).
  - Read: FERPA Zone-2 files (.deid_master.csv et al.) — the AGENTS.md discipline,
    enforced deterministically instead of by instruction (#212).

WHAT IT DOES NOT DO (honest limits)
  Regex on a command / file body is not a semantic firewall. A determined agent
  can obfuscate (eval, base64, variable indirection) past it. This decisively
  raises the bar against the ACTUAL failure mode (pattern-matching a /tmp push
  script), but true closure needs the capability layer (a read-scoped agent token
  + a write-proxy). See docs/grading_enforcement_A3.md.

HOW CLAUDE CODE INVOKES IT
  Registered as a PreToolUse hook (matcher `Bash|Write|Edit|Read`). Claude Code
  pipes the tool call as JSON on stdin; exit 2 blocks the call and the stderr text
  is fed back to the agent (so the denial redirects it to grader_push.py). Fails
  OPEN on any internal error — a guardrail must never brick the session.
"""
from __future__ import annotations

import json
import re
import sys

# A write verb: an HTTP mutation, however the script spells it.
_WRITE_VERB = re.compile(
    r"requests\.(put|post)\b"
    r"|httpx?\.(put|post)\b"
    r"|\b(curl|wget)\b[^\n]*-X\s*(PUT|POST)"
    r"|\.(put|post)\(",  # generic client.put(/.post(
    re.IGNORECASE,
)

# Canvas grade-write context: the submissions endpoint or a grade/comment payload.
_CANVAS_CTX = re.compile(
    r"/api/v1/courses/\d+/assignments/\d+/submissions"
    r"|/submissions/\d+"
    r"|posted_grade"
    r"|submission\[submission\]"
    r"|comment\[text_comment\]"
    r"|canvas.*submission",
    re.IGNORECASE,
)

# The sanctioned tool source. Writing Canvas-write code here is legitimate — this
# IS the reviewed tooling; running these scripts is the safe path.
_TOOLS_PATH = re.compile(r"/lib/tools/[^/\\]+\.py$")

# Prose/doc files — a code example inside a design doc is not an executable bypass.
_DOC_PATH = re.compile(r"\.(md|markdown|rst|txt)$", re.IGNORECASE)

# FERPA Zone-2 files — never surface to an LLM (AGENTS.md → FERPA discipline, #212).
_FERPA_PATH = re.compile(
    r"\.deid_master\.csv$"
    r"|\.known_names\.txt$"
    r"|\.keymap\.json$"
    r"|\.fetch_log\.json$"
    r"|\.review\.csv$"
    r"|/submissions_raw/"
    r"|feedback/_grader.*\.csv$"
)


def _redirect(what: str) -> str:
    return (
        f"⛔ Blocked {what}. Grades reach Canvas ONLY through grader_push.py, which "
        "enforces the HG-5 instructor-review gate (issue #213).\n"
        "   Do this instead:\n"
        "     uv run python <toolkit>/lib/tools/grader_push.py --challenge-dir <dir> --mark-reviewed\n"
        "     uv run python <toolkit>/lib/tools/grader_push.py --challenge-dir <dir> --push\n"
        "   If grader_push.py is genuinely blocking you, surface that to the instructor — "
        "do NOT hand-write a Canvas API script to get around it."
    )


def evaluate(tool_name: str, tool_input: dict) -> str | None:
    """Return a denial reason if the tool call must be blocked, else None.

    Pure function — the whole decision, unit-testable without Claude Code.
    """
    tool_input = tool_input or {}

    if tool_name == "Bash":
        cmd = tool_input.get("command", "") or ""
        if _TOOLS_PATH.search(cmd):
            return None  # invoking the sanctioned tools is the safe path
        if _WRITE_VERB.search(cmd) and _CANVAS_CTX.search(cmd):
            return _redirect("a direct Canvas grade write in a shell command")
        return None

    if tool_name in ("Write", "Edit"):
        path = tool_input.get("file_path", "") or ""
        if _TOOLS_PATH.search(path):
            return None  # editing the reviewed tooling is allowed
        if _DOC_PATH.search(path):
            return None  # prose/docs — a code example is not an executable bypass
        # Write carries file_contents; Edit carries new_string.
        body = tool_input.get("file_contents") or tool_input.get("new_string") or ""
        if _WRITE_VERB.search(body) and _CANVAS_CTX.search(body):
            target = path or "a new file"
            return _redirect(f"Canvas grade-write code being written into {target}")
        return None

    if tool_name == "Read":
        path = tool_input.get("file_path", "") or ""
        if _FERPA_PATH.search(path):
            return (
                "⛔ FERPA Zone-2 file — do not Read it (AGENTS.md → FERPA discipline). "
                "Trust the tool's summary output; for verification use `wc -l` or `ls`, "
                "never Read/cat/grep on the name-bearing files."
            )
        return None

    return None


# ---------------------------------------------------------------------------
# Installer helpers — cb_init wires this hook into a course repo's settings.json.
# Single-sourced here so the matcher/command never drift from the hook itself.
# ---------------------------------------------------------------------------

HOOK_MATCHER = "Bash|Write|Edit|Read"


def hook_command(toolkit_subdir: str = "canvas-toolbox") -> str:
    """The PreToolUse `command` for a course repo. ${CLAUDE_PROJECT_DIR} is the
    course root; the toolkit is vendored under it at <toolkit_subdir>/."""
    return f'python3 "${{CLAUDE_PROJECT_DIR}}/{toolkit_subdir}/lib/tools/grade_guardian.py"'


def ensure_hook(settings: dict) -> tuple:
    """Idempotently add the grade_guardian PreToolUse hook to a settings dict.

    Returns (new_settings, changed). If any PreToolUse hook already references
    grade_guardian, returns the settings unchanged. Never mutates the input.
    """
    import copy
    settings = copy.deepcopy(settings) if settings else {}
    pre = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
    for entry in pre:
        for h in entry.get("hooks", []):
            if "grade_guardian" in (h.get("command") or ""):
                return settings, False
    pre.append({
        "matcher": HOOK_MATCHER,
        "hooks": [{"type": "command", "command": hook_command()}],
    })
    return settings, True


def main() -> int:
    if "--help" in sys.argv[1:]:
        print("PreToolUse hook (issue #213). Reads a tool call as JSON on stdin; "
              "exits 2 to block a direct Canvas grade write. Not an operator CLI.")
        return 0
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return 0  # fail open — never break the session on bad/empty input
    reason = evaluate(data.get("tool_name", ""), data.get("tool_input", {}))
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
    endpoint or grade payload). ALSO the RUN of an existing bypass script: for a
    `python x.py` / `uv run … x.py` command it reads x.py and blocks if the file
    body carries that write signature (the create/edit hooks can't catch a script
    that already exists, and the write is hidden inside the file). Invocations of
    the sanctioned tools under lib/tools/ are exempt. ALSO a raw READ of a FERPA
    Zone-2 file in the shell (`cat`/`head`/`tail`/`less`/python `open()` on
    .keymap.json et al.) — the Read-tool block below doesn't cover `cat`, so an agent
    denied Read reached for the shell to reconstruct the code↔user_id map (#270).
    Metadata (`wc`/`ls`/`stat`) and the sanctioned `grep <code> … | cut -f1,2`
    verification are not raw-display verbs and still pass; lib/tools/ readers exempt.
  - Write/Edit: creating/editing a file (outside lib/tools/) whose contents carry
    that same Canvas-write signature — this catches the bypass SCRIPT at creation,
    which is the only reliable catch (a Bash hook can't see inside `python x.py`).
  - Read: FERPA Zone-2 files (.deid_master.csv et al.) — the AGENTS.md discipline,
    enforced deterministically instead of by instruction (#212).

WHAT IT ASKS (does not deny — forces a human prompt) (#264, #265)
  - Bash: a grader_push.py AI-drafted checkpoint (not --grade-only / --test-user /
    --retract) — at BOTH --mark-reviewed (the review attestation) and --push (the
    write). grader_push honors --yes on that path (no terminal keystroke — that
    dead-ended non-technical faculty at a shell), so an agent could `--mark-reviewed
    --yes` and self-attest review without ever showing the human _all_comments.md,
    then push (#265). The hook returns permissionDecision "ask" at each checkpoint,
    forcing Claude Code to prompt the instructor; their in-chat click is the
    attestation the agent cannot skip or forge. (In full bypass-permissions mode
    nothing prompts — an explicit opt-out, honestly out of scope.)

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
import os
import re
import sys
from pathlib import Path

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
#
# ONE source list, two compiled forms. They were two hand-maintained regexes with a
# "kept in sync by hand" comment, and they had already drifted: one was case-sensitive
# and used `.*` where the other used `[^/\\]*`. Deriving both removes the hazard.
#
# `(pattern, anchor)` — anchor=True appends `$` in PATH form (a filename suffix, e.g.
# `.keymap.json`); anchor=False is a path fragment that can appear mid-path (e.g.
# `/submissions_raw/`). FILE form is never anchored: it matches anywhere in a shell
# command string, so the Bash branch catches `cat .keymap.json` (#270).
_ZONE2_DEFAULT: list[tuple[str, bool]] = [
    (r"\.deid_master\.csv", True),
    (r"\.known_names\.txt", True),
    (r"\.keymap\.json", True),
    (r"\.fetch_log\.json", True),
    (r"\.review\.csv", True),
    (r"/submissions_raw/", False),
    (r"feedback/_grader[^/\\]*\.csv", True),   # stricter of the two drifted forms
    # The one non-Canvas default, and it earns its place: a D2L/Brightspace Classlist
    # export is the complete identity join for a section — name, username, email, and
    # institutional id on one row per student. The consumer who reported #278 argued
    # no shipped pattern could anticipate it because the filename carries course code,
    # term and timestamp. True of those parts, but `Classlist_Export` is D2L's own
    # export naming and is invariant across institutions — so this IS anticipatable,
    # and it matters: the complaint is that the hook installs and enforces nothing, and
    # a consumer who never writes the config file below would still be unprotected on
    # the most identifying file they hold. Costs Canvas repos nothing (no Canvas
    # artifact is named this). Also matches it sitting in ~/Downloads, unanchored.
    (r"Classlist_Export[^/\\]*\.csv", True),
]

# Course-local additions (#278). The defaults are Canvas-workflow filenames; a
# consumer on another LMS has entirely different name-bearing files (a Brightspace
# course's are `_all_posts.md`, `_roster.json`, `txt_full/` — zero overlap), and
# before this the hook installed, reported `present`, and enforced an empty set for
# them. One regex per line, `#` comments and blanks ignored. Consumer patterns are
# NEVER anchored: over-matching only blocks more reads, under-matching leaks.
_ZONE2_EXTRA_FILE = ".claude/ferpa_zone2.txt"


def _course_root() -> Path | None:
    """The course root as Claude Code reports it to the hook. None outside a hook run."""
    d = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(d) if d else None


def load_zone2(course_root: Path | None = None) -> tuple[list[tuple[str, bool]], list[str]]:
    """Resolved Zone-2 entries + any extra lines that failed to compile.

    Invalid patterns are DROPPED rather than raised — a guardrail must never brick a
    session over a typo in a config file. They're returned so `zone2_summary()` can
    surface them, because a silently-ignored pattern is exactly the false sense of
    coverage this issue is about."""
    entries, invalid = list(_ZONE2_DEFAULT), []
    root = course_root if course_root is not None else _course_root()
    if root is None:
        return entries, invalid
    try:
        text = (root / _ZONE2_EXTRA_FILE).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return entries, invalid
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            re.compile(line)
        except re.error:
            invalid.append(line)
            continue
        entries.append((line, False))       # unanchored — see above
    return entries, invalid


def compile_zone2(entries: list[tuple[str, bool]]) -> tuple[re.Pattern, re.Pattern]:
    """(PATH form, FILE form) from one entry list. Both IGNORECASE — the PATH form
    used to be case-sensitive, which on a case-insensitive filesystem (macOS default)
    meant `Read .DEID_MASTER.csv` sailed through a block that `cat` caught."""
    path_src = "|".join(p + ("$" if anchor else "") for p, anchor in entries)
    file_src = "|".join(p for p, _ in entries)
    return (re.compile(path_src, re.IGNORECASE), re.compile(file_src, re.IGNORECASE))


def zone2_summary(course_root: Path | None = None) -> dict:
    """For `cb_update` to report — so `present` can't be read as 'covering your
    files'. {'default': int, 'extra': int, 'invalid': [str], 'source': str|None}."""
    entries, invalid = load_zone2(course_root)
    root = course_root if course_root is not None else _course_root()
    src = root / _ZONE2_EXTRA_FILE if root else None
    return {
        "default": len(_ZONE2_DEFAULT),
        "extra": len(entries) - len(_ZONE2_DEFAULT),
        "invalid": invalid,
        "source": str(src) if src and src.is_file() else None,
    }


_FERPA_PATH, _FERPA_FILE = compile_zone2(load_zone2()[0])

# Raw display / read of a file's contents. The constitution forbids these on Zone-2
# files ("not with Read, cat, head, tail, or bare grep"). Deliberately EXCLUDES the
# sanctioned filtered verification (`grep <code> .deid_master.csv | cut -d',' -f1,2`,
# and `wc -l`/`ls`/`stat`) — those don't dump raw rows, so they still pass.
_RAW_READ = re.compile(  # case-sensitive: match the `head` command, not git `HEAD`
    r"\b(cat|bat|head|tail|less|more|nl|xxd|od|strings)\b"
    r"|\bopen\s*\(|\.read(?:_text|lines)?\s*\(|\bjson\.load\b"
)


# A `*.py` token in a shell command — `python push.py`, `uv run … x.py`. The `\b`
# after `.py` avoids matching `.python`. Quotes/pipes/parens bound the token.
_SCRIPT_TOKEN = re.compile(r"[^\s;|&'\"()]+\.py\b")
_MAX_SCRIPT_BYTES = 200_000


def _extract_script_paths(cmd: str) -> list:
    """Every `*.py` path token a shell command runs (deduped, order-preserved)."""
    return list(dict.fromkeys(_SCRIPT_TOKEN.findall(cmd)))


def _read_script(path: str) -> str:
    """Best-effort read of a script the command executes, so the run-catch can see a
    Canvas write hidden INSIDE the file. Resolves a relative path against
    CLAUDE_PROJECT_DIR and CWD. Returns "" on any failure — fail OPEN, never brick a
    session because a path didn't resolve."""
    import os
    tried = []
    for base in ("", os.environ.get("CLAUDE_PROJECT_DIR") or "", os.getcwd()):
        c = path if (not base or os.path.isabs(path)) else os.path.join(base, path)
        if c in tried:
            continue
        tried.append(c)
        try:
            with open(c, "r", encoding="utf-8", errors="ignore") as fh:
                return fh.read(_MAX_SCRIPT_BYTES)
        except (OSError, ValueError):
            continue
    return ""


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
        # FERPA Zone-2 (#270): block a RAW read/display of a name-bearing file in a
        # shell (`cat .keymap.json`, `head .deid_master.csv`, python open()) — the
        # AGENTS.md rule enforced for Bash, not just the Read tool. An agent blocked
        # from Read otherwise reaches for `cat`; reading the code↔user_id map into
        # context IS the re-identification the two-zone model prevents. Sanctioned tools
        # that legitimately read these (grader_reidentify) run via lib/tools/ → exempt.
        # Metadata (`wc`/`ls`/`stat`) and the sanctioned `grep <code> … | cut -f1,2`
        # verification aren't raw-display verbs, so they still pass.
        if ("/lib/tools/" not in cmd.replace("\\", "/")
                and _RAW_READ.search(cmd) and _FERPA_FILE.search(cmd)):
            return (
                "⛔ FERPA Zone-2 file — never cat/head/read it in a shell (AGENTS.md → FERPA "
                "discipline). It maps de-id codes ↔ names/user_ids; reading it into context "
                "IS the re-identification the two-zone model prevents. Verify with `wc -l` / "
                "`ls` only. To re-identify, run grader_reidentify.py (it reads the keymap "
                "internally, never surfacing it) — do NOT reconstruct the map by hand."
            )
        # Run-catch: executing an EXISTING script whose BODY writes to Canvas. The
        # create (Write) / edit (Edit) hooks can't catch a script that already
        # exists, and the command string alone hides the write inside the file —
        # `python push.py` has no write verb. Read each *.py the command runs (skip
        # the sanctioned lib/tools/, which legitimately contains Canvas writes) and
        # block if its body carries the grade-write signature. This is the same
        # regex-not-a-firewall limit noted above; it decisively stops a plain
        # `python push.py` bypass, the actual field failure mode.
        for script in _extract_script_paths(cmd):
            if "/lib/tools/" in ("/" + script.replace("\\", "/")):
                continue  # the reviewed tooling — running it is the safe path
            body = _read_script(script)
            if body and _WRITE_VERB.search(body) and _CANVAS_CTX.search(body):
                return _redirect(f"running {script} — it writes grades to Canvas directly")
        return None

    if tool_name in ("Write", "Edit"):
        path = tool_input.get("file_path", "") or ""
        if _TOOLS_PATH.search(path):
            return None  # editing the reviewed tooling is allowed
        if _DOC_PATH.search(path):
            return None  # prose/docs — a code example is not an executable bypass
        # Write sends the body as `content` (Claude Code's actual tool param); Edit
        # sends `new_string`. `file_contents` is a legacy/alt key kept for safety.
        # Reading the WRONG key silently blinds this catch — the bug that let a
        # hand-written push script sail through (the guard read `file_contents`
        # while the real payload used `content`). Check every plausible key.
        body = (tool_input.get("content") or tool_input.get("file_contents")
                or tool_input.get("new_string") or "")
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
# ASK layer (#264, #265): force a human permission prompt at BOTH AI-drafted
# checkpoints — the review attestation (--mark-reviewed) AND the push (--push).
# grader_push honors --yes there (no terminal keystroke), so an agent could run
# `--mark-reviewed --yes` and self-attest review without ever showing the human
# _all_comments.md, then push (#265). Firing the prompt at --mark-reviewed too
# means the instructor must click to attest review — the agent cannot skip it.
# ---------------------------------------------------------------------------

# What kind of AI-drafted checkpoint a grader_push command is — the moments a human
# must consciously click. The value-only (--grade-only), test (--test-user), and
# retract (--retract) paths are NOT AI-drafted-comment checkpoints.
_CHECKPOINT_REASONS = {
    "review": (
        "Review gate (HG-5, #265): the agent is attesting it reviewed the AI-drafted "
        "comments. Approve ONLY if it has shown you the actual comments "
        "(feedback/_all_comments.md) in this chat. If it hasn't, Deny and make it show "
        "you first — do not attest a review you didn't do."
    ),
    "push": (
        "Push gate (HG-5, #264): this sends AI-drafted feedback + grades to students on "
        "a LIVE course. Approve only after reviewing the comments and the old→new grade "
        "preview the agent showed you. Allow = send; Deny = hold."
    ),
}


def _grader_push_checkpoint(cmd: str) -> str | None:
    """Return 'push' or 'review' if this grader_push command is an AI-drafted
    human-checkpoint moment, else None. --push wins if both flags are present."""
    if "grader_push" not in cmd:
        return None
    if any(re.search(re.escape(f) + r"\b", cmd)
           for f in ("--grade-only", "--test-user", "--retract")):
        return None                                   # not the AI-drafted-comment path
    if re.search(r"--push\b", cmd):
        return "push"
    if re.search(r"--mark-reviewed\b", cmd):
        return "review"
    return None


def ask_reason(tool_name: str, tool_input: dict) -> str | None:
    """Return a permission-prompt reason if this call is an AI-drafted grade checkpoint
    (review attestation or push) the instructor must click, else None. Pure function —
    unit-testable without Claude Code. main() turns a non-None reason into a
    permissionDecision 'ask'."""
    tool_input = tool_input or {}
    if tool_name != "Bash":
        return None
    kind = _grader_push_checkpoint(tool_input.get("command", "") or "")
    return _CHECKPOINT_REASONS.get(kind)


# ---------------------------------------------------------------------------
# Installer helpers — cb_init wires this hook into a course repo's settings.json.
# Single-sourced here so the matcher/command never drift from the hook itself.
# ---------------------------------------------------------------------------

HOOK_MATCHER = "Bash|Write|Edit|Read"


def hook_command(toolkit_subdir: str = "canvas-toolbox") -> str:
    """The PreToolUse `command` for a course repo. ${CLAUDE_PROJECT_DIR} is the
    course root; the toolkit is vendored under it at <toolkit_subdir>/.

    FAILS OPEN if the guardian script is missing (a wrong path, a rename, an
    uninstalled toolkit): a guardrail must NEVER brick a session because it can't
    find itself. A bare `python3 <missing>` exits non-zero (Python's can't-open is
    exit 2 = the "deny" code), which would block EVERY tool call — including the
    Read/Edit you'd need to fix it. So: if the file is absent, `exit 0` (allow);
    if present, `exec` hands off so the guardian's own exit code (2 = deny)
    propagates unchanged.
    """
    path = f'$CLAUDE_PROJECT_DIR/{toolkit_subdir}/lib/tools/grade_guardian.py'
    return f'sh -c \'f="{path}"; [ -f "$f" ] || exit 0; exec python3 "$f"\''


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


def _emit_ask(reason: str) -> None:
    """Print the PreToolUse JSON that forces Claude Code to prompt the instructor
    (permissionDecision 'ask'). Exit 0 accompanies it — stdout JSON drives the
    decision; exit 2 would instead hard-block (deny)."""
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }}))


def main() -> int:
    if "--help" in sys.argv[1:]:
        print("PreToolUse hook (issue #213/#264). Reads a tool call as JSON on stdin; "
              "exits 2 to block a direct Canvas grade write, or emits an 'ask' JSON to "
              "prompt the instructor before an AI-drafted grade push. Not an operator CLI.")
        return 0
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return 0  # fail open — never break the session on bad/empty input
    tool_name, tool_input = data.get("tool_name", ""), data.get("tool_input", {})
    reason = evaluate(tool_name, tool_input)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    ask = ask_reason(tool_name, tool_input)
    if ask:
        _emit_ask(ask)
    return 0


if __name__ == "__main__":
    sys.exit(main())

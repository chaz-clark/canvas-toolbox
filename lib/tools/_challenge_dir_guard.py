"""
FERPA guard for --challenge-dir resolution — issue #44 fix.

WHAT IT GUARDS AGAINST
  Real incident: ds250-onln-master, 2026-06-04. Operator ran grader tools
  via `uv run --directory canvas-toolbox python lib/tools/grader_fetch.py
  --challenge-dir grading/<asg> ...`. `uv run --directory` sets cwd = the
  toolkit clone, so the RELATIVE `--challenge-dir grading/<asg>` resolved
  to `canvas-toolbox/grading/<asg>/` — INSIDE the toolkit clone, not the
  consumer course repo. 20 students' submissions + the keymap landed in
  the clone before the misconfiguration was noticed. The toolkit's own
  .gitignore did not (at the time) cover grading/ patterns; one `git
  add -A` would have committed the PII to the public repo.

DEFENSE IN DEPTH (issue #44 has two layers)
  1. BELT: canvas-toolbox/.gitignore now mirrors scaffold/grading/.gitignore
     — even if PII lands inside the clone via misconfiguration, git can't
     see it.
  2. SUSPENDERS (this file): every grader tool's --challenge-dir resolution
     goes through `resolve_challenge_dir()` below. It refuses (sys.exit 7)
     if the resolved path is inside the toolkit install directory, with
     a clear error message + three explicit fix options. Surfaces the
     configuration error LOUDLY before any PII is written.

WHY BOTH
  The gitignore is silent — it works without the operator knowing. But it
  doesn't prevent the bug; it just makes the bug uncommittable. The guard
  REFUSES the misconfigured run entirely, so the operator sees and fixes
  the cwd problem immediately. Together: PII can't land + if it somehow
  did, it can't commit.

USAGE — every tool that takes --challenge-dir
  Replace:
      cd = Path(args.challenge_dir)
  with:
      cd = resolve_challenge_dir(args.challenge_dir)

  The function returns an absolute Path (so all downstream subpath math
  stays unambiguous) and prints `writing submissions to <abs path>` to
  stderr so the operator sees where PII will land.

WHAT'S NOT A LEAK
  Printing the absolute path itself is not PII. The path is the operator's
  own filesystem layout; it doesn't reveal student identity. The same is
  true of the exit-code-7 refusal message — it names the toolkit install
  dir, not any student data.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Sentinel exit code so wrappers (CI, hermes, scripts) can detect a FERPA
# guard refusal distinctly from other failure modes.
FERPA_GUARD_REFUSED_EXIT = 7


def _toolkit_root() -> Path:
    """The canvas-toolbox install directory's root. Computed from __file__'s
    location: lib/tools/_challenge_dir_guard.py → lib/tools/ → lib/ → root."""
    return Path(__file__).resolve().parent.parent.parent


def _inside(child: Path, parent: Path) -> bool:
    """True iff `child` is (or is inside) `parent`. Path.is_relative_to() is
    Python 3.9+; we use try/relative_to for compatibility with the toolkit's
    >=3.14 floor (the same idiom appears throughout canvas-toolbox)."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_challenge_dir(arg: str, *, verb: str = "writing") -> Path:
    """Resolve a --challenge-dir argument to an absolute Path. Refuses
    (sys.exit FERPA_GUARD_REFUSED_EXIT) if the resolved path is inside
    the canvas-toolbox install directory.

    Prints `<verb> to <abs path>` to stderr so the operator sees exactly
    where PII will land — surfaces the bug LOUDLY before any write.

    Args:
        arg: The raw --challenge-dir CLI argument (may be relative).
        verb: The action verb to print (e.g. "writing", "reading",
              "deidentifying"). Default "writing" since most callers
              are write tools.

    Returns:
        The absolute, resolved Path. Callers can pass this directly to
        downstream subpath construction (`cd / "submissions_raw"`, etc.)
        without further .resolve() calls.

    Exits:
        Sys.exit(FERPA_GUARD_REFUSED_EXIT) when the resolved path is
        inside the toolkit install directory. The exit message names
        the resolved path + the toolkit dir + three explicit fix
        options.
    """
    cd = Path(arg).expanduser().resolve()
    toolkit_root = _toolkit_root()

    if _inside(cd, toolkit_root):
        print(
            "\n"
            "╔══════════════════════════════════════════════════════════════════╗\n"
            "║ FERPA GUARD REFUSED — issue #44                                  ║\n"
            "╚══════════════════════════════════════════════════════════════════╝\n"
            "\n"
            f"--challenge-dir resolves to:\n"
            f"  {cd}\n"
            "\n"
            f"...which is INSIDE the canvas-toolbox install directory:\n"
            f"  {toolkit_root}\n"
            "\n"
            "Writing PII inside the toolkit clone is a real FERPA hazard\n"
            "(real incident: ds250-onln-master 2026-06-04 — 20 students'\n"
            "submissions landed in the clone before the misconfiguration\n"
            "was noticed). The toolkit's .gitignore catches this case as a\n"
            "belt; this guard is the suspenders.\n"
            "\n"
            "FIX ONE OF:\n"
            "\n"
            "  1. Pass an ABSOLUTE --challenge-dir outside the toolkit clone:\n"
            "       --challenge-dir /Users/you/<course-repo>/grading/<asg>\n"
            "\n"
            "  2. cd to your course-repo root before running:\n"
            "       cd /Users/you/<course-repo>\n"
            "       uv run python canvas-toolbox/lib/tools/<tool>.py \\\n"
            "         --challenge-dir grading/<asg> ...\n"
            "\n"
            "  3. Drop `--directory canvas-toolbox` from your uv run command.\n"
            "     (That's what caused the misconfigured cwd in the original\n"
            "     incident.)\n"
            "\n"
            "See issue #44 for full context.\n",
            file=sys.stderr,
        )
        sys.exit(FERPA_GUARD_REFUSED_EXIT)

    # Path is outside the toolkit — surface it so the operator sees where
    # PII will land. To stderr so it doesn't pollute --json output.
    # (Callers pass the preposition in their verb — e.g. "fetching to",
    # "computing consensus in" — so the helper doesn't add one.)
    print(f"{verb} {cd}", file=sys.stderr)
    return cd

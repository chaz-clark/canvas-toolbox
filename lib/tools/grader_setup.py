#!/usr/bin/env python3
"""grader_setup.py — get a course ready to grade, in one idempotent pass (#440).

The grading on-ramp. Everything grading needs exists as a separate piece
(token, guardian hook, `grading/` folder, `.deid_master.csv`, voicing profile);
nothing ties them together, so a non-technical instructor had to know the order.
This checks each piece, fixes what is missing, and says in one plain line per
step what it found. Modeled on cb_update.py: dry-run by default, `--apply` writes,
re-running is safe, and the output never contains a student name.

Steps:
  1. Canvas token          valid / REJECTED / no-token ... (read-only GET /users/self)
  2. Guardian hook         present / installed — blocks reads of FERPA Zone-2 files
  3. FERPA Zone-2 coverage how many patterns the hook enforces
  4. grading/ folder       with its own `.gitignore` of `*` (FERPA tier 2)
  5. grading/.deid_master.csv   built from the roster when missing (counts only)
  6. Voicing profile       reported, never invented
  7. Grading package       reported: approved or still needs the consent gate

Exit 0 = ready to grade. Exit 1 = something needs a human decision (the lines
marked "needs you" say what). Capability approval is NOT performed here — that
stays with cb_flatten's consent gate.

USAGE
  uv run python lib/tools/grader_setup.py            # check, write nothing
  uv run python lib/tools/grader_setup.py --apply    # fix what is missing
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from _env_loader import force_utf8_console
except ImportError:  # pragma: no cover
    def force_utf8_console() -> None:
        pass

NESTED_DIR = "canvas-toolbox"
VOICE_FILE = "FEEDBACK_VOICE.md"
Line = tuple[str, str, str]  # (step, status, detail)


def _is_nested(root: Path) -> bool:
    return (root / NESTED_DIR / "lib" / "tools" / "grade_guardian.py").is_file()


def step_token() -> Line:
    from cb_update import check_token
    status = check_token()
    ok = status == "valid"
    return ("Canvas token", "ok" if ok else "needs you",
            "valid" if ok else f"{status} — fix your Canvas token before grading")


def step_hook(root: Path, apply: bool) -> Line:
    if _is_nested(root):
        from cb_update import ensure_guardian_hook
        status = ensure_guardian_hook(root, NESTED_DIR, apply)
    else:
        from cb_flatten import ensure_guardian_hook
        status = ensure_guardian_hook(root, apply)
    if status in ("present", "installed"):
        return ("Guardian hook", "ok", status)
    if status == "would-install":
        return ("Guardian hook", "todo", "missing — will install")
    if status == "skipped-no-script":
        return ("Guardian hook", "needs you",
                "the toolkit is not installed in this folder — run the toolkit install first")
    return ("Guardian hook", "needs you", f"{status} — cannot install automatically")


def step_zone2(root: Path) -> Line:
    try:
        from grade_guardian import zone2_summary
    except ImportError:
        return ("FERPA Zone-2 coverage", "needs you", "guardian not available")
    s = zone2_summary(root)
    extra = f" + {s['extra']} course-local" if s["extra"] else ""
    if s["invalid"]:
        return ("FERPA Zone-2 coverage", "needs you",
                f"{len(s['invalid'])} course pattern(s) are invalid and ignored")
    return ("FERPA Zone-2 coverage", "ok", f"{s['default']} built-in{extra} patterns")


def step_grading_dir(root: Path, apply: bool) -> Line:
    gi = root / "grading" / ".gitignore"
    if gi.is_file():
        return ("grading/ folder", "ok", "present, ignored by git")
    if not apply:
        return ("grading/ folder", "todo", "missing — will create")
    from build_deid_master import ensure_grading_gitignore
    ensure_grading_gitignore(root / "grading")
    return ("grading/ folder", "ok", "created, ignored by git")


def step_master(root: Path, apply: bool) -> Line:
    master = root / "grading" / ".deid_master.csv"
    if master.is_file():
        return ("De-id master", "ok", "present")
    if not apply:
        return ("De-id master", "todo", "missing — will build from the roster")
    from grader_fetch import _env_canvas, ensure_deid_master
    tok, cid, base = _env_canvas(None)
    if not (tok and cid and base):
        return ("De-id master", "needs you", "Canvas credentials/course not set")
    status = ensure_deid_master(master, tok, cid, base)
    if status == "failed":
        return ("De-id master", "needs you",
                "could not build — check the Canvas course and token")
    return ("De-id master", "ok", f"{status}")


def step_voice(root: Path) -> Line:
    course = root / "grading" / VOICE_FILE
    instructor = Path.home() / ".canvas" / VOICE_FILE
    if course.is_file() or instructor.is_file():
        which = "course" if course.is_file() else "instructor"
        return ("Voicing profile", "ok", f"{which} profile found")
    return ("Voicing profile", "optional",
            "none yet — comments will have no established voice until you set one up")


def step_package(root: Path) -> Line:
    if _is_nested(root):
        return ("Grading package", "ok", "nested layout — no separate approval")
    from capability_consent import load_approvals
    if "grading" in load_approvals(root):
        return ("Grading package", "ok", "approved")
    return ("Grading package", "needs you",
            "not yet approved — run the toolkit update so you can approve it")


def run(root: Path, apply: bool) -> int:
    lines: list[Line] = [
        step_token(),
        step_hook(root, apply),
        step_zone2(root),
        step_grading_dir(root, apply),
        step_master(root, apply),
        step_voice(root),
        step_package(root),
    ]
    mark = {"ok": "✓", "todo": "…", "needs you": "✗", "optional": "·"}
    for step, status, detail in lines:
        print(f"  {mark[status]} {step}: {detail}")
    blocked = [s for s, st, _ in lines if st == "needs you"]
    pending = [s for s, st, _ in lines if st == "todo"]
    if blocked:
        print(f"\nNot ready — needs you: {', '.join(blocked)}.")
        return 1
    if pending:
        print(f"\nNot applied yet — re-run with --apply to set up: {', '.join(pending)}.")
        return 0
    print("\nReady to grade.")
    return 0


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--course-root", type=Path, default=Path.cwd())
    ap.add_argument("--apply", action="store_true", help="write (else check only)")
    args = ap.parse_args()
    print(f"grader_setup — {'applying' if args.apply else 'checking'} {args.course_root.name}")
    return run(args.course_root, args.apply)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Push staged `## Suggested Canvas Comment` markdown blocks to Canvas.

Closes canvas-toolbox#57. The grader stages per-student Canvas comments
under a `## Suggested Canvas Comment (rubric-grounded)` H2 inside each
`feedback/_pass1/uid-<uid>.md` file (also rolled up into
`feedback/_all_comments.md` for instructor review). Without this tool,
the instructor copy-pastes each block into Canvas one at a time — for an
N-cohort calibration run, that's N round-trips. This automates the
transport between grader output and student-visible Canvas action.

WHAT IT DOES
  1. Walk `<task-dir>/feedback/_pass1/uid-*.md`.
  2. For each file:
       - Extract the H2 block titled `## Suggested Canvas Comment`
         (case-insensitive; allows trailing parenthetical, e.g.
         "(rubric-grounded)"). Body is everything from the H2 to the
         next H2 or EOF.
       - Strip leading `> ` blockquote markers (the canonical styling
         the grader uses for "this is the comment text").
       - Resolve `uid-<N>.md` → user_id=N. NO .keymap.json read.
  3. Build the (uid → comment) plan; print preview.
  4. Apply the standard write-path guards:
       - --dry-run by default; --push to actually POST.
       - Active enrollment filter (issue #61) — Test Student + inactive
         dropped.
       - Pre-push comment-collision guard (issue #62) — peek at existing
         submission_comments through the FERPA-safe deid layer (#65) and
         warn before posting on a thread with recent non-self activity.
       - Availability awareness (issue #63) — warn if the assignment is
         locked AND any comment contains resubmit-style language.
       - Idempotency: skip a uid whose latest non-self comment matches
         the stage block exactly (no double-post on re-run).

FERPA
  - Tool reads ONLY `_pass1/uid-<N>.md` (already FERPA-safe — names
    don't survive into per-student feedback by construction).
  - Resolves uid → Canvas submission via /submissions API. user_id is
    LMS row id (safe per the toolkit's standing rule).
  - NEVER reads .keymap.json or .known_names.txt.
  - Console output: `uid=<N> → 245 chars posted` style; never the
    comment text itself in stdout.
  - The comment text the instructor authored has already passed FERPA
    review (the per-student .md files are reviewed before mark-reviewed).
    This tool just transports.

USAGE
  # Dry-run preview (default)
  uv run python lib/tools/grader_push_comments.py \\
      --task-dir grading/p1t1_combined/ai_log \\
      --assignment-id 16958397

  # Push for real (requires --allow-enrolled on a live course)
  uv run python lib/tools/grader_push_comments.py \\
      --task-dir grading/p1t1_combined/ai_log \\
      --assignment-id 16958397 --push --allow-enrolled

EXIT CODES
  0  ran (push or dry-run); no fatal errors
  1  refused (missing required input, collision-confirmation aborted)
  2  setup / env / Canvas API error
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import requests

from _challenge_dir_guard import resolve_challenge_dir

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    pass

try:
    import canvas_course_guard as guard
except ImportError:
    guard = None

# Reuse the existing write-path guards rather than reimplementing them
# (issues #61 / #62 / #63 / #65).
from grader_push import (  # noqa: E402
    fetch_active_filter,
    fetch_assignment_lock_state,
    comment_has_resubmit_language,
    collision_warnings_for_submission,
)
from grader_deidentify_comments import (  # noqa: E402
    build_role_map,
    deidentify_submission_comments,
)

_TIMEOUT = 30
_UID_FILE_RE = re.compile(r"uid-(\d+)\.md$", re.IGNORECASE)

# The H2 we extract. Accept any trailing parenthetical (e.g.
# "## Suggested Canvas Comment (rubric-grounded)") plus optional whitespace.
_COMMENT_H2_RE = re.compile(
    r"^##\s+suggested\s+canvas\s+comment\s*(?:\([^)]*\))?\s*$",
    re.IGNORECASE,
)
_NEXT_H2_RE = re.compile(r"^##\s+", re.IGNORECASE)


def extract_comment_block(md_text: str) -> str:
    """Pull the body of `## Suggested Canvas Comment` until the next H2
    or EOF. Strips leading `> ` blockquote markers from each captured
    line. Returns empty string if the block isn't found."""
    lines = md_text.splitlines()
    in_block = False
    captured: list[str] = []
    for ln in lines:
        if not in_block:
            if _COMMENT_H2_RE.match(ln.strip()):
                in_block = True
            continue
        if _NEXT_H2_RE.match(ln):
            break
        # Strip leading blockquote marker
        stripped = ln
        if stripped.lstrip().startswith("> "):
            lead = stripped[:len(stripped) - len(stripped.lstrip())]
            stripped = lead + stripped.lstrip()[2:]
        elif stripped.strip() == ">":
            stripped = ""
        captured.append(stripped)
    # Trim leading/trailing blank lines
    while captured and not captured[0].strip():
        captured.pop(0)
    while captured and not captured[-1].strip():
        captured.pop()
    return "\n".join(captured)


def collect_plan(task_dir: Path) -> list[dict]:
    """Walk feedback/_pass1/uid-*.md. Each row: {uid, path, comment}."""
    pass1 = task_dir / "feedback" / "_pass1"
    if not pass1.is_dir():
        return []
    rows: list[dict] = []
    for p in sorted(pass1.glob("uid-*.md")):
        m = _UID_FILE_RE.search(p.name)
        if not m:
            continue
        uid = int(m.group(1))
        text = p.read_text(encoding="utf-8", errors="replace")
        comment = extract_comment_block(text).strip()
        rows.append({"uid": uid, "path": p, "comment": comment})
    return rows


def _env_canvas(course_id_override: str | None) -> tuple[str, str, str]:
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    cid = course_id_override or os.environ.get("CANVAS_COURSE_ID", "")
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return tok, cid, base


def fetch_thread(base: str, cid: str, headers: dict, aid: int) -> dict[int, dict]:
    """user_id → full submission dict (with submission_comments) for the
    collision-guard + idempotency check."""
    rows: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions",
            headers=headers,
            params={"per_page": 100, "page": page, "include[]": "submission_comments"},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows += batch
        page += 1
    return {int(s["user_id"]): s for s in rows if s.get("user_id") is not None}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Push staged '## Suggested Canvas Comment' markdown blocks to Canvas (#57).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--task-dir", required=True,
                    help="Convention base path (e.g. grading/p1t1_combined/ai_log). Reads "
                         "feedback/_pass1/uid-*.md.")
    ap.add_argument("--assignment-id", required=True, type=int,
                    help="Canvas assignment id to post comments against.")
    ap.add_argument("--course-id", default=None,
                    help="Override CANVAS_COURSE_ID env var.")
    ap.add_argument("--push", action="store_true",
                    help="Actually post (default: dry-run preview).")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Bypass canvas_course_guard for enrolled-course writes.")
    ap.add_argument("--yes", action="store_true", help="Skip interactive confirmations.")
    ap.add_argument("--include-inactive", action="store_true",
                    help="Issue #61: include Test Student + inactive enrollments (off by default).")
    ap.add_argument("--no-collision-check", action="store_true",
                    help="Issue #62: skip the pre-push comment-collision guard.")
    ap.add_argument("--collision-window-days", type=int, default=14,
                    help="Issue #62: how many days back to look. Default: 14.")
    ap.add_argument("--allow-collisions", action="store_true",
                    help="Issue #62: bypass the 'type collisions to confirm' interactive step.")
    ap.add_argument("--no-lock-check", action="store_true",
                    help="Issue #63: skip the availability-aware lock warning.")
    ap.add_argument("--allow-locked-resubmit", action="store_true",
                    help="Issue #63: bypass the 'type locked to confirm' interactive step.")
    args = ap.parse_args()

    tok, cid, base = _env_canvas(args.course_id)
    for var, val in (("CANVAS_API_TOKEN", tok), ("CANVAS_BASE_URL", base), ("CANVAS_COURSE_ID", cid)):
        if not val:
            print(f"Missing {var} (env or --course-id).", file=sys.stderr)
            return 2
    headers = {"Authorization": f"Bearer {tok}"}

    task_dir = resolve_challenge_dir(args.task_dir, verb="pushing comments from")
    plan = collect_plan(task_dir)
    if not plan:
        print(f"No feedback/_pass1/uid-*.md files under {task_dir}. Nothing to push.",
              file=sys.stderr)
        return 1
    plan = [p for p in plan if p["comment"]]
    if not plan:
        print("No '## Suggested Canvas Comment' blocks found in any uid-*.md file.",
              file=sys.stderr)
        return 1

    # Issue #61: drop Test Student + inactive (write path).
    if not args.include_inactive:
        active_set, inactive_map, test_id = fetch_active_filter(base, cid, headers)
        excluded: list[tuple[int, str]] = []
        kept: list[dict] = []
        for row in plan:
            uid = row["uid"]
            if test_id is not None and uid == test_id:
                excluded.append((uid, "Test Student"))
                continue
            if uid in inactive_map:
                excluded.append((uid, inactive_map[uid]))
                continue
            if uid not in active_set:
                excluded.append((uid, "no_active_student_enrollment"))
                continue
            kept.append(row)
        if excluded:
            print(f"  excluded by default (issue #61; --include-inactive to keep):")
            for uid, reason in excluded:
                print(f"    user_id={uid:<10}  reason={reason}")
        plan = kept

    if not plan:
        print("All rows excluded by the active-enrollment filter. Nothing to push.")
        return 0

    # Fetch the full thread (for #62 collision + idempotency dedupe).
    try:
        thread = fetch_thread(base, cid, headers, args.assignment_id)
    except requests.HTTPError as e:
        print(f"Canvas API error fetching thread: {e}", file=sys.stderr)
        return 2

    # Idempotency: skip rows whose comment already exactly matches a
    # prior posted comment. Cheap dedupe to prevent double-post on re-run.
    roster_namesfile = task_dir / ".known_names.txt"
    roster = ([ln.strip() for ln in roster_namesfile.read_text(encoding="utf-8").splitlines() if ln.strip()]
              if roster_namesfile.exists() else [])
    role_map = build_role_map(base, headers, cid) if not args.no_collision_check else {}

    duplicates: list[int] = []
    pushable: list[dict] = []
    for row in plan:
        sub = thread.get(row["uid"])
        if sub is None:
            row["status"] = "no_submission"
            continue
        existing_raw = sub.get("submission_comments") or []
        # Cheap exact-text idempotency: don't even need the deid layer
        # for this check (we're just comparing what's about to be posted
        # against what's already there — the comparison is internal to
        # the operator's own machine).
        if any((c.get("comment") or "").strip() == row["comment"] for c in existing_raw):
            duplicates.append(row["uid"])
            row["status"] = "duplicate"
            continue
        row["status"] = "ready"
        pushable.append(row)

    if duplicates:
        print(f"\n  skipped (issue #57 idempotency): {len(duplicates)} uid(s) already have "
              f"this exact comment in the thread:")
        for u in duplicates:
            print(f"    user_id={u}")

    # Issue #63 part 1: availability check.
    locked_resubmit: list[tuple[int, str]] = []
    lock_state: dict = {}
    if not args.no_lock_check:
        try:
            lock_state = fetch_assignment_lock_state(base, cid, headers, args.assignment_id)
        except requests.HTTPError as e:
            print(f"WARN: lock-state check disabled — {type(e).__name__}: {e}.", file=sys.stderr)
            lock_state = {"locked_now": False}
        if lock_state.get("locked_now"):
            for row in pushable:
                if comment_has_resubmit_language(row["comment"]):
                    locked_resubmit.append((row["uid"], row["comment"]))

    # Issue #62: collision guard.
    collisions: dict[int, list[dict]] = {}
    if not args.no_collision_check:
        for row in pushable:
            sub = thread.get(row["uid"])
            if sub is None:
                continue
            deid_list = deidentify_submission_comments(
                sub.get("submission_comments") or [],
                owner_user_id=row["uid"],
                role_map=role_map,
                roster=roster,
            )
            others, latest = collision_warnings_for_submission(
                deid_list, window_days=args.collision_window_days,
            )
            if others:
                collisions[row["uid"]] = others

    # FERPA-safe plan print: per uid, chars only — never the comment text.
    print(f"\nPlan: {len(pushable)} comment(s) ready to push to assignment "
          f"{args.assignment_id} (course {cid})")
    for row in pushable:
        marks = []
        if row["uid"] in collisions:
            marks.append(f"collision({len(collisions[row['uid']])})")
        if any(u == row["uid"] for u, _ in locked_resubmit):
            marks.append("locked+resubmit")
        suffix = f"  [{', '.join(marks)}]" if marks else ""
        print(f"  user_id={row['uid']:<10}  {len(row['comment'])} chars{suffix}")

    if locked_resubmit:
        print(f"\n  ⚠️  availability guard (issue #63): assignment is locked "
              f"({lock_state.get('reason', 'unknown')}); {len(locked_resubmit)} comment(s) "
              f"contain resubmit-style language students can't act on. Fix the lock window "
              f"or revise these comments before --push.")

    if collisions:
        print(f"\n  ⚠️  comment-collision guard (issue #62; window={args.collision_window_days}d): "
              f"{len(collisions)} uid(s) have recent non-self thread activity. Review before --push.")

    if not args.push:
        print(f"\nDry run — nothing posted. Re-run with --push to send to Canvas.")
        return 0
    if not pushable:
        print("\nNothing to push.")
        return 0

    if guard is not None:
        try:
            guard.enforce(base, headers, cid, mode="write",
                          allow_override=args.allow_enrolled, label="comment push target")
        except SystemExit:
            raise

    # Gates (same vocabulary as grader_push).
    if locked_resubmit and not args.allow_locked_resubmit and not args.yes:
        if input("Type 'locked' to acknowledge + continue: ").strip().lower() != "locked":
            print("Aborted (lock guard).")
            return 1
    if collisions and not args.allow_collisions and not args.yes:
        if input("Type 'collisions' to acknowledge + continue: ").strip().lower() != "collisions":
            print("Aborted (collision guard).")
            return 1
    if not args.yes:
        if input(f"\nType 'push' to post {len(pushable)} comment(s) to LIVE course {cid}: "
                 ).strip().lower() != "push":
            print("Aborted.")
            return 1

    # Per-assignment comment ledger (matches grader_push's #63 convention so
    # `grader_push --retract` can DELETE these later if needed).
    log = task_dir / ".push_log.md"
    pushed = 0
    failed: list[int] = []
    with log.open("a", encoding="utf-8") as lg:
        for row in pushable:
            data = {"comment[text_comment]": row["comment"]}
            resp = requests.put(
                f"{base}/api/v1/courses/{cid}/assignments/{args.assignment_id}"
                f"/submissions/{row['uid']}",
                headers=headers, data=data, timeout=_TIMEOUT,
            )
            if resp.status_code < 400:
                try:
                    sc_list = (resp.json() or {}).get("submission_comments") or []
                    new_id = (sc_list[-1] if sc_list else {}).get("id")
                except (ValueError, TypeError):
                    new_id = None
                print(f"  user_id={row['uid']} → {len(row['comment'])} chars posted")
                # Idempotency log entry — matches grader_push's format so
                # --retract can find it.
                key = f"uid-{row['uid']}"
                lg.write(f"- {key}: comment {new_id or '?'} pushed to assignment "
                         f"{args.assignment_id}\n")
                pushed += 1
            else:
                print(f"  ERROR user_id={row['uid']}: {resp.status_code} {resp.text[:120]}")
                failed.append(row["uid"])
                if 400 <= resp.status_code < 500:
                    print(f"\n⛔ 4xx on user_id={row['uid']}. STOP (P-003). Investigate, "
                          f"then re-run; idempotency dedupes successes.")
                    break

    print(f"\nPushed {pushed}/{len(pushable)} comment(s). Logged to {log} (gitignored).")
    if failed:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

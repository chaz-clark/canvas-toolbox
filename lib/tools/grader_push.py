#!/usr/bin/env python3
"""
Push finalized grades + comments to Canvas — LOCAL only, behind required review gate.

Part of the canvas-toolbox generic grader skill (v0.1). See:
  - lib/agents/canvas_grader.md (operator-facing pipeline guide)
  - lib/agents/knowledge/grader_knowledge.md §10 (push gate, idempotency, canvas_course_guard)

WHAT IT DOES
  Reads the LOCAL review sheet (.review.csv from grader_reidentify.py) and the
  per-student feedback files; resolves Canvas user_id by matching the original
  filename's embedded numeric IDs against the submissions API; writes
  `posted_grade` (+ optional `comment[text_comment]`) via PUT to
  /api/v1/courses/:id/assignments/:aid/submissions/:user_id.

  FERPA: pushing instructor → Canvas is the authorized owner writing to the system
  of record — NOT disclosure to a third party — so it's allowed in the LOCAL zone.
  No student name is fetched or printed; console shows keys + grades + comment
  previews only. Identity resolution is local via the numeric IDs in
  Canvas-format filenames.

GUARDRAILS (no override on the first three)
  1. --mark-reviewed REQUIRED before --push. Marker auto-invalidates if any
     comment file mtime > marker mtime (you can't approve a state and then
     mutate it).
  2. canvas_course_guard refuses live-course writes unless --allow-enrolled
     is passed. The toolkit's standing safety bar.
  3. Per-assignment idempotency. Keys already in the .push_log.md scoped to
     THIS assignment ID are skipped; --force overrides. Multi-output flows
     (one submission → N grades → N Canvas items) don't shadow each other.
  4. Test Student first (operator-explicit). Run with --test-user <id> before
     the real batch.
  5. **Issue #61** — push surface excludes Canvas's Test Student + inactive/
     withdrawn/completed/rejected enrollments by default. Excluded user_ids
     are printed before the plan. `--include-inactive` reverts to the
     unfiltered behavior for the rare intentional case.

MULTI-OUTPUT SUPPORT
  --grade-only suppresses the comment (e.g. the consequential grade in a two-
  output flow where the completion grade carries the comment).
  --default-comment <text> posts a fixed comment when a feedback file lacks a
  `## Comment to student` block (e.g. "See Mid Review for detailed feedback").

USAGE
  # 1. Validate path on the Test Student
  uv run python lib/tools/grader_push.py --challenge-dir grading/kc1 \\
    --assignment-id 12345 --test-user <test-student-uid>

  # 2. Mark the cohort reviewed (after eyeballing per-student files)
  uv run python lib/tools/grader_push.py --challenge-dir grading/kc1 \\
    --assignment-id 12345 --mark-reviewed

  # 3. Dry-run (always run this first; shows the plan)
  uv run python lib/tools/grader_push.py --challenge-dir grading/kc1 \\
    --assignment-id 12345

  # 4. Push for real (on an enrolled course requires --allow-enrolled)
  uv run python lib/tools/grader_push.py --challenge-dir grading/kc1 \\
    --assignment-id 12345 --push --allow-enrolled

GENERALIZED FROM: ds460-master/grading/push_grades.py
(commits 754c966..91a5113 + 8f7814b — round-1 and round-2 additions).
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from _challenge_dir_guard import resolve_challenge_dir  # issue #44 FERPA guard

import requests

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

try:
    from canvas_course_guard import enforce as guard_enforce
except ImportError:
    guard_enforce = None

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    pass

NUM_RE = re.compile(r"\d+")
_TIMEOUT = 30


def _env_canvas() -> tuple[str, str, str]:
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    cid = os.environ.get("CANVAS_COURSE_ID", "")
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return tok, cid, base


def comment_for(feedback_file: str) -> str:
    """Read the `## Comment to student` block from a per-student feedback file."""
    p = Path(feedback_file)
    if not p.exists():
        return ""
    t = p.read_text(encoding="utf-8")
    if "## Comment to student" not in t:
        return ""
    return t.split("## Comment to student", 1)[1].strip()


def fetch_submissions(base: str, cid: str, headers: dict, aid: str) -> list[dict]:
    """All submissions for the assignment — user_id + submission id only (no names)."""
    subs: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions",
            headers=headers, params={"per_page": 100, "page": page}, timeout=_TIMEOUT)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        subs += [{"user_id": s["user_id"], "id": s["id"]} for s in batch]
        page += 1
    return subs


# Issue #61: by default, the push surface excludes the Test Student (always)
# and inactive/withdrawn/completed/rejected enrollments. The default Canvas
# /submissions endpoint surfaces all three — easy footgun if you don't
# filter. `--include-inactive` reverts to the unfiltered behavior for the
# rare intentional case.
def fetch_active_filter(
    base: str, cid: str, headers: dict,
) -> tuple[set[int], dict[int, str], int | None]:
    """Return (active_user_ids, inactive_user_id_to_state, test_student_id).

    - active_user_ids: StudentEnrollment with state in {active, invited}.
      These are the rows safe to push to by default.
    - inactive_user_id_to_state: StudentEnrollment with state in
      {inactive, completed, rejected}. Surfaced in the excluded report so
      the operator sees who got dropped and why.
    - test_student_id: the course's `student_view_student` user_id, or None
      if the API doesn't expose one. ALWAYS excluded by default.
    """
    active_set: set[int] = set()
    inactive: dict[int, str] = {}

    page = 1
    while True:
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/enrollments",
            headers=headers,
            params=[
                ("per_page", 100), ("page", page),
                ("type[]", "StudentEnrollment"),
                ("state[]", "active"), ("state[]", "invited"),
                ("state[]", "inactive"), ("state[]", "completed"),
                ("state[]", "rejected"),
            ],
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        for e in batch:
            uid = e.get("user_id")
            state = (e.get("enrollment_state") or "").lower()
            if uid is None:
                continue
            uid = int(uid)
            if state in {"active", "invited"}:
                active_set.add(uid)
            elif state in {"inactive", "completed", "rejected"}:
                # Don't downgrade if the user is also enrolled actively elsewhere
                if uid not in active_set:
                    inactive[uid] = state
        page += 1

    test_id: int | None = None
    tr = requests.get(
        f"{base}/api/v1/courses/{cid}/student_view_student",
        headers=headers, timeout=_TIMEOUT,
    )
    if tr.status_code < 400:
        try:
            test_id = int(tr.json().get("id"))
        except (TypeError, ValueError, AttributeError):
            test_id = None

    if test_id is not None:
        active_set.discard(test_id)
        inactive.pop(test_id, None)
    return active_set, inactive, test_id


def resolve_user_id(filename: str, subs: list[dict]) -> int | None:
    """Match the Canvas download filename's numeric IDs to a submission (user_id [+ submission_id])."""
    nums = set(NUM_RE.findall(filename))
    cand = [s for s in subs if str(s["user_id"]) in nums]
    if len(cand) == 1:
        return cand[0]["user_id"]
    cand2 = [s for s in cand if str(s["id"]) in nums]
    return cand2[0]["user_id"] if len(cand2) == 1 else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Push grades + comments to Canvas (LOCAL, gated).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", required=True,
                    help="Convention base path (e.g. grading/kc1). Holds .review.csv, feedback/, etc.")
    ap.add_argument("--assignment-id",
                    help="Canvas assignment id (required for --push / dry-run / --test-user)")
    ap.add_argument("--review", default=".review.csv",
                    help="Review sheet path, relative to --challenge-dir. Use distinct sheets per output "
                         "in multi-output assignments. Default: .review.csv")
    ap.add_argument("--prefix", default=None,
                    help="Key prefix for the feedback files to gate on (auto-invalidate mtime check). "
                         "Default: uppercased basename of --challenge-dir.")
    ap.add_argument("--push", action="store_true",
                    help="Actually write to Canvas (default: dry-run). Refuses without --mark-reviewed.")
    ap.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Bypass canvas_course_guard for enrolled-course writes (instructor's own course).")
    ap.add_argument("--test-user", type=int,
                    help="Validate the API path: push ONE sample grade+comment to this user_id "
                         "(e.g. Canvas's Test Student).")
    ap.add_argument("--grade",
                    help="Grade to use with --test-user (default 3.5 with comment / 85 with --grade-only).")
    ap.add_argument("--mark-reviewed", action="store_true",
                    help="Confirm you've reviewed all comments + scores. Required before --push. "
                         "Auto-invalidates if any comment file changes after.")
    ap.add_argument("--force", action="store_true",
                    help="Re-push keys already in the per-assignment push log (default: skip already-pushed).")
    ap.add_argument("--default-comment", default="",
                    help="Comment to post when a row's feedback file has no '## Comment to student' block "
                         "(e.g. a short line for a completion-only output).")
    ap.add_argument("--grade-only", action="store_true",
                    help="Push the grade with NO comment (e.g. the consequential layer in a multi-output flow).")
    ap.add_argument("--include-inactive", action="store_true",
                    help="Issue #61: by default the push surface excludes Canvas's Test Student + "
                         "inactive/withdrawn/completed/rejected enrollments. Pass this flag for the "
                         "rare intentional case (e.g. posting a final grade to a student who withdrew).")
    args = ap.parse_args()

    challenge = resolve_challenge_dir(args.challenge_dir, verb="pushing from")
    if not challenge.is_dir():
        print(f"--challenge-dir {challenge} does not exist.", file=sys.stderr)
        return 1
    prefix = args.prefix or challenge.name.upper().replace("_", "-")

    fbdir = challenge / "feedback"
    reviewed = challenge / ".reviewed"

    # --- mark-reviewed mode (no Canvas call) ---
    # Issue #46: detect value-only / human-graded mode (no per-student comment
    # files exist — typical for the dual-push pattern's value-only output, or
    # any TA-graded run where the instructor only posts the consequential
    # number). Switch the review surface to .review*.csv + _gradebook_actuals.csv
    # instead of pointing at _all_comments.md + per-student .md files that
    # don't exist.
    if args.mark_reviewed:
        comment_files = list(fbdir.glob(f"{prefix}-*.md"))
        review_csvs = sorted(challenge.glob(".review*.csv"))
        actuals = fbdir / "_gradebook_actuals.csv"

        if comment_files:
            # LLM-comment run — original messaging
            n = len(comment_files)
            print(f"You are confirming you reviewed all {n} comments + scores in {fbdir}/")
            print(f"(the overall {fbdir}/_all_comments.md and each per-student {prefix}-*.md justification).")
        elif review_csvs:
            # Value-only / human-graded run — point at the actual review surface
            print(f"You are confirming you reviewed the value-only push surface for {fbdir.parent.name}:")
            for csv in review_csvs:
                print(f"  • {csv.name}  ({csv.stat().st_size} bytes)")
            if actuals.exists():
                print(f"  • {actuals.relative_to(challenge)}  (reconcile evidence)")
            print("\n  (No per-student comment files in this run — this is the "
                  "value-only / human-graded push path. The mtime auto-invalidation "
                  "gate will watch these CSV files instead of comment .md files.)")
        else:
            # Neither comment .md files nor .review*.csv — operator may have
            # skipped reidentify. Refuse loudly so they don't accidentally
            # mark-reviewed an empty review surface.
            print(f"\n⛔ Nothing to review. Neither comment files ({prefix}-*.md) "
                  f"nor .review*.csv exist in {challenge}/.", file=sys.stderr)
            print("   Run grader_consensus + grader_reidentify first to produce "
                  "a review surface.", file=sys.stderr)
            return 1

        if not args.yes and input("\nType 'reviewed' to confirm: ").strip().lower() != "reviewed":
            print("Not marked.")
            return 1
        reviewed.write_text("reviewed\n", encoding="utf-8")
        print(f"Marked reviewed -> {reviewed}. You can now run --push.")
        return 0

    tok, cid, base = _env_canvas()
    for var, val in (("CANVAS_API_TOKEN", tok), ("CANVAS_BASE_URL", base), ("CANVAS_COURSE_ID", cid)):
        if not val:
            print(f"Missing {var} in .env", file=sys.stderr)
            return 1
    headers = {"Authorization": f"Bearer {tok}"}

    if not args.assignment_id:
        print("--assignment-id is required to push / dry-run / test.", file=sys.stderr)
        return 1

    # canvas_course_guard: refuse enrolled-course writes unless --allow-enrolled
    if guard_enforce and (args.push or args.test_user is not None):
        guard_enforce(base, headers, cid, mode="write", allow_override=args.allow_enrolled)

    # --- one-shot Test Student validation ---
    if args.test_user:
        grade = args.grade or ("85" if args.grade_only else "3.5")
        comment = "" if args.grade_only else (
            "Test comment from the grading tool — please ignore. "
            "Validating that grade + comment post correctly (grader_push.py).")
        print(f"TEST push → course {cid}, assignment {args.assignment_id}, user {args.test_user}")
        print(f"  grade={grade}")
        print(f'  comment={chr(34)+comment+chr(34) if comment else "(none — grade only)"}')
        if not args.push:
            print("\nDry run — nothing written. Add --push to actually send.")
            return 0
        if not args.yes:
            if input(f"\nType 'push' to write to user {args.test_user} on LIVE course {cid}: "
                     ).strip().lower() != "push":
                print("Aborted.")
                return 1
        data = {"submission[posted_grade]": grade}
        if comment:
            data["comment[text_comment]"] = comment
        resp = requests.put(
            f"{base}/api/v1/courses/{cid}/assignments/{args.assignment_id}/submissions/{args.test_user}",
            headers=headers, data=data, timeout=_TIMEOUT)
        if resp.status_code < 400:
            j = resp.json()
            print(f"  OK — status {resp.status_code}; submission.grade now = {j.get('grade')}")
        else:
            print(f"  ERROR {resp.status_code}: {resp.text[:200]}")
        return 0 if resp.status_code < 400 else 2

    review = challenge / args.review
    if not review.exists():
        print(f"No {review} — run grader_reidentify.py first, then set final_grade column.",
              file=sys.stderr)
        return 1

    # idempotency: keys already in the per-assignment push log are skipped unless --force.
    log = challenge / ".push_log.md"
    _logtext = log.read_text(encoding="utf-8") if log.exists() else ""
    pushed_keys = set(re.findall(
        rf"^- (\S+): grade \S+ pushed to assignment {args.assignment_id}\b", _logtext, re.M))

    rows = list(csv.DictReader(review.open(encoding="utf-8")))
    subs = fetch_submissions(base, cid, headers, args.assignment_id)

    # Issue #61: default-exclude Test Student + inactive/withdrawn enrollments.
    excluded_test: list[int] = []
    excluded_inactive: list[tuple[int, str]] = []
    if not args.include_inactive:
        active_set, inactive_map, test_id = fetch_active_filter(base, cid, headers)
        kept: list[dict] = []
        for s in subs:
            uid = int(s["user_id"])
            if test_id is not None and uid == test_id:
                excluded_test.append(uid)
                continue
            if uid in inactive_map:
                excluded_inactive.append((uid, inactive_map[uid]))
                continue
            if uid not in active_set:
                # Not Test Student, not currently inactive — but also not an
                # active StudentEnrollment (could be observer / designer / a
                # dropped enrollment not yet propagated). Skip and report.
                excluded_inactive.append((uid, "no_active_student_enrollment"))
                continue
            kept.append(s)
        subs = kept

    extra = (f"; {len(pushed_keys)} already pushed (skip unless --force)"
             if pushed_keys and not args.force else "")
    print(f"Assignment {args.assignment_id}: {len(subs)} Canvas submissions, "
          f"{len(rows)} review rows{extra}\n")

    # Surface what was filtered so the operator sees it BEFORE the plan.
    if excluded_test or excluded_inactive:
        print(f"  excluded by default (issue #61; pass --include-inactive to keep):")
        if excluded_test:
            print(f"    Test Student:           user_id={excluded_test[0]} (1 row)")
        if excluded_inactive:
            by_state: dict[str, list[int]] = {}
            for uid, state in excluded_inactive:
                by_state.setdefault(state, []).append(uid)
            for state in sorted(by_state):
                ids = by_state[state]
                preview = ", ".join(str(u) for u in ids[:5])
                more = f", +{len(ids) - 5} more" if len(ids) > 5 else ""
                print(f"    {state:<22} user_ids=[{preview}{more}]  ({len(ids)} row{'s' if len(ids) != 1 else ''})")
        print()

    plan = []
    for r in rows:
        key = r.get("key", "")
        grade = (r.get("final_grade") or "").strip() or (r.get("recommended_score") or "").strip()
        comment = "" if args.grade_only else (
            comment_for(r.get("feedback_file", "")) or args.default_comment)
        uid = resolve_user_id(r.get("submission_file", ""), subs)
        done = key in pushed_keys and not args.force
        ok = bool(grade and uid and (comment or args.grade_only)) and not done
        plan.append((key, uid, grade, comment, ok))
        if done:
            mark, why = "done", "  (already pushed)"
        elif ok:
            mark, why = "OK ", ""
        else:
            mark, why = "SKIP", f"  ({'no match' if not uid else 'no grade' if not grade else 'no comment'})"
        # FERPA-safe console: key, grade, matched?, comment preview — NO names
        print(f"  [{mark}] {key}: grade={grade or '—'}  matched={'yes' if uid else 'NO'}  "
              f"comment=\"{comment[:50].replace(chr(10), ' ')}…\"{why}")

    pushable = [p for p in plan if p[4]]
    extra2 = (f" ({len(pushed_keys)} already done, skipped)"
              if pushed_keys and not args.force else "")
    print(f"\n{len(pushable)}/{len(plan)} ready to push{extra2}.")
    if not args.push:
        print("Dry run — nothing written. Re-run with --push to send to Canvas.")
        return 0
    if not pushable:
        print("Nothing to push.")
        return 1

    # --- REQUIRED REVIEW GATE: --mark-reviewed must exist + not be stale ---
    # Issue #46: the watch list is the union of EVERYTHING the operator might
    # have reviewed — comment files (LLM-comment runs), the all-comments
    # overview, AND the value-only review surface (.review*.csv +
    # _gradebook_actuals.csv). The mtime auto-invalidation fires if ANY of
    # these post-dates the .reviewed marker, regardless of which subset
    # actually exists in this run. So value-only pushes keep a real
    # "edited-after-review re-locks" guarantee.
    if not reviewed.exists():
        comment_files = list(fbdir.glob(f"{prefix}-*.md"))
        review_csvs = sorted(challenge.glob(".review*.csv"))
        print("\n⛔ Review required before pushing.")
        if comment_files:
            print(f"   Review {fbdir}/_all_comments.md and the per-student {prefix}-*.md justifications,")
        elif review_csvs:
            print(f"   Review the .review*.csv files in {challenge}/ + "
                  f"{fbdir.name}/_gradebook_actuals.csv (value-only / human-graded path),")
        else:
            print(f"   Produce a review surface first (per-student {prefix}-*.md OR "
                  f".review*.csv), then review it,")
        print("   then run:  uv run python lib/tools/grader_push.py --challenge-dir "
              f"{args.challenge_dir} --mark-reviewed")
        return 1
    rmt = reviewed.stat().st_mtime
    watch = (
        list(fbdir.glob(f"{prefix}-*.md"))
        + [fbdir / "_all_comments.md"]
        + list(challenge.glob(".review*.csv"))
        + [fbdir / "_gradebook_actuals.csv"]
    )
    stale = [p.name for p in watch if p.exists() and p.stat().st_mtime > rmt]
    if stale:
        print(f"\n⛔ {len(stale)} review-surface file(s) changed since you marked reviewed "
              f"(e.g. {stale[0]}). Re-review, then re-run --mark-reviewed.")
        return 1

    if not args.yes:
        print(f"\nThis writes {len(pushable)} grades + comments to the LIVE course {cid}.")
        if input("Type 'push' to confirm: ").strip().lower() != "push":
            print("Aborted.")
            return 1

    pushed = 0
    failed: list[str] = []
    with log.open("a", encoding="utf-8") as lg:
        for key, uid, grade, comment, _ in pushable:
            data = {"submission[posted_grade]": grade}
            if comment:
                data["comment[text_comment]"] = comment
            resp = requests.put(
                f"{base}/api/v1/courses/{cid}/assignments/{args.assignment_id}/submissions/{uid}",
                headers=headers, data=data, timeout=_TIMEOUT)
            if resp.status_code < 400:
                print(f"  pushed {key}: {grade}")
                lg.write(f"- {key}: grade {grade} pushed to assignment {args.assignment_id}\n")
                pushed += 1
            else:
                # P-003 stop on first 4xx — surface and abort rather than retry blindly
                print(f"  ERROR {key}: {resp.status_code} {resp.text[:120]}")
                failed.append(key)
                if 400 <= resp.status_code < 500:
                    print(f"\n⛔ 4xx on {key}. STOP (P-003). Don't retry blindly. "
                          f"Investigate, then re-run; idempotency skips successes.")
                    break
    print(f"\nPushed {pushed}/{len(pushable)}. Logged to {log} (keyed, gitignored).")
    if failed:
        print(f"Failed: {failed}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

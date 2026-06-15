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
  6. **Issue #62** — pre-push comment-collision guard. For each pushable
     row that ships a comment, peek at existing `submission_comments`
     through the FERPA-safe deid layer (#65) and warn on non-self
     comments within `--collision-window-days` (default 14). Operator
     must type `collisions` to ack OR pass `--allow-collisions`.
     `--skip-if-student-replied` drops rows where the latest comment is
     from the student. `--grade-only` / `--no-collision-check` opt out.
  7. **Issue #63** — availability awareness. Pre-fetch
     `/assignments/:aid` for `lock_at`/`unlock_at`; if the assignment is
     locked AND a pushable comment contains resubmit-style language
     (resubmit/redo/new template/wrong file/...), surface a warning.
     Operator types `locked` to ack OR passes `--allow-locked-resubmit`.
     `--no-lock-check` / `--grade-only` opt out.

RETRACT MODE (issue #63)
  Every comment push records `- <KEY>: comment <ID> pushed to assignment
  <AID>` to `.push_log.md`. `--retract` reads that ledger for THIS
  assignment, optionally scoped via `--retract-keys K1,K2,...`, and
  DELETEs each comment via /comments/:id. Idempotent: a `- KEY: comment
  ID retracted from assignment AID` line is appended on success, and
  subsequent retract runs skip the already-retracted entries.

  Dry-run by default (same as the push path):
    uv run python lib/tools/grader_push.py --challenge-dir grading/kc1 \\
      --assignment-id 12345 --retract --retract-keys KC1-A1B2C3,KC1-DEF456

  Real retract (--push is the verb; --mark-reviewed is NOT required —
  retract is a corrective action, not a fresh review surface):
    uv run python lib/tools/grader_push.py --challenge-dir grading/kc1 \\
      --assignment-id 12345 --retract --retract-keys KC1-A1B2C3 \\
      --push --allow-enrolled

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


# Issue #72: HOLD_<DIMENSION> grade-hold pattern (lifted from itm327's
# build_mid_letter_comments + push_mid_letter). When a per-student
# feedback file's top-of-file heading carries a trailing `· HOLD_<TOKEN>`
# marker, the push posts the qualitative comment but WITHHOLDS the grade
# write — the band may shift once the student replies with the missing
# self-reported value. Operator clears the marker (edit the heading) +
# re-runs to release the grade.
_HOLD_HEADING_RE = re.compile(
    r"^#+\s+.*?·\s*(HOLD_[A-Z][A-Z0-9_]*)\s*$",
    re.MULTILINE,
)


def extract_hold_token(feedback_file: str) -> str | None:
    """Return the first `HOLD_<DIMENSION>` token found in a top-of-file
    heading line (e.g. `# KC1-A1B2C3 · 4 · PUSH · HOLD_HOURS`), or None
    if no hold is staged. Issue #72."""
    p = Path(feedback_file)
    if not feedback_file or not p.exists():
        return None
    # Only scan the first ~3 heading lines — the hold marker is at the top.
    head_lines: list[str] = []
    with p.open(encoding="utf-8") as f:
        for ln in f:
            if ln.strip().startswith("#"):
                head_lines.append(ln)
                if len(head_lines) >= 3:
                    break
    if not head_lines:
        return None
    m = _HOLD_HEADING_RE.search("\n".join(head_lines))
    return m.group(1) if m else None


def fetch_submissions(base: str, cid: str, headers: dict, aid: str,
                      include_comments: bool = False) -> list[dict]:
    """All submissions for the assignment.

    Default: returns lean {user_id, id} per submission (the existing
    behavior).
    If `include_comments`, paginates with include[]=submission_comments
    and returns the full Canvas submission payloads (each dict has a
    `submission_comments` list of raw comments — caller MUST pass that
    list through grader_deidentify_comments.deidentify_submission_comments
    before logging anywhere). Issue #62 collision-guard uses this path.
    """
    subs: list[dict] = []
    page = 1
    while True:
        params: dict[str, object] = {"per_page": 100, "page": page}
        if include_comments:
            params["include[]"] = "submission_comments"
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions",
            headers=headers, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        if include_comments:
            subs += batch
        else:
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

    # Issue #67: follow Canvas's `Link: rel="next"` header instead of
    # blindly incrementing page numbers. Several Canvas endpoints return
    # HTTP 400 (not an empty list) when you ask for a page beyond the
    # last — `/enrollments` is one. Cohorts <= per_page hit this every
    # call.
    url: str | None = f"{base}/api/v1/courses/{cid}/enrollments"
    initial_params = [
        ("per_page", 100),
        ("type[]", "StudentEnrollment"),
        ("state[]", "active"), ("state[]", "invited"),
        ("state[]", "inactive"), ("state[]", "completed"),
        ("state[]", "rejected"),
    ]
    while url:
        r = requests.get(
            url, headers=headers,
            params=initial_params if "?" not in url else None,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json() or []
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
        link = r.headers.get("Link", "")
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
        initial_params = None  # subsequent pages are pre-parameterized in the next URL

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


# ---------------------------------------------------------------------------
# Issue #62 — pre-push comment-collision guard
#
# Before posting a comment that could contradict / duplicate / overwrite a
# human grader's recent activity, peek at the existing submission_comments
# thread for each pushable row. Surface collisions through the FERPA-safe
# de-id layer (issue #65) — author_name never reaches grader_push state.
# ---------------------------------------------------------------------------

def _parse_iso(s: str | None):
    """Datetime-or-None for collision-window comparisons. Operates in UTC."""
    from datetime import datetime, timezone
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


# Issue #63 part 1: availability awareness. The pushable comment text is
# scanned for resubmit-style language; if the assignment's lock_at has
# passed (or unlock_at hasn't), pushing such guidance creates instructions
# students literally cannot act on. Pattern list is conservative — false
# positives (a benign mention of "redo") are cheap (one extra warning);
# false negatives (a real "resubmit using the template" slipping past) are
# the actual harm.
_RESUBMIT_PATTERNS = [
    r"\bresubmit\b",
    r"\bre-?submit\b",
    r"\bre-?upload\b",
    r"\bupload\s+again\b",
    r"\bsubmit\s+again\b",
    r"\bredo\b",
    r"\bre-?do\b",
    r"\btry\s+again\b",
    r"\bnew\s+template\b",
    r"\bright\s+template\b",
    r"\bwrong\s+template\b",
    r"\bwrong\s+file\b",
    r"\bnew\s+version\b",
    r"\bright\s+version\b",
    r"\bwrong\s+version\b",
    r"\bcorrect\s+version\b",
]
_RESUBMIT_RE = re.compile("|".join(_RESUBMIT_PATTERNS), re.IGNORECASE)


def fetch_assignment_lock_state(
    base: str, cid: str, headers: dict, aid: str, now=None,
) -> dict:
    """Return {'locked_now', 'lock_at', 'unlock_at', 'reason'}.

    locked_now is True if (a) lock_at is in the past, or (b) unlock_at is
    in the future. reason is a short human string. Reads /assignments/:aid
    once; cheap."""
    from datetime import datetime, timezone
    if now is None:
        now = datetime.now(tz=timezone.utc)
    r = requests.get(
        f"{base}/api/v1/courses/{cid}/assignments/{aid}",
        headers=headers, timeout=_TIMEOUT,
    )
    r.raise_for_status()
    a = r.json() or {}
    lock_at = a.get("lock_at")
    unlock_at = a.get("unlock_at")

    def _iso(s):
        if not s:
            return None
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d

    lock_dt = _iso(lock_at)
    unlock_dt = _iso(unlock_at)
    locked_now = False
    reason = ""
    if lock_dt is not None and now > lock_dt:
        locked_now = True
        reason = f"lock_at={lock_dt.date()} has passed"
    elif unlock_dt is not None and now < unlock_dt:
        locked_now = True
        reason = f"unlock_at={unlock_dt.date()} is in the future"
    return {"locked_now": locked_now, "lock_at": lock_at, "unlock_at": unlock_at,
            "reason": reason}


def comment_has_resubmit_language(text: str) -> bool:
    """True if `text` contains any resubmit-style instruction pattern."""
    if not text:
        return False
    return bool(_RESUBMIT_RE.search(text))


def collision_warnings_for_submission(
    deid_comments: list[dict], *, window_days: int, now=None,
) -> tuple[list[dict], dict | None]:
    """Return (recent_other_author_comments, latest_comment_overall).

    - recent_other_author_comments: rows from `deid_comments` whose
      author_role is NOT 'self' AND whose created_at is within
      `window_days`. These are the comments grader_push warns about
      before posting (the operator may be duplicating / contradicting).
    - latest_comment_overall: the most-recent comment in the thread by
      created_at, regardless of role. Used by --skip-if-student-replied
      (if this is role='self', the student has already replied — skipping
      avoids noise on a thread where the student already acted).
    """
    from datetime import datetime, timedelta, timezone
    if now is None:
        now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=window_days)

    others_recent: list[dict] = []
    latest: dict | None = None
    latest_dt = None
    for c in deid_comments or []:
        dt = _parse_iso(c.get("created_at"))
        if dt is None:
            continue
        if c.get("author_role") != "self" and dt >= cutoff:
            others_recent.append(c)
        if latest_dt is None or dt > latest_dt:
            latest = c
            latest_dt = dt
    return others_recent, latest


def resolve_user_id(filename: str, subs: list[dict]) -> int | None:
    """Match the Canvas download filename's numeric IDs to a submission (user_id [+ submission_id])."""
    nums = set(NUM_RE.findall(filename))
    cand = [s for s in subs if str(s["user_id"]) in nums]
    if len(cand) == 1:
        return cand[0]["user_id"]
    cand2 = [s for s in cand if str(s["id"]) in nums]
    return cand2[0]["user_id"] if len(cand2) == 1 else None


# Issue #63 part 2: retract previously-pushed comments. Comment ids are
# captured in .push_log.md on every comment push (one line per push:
# `- <KEY>: comment <ID> pushed to assignment <AID>`). --retract reads
# that ledger for THIS assignment, optionally scoped to --retract-keys,
# and DELETEs each via the comments API. The ledger is updated with a
# retract line so a subsequent re-push has a clean slate.
_PUSH_LOG_COMMENT_RE = re.compile(
    r"^- (\S+): comment (\d+) pushed to assignment (\S+)", re.M
)
_PUSH_LOG_RETRACT_RE = re.compile(
    r"^- (\S+): comment (\d+) retracted from assignment (\S+)", re.M
)


def _read_comment_ledger(log: Path, assignment_id: str) -> list[tuple[str, int]]:
    """Return [(key, comment_id)] for every still-active comment recorded
    against `assignment_id`. A 'retracted' line cancels the matching push."""
    if not log.exists():
        return []
    text = log.read_text(encoding="utf-8")
    pushed = [(k, int(cid)) for k, cid, aid in _PUSH_LOG_COMMENT_RE.findall(text)
              if aid == str(assignment_id)]
    retracted = {(k, int(cid)) for k, cid, aid in _PUSH_LOG_RETRACT_RE.findall(text)
                 if aid == str(assignment_id)}
    return [(k, c) for (k, c) in pushed if (k, c) not in retracted]


def _resolve_uid_from_log_or_subs(
    base: str, cid: str, headers: dict, aid: str, key: str, subs: list[dict],
) -> int | None:
    """Best-effort uid resolution for retract. The push log has the key but
    not the uid; we need the uid for the DELETE URL. Strategy: scan the
    challenge's review.csv if present, otherwise fall back to the user
    passing keys + we look up by matching submission filenames."""
    # The grade-push log line is `- KEY: grade GRADE pushed to assignment AID`.
    # That also doesn't carry the uid. So we rebuild from the submissions
    # listing + the keymap-aware filename match.
    # For retract, this is best-effort: if we can't resolve, we report and skip.
    return None  # delegated to caller via subs-and-keymap match


def _retract_main(base: str, cid: str, headers: dict, args,
                  log: Path, prefix: str) -> int:
    """--retract entry. DELETEs previously-pushed comment ids for this
    assignment (scope: all keys in the ledger, or --retract-keys subset)."""
    # Read the comment ledger first — fail fast if there's nothing to retract.
    ledger = _read_comment_ledger(log, str(args.assignment_id))
    if args.retract_keys:
        wanted = {k.strip() for k in args.retract_keys.split(",") if k.strip()}
        ledger = [(k, c) for (k, c) in ledger if k in wanted]
    if not ledger:
        print(f"Nothing to retract for assignment {args.assignment_id}"
              f"{' (no matching keys in --retract-keys)' if args.retract_keys else ''}.")
        return 0

    # Map key → user_id via the assignment's submission list + the
    # challenge's keymap (.keymap.json holds key→filename; resolve_user_id
    # matches filename to uid via the numeric ids embedded in Canvas-format
    # filenames).
    import json as _json
    challenge = resolve_challenge_dir(args.challenge_dir, verb="retracting from")
    keymap_file = challenge / ".keymap.json"
    keymap = (_json.loads(keymap_file.read_text(encoding="utf-8")).get("map", {})
              if keymap_file.exists() else {})
    subs = fetch_submissions(base, cid, headers, args.assignment_id)
    key_to_uid: dict[str, int | None] = {
        k: resolve_user_id(fname, subs) for k, fname in keymap.items()
    }

    # canvas_course_guard: retract IS a write — gate it.
    if guard_enforce and args.push:
        guard_enforce(base, headers, cid, mode="write", allow_override=args.allow_enrolled)

    print(f"Retract plan for assignment {args.assignment_id} "
          f"({len(ledger)} comment(s) recorded):")
    rows_to_delete: list[tuple[str, int, int]] = []  # (key, uid, comment_id)
    for key, comment_id in ledger:
        uid = key_to_uid.get(key)
        if uid is None:
            print(f"  [SKIP] {key} comment={comment_id}  (uid not resolvable from .keymap.json)")
            continue
        rows_to_delete.append((key, uid, comment_id))
        print(f"  [OK]   {key} comment={comment_id} → DELETE /submissions/{uid}/comments/{comment_id}")

    if not args.push:
        print(f"\nDry run — nothing deleted. Re-run with --push to actually retract.")
        return 0
    if not rows_to_delete:
        print("\nNothing to delete after resolution.")
        return 1
    if not args.yes:
        if input(f"\nType 'retract' to delete {len(rows_to_delete)} comment(s) "
                 f"on LIVE course {cid}: ").strip().lower() != "retract":
            print("Aborted.")
            return 1

    retracted = 0
    failed: list[str] = []
    with log.open("a", encoding="utf-8") as lg:
        for key, uid, comment_id in rows_to_delete:
            resp = requests.delete(
                f"{base}/api/v1/courses/{cid}/assignments/{args.assignment_id}"
                f"/submissions/{uid}/comments/{comment_id}",
                headers=headers, timeout=_TIMEOUT,
            )
            if resp.status_code < 400:
                print(f"  retracted {key} comment={comment_id}")
                lg.write(f"- {key}: comment {comment_id} retracted from assignment "
                         f"{args.assignment_id}\n")
                retracted += 1
            else:
                print(f"  ERROR {key} comment={comment_id}: {resp.status_code} {resp.text[:120]}")
                failed.append(f"{key}/{comment_id}")
                if 400 <= resp.status_code < 500:
                    print(f"\n⛔ 4xx on {key}. STOP (P-003). Don't retry blindly. "
                          f"Investigate, then re-run; ledger updates only on success.")
                    break

    print(f"\nRetracted {retracted}/{len(rows_to_delete)}.")
    if failed:
        print(f"Failed: {failed}")
        return 2
    return 0


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
    ap.add_argument("--no-collision-check", action="store_true",
                    help="Issue #62: SKIP the pre-push comment-collision guard. By default, grader_push "
                         "checks each pushable row's existing submission_comments and warns if any "
                         "comment from a different author exists within --collision-window-days. The "
                         "guard runs through the FERPA-safe deid layer (#65) — no author_name reaches "
                         "console. --grade-only pushes always skip the check (no comment risk).")
    ap.add_argument("--collision-window-days", type=int, default=14,
                    help="Issue #62: how many days back the collision guard looks. Default: 14.")
    ap.add_argument("--skip-if-student-replied", action="store_true",
                    help="Issue #62: if the LATEST comment in a thread is from the student (author "
                         "role 'self'), drop that row from the push plan — the student has already "
                         "responded to prior feedback; new comments here add noise.")
    ap.add_argument("--allow-collisions", action="store_true",
                    help="Issue #62: bypass the collision-confirmation prompt. The plan still prints "
                         "the warnings; this flag just skips the explicit 'type collisions to confirm' "
                         "interactive step.")
    ap.add_argument("--no-lock-check", action="store_true",
                    help="Issue #63: skip the availability-aware warning. By default, grader_push "
                         "fetches the assignment's lock_at + unlock_at and warns if a comment "
                         "contains resubmit-style language (resubmit / redo / use the new "
                         "template / wrong file / etc.) while the assignment is locked or has not "
                         "yet unlocked — students can't act on the guidance.")
    ap.add_argument("--allow-locked-resubmit", action="store_true",
                    help="Issue #63: bypass the lock-check confirmation. The warnings still print; "
                         "this flag just skips the interactive 'type locked to confirm' step.")
    ap.add_argument("--retract", action="store_true",
                    help="Issue #63: DELETE previously-pushed comments for this assignment via "
                         "/courses/:cid/assignments/:aid/submissions/:uid/comments/:cid. Reads the "
                         "tracked comment_ids from .push_log.md (recorded automatically on every "
                         "push). Use --retract-keys to scope. WRITE path — same gates apply "
                         "(--mark-reviewed not required for retract; canvas_course_guard still "
                         "enforces; default is dry-run unless --push is also passed).")
    ap.add_argument("--retract-keys", default=None,
                    help="Issue #63: comma-separated list of keys to retract (default: all keys "
                         "for this assignment in .push_log.md). Has no effect without --retract.")
    ap.add_argument("--no-hold-tokens", action="store_true",
                    help="Issue #72: ignore `· HOLD_<DIM>` markers in per-student feedback "
                         "headings. By default, a heading like '# KEY · 4 · PUSH · HOLD_HOURS' "
                         "causes grader_push to POST the comment but WITHHOLD the grade write "
                         "(student must reply with the missing self-reported value first). "
                         "Pass this flag for cohorts where the convention doesn't apply.")
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
            # Issue #74: don't rebind the loop var as `csv` — that shadows
            # the module import and crashes the main push path further down.
            for rc in review_csvs:
                print(f"  • {rc.name}  ({rc.stat().st_size} bytes)")
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

    # Issue #63 retract mode: parse the per-assignment comment-id log and
    # DELETE matching submission_comments. Runs BEFORE the normal push
    # plan-build so the operator can retract + re-push in two passes.
    if args.retract:
        return _retract_main(base, cid, headers, args, log, prefix)

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

    # Issue #72: scan the comment-file headings once for HOLD_<DIM> markers
    # (e.g. '# KEY · 4 · PUSH · HOLD_HOURS'). Held rows post the comment
    # but WITHHOLD the grade write until the operator clears the token.
    hold_by_key: dict[str, str] = {}
    if not args.no_hold_tokens and not args.grade_only:
        for r in rows:
            ff = r.get("feedback_file", "") or ""
            if not ff:
                continue
            tok = extract_hold_token(ff)
            if tok:
                hold_by_key[r.get("key", "")] = tok

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
        hold = hold_by_key.get(key)
        if done:
            mark, why = "done", "  (already pushed)"
        elif hold:
            mark, why = "HOLD", f"  ({hold} — comment will post; grade withheld)"
        elif ok:
            mark, why = "OK ", ""
        else:
            mark, why = "SKIP", f"  ({'no match' if not uid else 'no grade' if not grade else 'no comment'})"
        # FERPA-safe console: key, grade, matched?, comment preview — NO names
        print(f"  [{mark}] {key}: grade={grade or '—'}  matched={'yes' if uid else 'NO'}  "
              f"comment=\"{comment[:50].replace(chr(10), ' ')}…\"{why}")

    # ---- Issue #63 part 1: availability awareness ------------------------
    # If the assignment is locked (lock_at passed, or unlock_at not yet
    # reached) AND a pushable row's comment text contains resubmit-style
    # language, the comment asks the student to do something they
    # literally can't. Warn loudly; require explicit ack before push.
    locked_resubmit_keys: list[tuple[str, str]] = []
    lock_state: dict = {}
    if not args.no_lock_check and not args.grade_only:
        try:
            lock_state = fetch_assignment_lock_state(base, cid, headers, args.assignment_id)
        except requests.HTTPError as e:
            print(f"WARN: lock-state check disabled — assignment metadata fetch failed "
                  f"({type(e).__name__}: {e}).", file=sys.stderr)
            lock_state = {"locked_now": False}
        if lock_state.get("locked_now"):
            for r in rows:
                key = r.get("key", "")
                comment = comment_for(r.get("feedback_file", "")) or args.default_comment
                if comment and comment_has_resubmit_language(comment):
                    locked_resubmit_keys.append((key, comment))
    # ---- end availability awareness --------------------------------------

    # ---- Issue #62: pre-push comment-collision guard --------------------
    # Only run when comments will actually be posted. --grade-only pushes
    # are objective + safe (per the issue: "the grade is safe; qualitative
    # comments cause harm"). --no-collision-check opts out explicitly.
    collisions: dict[str, dict] = {}
    student_replied_keys: set[str] = set()
    if not args.no_collision_check and not args.grade_only and any(p[4] for p in plan):
        try:
            # Lazy import — keeps grader_push standalone if a vendoring user
            # ships the toolkit without the comments adapter for some reason.
            from grader_deidentify_comments import (
                build_role_map,
                deidentify_submission_comments,
            )
        except ImportError as e:
            print(f"WARN: collision guard disabled — couldn't import grader_deidentify_comments "
                  f"({e}). Re-run with --no-collision-check to silence.", file=sys.stderr)
        else:
            full_subs = fetch_submissions(base, cid, headers, args.assignment_id,
                                          include_comments=True)
            full_by_uid = {int(s["user_id"]): s for s in full_subs if s.get("user_id") is not None}
            role_map = build_role_map(base, headers, cid)
            namesfile = challenge / ".known_names.txt"
            roster = ([ln.strip() for ln in namesfile.read_text(encoding="utf-8").splitlines() if ln.strip()]
                      if namesfile.exists() else [])

            for key, uid, _grade, _comment, ok in plan:
                if not ok or uid is None:
                    continue
                sub = full_by_uid.get(int(uid))
                if not sub:
                    continue
                deid_list = deidentify_submission_comments(
                    sub.get("submission_comments") or [],
                    owner_user_id=uid,
                    role_map=role_map,
                    roster=roster,
                )
                others, latest = collision_warnings_for_submission(
                    deid_list, window_days=args.collision_window_days)
                if others:
                    collisions[key] = {"others": others, "latest": latest}
                if latest is not None and latest.get("author_role") == "self":
                    student_replied_keys.add(key)

    if locked_resubmit_keys:
        print(f"\n  ⚠️  availability guard (issue #63): assignment is locked "
              f"({lock_state.get('reason', 'unknown')}); {len(locked_resubmit_keys)} comment(s) "
              f"contain resubmit-style language students can't act on:")
        for key, comment in locked_resubmit_keys[:5]:
            snippet = comment.replace("\n", " ").strip()
            if len(snippet) > 80:
                snippet = snippet[:77] + "…"
            print(f"    [{key}] \"{snippet}\"")
        if len(locked_resubmit_keys) > 5:
            print(f"    … +{len(locked_resubmit_keys) - 5} more")
        print("    Fix: extend the assignment's lock_at in Canvas, OR retract resubmit guidance "
              "from these rows' feedback files before --push.")

    if collisions:
        print(f"\n  ⚠️  comment-collision guard (issue #62; window={args.collision_window_days}d):")
        for key in sorted(collisions):
            info = collisions[key]
            print(f"    [{key}] {len(info['others'])} recent comment(s) from non-self authors:")
            for c in info["others"][:3]:
                snippet = (c.get("scrubbed_text") or "").replace("\n", " ").strip()
                if len(snippet) > 80:
                    snippet = snippet[:77] + "…"
                print(f"        role={c.get('author_role'):<10} created_at={c.get('created_at')}  "
                      f"comment_id={c.get('comment_id')}  text=\"{snippet}\"")
            if len(info["others"]) > 3:
                print(f"        … +{len(info['others']) - 3} more in window")

    if args.skip_if_student_replied and student_replied_keys:
        print(f"\n  --skip-if-student-replied: dropping {len(student_replied_keys)} row(s) where "
              f"the latest comment is from the student:")
        for k in sorted(student_replied_keys):
            print(f"    [{k}] latest comment role=self → skipped")
        plan = [(k, u, g, c, (ok and k not in student_replied_keys))
                for (k, u, g, c, ok) in plan]
    # ---- end collision guard --------------------------------------------

    pushable = [p for p in plan if p[4]]
    extra2 = (f" ({len(pushed_keys)} already done, skipped)"
              if pushed_keys and not args.force else "")
    print(f"\n{len(pushable)}/{len(plan)} ready to push{extra2}.")
    if hold_by_key:
        by_tok: dict[str, int] = {}
        for tok in hold_by_key.values():
            by_tok[tok] = by_tok.get(tok, 0) + 1
        print(f"  {sum(by_tok.values())} held (issue #72; comment posts, grade withheld): "
              f"{', '.join(f'{k}={v}' for k, v in sorted(by_tok.items()))}")
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

    if locked_resubmit_keys and not args.allow_locked_resubmit and not args.yes:
        pushable_set = {p[0] for p in pushable}
        affected = [k for k, _ in locked_resubmit_keys if k in pushable_set]
        if affected:
            print(f"\n⚠️  {len(affected)} pushable row(s) ask the student to resubmit/redo while "
                  f"the assignment is locked ({lock_state.get('reason', 'unknown')}).")
            if input("Type 'locked' to acknowledge + continue: ").strip().lower() != "locked":
                print("Aborted (lock guard).")
                return 1

    if collisions and not args.allow_collisions and not args.yes:
        pushable_with_collisions = sorted(k for k in collisions if k in {p[0] for p in pushable})
        if pushable_with_collisions:
            print(f"\n⚠️  {len(pushable_with_collisions)} pushable row(s) have a comment collision "
                  f"(see warnings above). Re-read those before continuing.")
            if input("Type 'collisions' to acknowledge + continue: ").strip().lower() != "collisions":
                print("Aborted (collision guard).")
                return 1

    if not args.yes:
        held_count = sum(1 for p in pushable if hold_by_key.get(p[0]))
        body_summary = (f"{len(pushable) - held_count} grades + comments + "
                        f"{held_count} held (comment-only)" if held_count else
                        f"{len(pushable)} grades + comments")
        print(f"\nThis writes {body_summary} to the LIVE course {cid}.")
        if input("Type 'push' to confirm: ").strip().lower() != "push":
            print("Aborted.")
            return 1

    pushed = 0
    held = 0
    failed: list[str] = []
    with log.open("a", encoding="utf-8") as lg:
        for key, uid, grade, comment, _ in pushable:
            # Issue #72: held rows post the qualitative comment but
            # WITHHOLD the grade write.
            hold_token = hold_by_key.get(key)
            data: dict[str, object] = {}
            if hold_token:
                if not comment:
                    # Held with no comment is nonsensical — the whole
                    # point is the qualitative ask. Skip rather than
                    # silently posting nothing.
                    print(f"  SKIP {key}: HOLD {hold_token} but no comment to post")
                    continue
                data["comment[text_comment]"] = comment
            else:
                data["submission[posted_grade]"] = grade
                if comment:
                    data["comment[text_comment]"] = comment
            resp = requests.put(
                f"{base}/api/v1/courses/{cid}/assignments/{args.assignment_id}/submissions/{uid}",
                headers=headers, data=data, timeout=_TIMEOUT)
            if resp.status_code < 400:
                if hold_token:
                    print(f"  held {key}: {hold_token} (comment posted; grade {grade} withheld)")
                    lg.write(f"- {key}: HELD {hold_token} for assignment "
                             f"{args.assignment_id} (grade {grade} withheld)\n")
                    held += 1
                else:
                    print(f"  pushed {key}: {grade}")
                    lg.write(f"- {key}: grade {grade} pushed to assignment {args.assignment_id}\n")
                    pushed += 1
                # Issue #63: capture the new comment_id (if any) so --retract
                # can DELETE it later. Canvas's PUT response includes
                # submission_comments[] — pick the LAST entry as the one we
                # just appended (ordered ASC by created_at).
                if comment:
                    try:
                        sc_list = (resp.json() or {}).get("submission_comments") or []
                        new_comment = sc_list[-1] if sc_list else None
                        new_id = (new_comment or {}).get("id")
                    except (ValueError, TypeError):
                        new_id = None
                    if new_id is not None:
                        lg.write(f"- {key}: comment {new_id} pushed to assignment "
                                 f"{args.assignment_id}\n")
            else:
                # P-003 stop on first 4xx — surface and abort rather than retry blindly
                print(f"  ERROR {key}: {resp.status_code} {resp.text[:120]}")
                failed.append(key)
                if 400 <= resp.status_code < 500:
                    print(f"\n⛔ 4xx on {key}. STOP (P-003). Don't retry blindly. "
                          f"Investigate, then re-run; idempotency skips successes.")
                    break
    summary_line = f"Pushed {pushed}/{len(pushable)}"
    if held:
        summary_line += f"; held {held} (comment posted; grade withheld — clear the HOLD_<DIM> token + re-push)"
    print(f"\n{summary_line}. Logged to {log} (keyed, gitignored).")
    if failed:
        print(f"Failed: {failed}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

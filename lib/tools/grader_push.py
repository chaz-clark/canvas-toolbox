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
     mutate it). **Issue #207 (HG-5)** — on the AI-drafted (LLM-comment)
     push path, --yes does NOT bypass the final "type 'push'" confirmation:
     an agent can pass --yes, but the instructor is the top layer and must
     decide the write. A deprecated disclosure tag in any comment file
     refuses the push (override: --allow-bad-disclosure-tags).
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

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import csv
import json
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


# Transparency disclosure (default, no opt-out): every AI-drafted feedback
# comment carries this tag so a student always knows the words were drafted by
# AI and reviewed by their instructor — never passed off as solely the
# instructor's own. Applied at send-time to the AI-drafted comment only; a
# manual default_comment (not AI-drafted) is left alone by callers.
DISCLOSURE_TAG = "— AI drafted, instructor reviewed"


def append_disclosure_tag(comment: str) -> str:
    """Append DISCLOSURE_TAG to an AI-drafted comment. Empty -> unchanged (never
    invents a tag-only comment); already-tagged -> unchanged (idempotent on
    re-push)."""
    if not comment or not comment.strip():
        return comment
    if comment.rstrip().endswith(DISCLOSURE_TAG):
        return comment
    return f"{comment.rstrip()}\n\n{DISCLOSURE_TAG}"


# Deprecated disclosure-tag formats that predate the canonical DISCLOSURE_TAG.
# A feedback file carrying one of these was drafted/edited under an older
# convention; because it doesn't end with the canonical tag, append_disclosure_tag
# would STACK the canonical tag on top of the stale one at send-time — two tags in
# one comment. So the push is refused until the operator fixes it (issue #207).
DEPRECATED_DISCLOSURE_TAGS = (
    "_🤖 AI-drafted feedback, instructor-reviewed_",
    "🤖 AI-drafted feedback, instructor-reviewed",
    "_AI drafted, instructor reviewed_",          # underscore-wrapped canonical
    "🤖 Generated with Claude Code",
    "AI-generated feedback",
)


def find_deprecated_disclosure_tags(comment_files: list) -> list:
    """Issue #207: scan per-student comment files for deprecated disclosure-tag
    formats. Returns [(filename, deprecated_tag), ...] — empty if all are clean.

    The canonical tag is DISCLOSURE_TAG, appended automatically at send-time. A
    file carrying an older format would get the canonical tag stacked on top of
    the stale one, so the push refuses (override: --allow-bad-disclosure-tags)
    until the operator removes it. Files with only the canonical tag pass.
    """
    violations: list = []
    for fb in comment_files:
        p = Path(fb)
        try:
            content = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for dep in DEPRECATED_DISCLOSURE_TAGS:
            if dep in content:
                violations.append((p.name, dep))
                break
    return violations


def push_precheck(challenge: Path, fbdir: Path, prefix: str, reviewed: Path,
                  challenge_dir_arg: str) -> tuple:
    """Issue #213 (Fix 2): the required review gate as one testable checkpoint.

    cmd_push calls this before any Canvas write — defense in depth. The
    grade_guardian PreToolUse hook keeps an agent *in* grader_push.py; this keeps
    grader_push.py from pushing an un-reviewed or stale state. Returns
    (blockers, warnings), each a ready-to-print message; a non-empty `blockers`
    means refuse the push.
    """
    blockers: list = []
    warnings: list = []
    comment_files = list(fbdir.glob(f"{prefix}-*.md"))

    # 1. .reviewed marker must exist — the human attested review (#46).
    if not reviewed.exists():
        review_csvs = sorted(challenge.glob(".review*.csv"))
        if comment_files:
            surface = (f"   Review {fbdir}/_all_comments.md and the per-student "
                       f"{prefix}-*.md justifications,")
        elif review_csvs:
            surface = (f"   Review the .review*.csv files in {challenge}/ + "
                       f"{fbdir.name}/_gradebook_actuals.csv (value-only / human-graded path),")
        else:
            surface = (f"   Produce a review surface first (per-student {prefix}-*.md OR "
                       f".review*.csv), then review it,")
        blockers.append(
            "\n⛔ Review required before pushing.\n" + surface +
            "\n   then run:  uv run python lib/tools/grader_push.py --challenge-dir "
            f"{challenge_dir_arg} --mark-reviewed")
        return blockers, warnings  # staleness/consensus need .reviewed to exist

    # 2. .reviewed must not be stale — any review-surface edit after it re-locks (#46).
    rmt = reviewed.stat().st_mtime
    watch = (
        list(fbdir.glob(f"{prefix}-*.md"))
        + [fbdir / "_all_comments.md"]
        + list(challenge.glob(".review*.csv"))
        + [fbdir / "_gradebook_actuals.csv"]
    )
    stale = [p.name for p in watch if p.exists() and p.stat().st_mtime > rmt]
    if stale:
        blockers.append(
            f"\n⛔ {len(stale)} review-surface file(s) changed since you marked reviewed "
            f"(e.g. {stale[0]}). Re-review, then re-run --mark-reviewed.")

    # 3. Consensus presence (warning): AI-drafted work should carry _consensus.csv
    #    (#95 gates this at --mark-reviewed; surfaced here for visibility on
    #    --allow-single-pass runs).
    if comment_files and not (fbdir / "_consensus.csv").exists():
        warnings.append("No feedback/_consensus.csv — was this single-pass graded?")

    return blockers, warnings


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


# Issue #96: letter-grade ranking for the regression check. Standard US scale
# F → A+, no F+/F-/D+? edge cases. Most schools (and Canvas's letter_grade
# grading_type) use these 13 distinct strings; pull-back order is enforced via
# the integer rank. Two-character strings ("A-", "B+") are checked BEFORE
# single-character strings so "A-" doesn't get split as "A" + extra. The map
# is case-insensitive at lookup time.
_LETTER_GRADE_RANK: dict[str, int] = {
    "F":  0,
    "D-": 1, "D": 2, "D+": 3,
    "C-": 4, "C": 5, "C+": 6,
    "B-": 7, "B": 8, "B+": 9,
    "A-": 10, "A": 11, "A+": 12,
}

# Pass/fail strings Canvas returns for the `pass_fail` grading_type. "C" /
# "I" / "P" / "F" single-char aliases are NOT included here — those collide
# with letter grades. Canvas's actual API returns the spelled-out forms.
_PASS_FAIL_RANK: dict[str, int] = {
    "incomplete": 0,
    "complete":   1,
}


def normalize_grade(value: object) -> tuple[str, float | None]:
    """Issue #96: classify a grade value for regression comparison.

    Returns one of:
      ('empty',   None)  — None, "", "-", "EX" (excused; treated as empty for
                            comparison so a first grade isn't blocked, but
                            callers should still surface excused → graded
                            transitions explicitly).
      ('numeric', float) — int, float, or numeric string (incl. "92%" / "3.5").
      ('letter',  int)   — recognized letter grade (case-insensitive); rank is
                            integer 0–12 per _LETTER_GRADE_RANK.
      ('pass_fail', int) — "complete" / "incomplete" (case-insensitive); rank
                            0 or 1.
      ('unknown', None)  — anything else (e.g. a custom rubric tag, a partial
                            string). Callers MUST halt on this rather than
                            silently allow — a grade we can't classify is a
                            grade we can't direction-check.

    The rank is the second tuple element for the three orderable classes;
    higher rank = better grade. For mixed-class comparison (e.g. existing is
    letter, new is numeric) the caller should treat the comparison as
    'mismatch' and halt regardless of rank.
    """
    if value is None:
        return "empty", None
    s = str(value).strip()
    if s == "" or s == "-" or s.upper() == "EX":
        return "empty", None
    # Numeric (incl. "92%" with trailing percent)
    try:
        cleaned = s.rstrip("%").strip()
        n = float(cleaned)
        return "numeric", n
    except (TypeError, ValueError):
        pass
    # Letter grade — uppercase normalization
    upper = s.upper()
    if upper in _LETTER_GRADE_RANK:
        return "letter", float(_LETTER_GRADE_RANK[upper])
    # Pass/fail — lowercase normalization
    lower = s.lower()
    if lower in _PASS_FAIL_RANK:
        return "pass_fail", float(_PASS_FAIL_RANK[lower])
    return "unknown", None


def regression_check(existing: object, new: object) -> str:
    """Issue #96: compare a new grade against the student's current Canvas
    grade. Returns one of:

      'first_fill' — existing is empty (None / "" / "-" / "EX"); pushing a
                     new grade is fine.
      'ok'         — same class; new rank >= existing rank (raise or hold).
      'regression' — same class; new rank <  existing rank (LOWERING).
                     The caller refuses unless --allow-lower was passed.
      'mismatch'   — different classes (letter vs numeric, etc.) — can't
                     direction-check safely; refuse + ask operator.
      'unknown'    — at least one of existing/new is 'unknown' class; refuse
                     + ask operator (a grade we can't classify is a grade we
                     can't direction-check).

    Note: 'first_fill' includes the EX → graded transition. That's
    arguably worth surfacing distinctly later, but for v1 it's not a
    regression (no earned grade is being lowered)."""
    ec, er = normalize_grade(existing)
    nc, nr = normalize_grade(new)
    if nc == "unknown" or ec == "unknown":
        return "unknown"
    if ec == "empty":
        return "first_fill"
    # By this point existing has a known orderable class and rank. If new is
    # empty/None we treat it as a non-push (the push loop will skip rows with
    # no grade anyway) — mark as 'mismatch' to surface rather than allow.
    if nc == "empty":
        return "mismatch"
    if ec != nc:
        return "mismatch"
    assert er is not None and nr is not None  # guaranteed by class != 'empty'/'unknown'
    if nr < er:
        return "regression"
    return "ok"


# Issue #99: sentinel patterns that should HOLD a row rather than push it.
# Operators have historically blanked `final_grade` in the .review.csv to
# "hold" a row, but the push code falls back to `recommended_score` — which
# often contains a placeholder string like `(held)`. On pass_fail
# assignments Canvas silently coerces any non-"complete" string to
# `incomplete` (score 0.0), turning a hold into a wrong fail.
_SENTINEL_KEYWORDS: set[str] = {
    "held", "hold", "not graded", "ungraded", "skip", "skipped",
    "pending", "n/a", "na", "tbd", "todo",
}
_SENTINEL_PAREN_RE = re.compile(r"^\((.+)\)$")


def validate_grade_for_grading_type(grade: str | None, grading_type: str | None) -> tuple[str, str]:
    """Issue #99: validate a posted_grade against the assignment's
    grading_type BEFORE the PUT. Canvas accepts arbitrary strings and
    silently coerces them — e.g. `"(held)"` on a pass_fail assignment
    becomes `incomplete` with score 0.0. This validator refuses the push
    instead of letting the coercion happen.

    Returns one of:
      ('ok',           '')                — grade is legal; push proceeds
      ('sentinel',     <text>)            — recognized placeholder (held /
                                             blank / parenthesized note);
                                             treat as explicit hold, not a
                                             push
      ('invalid',      <text>)            — not a legal grade for this
                                             grading_type; refuse + surface
      ('not_graded',   <text>)            — assignment grading_type is
                                             `not_graded`; no posts allowed
      ('unknown_type', <text>)            — unrecognized grading_type;
                                             proceed without validation
                                             (don't block on
                                             unfamiliar configurations)

    The caller maps these to skip/halt/proceed behaviors.
    """
    s = (grade or "").strip()
    if not s:
        return "sentinel", "blank grade"
    # Sentinel — anything in parens is suspicious (operator notation)
    if _SENTINEL_PAREN_RE.match(s):
        return "sentinel", f"parenthesized sentinel {s!r}"
    if s.lower() in _SENTINEL_KEYWORDS:
        return "sentinel", f"sentinel keyword {s!r}"

    gt = (grading_type or "").lower().strip()
    if not gt:
        return "unknown_type", "no grading_type captured from assignment metadata"
    if gt == "not_graded":
        return "not_graded", (
            "assignment grading_type=not_graded; Canvas accepts no grades here. "
            "If grading is intended, change the assignment's grading_type in Canvas."
        )
    if gt == "pass_fail":
        if s.lower() in {"complete", "incomplete", "pass", "fail"}:
            return "ok", ""
        return "invalid", (
            f"{s!r} is not a valid pass_fail grade "
            "(expected: complete / incomplete / pass / fail)"
        )
    if gt in {"points", "percent", "gpa_scale"}:
        try:
            float(s.rstrip("%").strip())
            return "ok", ""
        except (ValueError, TypeError):
            return "invalid", (
                f"{s!r} is not numeric — grading_type={gt} requires a number"
            )
    if gt == "letter_grade":
        if s.upper() in _LETTER_GRADE_RANK:
            return "ok", ""
        return "invalid", (
            f"{s!r} is not a recognized letter grade "
            "(F / D- / D / D+ / C- / C / C+ / B- / B / B+ / A- / A / A+)"
        )
    return "unknown_type", f"unrecognized grading_type {gt!r}; proceeding without validation"


def truncate_comment_preview(text: str | None, limit: int = 240) -> str:
    """Issue #98: produce a one-line truncated preview of a comment for the
    `--skip-if-student-replied` skip-print. Newlines collapse to single
    spaces (the goal is a one-line skim surface). Past `limit`, the tail
    is replaced with `…` so the preview always fits within `limit` chars.

    `text` is expected to be already FERPA-scrubbed (the caller pulls it
    from the deidentify_submission_comments output — the same scrub
    pipeline as the #62 collision guard). This helper does NOT scrub; it
    only truncates and normalizes whitespace.
    """
    snippet = (text or "").replace("\n", " ").replace("\r", " ").strip()
    if len(snippet) > limit:
        snippet = snippet[: limit - 1] + "…"
    return snippet


def is_yes_refused_on_review(comment_files: list, yes_flag: bool) -> bool:
    """Issue #97: --yes is refused on the LLM-comment review path.

    The `.reviewed` marker attests that a HUMAN reviewed
    `feedback/_all_comments.md` (+ each per-student `<KEY>.md`
    justification). A grading agent under the keyless protocol can pass
    `--yes` and self-attest review — that collapses the
    human-in-the-middle gate. The fix is to refuse the combination on
    the path where comment files exist (LLM-comment grading).

    The value-only / human-graded path keeps `--yes` (the human IS the
    grader; `--yes` there is a script convenience, not an attestation
    bypass).

    Issue #207 (HG-5): the same helper also gates the FINAL push
    confirmation. #97 closed the bypass on `--mark-reviewed`, but `--yes`
    still skipped the "type 'push'" prompt afterward — so an agent that
    re-marks reviewed could chain `--push --yes` and post AI-drafted
    feedback with no human keystroke. On the LLM-comment path, the
    instructor (the top layer) must physically confirm the write.

    Returns True if the caller should refuse the command and exit.
    """
    return bool(comment_files) and bool(yes_flag)


def is_group_mirror_row(row: dict) -> bool:
    """Issue #100: a .review.csv row is a 'group mirror' if its
    `group_mirror_of` column is non-empty — it's not the representative
    submitter for its group; in shared-grade mode, the rep's push
    distributes the grade + comment to this row's student automatically.
    """
    return bool((row.get("group_mirror_of") or "").strip())


def filter_group_mirror_rows(
    rows: list[dict], group_context: dict | None
) -> tuple[list[dict], list[dict]]:
    """Issue #100: on a shared-grade group assignment, split rows into
    (kept, dropped). Mirrored rows whose operator didn't override the
    grade (blank `final_grade`) are dropped — Canvas distributes the
    rep's grade + comment via `comment[group_comment]=true`. Mirrored
    rows where the operator HAS set `final_grade` are kept as explicit
    overrides (individual push for that one student).

    On individual-grade mode or non-group assignments, dropped is
    always empty and rows pass through unchanged.
    """
    if not group_context:
        return rows, []
    if group_context.get("grade_group_students_individually"):
        return rows, []
    kept: list[dict] = []
    dropped: list[dict] = []
    for r in rows:
        if not is_group_mirror_row(r):
            kept.append(r)  # rep row (or non-group row, in mixed contexts)
            continue
        # Mirrored row — operator can override by setting final_grade
        final = (r.get("final_grade") or "").strip()
        if final:
            kept.append(r)  # explicit operator override; push individually
        else:
            dropped.append(r)  # Canvas distributes from the rep


    return kept, dropped


def consensus_gate_status(fbdir: Path) -> tuple[str, list[Path]]:
    """Issue #95: consensus-presence + freshness check.

    Returns one of:
      ('ok', [grader_csvs])      — _consensus.csv exists and is at-or-newer than the
                                   newest _grader*.csv. Push may proceed.
      ('missing', [grader_csvs]) — _consensus.csv does not exist in fbdir.
      ('stale', [grader_csvs])   — _consensus.csv exists but is older than the
                                   newest _grader*.csv (a grader pass was re-run
                                   after consensus; rerun consensus).

    Callers should bypass this check entirely when --allow-single-pass is set.
    The grader_csvs list is returned for the error message regardless of status.
    """
    consensus = fbdir / "_consensus.csv"
    grader_csvs = sorted(fbdir.glob("_grader*.csv"))
    if not consensus.exists():
        return "missing", grader_csvs
    if grader_csvs:
        newest_grader_mtime = max(g.stat().st_mtime for g in grader_csvs)
        if consensus.stat().st_mtime < newest_grader_mtime:
            return "stale", grader_csvs
    return "ok", grader_csvs


def fetch_submissions(base: str, cid: str, headers: dict, aid: str,
                      include_comments: bool = False) -> list[dict]:
    """All submissions for the assignment.

    Default: returns lean {user_id, id, grade, score} per submission.
    `grade` is the displayed string ("3.5" / "B+" / "complete" / None);
    `score` is the numeric value (float or None). Both are needed for
    the issue #96 regression check (numeric vs letter vs pass/fail
    direction comparison).

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
            subs += [
                {
                    "user_id": s["user_id"],
                    "id": s["id"],
                    "grade": s.get("grade"),
                    "score": s.get("score"),
                }
                for s in batch
            ]
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
            "reason": reason,
            # Issue #99: capture grading_type from the same /assignments/:aid
            # call so the push loop can validate posted_grade against it
            # before the PUT (Canvas otherwise silently coerces invalid
            # strings to wrong grades — e.g. "(held)" → incomplete on
            # pass_fail).
            "grading_type": a.get("grading_type") or ""}


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


def assignment_posts_manually(base: str, cid: str, headers: dict, assignment_id) -> bool:
    """True if the assignment uses a MANUAL posting policy. Under manual posting,
    grades written via the API are ENTERED but not released — `posted_at` stays null,
    students can't see them, and the gradebook reads 'needs grading' (issue #199).
    Verified on Canvas: the push payload is correct; the posting policy is the gate."""
    try:
        r = requests.get(f"{base}/api/v1/courses/{cid}/assignments/{assignment_id}",
                         headers=headers, timeout=_TIMEOUT)
        if r.status_code < 400:
            return bool(r.json().get("post_manually"))
    except Exception:
        pass
    return False


def post_assignment_grades(base: str, cid: str, headers: dict, assignment_id) -> tuple[bool, str]:
    """Release entered grades to students via the GraphQL `postAssignmentGrades`
    mutation — the same action as the Gradebook 'Post grades' button (Canvas has no
    REST endpoint for it). Returns (ok, human-readable detail)."""
    query = ("mutation ($a: ID!, $go: Boolean) { postAssignmentGrades("
             "input: {assignmentId: $a, gradedOnly: $go}) "
             "{ progress { _id state } errors { message } } }")
    try:
        r = requests.post(f"{base}/api/graphql", headers=headers,
                          json={"query": query, "variables": {"a": str(assignment_id), "go": True}},
                          timeout=_TIMEOUT)
        payload = (r.json() or {}).get("data", {}).get("postAssignmentGrades") or {}
        errs = payload.get("errors")
        if r.status_code < 400 and not errs:
            prog = payload.get("progress") or {}
            return True, f"(progress {prog.get('_id')}, {prog.get('state')})"
        return False, f"HTTP {r.status_code}: {errs or r.text[:120]}"
    except Exception as e:
        return False, str(e)


def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

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
    ap.add_argument("--post", action="store_true",
                    help="After pushing, release grades to students via the Gradebook 'Post "
                         "grades' action (GraphQL postAssignmentGrades). Needed when the assignment "
                         "uses a MANUAL posting policy — otherwise grades are entered but hidden "
                         "from students and read as 'needs grading' (issue #199).")
    ap.add_argument("--yes", action="store_true",
                    help="Skip the confirmation prompt. NOTE: REFUSED on the "
                         "LLM-comment --mark-reviewed path (issue #97) — a human "
                         "must physically type 'reviewed' there to attest review "
                         "of _all_comments.md. Works on the value-only / "
                         "human-graded review path + on the main --push prompt.")
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
    ap.add_argument("--allow-single-pass", action="store_true",
                    help="Issue #95: explicit opt-out from the 3-pass consensus gate. By default, "
                         "--mark-reviewed refuses to mark an LLM-graded run reviewed unless "
                         "feedback/_consensus.csv exists AND is at least as fresh as the newest "
                         "feedback/_grader*.csv (so the consensus reflects the current grader "
                         "passes, not a stale prior run). Pass this flag for the rare intentional "
                         "case (e.g. a calibration cohort already gated by --mark-calibrated, or "
                         "a one-off where the operator has explicitly accepted single-pass risk).")
    ap.add_argument("--allow-bad-disclosure-tags", action="store_true",
                    help="Issue #207: explicit opt-out from the disclosure-tag validator. By "
                         "default, grader_push refuses to push when a per-student comment file "
                         "carries a deprecated disclosure tag (an older emoji/underscore format), "
                         "because the canonical tag would get stacked on top of it at send-time. "
                         "Pass this flag to push anyway (rare; the stale tag stays in the "
                         "student-visible comment).")
    ap.add_argument("--allow-lower", action="store_true",
                    help="Issue #96: explicit opt-out from the regression-direction gate. By "
                         "default, grader_push refuses to LOWER an existing non-empty Canvas grade "
                         "(numeric / letter / pass-fail aware). A regression skips the row and "
                         "logs '[REGRESSION] uid X: existing → new'. Raising a grade or filling "
                         "an empty grade is unaffected. Pass this flag when a re-grade legitimately "
                         "needs to lower (e.g. an academic-integrity reversal). The bypass is "
                         "logged per row so the audit trail shows the intentional regrade.")
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

            # Issue #95: consensus-presence + freshness gate. An LLM-graded run
            # without _consensus.csv (or with a stale one that predates the
            # newest _grader*.csv) means the 3-pass consensus protocol either
            # never ran or doesn't reflect the current grader output. Refuse
            # unless the operator explicitly opted out via --allow-single-pass.
            # Bypass on calibration runs is implicit: the .calibrated marker
            # already gates --bulk; --single calibration cohorts hit a
            # different review surface and aren't this path.
            if not args.allow_single_pass:
                gate, grader_csvs = consensus_gate_status(fbdir)
                if gate == "missing":
                    print(f"\n⛔ {fbdir.relative_to(challenge)}/_consensus.csv is missing.",
                          file=sys.stderr)
                    print("   The 3-pass consensus protocol either never ran or "
                          "its output was deleted.", file=sys.stderr)
                    print(f"   Found {len(grader_csvs)} grader pass(es): "
                          f"{[g.name for g in grader_csvs]}", file=sys.stderr)
                    print("   Fix: run `uv run python lib/tools/grader_consensus.py "
                          f"--challenge-dir {args.challenge_dir}` (after producing the "
                          "missing passes; grader_grade --bulk runs 3 by default).",
                          file=sys.stderr)
                    print("   Bypass (rare; logged): re-run with --allow-single-pass "
                          "to accept the risk.", file=sys.stderr)
                    return 1
                if gate == "stale":
                    print(f"\n⛔ {fbdir.relative_to(challenge)}/_consensus.csv is "
                          f"older than the newest _grader*.csv — stale consensus.",
                          file=sys.stderr)
                    print("   A grader pass was re-run after consensus was computed. "
                          "Re-run consensus so it reflects the current passes.",
                          file=sys.stderr)
                    print("   Fix: `uv run python lib/tools/grader_consensus.py "
                          f"--challenge-dir {args.challenge_dir}`", file=sys.stderr)
                    print("   Bypass: --allow-single-pass.", file=sys.stderr)
                    return 1
            else:
                print(f"⚠️  --allow-single-pass: skipping the consensus-presence/freshness gate "
                      f"for {fbdir.relative_to(challenge)}/. "
                      "Single-pass grading bypasses the inter-rater-reliability check.")

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

        # Issue #97: refuse --yes on the LLM-comment review path. The risk:
        # an agent grading on the keyless protocol can self-attest review by
        # running `grader_push --mark-reviewed --yes` immediately after
        # writing _all_comments.md, then chain into --push. That collapses
        # "grade" and "push" — the human-in-the-middle review of
        # _all_comments.md never happens. The value-only / human-graded
        # path keeps the --yes shortcut (the human IS the grader; --yes is
        # a script convenience).
        if is_yes_refused_on_review(comment_files, args.yes):
            print(f"\n⛔ --yes is refused on the LLM-comment review path (issue #97).",
                  file=sys.stderr)
            print(f"   The .reviewed marker attests human review of "
                  f"{fbdir.relative_to(challenge)}/_all_comments.md", file=sys.stderr)
            print(f"   + each per-student {prefix}-*.md justification. An agent can "
                  f"pass --yes; a human must physically type 'reviewed'.",
                  file=sys.stderr)
            print(f"   Fix: re-run WITHOUT --yes; eyeball the comments; type "
                  f"'reviewed' at the prompt.", file=sys.stderr)
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

    # Issue #100: read group_context from .fetch_log.json (written by
    # grader_fetch on group assignments). Used below to filter mirror
    # rows (shared-grade mode → Canvas distributes from the rep) and
    # to set comment[group_comment]=true on rep pushes.
    group_context: dict | None = None
    fetch_log_path = challenge / ".fetch_log.json"
    if fetch_log_path.exists():
        try:
            fl = json.loads(fetch_log_path.read_text(encoding="utf-8"))
            group_context = fl.get("group_context")
        except (json.JSONDecodeError, OSError):
            group_context = None

    # Filter mirror rows for shared-grade group assignments. Rows whose
    # operator left final_grade blank get dropped (Canvas distributes
    # the rep's grade); rows where the operator set final_grade are
    # kept as explicit individual overrides.
    is_shared_group_mode = bool(
        group_context and not group_context.get("grade_group_students_individually")
    )
    if is_shared_group_mode:
        rows, dropped_mirror_rows = filter_group_mirror_rows(rows, group_context)
        if dropped_mirror_rows:
            print(f"Issue #100: {len(dropped_mirror_rows)} mirrored group-member "
                  f"row(s) dropped from push plan (shared-grade mode — Canvas "
                  f"distributes the representative's grade + comment to them).")

    # Issue #100: build a key → row lookup so the push loop can check
    # `group_mirror_of` (for setting comment[group_comment]=true on rep
    # rows in shared-grade mode).
    key_to_row: dict[str, dict] = {r.get("key", ""): r for r in rows}

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

    # Issue #96: index existing Canvas grades by uid for the regression gate.
    # fetch_submissions now includes `grade` (display string) + `score` (numeric)
    # per row. The push loop looks up by uid to print before → after and refuse
    # silent regressions (lower-direction grade writes).
    existing_by_uid: dict[int, dict] = {
        int(s["user_id"]): {"grade": s.get("grade"), "score": s.get("score")}
        for s in subs if s.get("user_id") is not None
    }

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
            append_disclosure_tag(comment_for(r.get("feedback_file", ""))) or args.default_comment)
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
    # ---- Issue #99: grading_type capture for posted_grade validation -----
    # Both checks read /assignments/:aid; one fetch serves both. Lifted out
    # of the lock-check conditional because #99's validator needs
    # grading_type even on --grade-only / --no-lock-check pushes (those are
    # the most coercion-prone: a sentinel string on a pass_fail assignment
    # silently became `incomplete` in the DS 250 lived incident).
    locked_resubmit_keys: list[tuple[str, str]] = []
    lock_state: dict = {}
    try:
        lock_state = fetch_assignment_lock_state(base, cid, headers, args.assignment_id)
    except requests.HTTPError as e:
        print(f"WARN: assignment metadata fetch failed "
              f"({type(e).__name__}: {e}); lock-state + grading-type checks disabled.",
              file=sys.stderr)
        lock_state = {"locked_now": False, "grading_type": ""}
    grading_type = (lock_state.get("grading_type") or "").strip()
    # The resubmit-language check is still gated by the flags; only the
    # underlying fetch was lifted.
    if not args.no_lock_check and not args.grade_only and lock_state.get("locked_now"):
        for r in rows:
            key = r.get("key", "")
            comment = comment_for(r.get("feedback_file", "")) or args.default_comment
            if comment and comment_has_resubmit_language(comment):
                locked_resubmit_keys.append((key, comment))
    # ---- end availability + grading-type metadata -----------------------

    # ---- Issue #62: pre-push comment-collision guard --------------------
    # Only run when comments will actually be posted. --grade-only pushes
    # are objective + safe (per the issue: "the grade is safe; qualitative
    # comments cause harm"). --no-collision-check opts out explicitly.
    collisions: dict[str, dict] = {}
    # Issue #98: stash the deid'd latest comment alongside the key so the
    # skip-print can surface its scrubbed text inline (operator triage of
    # benign "I resubmitted" replies vs. unanswered questions in one pass).
    student_replied_latest: dict[str, dict] = {}
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
                    student_replied_latest[key] = latest

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

    if args.skip_if_student_replied and student_replied_latest:
        print(f"\n  --skip-if-student-replied: dropping {len(student_replied_latest)} row(s) where "
              f"the latest comment is from the student:")
        # Issue #98: surface the de-identified latest comment inline so the
        # operator can triage benign "I resubmitted" replies vs. unanswered
        # questions without a separate grader_deidentify_comments pass. The
        # `latest` dict is already FERPA-scrubbed (it came from
        # deidentify_submission_comments above).
        for k in sorted(student_replied_latest):
            latest_c = student_replied_latest[k]
            snippet = truncate_comment_preview(latest_c.get("scrubbed_text"))
            created = latest_c.get("created_at", "")
            print(f"    [{k}] role=self {created}: \"{snippet}\"")
        plan = [(k, u, g, c, (ok and k not in student_replied_latest))
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

    # --- REQUIRED REVIEW GATE (issue #213 Fix 2: push_precheck) ---
    # Issue #46: .reviewed must exist AND be fresh — the watch list is the union
    # of every review surface (comment files, _all_comments.md, .review*.csv,
    # _gradebook_actuals.csv); any of them post-dating the marker re-locks. Now
    # consolidated into one testable checkpoint (push_precheck) that cmd_push runs
    # before any Canvas write.
    pc_blockers, pc_warnings = push_precheck(challenge, fbdir, prefix, reviewed, args.challenge_dir)
    for w in pc_warnings:
        print(f"  ⚠  {w}")
    if pc_blockers:
        for b in pc_blockers:
            print(b)
        return 1

    # --- HG-5 GATE: instructor is the top layer on the AI-drafted push path ---
    # Issue #207: the presence of per-student comment files marks the LLM-comment
    # (AI-drafted) path. On that path --yes must not bypass the final push
    # confirmation — an agent can pass --yes, but a human must decide to write
    # AI-drafted feedback to a live course (HG-5: decision support, not autonomy).
    # The value-only / human-graded path (no comment files) keeps --yes.
    ai_comment_files = list(fbdir.glob(f"{prefix}-*.md"))
    if is_yes_refused_on_review(ai_comment_files, args.yes):
        print("\n⛔ --yes is refused on the AI-drafted push path (issue #207, HG-5).",
              file=sys.stderr)
        print("   Pushing AI-drafted feedback to a live course requires the instructor",
              file=sys.stderr)
        print("   to confirm the write — the instructor is the top layer and decides.",
              file=sys.stderr)
        print("   Fix: re-run WITHOUT --yes; type 'push' at the confirmation prompt.",
              file=sys.stderr)
        return 1

    # Issue #207: refuse deprecated disclosure-tag formats before writing. A stale
    # tag would get the canonical DISCLOSURE_TAG stacked on top of it at send-time.
    tag_violations = find_deprecated_disclosure_tags(ai_comment_files)
    if tag_violations and not args.allow_bad_disclosure_tags:
        print(f"\n⛔ {len(tag_violations)} feedback file(s) carry a deprecated disclosure "
              f"tag (issue #207).", file=sys.stderr)
        for fname, dep in tag_violations:
            print(f"     {fname}: {dep[:40]}", file=sys.stderr)
        print(f"   The canonical tag is {DISCLOSURE_TAG!r} (appended automatically at "
              f"send-time).", file=sys.stderr)
        print("   Fix: remove the stale tag from those files, or pass "
              "--allow-bad-disclosure-tags to override.", file=sys.stderr)
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
    regressions_skipped = 0
    grade_type_skipped = 0
    failed: list[str] = []
    with log.open("a", encoding="utf-8") as lg:
        for key, uid, grade, comment, _ in pushable:
            # Issue #72: held rows post the qualitative comment but
            # WITHHOLD the grade write.
            hold_token = hold_by_key.get(key)

            # Issue #99: grading_type validator. Pre-PUT check that the grade
            # is legal for the assignment's grading_type — refuses sentinels
            # like "(held)" / "not graded" / blanks that Canvas would
            # otherwise silently coerce (e.g. on pass_fail, a non-"complete"
            # string becomes incomplete + score 0.0). Skipped for held rows
            # (those withhold the grade write anyway) and for --grade-only=False
            # rows with no grade (legitimate comment-only / hold-token rows).
            if not hold_token:
                gv_status, gv_reason = validate_grade_for_grading_type(grade, grading_type)
                if gv_status == "sentinel":
                    print(f"  [HOLD] {key}: {gv_reason} — treating as held (no grade pushed)")
                    lg.write(f"- {key}: grade-type-hold uid={uid} grade={grade!r} {gv_reason} "
                             f"on assignment {args.assignment_id}\n")
                    grade_type_skipped += 1
                    continue
                if gv_status == "invalid":
                    print(f"  ⛔ [INVALID-GRADE] {key}: uid={uid}: {gv_reason} — refusing to push")
                    lg.write(f"- {key}: grade-type-invalid uid={uid} grade={grade!r} {gv_reason} "
                             f"on assignment {args.assignment_id}\n")
                    grade_type_skipped += 1
                    continue
                if gv_status == "not_graded":
                    print(f"  ⛔ [NOT-GRADED] {key}: {gv_reason}")
                    lg.write(f"- {key}: grade-type-not_graded uid={uid} {gv_reason} "
                             f"on assignment {args.assignment_id}\n")
                    grade_type_skipped += 1
                    continue
                # 'unknown_type' falls through with a one-time warning so the
                # push isn't blocked on unfamiliar grading types.
                if gv_status == "unknown_type":
                    # Print once per push, not per row, by stashing on the
                    # locals — cheap deduplication.
                    if not getattr(main, "_grade_type_warned", False):
                        print(f"  ⚠️  grading_type {grading_type!r} not recognized — "
                              f"posting grades without per-row validation. ({gv_reason})")
                        main._grade_type_warned = True  # type: ignore[attr-defined]

            # Issue #96: regression gate (numeric / letter / pass-fail). Skip
            # for HELD rows (those don't write the grade). Skip when --allow-lower
            # is set (logged inline so the bypass is auditable).
            existing = existing_by_uid.get(uid, {}) if uid is not None else {}
            existing_grade = existing.get("grade")
            before_repr = (str(existing_grade)
                           if existing_grade is not None and str(existing_grade) != ""
                           else "—")
            if not hold_token:
                rc = regression_check(existing_grade, grade)
                if rc == "regression" and not args.allow_lower:
                    print(f"  ⛔ [REGRESSION] {key}: uid={uid}: {before_repr} → {grade}  "
                          f"— refusing to LOWER (pass --allow-lower to permit)")
                    lg.write(f"- {key}: regression-blocked uid={uid} grade {before_repr} → {grade} "
                             f"on assignment {args.assignment_id} (--allow-lower not set)\n")
                    regressions_skipped += 1
                    continue
                if rc == "mismatch":
                    print(f"  ⛔ [MISMATCH] {key}: uid={uid}: existing={before_repr} new={grade} "
                          f"— grade types differ; cannot direction-check. Skipped (review manually).")
                    lg.write(f"- {key}: regression-mismatch uid={uid} existing={before_repr} "
                             f"new={grade} on assignment {args.assignment_id} (manual review required)\n")
                    regressions_skipped += 1
                    continue
                if rc == "unknown":
                    print(f"  ⛔ [UNKNOWN-CLASS] {key}: uid={uid}: existing={before_repr} new={grade} "
                          f"— can't classify grade. Skipped (review manually).")
                    lg.write(f"- {key}: regression-unknown uid={uid} existing={before_repr} "
                             f"new={grade} on assignment {args.assignment_id} (manual review required)\n")
                    regressions_skipped += 1
                    continue
                if rc == "regression" and args.allow_lower:
                    print(f"  ⚠️  --allow-lower: {key}: uid={uid}: {before_repr} → {grade}  "
                          f"(intentional regression)")

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
            # Issue #100: on shared-grade group assignments, set
            # comment[group_comment]=true for REP rows (where
            # group_mirror_of is empty) so Canvas distributes the
            # comment to all group members. Rows where the operator
            # explicitly set final_grade on a mirrored member skip the
            # flag — those are intentional individual overrides.
            if is_shared_group_mode and comment:
                row_meta = key_to_row.get(key, {})
                if not (row_meta.get("group_mirror_of") or "").strip():
                    data["comment[group_comment]"] = "true"
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
                    print(f"  pushed {key}: {before_repr} → {grade}")
                    lg.write(f"- {key}: grade {before_repr} → {grade} pushed to assignment "
                             f"{args.assignment_id}\n")
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
    if regressions_skipped:
        summary_line += (f"; {regressions_skipped} regression/mismatch row(s) skipped "
                         f"(see [REGRESSION] / [MISMATCH] / [UNKNOWN-CLASS] above; "
                         f"--allow-lower forces a regression through, manual review needed for the others)")
    if grade_type_skipped:
        summary_line += (f"; {grade_type_skipped} grade-type row(s) skipped "
                         f"(see [HOLD] / [INVALID-GRADE] / [NOT-GRADED] above — issue #99)")
    print(f"\n{summary_line}. Logged to {log} (keyed, gitignored).")

    # Issue #199: a MANUAL posting policy ENTERS grades but does not release them —
    # posted_at stays null, students can't see them, and the gradebook reads "needs
    # grading". The push payload is correct (verified on Canvas); the posting policy
    # is the gate. Detect it so hidden grades are never silently shipped as done.
    if pushed and args.push and assignment_posts_manually(base, cid, headers, args.assignment_id):
        if args.post:
            ok, detail = post_assignment_grades(base, cid, headers, args.assignment_id)
            print(f"  ✅ Released grades to students {detail}" if ok
                  else f"  ⚠️  Post-grades FAILED {detail} — use the Gradebook 'Post grades' action.")
        else:
            print(f"\n⚠️  MANUAL posting policy: the {pushed} grade(s) are ENTERED but NOT "
                  "posted — students can't see them and the gradebook shows 'needs grading'. "
                  "Release them via the Gradebook 'Post grades' action, or re-run with --post.")

    if failed:
        print(f"Failed: {failed}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
course_engagement_audit.py — Title IV "last date of academic engagement"
classifier for the course's enrolled students. Produces a faculty-facing
PDF + Markdown report dropped in the user's Downloads folder (NEVER the
repo) so the LLM never has accidental read access to the named output.

Part of the canvas-toolbox audit suite (v0.69.0+). See:
  - lib/agents/knowledge/course_engagement_audit_knowledge.md (Title IV
    research foundation + classification rules + date stamp)
  - lib/agents/knowledge/grader_knowledge.md §1 (FERPA two-zone +
    NEW third tier: ephemeral named report outside the repo)

WHY THIS EXISTS
  Faculty are required under Title IV (34 CFR 668.22 + 2024-2025 +
  2025-2026 FSA Handbook) to report a "last date of academic engagement"
  for any student who unofficially withdraws (stopped engaging without
  a formal withdrawal). The institution's Return-of-Title-IV (R2T4)
  calculation depends on it. Manually trawling SpeedGrader + discussion
  entries + quiz submissions for ~30-200 students at term-end is the
  pain point this tool removes.

WHAT COUNTS AS ACADEMIC ENGAGEMENT (per Title IV)
  ✅ Submitting an assignment (incl. late)
  ✅ Submitting a quiz / taking a quiz attempt
  ✅ Contributing to an online discussion (posts + replies)
  ✅ Initiating instructor contact about course content
       (not directly tracked here; surfaced via the discussion path)

WHAT DOES NOT COUNT (deliberately excluded)
  ❌ Logging into Canvas (per Title IV: "logging in is not sufficient")
  ❌ Viewing a page
  ❌ Canvas `last_activity_at` field (includes page views; not
       compliant for R2T4 documentation)
  ❌ Academic counseling / advising (removed from the list in the
       July 1, 2026 final rules)

CLASSIFICATION (per operator's UF date)
  - NEVER_PARTICIPATED  — no engagement events on record
  - UW (Unofficial Withdrawal) — last engagement < UF date
  - UF (Unofficial Fail)       — UW + current_score < passing threshold
                                   (subset of UW with Title IV stakes)
  - ACTIVE              — last engagement >= UF date

FERPA — THE DOWNLOADS PATTERN
  The audit runs DE-IDENTIFIED end-to-end. Names are looked up at the
  very last step (re-identification) and written ONLY to the report
  destined for the user's Downloads folder — never to a file in the
  repo. The LLM has no working-directory access to ~/Downloads/, so
  the named output is physically outside its read surface. This is
  documented as a third FERPA tier in grader_knowledge.md §1.

USAGE
  uv run python lib/tools/course_engagement_audit.py \\
    --uf-date 2026-04-15

  uv run python lib/tools/course_engagement_audit.py \\
    --uf-date 2026-04-15 --passing-score 60

  # Dry-run: print classification counts only; no file written
  uv run python lib/tools/course_engagement_audit.py \\
    --uf-date 2026-04-15 --dry-run

REQUIRES in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID

TITLE IV SOURCES — VERIFIED 2026-06-26
  - 34 CFR 668.22 — Treatment of Title IV funds when a student
    withdraws (Cornell Law / eCFR)
  - 2025-2026 FSA Handbook, Volume 5, Chapter 1 — General Requirements
    for Withdrawals and Return of Title IV Funds
  - 2025-2026 FSA Handbook, Volume 2, Chapter 1 — Institutional
    Eligibility (academic engagement definition)
  - Federal Register 2025-01-03 (89 FR 31031) — Distance Education and
    Return of Title IV final rules, effective July 1, 2026

  IF YOU READ THIS AFTER ~2027-06: re-verify against the then-current
  FSA Handbook. Title IV rules change periodically; the classification
  thresholds here were validated against the rules in effect 2026-06.
"""
from __future__ import annotations

import argparse
import json
import subprocess

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    pass

_TIMEOUT = 30
_TITLE_IV_VERIFIED_DATE = "2026-06-26"
_TITLE_IV_NEXT_REVIEW = "2027-06-26"


# ---------------------------------------------------------------------------
# Pure helpers (testable without Canvas)
# ---------------------------------------------------------------------------

def parse_uf_date(s: str | None) -> datetime | None:
    """Parse an operator-provided UF date string (YYYY-MM-DD).

    Returns a timezone-aware datetime at midnight UTC, or None on
    unparseable / empty input. We use start-of-day UTC for the cutoff
    so "last engagement on the UF date" counts as ACTIVE (the day OF
    the UF date is still active per Title IV interpretation — UW
    starts the day AFTER last engagement).
    """
    if not s:
        return None
    try:
        d = datetime.strptime(s.strip(), "%Y-%m-%d")
        return d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def resolve_uf_cutoff(arg: str | None, course: dict) -> tuple:
    """Resolve the UF cutoff from an operator arg OR the Canvas course settings.

    So the operator doesn't have to hand-look-up a date: with no --uf-date (or
    'end'/'auto'), use the course's Canvas end date (`end_at`), falling back to the
    enclosing term's end date. 'term-end' forces the term end date. An explicit
    YYYY-MM-DD is used as-is. Canvas end dates are full ISO timestamps; we take the
    date part so the cutoff matches parse_uf_date's start-of-day-UTC semantics
    ("last engagement ON the cutoff day is still ACTIVE").

    Returns (datetime_or_None, source_label). None means nothing resolved — the
    caller should ask for an explicit date.
    """
    key = (arg or "end").strip().lower()
    term_end = ((course.get("term") or {}).get("end_at") or "")
    if key in ("end", "auto"):
        course_end = course.get("end_at") or ""
        if course_end:
            return parse_uf_date(course_end[:10]), "Canvas course end date"
        return parse_uf_date(term_end[:10]), "Canvas term end date"
    if key in ("term-end", "term"):
        return parse_uf_date(term_end[:10]), "Canvas term end date"
    return parse_uf_date(arg), "explicit --uf-date"


def parse_iso_utc(s: str | None) -> datetime | None:
    """Parse a Canvas ISO timestamp to a UTC-aware datetime.

    Canvas returns timestamps like '2026-04-15T18:32:11Z' or
    '2026-04-15T18:32:11+00:00'. Both forms map to UTC.
    """
    if not s:
        return None
    try:
        # Normalize Z → +00:00 for fromisoformat
        s2 = s.strip()
        if s2.endswith("Z"):
            s2 = s2[:-1] + "+00:00"
        d = datetime.fromisoformat(s2)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except (TypeError, ValueError):
        return None


def compute_last_engagement(
    submission_timestamps: list[str],
    discussion_timestamps: list[str],
    quiz_timestamps: list[str],
) -> datetime | None:
    """Issue #(course-engagement-audit): per Title IV academically related
    activity, last engagement is the MAX timestamp across:
      - assignment submissions (submitted_at)
      - quiz submissions (submitted_at)
      - discussion entries (created_at + updated_at)

    Page views, logins, and last_activity_at are EXCLUDED (Title IV
    explicitly says these don't count).

    Returns None if no engagement events on record (NEVER_PARTICIPATED).
    """
    candidates: list[datetime] = []
    for batch in (submission_timestamps, discussion_timestamps, quiz_timestamps):
        for raw in batch:
            d = parse_iso_utc(raw)
            if d is not None:
                candidates.append(d)
    if not candidates:
        return None
    return max(candidates)


def classify_student(
    last_engagement: datetime | None,
    uf_date: datetime | None,
    current_score: float | None,
    passing_score: float = 60.0,
) -> str:
    """Issue #(course-engagement-audit): classify per the Title IV bucket
    scheme. Returns one of:
      - 'NEVER_PARTICIPATED' — no engagement on record
      - 'UF'                — last engagement < UF date AND current_score
                              below passing (federal Title IV concern)
      - 'UW'                — last engagement < UF date but passing-or-
                              missing-grade (still unofficial withdrawal
                              per 34 CFR 668.22 if no passing grade earned)
      - 'ACTIVE'            — last engagement >= UF date (or UF date
                              missing, in which case we default to
                              ACTIVE — caller should require uf_date)

    The UF/UW split is meaningful for Title IV reporting:
      - UF requires R2T4 calculation (Return of Title IV funds)
      - UW is the broader category; some UWs may not need R2T4 if the
        student didn't receive Title IV aid
    The institution's financial aid office makes the final R2T4 call;
    this tool surfaces the candidates.
    """
    if last_engagement is None:
        return "NEVER_PARTICIPATED"
    if uf_date is None:
        # No threshold given → can't classify as UW/UF
        return "ACTIVE"
    if last_engagement >= uf_date:
        return "ACTIVE"
    # last_engagement < uf_date → unofficial withdrawal territory
    if current_score is not None and current_score < passing_score:
        return "UF"
    return "UW"


def downloads_dir() -> Path:
    """Issue #(course-engagement-audit): cross-platform Downloads folder
    detection. Returns the absolute Path. Falls back to ~/Downloads if
    no environment variable overrides it.

    On Linux, XDG_DOWNLOAD_DIR can override (but XDG user-dirs config
    is not consistently set; ~/Downloads is the safe default).
    """
    home = Path.home()
    # Try XDG (Linux) first; fall back to ~/Downloads (works on macOS
    # + Windows + Linux defaults)
    xdg = os.environ.get("XDG_DOWNLOAD_DIR")
    if xdg:
        p = Path(os.path.expanduser(xdg))
        if p.is_dir():
            return p
    candidate = home / "Downloads"
    if candidate.is_dir():
        return candidate
    # Last-ditch: home directory itself. Better than crashing.
    return home


def slugify_course(name: str, maxlen: int = 40) -> str:
    """A filename-safe slug of a COURSE name (a title, not student PII) so a report
    is identifiable across sections: 'Big Data Programming' -> 'big-data-programming'.
    Empty/odd input -> 'course'."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:maxlen].strip("-") or "course"


_CLASS_ORDER = ["UW-never", "UW-before", "F-After"]
_CLASS_MEANING = {
    "UW-never": "never participated — no engagement on record (Title IV: return 100%; there is no last date of academically related activity)",
    "UW-before": "stopped engaging BEFORE the cutoff — an unofficial withdrawal (document the last-engagement date and run R2T4)",
    "F-After": "engaged ON/AFTER the cutoff but FAILING — attended through, a completer-F, not a withdrawal (no R2T4)",
}


def title_iv_class(last_engagement, uf_date, current_score: float | None,
                   passing_score: float) -> str | None:
    """The Title IV flag for a student, or None if they need no flag. The report is
    failing-students-only: a **passing** student (current_score >= passing_score) is
    excluded regardless of engagement. Flagged students are grouped by engagement:

      'UW-never'  — no engagement on record (never participated)
      'UW-before' — failing AND last engagement BEFORE the cutoff (stopped early)
      'F-After'   — failing AND engaged ON/AFTER the cutoff (attended through, failing)
      None        — passing-and-engaged → excluded

    A 'no grade' student counts as failing (they have no earned score); a
    never-participated student is UW-never regardless of grade.
    """
    if last_engagement is None:
        return "UW-never"
    if current_score is not None and current_score >= passing_score:
        return None                                # passing + engaged → excluded
    if uf_date is not None and last_engagement < uf_date:
        return "UW-before"                         # failing, stopped before cutoff
    return "F-After"                               # failing, engaged on/after cutoff


def render_report_md(
    rows: list[dict],
    course_title: str,
    course_id: str,
    uf_date_str: str,
    generated_at: str,
    passing_score: float,
) -> str:
    """Render the FOCUSED Title IV report — ONLY flagged students (UW-never /
    UW-before / F-After). Passing-and-engaged students, and anyone formally dropped
    (deleted/rejected enrollment), are excluded upstream. Input rows are re-identified
    (contain 'name' + 'title_iv_class'). Caller writes to ~/Downloads/ — NEVER the repo.
    """
    by_class: dict[str, list[dict]] = {k: [] for k in _CLASS_ORDER}
    for r in rows:
        by_class.setdefault(r.get("title_iv_class"), []).append(r)
    counts = {k: len(by_class.get(k, [])) for k in _CLASS_ORDER}
    total = sum(counts.values())

    _SECTION_NAME = {
        "UW-never": "Never Participated",
        "UW-before": f"Failing, Last Engagement Before {uf_date_str}",
        "F-After": f"Failing, Last Engagement After {uf_date_str}",
    }

    out: list[str] = [
        f"# Title IV Engagement Report — {course_title}",
        "",
        f"**Course ID:** {course_id}  ",
        f"**UF cutoff date:** {uf_date_str}  ",
        f"**Passing score threshold:** {passing_score}  ",
        f"**Report generated:** {generated_at}  ",
        f"**Title IV definitions verified against:** {_TITLE_IV_VERIFIED_DATE}",
        "",
        "> ⚠️ **Contains student names — generated OUTSIDE the repo for FERPA. Do NOT copy it into a repo folder, cloud-sync it, or email it unencrypted.**",
        "",
        "> Only **flagged** students appear (failing or never-participated), and only **actively-enrolled** ones. **Passing** students are excluded, and so are **withdrawn** students — anyone dropped/deactivated/concluded (inactive, completed, deleted, rejected) is a formally-handled withdrawal, not an *unofficial* one. Pass `--include-inactive` to review borderline cases (e.g. a withdrawal you suspect wasn't processed).",
        "",
        "## Summary",
        "",
        f"- **{counts['UW-never']}** UW-never · **{counts['UW-before']}** UW-before · "
        f"**{counts['F-After']}** F-After · **{total}** flagged total",
        "",
        "Federal reference: 34 CFR 668.22 + 2025-2026 FSA Handbook, Vol 5 Ch 1. Re-verify against the then-current FSA Handbook if reading after ~2027.",
        "",
    ]
    for cls in _CLASS_ORDER:
        bucket = by_class[cls]
        out += [f"## {cls} — {_SECTION_NAME[cls]} ({len(bucket)})", "",
                _CLASS_MEANING[cls], ""]
        if not bucket:
            out += ["_(none)_", ""]
            continue
        out += ["| Student | User ID | Last engagement | Current score | Enrollment |",
                "|---|---|---|---|---|"]
        for r in sorted(bucket, key=lambda x: x.get("name", "")):
            score = r.get("current_score")
            out.append(
                f"| {r.get('name', '(unknown)')} | {r.get('user_id', '')} | "
                f"{r.get('last_engagement_str', '(none)')} | "
                f"{score if score is not None else '(no grade)'} | "
                f"{r.get('enrollment_state', '')} |")
        out.append("")

    out.extend([
        "---",
        "",
        f"_Generated by canvas-toolbox `course_engagement_audit.py` (v{__version__}). Title IV definitions verified {_TITLE_IV_VERIFIED_DATE}; next review {_TITLE_IV_NEXT_REVIEW}._",
        "",
    ])
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Canvas API integration
# ---------------------------------------------------------------------------

def _env_canvas(course_id_override: str | None = None) -> tuple[str, str, str]:
    """Read CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID from env."""
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    base = (os.environ.get("CANVAS_BASE_URL", "") or "").rstrip("/")
    if base and not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    cid = course_id_override or os.environ.get("CANVAS_COURSE_ID", "")
    return tok, base, cid


def fetch_enrollments(
    base: str, cid: str, headers: dict, include_inactive: bool = True,
) -> list[dict]:
    """All StudentEnrollment records for the course. Each carries
    `enrollment_state` so the caller can tell active from inactive.

    Follows the `Link: rel="next"` header instead of blindly incrementing `page`.
    The /enrollments endpoint returns HTTP 400 (not an empty page) when asked for a
    page past the last — so a single-page course (<=100 students) hit page 2, got a
    400, and `raise_for_status()` crashed the whole audit. Same fix already in
    grader_push (issue #67).

    With include_inactive (default), inactive/completed students are returned too:
    for Title IV these are exactly the population to review — a Canvas-inactive
    student may be an unofficial withdrawal (or an already-processed official one),
    and either way the last-date-of-engagement must be documented. The caller
    surfaces them separately rather than auto-classifying them as UW/UF.
    """
    states = ["active", "invited"]
    if include_inactive:
        states += ["inactive", "completed"]
    params: list | None = [
        ("type[]", "StudentEnrollment"),
        ("include[]", "user"),
        ("per_page", 100),
    ] + [("state[]", s) for s in states]
    out: list[dict] = []
    url: str | None = f"{base}/api/v1/courses/{cid}/enrollments"
    while url:
        r = requests.get(
            url, headers=headers,
            params=params if "?" not in url else None,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        out += r.json() or []
        m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link", ""))
        url = m.group(1) if m else None
        params = None  # subsequent pages are pre-parameterized in the next URL
    return out


def fetch_student_submissions(
    base: str, cid: str, headers: dict, user_id: int | str,
) -> list[dict]:
    """All assignment + quiz submissions for one student. Submissions
    include `submitted_at` (None for not-yet-submitted) which is the
    Title IV engagement timestamp. Follows `Link: rel="next"` — blind `page += 1`
    hit page 2 on a single-page result, which `/students/submissions?student_ids[]`
    answers with HTTP 400, so every student looked 'never participated' (issue #67).
    """
    out: list[dict] = []
    url: str | None = f"{base}/api/v1/courses/{cid}/students/submissions"
    params: list | None = [("student_ids[]", str(user_id)), ("per_page", 100)]
    while url:
        r = requests.get(url, headers=headers,
                         params=params if "?" not in url else None, timeout=_TIMEOUT)
        r.raise_for_status()
        out += r.json() or []
        m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link", ""))
        url = m.group(1) if m else None
        params = None
    return out


def fetch_discussion_entries(
    base: str, cid: str, headers: dict, user_id: int | str,
) -> list[str]:
    """ISO timestamps of all discussion entries by one student in the
    course. Walks /courses/:cid/discussion_topics?per_page=100, then
    /discussion_topics/:tid/entries for each topic, filtering by user_id.

    NOTE: this is a per-topic walk; for large courses with many graded
    discussions it can be slow. For most BYUI courses (<10 discussion
    topics), it's fine. Future optimization: parallelize or use
    /courses/:cid/full?include[]=discussion_topics.
    """
    timestamps: list[str] = []
    # Get topic IDs
    page = 1
    topic_ids: list[str] = []
    while True:
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/discussion_topics",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json() or []
        if not batch:
            break
        topic_ids += [str(t.get("id")) for t in batch if t.get("id")]
        page += 1
    uid_str = str(user_id)
    for tid in topic_ids:
        entry_page = 1
        while True:
            r = requests.get(
                f"{base}/api/v1/courses/{cid}/discussion_topics/{tid}/entries",
                headers=headers,
                params={"per_page": 100, "page": entry_page},
                timeout=_TIMEOUT,
            )
            if r.status_code >= 400:
                break  # some topics return 404; skip silently
            batch = r.json() or []
            if not batch:
                break
            for entry in batch:
                if str(entry.get("user_id")) == uid_str:
                    for k in ("updated_at", "created_at"):
                        v = entry.get(k)
                        if v:
                            timestamps.append(v)
            entry_page += 1
    return timestamps


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

@dataclass
class EngagementRow:
    """One row per enrolled student. Built keyed; re-identified at the
    last step before report write."""
    user_id: int
    name: str  # set only at re-id step; empty during keyed processing
    last_engagement: datetime | None
    last_engagement_str: str
    current_score: float | None
    classification: str


def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Title IV last-date-of-academic-engagement classifier "
                    "for the course's enrolled students. Outputs PDF + MD "
                    "to ~/Downloads/ (NEVER the repo) for FERPA reasons.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--uf-date", default=None,
                    help="UF cutoff. YYYY-MM-DD for an explicit date; or 'end' "
                         "(the default) to use the course's Canvas end date, "
                         "falling back to the term end date; or 'term-end' to "
                         "force the term end date. Students whose last engagement "
                         "is BEFORE the cutoff get UW/UF (depending on "
                         "passing-score); engagement >= the cutoff is ACTIVE.")
    ap.add_argument("--course-id", default=None,
                    help="Override CANVAS_COURSE_ID from .env.")
    ap.add_argument("--passing-score", type=float, default=60.0,
                    help="Score threshold below which UW becomes UF "
                         "(Title IV R2T4 candidate). Default: 60.0 (typical "
                         "60%% passing bar).")
    ap.add_argument("--out", default=None,
                    help="Override output path. Default: "
                         "~/Downloads/engagement-<course-name>-<course-id>-<YYYY-MM-DD>.md")
    ap.add_argument("--include-inactive", action="store_true",
                    help="Also include withdrawn students — inactive/completed/deleted/"
                         "rejected enrollments. By DEFAULT they're EXCLUDED: an inactive "
                         "enrollment is a formally-dropped/withdrawn student (already "
                         "handled), not the unofficial withdrawal this report targets. "
                         "Include them only to review borderline cases.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print classification counts only; no file written.")
    ap.add_argument("--rust", action="store_true",
                    help="Use the fast concurrent Rust engine instead of the trusted "
                         "Python default. ONLY after rebuilding the Rust binary from "
                         "current source — an older binary mis-reports engagement "
                         "(every student 'never participated').")
    args = ap.parse_args()

    tok, base, cid = _env_canvas(args.course_id)
    missing = [k for k, v in (("CANVAS_API_TOKEN", tok),
                              ("CANVAS_BASE_URL", base),
                              ("CANVAS_COURSE_ID", cid)) if not v]
    if missing:
        print(f"ERROR: missing env vars: {missing}. Set in .env or pass --course-id.",
              file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {tok}"}

    # Course metadata — title, and the end date we may derive the UF cutoff from.
    try:
        r = requests.get(f"{base}/api/v1/courses/{cid}",
                         headers=headers, params={"include[]": "term"}, timeout=_TIMEOUT)
        r.raise_for_status()
        course = r.json() or {}
        course_title = course.get("name", f"Course {cid}")
    except (requests.HTTPError, requests.RequestException) as e:
        print(f"ERROR: course metadata fetch failed ({type(e).__name__}: {e}).",
              file=sys.stderr)
        return 1

    # Resolve the UF cutoff — from Canvas course/term settings by default, or an
    # explicit --uf-date. Prints the source so the classification date is auditable.
    uf_date, uf_source = resolve_uf_cutoff(args.uf_date, course)
    if uf_date is None:
        if uf_source == "explicit --uf-date":
            print(f"ERROR: invalid --uf-date {args.uf_date!r}. Use YYYY-MM-DD, "
                  "'end', or 'term-end'.", file=sys.stderr)
        else:
            print("ERROR: Canvas has no course or term end date set for this course, "
                  "so the UF cutoff can't be derived. Pass --uf-date YYYY-MM-DD.",
                  file=sys.stderr)
        return 1
    uf_date_str = uf_date.strftime("%Y-%m-%d")

    print(f"Course Engagement Audit (Title IV verified {_TITLE_IV_VERIFIED_DATE})")
    print(f"  Course: {course_title}")
    print(f"  Course ID: {cid}")
    print(f"  UF cutoff: {uf_date_str}  (source: {uf_source})")
    print(f"  Passing score: {args.passing_score}")
    print()

    # Step 1: Fetch enrollments. We get name + user_id together here, but
    # IMMEDIATELY split them — names go into a local keymap dict that
    # we'll use ONLY at the re-id step before writing the named report.
    try:
        enrollments = fetch_enrollments(base, cid, headers,
                                        include_inactive=args.include_inactive)
    except (requests.HTTPError, requests.RequestException) as e:
        print(f"ERROR: enrollment fetch failed ({type(e).__name__}: {e}).",
              file=sys.stderr)
        return 1

    if not enrollments:
        print("No enrollments. Nothing to audit.")
        return 0

    # Build the keymap (user_id → name) IN MEMORY; never written to disk
    # in the repo. Used at re-id step only.
    keymap: dict[int, str] = {}
    for e in enrollments:
        uid = e.get("user_id")
        user = e.get("user") or {}
        name = (user.get("sortable_name") or user.get("name")
                or user.get("short_name") or "").strip()
        if uid is not None and name:
            try:
                keymap[int(uid)] = name
            except (TypeError, ValueError):
                continue

    # Build (user_id, current_score) tuples — KEYED, no names
    keyed_rows: list[dict] = []
    for e in enrollments:
        try:
            uid = int(e.get("user_id"))
        except (TypeError, ValueError):
            continue
        score = e.get("grades", {}).get("current_score") if e.get("grades") else e.get("current_score")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        keyed_rows.append({"user_id": uid, "current_score": score_f,
                           "enrollment_state": (e.get("enrollment_state") or "").lower()})

    n_inactive = sum(1 for r in keyed_rows
                     if r["enrollment_state"] not in ("active", "invited"))
    print(f"  {len(keyed_rows)} enrollment(s) found "
          f"({len(keyed_rows) - n_inactive} active, {n_inactive} inactive). "
          "Fetching engagement events...")

    # Step 2: Per-student engagement events (KEYED — operates on user_id).
    # Engine: the PYTHON implementation is the trusted default. The Rust binary is
    # opt-in (--rust) and, until rebuilt from current source, carries the SAME
    # blind-pagination bug the Python path fixed in 1.8.6 — a compiled Rust binary in
    # the field zeroed out engagement and reported every student as "never
    # participated". A wrong Title IV report is worse than a slow one, so Rust is no
    # longer used unless explicitly requested AND freshly rebuilt.
    script_dir = Path(__file__).parent
    rust_bin = script_dir / "engagement_audit_rs" / "target" / "release" / "engagement-audit"
    if not args.rust:
        rust_bin = None  # trusted Python default

    user_ids = [row["user_id"] for row in keyed_rows]
    engagement_data = {}  # user_id -> {submission_timestamps, discussion_timestamps}

    if rust_bin and rust_bin.exists():
        # Rust path - concurrent fetching (opt-in; must be rebuilt from current source)
        print("  Using Rust implementation (--rust). Ensure it was rebuilt from "
              "current source (older binaries mis-report engagement).", file=sys.stderr)
        try:
            user_ids_csv = ",".join(str(uid) for uid in user_ids)
            result = subprocess.run(
                [
                    str(rust_bin),
                    "--course-id", cid,
                    "--base-url", base,
                    "--token", tok,
                    "--user-ids", user_ids_csv,
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if result.returncode == 0:
                engagement_results = json.loads(result.stdout)
                for item in engagement_results:
                    engagement_data[item["user_id"]] = item
            else:
                print(f"  ⚠ Rust binary failed (exit {result.returncode}), falling back to Python", file=sys.stderr)
                if result.stderr:
                    print(f"  Error: {result.stderr[:200]}", file=sys.stderr)
                # Fall through to Python fallback
                rust_bin = None  # Force Python fallback
        except Exception as e:
            print(f"  ⚠ Rust binary error: {e}, falling back to Python", file=sys.stderr)
            rust_bin = None  # Force Python fallback

    if not rust_bin or not rust_bin.exists():
        # Python — the trusted default engine (correct pagination; #67).
        print("  Fetching engagement (Python engine — the trusted default).",
              file=sys.stderr)
        print("  Sequential, so slow for large courses (~5-10 min for 100+ students). "
              "For speed, rebuild the Rust binary from current source and pass --rust.",
              file=sys.stderr)

        try:
            from _course_engagement_audit_python import run_python_fallback
            engagement_results = run_python_fallback(
                base_url=base,
                course_id=cid,
                token=tok,
                user_ids=user_ids,
            )
            for item in engagement_results:
                engagement_data[item["user_id"]] = item
        except ImportError as e:
            print(f"  ERROR: Failed to import Python fallback: {e}", file=sys.stderr)
            sys.exit(2)

    # Apply engagement data to rows and classify
    for row in keyed_rows:
        uid = row["user_id"]
        data = engagement_data.get(uid, {})
        sub_timestamps = data.get("submission_timestamps", [])
        disc_timestamps = data.get("discussion_timestamps", [])

        last = compute_last_engagement(sub_timestamps, disc_timestamps, [])
        row["last_engagement"] = last
        row["last_engagement_str"] = last.strftime("%Y-%m-%d") if last else "(never)"
        # Flag failing/never-participated students, grouped by engagement timing.
        # Passing-and-engaged → None (excluded). Inactive/completed enrollments ARE
        # classified (they may be unofficial withdrawals); the fetch already excludes
        # formally-dropped (deleted/rejected).
        row["title_iv_class"] = title_iv_class(
            last, uf_date, row["current_score"], args.passing_score)
    print()

    # Report only FLAGGED students — passing-and-engaged are excluded.
    flagged = [r for r in keyed_rows if r.get("title_iv_class")]
    counts: dict[str, int] = {}
    for r in flagged:
        counts[r["title_iv_class"]] = counts.get(r["title_iv_class"], 0) + 1
    print(f"Flagged {len(flagged)} of {len(keyed_rows)} students "
          "(passing-and-engaged excluded):")
    for k in ("UW-never", "UW-before", "F-After"):
        print(f"  {k:12} {counts.get(k, 0):3d}")
    print()

    if args.dry_run:
        print("Dry run — no file written.")
        return 0

    # Step 4: RE-IDENTIFICATION — swap user_id → name for the named report, for the
    # FLAGGED rows only. This is the FIRST place names enter the named-output flow;
    # the re-id'd report lives ONLY in ~/Downloads/, never in the repo.
    named_rows: list[dict] = [
        {**r, "name": keymap.get(r["user_id"], f"(user_id={r['user_id']})")}
        for r in flagged
    ]

    # Step 5: Render report
    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md_content = render_report_md(
        named_rows, course_title, cid, uf_date_str, generated_at, args.passing_score,
    )

    # Step 6: Write to ~/Downloads/ — NEVER the repo
    if args.out:
        out_path = Path(args.out).expanduser()
    else:
        dl = downloads_dir()
        today = datetime.now().strftime("%Y-%m-%d")
        out_path = dl / f"engagement-{slugify_course(course_title)}-{cid}-{today}.md"

    # Defense in depth: refuse to write inside the canvas-toolbox repo dir.
    # The repo lives at whatever the cwd is when this runs; we check by
    # looking for canvas-toolbox-specific markers in the resolved path.
    out_abs = out_path.resolve()
    cwd_abs = Path.cwd().resolve()
    if cwd_abs in out_abs.parents or out_abs == cwd_abs:
        print(f"ERROR: refusing to write named report inside the working directory "
              f"({out_abs}). The Downloads-folder pattern (FERPA tier 3 — see "
              f"grader_knowledge.md §1) requires the named report to live outside "
              f"the repo so the LLM has no working-directory access to it. Pass "
              f"--out with a path outside cwd, or remove --out to use ~/Downloads/.",
              file=sys.stderr)
        return 1

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md_content, encoding="utf-8")
    except OSError as e:
        print(f"ERROR: failed to write report ({e}).", file=sys.stderr)
        return 1

    print(f"Report written: {out_path}")
    print(f"  (named output; outside the repo; FERPA tier 3 — see grader_knowledge.md §1)")
    print()
    print("Next steps:")
    print(f"  1. Open the report: {out_path}")
    print(f"  2. Review the UF + NEVER_PARTICIPATED rows; forward to financial aid for R2T4 if applicable")
    print(f"  3. UW rows: check whether each student earns a passing grade by term end; if not, treat as unofficial withdrawal per 34 CFR 668.22")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

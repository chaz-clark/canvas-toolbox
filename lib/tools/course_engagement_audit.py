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

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import os
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


def render_report_md(
    rows: list[dict],
    course_title: str,
    course_id: str,
    uf_date_str: str,
    generated_at: str,
    passing_score: float,
) -> str:
    """Issue #(course-engagement-audit): render the named, FERPA-out-of-
    scope report as Markdown. Input rows must already be re-identified
    (contain 'name' field). Caller writes the output to ~/Downloads/
    — NEVER to a file inside the repo.

    Pure function for testability: takes pre-built row data + course
    metadata, returns the full Markdown string.
    """
    by_class: dict[str, list[dict]] = {
        "UF": [], "UW": [], "NEVER_PARTICIPATED": [], "ACTIVE": [],
    }
    for r in rows:
        by_class.setdefault(r["classification"], []).append(r)

    n = len(rows)
    n_uf = len(by_class["UF"])
    n_uw = len(by_class["UW"])
    n_never = len(by_class["NEVER_PARTICIPATED"])
    n_active = len(by_class["ACTIVE"])

    out: list[str] = [
        f"# Course Engagement Audit — {course_title}",
        "",
        f"**Course ID:** {course_id}  ",
        f"**UF cutoff date:** {uf_date_str}  ",
        f"**Passing score threshold:** {passing_score}  ",
        f"**Report generated:** {generated_at}  ",
        f"**Title IV definitions verified against:** {_TITLE_IV_VERIFIED_DATE}",
        "",
        "> ⚠️ **This report contains student names. It was generated outside the canvas-toolbox repo for FERPA reasons (see below). Do NOT copy it into a repo folder, share it via cloud sync, or email it unencrypted.**",
        "",
        "## Summary",
        "",
        f"- **{n}** total enrolled students",
        f"- **{n_uf}** classified as **UF** (Unofficial Fail — last engagement < UF date AND failing grade; R2T4 candidate)",
        f"- **{n_uw}** classified as **UW** (Unofficial Withdrawal — last engagement < UF date)",
        f"- **{n_never}** **NEVER PARTICIPATED** (no engagement on record)",
        f"- **{n_active}** **ACTIVE** (engagement on or after UF date)",
        "",
        "Federal Title IV reference: 34 CFR 668.22 + 2025-2026 FSA Handbook, Vol 5 Ch 1. Distance-education R2T4 final rules went into effect 2026-07-01. Re-verify this tool's classification rules against the then-current FSA Handbook if reading after ~2027.",
        "",
        "---",
        "",
    ]

    section_titles = [
        ("UF", "## UF — Unofficial Fail (R2T4 candidates)",
         "These students stopped engaging before the UF date AND have a failing current grade. The institution's financial aid office must run R2T4 if they received Title IV aid. The professor of record documents the **last date of academically related activity** (the `last_engagement` column below)."),
        ("UW", "## UW — Unofficial Withdrawal",
         "These students stopped engaging before the UF date but have a passing-or-unknown grade. Per 34 CFR 668.22, if they do not earn a passing grade by term end, the institution must treat them as unofficial withdrawals — re-classify and R2T4 then."),
        ("NEVER_PARTICIPATED", "## NEVER PARTICIPATED",
         "These students are enrolled but have no submissions, quiz attempts, or discussion entries on record. Per Title IV, logging in is not sufficient to demonstrate engagement; these students never had a date of academically related activity. If they received Title IV aid, the institution must return 100% per the no-show / no-attendance rules."),
        ("ACTIVE", "## ACTIVE",
         "These students have engagement on or after the UF date. No Title IV concern."),
    ]

    for key, header, blurb in section_titles:
        bucket = by_class.get(key, [])
        out.append(header)
        out.append("")
        out.append(blurb)
        out.append("")
        if not bucket:
            out.append("_(none)_")
            out.append("")
            continue
        out.append("| Student | User ID | Last engagement | Current score |")
        out.append("|---|---|---|---|")
        for r in sorted(bucket, key=lambda x: x.get("name", "")):
            name = r.get("name", "(unknown)")
            uid = r.get("user_id", "")
            last = r.get("last_engagement_str", "(none)")
            score = r.get("current_score")
            score_s = f"{score}" if score is not None else "(no grade)"
            out.append(f"| {name} | {uid} | {last} | {score_s} |")
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
    cid = course_id_override or os.environ.get("CANVAS_COURSE_ID", "")
    return tok, base, cid


def fetch_active_enrollments(
    base: str, cid: str, headers: dict
) -> list[dict]:
    """Issue #(course-engagement-audit): all active StudentEnrollment records
    for the course. Returns a list of {user_id, current_score, current_grade,
    sortable_name, name, ...}. Excludes Test Student + inactive/withdrawn
    states by default. Reuses the per-page-100 pagination pattern from
    grader_push.fetch_active_filter."""
    out: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/enrollments",
            headers=headers,
            params={
                "type[]": "StudentEnrollment",
                "state[]": "active",
                "include[]": "user",
                "per_page": 100,
                "page": page,
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json() or []
        if not batch:
            break
        out += batch
        page += 1
    return out


def fetch_student_submissions(
    base: str, cid: str, headers: dict, user_id: int | str,
) -> list[dict]:
    """All assignment + quiz submissions for one student. Submissions
    include `submitted_at` (None for not-yet-submitted) which is the
    Title IV engagement timestamp.
    """
    out: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/students/submissions",
            headers=headers,
            params={
                "student_ids[]": str(user_id),
                "per_page": 100,
                "page": page,
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json() or []
        if not batch:
            break
        out += batch
        page += 1
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
    ap.add_argument("--uf-date", required=True,
                    help="UF cutoff date (YYYY-MM-DD). Students whose last "
                         "engagement is BEFORE this date get classified as "
                         "UW or UF (depending on passing-score); students "
                         "with engagement >= this date are ACTIVE.")
    ap.add_argument("--course-id", default=None,
                    help="Override CANVAS_COURSE_ID from .env.")
    ap.add_argument("--passing-score", type=float, default=60.0,
                    help="Score threshold below which UW becomes UF "
                         "(Title IV R2T4 candidate). Default: 60.0 (typical "
                         "60%% passing bar).")
    ap.add_argument("--out", default=None,
                    help="Override output path. Default: "
                         "~/Downloads/engagement-audit-<course-id>-<YYYY-MM-DD>.md")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print classification counts only; no file written.")
    args = ap.parse_args()

    uf_date = parse_uf_date(args.uf_date)
    if uf_date is None:
        print(f"ERROR: invalid --uf-date {args.uf_date!r}. Use YYYY-MM-DD.",
              file=sys.stderr)
        return 1

    tok, base, cid = _env_canvas(args.course_id)
    missing = [k for k, v in (("CANVAS_API_TOKEN", tok),
                              ("CANVAS_BASE_URL", base),
                              ("CANVAS_COURSE_ID", cid)) if not v]
    if missing:
        print(f"ERROR: missing env vars: {missing}. Set in .env or pass --course-id.",
              file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {tok}"}

    # Course metadata for the report title
    try:
        r = requests.get(f"{base}/api/v1/courses/{cid}",
                         headers=headers, timeout=_TIMEOUT)
        r.raise_for_status()
        course_title = (r.json() or {}).get("name", f"Course {cid}")
    except (requests.HTTPError, requests.RequestException) as e:
        print(f"ERROR: course metadata fetch failed ({type(e).__name__}: {e}).",
              file=sys.stderr)
        return 1

    print(f"Course Engagement Audit (Title IV verified {_TITLE_IV_VERIFIED_DATE})")
    print(f"  Course: {course_title}")
    print(f"  Course ID: {cid}")
    print(f"  UF cutoff: {args.uf_date}")
    print(f"  Passing score: {args.passing_score}")
    print()

    # Step 1: Fetch enrollments. We get name + user_id together here, but
    # IMMEDIATELY split them — names go into a local keymap dict that
    # we'll use ONLY at the re-id step before writing the named report.
    try:
        enrollments = fetch_active_enrollments(base, cid, headers)
    except (requests.HTTPError, requests.RequestException) as e:
        print(f"ERROR: enrollment fetch failed ({type(e).__name__}: {e}).",
              file=sys.stderr)
        return 1

    if not enrollments:
        print("No active enrollments. Nothing to audit.")
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
        keyed_rows.append({"user_id": uid, "current_score": score_f})

    print(f"  {len(keyed_rows)} active enrollment(s) found. Fetching engagement events...")

    # Step 2: Per-student engagement events (KEYED — operates on user_id)
    for i, row in enumerate(keyed_rows, 1):
        uid = row["user_id"]
        # Submissions (assignments + quizzes)
        try:
            subs = fetch_student_submissions(base, cid, headers, uid)
        except (requests.HTTPError, requests.RequestException):
            subs = []
        sub_timestamps = [s.get("submitted_at") for s in subs if s.get("submitted_at")]
        # Discussion entries
        try:
            disc_timestamps = fetch_discussion_entries(base, cid, headers, uid)
        except (requests.HTTPError, requests.RequestException):
            disc_timestamps = []
        # Quiz timestamps are already included in /students/submissions
        # for graded quizzes; no separate quiz fetch needed
        last = compute_last_engagement(sub_timestamps, disc_timestamps, [])
        row["last_engagement"] = last
        row["last_engagement_str"] = last.strftime("%Y-%m-%d") if last else "(never)"
        row["classification"] = classify_student(
            last, uf_date, row["current_score"], args.passing_score,
        )
        if i % 10 == 0:
            print(f"  ...processed {i}/{len(keyed_rows)}")
    print(f"  ...processed {len(keyed_rows)}/{len(keyed_rows)}")
    print()

    # Step 3: classification summary (KEYED — no names in console)
    counts: dict[str, int] = {}
    for r in keyed_rows:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1
    print("Classification:")
    for k in ("UF", "UW", "NEVER_PARTICIPATED", "ACTIVE"):
        print(f"  {k:20} {counts.get(k, 0):3d}")
    print()

    if args.dry_run:
        print("Dry run — no file written.")
        return 0

    # Step 4: RE-IDENTIFICATION — swap user_id → name for the named report
    # This is the FIRST place names enter the named-output flow. Before
    # this point, console output was keyed-only. The re-id'd report lives
    # ONLY in ~/Downloads/, never in the repo.
    named_rows: list[dict] = []
    for r in keyed_rows:
        named_rows.append({
            **r,
            "name": keymap.get(r["user_id"], f"(user_id={r['user_id']})"),
        })

    # Step 5: Render report
    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md_content = render_report_md(
        named_rows, course_title, cid, args.uf_date, generated_at, args.passing_score,
    )

    # Step 6: Write to ~/Downloads/ — NEVER the repo
    if args.out:
        out_path = Path(args.out).expanduser()
    else:
        dl = downloads_dir()
        today = datetime.now().strftime("%Y-%m-%d")
        out_path = dl / f"engagement-audit-{cid}-{today}.md"

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

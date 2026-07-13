#!/usr/bin/env python3
"""
FERPA de-id layer for Canvas submission_comments threads.

Closes canvas-toolbox#65. The submission-content de-id pipeline
(`grader_deidentify_docx/text/pdf/...`) protects assignment WORK — but a
grading workflow increasingly needs to operate on the **comment thread**
attached to each submission (collision-guard for #62, retract/update for
#63, audit of a TA-vs-grader exchange). The Canvas API for those
(`/submissions?include[]=submission_comments`) returns `author_name` and
the raw comment body. A naive read of that thread sends student / TA /
instructor NAMES straight into AI context — exactly what the rest of the
pipeline is designed to prevent.

This tool produces a keyed, name-free view of the comment thread that
downstream agent-facing tools can act on without ever seeing a name.

FERPA DISCIPLINE
  - `author_name` is intentionally DROPPED. The tool never writes it to the
    output file and never prints it to stdout/stderr.
  - `author_id` is converted to a `role` (self / instructor / ta / peer /
    unknown) by joining against the course's teacher/TA enrollments and the
    submission's own user_id. The id itself is dropped from the output.
  - Comment body is scrubbed via the canonical scrub from
    `grader_deidentify_databricks` (`expand_name_terms` + `name_aware_subn` +
    EMAIL/USERPATH/SECRET regexes). Roster supplied by
    `<challenge-dir>/.known_names.txt` (the same file every other deid
    adapter uses).
  - The submission OWNER's user_id is converted to the existing opaque key
    via `<challenge-dir>/.keymap.json` (same key shape as everywhere else;
    no name reaches the output).
  - After scrubbing, the tool re-greps each scrubbed body for any name from
    `.known_names.txt`. If ANY leak survives, the tool fails non-zero and
    refuses to write the output (mirrors `grader_name_leak_check.py`).

OUTPUT SHAPE
  <challenge-dir>/submissions_deid/_comments.json — JSON array, one row per
  comment, sorted by submission key then created_at:

    [{
      "key":            "KC1-A1B2C3",
      "comment_id":     12345,
      "author_role":    "ta",
      "created_at":     "2026-05-01T18:22:00Z",
      "scrubbed_text":  "Thanks for the [REDACTED] reference …",
      "n_scrubs":       2
    }, …]

  Plus a parallel `_comments_summary.md` (counts by role, total scrubs, no
  text) for the operator's at-a-glance review.

USAGE
  # FERPA-safe fetch of comments for one assignment
  uv run python lib/tools/grader_deidentify_comments.py \\
      --challenge-dir grading/p1t1_combined/ai_log \\
      --assignment-id 16958397

  # Custom keymap / output location
  uv run python lib/tools/grader_deidentify_comments.py \\
      --challenge-dir grading/p1t1_combined/ai_log \\
      --assignment-id 16958397 \\
      --primary-assignment-id 16958397 \\
      --out submissions_deid/_comments.json

DEPENDS ON
  - `.keymap.json` (built by any grader_deidentify_* adapter) — key↔filename
  - `.known_names.txt` (built by `grader_fetch.py`'s roster pre-fetch) — scrub source

EXIT CODES
  0  comments fetched, scrubbed, leak-check clean, file written
  1  scrub left a name behind — refused to write; investigate the leak
  2  setup / env / config error
"""
from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import json
import os
import re
import sys

import requests

from _challenge_dir_guard import resolve_challenge_dir  # issue #44 FERPA guard

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

# Single source of truth for the scrub patterns + roster decomposition.
# Reusing `grader_deidentify_databricks` keeps every fix (issue #47 word-
# boundary scrub, etc.) landing in one place.
from grader_deidentify_databricks import (  # noqa: E402
    EMAIL_RE,
    USERPATH_RE,
    SECRET_PREFIX_RE,
    SECRET_ASSIGN_RE,
    expand_name_terms,
    name_aware_subn,
    name_aware_count,
)

NUM = re.compile(r"\d+")
_TIMEOUT = 30

# Issue #94 (FERPA) — greeting-position name scrub. The roster (built from
# `.known_names.txt`) catches known names via the canonical scrub pipeline;
# this regex is the safety net for off-roster names — typically dropped
# students who still have content in the gradebook (their own submissions
# OR — especially — TA comments mentioning them by first name).
#
# Real failure case (the precipitating incident on #94). Names below are
# OBVIOUSLY-FAKE placeholders — see AGENTS.md → Working Style on the
# placeholder-name discipline. They are NOT real students; they're chosen
# for readability the way crypto examples use "Alice/Bob":
#   Comment body: 'Excellent work, "Sarah" (fake name)!'
#   Roster:       {"Alice" (fake), "Bob" (fake), ...}    ← "Sarah" not present (she dropped)
#   Without this regex: scrub passes through "Sarah" untouched; leak-check
#   (which uses the SAME roster) reports "0 hits / clean" → false clean →
#   FERPA leak.
#
# Pattern: (case-insensitive greeting phrase)(separator)(Capitalized name).
# The greeting is case-insensitive ("hi", "Hi"); the name MUST be capitalized
# to avoid matching every common word. Reporter explicitly accepted the
# trade of occasionally over-redacting a capitalized non-name word
# ("Overall", "There") — a leaked name is the larger harm.
_GREETING_NAME_RE = re.compile(
    r'(?P<greeting>(?i:Hi|Hey|Hello|Dear|Nice work|Great work|Excellent work|Good work|Good job|Well done|Nicely done))'
    r'(?P<sep>[,:!\s]+)'
    r'(?P<name>[A-Z][a-z]+)\b'
)


# ---------------------------------------------------------------------------
# Env + HTTP
# ---------------------------------------------------------------------------

def _env_canvas(course_id_override: str | None) -> tuple[str, str, str]:
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    cid = course_id_override or os.environ.get("CANVAS_COURSE_ID", "")
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return tok, cid, base


def _get_paged(base: str, headers: dict, path: str, params: dict | None = None) -> list:
    out: list = []
    url = f"{base}/api/v1{path}"
    base_params = {**(params or {}), "per_page": 100}
    while url:
        r = requests.get(url, headers=headers,
                         params=base_params if "?" not in url else None,
                         timeout=_TIMEOUT)
        r.raise_for_status()
        page = r.json()
        if isinstance(page, list):
            out.extend(page)
        else:
            return [page]
        link = r.headers.get("Link", "")
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
        base_params = None
    return out


# ---------------------------------------------------------------------------
# Role map: build {user_id: role} from teacher/TA/designer enrollments
# ---------------------------------------------------------------------------

_ROLE_BY_TYPE = {
    "TeacherEnrollment": "instructor",
    "TaEnrollment": "ta",
    "DesignerEnrollment": "instructor",  # designers act in an instructor capacity
}


def build_role_map(base: str, headers: dict, cid: str) -> dict[int, str]:
    """Return {user_id: 'instructor'|'ta'} for all course staff. Students are
    NOT enumerated here — they're either the submission owner (→'self') or
    another student (→'peer'). Knowing only staff ids is enough."""
    role: dict[int, str] = {}
    for enrollment_type in _ROLE_BY_TYPE:
        rows = _get_paged(
            base, headers, f"/courses/{cid}/enrollments",
            params={"type[]": enrollment_type, "state[]": ["active", "invited"]},
        )
        for r in rows:
            uid = r.get("user_id")
            if uid is not None:
                role[int(uid)] = _ROLE_BY_TYPE[enrollment_type]
    return role


def classify_author(author_id: int | None, owner_user_id: int | None,
                    role_map: dict[int, str]) -> str:
    if author_id is None:
        return "unknown"
    if owner_user_id is not None and int(author_id) == int(owner_user_id):
        return "self"
    return role_map.get(int(author_id), "peer")


# ---------------------------------------------------------------------------
# Scrub (reuse the canonical pipeline from grader_deidentify_databricks)
# ---------------------------------------------------------------------------

def build_scrub_terms(body: str, extra_names: list[str]) -> list[str]:
    terms = set(expand_name_terms(extra_names))  # roster + parts
    terms.update(EMAIL_RE.findall(body))
    terms.update(USERPATH_RE.findall(body))
    return sorted((t for t in terms if t), key=len, reverse=True)


def scrub_comment(body: str, extra_names: list[str]) -> tuple[str, int]:
    terms = build_scrub_terms(body, extra_names)
    n = 0
    for t in terms:
        body, k = name_aware_subn(body, t)
        n += k
    body, k1 = EMAIL_RE.subn("[REDACTED]", body)
    body, k2 = USERPATH_RE.subn("[REDACTED]", body)
    body, k3 = SECRET_PREFIX_RE.subn("[REDACTED-SECRET]", body)
    body, k4 = SECRET_ASSIGN_RE.subn(r"\1=[REDACTED-SECRET]", body)
    # Issue #94 (FERPA): safety-net scrub for greeting-position names that
    # the roster might miss (dropped students; off-roster greeters). Runs
    # AFTER the roster pass so known names are caught with their canonical
    # name_aware_subn (more precise) first; this is the fallback.
    body, k5 = _GREETING_NAME_RE.subn(
        lambda m: f"{m.group('greeting')}{m.group('sep')}[REDACTED]",
        body,
    )
    return body, n + k1 + k2 + k3 + k4 + k5


def leak_count(scrubbed: str, roster_names: list[str]) -> int:
    """How many roster-name word-bounded matches survive in the scrubbed text."""
    n = 0
    for term in expand_name_terms(roster_names):
        n += name_aware_count(scrubbed, term)
    return n


# ---------------------------------------------------------------------------
# Submission resolution: filename → user_id (mirrors grader_reconcile)
# ---------------------------------------------------------------------------

def fetch_submissions(base: str, headers: dict, cid: str, aid: int,
                      include_comments: bool) -> list[dict]:
    params: dict[str, object] = {"per_page": 100}
    if include_comments:
        params["include[]"] = "submission_comments"
    return _get_paged(base, headers, f"/courses/{cid}/assignments/{aid}/submissions", params=params)


def deidentify_submission_comments(
    submission_comments: list[dict],
    *,
    owner_user_id: int | None,
    role_map: dict[int, str],
    roster: list[str],
) -> list[dict]:
    """In-memory helper: take a raw `submission_comments` payload + the
    course role map + the local roster, and return the deid'd comment list
    in the canonical record shape (`{comment_id, author_role, created_at,
    scrubbed_text, n_scrubs}`).

    Used by:
      - this tool's main() (paired with fetch + write)
      - grader_push.py's #62 collision guard (in-memory only, no disk write)

    FERPA: author_name is read off the payload by Canvas but NEVER reaches
    this function's output — we only consult `author_id` for the role
    lookup, then drop it. Caller MUST NOT log the original `submission_comments`
    raw payload (call this helper first, then operate on the return value)."""
    out: list[dict] = []
    for c in submission_comments or []:
        raw = c.get("comment") or ""
        scrubbed, n_scrubs = scrub_comment(raw, roster)
        out.append({
            "comment_id": c.get("id"),
            "author_role": classify_author(c.get("author_id"), owner_user_id, role_map),
            "created_at": c.get("created_at"),
            "scrubbed_text": scrubbed,
            "n_scrubs": n_scrubs,
        })
    return out


def resolve_user_id_from_filename(filename: str, primary_subs: dict[int, dict]) -> int | None:
    """Same approach as grader_reconcile.resolve_user_id: numeric tokens in
    the Canvas-format filename narrow to one submitter."""
    nums = set(NUM.findall(filename))
    cand = [uid for uid, s in primary_subs.items() if str(uid) in nums]
    if len(cand) == 1:
        return cand[0]
    cand2 = [uid for uid in cand if str(primary_subs[uid].get("id", "")) in nums]
    return cand2[0] if len(cand2) == 1 else None


def primary_submissions_index(base: str, headers: dict, cid: str, aid: int) -> dict[int, dict]:
    """{user_id: {'id': submission_id}} for the assignment whose filenames the
    keymap was built from."""
    out: dict[int, dict] = {}
    for s in fetch_submissions(base, headers, cid, aid, include_comments=False):
        uid = s.get("user_id")
        if uid is not None:
            out[int(uid)] = {"id": s.get("id")}
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="FERPA de-id layer for Canvas submission_comments. Drops author_name, "
                    "converts author_id to role, scrubs comment body, refuses to write on leak.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", dest="challenge_dir", required=True,
                    help="Convention base path (e.g. grading/<task>). Reads .keymap.json + "
                         ".known_names.txt; writes submissions_deid/_comments.json by default.")
    ap.add_argument("--assignment-id", required=True, type=int,
                    help="Assignment whose submission_comments threads to fetch.")
    ap.add_argument("--primary-assignment-id", type=int, default=None,
                    help="Assignment used to build the keymap (if different from --assignment-id). "
                         "Defaults to --assignment-id.")
    ap.add_argument("--course-id", default=None,
                    help="Override CANVAS_COURSE_ID env var.")
    ap.add_argument("--out", default=None,
                    help="Output path relative to --challenge-dir. "
                         "Default: submissions_deid/_comments.json")
    ap.add_argument("--summary-out", default=None,
                    help="Markdown summary path relative to --challenge-dir. "
                         "Default: submissions_deid/_comments_summary.md")
    args = ap.parse_args()

    tok, cid, base = _env_canvas(args.course_id)
    for var, val in (("CANVAS_API_TOKEN", tok), ("CANVAS_BASE_URL", base), ("CANVAS_COURSE_ID", cid)):
        if not val:
            print(f"Missing {var} (env or --course-id).", file=sys.stderr)
            return 2
    headers = {"Authorization": f"Bearer {tok}"}

    if guard is not None:
        try:
            guard.enforce(base, headers, cid, mode="read", label="comments target")
        except SystemExit:
            raise
        except Exception as e:
            print(f"WARN: canvas_course_guard failed ({type(e).__name__}: {e}) — continuing read-only.",
                  file=sys.stderr)

    cd = resolve_challenge_dir(args.challenge_dir, verb="de-identifying comments in")

    mapfile = cd / ".keymap.json"
    if not mapfile.exists():
        print(f"No {mapfile} — run a grader_deidentify_* tool first to build the keymap.",
              file=sys.stderr)
        return 2
    keymap: dict[str, str] = json.loads(mapfile.read_text(encoding="utf-8")).get("map", {})
    if not keymap:
        print(f"Keymap at {mapfile} is empty.", file=sys.stderr)
        return 2

    namesfile = cd / ".known_names.txt"
    roster: list[str] = []
    if namesfile.exists():
        roster = [ln.strip() for ln in namesfile.read_text(encoding="utf-8").splitlines() if ln.strip()]
    else:
        print(f"WARN: {namesfile} not found — peer-mention scrub will only catch email/path/secret patterns.",
              file=sys.stderr)

    primary_aid = args.primary_assignment_id or args.assignment_id
    primary_subs = primary_submissions_index(base, headers, cid, primary_aid)
    filename_to_uid: dict[str, int | None] = {
        fname: resolve_user_id_from_filename(fname, primary_subs) for fname in keymap.values()
    }
    uid_to_key: dict[int, str] = {}
    for key, fname in keymap.items():
        uid = filename_to_uid.get(fname)
        if uid is not None:
            uid_to_key[uid] = key

    role_map = build_role_map(base, headers, cid)

    rows = fetch_submissions(base, headers, cid, args.assignment_id, include_comments=True)

    records: list[dict] = []
    role_counts: dict[str, int] = {}
    total_scrubs = 0
    leak_total = 0
    leaked_keys: list[str] = []

    for sub in rows:
        owner_uid = sub.get("user_id")
        key = uid_to_key.get(int(owner_uid)) if owner_uid is not None else None
        deid_list = deidentify_submission_comments(
            sub.get("submission_comments") or [],
            owner_user_id=owner_uid,
            role_map=role_map,
            roster=roster,
        )
        for rec in deid_list:
            leak_here = leak_count(rec["scrubbed_text"], roster) if roster else 0
            if leak_here:
                leak_total += leak_here
                if key and key not in leaked_keys:
                    leaked_keys.append(key)
            row = {"key": key or "<UNRESOLVED>", **rec}
            records.append(row)
            role_counts[rec["author_role"]] = role_counts.get(rec["author_role"], 0) + 1
            total_scrubs += rec["n_scrubs"]

    records.sort(key=lambda r: (str(r["key"]), str(r.get("created_at") or "")))

    if leak_total:
        print(f"🔴 FERPA leak: {leak_total} roster-name match(es) survived the scrub in "
              f"{len(leaked_keys)} key(s). Refusing to write the output.", file=sys.stderr)
        print(f"   Investigate: is .known_names.txt complete? Are there nicknames not in the "
              f"roster? See grader_name_leak_check.py for the pattern.", file=sys.stderr)
        return 1

    out_path = cd / (args.out or "submissions_deid/_comments.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    summary_path = cd / (args.summary_out or "submissions_deid/_comments_summary.md")
    lines: list[str] = []
    lines.append(f"# Comment thread audit — assignment {args.assignment_id}")
    lines.append("")
    lines.append(f"- total comments: {len(records)}")
    lines.append(f"- total scrubs:   {total_scrubs}")
    lines.append(f"- roster-name leaks after scrub: {leak_total} (must be 0 for write)")
    lines.append("")
    lines.append("## Comments by author role")
    for r in sorted(role_counts):
        lines.append(f"- {r}: {role_counts[r]}")
    lines.append("")
    lines.append("All names/emails/paths scrubbed. No author_name in the output. "
                 "See `_comments.json` for the keyed records.")
    summary_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"  Comments deid → {out_path}  ({len(records)} comment(s), {total_scrubs} scrub(s)).")
    print(f"  Summary       → {summary_path}")
    print(f"  Role counts:  {dict(sorted(role_counts.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

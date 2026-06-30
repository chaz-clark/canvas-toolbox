#!/usr/bin/env python3
"""
Read-only submission-health check — flag submissions that look BROKEN
rather than absent, so a technical upload failure isn't graded as
missing work.

Closes canvas-toolbox#64. A real grading run lost effort to a silent
failure: a student's uploads did not render ("none of your submissions
rendered" per the TA), so the gradebook recorded them as missing, the
count-based competency grader read 1/4 tasks completed and assigned an F.
A purely count-based grader silently punishes a *technical* failure as
*missing work*.

WHAT IT DOES
  For each submission of one assignment, run cheap metadata + body
  heuristics and flag anything that looks broken-not-absent:

    likely_empty_upload      attachment present but size < threshold
                             (default 100 bytes — a corrupted upload that
                             made it past Canvas's submit step)
    unexpected_content_type  attachment's content-type doesn't match the
                             assignment's expected submission_types (e.g.
                             a `.exe` on an `online_upload` asking for
                             `.docx`)
    empty_text_entry         online_text_entry submitted with no body
                             text after whitespace strip
    empty_url                online_url submitted with no URL string
    submitted_but_nothing    submitted_at is set but no attachments AND
                             no body AND submission_type is one that
                             requires content (online_upload /
                             online_text_entry / online_url). The
                             "submitted nothing" case.

  Default output: human-readable text table. `--format json` for
  programmatic use (e.g. piping to a downstream meta-summary).

  ALL flagged rows print as "REVIEW — possible rendering/submission
  failure, not missing work" so the operator manually verifies before a
  low grade flows into the gradebook or feeds the competency grader (#60).

FERPA
  Read-only assignment + submission metadata only. Emits user_id (LMS row
  id — FERPA-safe per the toolkit's standing rule). If --challenge-dir is
  passed and `.keymap.json` exists, maps user_id → existing opaque key
  for the canonical anonymous report.

USAGE
  # By user_id (no challenge-dir context — useful before fetch is run)
  uv run python lib/tools/grader_submission_health.py
      --course-id 409936 --assignment-id 16958397

  # Keyed output for a graded cohort (reads .keymap.json)
  uv run python lib/tools/grader_submission_health.py
      --challenge-dir grading/p1t1_combined/ai_log
      --assignment-id 16958397

  # JSON
  uv run python lib/tools/grader_submission_health.py
      --course-id 409936 --assignment-id 16958397 --format json

EXIT CODES
  0  ran; printed any flags found (a 0-flag report is a clean run, not
     an error)
  2  setup / env / Canvas API error

KNOWN SCOPE LIMITATION
  v1 doesn't dereference attachment URLs to inspect the rendered body
  for in-document render-error markers ("Failed to render", "Error 500").
  That requires N extra HTTP fetches per assignment + per-MIME parsing,
  and the cheap size + content-type + body checks already catch the
  common case ("upload made it to Canvas but is 0 bytes / wrong type").
  Future enhancement: --deep-check that downloads + renders each
  attachment through the existing deid adapters' fallback path.
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

NUM = re.compile(r"\d+")
_TIMEOUT = 30
_NEAR_ZERO_BYTES = 100  # tunable; anything below this on an upload is suspect


# Content-type hints by submission_type. Loose — Canvas serves a wide
# variety of MIMEs for "online_upload" assignments and we only want to
# flag clearly-wrong types (e.g. `application/x-msdownload` on a docx-
# expected assignment). For unknown/unconfigured types, skip the check.
_EXPECTED_CT_HINTS = {
    "online_upload": None,  # any — Canvas accepts anything by default
}


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


def _get_paged(base: str, headers: dict, path: str, params=None) -> list:
    out: list = []
    url = f"{base}/api/v1{path}"
    base_params = list(params or [])
    base_params.append(("per_page", 100))
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


def _get_assignment(base: str, headers: dict, cid: str, aid: int) -> dict:
    r = requests.get(f"{base}/api/v1/courses/{cid}/assignments/{aid}",
                     headers=headers, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json() or {}


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

def classify_submission(sub: dict, allowed_types: list[str]) -> list[str]:
    """Return a list of flag strings (empty list = clean)."""
    flags: list[str] = []
    submitted_at = sub.get("submitted_at")
    sub_type = sub.get("submission_type")
    attachments = sub.get("attachments") or []
    body = (sub.get("body") or "").strip()
    url = (sub.get("url") or "").strip()

    if submitted_at is None and not attachments and not body and not url:
        return flags  # genuinely unsubmitted, not "broken"

    # Likely-empty upload(s)
    for att in attachments:
        size = att.get("size")
        if size is not None and int(size) < _NEAR_ZERO_BYTES:
            flags.append(f"likely_empty_upload (size={size}B < {_NEAR_ZERO_BYTES})")
        # Content-type mismatch — only when assignment hints at a type and
        # the attachment is clearly something else. Conservative: only
        # `application/x-msdownload` / `application/octet-stream` on a
        # course that expects a document is worth surfacing.
        ct = (att.get("content-type") or att.get("content_type") or "").lower()
        if allowed_types and "online_upload" in allowed_types and ct in (
            "application/x-msdownload",
            "application/x-executable",
        ):
            flags.append(f"unexpected_content_type (content-type={ct})")

    if "online_text_entry" in (allowed_types or []) and sub_type == "online_text_entry":
        if not body:
            flags.append("empty_text_entry")

    if "online_url" in (allowed_types or []) and sub_type == "online_url":
        if not url:
            flags.append("empty_url")

    # "Submitted but nothing" — submitted_at exists, but no attachments AND
    # no body AND no url AND the assignment expects content. Only fires
    # when the type-specific flags above didn't already catch this (e.g.
    # empty_text_entry covers the body-empty case for online_text_entry).
    has_type_flag = any(f.startswith("empty_text_entry") or f.startswith("empty_url")
                        or f.startswith("likely_empty_upload") for f in flags)
    if (submitted_at is not None and not attachments and not body and not url
            and not has_type_flag):
        if any(t in (allowed_types or []) for t in
               ("online_upload", "online_text_entry", "online_url")):
            flags.append("submitted_but_nothing")

    return flags


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def render_text(records: list[dict], assignment_name: str, course_id: str,
                assignment_id: int, total_subs: int) -> str:
    lines: list[str] = []
    lines.append(f"== grader_submission_health  course={course_id}  "
                 f"assignment={assignment_id} ({assignment_name}) ==")
    lines.append("")
    flagged = [r for r in records if r["flags"]]
    lines.append(f"Submissions scanned: {total_subs}")
    lines.append(f"Flagged for review:  {len(flagged)}")
    lines.append("")
    if flagged:
        lines.append("REVIEW — possible rendering/submission failure, not missing work:")
        for r in flagged:
            ident = r.get("key") or f"user_id={r['user_id']}"
            lines.append(f"  [{ident}]  submitted_at={r['submitted_at']}  "
                         f"submission_type={r['submission_type']}")
            for f in r["flags"]:
                lines.append(f"      !! {f}")
    else:
        lines.append("(no flags — all submissions look healthy)")
    return "\n".join(lines)


def render_json(records: list[dict], assignment_id: int, total_subs: int) -> str:
    flagged = [r for r in records if r["flags"]]
    payload = {
        "tool": "grader_submission_health",
        "version": __version__,
        "assignment_id": assignment_id,
        "summary": {"scanned": total_subs, "flagged": len(flagged)},
        "flagged": flagged,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Read-only submission-health check. Flag submissions that look broken "
                    "rather than absent, so a technical failure isn't graded as missing work "
                    "(issue #64).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--assignment-id", required=True, type=int,
                    help="Canvas assignment id to scan.")
    ap.add_argument("--course-id", default=None,
                    help="Override CANVAS_COURSE_ID env var.")
    ap.add_argument("--challenge-dir", default=None,
                    help="If provided AND .keymap.json exists under it, the output uses the "
                         "existing opaque keys instead of user_ids (FERPA-anonymous report).")
    ap.add_argument("--format", choices=("text", "json"), default="text",
                    help="Output format. Default: text.")
    args = ap.parse_args()

    tok, cid, base = _env_canvas(args.course_id)
    for var, val in (("CANVAS_API_TOKEN", tok), ("CANVAS_BASE_URL", base), ("CANVAS_COURSE_ID", cid)):
        if not val:
            print(f"Missing {var} (env or --course-id).", file=sys.stderr)
            return 2
    headers = {"Authorization": f"Bearer {tok}"}

    if guard is not None:
        try:
            guard.enforce(base, headers, cid, mode="read", label="submission-health target")
        except SystemExit:
            raise
        except Exception as e:
            print(f"WARN: canvas_course_guard failed ({type(e).__name__}: {e}) — continuing read-only.",
                  file=sys.stderr)

    try:
        assignment = _get_assignment(base, headers, cid, args.assignment_id)
        allowed_types = list(assignment.get("submission_types") or [])
        subs = _get_paged(
            base, headers, f"/courses/{cid}/assignments/{args.assignment_id}/submissions",
            params=[("include[]", "submission_history")],
        )
    except requests.HTTPError as e:
        print(f"Canvas API error: {e}", file=sys.stderr)
        return 2

    # Optional keymap for anonymous output
    uid_to_key: dict[int, str] = {}
    if args.challenge_dir:
        from _challenge_dir_guard import resolve_challenge_dir  # noqa: E402
        cd = resolve_challenge_dir(args.challenge_dir, verb="auditing health of")
        keymap_file = cd / ".keymap.json"
        if keymap_file.exists():
            keymap = json.loads(keymap_file.read_text(encoding="utf-8")).get("map", {})
            # Build user_id → key by matching numeric ids in the keymap's
            # filenames against the submissions list (same approach as
            # grader_reconcile.resolve_user_id).
            for s in subs:
                uid = s.get("user_id")
                if uid is None:
                    continue
                for key, fname in keymap.items():
                    nums = set(NUM.findall(fname))
                    if str(uid) in nums and str(s.get("id")) in nums:
                        uid_to_key[int(uid)] = key
                        break

    records: list[dict] = []
    for s in subs:
        # Pull the most recent submission_history entry that actually has
        # content (Canvas leaves earlier 'unsubmitted' shells in the array).
        history = s.get("submission_history") or [s]
        best = next(
            (h for h in reversed(history) if (h.get("attachments") or h.get("body") or h.get("url"))),
            s,
        )
        flags = classify_submission(best, allowed_types)
        records.append({
            "user_id": s.get("user_id"),
            "key": uid_to_key.get(int(s["user_id"])) if s.get("user_id") is not None else None,
            "submission_type": best.get("submission_type"),
            "submitted_at": best.get("submitted_at"),
            "flags": flags,
        })

    if args.format == "json":
        print(render_json(records, args.assignment_id, len(records)))
    else:
        print(render_text(records, assignment.get("name") or "?", cid,
                          args.assignment_id, len(records)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

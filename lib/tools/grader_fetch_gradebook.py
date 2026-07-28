#!/usr/bin/env python3
"""grader_fetch_gradebook.py — mirror the LIVE Canvas gradebook locally, de-identified.

The shared gradebook primitive. One API sweep → a user_id-keyed score matrix cached
under `.canvas/gradebook/`, stamped with `fetched_at`, so any skill/tool can reuse a
fresh copy instead of re-hitting Canvas per assignment. This is the upstream input
`grader_standing` (the "your grade" column) and `grader_reconcile` actually need: the
WHOLE multi-assignment gradebook, not one assignment at a time.

ONLINE mirror — distinct from offline `.imscc` mode; it fetches from Canvas over the
API. **De-identified by DEFAULT**: rows are keyed by Canvas `user_id`, columns are
assignment names, cells are scores. NO student names → the cache is FERPA Zone-1
(LLM-safe) and every skill can read it. To turn it into a named report for a human,
pipe it through `grader_reidentify_gradebook.py` (which reads the local keymap).

Freshness: skips the fetch if the cache is younger than `--max-age-hours` (default 6);
`--force` always refreshes. The Test Student is excluded (#61).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from _env_loader import force_utf8_console, load_env
    load_env()
except ImportError:
    def force_utf8_console() -> None:
        pass

import requests

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

from grader_push import _env_canvas  # single source of truth for Canvas env

_TIMEOUT = 30
_DEFAULT_OUT = Path(".canvas/gradebook")


def _get_paged(base: str, headers: dict, path: str, params: dict | None = None) -> list:
    """GET a Canvas collection, following the `Link: rel="next"` header (NOT blind
    page++ — several endpoints 400 past the last page; issue #67)."""
    out: list = []
    p = {**(params or {}), "per_page": 100}
    url: str | None = f"{base}{path}"
    while url:
        r = requests.get(url, headers=headers, params=p if "?" not in url else None,
                         timeout=_TIMEOUT)
        r.raise_for_status()
        batch = r.json() or []
        out += batch if isinstance(batch, list) else [batch]
        m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link", ""))
        url = m.group(1) if m else None
        p = None
    return out


def fetch_assignments(base: str, cid: str, headers: dict) -> list[dict]:
    """[{id, name, points_possible, position}] in gradebook order."""
    raw = _get_paged(base, headers, f"/api/v1/courses/{cid}/assignments")
    cols = [{"id": int(a["id"]), "name": a.get("name") or f"assignment_{a['id']}",
             "points_possible": a.get("points_possible"),
             "position": a.get("position") or 0} for a in raw]
    cols.sort(key=lambda c: c["position"])
    return cols


def fetch_scores_by_user(base: str, cid: str, headers: dict) -> dict:
    """{user_id: {assignment_id: score}} — one grouped sweep over all students."""
    raw = _get_paged(base, headers, f"/api/v1/courses/{cid}/students/submissions",
                     {"student_ids[]": "all", "grouped": "true"})
    by_user: dict[int, dict] = {}
    for entry in raw:
        uid = entry.get("user_id")
        if uid is None:
            continue
        cell = by_user.setdefault(int(uid), {})
        for s in entry.get("submissions") or []:
            aid = s.get("assignment_id")
            if aid is not None:
                cell[int(aid)] = s.get("score")
    return by_user


def test_student_id(base: str, cid: str, headers: dict) -> int | None:
    try:
        r = requests.get(f"{base}/api/v1/courses/{cid}/student_view_student",
                         headers=headers, timeout=_TIMEOUT)
        if r.status_code < 400:
            return int((r.json() or {}).get("id"))
    except (requests.RequestException, TypeError, ValueError):
        pass
    return None


def build_matrix(assignments: list[dict], scores_by_user: dict,
                 exclude: set) -> tuple[list[str], list[list]]:
    """Header + rows for the de-identified CSV. Columns disambiguate duplicate
    assignment names by appending the id. Rows sorted by user_id (deterministic)."""
    seen: dict[str, int] = {}
    headers_row = ["user_id"]
    col_order: list[int] = []
    for a in assignments:
        name = a["name"]
        if name in seen:
            name = f"{name} ({a['id']})"
        seen[a["name"]] = seen.get(a["name"], 0) + 1
        headers_row.append(name)
        col_order.append(a["id"])
    rows: list[list] = []
    for uid in sorted(scores_by_user):
        if uid in exclude:
            continue
        cells = scores_by_user[uid]
        rows.append([uid] + [cells.get(aid, "") for aid in col_order])
    return headers_row, rows


def is_fresh(meta_path: Path, max_age_hours: float, now: datetime) -> bool:
    """True if a cached meta records a fetch younger than max_age_hours."""
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(meta["fetched_at"].replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError):
        return False
    age_h = (now - fetched).total_seconds() / 3600.0
    return age_h < max_age_hours


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(
        description="Mirror the live Canvas gradebook locally (de-identified, cached).")
    ap.add_argument("--course-id", default=None, help="defaults to $CANVAS_COURSE_ID")
    ap.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT,
                    help=f"cache dir (default {str(_DEFAULT_OUT)!r}, gitignored)")
    ap.add_argument("--max-age-hours", type=float, default=6.0,
                    help="skip the fetch if the cache is younger than this (default 6)")
    ap.add_argument("--force", action="store_true", help="refresh even if fresh")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    args = ap.parse_args()

    tok, env_cid, base = _env_canvas()
    cid = args.course_id or env_cid
    if not (tok and base and cid):
        print("⛔ set CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID (or --course-id).",
              file=sys.stderr)
        return 1
    headers = {"Authorization": f"Bearer {tok}"}
    now = datetime.now(tz=timezone.utc)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.out_dir / f"gradebook_{cid}.csv"
    meta_path = args.out_dir / f".fetch_meta_{cid}.json"

    if not args.force and csv_path.exists() and is_fresh(meta_path, args.max_age_hours, now):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        print(f"✓ gradebook cache is fresh ({meta.get('fetched_at')}); "
              f"{meta.get('student_count')} students × {meta.get('assignment_count')} "
              f"assignments at {csv_path}. Pass --force to refresh.")
        return 0

    print(f"Mirroring gradebook for course {cid} …")
    assignments = fetch_assignments(base, cid, headers)
    scores = fetch_scores_by_user(base, cid, headers)
    exclude = {tsid} if (tsid := test_student_id(base, cid, headers)) is not None else set()
    header_row, rows = build_matrix(assignments, scores, exclude)

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header_row)
        w.writerows(rows)

    meta = {
        "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "course_id": str(cid),
        "assignment_count": len(assignments),
        "student_count": len(rows),
        "assignments": [{"id": a["id"], "name": a["name"],
                         "points_possible": a["points_possible"]} for a in assignments],
        "deidentified": True,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"✓ wrote {len(rows)} students × {len(assignments)} assignments → {csv_path}")
    print(f"  meta → {meta_path} (fetched_at {meta['fetched_at']})")
    print("  De-identified (user_id-keyed, no names — FERPA Zone-1). For a named report, "
          "run grader_reidentify_gradebook.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

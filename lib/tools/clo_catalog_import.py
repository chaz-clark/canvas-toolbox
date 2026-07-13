#!/usr/bin/env python3
"""
clo_catalog_import.py — pull a course's CLOs from the institution catalog and
(with --write) create them as Canvas Outcomes. API-ONLY.

WHY API-only: a `.imscc` export has NO course outcomes (they live at the account
level in Canvas), so offline mode can't produce them. Outcomes are written
straight to Canvas via the REST API — the same reason SAS accommodations and
quiz-time extensions are API-only.

SOURCE: the institution's Kuali public catalog API. Discovered/verified against
BYU-Idaho (byui.kuali.co), whose per-course `outcomes` field is already a
structured list of {id, value} — no HTML scraping. Any Kuali-hosted catalog at
`<institution>.kuali.co` follows the same shape; `--catalog-host` overrides the
host if it differs from `<institution>.kuali.co`.

  catalogs   GET /api/v1/catalog/public/catalogs/            -> [{_id/id, title}]
  index      GET /api/v1/catalog/courses/<catalogId>         -> [{__catalogCourseId, pid, id, title}]
  detail     GET /api/v1/catalog/course/<catalogId>/<pid>    -> {..., outcomes:[{id,value}]}

FLOW (read-only by default — you must pass --write to touch Canvas):
  1. Resolve <course-code> in the catalog (newest catalog first, or --catalog).
  2. Print the resolved course + its CLOs (the preview). Stop here unless --write.
  3. --write: guard the target course (refuses enrolled/blueprint children unless
     --allow-enrolled), then create each CLO as a Canvas Outcome. Idempotent —
     an outcome whose title already exists is skipped, so re-runs don't duplicate.

Each CLO becomes one Canvas Outcome: title "<CODE> CLO <n>", description = the
CLO text. (Re-import after the catalog text changes will NOT rewrite an existing
outcome — it skips by title. Editing text is a future enhancement.)

Usage:
  # read-only preview (no token needed to just look? — still needs online mode)
  uv run python canvas_toolbox/lib/tools/clo_catalog_import.py --course-code DS250
  # write into the sandbox
  uv run python canvas_toolbox/lib/tools/clo_catalog_import.py --course-code DS250 \
      --target CANVAS_SANDBOX_ID --write
  # write into a specific course id
  uv run python canvas_toolbox/lib/tools/clo_catalog_import.py --course-code ITM327 \
      --course-id 402262 --write --allow-enrolled

Exit codes:
  0  success (preview shown, or write completed)
  2  config error / course not found in catalog / guard refusal
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys

import requests
from dotenv import load_dotenv

import canvas_course_guard as guard
from _canvas_mode import check_mode_requirements

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url
_TIMEOUT = 30


# --------------------------------------------------------------------------
# Institution / catalog resolution
# --------------------------------------------------------------------------
def default_institution() -> str | None:
    """CANVAS_INSTITUTION, else the subdomain of CANVAS_BASE_URL (byui.* -> byui)."""
    inst = (os.environ.get("CANVAS_INSTITUTION") or "").strip().lower()
    if inst:
        return inst
    host = re.sub(r"^https?://", "", CANVAS_BASE_URL)
    sub = host.split(".")[0] if host else ""
    return sub or None


def catalog_base(host: str) -> str:
    return f"https://{host}/api/v1/catalog"


def _cid(catalog: dict) -> str | None:
    return catalog.get("_id") or catalog.get("id")


def list_catalogs(host: str) -> list[dict]:
    r = requests.get(f"{catalog_base(host)}/public/catalogs/", timeout=_TIMEOUT)
    r.raise_for_status()
    cats = r.json()
    return cats if isinstance(cats, list) else []


def resolve_course(host: str, course_code: str, catalog_filter: str | None = None):
    """Find course_code across catalogs (newest first). Return a dict or None.

    catalog_filter: a substring matched against catalog titles (e.g. "2026-2027"),
    or an exact catalog id. When None, every catalog is searched newest-first.
    """
    want = course_code.replace(" ", "").upper()
    cats = list(reversed(list_catalogs(host)))  # newest-first
    if catalog_filter:
        f = catalog_filter.lower()
        cats = [c for c in cats if f in (c.get("title", "").lower()) or catalog_filter == _cid(c)]
    for c in cats:
        cid = _cid(c)
        if not cid:
            continue
        idx = requests.get(f"{catalog_base(host)}/courses/{cid}", timeout=_TIMEOUT)
        if idx.status_code >= 400:
            continue
        for entry in (idx.json() if idx.content else []):
            if (entry.get("__catalogCourseId") or "").replace(" ", "").upper() == want:
                return {
                    "catalog_id": cid,
                    "catalog_title": c.get("title"),
                    "pid": entry.get("pid"),
                    "id": entry.get("id"),
                    "title": entry.get("title"),
                }
    return None


def _clean(text: str) -> str:
    """Normalize catalog text: unescape entities, drop non-breaking spaces,
    collapse whitespace. Stops Canvas from storing a literal `&nbsp;` when the
    catalog value contains a U+00A0 (several BYUI CLOs do)."""
    t = html.unescape(text or "").replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip()


def _norm(text: str) -> str:
    """Compare-normalize a possibly-HTML description down to plain words."""
    t = html.unescape(text or "")
    t = re.sub(r"<[^>]+>", " ", t).replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip()


def fetch_detail(host: str, catalog_id: str, pid: str) -> dict:
    r = requests.get(f"{catalog_base(host)}/course/{catalog_id}/{pid}", timeout=_TIMEOUT)
    r.raise_for_status()
    d = r.json()
    outcomes = [
        _clean(o.get("value") or "")
        for o in (d.get("outcomes") or [])
        if (o.get("value") or "").strip()
    ]
    credits = d.get("credits") or {}
    return {
        "code": d.get("__catalogCourseId"),
        "title": d.get("title"),
        "credits": credits.get("value") if isinstance(credits, dict) else None,
        "outcomes": outcomes,
    }


# --------------------------------------------------------------------------
# Canvas Outcomes write side
# --------------------------------------------------------------------------
def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}", "Content-Type": "application/json"}


def _next_link(link_header: str) -> str | None:
    for part in (link_header or "").split(","):
        seg = part.split(";")
        if len(seg) >= 2 and 'rel="next"' in seg[1]:
            return seg[0].strip().strip("<>")
    return None


def existing_outcomes(course_id: str) -> dict:
    """title -> {id, description} for every outcome linked in the course."""
    out: dict = {}
    url = f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/outcome_group_links"
    params = {"outcome_style": "full", "per_page": 100}
    while url:
        r = requests.get(url, headers=_headers(), params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        for ln in (r.json() if r.content else []):
            o = ln.get("outcome") or {}
            t = (o.get("title") or o.get("display_name") or "").strip()
            if t:
                out[t] = {"id": o.get("id"), "description": o.get("description") or ""}
        url = _next_link(r.headers.get("Link", ""))
        params = None
    return out


def root_group_id(course_id: str) -> int:
    r = requests.get(
        f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/root_outcome_group",
        headers=_headers(), timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["id"]


def create_outcome(course_id: str, group_id: int, title: str, description: str) -> dict:
    url = f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/outcome_groups/{group_id}/outcomes"
    r = requests.post(
        url, headers=_headers(),
        json={"title": title, "display_name": title, "description": description},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def update_outcome(outcome_id, description: str) -> dict:
    r = requests.put(
        f"{CANVAS_BASE_URL}/api/v1/outcomes/{outcome_id}",
        headers=_headers(), json={"description": description}, timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def resolve_target(args) -> str | None:
    if args.course_id:
        return str(args.course_id)
    if args.target:
        val = (os.environ.get(args.target) or "").strip()
        if not val:
            print(f"⛔ --target {args.target} is not set in the environment/.env", file=sys.stderr)
            sys.exit(2)
        return val
    return None


def main() -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description="Import catalog CLOs into Canvas as Outcomes (API-only).")
    ap.add_argument("--course-code", required=True, help="Catalog course code, e.g. DS250 / ITM327 / MATH119")
    ap.add_argument("--institution", default=None,
                    help="Catalog institution shortname (default: CANVAS_INSTITUTION or the CANVAS_BASE_URL subdomain)")
    ap.add_argument("--catalog-host", default=None,
                    help="Override the Kuali host (default: <institution>.kuali.co)")
    ap.add_argument("--catalog", default=None,
                    help="Restrict to a catalog by title substring (e.g. 2026-2027) or id. Default: newest catalog that has the course.")
    ap.add_argument("--course-id", default=None, help="Target Canvas course id (write mode)")
    ap.add_argument("--target", default=None, help="Env var naming the target course id, e.g. CANVAS_SANDBOX_ID")
    ap.add_argument("--write", action="store_true", help="Actually create outcomes (default: preview only)")
    ap.add_argument("--allow-enrolled", action="store_true", help="Override the course guard for a course with students / blueprint")
    ap.add_argument("--json", action="store_true", help="Machine-readable output")
    ap.add_argument("--save-local", nargs="?", const="course", default=None, metavar="DIR",
                    help="Also write the CLOs to <DIR>/_outcomes.json (loader shape) so offline "
                         "audits (e.g. clo_quality --local) read them without the API. Default DIR: course")
    args = ap.parse_args()

    # Catalog reads don't need a Canvas token; a write does. Only enforce the
    # online-mode/token requirement when we're actually going to write.
    if args.write:
        try:
            check_mode_requirements()
        except ValueError as e:
            print(f"⛔ {e}", file=sys.stderr)
            return 2

    institution = (args.institution or default_institution() or "").lower()
    if not institution:
        print("⛔ Could not determine institution. Pass --institution (e.g. byui).", file=sys.stderr)
        return 2
    host = args.catalog_host or f"{institution}.kuali.co"

    # 1. Resolve + fetch
    try:
        found = resolve_course(host, args.course_code, args.catalog)
    except requests.RequestException as e:
        print(f"⛔ Catalog lookup failed against {host}: {e}", file=sys.stderr)
        return 2
    if not found:
        print(f"⛔ Course '{args.course_code}' not found in the {host} catalog"
              + (f" (filter: {args.catalog})" if args.catalog else "") + ".", file=sys.stderr)
        return 2
    detail = fetch_detail(host, found["catalog_id"], found["pid"])
    clos = detail["outcomes"]

    if not args.json:
        print(f"📖 {detail['code']} — {detail['title']}"
              f"  ({detail['credits']} cr)  ·  catalog: {found['catalog_title']}")
        print(f"   {len(clos)} course learning outcome(s):")
        for i, c in enumerate(clos, 1):
            print(f"   {i}. {c}")

    if not clos:
        print("⚠️  No outcomes in the catalog for this course — nothing to import.", file=sys.stderr)
        return 0

    # Optional: mirror the CLOs into a local course/_outcomes.json (loader shape),
    # so offline audits (clo_quality --local) read the same outcomes without the API.
    if args.save_local:
        os.makedirs(args.save_local, exist_ok=True)
        local_outcomes = [
            {"id": None, "title": f"{detail['code']} CLO {i}", "description": text,
             "display_name": f"{detail['code']} CLO {i}"}
            for i, text in enumerate(clos, 1)
        ]
        _p = os.path.join(args.save_local, "_outcomes.json")
        with open(_p, "w", encoding="utf-8") as _f:
            json.dump(local_outcomes, _f, indent=2)
        if not args.json:
            print(f"💾 wrote {len(local_outcomes)} outcomes to {_p}")

    # 2. Preview-only unless --write
    if not args.write:
        if args.json:
            print(json.dumps({"course": detail, "catalog": found, "wrote": False}, indent=2))
        else:
            print("\n(preview only — re-run with --write --target CANVAS_SANDBOX_ID to create these in Canvas)")
        return 0

    # 3. Write
    course_id = resolve_target(args)
    if not course_id:
        print("⛔ --write needs a target: pass --course-id <id> or --target <ENV_VAR>", file=sys.stderr)
        return 2

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="write", allow_override=args.allow_enrolled, label="CLO-import target")

    existing = existing_outcomes(course_id)
    gid = root_group_id(course_id)
    created, updated, skipped = [], [], []
    for i, text in enumerate(clos, 1):
        title = f"{detail['code']} CLO {i}"
        if title in existing:
            cur = existing[title]
            if _norm(cur["description"]) != _norm(text):
                update_outcome(cur["id"], text)
                updated.append(title)
            else:
                skipped.append(title)
            continue
        create_outcome(course_id, gid, title, text)
        created.append(title)

    if args.json:
        print(json.dumps({"course": detail, "target": course_id, "created": created,
                          "updated": updated, "skipped": skipped, "wrote": True}, indent=2))
    else:
        print(f"\n✅ Wrote to course {course_id}: {len(created)} created, "
              f"{len(updated)} updated, {len(skipped)} unchanged.")
        for t in created:
            print(f"   + {t}")
        for t in updated:
            print(f"   ~ {t} (updated)")
        for t in skipped:
            print(f"   = {t} (unchanged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

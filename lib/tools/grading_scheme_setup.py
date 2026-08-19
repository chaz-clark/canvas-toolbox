#!/usr/bin/env python3
"""
grading_scheme_setup.py — create a Canvas grading standard, verified by read-back.

WHY THIS EXISTS (#302)
  The toolkit could already READ a course's `grading_standard_id` (canvas_sync
  cmd_init) and PROPAGATE it master -> blueprint -> section (blueprint_sync,
  course_mirror). What it could not do is CREATE the standard those ids point at.
  So a course using a custom scale — competency tiers, specifications grading,
  anything that isn't A/B/C/D/F — had to be set up by hand in the Canvas UI before
  any of the propagation was usable.

  This closes that gap and nothing more. It creates ONE course-level grading
  standard and, on request, sets it as the course default. It deliberately does
  NOT batch-configure assignments: that is per-assignment policy, it changes how
  already-earned grades DISPLAY to enrolled students, and it belongs behind the
  same review the grading push surface gets rather than in a setup helper.

WHY THE WRITE IS READ BACK
  Same reason course dates are (#182): Canvas can answer 200 and not apply the
  change. `manage_grades` is restricted at some institutions, and a create that
  "succeeds" while leaving nothing behind is the worst outcome — the operator
  moves on and discovers it when grades render wrong. So the standard is fetched
  back and its entries compared before this reports success.

WHY THE SCALE IS VALIDATED BEFORE IT IS SENT
  Canvas accepts a scheme with a gap under the lowest tier and then has no letter
  for scores that fall in it. A refused command costs a retype; a silently
  incomplete scale costs a semester of wrong letters. So: descending, unique,
  within 0-100, and floored at 0.

Usage:
  # dry run (default) — validates and shows what would be created
  uv run python lib/tools/grading_scheme_setup.py \
      --title "Industry Performance Tiers" \
      --tiers "Leading:90,Strong:80,Solid:70,Building:60,Insufficient:0"

  # write it
  uv run python lib/tools/grading_scheme_setup.py --title ... --tiers ... --apply

  # write it and make it the course default
  uv run python lib/tools/grading_scheme_setup.py --title ... --tiers ... \
      --apply --set-course-default

Requires in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, and the env var named by
--target (default CANVAS_COURSE_ID).

Exit codes:
  0  created (or already present) and verified
  1  Canvas did not apply the write, or read-back disagreed
  2  configuration / validation error
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

import requests
from dotenv import load_dotenv

import canvas_course_guard as guard
from __toolbox_version__ import __version__

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
# The .env convention is scheme-less ("byui.instructure.com"); requests needs a
# scheme. Matches canvas_sync.py / rubric_quality_audit.py.
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url

_TIMEOUT = 30
# Canvas stores tier lower bounds as fractions and may echo them rounded, so
# read-back compares within a tolerance rather than by equality.
_VALUE_TOL = 1e-4


def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(endpoint: str) -> list | dict | None:
    try:
        resp = requests.get(f"{CANVAS_BASE_URL}/api/v1{endpoint}",
                            headers=_headers(), params={"per_page": 100},
                            timeout=_TIMEOUT)
    except Exception:
        return None
    if resp.status_code >= 400:
        return None
    try:
        return resp.json()
    except Exception:
        return None


def _post(endpoint: str, payload: dict) -> tuple[dict | None, str]:
    """Returns (json, error_text). Canvas error bodies name the real cause
    (permissions, duplicate title), so they are surfaced rather than swallowed."""
    try:
        resp = requests.post(f"{CANVAS_BASE_URL}/api/v1{endpoint}",
                             headers=_headers(), json=payload, timeout=_TIMEOUT)
    except Exception as e:
        return None, str(e)
    if resp.status_code >= 400:
        return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
    try:
        return resp.json(), ""
    except Exception:
        return None, "response was not JSON"


# ---------------------------------------------------------------------------
# Scale parsing + validation
# ---------------------------------------------------------------------------

def parse_tiers(spec: str) -> list[dict]:
    """Parse "Leading:90,Strong:80,...". PURE — raises ValueError, writes nothing.

    The value is the tier's LOWER BOUND in percent, which is how Canvas models a
    scheme: each entry claims everything from its bound up to the next one."""
    tiers: list[dict] = []
    for chunk in (spec or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError(f"expected NAME:PERCENT, got {chunk!r}")
        name, _, raw = chunk.rpartition(":")
        name = name.strip()
        if not name:
            raise ValueError(f"missing tier name in {chunk!r}")
        try:
            pct = float(raw)
        except ValueError:
            raise ValueError(f"{raw!r} in {chunk!r} is not a number") from None
        tiers.append({"name": name, "percent": pct})
    if not tiers:
        raise ValueError("no tiers given")
    return tiers


def validate_tiers(tiers: list[dict]) -> None:
    """Refuse a scale Canvas would accept but render wrong. Raises ValueError."""
    names = [t["name"] for t in tiers]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ValueError(f"duplicate tier name(s): {', '.join(sorted(dupes))}")

    for t in tiers:
        if not 0 <= t["percent"] <= 100:
            raise ValueError(f"{t['name']}: {t['percent']} is outside 0-100")

    pcts = [t["percent"] for t in tiers]
    if pcts != sorted(pcts, reverse=True) or len(set(pcts)) != len(pcts):
        raise ValueError(
            "tiers must be listed high to low with no repeated bound; got "
            + ", ".join(f"{t['name']}:{t['percent']:g}" for t in tiers))

    if pcts[-1] != 0:
        raise ValueError(
            f"the lowest tier must start at 0, but {tiers[-1]['name']} starts at "
            f"{pcts[-1]:g}. Canvas has no letter for scores below the lowest tier, "
            f"so 0-{pcts[-1]:g}% would render blank.")


def find_existing(course_id: str, title: str) -> dict | None:
    """A standard already carrying this title, if any. Account-level standards are
    visible here too and are reused rather than shadowed by a course-level copy of
    the same name — two same-named scales is a support ticket waiting to happen."""
    for s in _get(f"/courses/{course_id}/grading_standards") or []:
        if isinstance(s, dict) and (s.get("title") or "").strip() == title.strip():
            return s
    return None


def entries_match(standard: dict, tiers: list[dict]) -> bool:
    got = standard.get("grading_scheme_entry") or []
    if len(got) != len(tiers):
        return False
    for g, t in zip(got, tiers):
        if (g.get("name") or "").strip() != t["name"]:
            return False
        if abs(float(g.get("value", -1)) - t["percent"] / 100.0) > _VALUE_TOL:
            return False
    return True


def create_standard(course_id: str, title: str,
                    tiers: list[dict]) -> tuple[dict | None, str]:
    return _post(f"/courses/{course_id}/grading_standards", {
        "title": title,
        "grading_scheme_entry": [
            {"name": t["name"], "value": t["percent"] / 100.0} for t in tiers
        ],
    })


def set_course_default(course_id: str, standard_id: int) -> tuple[bool, str]:
    """Point the course at the standard, then READ IT BACK (#182's lesson)."""
    try:
        requests.put(f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}",
                     headers=_headers(),
                     json={"course": {"grading_standard_id": standard_id}},
                     timeout=_TIMEOUT)
    except Exception as e:
        return False, str(e)
    after = _get(f"/courses/{course_id}") or {}
    if isinstance(after, dict) and after.get("grading_standard_id") == standard_id:
        return True, ""
    return False, (
        f"Canvas reported success but the course still shows "
        f"grading_standard_id={after.get('grading_standard_id')!r}. This is normally "
        f"a permissions restriction on the token — set it in Canvas -> Settings -> "
        f"Course Details, or ask a Canvas admin.")


def main() -> int:
    force_utf8_console()  # #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description="Create a Canvas grading standard (custom grading scheme).")
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    ap.add_argument("--title", required=True, help="Scheme name as it appears in Canvas")
    ap.add_argument("--tiers", required=True,
                    metavar="NAME:PCT,...",
                    help='Lower bounds, high to low, ending at 0. '
                         'e.g. "Leading:90,Strong:80,Solid:70,Building:60,Insufficient:0"')
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Env var holding the course id (default CANVAS_COURSE_ID)")
    ap.add_argument("--course-id", default=None, help="Literal course id; overrides --target")
    ap.add_argument("--apply", action="store_true",
                    help="Write to Canvas. Without this the run is a dry run.")
    ap.add_argument("--set-course-default", action="store_true",
                    help="Also point the course's grading_standard_id at this scheme")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Proceed even if the course has enrolled students")
    args = ap.parse_args()

    if not CANVAS_API_TOKEN or not CANVAS_BASE_URL:
        print("ERROR: CANVAS_API_TOKEN and CANVAS_BASE_URL must be set.")
        return 2
    course_id = (args.course_id or os.environ.get(args.target, "")).strip()
    if not course_id:
        source = "--course-id" if args.course_id else f"${args.target}"
        print(f"ERROR: course ID not found via {source}.")
        print("       Set the env var, or pass --course-id <id> directly.")
        return 2

    try:
        tiers = parse_tiers(args.tiers)
        validate_tiers(tiers)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 2

    print(f"Grading scheme: {args.title}"
          f"   ({'APPLYING' if args.apply else 'DRY RUN — pass --apply to write'})")
    for i, t in enumerate(tiers):
        upper = 100.0 if i == 0 else tiers[i - 1]["percent"]
        print(f"  {t['name']:<20} {t['percent']:g}% – {upper:g}%")

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="write" if args.apply else "read",
                  allow_override=args.allow_enrolled, label="scheme target")

    existing = find_existing(course_id, args.title)
    if existing:
        where = (existing.get("context_type") or "Course").lower()
        same = entries_match(existing, tiers)
        print(f"\n  already exists at {where} level (id {existing.get('id')}) — "
              f"{'tiers match' if same else 'TIERS DIFFER from what you passed'}")
        if not same:
            print("  Canvas has no scheme-edit endpoint; rename this run's --title "
                  "or change the scheme in the Canvas UI.")
            return 1
        standard_id = existing.get("id")
    else:
        if not args.apply:
            print("\nRe-run with --apply to create it.")
            return 0
        created, err = create_standard(course_id, args.title, tiers)
        if not created:
            print(f"\nERROR creating scheme: {err}")
            return 1
        standard_id = created.get("id")
        # Read back — a 200 is not proof it landed (#182).
        back = find_existing(course_id, args.title)
        if not back or not entries_match(back, tiers):
            print("\nCanvas reported success but the scheme did not read back "
                  "intact. Nothing here retries automatically; check "
                  "Canvas -> Settings -> Grading Schemes before re-running.")
            return 1
        standard_id = back.get("id")
        print(f"\n  ✓ created and verified (id {standard_id})")

    if args.set_course_default:
        if not args.apply:
            print("  would set it as the course default")
        else:
            ok, err = set_course_default(course_id, standard_id)
            print("  ✓ course default set" if ok else f"\n  {err}")
            if not ok:
                return 1

    if args.apply:
        print(f"\nUse it on an assignment with grading_type=letter_grade and "
              f"grading_standard_id={standard_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

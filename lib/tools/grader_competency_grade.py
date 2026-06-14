#!/usr/bin/env python3
"""
Config-driven competency grade: highest tier where ALL thresholds are met.

Closes canvas-toolbox#60. Sibling courses (DS250 + ITM327 confirmed; likely
more) were independently building the same script — pull each student's
<=cutoff gradebook elements, count completions per element, assign the
highest tier whose thresholds are ALL met. The element id-lists and the
tier table are the only course-specific parts; the engine is identical.
This pulls that engine into the toolkit.

Lifted from ds250-onln-master/grading/mid_letter_s2/calc_mid_grades.py
(commit + author per the issue thread). The DS250 prototype is the
reference implementation; this generalizes its hardcoded element / tier
tables into a config file.

CONFIG SHAPE (JSON; YAML if pyyaml installed)
  {
    "cutoff": "2026-06-07",                 // optional, informational
    "elements": {
      "core":    {"ids": [16847157, ...], "basis": "nonzero"},
      "stretch": {"ids": [17078897, ...], "basis": "nonzero"},
      "ds":      {"ids": [16847081, ...], "basis": "full_credit"},
      "methods": {"ids": [16846803, ...], "basis": "full_credit"}
    },
    "required_submission_id": 16847221,     // optional — if set, an
                                            //  unsubmitted student gets a
                                            //  "MISSING" letter flag
    "tiers": [
      {"grade": "A", "score": 95, "thresholds": {"core": 7, "stretch": 1, "ds": 1, "methods": 3}},
      {"grade": "B", "score": 85, "thresholds": {"core": 5, "stretch": 1, "ds": 1, "methods": 2}},
      {"grade": "C", "score": 75, "thresholds": {"core": 3, "stretch": 1, "ds": 1, "methods": 1}}
    ],
    "below": [
      {"when": {"core": ">=3"}, "grade": "D", "score": 65},
      {"when": "else",          "grade": "F", "score": 50}
    ]
  }

Tiers iterate top → bottom. The highest tier whose `thresholds` are ALL
met (each element count >= the named threshold) wins. If no tier matches,
`below` rules apply in order; the first matching rule wins; `"else"` is
the catch-all.

The same per-element `basis` semantics as grader_reconcile (#59):
  "submitted"   submitted_at is set
  "nonzero"     submitted AND score > 0
  "full_credit" submitted AND score == points_possible

FERPA
  Output is keyed (via .keymap.json if --challenge-dir is given) or
  emits user_id (LMS row id — FERPA-safe per the toolkit's standing rule).
  Console: aggregate band counts only. No names anywhere.

USAGE
  uv run python lib/tools/grader_competency_grade.py
      --config grading/mid_letter/competency.json
      --challenge-dir grading/mid_letter

  # CSV
  uv run python lib/tools/grader_competency_grade.py
      --config <path> --challenge-dir <dir> --format csv

EXIT CODES
  0  graded; printed band assignments + summary
  2  setup / env / config / Canvas API error

NOT DONE IN v1
  half_step: false — the ds460 / DS250 mid uses CLEAN tiers (no +/-
  halfsteps); the issue mentions half_step as the end-of-letter mode.
  Implement when the FA26 end-of-term run needs it. Captured in the
  config schema as a known key; ignored if set.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from pathlib import Path

import requests

from _challenge_dir_guard import resolve_challenge_dir

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

# Reuse the canonical completion-basis predicate + points_possible fetch.
from grader_reconcile import (  # noqa: E402
    _is_complete_under_basis,
    _VALID_BASES,
    fetch_assignment_points_possible,
)

NUM = re.compile(r"\d+")
_TIMEOUT = 30


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


def _load_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
            return yaml.safe_load(text)
        except ImportError:
            print(f"Config at {path} is not valid JSON, and pyyaml is not installed. "
                  f"Either write the config as JSON or `uv add pyyaml`.", file=sys.stderr)
            raise


def fetch_submissions_for(base: str, cid: str, headers: dict, aid: int) -> dict[int, dict]:
    """user_id → {score, state, submitted, id}. Matches grader_reconcile.submissions
    shape so _is_complete_under_basis works without adaptation."""
    out: dict[int, dict] = {}
    page = 1
    while True:
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions",
            headers=headers, params={"per_page": 100, "page": page},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        for s in batch:
            out[int(s["user_id"])] = {
                "score": s.get("score"),
                "state": s.get("workflow_state"),
                "submitted": s.get("submitted_at") is not None,
                "id": s.get("id"),
            }
        page += 1
    return out


# ---------------------------------------------------------------------------
# Element counting
# ---------------------------------------------------------------------------

def count_elements(
    base: str, cid: str, headers: dict, elements: dict,
) -> tuple[dict[str, dict[int, int]], set[int]]:
    """Return:
        per_element: {element_name: {user_id: complete_count}}
        all_uids: union of every user_id seen across the elements

    Caches points_possible per assignment id (cheap; one GET each), but
    only fetches it when the element's basis is 'full_credit'."""
    per_element: dict[str, dict[int, int]] = {}
    all_uids: set[int] = set()

    for name, spec in elements.items():
        basis = spec.get("basis", "submitted")
        if basis not in _VALID_BASES:
            print(f"  warn: element '{name}' has unknown basis '{basis}'; falling back "
                  f"to 'submitted'.", file=sys.stderr)
            basis = "submitted"

        ids = spec.get("ids") or []
        pp_cache: dict[int, float | None] = {}
        if basis == "full_credit":
            for aid in ids:
                pp_cache[aid] = fetch_assignment_points_possible(base, cid, headers, aid)

        counts: dict[int, int] = {}
        for aid in ids:
            subs = fetch_submissions_for(base, cid, headers, aid)
            for uid, s in subs.items():
                counts.setdefault(uid, 0)
                all_uids.add(uid)
                if _is_complete_under_basis(s, pp_cache.get(aid), basis):
                    counts[uid] += 1
        per_element[name] = counts

    return per_element, all_uids


# ---------------------------------------------------------------------------
# Tier evaluation
# ---------------------------------------------------------------------------

_CMP_RE = re.compile(r"^(>=|<=|>|<|==|=)(-?\d+(?:\.\d+)?)$")


def _eval_cmp(value: int, expr: str) -> bool:
    """Apply a comparison string like '>=3' or '<7' to an integer count."""
    m = _CMP_RE.match(expr.replace(" ", ""))
    if not m:
        return False
    op, rhs_s = m.groups()
    rhs = float(rhs_s)
    if op in (">=",):
        return value >= rhs
    if op == ">":
        return value > rhs
    if op == "<=":
        return value <= rhs
    if op == "<":
        return value < rhs
    if op in ("==", "="):
        return value == rhs
    return False


def evaluate_tier_thresholds(counts: dict[str, int], thresholds: dict[str, int]) -> tuple[bool, list[str]]:
    """All thresholds met? Return (ok, missing_elements_list)."""
    missing: list[str] = []
    for elem, need in thresholds.items():
        have = counts.get(elem, 0)
        if have < need:
            missing.append(f"{elem} {have}<{need}")
    return (not missing), missing


def evaluate_below_rule(counts: dict[str, int], when: object) -> bool:
    if when == "else":
        return True
    if isinstance(when, dict):
        for elem, expr in when.items():
            if not _eval_cmp(counts.get(elem, 0), str(expr)):
                return False
        return True
    return False


def assign_band(
    counts: dict[str, int], tiers: list[dict], below: list[dict],
) -> tuple[str, float, str]:
    """Highest tier with ALL thresholds met wins. Below-tier rules iterate
    in order; first match wins; 'else' is the catch-all. Returns
    (grade, score, reason)."""
    for tier in tiers:
        ok, missing = evaluate_tier_thresholds(counts, tier.get("thresholds") or {})
        if ok:
            return (tier["grade"], float(tier["score"]),
                    f"meets {tier['grade']} fully")

    # Below the lowest tier — report what blocked it via the LOWEST tier's
    # thresholds (typical "did not meet C: core 2<3, 0 stretch, ...").
    bottom = tiers[-1] if tiers else {}
    _, missing = evaluate_tier_thresholds(counts, bottom.get("thresholds") or {})
    why_prefix = (f"did not meet {bottom.get('grade', 'tier')}: " + ", ".join(missing)
                  if missing else "below lowest tier")

    for rule in below or []:
        if evaluate_below_rule(counts, rule.get("when")):
            return (rule["grade"], float(rule["score"]), why_prefix)

    return ("F", 0.0, why_prefix or "no coursework")


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def render_table(rows: list[dict], elements: list[str], required_sub_label: bool) -> str:
    out: list[str] = []
    headers = ["key", "uid"]
    if required_sub_label:
        headers.append("letter")
    headers += elements + ["grade", "score", "reason"]
    out.append("  " + "  ".join(f"{h:>10}" for h in headers))
    for r in rows:
        cells = [str(r.get("key") or "-"), str(r["user_id"])]
        if required_sub_label:
            cells.append(r.get("letter") or "-")
        for e in elements:
            cells.append(str(r["counts"].get(e, 0)))
        cells += [r["grade"], str(r["score"]), r["reason"]]
        out.append("  " + "  ".join(f"{c:>10}" for c in cells))
    return "\n".join(out)


def render_csv(rows: list[dict], elements: list[str], required_sub_label: bool) -> str:
    buf = io.StringIO()
    fieldnames = ["key", "user_id"]
    if required_sub_label:
        fieldnames.append("letter")
    fieldnames += elements + ["grade", "score", "reason"]
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        flat = {"key": r.get("key"), "user_id": r["user_id"]}
        if required_sub_label:
            flat["letter"] = r.get("letter")
        for e in elements:
            flat[e] = r["counts"].get(e, 0)
        flat["grade"] = r["grade"]
        flat["score"] = r["score"]
        flat["reason"] = r["reason"]
        w.writerow(flat)
    return buf.getvalue()


def render_json(rows: list[dict], elements: list[str]) -> str:
    return json.dumps([
        {"key": r.get("key"), "user_id": r["user_id"],
         "letter": r.get("letter"),
         "counts": {e: r["counts"].get(e, 0) for e in elements},
         "grade": r["grade"], "score": r["score"], "reason": r["reason"]}
        for r in rows
    ], indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Config-driven competency grade (highest tier with ALL thresholds met).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--config", required=True,
                    help="Path to competency config (JSON; YAML if pyyaml installed).")
    ap.add_argument("--challenge-dir", default=None,
                    help="Optional. Reads .keymap.json to label rows with opaque keys "
                         "(via numeric-id matching against the submissions list, same as "
                         "grader_reconcile). Without this, rows are labeled by user_id.")
    ap.add_argument("--course-id", default=None,
                    help="Override CANVAS_COURSE_ID env var.")
    ap.add_argument("--out", default=None,
                    help="Output file path. Default: stdout only.")
    ap.add_argument("--format", choices=("text", "csv", "json"), default="text",
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
            guard.enforce(base, headers, cid, mode="read", label="competency-grade target")
        except SystemExit:
            raise
        except Exception as e:
            print(f"WARN: canvas_course_guard failed ({type(e).__name__}: {e}) — continuing read-only.",
                  file=sys.stderr)

    cfg = _load_config(Path(args.config))
    elements_cfg = cfg.get("elements") or {}
    tiers = cfg.get("tiers") or []
    below = cfg.get("below") or []
    required_sub = cfg.get("required_submission_id")
    if not elements_cfg or not tiers:
        print("Config must define 'elements' AND 'tiers'.", file=sys.stderr)
        return 2

    element_names = list(elements_cfg.keys())

    try:
        per_element, all_uids = count_elements(base, cid, headers, elements_cfg)
    except requests.HTTPError as e:
        print(f"Canvas API error: {e}", file=sys.stderr)
        return 2

    # Required-submission letter flag
    letter_uids: set[int] = set()
    if required_sub is not None:
        try:
            req_subs = fetch_submissions_for(base, cid, headers, int(required_sub))
            letter_uids = {uid for uid, s in req_subs.items() if s.get("submitted")}
        except (requests.HTTPError, ValueError):
            print(f"WARN: couldn't fetch required_submission_id={required_sub}; "
                  f"letter flag disabled.", file=sys.stderr)

    # uid → key (if challenge_dir is set)
    uid_to_key: dict[int, str] = {}
    if args.challenge_dir:
        cd = resolve_challenge_dir(args.challenge_dir, verb="competency-grading in")
        keymap_file = cd / ".keymap.json"
        if keymap_file.exists():
            km = json.loads(keymap_file.read_text(encoding="utf-8")).get("map", {})
            # Match key → uid via numeric tokens in the filename (same as
            # grader_reconcile's resolve_user_id strategy; here we just match
            # whichever uid appears in the keymap value string for each uid in
            # all_uids).
            for uid in all_uids:
                for key, fname in km.items():
                    if str(uid) in NUM.findall(fname):
                        uid_to_key[uid] = key
                        break

    rows: list[dict] = []
    for uid in sorted(all_uids):
        counts = {e: per_element.get(e, {}).get(uid, 0) for e in element_names}
        grade, score, reason = assign_band(counts, tiers, below)
        rows.append({
            "user_id": uid,
            "key": uid_to_key.get(uid),
            "letter": ("sub" if uid in letter_uids else "MISSING") if required_sub is not None else None,
            "counts": counts,
            "grade": grade,
            "score": score,
            "reason": reason,
        })

    # Sort by score DESC, then key (so the top of the table is the high band).
    rows.sort(key=lambda r: (-r["score"], r.get("key") or str(r["user_id"])))

    if args.format == "csv":
        body = render_csv(rows, element_names, required_sub is not None)
    elif args.format == "json":
        body = render_json(rows, element_names)
    else:
        body = render_table(rows, element_names, required_sub is not None)

    print(body)

    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
        print(f"\n  -> wrote {args.out}", file=sys.stderr)

    band_counts: dict[str, int] = {}
    for r in rows:
        band_counts[r["grade"]] = band_counts.get(r["grade"], 0) + 1
    print(f"\nGraded {len(rows)} students. Band distribution: "
          f"{dict(sorted(band_counts.items()))}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

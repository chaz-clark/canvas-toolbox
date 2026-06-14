#!/usr/bin/env python3
"""
Resolve a reconcile/competency config's `assignment_ids` against the live
course and print a table the operator eyeballs BEFORE any grading run.

Closes canvas-toolbox#58. Background: the worst observed failure mode of the
grader pipeline is a SILENT misconfiguration — an `assignment_id` in the
reconcile config that points at the wrong assignment. The pipeline still
runs; it just grades everyone wrong. One real-world DS250 instance pointed
`ds_community` at a W14 end-quiz + a checkpoint and quietly capped students
at "DS=0" who had full DS credit.

WHAT IT DOES
  - Read-only. No grading. No writes. No FERPA-relevant data — assignment
    metadata only (name, group, points, due_at). Safe by construction.
  - For each dimension, resolves each `assignment_ids[]` entry to
    {name, assignment_group, points_possible, due_at} via one Canvas call
    (assignment_groups?include[]=assignments) + per-id fallbacks if needed.
  - Flags likely-wrong configurations using these checks:

      id_not_in_course      (FAIL) id absent from the course's assignments
      group_mismatch        (FAIL) dim has `expected_group_regex` and the
                                   assignment's group name doesn't match
      due_out_of_range      (FAIL) dim has `due_before` / `due_after` and the
                                   assignment's due_at falls outside
      group_mismatch_hint   (WARN) no explicit rule + no 3+ char token of the
                                   dimension name appears in the group name
      due_unset             (WARN) assignment has no `due_at` set in Canvas

CONFIG SHAPE (extends what grader_reconcile.py + #60 already use)
  Either of these is recognized; both can co-exist:

    {"reconciliation": {"dimensions": [
        {"dimension": "ds_community",
         "source": "gradebook",
         "assignment_ids": [40050, 40051, 40052],
         "expected_group_regex": "DS Community",  // optional
         "due_before": "2026-03-15",              // optional ISO date
         "due_after":  "2026-02-01"}              // optional ISO date
    ]}}

    {"competency": {"elements": {
        "core":   {"ids": [...], "basis": "nonzero",
                   "expected_group_regex": "Tasks"},
        "stretch":{"ids": [...]}
    }}}

  `expected_group_regex`, `due_before`, `due_after` are NEW optional keys.
  Existing reconcile configs without them still resolve + print fine — they
  just won't surface explicit FAIL flags (heuristic WARNs still apply).

USAGE
  uv run python lib/tools/grader_config_audit.py --config grading/mid/config.json
  uv run python lib/tools/grader_config_audit.py --config <path> --format json

  # Limit to one dimension
  uv run python lib/tools/grader_config_audit.py --config <path> \\
      --dimension ds_community

EXIT CODES
  0  all resolved + no FAIL flags
  1  at least one FAIL flag (id_not_in_course / group_mismatch / due_out_of_range)
  2  setup failure (config not found, env missing, course unreachable)

KNOWN SCOPE LIMITATION
  Cross-section sibling-count comparison (e.g. "section A's ds_community has
  3 ids, section B has 7 — which is right?") is not in v1. The audit takes
  one config + one course. A future enhancement could diff two configs.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

try:
    import canvas_course_guard as guard
except ImportError:
    guard = None

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    pass

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


def _get_one(base: str, headers: dict, path: str) -> dict | None:
    r = requests.get(f"{base}/api/v1{path}", headers=headers, timeout=_TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Config loader (accepts both reconciliation and competency shapes)
# ---------------------------------------------------------------------------

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


def _extract_dimensions(cfg: dict) -> list[dict]:
    """Normalize either config shape into a list of:
        {name, source, ids, expected_group_regex?, due_before?, due_after?}
    """
    out: list[dict] = []

    for d in (cfg.get("reconciliation") or {}).get("dimensions") or []:
        out.append({
            "name": d.get("dimension"),
            "source": d.get("source", "gradebook"),
            "ids": list(d.get("assignment_ids") or []),
            "expected_group_regex": d.get("expected_group_regex"),
            "due_before": d.get("due_before"),
            "due_after": d.get("due_after"),
            "origin": "reconciliation.dimensions",
        })

    elements = (cfg.get("competency") or {}).get("elements") or {}
    for name, e in elements.items():
        out.append({
            "name": name,
            "source": "gradebook",
            "ids": list(e.get("ids") or []),
            "expected_group_regex": e.get("expected_group_regex"),
            "due_before": e.get("due_before"),
            "due_after": e.get("due_after"),
            "origin": "competency.elements",
        })

    return out


# ---------------------------------------------------------------------------
# Flag detection
# ---------------------------------------------------------------------------

_STOPWORDS = {"and", "the", "of", "to", "in", "for", "a", "an"}


def _name_tokens(name: str) -> set[str]:
    parts = re.split(r"[_\s\-]+", name.lower())
    return {p for p in parts if len(p) >= 3 and p not in _STOPWORDS}


def _parse_due(due_at: str | None) -> datetime | None:
    if not due_at:
        return None
    try:
        return datetime.fromisoformat(due_at.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_iso_date(s: str | None) -> datetime | None:
    """Parse an operator-supplied date or datetime string. Bare dates
    ('2026-03-15') become UTC midnight so they compare against Canvas's
    timezone-aware due_at without TypeError."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def _evaluate(dim: dict, assn: dict | None) -> tuple[list[str], list[str]]:
    """Return (fails, warns) for one (dimension, assignment) pair."""
    fails: list[str] = []
    warns: list[str] = []

    if assn is None:
        fails.append("id_not_in_course")
        return fails, warns

    group_name = assn.get("assignment_group_name") or ""
    due = _parse_due(assn.get("due_at"))

    expected = dim.get("expected_group_regex")
    if expected:
        try:
            if not re.search(expected, group_name, re.IGNORECASE):
                fails.append(f"group_mismatch (group='{group_name}' !~ /{expected}/)")
        except re.error as e:
            warns.append(f"expected_group_regex_invalid ({e})")
    else:
        toks = _name_tokens(dim["name"] or "")
        if toks:
            group_lc = group_name.lower()
            if not any(t in group_lc for t in toks):
                warns.append(
                    f"group_mismatch_hint (no token from '{dim['name']}' in group '{group_name}')"
                )

    db = _parse_iso_date(dim.get("due_before"))
    da = _parse_iso_date(dim.get("due_after"))
    if (db or da) and due is None:
        warns.append("due_unset_but_dim_states_cutoff")
    if db and due and due > db:
        fails.append(f"due_out_of_range (due_at={due.date()} > due_before={db.date()})")
    if da and due and due < da:
        fails.append(f"due_out_of_range (due_at={due.date()} < due_after={da.date()})")

    if due is None and not (db or da):
        warns.append("due_unset")

    return fails, warns


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def _build_assignment_index(base: str, headers: dict, cid: str) -> dict[int, dict]:
    """{aid: {id, name, points_possible, due_at, assignment_group_id, assignment_group_name}}"""
    groups = _get_paged(base, headers, f"/courses/{cid}/assignment_groups",
                        params={"include[]": "assignments"})
    idx: dict[int, dict] = {}
    for g in groups:
        gname = g.get("name") or ""
        for a in g.get("assignments") or []:
            aid = a.get("id")
            if aid is None:
                continue
            idx[int(aid)] = {
                "id": int(aid),
                "name": a.get("name") or "",
                "points_possible": a.get("points_possible"),
                "due_at": a.get("due_at"),
                "assignment_group_id": g.get("id"),
                "assignment_group_name": gname,
            }
    return idx


def _audit_id(base: str, headers: dict, cid: str, aid: int,
              idx: dict[int, dict]) -> dict | None:
    """Look up an id in the cached index; fall back to a direct GET (catches
    assignments hidden from group listing in odd cases)."""
    hit = idx.get(int(aid))
    if hit:
        return hit
    direct = _get_one(base, headers, f"/courses/{cid}/assignments/{aid}")
    if not direct:
        return None
    return {
        "id": int(direct.get("id") or aid),
        "name": direct.get("name") or "",
        "points_possible": direct.get("points_possible"),
        "due_at": direct.get("due_at"),
        "assignment_group_id": direct.get("assignment_group_id"),
        "assignment_group_name": "(direct lookup — group name not joined)",
    }


def audit(base: str, headers: dict, cid: str, dims: list[dict]) -> dict:
    idx = _build_assignment_index(base, headers, cid)
    results: list[dict] = []
    for dim in dims:
        if not dim["name"]:
            continue
        rows: list[dict] = []
        for aid in dim["ids"]:
            assn = _audit_id(base, headers, cid, aid, idx)
            fails, warns = _evaluate(dim, assn)
            rows.append({
                "assignment_id": int(aid),
                "name": (assn or {}).get("name") or "<NOT IN COURSE>",
                "group": (assn or {}).get("assignment_group_name") or "",
                "points_possible": (assn or {}).get("points_possible"),
                "due_at": (assn or {}).get("due_at"),
                "fails": fails,
                "warns": warns,
            })
        results.append({
            "dimension": dim["name"],
            "source": dim["source"],
            "origin": dim["origin"],
            "expected_group_regex": dim.get("expected_group_regex"),
            "due_before": dim.get("due_before"),
            "due_after": dim.get("due_after"),
            "rows": rows,
        })
    return {"dimensions": results}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _fmt_pts(v) -> str:
    if v is None:
        return "—"
    return f"{float(v):g}"


def _fmt_due(s: str | None) -> str:
    d = _parse_due(s)
    return d.date().isoformat() if d else "—"


def render_text(result: dict, config_path: str, course_id: str) -> str:
    lines: list[str] = []
    lines.append(f"== grader_config_audit  config={config_path}  course={course_id} ==")
    lines.append("")

    total_fail = total_warn = total_ids = total_ok = 0

    for dim in result["dimensions"]:
        rule_bits = []
        if dim.get("expected_group_regex"):
            rule_bits.append(f"group~/{dim['expected_group_regex']}/")
        if dim.get("due_before"):
            rule_bits.append(f"due_before={dim['due_before']}")
        if dim.get("due_after"):
            rule_bits.append(f"due_after={dim['due_after']}")
        rule_str = "  " + ", ".join(rule_bits) if rule_bits else ""

        lines.append(f"[{dim['dimension']}]  source={dim['source']}, "
                     f"ids={len(dim['rows'])}{rule_str}")

        for row in dim["rows"]:
            total_ids += 1
            status = "ok"
            if row["fails"]:
                status = "FAIL"
                total_fail += 1
            elif row["warns"]:
                status = "warn"
                total_warn += 1
            else:
                total_ok += 1

            lines.append(
                f"   {row['assignment_id']:<10} "
                f"{(row['name'] or '')[:60]:<60} "
                f"pts={_fmt_pts(row['points_possible']):<6} "
                f"due={_fmt_due(row['due_at']):<12} "
                f"group={(row['group'] or '—')[:24]:<24} "
                f"{status}"
            )
            for f in row["fails"]:
                lines.append(f"        !! {f}")
            for w in row["warns"]:
                lines.append(f"        ?? {w}")
        lines.append("")

    lines.append(f"Summary: {total_ok} ok, {total_warn} warn, {total_fail} FAIL "
                 f"({total_ids} ids across {len(result['dimensions'])} dimensions)")
    if total_fail:
        lines.append("Exit code 1 — at least one FAIL. Fix before grading.")
    elif total_warn:
        lines.append("Exit code 0 — warnings are heuristic; verify but not blocking.")
    else:
        lines.append("Exit code 0 — clean.")
    return "\n".join(lines)


def render_json(result: dict, config_path: str, course_id: str) -> str:
    fails = sum(1 for d in result["dimensions"] for r in d["rows"] if r["fails"])
    warns = sum(1 for d in result["dimensions"] for r in d["rows"] if r["warns"] and not r["fails"])
    total = sum(len(d["rows"]) for d in result["dimensions"])
    payload = {
        "tool": "grader_config_audit",
        "version": __version__,
        "config": str(config_path),
        "course_id": str(course_id),
        "summary": {"total_ids": total, "fails": fails, "warns": warns,
                    "dimensions": len(result["dimensions"])},
        "dimensions": result["dimensions"],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Audit a reconcile/competency config's assignment_ids against the live "
                    "course (read-only). Catches silent misconfig BEFORE any grading run.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--config", required=True,
                    help="Path to reconcile/competency config (JSON; YAML if pyyaml installed).")
    ap.add_argument("--course-id", default=None,
                    help="Override CANVAS_COURSE_ID env var.")
    ap.add_argument("--dimension", default=None,
                    help="Limit audit to this dimension/element name.")
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
            guard.enforce(base, headers, cid, mode="read", label="audit target")
        except SystemExit:
            raise
        except Exception as e:
            print(f"WARN: canvas_course_guard failed ({type(e).__name__}: {e}) — continuing read-only.",
                  file=sys.stderr)

    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 2

    cfg = _load_config(config_path)
    dims = _extract_dimensions(cfg)
    if not dims:
        print(f"Config at {config_path} has no reconciliation.dimensions[] or "
              f"competency.elements{{}}. Nothing to audit.", file=sys.stderr)
        return 2

    if args.dimension:
        dims = [d for d in dims if d["name"] == args.dimension]
        if not dims:
            print(f"Dimension '{args.dimension}' not found in config.", file=sys.stderr)
            return 2

    try:
        result = audit(base, headers, cid, dims)
    except requests.HTTPError as e:
        print(f"Canvas API error: {e}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(render_json(result, str(config_path), cid))
    else:
        print(render_text(result, str(config_path), cid))

    any_fail = any(r["fails"] for d in result["dimensions"] for r in d["rows"])
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())

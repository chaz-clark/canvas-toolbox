#!/usr/bin/env python3
"""
Scaffold the canonical grading/<task>[_combined]/<surface>/ layout for one
or more Canvas assignments — eliminates the per-task mkdir + cp + edit
cycle.

Sub-item A of canvas-toolbox#54 umbrella. m119 SP26 calibration `mkdir`'d
+ `cp RUBRIC.md` four times for new task cohorts. This automates that:
takes one (or several) Canvas assignment IDs, looks up the names, infers
surface (AI Log / Cohesive Narrative / generic), lays down the directory
structure with a starter `config.yml` + a `RUBRIC.md` linked to the
appropriate template.

LAYOUT
  - One assignment OR --combine omitted on single → single-surface dir:
        <out-root>/<task>_<surface>/
            submissions_raw/   .gitignore + empty
            submissions_deid/  empty
            feedback/_pass1/   empty (grader writes uid-<N>.md here)
            config.yml         starter (sub-A skeleton; operator extends)
            RUBRIC.md          copied / linked from template

  - Multiple assignments OR --combine on single → combined task dir
    with sibling surface subdirs:
        <out-root>/<task>_combined/
            ai_log/<canonical subtree>
            cohesive_narrative/<canonical subtree>

SURFACE INFERENCE (case-insensitive, looks at the assignment name)
  contains "AI Log"            → ai_log
  contains "Cohesive Narrative"
   or "Cohesive"               → cohesive_narrative
  contains "Mid Letter" / "Mid Letter"
   or "Self-Review"            → self_review
  anything else                → generic   (no surface subdir)

TASK-PREFIX INFERENCE
  "Project 1 Task 1 AI Log"               → p1t1
  "Project 1 Task 2 - Cohesive Narrative" → p1t2
  Otherwise → lowercased+slugified first ≤16 chars of the assignment
  name minus the surface keywords.

  Override with --task-dir-name to force the slug.

FILES WRITTEN
  config.yml  starter shape (matches grader_setup_knowledge.md §1-§6
              schema). Operator extends with rubric/voice details.
  RUBRIC.md   copied from scaffold/grading/rubric_templates/<surface>.md
              if present; else a placeholder pointing to that template
              path.
  feedback/   submissions_raw/ + submissions_deid/ + feedback/_pass1/
              empty dirs ready for the pipeline.

IDEMPOTENT
  Re-running on an existing task dir is a no-op unless --force is passed.
  Files that already exist are NOT overwritten; the tool prints a status
  line per file (created / exists).

USAGE
  # Single-surface task
  uv run python lib/tools/grader_scaffold.py
      --assignment-ids 16958397 --out-root grading/

  # Multi-surface combined task (AI Log + Cohesive Narrative)
  uv run python lib/tools/grader_scaffold.py
      --assignment-ids 16958397,16958399 --combine --out-root grading/

  # Override the task-prefix slug
  uv run python lib/tools/grader_scaffold.py
      --assignment-ids 16958397 --task-dir-name p1t1 --out-root grading/

EXIT CODES
  0  scaffolded (created + existing files counted)
  2  setup / Canvas API error / no assignment IDs resolved
"""
from __future__ import annotations

import argparse
import os
import re
import sys
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

_SURFACE_PATTERNS = [
    (re.compile(r"\bai\s*log\b", re.IGNORECASE), "ai_log"),
    (re.compile(r"\bcohesive(?:\s+narrative)?\b", re.IGNORECASE), "cohesive_narrative"),
    (re.compile(r"\bself[-_\s]review\b|\bmid\s+(?:letter|review)\b", re.IGNORECASE), "self_review"),
]

_TASK_PT_RE = re.compile(r"project\s*(\d+)[\s\-:]*task\s*(\d+)", re.IGNORECASE)
_TASK_KC_RE = re.compile(r"\bkc\s*(\d+)\b", re.IGNORECASE)
_SLUG_NONALNUM = re.compile(r"[^a-z0-9]+")


def _env_canvas(course_id_override: str | None) -> tuple[str, str, str]:
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    cid = course_id_override or os.environ.get("CANVAS_COURSE_ID", "")
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return tok, cid, base


def infer_surface(name: str) -> str:
    for pat, surf in _SURFACE_PATTERNS:
        if pat.search(name or ""):
            return surf
    return "generic"


def infer_task_slug(name: str) -> str:
    """Extract a short task slug. Handles 'Project X Task Y' (→ pXtY) +
    'KC<n>' (→ kc<n>) explicitly; otherwise slugifies the assignment name
    with surface keywords stripped, capped at 16 chars."""
    m = _TASK_PT_RE.search(name or "")
    if m:
        return f"p{m.group(1)}t{m.group(2)}".lower()
    m = _TASK_KC_RE.search(name or "")
    if m:
        return f"kc{m.group(1)}".lower()
    cleaned = (name or "").lower()
    for pat, _ in _SURFACE_PATTERNS:
        cleaned = pat.sub("", cleaned)
    cleaned = _SLUG_NONALNUM.sub("_", cleaned).strip("_")
    return cleaned[:16] or "task"


def fetch_assignment(base: str, cid: str, headers: dict, aid: int) -> dict:
    r = requests.get(f"{base}/api/v1/courses/{cid}/assignments/{aid}",
                     headers=headers, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json() or {}


# ---------------------------------------------------------------------------
# Layout + file writers
# ---------------------------------------------------------------------------

_STARTER_CONFIG_YML = """# Starter config — scaffolded by grader_scaffold.py.
# Extend per grader_setup_knowledge.md (the 6-step setup interview).
assignment_id: {assignment_id}
prefix: {prefix}
outputs:
  - name: main
    grader_count: 3
    rubric: RUBRIC.md
# reconciliation:
#   enabled: false
#   dimensions: []
"""

_PLACEHOLDER_RUBRIC = """# RUBRIC — {assignment_name}

This is a placeholder. Drop the canonical rubric template into
`scaffold/grading/rubric_templates/{surface}.md` (issue #54 sub-F shipped
the cohesive narrative template) so grader_scaffold.py can copy it here
automatically next time.

For now, document your bands (names + anchors), grader-count, and
expected evidence per band before running the pipeline.
"""


def _write_if_missing(path: Path, content: str, *, force: bool) -> str:
    """Write `content` to `path` if it doesn't exist (or --force). Return
    a one-letter status: '+' new, '=' exists+kept, '!' overwritten."""
    if path.exists() and not force:
        return "="
    overwrote = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "!" if overwrote else "+"


def scaffold_surface_dir(
    base_dir: Path,
    *,
    assignment_id: int,
    assignment_name: str,
    surface: str,
    prefix: str,
    repo_root: Path,
    force: bool,
) -> list[tuple[str, Path]]:
    """Create the canonical sub-tree at `base_dir`. Returns a list of
    (status, path) tuples for the report."""
    actions: list[tuple[str, Path]] = []

    for sub in ("submissions_raw", "submissions_deid", "feedback/_pass1"):
        d = base_dir / sub
        if d.is_dir():
            actions.append(("=", d))
        else:
            d.mkdir(parents=True, exist_ok=True)
            actions.append(("+", d))

    cfg_path = base_dir / "config.yml"
    cfg_status = _write_if_missing(
        cfg_path,
        _STARTER_CONFIG_YML.format(assignment_id=assignment_id, prefix=prefix),
        force=force,
    )
    actions.append((cfg_status, cfg_path))

    template_dir = repo_root / "scaffold" / "grading" / "rubric_templates"
    template = template_dir / f"{surface}.md"
    rubric_path = base_dir / "RUBRIC.md"
    if template.exists():
        rubric_status = _write_if_missing(rubric_path, template.read_text(encoding="utf-8"),
                                          force=force)
    else:
        rubric_status = _write_if_missing(
            rubric_path,
            _PLACEHOLDER_RUBRIC.format(assignment_name=assignment_name, surface=surface),
            force=force,
        )
    actions.append((rubric_status, rubric_path))

    return actions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Scaffold the canonical grading/<task>[_combined]/<surface>/ layout "
                    "for one or more Canvas assignments (#54 sub-A).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--assignment-ids", required=True,
                    help="One or more Canvas assignment IDs, comma-separated.")
    ap.add_argument("--course-id", default=None,
                    help="Override CANVAS_COURSE_ID env var.")
    ap.add_argument("--out-root", default="grading",
                    help="Output root for the scaffolded layout. Default: grading/")
    ap.add_argument("--task-dir-name", default=None,
                    help="Override the inferred task-prefix slug (e.g. force 'p1t1').")
    ap.add_argument("--combine", action="store_true",
                    help="Force the <task>_combined/<surface>/ layout even for a single "
                         "assignment (default: multi-assignment auto-combines; single doesn't).")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing config.yml / RUBRIC.md instead of preserving.")
    args = ap.parse_args()

    tok, cid, base = _env_canvas(args.course_id)
    for var, val in (("CANVAS_API_TOKEN", tok), ("CANVAS_BASE_URL", base), ("CANVAS_COURSE_ID", cid)):
        if not val:
            print(f"Missing {var} (env or --course-id).", file=sys.stderr)
            return 2
    headers = {"Authorization": f"Bearer {tok}"}

    try:
        aids = [int(x.strip()) for x in args.assignment_ids.split(",") if x.strip()]
    except ValueError:
        print("--assignment-ids must be a comma-separated list of integers.", file=sys.stderr)
        return 2
    if not aids:
        print("--assignment-ids was empty.", file=sys.stderr)
        return 2

    assignments: list[dict] = []
    for aid in aids:
        try:
            a = fetch_assignment(base, cid, headers, aid)
        except requests.HTTPError as e:
            print(f"Canvas API error for assignment {aid}: {e}", file=sys.stderr)
            return 2
        assignments.append({
            "id": aid,
            "name": a.get("name") or f"assignment-{aid}",
            "surface": infer_surface(a.get("name") or ""),
        })

    # Decide on combined-vs-single layout
    combine = args.combine or len(assignments) > 1

    # Task slug: explicit override OR common prefix across assignments OR
    # fall back to the first assignment's slug.
    if args.task_dir_name:
        task_slug = args.task_dir_name
    else:
        slugs = [infer_task_slug(a["name"]) for a in assignments]
        if len(set(slugs)) == 1:
            task_slug = slugs[0]
        else:
            print(f"WARN: assignments don't share a task slug ({slugs}). Using "
                  f"first ({slugs[0]}). Override with --task-dir-name.", file=sys.stderr)
            task_slug = slugs[0]

    out_root = Path(args.out_root)
    repo_root = Path(__file__).resolve().parents[2]  # canvas-toolbox root

    report: list[tuple[str, Path]] = []
    if combine:
        base_dir = out_root / f"{task_slug}_combined"
        print(f"\nScaffolding COMBINED layout at {base_dir}/")
        for a in assignments:
            print(f"  surface={a['surface']}  assignment={a['id']}  ({a['name']})")
            report += scaffold_surface_dir(
                base_dir / a["surface"],
                assignment_id=a["id"],
                assignment_name=a["name"],
                surface=a["surface"],
                prefix=f"{task_slug}-{a['surface']}".upper().replace("_", "-"),
                repo_root=repo_root,
                force=args.force,
            )
    else:
        a = assignments[0]
        surface = a["surface"]
        slug = f"{task_slug}_{surface}" if surface != "generic" else task_slug
        base_dir = out_root / slug
        print(f"\nScaffolding SINGLE layout at {base_dir}/  "
              f"(surface={surface}, assignment={a['id']})")
        report += scaffold_surface_dir(
            base_dir,
            assignment_id=a["id"],
            assignment_name=a["name"],
            surface=surface,
            prefix=slug.upper().replace("_", "-"),
            repo_root=repo_root,
            force=args.force,
        )

    print("\nFile-level actions ('+' created, '=' kept existing, '!' overwritten via --force):")
    for status, p in report:
        print(f"  [{status}] {p}")
    created = sum(1 for s, _ in report if s == "+")
    kept = sum(1 for s, _ in report if s == "=")
    overwrote = sum(1 for s, _ in report if s == "!")
    print(f"\n{created} created, {kept} kept, {overwrote} overwritten.")
    print(f"\nNext steps:")
    print(f"  1. Edit {base_dir}/config.yml (per grader_setup_knowledge.md §1-§6)")
    print(f"  2. Replace the placeholder RUBRIC.md (or update the template at "
          f"scaffold/grading/rubric_templates/<surface>.md)")
    print(f"  3. Run:  uv run python lib/tools/grader_fetch.py "
          f"--challenge-dir {base_dir} --assignment-id <id>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

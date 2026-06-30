#!/usr/bin/env python3
"""
Mirror New Quizzes as UNPUBLISHED Classic quizzes so per-student responses are pullable.

Part of the canvas-toolbox generic grader skill (v0.1). See:
  - lib/agents/canvas_grader.md (operator-facing pipeline guide)
  - lib/agents/knowledge/grader_setup_knowledge.md §J (verifiable self-report quiz pattern)
  - lib/agents/knowledge/grader_knowledge.md verifiable_quiz_classic_mirror

WHY THIS EXISTS
  New Quizzes do NOT expose per-student item responses via the Canvas API
  (only metadata; /api/quiz/v1/.../{submissions,results,reports} return 404).
  Classic Quizzes DO via submission_data on /assignments/:aid/submissions
  ?include[]=submission_history. To make weekly self-reports (hours, missed
  meetings, involvement signals) reconcilable for performance reviews:

    1. Mirror each New Quiz as an UNPUBLISHED Classic Quiz (same title /
       description / due / assignment-group / module).
    2. Use NUMERIC questions with a WIDE RANGE (any answer = correct = full
       points → auto-grades on submit; no manual review).
    3. No essay questions (essays force manual grading).
    4. Missed-work justifications come in as Canvas submission COMMENTS
       instead.

REAL BUG TO AVOID
  Quizzes ARE assignments. A naive name-only filter mirrors your own Classic
  output → duplicates. This tool filters source on
  `submission_types == external_tool` (the New-Quizzes marker) only.

USAGE
  # Dry-run all matching New Quizzes
  uv run python lib/tools/grader_quiz_mirror.py --spec mirror_spec.json

  # Create one (e.g. week 7)
  uv run python lib/tools/grader_quiz_mirror.py --spec mirror_spec.json \\
    --filter-extra "Week 7" --create --allow-enrolled

  # Rebuild (delete + recreate) all mirrors
  uv run python lib/tools/grader_quiz_mirror.py --spec mirror_spec.json \\
    --rebuild --allow-enrolled

SPEC FILE (JSON; YAML supported if pyyaml is installed)
  {
    "source_pattern": "stand.?up",     // regex; case-insensitive
    "module_id": 4620497,              // module to add the mirror to (optional)
    "description": "<p>...</p>",       // HTML body for the Classic quiz
    "questions": [
      {"name": "Standups missed", "type": "numerical_question", "points": 1,
       "text": "<p>How many stand-up meetings did you miss this week?</p>",
       "any_answer": true},
      {"name": "Hours", "type": "numerical_question", "points": 1,
       "text": "<p>How many hours did you spend on the course this week?</p>",
       "any_answer": true}
    ]
  }

  `any_answer: true` produces a wide-range numeric question (auto-grades to full).

GENERALIZED FROM: ds460-master/mirror_standups_classic.py (commit 2fd277f).
The ds460 source hardcoded the description, the two questions, and the module
ID; the generic version takes all three via the spec file so any quiz pattern
can be mirrored.
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
from pathlib import Path

import requests

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

try:
    from canvas_course_guard import enforce as guard_enforce
except ImportError:
    guard_enforce = None

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    pass

_TIMEOUT = 30
WIDE = 1000000  # range that swallows any realistic answer => auto-full


def _env_canvas() -> tuple[str, str, str]:
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    cid = os.environ.get("CANVAS_COURSE_ID", "")
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return tok, cid, base


def _load_spec(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
            return yaml.safe_load(text)
        except ImportError:
            print(f"Spec at {path} is not valid JSON. Install pyyaml for YAML support.",
                  file=sys.stderr)
            raise


def pages(url: str, headers: dict, **p) -> list:
    out: list = []
    pg = 1
    while True:
        r = requests.get(url, headers=headers, params={**p, "per_page": 100, "page": pg},
                         timeout=_TIMEOUT).json()
        if not r:
            break
        out += r
        pg += 1
    return out


def _question_payload(q: dict) -> dict:
    """Build the Canvas-side question payload from a spec entry."""
    qtype = q.get("type", "numerical_question")
    payload: dict = {
        "question_name": q["name"],
        "question_type": qtype,
        "points_possible": q.get("points", 1),
        "question_text": q.get("text", ""),
    }
    answers: list[dict] = []
    if q.get("any_answer") and qtype == "numerical_question":
        answers = [{"numerical_answer_type": "range_answer",
                    "answer_range_start": -WIDE, "answer_range_end": WIDE}]
    elif q.get("answers"):
        answers = q["answers"]
    payload["answers"] = answers
    return payload


def create_one(base: str, cid: str, headers: dict, source: dict, spec: dict) -> tuple[int, float | None]:
    """Create a Classic quiz mirroring a single New-Quiz source assignment."""
    title = source["name"]
    body = {
        "quiz[title]": title,
        "quiz[description]": spec.get("description", ""),
        "quiz[quiz_type]": "assignment",
        "quiz[assignment_group_id]": source.get("assignment_group_id"),
        "quiz[published]": "false",  # UNPUBLISHED in source; operator publishes when ready to swap
        "quiz[due_at]": source.get("due_at") or "",
        "quiz[unlock_at]": source.get("unlock_at") or "",
        "quiz[lock_at]": source.get("lock_at") or "",
    }
    q = requests.post(f"{base}/api/v1/courses/{cid}/quizzes", headers=headers, data=body,
                      timeout=_TIMEOUT).json()
    qid = q["id"]
    for q_spec in spec.get("questions", []):
        qd = _question_payload(q_spec)
        d = {f"question[{k}]": v for k, v in qd.items() if k != "answers"}
        for i, ans in enumerate(qd["answers"]):
            for k, v in ans.items():
                d[f"question[answers][{i}][{k}]"] = v
        requests.post(f"{base}/api/v1/courses/{cid}/quizzes/{qid}/questions", headers=headers,
                      data=d, timeout=_TIMEOUT)
    if spec.get("module_id"):
        requests.post(
            f"{base}/api/v1/courses/{cid}/modules/{spec['module_id']}/items",
            headers=headers,
            data={"module_item[type]": "Quiz", "module_item[content_id]": qid},
            timeout=_TIMEOUT)
    # suppress notify-of-update emails on first publish
    requests.put(f"{base}/api/v1/courses/{cid}/quizzes/{qid}", headers=headers,
                 data={"quiz[notify_of_update]": "false"}, timeout=_TIMEOUT)
    qq = requests.get(f"{base}/api/v1/courses/{cid}/quizzes/{qid}", headers=headers,
                      timeout=_TIMEOUT).json()
    return qid, qq.get("points_possible")


def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(description="Mirror New Quizzes as UNPUBLISHED Classic quizzes (§J pattern).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--spec", required=True,
                    help="Path to mirror spec JSON (or YAML if pyyaml installed). See module docstring for shape.")
    ap.add_argument("--filter-extra", default=None,
                    help="Additional substring filter on source assignment name (e.g. 'Week 7') to mirror just one.")
    ap.add_argument("--create", action="store_true", help="Actually create mirrors (default: dry-run).")
    ap.add_argument("--rebuild", action="store_true",
                    help="Delete existing Classic mirrors with matching titles + recreate clean.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Bypass canvas_course_guard for enrolled-course writes.")
    args = ap.parse_args()

    spec = _load_spec(Path(args.spec))
    source_pattern = spec.get("source_pattern")
    if not source_pattern:
        print("Spec missing required field 'source_pattern' (regex matched against assignment names).",
              file=sys.stderr)
        return 1

    tok, cid, base = _env_canvas()
    for var, val in (("CANVAS_API_TOKEN", tok), ("CANVAS_BASE_URL", base), ("CANVAS_COURSE_ID", cid)):
        if not val:
            print(f"Missing {var} in .env", file=sys.stderr)
            return 1
    headers = {"Authorization": f"Bearer {tok}"}

    write = args.create or args.rebuild
    if guard_enforce and write:
        guard_enforce(base, headers, cid, mode="write", allow_override=args.allow_enrolled)

    # SOURCE = only the New Quizzes (external_tool); never own Classic mirrors (online_quiz) — else duplicates
    name_rx = re.compile(source_pattern, re.I)
    src = [a for a in pages(f"{base}/api/v1/courses/{cid}/assignments", headers)
           if name_rx.search(a.get("name", "")) and "external_tool" in a.get("submission_types", [])]
    src.sort(key=lambda a: a.get("name", ""))
    if args.filter_extra:
        src = [a for a in src if args.filter_extra in a.get("name", "")]

    existing = {q["title"]: q["id"]
                for q in pages(f"{base}/api/v1/courses/{cid}/quizzes", headers)}

    mode = "REBUILD" if args.rebuild else "CREATE" if args.create else "DRY RUN"
    print(f"{mode} — {len(src)} source quiz(es) matching /{source_pattern}/i, course {cid}\n")

    for a in src:
        title = a["name"]
        if title in existing and not args.rebuild:
            print(f"  SKIP {title} — classic quiz exists (use --rebuild to replace)")
            continue
        print(f"  {title}: due={a.get('due_at')} grp={a.get('assignment_group_id')} "
              f"→ {len(spec.get('questions', []))} questions, unpublished")
        if not write:
            continue
        if args.rebuild and title in existing:
            requests.delete(f"{base}/api/v1/courses/{cid}/quizzes/{existing[title]}",
                            headers=headers, timeout=_TIMEOUT)
        qid, pts = create_one(base, cid, headers, a, spec)
        print(f"     -> quiz {qid}  pts={pts}  ({len(spec.get('questions', []))} questions, "
              f"any-answer wide-range numerics auto-grade to full)")
    if not write:
        print("\nDry run — nothing written. Add --create (or --rebuild) to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

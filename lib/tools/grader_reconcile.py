#!/usr/bin/env python3
"""
Reconcile self-reported claims against the REAL Canvas gradebook — anonymously.

Part of the canvas-toolbox generic grader skill (v0.1). See:
  - lib/agents/canvas_grader.md (operator-facing pipeline guide)
  - lib/agents/knowledge/grader_knowledge.md §8 (grade earned, not asked)
  - lib/agents/knowledge/grader_setup_knowledge.md §J (Classic-quiz mirror pattern)

WHAT IT DOES
  Runs LOCALLY on the instructor's machine. For each dimension in the config's
  `reconciliation.dimensions[]`, resolves keymap → Canvas user_id locally (NEVER the
  AI), then pulls actual gradebook scores or Classic-quiz submission data per
  user_id. Writes a KEYED actuals sheet (no names) so claims in submissions_deid/
  can be checked against the system of record — without identity reaching the
  cloud.

  Two source types per dimension (from grader_setup_knowledge §D + §J):
    - `gradebook`: pulls `score` per (assignment_id, user_id). Sums or lists per
      dimension.
    - `classic_quiz_submissions`: pulls `submission_data` per (assignment_id,
      user_id) and extracts named question values. Use this with the §J
      Classic-quiz mirror pattern when evidence lives in New Quizzes.

FERPA
  - Console prints KEYED rows only — never a name, never a user_id.
  - .keymap.json is local-only; this tool reads it but the AI never does.
  - canvas_course_guard.enforce(mode="read") prints a course-safety advisory.

USAGE
  # Conventional layout with a config file
  uv run python lib/tools/grader_reconcile.py \\
    --challenge-dir grading/mid_review \\
    --config grading/mid_review/config.json \\
    --primary-assignment-id 16992555

  # The --primary-assignment-id is whatever assignment the keymap's filenames
  # came from (used to resolve key → user_id via the numeric IDs embedded in
  # Canvas-format filenames). For multi-output configs, pass the assignment
  # whose submissions yield the original download filenames.

CONFIG SHAPE (JSON; YAML supported if pyyaml is installed)
  {
    "reconciliation": {
      "enabled": true,
      "dimensions": [
        {"dimension": "key_challenges", "source": "gradebook",
         "assignment_ids": [40050, 40051, 40052], "zero_means": "not_submitted"},
        {"dimension": "hours", "source": "classic_quiz_submissions",
         "assignment_ids": [40060, 40061, 40062, 40063, 40064, 40065],
         "question_names": ["Hours"],
         "zero_means": "not_submitted"}
      ]
    }
  }

GENERALIZED FROM: ds460-master/grading/reconcile_gradebook.py
(commit 8f7814b + 2fd277f — round-2 + Classic-mirror addendum). The ds460 source
had hardcoded assignment-name regexes (KC1..3 / WC1..3 / Stand-Up weeks) and
question-name strings ("Standups missed", "Hours"); the generic version takes
both via the per-assignment config instead, so any course can reconcile against
its own gradebook layout without code changes.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
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
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

NUM = re.compile(r"\d+")
_TIMEOUT = 30


def _env_canvas() -> tuple[str, str, str]:
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    cid = os.environ.get("CANVAS_COURSE_ID", "")
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return tok, cid, base


def _load_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    # Try JSON first (stdlib); fall back to YAML if pyyaml is installed.
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


def submissions(base: str, cid: str, headers: dict, aid: int) -> dict[int, dict]:
    """user_id -> submission (score, state, submitted_at, id). No names fetched."""
    out: dict[int, dict] = {}
    page = 1
    while True:
        r = requests.get(f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions",
                         headers=headers,
                         params={"per_page": 100, "page": page},
                         timeout=_TIMEOUT).json()
        if not r:
            break
        for s in r:
            out[s["user_id"]] = {
                "score": s.get("score"),
                "state": s.get("workflow_state"),
                "submitted": s.get("submitted_at") is not None,
                "id": s.get("id"),
            }
        page += 1
    return out


def resolve_user_id(filename: str, primary_subs: dict[int, dict]) -> int | None:
    """Resolve a Canvas-format filename to its user_id by matching embedded numeric IDs.

    Canvas downloads are named `<name>_<submission_id>_<attempt_id>_<title>.ext` —
    submission_id is unique per (user, assignment), so a numeric match against
    the assignment's submissions narrows to one user.
    """
    nums = set(NUM.findall(filename))
    cand = [uid for uid, s in primary_subs.items() if str(uid) in nums]
    if len(cand) == 1:
        return cand[0]
    cand2 = [uid for uid in cand if str(primary_subs[uid].get("id", "")) in nums]
    return cand2[0] if len(cand2) == 1 else None


def submission_data_by_user(base: str, cid: str, headers: dict, aid: int) -> dict[int, list]:
    """user_id -> submission_data (per-question {question_id, text}) for a Classic quiz assignment.

    Uses /assignments/:aid/submissions?include[]=submission_history → submission_data path.
    This is the workaround for the New Quizzes API gap (grader_knowledge §8 / setup §J).
    """
    out: dict[int, list] = {}
    page = 1
    while True:
        r = requests.get(f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions",
                         headers=headers,
                         params={"include[]": "submission_history", "per_page": 100, "page": page},
                         timeout=_TIMEOUT).json()
        if not r:
            break
        for s in r:
            sd = next((h.get("submission_data") for h in s.get("submission_history", [])
                       if h.get("submission_data")), None)
            if sd:
                out[s["user_id"]] = sd
        page += 1
    return out


def classic_quiz_question_map(base: str, cid: str, headers: dict, quiz_id: int) -> dict[str, int]:
    """question_name -> question_id for a Classic quiz."""
    out: dict[str, int] = {}
    r = requests.get(f"{base}/api/v1/courses/{cid}/quizzes/{quiz_id}/questions",
                     headers=headers, params={"per_page": 100}, timeout=_TIMEOUT).json()
    for q in r:
        name = q.get("question_name")
        if name:
            out[name] = q["id"]
    return out


def assignment_to_quiz_id(base: str, cid: str, headers: dict, aid: int) -> int | None:
    """Look up a Classic quiz's quiz_id given its assignment_id."""
    r = requests.get(f"{base}/api/v1/courses/{cid}/assignments/{aid}",
                     headers=headers, timeout=_TIMEOUT).json()
    return r.get("quiz_id")


def reconcile_dimension_gradebook(
    base: str, cid: str, headers: dict,
    dimension: dict, key_to_uid: dict[str, int | None],
) -> dict[str, dict]:
    """Per-key totals for a gradebook-source dimension. Returns {key: {'sum': float, 'submitted': int, 'missing': int}}."""
    per_aid_subs = {aid: submissions(base, cid, headers, aid) for aid in dimension["assignment_ids"]}
    zero_means = dimension.get("zero_means", "not_submitted")
    out: dict[str, dict] = {}
    for key, uid in key_to_uid.items():
        if uid is None:
            out[key] = {"sum": None, "submitted": "?", "missing": "?"}
            continue
        total = 0.0
        submitted = missing = 0
        for aid, subs in per_aid_subs.items():
            s = subs.get(uid, {})
            score = s.get("score")
            if score is None:
                missing += 1
                continue
            if zero_means == "not_submitted" and score == 0 and not s.get("submitted"):
                missing += 1
                continue
            total += float(score)
            submitted += 1
        out[key] = {"sum": total, "submitted": submitted, "missing": missing}
    return out


def reconcile_dimension_classic_quiz(
    base: str, cid: str, headers: dict,
    dimension: dict, key_to_uid: dict[str, int | None],
) -> dict[str, dict]:
    """Per-key totals for a classic_quiz_submissions-source dimension. Sums named numeric questions across the listed Classic quiz assignments."""
    question_names = dimension.get("question_names") or [dimension["dimension"]]
    aid_to_qmap: dict[int, dict[str, int]] = {}
    for aid in dimension["assignment_ids"]:
        quiz_id = assignment_to_quiz_id(base, cid, headers, aid)
        if quiz_id is None:
            print(f"  warn: assignment {aid} is not a Classic quiz (no quiz_id) — skipping", file=sys.stderr)
            continue
        aid_to_qmap[aid] = classic_quiz_question_map(base, cid, headers, quiz_id)

    # user_id -> {question_name: cumulative_value, 'weeks': count}
    per_uid: dict[int, dict] = defaultdict(lambda: {**{qn: 0.0 for qn in question_names}, "weeks": 0})
    for aid in dimension["assignment_ids"]:
        qmap = aid_to_qmap.get(aid, {})
        qid_by_name = {qn: qmap.get(qn) for qn in question_names}
        if not any(qid_by_name.values()):
            continue
        for uid, sd in submission_data_by_user(base, cid, headers, aid).items():
            vals = {d["question_id"]: d.get("text") for d in sd}
            saw_any = False
            for qn, qid in qid_by_name.items():
                if qid is None:
                    continue
                v = vals.get(qid)
                if v not in (None, ""):
                    try:
                        per_uid[uid][qn] += float(v)
                        saw_any = True
                    except (TypeError, ValueError):
                        pass
            if saw_any:
                per_uid[uid]["weeks"] += 1

    out: dict[str, dict] = {}
    for key, uid in key_to_uid.items():
        if uid is None or uid not in per_uid:
            out[key] = {qn: 0.0 if uid is not None else "?" for qn in question_names}
            out[key]["weeks"] = 0 if uid is not None else "?"
            continue
        out[key] = {qn: per_uid[uid][qn] for qn in question_names}
        out[key]["weeks"] = per_uid[uid]["weeks"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Anonymously reconcile review claims vs Canvas gradebook (FERPA-safe, local).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", dest="challenge_dir", required=True,
                    help="Convention base path (e.g. grading/mid_review). Holds .keymap.json.")
    ap.add_argument("--config", required=True,
                    help="Path to per-assignment config (JSON; YAML if pyyaml installed). Reads "
                         "config.reconciliation.dimensions[].")
    ap.add_argument("--primary-assignment-id", required=True, type=int,
                    help="Assignment ID whose submissions yield the original filenames in the keymap "
                         "(used to resolve key → user_id via numeric IDs in Canvas-format filenames).")
    ap.add_argument("--out", default="feedback/_gradebook_actuals.csv",
                    help="Keyed output path, relative to --challenge-dir. Default: feedback/_gradebook_actuals.csv")
    args = ap.parse_args()

    tok, cid, base = _env_canvas()
    for var, val in (("CANVAS_API_TOKEN", tok), ("CANVAS_BASE_URL", base), ("CANVAS_COURSE_ID", cid)):
        if not val:
            print(f"Missing {var} in .env", file=sys.stderr)
            return 1
    headers = {"Authorization": f"Bearer {tok}"}

    # Course-safety advisory (read-only; doesn't block, but surfaces the verdict)
    if guard_enforce:
        guard_enforce(base, headers, cid, mode="read")

    base_dir = Path(args.challenge_dir)
    mapfile = base_dir / ".keymap.json"
    if not mapfile.exists():
        print(f"No {mapfile} — run a grader_deidentify_* tool first.", file=sys.stderr)
        return 1
    keymap = json.loads(mapfile.read_text(encoding="utf-8")).get("map", {})

    cfg = _load_config(Path(args.config))
    dims = (cfg.get("reconciliation") or {}).get("dimensions") or []
    if not dims:
        print(f"Config at {args.config} has no reconciliation.dimensions[]. Nothing to reconcile.",
              file=sys.stderr)
        return 1

    # Resolve key → user_id via the primary assignment's submissions
    primary_subs = submissions(base, cid, headers, args.primary_assignment_id)
    key_to_uid: dict[str, int | None] = {k: resolve_user_id(f, primary_subs) for k, f in keymap.items()}

    # Reconcile each dimension
    per_dim_results: dict[str, dict[str, dict]] = {}
    for dim in dims:
        name = dim["dimension"]
        src = dim["source"]
        if src == "gradebook":
            per_dim_results[name] = reconcile_dimension_gradebook(base, cid, headers, dim, key_to_uid)
        elif src == "classic_quiz_submissions":
            per_dim_results[name] = reconcile_dimension_classic_quiz(base, cid, headers, dim, key_to_uid)
        else:
            print(f"  warn: unknown source '{src}' for dimension '{name}' — skipping", file=sys.stderr)

    # Flatten into one keyed row per key
    rows: list[dict] = []
    fieldnames = ["key", "uid_resolved"]
    for dim in dims:
        name = dim["dimension"]
        if dim["source"] == "gradebook":
            fieldnames += [f"{name}_sum", f"{name}_submitted", f"{name}_missing"]
        elif dim["source"] == "classic_quiz_submissions":
            for qn in (dim.get("question_names") or [name]):
                fieldnames.append(f"{name}_{qn}")
            fieldnames.append(f"{name}_weeks")

    print("  " + " ".join(f"{f:>16}" for f in fieldnames))
    unresolved = 0
    for key in sorted(keymap):
        uid = key_to_uid.get(key)
        if uid is None:
            unresolved += 1
        row = {"key": key, "uid_resolved": "yes" if uid is not None else "NO"}
        for dim in dims:
            name = dim["dimension"]
            r = per_dim_results.get(name, {}).get(key, {})
            if dim["source"] == "gradebook":
                row[f"{name}_sum"] = r.get("sum")
                row[f"{name}_submitted"] = r.get("submitted")
                row[f"{name}_missing"] = r.get("missing")
            elif dim["source"] == "classic_quiz_submissions":
                for qn in (dim.get("question_names") or [name]):
                    row[f"{name}_{qn}"] = r.get(qn)
                row[f"{name}_weeks"] = r.get("weeks")
        rows.append(row)
        print("  " + " ".join(f"{str(row.get(f, '')):>16}" for f in fieldnames))

    out = base_dir / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"\nKeyed actuals -> {out}  ({len(rows)} keys, {unresolved} unresolved). "
          f"No names anywhere — claims-vs-earned analysis safe to feed the grader.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

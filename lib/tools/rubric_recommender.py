#!/usr/bin/env python3
"""
rubric_recommender.py — Stage 7 of the rubrics workstream (generative).

For assignments that have NO rubric (the `missing_rubric` bucket from
rubric_coverage_audit), recommend a rubric whose criteria are derived from the
course's learning outcomes — so alignment/validity (backbone Criterion 1) is
satisfied BY CONSTRUCTION, the very judgment the audit's lexical C1 can't make —
with observable level descriptors pitched at the assignment's targeted Bloom's
level.

HYBRID DESIGN (per the workstream decision):
  - Deterministic SCAFFOLD now (this tool): one criterion per relevant CLO,
    4 observable levels templated from the CLO's action verb, even weights.
    Repeatable, sandbox-testable, alignment built in.
  - Agent-enrichment LATER: canvas_course_expert (wired to rubrics_knowledge)
    can refine the scaffold's descriptor prose. The scaffold is an honest
    starting point — rubrics_knowledge says rubrics always need human refinement.

Ties to:
  - course outcomes  → criteria are built FROM matched CLOs (outcome_group_links)
  - Bloom's level    → detected from the assignment's verbs; pitches the levels
                       and flags assignment-vs-CLO Bloom mismatches

`--plan` (default) shows recommendations; `--apply` writes them to Canvas via the
rubric CREATE flow (guard-checked). Sandbox-first: validate against
CANVAS_SANDBOX_ID before using on a real course.

Endpoints:
  GET    /courses/:id?include[]=total_students        (guard)
  GET    /courses/:id/blueprint_subscriptions         (guard)
  GET    /courses/:id/assignments?include[]=rubric...  (find missing-rubric)
  GET    /courses/:id/outcome_group_links?outcome_style=full  (CLOs; via import)
  POST   /courses/:id/rubrics                          (--apply only)

Exit codes:
  0  ran (plan shown, or apply completed) with no recommendations needed
  1  recommendations were produced (assignments lack rubrics)
  2  configuration error / cannot run

Usage:
  uv run python canvas_toolbox/lib/tools/rubric_recommender.py            # --plan
  uv run python canvas_toolbox/lib/tools/rubric_recommender.py --course-id 145706
  uv run python canvas_toolbox/lib/tools/rubric_recommender.py --assignment-id 123
  uv run python canvas_toolbox/lib/tools/rubric_recommender.py --json
  uv run python canvas_toolbox/lib/tools/rubric_recommender.py --apply      # writes

Requires in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, and the --target env var
(default CANVAS_COURSE_ID) or --course-id.

Reads (knowledge): rubrics_knowledge.md (backbone + typology + the "criteria must
trace to CLOs" alignment requirement this tool satisfies by construction),
outcomes_quality_knowledge.md / taxonomy_explorer_knowledge.md (Bloom verb lists).
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
from dotenv import load_dotenv

import canvas_course_guard as guard
from rubric_coverage_audit import classify, MISSING_RUBRIC
from rubric_quality_audit import fetch_course_outcomes
from __toolbox_version__ import __version__

load_dotenv()

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw_url = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = "https://" + _raw_url
CANVAS_BASE_URL = _raw_url

_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Bloom's taxonomy (revised, Anderson & Krathwohl) — from outcomes_quality /
# taxonomy_explorer knowledge. Lowest → highest cognitive level.
# ---------------------------------------------------------------------------

BLOOM_LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
BLOOM_RANK = {name: i + 1 for i, name in enumerate(BLOOM_LEVELS)}

BLOOM_VERBS = {
    "remember":   ["define", "list", "name", "recall", "identify", "label", "state",
                   "recognize", "repeat", "memorize", "match", "arrange"],
    "understand": ["explain", "describe", "summarize", "classify", "discuss",
                   "interpret", "paraphrase", "restate", "report", "review", "translate"],
    "apply":      ["apply", "use", "demonstrate", "solve", "implement", "execute",
                   "calculate", "practice", "illustrate", "operate", "schedule"],
    "analyze":    ["analyze", "compare", "contrast", "differentiate", "examine",
                   "categorize", "distinguish", "investigate", "diagram", "experiment"],
    "evaluate":   ["evaluate", "assess", "critique", "judge", "justify", "defend",
                   "argue", "appraise", "recommend", "rate", "determine"],
    "create":     ["create", "design", "develop", "compose", "construct", "formulate",
                   "produce", "generate", "devise", "plan", "synthesize", "write"],
}
_VERB_TO_LEVEL = {v: lvl for lvl, vs in BLOOM_VERBS.items() for v in vs}
# Match the longest/highest-signal verbs; word-boundary scan.
_BLOOM_RE = re.compile(r"\b(" + "|".join(sorted(_VERB_TO_LEVEL, key=len, reverse=True)) + r")\w*\b",
                       re.IGNORECASE)


def detect_bloom(text: str) -> tuple[str | None, int]:
    """Highest Bloom level whose verb appears in `text`. Returns (level, rank)
    or (None, 0) if no Bloom verb found."""
    best = (None, 0)
    plain = re.sub(r"<[^>]+>", " ", text or "")
    for m in _BLOOM_RE.finditer(plain):
        # map the matched token back to a base verb by prefix
        tok = m.group(1).lower()
        lvl = _VERB_TO_LEVEL.get(tok)
        if lvl is None:
            # token may be a conjugation (e.g. "analyzes") — strip to base
            for base in (tok[:-1], tok[:-2], tok[:-3]):
                if base in _VERB_TO_LEVEL:
                    lvl = _VERB_TO_LEVEL[base]; break
        if lvl and BLOOM_RANK[lvl] > best[1]:
            best = (lvl, BLOOM_RANK[lvl])
    return best


# ---------------------------------------------------------------------------
# Token matching (shares the stemming approach used by rubric_quality_audit C1)
# ---------------------------------------------------------------------------

_STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
         "with", "by", "from", "as", "at", "that", "this", "be", "will", "have",
         "has", "their", "its", "it", "they", "student", "students", "able",
         "course", "outcome", "learner", "learners"}


def _stem(t: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: -len(suf)]
    return t


def _tokens(s: str) -> set[str]:
    return {_stem(t) for t in re.findall(r"[a-z]+", (s or "").lower())
            if len(t) >= 4 and t not in _STOP}


def extract_clo_verb_object(clo_text: str) -> tuple[str, str]:
    """Pull the action verb + object from a CLO. Returns (verb, object_phrase).
    Falls back to ('demonstrate', <whole clo>) if no Bloom verb is found."""
    plain = re.sub(r"<[^>]+>", " ", clo_text or "").strip()
    # strip a leading "Course Outcome NN" label + "Students will"
    plain = re.sub(r"^\s*course\s+outcome\s*\d*\s*[-:]?\s*", "", plain, flags=re.IGNORECASE)
    plain = re.sub(r"^\s*students?\s+will\s+(be\s+able\s+to\s+)?", "", plain, flags=re.IGNORECASE)
    m = _BLOOM_RE.search(plain)
    if m:
        verb_tok = m.group(1).lower()
        base = _VERB_TO_LEVEL.get(verb_tok)
        # use the matched (possibly conjugated) token's base form for the frame
        verb = verb_tok
        for cand in (verb_tok, verb_tok[:-1], verb_tok[:-2], verb_tok[:-3]):
            if cand in _VERB_TO_LEVEL:
                verb = cand; break
        obj = plain[m.end():].strip(" .,:;") or plain
        return verb, obj
    return "demonstrate", plain.strip(" .,:;")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}


def _get(endpoint: str, params: dict | None = None):
    url = f"{CANVAS_BASE_URL}/api/v1{endpoint}"
    results: list = []
    p: dict = {**(params or {}), "per_page": 100}
    while url:
        try:
            resp = requests.get(url, headers=_headers(), params=p, timeout=_TIMEOUT)
        except Exception:
            return None
        if resp.status_code >= 400:
            return None
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url = None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        p = {}
    return results


def list_assignments(course_id: str) -> list[dict]:
    url = f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/assignments"
    p = {"include[]": ["rubric", "rubric_settings"], "per_page": 100}
    out: list = []
    while url:
        try:
            resp = requests.get(url, headers=_headers(), params=p, timeout=_TIMEOUT)
        except Exception:
            return out
        if resp.status_code >= 400:
            return out
        data = resp.json()
        if isinstance(data, list):
            out.extend(data)
        else:
            return [data]
        url = None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        p = {}
    return out


def create_rubric(course_id: str, assignment_id: int, spec: dict) -> dict | None:
    """Write a rubric + grading association onto the assignment (form-encoded
    nested payload — same shape proven by sandbox_rubric_fixtures.py)."""
    data: dict[str, str] = {
        "rubric[title]": spec["title"],
        "rubric[free_form_criterion_comments]": "0",
        "rubric_association[association_id]": str(assignment_id),
        "rubric_association[association_type]": "Assignment",
        "rubric_association[purpose]": "grading",
        "rubric_association[use_for_grading]": "true",
    }
    for ci, crit in enumerate(spec["criteria"]):
        base = f"rubric[criteria][{ci}]"
        data[f"{base}[description]"] = crit["description"]
        data[f"{base}[long_description]"] = crit.get("long_description", "")
        data[f"{base}[points]"] = str(crit["points"])
        data[f"{base}[criterion_use_range]"] = "false"
        for ri, rating in enumerate(crit["ratings"]):
            rb = f"{base}[ratings][{ri}]"
            data[f"{rb}[description]"] = rating["description"]
            data[f"{rb}[long_description]"] = rating.get("long_description", "")
            data[f"{rb}[points]"] = str(rating["points"])
    try:
        resp = requests.post(
            f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/rubrics",
            headers=_headers(), data=data, timeout=_TIMEOUT,
        )
    except Exception as e:
        print(f"    ERROR creating rubric: {e}", file=sys.stderr)
        return None
    if resp.status_code >= 400:
        print(f"    ERROR creating rubric: {resp.status_code} {resp.text[:200]}",
              file=sys.stderr)
        return None
    return resp.json()


# ---------------------------------------------------------------------------
# Recommendation (deterministic scaffold)
# ---------------------------------------------------------------------------

def build_criterion(clo_text: str, points: float, assignment_bloom: str | None) -> dict:
    """One criterion derived from a CLO, with 4 observable levels templated from
    the CLO's action verb. Alignment is built in (the criterion IS the CLO)."""
    verb, obj = extract_clo_verb_object(clo_text)
    obj_short = (obj[:48] + "…") if len(obj) > 49 else obj
    desc = f"{verb.capitalize()}: {obj_short}".strip()
    p = round(points)
    # Even 4-level point split (Exemplary=full, then ~75/50/0).
    lv = [
        ("Exemplary", f"Thoroughly and accurately demonstrates the ability to {verb} {obj}; insight beyond the requirement.", p),
        ("Proficient", f"Demonstrates the ability to {verb} {obj} correctly and completely.", round(p * 0.75)),
        ("Developing", f"Partially demonstrates the ability to {verb} {obj}; notable gaps or inaccuracies.", round(p * 0.5)),
        ("Beginning", f"Does not yet demonstrate the ability to {verb} {obj}.", 0),
    ]
    return {
        "description": desc,
        "long_description": f"Assesses course outcome: {re.sub(r'<[^>]+>', ' ', clo_text).strip()}",
        "points": p,
        "clo_verb": verb,
        "clo_bloom": detect_bloom(clo_text)[0],
        "ratings": [{"description": d, "long_description": ld, "points": pts} for d, ld, pts in lv],
    }


def recommend_for_assignment(a: dict, outcomes: list[str]) -> dict:
    """Produce a recommended rubric scaffold for one no-rubric assignment."""
    name = a.get("name") or "<untitled>"
    desc = re.sub(r"<[^>]+>", " ", a.get("description") or "")
    a_text = f"{name}  {desc}"
    a_bloom, a_rank = detect_bloom(a_text)

    total = a.get("points_possible")
    try:
        total = float(total) if total not in (None, 0) else 100.0
    except (TypeError, ValueError):
        total = 100.0

    # Match relevant CLOs by stemmed token overlap (>=2 shared).
    a_tokens = _tokens(a_text)
    scored = []
    for clo in outcomes:
        shared = a_tokens & _tokens(clo)
        if len(shared) >= 2:
            scored.append((len(shared), clo, sorted(shared)))
    scored.sort(key=lambda x: -x[0])
    matched = scored[:5]  # cap criteria at 5 (Brown: 4-6 is the sweet spot)

    notes: list[str] = []
    if matched:
        per = round(total / len(matched))
        criteria = [build_criterion(clo, per, a_bloom) for _, clo, _ in matched]
        # Bloom mismatch check: assignment targets higher than its CLOs?
        clo_ranks = [BLOOM_RANK.get(c["clo_bloom"], 0) for c in criteria if c["clo_bloom"]]
        if a_rank and clo_ranks and a_rank > max(clo_ranks):
            notes.append(
                f"Assignment verbs target Bloom '{a_bloom}' but matched outcomes top out at "
                f"'{BLOOM_LEVELS[max(clo_ranks)-1]}'. Ensure the top rating requires "
                f"{a_bloom}-level work, or confirm the assignment isn't over-reaching its CLOs."
            )
        source = "criteria derived from matched course outcomes (alignment built in)"
    else:
        # No CLO clearly relates — honest fallback, flag the alignment gap.
        criteria = [{
            "description": f"{(a_bloom or 'demonstrate').capitalize()}: {name[:48]}",
            "long_description": "GENERIC scaffold — no course outcome clearly relates to this "
                                "assignment by wording. Map this to a CLO before use, or treat "
                                "as a possible alignment gap.",
            "points": round(total),
            "clo_verb": a_bloom or "demonstrate",
            "clo_bloom": a_bloom,
            "ratings": [
                {"description": "Exemplary", "long_description": "Exceeds the stated task requirements with insight.", "points": round(total)},
                {"description": "Proficient", "long_description": "Meets the stated task requirements correctly and completely.", "points": round(total * 0.75)},
                {"description": "Developing", "long_description": "Partially meets the task; notable gaps.", "points": round(total * 0.5)},
                {"description": "Beginning", "long_description": "Does not yet meet the task.", "points": 0},
            ],
        }]
        notes.append(
            "No course outcome clearly relates to this assignment by wording — scaffold is "
            "GENERIC. Either map the assignment to a CLO (validity gap to resolve) or refine "
            "criteria manually. (rubrics_knowledge: criteria should trace to a stated CLO.)"
        )
        source = "generic scaffold (no CLO matched)"

    notes.append("Scaffold only — refine descriptor language and weights for your context "
                 "(rubrics_knowledge: rubrics always need human refinement). "
                 "canvas_course_expert can enrich this.")

    return {
        "assignment_id": a.get("id"),
        "assignment_name": name,
        "assignment_bloom": a_bloom,
        "points_possible": a.get("points_possible"),
        "matched_clo_count": len(matched),
        "source": source,
        "rubric": {
            "title": f"Recommended rubric — {name}"[:200],
            "criteria": criteria,
        },
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render(course_id: str, course_name: str, recs: list[dict],
            n_outcomes: int, ts: str, detailed: bool) -> list[str]:
    out = [
        "# Rubric Recommendations (scaffolds for assignments lacking a rubric)",
        "",
        f"Course:         {course_name} ({course_id})",
        f"Run at:         {ts}",
        f"CLOs available: {n_outcomes}" + ("" if n_outcomes else "  ⚠️ none — recommendations will be GENERIC; criteria can't be tied to outcomes"),
        f"No-rubric assignments needing a rubric: {len(recs)}",
        "",
        "Each rubric below is a DETERMINISTIC SCAFFOLD: criteria derived from the",
        "matched course outcomes (so alignment is built in), 4 observable levels",
        "templated from each outcome's verb, even weights. Refine before/at --apply.",
        "",
        "=" * 64,
    ]
    for r in recs:
        out.append("")
        out.append(f"## {r['assignment_name']}  (assignment_id={r['assignment_id']})")
        out.append(f"   targeted Bloom's: {r['assignment_bloom'] or 'unspecified'}   "
                   f"points: {r['points_possible']}   {r['source']}")
        for n in r["notes"]:
            out.append(f"   → {n}")
        out.append(f"   Recommended rubric: {r['rubric']['title']}")
        for c in r["rubric"]["criteria"]:
            out.append(f"     • {c['description']}  ({c['points']} pts"
                       + (f", CLO Bloom: {c['clo_bloom']}" if c.get('clo_bloom') else "") + ")")
            if detailed:
                out.append(f"         {c['long_description']}")
                for rt in c["ratings"]:
                    out.append(f"           [{rt['points']:>3}] {rt['description']}: {rt['long_description']}")
    return out


def _write_report(path: Path, body: str) -> None:
    path.write_text(body + "\n", encoding="utf-8")
    print(f"\nReport written to {path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Recommend CLO-aligned, Bloom-targeted rubric scaffolds for "
                    "assignments that lack a rubric (Stage 7, hybrid scaffold).")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--target", default="CANVAS_COURSE_ID",
                    help="Env var holding the course ID (default CANVAS_COURSE_ID)")
    ap.add_argument("--course-id", default=None, help="Literal course ID; overrides --target")
    ap.add_argument("--assignment-id", default=None,
                    help="Recommend for just this assignment (must be missing a rubric)")
    ap.add_argument("--detailed", action="store_true", help="Show full level descriptors")
    ap.add_argument("--json", action="store_true", dest="emit_json", help="Machine-readable JSON")
    ap.add_argument("--report", default=None, metavar="PATH", help="Write output to PATH")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE the recommended rubrics to Canvas (guard-checked). "
                         "Default is plan-only.")
    ap.add_argument("--allow-enrolled", action="store_true",
                    help="Bypass the safety guard on --apply (sandbox should be safe)")
    ap.add_argument("--allow-generic", action="store_true",
                    help="Proceed even when NO course outcomes can be established "
                         "(emits generic, NON-outcome-aligned scaffolds). Off by "
                         "default: the recommender refuses rather than emit "
                         "anti-aligned rubrics (#31 CLO-discovery gate).")
    args = ap.parse_args()

    if not CANVAS_BASE_URL or CANVAS_BASE_URL == "https://" or not CANVAS_API_TOKEN:
        print("ERROR: set CANVAS_BASE_URL and CANVAS_API_TOKEN in .env", file=sys.stderr)
        sys.exit(2)
    course_id = (args.course_id or os.environ.get(args.target, "")).strip()
    if not course_id:
        print(f"ERROR: no course ID via --course-id or ${args.target}.", file=sys.stderr)
        sys.exit(2)

    guard.enforce(base_url=CANVAS_BASE_URL, headers=_headers(), course_id=course_id,
                  mode="write" if args.apply else "read",
                  allow_override=args.allow_enrolled, label="recommender target")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    course = _get(f"/courses/{course_id}") or {}
    course_name = (course.get("name") if isinstance(course, dict) else None) or "<unknown>"

    assignments = list_assignments(course_id)
    if not assignments:
        print(f"\nNo assignments returned for {course_id} ('{course_name}').", file=sys.stderr)
        sys.exit(2)
    outcomes = fetch_course_outcomes(course_id)

    # CLO-discovery gate (#31): criteria are derived FROM the course's outcomes,
    # so with no outcomes established every emitted rubric is unaligned by
    # construction. Refuse rather than emit confidently-wrong (anti-aligned)
    # rubrics. --allow-generic overrides for the case where generic scaffolds
    # are knowingly wanted.
    if not outcomes and not args.allow_generic:
        print(f"\n🔴 Could not establish course outcomes for {course_id} "
              f"('{course_name}').", file=sys.stderr)
        print("   No Canvas Outcomes, and no Learning Outcomes section found in the "
              "syllabus. Rubric criteria can't be aligned to outcomes that don't "
              "exist — refusing to emit anti-aligned rubrics.", file=sys.stderr)
        print("   Fix: define Canvas Outcomes, or add a Learning Outcomes section to "
              "the syllabus (run syllabus_audit.py to check), then re-run.",
              file=sys.stderr)
        print("   Override: --allow-generic emits generic scaffolds anyway "
              "(NOT outcome-aligned).", file=sys.stderr)
        sys.exit(2)

    # Target set: missing-rubric assignments (optionally one).
    targets = [a for a in assignments if classify(a) == MISSING_RUBRIC]
    if args.assignment_id:
        targets = [a for a in targets if str(a.get("id")) == str(args.assignment_id)]
        if not targets:
            print(f"\nAssignment {args.assignment_id} is not in the missing_rubric set "
                  "(already has a rubric, or isn't a gradable/submittable gap).", file=sys.stderr)
            sys.exit(2)

    recs = [recommend_for_assignment(a, outcomes) for a in targets]

    if args.emit_json:
        payload = {
            "tool": "rubric_recommender", "tool_version": __version__, "run_at": ts,
            "course": {"id": course_id, "name": course_name},
            "outcomes_available": len(outcomes),
            "recommendations": recs,
        }
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        print(body)
        if args.report:
            _write_report(Path(args.report), body)
    else:
        lines = _render(course_id, course_name, recs, len(outcomes), ts, args.detailed)
        print("\n".join(lines))
        if args.report:
            _write_report(Path(args.report), "\n".join(lines))

    if args.apply:
        print("\n--apply: writing recommended rubrics to Canvas…", file=sys.stderr)
        applied = 0
        for r in recs:
            res = create_rubric(course_id, r["assignment_id"], r["rubric"])
            ok = res is not None
            print(f"  {'CREATED' if ok else 'FAILED ':8} {r['assignment_name']}", file=sys.stderr)
            applied += 1 if ok else 0
        print(f"\nApplied {applied}/{len(recs)} rubrics.", file=sys.stderr)

    sys.exit(1 if recs else 0)


if __name__ == "__main__":
    main()

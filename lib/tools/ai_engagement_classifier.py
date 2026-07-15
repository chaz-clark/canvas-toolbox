#!/usr/bin/env python3
"""AI engagement classifier — pluggable engagement-taxonomy over a student↔AI transcript.

cb owns this primitive; ngai-n8n consumes it (see docs/ai-engagement-classifier-design.md).

The framework (tiers, modes, thresholds, archetypes) is NOT hard-coded — it lives in a
swappable *taxonomy profile* JSON under lib/agents/knowledge/engagement_taxonomy/. Swap the
profile to revert to a 3-tier model, compare a 5-tier model, or plug in a validated instrument;
the engine and the output contract stay stable.

The LLM's only job is to classify each STUDENT turn into one mode (the ordered `sequence`).
Everything else — tier/mode distribution, 0-100 agency score, threshold gaps, transitions
(the route), archetype — is computed deterministically in Python from that sequence, so it's
unit-testable without the model.

Usage:
    ai_engagement_classifier.py --transcript conv.json [--profile aimodes_placeholder]
    ai_engagement_classifier.py --list-profiles
    ai_engagement_classifier.py --transcript conv.json --dry-run   # prints prompt, no LLM call

Transcript JSON:
    {"conversation_id": "abc", "messages": [{"role": "student", "text": "..."},
                                            {"role": "assistant", "text": "..."}, ...]}

ANTHROPIC_API_KEY must be set for a real run (the toolkit already ships `anthropic`).
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parent.parent / "agents" / "knowledge" / "engagement_taxonomy"
DEFAULT_PROFILE = "aimodes_placeholder"
CONTRACT_SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------

def list_profiles() -> list[str]:
    if not PROFILE_DIR.is_dir():
        return []
    return sorted(p.stem for p in PROFILE_DIR.glob("*.json"))


def load_profile(profile_id: str) -> dict:
    path = PROFILE_DIR / f"{profile_id}.json"
    if not path.is_file():
        avail = ", ".join(list_profiles()) or "(none found)"
        print(f"Unknown profile '{profile_id}'. Available: {avail}", file=sys.stderr)
        sys.exit(1)
    profile = json.loads(path.read_text(encoding="utf-8"))
    _validate_profile(profile)
    return profile


def _validate_profile(p: dict) -> None:
    for key in ("profile_id", "tiers", "modes"):
        if key not in p:
            print(f"Profile missing required key '{key}'.", file=sys.stderr)
            sys.exit(1)
    tier_ids = {t["id"] for t in p["tiers"]}
    for m in p["modes"]:
        if m["tier"] not in tier_ids:
            print(f"Mode '{m['id']}' references unknown tier '{m['tier']}'.", file=sys.stderr)
            sys.exit(1)


# ---------------------------------------------------------------------------
# LLM provider (same shape as grader_grade.py's GraderLLM; kept local + minimal)
# ---------------------------------------------------------------------------

class ClassifierLLM:
    def complete(self, system: str, user: str, temperature: float = 0.0,
                 max_tokens: int = 4096) -> str:
        raise NotImplementedError


class AnthropicClassifierLLM(ClassifierLLM):
    """Lazy-imports `anthropic` so --help / --list-profiles / --dry-run work without the SDK."""

    def __init__(self, model: str):
        try:
            from anthropic import Anthropic
        except ImportError:
            print("Missing dep: `anthropic`. Install via `uv add anthropic`.", file=sys.stderr)
            sys.exit(1)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY not set in .env.", file=sys.stderr)
            sys.exit(1)
        self.client = Anthropic()
        self.model = model

    def complete(self, system: str, user: str, temperature: float = 0.0,
                 max_tokens: int = 4096) -> str:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = self.client.messages.create(
                    model=self.model, max_tokens=max_tokens, temperature=temperature,
                    system=system, messages=[{"role": "user", "content": user}],
                )
                return "".join(b.text for b in resp.content if hasattr(b, "text"))
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if any(k in msg for k in ("rate", "overloaded", "timeout", "connection")):
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise RuntimeError(f"LLM call failed after 3 attempts: {last_err}")


def make_provider(name: str, model: str) -> ClassifierLLM:
    if name == "anthropic":
        return AnthropicClassifierLLM(model)
    print(f"Unknown provider '{name}'. Supported: anthropic.", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def build_system_prompt(profile: dict) -> str:
    lines = [
        "You classify how a STUDENT is engaging an AI in each of their turns, using the",
        f"taxonomy below (profile: {profile.get('display_name', profile['profile_id'])}).",
        "",
        "TIERS (least to most intellectual agency):",
    ]
    for t in sorted(profile["tiers"], key=lambda x: x["order"]):
        lines.append(f"  - {t['label']} ({t['id']}): {t['description']}")
    lines += ["", "MODES (assign exactly one per student turn; use the mode id):"]
    for m in profile["modes"]:
        sig = "; ".join(m.get("signals", []))
        lines.append(f"  - {m['id']} [{m['tier']}] {m['label']}: {m['definition']}"
                     + (f"  Signals: {sig}" if sig else ""))
    lines += [
        "",
        "Classify each student turn by what the student is DOING in that exchange, in order.",
        "Return STRICT JSON, no prose, no code fences:",
        '  {"sequence": [{"index": <student-turn number>, "mode": "<mode id>",',
        '                 "confidence": <0..1>, "evidence": "<short quote or rationale>"}]}',
        "One entry per student turn. `mode` MUST be one of the mode ids above.",
    ]
    return "\n".join(lines)


def build_user_prompt(messages: list[dict]) -> tuple[str, int]:
    """Render the transcript with student turns numbered; returns (prompt, student_turn_count)."""
    parts = ["Conversation — classify each STUDENT turn:", ""]
    student_n = 0
    for msg in messages:
        role = msg.get("role", "").lower()
        text = (msg.get("text") or "").strip()
        if role in ("student", "user", "human"):
            parts.append(f"[Student turn {student_n}]")
            parts.append(text)
            student_n += 1
        else:  # assistant / ai — context only
            parts.append("[AI reply]")
            parts.append(text)
        parts.append("")
    parts.append(f"There are {student_n} student turns (0..{student_n - 1}). "
                 "Return one sequence entry per student turn.")
    return "\n".join(parts), student_n


def _parse_response(text: str) -> dict | None:
    """Parse the LLM's JSON. Tolerant of stray markdown fencing (mirrors grader_grade)."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(t[start:end + 1])
            except json.JSONDecodeError:
                pass
    return None


# ---------------------------------------------------------------------------
# Deterministic aggregation (LLM produces `sequence`; everything here is pure)
# ---------------------------------------------------------------------------

def aggregate(sequence: list[dict], profile: dict) -> dict:
    """Compute the full contract body from an ordered mode sequence + a profile."""
    mode_to_tier = {m["id"]: m["tier"] for m in profile["modes"]}
    tier_weight = {t["id"]: t.get("agency_weight", 0) for t in profile["tiers"]}
    n = len(sequence)

    # normalize + attach derived tier
    seq: list[dict] = []
    for i, e in enumerate(sequence):
        mode = e.get("mode")
        tier = mode_to_tier.get(mode)
        seq.append({
            "index": e.get("index", i),
            "mode": mode,
            "tier": tier,
            "confidence": e.get("confidence"),
            "evidence": e.get("evidence", ""),
        })

    mode_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    for e in seq:
        if e["mode"]:
            mode_counts[e["mode"]] = mode_counts.get(e["mode"], 0) + 1
        if e["tier"]:
            tier_counts[e["tier"]] = tier_counts.get(e["tier"], 0) + 1

    mode_distribution = {k: round(v / n, 4) for k, v in mode_counts.items()} if n else {}
    tier_distribution = {k: round(v / n, 4) for k, v in tier_counts.items()} if n else {}

    agency_score = round(sum(
        (tier_counts.get(t["id"], 0) / n) * tier_weight[t["id"]] for t in profile["tiers"]
    )) if n else 0

    threshold_gaps = []
    for m in profile["modes"]:
        if "threshold" not in m:
            continue
        actual = mode_distribution.get(m["id"], 0.0)
        threshold_gaps.append({
            "mode": m["id"], "actual": actual, "target": m["threshold"],
            "gap": round(actual - m["threshold"], 4),
        })

    transitions_counter: dict[tuple[str, str], int] = {}
    for a, b in zip(seq, seq[1:]):
        if a["mode"] and b["mode"]:
            transitions_counter[(a["mode"], b["mode"])] = \
                transitions_counter.get((a["mode"], b["mode"]), 0) + 1
    transitions = [{"from": f, "to": t, "count": c}
                   for (f, t), c in sorted(transitions_counter.items())]

    archetype = classify_archetype(mode_distribution, tier_distribution, mode_counts, profile)

    return {
        "sequence": seq,
        "tier_distribution": tier_distribution,
        "mode_distribution": mode_distribution,
        "agency_score": agency_score,
        "threshold_gaps": threshold_gaps,
        "transitions": transitions,
        "archetype": archetype,
    }


def classify_archetype(mode_dist: dict, tier_dist: dict, mode_counts: dict, profile: dict) -> dict:
    """Evaluate each archetype's declarative rule; return the first match, else the default."""
    agency_mode_ids = [m["id"] for m in profile["modes"] if m["tier"] == "agency"]
    thresholds = {m["id"]: m.get("threshold", 0.0) for m in profile["modes"]}
    modal_mode = max(mode_counts, key=mode_counts.get) if mode_counts else None
    ctx = {
        "mode_dist": mode_dist, "tier_dist": tier_dist, "modal_mode": modal_mode,
        "agency_mode_ids": agency_mode_ids, "thresholds": thresholds,
    }
    for arch in profile.get("archetypes", []):
        if _eval_rule(arch.get("rule", ""), ctx):
            return {"id": arch["id"], "label": arch["label"],
                    "rationale": arch.get("rule", "")}
    default_id = profile.get("archetype_default")
    match = next((a for a in profile.get("archetypes", []) if a["id"] == default_id), None)
    if match:
        return {"id": match["id"], "label": match["label"], "rationale": "default"}
    return {"id": default_id or "unknown", "label": default_id or "Unknown", "rationale": "default"}


def _eval_rule(rule: str, ctx: dict) -> bool:
    """Tiny, safe evaluator for the profile archetype DSL (no eval()).

    Grammar:  rule := clause (' AND ' clause)*
              clause := 'modal_mode == <mode_id>'  |  <sum> OP <rhs>
              sum    := term (' + ' term)*
              term   := 'tier:<id>' | 'mode:<id>' | 'any_agency_mode'
              OP     := '>=' | '=='
              rhs    := <float> | 'threshold' (the LHS mode's own threshold)
    Any parse failure yields False (the rule simply doesn't fire).
    """
    try:
        return all(_eval_clause(c.strip(), ctx) for c in rule.split(" AND ") if c.strip())
    except Exception:
        return False


def _eval_clause(clause: str, ctx: dict) -> bool:
    if clause.startswith("modal_mode"):
        _, _, target = clause.partition("==")
        return ctx["modal_mode"] == target.strip()

    op = ">=" if ">=" in clause else ("==" if "==" in clause else None)
    if op is None:
        return False
    lhs_raw, _, rhs_raw = clause.partition(op)
    terms = [t.strip() for t in lhs_raw.split("+")]
    lhs_val = sum(_resolve_term(t, ctx) for t in terms)

    rhs_raw = rhs_raw.strip()
    if rhs_raw == "threshold":
        # single mode:<id> term on the LHS → use that mode's threshold
        mid = terms[0].split(":", 1)[1] if terms[0].startswith("mode:") else None
        rhs_val = ctx["thresholds"].get(mid, 0.0)
    else:
        rhs_val = float(rhs_raw)

    return lhs_val >= rhs_val if op == ">=" else lhs_val == rhs_val


def _resolve_term(term: str, ctx: dict) -> float:
    if term.startswith("tier:"):
        return ctx["tier_dist"].get(term.split(":", 1)[1], 0.0)
    if term.startswith("mode:"):
        return ctx["mode_dist"].get(term.split(":", 1)[1], 0.0)
    if term == "any_agency_mode":
        return max((ctx["mode_dist"].get(m, 0.0) for m in ctx["agency_mode_ids"]), default=0.0)
    raise ValueError(f"unknown term '{term}'")


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def build_report(profile: dict, conversation_id: str, message_count: int,
                 student_turn_count: int, body: dict) -> dict:
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "profile_id": profile["profile_id"],
        "profile_version": profile.get("version"),
        "profile_status": profile.get("status"),
        "attribution": profile.get("attribution"),
        "conversation_id": conversation_id,
        "message_count": message_count,
        "student_turn_count": student_turn_count,
        **body,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Classify AI engagement modes over a transcript.")
    ap.add_argument("--transcript", help="Path to transcript JSON (see module docstring).")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, help=f"Taxonomy profile id (default {DEFAULT_PROFILE}).")
    ap.add_argument("--list-profiles", action="store_true", help="List available profiles and exit.")
    ap.add_argument("--dry-run", action="store_true", help="Print the assembled prompt; no LLM call.")
    ap.add_argument("--provider", default="anthropic", help="LLM provider (currently: anthropic).")
    ap.add_argument("--model", default="claude-sonnet-4-6", help="Model id.")
    ap.add_argument("--out", help="Write the report JSON here (default: stdout).")
    args = ap.parse_args()

    if args.list_profiles:
        for pid in list_profiles():
            p = load_profile(pid)
            print(f"{pid:24s} {p.get('status','?'):11s} {p.get('display_name','')}")
        return 0

    if not args.transcript:
        ap.error("--transcript is required (or use --list-profiles)")

    profile = load_profile(args.profile)
    convo = json.loads(Path(args.transcript).read_text(encoding="utf-8"))
    messages = convo.get("messages", [])
    conversation_id = convo.get("conversation_id", Path(args.transcript).stem)

    system = build_system_prompt(profile)
    user, student_turn_count = build_user_prompt(messages)

    if args.dry_run:
        print("===== SYSTEM =====\n" + system)
        print("\n===== USER =====\n" + user)
        report = build_report(profile, conversation_id, len(messages), student_turn_count,
                              aggregate([], profile))
        print("\n===== EMPTY CONTRACT (no LLM call) =====\n"
              + json.dumps(report, indent=2))
        return 0

    llm = make_provider(args.provider, args.model)
    raw = llm.complete(system, user, temperature=0.0)
    parsed = _parse_response(raw)
    if not parsed or "sequence" not in parsed:
        print("Model did not return a valid {'sequence': [...]} object.", file=sys.stderr)
        print(raw, file=sys.stderr)
        return 1

    report = build_report(profile, conversation_id, len(messages), student_turn_count,
                          aggregate(parsed["sequence"], profile))
    out_text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(out_text + "\n", encoding="utf-8")
        print(f"Wrote {args.out}  (agency_score={report['agency_score']}, "
              f"archetype={report['archetype']['id']})")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

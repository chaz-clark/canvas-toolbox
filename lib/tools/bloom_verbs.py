#!/usr/bin/env python3
"""
bloom_verbs.py — the single shared home for Bloom's (revised) verb→level data
and observable-verb checks. Pure data + functions, no I/O.

Grounds the "measurable" and "rigor" checks in clo_quality_audit.py and the
Bloom-level targeting in rubric_recommender.py. Sourced from
outcomes_quality_knowledge.md / taxonomy_explorer_knowledge.md (Anderson &
Krathwohl 2001 revised taxonomy + the AoL CLO rubric's non-observable flag list).

NOTE: rubric_recommender.py still carries an older inline copy of this verb map
(BLOOM_VERBS / detect_bloom). It is functionally equivalent; migrating it to
import from here is a queued tidy-up (kept separate to avoid destabilizing the
already-validated recommender in the same change).
"""

from __future__ import annotations

import re

# Lowest → highest cognitive level (revised Bloom's).
BLOOM_LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
BLOOM_RANK = {name: i + 1 for i, name in enumerate(BLOOM_LEVELS)}

BLOOM_VERBS: dict[str, list[str]] = {
    "remember":   ["define", "list", "name", "recall", "identify", "label", "state",
                   "repeat", "memorize", "match", "arrange", "duplicate", "order"],
    "understand": ["explain", "describe", "summarize", "classify", "discuss",
                   "interpret", "paraphrase", "restate", "report", "review",
                   "translate", "express", "indicate", "locate", "select", "sort"],
    "apply":      ["apply", "use", "demonstrate", "solve", "implement", "execute",
                   "calculate", "practice", "illustrate", "operate", "schedule",
                   "employ", "administer", "prepare", "sketch"],
    "analyze":    ["analyze", "compare", "contrast", "differentiate", "examine",
                   "categorize", "distinguish", "investigate", "diagram",
                   "experiment", "appraise", "criticize", "question", "test"],
    "evaluate":   ["evaluate", "assess", "critique", "judge", "justify", "defend",
                   "argue", "recommend", "rate", "determine", "value", "predict"],
    "create":     ["create", "design", "develop", "compose", "construct", "formulate",
                   "produce", "generate", "devise", "plan", "synthesize", "write",
                   "build", "combine", "organize", "rank", "estimate", "decide"],
}

_VERB_TO_LEVEL: dict[str, str] = {v: lvl for lvl, vs in BLOOM_VERBS.items() for v in vs}

# Non-observable verbs — the AoL CLO rubric flags these as NOT measurable: they
# describe internal states no assessment can directly observe. (Note: "recognize"
# is flagged here even though some Bloom lists include it, per the AoL rubric.)
NON_OBSERVABLE = {
    "understand", "know", "appreciate", "learn", "feel", "recognize", "grasp",
    "comprehend", "realize", "be", "become", "value", "believe", "think",
}
# "be aware of" / "be familiar with" — multiword non-observable phrases.
NON_OBSERVABLE_PHRASES = ["be aware of", "be familiar with", "have knowledge of",
                          "gain an understanding", "develop an appreciation"]

_BLOOM_RE = re.compile(
    r"\b(" + "|".join(sorted(_VERB_TO_LEVEL, key=len, reverse=True)) + r")\w*\b",
    re.IGNORECASE,
)


def _strip(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def detect_bloom(text: str) -> tuple[str | None, int]:
    """Highest Bloom level whose verb appears in `text`. (level, rank) or (None, 0)."""
    best: tuple[str | None, int] = (None, 0)
    for m in _BLOOM_RE.finditer(_strip(text)):
        tok = m.group(1).lower()
        lvl = _VERB_TO_LEVEL.get(tok)
        if lvl is None:
            for base in (tok[:-1], tok[:-2], tok[:-3]):
                if base in _VERB_TO_LEVEL:
                    lvl = _VERB_TO_LEVEL[base]
                    break
        if lvl and BLOOM_RANK[lvl] > best[1]:
            best = (lvl, BLOOM_RANK[lvl])
    return best


def all_bloom_levels(text: str) -> set[str]:
    """Every distinct Bloom level whose verb appears in `text` (for double-barrel
    detection — a CLO spanning two levels often means two goals)."""
    levels: set[str] = set()
    for m in _BLOOM_RE.finditer(_strip(text)):
        tok = m.group(1).lower()
        lvl = _VERB_TO_LEVEL.get(tok)
        if lvl is None:
            for base in (tok[:-1], tok[:-2], tok[:-3]):
                if base in _VERB_TO_LEVEL:
                    lvl = _VERB_TO_LEVEL[base]
                    break
        if lvl:
            levels.add(lvl)
    return levels


def leading_nonobservable(text: str) -> str | None:
    """If the outcome's PRIMARY verb is non-observable, return it; else None.
    Checks multiword phrases first, then the first verb-like token."""
    plain = _strip(text).strip().lower()
    for ph in NON_OBSERVABLE_PHRASES:
        if ph in plain:
            return ph
    # Strip a common stem ("students will be able to") to reach the real verb.
    plain = re.sub(r"^.*?\bwill\s+be\s+able\s+to\b\s*", "", plain)
    plain = re.sub(r"^.*?\b(students?|learners?|you|the\s+student)\s+will\b\s*", "", plain)
    plain = plain.lstrip("•-–*0123456789.): ")
    tokens = re.findall(r"[a-z]+", plain)
    for t in tokens[:3]:  # the action verb is among the first few words
        if t in NON_OBSERVABLE:
            return t
        if t in _VERB_TO_LEVEL:
            return None  # hit an observable verb first → measurable
    return None

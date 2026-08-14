#!/usr/bin/env python3
"""Course rebinding — re-point local sync state at a DIFFERENT Canvas course (#294).

WHY THIS EXISTS
  `.canvas/index.json` and the markdown frontmatter carry `canvas_id` values that are
  COURSE-SPECIFIC. Pull from course A, then push to course B, and every write is
  `PUT /courses/B/assignments/<A's id>` → "The specified resource does not exist."
  Four courses hit this in one week migrating Spring→Fall (52, 131, 44 and 71 items),
  and it recurs 3x/year plus on every master→section promotion.

WHY STRIPPING THE IDS DOESN'T WORK
  The obvious fix — delete the ids and let push create fresh — was tried in the field
  and failed 44/44 with "no canvas_id in index". Every writer in canvas_sync
  (`_push_assignment`, `_push_quiz`, `_push_discussion`) is UPDATE-ONLY: it requires an
  existing id and issues a PUT. There is no create path.

  Nor should there be. New Quizzes (quizzes.next) cannot be created or edited through
  the classic API at all — the field report shows canvas_sync already refusing them
  with "Canvas-only: must be edited in Canvas UI". Any hand-rolled create path would
  silently drop them, along with rubrics, question banks and file attachments.

  Canvas's OWN copy (content migration / .imscc import) carries all of it. Both field
  workarounds independently converged on it. So the division of labour is:

      Canvas creates the content.   This module re-points local state at it.

WHAT MATCHING IS ALLOWED TO DO
  A wrong match is worse than no match: it silently aims every future push — and any
  grade sync — at the wrong item, and nothing surfaces until someone notices marks on
  the wrong assignment. So:

    - Pages match on `page_url` (a real slug, stable across copies).
    - Everything else matches on TITLE: exact first, then case/whitespace-normalized.
    - Anything ambiguous on EITHER side is refused and reported, never guessed.
    - Unmatched items are reported and left untouched, never silently dropped.

  Nothing here writes. `plan_rebind()` is pure; the caller decides whether to apply.
"""
from __future__ import annotations

import re

# Types whose identity is a slug rather than a title.
_SLUG_TYPES = {"Page"}

_WS = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Case- and whitespace-insensitive key. Deliberately conservative — it does NOT
    strip punctuation, because "Quiz 1" and "Quiz 1 (Retake)" must stay distinct."""
    return _WS.sub(" ", (title or "").strip()).casefold()


def _dupes(keys: list[str]) -> set[str]:
    seen, dupe = set(), set()
    for k in keys:
        (dupe if k in seen else seen).add(k)
    return dupe


def index_target(items: list[dict]) -> dict:
    """Build lookup tables from a target-course inventory.

    `items` are dicts with at least: type, canvas_id, title, and page_url for Pages.
    Returns {"by_slug", "by_title", "by_norm", "ambiguous"} where `ambiguous` holds
    normalized titles that appear more than once IN THE TARGET — those can never be
    matched safely, whatever the local side looks like."""
    by_slug, by_title, by_norm = {}, {}, {}
    norm_keys = []
    for it in items:
        t, cid = it.get("type"), it.get("canvas_id")
        if not cid:
            continue
        if t in _SLUG_TYPES and it.get("page_url"):
            by_slug[(t, it["page_url"])] = cid
            continue
        title = it.get("title") or ""
        if not title:
            continue
        by_title[(t, title)] = cid
        n = normalize_title(title)
        norm_keys.append((t, n))
        by_norm[(t, n)] = cid
    ambiguous = {k for k in _dupes([f"{t}\x00{n}" for t, n in norm_keys])}
    return {"by_slug": by_slug, "by_title": by_title, "by_norm": by_norm,
            "ambiguous": ambiguous}


def plan_rebind(local_files: dict, target: dict) -> dict:
    """Work out the new canvas_id for each local entry. PURE — writes nothing.

    `local_files` is `.canvas/index.json["files"]`: path -> entry.

    Returns {"matched": {path: (old_id, new_id, how)}, "unmatched": [...],
             "ambiguous": [...], "skipped": [...]}.

      matched    — safe to re-point. `how` is "slug" | "title" | "normalized".
      unmatched  — exists locally, not found in the target. Left alone; the content
                   must be copied into the target first.
      ambiguous  — the title is duplicated on one side or the other. REFUSED, because
                   guessing here aims future pushes at the wrong item.
      skipped    — no usable identity (no title and no slug) — nothing to match on."""
    matched, unmatched, ambiguous, skipped = {}, [], [], []
    local_norm = [f"{e.get('type')}\x00{normalize_title(e.get('title') or '')}"
                  for e in local_files.values()
                  if e.get("type") not in _SLUG_TYPES and e.get("title")]
    local_dupes = _dupes(local_norm)

    for path, entry in local_files.items():
        typ = entry.get("type")
        old = entry.get("canvas_id")

        if typ in _SLUG_TYPES:
            slug = entry.get("page_url")
            if not slug:
                skipped.append(path)
                continue
            new = target["by_slug"].get((typ, slug))
            if new:
                matched[path] = (old, new, "slug")
            else:
                unmatched.append(path)
            continue

        title = entry.get("title") or ""
        if not title:
            skipped.append(path)
            continue
        key = f"{typ}\x00{normalize_title(title)}"
        if key in target["ambiguous"] or key in local_dupes:
            ambiguous.append(path)
            continue
        new = target["by_title"].get((typ, title))
        how = "title"
        if not new:
            new = target["by_norm"].get((typ, normalize_title(title)))
            how = "normalized"
        if new:
            matched[path] = (old, new, how)
        else:
            unmatched.append(path)

    return {"matched": matched, "unmatched": unmatched,
            "ambiguous": ambiguous, "skipped": skipped}


def apply_rebind(index: dict, plan: dict, new_course_id: str) -> dict:
    """Return a NEW index with matched entries re-pointed. Does not mutate the input
    and does not touch the filesystem.

    Stale `module_item_id` / `module_canvas_id` are CLEARED on every rebound entry
    rather than carried over: they belong to the old course, and a stale value is
    worse than an absent one because it looks valid."""
    import copy
    out = copy.deepcopy(index)
    out["course_id"] = str(new_course_id)
    for path, (_old, new, _how) in plan["matched"].items():
        entry = out["files"].get(path)
        if entry is None:
            continue
        entry["canvas_id"] = new
        entry.pop("module_item_id", None)
        entry.pop("module_canvas_id", None)
    return out


def summarize(plan: dict) -> str:
    """One-line-per-bucket summary. Never prints a canvas_id — the counts are what an
    operator acts on, and the detail lives in the index."""
    m = plan["matched"]
    by_how = {}
    for _old, _new, how in m.values():
        by_how[how] = by_how.get(how, 0) + 1
    bits = ", ".join(f"{n} by {how}" for how, n in sorted(by_how.items()))
    lines = [f"  matched   : {len(m)}" + (f"  ({bits})" if bits else "")]
    if plan["ambiguous"]:
        lines.append(f"  AMBIGUOUS : {len(plan['ambiguous'])}  — duplicate titles; "
                     f"refused rather than guessed")
    if plan["unmatched"]:
        lines.append(f"  unmatched : {len(plan['unmatched'])}  — not in the target "
                     f"course; copy the content there first")
    if plan["skipped"]:
        lines.append(f"  skipped   : {len(plan['skipped'])}  — no title or slug to "
                     f"match on")
    return "\n".join(lines)

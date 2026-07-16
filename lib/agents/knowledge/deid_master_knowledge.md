---
name: deid_master_knowledge
version: "1.0"
last_updated: 2026-06-26
description: The de-identification master — the foundational primitive underneath every keyed / FERPA workflow; a stable user_id <-> deid_code surface.
skill_type: knowledge
shape: reference
scope: "The deid master primitive (build_deid_master.py), the FERPA rule (agents never read .deid_master.csv), and how user_id / deid_code are used across keyed tools."
consumed_by:
  - student_late_accommodation.py
companion_json_deprecated: "2026-07-16 - authored as YAML frontmatter (JSON purge convention)"
provenance:
  sources:
    - "issue #109 (v0.70.0, 2026-06-26)"
runtime_strategy: read_at_runtime
metadata: { knowledge_id: deid_master_knowledge }
---

# De-identification master — the foundational primitive

**The missing primitive that sits underneath every keyed / FERPA workflow.**

Status: introduced in v0.70.0 (2026-06-26) per issue #109.
Built by: `lib/tools/build_deid_master.py`.
Consumed by: `lib/tools/student_late_accommodation.py`, and future
keyed-grading + PR-check tools.

---

## For AI Agents

**DO NOT READ** `grading/.deid_master.csv`. It contains student names (FERPA Zone 2).

When the instructor provides `--user-id 280379` or `--deid-code DS-B9CA2B`, use it directly with accommodation tools. You never need the mapping file.

---

## Why this exists

Before v0.70.0, the canvas-toolbox had two ways to identify a student
PII-free:

- **Per-assignment keymaps** — generated during `grader_fetch` for each
  assignment. The same student gets a DIFFERENT key in each set, tied
  to the assignment's filenames. Useful for the grading pipeline; not
  useful for course-wide cross-tool reference.
- **`.known_names.txt`** — flat name roster used by the scrub pass.
  Has no stable id surface.

What's been missing: a **course-wide stable** `code ↔ user_id ↔ name`
master. One row per enrolled student. Same code for the same student
across every tool, every run, every refresh. That's what this file is.

---

## The 4-column contract

```csv
deid_code,user_id,sortable_name,withdrawn
S-95DBB6,173819,"Ahlstrom, Sydney",0
S-A8FE4E,18065,"Alfaia Monteiro, Ronaldo",1
```

| Column | Type | Meaning | Read by tools? |
|---|---|---|---|
| `deid_code` | `str` | Stable opaque code, format `<prefix><N-hex-chars>` | YES — primary key |
| `user_id` | `int` | Canvas numeric user_id, source of truth | YES — for API calls |
| `sortable_name` | `str` | `"Lastname, Firstname"` from Canvas | **NO** unless explicit |
| `withdrawn` | `int` | `1` if enrollment is `inactive`/`completed`/`deleted`, else `0` | YES — for analysis |

**The `sortable_name` column is for the OPERATOR's local lookup only.**
Tools must not read it (and must not echo it) unless the operator has
explicitly requested re-identification (e.g., the Title IV report's
final step, which writes outside the repo).

---

## How `deid_code` is computed

```python
deid_code = f"{prefix}{sha256(str(user_id))[:hash_bits].upper()}"
```

- **Default prefix:** `S-` (Student). Override via `--prefix DS-` or similar.
- **Default hash bits:** 6 hex chars. Format example: `S-95DBB6`.
- **Stable:** same `user_id` → same `deid_code` across every run.
- **Order-free:** doesn't depend on roster position or fetch order.
- **Collision-aware:** the build tool detects duplicates at write-time
  and errors out with instructions to re-run with `--hash-bits 8`.

Collision math (sha256 first N hex chars, birthday paradox):

| Hash bits | Collision-free space | 50 students | 200 | 500 | 1000 | 5000 |
|---|---|---|---|---|---|---|
| 6 | 16M | 0.007% | 0.12% | 0.7% | 3% | — |
| 8 | 4B | — | — | 0.003% | 0.01% | 0.3% |
| 10 | 1T | practically collision-free at any class size |

For typical 30–200 student courses, 6 hex is safe and far more typeable
(`S-95DBB6` vs `S-95DBB6A8`).

---

## Why `withdrawn` matters

The default Canvas People view shows ACTIVE students only. Final-grade
analysis, last-engagement audits (`course_engagement_audit.py`), and
accommodations frequently need visibility into students who **dropped
mid-semester** (state: `inactive` / `completed` / `deleted`).

In one DS 460 pilot: **30 active → 37 total → 7 withdrawn**.

The withdrawn flag lets downstream tools either include or exclude
withdrawn students depending on the use case (engagement audit:
include; gradebook reconcile: probably include; accommodation: usually
exclude — withdrawn students don't need accommodations).

---

## FERPA tier — gitignored repo file (tier 2)

This file lives in the repo at `grading/.deid_master.csv` but is
**git-ignored**. The build tool writes a `grading/.gitignore` (containing
`*`) the first time it creates the directory — so even if the operator
forgets to add `grading/` to their main `.gitignore`, the directory's own
`.gitignore` prevents tracked commits.

| Tier | Surface | What lives here | Defense |
|---|---|---|---|
| 1 (cloud) | LLM token I/O | deid_code only; never user_id or name | The keymap is here |
| **2 (gitignored repo file)** | **local filesystem in repo** | **`.deid_master.csv`, keymaps, `.known_names.txt`, `.env`** | **`grading/.gitignore`** |
| 3 (outside repo) | `~/Downloads/` | Named PDF / MD reports | LLM has no cwd access there |

---

## How downstream tools consume the master

**Resolve `deid_code` → `user_id`, read ONLY the user_id column:**

```python
from lib.tools.build_deid_master import resolve_user_id_from_master  # pseudo
uid = resolve_user_id_from_master(Path("grading/.deid_master.csv"), "S-95DBB6")
# uid is now 173819. sortable_name was never read.
```

**Reference implementation:** `lib/tools/student_late_accommodation.py`
(`resolve_user_id_from_master`) — reads only the `user_id` column, raises
clear errors when the master doesn't exist or the code isn't present.

**Operators tell their agent:**
> *"Give student S-95DBB6 late-work accommodation on all assignments."*

The agent passes the code (not the name) to the tool. The tool resolves
the code locally. The name never crosses the LLM boundary.

---

## Refresh discipline

Re-run `build_deid_master.py` when:

- New students enroll
- Students drop / are dropped
- The enrollment-state field flips (inactive → active or vice versa)

The tool refuses to overwrite an existing master without `--force`. This
is a deliberate friction point — re-running silently could invalidate
deid_code references in operator notes / handoffs / Slack messages.
Always check the diff (`git diff` won't help — file is gitignored —
but `--dry-run` previews changes).

---

## Path A — `.known_names.txt` is now derived from the master (v0.71.0)

As of v0.71.0, every `build_deid_master.py` run **also writes
`grading/.known_names.txt`** (the scrub-pass roster used by every
`grader_deidentify_*` tool). Each enrolled student contributes BOTH
forms of their name (sortable "Lastname, Firstname" + display
"Firstname Lastname") so the scrub matches whichever shape appears
in a submission's raw text.

This makes the master the single source of truth for the scrub
roster — one rebuild keeps both files in sync. `grader_fetch.py`
continues to APPEND submitters not yet in the roster (it preserves
its `update_known_names()` append-dedup), so a workflow that runs
grader_fetch first still works without a master rebuild.

**Path B** (full migration where the master replaces per-assignment
keymaps for the grader pipeline) is approved in principle and
deferred to a future session.

## Related knowledge

- `grader_knowledge.md §1` — the three FERPA tiers + zone discipline
- `course_engagement_audit_knowledge.md` — Title IV pattern; also uses
  re-identification at the last step
- Issue #109 — the original ask that led to this primitive

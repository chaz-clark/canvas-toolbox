---
name: ferpa-deid
description: Use for the de-identification / re-identification WORKFLOW — building the course-wide de-id master, de-identifying submissions or a gradebook (docx/pdf/xlsx/jupyter/databricks/text/comments) before anything reaches the LLM, re-identifying keyed results back to students, and scanning for name leaks. Load this when preparing student artifacts for AI processing or turning keyed results back into a named report. The FERPA *discipline* (never read Zone-2 files) is constitutional and always applies; this skill is the *how* of the de-id machinery.
---

# FERPA de-identification / re-identification

The machinery that lets student work be processed by an LLM without a name ever
reaching cloud context: strip identity → opaque keys → process → map keys back
locally.

> The **constitution** (AGENTS.md) is the law: the name-bearing files
> (`.deid_master.csv`, `.keymap.json`, `.known_names.txt`, `.review.csv`,
> `submissions_raw/`, `feedback/_grader*.csv`) are **FERPA Zone-2** and are **never**
> read or displayed — verify with `wc -l`/`ls`, never `cat`/`head`/`grep`. This
> skill runs the de-id tools; it never bypasses that rule.

## The two-zone flow

```
raw submissions (names) ──deidentify──▶ opaque keys ──▶ LLM / analysis
        ▲                                                     │
        └────────── reidentify (BY KEY, local) ◀──────────────┘
```

- **Zone 1 (cloud-safe):** de-identified keys + grades. Fine for the LLM.
- **Zone 2 (local only, gitignored):** the keymap/master that links keys ↔ names.

## Building the master

`build_deid_master.py` builds the course-wide `.deid_master.csv` — **one row per
student**, keyed by `user_id`, with a stable opaque `deid_code = sha256(user_id)[:6]`.
It dedups multi-section students (a student in S1+S2 is otherwise returned twice) and
auto-derives `.known_names.txt` (the scrub roster). Run `--force` to refresh from
current enrollment. This is the identity surface every keyed tool and accommodation
consumes.

## De-identifying artifacts (before the LLM)

`grader_fetch.py` de-identifies submissions automatically, dispatching to the right
format adapter. The standalone adapters exist for direct/one-off use:

| Artifact | Tool |
|---|---|
| Word docs | `grader_deidentify_docx.py` |
| PDFs | `grader_deidentify_pdf.py` |
| Excel | `grader_deidentify_xlsx.py` |
| Jupyter notebooks | `grader_deidentify_jupyter.py` |
| Databricks exports | `grader_deidentify_databricks.py` |
| Plain text | `grader_deidentify_text.py` |
| Canvas submission comments | `grader_deidentify_comments.py` |
| A gradebook export | `grader_deidentify_gradebook.py` |

## Re-identifying results (BY KEY — never by sort order)

- `grader_reidentify.py` maps `key → user_id` via `.keymap.json`, and is
  **duplicate-aware** (`user_id → [keys]`): one student legitimately has many keys
  across submission batches (e.g. `final-review_*` + `fpr_*`). **Never** map by row
  position / sort order — that misattributes results. If two batches share user_ids,
  that's expected; the keymap disambiguates.
- `grader_reidentify_gradebook.py` re-identifies a de-identified gradebook.
- Re-identified output is Zone-2 — write it outside any cloud-synced or git-tracked
  path (e.g. `~/Downloads/`), never back into the repo.

## Verifying no leak

`grader_name_leak_check.py` scans keyed/de-identified artifacts for any name that
slipped through the scrub (against `.known_names.txt`). Run it before handing
de-identified material to the LLM if you're unsure the scrub was complete.

## Quick command map

| Ask | Command |
|---|---|
| "Rebuild the de-id master / student list" | `build_deid_master.py --force` |
| "De-identify these submissions" | (usually automatic via `grader_fetch.py`) |
| "Turn the keyed results back into names" | `grader_reidentify.py --challenge-dir grading/<name>` |
| "Check nothing leaked a name" | `grader_name_leak_check.py …` |

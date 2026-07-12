# Canvas Toolbox — Offline Mode Guide

**For faculty without a Canvas API token** — work from Canvas UI downloads instead of the API.

> Rewritten 2026-07-12 to match what actually shipped. Earlier drafts of this
> guide described tools and flows that don't exist (`grade_assignments.py`,
> comment upload via gradebook CSV, `CANVAS_TOKEN`). Those are corrected here.

---

## The core idea

Almost every toolbox tool ultimately reads a course into a **local `course/` folder** and works from that. How the folder gets filled is the only thing that changes between online and offline:

```
online:   canvas_sync --pull   (Canvas API)   ─┐
                                                ├─►  course/  ─►  tools read course/
offline:  offline_import  (a .imscc export)    ─┘
```

A tool run with `--local` (or `CANVAS_MODE=offline`) reads `course/` and makes **zero API calls** — so it needs no token, and it doesn't re-fetch data that's already synced. "Offline" is just "the folder was filled from a `.imscc` instead of the API."

The gradebook workflows are separate (they use the exported CSV, not `course/`) — see below.

---

## What can and can't run offline

| Category | Offline? | Notes |
|---|---|---|
| **Read / report** — audits & analysis | ✅ **yes** | Read `course/`, emit a report. Never touch the live course. |
| **Gradebook** — grades, de-ID, scores → CSV | ✅ **yes** | Work from the exported gradebook CSV; upload via **Grades → Import**. |
| **Content write-back** — `.imscc` date-shift | ⚠️ **new/empty course only** | Re-importing to a *live* section is destructive; use a new course. |
| **Student-specific writes** — SAS accommodations, quiz-time extensions, late/exempt, submit-on-behalf | ❌ **API-only** | Per-student data isn't in a content export, and there's no safe offline write-back. Do these in the Canvas UI. |
| **Learning-outcome & analytics tools** | ❌ **API-only** | Outcomes are account-level (empty in a course export); page-views/participation are API-only. |

**Why the split:** a read-only audit on a slightly-stale local snapshot just produces an out-of-date *report* (re-sync and re-run). A *write* derived from stale data can clobber live changes — and student accommodations were never in the local store to begin with.

---

## Setup

```bash
# .env
CANVAS_MODE=offline        # optional — makes --local the default for tools that support it
CANVAS_API_TOKEN=          # not needed in offline mode
CANVAS_TIMEZONE=America/Denver   # for DST-correct .imscc date shifting (set your institution's zone)
```

The env var is **`CANVAS_API_TOKEN`** (online only). Helpers live in `lib/tools/` (e.g. `_course_loader.py`).

---

## Workflow 1 — Audit a course offline

**Download:** Canvas → Course → Settings → **Export Course Content** → Common Cartridge (`.imscc`) → `~/Downloads/`.

```bash
# .imscc -> course/
uv run python lib/tools/offline_import.py --imscc ~/Downloads/<course>.imscc

# then any converted audit reads course/ (no API):
uv run python lib/tools/workload_audit.py        --local
uv run python lib/tools/syllabus_audit.py        --local
uv run python lib/tools/accessibility_audit.py   --local
uv run python lib/tools/content_representation_audit.py --local
```

Converted audits accept `--local` (read `course/`) or `--course-dir <dir>`. With `CANVAS_MODE=offline` set, `--local` is automatic.

**Read-only:** these emit reports and never touch Canvas.

**Staleness caveat:** the report reflects the `.imscc` you imported (or your last `canvas_sync --pull`), not the live course. Re-export/re-import to refresh.

**Not yet offline** (need data a content export doesn't include or reconstruct yet): `grading_structure_audit`, `formative_variety_audit`, `rubric_quality_audit`, `rubric_coverage_audit` (assignment-group / rubric joins — planned), and `clo_quality_audit` (outcomes are account-level, absent from exports → API-only).

---

## Workflow 2 — Grade offline (scores)

**Download:** Canvas → **Grades → Export** → `~/Downloads/`.

```bash
# (optional, for sharing) de-identify:
uv run python lib/tools/grader_deidentify_gradebook.py --input ~/Downloads/<grades>.csv

# apply scores to the gradebook CSV, then re-identify for upload:
uv run python lib/tools/grader_gradebook_apply.py --scores scores.csv --assignment-id <id> \
    --gradebook ~/Downloads/<grades>.csv --out ~/Desktop/grades_upload.csv
uv run python lib/tools/grader_reidentify_gradebook.py --input <deid>.csv --map <map>.json --out upload.csv
```

**Upload:** Canvas → **Grades → Import** → `grades_upload.csv`.

**Comments do NOT ride the gradebook CSV** — Canvas gradebook import is scores-only. Offline, use `feedback/_all_comments.md` as a SpeedGrader paste sheet; with a token, `grader_push_comments.py` posts them via the API.

---

## Workflow 3 — Copy a course to a new semester

**Download** the `.imscc`, then:

```bash
uv run python lib/tools/imscc_adjust_dates.py --input ~/Downloads/<course>.imscc \
    --shift-days 364 --out ~/Desktop/next_semester.imscc
```

- Shifts every schedule date, **preserving identifiers** (so a re-import overwrites in place) and **DST-correct** (a Saturday 11:59 PM due date stays Saturday). Use a multiple of **7** (e.g. 364) to keep weekdays.
- Validates before writing; **import to a NEW/empty course** — re-importing to a live section is destructive.

---

## FERPA

- De-ID uses stable codes (`deid_code_for`, consistent toolbox-wide); the re-id map lives under `.canvas/` (git-ignored). De-ID tools print counts only, never names.
- `course/` and gradebook CSVs hold real data — keep them out of git (`.canvas/` is already ignored).

---

## FAQ

**Do I need a token?** No — offline audits, gradebook CSV work, and `.imscc` date-shift all run tokenless.

**Can I do SAS accommodations offline?** No. They're per-student live writes; do them in the Canvas UI. This is a hard limitation, not a missing feature.

**Is offline data live?** No — it reflects your last export/sync. Re-import to refresh.

**Related:** [offline_mode_sprints.md](./offline_mode_sprints.md) (build status + architecture), [offline_mode.md](./offline_mode.md) (design notes).

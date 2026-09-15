---
name: title-iv
description: Use for federal Title IV compliance — the last-date-of-academic-engagement / unofficial-withdrawal audit (course_engagement_audit), the cached Title IV snapshot (update_title_iv_snapshot), and AI-engagement classification. Load this when the task mentions Title IV, R2T4, unofficial withdrawal (UW/UF), last date of attendance/engagement, or "who stopped participating." This is a compliance domain, distinct from general course auditing — the classifications carry federal-aid consequences.
---

# Title IV engagement & unofficial-withdrawal compliance

Federal financial-aid compliance (34 CFR 668.22 / R2T4): determine each student's
**last date of academically related activity** and flag unofficial withdrawals. This
is a **compliance** domain, not a general course audit — a wrong classification has
federal-aid consequences, so the tool surfaces candidates and the registrar/financial-
aid office makes the determination.

> The **constitution** (AGENTS.md) binds you: named reports are written OUTSIDE the
> repo (never a cloud-synced or git-tracked path), and console output is
> de-identified (user_id, never names).

## The classifier — `course_engagement_audit.py`

Classifies enrolled students:

- **NEVER_PARTICIPATED** — no engagement on record (logging in ≠ engagement; there
  must be a submission, quiz attempt, or discussion entry).
- **UW** (Unofficial Withdrawal) — last engagement before the UF cutoff, passing-or-
  unknown grade.
- **UF** (Unofficial Fail) — UW *and* a failing grade → R2T4 candidate.
- **INACTIVE_ENROLLMENT** — dropped/concluded in Canvas; surfaced for review, **not**
  auto-classified (may be an already-processed *official* withdrawal — the registrar/
  FA office decides).

## Key behaviors

- **UF cutoff auto-derives from Canvas.** No `--uf-date`? It uses the course's Canvas
  end date, falling back to the term end date (`--uf-date end` / `term-end` / an
  explicit `YYYY-MM-DD`). The resolved date + its source print in the header, so the
  classification date is auditable.
- **Inactive students are included by default** — the exact population an engagement
  audit exists to review. `--active-only` excludes them.
- **FERPA output discipline:** the named report is written to `~/Downloads/`, never
  inside the repo. Re-identification happens only at the final write step, keyed, to a
  file outside any cloud-synced / git-tracked location.

```
course_engagement_audit.py                       # cutoff = Canvas course end date
course_engagement_audit.py --uf-date 2026-07-25  # explicit cutoff
course_engagement_audit.py --active-only         # skip the inactive-review section
```

## Supporting tools

- `update_title_iv_snapshot.py` — fetch + cache the canonical Title IV snapshot for a
  course (the reference state a report is computed against).
- `ai_engagement_classifier.py` — pluggable engagement-taxonomy over a student↔AI
  transcript, for courses that count AI-tutor interaction as academically related
  activity.

## Regulatory note

The distance-education R2T4 final rules took effect **2026-07-01**. Re-verify the
tool's classification rules against the then-current FSA Handbook (Vol. 5, Ch. 1) if
you're reading this well after that date — federal definitions of "academic
engagement" evolve.

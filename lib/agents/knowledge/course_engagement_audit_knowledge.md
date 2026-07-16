---
name: course_engagement_audit_knowledge
version: "1.0"
last_updated: 2026-06-26
description: The Title IV last-date-of-academic-engagement audit — classifies enrolled students into UF / UW / Never-Participated / Active for R2T4 reporting.
skill_type: knowledge
shape: reference
scope: "Title IV academic-engagement definition (34 CFR 668.22), the UF/UW/Never-Participated/Active classification, the Downloads-folder FERPA pattern, re-verification cadence. Out of scope: the financial-aid office's R2T4 calculation."
consumed_by:
  - canvas_grader.md
  - canvas_course_expert.md
companion_json_deprecated: "2026-07-16 - authored as YAML frontmatter (JSON purge convention)"
provenance:
  sources:
    - "34 CFR 668.22 (Title IV); local snapshots in sources/title_iv/ (verified 2026-06-26)"
runtime_strategy: read_at_runtime
metadata: { knowledge_id: course_engagement_audit_knowledge }
---

# Course Engagement Audit — Title IV last-date-of-engagement classifier

> Reference. The Title IV federal-compliance audit that classifies enrolled students by their last date of academic engagement against an operator-provided UF cutoff date.

**Used by:** [`canvas_grader.md`](../canvas_grader.md), `canvas_course_expert.md`, anyone running term-end UW/UF reporting.

**Companions:**
- [`grader_knowledge.md §1`](grader_knowledge.md) — FERPA two-zone architecture + NEW third tier (Downloads-folder named reports)
- [`../tools/course_engagement_audit.py`](../../tools/course_engagement_audit.py) — the audit tool
- [`../tools/update_title_iv_snapshot.py`](../../tools/update_title_iv_snapshot.py) — refreshes the cached Title IV sources
- [`sources/title_iv/`](sources/title_iv/) — local snapshots of the canonical Title IV sources (auditable provenance)

**Scope:** the Title IV definition of academic engagement, the UF/UW/Never-Participated/Active classification scheme, the Downloads-folder FERPA pattern, and re-verification cadence. Out of scope: the financial aid office's R2T4 calculation itself (that's their job; this tool surfaces the candidates).

_**Title IV definitions verified:** 2026-06-26. **Next review:** 2027-06-26 (or sooner if DOE issues new R2T4 / distance-ed guidance)._

---

## 1 — Why this exists

Federal Title IV (34 CFR 668.22) requires that when a student receives federal financial aid (Pell, Direct Loans, etc.) AND fails to complete an enrollment period, the institution must:

1. Determine the student's **last date of academically related activity**
2. Run an **R2T4 (Return of Title IV funds) calculation**
3. Return unearned funds to the federal government (or the student must repay)
4. Document the determination within **14 days**, calculation within **30 days**, return within **45 days**

Without this tool, the BYUI faculty workflow is: trawl SpeedGrader + Discussions + Quizzes for 30-200 students at term-end, manually note each one's last engagement date, then forward to the financial aid office. Term-end load is real; the audit removes it.

---

## 2 — What counts as academic engagement (Title IV definitions)

Per the [2025-2026 FSA Handbook Vol 2 Ch 1](sources/title_iv/fsa-2025-2026-vol2-ch1.md) (cached) and the [Jan 2025 Federal Register final rules](sources/title_iv/federal-register-2025-01-03-final-rules.md) (cached; effective 2026-07-01):

> "Academic engagement" = **Active participation by a student in an instructional activity** related to the student's course of study.

### ✅ Counts (distance-ed examples DOE cites)

- Submitting an assignment
- Submitting a quiz / taking a quiz attempt
- Contributing to an online discussion (posts + replies)
- Initiating contact with a faculty member to ask a course-related question

### ❌ Does NOT count

- **Logging into Canvas** — "documenting that a student has logged into an online class is not sufficient, by itself, to demonstrate academic attendance" ([Vol 2 Ch 2](sources/title_iv/fsa-2025-2026-vol2-ch1.md))
- **Viewing a page** — passive consumption is not engagement
- **Canvas `last_activity_at`** — this field includes page views; not Title IV-compliant for R2T4 documentation
- **Academic counseling / advising** — explicitly removed from the list of academically related activities in the new R2T4 final rules

### Operational implication for the audit

The tool computes `last_engagement` as the **MAX timestamp** across three data sources Canvas explicitly exposes:

| Source | Canvas API endpoint | Timestamp field |
|---|---|---|
| Assignment submissions | `/courses/:cid/students/submissions` | `submitted_at` |
| Quiz submissions | `/courses/:cid/students/submissions` (graded quizzes appear here) | `submitted_at` |
| Discussion entries | `/courses/:cid/discussion_topics/:tid/entries` | `created_at` + `updated_at` |

`last_activity_at` from the enrollment record is **deliberately excluded** — including it would make the audit non-compliant for R2T4 purposes.

---

## 3 — The classification scheme

Per 34 CFR 668.22 and the [2025-2026 FSA Handbook Vol 5 Ch 1](sources/title_iv/fsa-2025-2026-vol5-ch1.md):

| Bucket | Definition | What the institution does |
|---|---|---|
| **ACTIVE** | `last_engagement >= UF_date` | No Title IV concern; nothing to report |
| **UW** (Unofficial Withdrawal) | `last_engagement < UF_date` AND current grade is passing-or-unknown | Watch; if the student does not earn a passing grade by term end, re-classify as UF and run R2T4 |
| **UF** (Unofficial Fail) | `last_engagement < UF_date` AND `current_score < passing_threshold` | R2T4 candidate — forward to financial aid; institution must complete R2T4 within 30 days of determination |
| **NEVER_PARTICIPATED** | No engagement events on record (enrolled but never engaged) | Must return 100% of Title IV aid disbursed (no-show rule); institution treats as never having begun attendance |

The faculty operator provides the **UF cutoff date** — typically a date past which "if they hadn't engaged by then, they're presumed withdrawn." Common choices:
- The midpoint of the term (for institutions using the midpoint as the default withdrawal date)
- Two weeks before the term end (institution-specific policy)
- The last day classes were synchronously meeting

This is a **policy choice the institution makes**; the audit is parameterized so different institutions can match their own policy.

---

## 4 — The Downloads-folder pattern (FERPA tier 3)

This audit is the FIRST canvas-toolbox tool that writes a **named report outside the repo**. It establishes a third tier of FERPA discipline:

| Tier | Where names live | What's there | Example |
|---|---|---|---|
| 1 | **Cloud / AI zone** | NO names — opaque keys only | Grader sees `KC1-A1B2C3`, never the student's name |
| 2 | **Local repo, gitignored** | Names allowed, but never committed; never read by AI | `.fetch_log.json`, `.known_names.txt`, `submissions_raw/<prefix>_<uid>.<ext>` |
| 3 | **Outside the repo entirely** *(NEW v0.69.0+)* | Named reports the AI must never touch | `~/Downloads/engagement-audit-<course-id>-<YYYY-MM-DD>.md` |

The audit's flow:

1. Process **keyed** end-to-end (user_id, not name)
2. Console output is **keyed-only** (counts + path; no names hit the terminal)
3. At the very last step, the audit looks up `user_id → name` from the in-memory enrollment data
4. The named report is written to `~/Downloads/` — outside the repo, outside the LLM's working-directory access

**Defense in depth:** the audit refuses to write the named report inside `cwd` even if the operator passes `--out` with a path inside the repo. The error message names the FERPA tier 3 pattern + points at `grader_knowledge.md §1`.

**Why this matters:** the LLM running canvas-toolbox has filesystem access scoped to the repo's working directory (per Claude Code / Cursor / Continue.dev defaults). It does NOT have access to `~/Downloads/` (or it shouldn't — verify per IDE / extension). The named report physically lives outside the LLM's read surface.

**Operator discipline:** **don't copy the Downloads report back into the repo**, don't sync it to a cloud folder that the IDE indexes, don't paste its contents into an agent prompt. If the report needs to be shared with the financial aid office, share it directly from Downloads (email attachment, institutional file-sharing, etc.) — never via the repo.

---

## 5 — Title IV source provenance + re-verification

This knowledge file references **6 cached Title IV sources** in [`sources/title_iv/`](sources/title_iv/). The cached snapshots are produced by [`update_title_iv_snapshot.py`](../../tools/update_title_iv_snapshot.py):

| Source id | What | Char count (2026-06-26) |
|---|---|---|
| `cfr-668-22` | 34 CFR 668.22 — Treatment of Title IV funds when a student withdraws (Cornell Law) | ~42k |
| `fsa-2025-2026-vol5-ch1` | FSA Handbook Vol 5 Ch 1 — General Requirements for Withdrawals + R2T4 | ~131k |
| `fsa-2025-2026-vol5-ch2` | FSA Handbook Vol 5 Ch 2 — Steps in R2T4 Calculation Part 1 | ~137k |
| `fsa-2025-2026-vol5-ch3` | FSA Handbook Vol 5 Ch 3 — R2T4 Case Studies Part 1 | ~53k |
| `fsa-2025-2026-vol2-ch1` | FSA Handbook Vol 2 Ch 1 — Institutional Eligibility (academic engagement definition) | ~52k |
| `federal-register-2025-01-03-final-rules` | Federal Register 89 FR 31031 (2025-01-03) — Distance Ed + R2T4 final rules (effective 2026-07-01) | ~258k |

The manifest at [`sources/title_iv/_manifest.json`](sources/title_iv/_manifest.json) records each source's URL + fetched_at + content sha256 — auditable provenance.

### When to re-run `update_title_iv_snapshot.py`

| Trigger | Why |
|---|---|
| The "next review" date stamp above passes | Annual sanity check |
| DOE issues new R2T4 / distance-ed guidance | Material rule change |
| A new FSA Handbook year is published (typically summer) | The 2026-2027 Vol 5 Ch 1 will exist around July 2026 |
| The audit produces unexpected classifications | Maybe the rules changed; verify against current sources |

The script reports **NEW / UNCHANGED / UPDATED / SUSPICIOUS** per source on each run. UNCHANGED means content is byte-identical to the last cached version (sha256 match); no token cost.

### What to do if a source is SUSPICIOUS

- Means: fetched response was suspiciously short (under 5000 chars); usually an anti-scraping shell or a moved-page redirect
- The script keeps the prior good snapshot + logs the failed attempt in the manifest
- Manual review: open the URL in a browser, confirm it still resolves, update `_SOURCES` in the script if the URL moved

---

## 6 — Faculty workflow (end-to-end)

```bash
# 1. (Optional) refresh the Title IV sources if it's been a while
uv run python lib/tools/update_title_iv_snapshot.py

# 2. Run the audit with the faculty's institutional UF cutoff date
uv run python lib/tools/course_engagement_audit.py \
  --uf-date 2026-04-15 \
  --passing-score 60.0

# 3. Open the report from ~/Downloads/
#    The console output names the path; no names hit the terminal.
```

The agent recognizes natural-language prompts for step 2 (canvas_grader spec language):
- *"Run a UW check on this course"*
- *"Last participation report"*
- *"Engagement audit for term end"*
- *"Which students are at Title IV risk?"*

All of these invoke `course_engagement_audit.py`.

---

## 7 — Anti-patterns (what this tool will NOT do)

1. **It will NOT use `last_activity_at`** from the enrollment record. That field includes page views and login times; not Title IV-compliant.
2. **It will NOT report the R2T4 calculation itself.** That's the financial aid office's job (their software has the disbursement amounts; this tool doesn't). The audit surfaces the **candidates**.
3. **It will NOT write the named report inside the repo.** Hard refusal with a pointer to FERPA tier 3.
4. **It will NOT print names to the console.** Counts per classification only.
5. **It will NOT silently use stale Title IV rules.** The date stamp at the top of this file + the snapshot manifest are the freshness signals; re-verify per the cadence in §5.

---

## Quick-reference: the audit in one paragraph

The audit fetches active student enrollments + their assignment/quiz submissions + their discussion entries via the Canvas API, computes each student's `last_engagement` as the max timestamp across those (page views deliberately excluded per Title IV), classifies each student against the operator's UF cutoff date into `ACTIVE / UW / UF / NEVER_PARTICIPATED` (per 34 CFR 668.22 + 2025-2026 FSA Handbook), re-identifies user_ids → names ONLY at the last step before writing the report, and drops the named MD + PDF report in `~/Downloads/` so the LLM never has filesystem access to the named output. Title IV definitions verified 2026-06-26; cached snapshots of the 6 canonical sources in `sources/title_iv/`; re-verify annually or whenever DOE issues new guidance.

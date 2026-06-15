# Upgrading canvas-toolbox

For early adopters running an older version (v0.35.x and earlier). This
is the migration guide; for the mechanical per-version diff, see
[`CHANGELOG.md`](CHANGELOG.md).

Usage is still small enough (a handful of consumer repos as of
2026-06-15) that we can be specific about what changed and how to
handle it. This file gets shorter over time as adopters catch up.

---

## What version am I on?

Any grader tool's `--version` reports the toolkit version:

```bash
uv run python canvas-toolbox/lib/tools/grader_fetch.py --version
# → canvas-toolbox 0.35.4
```

The current latest is **v0.50.1**.

---

## Quick upgrade (most common case)

If you cloned canvas-toolbox as a sibling directory inside your course
repo (the recommended layout for m119 / ds460 / ds250 / itm327 /
aol-student style adopters):

```bash
cd canvas-toolbox
git pull
uv sync                              # picks up any new deps
uv run python lib/tools/grader_fetch.py --version
# → canvas-toolbox 0.50.1
```

That's it for the upgrade itself. Read the "Behavior changes worth
knowing" section below before your next run.

---

## Behavior changes worth knowing (v0.35 → v0.50)

These are operator-visible changes that might surprise a workflow you
already have. None require code changes on your side, but you may want
to know they exist.

### `grader_push` got safer — and louder

If you ran `grader_push --push` on a workflow that included Test
Student or inactive enrollments, **the new default excludes them**
(issue #61). You'll see them listed in an "excluded by default" block
before the plan prints, and they won't appear in the pushable rows.
If your prior workflow intentionally pushed grades to Test Student
or to inactive enrollments, pass `--include-inactive`.

Two new guardrails fire BEFORE the push happens:

- **Pre-push comment-collision guard** (#62) — warns if recent non-self
  comments exist on a submission's thread. Operator types `collisions`
  to acknowledge. Pass `--allow-collisions` to skip the interactive
  step.
- **Availability-aware warnings** (#63) — if the assignment is locked
  AND a pushable comment contains "resubmit"-style language, warns
  before the push gate. Operator types `locked` to acknowledge. Pass
  `--allow-locked-resubmit` to skip.

Both are FYI-then-confirm rather than block-by-default. The push still
proceeds if you confirm.

### `grader_push --retract` is new (#63)

Made the wrong call on a comment push? `grader_push --retract` (with
optional `--retract-keys K1,K2`) DELETEs previously-pushed comments
via the per-assignment ledger that's now automatically written on
every push. Same dry-run-by-default + canvas_course_guard + confirmation
discipline as the forward push.

### `grader_reconcile` has a new column (#59)

If you consume the keyed actuals CSV from `grader_reconcile`, it now
has an extra `<dim>_complete` column alongside the existing
`<dim>_sum` / `<dim>_submitted` / `<dim>_missing`. Driven by a new
optional `completion_basis` config key per dimension
(`submitted` / `nonzero` / `full_credit`). Default `submitted`
preserves legacy behavior.

### Deid adapters refuse re-runs that conflict (#54-D)

If you re-run `grader_deidentify_*` on a `submissions_raw/` that
previously went through a DIFFERENT adapter (or the same adapter with
a renamed challenge dir), the second run now refuses with
exit-code 3 + a clear "stale prefix files exist" message. Pass
`--cleanup-legacy` to remove the stale files automatically.

### Single-surface vs multi-surface task layout (#54-E)

Codified in `grading_readme.md`. Single-surface tasks use
`grading/<task>_<surface>/`. Multi-surface tasks use
`grading/<task>_combined/<surface>/`. The new `grader_scaffold.py`
(#54-A) auto-picks based on how many assignment ids you pass; the
downstream `grader_join` (#54-B) and `grader_meta_summary` (#54-C)
auto-detect both layouts.

**No migration required** if your existing layout already follows
either convention. The fallback discovery in `grader_meta_summary`
handles m119-style task-level feedback dirs too.

---

## What's actually new (the new tools you might want)

These shipped between v0.35.4 and v0.50.0. The order below is roughly
"most likely to be useful first".

| Tool | What it does | When to reach for it |
|---|---|---|
| `cb_report_bug.py` | One-command bug/enhancement reporter; no GitHub account needed | When something deviates from documented behavior, or you want the toolkit to grow a feature it doesn't have |
| `grader_config_audit.py` | Resolves every `assignment_id` in a reconcile/competency config against the live course; flags wrong IDs | Before EVERY first grading run on a new assignment config — catches the silent "DS=0 with full DS credit" bug |
| `grader_list_assignments.py` | Lists Canvas assignments for a course | Whenever you're about to run `grader_fetch.py --assignment-id <N>` and don't know N |
| `grader_pull_ta_grades.py` | Symmetric PULL counterpart to `grader_grade.py` | Calibration cohorts where you want to compare grader band vs. TA's pass/fail |
| `grader_submission_health.py` | Flags submissions that look broken-not-absent (empty/wrong-type upload) | Before any grading run — catches the "1 task completed → F" failure mode from a technical upload issue |
| `grader_competency_grade.py` | Config-driven "highest tier where all thresholds met" engine | Mid-term + end-of-term letter grade computation |
| `grader_push_comments.py` | Pushes staged `## Suggested Canvas Comment` blocks from per-student feedback files | When you've got 30+ student comments to post and don't want to copy-paste |
| `grader_scaffold.py` | Sets up the canonical task layout from a Canvas assignment id | First-time setup for a new task / new cohort |
| `grader_join.py` | Builds the FERPA-safe `_userid_key_grade_join.json` for multi-surface tasks | When you need uid → KEYs across surfaces (AI Log + Cohesive) + TA grades |
| `grader_meta_summary.py` | Cross-task uid × task matrix + flag-streak | When you've got 4+ task cohorts and want to see patterns |
| `grader_deidentify_comments.py` | FERPA de-id layer for Canvas comment threads | If your workflow ever needs to READ comments (audit, retract, collision-check) — never read submission_comments directly |

---

## The bug-intake CLI is the official feedback channel now

When something doesn't work right, or you wish the toolkit did something
it doesn't:

```bash
uv run python canvas-toolbox/lib/tools/cb_report_bug.py
```

No GitHub account needed. Title prefix `bug:` or `enhancement:`. The CLI
scrubs PII locally before posting. See
[`AGENTS.md → Continuous improvement`](AGENTS.md#continuous-improvement--bugs--enhancements)
for the full DO / DO-NOT calibration if you're an agent operating in
this repo.

---

## For agents

When you're working in a consumer repo and notice `canvas-toolbox`
isn't at the latest version, surface this file:

> _The toolkit at `canvas-toolbox/` is at v{X}.{Y}.{Z}; latest is
> v0.50.1. The upgrade is a `cd canvas-toolbox && git pull && uv sync`.
> Behavior changes worth knowing in `canvas-toolbox/UPDATE.md`._

The toolkit doesn't auto-upgrade — that's by design (operator control).
But agents can and should notice the gap.

---

## Older upgrade paths

If you're on something older than v0.30, contact the maintainer before
upgrading — the layout convention shifted around the v0.30 → v0.35
window and you may need a one-time data move. Most adopters are
already at v0.35+; this section exists for anyone who's been pinning
to a very old release.

# Upgrading canvas-toolbox

The migration guide — what changes about your *workflow*. For the
mechanical per-version diff, see [`CHANGELOG.md`](../CHANGELOG.md).

---

## What version am I on?

Any grader tool's `--version` reports the toolkit version:

```bash
uv run python canvas-toolbox/lib/tools/grader_fetch.py --version
# → canvas-toolbox 1.13.0
```

The current latest is **v1.20.0**.

---

## Quick upgrade (most common case)

If you cloned canvas-toolbox as a sibling directory inside your course
repo (the recommended layout for m119 / ds460 / ds250 / itm327 /
aol-student style adopters):

```bash
cd canvas-toolbox && git pull && uv sync
cd .. && uv run python canvas-toolbox/lib/tools/cb_update.py          # dry run
uv run python canvas-toolbox/lib/tools/cb_update.py --apply
```

`cb_update` is the re-init step: it makes new toolkit standards active
in a repo that was set up months ago. **It is dry-run by default** —
run it without `--apply` first and read what it says it will do.

---

## Behavior changes worth knowing (v1.13 → v1.20)

Three of these change what happens when you run something you already
run. None require code changes, but two can stop you mid-workflow if
they surprise you.

### `cb_update --apply` now installs a hook that can BLOCK a push (1.19.0)

The biggest change. `grade_guardian` protects the *agent* layer and
cannot see `git push` — and unlike a bad read, a push can't be undone.
`cb_update` now installs `.git/hooks/pre-push`, which checks the commit
**range** (history is what gets published; deleting a file later doesn't
unpublish it) and refuses a push carrying FERPA Zone-2 files or a
credential.

If it fires, the message tells you what to do in order, and **leads with
the fix that doesn't rewrite history** — branch fresh from a clean tree
and push that. The one thing not to do is `--no-verify`; that publishes
the data.

It installs to `.git/hooks/pre-push`, **not** via `core.hooksPath` —
that setting is consulted *instead of* `.git/hooks/`, so it would
silently disable an existing `pre-commit` hook (and `pre-commit install`
then refuses to run). If you already have your own `pre-push`, yours is
left alone and `cb_update` reports `skip-foreign`.

Path checks run by default. Content scanning (uid→name maps, roster
surnames) is opt-in via `touch .claude/ferpa_scan_content`, because
surname matching trips on ordinary prose.

### `cb_update --apply` may move your Canvas token (1.20.0)

Canvas now expires API tokens every 29 days. If you run **more than one
course repo**, `cb_update` consolidates the token into
`~/.canvas/config` (chmod 600) and **comments out** — not deletes — the
`CANVAS_API_TOKEN` line in that repo's `.env`. Rotation becomes one edit
instead of one per repo.

- **Single-course operators are untouched.** Detection is by sibling
  repos and fails safe toward "single"; `--multi-course` forces it.
- **Course ids never move.** `~/.canvas/config` accepts only
  `CANVAS_API_TOKEN` and `CANVAS_BASE_URL`. A `CANVAS_COURSE_ID` there
  is ignored and reported — a global course id would silently send
  writes to whichever course was configured last.
- Precedence is unchanged: environment variable → repo `.env` → global.
  A real per-repo token still wins; an empty one doesn't count.
- `cb_update` now verifies the token with one read-only call and reports
  `valid` / `REJECTED` / `unreachable`. `--no-token-check` skips it.

**If it says `REJECTED`, check first whether the token needs *accepting*
in Canvas → Account → Settings.** A user-generated token is listed as
active the entire time it doesn't work, so this looks exactly like an
expired token. It cost the maintainer twenty minutes.

### Agents can no longer `cat` your `.env` (1.20.0)

`grade_guardian` now denies raw display of credential files — including
the `python -c "...read_text()"` form, which is how it actually happens.
`Read .env` still works (blocking it would also block `Edit`), as do
`.env.example`, `.envrc`, and `grep -o '^[A-Z_]*=' .env` for key names.
`~/.canvas/config` is blocked outright; nothing legitimate reads it.

### Your course-owned skills become visible to git (1.14.1, 1.15.1)

`cb_update` used to write a blanket `.claude/skills/` ignore, which also
hid skills *you* wrote there. It now ignores the toolkit's skills by
name and migrates the old line. After upgrading, a course-owned skill
that was silently untracked will start showing in `git status` — that's
the fix, not a regression. If you added `.gitignore` negations as a
workaround, they're now redundant and harmless.

### `.deid_master.csv` gained an `org_id` column (1.17.0)

The institution's id — Canvas `sis_user_id`, D2L `OrgDefinedId`. It is
**stored, never a key**. Appended last, and readers use `csv.DictReader`,
so a master written before 1.17.0 still parses; no rebuild needed.

### Student names in agent output (1.15.0, 1.18.0)

Agents now refer to students by `user_id` / `deid_code` in anything
written *about* a student, and by given name + last initial in text
written *for* one (a discussion reply). A name never appears beside a
score, criterion, or standing. If an agent starts declining to use a
name you just typed, that's over-application — the rule scopes to what
the agent surfaces on its own, not what you supplied in the same turn.

### Not on Canvas? (1.16.0, 1.17.0)

Courses on another LMS can now use the toolkit's constitution, skills,
FERPA discipline and consensus grading without the Canvas API:
`.claude/ferpa_zone2.txt` teaches `grade_guardian` your own name-bearing
files, and `build_deid_master.py --roster-json` builds the de-id master
from a local roster with no credentials.

---

## Older behavior changes (v0.35 → v0.50)

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

## Tools added in the v0.35 → v0.50 window

Still current and still worth knowing if you skipped that window — but
these are no longer the newest additions. The order below is roughly
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
[`AGENTS.md → Continuous improvement`](../AGENTS.md#continuous-improvement--bugs--enhancements)
for the full DO / DO-NOT calibration if you're an agent operating in
this repo.

---

## For agents

When you're working in a consumer repo and notice `canvas-toolbox`
isn't at the latest version, surface this file:

> _The toolkit at `canvas-toolbox/` is at v{X}.{Y}.{Z}; latest is
> v1.20.x. The upgrade is `cd canvas-toolbox && git pull && uv sync`,
> then `cb_update.py` (dry-run) and `--apply`. Behavior changes worth
> knowing in `canvas-toolbox/docs/UPGRADING.md` — from 1.19 onward
> `--apply` installs a pre-push hook and may move the Canvas token._

The toolkit doesn't auto-upgrade — that's by design (operator control).
But agents can and should notice the gap.

**Run `cb_update` without `--apply` first and show the operator the
output.** From 1.19 it installs a hook that can block a push, and from
1.20 it can rewrite `.env` and write to `$HOME`. All of that is correct
and wanted — but it's the operator's call to see it before it happens.

---

## Older upgrade paths

If you're on something older than v0.30, contact the maintainer before
upgrading — the layout convention shifted around the v0.30 → v0.35
window and you may need a one-time data move. Most adopters are
already at v0.35+; this section exists for anyone who's been pinning
to a very old release.

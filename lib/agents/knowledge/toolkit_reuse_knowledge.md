---
name: toolkit_reuse_knowledge
version: '1.0'
last_updated: '2026-07-27'
description: Consume the vendored canvas-toolbox tools; do not reimplement them. The canonical custom-script → vendored-tool migration map, the tool-discovery rule that stops parallel toolchains forming, and how the grade_guardian hook makes it enforceable.
skill_type: knowledge
shape: reference
scope: 'Why course repos accumulate parallel custom scripts (the toolkit was generalized FROM them), why that drift is dangerous (it bypasses the safety hardening), the tool-discovery rule, the known custom→vendored migration map, and the migration procedure. Out of scope: the internals of any specific tool (see that tool''s --help/docstring) and the grading protocol itself (grader_knowledge / the HG-5 pointer).'
consumed_by:
- cb_init.py (course AGENTS.md stub points here)
provenance:
  sources:
    - '2026-07-27 usage scan of itm327-master + ds460-master (mature consumer repos)'
    - 'issue #213 (tool-bypass RCA) + the grade_guardian hook (v1.7.15)'
metadata: { knowledge_id: toolkit_reuse }
---

# Use the vendored tools — don't reimplement them

**Consumed by:** the course-repo AGENTS.md stub (via `cb-init`). Read this before writing
any script that talks to Canvas from a course repo.

## The core rule

> **Before implementing ANY Canvas operation, search `canvas-toolbox/lib/tools/` first.
> If a tool exists, use it. If one doesn't, propose it — never hand-write a Canvas API
> script.** Grades reach Canvas ONLY through a sanctioned writer under `lib/tools/`:
> `grader_push.py` for submission feedback (comments + grades), and
> `grader_standing.py` for a roster-keyed **standing** column — an instructor-computed,
> value-only "your grade" No-Submission assignment you refresh weekly (#242). Both share
> one auth/course-guard/post-policy core, so they can't drift on what matters.

## Why this file exists (the drift trap)

Many of the toolkit's tools were **generalized *from* course-repo scripts** — e.g.
`grader_signals.py` says *"GENERALIZED FROM ds460-master/grading/checks.py"*, and
`grader_push.py`'s HOLD-token pattern (#72) was *"lifted from itm327's
build_mid_letter_comments + push_mid_letter."* So the pattern is predictable: a course
builds a script → the toolkit absorbs and hardens it → the course keeps running its
**old local copy**. Now there are two implementations, and the local one:

- **misses every safety fix** the vendored tool has gained. The field bugs that bit real
  courses — 4 comments stacked on one student, empty comments pushed silently
  (#228), grades stuck at `workflow_state: submitted` (#226), autonomous un-reviewed
  pushes (HG-5) — **all came from custom push scripts**, and are all fixed in the
  vendored `grader_push.py`.
- **drifts** from the maintained version and has to be re-fixed by hand each time.
- **bypasses the `grade_guardian` hook** — the harness-level guard (#213, v1.7.15) that
  blocks direct Canvas writes and the *creation* of a bypass script. A custom script
  only escapes it because the hook isn't installed; see "Make it enforceable" below.

## The migration map (custom → vendored)

Known duplications observed in the mature repos. **Verify each against the vendored
tool's `--help` / docstring before switching** (names match; confirm the behavior fits),
then retire the local copy and repoint your AGENTS.md at the vendored path.

| Custom script (in a course repo) | → vendored `canvas-toolbox/lib/tools/…` |
|---|---|
| `grading/push_grades.py` | `grader_push.py` |
| `grading/push_your_grade.py`, `grading/update_standing.py` (writes a "your grade" column) | `grader_standing.py` — computes nothing; pushes your script's values, dry-run by default |
| `grading/final_letter/fix_push.py`, `push_final_grades.py` (final-letter grade + End-Letter comment) | **split the write:** `grader_standing.py` for the value (Course Grade) + `grader_letter_comments.py` for the instructor comment (End Letter). Keep `calc_final_grades.py` (course-specific computation); retire the direct writer. |
| `grading/checks.py` | `grader_signals.py` |
| `grading/consensus.py` | `grader_consensus.py` |
| `grading/reidentify.py` | `grader_reidentify.py` |
| `grading/deidentify_*.py` | `grader_deidentify_*.py` |
| `grading/check_name_leak.py` | `grader_name_leak_check.py` |
| `grading/reconcile_gradebook.py` | `grader_reconcile.py` |
| `…/fix_canvas_grade_state.py` | `grader_audit_workflow.py` (#226: stuck-`workflow_state` `--check`/`--fix`) |
| `…/add_ai_tag.py` | *(delete)* — `grader_push.py` appends a provenance tag automatically; pick the honest one with `--disclosure {ai,hybrid,script}` (or `$CANVAS_DISCLOSURE_DEFAULT`): `ai` = AI drafted grade+comment, `hybrid` = script graded / AI drafted the comment, `script` = script graded / no AI |
| `tools/canvas_sync.py` | `canvas_sync.py` |
| `tools/blueprint_sync.py` | `blueprint_sync.py` |
| `tools/course_mirror.py` | `course_mirror.py` |
| `tools/module_settings_sync.py` | `module_settings_sync.py` |
| `tools/module_structure_diff.py` | `module_structure_diff.py` |
| `tools/course_quality_check.py` | `course_quality_check.py` |
| `tools/canvas_pages.py` · `tools/canvas_quiz_questions.py` | same-named vendored tools |

**When a custom script is legitimate:** it does something the toolkit doesn't (and
shouldn't) cover — course-specific content (lab/video injectors, PDF splitters), bespoke
final-grade math, one-off DAG scaffolding. Keep those local; and if a local tool is
*reusable* across courses, upstream it (`cb_report_bug.py --title "enhancement: …"`)
rather than letting every course carry its own copy.

## The migration procedure

1. `cd <course>/canvas-toolbox && git pull` — get the current tool.
2. `uv run python canvas-toolbox/lib/tools/<vendored>.py --help` — confirm it covers your use.
3. Retire the local copy (deprecate with a pointer comment, then archive/delete).
4. Repoint every AGENTS.md / docs invocation from `tools/<x>.py` → `canvas-toolbox/lib/tools/<x>.py`.
5. Make it enforceable (below).

## Make it enforceable — the `grade_guardian` hook

A deprecation *comment* doesn't stop an agent from running the old script. The hook does.
Install it once per course repo:

```bash
uv run python canvas-toolbox/lib/tools/cb_init.py --yes   # step 14 wires the hook
```

After that, a direct Canvas grade write — or the creation of a script that would do one —
is **blocked at the harness and redirected to `grader_push.py`.** Structural, not advisory.
Verify: `grep grade_guardian .claude/settings.json`.

## The one-line summary

The toolkit was built by absorbing course scripts and hardening them. Consuming the
vendored tool is how you get that hardening for free; keeping the local copy is how you
keep re-living the bugs it already fixed.

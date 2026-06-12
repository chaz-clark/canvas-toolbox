---
title: Doc drift on multi-commit feature sweeps — the agent spec lagged the code by 3 commits
date: 2026-06-11
operator: Chaz Clark
producer: Claude in canvas-toolbox
trigger: After 6 commits across 2 days extending the grader pipeline, operator
  asked "are the proper agents and readme files updated so they know when and
  why to use each one?" — the answer was no for `canvas_grader.md`.
relevance: Hermes (sprint coordinator) and any future multi-commit feature work
---

# What happened

Between 2026-06-10 and 2026-06-11, the grader pipeline shipped:

| Commit | Code change | Did I update `canvas_grader.md`? |
|---|---|---|
| `9ea8692` | `grader_fetch.py` (FERPA Step 0 with roster pre-fetch + auto-chain) + `grader_prep_answer_key.py` + `grader_consensus.py` `_all_comments.md` extension + `scaffold/grading/.gitignore` | ❌ No |
| `7d07fcb` | `_env_loader.py` + 12 tools converted | ❌ Not applicable (no agent-facing behavior change) |
| `ebc4be3` | `grader_deidentify_text.py` + `grader_deidentify_pdf.py` + `grader_deidentify_xlsx.py` + auto-detect chain expanded | ❌ No |
| `f7a3bc0` | `grader_deidentify_jupyter.py` + `grader_fetch.py` discussion-topic branch + `grader_fetch.py` quiz branch + coverage matrix in `grading_readme.md` | ❌ No |

`grading_readme.md` (faculty-facing) WAS updated each time. `canvas_grader.md`
(agent-facing) was not. By the end of the sweep, the agent spec read as
Phase 3c era: it listed the de-id adapters generically as "`lib/tools/
grader_deidentify_*.py` — one per format" but didn't enumerate them, didn't
know about `grader_fetch.py`'s submission_type branching, and didn't mention
the auto-chain that's now the default behavior. The operator surfaced the
gap on the 5th commit of the day with one direct question. The fix took
~30 minutes — but the gap had existed for 3 commits before that.

# The smell

The fix is cheap; the drift was costly. An operator-in-the-loop or
agent-in-the-loop reading `canvas_grader.md` mid-sweep would have:

- Tried to run the pipeline using only `grader_deidentify_databricks.py` /
  `grader_deidentify_docx.py` (the two adapters explicitly named in the
  spec at that time), missing the four newer adapters
- Manually invoked each pipeline step instead of using the new
  `grader_fetch.py` auto-chain (which is now the default)
- Not known that discussion-topic and online_quiz assignments have
  their own branches inside `grader_fetch.py`

None of these would be wrong per se, but each is the OLD path. The agent
spec defaulted to the obsolete instructions silently.

# What should have happened

Every code commit that **changes agent-visible behavior** should be paired
with a docs update in the SAME commit. Concretely, the trigger for
"agent-visible behavior" is:

1. **A new tool ships** in `lib/tools/` that the agent would invoke
2. **An existing tool's CLI surface changes** (new flag, new default,
   new auto-detect behavior)
3. **A pipeline order changes** (steps add, remove, or rearrange)
4. **A new convention lands** (a new folder, a new file name pattern,
   a new gitignore rule)

For each, the docs to update are:

- `lib/agents/canvas_grader.md` (or the relevant agent spec) — the
  Existing Tooling table + the Pipeline run order + any §-by-§ behavior
  change
- `lib/agents/knowledge/<topic>_knowledge.md` if the change touches
  reasoning, not just mechanics
- The faculty-facing `grading_readme.md` (or equivalent) for any new
  CLI flag, new convention, or new submission-type support

This is not new policy — it's just the policy I forgot to follow during
a 6-commit sweep.

# Why this is a Hermes-class lesson

Hermes is the sprint coordinator. A "feature sweep" by definition has
multiple commits, and each commit risks updating only PART of the surface
area. The natural failure mode is exactly what happened here: the code
ships, the faculty-facing README gets updated because it's where the
"what to do" lives, but the agent-facing spec gets forgotten because it's
two levels of abstraction away ("I'm shipping code; the agent reads docs;
docs read each other; somewhere this gets covered").

A Hermes check at end-of-sprint (or end-of-each-commit) could be:

> "Did this commit add/modify a tool in `lib/tools/`?
>  → Did `lib/agents/canvas_grader.md` (or the relevant agent spec)
>     change in the same commit?
>  → If no, surface a warning before push: 'Agent spec may be stale.
>     Review `<spec>.md` for adapter roster + pipeline order references.'"

Lower-friction version (the diff-driven one):

> Before the close of any commit that touches `lib/tools/grader_*.py` or
> `lib/tools/canvas_*.py`, grep the agent spec(s) for references to
> tools in the same family. If any tool in `lib/tools/grader_*.py`
> changes or is added but the agent spec's "Existing Tooling" table
> doesn't list it, flag the gap.

# The fix this time

Updated `canvas_grader.md` (Existing Tooling table + Pipeline run order
+ submission_type branching note), `grader_setup_knowledge.md` §1 (input
format → adapter routing), and `grader_knowledge.md` (FERPA two-zone
section now references `grader_fetch.py`'s auto-chain + roster pre-fetch).
Committed in `<commit hash TBD>`.

# Generalizable principle

**Tools and agent docs are a single source of truth, split across two
files.** If the code says "use adapter X" and the doc doesn't mention
adapter X, the agent will reach for the named-but-stale option in the
doc — not the unnamed-but-current option in the code. Code wins
eventually, but only after the agent makes a mistake or the operator
catches the gap.

The fix is one of:

1. **Co-commit policy** — code change + agent doc change land in the
   same commit. Easy enough when remembered; easy to forget mid-sweep.
2. **Pre-commit grep** — Hermes (or a pre-commit hook) greps the agent
   spec for the tool's old reference; if missing, asks the operator to
   add it. Catches forgetfulness.
3. **Single-source-of-truth generation** — agent docs are generated
   from tool docstrings / argparse help. Larger refactor, but
   eliminates the class of error entirely. Probably overkill for
   canvas-toolbox's current size; worth revisiting at v1.x scale.

For now, **(1) + (2) is the right combination**. Co-commit when I
remember; let Hermes catch when I forget.

# Cohesive Narrative — Rubric (canonical 5-criterion template)

**Canvas grading:** instructor configures the scale + banding. The template
below assumes a **Meets / Developing / Does Not Yet Meet** holistic band
on five canonical criteria; adapt names + descriptors to your course's
specifics.

This template closes part F of canvas-toolbox#54 (umbrella). For SP26
m119 worked from project specs directly — no canonical template existed.
This captures the criteria-set that surfaced from that real run.

## The five canonical criteria

| # | Criterion | What "Meets" looks like |
|---|-----------|--------------------------|
| 1 | **Project task complete** | The narrative addresses every required deliverable of the assignment (no skipped sub-parts, no off-topic substitution). |
| 2 | **Cohesive analysis** | The narrative reads as ONE story across all sub-tasks. Conclusions link back to the framing question; transitions between sections are explicit. Not a stitched-together set of independent answers. |
| 3 | **Reproducible work** | The analysis is reproducible from the submission. Data sources, parameter choices, seed values, and any sampling decisions are stated explicitly. A reader could re-run the work from what's in the submission. |
| 4 | **Correct calculations** | Numerical results are right. Where uncertainty exists (e.g. monte-carlo, fitting), the band of acceptable answers is stated and the result falls in it. Wrong answers don't pass on style alone. |
| 5 | **Mathematical notation** | Notation is consistent with the course's conventions. Equations, units, and symbols match the assigned style guide. (Drop this row if your course doesn't grade notation.) |

## Holistic banding (not additive)

Score against the named band as a single judgment — NOT a per-criterion
arithmetic. Consistent with `grader_knowledge.md` §2 (holistic, not
additive).

- **Meets** — all five criteria at or near "Meets" descriptors. Some unevenness across criteria is fine if the narrative still functions as a cohesive analysis.
- **Developing** — clear effort, but one or more criteria show consistent gaps. Specific revisions would close them.
- **Does Not Yet Meet** — substantial work still needed on the dominant criterion(s) that block the analysis from holding together.

The grader's job is to name the band and cite the criterion that drove
the call. Don't try to assign sub-points per criterion.

## Per-student file shape (template)

```markdown
# COHESIVE Feedback — <KEY>
**Score: <Meets | Developing | Does Not Yet Meet>**  (criterion that drove the call: <name>)

## Evidence for the score

**Per-criterion summary:**
- 1. Project task complete:  <Meets / Developing / DNYM> — <1-line evidence>
- 2. Cohesive analysis:      <...>
- 3. Reproducible work:      <...>
- 4. Correct calculations:   <...>
- 5. Mathematical notation:  <...>

**Quotes / specific anchors from the submission:**
- <specific line / section / value the grader cited>

## Suggested Canvas Comment (rubric-grounded)

> <one-paragraph comment grounded in the criterion that drove the band
>  call. Avoid feeding back data values per
>  grader_voice_knowledge.md.>
```

## Notes for the instructor

- Remove criteria you don't grade (e.g. drop "Mathematical notation" for
  prose-heavy courses). The toolkit treats the criteria list as opaque
  strings — fewer rows is fine.
- For courses that need a 4-point scale instead of a 3-band, replace
  "Meets / Developing / Does Not Yet Meet" with your scale; the holistic
  approach still applies.
- If your course pairs a Cohesive Narrative with an AI Log, both surfaces
  go under the same `<task>_combined/` directory (canonical layout, per
  #54 sub-A scaffolder).

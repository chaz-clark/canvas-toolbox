# Course Design Workflow — Redesign or Build From Scratch

A step-by-step walkthrough an agent (or instructor) follows to **design a course backward
from outcomes**, in two flavors:

- **Flow A — Redesign** an existing Canvas course you already teach.
- **Flow B — Architect** a brand-new course from a blank page.

Both flows share the same backbone: **CLOs → assessments → modules → rubrics → workload**,
each step grounded in a specific knowledge file and (where one exists) a deterministic audit
tool. The only difference is where you start: Flow A starts by *auditing what's there*; Flow B
starts by *stating the course's purpose*.

> **Ground every step in the knowledge base — don't free-style.** Before each step below, read
> the named file(s) under [`lib/agents/knowledge/`](../lib/agents/knowledge/README.md) and follow
> that file's guidance. Cite which files you used so the instructor can verify the work is
> grounded in the toolkit's cited frameworks, not the model's generic training. This is the
> rule in [`AGENTS.md`](../AGENTS.md) → Working Style.

---

## The backbone (shared by both flows)

| Step | Read this knowledge file | Run this tool | Gate |
|---|---|---|---|
| 1. Outcomes (CLOs) | `outcomes_quality_knowledge.md` | `clo_quality_audit.py` | CLOs pass the AoL 6-criteria before anything aligns to them |
| 2. Assessments | `assessments_knowledge.md` + `backwards_design_knowledge.md` | — (design step) | Every assessment names a CLO; formative + summative both present |
| 3. Modules | `merrill_first_principles_knowledge.md` + `hattie_3phase_knowledge.md` | `learning_model_audit.py` | Task-centered spine; Surface→Deep→Transfer; ≤7 items/module |
| 4. Rubrics | `rubrics_knowledge.md` | `rubric_coverage_audit.py`, `rubric_quality_audit.py`, `rubric_recommender.py` | Criteria trace to CLOs; behavioral levels; CLO-weighted |
| 5. Workload | `workload_calibration_knowledge.md` | `workload_audit.py` | Distribution balanced (no crunch / back-loading) |
| (cross-cutting) | `syllabus_knowledge.md`, `course_design_standards_knowledge.md` | `syllabus_audit.py`, `course_audit.py` | Syllabus complete; standards covered |

Why this order: *if the outcome isn't well-formed, alignment to it is meaningless* — so CLOs come
first, and each later step aligns backward to them (Wiggins/McTighe Understanding by Design).

---

## Flow A — Redesign an existing course

### A0. Baseline audit (start here)

**First, validate the audit baseline** (prevents stale/wrong-course errors):

Check for `.canvas/audit/<course_id>.json`:
- **If absent** → run the audit (step below)
- **If course_id mismatch** → **ERROR** (never redesign course X using course Y's audit)
- **If run_at > 30 days** → **WARN** "audit is stale, consider re-running"
- **If valid** → use structured findings to inform decisions

This artifact enables **progress tracking across iterations**: compare `missing_rubrics: 32 → 22 → 12`
as you improve the course over 1-3 semesters. See [`docs/proposals/audit-artifact-progress-tracking.md`](../docs/proposals/audit-artifact-progress-tracking.md).

**Run the read-only health check** to see what you're fixing before changing anything:

```bash
uv run python lib/tools/course_audit.py --course-id <id> --full --report audit.md
```

This writes both `audit.md` (human-readable) and `.canvas/audit/<course_id>.json` (machine-readable
artifact for progress tracking).

Read the verdict (`HEALTHY` / `REVIEW` / `NEEDS_ATTENTION`) and the per-area findings (rubric
coverage, rubric quality, syllabus, CLO quality, workload). This is your evidence base.

### A1. Choose the redesign scope
Decide how radical the change is — this fork changes everything downstream:

| Scope | When | What it touches |
|---|---|---|
| **Refine, then realign** | CLOs already pass; the gaps are structural (missing rubrics, back-loaded) | Keep CLOs; rebuild assessments → workload |
| **Re-derive the CLOs first** | CLOs have rigor-spread or kind-coverage gaps | Reconsider the outcome set, then work outward (bigger blast radius) |
| **Full blank-page rebuild** | The course is fundamentally mis-scoped | Switch to Flow B, using the old course as loose reference |

Surface the trade-offs and let the instructor choose — don't assume.

### A2–A6. Work the backbone
Walk steps 1–5 of the backbone above. Two redesign-specific notes:
- **CLO step:** `clo_quality_audit.py` is heuristic — it can mis-count a rubric-criterion line as a
  CLO. Read `outcomes_quality_knowledge.md`'s **Process-vs-Outcome anti-pattern** and verify each
  discovered "CLO" describes *student achievement*, not a scoring instrument.
- **Assessment step:** the most common redesign win is collapsing many scattered graded assignments
  into **one culminating performance task + a formative spine** (Merrill: don't leave the only whole
  task for the final week).

### A7. Confirm the fix
After building changes (locally first — see Gates), re-run `course_audit.py --full` and confirm the
findings close (e.g., rubric coverage complete, `workload` now `balanced`).

---

## Flow B — Architect a new course from scratch

No existing course to audit, so you start from purpose instead of evidence.

### B0. State the course's purpose
Capture, from the instructor: the **subject**, the **level** (intro / intermediate / advanced),
**credits + length** (drives the workload budget), and a one-sentence **mission** (Wiggins's
"what's the point of your course?"). Level is the highest-leverage input — it calibrates the Bloom
rigor of every CLO you're about to write.

### B1. Derive the CLOs
Read `outcomes_quality_knowledge.md`. Draft 3–6 CLOs in the form *"The student will be able to
[observable verb] [content]"*, with:
- a **Bloom spread** appropriate to the level (intro centers on Remember/Understand/Apply + one
  stretch; advanced centers on Analyze/Evaluate/Create),
- coverage across the **5 kinds** of outcomes (Knowledge, Skills, **Character & Values**,
  Experiences, Learning-to-Learn) — the Character/Values kind is the most-skipped.

### B2–B5. Work the backbone
Walk steps 2–5 exactly as in Flow A. Design assessments backward from the CLOs (UbD Stage 2:
*think like an assessor before designing lessons*), sequence modules task-centered toward a
culminating performance task, draft one analytic rubric per summative, and lay out a balanced
calendar within the Carnegie budget (`credits × ~3` hrs/week).

### B6. Stand it up
Write the artifacts into a local `course/` working folder (your review surface), not straight to
Canvas. Build the rubric scaffold with `rubric_recommender.py`. Push to Canvas only on explicit
approval.

---

## Where the two flows differ

| | Flow A — Redesign | Flow B — From scratch |
|---|---|---|
| **Start** | Baseline audit (`course_audit.py --full`) | Course purpose + level interview |
| **CLOs** | Refine or re-derive existing | Derive fresh from purpose |
| **Evidence base** | The audit findings | The instructor's intent |
| **Risk** | Disrupting a live/enrolled course | Scope creep / blank-page paralysis |
| **First gate** | "What does the audit say is broken?" | "What's the one-sentence mission?" |

Everything from the assessment step onward is **identical** — both converge on the same backbone.

---

## Safety gates (both flows)

These come from [`AGENTS.md`](../AGENTS.md) → Working Style and apply throughout:

1. **Local files are source of truth.** Write CLOs, modules, and rubrics into a local `course/`
   working folder first. Canvas is the push *target*, never edited blind.
2. **Sandbox-first for writes.** Validate any write tool (e.g. `rubric_recommender.py --apply`)
   against `CANVAS_SANDBOX_ID` before touching a real course.
3. **Confirm scope before any write.** Master, blueprint, and section courses have different IDs;
   a mis-scoped push replicates to the wrong place.
4. **Re-audit after any push.** Run `course_audit.py --full` to confirm the change landed and
   closed the finding it was meant to.
5. **The human is the author.** Outcomes, assessments, and rubric language are drafted *for the
   instructor's approval* — surfaced, never silently pushed.

---

## Tools referenced

| Tool | Role |
|---|---|
| [`course_audit.py`](../lib/tools/course_audit.py) | Read-only health check; the Flow-A starting point and the after-the-fact verifier |
| [`clo_quality_audit.py`](../lib/tools/clo_quality_audit.py) | Scores CLOs against the AoL rubric |
| [`rubric_coverage_audit.py`](../lib/tools/rubric_coverage_audit.py) | Finds assignments missing rubrics |
| [`rubric_quality_audit.py`](../lib/tools/rubric_quality_audit.py) | Scores rubrics against the 4-criterion backbone |
| [`rubric_recommender.py`](../lib/tools/rubric_recommender.py) | Generates rubric scaffolds from a course's CLOs (write-capable; sandbox-first) |
| [`learning_model_audit.py`](../lib/tools/learning_model_audit.py) | Checks module sequence against Merrill / Hattie / Kolb presets |
| [`workload_audit.py`](../lib/tools/workload_audit.py) | Flags clustering / front- or back-loading |
| [`syllabus_audit.py`](../lib/tools/syllabus_audit.py) | Scores syllabus completeness |

For the full framework catalog and routing table, see
[`lib/agents/knowledge/README.md`](../lib/agents/knowledge/README.md).

---
name: canvas-toolbox-working-style
version: "1.0"
last_updated: 2026-07-12
description: Detailed working-style guidelines for canvas-toolbox — project-specific rules with the motivating cases behind each (bullet summaries live in AGENTS.md).
skill_type: knowledge
shape: identity
scope: "Project-specific working-style rules for canvas-toolbox agents, with the motivating cases behind each. Quick-reference summaries live in AGENTS.md."
consumed_by:
  - AGENTS.md
companion_json_deprecated: "2026-07-16 - authored as YAML frontmatter (JSON purge convention)"
runtime_strategy: read_at_runtime
metadata:
  knowledge_id: canvas-toolbox-working-style
  repo: canvas-toolbox
---

# Canvas Toolbox Working Style (Detailed)

This file contains the **detailed explanations and motivating cases** for project-specific working style rules. The bullet-point summaries live in `AGENTS.md` for quick reference.

---

## 1. Local files are source of truth

**Rule**: Canvas is the sync target, not the source. Never treat Canvas as authoritative unless `--pull` was just run.

**Why**: The toolkit mirrors Canvas to local files, edits locally, then pushes. Treating Canvas as source creates drift between local and remote state.

**Application**: Always work from local files (`course/`, `grading/`, etc.). Only query Canvas when explicitly pulling fresh state.

---

## 2. Ground pedagogical work in the knowledge base — don't free-style it

**Rule**: Before any course design, redesign, audit, or outcome/assessment/rubric work, read [`lib/agents/knowledge/README.md`](README.md) and follow its routing table to the relevant knowledge file(s) **first**, then pull them in the documented order.

**Why**: The toolkit encodes 8 instructional-design frameworks (Cognitive Load, Hattie 3-Phase, Three Domains, BYUI Taxonomy Explorer, Experiential Learning, Designer Thinking, Course Design Language, Toyota A3). Generic LLM training doesn't capture these frameworks accurately.

**Application**:
- User asks: *"architect a redesign — start with the CLOs"*
- Agent reads: `README.md` → routes to `clo_quality_framework.md` + `three_domains_framework.md`
- Agent cites: "Using Three Domains framework (Anderson et al., 2001) from knowledge/three_domains_framework.md"

**Evidence requirement**: Cite which knowledge files you used so the operator can verify grounding.

**Motivating case**: Early course audits (pre-v0.30) free-styled CLO quality judgments based on generic Bloom's taxonomy. Faculty rejected results as "not aligned with our pedagogy." Framework grounding requirement added v0.32.

---

## 3. Validate audit baseline before redesign workflows

**Rule**: Before starting a redesign (Flow A in [`docs/course-design-workflow.md`](../../../docs/course-design-workflow.md)), check `.canvas/audit/<course_id>.json` for a recent audit artifact:
1. Verify `course_id` matches target course (never redesign course X using course Y's audit)
2. Warn if `run_at` > 30 days (semester-scale staleness)
3. If absent/stale, run `course_audit.py` first

**Why**: The audit artifact enables **progress tracking across iterations** — compare findings semester-over-semester (`missing_rubrics: 32 → 22 → 12`) to validate iterative improvements.

**See**: [`docs/proposals/audit-artifact-progress-tracking.md`](../../../docs/proposals/audit-artifact-progress-tracking.md) for rationale.

**Motivating case**: 2026-05-15, agent redesigned ITM-327 course using stale DS250 audit artifact (wrong course_id). Recommended dropping modules that didn't exist in ITM-327. Course-id validation added to prevent cross-course audit contamination.

---

## 4. Canvas IDs are course-specific

**Rule**: Match content across courses by title, never by ID. The same assignment has different IDs in master, blueprint, and every section.

**Why**: Canvas assigns new IDs when content is copied/synced between courses. An assignment with ID 123 in master might be 456 in blueprint and 789 in section S1.

**Application**: `canvas_sync.py` matches by `title` + `content_type`, not by `canvas_id`.

**Failure mode**: Attempting to update assignment 123 in blueprint when it's actually 456 → 404 error or wrong-assignment update.

---

## 5. Adding content requires two steps: course + module

**Rule**: Creating an assignment, quiz, or page is not enough — it must also be added as a module item, or students cannot find it.

**Why**: Canvas doesn't auto-add new content to modules. Students navigate via modules, not via Assignments index page.

**Application**: After `POST /courses/{id}/assignments`, must also `POST /courses/{id}/modules/{module_id}/items`.

**Failure mode**: "I created the assignment but students say it doesn't exist" → it exists in Canvas but not in any module.

---

## 6. Confirm scope before any write

**Rule**: Master, blueprint, and sections are different courses with different IDs. A push scoped wrong replicates to the wrong course.

**Why**: Multi-course mode (master → blueprint → sections) has 4+ courses. Pushing to wrong course propagates errors broadly.

**Application**: Tools verify `MASTER_COURSE_ID`, `BLUEPRINT_COURSE_ID`, `S1_COURSE_ID` before any write. Prompt user to confirm scope.

**Motivating case**: 2026-04-12, agent pushed master content to S1 (live course) instead of blueprint. Overwrote instructor's section-specific edits. Scope confirmation prompts added v0.45.

---

## 7. `request_confirmation()` must return `approved=true` before any Canvas write

**Rule**: Audit agents enforce this; honor it manually too.

**Why**: FERPA gate + destructive-operation gate. Prevents accidental writes to live courses or exposure of student data.

**Application**: Any Canvas POST/PUT/PATCH/DELETE must be preceded by user confirmation.

**Failure mode**: Agent pushes grades without confirmation → PII surfaces in logs/errors.

---

## 8. Run `course_quality_check.py` after every push

**Rule**: Post-push validation surfaces orphaned items, duplicates, and dates outside the course window.

**Why**: Canvas sync can create orphans (content exists but not in modules), duplicates (title collisions), or invalid dates (assignment due before course starts).

**Application**: After `canvas_sync.py --push`, run `course_quality_check.py --course-id <id>`.

**Motivating case**: 2026-05-08, blueprint sync created duplicate "Week 1 Overview" pages (Canvas auto-suffixed `-2`). Students saw both; unclear which to read. Quality check now catches duplicates.

---

## 9. Completion requirements enable the prerequisite chain

**Rule**: Sequential sprint locks silently fail if any item lacks `must_submit` (assignments, quizzes), `must_contribute` (discussions), or `must_view` (pages, tools, URLs). This is the `chain-complete` policy `module_settings_sync.py` applies by default.

**Why**: Canvas module prerequisites check if prior module is "complete." Completeness requires ALL items have completion requirements. Missing one requirement breaks the chain.

**Application**: `module_settings_sync.py` sets completion requirements on all items automatically.

**Failure mode**: Module 2 locked by "complete Module 1 first." Student completed all assignments but Module 2 won't unlock → one Page in Module 1 had no `must_view` requirement.

**Motivating case**: 2026-04-18, DS250 students reported Module 3 wouldn't unlock despite completing all Module 2 work. Root cause: one ExternalUrl had no completion requirement. `chain-complete` policy added to prevent recurrence.

---

## 10. Keep institutional and course-specific facts out of committed files

**Rule**: This toolkit is institution-agnostic by design. Course IDs, semester data, instructor names, institutional vocabulary that isn't already neutralized (e.g., "BYUI" outside the institution-specific `byui_course_design/` template-set), and any per-course working state belong in `.env`, in `pre_knowledge/` (gitignored), or in per-course downstream repos that subtree-pull this toolkit — never in `AGENTS.md`, `README.md`, or other committed top-level files.

**Why**: The toolkit is used by multiple institutions. Hardcoding BYUI-specific content breaks adoption elsewhere.

**Application**: Course IDs → `.env`. Instructor names → gitignored files. Institutional frameworks → `byui_course_design/` subdirectory (clearly labeled).

**Motivating case**: 2026-03-22, potential adopter (community college in Oregon) cloned repo and found BYUI semester dates, course codes, and references to "Brother Hathaway" in AGENTS.md. Perceived as "BYUI-only tool." Institution-agnostic cleanup sprint (v0.38) removed all hardcoded institutional references.

---

## 11. Sandbox-first testing: validate new or changed tools against a sandbox course before handing them off

**Rule**: Before a new/changed tool is committed for a downstream repo or person to test (e.g., a course repo that subtree-pulls this toolkit), exercise it first against a write-safe sandbox course (`CANVAS_SANDBOX_ID` in `.env`) on the real Canvas API — not just unit tests and `--help`/argparse smoke.

**Why**: Real-API failures should be caught in-house, not by downstream testers.

**Application**: If the change needs specific conditions to exercise (e.g., rubrics of various shapes for the rubric audit tools), **create those scenarios in the sandbox** — it's write-safe and built for exactly this.

**Motivating case**: 2026-05-21, the rubric audit tools were handed to a downstream course repo with no live-API run here first; they hit a blocking `CANVAS_BASE_URL` scheme bug on the first invocation — a defect a 30-second sandbox run would have caught.

---

## 12. Surface-before-apply (P-002) applies to every state-changing action

**Rule**: Between *"I understand the issue"* and the first `Edit` / `Bash` commit / `gh issue close`, propose the fix and wait for explicit go.

**Why**: **GitHub-issue triage is in scope.** A one-word reply on a *summary* is ambiguous — *"continue"* / *"yes"* / *"ok"* can mean *"continue the conversation, what's the plan?"* or *"go execute."*

**Explicit go triggers** (honored without re-surfacing):
- *"go"*
- *"yes apply"*
- *"flow approved"*
- *"fix and ship"*
- *"I trust the call here"*

**No smallness loophole**: A one-line `replace_all` and a 200-line refactor both need surfacing.

**Motivating case**: 2026-06-01, issue #38 fix bypassed surfacing because the agent inferred go from a *"continue"* that was meant as continue-the-conversation. See [`learned/2026-06-01_surface-before-apply-on-issue-triage.md`](learned/2026-06-01_surface-before-apply-on-issue-triage.md) for the failure-mode write-up.

---

## 13. `git push` after every commit

**Rule**: In BOTH consumer repos AND canvas-toolbox itself. A commit that isn't pushed isn't a backup; it can be lost to disk failure, mistaken `reset --hard`, or just forgotten across a session boundary.

**Why**: **Local-only commits are a smell.** The goal is `git log --branches --not --remotes` showing zero commits at all times.

**Application**: Use `git add ... && git commit -m "..." && git push` as the single operation; if `git push` is omitted, the next session inherits unpushed work.

**Motivating cases**:
- (a) 2026-06-17, itm327-master had 23 local-only commits ahead of origin spanning ~3 weeks of canvas-toolbox-prompted work (issue #88)
- (b) 2026-06-18, canvas-toolbox itself had 6 local-only commits when an adopter cloned from GitHub and found `cb_init.py` missing — the v0.54.0 work was complete locally but invisible to the world

**Rule applies to**: Maintainers, not just adopters.

---

## 14. Placeholder names in code comments, commit messages, and prose docs must be visibly fake

**Rule**: In any prose context (code comments, commit messages, AGENTS.md entries, learned-lessons docs, parking-lot entries), the first appearance of a placeholder name **gets the explicit "fake" annotation** — `"Sarah" (fake name)` — and subsequent appearances in the same artifact stay in quotes: `"Sarah"`.

**Why**: The annotation is an **active FERPA-discipline signal** so any reader (auditor, IRB, future contributor) immediately knows the name is not real.

**Exception**: Inside test FIXTURES (literal grading-comment strings), names stay un-quoted because the tests assert against the literal shape; instead, the test file's top docstring documents the convention.

**Naming convention**: Common first names ("Sarah", "Alex", "Maria") chosen for readability remain fine — the discipline is to make their placeholder-status VISIBLE, not to invent obscure tokens.

**Motivating case**: 2026-06-22 (v0.57.1 → v0.57.2), the FERPA-fix commit for #94 used "Sarah" throughout as a placeholder (the reporter had been more careful, using `<Name>`). Operator caught the inconsistency: "we shipped a FERPA fix; did we ourselves follow FERPA discipline in the artifacts?" — answer: not visibly enough. The annotation pattern was adopted to over-communicate the discipline rather than rely on context for it.

---

## 15. Deterministic-first grader design — bias toward Python; reach for the LLM where contextual judgment or voice-anchored prose is the better fit

**Rule**: It's a tuning preference, not a hard rule.

**Why**: Many rubric criteria (output matching, structural checks, function-signature presence, count thresholds, completion-basis ratios, file-presence) are cleanly deterministic — `regex` / `Levenshtein` / `AST parse` / a counter + a threshold.

**LLM strength**: Contextual judgment on prose where a rule can't reach (was the reflection coherent? did they engage with the prompt?), and writing voice-anchored student-facing comments.

**The messy middle**: "is the code well-organized?" / "did the analysis go deep enough?" / "is the voice appropriate?" — criteria that LOOK rule-friendly but resist clean regex, OR look LLM-only but have deterministic shadows (length checks, structural-flatness heuristics) that approximate the judgment cheaply.

**The principle**: Prefer Python when the criterion is cleanly deterministic; prefer the LLM when contextual judgment is genuinely required; in the messy middle, **the rubric author / instructor decides** based on pedagogical intent, available time, and what fits THEIR rubric (sometimes a deterministic prefilter + LLM-on-what-passes is the right hybrid).

**Migration is fine**: A criterion may start as LLM (cheap proof-of-concept) and harden to deterministic later when patterns emerge; or start deterministic and escalate to LLM when the rule misses cases.

**Current pipeline**: The grader pipeline today already follows the preference for parts of the work:
- `grader_signals.py` extracts signals deterministically
- `grader_reconcile.py` counts via `completion_basis`
- `grader_competency_grade.py` applies tier thresholds rule-based

**Discipline**: ASK the question at design time, not to assume the LLM is the default.

**Why it matters**: Deterministic checks are free (no token cost), reproducible, auditable, and FERPA-safe by default. The LLM's cost / drift / pedagogical-risk concentrate on the (smaller) judgment-required portion.

**Motivating case**: 2026-06-22 design conversation on a potential v1.2 auto-grade-on-cycle feature — original framing assumed the LLM grades everything per submission; operator's reframe ("use deterministic where you can; LLM for context and comments") collapsed token cost + drift + safety concerns substantially, BUT the operator also flagged the messy middle so the principle is "tuned toward Python first" — not a hard binary. See `grader_knowledge.md` §16 + the v1.2 parking-lot entry for the full nuance.

---

## HERMES Refresh Cycle (Canvas-Toolbox Specific)

**Active development phase** (current state, beta/sprint cadence):
- Review this file every 20 sessions
- Move sections with <2 reads in 20 sessions → long-term-parking.md
- Faster rotation than stable repos due to rapid iteration

**Hardened/stable phase** (future state, post-v2.0):
- Review every 50 sessions (standard HERMES cycle)
- Move sections with <3 reads in 50 sessions → long-term-parking.md

**Current stats** (as of 2026-07-12):
- Working Style accessed: ~8 times per 20 sessions (keep)
- Deterministic-first grader: ~2 times per 20 sessions (keep, actively iterating)
- FERPA placeholder names: ~1 time per 20 sessions (keep, safety-critical)

All sections currently above threshold for active development phase.

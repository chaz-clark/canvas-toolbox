---
title: The AI Coding Loop
description: How to build software with coding agents without vibe coding — align first, small tickets, feedback loops, review by merge danger, retro
sources:
  - https://www.youtube.com/watch?v=mU8WKII1gpk
  - https://github.com/mattpocock/skills
  - https://www.aihero.dev/skills
last_updated: 2026-11-22
---

# The AI Coding Loop

> "AI is great at tactical programming and terrible at strategic programming." The strategic part (what to build, where the seams go, how the design holds up) is the human's job.
> — Matt Pocock, on NetworkChuck's "How to Actually Code with AI" (2026-11-20)

This file condenses that video and Matt Pocock's public skills into the loop this toolkit follows. The skills themselves are MIT-licensed and installable as a Claude Code plugin (`mattpocock-skills`), and as skills for Codex, Copilot, Gemini and other agents (see the repo's README). This file is the tool-agnostic summary. Use it whether or not the skills are installed.

**Source caveat:** written from the video's description and chapters plus the skills' own documentation, not a full transcript.

---

## Vibe coding vs. the loop

**Vibe coding** means typing "build this" and accepting what comes back. It works for tactical code and wrecks the design over time. Agents speed up coding, so they also speed up software entropy.

**The loop** keeps the human on the strategic decisions and gives the agent tight feedback on the tactical ones:

```
grill → spec → tickets → implement (test-first) → review → retro
```

| Step | What happens | Matt's skill |
|---|---|---|
| **Grill** | The agent interviews you, one round of questions at a time, until you share one understanding. It answers anything the codebase can answer by reading the code, not by asking you. Agreed terms go into a glossary. | `grill-with-docs` (`grill-me` outside a repo) |
| **Spec** | The conversation becomes a written spec. No new questions are asked: the spec only records decisions already made, including what is out of scope. | `to-spec` |
| **Tickets** | The spec splits into **tracer bullets**, thin slices through every layer that can each be demoed on their own. Each states what blocks it, and each fits one fresh context window. | `to-tickets` |
| **Implement** | Builds one ticket test-first (red → green → refactor) and never reopens the plan. | `implement`, `tdd` |
| **Review** | Two independent reviewers (see below). | `code-review` |
| **Retro** | Looks back at where the agent struggled and proposes a check, pointer or standard so it can't recur. | `retro` |

For a hard bug: `diagnosing-bugs` (build a loop that goes red on this bug → minimize → hypothesize → instrument → fix → regression test).

---

## Ideas worth keeping

**1. Align before a line is written.** The most common failure is misalignment: the agent built something, but not what you meant. A grilling session costs minutes and prevents rework. (This toolkit already does a version of it: clickable choices with a recommended option, before building.)

**2. The smart zone and the dumb zone.** An agent is sharpest early in a context window and degrades as it fills. Write the spec first, size tickets to fit one fresh context, and hand each ticket to a fresh session rather than one session that has been summarized again and again.

**3. Review by merge danger, not line by line.** Every PR states:
- **Door:** a **two-way door** is cheap to reverse. A **one-way door** is not: a destructive migration, a published release, a write to a live system, a message sent, a public API removal.
- **Blast radius:** what could break if the change is wrong.

Skim a two-way door with a small blast radius, and read a one-way door slowly. Be most suspicious of the agent's own "two-way, small" call, because the author is grading itself.

**4. Two-question review.** Two reviewers in separate, fresh contexts, so neither sees the other's reasoning or the author's assumptions:
- **Standards:** is it built the way this repo builds things? Each finding cites a documented rule, or a named code smell from Fowler's *Refactoring* (as a judgement call).
- **Spec:** is it the right thing? Each finding quotes the spec line it fails: missing requirements, scope creep.

Report the two separately, with no blended verdict, so a pass on one axis can't hide a fail on the other. Findings are leads, not evidence: check each against the files, act on the cited ones, then stop. It never comes back clean, so don't loop until it does.

**5. The trust ladder.** You can trust an agent's output as far as its feedback loops reach: types, automated tests, a real browser or app, real data. "The rate of feedback is your speed limit." Without feedback the agent is flying blind.

**6. Deep modules.** A lot of behavior behind a small interface, placed at a clean seam and tested through that interface (Ousterhout, *A Philosophy of Software Design*). Agents navigate and change deep modules safely. A ball of mud defeats them. Survey the codebase for deepening opportunities every few days (`improve-codebase-architecture`). That survey suggests candidates; it doesn't rescue the codebase.

**7. A shared language.** A glossary of the project's own words, agreed once, so the agent says "the materialization cascade" instead of a paragraph. It also makes naming in the code consistent.

**8. Care.** Matt's recurring word. The tools don't replace caring about the design.

---

## How it maps to this toolkit

| The loop | Already here | Where |
|---|---|---|
| Grill | Clickable choices with a recommendation; "state assumptions, ask before acting" | AGENTS.md → Working style; `behavioral_discipline.md` (P-001, P-010) |
| Tickets | Short-lived branches, one reviewable unit per PR | `trunk-based-development.md` |
| Test-first, trust ladder | Jidoka: tests with the code; Genchi Gembutsu: verify with real data, a real sandbox | AGENTS.md → Toyota Quality Loop |
| Retro: repeat mistakes become checks | Poka-yoke: every defect gets an automated guard (`grade_guardian`, pre-push, static checks) | AGENTS.md → Toyota Quality Loop |
| Merge danger | One-way doors already gated: Canvas writes need an approval pop-up, releases need an explicit go | AGENTS.md → Canvas writes |

What the loop adds on top: the **merge-danger line** in every PR, the **two-question review** on anything that isn't a small two-way door, **fresh context per ticket**, and a regular **architecture survey**.

Retro's measure of success applies to this repo too: repeat mistakes turn into failing checks, and AGENTS.md gets shorter over time, not longer.

---

## How it runs in this repo

In the toolkit repo, the skills are set up in `.github/CONTRIBUTING.md` → *Agent skills*, which points them to `docs/agents/` (issue tracker: GitHub; the five default triage labels; domain docs: the glossary and `docs/architecture/adr-*.md`). Those files are in the toolkit repo only; they don't ship to course folders. Each step, in order, with the skill and the practice it serves:

| Step | Skill | What it serves here |
|---|---|---|
| 1. Align | `grill-with-docs` | Nemawashi (P-002 Plan Before Acting). Settled terms go into `knowledge/glossary.md` in the same session. |
| 2. Spec | `to-spec` | A GitHub issue holding the user story and every decision already made, including what is out of scope. |
| 3. Tickets | `to-tickets` | Heijunka and small steps (P-005): tracer-bullet issues, each with its blockers, each fitting one fresh session. |
| 4. Build | `tdd` (and `implement` for a whole ticket) | Jidoka: the failing test comes first, and a red test blocks progress. |
| 5. Verify | (no skill) | Genchi Gembutsu: run it on real course data or the sandbox before calling it done. |
| 6. Review | `code-review` | The two-question review (Standards, Spec) for anything but a small two-way door. |
| 7. PR | `pr` | The PR body: user story, merge danger, test plan. |
| 8. Retro | `retro` | HERMES and Poka-yoke: a friction hit twice becomes a lesson in `lib/agents/knowledge/learned/`, and a repeat mistake becomes a check. |

**Every few days:** `improve-codebase-architecture` surveys for deep-module candidates. It produces candidates, not changes.

**A hard bug:** `diagnosing-bugs`.

**Decisions:** a choice that is hard to reverse, surprising without context, and a real trade-off becomes the next `docs/architecture/adr-NNN-<slug>.md` in the toolkit repo, often during step 1.

The public-repo rule holds at every step: specs, tickets and PRs on this repo never identify a student or describe private work elsewhere.

---

## Recommended reading (from the video)

- John Ousterhout, *A Philosophy of Software Design*: deep modules
- Eric Evans, *Domain-Driven Design*: a shared language
- Michael Feathers, *Working Effectively with Legacy Code*: seams, and getting old code under test

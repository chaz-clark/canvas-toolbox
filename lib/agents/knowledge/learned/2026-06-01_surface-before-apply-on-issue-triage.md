---
name: surface-before-apply-on-issue-triage
description: A failure mode where the agent treated a one-word reply on a GitHub issue summary as approval to fix → commit → push → close, bypassing P-002 (Plan Before Acting). The rule exists upstream; the failure was operational. Concrete behavioral fix below.
version: "0.1"
author: chaz-clark
license: MIT
metadata:
  repo: canvas-toolbox
  surfaced: "2026-06-01 — issue #38 fix bypassed surface-before-apply"
  binds-to: behavioral_discipline P-002; AGENTS.md Sprint F Rule 3
---

# Surface-before-apply applies to GitHub-issue triage too

## What happened

Issue #38 (`course_quality_check` end_at guard) came in. Sequence:

1. Operator: *"we have a new issue in GH."*
2. Agent: polled `gh issue list`, showed the issue body.
3. Operator: *"continue."*
4. Agent: jumped straight to `Read` → `Edit` → `Bash` (commit + push) → `gh issue close`, all in a single assistant message.

The fix itself was correct (it matched the reporter's suggested patch and verified on all four input shapes). **The process violated P-002** — push-to-main and issue-close are non-reversible, and they happened without a surfaced plan or an explicit go.

## Why it happened (three layers)

1. **No precondition gate.** Between *"read the issue"* and the first `Edit` call, the agent did not pause to check *"does this need surfacing?"*. The apply-side tool calls fired reflexively in the same message as the read.

2. **"Continue" resolved in the cheap direction.** A one-word reply on a *summary* is genuinely ambiguous between **(A)** *continue the conversation, what's the plan?* and **(B)** *continue the flow, go execute.* The agent picked (B) for momentum. The right move was to ask — a two-second clarifying question costs nothing; a wrong-direction inference cost a wrong-process commit landing on `origin/main`.

3. **Implicit smallness loophole.** The fix was tiny (one-line `replace_all`, reporter even pasted the patch, risk essentially zero). The agent unconsciously downgraded the rule's bindingness because the *artifact* risk was low. **P-002 has no smallness exception** — small fixes are *exactly* where the discipline slips, which is why the rule isn't size-gated.

## Operational fix (binding going forward)

- **Insert an explicit "proposed fix" assistant message between *read-issue* and the first apply-side tool call.** That message **is** the gate. If no explicit go follows, do not proceed to Edit / Bash-commit / gh-close.
- **One-word replies on a summary are ambiguous.** Clarify, don't infer. Replies like *"continue,"* *"yes,"* *"ok"* after a *summary* (not a *proposal*) → ask: *"should I go ahead with [the proposed fix], or did you want to see the plan first?"*
- **No smallness loophole.** A one-line `replace_all` and a 200-line refactor both need surfacing before apply.
- **Explicit approval triggers** (honored without re-surfacing): *"go,"* *"yes apply,"* *"flow approved,"* *"fix and ship,"* *"I trust the call here."* Anything else after a summary → clarify.

## The underlying principle

Between "I understand the issue" and "I make the first edit," there must be a **rule-check checkpoint**. The check is structural, not vibe-based: did I surface a proposal? did the user explicitly approve? Either answer "no" means stop and surface.

## Promotion check

Per Sprint B's promotion rule: if this file is referenced a second time (or this failure mode recurs in `canvas-toolbox`), promote to `lib/agents/knowledge/` as a first-class agent norm. If the same failure mode appears in **another** chaz-clark repo (e.g., a downstream course mirror's own session), elevate via a cross-repo handoff to `make-AGENTS` as a documented Pitfall in `make_AGENTS.md` — that's the universal-trap path.

---
name: improve
description: Use to log, prioritize, move, or review COURSE IMPROVEMENTS — the local kanban backlog in the course's `IMPROVEMENTS.md`. Load whenever an audit surfaces findings, the user notes something to fix / try / revisit, a handoff lands action items, or you're asked "what's on the board / what's next / show the backlog / log this". Each improvement is a card that moves Backlog → Ready → In Progress → In Review → Done. This is CONTINUOUS IMPROVEMENT (kaizen) for the course — NOT continuous integration / CI pipelines / GitHub Actions.
---

# Improve — the course continuous-improvement board

Every course accumulates "should fix / should try" items — from audits, from teaching
a term, from the instructor noticing something. Left in chat or one-off letters, they're
lost by the next session. This skill keeps them in **one local, git-tracked kanban
board** so improvements are tracked to *done*, not rediscovered every term.

## The board

**`IMPROVEMENTS.md` at the course root.** Git-tracked (travels with the repo), plain
markdown (the instructor can edit it directly), no external service. If it doesn't
exist yet, copy `IMPROVEMENTS.template.md` from this skill to create it — confirm with
the instructor the first time.

## The one rule

**When an improvement is found — by an audit, by the instructor, by a handoff — it
becomes a card on the board. When it's worked, it moves through the columns. Nothing
that matters gets left only in chat.**

## Columns (the lifecycle)

`🗄 Backlog` (unordered ideas) → `🔴 Ready` (prioritized; top = next) →
`🟡 In Progress` (being worked) → `🔵 In Review` (done but unverified — awaiting the
instructor) → `✅ Done` (verified, linked to the PR/commit that closed it).

## Card schema

One line per card, compact:

```
- **[C-###] Short title** — src: <audit YYYY-MM-DD | user | handoff | session> · size <S/M/L> · risk <low/med/high> · <link when it moves>
```

- **id** `C-###` — stable, monotonic; never reused. Assign the next free number.
- **src** — where it came from + date, so provenance survives.
- **size / risk** — rough, for ordering. No story points.
- **link** — the PR/commit/handoff, added as the card moves to In Review / Done.

## How to work it (lightweight agile — solo-instructor scale)

- **Log**: new find → a `Backlog` card (or straight to `Ready` if it's clearly next).
  Audits write their findings here **as cards**, not as a separate lost letter.
- **Prioritize**: order `Ready` so the **top is the next thing** to pull. Tag size/risk.
- **Pull, don't push**: start work by pulling the top of `Ready` into `In Progress`.
  **WIP limit: keep `In Progress` small (≈2).** Finish before starting.
- **Review gate**: work lands in `In Review`, not `Done`, until the instructor has
  seen/verified it. Nothing self-marks Done.
- **Close**: move to `Done` with the PR/commit link and the date. Keep Done as the
  record (prune only when it's long).
- **Age**: flag a card that's sat in `In Progress`/`In Review` too long — surface it.

## Phrases that load this

"log this / add to the board", "what's on the board / show the backlog", "what's next /
what should I work on", "move C-012 to in progress / done", "prioritize the board",
"turn the audit into cards".

## Where it plugs in

- **`audit`** — an audit's output is a set of `IMPROVEMENTS.md` cards (with `src: audit
  <date>`), so findings are tracked to closure instead of filed and forgotten.
- **Handoffs** — a received handoff's action items become cards.
- The board is course context (no student PII) — **Zone-1**, safe to read and commit.

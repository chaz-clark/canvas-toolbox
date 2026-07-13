# Canvas access boundary — keeping an AI agent away from Canvas

**Opt-in.** If you keep `CANVAS_API_TOKEN` in `.env` and drive the toolkit with a single
agent, nothing here applies and nothing changes for you.

---

## The problem this solves

Universities are formalizing AI policy faster than they can evaluate vendors. A common
first position: **"no AI tool touches our LMS until we've reviewed it."** That is
reasonable. It is also, today, incompatible with this toolkit.

The toolkit assumes **one agent does everything.** The same agent that reasons about
course design also runs `canvas_sync.py --pull`, which authenticates to Canvas with the
instructor's token. There is no seam between *thinking about the course* and *calling the
Canvas API*.

So an instructor whose institution hasn't approved their AI tool for Canvas faces an
all-or-nothing choice: abandon the toolkit, or violate the policy.

## The insight

**Nothing at the Canvas boundary needs intelligence.**

- Pulling a course is: fetch JSON, write files.
- Auditing it is: read files, apply rules, write a report.
- Pushing is: read files, POST.

That's deterministic work — and the toolkit's tools are already ordinary Python scripts.
The only reason an AI agent was ever at the network boundary is that it happened to be the
thing typing the commands.

And here's the payoff: **the audit output is a file.** `course_audit.py` writes `audit.md`
and `.canvas/audit/<id>.json`. The mirror lands in `course/`. The agent reads those from
disk, like any other file in the repo.

**The agent never needed Canvas access.** It needed the *results* of a Canvas fetch —
which are sitting in the repository.

## The shape

| | |
|---|---|
| **`lib/tools/canvas_run.py`** | A plain CLI. No AI. The instructor runs it. The only thing that authenticates to Canvas. |
| **The AI agent** | Local files only. Holds no Canvas credential. |

```text
you     →  canvas_run.py pull       →  course/ mirror + audit.md + .canvas/audit/
agent   →  reads those files, drafts changes as local files    (no network)
you     →  canvas_run.py push --confirm-course <id>            (only when you decide to)
```

## Why not have an *approved* AI agent drive the script?

Worth addressing, because it's the first thing people try — we did:

- **Security:** it hands the Canvas token to an AI vendor and lets a language model choose
  which command to run. A script that takes `pull` and runs `pull` has strictly less attack
  surface than a model interpreting "pull the course."
- **Compliance:** it "solves" *one AI vendor isn't approved* by depending on **another** AI
  vendor's approval. You trade one vendor-review problem for a different one.
- **Simplicity:** it's a natural-language wrapper around five commands.
- **Honesty:** the memo to your IT department gets *harder* to write. Explaining why two AI
  tools are involved is worse than explaining why zero are.

The answer to *"which AI agent should hold the Canvas token?"* is **none of them.**

## How the boundary is enforced

### 1. Token isolation — the structural layer

| File | Contents | The agent |
|---|---|---|
| `.env` | `CANVAS_BASE_URL`, `CANVAS_COURSE_ID` — non-secret | reads |
| `.env.canvas` | `CANVAS_API_TOKEN`, nothing else. Gitignored. | **denied** |

This works because of two facts that were already true of the toolkit:

- every tool reads the token as `os.environ.get("CANVAS_API_TOKEN")`; and
- `python-dotenv`'s `load_dotenv()` does not override variables already in the process
  environment.

So `canvas_run.py` injects the token and every tool honors it — while a tool invoked
*outside* it finds no token in any file it loads.

**This is the property worth having.** Remove every hook, ignore every instruction in
`AGENTS.md` / `CLAUDE.md`, and the agent still cannot reach Canvas: it has no credential,
and Canvas answers `401 unauthenticated`. **Enforcement does not depend on the agent
cooperating** — which is exactly the assurance an institutional reviewer wants, because
"we told it not to" is not a control.

### 2. The script — `lib/tools/canvas_run.py`

The only process that reads `.env.canvas`. Named subcommands only:

```bash
uv run python lib/tools/canvas_run.py pull       # read-only
uv run python lib/tools/canvas_run.py status     # read-only
uv run python lib/tools/canvas_run.py audit      # read-only
uv run python lib/tools/canvas_run.py quality    # read-only
uv run python lib/tools/canvas_run.py push --confirm-course <id> --allow-enrolled   # WRITES
```

Each maps to exactly one toolkit invocation defined inside the script. The caller never
composes a `python lib/tools/...` command line, so **there is no argument-injection
surface**. Default-deny: anything unlisted is refused.

`push` requires `--confirm-course <id>` matching the target. On a live course a grading
change re-scores real student work the moment it lands — Canvas has no draft state.

**A course with enrolled students takes a second flag.** `canvas_course_guard` refuses any
write to an enrolled course unless `--allow-enrolled` is passed, so a push to a live course
needs **both** flags. Two flags, typed on purpose, for an action students see immediately.
`--allow-enrolled` is *refused* on the read-only subcommands rather than ignored — a flag
quietly accepted where it does nothing is a flag that becomes muscle memory where it does.

> This was **not** in the first draft of the gate, and its absence was not theoretical: the
> allowlist had no way to forward `--allow-enrolled`, so `push --confirm-course <id>` was
> refused by the guard **every time**. The gate shipped with no working write path at all on
> any live course. It surfaced the first time someone actually ran a push — which is the
> argument for running one.

Every decision, allow or refuse, is appended to `.canvas/canvas-run.log`.

### 2b. The launcher — `bin/Canvas.cmd` / `bin/Canvas.command`

The CLI asks an instructor to remember `--confirm-course <id> --allow-enrolled`. Faculty
who don't live in a terminal bounce off that, and the tempting "fix" is to let the AI agent
run the command for them — which hands the Canvas credential to an AI vendor and destroys
the only assurance this design offers.

So the fix goes the other way: **make it trivial for the human.** Double-click
`bin/Canvas.cmd` (Mac: `bin/Canvas.command`) — a numbered menu, no terminal, no flags.

```text
   Course:  Introduction to Data Science
   ID:      111111          https://school.instructure.com

    1.  Get the latest from Canvas       (safe - read only)
    2.  See what would change in Canvas  (safe - read only)
    3.  Check the course for problems    (safe - read only)

    4.  SEND my changes to Canvas        (students see this immediately)
```

Option 4 runs `status` **first**, shows exactly what would be overwritten, names the
course, and requires typing `SEND`. It types the two flags for you *after* asking, in
English, whether you meant it — they are not skipped, just not memorized.

It shows the course **NAME** from the local mirror, not just the id. A stale `.env` aimed
at the wrong course id is invisible to a human (`111111` vs `111112`); a wrong course name
is not. That is [L12](../lib/agents/knowledge/canvas_api_lessons_learned.md) made visible
to the person who can actually catch it.

**It changes nothing about the security model.** Every guard still lives in
`canvas_run.py`; the menu is presentation. It cannot do anything the CLI could not.

**But it is a path to Canvas, so the hook blocks it for the agent too.** Building it
briefly *opened a hole* — an agent could have reached Canvas by proxy simply by running
`Canvas.cmd`. A convenience wrapper around a gated tool is still the gated tool. That is
the standing failure mode of this whole design, and it is worth stating plainly:

> **The boundary is only as good as its enumeration of the paths to Canvas.**
> Every new convenience script is a new path. Add it to the block list in the same commit.

### 3. Block the agent, and log the refusals

`scaffold/claude/` is a worked example for Claude Code: deny rules plus a `PreToolUse` hook
that blocks Canvas-touching commands, explains what to do instead, and logs each refusal to
`.canvas/claude-canvas-block.log`.

**That log is the artifact for an institutional reviewer** — positive evidence of refusals,
rather than asking them to infer safety from an absence of records.

The matcher keys on toolkit entrypoints and the token file, deliberately **not** on the
substring "canvas" — `grep -rn 'canvas' docs/` stays allowed. A hook that fires on harmless
commands is one the operator learns to disable, and then you have neither the hook nor the
honesty.

## Setup

1. Move `CANVAS_API_TOKEN` from `.env` into `.env.canvas` (`scaffold/env.canvas.example`).
2. Gitignore `.env.canvas` **and** `.env.backup*`, then **verify before writing the
   secret**: `git check-ignore -v .env.canvas`. If it prints nothing, stop.
3. Copy `scaffold/claude/` to `.claude/` in your course repo. Claude Code loads settings at
   **session start** — restart it.
4. Verify — below.

## Verification

Not done until demonstrated. The **negative** tests are the ones that matter:

```console
$ uv run python lib/tools/canvas_sync.py --status     # as the BLOCKED agent
⚠️  canvas_course_guard: ... returned 401:
{"status":"unauthenticated","errors":[{"message":"user authorization required"}]}

$ ./bin/canvas-run.sh push                            # no confirmation
REFUSED: 'push' writes to Canvas. Re-run with --confirm-course <id> to proceed.

$ ./bin/canvas-run.sh definitely-not-allowed          # default-deny
REFUSED: 'definitely-not-allowed' is not on the allowlist. Allowed: audit, pull, push, quality, status
```

**Then run the positive path too — pull, and an actual push.** This is the step it is
tempting to skip, and skipping it is how you ship a boundary that does not work.

The first end-to-end run of this design against a live course (2026-07-13, an instructor's
course with enrolled students) found **four defects that code review and unit tests had
both missed**:

| Defect | Consequence |
|---|---|
| The gate had **no working write path** — the allowlist could not forward `--allow-enrolled`, and the enrolled-course guard refuses without it | `push --confirm-course <id>` was refused every time. The write half of the workflow had never worked |
| The hook matcher keyed on bare substrings | Reading the gate's own audit log (`cat .canvas/canvas-run.log`) was blocked as a Canvas call — as were the boundary's own unit tests, by filename |
| `canvas_sync --status` ignored the homepage, syllabus, and `_course.json` — which `--push` writes | `--status` could report *"Everything up to date"* while `--push` was poised to overwrite a **live syllabus** |
| `canvas_sync --push` printed *"Nothing to push"* while pushing | Caused a **duplicate push against the live course** during the verification itself — the operator re-ran it to be sure |

All four are fixed here. The point is not the bug list; it is that **a control you have
never exercised is a claim, not a control** — and the two that mattered most were only
visible from the far side of a real Canvas write.

## Honest limits

State these to your IT department. The credibility of everything else depends on it.

- **This is a guardrail, not a sandbox.** It's client-side. Anyone with shell access can
  bypass any client-side control — equally true of every locally-run tool an institution
  already permits.
- **What it does guarantee is narrow and verifiable:** the credential is not in any file the
  agent can read, Canvas rejects its calls with a `401`, and every attempt is logged.
- **The write confirmations are speed bumps with an audit trail, not technical
  impossibilities.** They stop accidents and drift, not a determined operator — who in any
  case already has full write access to their own course through the Canvas web UI, with no
  equivalent log. This workflow is *more* auditable than the status quo, not less. Say so.
- **If an institution wants a hard guarantee, the strongest control is theirs, not yours** —
  issue the Canvas API token scoped to the approved workflow, and rotate it. Then
  enforcement sits at the Canvas end, where nothing on a laptop can defeat it. **Offer
  this.** A reviewer who hears you volunteer the limits of your own control will trust the
  parts you do assert.
- **Test the write path on a sandbox course if you have one** (`CANVAS_SANDBOX_ID`). The
  2026-07-13 verification had to push to a live course because no sandbox was configured —
  a single character in the syllabus, reverted immediately, but briefly visible to enrolled
  students. That cost is avoidable, and you should avoid it.

## What the agent still does

Everything that was ever valuable, and none of it needs Canvas: it reads the mirror and the
audit artifact from disk, drafts rubrics and outcomes and module structure as local files,
and plans the changes you then push yourself.

**The AI does the thinking. The script does the network.**

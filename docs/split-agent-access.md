# Split-agent access — one agent for the network, another for the work

**Opt-in.** If you keep `CANVAS_API_TOKEN` in `.env` and drive the toolkit with a single
agent, nothing here applies and nothing changes for you.

---

## The problem this solves

Universities are formalizing AI policy faster than they are evaluating vendors. A common
result: **one AI vendor is approved for access to university systems, and another is
not** — often with no judgment implied about either tool, just an approval queue that
hasn't finished.

That collides with how this toolkit is built. It assumes **one agent does everything**:
the same agent that reasons about course design also runs `canvas_sync.py --pull`, which
authenticates to Canvas with the instructor's token. There is no seam between *thinking
about the course* and *calling the Canvas API*.

So an instructor whose institution permits agent A but not agent B faces an
all-or-nothing choice: abandon the tool they were using, or violate the policy.

The seam is cuttable. This is how.

## The boundary

The prohibited act is usually the **authenticated network call**, not the presence of
course content on the instructor's own machine. Split there:

| | |
|---|---|
| **The approved agent** | The only one that authenticates to Canvas. Pull, status, audit, and (gated) push. A transport layer — it doesn't reason about the course. |
| **The other agent** | Local files only. The mirror, the drafts, the plans. Never authenticates. |

> **Confirm this reading with your IT department before you build on it.** If their
> objection is broader — that Canvas-derived *data* must not reach the vendor at all,
> including content already on your laptop — then this design does **not** satisfy them.
> Better to learn that now.

## How it's enforced

### 1. Token isolation — the structural layer

| File | Contents | The blocked agent |
|---|---|---|
| `.env` | `CANVAS_BASE_URL`, `CANVAS_COURSE_ID` — non-secret | reads |
| `.env.canvas` | `CANVAS_API_TOKEN`, nothing else. Gitignored. | **denied** |

This works because of two existing facts about the toolkit:

- every tool reads the token as `os.environ.get("CANVAS_API_TOKEN")`; and
- `python-dotenv`'s `load_dotenv()` does not override variables already in the process
  environment.

So the gate exports the token and every tool honors it — while a tool invoked *outside*
the gate finds no token in any file it loads.

**This is the important part.** Remove every hook, ignore every instruction in
`CLAUDE.md`, and the blocked agent still cannot reach Canvas: it has no credential, and
Canvas answers `401 unauthenticated`. **Enforcement does not depend on the agent
cooperating.**

### 2. The gate — `lib/tools/canvas_run.py`

The only process that reads `.env.canvas`. It exposes **named subcommands**, not
arbitrary invocations:

```bash
uv run python lib/tools/canvas_run.py pull       # read-only
uv run python lib/tools/canvas_run.py status     # read-only
uv run python lib/tools/canvas_run.py audit      # read-only
uv run python lib/tools/canvas_run.py quality    # read-only
uv run python lib/tools/canvas_run.py push --confirm-course <id>   # WRITES
```

Each maps to exactly one toolkit invocation defined inside the gate. The caller never
composes a `python lib/tools/...` command line, so **there is no argument-injection
surface**. Default-deny: anything unlisted is refused.

`push` requires `--confirm-course <id>` matching the target. On a live course a grading
change re-scores real student work the moment it lands — Canvas has no draft state. An
agent must not be able to push on inference alone.

Every decision, allow or refuse, is appended to `.canvas/canvas-run.log`.

**The gate names no vendor.** It enforces "only this process holds the token." Which
agent sits on which side is local configuration — the same structure serves the opposite
institutional decision.

### 3. Restrict the blocked agent

`scaffold/claude/` has a worked example for Claude Code: deny rules plus a `PreToolUse`
hook that blocks Canvas-touching commands, explains the alternative, and logs each
refusal to `.canvas/claude-canvas-block.log`.

**That log is the artifact for an institutional reviewer** — positive evidence of
refusals, rather than asking them to infer safety from an absence of records.

The matcher deliberately keys on toolkit entrypoints and the token file, **not** on the
substring "canvas" — `grep -rn 'canvas' docs/` stays allowed. A hook that fires on
harmless commands is one the operator learns to disable.

### 4. Restrict the approved agent too

Make the split **symmetric**: the approved agent moves data, it doesn't author content.
Give it read tools plus shell access to the gate, and withhold its file-editing tools.

⚠️ **Use an allowlist, not a denylist.** If you're driving Gemini CLI, Google's own
configuration docs warn that the `excludeTools` denylist

> is based on simple string matching and can be easily bypassed. This feature is **not a
> security mechanism** … It is recommended to use `coreTools` to explicitly select
> commands that can be executed.

So restrict with `tools.core` (allowlist) and let the edit tools be excluded **by
omission**:

```json
{
  "tools": {
    "core": [
      "read_file",
      "read_many_files",
      "glob",
      "search_file_content",
      "run_shell_command(uv run python lib/tools/canvas_run.py)"
    ]
  }
}
```

The result: **neither agent can quietly absorb the other's job.** That symmetry is also
far easier to explain to a reviewer than "we promised to be careful."

## Setup

1. Move `CANVAS_API_TOKEN` from `.env` into `.env.canvas`
   (`scaffold/env.canvas.example`). Gitignore `.env.canvas` **and** `.env.backup*`.
2. **Verify the ignore rule before writing the secret:** `git check-ignore -v .env.canvas`.
   If it prints nothing, stop.
3. Copy `scaffold/claude/` to `.claude/` in your course repo.
4. Point the approved agent at the gate (allowlist above).
5. Verify — below.

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

Note that Claude Code loads `.claude/settings.json` at **session start** — restart it, or
the hook won't be live.

## Honest limits

State these to your IT department. The credibility of everything else depends on it.

- **This is a guardrail, not a sandbox.** It is client-side. A determined agent — or
  human — with shell access can bypass any client-side control. That is equally true of
  every locally-run tool an institution already permits.
- **What it does guarantee is narrow and verifiable:** the credential is not present in
  any file the blocked agent can read, Canvas rejects its calls with a 401, and every
  attempt is logged.
- **If an institution needs a hard guarantee, the strongest control is theirs, not
  yours** — issue the Canvas API token to the approved workflow only, and scope and
  rotate it. Then enforcement sits at the Canvas end, where nothing on a laptop can
  defeat it. **Offer this.** A reviewer who hears you volunteer the limits of your own
  control will trust the parts you do assert.

## A trap worth naming

If your approved agent won't authenticate, the fastest fix is often the wrong one. In our
case Gemini CLI refused a Workspace account on the free individual tier, and a personal
`GEMINI_API_KEY` was already sitting in the environment — one setting away from "working."

But an AI Studio API key is an **individual** relationship with the vendor, billed outside
the university's agreements. If IT approved *university-licensed* Gemini, an API key is
not that. The split-agent story would be quietly false while appearing to work.

**Ask for the licensed path and wait for it.** The point of this whole arrangement is to
stop being in a shadow arrangement.

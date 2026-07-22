# A3 — Deterministic enforcement of the grade-push review gate

**Owner:** grading toolkit · **Date:** 2026-07-22 · **Issues:** #207, #212, #213
**Status:** countermeasures landing across two PRs (A: harness hook · B: precheck + spec)

---

## 1. Background

AI-assisted grading is **decision support, not autonomy** — principle **HG-5**
([grader_hybrid_architecture.md](../lib/agents/knowledge/grader_hybrid_architecture.md)):
a human decides every grade that reaches a student, and every AI-drafted comment is
tagged `— AI drafted, instructor reviewed`. That tag is only *true* if review
actually happened. Three incidents say it didn't.

## 2. Current condition (the seam problem)

We have real enforcement in `grader_push.py` — the `.reviewed` marker, mtime
auto-invalidation, 3-pass consensus gate (#95), and, after #207/#214, refusal of
`--yes` on the AI-drafted push path plus disclosure-tag validation. We also have
`canvas_course_guard` as a standing write-safety bar.

**Every one of those lives *inside* a tool.** They share exactly one bypass:

```
Agent: "push grades" → writes /tmp/push_kc_grades.py → requests.put(.../submissions/...)
```

In the KC1/KC2 incident (#213) an agent did exactly this — 46 grades pushed via a
hand-written script. None of the in-tool gates ran, because the tool was never
called. `grader_knowledge.md §4` already states the principle — *"enforced at the
push seam, not by memory"* — but the seam is inside the tool, and the tool is
skippable.

## 3. Root cause (5 Whys)

1. Grades posted without review → 2. Agent used a custom API script → 3. It
pattern-matched the sprint workaround (direct-API push) to all grading → 4. Nothing
*outside* the tool stops a direct Canvas write → 5. **All enforcement is at a seam
the agent can route around by not using the tool.**

Corollary: none of the three issues proposed the mechanism that closes this.
#212 Option 2 suggested a hook that blocks `grader_push.py --push` — backwards; that
is the *safe* path. #213's fixes (precheck tool, agent instructions) all rely on the
agent *choosing* to run them — the exact failure mode.

## 4. Target condition

Grades can reach Canvas **only** through `grader_push.py`. A direct Canvas write, or
the creation of a script that would do one, is refused at a seam the model cannot
disable — and the refusal *redirects* the agent to the safe path.

## 5. Countermeasures — defense in depth across `AGENT_LAYERS.md`

No single mechanism is complete; robustness is layering mechanisms whose gaps don't
overlap.

| Layer | Mechanism | Catches | Residual gap |
|---|---|---|---|
| Spec (L3) | AGENTS.md HG-5 pointer (#214) + tool-discovery rule (#213 Fix 1/3/4, **PR B**) | cooperative agents | ignorable |
| Tool (L0) | grader_push gates (#207/#214) + `push_precheck()` internal (**PR B**) | misuse *of* the tool | not using it |
| **Harness (L1)** | **`grade_guardian.py` PreToolUse hook (PR A)** | direct API writes, bypass-script **creation**, FERPA reads | heavy obfuscation |
| Capability | Canvas token scoping / write-proxy | **all** direct writes | infra weight; **north-star, not now** |

### The hook (PR A) — [lib/tools/grade_guardian.py](../lib/tools/grade_guardian.py)

Claude Code `PreToolUse` hooks are **harness-enforced** — the model cannot disable,
edit, or prompt-inject around them; a hook `deny` beats any permission `allow`; they
fire in headless `-p` and cron. The hook receives the tool call as JSON on stdin and
exits `2` to block, with the stderr message fed back to the agent as redirection.

It denies:
- **Bash** — a write verb (`requests.put/post`, `curl -X PUT/POST`) aimed at a Canvas
  submissions endpoint / grade payload. Invoking `lib/tools/*.py` is exempt (the safe path).
- **Write/Edit** — creating/editing a file (outside `lib/tools/`, excluding `.md`
  docs) whose contents carry that signature. **This is the key catch:** a Bash hook
  can't see inside `python /tmp/push.py`, but the Write hook sees the script *as it's
  created*.
- **Read** — FERPA Zone-2 files (`.deid_master.csv`, `.keymap.json`, `submissions_raw/`,
  …), enforcing the AGENTS.md discipline deterministically (#212's parallel ask).

Wiring: `cb_init` merges a `PreToolUse` entry into the **course root**
`.claude/settings.json` pointing at the vendored hook
(`${CLAUDE_PROJECT_DIR}/canvas-toolbox/lib/tools/grade_guardian.py`) — idempotent,
non-clobbering, and auto-current on `git pull`.

## 6. Honest limits (Genchi Genbutsu)

Regex over a command / file body is **not** a semantic firewall. A determined agent
can obfuscate — `eval`, base64, variable indirection, staging the payload in a
non-`.py`/`.md` file — and slip past. The hook **decisively raises the bar against
the actual failure mode** (pattern-matching a `/tmp` push script) but does not make
bypass impossible. The only closure is the **capability layer**: give the agent a
read-scoped Canvas token and route writes through a proxy that enforces review. That
is real infrastructure (Canvas tokens inherit full user permissions, so it needs a
limited-permission API user or a mediating service) and is recorded here as the
north-star, not this sprint.

## 7. Verification

`grade_guardian.evaluate()` is a pure function with unit coverage for every deny/allow
case (curl-PUT, inline `python -c` requests, bypass-script **creation**, FERPA reads →
deny; grader_push invocation, ordinary bash, toolkit-source edits, doc examples,
non-FERPA reads → allow), plus subprocess tests that drive the real hook exactly as
Claude Code does (exit 2 + redirect; exit 0 on allowed; fail-open on garbage stdin).

## 8. Follow-up / parking lot

- **PR B** — refactor grader_push gates into `push_precheck()` (internal defense in
  depth, #213 Fix 2); fold #213 Fix 1/3/4 into the AGENTS.md protocol (tool-discovery
  rule, "never hand-write a Canvas script," sprint-exception note).
- **FERPA Bash discipline** — extend the hook to `cat`/`head`/`grep` on `.deid_master.csv`
  without the `cut` column filter (AGENTS.md already documents the safe form).
- **Capability layer** — read-scoped token + write-proxy. North-star.
- **Not doing:** #212 Option 3 (`--stage` rename — churn, no guarantee); #212's
  "N-minute freshness" (we already do stronger content-based mtime invalidation).

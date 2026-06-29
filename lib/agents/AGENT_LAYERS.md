# Agent Layers — Taxonomy and AI Engineering Per Layer

A reference document for distinguishing the three abstraction layers commonly all called "agent," and the AI engineering practices that apply at each. Useful for designing real systems and for teaching agent concepts (originally written to support a LangChain course, applied here in the canvas_toolbox repo).

---

## The Disambiguation Problem

The word **agent** is used to describe at least three distinct things in modern AI systems. Most online tutorials, Twitter threads, and product docs conflate them. Before designing or teaching, name the layer you mean.

| Layer | Common name | What it actually is | Lives in |
|---|---|---|---|
| **1. Runtime** | "LangChain agent", "ReAct agent", "AgentExecutor", "Claude Code", "Antigravity agent" | An LLM in a reasoning loop, with access to tools, choosing the next step | A running process |
| **2. Capability** | "Agent Skill", "Skill", "Tool" (loosely), "MCP server" | A packaged unit of capability the runtime can invoke | A directory you can ship |
| **3. Specification** | "Agent definition", "System prompt", "Agent spec", "Persona" | A document describing how an agent should behave when instantiated | A markdown/JSON file in your repo |

A fourth layer sometimes called "tool" or "function" sits below these — pure deterministic code with no LLM in the loop. It's the leaf that capabilities and runtimes ultimately call.

---

## The Three Layers in Detail

### Layer 1 — Runtime (the executing agent)

The thing actually running right now. An LLM with a system prompt, a tool list, and a control loop:

```
while not done:
    response = llm.invoke(messages)
    if response.tool_calls:
        for call in response.tool_calls:
            result = call.tool(*call.args)
            messages.append(result)
    else:
        done = True
```

This is what LangChain's `AgentExecutor`, `create_react_agent`, and the modern `LangGraph` primitives implement. It's also what Claude Code, Antigravity, Cursor, and Codex are at their core — a reasoning loop wrapped in an IDE.

**Defining feature:** the LLM **chooses** what to do next at every step. High autonomy, open-ended task.

### Layer 2 — Capability (the invokable unit)

A packaged thing a runtime can invoke. Examples:

- An [Agent Skill](https://agentskills.io/specification): directory containing `SKILL.md` (metadata + when_to_use + instructions), optional `scripts/`, `references/`, `assets/`
- A LangChain `Tool` (`@tool`-decorated function with a docstring)
- An MCP server (Model Context Protocol — exposes tools over stdio/HTTP)
- A REST API the runtime knows how to call

A capability has a **defined contract**: input schema, output schema, when-to-invoke triggers. The runtime decides *when* to invoke it; the capability decides *how* to do its job once invoked.

**Defining feature:** constrained autonomy. The capability does its job and returns. It may invoke an LLM internally, but it doesn't decide whether to run.

### Layer 3 — Specification (the design-time artifact)

A document that describes an agent's behavior. Read by an LLM as a system prompt at runtime to *configure* a runtime instance.

Examples:
- This repo's `make_agent.md/.json` produces specifications for canvas audit, blueprint sync, etc.
- A LangChain `ChatPromptTemplate` with role and instructions
- A Claude Code subagent definition (`.claude/agents/<name>.md`)

A specification is not executable on its own. Loaded into a runtime, it shapes the runtime's behavior — but the runtime is what actually runs.

**Defining feature:** a specification is documentation that becomes prompt at runtime.

---

## The Autonomy Axis

The cleanest single dimension separating these layers is **how much choice the unit has**. From least to most autonomous:

| | Autonomy | What it decides | Example |
|---|---|---|---|
| **Tool / function** | None | Nothing — executes when called | `requests.get(url)` |
| **Capability / skill** | Bounded | How to do *its* job; not whether to run | `.agents/skills/canvas-audit/` running an audit when invoked |
| **Runtime / agent** | Open-ended | What to do next, in a loop, until task is done | Claude Code working through a multi-step refactor |
| **Multi-agent system** | Distributed | Orchestrates other agents; meta-decisions | A planner agent delegating to specialist subagents |

This axis matters because it determines what can fail and how. Autonomy creates capability and risk in equal measure.

---

## AI Engineering Per Layer

Each layer has its own engineering discipline. Building production-quality systems means doing each one well at the right layer.

### Engineering Layer 1 — Runtimes

Concerns: orchestration, control flow, observability.

| Dial | What it controls | Common failure |
|---|---|---|
| **Model choice** | Capability vs. cost vs. latency | Overspending on Opus when Haiku would do, or starving complex tasks with weak models |
| **Tool descriptions** | The LLM picks tools based on these — they're prompts, not just docs | Vague descriptions → wrong tool, or correct tool with wrong params |
| **Max iterations** | Prevents infinite reasoning loops | Either set too low (truncates real work) or too high (burns tokens on stuck loops) |
| **Temperature** | Determinism in tool calls vs. creativity in narrative | Tool-use phases need temperature near 0; explanation phases can be higher |
| **Context window management** | What stays in working memory | Tool results bloat context; need summarization or pruning strategies |
| **Error handling in the loop** | What happens when a tool fails | Retry blindly = infinite loop. Surface to LLM = sometimes recovers, sometimes doubles down |
| **Subagent delegation** | When to invoke a specialist runtime | Over-delegation fragments context; under-delegation overloads main context |
| **Evaluation** | How you know it works | Hard — the same task can succeed via many paths; need rubric-based or trajectory-based eval |

LangChain primitives most relevant: `AgentExecutor`, `create_react_agent`, `bind_tools()`, `LangGraph` for stateful workflows, `LangSmith` for tracing/evaluation.

This is the layer most LangChain courses focus on. Students build these.

### Engineering Layer 2 — Capabilities / Skills

Concerns: contract design, discoverability, parameterization, isolation.

| Dial | What it controls | Common failure |
|---|---|---|
| **`when_to_use` clarity** | Whether the host runtime invokes you correctly | Vague trigger → never invoked, or invoked at the wrong time |
| **Input schema** | What the runtime must provide | Too rigid → runtime can't satisfy; too loose → garbage in, garbage out |
| **Output schema** | What the runtime can rely on | Unstructured output forces the runtime LLM to re-parse |
| **Idempotency** | Whether re-invoking is safe | Side effects without idempotency = double-charge, double-create, double-delete |
| **Parameterization** | Whether other users can deploy it | Hardcoded institution / API key / paths → not reusable |
| **Internal LLM use** | Whether the skill calls an LLM itself | Doubles cost; pick the smallest model that works |
| **Failure modes** | What happens on bad input | Silent failure = worst; loud error with recovery hint = best |
| **Versioning** | How updates roll out without breaking callers | No version → breaking change ships silently |

LangChain primitives: `@tool` decorator, `StructuredTool` with Pydantic schemas, `BaseTool` subclasses for stateful capabilities. Outside LangChain: SKILL.md, OpenAPI specs, MCP server definitions.

The crucial AI-engineering insight here: **`when_to_use` text is a prompt to the host LLM, not human documentation.** Write it the way the host LLM will read it.

### Engineering Layer 3 — Specifications

Concerns: prompt engineering at the system level.

| Dial | What it controls | Common failure |
|---|---|---|
| **Mission clarity** | Does the LLM understand what it's for? | Wandering or confused agents come from fuzzy missions |
| **Principle ordering** | Which rules dominate when they conflict | "Always X" + "Never Y" without precedence = ambiguous |
| **Workflow narrative** | How the agent should sequence steps | Steps as bullet points without "why" → skipped or reordered |
| **Pitfall documentation** | Pre-empting known failure modes | Without documented pitfalls, the agent rediscovers them painfully |
| **Tool list framing** | What the agent thinks it has access to | Listing tools in the spec without aligning to runtime tool list = phantom tools |
| **Confirmation requirements** | What the agent must check before acting | Missing here = unwanted side effects |
| **Domain context** | Institution/codebase-specific facts | Without this, agents hallucinate plausible-sounding but wrong answers |
| **MD vs JSON split** | Narrative vs. structured data | Stuffing structured data into prose loses parseability; stuffing principles into JSON loses readability |

There aren't great LangChain primitives for this — specifications usually live as raw `.md` and `.json` files (your repo's pattern) or as `ChatPromptTemplate` objects in code.

The AI-engineering insight: **a specification IS a prompt**, just a long one written carefully. Treat it with the same rigor as production prompt engineering.

### Engineering Layer 0 — Tools / Functions (the leaf)

Concerns: traditional software engineering — but with one AI-flavored twist.

| Dial | What it controls | Common failure |
|---|---|---|
| **Docstring quality** | Whether the LLM correctly invokes you | Bad docstring = unused or misused function |
| **Parameter names** | LLM matches by name semantics | `param1, param2` → LLM can't infer; `course_id, module_position` → LLM gets it right |
| **Return type clarity** | Whether the LLM can reason about results | Returning `dict` with no schema → LLM guesses keys; returning typed object → LLM uses it correctly |
| **Determinism** | Whether the same call produces the same result | Stateful tools with hidden state confuse runtimes |
| **Side-effect transparency** | Whether the LLM knows what changes | "Returns nothing" tools that mutate state = surprise mutations |

LangChain primitive: the function itself. The `@tool` decorator surfaces the docstring as the LLM-visible description.

The AI-engineering insight: **function docstrings are now LLM-visible prompts.** Comments inside the function are private; the docstring is public.

---

## How They Compose — Canvas Audit Example

When you (in Claude Code) run the Canvas course audit in this repo right now, all four layers are stacked:

| Layer | What plays this role |
|---|---|
| **Runtime** | Claude Code itself — the LLM in a reasoning loop, picking next steps |
| **Capability** | Currently: the Python CLI scripts in `lib/tools/`. Future: `.agents/skills/canvas-audit/` |
| **Specification** | `lib/agents/canvas_course_expert.md` + `.json` — load these and Claude becomes the audit agent |
| **Tool / function** | `parse_course_export()`, `analyze_cognitive_load()`, `canvas_api()` etc. — invoked from the runtime |

The Roadmap in [`AGENTS.md`](../../AGENTS.md#roadmap) describes the migration: extract the audit capability from the Python CLI tools layer up into a deployable Skill (Layer 2), so any runtime — not just Claude Code — can invoke it.

---

## Why Students Get Confused (and How to Help)

When a student reads "build an agent in LangChain," "deploy a Claude agent skill," and "write your agent definition" in the same week, all three uses of "agent" describe **different layers**. Without disambiguation, the concepts blur.

Suggested teaching slide:

> When someone says "agent," ask which layer they mean:
> 1. The **runtime** (a process executing right now)
> 2. The **capability** (a thing the runtime calls)
> 3. The **specification** (a document configuring the runtime)
>
> 70% of agent-architecture confusion is layer-conflation. Name the layer.

For a LangChain course specifically: students will mostly work at the runtime layer (Layer 1), invoking capabilities at Layer 2, occasionally writing specifications at Layer 3 (their system prompts). Calling all three "the agent" without disambiguation is the source of most architectural confusion downstream.

---

## Where Each Layer's Discipline Lives in Public Frameworks

| Layer | LangChain | OpenAI | Anthropic | Cross-tool |
|---|---|---|---|---|
| **Runtime** | `AgentExecutor`, `create_react_agent`, `LangGraph`, `LangSmith` | Assistants API, Codex CLI | Claude Code, Agent SDK | Cursor, Antigravity, Aider |
| **Capability** | `@tool`, `StructuredTool`, `BaseTool` | Function calling, Assistants tools | Tool use API, MCP | [Agent Skills spec](https://agentskills.io/specification), MCP, OpenAPI |
| **Specification** | `ChatPromptTemplate`, system messages | Assistant instructions field | System prompts, [`AGENTS.md`](https://agents.md/) | AGENTS.md, CLAUDE.md, GEMINI.md |
| **Tool / function** | Plain Python with `@tool` | JSON schema function defs | JSON schema tools | OpenAPI / MCP |

The convergence point in 2026 is **AGENTS.md at the spec layer** and the **Agent Skills standard at the capability layer** — both Linux-Foundation-stewarded, both adopted across most major tools.

---

## Further Reading

- [AGENTS.md — open format for agent specifications](https://agents.md/)
- [Agent Skills Specification (agentskills.io)](https://agentskills.io/specification)
- [LangChain Agents documentation](https://python.langchain.com/docs/concepts/agents/)
- [LangGraph (stateful agent orchestration)](https://langchain-ai.github.io/langgraph/)
- [Anthropic — Building effective agents](https://www.anthropic.com/research/building-effective-agents)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- [OpenAI — Function calling and the Assistants API](https://platform.openai.com/docs/guides/function-calling)

---

## TL;DR

| If you're… | You're working at… |
|---|---|
| Writing the loop that calls tools | Layer 1 (Runtime) — LangChain's `AgentExecutor` is here |
| Packaging a capability for distribution | Layer 2 (Capability) — Agent Skills spec is here |
| Writing the system prompt that shapes behavior | Layer 3 (Specification) — `AGENTS.md`, `make_agent.md` are here |
| Writing the function the LLM eventually calls | Layer 0 (Tool/function) — your Python code |

When designing: explicitly choose which layer you're working at. When debugging: identify which layer is failing. When teaching: name the layer before describing the concept.

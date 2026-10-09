---
name: langgraph-workflows
description: Our conventions for LangGraph and LangChain code, covering StateGraph, create_agent, subagents and supervisors, middleware, MCP tools in agents, checkpointers, streaming and tests. Use when writing, changing or reviewing code that uses langgraph or langchain. To choose the architecture, use agent-architecture first; for the MCP server itself, use mcp-servers.
---

# LangGraph workflows

Our conventions on top of LangGraph and LangChain, for the versions at the end. For the API itself (`StateGraph`, `Command`, `Send`, `interrupt`), read LangChain's official skills (`langchain-ai/langchain-skills`) or the live docs. While the architecture isn't settled, load the `agent-architecture` skill first: it owns the rules every multi-agent design follows, and this skill says how to do them in LangGraph.

Read the reference file for the part you're working on:

| Working on | Read |
|---|---|
| Handoffs, parallel branches or `Send`, subgraphs | [WIRING.md](WIRING.md) |
| MCP tools in an agent: connecting, allowlists, retries, tool errors | [MCP-CLIENT.md](MCP-CLIENT.md) |
| Checkpointers, approval before side effects, state across deploys | [PERSISTENCE.md](PERSISTENCE.md) |
| The graph as a service: run ids, resuming, streaming events | [RUNS-AND-STREAMING.md](RUNS-AND-STREAMING.md) |
| Tests | [TESTING.md](TESTING.md) |

Tested code for these rules: [examples/triage_agent.py](examples/triage_agent.py) (one agent), [examples/supervisor.py](examples/supervisor.py), [examples/mcp_tools.py](examples/mcp_tools.py) (MCP tools from the run's server), [examples/models.py](examples/models.py), and the tests in [examples/test_examples.py](examples/test_examples.py) with [examples/testing.py](examples/testing.py).

## Graph shape

- Define the graph fully at build time; at runtime it only picks a path (conditional edges, `Command`, `Send`). Checkpoints name nodes, so a thread resumes only into a graph that still has them, and the graph you test is the graph that runs.
- Nodes run an agent loop and return state. Behaviour lives in prompts, response schemas, MCP tools and middleware, where the eval measures it.
- Add the built agent itself as the node. A thin node that only maps state in and out is for agents that shouldn't see each other's `messages` or would overwrite each other's `structured_response`. Whatever depends on the run goes into middleware and tools that read the run context; plain nodes read it through `Runtime[Context]`.
- Rules about what an agent returns go in its prompt and its response schema (e.g. `Literal[...]` of allowed values), and the eval checks them. Code that filters output afterwards hides the failure from the eval and the agent alike.
- An orchestrator agent routes work and feedback itself; graph code only caps the rounds. It has the whole run in its conversation, and routing in code would decide again with less.
- Use a built-in from LangGraph, LangChain or deepagents (middleware, `RetryPolicy`, checkpointers) before writing custom code, and say in a comment why none fit. Custom code is ours to keep working across upgrades.
- Every state key and counter has a reader; delete the rest. State goes into every checkpoint and must stay compatible for waiting threads.

## Multi-agent

- Every agent and composed pattern keeps the `create_agent` contract (`messages` in, `messages` and `structured_response` out), so patterns nest as nodes, subgraphs or tools.
- A supervisor is a `create_agent` whose subagents are tools taking one `task` string ([examples/supervisor.py](examples/supervisor.py)). The subagent starts from that string alone, so the supervisor's prompt asks for self-contained tasks.
- A subagent gets only its task. Forward the parent's conversation, without tool traffic, only to a subagent that decides on the whole conversation.
- Subagents return a structured report (`response_format`), and their prompt says the caller sees nothing else. The supervisor's response schema carries the reports unchanged, like `Submission` in the supervisor example.
- Name every agent (`create_agent(name=...)`): routing decides on names and descriptions, and the name tags the agent's events in streams and traces.
- Routing and plan schemas allow only the agents the graph was built with (a `Literal` built at build time), and the prompt lists their names and descriptions, so the model can only pick an agent that exists.

## Agents

- One file per agent with its name, description, prompt, tools, response schema and build function ([examples/triage_agent.py](examples/triage_agent.py)). Graphs compose the built agents.
- Build the graph and its agents once, at service start or once per eval variant, with model, prompt variants and limits as arguments of the build. Building per run repeats compile and tool setup on every call; configuration read at import time can't build two variants side by side.
- Whatever differs between runs (e.g. the MCP URL an eval case uses) comes with the run's context (`invoke(..., context=...)`). Agents read it per call through middleware (MCP tools as in [examples/mcp_tools.py](examples/mcp_tools.py), `@dynamic_prompt`, `wrap_model_call`) and tools (`ToolRuntime.context`). The graph and its agents share one `context_schema`.
- Pass built agents and graphs as arguments; a static table of build functions (`GRAPHS = {"name": build}`) is fine. Registries of built instances behind globals (`.active()`, `get_graph()`), lazy agent wrappers and tool caches make a run's instance depend on what ran before.
- Agents get validation feedback inside their own loop, e.g. a validation tool they and the reviewer call, so they fix a value while they still have the context.
- Field types come from the source of truth (the DB or API schema); agents return typed values, not strings for the app to decode.
- Validate exactly as the real system does, with no conversions it wouldn't make (`"yes"` → `true`): a leniency the system lacks passes the eval and fails in production.

## Limits and failures

- Cap every loop explicitly: `ModelCallLimitMiddleware(run_limit=...)` on every agent, `ToolCallLimitMiddleware(tool_name=<subagent>, run_limit=...)` per subagent in a supervisor, round, handoff and iteration counters in the graph. The recursion limit (10,007 by default) stops a runaway graph only after thousands of steps.
- Reset per-run counters in `before_agent` or an entry node, since a thread's state outlives the run, and decide what hitting a cap does (escalate or fail) so no unchecked result is passed on.
- `ModelRetryMiddleware` takes `on_failure="error"`; with `"continue"`, the error text reaches callers as the answer.
- Async nodes that run agents get a `timeout` (`TimeoutPolicy`); `add_node(..., error_handler=...)` recovers once a node's retries run out.
- Code that reads a run's result checks that `structured_response` is there: an agent can end without calling its output tool.

## Models and media

- Azure OpenAI is plain `ChatOpenAI` with `base_url=<endpoint>/openai/v1/` and `use_responses_api=True` ([examples/models.py](examples/models.py)); the v1 API has no `api-version` to keep current.
- Return images as image content blocks in the tool result, so the model sees the image, not a description.
- Pick the model per agent: cheaper models for classification, routing and summaries, the strong one where the work is decided.
- Keep the system prompt and tool list stable and put run-specific content after them; the prompt cache matches on the prefix.
- Return large tool results as a reference (file, id) with a short preview. Inline, they stay in the context for every later call.

## Before you finish

Run `uv run python <this skill's directory>/scripts/check_agents.py src/` and fix every finding. To check built agents for a name and a model-call cap, copy the script into the project's tests and assert `agent_problems(agent) == []` ([examples/test_examples.py](examples/test_examples.py)). Then:

- [ ] No node or tool builds an agent or compiles a graph.
- [ ] Everything that differs between runs arrives through the run's context.
- [ ] Every loop has a cap, and the code says what happens when it's hit.
- [ ] Routing and plan schemas allow only agents the graph was built with.
- [ ] Offline tests cover the change and assert model calls per run ([TESTING.md](TESTING.md)).

## Versions and replaced APIs

Written for langgraph 1.2.14, langchain 1.4.3, fastmcp 4.0.11 and mcp 2.3.0, checked on 2026-10-07. After an upgrade, re-check this table and the recursion limit, and run `uv run pytest` in the skills repo.

| Instead of | Use | Because |
|---|---|---|
| `langgraph-supervisor` | `create_agent` with subagents as tools ([examples/supervisor.py](examples/supervisor.py)) | archived |
| `langchain-mcp-adapters` | `langchain.mcp.MCPAdapter` ([examples/mcp_tools.py](examples/mcp_tools.py)) | archived, pinned to MCP SDK 1 |
| `langgraph.prebuilt.create_react_agent` | `langchain.agents.create_agent` | deprecated since LangGraph 1.0 |
| `AzureChatOpenAI`, `api_version=` | `ChatOpenAI(base_url=<endpoint>/openai/v1/, use_responses_api=True)` | Azure's v1 API needs neither |

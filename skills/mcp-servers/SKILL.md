---
name: mcp-servers
description: Our conventions for MCP servers in Python with FastMCP, covering tool design and descriptions, schemas, errors, mounting next to a FastAPI REST API, transport, auth and tests. Use when writing, changing or reviewing a FastMCP server or its tools (@mcp.tool), or when an agent misuses a tool and the fix belongs on the server. For the agent side, use langgraph-workflows.
---

# MCP servers

Our conventions for FastMCP servers whose clients are our LangGraph agents, for the versions at the end. When the change is on the agent side (connecting, allowlists, retries), load the `langgraph-workflows` skill and read its MCP-CLIENT.md.

| Working on | Read |
|---|---|
| Transport, the lifespan, blocking work, auth | [RUNTIME.md](RUNTIME.md) |
| Tests and evaluating the server through the agent | [TESTING.md](TESTING.md) |

[examples/server.py](examples/server.py) follows every rule below, mounted into FastAPI next to a REST route; [examples/test_server.py](examples/test_server.py) tests it.

## Layout

- Business logic lives in a service layer with typed inputs, typed results and domain exceptions. MCP tools and REST routes are thin wrappers over it and share one write path; two write paths drift until the agent can store what the app would reject.
- One `FastMCP` instance, mounted into the FastAPI app with `mcp_app = mcp.http_app(path="/")` and `app.mount("/mcp", mcp_app)`. The app's lifespan wraps `mcp_app.lifespan`, or the session manager never starts.
- A tool's name is its function's name; with a `name=` override, validation errors name a function the agent doesn't know.
- The tools that exist decide what an agent may do. Agents get reads, and writes that land as suggestions; creating, approving and deleting stay in the app unless an agent must do them. A confused or injected agent can't misuse a tool that isn't there.
- Values a description mentions (limits, caps) come from config, so text and behaviour agree.
- Short server `instructions` say what the server is for and how its tools relate. LangChain's MCP client drops them, so everything an agent needs is also in the tool descriptions.

## Tool design

- Design tools around the agent's tasks, not tables or endpoints: the agent passes ids and choices, the server builds the queries. Tools generated from a REST API leave joins and query building to the agent, over many calls.
- Few tools with distinct purposes. Reads and writes are separate tools, so approval and retries can treat them differently.
- Name tools `verb_noun` in snake_case, in one language, with the domain's own nouns, and without the service name: clients that combine servers prefix it already.
- A description says what the tool does, when to use it, what it returns, which sibling to use instead, and its known weaknesses with numbers ("the top result is the best match in fewer than one case in five"). The agent picks and uses tools from this text alone.
- FastMCP publishes the docstring's summary and body as the description and turns `Args:` entries into parameter descriptions; it drops `Returns:` and `Raises:`. Describe the return shape and the errors in the body: the model reads the description and the text result, never the `outputSchema`.
- Every parameter is `Annotated[T, Field(description=...)]` with an example. `Literal`, constraints and Pydantic models instead of bare `str` and `dict` reject a bad call before the tool runs, naming the field.
- Return Pydantic models, so the tool publishes an `outputSchema` and `structuredContent` next to the JSON text. A list goes in a field of a model, next to its cursor.
- Results carry what the agent decides on (which fields match, why an item was skipped) and the ids for follow-up calls. With only a score, the agent takes the top hit.
- Bound every result with a default limit, a cursor, or a truncation note that says how to narrow the query; one unbounded result can fill the agent's context.
- Normalize identifiers leniently (`"10"` → `"000010"`) and validate values exactly as the system of record does. A lenient id costs nothing; a lenient value passes here and fails where it's stored.
- Offer a dry-run validation tool that gives the same feedback as the write, so the agent fixes values before writing them.
- Set all four annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) and a `title` on every tool. Unset hints default to a destructive, open-world tool, and agents decide on approval from them.
- Every call stands on its own; state across calls travels as a handle the agent passes back (e.g. a draft id). Session state is lost with stateless HTTP and on a second replica.
- `tools/list` is the same, in the same order, for every caller with the same rights, so prompt caches hold and runs are reproducible.
- A description changes in the same commit as the behaviour it describes.
- Tool names and result fields are a contract that agent prompts and other consumers rely on: add the new one, retire the old one later.

## Errors

- Map domain exceptions to `ToolError` once, in a decorator around every tool, with a message that says what was wrong and what to do next; the agent reads it as an `isError` result. A FastMCP 4 middleware only sees the exception already wrapped in a masked `ToolError` (the domain exception is its `__cause__`).
- `mask_error_details=True`, so any other exception reaches the agent as "Error calling tool ..." without internals.
- Partial success is data: each skipped item comes back with a reason code, so the agent retries exactly those.
- Infrastructure errors stay errors. A failed query returned as an empty result tells the agent there is nothing there.
- REST and MCP raise the same domain exceptions, and each interface maps them once (HTTP status, `ToolError`).

## Before you finish

Run `uv run python <this skill's directory>/scripts/check_tools.py my_package.mcp_service:mcp` and fix every finding: it checks names, titles, annotations, parameter descriptions, Pydantic results, dropped docstring sections and `mask_error_details`. Then:

- [ ] Every description says what the tool does, when to use it, what it returns and which sibling to use instead.
- [ ] Every result is bounded.
- [ ] Domain errors say what to do next; infrastructure errors stay errors.
- [ ] A changed tool has its description and its `list_tools()` snapshot changed in the same commit, and no tool or result field was renamed.
- [ ] The real agent ran a task the change affects, and you read the transcript ([TESTING.md](TESTING.md)).

## Versions and replaced APIs

Written for FastMCP 4.0.11 on MCP SDK 2.3.0 (spec 2026-07-28), with clients on `langchain.mcp` (langchain 1.4.3), checked on 2026-10-07.

Upgrade the server's and its clients' FastMCP/MCP SDK majors together: the old LangChain client, `langchain-mcp-adapters`, was pinned to SDK 1, so the server's move to FastMCP 4 needed the clients' move to `langchain.mcp`.

| Instead of | Use | Because |
|---|---|---|
| `from mcp.server.fastmcp import FastMCP` | `from fastmcp import FastMCP` | SDK 2 no longer ships that module |
| `transport="sse"` | `mcp.http_app(...)` mounted in FastAPI, or `mcp.run(transport="http")` | the HTTP+SSE transport is deprecated in the spec |
| MCP logging, sampling, roots | stderr or OpenTelemetry, direct model calls, path parameters | deprecated in spec 2026-07-28 |
| `tool.inputSchema`, `tool.outputSchema` | `tool.input_schema`, `tool.output_schema` | renamed in SDK 2; the old names warn |

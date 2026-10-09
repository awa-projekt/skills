# MCP tools in agents

The agent side of MCP. What a server publishes (tool names, descriptions, errors, annotations) is covered by the `mcp-servers` skill; when the fix belongs on the server, load that skill. [examples/triage_agent.py](examples/triage_agent.py) wires up everything below.

## Connecting

- Give an agent its MCP tools through a middleware on `langchain.mcp.MCPAdapter` that connects to the server the run's context names, like `McpTools` in [examples/mcp_tools.py](examples/mcp_tools.py) (`McpTools(lambda context: context.mcp_url, ...)`). The agent is built once, and each run or eval case brings its own server.
- Give each agent an allowlist of MCP tool names (`McpTools(..., tools=TOOLS)`), checked when the agent starts, so a renamed or missing tool fails the start rather than a run halfway through. The agent also never sees tools added to the server for someone else.
- Code that needs a tool's structured result reads the server's `structuredContent` from the `ToolMessage` (`message.artifact["structured_content"]`) instead of parsing the text. The model itself gets only the text (what that means for the server is in `mcp-servers`).

## Errors and retries

- An error the server reports (`isError`) reaches the agent as the tool's answer; that is how the agent learns to fix its call.
- Retry an unreachable server, and only that (`unreachable` in [examples/mcp_tools.py](examples/mcp_tools.py) tells it from an error the server reports). Use `ToolRetryMiddleware(tools=[...], retry_on=unreachable, on_failure=<callable>)` on tool calls, and `RetryPolicy(retry_on=unreachable)` on the nodes that run agents, because listing tools at the agent's start happens outside any tool call. Once the retries run out, `on_failure` returns a tool message saying the server seems down, so the agent reports what it has instead of the run crashing.
- `tools=` lists only idempotent tools: a retried write can apply twice.
- Chat models already retry their own calls (`max_retries`). A `ModelRetryMiddleware` on top multiplies the attempts, so add one only on purpose.
- `ToolErrorMiddleware(on_error)` turns other tool exceptions into tool messages. List it before `ToolRetryMiddleware`, so it wraps the retries and only sees what they let through. Without it, `ToolNode` re-raises the exception and a node `RetryPolicy` reruns the whole agent.
- `on_error` names the exception type, not its message, which can carry internals. It returns `None` for exceptions that should stop the run.

Server and client move to a new FastMCP/MCP SDK major together; the `mcp-servers` skill keeps that rule and the versions.

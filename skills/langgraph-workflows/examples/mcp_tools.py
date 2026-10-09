"""MCP tools from the server a run names: a middleware on `langchain.mcp`, so an agent is built
once and each run (or eval case) brings its own server through the run's context.

    agent = create_agent(
        model,
        tools=[],
        middleware=[
            ToolRetryMiddleware(tools=["search"], retry_on=unreachable, on_failure=lambda e: "The server is down."),
            McpTools(lambda context: context.mcp_url, tools=["search", "get_record"], server="records"),
        ],
        context_schema=Context,
    )
    await agent.ainvoke({"messages": [...]}, context=Context(mcp_url=...))

When the agent starts, the middleware lists the server's tools once, checks the allowlist and
keeps the definitions in the agent's state. Every model call is offered them, and every tool
call connects to the run's server. Async only, like the MCP client.
"""

from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, Any, NotRequired

import anyio
import httpx2
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import PrivateStateAttr
from langchain.mcp import MCPAdapter, as_langchain_tool
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command
from mcp.types import Tool as McpTool

_TRANSPORT_FAILURES = (httpx2.TransportError, anyio.ClosedResourceError, anyio.BrokenResourceError, anyio.EndOfStream)


def unreachable(error: BaseException) -> bool:
    """Whether an MCP call failed because the server could not be reached: a transport error,
    possibly wrapped by the client, or a gateway's 502/503/504. An error the server reports
    for a call is no such failure; the agent gets it as the tool's answer. Use it as `retry_on=`
    of `ToolRetryMiddleware` and of a node's `RetryPolicy`."""
    if isinstance(error, BaseExceptionGroup):
        return any(unreachable(inner) for inner in error.exceptions)
    if isinstance(error, _TRANSPORT_FAILURES):
        return True
    if isinstance(error, httpx2.HTTPStatusError):
        return error.response.status_code in (502, 503, 504)
    return error.__cause__ is not None and unreachable(error.__cause__)


def _by_server(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


class McpToolsState(AgentState):
    mcp_tools: NotRequired[Annotated[dict[str, list[dict[str, Any]]], PrivateStateAttr, _by_server]]


class McpTools(AgentMiddleware):
    """Offers an agent the tools `tools` of the MCP server `target(runtime.context)` names.

    `target` returns anything `MCPAdapter` accepts (a URL, or a `fastmcp.Client` for auth and
    timeouts) and does no I/O. A name in `tools` the server doesn't list fails the agent's start.
    An agent with several servers needs a different `server` name for each.
    """

    state_schema = McpToolsState

    def __init__(self, target: Callable[[Any], Any], *, tools: Sequence[str], server: str = "mcp") -> None:
        super().__init__()
        self.target = target
        self.tool_names = tuple(tools)
        self.server = server

    @property
    def name(self) -> str:
        return f"McpTools_{self.server}"

    def _adapter(self, context: Any) -> MCPAdapter:
        return MCPAdapter(self.target(context))

    def _definitions(self, state: Any) -> list[dict[str, Any]]:
        return ((state or {}).get("mcp_tools") or {}).get(self.server, [])

    async def abefore_agent(self, state: McpToolsState, runtime: Runtime[Any]) -> dict[str, Any]:
        adapter = self._adapter(runtime.context)
        async with adapter:
            listed = {tool.name: tool for tool in await adapter.client.list_tools()}
        if missing := [name for name in self.tool_names if name not in listed]:
            raise ValueError(f"The MCP server {self.server!r} lists no tool {', '.join(missing)}.")
        definitions = [listed[name].model_dump(mode="json", by_alias=True, exclude_none=True) for name in self.tool_names]
        return {"mcp_tools": {self.server: definitions}}

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> ModelResponse:
        offered = {tool.name if isinstance(tool, BaseTool) else tool.get("name") for tool in request.tools}
        definitions = [d for d in self._definitions(request.state) if d["name"] not in offered]
        if not definitions:
            return await handler(request)
        client = self._adapter(request.runtime.context).client
        mine = [await as_langchain_tool(McpTool.model_validate(d), client) for d in definitions]
        return await handler(request.override(tools=[*request.tools, *mine]))

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]]
    ) -> ToolMessage | Command:
        definition = next((d for d in self._definitions(request.state) if d["name"] == request.tool_call["name"]), None)
        if definition is None:
            return await handler(request)
        adapter = self._adapter(request.runtime.context)
        async with adapter:
            if "outputSchema" in definition:
                await adapter.client.list_tools()  # the client reads output schemas from a listing
            tool = await as_langchain_tool(McpTool.model_validate(definition), adapter.client)
            return await handler(request.override(tool=tool))

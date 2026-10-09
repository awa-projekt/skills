"""Offline test helpers: a chat model scripted by a policy, a model-call counter, and an MCP
server served over HTTP for the length of a test.

The policy gets everything the model sees in one call (`ModelTurn`) and returns the reply. Because
the reply is a function of the conversation, parallel branches and subagents stay deterministic
whatever order they run in, which a model replaying a fixed list can't promise.

    def policy(turn: ModelTurn):
        if not turn.called("search"):
            return turn.call("search", query="login")
        return turn.structured(Report(...))

    model = ScriptedChatModel(policy=policy)                                     # tool strategy
    model = ScriptedChatModel(policy=policy, profile={"structured_output": True})  # native strategy
"""

import json
import socket
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import uvicorn
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel


@dataclass
class ModelTurn:
    """What the model sees in one call, with helpers to build its reply."""

    messages: list[BaseMessage]
    tools: list[dict[str, Any]] = field(default_factory=list)
    response_format: dict[str, Any] | None = None  # set on the native structured-output path

    @property
    def system(self) -> str:
        return "\n".join(m.text for m in self.messages if isinstance(m, SystemMessage))

    def called(self, tool: str) -> bool:
        return any(isinstance(m, ToolMessage) and m.name == tool for m in self.messages)

    def result(self, tool: str) -> str | None:
        results = [m.text for m in self.messages if isinstance(m, ToolMessage) and m.name == tool]
        return results[-1] if results else None

    def json_result(self, tool: str) -> Any:
        return json.loads(self.result(tool))

    def call(self, tool: str, **args: Any) -> AIMessage:
        bound = [t["function"]["name"] for t in self.tools]
        if tool not in bound:
            raise AssertionError(f"the policy called {tool!r}, but only {bound} are bound")
        return AIMessage(content="", tool_calls=[{"name": tool, "args": args, "id": uuid.uuid4().hex, "type": "tool_call"}])

    def structured(self, report: BaseModel) -> AIMessage:
        """The final report: JSON text on the native path, else a call of the schema's tool."""
        if self.response_format is not None:
            return AIMessage(content=report.model_dump_json())
        return self.call(type(report).__name__, **report.model_dump(mode="json"))


class ScriptedChatModel(BaseChatModel):
    policy: Callable[[ModelTurn], AIMessage | str]

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], *, tool_choice: Any = None, **kwargs: Any):
        return self.bind(tools=[convert_to_openai_tool(t) for t in tools], tool_choice=tool_choice, **kwargs)

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        turn = ModelTurn(list(messages), list(kwargs.get("tools") or []), kwargs.get("response_format"))
        reply = self.policy(turn)
        message = AIMessage(content=reply) if isinstance(reply, str) else reply
        return ChatResult(generations=[ChatGeneration(message=message)])


class ModelCalls(BaseCallbackHandler):
    """Counts model calls per agent; pass it as `config={"callbacks": [calls]}`. Callbacks reach
    subagents called from tools too."""

    def __init__(self) -> None:
        self.by_agent: Counter[str] = Counter()

    def on_chat_model_start(self, serialized: Any, messages: Any, **kwargs: Any) -> None:
        self.by_agent[(kwargs.get("metadata") or {}).get("lc_agent_name", "?")] += 1


@contextmanager
def serve_mcp(server: Any) -> Iterator[str]:
    """Serves a FastMCP server over streamable HTTP on a free port and yields its URL."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    web = uvicorn.Server(uvicorn.Config(server.http_app(path="/mcp"), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=web.run, daemon=True)
    thread.start()
    while not web.started:
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        web.should_exit = True
        thread.join(timeout=10)

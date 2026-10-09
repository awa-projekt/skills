"""One agent, one file: its name, description, prompt, tools, response schema and the function
that builds it. A graph or a supervisor composes the built agent; nothing here runs per request.

The agent triages a support ticket: it proposes a category, priority and team from similar
resolved tickets, each value with the tickets it rests on.
"""

from dataclasses import dataclass
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolErrorMiddleware, ToolRetryMiddleware
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from mcp_tools import McpTools, unreachable


@dataclass(frozen=True)
class Context:
    """What differs between runs, passed with each one: `agent.ainvoke(input, context=Context(...))`.
    The graph and every agent in it share this one `context_schema`."""

    mcp_url: str


NAME = "triage"  # tags the agent's events in streams and traces; routing decides on it
DESCRIPTION = (
    "Proposes a category, priority and team for a support ticket from similar resolved tickets. "
    "Give it the ticket number; it answers with one decision per field, each with its sources."
)
PROMPT = """You are the triage agent. Read the ticket, search similar resolved tickets, and \
propose a value for each field you can source. Check every value with validate_fields before \
you report it. The caller sees only your final report."""

# The MCP tools this agent may use. McpTools checks them when the agent starts, so a renamed or
# missing tool fails the start instead of a run halfway through.
TOOLS = ("get_ticket", "search_similar_tickets", "validate_fields")
MAX_MODEL_CALLS = 12

UNREACHABLE = (
    "The ticket server is not answering, not even after several tries; it seems to be down. "
    "Report only the values you could already trace to similar tickets."
)


class FieldDecision(BaseModel):
    field: Literal["category", "priority", "team"] = Field(description="The ticket field this value is for.")
    value: str | int = Field(description="The proposed value, in the form validate_fields accepted.")
    sources: list[str] = Field(description="Numbers of the similar tickets the value rests on, at least one.")


class TriageReport(BaseModel):
    decisions: list[FieldDecision] = Field(description="One entry per field you found a value for.")


def tool_failed(error: Exception, request) -> str:
    """Any other tool exception, as the tool's answer: its type, not its message, which may carry internals."""
    return f"{request.tool_call['name']} failed ({type(error).__name__}). Check the arguments, or go on without it."


def agent(model: BaseChatModel) -> CompiledStateGraph:
    """Built once, with the graph; the MCP server comes from each run's context."""
    return create_agent(
        model,
        tools=[],  # the MCP tools come from McpTools, per run
        system_prompt=PROMPT,
        response_format=TriageReport,
        context_schema=Context,
        middleware=[
            # Listed first, so it wraps the others: it only sees what the retries let through.
            ToolErrorMiddleware(tool_failed),
            # Only idempotent tools, only an unreachable server; after the retries the agent is told.
            ToolRetryMiddleware(tools=list(TOOLS), retry_on=unreachable, on_failure=lambda _: UNREACHABLE),
            McpTools(lambda context: context.mcp_url, tools=TOOLS, server="tickets"),
            # Raises at the cap; the caller decides what a capped run means.
            ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS, exit_behavior="error"),
        ],
        name=NAME,
    )

"""A supervisor: a `create_agent` whose subagents are tools taking one `task` string.

Each subagent starts from that task alone and answers with its structured report, which the
supervisor's own response schema carries on unchanged.
"""

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

import triage_agent

NAME = "supervisor"
PROMPT = """You are the supervisor. Hand the ticket's triage to the triage agent: one task that \
names the ticket number and says what to return. Pass its report on unchanged; do not summarise it."""


class Task(BaseModel):
    task: str = Field(description="Everything the agent needs, on its own: the ticket number, what to decide, what to return.")


class Submission(BaseModel):
    decisions: list[triage_agent.FieldDecision] = Field(description="The triage agent's decisions exactly as it reported them.")


def subagent_tool(subagent: CompiledStateGraph, description: str) -> BaseTool:
    """The subagent as a tool: it sees only the task, and answers with its report as JSON."""

    async def delegate(task: str) -> str:
        # Called inside the supervisor's run, so the subagent gets the run's context and callbacks.
        result = await subagent.ainvoke({"messages": [HumanMessage(task)]})
        report = result.get("structured_response")
        return report.model_dump_json() if report is not None else f"{subagent.name} ended without a report."

    return StructuredTool.from_function(coroutine=delegate, name=subagent.name, description=description, args_schema=Task)


def agent(model: BaseChatModel) -> CompiledStateGraph:
    triage = triage_agent.agent(model)  # built once, here, with the supervisor
    subagents = {triage_agent.NAME: triage_agent.DESCRIPTION}
    return create_agent(
        model,
        tools=[subagent_tool(triage, triage_agent.DESCRIPTION)],
        # The catalog the supervisor routes on: names and descriptions of the agents it was built with.
        system_prompt=PROMPT + "\n\nAgents you can delegate to:\n" + "\n".join(f"- {n}: {d}" for n, d in subagents.items()),
        response_format=Submission,
        context_schema=triage_agent.Context,
        middleware=[
            ToolCallLimitMiddleware(tool_name=triage_agent.NAME, run_limit=2),  # the subagent at most twice per run
            ModelCallLimitMiddleware(run_limit=6, exit_behavior="error"),
        ],
        name=NAME,
    )

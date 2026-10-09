"""Tests of the examples, offline: one scripted model that answers as each agent (told apart by
its system prompt), and an in-process FastMCP server with the real tool names and payload
shapes, served over HTTP."""

import ast
import asyncio
import json
from pathlib import Path

import pytest
from check_agents import agent_problems, scan, source_problems
from fastmcp import FastMCP
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_core.messages import HumanMessage, SystemMessage

import supervisor
import triage_agent
from testing import ModelCalls, ModelTurn, ScriptedChatModel, serve_mcp
from triage_agent import Context, FieldDecision, TriageReport

TICKET = "000042"
TASK = {"messages": [HumanMessage(f"Triage ticket {TICKET}.")]}


def tickets_server(name: str, similar: list[dict], tools: tuple[str, ...] = triage_agent.TOOLS) -> FastMCP:
    """A stand-in for the ticket server: the real tool names, its JSON payloads, canned data."""
    server = FastMCP(name)

    def get_ticket(ticket_id: str) -> str:
        """One ticket with its fields."""
        return json.dumps({"id": ticket_id, "title": "Login fails after password reset", "category": None})

    def search_similar_tickets(ticket_id: str) -> str:
        """Resolved tickets similar to this one, most similar first."""
        return json.dumps(similar)

    def validate_fields(values: dict) -> str:
        """Checks field values without writing them."""
        return json.dumps({"ok": True})

    for tool in (get_ticket, search_similar_tickets, validate_fields):
        if tool.__name__ in tools:
            server.tool(tool)
    return server


def triage_policy(turn: ModelTurn):
    """The triage agent: read, search, validate, report the most similar ticket's category."""
    if not turn.called("get_ticket"):
        return turn.call("get_ticket", ticket_id=TICKET)
    if not turn.called("search_similar_tickets"):
        return turn.call("search_similar_tickets", ticket_id=TICKET)
    [best, *_] = turn.json_result("search_similar_tickets")
    if not turn.called("validate_fields"):
        return turn.call("validate_fields", values={"category": best["category"]})
    decision = FieldDecision(field="category", value=best["category"], sources=[best["id"]])
    return turn.structured(TriageReport(decisions=[decision]))


def as_agents(**policies):
    """One policy per agent, picked by the start of its system prompt."""

    def policy(turn: ModelTurn):
        for role, answer in policies.items():
            if turn.system.startswith(f"You are the {role}"):
                return answer(turn)
        raise AssertionError(f"no policy for this prompt: {turn.system[:60]!r}")

    return policy


SIMILAR = [{"id": "000007", "category": "access"}]


@pytest.mark.parametrize("profile", [None, {"structured_output": True}], ids=["tool-strategy", "native"])
def test_the_report_comes_back_on_both_structured_output_paths(profile):
    agent = triage_agent.agent(ScriptedChatModel(policy=triage_policy, profile=profile))
    calls = ModelCalls()

    with serve_mcp(tickets_server("tickets", SIMILAR)) as url:
        result = asyncio.run(agent.ainvoke(TASK, {"callbacks": [calls]}, context=Context(mcp_url=url)))

    assert result["structured_response"].decisions[0].sources == ["000007"]
    # A change that adds a hop shows up here.
    assert calls.by_agent == {"triage": 4}


def test_one_agent_serves_runs_against_different_servers():
    agent = triage_agent.agent(ScriptedChatModel(policy=triage_policy))  # built once
    first = tickets_server("first", [{"id": "000001", "category": "billing"}])
    second = tickets_server("second", [{"id": "000002", "category": "bug"}])

    async def both(a, b):
        return await asyncio.gather(
            agent.ainvoke(TASK, context=Context(mcp_url=a)), agent.ainvoke(TASK, context=Context(mcp_url=b))
        )

    with serve_mcp(first) as a, serve_mcp(second) as b:
        one, two = asyncio.run(both(a, b))

    assert one["structured_response"].decisions[0].value == "billing"
    assert two["structured_response"].decisions[0].value == "bug"


def test_a_missing_tool_fails_the_agent_at_its_start():
    agent = triage_agent.agent(ScriptedChatModel(policy=triage_policy))
    server = tickets_server("old", [], tools=("get_ticket", "search_similar_tickets"))

    with serve_mcp(server) as url, pytest.raises(ValueError, match="validate_fields"):
        asyncio.run(agent.ainvoke(TASK, context=Context(mcp_url=url)))


def test_an_agent_that_never_finishes_hits_its_cap():
    def searches_forever(turn: ModelTurn):
        return turn.call("search_similar_tickets", ticket_id=TICKET)

    agent = triage_agent.agent(ScriptedChatModel(policy=searches_forever))

    with serve_mcp(tickets_server("tickets", [])) as url, pytest.raises(ModelCallLimitExceededError):
        asyncio.run(agent.ainvoke(TASK, context=Context(mcp_url=url)))


def test_a_server_that_goes_down_is_reported_to_the_agent():
    with serve_mcp(tickets_server("short-lived", [])) as gone:
        pass  # nothing listens there any more
    told = []

    def triage(turn: ModelTurn):
        if not turn.called("search_similar_tickets"):
            object.__setattr__(context, "mcp_url", gone)  # the server goes away after the start
            return turn.call("search_similar_tickets", ticket_id=TICKET)
        told.append(turn.result("search_similar_tickets"))
        return turn.structured(TriageReport(decisions=[]))

    with serve_mcp(tickets_server("tickets", [])) as url:
        context = Context(mcp_url=url)
        agent = triage_agent.agent(ScriptedChatModel(policy=triage))
        asyncio.run(agent.ainvoke(TASK, context=context))

    assert told == [triage_agent.UNREACHABLE]


def test_the_subagent_sees_only_its_task_and_its_report_is_passed_on():
    delegated = f"Triage ticket {TICKET}; return your report."
    first_turns = []

    def triage(turn: ModelTurn):
        if not turn.called("get_ticket"):
            first_turns.append(turn.messages)
        return triage_policy(turn)

    def lead(turn: ModelTurn):
        if not turn.called("triage"):
            return turn.call("triage", task=delegated)
        report = turn.json_result("triage")
        return turn.structured(supervisor.Submission(decisions=report["decisions"]))

    graph = supervisor.agent(ScriptedChatModel(policy=as_agents(triage=triage, supervisor=lead)))
    calls = ModelCalls()

    with serve_mcp(tickets_server("tickets", SIMILAR)) as url:
        result = asyncio.run(graph.ainvoke(TASK, {"callbacks": [calls]}, context=Context(mcp_url=url)))

    # Its system prompt and the task, nothing of the supervisor's conversation.
    [(system, task)] = first_turns
    assert isinstance(system, SystemMessage) and isinstance(task, HumanMessage)
    assert task.text == delegated
    assert result["structured_response"].decisions[0].sources == ["000007"]
    assert calls.by_agent == {"supervisor": 2, "triage": 4}


def test_the_built_agents_follow_the_skill():
    model = ScriptedChatModel(policy=triage_policy)
    assert agent_problems(triage_agent.agent(model)) == []
    assert agent_problems(supervisor.agent(model)) == []


def test_the_example_code_passes_the_scan():
    assert list(scan([Path(__file__).parent])) == []


def test_the_scan_reports_what_the_skill_rules_out():
    code = """
from langchain_openai import AzureChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
agent = create_agent(model, tools=[], middleware=[ToolRetryMiddleware(), ToolErrorMiddleware(handle), ModelRetryMiddleware()])
"""
    found = "\n".join(problem for _, problem in source_problems(ast.parse(code)))
    for expected in ("AzureChatOpenAI", "langchain_mcp_adapters", "name=", "tools=", "before ToolRetryMiddleware", 'on_failure="error"'):
        assert expected in found

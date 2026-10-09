"""Tests of the example server: the MCP layer in memory, the mounted app over HTTP, and a
snapshot of the tool contract. Run with `UPDATE_SNAPSHOT=1` to accept a contract change."""

import asyncio
import json
import os
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn
from check_tools import problems
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

import server

SNAPSHOT = Path(__file__).with_name("tools.snapshot.json")


def call(name: str, arguments: dict):
    async def run():
        async with Client(server.mcp) as client:
            return await client.call_tool(name, arguments, raise_on_error=False)

    return asyncio.run(run())


def test_a_tool_returns_structured_content_and_the_same_json_as_text():
    result = call("get_ticket_details", {"ticket_id": "42"})  # lenient id

    assert not result.is_error
    assert result.structured_content["ticket_id"] == "000042"
    assert json.loads(result.content[0].text) == result.structured_content


def test_a_domain_error_reaches_the_agent_with_what_to_do_next():
    result = call("get_ticket_details", {"ticket_id": "999"})

    assert result.is_error
    assert result.content[0].text == "There is no ticket 000999. Find the ticket number with find_tickets."


def test_any_other_exception_reaches_the_agent_without_internals(monkeypatch):
    def broken(ticket_id):
        raise RuntimeError("password=hunter2")

    monkeypatch.setattr(server, "get_ticket", broken)
    result = call("get_ticket_details", {"ticket_id": "42"})

    assert result.is_error
    assert "hunter2" not in result.content[0].text


def test_partial_success_names_each_skipped_field_with_a_reason():
    result = call("suggest_ticket_fields", {"ticket_id": "000042", "values": {"priority": 2, "category": "printer", "colour": "red"}})

    assert result.structured_content["written"] == ["priority"]
    assert {s["field"]: s["reason"] for s in result.structured_content["skipped"]} == {
        "category": "invalid_value",
        "colour": "unknown_field",
    }


def test_the_tools_follow_the_skill():
    assert asyncio.run(problems(server.mcp)) == []


def test_the_check_reports_what_the_skill_rules_out():
    bad = FastMCP("bad")

    @bad.tool(name="fetch")
    def get_thing(thing_id: str) -> dict:
        """Fetch a thing.

        Returns:
            The thing.
        """
        return {}

    found = "\n".join(asyncio.run(problems(bad)))
    for expected in ("mask_error_details", "name=", "verb_noun", "title=", "readOnlyHint", "Returns:", "'thing_id'", "Pydantic"):
        assert expected in found


def test_the_tool_contract_only_changes_on_purpose():
    async def listed():
        async with Client(server.mcp) as client:
            return [tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in await client.list_tools()]

    tools = asyncio.run(listed())
    if os.environ.get("UPDATE_SNAPSHOT") or not SNAPSHOT.exists():
        SNAPSHOT.write_text(json.dumps(tools, indent=2, ensure_ascii=False) + "\n")
    assert tools == json.loads(SNAPSHOT.read_text())


@contextmanager
def serve(app) -> Iterator[str]:
    """The FastAPI app under uvicorn on a free port, so its lifespan runs as in production."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    web = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=web.run, daemon=True)
    thread.start()
    while not web.started:
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        web.should_exit = True
        thread.join(timeout=10)


def test_the_mounted_server_answers_over_http():
    async def run(url):
        async with Client(f"{url}/mcp/") as client:
            return await client.call_tool("find_tickets", {"query": "login"})

    with serve(server.app) as url:
        result = asyncio.run(run(url))

    assert [t["ticket_id"] for t in result.structured_content["tickets"]] == ["000041", "000042"]


def test_a_missing_tool_raises_in_the_client():
    async def run():
        async with Client(server.mcp) as client:
            await client.call_tool("no_such_tool", {})

    with pytest.raises(ToolError):
        asyncio.run(run())

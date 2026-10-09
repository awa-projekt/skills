"""Checks an MCP server's tools for the mcp-servers rules a script can verify.

Run it on the FastMCP instance, from the server project's environment:

    uv run python <skill-dir>/scripts/check_tools.py my_package.mcp_service:mcp

or call it from a test:

    from check_tools import problems
    assert asyncio.run(problems(mcp)) == []

Prints one line per problem and exits with 1 if there is any. Written for FastMCP 4.
"""

import argparse
import asyncio
import importlib
import re
import sys
from pathlib import Path

from fastmcp import FastMCP

HINTS = {
    "readOnlyHint": "read_only_hint",
    "destructiveHint": "destructive_hint",
    "idempotentHint": "idempotent_hint",
    "openWorldHint": "open_world_hint",
}
DROPPED_SECTION = re.compile(r"^\s*(Returns|Raises|Yields)\s*:\s*$", re.MULTILINE)
VERB_NOUN = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")


async def problems(server: FastMCP) -> list[str]:
    """Every problem found, as '<tool>: <what to change>'."""
    found: list[str] = []
    # FastMCP 4 keeps this setting in a private attribute; the check is only as stable as that.
    if getattr(server, "_mask_error_details", None) is not True:
        found.append("server: set mask_error_details=True, so unexpected exceptions reach the agent without internals")

    for tool in await server.list_tools():
        name = tool.name
        fn = getattr(tool, "fn", None)

        def add(message: str) -> None:
            found.append(f"{name}: {message}")

        if fn is not None and getattr(fn, "__name__", name) != name:
            add(f"registered with name= but the function is {fn.__name__!r}; validation errors name the function, so rename the function instead")
        if not VERB_NOUN.match(name):
            add("name the tool verb_noun in snake_case")
        if not tool.title:
            add("set title=")
        missing = [hint for hint, attr in HINTS.items() if tool.annotations is None or getattr(tool.annotations, attr) is None]
        if missing:
            add(f"set the annotations {', '.join(missing)}; unset hints default to a destructive, open-world tool")
        if not (tool.description or "").strip():
            add("write a description: what it does, when to use it, what it returns, which sibling to use instead")
        if fn is not None and DROPPED_SECTION.search(fn.__doc__ or ""):
            add("the docstring has a Returns:/Raises: section, which FastMCP drops; describe the result and the errors in the body")
        for param, schema in (tool.parameters.get("properties") or {}).items():
            if not schema.get("description"):
                add(f"parameter {param!r} needs Annotated[..., Field(description=...)]")
        output = tool.output_schema or {}
        if output.get("x-fastmcp-wrap-result") or not output.get("properties"):
            add("return a Pydantic model (a list goes in a field of it), so the tool publishes an outputSchema and structuredContent")
    return found


def load(target: str) -> FastMCP:
    module_name, _, attribute = target.partition(":")
    sys.path.insert(0, str(Path.cwd()))
    server = getattr(importlib.import_module(module_name), attribute or "mcp")
    if not isinstance(server, FastMCP):
        raise SystemExit(f"{target} is a {type(server).__name__}, not a FastMCP server")
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", help="the FastMCP instance as module:attribute, e.g. my_package.mcp_service:mcp")
    found = asyncio.run(problems(load(parser.parse_args().target)))
    print("\n".join(found) if found else "No problems found.")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()

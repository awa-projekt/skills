"""Checks LangGraph and LangChain code for the langgraph-workflows rules a script can verify.

Scan the source, from the project's root:

    uv run python <skill-dir>/scripts/check_agents.py src/

and check the built agents in a test:

    from check_agents import agent_problems
    assert agent_problems(research.agent(model)) == []

The scan prints `file:line: problem` and exits with 1 if there is any. It reads the code
without running it, so a call built from `**kwargs` is given the benefit of the doubt.
"""

import ast
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

SKIP_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".git"}

REPLACED_MODULES = {
    "langgraph_supervisor": "archived: build the supervisor as create_agent with subagents as tools",
    "langchain_mcp_adapters": "archived and pinned to mcp<2: use langchain.mcp.MCPAdapter",
}
REPLACED_NAMES = {
    "AzureChatOpenAI": "use ChatOpenAI(base_url=f'{endpoint}/openai/v1/', use_responses_api=True), no api_version",
    "create_react_agent": "deprecated: use langchain.agents.create_agent",
}


def _keywords(call: ast.Call) -> dict[str | None, ast.expr]:
    return {kw.arg: kw.value for kw in call.keywords}


def _called(call: ast.Call) -> str | None:
    func = call.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None


def _constant(node: ast.expr | None) -> Any:
    return node.value if isinstance(node, ast.Constant) else None


def source_problems(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """(line, problem) for one parsed module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in REPLACED_MODULES:
                    yield node.lineno, f"{alias.name}: {REPLACED_MODULES[root]}"
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in REPLACED_MODULES:
                yield node.lineno, f"{node.module}: {REPLACED_MODULES[root]}"
            for alias in node.names:
                if alias.name in REPLACED_NAMES:
                    yield node.lineno, f"{alias.name}: {REPLACED_NAMES[alias.name]}"
        elif isinstance(node, ast.Call):
            name, keywords = _called(node), _keywords(node)
            if None in keywords:  # **kwargs: can't tell what is passed
                continue
            if name == "create_agent" and "name" not in keywords:
                yield node.lineno, "create_agent without name=: routing decides on names, and the name tags the agent's events"
            elif name == "ModelRetryMiddleware" and _constant(keywords.get("on_failure")) != "error":
                yield node.lineno, 'ModelRetryMiddleware needs on_failure="error"; otherwise the error text reaches callers as the answer'
            elif name == "ToolRetryMiddleware" and "tools" not in keywords:
                yield node.lineno, "ToolRetryMiddleware without tools=: scope it to idempotent tools, a retried write may apply twice"
        elif isinstance(node, ast.List):
            order = [_called(e) for e in node.elts if isinstance(e, ast.Call)]
            if "ToolErrorMiddleware" in order and "ToolRetryMiddleware" in order:
                if order.index("ToolErrorMiddleware") > order.index("ToolRetryMiddleware"):
                    yield node.lineno, "list ToolErrorMiddleware before ToolRetryMiddleware, so it handles what the retries let through"


def scan(paths: list[Path]) -> Iterator[str]:
    for root in paths:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for file in files:
            if SKIP_DIRS.intersection(file.parts):
                continue
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
            for line, problem in source_problems(tree):
                yield f"{file}:{line}: {problem}"


def agent_problems(agent: Any) -> list[str]:
    """Problems of a built `create_agent` graph: its name and its model-call cap."""
    found = []
    if agent.name == "LangGraph":  # create_agent's default
        found.append("unnamed agent: pass create_agent(name=...)")
    if not any(node.startswith("ModelCallLimitMiddleware") for node in agent.get_graph().nodes):
        found.append(f"{agent.name}: no ModelCallLimitMiddleware(run_limit=...); every agent caps its model calls")
    return found


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]] or [Path(".")]
    found = list(scan(paths))
    print("\n".join(found) if found else "No problems found.")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()

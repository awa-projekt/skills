# Agent Skills

[Deutsch](README.md) | English

[Agent Skills](https://agentskills.io) for building agent systems: folders of instructions that a
coding agent loads when a task needs them.

| Skill | What it covers |
|---|---|
| [agent-architecture](skills/agent-architecture/SKILL.md) | Deciding the architecture before code: workflow, single agent or a multi-agent pattern, and the rules any multi-agent design follows |
| [langgraph-workflows](skills/langgraph-workflows/SKILL.md) | Conventions for LangGraph and LangChain code: graphs, agents, subagents, middleware, MCP tools in agents, persistence, streaming, tests |
| [mcp-servers](skills/mcp-servers/SKILL.md) | Conventions for FastMCP servers: layout next to a REST API, tool design, errors, transport, tests |

## Install

Install them with the [skills CLI](https://github.com/vercel-labs/skills) straight from GitHub:

```bash
npx skills add awa-projekt/skills                         # pick skills and agents interactively
npx skills add awa-projekt/skills --skill '*' -a <agent>  # all skills for one agent, e.g. claude-code, codex, cursor
npx skills add awa-projekt/skills --list                  # list the skills without installing
```

Add `-g` to install for your user instead of the current project. `npx skills update` fetches newer
versions.

## Layout

Each folder under `skills/` holds:

- `SKILL.md`: the skill, and reference files it points to for parts only some tasks need
- `examples/`: working code for the rules, with tests
- `scripts/`: checks the skill tells the agent to run
- `evals/`: tasks with checkable expectations, and prompts that should and shouldn't load the skill

## Checks

The examples and check scripts are tested in the environment from `pyproject.toml`; the skills are
validated against the [Agent Skills specification](https://agentskills.io/specification). CI runs
both.

```bash
uv run pytest
for s in skills/*/; do uvx --from "git+https://github.com/agentskills/agentskills#subdirectory=skills-ref" skills-ref validate "$s"; done
```

## License

Licensed under the [Apache License 2.0](LICENSE). Copyright 2026 awa-projekt.

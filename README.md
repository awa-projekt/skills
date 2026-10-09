# Agent Skills

Deutsch | [English](README.en.md)

[Agent Skills](https://agentskills.io) für den Bau von Agentensystemen: Ordner mit Anweisungen, die
ein Coding-Agent lädt, wenn eine Aufgabe sie braucht.

| Skill | Inhalt |
|---|---|
| [agent-architecture](skills/agent-architecture/SKILL.md) | Die Architektur vor dem Code festlegen: Workflow, einzelner Agent oder ein Multi-Agent-Muster, und die Regeln, die für jedes Multi-Agent-Design gelten |
| [langgraph-workflows](skills/langgraph-workflows/SKILL.md) | Konventionen für LangGraph- und LangChain-Code: Graphen, Agenten, Subagenten, Middleware, MCP-Tools in Agenten, Persistenz, Streaming, Tests |
| [mcp-servers](skills/mcp-servers/SKILL.md) | Konventionen für FastMCP-Server: Aufbau neben einer REST-API, Tool-Design, Fehler, Transport, Tests |

## Installation

Mit der [skills-CLI](https://github.com/vercel-labs/skills) direkt von GitHub installieren:

```bash
npx skills add awa-projekt/skills                         # Skills und Agenten interaktiv auswählen
npx skills add awa-projekt/skills --skill '*' -a <agent>  # alle Skills für einen Agenten, z. B. claude-code, codex, cursor
npx skills add awa-projekt/skills --list                  # Skills auflisten, ohne zu installieren
```

Mit `-g` werden die Skills für den eigenen Benutzer statt für das aktuelle Projekt installiert.
`npx skills update` holt neuere Versionen.

## Aufbau

Jeder Ordner unter `skills/` enthält:

- `SKILL.md`: den Skill und die Referenzdateien, auf die er für Teile verweist, die nur manche Aufgaben brauchen
- `examples/`: lauffähigen Code zu den Regeln, mit Tests
- `scripts/`: Prüfungen, die der Skill den Agenten ausführen lässt
- `evals/`: Aufgaben mit prüfbaren Erwartungen sowie Prompts, die den Skill laden sollen und solche, die ihn nicht laden sollen

## Prüfungen

Die Beispiele und Prüfskripte werden in der Umgebung aus `pyproject.toml` getestet; die Skills
werden gegen die [Agent-Skills-Spezifikation](https://agentskills.io/specification) validiert. Die
CI führt beides aus.

```bash
uv run pytest
for s in skills/*/; do uvx --from "git+https://github.com/agentskills/agentskills#subdirectory=skills-ref" skills-ref validate "$s"; done
```

Die Skills selbst sind auf Englisch geschrieben.

## Lizenz

Lizenziert unter der [Apache License 2.0](LICENSE). Copyright 2026 awa-projekt.

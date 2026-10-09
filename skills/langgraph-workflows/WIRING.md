# Handoffs, parallel branches and subgraphs

Wiring that only some graphs need. The rules every multi-agent graph follows are in `SKILL.md`.

## Handoffs

- Conversation steps that hand over to each other are one agent whose middleware switches prompt and tools on a `current_step` key: register all tools at build time, narrow them in `wrap_model_call`, and set `response_format` only in the final step. One agent keeps one conversation, one checkpoint and one set of limits.
- Separate agents with `Command(goto=..., graph=Command.PARENT)` are for steps that are genuinely different graphs. Such a handoff `Command` carries the triggering `AIMessage` and its paired `ToolMessage`, because providers reject a tool call without its result.
- Declare a handoff's targets with `destinations=`. It only affects the graph view, which otherwise shows no edge for the handoff.
- Agents that can hand off make no parallel tool calls: two handoffs in one turn contradict each other.

## Parallel branches and `Send`

- Every key written by parallel branches or `Send` has a reducer; without one, two branches writing the key in the same step raise `InvalidUpdateError`.
- A key a child returns in full gets no reducer, or the list doubles.

## Subgraphs and subagents

- Only the outermost graph gets a checkpointer. Subgraphs and subagents keep the default and use the parent's for the run; their own checkpointer would carry state from one call to the next, where a subagent should start fresh.
- Subagents called inside tools don't show in `get_state(subgraphs=True)` or the graph view. Add an agent as a node when it must be inspected, interrupted or resumed on its own.

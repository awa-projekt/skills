# Persistence and approval

How we keep a run's state and gate its side effects. For the checkpointer and `interrupt` APIs themselves, see LangChain's `langgraph-persistence` and `langgraph-human-in-the-loop` skills. Why side effects wait for approval is in the `agent-architecture` skill.

## Checkpoints

- Checkpoint every step to Postgres with `AsyncPostgresSaver`, in a schema of its own, on a pool configured like this:

  ```python
  SCHEMA = "agent"  # apart from the tables the app migrates

  @asynccontextmanager
  async def checkpointer(url: str) -> AsyncIterator[AsyncPostgresSaver]:
      async with AsyncConnectionPool(
          url,
          open=False,
          kwargs={
              "autocommit": True,         # setup() and every write commit on their own
              "prepare_threshold": 0,     # no prepared statements: they break behind a pooler
              "row_factory": dict_row,    # the saver reads rows by column name
              "options": f"-c search_path={SCHEMA}",
          },
      ) as pool:
          serde = JsonPlusSerializer(allowed_msgpack_modules=STATE_TYPES)  # see below
          saver = AsyncPostgresSaver(pool, serde=serde)
          await saver.setup()
          yield saver
  ```

- Allow-list the types that state carries in the checkpointer's serializer, `JsonPlusSerializer(allowed_msgpack_modules=[...])`, and run with `LANGGRAPH_STRICT_MSGPACK=true`. By default LangGraph loads any class it finds in a checkpoint and only warns. Anyone who can write to the checkpoint database could then run code in the service; strict mode loads only the listed types.
- Graph input and state are written to checkpoints as they are. Redact before `invoke`, and encrypt checkpoints (`EncryptedSerializer`) when state holds personal data.

## Approval

- Irreversible side effects run in deterministic code after approval (`interrupt()`, `HumanInTheLoopMiddleware`), not in a tool the model calls at will: the model proposes, code applies.
- Gate MCP tools on their annotations (`metadata["mcp"]["tool"]["annotations"]`), so a server marking a tool destructive puts it behind approval without a change in the agent.
- Test an approval by asserting the interrupt, then resuming with `Command(resume=...)` on the same `thread_id` ([TESTING.md](TESTING.md)).

## Deploys

A thread waiting on an interrupt resumes into the new code with its old state and its old position in the graph. To keep it working across deploys, add state keys as optional, and keep node names stable while threads wait on them.

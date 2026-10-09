# Testing

How we test graphs and agents. [examples/test_examples.py](examples/test_examples.py) does each of these against the example agents.

- Test graphs offline with a scripted chat model whose answer is a function of the conversation (`ScriptedChatModel` in [examples/testing.py](examples/testing.py)). A model that replays a fixed list of answers breaks as soon as parallel branches or subagents call it in a different order. One model can play every agent by picking its answer by the system prompt.
- Run structured output through both paths: the tool path (default) and the native path (`ScriptedChatModel(..., profile={"structured_output": True})`). `create_agent` picks the path from the model's profile, so production may take the one a test skipped.
- Assert model calls per agent and run (`ModelCalls` in [examples/testing.py](examples/testing.py)), so a change that adds a hop fails a test.
- Fake MCP servers with an in-process FastMCP server that serves the real tool names and payload shapes, run over HTTP (`serve_mcp` in [examples/testing.py](examples/testing.py)). With other names the agent's allowlist fails its start; with other payloads the test passes on data production never sends.
- Test an approval by asserting the interrupt, then resuming with `Command(resume=...)` on the same `thread_id`. Each test gets a fresh graph and its own `InMemorySaver`, so no test resumes another test's thread.
- Real-model tests are opt-in through an env var. The eval, not the unit tests, decides on prompt and architecture changes: a scripted model can't tell a better prompt from a worse one.

# Testing

How we test MCP servers. [examples/test_server.py](examples/test_server.py) does the first item, including the snapshot, against the example server.

- Test the MCP layer in memory with `fastmcp.Client(mcp)`: call every tool, check `isError` for domain errors, and snapshot `list_tools()` (names, descriptions, schemas) so contract changes show up in review.
- Test the mounted app once over HTTP, so a missing lifespan wrapper fails a test instead of the first deploy.
- Test the service against a real Postgres with a throwaway database per test, and mock only embeddings and external APIs. Mocked SQL accepts queries the real database rejects.
- Run all tests in CI, so a test module that fails to import fails the build instead of silently not running.
- Evaluate the server through the real agent (`MCPAdapter` on the in-process server) on real tasks, read the transcripts, and fix descriptions where the agent went wrong. Only a transcript shows whether the agent understood a description.

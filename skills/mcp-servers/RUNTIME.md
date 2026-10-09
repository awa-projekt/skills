# Transport and runtime

How the server runs. [examples/server.py](examples/server.py) shows the transport, the lifespan, sync tools and the health route.

- Streamable HTTP with `stateless_http=True` (`mcp.http_app(path="/", stateless_http=True)`), so any replica answers any call. LangChain's client opens a session per call anyway.
- Call the model provider directly instead of using sampling, take paths as parameters instead of roots, and log to stderr or OpenTelemetry instead of MCP logging. The spec has deprecated all three.
- Blocking DB work runs in sync tools, which FastMCP runs in a thread pool; blocking inside an `async def` stalls every other call on the server. One connection or transaction per call.
- Load heavy resources (embedding models, pools) in the lifespan, so the first agent call isn't the slow one. A plain HTTP health route reports readiness, since the new protocol has no `ping`.
- Auth: check that a token was issued for this server (issuer, audience), and call downstream systems with the server's own credentials. A caller's token passed on lets whatever holds it act as the user everywhere that token is accepted.
- Treat retrieved content as untrusted: a tool's text can carry prompt injection into the agent.

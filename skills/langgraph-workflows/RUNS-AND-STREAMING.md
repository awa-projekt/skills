# Runs and streaming

How a graph runs as a service.

## Runs

- A run has its own lifecycle: the agent keeps running if its client disconnects, and the client subscribes again instead of resubmitting. A resubmitted run does the work, and any side effects, twice.
- A run's id is its `thread_id`; with A2A, the task id, with tasks in a `DatabaseTaskStore` next to the checkpoints. A run whose process died resumes from its checkpoint, and the service resumes unfinished runs on startup:

  ```python
  snapshot = await graph.aget_state({"configurable": {"thread_id": task_id}})
  if snapshot.values and not snapshot.next:
      return snapshot.values                 # finished before the restart
  graph_input = None if snapshot.next else start(request)  # None continues from the checkpoint
  ```

- Use one standard protocol end to end, e.g. A2A, rather than custom polling endpoints. Clients, the run lifecycle and resubscription come with the protocol, and every UI reads the same events.

## Streaming

- Stream almost everything, and let each UI pick what it shows. A UI that needs one more event then needs no change to the service.
- One translator maps graph events to the protocol's events and decides what leaves the service. Private state keys are in the `values` stream too, so filtering happens in the translator, not in each UI.
- Tell agents apart in the stream by `metadata["lc_agent_name"]`, which `create_agent(name=...)` sets on everything inside the agent.
- New code streams with `stream_events(version="v3")`.
- Tools report progress through `runtime.stream_writer`, not in their result: the result goes into the model's context, and progress is for people.

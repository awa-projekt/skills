# Architecture decision record

Write one record per agent system, in the system's repository (e.g. `docs/architecture.md`). Start with the baseline and its eval score, then make one choice per decision below. Anything beyond the baseline names the eval result that justified it.

```markdown
# <System>: agent architecture

Baseline: <workflow or single agent>, <score> on <n> real tasks (<date>, <model>).

| Decision | Choice | Why (eval result or constraint) |
|---|---|---|
| Coordination | predefined workflow / supervisor / handoffs | |
| Task assignment | fixed / rule or classifier routing / dynamic planning | |
| Specialization | single agent / domain specialists / function pipeline | |
| Scheduling | sequential / parallel / mix | |
| Communication | shared typed state / messages between agents | |
| Knowledge | where each agent's knowledge comes from | |
| Verification | none / deterministic checks / independent critic | |
| Human involvement | where people approve, answer or take over | |
| Failure handling | stop / bounded retries / bounded replanning, and what happens at each cap | |
| State and memory | per run only / durable run state / memory across runs | |
| Traceability | what is logged for each decision | |
| Deliverable | what the run returns, in which schema | |
| Side effects | read-only / staged writes / direct actions, and who executes them | |
```

Update the record when an eval changes a decision, and note the date and the result.

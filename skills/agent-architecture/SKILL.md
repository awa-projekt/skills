---
name: agent-architecture
description: How to decide the architecture of an LLM agent system, from a workflow or single agent to multi-agent patterns (router, orchestrator-workers, supervisor, handoffs, evaluator-optimizer, hierarchical teams). Use when designing an agent system, deciding whether to add, split or merge agents, or reviewing an architecture proposal, in any framework. To build it in LangGraph, use langgraph-workflows.
---

# Agent architecture

This skill decides which design to build and owns the rules every multi-agent design follows. Once the design is chosen and it's time to write LangGraph code, load the `langgraph-workflows` skill, which says how to do these rules in LangGraph.

## Start from the baseline

- The baseline is the simplest setup that meets the hard constraints: a workflow in code with agents inside its steps, or a single agent with good tools.
- An extra agent must name the decision it makes at runtime. A component that only applies fixed rules is a workflow step, cheaper and testable as code.
- Measure the baseline on 20–50 real tasks before splitting anything. When a single agent already solves most of them, improve its tools, prompt and context instead: past roughly 45% single-agent success, adding agents measured worse (Kim et al. 2026).
- Change one decision at a time against the baseline, so you know what moved the score, and keep it only when the gain pays for it.
- Multi-agent costs about 3–15× the tokens of one agent, plus a hop of latency per level.

## Decide in this order

1. Steps known up front → a workflow in code: a sequential pipeline with deterministic gates, parallel branches for independent parts, a router for inputs in distinct categories. Agents work inside the steps.
2. A single agent failing on context (verbose tool output, long traces) → trim tool results, offload them to files, compact; then move the noisy read-only part into a subagent that returns a short report.
3. Failing on too many tools or instructions → merge overlapping tools, add tool selection or tool search, move rarely needed knowledge into skills. Split into specialists only if that still fails.
4. Breadth-first, decomposable, read-heavy work (research across sources, review under several lenses, competing hypotheses) → a supervisor or orchestrator-workers with parallel subagents; one lead checks and merges their results.
5. Sequential, tightly coupled or write-heavy work → one agent writes; the others only read, search or review.
6. Who talks to the user?
   - A specialist holds a multi-turn conversation → handoffs: one agent switching steps, separate agents only for genuinely different graphs.
   - One agent stays in charge and merges → subagents as tools.
   - The right handler is clear from the input → a router.
7. Parts need different permissions, data, owners or models → separate agents with their own tools. That is an organizational reason, not an accuracy gain.
8. Quality can be checked outside the model (tests, a validator, the system of record) → an evaluator-optimizer around any of the above, with an iteration cap and a fallback.
9. One answer must be reliable → parallel samples and a majority vote, not a debate: voting accounts for most of debate's gain, and debating agents can talk each other out of a correct answer.
10. More subagents than one supervisor routes reliably (about 7–10, or overlapping descriptions) → merge or flatten first, then hierarchical teams.

## Patterns

| Pattern | Use when | Avoid when | Main risk |
|---|---|---|---|
| Single agent | one domain, fewer than ~10–15 distinct tools | overlapping tools, a prompt that has become a handbook, tools that need security boundaries | tool overload, context rot |
| Sequential pipeline | known, stable, auditable process; high volume on cheap models | open-ended work, backtracking | early errors propagate |
| Router | distinct input categories with their own prompts, tools or knowledge | the handler only emerges while working; multi-turn specialists | misrouting is final |
| Parallelization | independent analyses, guardrails beside the main task, batch map-reduce, voting | dependent steps; most branches wasted | cost multiplies with branches |
| Orchestrator-workers | subtasks depend on the input and on earlier results; the plan must be inspectable | fixed process; short interactive tasks | planner quality, most model calls |
| Supervisor (subagents as tools) | several domains, parallel work, team-owned or third-party agents | few tools; specialists must talk to the user | telephone game, extra hop |
| Hierarchical teams | more agents than one supervisor routes | few agents; latency-critical paths | summarization loss per level |
| Handoffs | multi-turn conversations where the active specialist changes | batch and back-office work | handoff loops, growing context |
| Skills | one agent, many specializations loaded on demand | large per-domain context that needs isolation | context growth after loading, wrong picks past ~50–100 skills |
| Evaluator-optimizer | checkable criteria, high stakes | subjective criteria; a deterministic validator suffices | lenient judge, loop that doesn't converge |

## Rules for any multi-agent design

- Split by context, not by role. Planner → implementer → tester → reviewer chains spend more on coordination than on the work.
- One agent writes; extra agents add reading, search and review. Parallel writers need hard partitioning (their own files or records) and a checker, or their changes conflict.
- A lead checks the agents' results before they are merged or acted on: independent agents without that check amplified errors about 17×, against about 4× with one (Kim et al. 2026).
- The model proposes, code applies: side effects run in deterministic code or behind human approval, where they can be reviewed before they happen.
- Each delegation states the objective, the output format, the tools and the boundaries. Vague tasks produce duplicate work and gaps.
- Decide per agent what it sees: only its task by default, the full conversation for agents that decide on it, a clean context for reviewers. Anything else is noise the agent may act on, and a reviewer without the author's reasoning judges the work, not the argument.
- Subagents return structured reports, and the lead passes them on instead of paraphrasing: each paraphrase loses detail (the telephone game).
- Plans and routes are constrained to known agents and validated before they run; out-of-scope actions are rejected.
- Cap every loop at every level (calls per agent, rounds, handoffs, iterations, run budget) and define what happens at the cap: agents often miss that they repeat themselves or are done.
- Prefer deterministic checks to LLM judges: a judge in the loop is advice, and self-evaluation is no check.
- Runs that are long or wait for people need durable state from the start (checkpoints, resumable runs); retrofitting it changes every step.
- Log each coordination decision with its reason, so a bad result traces back to its cause.
- Re-test the architecture on each model upgrade and remove parts added for weaknesses the new model no longer has.

## Before you finish

- [ ] The baseline is named, with its score on real tasks (or the reason it couldn't be measured yet).
- [ ] Every agent beyond the baseline names the decision it makes at runtime and the eval result that justified it.
- [ ] Every loop has a cap and a defined outcome when the cap is hit.
- [ ] Every side effect says who executes it, and after which approval.
- [ ] The decision record is written in the format of [DECISION-RECORD.md](DECISION-RECORD.md).

The numbers in this skill (token cost, the 45% threshold, error amplification, ~7–10 subagents, ~50–100 skills) come from 2026 sources, checked on 2026-10-07. They depend on the models: re-check them with each model generation.

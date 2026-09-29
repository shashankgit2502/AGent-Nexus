# Step 5 — Mesh round + Consensus — done, stopped for review

## What I built (real primitives only, R2)

- `app/graph/context.py` — `MeshContext` + `MeshRunner` Protocol. Non-state dependencies (the agent factory/repo) are injected via LangGraph Runtime context (`context_schema`), the framework's DI seam — not stuffed into the checkpointed blackboard.
- `app/agents/mesh.py` — `FactoryMeshRunner`: thin glue resolving `agent_id → AgentConfig → factory.build() → run_agent_turn()`. Every load-bearing piece is a Step-3/4 primitive.
- `app/graph/nodes/agent_turn.py` — rewrote the stub into the real mesh node: Runtime-injected runner (real ReAct turn), stub fallback when no runner (keeps the foundation resume tests intact), idempotency guard keyed `(agent_id, round)` (§22.5), and graceful abstention — a failed agent becomes a confidence-0 contribution + an error event so the round still completes (§21.5), logged with full traceback, never silently swallowed.
- `app/graph/build.py` — `StateGraph(CollabState, context_schema=MeshContext)`.
- Consensus node + `Send()` fan-out + round loop were already present from the foundation slice and match §8; Step 5 wires real agents through them and tests the ranking order (the foundation only used uniform confidence).

## Root-cause fix included (R3)

`render_round_message` filtered to the current round, but during a round-N `Send()` fan-out the round-N contributions don't exist yet (they're produced in parallel — §23.4 "eventually visible next round"). Every round-≥2 agent was therefore told "opening round," blinding the mesh and defeating "emergence through iteration." Fixed to surface the previous round (`new previous_round_contributions helper`) + a regression test named for the cause. The frontend spec's round-cadenced animation (§9.10) assumes exactly this semantics.

## Acceptance ("Done when: 3-agent team runs multiple rounds, terminates by both rules, ranking correct")

- Converge-by-confidence: round-1 mean `0.60 < τ` → round 2; round-2 mean `≈0.92 ≥ τ` → converged; ranking `[C:2, B:2, A:2]`, output `C-r2`. ✅
- Terminate-by-max_rounds (`τ` unreachable): exactly 2 debate rounds. ✅
- Abstention + idempotency + stub-path. ✅
- `78/78` tests pass; `ruff` clean; `mypy` clean.

## Flags for your review (R6)

1. Mesh node is sync, not async. I verified against `langgraph 1.2.5` that a sync `.invoke()` cannot drive an async-only node, and the Step-2 acceptance tests use sync `.invoke()`. `Send()` already gives concurrency (threadpool), satisfying the locked "concurrency from Send()" decision. R5's async-client preference is deferred to when the stack is driven by `ainvoke` (Steps 8–9). Tell me if you'd rather I add a dual sync/async node now.

2. I changed one existing reviewed test (`test_round_message_*`) because its fixture encoded the buggy current-round semantics that can't occur in real fan-out. Flagging since it touches prior-approved code.

3. Agent built per turn, not cached. Caching by `(catalog_id, profile_id)` (NFR-2) is a deliberate later optimization; correctness doesn't depend on it.

## Verified packages (R1, pinned)

- `langgraph 1.2.5`
- `langchain 1.3.9`
- `langchain-core 1.4.7`
- `deepagents 0.6.10`
- `langgraph-checkpoint-postgres 3.1.0`

## Ready for Step 6

Ready for Step 6 (HITL + Synthesizer + End) on your go.
# Step 4 is complete and verified. Stopping here for review as instructed.

## Step 4 — Agent factory (real ReAct agents) ✅

Acceptance check (BUILD_PLAYBOOK Step 4 "Done when"): one real ReAct agent runs a turn — reads the blackboard, calls a tool, writes a contribution + confidence. Verified by `test_one_real_agent_runs_a_turn_...`, which builds a genuine `create_deep_agent` through the factory, drives its real ReAct loop offline (scripted tool-calling model), executes the lookup tool, and maps the structured output onto the blackboard.

Quality gates: `ruff clean` · `ruff format clean` · `mypy --strict clean` · `69/69 tests pass` (22 new + all Step 1–3, graph wiring untouched).

## What I built (real primitives only, R2)

| File | Role (ARCH ref) |
|--------|--------|
| `agents/contribution.py` | `ContributionOut` structured output, confidence 0–1 validated (§22.3) |
| `agents/config.py` | `AgentConfig` + `Capabilities` + repository, mirrors agents table (§22.1 / TECH §11.2) |
| `tools/registry.py` | capability→tool registry with injection seam for later-step tools (§10.5.4) |
| `skills/loader.py` | ordered filesystem-base→uploaded skill paths, last-wins, path-safety (§26.3/§26.4) |
| `agents/prompts.py` | static persona system prompt + per-round blackboard message (§22.2) |
| `memory/namespaces.py` | per-(team,agent) memory namespace (§25.1) |
| `agents/factory.py` | config → `create_deep_agent(...)` with model/tools/skills/memory/response_format (§22.2) |
| `agents/runtime.py` | `run_agent_turn/arun_agent_turn` → additive blackboard update (§22.2 output) |

## Decisions flagged for your review (R4/R6)

1. `create_deep_agent` over `create_agent` — your confirmed choice. It internally builds a `create_agent` ReAct agent and auto-wires the deepagents skills/memory/filesystem/summarization middleware, satisfying both locked decisions without hand-rolling middleware (R2).

2. R1 API drift handled — `deepagents 0.6.10`'s surface differs from the ARCH §10.1/§22.2 illustrative snippets (no `FilesystemMiddleware(routes=...)`; `skills=`/`memory=` are path lists). I adapted to the verified API and tightened the manifest pin to:

   ```text
   deepagents>=0.6.10,<0.7.0
   ```

   Locked decisions remain honored (tool-calling gate, `/memories/` StoreBackend, base+uploaded skills last-wins).

3. Fail-fast guards (R3, not band-aids): `memory_enabled` or uploaded skills without a store raise `AgentBuildError` rather than building a broken agent. Full memory/knowledge/uploaded-skill backend wiring is Step 7.

## Deliberate step boundary

I did not rewire the graph's fanned-out `agent_turn_node` — that integration (DI + the `(run_id, agent_id, round)` idempotency key, §22.5) belongs to Step 5 (Mesh round + Consensus). The Step-2 stub node and its integration tests are intact, keeping this slice reviewable.

---

### (a) Key concepts

- the factory/runtime split (persona cached in `system_prompt`, volatile blackboard passed per-turn at invoke);
- `ToolStrategy` structured output (`response_format → structured_response`);
- capability→tool assembly via an injectable registry;
- last-wins skill layering via path ordering.

### (b) Takeaways

- R1 caught a real API divergence before it became a bug;
- using `create_deep_agent` removed an entire class of hand-rolled middleware (R2);
- test doubles let us exercise the real ReAct loop with zero secrets/network.

### (c) Understanding check

Why is the per-round blackboard placed in the human message rather than the agent's `system_prompt` — what would break (or get expensive) if we baked it into `system_prompt` instead?

### (d) Suggested next step

Step 5 — wire `run_agent_turn` into the parallel `Send()` fan-out node with the idempotency key, then the confidence-weighted consensus math.
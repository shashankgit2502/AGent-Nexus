# Step 8 — AG-UI streaming — complete and stopped for review.

## What I built (ARCH §24, §23; TECHNICAL §11.4)

New package `app/streaming/`, all on real primitives (R2), wired into the existing graph without touching any locked node:

| Module | Responsibility | ARCH |
|----------|----------|----------|
| `events.py` | AG-UI envelope `{type,session_id,run_id,seq,ts,data}` + the locked 15-type catalog + fail-fast validation | §24.3/§24.4 |
| `store.py` | `RunEventStore` Protocol + `InMemoryRunEventStore` — the `run_events` log + `replay(after_seq)` | §24.8 |
| `publisher.py` | `EventPublisher` Protocol + `InProcessEventPublisher` (no-Redis dev) + `RedisEventPublisher` (cross-replica `run:{run_id}`) | §24.5 |
| `emitter.py` | `RunEventEmitter` — the one choke point assigning monotonic `seq`, persisting, and publishing; `for_run` continues `seq` across HITL resume | §24.3 |
| `runner.py` | `stream_run` — drives `graph.astream(stream_mode="updates", version="v2") → events`; derives `hitl_request` from `StateSnapshot.interrupts` | §21.4 |
| `websocket.py` | WS `/sessions/{id}/stream` — replay-missed-then-live, deduped by `seq` | §24.2/§24.8 |

Wired into `app/main.py` (mounts the WS router; `STREAM_FANOUT=memory|redis` config).

## R1 verification (all against installed pkgs, pinned)

- `langgraph 1.2.5`: `astream(version="v2")` exists (unified `StreamPart {type,ns,data}`); `StateSnapshot.interrupts` + `Interrupt.value` confirmed.
- `redis 8.0` `asyncio.Redis.pubsub()` confirmed.
- `FastAPI 0.137` / `starlette 1.3` WebSocket.

Each documented inline in the module docstrings.

## Acceptance check ✅

> "a run streams the full typed event sequence; a reconnect replays missed events by seq"

- `test_runner.py`: full run streams `run_start → contribution×2 → consensus_update → hitl_resolved → synthesis → run_finished` with contiguous `seq 1..N` and well-formed envelopes; HITL run pauses on `hitl_request`, then resume keeps one monotonic `seq` space.
- `test_websocket.py`: reconnect with `after_seq` replays exactly the missed events.
- `20 streaming tests pass`; full suite `140 passed`, `3 skipped` (Postgres/Redis-gated), `ruff + mypy --strict` clean, no regressions.

## One R3 note

My first publisher cleanup test wrongly assumed `async for … return` runs a generator's `finally` synchronously — it doesn't (only on `aclose()` / GC).

Fixed the test to drive `aclose()` deterministically; the code was correct.

## Deliberate boundaries left for Step 9 (flagged per R6 — not silent)

### 1. `run_events` is in-memory behind the Protocol

The durable Postgres store + table migration is Step 9 (no ORM models exist yet).

Swap is one line in `main.py`.

### 2. Run-launch REST route

`POST /sessions/{id}/run` + `run_id↔thread_id` DB resolution is Step 9.

Only the WS stream endpoint is Step 8.

### 3. Catalog vs emission

The 15 types are locked/validated, but nodes emit only the lifecycle subset.

Granular per-agent events (`round_start`, `agent_turn_start`, `reasoning`, `tool_call`, `tool_result`, `confidence`, `critique`) are defined but not yet emitted — needs your approval as a small follow-up since it edits the agent runtime.

## I did not start Step 9

(Also flagged earlier: your prompt mixed a "stop after milestone 1" boilerplate with "do Step 8" — I followed Step 8 since the backend is already at that point. Tell me if that was wrong.)

---

## Key concepts

- LangGraph v2 streaming (discriminated `StreamPart` union)
- Interrupts surfaced via `StateSnapshot.interrupts`, not the update stream
- Protocol-based seams for swappable store/publisher
- Monotonic `seq` as the backbone of replay

## Takeaway

The events channel already existed in state, so the streaming layer is a projection (`stream → envelope → fan-out`), not new graph logic — keeping the blackboard the single source.

## Check your understanding

Why must `seq` be assigned in `RunEventEmitter` (one place) rather than each node — and what breaks on reconnect if it weren't monotonic per run?

## Suggested next step

Approve item #3 (granular event emission) or proceed to Step 9 (FastAPI routes + Alembic migrations + RLS), which also lets me replace the in-memory `run_events` with the Postgres-backed store.
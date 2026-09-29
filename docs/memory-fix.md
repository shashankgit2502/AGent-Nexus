# RCA: why Memory Explorer is empty

## Reproduce — the two call paths

### Write path (agent → store)

```text
agent_turn_node
  → FactoryMeshRunner.run (mesh.py:58)
  → run_agent_turn (sync agent.invoke, runtime.py:301)
```

The factory does mount the persistent `/memories/` `StoreBackend`, namespaced:

```text
("team", t, "agent", a)
```

and passes:

```python
memory=["/memories/AGENTS.md"]
```

(`factory.py:176-180`)

Under the hood `create_deep_agent` adds both:

- `FilesystemMiddleware` (gives `write_file` / `edit_file`)
- `MemoryMiddleware`

whose system prompt invites the model to:

> "save new knowledge by calling edit_file"

(`deepagents/middleware/memory.py:111-120`)

---

### Read path (store → API → UI)

```text
GET /agents/{id}/memory
```

→ `MemoryService(app.state.memory_store).read / read_shared`

(`api/memory.py:45-48`)

over the same store table the agents use (`main.py:93-97`), mirroring the exact `CompositeBackend` route prefix-strip and §25.1 namespaces (`service.py:55-74`, `namespaces.py:32-44`).

---

# Root cause — nothing ever writes memory

The read path is correct and is not the bug.

Namespaces match §25.1, the composite-route key translation matches, and the read endpoint shares the agents' physical store table.

The Step-7 recall test proves the read side works — but only because it seeds the write by hand:

```python
MemoryService.write(...)
```

to simulate:

> "a prior run persisted a memory"

then scripts the model to call only `ContributionOut`.

(`test_recall.py:67-84`)

That hand-seed is the tell.

---

## The write side is never driven

A grep of the whole `app/` shows:

```python
MemoryService.write
```

is called nowhere in production.

`api/memory.py` only ever calls:

- `read`
- `read_shared`

So memory is written only if a mesh agent spontaneously calls:

```text
edit_file
```

during its turn.

It won't, because:

### The turn is engineered to exit via `ContributionOut`

Our persona output contract hard-orders:

> "You MUST finish your turn by calling the ContributionOut tool… a turn that ends without calling ContributionOut is discarded"

(`prompts.py:26-39`)

The ReAct loop terminates on that structured-output call:

```text
runtime.py:223-235
```

and the round task framing never asks the agent to record a durable learning.

`deepagents`' "save via edit_file" guidance is aimed at user-preference/feedback capture and loses to our explicit exit contract.

---

### No consolidation step exists

ARCH §10.2 / §25.3 call for:

```text
during-conversation writes
optional background consolidation
```

Neither is wired.

Step 7 built the read side and left the write side undriven.

Result:

```text
private memory namespace stays empty
```

→ Explorer's "private" is empty.

---

## Team-shared is empty by construction

The namespace:

```text
("team", t, "shared")
```

has no writer anywhere — not even a seed.

§25.1 says it is written by:

```text
admins / endorsed memories
```

and there is no admin-write or endorsement flow.

So:

```text
shared empty
```

is expected-by-omission, not a glitch.

---

# Two things I deliberately did not pin the blame on (honesty per R3)

## 1. Sync-vs-async store mismatch

A real fragility, not the confirmed cause.

The factory is handed the async:

```python
app.state.store
```

(`run_service.py:316`)

but the mesh invokes the agent synchronously, and `StoreBackend`'s sync ops call sync:

```python
store.get
store.put
```

(`store.py:500,577,584`)

On `AsyncPostgresStore` those route through:

```python
run_coroutine_threadsafe
```

and `_check_loop` only raises if called on the store's own loop thread (`batch.py:33-53`).

Since LangGraph runs sync nodes in worker threads, it most likely works.

So I won't claim it as the cause.

But it's a latent landmine:

A memory write that does happen on the loop thread would raise.

The clean fix is to drive the mesh memory ops through the async path:

```text
arun_agent_turn
aget
aput
```

---

## 2. Read response shape vs FRONTEND_SPEC §14

Even once writes exist, the endpoint returns one:

```json
{
  "private": "...",
  "shared": "..."
}
```

blob string (the whole `AGENTS.md`), and the frontend just fetches it (`use-memory.ts`).

§14 requires:

- structured sections (`Facts` / `Experiences` / `Session Learnings` / `Summaries`)
- team → agent drill-down
- search
- delete
- pin

i.e. per-item Store records, not one file.

So:

```text
make it real
```

is a superset of:

```text
enable writes
```

---

# Concepts / takeaways

## Key concept

`deepagents` memory is opt-in by the model (`edit_file`), not automatic.

A structured-output exit contract that ends the turn deterministically will starve it.

The read plumbing can be flawless while the store stays empty.

---

## Takeaway

The empty Explorer is:

1. A write-trigger gap.
2. A read-contract gap (blob vs §14 searchable items).
3. A structurally-unwritten shared namespace.

---

## Check for you

Given the turn ends on `ContributionOut`, which is more robust for persisting:

> "what this agent learned this run"

- asking the model to also call `edit_file` mid-turn, or
- a deterministic post-run consolidation node?

(My reasoning is in the options below.)

---

## Next step

Pick the write-trigger approach and the read-storage model, then I'll write it:

- tests first
- R3 regression on:

```text
a run persists a memory
```

Before I build anything, two decisions genuinely change the design (R6 / §25.3), so let me get your call.


---


# FIXES

# RCA → first slice complete

## RCA verdict (recap)

Memory Explorer is empty because nothing writes memory — the read path is correctly built, but `MemoryService.write` is never called in production; mesh agents exit each turn via `ContributionOut` and never persist, and no consolidation step exists. Team-shared has no writer by design.

## M1 — memory record store/service (this slice): ✅

### `namespaces.py`

Added `agent_memory_items_namespace` →

```text
("team", t, "agent", a, "memories")
```

a sub-namespace so Explorer records don't pollute the agent's `ls /memories/`.

### `items.py`

`MemoryItem` + `MemoryItemStore`

- `write_item`
- `get_item`
- `list_items`
- `set_pinned`
- `delete_item`

over the real `BaseStore` primitive (R2).

Ordered:

```text
pinned-first
then newest
```

(strict seq, not wall-clock)

Supports:

- filter by kind
- filter by pinned
- deterministic substring search
- pagination

### `test_items.py`

9 tests, written first (`RED → GREEN`).

### Gate

- `14/14` memory tests pass (no regression)
- `ruff` clean
- `mypy` clean

---

## Deliberate seams flagged for later slices (not silently skipped)

### Semantic search

Needs the Store configured with a pgvector embedding index (sticky-dimension decision, §9.5).

M1 uses substring search.

The:

```text
list
filter
paginate
```

surface stays stable when semantic lands.

### M2 synchronization

M2 must keep:

```text
/memories/AGENTS.md
```

(deepagents recall)

in sync with records.

Also note:

```text
StoreBackend.write
```

refuses overwrite, so the rollup will use:

```text
delete + write
```

or raw:

```text
store.put
```

---

# Concepts / takeaways

## Concept

Record CRUD (mutable, pin-toggle) wants the raw `BaseStore`, not deepagents' file-semantics `StoreBackend` — picking the right real primitive is still R2-compliant.

## Takeaway

Strict seq ordering avoids non-deterministic sorts when the wall clock ties rapid writes.

## Check for you

In M2, when the consolidation node summarizes a memory-enabled agent's contributions, should it write:

- one summary record per run,

or also

- split out fact/experience records?

(Affects how the §14 sections populate.)

## Next step (M2, awaiting your go-ahead)

Build the post-run consolidation node:

```text
summarize each memory-enabled agent's contributions
    → via the cheap model
    → write_item
    → refresh the AGENTS.md recall rollup
```

and add the integration test:

```text
a memory-enabled run persists a recallable memory
```


# M2 — post-run consolidation node (write trigger): implemented

The fix for the Item 3 RCA ("nothing writes memory") is now wired.

## `consolidation.py` — `MemoryConsolidator`

After a run, for each memory-enabled agent that did real work:

- skips non-memory agents
- skips abstentions
- skips `NONE` summaries

the cheap non-tool model distils its contributions into one durable experience record (`write_item`) and refreshes the:

```text
/memories/AGENTS.md
```

recall rollup so the next session recalls it.

Pure helpers:

- `render_consolidation_messages`
- `render_recall_markdown`

are unit-tested in isolation.

---

## `service.py`

Added:

```python
MemoryService.upsert
```

(overwrite via `upload_files`, since `write` is create-only)

to regenerate the rollup through the same composite backend (no key drift).

---

## `nodes/consolidation.py` + `build.py`

A thin consolidation node placed:

```text
synthesizer
    → consolidation
    → end_node
```

Characteristics:

- no-op when no consolidator is injected
- a failure is logged and the finished run still completes cleanly

(R3 — architected, not swallowed)

It:

- writes no blackboard channels
- emits no AG-UI event

(§24.4 contract untouched)

---

## `context.py`

New `Consolidator` DI seam:

```text
runner
synthesizer
consolidator
```

(mirrors runner/synthesizer)

`snapshot.py` builds it at the composition root, reusing:

- the synthesizer's model
- the agents' store

---

## Gate so far

The M2 tests:

```text
7 passed
```

Combined:

```text
tests/graph + tests/memory
```

results:

```text
54 passed
1 skipped
```

Quality gates:

```text
ruff clean
mypy clean
```

on all changed files.

---

## End-to-end recall closure test

Passes.

Flow:

```text
consolidation writes
    → fresh agent built afterward
    → recalls the memory in its prompt
```

This closes the §10.1 acceptance path with a real run-driven write path rather than the earlier hand-seeded test fixture.

---

## Decision I made

(You said "proceed" without picking.)

M2 writes:

```text
one experience (episodic) record
per memory-enabled agent
per run
```

The other §14 sections populate later:

- `fact` via deferred agent self-write
- `session_learning` later
- `summary` later

The kinds are already supported by the M1 store.

Flag if you'd prefer a different default.

---

## Status

Waiting on the full-suite result before I call M2 done.

I'll report the moment it finishes, then stop for your review before:

```text
M3 — the §14 read/CRUD API + docs
```
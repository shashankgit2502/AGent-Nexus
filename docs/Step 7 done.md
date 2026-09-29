# Step 7 is complete and green. Stopping for review per the playbook.

## Step 7 — Memory + Knowledge ✅

### Acceptance check (BUILD_PLAYBOOK Step 7 "Done when")

- "search_knowledge returns only that team/agent's chunks" → `tests/knowledge/test_pgvector_integration.py` runs the whole path against the live pgvector container (real `IngestionService → real PGVector → real filter`): agent 1 sees team-shared + own private, not agent 2's private, not team B; the "only specified sources" toggle restricts correctly. Passed.
- "an agent recalls a prior-session memory" → `tests/memory/test_recall.py`: a memory persisted via `MemoryService` (session 1) is loaded into a freshly-built agent's prompt (session 2) through real deepagents `MemoryMiddleware`. Passed.

Full suite: `122 passed`. `mypy app`: clean. `ruff` on all Step-7 files: clean.

## What I built (real primitives only — R2)

| Area | Files |
|--------|--------|
| Embeddings resolution (`init_embeddings`, §9.5) | `app/models_layer/embeddings.py` (+ `NotAnEmbeddingModel`) |
| Knowledge: store / metadata+filter / ingest / retriever | `app/knowledge/{store,metadata,ingest,retriever,__init__}.py` |
| Memory service + shared namespace (§10/§25) | `app/memory/service.py`, `app/memory/namespaces.py` |
| Config: `org_id` + `KnowledgeConfig` (RAG scoping) | `app/agents/config.py` |
| Tests | `tests/knowledge/*`, `tests/memory/*`, `tests/models_layer/test_embeddings.py` |

## Two R3 root-cause findings (fixed at the root, with regression tests — no patches)

### 1. PGVector `$in [None, …]` fails (`langchain_postgres 0.0.17`)

The spec's illustrative:

```python
agent_id: {"$in": [None, agent_id]}
```

raises `NotImplementedError` on a null.

Fix: store no null — tag chunks:

```text
scope="team" | "agent"
```

and filter:

```python
{"$or": [{"scope": "team"}, {"agent_id": …}]}
```

Same intent, verified live.

(Spec's own caveat: re-verify filter syntax at build time.)

### 2. CompositeBackend strips its `/memories/` route prefix

`MemoryService` originally used a standalone `StoreBackend` → keyed files at:

```text
/memories/AGENTS.md
```

while the agent reads via the composite →:

```text
/AGENTS.md
```

They never met → no recall.

Fix: `build_memory_backend()` — one shared composite both the service and factory use, so keys can't drift.

## Deliberately deferred (flagged, not silently skipped)

- URL/DB loaders raise a clear `UnsupportedSourceKind` (need unpinned deps — R1). File + team_doc implemented.
- Semantic memory indexing (pgvector-indexed `PostgresStore`): recall here is file-based (deepagents loads the whole memory file), which meets the acceptance; configuring the Store's embedding index is tied to seeding the default embedding profile (Step 9 data migration).
- Composition-root wiring (registering `rag` on a live registry, the ingestion worker/queue, building the knowledge PGVector in `main.py`): lands with the routes in Step 9 — consistent with how Steps 4–6 left composition to later. `main.py` is untouched.
- HNSW index on knowledge vectors (TECHNICAL §11.5) + background consolidation (§25.3) → Step 9 / optional.

## Pre-existing (not mine, not touched)

`ruff` flags:

- `alembic/env.py` (import order)
- `tests/models_layer/test_resolver.py` (format)

both outside this changeset.

Want me to fix them separately?

---

# 🎓 Learning wrap-up (per CLAUDE §2A)

## (a) Key concepts

- RAG ingestion pipeline (`load → split → embed → store`)
- Tenant isolation as a metadata filter (the security boundary lives in the query, not separate tables)
- The difference between short-term checkpointer memory and long-term Store memory
- deepagents' logical-path vs physical-store-key translation

## (b) Takeaways

- Illustrative spec code is a starting point, not gospel — R1 verification against the pinned version caught a filter that would have shipped broken.
- A "works in isolation" component (`MemoryService`) can still be wrong if it doesn't address state the same way its counterpart does.

## (c) Check for you

Why does tagging chunks with `scope="team"` and using `$or` give the same security guarantee as the spec's `$in [None, agent_id]` — and why is it actually safer here?

## (d) Suggested next step

Review this slice, then Step 8 — AG-UI streaming (event emission from the graph + WebSocket + Redis fan-out + `run_events` replay), which makes everything we've built observable in the Session Workspace.

I'll wait for your review before starting Step 8.



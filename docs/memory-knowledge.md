Chunking needs no embedding model — that's just text splitting (`RecursiveCharacterTextSplitter`). Embeddings come after chunking, when chunks are turned into vectors. So "embedding model for chunking" is two separate steps:

```text
load → split (NO model) → embed (needs model) → pgvector
```

Is the embedding side done? Mostly — here's the honest split:

| Piece | Status |
|--------|--------|
| EmbeddingsResolver (catalog embedding model → real `init_embeddings`) | ✅ Built, real, tested |
| PGVector embeds chunks on `add_documents` via the injected embeddings | ✅ Built |
| A live embedding model running in the pipeline | ❌ Not yet wired |

## Why not wired live yet: two deliberate reasons —

### 1. No composition root until Step 9

`main.py` doesn't instantiate the knowledge PGVector store yet (same as Steps 4–6 left wiring to later).

Building it at startup requires a real connection + the default embedding profile, which Step 9 seeds via a data migration (TECHNICAL §11.8).

Wiring a live model now would mean hardcoding something Step 9 owns.

### 2. The acceptance check doesn't need a real provider

Tests use `DeterministicFakeEmbedding` (offline, no API key) so the isolation logic is proven against real pgvector without burning tokens or needing a key.

The embedding code path is real; only the model instance is a deterministic fake in tests.

## So:

The resolver and the embed hook are real and done; plugging in an actual OpenAI/Ollama embedding model is the Step-9 composition step:

```text
seed default embedding profile
    → resolve it
    → pass to build_knowledge_vectorstore
```

Want me to wire a live embedding model into `main.py` now instead of deferring?

It's a small change, but it pulls Step 9's default-embedding-profile decision forward.
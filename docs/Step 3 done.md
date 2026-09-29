# Step 3 is complete and green. Stopping here for your review per R6.

## What I built — Step 3: Model Resolution Layer (ARCH §9 / §27)

The four-layer chain resolving an agent's model selection into a live LangChain chat model, all behind repository Protocols so the in-memory stores (tests/dev) swap cleanly for the SQLAlchemy stores in Step 9.

| File | Role |
|------|------|
| `app/models_layer/translate_params.py` | NormalizedParams + `translate_params()` — per-provider kwarg mapping/dropping (highest-bug-risk, ARCH §20 note 3) |
| `app/models_layer/connections.py` | Layer 1: `LLMConnection` + repo (`api_key_ref`, never the key) |
| `app/models_layer/catalog.py` | Layer 2: `CatalogModel` + repo (`supports_tools` flag) |
| `app/models_layer/profiles.py` | Layer 3: `InferenceProfile` + repo (Q1 default model + params) |
| `app/models_layer/resolver.py` | `ModelResolver.resolve()` → `init_chat_model`; tool-gate, provider mapping, caching |
| `app/models_layer/validation.py` | SSRF guard (`validate_base_url`) + validation probe (`probe_model`, §27.3) |
| `app/models_layer/errors.py` | Typed errors (no bare-except band-aids, R3) |
| `app/core/secrets.py` | `SecretResolver` Protocol + env/in-memory impls (§9.4) |

Locked behaviours honoured: Q1 override-wins-over-default; the §9.3 `supports_tools` hard gate (`require_tools=True` for mesh agents, relaxed for the Synthesizer); secrets resolved by reference only; SSRF allowlist; (`catalog_id`, `profile_id`, `require_tools`) caching with `invalidate()`.

## Key R1 findings (verified against the installed versions, not memory)

- `langchain 1.3.9` / `langgraph 1.2.5` / `langchain-core 1.4.7` / `langchain-openrouter 0.2.3`.
- `init_chat_model`'s native provider registry includes `openai`, `anthropic`, `azure_openai`, `ollama`, `openrouter` — but not `openai_compatible`. An OpenAI-compatible endpoint is just the OpenAI client with a custom `base_url`, so the resolver maps `openai_compatible → model_provider="openai"`.
- Confirmed real kwarg names per client: Ollama takes no `api_key`/`max_tokens`; OpenAI reasoning models reject `temperature`/`top_p` (→ `reasoning_effort`); Anthropic extended thinking needs `thinking={...}` + `max_tokens` above the budget and no sampling.

## Acceptance check (BUILD_PLAYBOOK Step 3) — ✅

- `resolve_model()` returns a working `init_chat_model` for OpenAI, Ollama, OpenRouter (+ `openai_compatible`, Anthropic-reasoning) — asserted as the correct concrete client class with the right `base_url`/key/params, no network.
- `translate_params` is unit-tested per provider.
- Full suite: 47 passed; `ruff` clean; `mypy --strict` clean on the new modules. One failure during the run was a test-fixture defect (OpenAI connection missing a key), root-caused and fixed — not a resolver bug.

## One deliberate scope decision to flag

I did not implement `discovery.py` (`models.dev` / `/v1/models`) or embeddings resolution. Neither is in the Step 3 "Build" list — discovery is a Settings concern and embeddings wiring belongs to Step 7 (Knowledge/Memory). The `model_type="embedding"` field exists on the catalog so the seam is ready. Tell me if you'd rather I pull embeddings resolution forward.

---

## Teaching wrap-up (§2A)

### Key concepts

- The adapter/anti-corruption pattern (`translate_params` shields the app from non-portable provider params).
- The repository pattern (resolver depends on Protocols, not storage).
- Reference-based secrets (DB holds `api_key_ref`, not keys).
- SSRF (why a user-supplied `base_url` is dangerous).

### Takeaways

- R1 caught a real trap — trusting training-data memory would have had us pass `model_provider="openai_compatible"` and fail at runtime.
- Verifying against the installed package is the authoritative move.

### Comprehension check

Why does the resolver pass no `api_key` for an Ollama connection even if one were configured — and what specifically would break if we passed it anyway?

### Suggested next step

Step 4 — the Agent factory (`config → create_agent(model=resolve_model(...), tools, skills, memory)`), putting one real ReAct agent into the mesh node.

Shall I proceed, or would you like to review/adjust Step 3 first?
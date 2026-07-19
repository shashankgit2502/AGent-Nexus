# TECHNICAL.md — NEX AGI Setup & Structure

Companion to `CLAUDE.md` (rules), `ARCHITECTURE.md` (backend design), `FRONTEND_SPEC.md` (frontend design).

> **Version policy:** every package below is "**latest stable, pinned at install**." Per `CLAUDE.md` R1, verify current versions and v1 import paths via the LangChain docs MCP / Context7 / web before installing — do not copy versions from memory.

---

## 1. Prerequisites
- **Python** 3.12+
- **Node** 20+ and **pnpm**
- **Docker** + Docker Compose (Postgres+pgvector, Redis)
- **uv** (Python package/project manager) — fast, reproducible
- A **secrets store** for provider API keys (env for local; a real secrets manager in prod — never commit keys)

---

## 2. Repository structure (monorepo)

```
nex-agi/
├── CLAUDE.md                  # constitution (always read by Claude Code)
├── ARCHITECTURE.md            # backend design (source of truth)
├── FRONTEND_SPEC.md           # frontend design (source of truth)
├── TECHNICAL.md               # this file
├── README.md
├── docker-compose.yml         # postgres+pgvector, redis
├── Makefile                   # dev shortcuts
│
├── backend/
│   ├── pyproject.toml         # uv-managed; deps grouped
│   ├── .env.example
│   ├── alembic/               # DB migrations
│   ├── app/
│   │   ├── main.py            # FastAPI app factory + lifespan (checkpointer/store setup)
│   │   ├── core/              # config (pydantic-settings), logging, security/secrets, deps
│   │   ├── db/                # SQLAlchemy 2.0 models, session, base
│   │   ├── schemas/           # Pydantic v2 request/response + domain DTOs
│   │   ├── api/               # FastAPI routers (thin); one module per resource (ARCH §14)
│   │   │   ├── teams.py  agents.py  sessions.py  providers.py  knowledge.py  memory.py
│   │   ├── graph/             # LangGraph: state.py (CollabState), build.py, nodes/, routing
│   │   │   ├── state.py       # CollabState + reducers (ARCH §6)
│   │   │   ├── build.py       # build_collab_graph (ARCH §7)
│   │   │   ├── nodes/         # orchestrator.py, agent_turn.py, consensus.py, hitl.py, synthesizer.py, end.py
│   │   ├── agents/            # factory.py (config→create_agent, ARCH §22), runtime, prompts
│   │   ├── middleware/        # guardrails, context-engineering, memory wiring (deepagents)
│   │   ├── consensus/         # confidence math, weighted vote (ARCH §8)
│   │   ├── models_layer/      # MODEL RESOLUTION (ARCH §9/§27)
│   │   │   ├── connections.py catalog.py profiles.py resolver.py translate_params.py
│   │   │   ├── discovery.py   # models.dev + provider /models endpoints
│   │   │   ├── validation.py  # validation probe
│   │   ├── memory/            # deepagents memory config (StoreBackend at /memories/), namespaces
│   │   ├── knowledge/         # ingestion (load→split→embed), pgvector store, retriever tool (ARCH §10.5)
│   │   ├── skills/            # SKILL.md loader, base+uploaded layering (ARCH §26)
│   │   ├── tools/             # predefined tool registry (web search, code, doc/chart/image, search_knowledge)
│   │   ├── streaming/         # AG-UI events, websocket handler, redis pub/sub (ARCH §24)
│   │   └── a2a/               # A2A message contract over the blackboard (ARCH §23)
│   └── tests/                 # pytest; mirrors app/ ; fixtures + mock AG-UI streams
│
├── frontend/                  # Next.js 15 (see FRONTEND_SPEC §19 for feature tree)
│   ├── package.json
│   ├── .env.example
│   ├── app/                   # routes (FRONTEND_SPEC §6)
│   ├── components/            # shadcn primitives
│   ├── features/              # layout, teams, agents, session, providers, knowledge, memory
│   ├── store/                 # zustand: session store + AG-UI event reducer
│   ├── lib/                   # agui websocket client, api client, types
│   ├── types/                 # shared AG-UI + domain types (mirror ARCH §24)
│   └── mocks/                 # AG-UI event replayer + fixtures (build Session Workspace against this)
│
└── infra/                     # optional: prod compose, k8s, etc. (deferred)
```

---

## 3. Backend setup

### 3.1 Dependencies (grouped; pin latest stable, verify per R1)
**Runtime/API:** `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`
**DB:** `sqlalchemy>=2`, `asyncpg`, `alembic`
**LangChain/Graph v1:** `langchain`, `langgraph`, `langgraph-checkpoint-postgres`, `langchain-postgres` (PGVector), `langchain-text-splitters`, `deepagents`
**Knowledge ingestion (ITEM 2):** `pypdf`, `python-docx`, `openpyxl`, `python-pptx` (office formats, Slice B); `pytesseract` + `Pillow` (image OCR, Slice C — images + embedded images are also captioned by a `supports_vision` catalog model via the model-resolution layer). Slice D adds `beautifulsoup4` (URL fetch → HTML→text, SSRF-guarded) and `unstructured` (long-tail formats — rtf/odt/epub/eml/…) plus the read-only DB connector (`psycopg`, SELECT-only). All pinned, R1-verified. Full universal parsing needs **system binaries** shipped in `backend/Dockerfile` (`poppler-utils`, `tesseract-ocr`, `libreoffice`, `libmagic1`) — without them, those paths degrade to a clear `failed` status (or vision-only captioning when tesseract is absent), never a silent hang. `unstructured` runs in an **isolated subprocess** (it can segfault on adversarial input) so a crash fails one source, not the worker.
**Providers:** `langchain-openai`, `langchain-anthropic`, `langchain-ollama`, `langchain-openrouter`, `langchain-google-genai`, `langchain-aws` (as needed)
**Infra:** `redis`
**Obs:** `langsmith`
**Dev:** `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `httpx`, `pre-commit`

```bash
cd backend
uv init && uv add fastapi "uvicorn[standard]" pydantic pydantic-settings \
  "sqlalchemy>=2" asyncpg alembic redis langsmith \
  langchain langgraph langgraph-checkpoint-postgres langchain-postgres \
  langchain-text-splitters deepagents \
  langchain-openai langchain-anthropic langchain-ollama langchain-openrouter
uv add --dev ruff mypy pytest pytest-asyncio httpx pre-commit
```

### 3.2 Database
- Use the **pgvector-enabled Postgres image** (§5). On first run: `CREATE EXTENSION IF NOT EXISTS vector;`
- LangGraph: call `checkpointer.setup()` and `store.setup()` at app startup (FastAPI lifespan).
- App tables (ARCH §13) via **Alembic** migrations: `alembic revision --autogenerate -m "init"` → `alembic upgrade head`.
- **Full production schema → §11.** It supersedes the ARCH §13 sketch (adds tenancy, identity/RBAC, soft-delete, audit, indexes, RLS).

### 3.3 Run
```bash
docker compose up -d              # postgres+pgvector, redis
cd backend && alembic upgrade head
uv run uvicorn app.main:app --reload
```

---

## 4. Frontend setup
```bash
cd frontend
pnpm create next-app@latest .      # TS, App Router, Tailwind
pnpm add @xyflow/react framer-motion zustand @tanstack/react-query
pnpm dlx shadcn@latest init
pnpm dev
```
- **React Flow** is published as `@xyflow/react` — verify the import at install (R1).
- Build the **Session Workspace against `mocks/` (AG-UI replayer) first** (FRONTEND_SPEC §18) — no live backend needed.
- Keep `types/` AG-UI definitions in lockstep with `ARCHITECTURE.md` §24.

---

## 5. docker-compose.yml (starter)
```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: nex
      POSTGRES_PASSWORD: nex
      POSTGRES_DB: nexagi
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  redis:
    image: redis:7
    ports: ["6379:6379"]
volumes: { pgdata: {} }
```

---

## 6. Environment variables

**backend/.env.example**
```
APP_ENV=local
DATABASE_URL=postgresql+asyncpg://nex:nex@localhost:5432/nexagi
LANGGRAPH_PG_URL=postgresql://nex:nex@localhost:5432/nexagi   # checkpointer/store (sync driver)
REDIS_URL=redis://localhost:6379/0
# Observability
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=__set_via_secrets__
# Provider keys are NOT stored here in prod — use a secrets manager.
# Local dev only, and never commit real values:
OPENAI_API_KEY=__local_only__
ANTHROPIC_API_KEY=__local_only__
```

**frontend/.env.example**
```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

> Secrets: local via `.env` (git-ignored); production via a secrets manager referenced by `api_key_ref` (ARCH §9.4). Never commit keys; keys are write-only/masked in the UI.

---

## 7. Coding standards & tooling
- **Python:** `ruff` (lint + format), `mypy` (typed), Pydantic v2 at boundaries, SQLAlchemy 2.0 typed models, structured logging via `logging` (JSON in prod), no `print`. Thin routers; logic in `services`/`graph`/`models_layer`.
- **TypeScript:** `tsconfig` strict, ESLint + Prettier, no `any` without reason, shared AG-UI types.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`…). Small, reviewable PRs aligned to the build-order milestones.
- **Pre-commit:** ruff + mypy + prettier/eslint on staged files.

---

## 8. Testing
- **Unit:** every node, service, resolver. High-risk first: `translate_params` (per provider), the model resolver, consensus math, the blackboard reducers.
- **Integration:** compile and run `build_collab_graph` with a stub agent; assert checkpoint/resume on a `thread_id`; assert round loop + termination.
- **Contract:** frontend tests run against recorded AG-UI event fixtures in `mocks/` to lock the §24 contract.
- **Bug protocol (R3):** every fixed bug gets a regression test named after the root cause.

---

## 9. Make targets (suggested)
```
make up        # docker compose up -d
make migrate   # alembic upgrade head
make api       # uvicorn --reload
make web       # pnpm dev (frontend)
make lint      # ruff + mypy + eslint
make test      # pytest + frontend tests
```

---

## 10. First milestone (acceptance)
Repo skeleton compiles; `docker compose up` brings up Postgres+pgvector & Redis; `build_collab_graph` compiles with a stub agent node and a `PostgresSaver`; a trivial run checkpoints and resumes on the same `thread_id`. Stop here for review before building the model layer (CLAUDE.md §4, step 2).

---

## 11. Database schema (production standard)

Supersedes the ARCH §13 sketch. Decisions baked in: **Organization is the top tenant** (every tenant table carries `org_id`); **external-IdP auth** (no passwords); **soft-delete** (`deleted_at`) on core entities with **hard `ON DELETE CASCADE`** for derived data. Managed by **Alembic** (§11.7).

### 11.0 Conventions
- **PKs:** `UUID` (`gen_random_uuid()` default). **Prefer UUIDv7** in the app layer (or `pg_uuidv7`) for index locality at scale.
- **Time:** all timestamps `TIMESTAMPTZ`; `created_at`/`updated_at` on every table; `updated_at` maintained by trigger (§11.6).
- **Tenancy:** `org_id UUID NOT NULL` on every tenant-scoped table → enables Row-Level Security (§11.5).
- **Soft-delete:** `deleted_at TIMESTAMPTZ NULL` on core entities; all reads filter `deleted_at IS NULL`; uniqueness via **partial unique indexes** `WHERE deleted_at IS NULL`. Derived/child rows are hard-deleted via FK cascade.
- **Enums:** `TEXT` + `CHECK` (migration-friendly); promote to native enums only if churn is low.
- **Provenance:** `created_by UUID REFERENCES users(id)` where a user action creates the row.

```sql
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector (knowledge + semantic memory)
-- gen_random_uuid() is built in (pg13+). For UUIDv7, generate in app or add pg_uuidv7.
```

### 11.1 Tenancy & identity
```sql
CREATE TABLE organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_org_slug ON organizations(slug) WHERE deleted_at IS NULL;

CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idp_provider  TEXT NOT NULL,                 -- 'clerk' | 'auth0' | 'google' | ...
    idp_subject   TEXT NOT NULL,                 -- IdP 'sub'; no passwords stored
    email         TEXT NOT NULL,
    display_name  TEXT,
    avatar_url    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at    TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_users_idp   ON users(idp_provider, idp_subject) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uq_users_email ON users(lower(email))              WHERE deleted_at IS NULL;

CREATE TABLE org_memberships (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES users(id)         ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('owner','admin','member','viewer')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, user_id)
);
```

### 11.2 Teams & agents
```sql
CREATE TABLE teams (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    description      TEXT,
    goal_title       TEXT,
    goal_description TEXT,
    success_criteria JSONB NOT NULL DEFAULT '[]',
    created_by       UUID REFERENCES users(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_team_name_per_org ON teams(org_id, lower(name)) WHERE deleted_at IS NULL;
CREATE INDEX ix_teams_org ON teams(org_id) WHERE deleted_at IS NULL;

CREATE TABLE agents (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    team_id           UUID NOT NULL REFERENCES teams(id)          ON DELETE CASCADE,
    name              TEXT NOT NULL,
    description       TEXT,
    instructions      TEXT,                       -- system prompt
    capabilities      JSONB NOT NULL DEFAULT '{}',-- web_search, rag, code, doc/chart, image (→ tools, ARCH §10.5.4)
    memory_enabled    BOOLEAN NOT NULL DEFAULT false,
    profile_id        UUID REFERENCES inference_profiles(id),
    override_model_id UUID REFERENCES model_catalog(id),          -- ARCH Q1 override (nullable)
    created_by        UUID REFERENCES users(id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at        TIMESTAMPTZ
);
CREATE INDEX ix_agents_team ON agents(team_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_agents_org  ON agents(org_id)  WHERE deleted_at IS NULL;

-- Runtime embedding-model selection (ITEM 2, ARCH §9.5). Both nullable FKs to a
-- model_catalog row whose model_type must be 'embedding' (enforced at the service
-- layer — a CHECK can't cross tables). Resolution chain for a knowledge source:
--   agents.embedding_model_id  (agent-private override)
--     → teams.embedding_model_id
--       → the org's default embedding model (its single enabled embedding catalog row)
-- The pgvector collection is keyed by the resolved model (knowledge__<model_id>) so
-- each model's dimension stays sticky (§9.5 / ARCH §20 note 6). Added by migration
-- d4e5f6a7b8c9.
ALTER TABLE teams  ADD COLUMN embedding_model_id UUID REFERENCES model_catalog(id);
ALTER TABLE agents ADD COLUMN embedding_model_id UUID REFERENCES model_catalog(id);

CREATE TABLE skills (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    team_id     UUID REFERENCES teams(id) ON DELETE CASCADE,   -- NULL = org/global base skill
    name        TEXT NOT NULL,
    description TEXT NOT NULL,                                  -- the 'when-to-use' shown up front
    source      TEXT NOT NULL CHECK (source IN ('filesystem','uploaded')),
    body_md     TEXT,
    assets      JSONB NOT NULL DEFAULT '{}',
    enabled     BOOLEAN NOT NULL DEFAULT true,
    approved_by UUID REFERENCES users(id),                      -- uploaded-skill review (ARCH §26.4)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);
-- uniqueness within a scope; uploaded wins over base at the app layer (last-wins, ARCH §26.3)
CREATE UNIQUE INDEX uq_skill_name ON skills(org_id, COALESCE(team_id, '00000000-0000-0000-0000-000000000000'), name)
    WHERE deleted_at IS NULL;

CREATE TABLE agent_skills (             -- derived link; hard cascade
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    PRIMARY KEY (agent_id, skill_id)
);
```

### 11.3 Model resolution layer (ARCH §9/§27)
```sql
CREATE TABLE llm_connections (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    provider     TEXT NOT NULL CHECK (provider IN
                   ('openai','anthropic','azure_openai','ollama','openrouter','openai_compatible')),
    base_url     TEXT,
    api_key_ref  TEXT,                          -- REFERENCE to secrets manager, NEVER the key
    api_version  TEXT,                          -- azure default
    scope        TEXT NOT NULL DEFAULT 'org' CHECK (scope IN ('org','team')),
    team_id      UUID REFERENCES teams(id) ON DELETE CASCADE,   -- when scope='team'
    enabled      BOOLEAN NOT NULL DEFAULT true,
    validated_at TIMESTAMPTZ,                    -- set by the validation probe (ARCH §27.3)
    last_sync_at TIMESTAMPTZ,
    created_by   UUID REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at   TIMESTAMPTZ
);
CREATE INDEX ix_conn_org ON llm_connections(org_id) WHERE deleted_at IS NULL;

CREATE TABLE model_catalog (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider_connection_id  UUID NOT NULL REFERENCES llm_connections(id) ON DELETE CASCADE,
    display_name            TEXT NOT NULL,
    model_identifier        TEXT NOT NULL,        -- passed through unchanged (e.g. org/model)
    model_type              TEXT NOT NULL CHECK (model_type IN ('chat','embedding')),
    deployment_name         TEXT,                 -- per-model (Azure)
    supports_tools          BOOLEAN NOT NULL DEFAULT false,   -- HARD GATE for mesh agents (ARCH §9.3)
    supports_streaming      BOOLEAN NOT NULL DEFAULT true,
    supports_vision         BOOLEAN NOT NULL DEFAULT false,
    supports_reasoning      BOOLEAN NOT NULL DEFAULT false,
    context_window          INT,
    pricing                 JSONB,
    source                  TEXT NOT NULL CHECK (source IN ('discovered','models.dev','manual')),
    enabled                 BOOLEAN NOT NULL DEFAULT true,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at              TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_catalog_model ON model_catalog(provider_connection_id, model_identifier)
    WHERE deleted_at IS NULL;
CREATE INDEX ix_catalog_tools ON model_catalog(org_id) WHERE supports_tools AND deleted_at IS NULL;

CREATE TABLE inference_profiles (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    default_model_id UUID REFERENCES model_catalog(id),  -- ARCH Q1: profile default model
    temperature      REAL,
    top_p            REAL,
    max_tokens       INT,
    reasoning_level  TEXT,
    json_mode        BOOLEAN NOT NULL DEFAULT false,
    streaming        BOOLEAN NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ
);
```

> **Profile delete policy (ARCH §14 `DELETE /providers/profiles/{id}`):** a profile is
> soft-deleted (`deleted_at`). Because agents select a model bundle via
> `agents.profile_id`, the endpoint **blocks with 409** and returns the referencing
> agents when any live agent still points at it — it never nulls `agents.profile_id`
> silently (no orphaning). The same guard covers the model catalog (a profile's
> `default_model_id`) by extension. No schema change is needed: the soft-delete column
> and the `profile_id` reference already exist above.

### 11.4 Sessions, runs, artifacts, events (ARCH §13–§24)
```sql
CREATE TABLE sessions (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    team_id    UUID NOT NULL REFERENCES teams(id)          ON DELETE CASCADE,
    thread_id  TEXT NOT NULL,                  -- LangGraph checkpointer thread
    status     TEXT NOT NULL DEFAULT 'created',
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_session_thread ON sessions(thread_id);
CREATE INDEX ix_sessions_team ON sessions(team_id) WHERE deleted_at IS NULL;

-- derived data below: hard cascade, no soft-delete
CREATE TABLE runs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    session_id  UUID NOT NULL REFERENCES sessions(id)       ON DELETE CASCADE,
    query       TEXT NOT NULL,
    rounds      INT  NOT NULL DEFAULT 0,
    converged   BOOLEAN NOT NULL DEFAULT false,
    status      TEXT NOT NULL DEFAULT 'running',
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_runs_session ON runs(session_id);

CREATE TABLE artifacts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    run_id         UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    kind           TEXT NOT NULL,
    content        TEXT,
    content_format TEXT NOT NULL DEFAULT 'markdown',  -- markdown|json|document
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_artifacts_run ON artifacts(run_id);

-- AG-UI event log: append-only; powers dashboard activity feed + reconnect/replay (ARCH §24.8)
CREATE TABLE run_events (
    id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    run_id  UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq     BIGINT NOT NULL,                  -- monotonic per run, for ordering/replay
    type    TEXT NOT NULL,                    -- AG-UI event type (ARCH §24.4)
    data    JSONB NOT NULL,
    ts      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_run_event_seq ON run_events(run_id, seq);
```

> **Blackboard note:** live contributions/critiques/votes live in **LangGraph state** (checkpointer), not a relational table. `run_events` is the queryable, replayable projection for the UI; persist a denormalized `contributions` table only if you later need analytics beyond the event log.

### 11.4a Chat & conversational layer (ARCH §8.5)
```sql
-- A run belongs to EITHER a launched Session OR a Chat conversation:
ALTER TABLE runs ALTER COLUMN session_id DROP NOT NULL;
ALTER TABLE runs ADD COLUMN conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE;
ALTER TABLE runs ADD CONSTRAINT runs_owner_chk
    CHECK ((session_id IS NOT NULL) <> (conversation_id IS NOT NULL));  -- exactly one

CREATE TABLE conversations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    team_id       UUID REFERENCES teams(id) ON DELETE CASCADE,   -- NULL = no-team single-LLM chat
    model_ref     JSONB,                       -- {connection_id, model_id, profile_id} for no-team chat
    thread_id     TEXT NOT NULL,               -- LangGraph checkpointer thread
    title         TEXT,
    is_playground BOOLEAN NOT NULL DEFAULT false,  -- true = ephemeral, excluded from history
    created_by    UUID REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at    TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_conv_thread ON conversations(thread_id);
CREATE INDEX ix_conv_org ON conversations(org_id) WHERE deleted_at IS NULL AND NOT is_playground;

CREATE TABLE messages (                         -- transcript; derived, hard cascade
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
    content         TEXT,
    run_id          UUID REFERENCES runs(id) ON DELETE SET NULL,  -- set for team-chat assistant turns
    deep_collaborate BOOLEAN NOT NULL DEFAULT false,              -- this turn used full multi-round
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_messages_conv ON messages(conversation_id, created_at);

CREATE TABLE attachments (                       -- chat file uploads; derived, hard cascade
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_id      UUID REFERENCES messages(id) ON DELETE SET NULL,
    kind            TEXT NOT NULL,               -- file mime/type
    uri             TEXT NOT NULL,               -- object storage location
    scope           TEXT NOT NULL DEFAULT 'transient' CHECK (scope IN ('transient','knowledge')),
    promoted_source_id UUID REFERENCES knowledge_sources(id) ON DELETE SET NULL,  -- if "Save to knowledge"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_attach_conv ON attachments(conversation_id);
```
> Transient attachments are ingested into a **conversation-scoped vector namespace** (reusing the knowledge pipeline) and are visible only to that conversation. "Save to team knowledge" promotes them into `knowledge_sources` and sets `promoted_source_id`. Playground conversations (`is_playground=true`) and their messages/attachments are not shown in session history and may be swept on a TTL.


### 11.5 Knowledge + observability
```sql
CREATE TABLE knowledge_sources (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    team_id     UUID NOT NULL REFERENCES teams(id)          ON DELETE CASCADE,
    agent_id    UUID REFERENCES agents(id) ON DELETE CASCADE,  -- NULL = team-shared; set = agent-private
    kind        TEXT NOT NULL CHECK (kind IN ('file','url','db','team_doc')),
    uri         TEXT,
    connector_config JSONB,  -- kind='db': {dsn, query} (read-only SELECT); Slice D, migration e5f6a7b8c9d0
    display_name TEXT,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','ingesting','ready','failed')),
    error       TEXT,
    chunk_count INT NOT NULL DEFAULT 0,
    created_by  UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);
CREATE INDEX ix_ks_team ON knowledge_sources(team_id) WHERE deleted_at IS NULL;

-- Usage metering (dashboard KPIs / provider health) — derived, hard cascade where linked
CREATE TABLE usage_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    run_id           UUID REFERENCES runs(id) ON DELETE SET NULL,
    agent_id         UUID REFERENCES agents(id) ON DELETE SET NULL,
    model_identifier TEXT,
    prompt_tokens    INT,
    completion_tokens INT,
    cost_usd         NUMERIC(12,6),
    ts               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_usage_org_ts ON usage_events(org_id, ts);

-- Audit trail (who did what) — production governance
CREATE TABLE audit_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES users(id),
    action        TEXT NOT NULL,               -- e.g. 'connection.create','skill.approve'
    entity_type   TEXT NOT NULL,
    entity_id     UUID,
    metadata      JSONB NOT NULL DEFAULT '{}',
    ts            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_org_ts ON audit_log(org_id, ts);
```

**Vector / LangGraph-managed tables (do NOT hand-author):**
- **Knowledge vectors** — created by `langchain_postgres` (`PGVector`). Ensure an ANN index (**HNSW** recommended) on the embedding column, and that chunk metadata carries `org_id`, `team_id`, `agent_id`, `source_id`, `scope` for tenant-filtered retrieval (ARCH §10.5.2). Exact table names vary by version — verify at install (R1).
- **Checkpointer + long-term Store** — created by `PostgresSaver.setup()` / `PostgresStore.setup()`. The Store is pgvector-indexed for semantic memory (ARCH §10).
- **Memory Explorer records** (Item 3) — the per-item long-term memories (Facts/Experiences/Session-Learnings/Summaries) are **Store keys**, not a relational table: namespace `("org",org_id,"team",team_id,"agent",agent_id,"memories")` (org-prefixed, ARCH §25.1), one key per record with value `{kind, content, pinned, created_at, run_id, seq}`. Written by the post-run consolidation step (ARCH §25.3); read/deleted/pinned via the §14 memory endpoints. The agent's `/memories/AGENTS.md` recall rollup is a separate Store key in the `(…,"agent",agent_id)` namespace, regenerated from the records.

### 11.6 `updated_at` trigger
```sql
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
-- attach per table, e.g.:
CREATE TRIGGER trg_agents_updated BEFORE UPDATE ON agents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
-- (repeat for every table with updated_at)
```

### 11.7 Row-Level Security (tenant isolation)
Enable RLS on every tenant table; the app sets the current org per request/transaction.
```sql
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON teams
    USING (org_id = current_setting('app.current_org', true)::uuid);
-- repeat per tenant table. The app runs: SET app.current_org = '<org-uuid>'; per request.
```
RLS is defense-in-depth; the app must **also** filter by `org_id` in every query. Never rely on RLS alone, and never on app filtering alone.

### 11.8 Migration notes (Alembic)
- Order: create extensions → tables → indexes → triggers → RLS policies.
- **Exclude framework-managed tables from autogenerate.** Alembic will otherwise try to drop the LangGraph checkpointer/store and `PGVector` tables. Configure `include_object` in `env.py` to skip any table it doesn't own (e.g. names beginning `checkpoint`, `store`, `langchain_`, plus the vector tables).
- Enum changes go through explicit migrations (TEXT+CHECK keeps these cheap).
- Seed the **Default Embedding Profile** (ARCH §9.5) in a data migration; remember the pgvector dimension is sticky (changing it = re-index migration, ARCH §20 note 6).

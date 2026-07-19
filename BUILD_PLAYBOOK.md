# BUILD_PLAYBOOK.md — How to develop NEX AGI, step by step

This is the **operating manual** for the build. It tells you, for each step: what to read, what to build, and when it's done. Work top-down, one step at a time, and **stop for review at each step** before moving on.

---

## The four documents (what each is for)

| Doc | Use it for | Authority |
|---|---|---|
| **CLAUDE.md** | The rules (R1–R6), the locked decisions, the build order, definition of done. Claude Code auto-reads it every session. | Process + non-negotiables |
| **ARCHITECTURE.md** | *What to build* on the backend: state, graph, agents, consensus, chat, model layer, memory, skills, knowledge, API, AG-UI contract. | Backend design |
| **TECHNICAL.md** | *How to set up*: repo structure, tooling, env, `docker-compose`, run commands, and the **production DB schema (§11)**. | Setup + schema |
| **FRONTEND_SPEC.md** | *What to build* on the frontend: layout, Session Workspace, Chat, components. | Frontend design |

**Rule of thumb:** "How do I set it up / what's the table?" → TECHNICAL. "What does this component do / what's the contract?" → ARCHITECTURE (backend) or FRONTEND_SPEC (frontend). "Am I allowed to / what was decided?" → CLAUDE.md.

When backend and frontend must agree on the event stream, **ARCHITECTURE.md §24 (AG-UI) is the single source of truth**; the frontend conforms to it.

---

## The loop for every step

1. **Read** the doc sections listed for the step (below).
2. **Verify packages (CLAUDE R1):** before importing anything, confirm current versions + v1 import paths via the LangChain MCP / Context7 / web. Pin them.
3. **Build** only that step, using real primitives (R2).
4. **Test** it (unit + the step's acceptance check). For any bug, do RCA first (R3) — no patches.
5. **Stop** and review against the step's "Done when." Then proceed.

Start each Claude Code session by having it restate CLAUDE.md's rules + locked decisions, so context never drifts.

---

## BACKEND — build the engine first (everything hangs off it)

### Step 1 — Project skeleton & infra
- **Read:** TECHNICAL §2 (structure), §3 (backend setup), §5 (docker-compose), §6 (env), §7 (standards); CLAUDE §2, §5.
- **Build:** repo tree, `uv` project, `docker-compose` (Postgres+pgvector, Redis), config (pydantic-settings), structured logging, FastAPI app factory with a lifespan that calls `checkpointer.setup()` / `store.setup()`.
- **Done when:** `docker compose up` runs; the app boots; lint/type-check clean.

### Step 2 — Foundation slice (the load-bearing one)
- **Read:** ARCHITECTURE §6 (CollabState + reducers), §7 (graph + nodes).
- **Build:** `CollabState`, `build_collab_graph` with a **stub** agent node, compiled with `PostgresSaver`.
- **Done when:** a trivial run **checkpoints and resumes** on the same `thread_id`. *Do not proceed until resume works* — this is where multi-agent projects silently break.

### Step 3 — Model Resolution Layer
- **Read:** ARCHITECTURE §9 + §27; TECHNICAL §11.3 (tables: `llm_connections`, `model_catalog`, `inference_profiles`).
- **Build:** the four layers + `resolve_model()` + `translate_params()` (per-provider) + the `supports_tools` gate + secrets resolution + validation probe.
- **Done when:** `resolve_model()` returns a working `init_chat_model` for OpenAI, Ollama, and OpenRouter; `translate_params` is unit-tested per provider.

### Step 4 — Agent factory (real ReAct agents)
- **Read:** ARCHITECTURE §22 (agent runtime), §11/§26 (skills), §12 (middleware); TECHNICAL §11.2 (agents/skills tables).
- **Build:** config → `create_agent(model, tools, skills, memory, system_prompt)`; the predefined tool registry; skills loader (filesystem + uploaded).
- **Done when:** one real ReAct agent runs a turn (reads the blackboard, calls a tool, writes a contribution + confidence).

### Step 5 — Mesh round + Consensus
- **Read:** ARCHITECTURE §7 (`Send` fan-out), §8 (consensus math).
- **Build:** parallel `Send()` fan-out to all active agents; consensus node (`max_rounds` OR `mean(confidence) ≥ τ`); confidence-weighted ranking; the round loop.
- **Done when:** a 3-agent team runs multiple rounds and terminates by both rules; ranking is correct.

### Step 6 — HITL + Synthesizer + End
- **Read:** ARCHITECTURE §4.5–4.7, §12 (HITL middleware).
- **Build:** `HumanInTheLoopMiddleware`/`interrupt()` before synthesis; synthesizer node (plain node, cheaper model); end node persists the artifact.
- **Done when:** a run pauses at HITL, resumes on approve/edit, and produces a final artifact.

### Step 7 — Memory + Knowledge
- **Read:** ARCHITECTURE §10 (memory: deepagents StoreBackend), §10.5 (knowledge: ingest → pgvector → `search_knowledge`); TECHNICAL §11.5 (`knowledge_sources`).
- **Build:** long-term memory via deepagents backend; knowledge ingestion worker + the tenant-filtered retriever tool.
- **Done when:** an agent recalls a prior-session memory; `search_knowledge` returns only that team/agent's chunks.

### Step 8 — AG-UI streaming
- **Read:** ARCHITECTURE §24 (event contract), §23 (A2A intents); TECHNICAL §11.4 (`run_events`).
- **Build:** event emission from the graph, WebSocket endpoint, Redis fan-out, the `run_events` log + replay.
- **Done when:** a run streams the full typed event sequence; a reconnect replays missed events by `seq`.

### Step 9 — FastAPI routes
- **Read:** ARCHITECTURE §14; TECHNICAL §11 (all tables); CLAUDE §3 (RLS/tenancy).
- **Build:** REST CRUD for teams/agents/sessions/providers/knowledge/memory; Alembic migrations (§11.8 — exclude framework-managed tables); RLS + `org_id` filtering.
- **Done when:** you can create a team + agents + a session and launch a run end-to-end via the API.

### Step 10 — Chat & Playground (backend)
- **Read:** ARCHITECTURE §8.5; TECHNICAL §11.4a (`conversations`/`messages`/`attachments`, run XOR constraint).
- **Build:** team chat (lightweight = graph with `max_rounds=1`, HITL off; Deep Collaborate = full run), no-team single-agent chat, playground (ephemeral), transient file upload.
- **Done when:** a team chat returns a fast 1-round reply, Deep Collaborate runs the full loop, no-team chat works, playground isn't persisted.

---

## FRONTEND — build against a mock AG-UI stream first

### Step 11 — Session Workspace (the product)
- **Read:** FRONTEND_SPEC §9 (multi-pane layout) + §9.10 (animation) + §18 (AG-UI contract) + §19 (components); ARCHITECTURE §24 (event types).
- **Build:** shared AG-UI TS types + the **mock replayer** (`mocks/`), then the multi-pane workspace (graph, debate, consensus, blackboard, output) driven by the mock stream.
- **Done when:** the workspace renders a full recorded run from the mock replayer, with event-driven edge animation.

### Step 12 — the rest, in order
- **Read:** FRONTEND_SPEC §10 (Team), §11 (Agent Builder), §12 (Settings→AI), §13 (Knowledge), §14 (Memory), §15 (Dashboard), §9A (Chat & Playground).
- **Build, in this order:** Team Workspace → Agent Builder → Settings/AI → Knowledge → Memory → Dashboard → **Chat & Playground** (last, since it reuses the Session Workspace stream + expand view).
- **Done when:** each screen matches its spec section and talks to the real API; chat can expand a team turn into the Session Workspace.

---

## ARTIFACTS — downloadable deliverables (after the engine + chat work)

> Generation-only (no code execution in v1 — ARTIFACTS §6/§15). Reuses the run XOR,
> capability→tools gate, the `artifacts` table, and standard AG-UI events — no parallel
> system. Build one slice at a time, tests + review between (ARTIFACTS §18).

### Step 13 — Artifacts: generation & export
- **Read:** ARTIFACTS.md (whole); ARCHITECTURE §8.5 (run XOR), §10.5.4 (capability→tools), §24 (AG-UI); TECHNICAL §11.4 (artifacts table) + §11.5 (worker); FRONTEND_SPEC §9.7 (Final Output) + §11 (capabilities).
- **Slices (one at a time):**
  - **Slice 1 — schema + storage + download ✅ (done).** Extended `artifacts` (storage/version/linkage cols), added `artifact_versions`, an `ObjectStorage` seam (`LocalDiskStorage` in dev), HMAC signed + RLS-scoped `GET /artifacts/{id}/download` (+ `/versions/{v}/download`, `GET /artifacts/{id}`, `GET /runs/{id}/artifacts`). Migration `b8c9d0e1f2a3`.
  - **Slice 2 — text/code tools + live event + basic panel ✅ (done).** Backend: `write_code_file`/`write_markdown`/`write_json`/`write_csv` (`doc_chart`-gated); a **designated post-consensus producer agent** (ARTIFACTS §2A, reuses `create_agent`) invoked as a synthesizer sub-step (control graph unchanged); artifacts carried on the standard `tool_result` event as a descriptor `attachment` (registered in **ARCHITECTURE §24.9**, no custom event), committed per-artifact so the signed `download_url` is valid the instant it streams. Frontend: the reducer folds the `attachment` into `run.artifacts` (upsert by id for live `generating→ready`, no phantom agent node); a basic **ArtifactPanel** (cards → overlay panel with per-kind preview + Download + live status) is artifact-aware in the Final Output canvas (FRONTEND_SPEC §9.7), so it appears in both the Session Workspace and chat. **Deferred to Slice 3:** versions, iterate, copy, open-in-editor, inline chat cards.
  - **Slice 3 — panel parity ✅ (done).** Backend: `POST /artifacts/{id}/iterate` (synchronous/atomic — re-runs the producer agent's model on the current content → a new immutable `artifact_versions` snapshot, advances `current_version`, older versions stay downloadable); `ArtifactService.add_version`; `state_delta` deliberately **not** emitted (synchronous iterate + whole-file producer → no honest deltas; stays the designed seam, ARCH §24.9). Frontend: ArtifactPanel parity — **version switcher** (v1/v2…), **iterate** (instruction → new version, synced back to the Final Output card), **copy**, **open-in-editor** (new tab), download — all over the authenticated artifact API (any version, no token-expiry); **chat inline cards** on done team-turn assistant messages (from `GET /runs/{id}/artifacts`, file kinds only). Session Workspace Final Output integration landed in Slice 2.
  - **Slice 4 — Office + media tools ✅ (done).** Backend: `create_docx`/`create_xlsx`/`create_pptx`/`create_pdf`/`create_chart`/`create_image` ([app/artifacts/generators.py](backend/app/artifacts/generators.py) + [app/tools/artifacts_media.py](backend/app/tools/artifacts_media.py)) — each validates its spec and generates real bytes **off the event loop** (`asyncio.to_thread`), persisted as a binary `tool_result` attachment; capability-assembled per the producer agent (`doc_chart` → docs/office/chart, `image_gen` → image/chart, §13). **R1 verified + pinned:** `python-docx` 1.2 · `openpyxl` 3.1 · `python-pptx` 1.0 · `fpdf2` 2.8 (PDF) · `matplotlib` 3.11 (charts, thread-safe OO API) · `Pillow` 12 (images). Frontend: the panel previews chart/image artifacts **inline** (`<img>`) and offers download for office binaries. **Deferred (flagged):** (a) packaging tools as deepagents `SKILL.md` (progressive disclosure) — the tool schemas/docstrings already carry the format know-how, and the producer is a plain `create_agent`; (b) a broker-backed enqueue worker with live `generating→ready` streaming — `to_thread` already keeps the loop responsive for our bounded generation (the documented scaling seam, like ingestion's swappable worker).
  - **Slice 5 — bundles ✅ (done).** `create_archive(filename, artifact_ids)` — a format-agnostic bundle meta-tool always in the producer's toolset: resolves the ids to bytes (restricted to **this run** + org via RLS, nested archives skipped, §15), zips them with duplicate-name disambiguation ([generators.py](backend/app/artifacts/generators.py) `build_archive`), persists a `kind="archive"` artifact (`application/zip`). Empty `artifact_ids` ⇒ bundle everything produced this run ("download all files", §14). Proven end-to-end: a producer creates two `.py` files then bundles them into a working `.zip` downloaded + re-opened with `zipfile`.
- **Done when (ARTIFACTS §19):** an agent produces a downloadable file in **both** team chat and a session; it streams `generating→ready`, previews, downloads via a signed tenancy-scoped URL; iterate makes a new version; `create_archive` bundles a working `.zip`; no generated code executes server-side.

---

## Session discipline

- **Starting prompt (first session):** see the kickoff prompt you were given — have Claude Code read all four docs, restate rules + locked decisions, then do **Step 1 only** and stop.
- **Each later session:** "Read CLAUDE.md. We're on Step N of BUILD_PLAYBOOK.md. Read the sections it lists for Step N, verify packages per R1, implement Step N only, run its acceptance check, and stop for review."
- **On any error:** "Root-cause first per R3" — reproduce, backtrack the full path, explain the cause, then an integrated fix + regression test. Never accept a `try/except` band-aid.
- **On ambiguity or a wish to deviate from a locked decision:** stop and ask (R4/R6).

---

## Critical "don't skip" checks
- Step 2 resume **must** work before any real agents (the foundation).
- `supports_tools` gate (Step 3) — mesh agents only get tool-calling models.
- Alembic `include_object` excludes LangGraph/PGVector tables (Step 9 / TECHNICAL §11.8) or migrations will try to drop them.
- AG-UI types stay locked to ARCHITECTURE §24 (Steps 8 & 11) — the one place backend/frontend silently drift.
- Re-verify v1 import paths at install (R1) — LangChain v1 / LangGraph / deepagents / langchain-postgres surfaces still move.

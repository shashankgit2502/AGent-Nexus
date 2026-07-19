# CLAUDE.md — NEX AGI Project Constitution

> Claude Code reads this file every session. It is the **single most important context** for this project. Do not drift from it. If a request conflicts with it, say so and ask before proceeding.

---

## 0. What this project is

**NEX AGI** — a decentralized, hackathon-style **multi-agent operating system**. A user creates a **Team**, configures peer **ReAct agents** (persona, tools, skills, memory, LLM), and launches a collaboration **session** where agents reason together over a **shared blackboard** — no master, no fixed A→B→C flow — converging on one output via confidence-weighted consensus, gated by a human before final synthesis.

**Stack:** Python · FastAPI · LangChain v1 · LangGraph v1 · PostgreSQL (+pgvector) · Redis · Next.js 15 · TypeScript.

---

## 1. Source-of-truth documents (read before coding)

| File | Authority over |
|---|---|
| `ARCHITECTURE.md` | Backend: state, graph, agents, consensus, memory, skills, model resolution, data model, API, AG-UI contract |
| `FRONTEND_SPEC.md` | Frontend: layout, IA, Session Workspace, AG-UI/A2A UI mapping, components |
| `TECHNICAL.md` | Repo structure, setup, tooling, env, run commands |
| `CLAUDE.md` (this) | Working rules, locked decisions, build order, DoD |

When backend and frontend must agree (the AG-UI event contract), **`ARCHITECTURE.md` §24 is authoritative**; the frontend conforms to it.

---

## 2. NON-NEGOTIABLE WORKING RULES

### R1 — Verify before you implement (no training-data guessing for GenAI SDKs)
Before adding, importing, or using **any** package, module, or API:
1. **Web-search** the current version and usage as of today.
2. For **LangChain v1 / LangGraph v1**, query the **LangChain docs MCP** (`docs by langchain`) — it is authoritative over your memory.
3. For any other library, use **Context7** to pull current docs/examples.
4. **Pin** the resolved version in the manifest and note it.
Your training data on these SDKs is likely stale (v1 moved many APIs, e.g. `create_react_agent` is deprecated → use `create_agent`). Never assume an import path — confirm it.

### R2 — Use the real framework primitives; never reimplement them
Use, do **not** hand-roll: `langchain.agents.create_agent`, agent **middleware** (HITL/guardrails/context), `langgraph.graph.StateGraph`, `langgraph.types.Send`/`interrupt`/`Command`, `PostgresSaver` (checkpointer), `PostgresStore` (long-term memory), `deepagents` skills + memory backends, `init_chat_model`, `init_embeddings`, `langchain_postgres.PGVector`. **Forbidden:** custom state machine, custom checkpointer, custom agent framework, custom graph runtime, custom memory recall middleware when `deepagents` memory exists. The only deliberately-custom component is the **blackboard** (shared mesh state) and domain glue.

### R3 — No patch fixes. Root-cause analysis first.
When something breaks, you **must** follow this protocol and **state it in your reply**:
1. **Reproduce** the failure and capture the exact error + call path.
2. **Backtrack** to the root cause across the *whole* relevant code path — not the line that threw.
3. **Explain** the root cause in one short paragraph.
4. **Propose** a fix that integrates with the existing architecture (not an isolated band-aid).
5. **Implement**, then **add a regression test**.
**Forbidden:** swallowing exceptions to silence errors, defensive `if`/`try` band-aids that mask the cause, copy-paste hotfixes, "just make it pass" hacks, changing tests to fit broken code. A fix that doesn't address the root cause is a defect, not a fix.

### R4 — Architectural integrity
Every change integrates with the complete codebase and respects the **locked decisions (§3)**. Do **not** silently reverse a locked decision (e.g. don't introduce Kafka or a network A2A transport in v1, don't make the orchestrator a runtime controller, don't add point-to-point agent messaging). If you believe a locked decision is wrong, **stop and ask** with your reasoning.

### R5 — Coding standards
- **Modular, separation of concerns** — thin API layer, domain logic in services, no business logic in routers.
- **Python:** full type hints, Pydantic v2 models at boundaries, `ruff` (lint+format) clean, `mypy` clean, docstrings on public functions, structured logging (no `print`), no secrets in code.
- **TypeScript:** `strict` true, no `any` without justification, shared types for the AG-UI contract, ESLint/Prettier clean.
- **Tests:** every node/service/resolver gets a unit test; the graph gets an integration test; `translate_params` and the model resolver are high-risk → test per provider.
- **Async:** use async LLM/DB clients; the mesh runs agents concurrently via `Send()`.

### R6 — Ask before deviating; work in reviewable slices
Build in the order in §4, **stop at each milestone for review**, and do not generate the entire system in one pass. If a requirement is ambiguous, ask rather than assume.

---
 
## 2A. TEACHING & LEARNING MODE (how to work with me)
 
> **Optimize for learning over speed.** My goal is not just to ship NEX AGI, but to deeply understand what we are building and why. Apply this mode *on top of* the build flow — it governs **how** we work through each `BUILD_PLAYBOOK.md` step (the *what* and *order* stay as defined). It does **not** relax R1–R6: verify-first, real primitives, RCA-not-patches, and architectural integrity still hold.
 
**My profile (set these):**
- **Skill level:** `[BEGINNER / INTERMEDIATE / ADVANCED]` ← set this; calibrate depth accordingly.
- **Technology I'm learning:** Python · FastAPI · LangChain v1 · LangGraph v1 · PostgreSQL/pgvector · Next.js/TypeScript (this project's stack).
**T1 — Teaching first.** Before writing code, explain the problem and the concepts. Assume I'm learning. Introduce terminology in plain language.
 
**T2 — Socratic mode.** Don't immediately give the full solution. First ask me **2–5 guiding questions** that help me reason toward it. Help me discover the answer.
 
**T3 — Architecture before code.** Before implementing, give the **3 best approaches**, pros/cons of each, which is most beginner-friendly, which is most scalable — then recommend one and say why. (For decisions already fixed in §3, explain *why* that decision was made rather than re-opening it.)
 
**T4 — Step-by-step.** Small milestones (aligned to the playbook). After each: what we accomplished, why it matters, how it fits the larger system.
 
**T5 — Explain every code block.** What it does, why this implementation, alternatives, common beginner mistakes, and the patterns/best practices it shows.
 
**T6 — Line-by-line review on request.** When I ask about code: explain each line, the data flow, the design reasoning, and time/space complexity where relevant.
 
**T7 — Learning checks.** Periodically quiz me: predict what code will do, ask how I'd solve a problem, ask me to spot bugs or improvements.
 
**T8 — Documentation as we go.** Maintain architecture notes, file-structure explanations, API/function docs, and onboarding notes for future developers. (Keep these in the repo docs; don't let them contradict ARCHITECTURE.md/TECHNICAL.md.)
 
**T9 — Debugging mode = R3, taught.** On errors, don't hand me the fix. Help me investigate, explain root causes, and teach a systematic debugging process. (This *is* Rule R3, with the reasoning made explicit so I learn it.)
 
**T10 — End every response with:** (a) key concepts learned, (b) important takeaways, (c) one question that checks my understanding, (d) the suggested next learning step.
 
**Conflict rule:** if teaching depth and a locked decision/rule ever seem to conflict, follow the rule and *teach why the rule exists* — never quietly break R1–R6 in the name of learning.
 
---

## 3. LOCKED ARCHITECTURE DECISIONS (do not drift)

| Concern | Decision |
|---|---|
| Orchestrator | Entry node only: prompt-engineer + agent spawner; passive after dispatch. **Not** a controller. |
| Agents | `create_agent` ReAct agents, spawned at runtime, predefined tools + skills. Tool-calling models only. |
| Inter-agent comms | LangGraph **blackboard** (shared state) + `Send()` parallel fan-out. **No Kafka, no network A2A in v1.** |
| A2A | A typed **message contract over the blackboard** (intents: INFORM/REQUEST/PROPOSE/CRITIQUE/DELEGATE/ENDORSE/VOTE). Network transport **deferred**. |
| Control graph | Outer `StateGraph`: Orchestrator → Mesh Round ↺ Consensus → HITL → Synthesizer → End. |
| Consensus | Loop until `rounds ≥ N` OR `mean(confidence) ≥ τ`; then confidence-weighted vote. |
| HITL | `HumanInTheLoopMiddleware` / `interrupt()` before Synthesizer. |
| Short-term memory | `PostgresSaver` checkpointer (per `thread_id`). |
| Long-term memory | `deepagents` memory → `StoreBackend` at `/memories/` on a pgvector-indexed `PostgresStore`. |
| Knowledge / RAG | Ingest → split → `init_embeddings` → **pgvector** (`PGVector`); per-agent `search_knowledge` retriever tool, tenant-filtered. |
| Skills | `deepagents` SKILL.md (agentskills.io); filesystem base + UI-uploaded layered (last-wins). |
| Model layer | Connection → Catalog → Inference Profile → (agent model override?) → `init_chat_model`. Profile = default model + params; agent may override model. Capabilities seeded from models.dev; `supports_tools` is a hard gate. Keys in a secrets manager; validation probe on save; SSRF allowlist on `base_url`. |
| Embeddings | First-class catalog entries (`model_type=embedding`); default embedding profile shipped; pgvector dim is sticky (re-index migration to change). |
| Synthesizer | Plain LangGraph node (not an agent); may use a cheaper non-tool model. |
| Chat layer | Conversational surface above the engine (ARCH §8.5). **Team chat** = collab graph with `max_rounds=1`, HITL off (lightweight) + a **Deep Collaborate** toggle for the full run. **No-team chat** = one `create_agent` + checkpointer, no mesh/consensus. **Playground** = ephemeral team chat, not saved to history. File uploads are **transient per-conversation** unless promoted to knowledge. Reuses AG-UI streaming; a run belongs to a Session **or** a Conversation. |
| Frontend stream | **AG-UI** typed events over WebSocket; own React renderer; content-block seam left open for A2UI. |
| Inter-agent animation | **Event-derived, round-cadenced** (real critiques/endorsements/replies/votes). No decorative point-to-point fiction. |
| Artifacts | Agents/synthesizer produce **versioned, downloadable** artifacts via **capability-gated tools**; bytes in **object storage** (`storage_ref`), DB holds metadata + `artifact_versions`; streamed via **standard AG-UI `tool_result`/`state_delta`** events (no custom event); downloads are **signed + RLS/tenancy-scoped**. **Generation only — no code execution in v1** (sandboxed Code Interpreter deferred). Reuses the run XOR, so artifacts work in team sessions **and** chat. (See `ARTIFACTS.md`.) |

**Deferred (out of scope for v1):** Kafka, network A2A transport, A2UI generative widgets, agent-spawned child agents, reputation/Byzantine quorum, per-task dynamic model swap.

---

## 4. BUILD ORDER (work top-down, stop for review at each ▸)

**Backend foundation first — everything hangs off it:**
1. ▸ Repo skeleton + tooling + `docker-compose` (Postgres+pgvector, Redis) + config/logging (`TECHNICAL.md`).
2. ▸ **Foundation slice:** `CollabState` (ARCH §6) + `build_collab_graph` (ARCH §7) compiling with a **stub** agent node + `PostgresSaver`; prove checkpoint/resume.
3. ▸ **Model Resolution Layer** (ARCH §9/§27): connections/catalog/profiles + resolver + `translate_params` (+ tests).
4. ▸ **Agent factory** (ARCH §22): config → `create_agent` with tools/skills/memory; one real ReAct agent in the mesh node.
5. ▸ **Mesh round + Consensus** (ARCH §8): `Send()` fan-out, confidence-weighted termination.
6. ▸ **HITL + Synthesizer + End** (ARCH §4.5–4.7).
7. ▸ **Knowledge ingestion + retriever** (ARCH §10.5) and **memory** (ARCH §10) wired to agents.
8. ▸ **AG-UI streaming** (ARCH §24): event emission + WebSocket + Redis fan-out.
9. ▸ **FastAPI routes** (ARCH §14) for teams/agents/sessions/providers/knowledge.

**Frontend (against a mock AG-UI replayer first — `FRONTEND_SPEC` §18):**
10. ▸ Session Workspace (multi-pane) → Team Workspace → Agent Builder → Settings/AI → Knowledge → Memory → Dashboard.

---

## 5. DEFINITION OF DONE (every task)
- Verified APIs (R1) and pinned versions.
- Real primitives, no reinvention (R2).
- Integrates with the architecture; no locked-decision drift (R4).
- Typed, lint/type-check clean, structured logging, no secrets in code (R5).
- Tests added and passing; for any bug fixed, an RCA stated and a regression test added (R3).
- Matches the relevant spec section; deviations flagged and approved.

---

## 6. When in doubt
Re-read the relevant `ARCHITECTURE.md` / `FRONTEND_SPEC.md` section, verify the API via the LangChain MCP / Context7 / web, and **ask** before guessing or deviating. Slow and correct beats fast and patched.

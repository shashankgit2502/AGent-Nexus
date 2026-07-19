# FRONTEND_INTEGRATION_PLAN.md — NEX AGI Frontend ⇄ Backend Integration

> **Purpose.** This is the durable, self-contained playbook for wiring the **real NEX AGI backend**
> (already built, `backend/`) to the **frontend** (`frontend/`), using `reference/nex-agi/` as the
> **design + behavior source**. It is written so a **cold agent in a fresh chat** can execute any one
> slice end-to-end with only: (1) this file, (2) `CLAUDE.md`, and (3) the named `ARCHITECTURE.md` /
> `FRONTEND_SPEC.md` sections. Each slice has a ready-to-paste prompt at the bottom.

---

## 0. How to use this document (cold-start protocol)

For each slice:
1. Open a **new chat** in the repo.
2. Paste the slice's **PROMPT** (§10). It instructs the agent to read `CLAUDE.md`, this file, and the
   cited spec sections, **restate R1–R6 + locked decisions**, then implement only that slice.
3. The agent works the slice, writes tests, and **stops at the slice boundary** for your review.
4. You tick the slice in **§9 Progress Tracker** (or have the agent do it) before starting the next.

**Golden rules for every slice (do not skip):**
- **R1** — verify any package/import against the LangChain docs MCP / Context7 / web **before** using it; pin versions. SDK memory is stale.
- **R2** — use real primitives (LangGraph/LangChain on the backend; Zustand/React Query/@xyflow on the frontend). Don't hand-roll a store, a fetch layer, or a graph renderer.
- **R3** — root-cause first; no patches, no swallowed errors; add a regression test for every fix.
- **R4** — no drift from the locked decisions (§2) or the AG-UI contract (§5). The contract is mirrored, never forked.
- **R5** — TypeScript `strict`, no unjustified `any`, Zod (or typed guards) at boundaries, no secrets in code, no `console.log` in committed code.
- **R6** — one reviewable slice at a time; stop at each boundary.
- **Teaching Mode (§2A of CLAUDE.md)** — before coding a slice, explain the approach + data flow + why; end with key concepts and a check question.

---

## 1. Source-of-truth hierarchy (for this integration)

1. **Visual design** (theme, color, type, spacing, shadows, component styling): **`reference/nex-agi/` WINS.** Ignore FRONTEND_SPEC §4 visuals.
2. **IA / screens / behavior / component responsibilities / data needs / Chat & Playground (§9A) / Session Workspace (§9, §9.10):** **FRONTEND_SPEC.md (non-visual parts).**
3. **Contract:** **ARCHITECTURE.md** — REST routes (§14), AG-UI events (§24, the single source of truth for the stream), Chat modes (§8.5), Model Resolution (§9/§27). DB/setup: TECHNICAL.md (§11, §2–§7).

**Hard constraints:** Do **not** change backend architecture to fit the UI. Do **not** fork the AG-UI contract (§24.4) — frontend types mirror it exactly. Keep the reference theme throughout. Respect `org_id` tenancy / RLS on every call.

---

## 2. Locked decisions that bound the frontend

- Stream = **AG-UI typed events over WebSocket**; the frontend owns a React renderer; content-block seam (§24.6) left open for A2UI.
- Inter-agent animation is **event-derived and round-cadenced** (real `round_start` / `agent_turn_start` / `critique` / `consensus_update` / votes) — **no decorative point-to-point fiction**.
- Chat layer (§8.5): **Team chat** = collab graph with `max_rounds=1`, HITL off + a **Deep Collaborate** toggle for the full run. **No-team chat** = one agent + checkpointer, no mesh. **Playground** = ephemeral team chat, excluded from history. Uploads transient per-conversation unless promoted.
- A run belongs to a **Session XOR a Conversation**; both stream by `run_id` through the **same renderer**.
- **Streaming state → Zustand store (AG-UI event-reducer, keyed by `seq`). REST DTOs → React Query.** Never mix the two.

---

## 3. Target stack (what `frontend/` actually is)

> ⚠️ **Reconciliation:** `frontend/` is **NOT** a copy of the Vite/Tailwind-v4 reference. The reference is the **design source only**. The real stack (from `frontend/package.json`) is:

| Concern | Choice | Role |
|---|---|---|
| Framework | **Next.js 15.3** (App Router, `--turbopack`) | routing, RSC shell |
| Language | **TypeScript** `strict` | — |
| Styling | **Tailwind CSS v3** + `clsx` + `tailwind-merge` + `class-variance-authority` | shadcn-style utilities |
| Animation | **framer-motion** v12 | (reference uses `motion`; same lib, import from `framer-motion`) |
| Icons | **lucide-react** | matches reference |
| Graph | **@xyflow/react** (React Flow 12) | the AgentGraph topology (replaces the reference's hand-rolled SVG) |
| Streaming store | **Zustand** v5 | session store + AG-UI event-reducer |
| REST cache | **@tanstack/react-query** v5 | typed DTO fetching/mutations |

Env (`frontend/.env.example`): `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`, `NEXT_PUBLIC_WS_URL=ws://localhost:8000`.

**Theme port (reference → Tailwind v3):** The reference theme lives in `reference/nex-agi/src/index.css` (Tailwind v4 `@theme`). Port it to:
- `frontend/app/globals.css` — copy the plain-CSS classes **verbatim**: `.artistic-background`, `.artistic-grid`, `.artistic-text-gradient`, `.artistic-glow-blob` (hidden), `.artistic-pane` (glass: `rgba(18,18,22,0.45)`, `backdrop-blur(20px)`, border `rgba(255,255,255,0.06)`), `.artistic-pane-hover`, `.vertical-protocol`, custom scrollbars. Base: `html/body` bg `#050506`, text `#fff`.
- `frontend/tailwind.config.ts` — `theme.extend`: `fontFamily.sans = ['Inter', …]`, `fontFamily.mono = ['JetBrains Mono', …]`; accent color `emerald` `#10b981`; load Inter + JetBrains Mono via `next/font` (preferred) or the Google Fonts import.
- Keep the reference's exact class usage when porting each view (e.g. `artistic-pane`, `text-[#10b981]`, `text-[10px] font-mono uppercase tracking-[0.3em]`).

---

## 4. Target directory layout (`frontend/`)

```
frontend/
  app/
    layout.tsx                 # root shell: header nav, providers (RQ + theme), globals.css
    globals.css                # ported theme
    page.tsx                   # dashboard (landing after "login")
    workspace/page.tsx         # Session Workspace (flagship)
    chat/page.tsx              # Chat & Playground
    teams/page.tsx             # Teams + Agent Builder
    settings/ai/page.tsx       # Connections / Catalog / Profiles
    knowledge/page.tsx
    memory/page.tsx
    history/page.tsx
  components/                  # shared presentational (ported from reference/src/components + views)
    agent-graph/               # @xyflow/react topology
    debate-thread/
    blackboard/
    hitl-gate/
    ui/                        # shadcn-style primitives (button, card, dialog, …)
  features/                    # per-domain hooks + view logic (teams, sessions, chat, providers, …)
  lib/
    api/                       # typed REST client (one module per resource)
    ws/                        # AG-UI WebSocket client (replay-then-live by seq)
    org.ts                     # org context header injection
  store/
    session-store.ts          # Zustand: AG-UI event-reducer (the run's live state)
  types/
    agui.ts                    # AG-UI envelope + event union — mirrors backend app/streaming/events.py + ARCH §24.4
    api.ts                     # REST DTOs — mirror backend app/schemas/*
  mocks/
    agui-replayer.ts           # canned AG-UI event stream for offline UI dev (FRONTEND_SPEC §18)
```

---

## 5. THE CONTRACT (embedded — mirror exactly)

### 5.1 AG-UI envelope (ARCH §24.3)
```ts
interface AGUIEvent<T = unknown> {
  type: AGUIEventType;
  session_id: string;   // the owning surface id (session OR conversation)
  run_id: string;
  seq: number;          // monotonic per-run; ordering + replay dedup key
  ts: string;           // ISO-8601 UTC
  data: T;
}
```

### 5.2 Event catalog (ARCH §24.4 == backend `app/streaming/events.py` frozenset)
`run_start`, `round_start`, `agent_turn_start`, `reasoning`, `tool_call`, `tool_result`,
`contribution`, `confidence`, `critique`, `consensus_update`, `hitl_request`,
`hitl_resolved`, `synthesis`, `run_finished`, `error`.

**`data` payloads** (the target contract **after Slice 0** completes the §24.4 emission). Fields marked **[S0]** are added in Slice 0; confirm exact shapes against the backend emission while doing Slice 0, and keep `types/agui.ts` in lockstep.

> ✅ **Slice 0 done — these shapes are now the live, emitted contract** (verified against `backend/app/`, 185 tests green). Two reconciliations vs. the original projection are marked **[S0-NOTE]**.

| type | `data` shape |
|---|---|
| `run_start` | `{ goal: string, roster: string[] }` — **[S0-NOTE]** `roster` is `active_agent_ids` (agent-id **strings**), NOT rich objects. The frontend joins these ids with `GET /teams/{id}/agents` to label nodes (name/model). |
| `round_start` | `{ round: number }` |
| `agent_turn_start` | `{ agent_id: string, round: number }` |
| `reasoning` | `{ agent_id: string, round: number, text: string }` (per-turn narration, round-cadenced — not per-token) |
| `tool_call` | `{ agent_id: string, round: number, tool: string, args: object }` |
| `tool_result` | `{ agent_id: string, round: number, tool: string, result: unknown }` |
| `contribution` | `{ agent_id: string, round: number, confidence: number, content_blocks: ContentBlock[], responds_to?: string[] }` — **[S0-NOTE]** `responds_to` = agent-ids of prior-round peers this proposal builds on (server-validated by `_valid_responds_to`); drives the §9.10 reply edges. Optional: emitted by the real agent runtime, omitted by the foundation stub; readers default to `[]`. |
| `confidence` | **[S0-NOTE]** NOT emitted as a standalone event — confidence is folded into `contribution.data.confidence`. The type stays reserved in the catalog; the frontend reads confidence off `contribution`. |
| `critique` | `{ sender: string, target: string, round: number, severity: 'minor'\|'major'\|'blocking', content: string }` |
| `consensus_update` | `{ mean_confidence: number, converged: boolean, ranking: string[] }` (ranking keys are `"agent_id:round"`) |
| `hitl_request` | `{ candidate: string \| null, candidate_key: string \| null, ranking: string[], converged: boolean, allowed_decisions: string[] }` |
| `hitl_resolved` | `{ decision: 'approve'\|'edit'\|'reject', source: 'human'\|'auto'\|'human_edit' }` |
| `synthesis` | approve/model/fallback → `{ source: string, ranking: string[], content_blocks: ContentBlock[] }`; edit → `{ source: 'human_edit', content_blocks: ContentBlock[] }`; reject → `{ rejected: true }` |
| `run_finished` | `{ artifact: { kind: 'synthesis'\|'rejected', content: string \| null, content_format: 'markdown' } }` |
| `error` | `{ scope: string, agent_id?: string, round?: number, message: string }` |

**Per-run event ordering (what the Zustand reducer will see):** `run_start` → `round_start(1)` → per agent: `agent_turn_start` → `reasoning*` → (`tool_call` → `tool_result`)* → `contribution` → `critique*` → (after all agents) `consensus_update` → [`round_start(n+1)` if looping … repeat] → `hitl_request` (deep only; pause) → `hitl_resolved` → `synthesis` → `run_finished`.

**ContentBlock (§24.6, discriminated union — extensible):**
```ts
type ContentBlock =
  | { type: 'text'; text: string }
  | { type: 'code'; language: string; code: string }
  | { type: 'tool_result'; tool: string; value: string };
```

### 5.3 REST routes (ARCH §14) — base `NEXT_PUBLIC_API_BASE_URL`
- **Teams:** `POST /teams` · `GET /teams` · `GET /teams/{id}` · `GET /teams/{id}/sessions`
- **Agents:** `POST /teams/{id}/agents` · `GET /teams/{id}/agents` · `GET /agents/{id}` · `PUT /agents/{id}` · `DELETE /agents/{id}`
- **Sessions/runs:** `POST /teams/{id}/sessions` · `GET /sessions/{id}` · `POST /sessions/{id}/run` · `POST /sessions/{id}/resume`
- **Providers (Settings→AI):** `POST/GET /providers/connections` · `POST/GET /providers/catalog` (`?supports_tools=`) · `POST/GET /providers/profiles`
- **Knowledge:** `POST/GET /teams/{id}/knowledge`
- **Memory:** `GET /agents/{id}/memory` → `{ agent_id, team_id, private, shared }`
- **Chat:** `POST /conversations` · `GET /conversations` · `GET /conversations/{id}` · `POST /conversations/{id}/messages` · `POST /conversations/{id}/attachments` · `POST /conversations/{id}/attachments/{aid}/save-to-knowledge`
- **Read endpoints added in Slice 0:** `GET /sessions` (org-scoped list) · `GET /runs/{id}/artifact` · `GET /stats`
- **Read endpoint added in Slice 4 follow-up:** `GET /sessions/{id}/runs` (a session's runs, newest first → History reaches the terminal run's artifact)
- **Streaming (WS):** `WS /sessions/{id}/stream?run_id=&after_seq=` · `WS /conversations/{id}/stream?run_id=&after_seq=`
- **Health:** `GET /health`

### 5.4 Key request/response DTOs (mirror `backend/app/schemas/*`)
- `RunLaunch` → `{ query: string, max_rounds?: number=3, confidence_threshold?: number=0.85, deep_collaborate?: boolean=true }`
- `RunLaunchResponse` → `{ run: RunRead, interrupted: boolean, stream_url: string }`
- `ResumeRequest` → `{ run_id: string, decision: 'approve'|'edit'|'reject', content?: string, reason?: string }`
- `ConversationCreate` → `{ team_id?: string, model_ref?: object, title?: string, is_playground?: boolean, thread_id?: string }` (no-team requires `model_ref`; playground requires `team_id`)
- `MessageCreate` → `{ content: string, deep_collaborate?: boolean=false }`
- `SendMessageResponse` → `{ assistant_message: MessageRead, run?: RunRead|null, stream_url?: string|null }`
- Provider DTOs: `ConnectionCreate/Read` (`provider, base_url, api_key_ref, …`), `CatalogModelCreate/Read` (`model_identifier, model_type, supports_tools, …`), `ProfileCreate/Read` (`default_model_id, temperature, top_p, max_tokens, reasoning_level, json_mode, streaming`).
- Full field lists: read the matching Pydantic model in `backend/app/schemas/` while writing `types/api.ts` — that file is the source of truth.

### 5.5 Org tenancy
Every REST/WS call must carry org context. Confirm the mechanism in `backend/app/core/deps.py` / `core/identity.py` (dev seeds a default org; likely a header or default fallback). Centralize it in `lib/org.ts` and inject on every request.

---

## 6. Screen → endpoint / event map (condensed)

| Screen | REST | Stream |
|---|---|---|
| **Workspace** (flagship) | `POST /teams/{id}/sessions` → `POST /sessions/{id}/run` → `POST /sessions/{id}/resume` | `WS /sessions/{id}/stream` → all §5.2 events |
| · AgentGraph (@xyflow) | roster from `run_start`; `GET /teams/{id}/agents` | `agent_turn_start`, `reasoning`, `tool_call`, `critique` → node status |
| · DebateThread | — | `contribution.content_blocks`, `critique` |
| · Blackboard / output | `GET /runs/{id}/artifact` | `consensus_update`, `synthesis`, `run_finished` |
| · HITL gate | `POST /sessions/{id}/resume` | `hitl_request` → `hitl_resolved` |
| **Chat** | `POST /conversations` → `POST .../messages` → `.../attachments` | team turn: `SendMessageResponse.stream_url` → `WS /conversations/{id}/stream` |
| **Teams / Agent Builder** | teams + agents CRUD | — |
| **Settings→AI** | providers connections/catalog/profiles | — |
| **Knowledge** | `GET/POST /teams/{id}/knowledge` | — |
| **Memory** | `GET /agents/{id}/memory` | — |
| **History** | `GET /sessions`, `GET /sessions/{id}`, `GET /runs/{id}/artifact` | replay `WS …?after_seq=0` |
| **Dashboard** | `GET /stats` | — |

---

## 7. Slice plan (each is a reviewable milestone — stop between)

### Slice 0 — Backend contract completion *(lands in `backend/`, prerequisite for the flagship)*
- **Goal:** make the backend emit the **full §24.4 event set** and add the read endpoints, so the frontend can render the real Session Workspace and History/Dashboard.
- **Scope:**
  - Emit (with the run/seq envelope through the existing emitter): `round_start`, `agent_turn_start`, `reasoning` (from the agent message stream), `tool_call` + `tool_result` (from tool messages), `critique` (from the blackboard `critiques`), and add `content_blocks` to `contribution` and `synthesis`.
  - **R1:** verify how per-token `reasoning` / tool events surface in `graph.astream` (stream modes `messages`/`updates`, langgraph 1.2.x) via the LangChain docs MCP before implementing — these come from the agent's message stream, not the additive `events` channel.
  - Add read endpoints: `GET /sessions` (org-scoped), `GET /runs/{id}/artifact`, `GET /stats`. RLS-scoped, thin routers (R5).
- **Acceptance:** a run's WS stream now carries round/turn/reasoning/tool/critique events + contribution/synthesis content_blocks; the three GET endpoints return data; backend tests green (unit per node/emitter + an integration test asserting the new event sequence). No drift from §24.4.

### Slice 1 — Integration seam *(`frontend/`)*
- **Goal:** the wiring layer + offline-runnable shell, **no live backend needed yet**.
- **Scope:** port theme → `globals.css` + `tailwind.config.ts`; build `types/agui.ts` (mirror §5.2) + `types/api.ts` (mirror `schemas/*`); `lib/api/*` (typed client, org header); `lib/ws/*` (replay-then-live by `seq`, `after_seq` reconnect); `store/session-store.ts` (Zustand AG-UI event-reducer); React Query provider in `app/layout.tsx`; `mocks/agui-replayer.ts`; remove the reference's `@google/genai` + `express/server.js` pattern (we run Next.js); add a Next rewrite/proxy or direct base-URL calls to FastAPI.
- **Acceptance:** `pnpm/npm run type-check` + `lint` clean; the session store reduces a replayed mock stream into render-ready state; app boots with the ported theme.

### Slice 2 — Session Workspace live stream *(flagship, `frontend/`)*
- **Goal:** replace the reference's `setTimeout` simulation with the **real run → WS → reducer → panels** flow.
- **Scope:** Workspace page; create-session + launch-run controls (goal, τ, max_rounds, deep toggle); subscribe to `WS /sessions/{id}/stream`; AgentGraph (@xyflow) driven by `agent_turn_start`/`reasoning`/`tool_call`/`critique`; DebateThread from `contribution`/`critique`; Blackboard + output from `consensus_update`/`synthesis`/`run_finished`; **HITL gate** (approve/edit/reject → `/resume`). Reuse reference visuals (`artistic-pane`, etc.).
- **Acceptance:** launch a real run, watch live events render round-cadenced, hit the HITL gate, resume, see synthesized output. Reconnect mid-run (`after_seq`) without duplicate events. One e2e-ish test (mock replayer) for the reducer→panels path.

### Slice 3 — Chat & Playground *(`frontend/`, FRONTEND_SPEC §9A, ARCH §8.5)*
- **Scope:** conversations list + thread; team vs no-team (`model_ref`) creation; Deep Collaborate toggle; attachments (transient) + save-to-knowledge; team turns expand into the Workspace renderer via `stream_url` / `WS /conversations/{id}/stream`; Playground = ephemeral team chat.
- **Acceptance:** team chat (fast 1-round) and Deep Collaborate both work against the backend; no-team single-LLM chat replies directly; playground excluded from history.

### Slice 4 — CRUD screens *(`frontend/`)*
- **Scope:** Teams + Agent Builder (teams/agents CRUD, capabilities, profile/override model); **Settings→AI** (Connections → Catalog → Profiles, the 3-layer model replacing the reference's flat `InferenceProfile`); Knowledge (sources list/register; note ingestion worker deferred → status `pending`); Memory Explorer (`GET /agents/{id}/memory`); History (`GET /sessions` + artifact) ; Dashboard (`GET /stats`).
- **Acceptance:** create a team + agents, configure a connection/catalog/profile, register a knowledge source, read agent memory, browse history, see dashboard tiles — all against the backend.

**Final acceptance (whole integration):** on the reference's look — create team+agents → configure provider/model → team chat (fast) + Deep Collaborate → launch a session → watch the live AG-UI stream in the Workspace → get a synthesized output — all against the real backend, org-scoped.

---

## 8. Definition of Done (every slice)
- Verified APIs/imports (R1), versions pinned.
- Real primitives, no reinvention (R2).
- Integrates with the architecture; no contract/locked-decision drift (R4).
- TS `strict`, no unjustified `any`, validated at boundaries, no secrets, no `console.log` (R5).
- Tests added and passing; any bug fixed gets an RCA + regression test (R3).
- Reference theme preserved; matches the cited spec section; deviations flagged + approved (R6).
- §9 Progress Tracker updated.

---

## 9. Progress Tracker (update after each slice)
- [x] **Slice 0** — Backend §24.4 emission + read endpoints (`GET /sessions`, `/runs/{id}/artifact`, `/stats`) — ✅ done, 185 tests green; §5.2 shapes reconciled (`run_start.roster` = id strings, `confidence` folded into `contribution`).
- [x] **Slice 1** — Integration seam — ✅ done. Theme ported (`app/globals.css` + `tailwind.config.ts`, fonts via `next/font`); `types/agui.ts` + `types/api.ts` mirror the verified contract; `lib/api/*` (client + 7 resource modules + `lib/org.ts` `X-Org-Id` header) and `lib/ws/agui-client.ts` (replay-then-live, `after_seq` reconnect, seq-validated); pure `store/session-reducer.ts` + Zustand `store/session-store.ts`; `mocks/agui-replayer.ts`. App shell (layout + RQ provider + nav, no fake login/sim) with home seam self-test + 7 placeholder routes. Verified: `tsc --noEmit` 0 errors, `next lint` clean, 11 reducer tests green, `next build` all 11 routes. Next bumped `15.3.3 → ^15.3.9` (CVE-2025-66478 fixed in 15.3.6+); re-verified clean.
- [x] **Slice 2** — Session Workspace live stream + HITL — ✅ done. Real flow: `POST /teams/{id}/sessions` → `POST /sessions/{id}/run` (React Query mutations) → `AGUIStream` (WS) → `applyEvent` → Zustand → panels. Built `components/agent-graph/{graph-model.ts,agent-node.tsx,agent-graph.tsx}` (@xyflow/react v12, R1-verified), `debate-thread`, `blackboard/{output-canvas,consensus-detail}`, `hitl-gate`, `content-blocks`, `workspace/{session-header,consensus-ring,launch-config}`, hooks `features/sessions/{use-session-stream,use-run-controls}`, and the wired `app/workspace/page.tsx` (replaces the reference setTimeout sim). Pure view-model builders (`buildGraphModel`/`buildDebateTimeline`/`buildConsensusModel`) cover the reducer→panels path with 10 node-env tests (21 total green); `tsc` 0 errors, `next lint` clean, `next build` all 11 routes. WS stays open across the HITL gate (resume continues the same run_id); reconnect/replay via `after_seq` + seq-dedup reused from Slice 1. **§9.10 inter-agent edges (resolved honestly vs the spec mock):** (1) **Dispatch fan-out** — a synthetic, frontend-only **Orchestrator hub** node + dispatch edges orchestrator→each roster agent, derived purely from the real `run_start` (the `Send()` fan-out); animated in the opening round (beat 1), faint after. No backend/contract change, no drift (orchestrator stays the passive entry node, just visualized). (2) **Critique edges** — `critique` events (sender→target, current round, severity→thickness). (3) **Reply edges — ✅ now built (post-Slice-2 follow-up).** The earlier blocker (the `Contribution` model carried no peer correlation) was resolved with a real backend contract change, not a frontend fabrication: `ContributionOut.responds_to: list[str]` (the agent declares which prior-round peers it builds on), server-validated by `_valid_responds_to` (drops self / hallucinated / non-prior-round ids), stamped onto the blackboard `Contribution`, and emitted on the `contribution` event. Frontend now mirrors it (`ContributionData.responds_to?`, reducer `respondsTo`) and `buildGraphModel` draws accent reply edges responder→author for the **current round only**, re-filtered to roster ids that aren't self (R5 boundary). Tests added in `graph-model.test.ts` (build / round-cadence drop / self+non-roster filter). No drift: this is the backend `responds_to` form of §9.10's `in_reply_to`, so every edge is still backed by a real event.
- [x] **Slice 3** — Chat & Playground — ✅ done. Real flow against the backend, reusing the Slice-1 seam + Slice-2 renderer (no new engine, R2). Built `features/chat/{chat-model.ts,use-chat.ts}` (pure domain logic + React Query hooks), `components/chat/{chat-list,new-chat-dialog,chat-thread,message-list,message-bubble,chat-composer,attachment-chip,playground-banner,run-replay-view}.tsx`, and the wired `app/chat/page.tsx` (replaces the placeholder). Modes (ARCH §8.5.1): **team** chat (fast `max_rounds=1`) with a per-turn **Deep Collaborate** toggle → `MessageCreate.deep_collaborate`; **no-team** single-LLM via `model_ref={profile_id, model_id?}` (shape confirmed in `single_agent.py`); **playground** (`is_playground`, team-only, excluded from `GET /conversations`). A team turn's `SendMessageResponse.{run,stream_url}` expands into `RunReplayView`, which mounts the **exact** Slice-2 panels (AgentGraph/DebateThread/OutputCanvas/ConsensusDetail — pure store readers) fed by `WS /conversations/{id}/stream?after_seq=0` → Zustand (never React Query). Attachments upload transient (new `apiUpload` multipart helper + `conversationsApi.uploadAttachment`); save-to-knowledge is team-only. Verified: `tsc` 0 errors, `next lint` clean, 38 tests green (11 new pure `chat-model` tests: mode/guards, model_ref, validation mirroring the backend validator, immutable transcript fold pending→resolved/failed), `next build` all 11 routes. **Three honest reconciliations vs the spec (R4 — conformed to the *implemented* backend, no fork):** (1) **Transcript GET — ✅ now FIXED (post-Slice-3 follow-up, backend+frontend).** The earlier gap (no `GET /conversations/{id}/messages`) was a genuine missing read endpoint — the `Message` rows are persisted, only the route was absent. Added `GET /conversations/{id}/messages` → `list[MessageRead]`, RLS/org-scoped, ordered by `created_at` (backed by the existing `(conversation_id, created_at)` index); added a generic opt-in `order_by` to `OrgScopedRepository.list`. Frontend rehydrates on (re)open: `conversationsApi.listMessages` + `useMessages` + `fromServerMessage` (re-derives a team turn's stream url so "Expand" survives a reload) seeded into `ChatThread`. Regression tests: backend `test_conversation_messages_rehydrate_in_order` (order + 404), frontend 2 mapper tests. (2) **No-team doesn't stream** — `_no_team_turn` returns the reply synchronously with no run/stream (§8.5.4 describes streaming as intent); rendered directly from the POST. (3) **Team turn is blocking** — `drive_run` completes inside the POST and `run_id` only returns after; so "Expand" is a full **replay** (after_seq=0), not a live tail — the same replay-then-live `AGUIStream` path handles it identically.
- [x] **Slice 4** — CRUD: Teams/Agent Builder, Settings→AI, Knowledge, Memory, History, Dashboard — ✅ done. All reads/writes via React Query (REST DTOs; streaming store untouched, locked decision). Shared `components/crud/primitives.tsx` (CrudPage/Pane/Field/controls/Toggle/buttons/StatusPill/EmptyState/`QueryBoundary`) + `components/crud/resource-pickers.tsx` (TeamPicker/AgentPicker) keep six screens small + on-theme. Pure, tested form→DTO modules: `features/agents/agent-model.ts` (capability toggling + create/update mapping) and `features/providers/provider-model.ts` (3-layer Connection/Catalog/Profile mapping, numeric parsing). Hooks: `features/{dashboard,teams,agents,providers,knowledge,memory,history}/use-*.ts` (mutations invalidate the matching list key). Screens: **Dashboard** (`GET /stats` tiles, replaces the Slice-1 self-test); **Teams + Agent Builder** (master-detail; teams list/create → roster create/edit/**delete** with the five real capability toggles from `Capabilities` (R1/R4 — `rag/web_search/code_interpreter/doc_chart/image_gen`), profile + tool-capable override pickers); **Settings→AI** (3-layer panels, `supports_tools` gate, embeddings never claim tool support); **Knowledge** (team-scoped register/list, `pending` status honest); **Memory** (team→agent → private/shared read-only); **History** (org session list). `slice-placeholder.tsx` deleted (all routes wired). Verified: `tsc` 0 errors, `next lint` clean, **59 tests green** (19 new: agent-model 9 + provider-model 10), `next build` all routes. **History artifact view — ✅ now CLOSED (Slice-4 follow-up, backend+frontend).** The flagged gap (a session carried no run id) was resolved with a real backend read, not a fork: added `GET /sessions/{id}/runs` → `list[RunRead]` (org-scoped, 404 on unknown session, ordered by `created_at` desc so row 0 is the latest run — `started_at` is nullable). Frontend now master-details History: select a session → `useSessionRuns` lists its runs → pure `terminalRun`/`hasArtifact` (`features/history/history-model.ts`, tested) pick the latest *finished* run → `useArtifact` (`GET /runs/{id}/artifact`) renders its synthesized output; a still-running run shows "in progress" instead of fetching a guaranteed 404. Backend regression `test_list_session_runs_backs_history_artifact_view` (lists the launched run + 404). Verified: backend mypy 100 files + ruff + 4 acceptance tests green (real Postgres); frontend tsc + lint + **63 tests** (4 new) + build green. **Workspace replay deep-link also now done** (frontend-only): History run rows → `/workspace?session=&run=` attaches the existing `AGUIStream` to the run's WS (after_seq=0, replay-then-live) via the same reducer→panels path; `Suspense`-wrapped `useSearchParams`; header shows a "Replay" badge instead of a fake live clock.

---

## 10. Per-slice PROMPTS (paste into a fresh chat)

> Each prompt is self-contained. The agent reads the cited docs, restates the rules, does **only** that slice, writes tests, and stops.

### PROMPT — Slice 0 (Backend contract completion)
```
NEX AGI — Slice 0 (backend). Read CLAUDE.md (R1–R6 + Teaching Mode §2A), FRONTEND_INTEGRATION_PLAN.md
(esp. §5 contract + §7 Slice 0), and ARCHITECTURE.md §24 (AG-UI), §8 (mesh/consensus), §21.4 (run
sequence). Restate the locked decisions and R1–R6 before doing anything.

Goal: complete the AG-UI §24.4 emission and add read endpoints in backend/.
1. R1 FIRST: query the LangChain docs MCP for how langgraph `graph.astream` surfaces per-token agent
   reasoning and tool calls (stream modes `messages` vs `updates`, version="v2", langgraph 1.2.x).
   State what you confirmed before coding.
2. Emit through the existing RunEventEmitter: round_start, agent_turn_start, reasoning, tool_call,
   tool_result, critique; add content_blocks to `contribution` and `synthesis` (§24.6). Keep the
   envelope/seq/persist/fan-out path unchanged. No new event types beyond the locked §24.4 catalog.
3. Add read endpoints (thin routers, RLS/org-scoped, R5): GET /sessions (org list), GET /runs/{id}/artifact,
   GET /stats. Add Pydantic DTOs.
4. Tests first where practical (R3/R5): unit per new emission + an integration test asserting the new
   event sequence on a run; tests for the 3 endpoints. ruff + mypy clean.
Do NOT touch the frontend. Stop at the slice boundary with a summary + the exact emitted `data` shapes
so FRONTEND_INTEGRATION_PLAN.md §5.2 can be confirmed. End with Teaching-Mode key concepts + a check question.
```

### PROMPT — Slice 1 (Integration seam)
```
NEX AGI — Slice 1 (frontend seam). Read CLAUDE.md (R1–R6 + §2A), FRONTEND_INTEGRATION_PLAN.md (esp.
§3 stack, §4 layout, §5 contract, §7 Slice 1), FRONTEND_SPEC.md §18 (mock replayer). Restate locked
decisions + R1–R6 first.

Target stack is Next.js 15 App Router + Tailwind v3 + Zustand + React Query + @xyflow/react +
framer-motion (see frontend/package.json). The reference (reference/nex-agi) is the DESIGN source only.
Build the wiring layer — no live backend required:
1. Port the theme: reference/nex-agi/src/index.css → frontend/app/globals.css (artistic-* classes
   verbatim) + tailwind.config.ts (Inter/JetBrains Mono via next/font, emerald #10b981, bg #050506).
2. types/agui.ts mirroring §5.2 (envelope + discriminated event union). types/api.ts mirroring
   backend/app/schemas/* (read those files — they are the source of truth).
3. lib/api/* typed REST client (one module per resource) with org context from lib/org.ts (confirm the
   mechanism in backend/app/core/deps.py). lib/ws/* AG-UI client: replay-then-live, reconnect via after_seq,
   dedup by seq. store/session-store.ts: Zustand reducer that folds AG-UI events into render-ready run state.
4. React Query provider + root layout shell (header nav ported from reference App.tsx, real routes, no fake
   login simulation/toasts). mocks/agui-replayer.ts (canned stream). Remove reference's @google/genai +
   express/server.js pattern; run via Next.js (proxy/base-URL to FastAPI).
Acceptance: type-check + lint clean; store reduces the mock stream; app boots with the ported theme.
Write a unit test for the session-store reducer. Stop at the boundary. End with key concepts + a check question.
```

### PROMPT — Slice 2 (Session Workspace live stream)
```
NEX AGI — Slice 2 (frontend, flagship). Read CLAUDE.md (R1–R6 + §2A), FRONTEND_INTEGRATION_PLAN.md
(§5 contract, §6 map, §7 Slice 2), FRONTEND_SPEC.md §9 + §9.10 (Session Workspace), ARCHITECTURE.md
§24. Restate locked decisions + R1–R6 first. Slices 0 and 1 are done.

Build the Session Workspace against the REAL backend, keeping the reference visuals (artistic-pane, etc.):
- Controls to create a session (POST /teams/{id}/sessions) and launch a run (POST /sessions/{id}/run with
  query, confidence_threshold (τ), max_rounds, deep_collaborate). Subscribe to WS /sessions/{id}/stream?run_id=.
- AgentGraph via @xyflow/react driven by agent_turn_start/reasoning/tool_call/critique (round-cadenced,
  event-derived — NO decorative fiction). DebateThread from contribution.content_blocks + critique.
  Blackboard/output from consensus_update/synthesis/run_finished.
- HITL gate (approve/edit/reject) → POST /sessions/{id}/resume; render hitl_request, then hitl_resolved.
- Replace the reference's setTimeout simulation entirely. Streaming → Zustand store, NOT React Query.
Acceptance: launch a real run, watch live round-cadenced events, hit + resolve the HITL gate, see the
synthesized output; reconnect mid-run via after_seq with no duplicates. Add a reducer→panels test using the
mock replayer. Stop at the boundary. End with key concepts + a check question.
```

### PROMPT — Slice 3 (Chat & Playground)
```
NEX AGI — Slice 3 (frontend). Read CLAUDE.md (R1–R6 + §2A), FRONTEND_INTEGRATION_PLAN.md (§5, §6, §7
Slice 3), FRONTEND_SPEC.md §9A (Chat & Playground), ARCHITECTURE.md §8.5 (chat modes). Restate locked
decisions + R1–R6 first. Slices 0–2 are done.

Build Chat & Playground against the backend, reference visuals preserved:
- Conversations list (GET /conversations, playgrounds excluded) + thread. Create via POST /conversations:
  team chat (team_id) vs no-team single-LLM (model_ref). Deep Collaborate toggle (team only) → MessageCreate
  .deep_collaborate. Attachments (POST .../attachments, transient) + save-to-knowledge.
- A team turn returns SendMessageResponse.run + stream_url → expand into the Slice-2 Workspace renderer via
  WS /conversations/{id}/stream. No-team turn replies directly (no run). Playground = ephemeral team chat.
Acceptance: team chat (fast 1-round) + Deep Collaborate both work; no-team single-LLM replies directly;
playground excluded from history. Add tests for the conversation/turn flow. Stop. End with key concepts + a check question.
```

### PROMPT — Slice 4 (CRUD screens)
```
NEX AGI — Slice 4 (frontend). Read CLAUDE.md (R1–R6 + §2A), FRONTEND_INTEGRATION_PLAN.md (§5, §6, §7
Slice 4), FRONTEND_SPEC.md (Teams, Agent Builder, Settings→AI, Knowledge, Memory, Dashboard sections),
ARCHITECTURE.md §9/§27 (model resolution). Restate locked decisions + R1–R6 first. Slices 0–3 are done.

Build the CRUD screens against the backend, reference visuals preserved:
- Teams + Agent Builder: teams & agents CRUD (capabilities, profile_id, override_model_id).
- Settings→AI: Connections → Catalog (?supports_tools) → Profiles (the 3-layer model; replace the
  reference's flat InferenceProfile).
- Knowledge: list/register sources (GET/POST /teams/{id}/knowledge); note ingestion deferred (status pending).
- Memory Explorer: GET /agents/{id}/memory (private + shared). History: GET /sessions + GET /runs/{id}/artifact
  (+ replay via after_seq). Dashboard: GET /stats.
All reads via React Query; respect org_id tenancy. Acceptance: full create-team→agents→provider/model→
knowledge→memory→history→dashboard loop works against the backend. Add tests for the CRUD hooks. Stop.
End with key concepts + a check question.
```

---

## 11. Notes / open items to confirm during execution
- **Org header name** — confirm in `backend/app/core/deps.py` (Slice 1).
- **`model_ref` shape** for no-team chat — ✅ resolved (Slice 3): `{ profile_id: string (required), model_id?: string }` (confirmed in `backend/app/chat/single_agent.py:_ref_from_model_ref`).
- **`GET /conversations/{id}/messages`** — ✅ RESOLVED (Slice-3 follow-up): added the RLS-scoped, ordered transcript endpoint + frontend rehydration. Reopening a saved conversation now replays its persisted turns; team turns stay expandable (stream url re-derived from `run_id`).
- **Team turns / sessions were blocking, not live** — ✅ FIXED (live-execution rearchitecture, backend+frontend). Root cause: `POST /sessions/{id}/run` and `/conversations/{id}/messages` `await drive_run` to completion *inside* the request, returning `run_id` only after → every WS connect was a pure **replay** (sessions included). This **deviated** from the locked design (§24.1 "live collaboration view", §24.5 "a run executes on one replica while a client is attached to another", §21.4 HITL pauses mid-run). Fix: runs now execute in a **background task** (`spawn_run` → `_execute_run` on its own RLS-scoped session); launch returns `run_id` immediately (status `running`); the graph streams live via the existing per-event `emitter.append`+`publish`. Also fixed the now-load-bearing replay→live **handoff race** (subscribe-before-replay + eager in-process queue registration + seq-dedup) and registered the run→org mapping synchronously at `spawn_run` (else a mid-run WS replay hit `RunOrgUnknown`). Chat team turns return a **pending** assistant message filled on completion; the frontend is server-driven (`useMessages` polls while pending, Expand streams live). Acceptance tests reworked to drain the live WS + poll async completion; **all 186 backend tests green**. HITL resume is background too. (Also fixed a pre-existing `runtime.py` `_to_blackboard_update(blackboard=…)` bug — the Slice-2 `responds_to` refactor missed two callers — which had 8 tests red; now green + mypy clean.)
- **No-team chat streaming** — ✅ FIXED (backend+frontend). `_no_team_turn` now creates a **lightweight single-agent run** (no mesh, no consensus — the §3 locked constraint) that executes in the background and streams its trajectory over `WS /conversations/{id}/stream`, realizing §8.5.4 ("no-team emits text/reasoning/tool_call events"). New `app/chat/noteam_stream.py` drives it, reusing the **shared** `runtime.turn_events` projection (promoted from `_turn_events`) so the single-agent and mesh surfaces emit identically (round-cadenced, post-hoc — not per-token, CLAUDE §3). `single_agent.run_noteam_agent` now returns `(reply, trajectory_messages)`. Emits `run_start`/`round_start`/`agent_turn_start`/`reasoning*`/`tool_call*`/`tool_result*`/`contribution`/`run_finished`. The §8.5.2 "without a run" prose is superseded here by the §24 run-keyed streaming contract (the §3 locked table only forbids mesh/consensus — a single-agent run is consistent). Frontend needed **no structural change** — `fromServerMessage`/`isPendingAssistant`/Expand already handle any assistant-with-run generically; no-team turns are now pending→filled + expandable like team turns (1 new test). User-approved (R4). Verified: 186 backend tests, mypy 100 files, ruff clean; frontend tsc+lint+40 tests+build green.
- **`run_start.roster` exact fields** — ✅ resolved (Slice 0): `string[]` of agent ids; frontend joins with `GET /teams/{id}/agents`.
- **`confidence` event** — ✅ resolved (Slice 0): folded into `contribution.data.confidence`; no standalone event.
- **Knowledge status lifecycle** — ingestion worker is deferred; sources stay `pending` (Slice 4 caveat).
- **History artifact view** — ✅ RESOLVED (Slice-4 follow-up): added `GET /sessions/{id}/runs` (org-scoped, newest-first) + wired History master-detail (session → runs → terminal-run artifact via `GET /runs/{id}/artifact`). Pure `terminalRun`/`hasArtifact` tested.
- **Workspace replay deep-link** — ✅ RESOLVED (follow-up, frontend-only, no backend/contract change): History run rows link to `/workspace?session=&run=`; the Workspace reads the params (under a `Suspense` boundary, App-Router requirement), resolves the run's team via `useSession` (roster labels), and attaches the existing `AGUIStream` to `WS /sessions/{id}/stream?run_id=&after_seq=0` — full replay then live — through the **same** `useSessionStream`→reducer→panels path (R2, no new streaming machinery). `ActiveRun.replay` flips the header from a (misleading) live clock to a "Replay" badge; a `consumedDeepLink` ref stops Reset from re-attaching. Any run is replayable (a still-running one live-tails, §24.5). Verified: tsc + lint + 63 tests + build (`/workspace` still static ○).
- **Agent capability keys** — ✅ resolved (Slice 4): the five real keys are `rag/web_search/code_interpreter/doc_chart/image_gen` (source of truth `backend/app/agents/config.py:Capabilities`, filtered by `snapshot.py`). The Agent Builder offers exactly these; the schema docstring's older `doc_chart/image_gen`-only mention was superseded.

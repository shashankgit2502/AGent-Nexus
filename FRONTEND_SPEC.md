# NEX AGI — Frontend Specification (v2.0, backend-aligned)

**Status:** Reviewed & revised from the v1.0 Master Spec.
**Scope:** Layout & information architecture (visual polish to be done later with Stitch / 21st.dev).
**Pairs with:** `ARCHITECTURE.md` — this frontend consumes the AG-UI event contract (§24), A2A intents (§23), model-resolution layer (§9/§27), memory (§10/§25), skills (§11/§26), and knowledge (§10.5).

> **What changed from v1.0** is marked inline with **△** and summarized in §20. The three structural changes: multi-pane Session Workspace (was a vertical stack), consolidated navigation (was 9 flat items), and explicit AG-UI/A2A alignment.

---

## 1. Product vision

NEX AGI is a **Multi-Agent Operating System**, not a chatbot. The user observes and steers an autonomous engineering team converging on a shared goal. It should feel like Cursor / Kiro / Linear / GitHub PRs / Vercel — a real-time engineering tool — and explicitly **not** like a generic SaaS dashboard, AutoGen Studio, Flowise, or a chat app.

The **Session Workspace is the product.** ~70% of design and engineering effort goes there; every other screen exists to feed it.

---

## 2. Design principles

1. **Session-first.** The Session Workspace is the flagship; everything else supports it.
2. **Professional engineering tool.** Visual language of Cursor / Kiro / Linear. No neon, cyberpunk, heavy gradients, or glow.
3. **Information density.** Rich, scannable, clear hierarchy, high signal. No decorative empty space.
4. **△ Lifecycle-driven disclosure.** Panels change prominence with the run's phase — the Final Output is dormant during debate and takes center stage at synthesis. Layout follows the state machine, not a fixed scroll.
5. **△ Animation communicates state, never decorates.** Every motion encodes something real (an agent thinking, a message flowing, consensus rising).

---

## 3. Technology

| Concern | Choice |
|---|---|
| Framework | Next.js 15 (App Router) + TypeScript |
| Styling | TailwindCSS + shadcn/ui |
| Graph viz | React Flow — **△ note:** now published as `@xyflow/react`; pin at install |
| Animation | Framer Motion |
| Client state | Zustand |
| Server state | TanStack Query |
| Realtime | WebSocket + AG-UI events (§18) |

**△ State boundary (important):** live session/run state (the AG-UI stream) lives in a **Zustand session store fed by an event-reducer** — *not* TanStack Query. TanStack Query is only for REST CRUD (teams, agents, providers, catalog, profiles, knowledge, memory). Don't shoehorn the stream into the query cache.

---

## 4. Theme (unchanged from v1.0)

| Token | Value |
|---|---|
| Background | `#09090B` |
| Surface | `#111113` |
| Card | `#18181B` |
| Border | `#27272A` |
| Primary text | `#FAFAFA` |
| Secondary text | `#A1A1AA` |
| Accent | `#8B5CF6` |
| Success | `#22C55E` |
| Warning | `#F59E0B` |
| Danger | `#EF4444` |

**Typography:** Inter (primary), JetBrains Mono (monospace).
**Radius:** cards 16px, buttons 12px, inputs 12px.
**Shadows:** subtle only — no large glows or heavy shadows.
**Layout:** desktop-first; sidebar 280px; content fluid; max width 1800px; 4px spacing system.

---

## 5. △ Information architecture & navigation (consolidated)

v1.0 had 9 flat sidebar items with Knowledge/Memory duplicated globally and per-team, and config pages mixed with daily destinations. Revised to ~5 primaries + a Settings home for configuration.

### Sidebar (primary destinations)
- **Dashboard** — global, informational only
- **Chat** — conversational entry: chat with a Team or with a single LLM (no team); file upload (§9A)
- **Teams** — the workspace hub (contains agents, skills, knowledge, memory, sessions as tabs)
- **Sessions** — global list of runs across teams (entry to the Session Workspace)
- **Knowledge** — global rollup (read-only view across teams); authoring is team-scoped
- **Settings**

### Settings home (configuration, not daily use)
- **AI → Providers** (connections)
- **AI → Model Catalog**
- **AI → Inference Profiles**
- **Workspace / Members / RBAC**
- **General**

### Top navigation
Workspace switcher · global search · **Command Palette (⌘K)** · notifications · user profile.

**Rationale:** Knowledge and Memory are team-scoped in the backend, so their authoring lives inside the Team Workspace; only a read-only global rollup is promoted to the sidebar. Providers/Models/Profiles are setup tasks, so they live under Settings → AI.

---

## 6. Route map

```
/                                  Dashboard
/chat                              Chat list / new chat
/chat/[conversationId]             Chat thread (team or no-team)
/teams                             Teams list
/teams/[teamId]                    Team Workspace (tabs: overview|agents|skills|knowledge|memory|sessions)
/teams/[teamId]/agents/[agentId]   Agent Builder
/teams/[teamId]/playground         Playground (ephemeral team chat)
/sessions                          Sessions list (global)
/sessions/[sessionId]              ★ Session Workspace (the product)
/knowledge                         Global knowledge rollup (read-only)
/settings/ai/providers
/settings/ai/models
/settings/ai/profiles
/settings/workspace
```

---

## 7. Global layout

`AppShell` = `AppSidebar` (280px) + `TopNavigation` + content. `CommandPalette` mounted globally. `WorkspaceSwitcher` in the top nav. All shells share a `ConnectionStatus` indicator (driven by the session WebSocket when inside a session).

---

## 8. Core user journey

`Create Team → Create Agents → Assign Skills → Configure Models → Run Session → Observe Collaboration → Reach Consensus → Generate Output.`

---

## 9. ★ Session Workspace (flagship) — △ multi-pane layout

**This replaces the v1.0 vertical stack.** A vertical scroll can't show the mesh, the debate, and the output at once, which breaks the "understand in 10 seconds" goal. Instead, an IDE-style multi-pane workspace where panes change prominence by run phase.

### 9.1 Layout zones

```
┌───────────────────────────────────────────────────────────────────────────┐
│ SESSION HEADER:  Goal · Status · Runtime · Round · [Consensus ring] ·       │
│                  Pause · Resume · Stop                                      │
├──────────────────────────────────────────────┬────────────────────────────┤
│                                                │                            │
│   AGENT NETWORK  (React Flow mesh — hero)      │   DEBATE  (right rail)     │
│   nodes = agents, edges light up on message    │   PR-style threaded        │
│   node size/border = confidence                │   contributions+critiques  │
│                                                │   (maps to A2A intents)    │
│                                                │                            │
├──────────────────────────────────────────────┴────────────────────────────┤
│ BOTTOM DOCK (tabs):  Blackboard  |  Consensus detail  |  Activity/Timeline  │
└───────────────────────────────────────────────────────────────────────────┘

   FINAL OUTPUT: collapsed during debate → expands to a center Canvas pane
                 when synthesis begins (lifecycle-driven, §9.7).
```

- **Header** is always visible and carries the compact **Consensus ring** (the at-a-glance convergence signal) plus run controls.
- **Agent Network** is the center hero; **Debate** is a persistent right rail.
- **Blackboard / Consensus detail / Timeline** share a bottom dock (tabbed) so they don't each consume a full section.
- **Final Output** is not a stacked section — it's a panel that animates into the center when the run reaches synthesis.

### 9.2 Session header
Goal, status badge, runtime clock, current round, and controls: Pause / Resume / Stop. Consensus ring (animated %) sits here for constant visibility.

### 9.3 Agent Network (React Flow)
- **Node** = agent: name, model, state, confidence.
- **States:** Thinking · Tool Calling · Critiquing · Generating · Waiting · Completed · **Error**.
- **△ Visual encoding:** node size/border intensity = confidence; edge thickness = interaction frequency.
- **△ Performance rule:** the mesh is conceptually fully-connected, but **edges animate only when a message actually flows that round** (driven by AG-UI `tool_call`/`contribution`/`critique` events). Do **not** render permanent animated particles on all O(N²) edges — that janks past ~15 agents and communicates nothing. Lit edges = who's actually talking now.

### 9.4 Debate panel (the differentiator) — △ mapped to A2A intents
Renders as a GitHub PR review thread, not a console log. Each item maps to an A2A intent (§23.3):

| A2A intent | Debate UI element |
|---|---|
| `INFORM` / `PROPOSE` | a contribution "comment" (author = agent, with confidence badge) |
| `CRITIQUE` | a "requested changes" review comment, color-coded by severity |
| `ENDORSE` | 👍 reaction / agreement marker on a target comment |
| `VOTE` | visible weighted vote tally during consensus |
| `REQUEST` / `DELEGATE` | an @-mention to a peer (advisory in v1) |

Threading uses `in_reply_to` for correlation. Messages animate in (fade + slide-up, ~300ms).

### 9.5 Consensus
Compact ring in the header (always visible) + a bottom-dock detail tab showing agreement %, mean confidence, current round, target threshold (τ), and a progress bar. Percentage changes animate smoothly (e.g. 65→72→78→85).

### 9.6 Blackboard (bottom dock tab)
Shared workspace view: contributions, critiques, shared findings/facts. Capabilities: **round filtering** and **timeline/history replay** (round scrubber promoted to v1, since scrubbing rounds is core to seeing emergence). New entries slide-up + fade-in (~300ms).

### 9.7 Final Output (lifecycle Canvas) — △
- During debate: collapsed/empty placeholder.
- At synthesis: shows "Synthesizing…", then **streams markdown progressively** (ChatGPT-Canvas style) into an expanding center pane.
- Views: Markdown · JSON · Document. Actions: Copy · Export · Open in Editor.
- On completion the pane expands and the completion state (§9.9) fires.

### 9.8 △ Connection & replay states (must-spec for a realtime tool)
- **Connecting / Live / Reconnecting / Disconnected** indicator in the header.
- On reconnect, the client sends the last `seq` seen and **replays missed events** from the server event log (AG-UI §24.8) before resuming live.
- Per-agent **Error** state surfaces in the node and debate; a failed agent is shown as an abstention, the round still completes (backend §21.5).
- First-run / empty / loading-skeleton states for every pane.

### 9.9 Completion state
When τ is reached: consensus ring completes, graph motion slows, status turns green (`#22C55E`), Final Output expands. Completion should feel rewarding (deliberate, brief celebratory motion — still tasteful, no confetti-glow).

### 9.10 ★△ Inter-agent communication animation (Option A — event-derived, round-cadenced)

**This is the "agents talking to each other" moment, and the rule is absolute: every animated edge is backed by a real event. Nothing is decorative fiction.** The backend is a parallel, round-based blackboard (agents don't message point-to-point in real time), so the animation honestly represents *real directed interactions* (critiques, endorsements, replies, votes) rather than faking a live chat wire.

**The run as a four-beat "performance":**

1. **Dispatch (`run_start`)** — the orchestrator node pulses and edges **fan out from orchestrator → all active agents**. This is the literal "orchestrator passes the query to the agents" beat and it is 100% real (the `Send()` fan-out). Strong opening animation.
2. **Deliberation (round in progress)** — active agents pulse by state (Thinking / Tool Calling / Critiquing / Generating); a **faint static full-mesh** sits in the background to say "any agent *could* reach any agent." **No inter-agent edges animate yet** — agents are working in parallel against the blackboard and haven't seen each other this round.
3. **Round resolution (`consensus_update` / round boundary)** — **stagger-animate the directed interactions that actually happened this round**, each derived from a real event, over ~1–2s, then settle back to faint. This is the visible "talking."
4. **Consensus rises** across rounds (ring 65→72→78→85); on synthesis, edges quiet and the Final Output canvas expands.

**Edge encoding (intent → style)** — driven by the A2A intents (backend §23.3) carried in AG-UI events:

| Interaction (real event) | Edge style |
|---|---|
| `INFORM` / `PROPOSE` (contribution) | neutral/accent, thin |
| `CRITIQUE` (critique event) | danger `#EF4444`; severity → thickness; sender → target |
| `ENDORSE` | success `#22C55E`; 👍 marker |
| reply (`contribution` with `in_reply_to`) | accent, references the prior author |
| `REQUEST` / `DELEGATE` | accent **dashed** (advisory in v1) |
| `VOTE` | accent, **consensus phase only** |

**Static vs active edges:** faint static full-mesh (low opacity) communicates topology; bright animated edges = real interactions *this round*. **Do not** render permanent particles on all O(N²) edges (perf + meaningless past ~15 agents, §9.3).

**Data path:** the session store's AG-UI **event-reducer** maps each relevant event (`tool_call`, `contribution` incl. `in_reply_to`, `critique`, `consensus_update`) into a transient **active-edge** entry with a short TTL; React Flow renders edges, Framer Motion animates them, TTL expiry fades them to faint.

```ts
// pseudo: event → transient edge
onEvent(e) {
  if (e.type === "critique")     addActiveEdge(e.data.sender, e.data.target, "critique", e.data.severity)
  if (e.type === "contribution" && e.data.in_reply_to)
                                 addActiveEdge(e.data.agent_id, authorOf(e.data.in_reply_to), "reply")
  if (e.type === "run_start")    e.data.roster.forEach(a => addActiveEdge("orchestrator", a, "dispatch"))
  // edges auto-fade after TTL; round boundary triggers the staggered playback
}
```

**Honesty about cadence (state this in the demo):** inter-agent edges animate **at round boundaries, not continuously**, because interactions resolve per round (backend §23.4, "eventually visible next round"). Aliveness comes from *staggered playback*, not fake continuous motion. A **round scrubber** (§9.6) can replay any round's interactions. The result reads like a deliberate engineering team reviewing each other's work in rounds — which looks more credible than frantic chat-bubble chatter, and it never lies.

---

## 9A. Chat & Playground (△ new — backend §8.5)

The **conversational entry layer**. Chat is the *input* surface; the Session Workspace (§9) is the *observation* surface. They compose: a team-chat turn can expand into the full Session Workspace.

### 9A.1 New chat
A "New chat" flow first picks a target:
- **A Team** → multi-agent chat (the team collaborates to answer).
- **No team** → single-LLM chat; the user picks a model (via the model-resolution dropdown — connection/catalog/profile).

`ChatComposer` supports text + **file upload** (drag/drop or picker). Uploaded files are **transient to the conversation** by default; a per-attachment "Save to team knowledge" action promotes them (team chats only).

### 9A.2 Team chat thread
- Standard chat transcript (`MessageList` of user/assistant turns).
- **△ Deep Collaborate toggle** in the composer: off (default) = lightweight 1-round pass, no HITL, fast; on = full multi-round consensus run.
- Each assistant turn streams via AG-UI; a turn produced by the team shows an **"Expand to Session Workspace"** affordance that opens the full mesh/debate/consensus view (§9) for that run's events. Lightweight turns show a compact inline "who contributed + confidence" strip; deep turns get the full treatment.
- Multi-turn context persists on the conversation thread (backend §8.5.2).

### 9A.3 No-team chat thread
- Plain single-model chat: streaming `text`/`reasoning`/`tool_call` blocks (same AG-UI content-block renderer, §18). No mesh graph, no consensus UI, no expand affordance.
- Model shown in the header; switchable per conversation.

### 9A.4 Playground (`/teams/[teamId]/playground`)
- Same UI as team chat (lightweight default + Deep Collaborate toggle) but **ephemeral**: a banner marks it as not saved to session history; conversations are `is_playground` and may be swept on a TTL. For quickly trying a team before committing to a real session.

### 9A.5 Components
`ChatList`, `NewChatDialog` (team-or-LLM picker + model selector), `ChatThread`, `MessageList`, `MessageBubble` (renders AG-UI content blocks), `ChatComposer` (input + file upload + Deep Collaborate toggle), `AttachmentChip`, `ExpandToSessionButton`, `PlaygroundBanner`.

---

## 9A. Chat & Playground (entry surfaces) — △ new

The primary way users *start* work (like the Claude interface you referenced): a chat. The Session Workspace (§9) stays the observation view; **Chat is the input surface.**

### 9A.1 New chat
"**+ New chat**" → pick scope: **Team** (multi-agent) or **No Team** (single LLM). No-team shows a **model picker** (from the catalog). Team chats show a **Deep Collaborate** toggle: off = fast 1-round pass (no HITL); on = full multi-round consensus (ARCH §8.5).

### 9A.2 Conversation thread
Standard user/assistant thread; composer with **file upload** + the scope/depth controls. Replies stream via AG-UI. For a team turn, the reply has an **"Expand"** affordance that opens *that turn's* live mesh / debate / consensus in the Session Workspace (§9). Uploaded files are **transient to the conversation**; a per-attachment **"Save to team knowledge"** promotes them (ARCH §8.5 / §10.5).

### 9A.3 Single-LLM chat
No team → plain single-model chat (no mesh/consensus/expand). Same composer + file upload (transient context). Model swappable per conversation.

### 9A.4 Playground
"**Try this team**" launched from a Team — an **ephemeral** team chat, **not saved** to session history. Same UI as team chat; results aren't persisted. For experimentation before committing to a real session.

### 9A.5 States & streaming
Reuse the AG-UI connection/replay states (§9.8). Team-chat "thinking" shows a compact inline live status (agents working), expandable to the full graph.

---

## 10. Team pages

### Teams list
`TeamCard`: name, description, agent count, session count, skills count. Actions: Open / Edit / Delete. Primary CTA: Create Team (`CreateTeamDialog` — name, description, goal).

### Team Workspace
Header: team name, description, goal. **Tabs:** Overview · Agents · Skills · Knowledge · Memory · Sessions. (This is where Knowledge/Memory are *authored* — the sidebar only shows the global rollup.)

### Agents tab
`AgentCard`: name, model, inference profile, memory status, current state (Ready/Running/Waiting/Error).

---

## 11. Agent Builder (three-column, unchanged structure)

- **Column 1 — Identity:** name, description, instructions / system prompt.
- **Column 2 — Knowledge:** files, URLs, databases, collections. **△** "Only use specified sources" toggle (RAG scoping) is distinct from the web-search capability (§11 note).
- **Column 3 — Execution:** provider, model, **inference profile**, **△ optional model override** (profile default + override, per backend Q1), memory profile, capabilities.
- **Bottom — Skills:** assigned as chips (Research / Planning / Review / Architecture / Coding…).

**△ Capability → tool mapping** (surface as the capability toggles; they map to backend tools, §10.5.4): RAG/Knowledge → `search_knowledge`; Web Search → live web tool; Code Interpreter → sandboxed exec; Create documents/charts; Create images. Only **tool-calling models** are selectable for mesh agents (backend §9.3 gate) — non-tool models are filtered out of the dropdown.

---

## 12. Settings → AI

### Providers
`ConnectionForm`: display name, provider type (OpenAI / Anthropic / Azure OpenAI / Ollama / OpenAI-Compatible / **△ OpenRouter**), API key (**write-only, masked**), base URL, validation status, models count, last sync. **△** Show a validation-probe result before a connection is usable.

### Model Catalog
`ModelCatalogTable`: model, provider, context window, tool-calling, vision, streaming, reasoning, status. Searchable / filterable / sortable. **△** capabilities seeded from models.dev + manual override (backend Q2); `supports_tools` filter is first-class.

### Inference Profiles
`InferenceProfileCard`: name, default model, temperature, top-P, max tokens, reasoning level, streaming, JSON mode. Agents reference a profile and **may override the model** while keeping profile settings.

---

## 13. Knowledge

Team-scoped authoring (Team Workspace → Knowledge tab) with a global read-only rollup at `/knowledge`. Sources: files, URLs, databases, collections. Actions: Upload, Delete, **Reindex**, Sync. **△** show ingestion status per source (pending/ingesting/ready/failed) and a **reindex warning** if the team's embedding model changes (pgvector dimension constraint, backend §20 note 6).

---

## 14. Memory Explorer

**△ Team → agent drill-down** (memory is per-agent-namespaced in the backend, not a flat global list). Sections aligned to the backend memory taxonomy: **Facts (semantic)** · **Experiences (episodic)** · **Session Learnings** · **Summaries**. Actions: Search · Delete · Pin. Distinguish agent-private vs team-shared (read-only) memory.

---

## 15. Dashboard (informational only)

KPI cards (Total Teams, Active Agents, Running Sessions, Knowledge Sources, Memories Stored), Recent Sessions table, Agent Activity feed, Usage metrics, Provider health. Explicitly **not** the main product.

---

## 16. Command palette (⌘K)

Search across Teams, Agents, Sessions, Knowledge, Memory, Providers, Models, Profiles, Settings. **△** Inside a session, add quick actions: jump to agent, focus debate, scrub round.

---

## 17. Animation philosophy (state-communicating)

| Moment | Motion |
|---|---|
| Agent thinking | pulse, scale 1 → 1.03 → 1, 2s, infinite |
| Agent communication | **△** edge lights up + particle travels **only when a message flows** |
| Consensus update | animated % + smooth ring fill |
| Blackboard update | slide-up + fade-in, 300ms |
| Debate message | fade-in + slide-up (PR-review style) |
| Final output | "Synthesizing…" → progressive markdown stream |
| Completion | ring completes, motion slows, status green, output expands |

---

## 18. △ AG-UI event contract (frontend ⇄ backend)

Define shared TypeScript types matching the backend AG-UI catalog (`ARCHITECTURE.md` §24.4). Event envelope: `{ type, session_id, run_id, seq, ts, data }`. Event types the UI handles: `run_start, round_start, agent_turn_start, reasoning, tool_call, tool_result, contribution, confidence, critique, consensus_update, hitl_request, hitl_resolved, synthesis, run_finished, error`.

**△ Build contract-first:** implement a **mock AG-UI event replayer** (recorded/synthetic streams) and build the entire Session Workspace against it before the backend is live. This de-risks the flagship page and guarantees the contract can't drift. The `content_blocks` array on `contribution`/`synthesis` is the **A2UI seam** — render `text`/`tool_result`/`confidence` now; a future `a2ui_component` block adds one render branch (backend §24.6–24.7).

---

## 19. Component architecture & folder structure

```
app/                # routes (§6)
components/          # shared primitives (shadcn-based)
features/
  layout/           AppSidebar, TopNavigation, WorkspaceSwitcher, CommandPalette, ConnectionStatus
  chat/             ChatList, NewChatDialog, ScopePicker(Team|No-Team), ModelPicker, DepthToggle,
                    MessageThread, MessageBubble, ChatComposer, FileUpload, ExpandToSession, PlaygroundView
  teams/            TeamCard, TeamHeader, CreateTeamDialog
  agents/           AgentCard, AgentBuilder, ModelSelector, SkillSelector, CapabilitySelector
  session/          AgentGraph, AgentNode, DebatePanel, ConsensusPanel/Ring, BlackboardPanel,
                    FinalOutputPanel, SessionHeader, RoundScrubber, ConnectionStatus
  providers/        ProviderCard, ConnectionForm, ModelCatalogTable, InferenceProfileCard
  knowledge/        KnowledgeSourceCard, KnowledgeTable, UploadDialog
  memory/           MemoryExplorer, MemoryCard, MemorySearch
hooks/
store/              session store (Zustand + AG-UI event reducer), ui store
lib/                agui client (WebSocket), api client, types
types/              shared AG-UI + domain types
mocks/              AG-UI event replayer + fixtures
```

---

## 20. △ Summary of deviations from v1.0

1. **Session Workspace: vertical stack → multi-pane IDE layout** (graph center, debate right rail, consensus in header, blackboard/timeline bottom dock, output expands at synthesis).
2. **Navigation: 9 flat items → ~5 primaries** + Settings → AI for config; Knowledge/Memory authored in Team Workspace, global rollup read-only.
3. **Final Output: stacked last → lifecycle-driven Canvas** that expands at synthesis.
4. **Mesh edges: permanent particles → event-driven lit edges** (perf + meaning).
5. **Debate panel mapped to A2A intents** (INFORM/CRITIQUE/ENDORSE/VOTE).
6. **AG-UI contract-first** with a mock replayer + shared TS types; streaming in a Zustand store, not TanStack Query.
7. **Connection/reconnect/replay + empty/error states** specified for the realtime view.
8. **Agent Builder:** model override, capability→tool mapping, tool-calling model gate.
9. **Providers:** OpenRouter added; validation probe; write-only masked keys; models.dev capability seeding.
10. **Memory:** team→agent drill-down aligned to the episodic/semantic/procedural taxonomy.
11. **Inter-agent communication animation (§9.10, Option A):** event-derived and round-cadenced — every animated edge backed by a real critique/endorse/reply/vote; orchestrator dispatch fan-out as the opening beat; no decorative point-to-point fiction.
12. **△ Chat & Playground entry surfaces (§9A):** new-chat picks Team (multi-agent) or No-Team (single LLM); team chat = fast 1-round pass with a Deep Collaborate toggle for full consensus; file upload as transient context (promotable to knowledge); reply expands into the Session Workspace; Playground = ephemeral, unsaved team chat.

---

## 21. Success criteria (unchanged)

Within 10 seconds a new user understands: the goal, which agents are active, what they're discussing, whether consensus is rising, and what output is forming. It must feel like a real-time AI operating system, not a CRUD dashboard.

---

## 22. Build order (for Claude Code)

1. **Session Workspace** (against the mock AG-UI replayer) — the product
2. Team Workspace
3. Agent Builder
4. Settings → AI: Providers
5. Model Catalog
6. Inference Profiles
7. Knowledge Hub
8. Memory Explorer
9. Dashboard
10. **Chat & Playground** (§9A) — builds on the Session Workspace (reuses its AG-UI stream + expand view)

Design north star: Kiro + Cursor + Linear. Dark theme, accent `#8B5CF6`. The Session Workspace gets the majority of effort.

---

## 23. Caveats

- This spec is **layout & IA**, not visual design — refine visuals later with Stitch / 21st.dev against these tokens and structure.
- Pin versions at install (Next 15, `@xyflow/react`, shadcn, Framer Motion, Zustand, TanStack Query); the React Flow package name in particular has changed, so verify imports.
- Keep the AG-UI TS types in lockstep with backend `ARCHITECTURE.md` §24 — treat that as the single source of truth for the event contract.

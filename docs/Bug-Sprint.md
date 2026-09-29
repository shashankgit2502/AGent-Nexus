# BUG_SPRINT.md — Critical Bug Fixes (Priority-Ordered)

**Rules:** Read `CLAUDE.md` R1–R6 before starting. Every bug gets **RCA first** (R3) — reproduce, trace the full code path, explain the root cause, get my approval, THEN fix. No patches, no `try/except` band-aids. Work one bug at a time, stop between bugs for review.

**Priority:** Bug 1 & Bug 2 are P0 (the product doesn't work without them). Bug 3 is P1. Bug 4 is P1.

---

## Bug 1 (P0) — Knowledge base documents are never used as a data source during chat/collaboration

### Observed behavior
Documents uploaded to Knowledge (team-shared or agent-scoped) stay inert. When a user chats with a team or an agent runs during a session, the agents **never query the ingested chunks**. The knowledge exists in pgvector but is never retrieved — it's as if RAG doesn't exist at runtime.

### Expected behavior (per ARCHITECTURE.md §10.5)
- **Team-shared knowledge:** when ANY agent in the team runs (team chat, deep collaborate, or session), the `search_knowledge` retriever tool (§10.5.2) should be in the agent's tool list, scoped to `team_id` + `agent_id=NULL` (team-shared) + the agent's own private sources.
- **Agent-scoped knowledge:** when a specific agent with private knowledge runs, `search_knowledge` additionally includes chunks where `agent_id = that_agent`.
- The agent calls `search_knowledge(query)` during its ReAct loop when it needs context — it's a **tool**, not automatic injection.

### RCA checklist (investigate in this order)
1. **Is `search_knowledge` in the agent's tool list at spawn time?** Trace the agent factory (ARCH §22) — does it check `agent.capabilities` for RAG being enabled and, if so, build and attach the retriever tool via `make_knowledge_tool()` (§10.5.2)?
2. **Is the retriever tool built with the correct metadata filter?** It must filter `{team_id, agent_id: {$in: [None, this_agent_id]}}` (+ optional source_id scoping if "only specified sources" is on). Wrong filter = tool exists but returns nothing.
3. **Does the tool actually appear in the `create_agent(tools=[...])` call?** Log the tool list at spawn and confirm `search_knowledge` is present.
4. **Is the agent's system prompt aware the tool exists?** If the prompt doesn't mention knowledge/documents, the model may never call the tool. The prompt should say something like "You have access to team knowledge via the search_knowledge tool. Use it when the user's question may relate to uploaded documents or reference material."

### Fix scope
- Wire `make_knowledge_tool()` into the agent factory, gated on `capabilities.rag == true`.
- Ensure the metadata filter matches the scoping logic in §10.5.2.
- Add a line to the agent system prompt template acknowledging the knowledge tool.
- **Test:** upload a .md file to team knowledge, wait for `status=ready` + `chunk_count > 0`, then ask a team chat question about its content. The agent must call `search_knowledge`, retrieve chunks, and use them in its answer.

### Acceptance
A team-shared doc is retrievable by any team agent. An agent-private doc is retrievable only by that agent. Chunks appear in the agent's tool call logs. The answer references the document content.

---

## Bug 2 (P0) — File upload in Chat does not work at all (no endpoint called, no chunking, no error)

### Observed behavior
**Team chat:** user uploads a document and asks "summarize this document." Backend logs show NO upload endpoint called, NO chunking. Agents produce empty stub contributions with placeholder text. The file is silently ignored.

**Single-LLM chat:** same — user uploads a doc, asks for a summary. Response says "I don't see any uploaded document." Again, no upload endpoint called, no backend log, no error.

### Expected behavior (per ARCHITECTURE.md §8.5.3)
File upload in chat is **transient context** — the file is embedded into a **conversation-scoped** pgvector namespace and available only within that conversation. The flow should be:

```
User attaches file in composer
    → Frontend calls a file-upload endpoint (multipart POST)
    → Backend stores the file, creates a transient knowledge source scoped to conversation_id
    → Ingestion worker: load → split → embed → pgvector (metadata: conversation_id)
    → A conversation-scoped retriever tool is added to the agent(s) for this turn
    → Agent calls the retriever, gets the chunks, answers the question
```

### RCA checklist (investigate in this order — the cause is likely multi-layered)
1. **Does the frontend actually call an upload endpoint?** Check the chat composer's file-upload handler. If it only stores the file in React state / attaches it as a message property but never POSTs it to the backend, that's the root — **the upload endpoint is never called** (user's own observation). Check network tab behavior.
2. **Does the upload endpoint exist?** Check the FastAPI routes. If there's no `POST /conversations/{id}/attachments` (or equivalent) endpoint, it was never built. This is the likely gap — the chat backend (§8.5) specifies transient uploads but the route may not have been implemented.
3. **If the endpoint exists but isn't called:** trace the frontend wiring — is the composer's upload button connected to the API client? Is the multipart form data correctly assembled?
4. **If the endpoint IS called but nothing happens:** trace the backend — does it trigger ingestion? Does the conversation-scoped retriever get built and added to the agent's tools for that turn?
5. **For team chat specifically:** the agents returning empty stubs (`"[stub] [agent-id]'s proposal for round 1"`) is a SEPARATE concern — even without the doc, agents should produce real reasoning. If agents always produce stubs, the agent factory or the agent_turn node has a deeper issue (possibly the ReAct agent isn't actually running its loop). Investigate this independently.

### Fix scope (end-to-end, not just one layer)
- **Backend:** add `POST /conversations/{id}/attachments` — accept multipart file, store bytes, create a transient `knowledge_source` scoped to `conversation_id` (not `team_id`), trigger ingestion.
- **Backend:** build a conversation-scoped retriever tool (filter: `conversation_id`) and inject it into the agent(s) for that turn, alongside any team/agent knowledge tools.
- **Frontend:** wire the composer's file-upload to call the new endpoint; show upload progress; on success, include the `attachment_id` in the message payload so the backend knows to add the retriever.
- **Bonus (§8.5.3):** add a "Save to team knowledge" action on attachments to promote them from transient to permanent.
- **Test:** upload a .md in team chat → ask about its content → agent retrieves chunks and answers. Repeat for single-LLM chat. Verify no stale transient chunks leak across conversations.

### Acceptance
- File upload in team chat: document is ingested, agent retrieves from it, answer references the content.
- File upload in single-LLM chat: same behavior.
- No silent failures — if ingestion fails, the user sees an error, not silence.
- Agents never produce empty stub contributions (if they do, that's a separate bug to RCA).

---

## Bug 3 (P1) — No back-navigation from expanded workspace to chat

### Observed behavior
User is in a chat conversation, clicks "Expand to workspace" on a team-chat turn, enters the Session Workspace view. There is **no button, breadcrumb, or gesture to return to the chat thread.** The user is stranded.

### Expected behavior
The expanded workspace is a **drill-in from the chat**, not a navigation replacement. There must be a clear affordance to return to the originating conversation — either a back button/arrow, a breadcrumb (`Chat > Conversation > Expanded Turn`), a close/collapse button, or all three.

### RCA checklist
1. **How is the expand implemented?** Does it navigate to `/sessions/{id}` (a full route change, losing chat context) or render an overlay/panel within the chat route?
2. If it's a route change: the chat `conversationId` is lost from the URL. Fix = either use a query param (`/sessions/{id}?from=/chat/{convId}`) for the back link, or render the workspace as a full-screen overlay within `/chat/[convId]` that can be dismissed.
3. If it's an overlay: the close button is simply missing.

### Fix scope
- Add a persistent "← Back to chat" button (top-left of the expanded workspace header) that returns to `/chat/[conversationId]` with scroll position preserved.
- If the workspace is a route change, pass the return path; if it's an overlay, add a close/dismiss control.
- **Test:** expand a turn → verify back button exists → click it → verify you're back in the same conversation at the same scroll position.

### Acceptance
User can expand to workspace and return to chat in one click, without losing conversation context.

---

## Bug 4 (P1) — Mesh visualization: no edge animation, no communication glow, debate thread empty

### Sub-bugs (treat as three issues sharing one RCA pass)

**4a — Edge animation not working (both session workspace and expanded-from-chat).**
Observed: agents run, but edges between nodes never glow or animate. The mesh graph is static.
Expected (FRONTEND_SPEC §9.10, Option A): edges light up **only when a real event flows** — dispatch edges on `run_start`, critique/endorse/reply edges at round boundaries, driven by the AG-UI event stream. Faint static mesh in background; bright animated edges for actual interactions.

**4b — Expanded-from-chat workspace has the same issue.**
This is the same component (`AgentGraph`) rendered in a different context. If 4a is fixed, 4b should be fixed. But verify the AG-UI event stream is actually connected when the workspace is rendered from the chat expand (it may not be subscribing to the WebSocket in the expanded context).

**4c — Debate thread shows no output.**
Observed: the debate panel is empty during a run — no contributions, no critiques, nothing.
Expected (FRONTEND_SPEC §9.4): contributions render as PR-style comments, critiques as "requested changes," endorsements as 👍, mapped from AG-UI events (`contribution`, `critique` event types).

### RCA checklist (all three likely share one root cause)
1. **Is the AG-UI WebSocket connected and receiving events?** Open browser devtools → Network → WS tab. If no WebSocket connection or no events flowing, the stream isn't wired → nothing to animate or display.
2. **Is the Zustand session store receiving and reducing events?** The AG-UI event-reducer should be populating `contributions[]`, `critiques[]`, and `activeEdges[]` in the store. If the store is empty, the reducer isn't processing events (or events aren't arriving — see #1).
3. **Does the backend actually emit these events?** This was the issue from the §24.4 blocker we fixed earlier (the "extend backend to emit fully" decision). Verify that `contribution`, `critique`, `agent_turn_start`, `reasoning`, `tool_call` events are in the `run_events` table for a completed run. If they're missing, the backend emission (BUILD_PLAYBOOK Step 8) isn't complete.
4. **For edges specifically:** does the event-reducer produce `activeEdges` entries from events? Check the `onEvent` handler (§9.10 pseudo-code) — it should map `critique` → `addActiveEdge(sender, target, "critique")`, `contribution` with `responds_to` → reply edges, `run_start` → dispatch edges.
5. **For the expanded-from-chat context:** does the component subscribe to the session's WebSocket when mounted from the chat route, or only when navigated to directly?

### Fix scope
- Verify end-to-end: backend emits → WebSocket delivers → store reduces → components render.
- Fix whichever link in the chain is broken (likely the store reducer → component wiring, since the backend emission was recently added).
- For the expanded context: ensure the WebSocket subscription is initialized on mount regardless of entry point.
- **Test:** run a team session with 3+ agents. Verify: (a) debate thread shows contributions and critiques in real time, (b) edges animate at round boundaries (critique = red, endorse = green, reply = accent), (c) dispatch edges fan out on run_start, (d) same behavior when expanded from chat.

### Acceptance
- Debate thread renders real-time contributions and critiques during a run.
- Mesh edges animate on real events (dispatch, critique, endorse, reply) — no static graph during active runs.
- Both direct-navigation and expanded-from-chat workspace show the same live behavior.

---

## Work order

```
Bug 1 (P0) → RCA → fix → test → review
Bug 2 (P0) → RCA → fix → test → review
Bug 3 (P1) → RCA → fix → test → review
Bug 4 (P1) → RCA (shared) → fix 4a/4b/4c → test → review
```

Do NOT start fixing before showing me the RCA for each bug. One bug at a time.
# ARTIFACTS.md — Artifact Generation & Export (feature spec)

**Status:** New feature for NEX AGI. Generalized — not coupled to any single use case.
**Pairs with:** `ARCHITECTURE.md`, `TECHNICAL.md`, `FRONTEND_SPEC.md`, `CLAUDE.md`, `BUILD_PLAYBOOK.md`.
**Rules:** standard project rules apply (CLAUDE R1–R6). Verify/pin library versions at build (R1); reuse real primitives (R2); reviewable slices (R6).

---

## 1. Why this exists (the gap + the intent)

Today NEX AGI produces a **synthesized text answer** — a plan, analysis, or design. It cannot hand the user a **downloadable file** (a `.py`, `.xlsx`, `.pptx`, `.docx`, `.pdf`, `.html`, a chart image, or a multi-file `.zip`). This feature adds that, generically, so **any team or agent, for any use case**, can produce real deliverables the user downloads — behaving like ChatGPT Canvas / Claude Artifacts (live preview, iterate, versions, download).

**Intent (explicitly decoupled):** the hackathon-squad example is *one* use case. A finance team emits `.xlsx`; a docs team emits `.docx`/`.pdf`; a data team emits charts + `.csv`; a scaffolding team emits code files + a `.zip`. Nothing here is tied to a specific domain — it's a reusable artifact subsystem driven by agent capabilities.

### The boundary (be honest about it)
This makes NEX AGI able to **generate and export deliverables** (single files or bundles). It does **not** turn it into Claude Code — it does not autonomously scaffold/run a repo or execute arbitrary generated code on your machine. Agents **generate file content**; the platform **stores and serves** it for download. (Sandboxed execution is a deferred, separately-gated feature — §15.) Generation + download covers "produce a `.py`/`.xlsx`/`.pptx` I can download"; it is not "run my project."

---

## 2. Core concept: the Artifact

An **Artifact** is a produced, downloadable output with a type, content (or a storage reference for binaries), a filename, and a version. Produced by an agent (via a tool) or by the Synthesizer (final deliverable). Rendered in an **Artifact panel** like Claude/ChatGPT.

**Artifact kinds (open registry — add more without schema change):**
- **Text/code:** `markdown`, `code` (`.py`, `.js`, `.ts`, `.sql`, `.html`, …), `json`, `csv`
- **Office (binary):** `docx`, `xlsx`, `pptx`, `pdf`
- **Media:** `image` (chart or generated image, `.png`/`.svg`)
- **Bundle:** `archive` (`.zip` of multiple artifacts — the "download all files" case)

Artifacts are **versioned** — iterating ("make the chart blue", "add a section") creates v2, v3… (Canvas/Artifact behavior).

---

## 2A. Artifacts are POST-CONSENSUS deliverables (the production order)

**This is the core behavioral rule: the team debates first, converges on the best answer, and only then — if the task calls for one — produces the downloadable file from the agreed result.** Artifact generation is a *consequence of consensus*, never a substitute for it.

### Required order
```
Rounds:      agents propose → critique → refine over the blackboard      ← the DEBATE
Consensus:   converge on the agreed result (confidence-weighted, ARCH §8)
HITL:        human gate (if enabled)
Synthesizer: produce the FINAL output, and decide its form:
               ├─ task wants prose      → text answer (no artifact)
               └─ task wants a file     → emit artifact(s) BUILT FROM the agreed result
```

### Four rules this enforces
1. **Debate before deliverable.** The mesh debate and consensus (ARCH §8) run to completion *first*. The agreed-upon, consensus-ranked result is the **single source** the artifact is built from.
2. **Generation is a post-consensus step.** Files are produced **after** convergence — by the **Synthesizer node** (preferred), or by a single designated **producer agent** acting on the agreed result. Never during the debate rounds.
3. **No competing artifacts mid-debate.** Agents must **not** each emit their own file while still arguing — that would create N divergent deliverables instead of one collaborated answer. Artifact tools are intended for the post-consensus producer, not for parallel proposal rounds. (If an agent uses a tool mid-round, it's for *reasoning* — e.g. drafting content into the blackboard — not for emitting the user-facing deliverable.)
4. **"If required" is a real decision.** The Synthesizer decides whether a downloadable deliverable is even needed: *"summarize this"* → text only; *"build me the model"* → `.xlsx`. Don't force a file when the answer is prose, and don't withhold one when the task is clearly a deliverable. When ambiguous, the text answer leads and the artifact is offered.

### How this maps to the existing graph (no new machinery)
- The **debate → consensus → HITL → Synthesizer → End** flow is unchanged (ARCH §7, §8).
- The **only addition** is that the Synthesizer (or a producer agent it triggers) may call artifact tools (§5) on the consensus result and emit artifact tool events (§11). Lightweight team chat (`max_rounds=1`) still works — it just has one proposal "round" before the synthesizer; Deep Collaborate gives a real multi-round debate before the file is built.

> **Implementation note:** the producer step reads the **consensus-ranked contributions** (ARCH §8 `consensus_ranking`) as its input, not raw individual proposals — so the file reflects what the team agreed on, not one agent's unreviewed draft.

---

## 3. How it fits the locked architecture (reuse, don't rebuild)

| Existing seam | How artifacts use it |
|---|---|
| **Agent capabilities → tools** (ARCH §10.5.4; agent config "Create documents/charts/code", "Create images") | These toggles already exist — they now gate **artifact-producing tools** (§5). |
| **`artifacts` table** (TECHNICAL §11.4) | Extended (§9) with file-storage columns + versions + message linkage. |
| **Run XOR (session ⊕ conversation)** (ARCH §8.5) | An artifact links to `run_id`; the run already belongs to a session *or* a conversation, so artifacts work in both **team sessions and chat** with no new branching. |
| **AG-UI content blocks / events** (ARCH §24, the A2UI/artifact seam left open) | Standard `tool_result`/`state_delta` events carry artifacts (no custom event) — streams live (§11). |
| **Synthesizer node** (ARCH §4.6) | Can emit the final deliverable as an artifact (not just text). |
| **`deepagents` skills** (ARCH §11/§26) | Office/code generation can be packaged as skills (the same SKILL.md pattern) so agents learn *when* and *how* to produce each format. |
| **Ingestion worker pattern** (TECHNICAL §11.5) | Heavy generation (large `.pptx`/`.pdf`/`.zip`) reuses the async worker pattern. |

No new graph runtime, no new agent framework — artifacts are **tools + storage + a UI panel** layered on what exists.

---

## 4. Use-case examples (all the same subsystem)

- **Plan → docs:** product team produces `PRD.docx` + `architecture.pdf`.
- **Data → spreadsheet:** finance team produces `model.xlsx` with formulas + a chart.
- **Deck:** strategy team produces `pitch.pptx`.
- **Code:** scaffolding team produces `main.py`, `index.html`, `app.js`, bundled as `project.zip`.
- **Mixed:** a team produces a `.md` summary *and* a `.xlsx` *and* a chart `.png` in one run.

Each is just agents calling artifact tools; the subsystem doesn't know or care about the domain.

---

## 5. Artifact-producing tools (the registry)

A predefined **artifact tool registry** (extends the tool registry in ARCH §12). Agents call these during their ReAct loop; capability toggles decide which an agent has.

```python
@tool
def write_code_file(filename: str, language: str, content: str) -> ArtifactRef:
    """Produce a downloadable code/text file (.py/.js/.ts/.sql/.html/...)."""

@tool
def create_docx(filename: str, title: str, sections: list[dict]) -> ArtifactRef:
    """Produce a Word document."""

@tool
def create_xlsx(filename: str, sheets: list[dict]) -> ArtifactRef:
    """Produce an Excel workbook (cells, formulas, charts)."""

@tool
def create_pptx(filename: str, slides: list[dict]) -> ArtifactRef:
    """Produce a PowerPoint deck."""

@tool
def create_pdf(filename: str, content_md: str) -> ArtifactRef:
    """Produce a PDF (from markdown/HTML)."""

@tool
def create_chart(filename: str, spec: dict) -> ArtifactRef:
    """Produce a chart image (.png/.svg) from a data spec."""

@tool
def create_archive(filename: str, artifact_ids: list[str]) -> ArtifactRef:
    """Bundle multiple existing artifacts into a downloadable .zip."""
```

Each tool: generates bytes via a library, stores them (§7), writes an `artifacts` row + version, emits a standard `tool_result` event carrying the artifact descriptor (§11), and returns an `ArtifactRef` (id + filename + download token) the agent can reference.

**Generation libraries (verify/pin at build, R1):** docx → `python-docx`; xlsx → `openpyxl`; pptx → `python-pptx`; pdf → a PDF lib; charts → a plotting lib; code/text/json/csv → direct write. Packaging these as **deepagents skills** (one SKILL.md per format) is recommended so agents get format know-how via progressive disclosure rather than bloated prompts.

---

## 6. Generation vs execution (the security line — read this)

- **Generating** a `.py` (or any code/file) and letting the user download it is **safe** — it's just text/bytes. ✅ v1.
- **Executing** generated code server-side is **not** done in v1. Running arbitrary agent-written code is an RCE risk and requires a sandbox (gVisor/Firecracker/container with no network, resource caps). That's a **deferred, separately-gated** capability (a Code Interpreter tool), not part of this spec. ⛔ v1.

This keeps "download a Python file" fully supported while refusing to silently become a code-execution engine.

---

## 7. Storage & lifecycle

- **Binary artifacts** (`docx`/`xlsx`/`pptx`/`pdf`/`image`/`archive`) → **object storage** (S3/GCS in prod, **MinIO or local disk in dev**); the DB stores a `storage_ref`, not the bytes.
- **Text artifacts** (`markdown`/`code`/`json`/`csv`) → may inline in `content` (small) or go to storage (large). Threshold configurable.
- **Download** → a short-lived **signed URL** or an authenticated streaming endpoint (`GET /artifacts/{id}/download`), RLS/tenancy enforced.
- **Versioning** → each iterate creates a new `artifact_versions` row; the artifact's `current_version` advances; older versions remain downloadable (Canvas history).
- **Lifecycle/cleanup** → artifacts inherit their run's lifecycle; playground/ephemeral runs' artifacts are not persisted; deleting a conversation/session hard-deletes its artifacts + storage objects (reuse the delete-by-source cleanup pattern).
- **Tenancy** → every artifact carries `org_id`; storage keys are namespaced per org.

---

## 8. Backend flow

```
Agent (ReAct loop) decides a deliverable is needed
   → calls an artifact tool (e.g. create_xlsx)
   → tool generates bytes via the format library
   → stores bytes (object storage) + writes artifacts row + artifact_versions row
   → emits a standard `tool_result` event carrying the artifact descriptor (live to the UI)
   → returns ArtifactRef to the agent (so it can reference / bundle later)
...
Synthesizer (optional) → emits the FINAL deliverable as an artifact too
End node → finalizes; artifacts are listed on the run/message
```

Heavy generation (large deck/pdf/zip) runs via the **async worker** (TECHNICAL §11.5 pattern): tool enqueues, artifact starts `generating`, worker produces + flips to `ready`, UI updates from the event stream.

---

## 9. Data model changes (extend, don't replace)

Extend the existing `artifacts` table and add versions:

```sql
ALTER TABLE artifacts
  ADD COLUMN conversation_message_id UUID REFERENCES messages(id) ON DELETE CASCADE, -- chat artifacts
  ADD COLUMN producer_agent_id UUID REFERENCES agents(id),      -- which agent made it (nullable: synthesizer)
  ADD COLUMN filename     TEXT,
  ADD COLUMN mime_type    TEXT,
  ADD COLUMN kind         TEXT,    -- markdown|code|json|csv|docx|xlsx|pptx|pdf|image|archive
  ADD COLUMN storage_ref  TEXT,    -- object-storage key (NULL if inlined in content)
  ADD COLUMN size_bytes   BIGINT,
  ADD COLUMN current_version INT NOT NULL DEFAULT 1,
  ADD COLUMN status       TEXT NOT NULL DEFAULT 'ready' CHECK (status IN ('generating','ready','failed')),
  ADD COLUMN error        TEXT;

CREATE TABLE artifact_versions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL REFERENCES artifacts(id)     ON DELETE CASCADE,
    version     INT  NOT NULL,
    content     TEXT,            -- inline for text kinds
    storage_ref TEXT,            -- object key for binary kinds
    size_bytes  BIGINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (artifact_id, version)
);
CREATE INDEX ix_artifacts_message ON artifacts(conversation_message_id);
```

`artifacts.run_id` (existing) still anchors team-session and chat-turn artifacts via the run; `conversation_message_id` lets chat render an artifact inline on the assistant message (ChatGPT-style).

---

## 10. API

```
GET  /runs/{id}/artifacts                 list artifacts for a run
GET  /conversations/{id}/artifacts        list artifacts in a conversation
GET  /artifacts/{id}                       metadata + version list
GET  /artifacts/{id}/download              stream/redirect to signed URL (RLS-scoped)
GET  /artifacts/{id}/versions/{v}/download specific version
POST /artifacts/{id}/iterate               { instruction } → re-run producer → streams state_delta (§11.2), persists new version snapshot
```

Artifacts are usually **created implicitly** by agent tool calls, not by a direct POST. `iterate` is the Canvas "edit/refine" action: it streams JSON-Patch deltas live (RFC 6902, §11.2) and persists a full snapshot as the new version (§9).

---

## 11. AG-UI streaming (idiomatic — transport vs payload)

> **Protocol alignment (verified against current AG-UI/A2UI practice, 2026).** AG-UI is the **transport/runtime layer**; A2UI is the **UI-payload layer**; MCP is tools; A2A is agent coordination. The community's main critique of AG-UI is that leaning on **custom events** recreates the fragmentation the protocol exists to remove — so we **do not invent a bespoke `artifact` event.** Instead we ride the standard event types.

### 11.1 Producing → announcing an artifact (typed tool event, not a custom event)
An artifact is produced by an artifact **tool** (§5). The idiomatic path is therefore a standard **tool-call / tool-result** event carrying an **artifact descriptor** as a typed attachment — not a one-off `artifact` type:

```jsonc
// tool_result event (standard AG-UI) carrying the artifact descriptor as a typed attachment
{
  "type": "tool_result",
  "data": {
    "tool": "create_xlsx",
    "producer_agent_id": "finance-agent",
    "attachment": {                       // typed attachment (AG-UI first-class: files/media + provenance)
      "artifact_id": "...",
      "kind": "xlsx",
      "filename": "model.xlsx",
      "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "version": 1,
      "status": "ready",                  // generating → ready for heavy files
      "preview": "...",                   // text/markdown/code preview; null for binary
      "download_url": "/artifacts/.../download",
      "size_bytes": 20480
    }
  }
}
```

(If you later render an artifact as an interactive component rather than a download card, the **A2UI** declarative JSON tree is carried inside a `tool_call` event — the standard "transport carries the payload" pattern — not as raw executable code. This is the A2UI seam from ARCH §24.6–24.7.)

### 11.2 Live drafting & iteration = JSON-Patch deltas (not full re-sends)
For evolving artifacts (a doc being drafted, a spreadsheet being filled, an iterate→v2), **do not resend the whole file each tick.** Use AG-UI's shared-state mechanism: emit **`state_delta` events as JSON Patch (RFC 6902)** against the artifact's working state, so the UI updates incrementally (add/modify/remove) without regenerating the whole tree.

```jsonc
{ "type": "state_delta",
  "data": { "artifact_id": "...",
            "patch": [ { "op": "replace", "path": "/sections/2/body", "value": "..." } ] } }
```

**Server-side, persist full version snapshots** (`artifact_versions`, §9) even though the wire carries deltas — deltas are for live UX; snapshots are the durable, downloadable record of each version.

### 11.3 Where it's consumed
Session Workspace and Chat both consume these standard events; team modes already stream the full event set (ARCH §8.5), so artifacts appear live as the post-consensus producer (§2A) generates them — `generating → ready` via status, incremental content via `state_delta`.

---

## 12. Frontend — the Artifact panel (ChatGPT/Claude behavior)

A reusable **ArtifactPanel** (Canvas) that appears wherever artifacts are produced:

- **In Chat:** assistant messages with artifacts show **artifact cards**; clicking opens the side panel (split view, like Claude). Cards show kind icon, filename, size, version.
- **In Session Workspace:** the Final Output area (FRONTEND_SPEC §9.7) becomes artifact-aware — synthesized text *and* downloadable artifacts.
- **Panel features (Canvas parity):**
  - **Preview:** markdown rendered; code with syntax highlighting; `csv`/`xlsx` as a table; `image` inline; `docx`/`pptx`/`pdf` → preview-if-available + a prominent **Download** card.
  - **Actions:** **Download**, **Copy** (text kinds), **Open in editor** (text/code), **Iterate** (prompt → new version), **Version switcher** (v1/v2/v3).
  - **Live status:** `generating…` spinner → `ready` (heavy files), driven by the `tool_result` status + `state_delta` events (§11).
- **Components:** `ArtifactPanel`, `ArtifactCard`, `ArtifactPreview` (per-kind renderer), `ArtifactVersionSwitcher`, `ArtifactToolbar`.

This is the "exactly like ChatGPT/Claude" behavior: artifacts stream in, you preview, iterate, switch versions, and download.

---

## 13. Capabilities → artifact tools (the gate)

The agent-config capability toggles (FRONTEND_SPEC §11) map to artifact tools:

| Capability toggle | Artifact tools granted |
|---|---|
| Create documents/charts/code | `write_code_file`, `create_docx`, `create_xlsx`, `create_pptx`, `create_pdf`, `create_chart`, `create_archive` |
| Create images | `create_image` (+ `create_chart`) |

An agent only gets the tools its capabilities enable — so a "reviewer" agent without these toggles can't emit files, while a "builder" agent can. Fully decoupled from use case.

---

## 14. Multiple teams / agents / use cases / files

- **Multiple teams & use cases:** the subsystem is domain-agnostic; any team whose agents have the capability can produce any registered kind.
- **Multiple agents producing in one run:** each artifact records its `producer_agent_id`; the run lists them all.
- **Multiple files / "download everything":** an agent (or the synthesizer) calls `create_archive(artifact_ids=[...])` to bundle produced artifacts into one `.zip` — the closest honest equivalent to "output every project file," without becoming a repo-writing harness.

---

## 15. Security (production)

- **No execution of generated code in v1** (§6). Sandboxed Code Interpreter is deferred + separately gated.
- **File-type allowlist** for generation; **size limits** per artifact and per run.
- **Signed, expiring download URLs**; downloads are RLS/tenancy-scoped — a user can only fetch artifacts in their org.
- **Storage isolation** per `org_id`; never expose raw storage paths.
- **Treat generated content as untrusted on render:** sanitize HTML/markdown previews (no script execution in the preview pane); render `.html` artifacts in a sandboxed iframe or download-only.
- **(Optional) malware scan** hook for uploaded-then-bundled files.

---

## 16. Non-functional

- Heavy generation is **async** (worker pattern); the UI shows `generating → ready` from the event stream — never blocks the run.
- Artifacts are **versioned and immutable** per version (iterate = new version, old stays).
- Caching: signed URLs cached briefly; previews generated once.

---

## 17. What this is NOT
- Not a code executor (no running generated code in v1).
- Not Claude Code (no autonomous repo scaffolding, no shell, no command execution).
- Not a file-system mutation tool — it produces *deliverables*, not changes to your machine.
The clean division stays: **NEX AGI team → reasoning + deliverables (artifacts);** a coding agent → building/running software.

---

## 18. Build slices (R6 — reviewable, one at a time)
1. **Schema + storage** — extend `artifacts`, add `artifact_versions`, wire object storage (MinIO/local dev), download endpoint with signed URLs + RLS.
2. **Text/code artifact tools** — `write_code_file`, markdown/json/csv; artifacts carried via standard `tool_result`/`state_delta` events (§11); basic ArtifactPanel preview + download. (Smallest end-to-end vertical.)
3. **Artifact panel parity** — versions, iterate, copy, open-in-editor; chat inline cards + Session Workspace integration.
4. **Office + media tools** — `create_docx`/`xlsx`/`pptx`/`pdf`/`chart`/`image` (as deepagents skills); async worker for heavy files.
5. **Bundles** — `create_archive` (.zip) for multi-file downloads.
6. **(Deferred)** sandboxed Code Interpreter — separate spec, separate security review.

---

## 19. Acceptance criteria
- An agent with the capability produces a downloadable file (`.py`, `.xlsx`, `.docx`, `.pptx`, `.pdf`, chart `.png`) in **both** team chat and a session.
- The artifact streams into the UI live (`generating → ready`), previews correctly, and downloads with a signed, tenancy-scoped URL.
- Iterating produces a new version; the version switcher works; old versions remain downloadable.
- Multiple artifacts in one run are all listed; `create_archive` bundles them into a working `.zip`.
- No generated code is executed server-side; previews don't execute scripts.
- Works identically for unrelated use cases (finance `.xlsx`, docs `.docx`, scaffold `.zip`) — nothing hardcoded to one domain.

---

## 20. Integration into the doc set (do this when you adopt it)
- **CLAUDE.md §3:** add a locked-decision row — *"Artifacts: agents/synthesizer produce versioned, downloadable artifacts via capability-gated tools; stored in object storage; streamed via standard AG-UI `tool_result`/`state_delta` events (no custom event); generation only (no code execution in v1)."*
- **BUILD_PLAYBOOK.md:** add the §18 slices as steps (after the engine + chat are working).
- **ARCHITECTURE.md §24:** register the artifact attachment descriptor + `state_delta` (JSON-Patch) usage in the contract — via standard `tool_result`/`state_delta` events, not a custom event.
- **Version caveat (R1):** pin and verify `python-docx`/`openpyxl`/`python-pptx`/PDF/plotting libs at install.
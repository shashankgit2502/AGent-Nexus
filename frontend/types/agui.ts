/**
 * AG-UI event contract — TypeScript mirror of the backend's single source of
 * truth (`backend/app/streaming/events.py` + ARCHITECTURE.md §24.3/§24.4).
 *
 * R4: this is a **mirror, never a fork**. Every `data` shape below was verified
 * against the live backend emission (the `make_event(...)` call sites in
 * `app/graph/nodes/*` and `app/agents/runtime.py`) during Slice 0/1 — see
 * FRONTEND_INTEGRATION_PLAN §5.2. Adding/removing a type must happen in §24.4
 * first, then here.
 *
 * Two reconciliations vs. the original projection (FRONTEND_INTEGRATION_PLAN §5.2):
 *  - `run_start.roster` is `active_agent_ids` — **agent-id strings**, not rich
 *    objects. The UI joins these with `GET /teams/{id}/agents` to label nodes.
 *  - `confidence` is NOT emitted standalone; it is folded into
 *    `contribution.data.confidence`. The type stays reserved in the catalog.
 */

// ── Content blocks (§24.6) — the A2UI seam: a discriminated, extensible union ──
export type ContentBlock =
  | { type: "text"; text: string }
  | { type: "code"; language: string; code: string }
  | { type: "tool_result"; tool: string; value: string };

export type CritiqueSeverity = "minor" | "major" | "blocking";
export type HitlDecision = "approve" | "edit" | "reject";
export type HitlSource = "human" | "auto" | "human_edit";
/** `run_finished.artifact.kind` — the run's terminal outcome (NOT a file kind). */
export type ArtifactKind = "synthesis" | "rejected";

// ── Downloadable file artifacts (ARTIFACTS.md §11.1 / ARCH §24.9) ─────────────
/** The producible file kinds (open registry; backend `artifacts.kind`). */
export type ArtifactFileKind =
  | "markdown"
  | "code"
  | "json"
  | "csv"
  | "docx"
  | "xlsx"
  | "pptx"
  | "pdf"
  | "image"
  | "archive";
/** Generation lifecycle (`generating` → `ready`|`failed`) for heavy/async files. */
export type ArtifactStatus = "generating" | "ready" | "failed";

/**
 * The artifact **descriptor** carried as a typed `attachment` on a `tool_result`
 * event (ARCH §24.9 — *not* a custom event type). Mirror of the backend's
 * `app/artifacts/descriptor.py::artifact_attachment`; R4 — never fork the shape.
 */
export interface ArtifactAttachment {
  artifact_id: string;
  kind: ArtifactFileKind;
  filename: string | null;
  mime_type: string | null;
  version: number;
  status: ArtifactStatus;
  /** inline text/code preview; null for binary or storage-spilled artifacts. */
  preview: string | null;
  /** signed, RLS-scoped, relative download path (`/artifacts/{id}/download?token=`). */
  download_url: string;
  size_bytes: number | null;
}

// ── Per-event `data` payloads (verified against backend emission) ─────────────
export interface RunStartData {
  goal: string;
  /** active agent-id strings (run_start.roster == CollabState.active_agent_ids). */
  roster: string[];
}
export interface RoundStartData {
  round: number;
}
export interface AgentTurnStartData {
  agent_id: string;
  round: number;
}
export interface ReasoningData {
  agent_id: string;
  round: number;
  text: string;
}
export interface ToolCallData {
  agent_id: string;
  round: number;
  tool: string;
  args: Record<string, unknown>;
}
export interface ToolResultData {
  agent_id: string;
  round: number;
  tool: string;
  result: unknown;
  /**
   * Present only when this `tool_result` produced a downloadable file (the
   * post-consensus artifact producer, ARTIFACTS §2A / §11.1). Mesh-agent tool
   * results omit it. Drives the ArtifactPanel; the run-finished synthesis artifact
   * is a separate concept (see `RunFinishedData`).
   */
  attachment?: ArtifactAttachment;
  /** producer agent id; null when the synthesizer produced the file. */
  producer_agent_id?: string | null;
}
export interface ContributionData {
  agent_id: string;
  round: number;
  confidence: number;
  content_blocks: ContentBlock[];
  /**
   * agent_ids of the prior-round peers this proposal directly builds on
   * (backend `Contribution.responds_to`, already validated by `_valid_responds_to`
   * to real, non-self prior-round contributors). Drives the §9.10 reply edges.
   * Optional: the real agent runtime always emits it, but the foundation stub
   * omits it; readers default to `[]`. Empty in the opening round.
   */
  responds_to?: string[];
}
/** Reserved (ARCH §24.4) — not emitted standalone; confidence rides `contribution`. */
export interface ConfidenceData {
  agent_id: string;
  round: number;
  confidence: number;
}
export interface CritiqueData {
  sender: string;
  target: string;
  round: number;
  severity: CritiqueSeverity;
  content: string;
}
export interface ConsensusUpdateData {
  mean_confidence: number;
  converged: boolean;
  /** ranking keys are `"agent_id:round"`, best first. */
  ranking: string[];
}
export interface HitlRequestData {
  candidate: string | null;
  candidate_key: string | null;
  ranking: string[];
  converged: boolean;
  allowed_decisions: string[];
}
export interface HitlResolvedData {
  decision: HitlDecision;
  source: HitlSource;
}
/**
 * `synthesis` is variant-shaped (ARCH §24.4 / synthesizer node):
 *  - approve/model/fallback → `{ source, ranking, content_blocks }`
 *  - edit → `{ source: "human_edit", content_blocks }`
 *  - reject → `{ rejected: true }`
 */
export interface SynthesisData {
  source?: string;
  ranking?: string[];
  content_blocks?: ContentBlock[];
  rejected?: boolean;
}
export interface RunFinishedData {
  artifact: {
    kind: ArtifactKind;
    content: string | null;
    content_format: "markdown";
  };
}
/**
 * Stable discriminator for an abstention/failure (§24.4 `error.reason`). Lets the UI
 * tell a *config* abstention a user can fix (`not_tool_capable`) from a *transient*
 * runtime failure, without string-matching `message`. Open-ended (it crosses a trust
 * boundary): treat unknown values as a generic failure.
 */
export type ErrorReason = "not_tool_capable" | "timeout" | "turn_failed";

export interface ErrorData {
  scope: string;
  agent_id?: string;
  round?: number;
  message: string;
  /** Optional §24.4 discriminator; absent on older events / run-scoped errors. */
  reason?: ErrorReason;
}

// ── Type → data map (the locked §24.4 catalog) ───────────────────────────────
export interface AGUIEventDataMap {
  run_start: RunStartData;
  round_start: RoundStartData;
  agent_turn_start: AgentTurnStartData;
  reasoning: ReasoningData;
  tool_call: ToolCallData;
  tool_result: ToolResultData;
  contribution: ContributionData;
  confidence: ConfidenceData;
  critique: CritiqueData;
  consensus_update: ConsensusUpdateData;
  hitl_request: HitlRequestData;
  hitl_resolved: HitlResolvedData;
  synthesis: SynthesisData;
  run_finished: RunFinishedData;
  error: ErrorData;
}

export type AGUIEventType = keyof AGUIEventDataMap;

/** Runtime guard: the locked catalog (mirror of the backend frozenset). */
export const AGUI_EVENT_TYPES: readonly AGUIEventType[] = [
  "run_start",
  "round_start",
  "agent_turn_start",
  "reasoning",
  "tool_call",
  "tool_result",
  "contribution",
  "confidence",
  "critique",
  "consensus_update",
  "hitl_request",
  "hitl_resolved",
  "synthesis",
  "run_finished",
  "error",
] as const;

/** The AG-UI envelope (ARCH §24.3). `seq` is the monotonic per-run ordering key. */
export interface AGUIEvent<T extends AGUIEventType = AGUIEventType> {
  type: T;
  /** owning surface id — a Session OR a Conversation (ARCH §8.5). */
  session_id: string;
  run_id: string;
  /** monotonic per-run; ordering + replay dedup key (ARCH §24.8). */
  seq: number;
  /** ISO-8601 UTC. */
  ts: string;
  data: AGUIEventDataMap[T];
}

/** The discriminated union the renderer/reducer switches on. */
export type AnyAGUIEvent = { [T in AGUIEventType]: AGUIEvent<T> }[AGUIEventType];

/** Narrowing guard at the WS boundary (R5: validate untrusted input). */
export function isAGUIEventType(value: unknown): value is AGUIEventType {
  return typeof value === "string" && (AGUI_EVENT_TYPES as readonly string[]).includes(value);
}

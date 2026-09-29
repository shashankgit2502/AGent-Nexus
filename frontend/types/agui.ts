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
/**
 * `run_finished.artifact.kind` — the run's terminal outcome (NOT a file kind).
 *
 * `cancelled` is distinct from `rejected` on purpose: rejected means a human read the
 * answer and refused it; cancelled means a human stopped the run before there *was* an
 * answer. History has to be able to tell those apart.
 */
export type ArtifactKind = "synthesis" | "rejected" | "cancelled";

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
/** The producible deliverable kinds — mirror of backend `plan.DeliverableKind`. */
export type DeliverableKind =
  | "none"
  | "markdown"
  | "code"
  | "json"
  | "csv"
  | "docx"
  | "xlsx"
  | "pptx"
  | "pdf"
  | "chart"
  | "image"
  | "archive";

/** How the orchestrator decided to approach the goal (backend `plan.PlanStrategy`). */
export type PlanStrategy = "decompose" | "debate" | "single_owner";

export interface PlanSubtask {
  id: string;
  title: string;
  instruction: string;
  /** the roster agent that owns this piece (validated server-side to be on-roster). */
  agent_id: string;
  /** phase hint, 1-based — NOT a scheduling constraint (ARCH §23.4). */
  round: number;
  depends_on: string[];
  acceptance: string[];
}

/**
 * The orchestrator's plan, emitted once between `run_start` and the first
 * `round_start` (ARCH §4.1 / §24.4). `subtasks` is empty for a `debate` plan —
 * that is a deliberate choice, not a missing plan.
 */
export interface PlanReadyData {
  strategy: PlanStrategy;
  summary: string;
  subtasks: PlanSubtask[];
  deliverable: {
    kind: DeliverableKind;
    filename: string | null;
    notes: string | null;
  };
  /** honest degradation notes: reassignments, clamped rounds, capability gaps. */
  warnings: string[];
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
  /**
   * Tokens this agent's turn consumed (ARCH §21.7). Absent when the provider reported no
   * usage — absent means *unknown*, not zero.
   */
  tokens?: { input: number; output: number; total: number };
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

/**
 * The seven A2A performatives (ARCH §23.3) — the vocabulary that turns a parallel
 * poll into a team. Mirror of the backend `Intent` union; never fork it.
 */
export type A2AIntent =
  | "INFORM"
  | "REQUEST"
  | "PROPOSE"
  | "CRITIQUE"
  | "DELEGATE"
  | "ENDORSE"
  | "VOTE";

/**
 * One typed inter-agent message (ARCH §23.2 envelope, §24.4 event).
 *
 * `recipients` is `"*"` for a broadcast or an explicit agent-id list for directed
 * mail — the distinction drives whether the Workspace draws a point-to-point edge
 * or a board post. Only messages that *passed* backend validation are emitted, so
 * the UI never renders a hand-off that was actually dropped.
 */
export interface A2AMessageData {
  id: string;
  sender: string;
  recipients: string[] | "*";
  intent: A2AIntent;
  round: number;
  /** intent-specific body: `content` | `question` | `subtask` | `reason` (+ `severity`, `source_urls`, `weight`). */
  payload: Record<string, unknown>;
  /** msg id this answers, when the agent replied to something in its inbox. */
  in_reply_to?: string | null;
}

/**
 * A peer changed the plan mid-run via DELEGATE/PROPOSE (ARCH §4.1 / §23.3).
 * The orchestrator is never re-entered — adaptation happens through the blackboard,
 * so this records who changed what, not a controller's instruction.
 */
export interface PlanAmendedData {
  round: number;
  by_agent: string;
  change: string;
  subtask_id?: string | null;
  reason?: string | null;
}

/** One plan acceptance criterion, checked post-consensus (ARCH §4.1). */
export interface AcceptanceCheck {
  subtask_id: string;
  criterion: string;
  met: boolean;
  evidence?: string | null;
}

/**
 * Post-consensus verification that the plan's `acceptance` criteria were actually
 * met — so a run ends because the work is done, not because the round counter
 * expired. Rendered at the HITL gate so the human approves against evidence.
 */
export interface AcceptanceReportData {
  round: number;
  checks: AcceptanceCheck[];
  met_count: number;
  total: number;
}
export interface ConsensusUpdateData {
  /** raw mean of self-reported confidence — unchanged meaning, kept for older consumers. */
  mean_confidence: number;
  converged: boolean;
  /** ranking keys are `"agent_id:round"`, best first — now ordered by peer-adjusted score. */
  ranking: string[];
  /**
   * Peer-weighted scoring (ARCH §8.1). Optional: a run with no A2A signal — or a replay
   * from before §8.1 — carries none, and the panels fall back to `mean_confidence`.
   */
  /** mean of the peer-adjusted scores; this is what is compared against τ. */
  mean_score?: number;
  /** `"agent_id:round"` → final peer-adjusted score. */
  peer_scores?: Record<string, number>;
  /** `"agent_id:round"` → the signed peer adjustment (−1…+1) applied to self-confidence. */
  peer_deltas?: Record<string, number>;
  /** share of peer votes landing on the top-ranked candidate; absent when nobody voted. */
  agreement?: number | null;
  /** agent_id → votes received, for the "who backed whom" view. */
  tally?: Record<string, number>;
}
/**
 * The debate loop stopped early because EVERY agent abstained this round (e.g. all
 * rate-limited) — §21.5. Not an error: the run proceeds to the human gate with
 * whatever exists. Emitted right after `consensus_update`, and terminal for the loop
 * (no `round_start` follows).
 */
export interface ConsensusStalledData {
  round: number;
  mean_confidence: number;
  message: string;
}
export interface HitlRequestData {
  candidate: string | null;
  candidate_key: string | null;
  ranking: string[];
  converged: boolean;
  allowed_decisions: string[];
  /**
   * The plan's acceptance criteria checked against the agreed result (ARCH §4.1).
   *
   * `null`/absent means **unverified** — no plan criteria, no verifier configured, or
   * verification failed — and must NOT be rendered as "passed". Showing an unverified
   * run as a clean bill of health is the false assurance the gate exists to prevent.
   */
  acceptance?: {
    checks: AcceptanceCheck[];
    met_count: number;
    total: number;
  } | null;
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
export type ErrorReason = "not_tool_capable" | "timeout" | "turn_failed" | "cancelled";

/** Token counts for one model, or for the run as a whole (ARCH §21.7). */
export interface TokenCounts {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

/**
 * The run's token usage, emitted once before `run_finished` (ARCH §21.7).
 *
 * Tokens only — there is deliberately no cost field, because `model_catalog.pricing` has
 * no writers yet and a fabricated dollar figure would be worse than none. `by_model` is
 * keyed by resolved model name, which is the useful breakdown when a team's agents run
 * different models.
 */
export interface UsageData extends TokenCounts {
  by_model: Record<string, TokenCounts>;
}

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
  plan_ready: PlanReadyData;
  round_start: RoundStartData;
  agent_turn_start: AgentTurnStartData;
  reasoning: ReasoningData;
  tool_call: ToolCallData;
  tool_result: ToolResultData;
  contribution: ContributionData;
  confidence: ConfidenceData;
  critique: CritiqueData;
  a2a_message: A2AMessageData;
  plan_amended: PlanAmendedData;
  acceptance_report: AcceptanceReportData;
  consensus_update: ConsensusUpdateData;
  consensus_stalled: ConsensusStalledData;
  hitl_request: HitlRequestData;
  hitl_resolved: HitlResolvedData;
  synthesis: SynthesisData;
  usage: UsageData;
  run_finished: RunFinishedData;
  error: ErrorData;
}

export type AGUIEventType = keyof AGUIEventDataMap;

/** Runtime guard: the locked catalog (mirror of the backend frozenset). */
export const AGUI_EVENT_TYPES: readonly AGUIEventType[] = [
  "run_start",
  "plan_ready",
  "round_start",
  "agent_turn_start",
  "reasoning",
  "tool_call",
  "tool_result",
  "contribution",
  "confidence",
  "critique",
  "a2a_message",
  "plan_amended",
  "acceptance_report",
  "consensus_update",
  "consensus_stalled",
  "hitl_request",
  "hitl_resolved",
  "synthesis",
  "usage",
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

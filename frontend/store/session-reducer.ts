/**
 * AG-UI event reducer — the pure fold that turns the run's event stream into
 * render-ready state (the data the Slice-2 Workspace panels read).
 *
 * Why a pure function (separate from the Zustand store):
 *  - it is the highest-risk piece (reconstructing run state from 15 event types),
 *    so it gets its own unit test with no React/DOM (R3/R5);
 *  - it is immutable by construction — every branch returns a NEW state object,
 *    never mutating the input (global coding-style: immutability is critical);
 *  - `seq` dedup lives here, so replay-then-live reconnection (`after_seq`) is
 *    safe: an event whose `seq` was already applied is a no-op (ARCH §24.8).
 *
 * The shape is deliberately panel-oriented:
 *  - `agents`        → AgentGraph nodes (status / round / reasoning / tool)
 *  - `contributions` + `critiques` → DebateThread
 *  - `consensus` / `synthesis` / `artifact` → Blackboard + output
 *  - `hitl`          → HITL gate
 */
import type {
  AnyAGUIEvent,
  ArtifactAttachment,
  ArtifactFileKind,
  ArtifactStatus,
  ContentBlock,
  CritiqueSeverity,
  HitlDecision,
  HitlSource,
  ArtifactKind,
  ErrorReason,
} from "@/types/agui";

export type RunStatus = "idle" | "running" | "awaiting_human" | "finished" | "error";
export type AgentStatus = "idle" | "thinking" | "tool_call" | "contributed";

export interface AgentToolCall {
  tool: string;
  args: Record<string, unknown>;
  round: number;
  result?: unknown;
}

export interface AgentRuntimeState {
  agentId: string;
  status: AgentStatus;
  round: number;
  /** accumulated round-cadenced reasoning narration. */
  reasoning: string[];
  toolCalls: AgentToolCall[];
  latestConfidence: number | null;
}

export interface ContributionEntry {
  agentId: string;
  round: number;
  confidence: number;
  contentBlocks: ContentBlock[];
  /** prior-round peers this contribution builds on (§9.10 reply edges). */
  respondsTo: string[];
}

export interface CritiqueEntry {
  sender: string;
  target: string;
  round: number;
  severity: CritiqueSeverity;
  content: string;
}

export interface ConsensusState {
  meanConfidence: number;
  converged: boolean;
  /** `"agent_id:round"` keys, best first. */
  ranking: string[];
}

export interface HitlState {
  status: "pending" | "resolved";
  candidate: string | null;
  candidateKey: string | null;
  ranking: string[];
  converged: boolean;
  allowedDecisions: string[];
  decision: HitlDecision | null;
  source: HitlSource | null;
}

export interface SynthesisState {
  source: string | null;
  ranking: string[];
  contentBlocks: ContentBlock[];
  rejected: boolean;
}

export interface ArtifactState {
  kind: ArtifactKind;
  content: string | null;
  contentFormat: "markdown";
}

/** One downloadable file artifact streamed via a `tool_result` attachment (§11.1). */
export interface ArtifactEntry {
  artifactId: string;
  kind: ArtifactFileKind;
  filename: string | null;
  mimeType: string | null;
  version: number;
  status: ArtifactStatus;
  preview: string | null;
  /** relative signed path; the UI prefixes the API base (see lib/artifacts). */
  downloadUrl: string;
  sizeBytes: number | null;
  producerAgentId: string | null;
}

export interface RunErrorEntry {
  scope: string;
  agentId?: string;
  round?: number;
  message: string;
  /** §24.4 discriminator (e.g. "not_tool_capable") → drives the per-node badge. */
  reason?: ErrorReason;
}

export interface RunState {
  runId: string | null;
  sessionId: string | null;
  status: RunStatus;
  goal: string | null;
  /** roster agent-id strings from `run_start` (joined to agent records by the UI). */
  roster: string[];
  round: number;
  /** highest `seq` applied — the dedup / reconnect cursor (ARCH §24.8). */
  lastSeq: number;
  agents: Record<string, AgentRuntimeState>;
  contributions: ContributionEntry[];
  critiques: CritiqueEntry[];
  consensus: ConsensusState | null;
  hitl: HitlState | null;
  synthesis: SynthesisState | null;
  artifact: ArtifactState | null;
  /** Downloadable file artifacts (post-consensus producer, §11.1), in arrival order. */
  artifacts: ArtifactEntry[];
  errors: RunErrorEntry[];
}

/** A fresh, empty run state (before any event). */
export function initialRunState(): RunState {
  return {
    runId: null,
    sessionId: null,
    status: "idle",
    goal: null,
    roster: [],
    round: 0,
    lastSeq: 0,
    agents: {},
    contributions: [],
    critiques: [],
    consensus: null,
    hitl: null,
    synthesis: null,
    artifact: null,
    artifacts: [],
    errors: [],
  };
}

/**
 * Upsert an artifact entry into the list (immutably), keyed by `artifactId`.
 *
 * A later entry for the same artifact (a `generating → ready` flip, or an iterate→v2)
 * **replaces** in place; a new artifact is appended (arrival order). This backs both
 * the streamed `tool_result` path and the REST iterate action (§11.3 / §10) without
 * duplicating cards.
 */
export function upsertArtifactEntry(list: ArtifactEntry[], entry: ArtifactEntry): ArtifactEntry[] {
  const index = list.findIndex((a) => a.artifactId === entry.artifactId);
  if (index === -1) return [...list, entry];
  return list.map((a, i) => (i === index ? entry : a));
}

/** Map a streamed artifact descriptor (§11.1) to a render entry. */
function entryFromAttachment(
  attachment: ArtifactAttachment,
  producerAgentId: string | null,
): ArtifactEntry {
  return {
    artifactId: attachment.artifact_id,
    kind: attachment.kind,
    filename: attachment.filename,
    mimeType: attachment.mime_type,
    version: attachment.version,
    status: attachment.status,
    preview: attachment.preview,
    downloadUrl: attachment.download_url,
    sizeBytes: attachment.size_bytes,
    producerAgentId,
  };
}

/** Immutably get-or-create an agent's runtime slice. */
function ensureAgent(
  agents: Record<string, AgentRuntimeState>,
  agentId: string,
): AgentRuntimeState {
  return (
    agents[agentId] ?? {
      agentId,
      status: "idle",
      round: 0,
      reasoning: [],
      toolCalls: [],
      latestConfidence: null,
    }
  );
}

/** Immutably merge an agent slice back into the agents map. */
function withAgent(
  state: RunState,
  agentId: string,
  patch: Partial<AgentRuntimeState>,
): Record<string, AgentRuntimeState> {
  const current = ensureAgent(state.agents, agentId);
  return { ...state.agents, [agentId]: { ...current, ...patch } };
}

/**
 * Fold one AG-UI event into the run state, returning a NEW state.
 *
 * Dedup: an event whose `seq` is not greater than `lastSeq` (and which belongs
 * to the current run) is a no-op — this is what makes replay + live reconnect
 * idempotent. A `run_start` for a different `run_id` resets state (new run).
 */
export function applyEvent(state: RunState, event: AnyAGUIEvent): RunState {
  // New run on this surface → start clean (handles re-launch / surface reuse).
  if (event.type === "run_start" && state.runId !== null && state.runId !== event.run_id) {
    state = initialRunState();
  }

  // Replay/live dedup by monotonic seq (ARCH §24.8), scoped to the same run.
  if (state.runId !== null && state.runId === event.run_id && event.seq <= state.lastSeq) {
    return state;
  }

  const base: RunState = {
    ...state,
    runId: state.runId ?? event.run_id,
    sessionId: state.sessionId ?? event.session_id,
    lastSeq: Math.max(state.lastSeq, event.seq),
  };

  switch (event.type) {
    case "run_start":
      return {
        ...base,
        goal: event.data.goal,
        roster: [...event.data.roster],
        status: "running",
      };

    case "round_start":
      return { ...base, round: event.data.round, status: "running" };

    case "agent_turn_start":
      return {
        ...base,
        round: event.data.round,
        agents: withAgent(base, event.data.agent_id, {
          status: "thinking",
          round: event.data.round,
        }),
      };

    case "reasoning": {
      const agent = ensureAgent(base.agents, event.data.agent_id);
      return {
        ...base,
        agents: withAgent(base, event.data.agent_id, {
          status: "thinking",
          round: event.data.round,
          reasoning: [...agent.reasoning, event.data.text],
        }),
      };
    }

    case "tool_call": {
      const agent = ensureAgent(base.agents, event.data.agent_id);
      return {
        ...base,
        agents: withAgent(base, event.data.agent_id, {
          status: "tool_call",
          round: event.data.round,
          toolCalls: [
            ...agent.toolCalls,
            { tool: event.data.tool, args: event.data.args, round: event.data.round },
          ],
        }),
      };
    }

    case "tool_result": {
      // Producer file artifact (ARTIFACTS §11.1): a tool_result carrying an
      // `attachment` is a post-consensus deliverable, NOT a mesh-agent tool call —
      // fold it into `artifacts` only, never into `agents` (else the producer would
      // appear as a phantom debate node).
      if (event.data.attachment) {
        return {
          ...base,
          artifacts: upsertArtifactEntry(
            base.artifacts,
            entryFromAttachment(event.data.attachment, event.data.producer_agent_id ?? null),
          ),
        };
      }
      const agent = ensureAgent(base.agents, event.data.agent_id);
      // Attach the result to the most recent matching, still-open tool call.
      const idx = [...agent.toolCalls]
        .map((c, i) => ({ c, i }))
        .reverse()
        .find(({ c }) => c.tool === event.data.tool && c.result === undefined)?.i;
      const toolCalls =
        idx === undefined
          ? agent.toolCalls
          : agent.toolCalls.map((c, i) =>
              i === idx ? { ...c, result: event.data.result } : c,
            );
      return {
        ...base,
        agents: withAgent(base, event.data.agent_id, { toolCalls }),
      };
    }

    case "contribution":
      return {
        ...base,
        agents: withAgent(base, event.data.agent_id, {
          status: "contributed",
          round: event.data.round,
          latestConfidence: event.data.confidence,
        }),
        contributions: [
          ...base.contributions,
          {
            agentId: event.data.agent_id,
            round: event.data.round,
            confidence: event.data.confidence,
            contentBlocks: event.data.content_blocks,
            // Defensive default: older replays / the stub emit no responds_to.
            respondsTo: event.data.responds_to ?? [],
          },
        ],
      };

    case "confidence":
      // Reserved (not emitted standalone) — fold defensively if it ever appears.
      return {
        ...base,
        agents: withAgent(base, event.data.agent_id, {
          latestConfidence: event.data.confidence,
        }),
      };

    case "critique":
      return {
        ...base,
        critiques: [
          ...base.critiques,
          {
            sender: event.data.sender,
            target: event.data.target,
            round: event.data.round,
            severity: event.data.severity,
            content: event.data.content,
          },
        ],
      };

    case "consensus_update":
      return {
        ...base,
        consensus: {
          meanConfidence: event.data.mean_confidence,
          converged: event.data.converged,
          ranking: [...event.data.ranking],
        },
      };

    case "hitl_request":
      return {
        ...base,
        status: "awaiting_human",
        hitl: {
          status: "pending",
          candidate: event.data.candidate,
          candidateKey: event.data.candidate_key,
          ranking: [...event.data.ranking],
          converged: event.data.converged,
          allowedDecisions: [...event.data.allowed_decisions],
          decision: null,
          source: null,
        },
      };

    case "hitl_resolved":
      return {
        ...base,
        status: "running",
        hitl: {
          ...(base.hitl ?? {
            status: "resolved",
            candidate: null,
            candidateKey: null,
            ranking: [],
            converged: false,
            allowedDecisions: [],
            decision: null,
            source: null,
          }),
          status: "resolved",
          decision: event.data.decision,
          source: event.data.source,
        },
      };

    case "synthesis":
      return {
        ...base,
        synthesis: {
          source: event.data.source ?? null,
          ranking: event.data.ranking ? [...event.data.ranking] : [],
          contentBlocks: event.data.content_blocks ?? [],
          rejected: event.data.rejected ?? false,
        },
      };

    case "run_finished":
      return {
        ...base,
        status: "finished",
        artifact: {
          kind: event.data.artifact.kind,
          content: event.data.artifact.content,
          contentFormat: event.data.artifact.content_format,
        },
      };

    case "error": {
      const errors = [
        ...base.errors,
        {
          scope: event.data.scope,
          agentId: event.data.agent_id,
          round: event.data.round,
          message: event.data.message,
          reason: event.data.reason,
        },
      ];
      // A per-agent failure is an ABSTENTION, not a run failure: the backend
      // records confidence-0 and the round still completes (§21.5), going on to
      // consensus + HITL. Flipping the whole run to "error" here was the bug that
      // made the Workspace look dead while the run actually continued — so only a
      // RUN-scoped error (no agent_id) sets the run-level error status. The failed
      // agent itself is still surfaced per-node via `errors` (see graph-model).
      if (event.data.agent_id === undefined) {
        return { ...base, status: "error", errors };
      }
      return { ...base, errors };
    }

    default:
      // Exhaustiveness: every catalog type is handled above. An unknown type
      // here is a contract drift — surface it loudly rather than silently drop.
      return assertNever(event);
  }
}

/** Fold an ordered batch of events (replay or test convenience). */
export function reduceEvents(events: readonly AnyAGUIEvent[], from?: RunState): RunState {
  return events.reduce(applyEvent, from ?? initialRunState());
}

function assertNever(event: never): never {
  throw new Error(`Unhandled AG-UI event in reducer: ${JSON.stringify(event)}`);
}

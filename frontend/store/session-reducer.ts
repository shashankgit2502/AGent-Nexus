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
  A2AIntent,
  A2AMessageData,
  AcceptanceCheck,
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
  PlanStrategy,
  PlanSubtask,
  DeliverableKind,
} from "@/types/agui";

export type RunStatus =
  | "idle"
  | "running"
  | "awaiting_human"
  | "finished"
  | "error"
  /** stopped by the user (ARCH §21.6) — not a failure, and not a completed answer. */
  | "cancelled";
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
  /** tokens this agent has consumed so far this run; null when unreported. */
  tokens: { input: number; output: number; total: number } | null;
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

/**
 * One typed inter-agent message (ARCH §23) — what the team actually said to each
 * other. This is the data behind "who asked whom for what": directed intents
 * (`REQUEST`/`DELEGATE`/`ENDORSE`/`VOTE`/`CRITIQUE`) name a peer, broadcasts
 * (`INFORM`/`PROPOSE`) go to the whole board.
 */
export interface A2AMessageEntry {
  id: string;
  sender: string;
  /** `"*"` = broadcast to the team; otherwise the addressed peers. */
  recipients: string[] | "*";
  intent: A2AIntent;
  round: number;
  /** human-readable body pulled from the intent's payload key. */
  body: string;
  severity?: CritiqueSeverity;
  sourceUrls: string[];
  inReplyTo: string | null;
}

/** A mid-run plan change made by a peer, not by an orchestrator (ARCH §4.1). */
export interface PlanAmendmentEntry {
  round: number;
  byAgent: string;
  change: string;
  subtaskId: string | null;
  reason: string | null;
}

/** Post-consensus verification that the plan's acceptance criteria were met. */
export interface AcceptanceState {
  round: number;
  checks: AcceptanceCheck[];
  metCount: number;
  total: number;
}

export interface ConsensusState {
  /** raw mean of self-reported confidence (unchanged meaning). */
  meanConfidence: number;
  /** mean of the peer-adjusted scores — what τ is actually compared against (ARCH §8.1). */
  meanScore: number;
  converged: boolean;
  /** `"agent_id:round"` keys, best first — ordered by peer-adjusted score. */
  ranking: string[];
  /** `"agent_id:round"` → peer-adjusted score; empty when no peer signal exists. */
  peerScores: Record<string, number>;
  /** `"agent_id:round"` → signed peer adjustment (−1…+1) applied to self-confidence. */
  peerDeltas: Record<string, number>;
  /** share of peer votes on the top candidate; null when nobody voted. */
  agreement: number | null;
  /** agent_id → votes received — the "who backed whom" tally. */
  tally: Record<string, number>;
}

/**
 * The orchestrator's plan for the run (ARCH §4.1) — who is doing what, and what
 * the team is building. Present from `plan_ready`, i.e. before round 1 opens, so
 * the Workspace can show the assignment up front instead of inferring it from
 * contributions after the fact.
 */
export interface PlanState {
  strategy: PlanStrategy;
  summary: string;
  subtasks: PlanSubtask[];
  deliverable: { kind: DeliverableKind; filename: string | null; notes: string | null };
  warnings: string[];
}

/**
 * Why the debate loop stopped early — every agent abstained this round (§21.5),
 * e.g. all rate-limited. Distinct from `errors`: the run did not fail, it simply
 * has no further signal to gain from another identical round.
 */
export interface StalledState {
  round: number;
  meanConfidence: number;
  message: string;
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

/** The run's token usage (ARCH §21.7). Tokens only — there is no cost figure yet. */
export interface UsageState {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  /** resolved model name → its own counts, for a team whose agents run different models. */
  byModel: Record<string, { input_tokens: number; output_tokens: number; total_tokens: number }>;
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
  /** the orchestrator's assignment for this run; null until `plan_ready`. */
  plan: PlanState | null;
  /** highest `seq` applied — the dedup / reconnect cursor (ARCH §24.8). */
  lastSeq: number;
  agents: Record<string, AgentRuntimeState>;
  contributions: ContributionEntry[];
  critiques: CritiqueEntry[];
  /** the team's inter-agent conversation, in arrival order (ARCH §23). */
  messages: A2AMessageEntry[];
  /** plan changes peers made mid-run (ARCH §4.1). */
  planAmendments: PlanAmendmentEntry[];
  /** post-consensus acceptance verification; null until the report arrives. */
  acceptance: AcceptanceState | null;
  consensus: ConsensusState | null;
  /** set when the loop stopped early on an all-abstained round (§21.5). */
  stalled: StalledState | null;
  hitl: HitlState | null;
  synthesis: SynthesisState | null;
  artifact: ArtifactState | null;
  /** Downloadable file artifacts (post-consensus producer, §11.1), in arrival order. */
  artifacts: ArtifactEntry[];
  /** token usage for the run; null until the `usage` event arrives (ARCH §21.7). */
  usage: UsageState | null;
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
    plan: null,
    lastSeq: 0,
    agents: {},
    contributions: [],
    critiques: [],
    messages: [],
    planAmendments: [],
    acceptance: null,
    consensus: null,
    stalled: null,
    hitl: null,
    synthesis: null,
    artifact: null,
    artifacts: [],
    usage: null,
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

/**
 * Payload key carrying the readable body, per intent (mirror of the backend's
 * `_BODY_KEY_BY_INTENT`, ARCH §23.3). `VOTE` has none — a ballot is a target and an
 * optional weight, not a statement.
 */
const A2A_BODY_KEY: Record<A2AIntent, string | null> = {
  INFORM: "content",
  REQUEST: "question",
  PROPOSE: "content",
  CRITIQUE: "content",
  DELEGATE: "subtask",
  ENDORSE: "reason",
  VOTE: null,
};

/** Read a payload value as a trimmed string, or `""` — the payload is untyped JSON. */
function payloadText(payload: Record<string, unknown>, key: string | null): string {
  if (!key) return "";
  const value = payload[key];
  return typeof value === "string" ? value.trim() : "";
}

/** Map a streamed A2A message onto a render entry, flattening the intent-keyed body. */
function entryFromMessage(data: A2AMessageData): A2AMessageEntry {
  const severity = data.payload.severity;
  const sources = data.payload.source_urls;
  return {
    id: data.id,
    sender: data.sender,
    recipients: data.recipients === "*" ? "*" : [...data.recipients],
    intent: data.intent,
    round: data.round,
    body: payloadText(data.payload, A2A_BODY_KEY[data.intent]),
    severity:
      severity === "minor" || severity === "major" || severity === "blocking"
        ? severity
        : undefined,
    sourceUrls: Array.isArray(sources) ? sources.map(String) : [],
    inReplyTo: data.in_reply_to ?? null,
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
      tokens: null,
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

    case "plan_ready":
      return {
        ...base,
        plan: {
          strategy: event.data.strategy,
          summary: event.data.summary,
          subtasks: [...event.data.subtasks],
          deliverable: { ...event.data.deliverable },
          warnings: [...event.data.warnings],
        },
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

    case "contribution": {
      const agent = ensureAgent(base.agents, event.data.agent_id);
      // Accumulate across rounds — an agent's cost is what it spent over the whole run,
      // not just its last turn. Absent `tokens` leaves the prior value untouched, so an
      // unreported turn cannot erase what earlier rounds already measured.
      const tokens = event.data.tokens
        ? {
            input: (agent.tokens?.input ?? 0) + event.data.tokens.input,
            output: (agent.tokens?.output ?? 0) + event.data.tokens.output,
            total: (agent.tokens?.total ?? 0) + event.data.tokens.total,
          }
        : agent.tokens;
      return {
        ...base,
        agents: withAgent(base, event.data.agent_id, {
          status: "contributed",
          round: event.data.round,
          latestConfidence: event.data.confidence,
          tokens,
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
    }

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

    case "a2a_message":
      return {
        ...base,
        messages: [...base.messages, entryFromMessage(event.data)],
      };

    case "plan_amended":
      return {
        ...base,
        planAmendments: [
          ...base.planAmendments,
          {
            round: event.data.round,
            byAgent: event.data.by_agent,
            change: event.data.change,
            subtaskId: event.data.subtask_id ?? null,
            reason: event.data.reason ?? null,
          },
        ],
      };

    case "acceptance_report":
      return {
        ...base,
        acceptance: {
          round: event.data.round,
          checks: [...event.data.checks],
          metCount: event.data.met_count,
          total: event.data.total,
        },
      };

    case "consensus_update":
      return {
        ...base,
        consensus: {
          meanConfidence: event.data.mean_confidence,
          converged: event.data.converged,
          ranking: [...event.data.ranking],
          // Peer-weighted fields (ARCH §8.1) are optional: a run with no A2A signal —
          // or a replay from before §8.1 — carries none, so `meanScore` falls back to
          // `mean_confidence`, which is exactly what it equals when no peer signal exists.
          meanScore: event.data.mean_score ?? event.data.mean_confidence,
          peerScores: { ...(event.data.peer_scores ?? {}) },
          peerDeltas: { ...(event.data.peer_deltas ?? {}) },
          agreement: event.data.agreement ?? null,
          tally: { ...(event.data.tally ?? {}) },
        },
      };

    case "consensus_stalled":
      // Not a failure: the loop stops early because another identical round would
      // abstain identically (§21.5). The run continues to the human gate, so the
      // status is left untouched — we only record WHY the debate ended short.
      return {
        ...base,
        stalled: {
          round: event.data.round,
          meanConfidence: event.data.mean_confidence,
          message: event.data.message,
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
        // The gate carries the acceptance verdict too, so a replay that starts at the
        // interrupt still shows ✓/✗ even if the `acceptance_report` event scrolled past.
        // Absent ⇒ leave whatever the report set (possibly null = unverified).
        acceptance: event.data.acceptance
          ? {
              round: base.round,
              checks: [...event.data.acceptance.checks],
              metCount: event.data.acceptance.met_count,
              total: event.data.acceptance.total,
            }
          : base.acceptance,
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

    case "usage":
      return {
        ...base,
        usage: {
          inputTokens: event.data.input_tokens,
          outputTokens: event.data.output_tokens,
          totalTokens: event.data.total_tokens,
          byModel: { ...event.data.by_model },
        },
      };

    case "run_finished":
      return {
        ...base,
        // A cancelled run is terminal but is neither a success nor a failure — the
        // header must say "stopped", not "finished" (which would imply an answer exists)
        // and not "error" (which would imply something broke).
        status: event.data.artifact.kind === "cancelled" ? "cancelled" : "finished",
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

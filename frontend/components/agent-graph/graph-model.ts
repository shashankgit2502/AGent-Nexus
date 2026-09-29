/**
 * Pure view-model builders: RunState → render-ready panel data.
 *
 * This is the highest-risk mapping in Slice 2 (reconstructing the AgentGraph
 * topology, the debate timeline, and the consensus read-out from the folded
 * run state), so it lives as PURE functions — no React, no @xyflow runtime, no
 * DOM — and gets its own unit test in the node env (R3/R5), the same pattern as
 * the Slice-1 reducer test.
 *
 * Contract honesty (R4 — §9.10's absolute rule "every animated edge is backed
 * by a real event"): the verified §24.4 contract now carries two directed
 * interactions — `critique` (sender→target) and a contribution's `responds_to`
 * (the backend's honest form of §9.10's `in_reply_to`: agent-ids of prior-round
 * peers this proposal builds on, server-validated by `_valid_responds_to`). Both
 * yield active edges for the CURRENT round only. The graph renders a PURE PEER
 * MESH: the orchestrator is the passive entry node (locked decision §3 — "no
 * master, no hierarchy"), never a mesh agent, so it is NOT drawn here. It never
 * appears in `run_start.roster`, and we deliberately render no synthetic hub for
 * it — a central dispatcher node would visually imply the very hierarchy the
 * architecture forbids.
 *
 * `import type` keeps @xyflow/react out of the test runtime — these are
 * type-only imports, erased at compile, so the pure test never loads React Flow.
 */
import type { Node, Edge } from "@xyflow/react";
import type { A2AIntent, ContentBlock, CritiqueSeverity } from "@/types/agui";
import type {
  RunState,
  AgentStatus,
  A2AMessageEntry,
  ContributionEntry,
  CritiqueEntry,
} from "@/store/session-reducer";

/**
 * Node status = the reducer's AgentStatus plus two derived per-agent terminal states:
 * `abstained` (a config/capability abstention the user can fix — e.g. the model can't
 * call tools, §9.3) and `error` (a transient/unknown failure). Split so the board can
 * show a fixable amber warning instead of an alarming red error (Slice 2).
 */
export type AgentNodeStatus = AgentStatus | "error" | "abstained";

/** Label/model for a roster id, joined from `GET /teams/{id}/agents` (§5.2). */
export interface AgentLabel {
  id: string;
  name: string;
  model?: string | null;
}

/** Custom-node payload the `AgentNodeView` renders. */
export interface AgentNodeData extends Record<string, unknown> {
  agentId: string;
  label: string;
  model: string | null;
  status: AgentNodeStatus;
  round: number;
  /** latest contributed confidence (0–1) or null before contributing. */
  confidence: number | null;
  hasError: boolean;
  /** why this agent failed/abstained this run (backend `error.message`), for the
   * node to show — null when the agent has no error. */
  errorMessage: string | null;
  /**
   * What the plan assigned this agent (ARCH §4.1) — the node's job title, so the board
   * reads "Research: find the regulations" instead of an anonymous dot. Null for an agent
   * the plan gave no subtask (a reviewer role, or a `debate` plan with no split).
   */
  subtask: string | null;
  /** Peer votes received this round (ARCH §8.1) — shows who the team actually backed. */
  votes: number;
}

export type AgentNode = Node<AgentNodeData, "agent">;

export interface AgentEdgeData extends Record<string, unknown> {
  kind: "static" | "critique" | "reply" | "a2a";
  severity?: CritiqueSeverity;
  /** For `kind: "a2a"` — which performative this edge represents (ARCH §23.3). */
  intent?: A2AIntent;
  active: boolean;
}

/**
 * A2A intents that produce a **point-to-point edge** on the graph.
 *
 * Only directed intents qualify. `INFORM` and `PROPOSE` are broadcasts — they have no
 * single "whom", so rendering them as edges would mean N-1 lines from every sender to
 * every peer: the exact O(N²) clutter `STATIC_MESH_MAX` already exists to prevent, and it
 * would say nothing beyond "someone spoke". Broadcasts belong in the debate timeline, which
 * answers "what was said, in order"; the graph answers "who asked whom".
 */
const EDGE_INTENTS: readonly A2AIntent[] = ["REQUEST", "DELEGATE", "ENDORSE", "VOTE"];

/** Per-intent edge styling — colour carries meaning, width carries emphasis. */
const A2A_EDGE_STYLE: Record<string, { color: string; width: number }> = {
  // Amber: someone is blocked and waiting on a peer. The most action-bearing edge
  // on the board, so it reads warmest.
  REQUEST: { color: "#f59e0b", width: 2.0 },
  // Violet: work changed hands — a structural change to who-does-what.
  DELEGATE: { color: "#a78bfa", width: 2.2 },
  // Emerald: genuine peer agreement (feeds the §8.1 consensus score).
  ENDORSE: { color: "#34d399", width: 1.6 },
  // Teal, thin: a ballot is real signal but carries no content to read.
  VOTE: { color: "#2dd4bf", width: 1.2 },
};

export type AgentEdge = Edge<AgentEdgeData>;

export interface GraphModel {
  nodes: AgentNode[];
  edges: AgentEdge[];
}

// Static-mesh cap: past this many agents an O(N²) faint mesh janks and says
// nothing (FRONTEND_SPEC §9.3) — drop the static mesh, keep only live edges.
const STATIC_MESH_MAX = 12;

// A restrained, professional palette (Bug 5): a desaturated rose for critique
// ("requested changes") and a calm slate-blue for a reply ("builds on"), both solid
// — not the harsh primary red + dashed indigo that read as cluttered.
const CRITIQUE_COLOR = "#f43f5e"; // rose-500
const STATIC_EDGE_COLOR = "rgba(255,255,255,0.05)";
const REPLY_COLOR = "#60a5fa"; // blue-400
const GRAPH_CENTER = { x: 400, y: 210 };
const AGENT_RING_RADIUS = 175;

/** Short, stable fallback label when no agent record is joined yet. */
function shortId(id: string): string {
  return id.length <= 8 ? id : `${id.slice(0, 8)}…`;
}

/** Severity → edge thickness (§9.10 "severity → thickness"). */
function severityWidth(severity: CritiqueSeverity): number {
  switch (severity) {
    case "blocking":
      return 3;
    case "major":
      return 2.2;
    case "minor":
    default:
      return 1.4;
  }
}

/**
 * Deterministic ring layout — agents sit on a circle around the orchestrator
 * hub (placed at the centre by `buildGraphModel`). Stable per roster index so
 * nodes don't jump between renders (React Flow diffs by id; positions hold).
 */
export function layoutPositions(ids: readonly string[]): Record<string, { x: number; y: number }> {
  const r = ids.length <= 1 ? 0 : AGENT_RING_RADIUS;
  const positions: Record<string, { x: number; y: number }> = {};
  ids.forEach((id, i) => {
    const angle = (2 * Math.PI * i) / Math.max(1, ids.length) - Math.PI / 2;
    positions[id] = {
      x: GRAPH_CENTER.x + r * Math.cos(angle),
      y: GRAPH_CENTER.y + r * Math.sin(angle),
    };
  });
  return positions;
}

/** Build the React Flow nodes + edges for the AgentGraph from the run state. */
export function buildGraphModel(
  run: RunState,
  labels: Record<string, AgentLabel> = {},
): GraphModel {
  // Roster ids drive the topology; fall back to whatever agents have spoken if
  // run_start hasn't been seen yet (e.g. mid-run reconnect replay ordering).
  const ids = run.roster.length > 0 ? run.roster : Object.keys(run.agents);
  const idSet = new Set(ids);
  const positions = layoutPositions(ids);

  // agent_id → the plan's title for its work. Multiple subtasks join with " · " so an
  // agent owning two pieces still reads honestly rather than showing only the first.
  const subtasks = new Map<string, string[]>();
  for (const task of run.plan?.subtasks ?? []) {
    const list = subtasks.get(task.agent_id);
    if (list) list.push(task.title);
    else subtasks.set(task.agent_id, [task.title]);
  }
  const tally = run.consensus?.tally ?? {};

  // A run that reached a terminal state (finished/errored — including an
  // interrupted run finalized by the backend's startup recovery, ARCH §24.8) must
  // not leave agents pulsing "thinking"/"tool_call" forever: the work is over.
  const runEnded = run.status === "finished" || run.status === "error";

  const nodes: AgentNode[] = ids.map((id) => {
    const runtime = run.agents[id];
    // Last error naming this agent carries the reason to show on the node. Using
    // the latest (not first) means a later round's failure replaces a stale one.
    const agentError = [...run.errors].reverse().find((e) => e.agentId === id);
    const hasError = agentError !== undefined;
    const liveStatus = runtime?.status ?? "idle";
    // When the run has ended but this agent was left mid-turn (never contributed,
    // no per-agent error), settle it to "idle" so the node stops showing the live
    // "thinking" glow — the terminal event arrived; nothing more is coming.
    const stalled =
      runEnded && (liveStatus === "thinking" || liveStatus === "tool_call");
    // A `not_tool_capable` abstention is a fixable config state (amber), distinct from
    // a transient/unknown failure (red). Unknown reasons fall through to "error".
    const errorStatus: AgentNodeStatus =
      agentError?.reason === "not_tool_capable" ? "abstained" : "error";
    const status: AgentNodeStatus = hasError ? errorStatus : stalled ? "idle" : liveStatus;
    return {
      id,
      type: "agent",
      position: positions[id] ?? { x: 0, y: 0 },
      data: {
        agentId: id,
        label: labels[id]?.name ?? shortId(id),
        model: labels[id]?.model ?? null,
        status,
        round: runtime?.round ?? 0,
        confidence: runtime?.latestConfidence ?? null,
        hasError,
        errorMessage: agentError?.message ?? null,
        subtask: subtasks.get(id)?.join(" · ") ?? null,
        votes: tally[id] ?? 0,
      },
    };
  });

  const edges: AgentEdge[] = [];

  // Faint static full-mesh = "any agent could reach any agent" (topology only).
  if (ids.length <= STATIC_MESH_MAX) {
    for (let i = 0; i < ids.length; i += 1) {
      for (let j = i + 1; j < ids.length; j += 1) {
        const a = ids[i];
        const b = ids[j];
        if (a === undefined || b === undefined) continue;
        edges.push({
          id: `static-${a}-${b}`,
          source: a,
          target: b,
          selectable: false,
          data: { kind: "static", active: false },
          style: { stroke: STATIC_EDGE_COLOR, strokeWidth: 1 },
        });
      }
    }
  }

  // The glowing mesh only lives **while the agents are actively communicating**
  // (Bug 5): a round is in flight. Once the run converges and moves on (awaiting the
  // human gate, synthesizing, finished, errored), the communication is over — we drop
  // the animated edges so the board settles back to the faint static mesh instead of
  // freezing a cluttered web of edges. `run.round` still scopes them to the current
  // round (round-cadenced, §9.10).
  const communicating = run.status === "running";
  const round = run.round;

  // Bright animated edges = real critiques of the CURRENT round, one edge per
  // (sender→target) pair, keeping the highest severity.
  if (communicating) {
    const merged = new Map<string, { sender: string; target: string; severity: CritiqueSeverity }>();
    for (const c of run.critiques) {
      if (c.round !== round) continue;
      if (!idSet.has(c.sender) || !idSet.has(c.target)) continue;
      const key = `${c.sender}->${c.target}`;
      const prev = merged.get(key);
      merged.set(key, {
        sender: c.sender,
        target: c.target,
        severity: maxSeverity(prev?.severity, c.severity),
      });
    }
    for (const [key, { sender, target, severity }] of merged) {
      edges.push({
        id: `crit-${key}-r${round}`,
        source: sender,
        target,
        animated: true,
        selectable: false,
        markerEnd: "arrowclosed",
        data: { kind: "critique", severity, active: true },
        style: { stroke: CRITIQUE_COLOR, strokeWidth: severityWidth(severity) },
      });
    }

    // Reply edges (§9.10 "reply → accent, references the prior author"): a
    // CURRENT-round contribution's `respondsTo` peers, drawn responder→author. The
    // backend already validated honesty (`_valid_responds_to`), but the WS is a trust
    // boundary (R5), so we re-filter to roster ids that aren't self and dedup per pair.
    const replyPairs = new Set<string>();
    for (const c of run.contributions) {
      if (c.round !== round) continue;
      if (!idSet.has(c.agentId)) continue;
      for (const author of c.respondsTo) {
        if (author === c.agentId || !idSet.has(author)) continue;
        const key = `${c.agentId}->${author}`;
        if (replyPairs.has(key)) continue;
        replyPairs.add(key);
        edges.push({
          id: `reply-${key}-r${round}`,
          source: c.agentId,
          target: author,
          animated: true,
          selectable: false,
          markerEnd: "arrowclosed",
          data: { kind: "reply", active: true },
          style: { stroke: REPLY_COLOR, strokeWidth: 1.4 },
        });
      }
    }

    // A2A edges (ARCH §23.3) — the directed intents, which is what finally makes the
    // board show a *team* rather than parallel monologues: who is blocked on whom
    // (REQUEST), who handed work over (DELEGATE), and who backed whose answer
    // (ENDORSE/VOTE). Broadcasts are deliberately excluded — see `EDGE_INTENTS`.
    //
    // Same honesty rule as every other edge (§9.10): each one is backed by a real
    // `a2a_message` event that passed backend validation. Nothing decorative.
    const a2aPairs = new Set<string>();
    for (const m of run.messages) {
      if (m.round !== round) continue;
      if (!EDGE_INTENTS.includes(m.intent)) continue;
      if (m.recipients === "*" || !idSet.has(m.sender)) continue;
      for (const target of m.recipients) {
        if (target === m.sender || !idSet.has(target)) continue;
        // One edge per (sender, target, intent): an agent that sends two REQUESTs to
        // the same peer in one round is one relationship, not two lines.
        const key = `${m.intent}-${m.sender}->${target}`;
        if (a2aPairs.has(key)) continue;
        a2aPairs.add(key);
        const style = A2A_EDGE_STYLE[m.intent] ?? { color: REPLY_COLOR, width: 1.4 };
        edges.push({
          id: `a2a-${key}-r${round}`,
          source: m.sender,
          target,
          animated: true,
          selectable: false,
          markerEnd: "arrowclosed",
          data: { kind: "a2a", intent: m.intent, active: true },
          style: { stroke: style.color, strokeWidth: style.width },
        });
      }
    }
  }

  return { nodes, edges };
}

const SEVERITY_RANK: Record<CritiqueSeverity, number> = { minor: 0, major: 1, blocking: 2 };
function maxSeverity(a: CritiqueSeverity | undefined, b: CritiqueSeverity): CritiqueSeverity {
  if (a === undefined) return b;
  return SEVERITY_RANK[b] > SEVERITY_RANK[a] ? b : a;
}

// ── Debate timeline (right rail) ──────────────────────────────────────────────

export interface DebateContributionItem {
  kind: "contribution";
  key: string;
  round: number;
  author: string;
  confidence: number;
  contentBlocks: ContentBlock[];
}
export interface DebateCritiqueItem {
  kind: "critique";
  key: string;
  round: number;
  sender: string;
  target: string;
  severity: CritiqueSeverity;
  content: string;
}
/**
 * One typed inter-agent message in the thread (ARCH §23.3).
 *
 * The timeline is where broadcasts live: an `INFORM` carrying the three regulations
 * Research found has no single recipient to draw an edge to, but it is exactly the thing a
 * user needs to read. Directed intents appear here *as well as* on the graph — the graph
 * shows the relationship, the thread shows what was actually said.
 */
export interface DebateMessageItem {
  kind: "message";
  key: string;
  round: number;
  sender: string;
  /** `null` = broadcast to the whole team. */
  recipients: string[] | null;
  intent: A2AIntent;
  body: string;
  severity?: CritiqueSeverity;
  sourceUrls: string[];
}

export type DebateItem = DebateContributionItem | DebateCritiqueItem | DebateMessageItem;

/**
 * Merge contributions + critiques into one ordered thread.
 *
 * The reducer keeps the two arrays in arrival order. We concatenate
 * contributions-then-critiques and stable-sort by round, so within a round the
 * contributions render before the critiques that respond to them (matches the
 * PR-review reading order of §9.4). Stable sort preserves arrival order within
 * each (round, kind) group. We have no global per-event index in RunState, so
 * round + kind is the honest, deterministic ordering we can derive.
 */
export function buildDebateTimeline(run: RunState): DebateItem[] {
  const contributions: DebateItem[] = run.contributions.map(
    (c: ContributionEntry, i): DebateContributionItem => ({
      kind: "contribution",
      key: `contrib-${c.agentId}-${c.round}-${i}`,
      round: c.round,
      author: c.agentId,
      confidence: c.confidence,
      contentBlocks: c.contentBlocks,
    }),
  );
  const critiques: DebateItem[] = run.critiques.map(
    (c: CritiqueEntry, i): DebateCritiqueItem => ({
      kind: "critique",
      key: `crit-${c.sender}-${c.target}-${c.round}-${i}`,
      round: c.round,
      sender: c.sender,
      target: c.target,
      severity: c.severity,
      content: c.content,
    }),
  );
  // A2A messages join the same thread. `VOTE` is excluded: it carries no body, so as a
  // thread row it would be a content-free line repeated once per agent per round —
  // pure noise. Votes are shown where they mean something: the graph edge and the
  // consensus tally.
  const messages: DebateItem[] = run.messages
    .filter((m: A2AMessageEntry) => m.intent !== "VOTE")
    .map(
      (m: A2AMessageEntry): DebateMessageItem => ({
        kind: "message",
        key: `msg-${m.id}`,
        round: m.round,
        sender: m.sender,
        recipients: m.recipients === "*" ? null : [...m.recipients],
        intent: m.intent,
        body: m.body,
        severity: m.severity,
        sourceUrls: m.sourceUrls,
      }),
    );
  return [...contributions, ...critiques, ...messages].sort((a, b) => a.round - b.round);
}

// ── Consensus read-out (header ring + detail) ─────────────────────────────────

export interface ConsensusModel {
  /** mean confidence 0–1 (drives the ring); null before any consensus_update. */
  meanConfidence: number | null;
  /**
   * Mean peer-adjusted score (ARCH §8.1) — the number actually compared against τ.
   * Equals `meanConfidence` when there is no peer signal, so it is safe to show alone.
   */
  meanScore: number | null;
  converged: boolean;
  /** `"agent_id:round"` ranking keys, best first. */
  ranking: string[];
  round: number;
  /** `"agent_id:round"` → signed peer adjustment (−1…+1) applied to self-confidence. */
  peerDeltas: Record<string, number>;
  /** agent_id → votes received. Empty when no peer voted. */
  tally: Record<string, number>;
  /** share of votes on the top candidate; null when nobody voted. */
  agreement: number | null;
}

export function buildConsensusModel(run: RunState): ConsensusModel {
  return {
    meanConfidence: run.consensus?.meanConfidence ?? null,
    meanScore: run.consensus?.meanScore ?? run.consensus?.meanConfidence ?? null,
    converged: run.consensus?.converged ?? false,
    ranking: run.consensus?.ranking ?? [],
    round: run.round,
    peerDeltas: run.consensus?.peerDeltas ?? {},
    tally: run.consensus?.tally ?? {},
    agreement: run.consensus?.agreement ?? null,
  };
}

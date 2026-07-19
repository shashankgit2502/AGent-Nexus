/**
 * Mock AG-UI replayer (FRONTEND_SPEC §18).
 *
 * A canned, **contract-valid** event stream (one deep-collaborate run: two
 * agents, one round, a HITL gate, an approved synthesis) so the UI and the
 * session store can run with no live backend. The same array is the fixture
 * for the reducer unit test. Every envelope matches `types/agui.ts` exactly;
 * `seq` is monotonic from 1, in the canonical per-run order (§5.2).
 *
 * `replayAGUIStream` plays the events back over time into an `onEvent`
 * callback, mimicking the WS client — useful for offline Workspace dev.
 */
import type { AGUIEvent, AGUIEventType, AnyAGUIEvent, AGUIEventDataMap } from "@/types/agui";

const SESSION_ID = "mock-session-0001";
const RUN_ID = "mock-run-0001";
const AGENT_A = "agent-alpha";
const AGENT_B = "agent-beta";

/** Build a fully-formed envelope; `seq` and `ts` are assigned by the builder. */
function makeBuilder() {
  let seq = 0;
  const base = Date.now();
  return function event<T extends AGUIEventType>(
    type: T,
    data: AGUIEventDataMap[T],
  ): AGUIEvent<T> {
    seq += 1;
    return {
      type,
      session_id: SESSION_ID,
      run_id: RUN_ID,
      seq,
      ts: new Date(base + seq * 250).toISOString(),
      data,
    };
  };
}

/** The canned stream — exercises every event the backend emits in a run. */
export function buildMockStream(): AnyAGUIEvent[] {
  const e = makeBuilder();
  return [
    e("run_start", { goal: "Design a resilient rate-limiter", roster: [AGENT_A, AGENT_B] }),
    e("round_start", { round: 1 }),

    // Agent A's turn
    e("agent_turn_start", { agent_id: AGENT_A, round: 1 }),
    e("reasoning", { agent_id: AGENT_A, round: 1, text: "Considering a token-bucket per tenant." }),
    e("tool_call", { agent_id: AGENT_A, round: 1, tool: "search_knowledge", args: { q: "rate limiter" } }),
    e("tool_result", { agent_id: AGENT_A, round: 1, tool: "search_knowledge", result: "3 docs found" }),
    e("contribution", {
      agent_id: AGENT_A,
      round: 1,
      confidence: 0.82,
      content_blocks: [{ type: "text", text: "Use a Redis token-bucket keyed by tenant." }],
    }),
    e("critique", {
      sender: AGENT_A,
      target: AGENT_B,
      round: 1,
      severity: "minor",
      content: "Sliding window adds memory cost at scale.",
    }),

    // Agent B's turn
    e("agent_turn_start", { agent_id: AGENT_B, round: 1 }),
    e("reasoning", { agent_id: AGENT_B, round: 1, text: "Sliding-window log gives smoother limits." }),
    e("contribution", {
      agent_id: AGENT_B,
      round: 1,
      confidence: 0.9,
      content_blocks: [
        { type: "text", text: "Prefer a sliding-window counter with a Lua script." },
        { type: "code", language: "lua", code: "-- atomic INCR + EXPIRE\nreturn redis.call('INCR', KEYS[1])" },
      ],
    }),
    e("critique", {
      sender: AGENT_B,
      target: AGENT_A,
      round: 1,
      severity: "major",
      content: "Token bucket bursts past the limit at window edges.",
    }),

    // Consensus over round 1
    e("consensus_update", {
      mean_confidence: 0.86,
      converged: true,
      ranking: [`${AGENT_B}:1`, `${AGENT_A}:1`],
    }),

    // Human gate (deep collaborate)
    e("hitl_request", {
      candidate: "Prefer a sliding-window counter with a Lua script.",
      candidate_key: `${AGENT_B}:1`,
      ranking: [`${AGENT_B}:1`, `${AGENT_A}:1`],
      converged: true,
      allowed_decisions: ["approve", "edit", "reject"],
    }),
    e("hitl_resolved", { decision: "approve", source: "human" }),

    // Synthesis + finish
    e("synthesis", {
      source: "model",
      ranking: [`${AGENT_B}:1`, `${AGENT_A}:1`],
      content_blocks: [
        { type: "text", text: "Adopt a sliding-window counter (Lua) with a token-bucket fallback." },
      ],
    }),
    e("run_finished", {
      artifact: {
        kind: "synthesis",
        content: "Adopt a sliding-window counter (Lua) with a token-bucket fallback.",
        content_format: "markdown",
      },
    }),
  ];
}

export interface ReplayOptions {
  /** ms between events (default 400). */
  intervalMs?: number;
  /** stop early after N events (default: all). */
  limit?: number;
}

/** Play the canned stream into `onEvent` over time; returns a cancel function. */
export function replayAGUIStream(
  onEvent: (event: AnyAGUIEvent) => void,
  options: ReplayOptions = {},
): () => void {
  const { intervalMs = 400, limit } = options;
  const events = buildMockStream().slice(0, limit);
  let index = 0;
  const timer = setInterval(() => {
    const next = events[index];
    if (!next) {
      clearInterval(timer);
      return;
    }
    onEvent(next);
    index += 1;
  }, intervalMs);
  return () => clearInterval(timer);
}

export const MOCK_IDS = { sessionId: SESSION_ID, runId: RUN_ID, agentA: AGENT_A, agentB: AGENT_B };

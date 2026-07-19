/**
 * Slice-2 acceptance test: the reducer→panels path.
 *
 * Pure-function tests (node env, no DOM/React/@xyflow runtime): fold the canned
 * mock AG-UI stream with the Slice-1 reducer, then assert the view-model
 * builders produce the render-ready shapes the Workspace panels consume —
 * AgentGraph nodes/edges, the debate timeline, and the consensus read-out.
 *
 * This is the highest-risk mapping in the slice, so it is verified end-to-end
 * (events → RunState → panel model) without rendering any component.
 */
import { describe, it, expect } from "vitest";
import { buildMockStream, MOCK_IDS } from "@/mocks/agui-replayer";
import { reduceEvents, applyEvent, initialRunState } from "@/store/session-reducer";
import {
  buildGraphModel,
  buildDebateTimeline,
  buildConsensusModel,
  layoutPositions,
  type AgentEdgeData,
} from "@/components/agent-graph/graph-model";
import type { AnyAGUIEvent } from "@/types/agui";

describe("buildGraphModel — RunState → React Flow topology", () => {
  const labels = {
    [MOCK_IDS.agentA]: { id: MOCK_IDS.agentA, name: "Alpha", model: "gpt-4o" },
    [MOCK_IDS.agentB]: { id: MOCK_IDS.agentB, name: "Beta", model: "claude" },
  };

  it("renders one node per roster id with joined labels — a pure peer mesh, no hub", () => {
    const run = reduceEvents(buildMockStream());
    const { nodes } = buildGraphModel(run, labels);
    // Exactly the roster agents — no synthetic orchestrator hub (locked decision §3).
    expect(nodes).toHaveLength(2);
    const alpha = nodes.find((n) => n.id === MOCK_IDS.agentA);
    expect(alpha?.data.label).toBe("Alpha");
    expect(alpha?.data.model).toBe("gpt-4o");
    // Both agents contributed in the mock → terminal status, confidence set.
    expect(alpha?.data.status).toBe("contributed");
    expect(alpha?.data.confidence).toBeCloseTo(0.82);
  });

  it("renders no nodes before any run_start (empty/idle state)", () => {
    const { nodes } = buildGraphModel(initialRunState(), labels);
    expect(nodes).toHaveLength(0);
  });

  it("never emits an orchestrator dispatch edge (no master, no hierarchy)", () => {
    const run = reduceEvents([
      mk("run_start", 1, { goal: "g", roster: ["a", "b"] }),
      mk("round_start", 2, { round: 1 }),
    ]);
    const { nodes, edges } = buildGraphModel(run);
    // No hub node, and no dispatch edges of any kind.
    expect(nodes.map((n) => n.id).sort()).toEqual(["a", "b"]);
    expect(edges.some((e) => (e.data as AgentEdgeData).kind === ("dispatch" as string))).toBe(
      false,
    );
  });

  it("falls back to a short id when no agent record is joined", () => {
    const run = reduceEvents(buildMockStream());
    const { nodes } = buildGraphModel(run); // no labels
    const alpha = nodes.find((n) => n.id === MOCK_IDS.agentA);
    // "agent-alpha" is 11 chars (> 8) → truncated to first 8 chars + ellipsis.
    expect(alpha?.data.label).toBe(`${MOCK_IDS.agentA.slice(0, 8)}…`);
    expect(alpha?.data.label).toMatch(/…$/);
  });

  it("emits a faint static mesh edge between the two agents", () => {
    const run = reduceEvents(buildMockStream());
    const { edges } = buildGraphModel(run, labels);
    const staticEdges = edges.filter((e) => (e.data as AgentEdgeData).kind === "static");
    expect(staticEdges).toHaveLength(1); // one pair → one undirected mesh edge
    expect(staticEdges[0]?.selectable).toBe(false);
  });

  it("derives bright critique edges only from the CURRENT round while RUNNING, sender→target", () => {
    // A run mid-debate (status 'running', round 1) with A→B (minor) and B→A (major).
    const run = reduceEvents([
      mk("run_start", 1, { goal: "g", roster: ["a", "b"] }),
      mk("round_start", 2, { round: 1 }),
      mk("critique", 3, { sender: "a", target: "b", round: 1, severity: "minor", content: "x" }),
      mk("critique", 4, { sender: "b", target: "a", round: 1, severity: "major", content: "y" }),
    ]);
    expect(run.status).toBe("running");
    const { edges } = buildGraphModel(run);
    const critEdges = edges.filter((e) => (e.data as AgentEdgeData).kind === "critique");
    expect(critEdges).toHaveLength(2);
    const ab = critEdges.find((e) => e.source === "a" && e.target === "b");
    const ba = critEdges.find((e) => e.source === "b" && e.target === "a");
    expect(ab?.animated).toBe(true);
    expect(ab?.markerEnd).toBe("arrowclosed");
    expect((ba?.data as AgentEdgeData).severity).toBe("major");
  });

  it("clears the animated mesh once communication is done (Bug 5 — run finished)", () => {
    // The mock stream ends in run_finished → status 'finished' → the discussion is
    // over, so the glowing edges drop and only the faint static mesh remains.
    const run = reduceEvents(buildMockStream());
    expect(run.status).toBe("finished");
    const { edges } = buildGraphModel(run, labels);
    expect(edges.filter((e) => (e.data as AgentEdgeData).active)).toHaveLength(0);
    expect(edges.every((e) => (e.data as AgentEdgeData).kind === "static")).toBe(true);
  });

  it("drops critique edges from earlier rounds once the round advances", () => {
    // Synthesize a 2-round run: a round-1 critique, then round_start(2).
    const events: AnyAGUIEvent[] = [
      mk("run_start", 1, { goal: "g", roster: ["a", "b"] }),
      mk("round_start", 2, { round: 1 }),
      mk("critique", 3, { sender: "a", target: "b", round: 1, severity: "minor", content: "x" }),
      mk("round_start", 4, { round: 2 }),
    ];
    const run = reduceEvents(events);
    const { edges } = buildGraphModel(run);
    const critEdges = edges.filter((e) => (e.data as AgentEdgeData).kind === "critique");
    expect(critEdges).toHaveLength(0); // the round-1 critique is no longer "current"
  });

  it("builds an accent reply edge responder→author for a current-round responds_to", () => {
    // Round 2: B contributes building on A's round-1 work → reply edge B→A.
    const run = reduceEvents([
      mk("run_start", 1, { goal: "g", roster: ["a", "b"] }),
      mk("round_start", 2, { round: 1 }),
      mk("contribution", 3, { agent_id: "a", round: 1, confidence: 0.7, content_blocks: [] }),
      mk("round_start", 4, { round: 2 }),
      mk("contribution", 5, {
        agent_id: "b",
        round: 2,
        confidence: 0.8,
        content_blocks: [],
        responds_to: ["a"],
      }),
    ]);
    const { edges } = buildGraphModel(run);
    const reply = edges.filter((e) => (e.data as AgentEdgeData).kind === "reply");
    expect(reply).toHaveLength(1);
    expect(reply[0]?.source).toBe("b");
    expect(reply[0]?.target).toBe("a");
    expect(reply[0]?.animated).toBe(true);
    expect(reply[0]?.markerEnd).toBe("arrowclosed");
  });

  it("drops reply edges from earlier rounds once the round advances", () => {
    const run = reduceEvents([
      mk("run_start", 1, { goal: "g", roster: ["a", "b"] }),
      mk("round_start", 2, { round: 1 }),
      mk("contribution", 3, {
        agent_id: "b",
        round: 1,
        confidence: 0.8,
        content_blocks: [],
        responds_to: ["a"],
      }),
      mk("round_start", 4, { round: 2 }),
    ]);
    const { edges } = buildGraphModel(run);
    const reply = edges.filter((e) => (e.data as AgentEdgeData).kind === "reply");
    expect(reply).toHaveLength(0); // the round-1 reply is no longer "current"
  });

  it("drops self-referential and non-roster responds_to targets (R5 boundary re-filter)", () => {
    const run = reduceEvents([
      mk("run_start", 1, { goal: "g", roster: ["a", "b"] }),
      mk("round_start", 2, { round: 1 }),
      mk("contribution", 3, {
        agent_id: "a",
        round: 1,
        confidence: 0.7,
        content_blocks: [],
        responds_to: ["a", "ghost"], // self + a non-roster id → both dropped
      }),
    ]);
    const { edges } = buildGraphModel(run);
    const reply = edges.filter((e) => (e.data as AgentEdgeData).kind === "reply");
    expect(reply).toHaveLength(0);
  });

  it("marks an agent node as error and surfaces the failure reason", () => {
    const events: AnyAGUIEvent[] = [
      mk("run_start", 1, { goal: "g", roster: ["a", "b"] }),
      mk("round_start", 2, { round: 1 }),
      mk("error", 3, {
        scope: "agent_turn",
        agent_id: "a",
        round: 1,
        message: "PaymentRequiredResponseError: more credits required",
      }),
    ];
    const run = reduceEvents(events);
    const { nodes } = buildGraphModel(run);
    const a = nodes.find((n) => n.id === "a");
    expect(a?.data.status).toBe("error");
    // The reason is carried to the node so the viewer sees *why* it failed.
    expect(a?.data.errorMessage).toContain("PaymentRequired");
    // A peer that didn't fail is unaffected.
    expect(nodes.find((n) => n.id === "b")?.data.errorMessage).toBeNull();
  });

  it("marks a not_tool_capable abstention as 'abstained' (fixable), not a hard error", () => {
    // Slice 2: a per-agent abstention whose backend `reason` is `not_tool_capable`
    // (the §9.3 gate) reads as an amber "No Tools" warning the user can fix — distinct
    // from a transient red error. A different reason / no reason stays "error".
    const events: AnyAGUIEvent[] = [
      mk("run_start", 1, { goal: "g", roster: ["cap", "notool"] }),
      mk("round_start", 2, { round: 1 }),
      mk("error", 3, {
        scope: "agent_turn",
        agent_id: "notool",
        round: 1,
        message: "Model 'nemotron' does not support tool calling; mesh agents require…",
        reason: "not_tool_capable",
      }),
    ];
    const run = reduceEvents(events);
    const { nodes } = buildGraphModel(run);
    const notool = nodes.find((n) => n.id === "notool");
    expect(notool?.data.status).toBe("abstained");
    expect(notool?.data.hasError).toBe(true);
    expect(notool?.data.errorMessage).toContain("does not support tool calling");
  });

  it("settles still-'thinking' nodes to idle once the run reaches a terminal state", () => {
    // Regression (orphaned-run recovery, ARCH §24.8): a run interrupted by a
    // backend restart is finalized server-side with a terminal run-scoped `error`.
    // Agents left mid-turn must stop pulsing "thinking" — the work is over.
    const run = reduceEvents([
      mk("run_start", 1, { goal: "g", roster: ["a", "b"] }),
      mk("round_start", 2, { round: 1 }),
      mk("agent_turn_start", 3, { agent_id: "a", round: 1 }),
      mk("agent_turn_start", 4, { agent_id: "b", round: 1 }),
      // Terminal run-scoped error (no agent_id) — the recovery's finalization event.
      mk("error", 5, { scope: "run", message: "Run interrupted: backend restarted." }),
    ]);
    expect(run.status).toBe("error");
    const { nodes } = buildGraphModel(run);
    // Both agents were "thinking" when the run ended → settled to "idle", not frozen.
    expect(nodes.find((n) => n.id === "a")?.data.status).toBe("idle");
    expect(nodes.find((n) => n.id === "b")?.data.status).toBe("idle");
  });
});

describe("buildDebateTimeline — contributions + critiques in reading order", () => {
  it("orders by round, contributions before the critiques that respond", () => {
    const run = reduceEvents(buildMockStream());
    const items = buildDebateTimeline(run);
    // Mock: 2 contributions + 2 critiques, all round 1.
    expect(items).toHaveLength(4);
    expect(items.every((i) => i.round === 1)).toBe(true);
    // Stable order: both contributions precede both critiques within the round.
    const kinds = items.map((i) => i.kind);
    expect(kinds.slice(0, 2)).toEqual(["contribution", "contribution"]);
    expect(kinds.slice(2)).toEqual(["critique", "critique"]);
  });
});

describe("buildConsensusModel — header read-out", () => {
  it("reads mean confidence, convergence and ranking off the run", () => {
    const run = reduceEvents(buildMockStream());
    const model = buildConsensusModel(run);
    expect(model.meanConfidence).toBeCloseTo(0.86);
    expect(model.converged).toBe(true);
    expect(model.ranking[0]).toBe(`${MOCK_IDS.agentB}:1`);
  });

  it("is null-safe before any consensus_update", () => {
    const run = applyEvent(initialRunState(), mk("run_start", 1, { goal: "g", roster: ["a"] }));
    expect(buildConsensusModel(run).meanConfidence).toBeNull();
  });
});

describe("layoutPositions — stable circular layout", () => {
  it("places a single node and is deterministic across calls", () => {
    expect(layoutPositions(["solo"])).toEqual(layoutPositions(["solo"]));
    const two = layoutPositions(["a", "b"]);
    expect(Object.keys(two)).toEqual(["a", "b"]);
  });
});

/** Tiny typed envelope builder for synthetic events (mirrors the mock builder). */
function mk<T extends AnyAGUIEvent["type"]>(
  type: T,
  seq: number,
  data: Extract<AnyAGUIEvent, { type: T }>["data"],
): AnyAGUIEvent {
  return {
    type,
    session_id: "s",
    run_id: "r",
    seq,
    ts: new Date().toISOString(),
    data,
  } as AnyAGUIEvent;
}

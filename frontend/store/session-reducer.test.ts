/**
 * Unit tests for the pure AG-UI reducer (Slice-1 acceptance: "the session store
 * reduces a replayed mock stream into render-ready state").
 *
 * Pure-function tests: no React, no DOM, no Zustand — just `applyEvent` /
 * `reduceEvents` over the canned mock stream and targeted edge cases (seq dedup,
 * tool-result pairing, HITL lifecycle, new-run reset).
 */
import { describe, it, expect } from "vitest";
import { buildMockStream, MOCK_IDS } from "@/mocks/agui-replayer";
import {
  applyEvent,
  initialRunState,
  reduceEvents,
  upsertArtifactEntry,
  type ArtifactEntry,
  type RunState,
} from "@/store/session-reducer";
import type { AGUIEvent, AnyAGUIEvent } from "@/types/agui";

describe("session reducer — folding the mock stream", () => {
  const final = reduceEvents(buildMockStream());

  it("reaches a finished run with the synthesized artifact", () => {
    expect(final.status).toBe("finished");
    expect(final.runId).toBe(MOCK_IDS.runId);
    expect(final.sessionId).toBe(MOCK_IDS.sessionId);
    expect(final.artifact).not.toBeNull();
    expect(final.artifact?.kind).toBe("synthesis");
    expect(final.artifact?.content).toContain("sliding-window");
  });

  it("captures the goal and roster from run_start", () => {
    expect(final.goal).toBe("Design a resilient rate-limiter");
    expect(final.roster).toEqual([MOCK_IDS.agentA, MOCK_IDS.agentB]);
  });

  it("builds per-agent runtime state (status, reasoning, tools, confidence)", () => {
    const alpha = final.agents[MOCK_IDS.agentA];
    const beta = final.agents[MOCK_IDS.agentB];
    expect(alpha?.status).toBe("contributed");
    expect(alpha?.reasoning).toHaveLength(1);
    expect(alpha?.toolCalls).toHaveLength(1);
    expect(alpha?.latestConfidence).toBeCloseTo(0.82);
    expect(beta?.latestConfidence).toBeCloseTo(0.9);
  });

  it("pairs tool_result onto its open tool_call", () => {
    const alpha = final.agents[MOCK_IDS.agentA];
    expect(alpha?.toolCalls[0]?.tool).toBe("search_knowledge");
    expect(alpha?.toolCalls[0]?.result).toBe("3 docs found");
  });

  it("collects contributions and critiques", () => {
    expect(final.contributions).toHaveLength(2);
    expect(final.critiques).toHaveLength(2);
    expect(final.critiques.map((c) => c.severity)).toEqual(["minor", "major"]);
  });

  it("records consensus and the resolved HITL gate", () => {
    expect(final.consensus?.converged).toBe(true);
    expect(final.consensus?.ranking[0]).toBe(`${MOCK_IDS.agentB}:1`);
    expect(final.hitl?.status).toBe("resolved");
    expect(final.hitl?.decision).toBe("approve");
    expect(final.hitl?.source).toBe("human");
  });

  it("tracks lastSeq as the highest applied seq (the reconnect cursor)", () => {
    const stream = buildMockStream();
    expect(final.lastSeq).toBe(stream[stream.length - 1]?.seq);
  });
});

describe("session reducer — invariants", () => {
  it("does not mutate the input state (immutability)", () => {
    const start = initialRunState();
    const snapshot = JSON.stringify(start);
    const stream = buildMockStream();
    applyEvent(start, stream[0]!);
    expect(JSON.stringify(start)).toBe(snapshot);
  });

  it("dedups events whose seq was already applied (replay-then-live safety)", () => {
    const events = buildMockStream();
    const once = reduceEvents(events);
    // Re-apply the whole stream (a full replay after a reconnect at seq 0).
    const twice = events.reduce(applyEvent, once);
    expect(twice.contributions).toHaveLength(once.contributions.length);
    expect(twice.critiques).toHaveLength(once.critiques.length);
    expect(twice.lastSeq).toBe(once.lastSeq);
  });

  it("pauses the run at a pending HITL request", () => {
    const events = buildMockStream();
    const hitlIndex = events.findIndex((e) => e.type === "hitl_request");
    const upToGate = reduceEvents(events.slice(0, hitlIndex + 1));
    expect(upToGate.status).toBe("awaiting_human");
    expect(upToGate.hitl?.status).toBe("pending");
    expect(upToGate.hitl?.allowedDecisions).toEqual(["approve", "edit", "reject"]);
  });

  it("resets state when a run_start arrives for a different run_id", () => {
    const events = buildMockStream();
    const afterFirst = reduceEvents(events);
    const newRunStart: AGUIEvent<"run_start"> = {
      type: "run_start",
      session_id: MOCK_IDS.sessionId,
      run_id: "mock-run-0002",
      seq: 1,
      ts: new Date().toISOString(),
      data: { goal: "A different goal", roster: ["agent-gamma"] },
    };
    const reset = applyEvent(afterFirst, newRunStart);
    expect(reset.runId).toBe("mock-run-0002");
    expect(reset.goal).toBe("A different goal");
    expect(reset.contributions).toHaveLength(0);
    expect(reset.artifact).toBeNull();
  });
});

describe("session reducer — error semantics (§21.5 abstention vs run failure)", () => {
  const env = <T extends AnyAGUIEvent["type"]>(
    type: T,
    seq: number,
    data: Extract<AnyAGUIEvent, { type: T }>["data"],
  ): AnyAGUIEvent =>
    ({ type, session_id: "s", run_id: "r", seq, ts: new Date().toISOString(), data }) as AnyAGUIEvent;

  it("does NOT fail the whole run when a single agent errors (it abstains)", () => {
    const run = reduceEvents([
      env("run_start", 1, { goal: "g", roster: ["a", "b"] }),
      env("round_start", 2, { round: 1 }),
      env("agent_turn_start", 3, { agent_id: "a", round: 1 }),
      env("error", 4, {
        scope: "agent_turn",
        agent_id: "a",
        round: 1,
        message: "PaymentRequiredResponseError: more credits required",
      }),
    ]);
    // Run keeps going (it later reaches consensus/HITL) — not a dead "error" run.
    expect(run.status).toBe("running");
    expect(run.errors).toHaveLength(1);
    expect(run.errors[0]?.agentId).toBe("a");
    expect(run.errors[0]?.message).toContain("PaymentRequired");
  });

  it("a per-agent error does not block the run from pausing at HITL", () => {
    const run = reduceEvents([
      env("run_start", 1, { goal: "g", roster: ["a", "b"] }),
      env("error", 2, { scope: "agent_turn", agent_id: "a", round: 1, message: "boom" }),
      env("hitl_request", 3, {
        candidate: "x",
        candidate_key: "b:1",
        ranking: ["b:1"],
        converged: false,
        allowed_decisions: ["approve", "edit", "reject"],
      }),
    ]);
    expect(run.status).toBe("awaiting_human");
    expect(run.errors).toHaveLength(1);
  });

  it("DOES fail the run for a run-scoped error (no agent_id)", () => {
    const run = reduceEvents([
      env("run_start", 1, { goal: "g", roster: ["a"] }),
      env("error", 2, { scope: "graph", message: "fatal: graph crashed" }),
    ]);
    expect(run.status).toBe("error");
    expect(run.errors[0]?.agentId).toBeUndefined();
  });
});

describe("session reducer — artifact attachments (ARTIFACTS §11.1)", () => {
  const env = <T extends AnyAGUIEvent["type"]>(
    type: T,
    seq: number,
    data: Extract<AnyAGUIEvent, { type: T }>["data"],
  ): AnyAGUIEvent =>
    ({ type, session_id: "s", run_id: "r", seq, ts: new Date().toISOString(), data }) as AnyAGUIEvent;

  const attachment = (over: Partial<import("@/types/agui").ArtifactAttachment> = {}) => ({
    artifact_id: "art-1",
    kind: "code" as const,
    filename: "main.py",
    mime_type: "text/x-python",
    version: 1,
    status: "ready" as const,
    preview: "print('hi')",
    download_url: "/artifacts/art-1/download?token=t",
    size_bytes: 11,
    ...over,
  });

  it("folds a producer tool_result attachment into `artifacts`", () => {
    const run = reduceEvents([
      env("run_start", 1, { goal: "g", roster: ["a"] }),
      env("tool_result", 2, {
        agent_id: "synthesizer",
        round: 0,
        tool: "write_code_file",
        result: "created main.py",
        attachment: attachment(),
        producer_agent_id: null,
      }),
    ]);
    expect(run.artifacts).toHaveLength(1);
    expect(run.artifacts[0]?.filename).toBe("main.py");
    expect(run.artifacts[0]?.kind).toBe("code");
    expect(run.artifacts[0]?.downloadUrl).toContain("token=");
  });

  it("does NOT create a phantom agent node for a producer tool_result", () => {
    const run = reduceEvents([
      env("run_start", 1, { goal: "g", roster: ["a"] }),
      env("tool_result", 2, {
        agent_id: "synthesizer",
        round: 0,
        tool: "write_code_file",
        result: "created main.py",
        attachment: attachment(),
        producer_agent_id: null,
      }),
    ]);
    expect(run.agents.synthesizer).toBeUndefined();
  });

  it("upserts the same artifact (generating → ready) without duplicating the card", () => {
    const run = reduceEvents([
      env("run_start", 1, { goal: "g", roster: ["a"] }),
      env("tool_result", 2, {
        agent_id: "synthesizer",
        round: 0,
        tool: "write_code_file",
        result: "generating",
        attachment: attachment({ status: "generating", size_bytes: null, preview: null }),
      }),
      env("tool_result", 3, {
        agent_id: "synthesizer",
        round: 0,
        tool: "write_code_file",
        result: "created main.py",
        attachment: attachment({ status: "ready" }),
      }),
    ]);
    expect(run.artifacts).toHaveLength(1);
    expect(run.artifacts[0]?.status).toBe("ready");
    expect(run.artifacts[0]?.sizeBytes).toBe(11);
  });

  it("upsertArtifactEntry appends a new artifact and replaces by id (iterate path)", () => {
    const v1: ArtifactEntry = {
      artifactId: "a",
      kind: "code",
      filename: "main.py",
      mimeType: "text/x-python",
      version: 1,
      status: "ready",
      preview: "print(1)",
      downloadUrl: "/artifacts/a/download?token=t",
      sizeBytes: 8,
      producerAgentId: null,
    };
    const afterCreate = upsertArtifactEntry([], v1);
    expect(afterCreate).toHaveLength(1);
    // Iterate → v2 replaces the same id in place (no duplicate card).
    const afterIterate = upsertArtifactEntry(afterCreate, { ...v1, version: 2, preview: "print(2)" });
    expect(afterIterate).toHaveLength(1);
    expect(afterIterate[0]?.version).toBe(2);
    expect(afterIterate[0]?.preview).toBe("print(2)");
  });

  it("leaves a mesh-agent tool_result (no attachment) out of `artifacts`", () => {
    const run = reduceEvents([
      env("run_start", 1, { goal: "g", roster: ["a"] }),
      env("agent_turn_start", 2, { agent_id: "a", round: 1 }),
      env("tool_call", 3, { agent_id: "a", round: 1, tool: "search_knowledge", args: {} }),
      env("tool_result", 4, {
        agent_id: "a",
        round: 1,
        tool: "search_knowledge",
        result: "3 docs",
      }),
    ]);
    expect(run.artifacts).toHaveLength(0);
    expect(run.agents.a?.toolCalls[0]?.result).toBe("3 docs");
  });
});

// Type-level sanity: RunState is the exported render contract for Slice 2 panels.
export type _RunStateContract = RunState;

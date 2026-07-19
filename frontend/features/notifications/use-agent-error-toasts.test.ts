/**
 * Unit tests for the pure error→toast mapping (`toErrorAlert`). The React hook
 * itself is thin view glue over `emitAlert`; the testable logic — how a run
 * error becomes a toast detail — is isolated here so it runs in the node env
 * (no jsdom/RTL, matching the project's vitest setup, R2).
 */
import { describe, it, expect } from "vitest";
import { toErrorAlert } from "@/features/notifications/use-agent-error-toasts";
import type { RunErrorEntry } from "@/store/session-reducer";
import type { AgentLabel } from "@/components/agent-graph/graph-model";

const labels: Record<string, AgentLabel> = {
  "73069a2f-5299-4e09-be89-bf1a462f2631": {
    id: "73069a2f-5299-4e09-be89-bf1a462f2631",
    name: "Security Engineer",
  },
};

describe("toErrorAlert — run error → notification toast detail", () => {
  it("names the agent from the joined label; a reasonless failure is status 'error'", () => {
    const err: RunErrorEntry = {
      scope: "agent_turn",
      agentId: "73069a2f-5299-4e09-be89-bf1a462f2631",
      round: 1,
      message: "PaymentRequiredResponseError: more credits required",
    };
    expect(toErrorAlert(err, labels)).toEqual({
      agent: "Security Engineer",
      action: "PaymentRequiredResponseError: more credits required",
      status: "error",
    });
  });

  it("falls back to a truncated short id when no label is joined", () => {
    const err: RunErrorEntry = {
      scope: "agent_turn",
      agentId: "73069a2f-5299-4e09-be89-bf1a462f2631",
      round: 1,
      message: "RemoteProtocolError: Server disconnected",
    };
    const alert = toErrorAlert(err); // no labels
    expect(alert.agent).toBe("73069a2f…");
    expect(alert.status).toBe("error");
  });

  it("maps a not_tool_capable abstention to an amber 'warning', not a red error", () => {
    const err: RunErrorEntry = {
      scope: "agent_turn",
      agentId: "73069a2f-5299-4e09-be89-bf1a462f2631",
      round: 1,
      message: "Model 'nemotron' does not support tool calling; mesh agents require…",
      reason: "not_tool_capable",
    };
    expect(toErrorAlert(err, labels)).toEqual({
      agent: "Security Engineer",
      action: "Model 'nemotron' does not support tool calling; mesh agents require…",
      status: "warning",
    });
  });

  it("attributes a run-scoped error (no agent_id) to 'Run'", () => {
    const err: RunErrorEntry = { scope: "graph", message: "fatal: graph crashed" };
    expect(toErrorAlert(err)).toEqual({
      agent: "Run",
      action: "fatal: graph crashed",
      status: "error",
    });
  });
});

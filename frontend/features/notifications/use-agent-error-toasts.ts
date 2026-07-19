"use client";

/**
 * Live failure toasts — bridges the run's `errors` channel to the global
 * notification bus (`features/notifications/use-notifications`) so an agent
 * dropping out raises a visible alert instead of silently going "error" on its
 * node. This is deliberately VIEW GLUE: the reducer/store stay pure (no side
 * effects), and this hook is the only place that turns a folded `error` event
 * into a `nexagi-new-alert` toast via the decoupled `emitAlert` window seam.
 *
 * Why a cursor (not "toast on every render"): `run.errors` is append-only within
 * a run, so we remember how many we've already toasted and only fire for the
 * freshly-appended tail. The cursor resets when `runId` changes, so a relaunch
 * starts clean. During a History REPLAY the caller disables toasts (the whole
 * past run's errors would otherwise burst in at once) — the per-node reason
 * (graph-model `errorMessage`) still shows on replay.
 */
import { useEffect, useRef } from "react";
import { useSessionStore } from "@/store/session-store";
import {
  emitAlert,
  type AlertStatus,
  type NewAlertDetail,
} from "@/features/notifications/use-notifications";
import type { AgentLabel } from "@/components/agent-graph/graph-model";
import type { RunErrorEntry } from "@/store/session-reducer";

/** Short, stable fallback when no agent record is joined (mirrors graph-model). */
function shortId(id: string): string {
  return id.length <= 8 ? id : `${id.slice(0, 8)}…`;
}

/**
 * Map one run error entry to a toast detail (pure — unit-tested without React).
 *
 * Agent-scoped errors are labelled with the joined agent name (falling back to a
 * short id); run-scoped errors (no `agentId`) are attributed to "Run". The
 * message becomes the toast body verbatim — it already carries the typed reason
 * (e.g. `PaymentRequiredResponseError: ...`) from the backend.
 *
 * A `not_tool_capable` abstention (§9.3) is a *fixable config* condition, so it raises
 * an amber `warning` rather than a red `error` — consistent with the node's "No Tools"
 * badge. Any other / unknown reason stays a hard `error`.
 */
export function toErrorAlert(
  err: RunErrorEntry,
  labels: Record<string, AgentLabel> = {},
): NewAlertDetail {
  const agent = err.agentId ? (labels[err.agentId]?.name ?? shortId(err.agentId)) : "Run";
  const status: AlertStatus = err.reason === "not_tool_capable" ? "warning" : "error";
  return { agent, action: err.message, status };
}

/**
 * Emit a notification toast for each newly-appended run error.
 *
 * @param labels  id → {name,model} so toasts name the agent, not a raw id.
 * @param enabled when false, the cursor still advances (so re-enabling won't
 *   dump a backlog) but no toasts fire — used to silence History replays.
 */
export function useAgentErrorToasts(
  labels: Record<string, AgentLabel> = {},
  enabled = true,
): void {
  const errors = useSessionStore((s) => s.run.errors);
  const runId = useSessionStore((s) => s.run.runId);
  const seenRef = useRef(0);
  const runIdRef = useRef<string | null>(null);

  useEffect(() => {
    // New run (or reset) → restart the cursor so we don't re-toast prior errors.
    if (runId !== runIdRef.current) {
      runIdRef.current = runId;
      seenRef.current = 0;
    }
    // Nothing new (or the array shrank on reset) → just resync the cursor.
    if (errors.length <= seenRef.current) {
      seenRef.current = errors.length;
      return;
    }
    const fresh = errors.slice(seenRef.current);
    seenRef.current = errors.length;
    if (!enabled) return; // cursor kept in sync above; suppress the toasts only
    for (const err of fresh) emitAlert(toErrorAlert(err, labels));
  }, [errors, runId, labels, enabled]);
}

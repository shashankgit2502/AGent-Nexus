"use client";

/**
 * History REST hooks (React Query — REST DTOs).
 *
 *  - `useSessions`: the org-scoped session list (`GET /sessions`, Slice-0 read).
 *  - `useSessionRuns`: a session's runs, newest first (`GET /sessions/{id}/runs`).
 *  - `useArtifact`: a run's synthesized artifact (`GET /runs/{id}/artifact`).
 *
 * A session carries no run id of its own, so History fetches its runs, picks the
 * terminal one, and reads that run's artifact. The runs endpoint closes the gap
 * flagged in Slice 4 (added as a thin org-scoped read, no locked-decision drift).
 */
import { useQuery } from "@tanstack/react-query";
import { sessionsApi } from "@/lib/api/sessions";

// Pure run-selection helpers live in `history-model` (testable without React).
export { terminalRun, hasArtifact } from "@/features/history/history-model";

export function useSessions() {
  return useQuery({ queryKey: ["sessions"], queryFn: () => sessionsApi.list() });
}

export function useSessionRuns(sessionId: string | null) {
  return useQuery({
    queryKey: ["session-runs", sessionId],
    queryFn: () => sessionsApi.listRuns(sessionId as string),
    enabled: Boolean(sessionId),
  });
}

export function useArtifact(runId: string | null) {
  return useQuery({
    queryKey: ["artifact", runId],
    queryFn: () => sessionsApi.artifact(runId as string),
    enabled: Boolean(runId),
  });
}

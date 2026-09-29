"use client";

/**
 * REST hooks for the Workspace (React Query — the locked home for DTO calls).
 *
 *  - `useTeams` / `useTeamAgents`: read teams and a team's agents (the agents
 *    are joined to roster ids to label the graph nodes, §5.2).
 *  - `useLaunchRun`: create a session then launch a run in one mutation; returns
 *    the session + the launch response (stream_url, run id, interrupted flag).
 *  - `useResumeRun`: resolve the HITL gate (approve/edit/reject) → POST /resume.
 *
 * Streaming is deliberately absent here — it lives in `useSessionStream`.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { teamsApi } from "@/lib/api/teams";
import { agentsApi } from "@/lib/api/agents";
import { sessionsApi } from "@/lib/api/sessions";
import type {
  AgentRead,
  RunLaunch,
  RunLaunchResponse,
  RunRead,
  SessionRead,
  ResumeRequest,
} from "@/types/api";
import type { AgentLabel } from "@/components/agent-graph/graph-model";

export function useTeams() {
  return useQuery({ queryKey: ["teams"], queryFn: () => teamsApi.list() });
}

/** One session by id — used to resolve a deep-linked run's team (roster labels). */
export function useSession(sessionId: string | null) {
  return useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => sessionsApi.get(sessionId as string),
    enabled: Boolean(sessionId),
  });
}

export function useTeamAgents(teamId: string | null) {
  return useQuery({
    queryKey: ["team-agents", teamId],
    queryFn: () => agentsApi.listForTeam(teamId as string),
    enabled: Boolean(teamId),
  });
}

/** Map a team's agents into the id→{name, model} labels the graph nodes need. */
export function toAgentLabels(agents: AgentRead[] | undefined): Record<string, AgentLabel> {
  const labels: Record<string, AgentLabel> = {};
  for (const a of agents ?? []) {
    // override_model_id (or profile default) is resolved server-side; we only
    // have ids here, so the model column shows the override id when present.
    labels[a.id] = { id: a.id, name: a.name, model: a.override_model_id ?? null };
  }
  return labels;
}

export interface LaunchVars {
  teamId: string;
  payload: RunLaunch;
}
export interface LaunchResult {
  session: SessionRead;
  launch: RunLaunchResponse;
}

export function useLaunchRun() {
  return useMutation<LaunchResult, Error, LaunchVars>({
    mutationFn: async ({ teamId, payload }) => {
      const session = await sessionsApi.create(teamId);
      const launch = await sessionsApi.run(session.id, payload);
      return { session, launch };
    },
  });
}

export interface ResumeVars {
  sessionId: string;
  payload: ResumeRequest;
}

export function useResumeRun() {
  return useMutation<RunLaunchResponse, Error, ResumeVars>({
    mutationFn: ({ sessionId, payload }) => sessionsApi.resume(sessionId, payload),
  });
}

/**
 * Stop a run (ARCH §21.6).
 *
 * Deliberately fire-and-observe: the terminal `run_finished` arrives on the SAME open
 * WebSocket, so the UI settles from the event stream rather than from this response. That
 * keeps one source of truth for run state and means a cancel issued from another tab (or
 * another operator) lands identically.
 */
export function useCancelRun() {
  return useMutation<RunRead, Error, string>({
    mutationFn: (runId) => sessionsApi.cancel(runId),
  });
}

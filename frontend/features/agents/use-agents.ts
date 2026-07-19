"use client";

/**
 * Agents REST hooks (React Query — REST DTOs). `useTeamAgents` (roster read) was
 * first defined for the Workspace graph; re-exported here for a single import
 * surface. Mutations invalidate `["team-agents", teamId]` so the roster refreshes.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { agentsApi } from "@/lib/api/agents";
import { useTeamAgents } from "@/features/sessions/use-run-controls";
import type { AgentCreate, AgentUpdate, AgentRead } from "@/types/api";

export { useTeamAgents };

function teamAgentsKey(teamId: string) {
  return ["team-agents", teamId] as const;
}

export interface CreateAgentVars {
  teamId: string;
  payload: AgentCreate;
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation<AgentRead, Error, CreateAgentVars>({
    mutationFn: ({ teamId, payload }) => agentsApi.create(teamId, payload),
    onSuccess: (_data, { teamId }) =>
      qc.invalidateQueries({ queryKey: teamAgentsKey(teamId) }),
  });
}

export interface UpdateAgentVars {
  teamId: string;
  agentId: string;
  payload: AgentUpdate;
}

export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation<AgentRead, Error, UpdateAgentVars>({
    mutationFn: ({ agentId, payload }) => agentsApi.update(agentId, payload),
    onSuccess: (_data, { teamId }) =>
      qc.invalidateQueries({ queryKey: teamAgentsKey(teamId) }),
  });
}

export interface DeleteAgentVars {
  teamId: string;
  agentId: string;
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation<void, Error, DeleteAgentVars>({
    mutationFn: ({ agentId }) => agentsApi.remove(agentId),
    onSuccess: (_data, { teamId }) =>
      qc.invalidateQueries({ queryKey: teamAgentsKey(teamId) }),
  });
}

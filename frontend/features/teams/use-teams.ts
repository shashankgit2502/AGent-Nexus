"use client";

/**
 * Teams REST hooks (React Query — REST DTOs). `useTeams` (the org team list) was
 * first defined for the Workspace; we re-export it here so the Teams screen has a
 * single import surface, and add create + per-team session reads. The query key
 * `["teams"]` is shared so a create invalidates every consumer (Workspace picker,
 * Chat dialog, Teams list).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { teamsApi } from "@/lib/api/teams";
import { useTeams } from "@/features/sessions/use-run-controls";
import type { TeamCreate, TeamRead, TeamUpdate } from "@/types/api";

export { useTeams };

export const TEAMS_KEY = ["teams"] as const;

export function useCreateTeam() {
  const qc = useQueryClient();
  return useMutation<TeamRead, Error, TeamCreate>({
    mutationFn: (payload) => teamsApi.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEAMS_KEY }),
  });
}

export interface UpdateTeamVars {
  teamId: string;
  payload: TeamUpdate;
}

export function useUpdateTeam() {
  const qc = useQueryClient();
  return useMutation<TeamRead, Error, UpdateTeamVars>({
    mutationFn: ({ teamId, payload }) => teamsApi.update(teamId, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEAMS_KEY }),
  });
}

export function useDeleteTeam() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (teamId) => teamsApi.remove(teamId),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEAMS_KEY }),
  });
}

/** A team's sessions (used by History deep-links / team detail). */
export function useTeamSessions(teamId: string | null) {
  return useQuery({
    queryKey: ["team-sessions", teamId],
    queryFn: () => teamsApi.listSessions(teamId as string),
    enabled: Boolean(teamId),
  });
}

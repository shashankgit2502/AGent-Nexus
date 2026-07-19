"use client";

/**
 * Knowledge REST hooks (React Query). Sources are team-scoped
 * (`GET|POST /teams/{id}/knowledge`). Ingestion runs on an async worker (ITEM 2):
 * a source starts `pending`, moves through `ingesting`, and ends `ready`/`failed`.
 * The list query **polls** while any source is non-terminal so the UI reflects
 * live status + chunk_count without a manual refresh.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { knowledgeApi } from "@/lib/api/knowledge";
import { teamsApi } from "@/lib/api/teams";
import type {
  KnowledgeSourceCreate,
  KnowledgeSourceRead,
  TeamRead,
  UUID,
} from "@/types/api";

function knowledgeKey(teamId: string) {
  return ["knowledge", teamId] as const;
}

const TERMINAL = new Set(["ready", "failed"]);

export function useKnowledge(teamId: string | null) {
  return useQuery({
    queryKey: ["knowledge", teamId],
    queryFn: () => knowledgeApi.list(teamId as string),
    enabled: Boolean(teamId),
    // Poll while any source is still ingesting; stop once all are terminal.
    refetchInterval: (query) => {
      const data = query.state.data as KnowledgeSourceRead[] | undefined;
      if (!data || data.length === 0) return false;
      return data.some((s) => !TERMINAL.has(s.status)) ? 1500 : false;
    },
  });
}

export interface RegisterSourceVars {
  teamId: string;
  payload: KnowledgeSourceCreate;
}

export function useRegisterSource() {
  const qc = useQueryClient();
  return useMutation<KnowledgeSourceRead, Error, RegisterSourceVars>({
    mutationFn: ({ teamId, payload }) => knowledgeApi.create(teamId, payload),
    onSuccess: (_data, { teamId }) => qc.invalidateQueries({ queryKey: knowledgeKey(teamId) }),
  });
}

export interface UploadFileVars {
  teamId: string;
  file: File;
  agentId?: string | null;
  displayName?: string | null;
}

export function useUploadKnowledgeFile() {
  const qc = useQueryClient();
  return useMutation<KnowledgeSourceRead, Error, UploadFileVars>({
    mutationFn: ({ teamId, file, agentId, displayName }) =>
      knowledgeApi.upload(teamId, file, { agentId, displayName }),
    onSuccess: (_data, { teamId }) => qc.invalidateQueries({ queryKey: knowledgeKey(teamId) }),
  });
}

export function useDeleteKnowledgeSource() {
  const qc = useQueryClient();
  return useMutation<void, Error, { teamId: string; sourceId: UUID }>({
    mutationFn: ({ teamId, sourceId }) => knowledgeApi.remove(teamId, sourceId),
    onSuccess: (_data, { teamId }) => qc.invalidateQueries({ queryKey: knowledgeKey(teamId) }),
  });
}

/** Read one team (for its current embedding_model_id). */
export function useTeam(teamId: string | null) {
  return useQuery({
    queryKey: ["team", teamId],
    queryFn: () => teamsApi.get(teamId as string),
    enabled: Boolean(teamId),
  });
}

/** Set a team's runtime embedding model (ARCH §9.5). Refreshes the team + its sources. */
export function useSetTeamEmbeddingModel() {
  const qc = useQueryClient();
  return useMutation<TeamRead, Error, { teamId: string; embeddingModelId: UUID | null }>({
    mutationFn: ({ teamId, embeddingModelId }) =>
      teamsApi.update(teamId, { embedding_model_id: embeddingModelId }),
    onSuccess: (_data, { teamId }) => {
      qc.invalidateQueries({ queryKey: ["team", teamId] });
      qc.invalidateQueries({ queryKey: knowledgeKey(teamId) });
    },
  });
}

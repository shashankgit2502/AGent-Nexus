"use client";

/**
 * Memory Explorer REST hooks (React Query).
 *
 * Two reads — the structured per-item records (`GET /agents/{id}/memories`, the §14
 * source of truth) and the rendered recall view (`GET /agents/{id}/memory`, used for
 * the read-only team-shared layer) — plus pin/delete mutations that invalidate the
 * agent's record list so the UI reflects the change immediately.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { memoryApi } from "@/lib/api/memory";
import type { MemoryItemRead, MemoryListParams, UUID } from "@/types/api";

function memoriesKey(agentId: string, params: MemoryListParams) {
  return ["agent-memories", agentId, params] as const;
}

/** List an agent's structured memory records (filtered/searched/paginated). */
export function useAgentMemories(agentId: string | null, params: MemoryListParams = {}) {
  return useQuery({
    queryKey: ["agent-memories", agentId, params],
    queryFn: () => memoryApi.list(agentId as string, params),
    enabled: Boolean(agentId),
  });
}

/** The rendered recall view — used here for the read-only team-shared layer. */
export function useAgentRecall(agentId: string | null) {
  return useQuery({
    queryKey: ["agent-memory", agentId],
    queryFn: () => memoryApi.recall(agentId as string),
    enabled: Boolean(agentId),
  });
}

/** Invalidate every list query for an agent (any filter combination). */
function useInvalidateAgent() {
  const qc = useQueryClient();
  return (agentId: string) =>
    qc.invalidateQueries({
      predicate: (q) =>
        q.queryKey[0] === "agent-memories" && q.queryKey[1] === agentId,
    });
}

export function usePinMemory() {
  const invalidate = useInvalidateAgent();
  return useMutation<MemoryItemRead, Error, { agentId: string; itemId: UUID; pinned: boolean }>({
    mutationFn: ({ agentId, itemId, pinned }) => memoryApi.pin(agentId, itemId, pinned),
    onSuccess: (_data, { agentId }) => invalidate(agentId),
  });
}

export function useDeleteMemory() {
  const invalidate = useInvalidateAgent();
  return useMutation<void, Error, { agentId: string; itemId: UUID }>({
    mutationFn: ({ agentId, itemId }) => memoryApi.remove(agentId, itemId),
    onSuccess: (_data, { agentId }) => invalidate(agentId),
  });
}

// `memoriesKey` is exported for callers that need the exact key (kept colocated
// with the query above so the shape stays in one place).
export { memoriesKey };

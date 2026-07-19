/** Memory Explorer records (ARCH §14/§25.1; backend `api/memory.py`). */
import { apiFetch } from "@/lib/api/client";
import type {
  AgentMemoryRead,
  MemoryItemRead,
  MemoryListParams,
  MemoryPage,
  UUID,
} from "@/types/api";

export const memoryApi = {
  /** Rendered recall view: private /memories/AGENTS.md rollup + read-only shared layer. */
  recall: (agentId: string) => apiFetch<AgentMemoryRead>(`/agents/${agentId}/memory`),
  /** List structured records — filter by kind, substring search (q), pinned; paginated. */
  list: (agentId: string, params: MemoryListParams = {}) =>
    apiFetch<MemoryPage>(`/agents/${agentId}/memories`, {
      query: {
        kind: params.kind,
        q: params.q,
        pinned: params.pinned,
        limit: params.limit,
        offset: params.offset,
      },
    }),
  /** Delete one record. */
  remove: (agentId: string, itemId: UUID) =>
    apiFetch<void>(`/agents/${agentId}/memories/${itemId}`, { method: "DELETE" }),
  /** Pin or unpin a record → the updated record. */
  pin: (agentId: string, itemId: UUID, pinned: boolean) =>
    apiFetch<MemoryItemRead>(`/agents/${agentId}/memories/${itemId}`, {
      method: "PATCH",
      body: { pinned },
    }),
};

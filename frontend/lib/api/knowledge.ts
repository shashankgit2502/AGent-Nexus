/** Knowledge sources per team (ARCH §14/§10.5; backend `api/knowledge.py`). */
import { apiFetch, apiUpload } from "@/lib/api/client";
import type { KnowledgeSourceCreate, KnowledgeSourceRead, UUID } from "@/types/api";

export const knowledgeApi = {
  list: (teamId: string) => apiFetch<KnowledgeSourceRead[]>(`/teams/${teamId}/knowledge`),
  /** Register a by-reference source (url/db/team_doc); ingestion is spawned server-side. */
  create: (teamId: string, payload: KnowledgeSourceCreate) =>
    apiFetch<KnowledgeSourceRead>(`/teams/${teamId}/knowledge`, {
      method: "POST",
      body: payload,
    }),
  /** Upload a real file (multipart); the worker routes by format + embeds (ITEM 2). */
  upload: (
    teamId: string,
    file: File,
    opts: { agentId?: string | null; displayName?: string | null } = {},
  ) => {
    const form = new FormData();
    form.append("file", file);
    if (opts.agentId) form.append("agent_id", opts.agentId);
    if (opts.displayName) form.append("display_name", opts.displayName);
    return apiUpload<KnowledgeSourceRead>(`/teams/${teamId}/knowledge/upload`, form);
  },
  /** Delete a source AND its vector chunks (no stale RAG). */
  remove: (teamId: string, sourceId: UUID) =>
    apiFetch<void>(`/teams/${teamId}/knowledge/${sourceId}`, { method: "DELETE" }),
};

/** Agents CRUD + memory (ARCH §14/§22; backend `api/agents.py`, `api/memory.py`). */
import { apiFetch } from "@/lib/api/client";
import type {
  AgentCreate,
  AgentUpdate,
  AgentRead,
  AgentMemoryRead,
} from "@/types/api";

export const agentsApi = {
  listForTeam: (teamId: string) =>
    apiFetch<AgentRead[]>(`/teams/${teamId}/agents`),
  get: (agentId: string) => apiFetch<AgentRead>(`/agents/${agentId}`),
  create: (teamId: string, payload: AgentCreate) =>
    apiFetch<AgentRead>(`/teams/${teamId}/agents`, { method: "POST", body: payload }),
  update: (agentId: string, payload: AgentUpdate) =>
    apiFetch<AgentRead>(`/agents/${agentId}`, { method: "PUT", body: payload }),
  remove: (agentId: string) =>
    apiFetch<void>(`/agents/${agentId}`, { method: "DELETE" }),
  memory: (agentId: string) =>
    apiFetch<AgentMemoryRead>(`/agents/${agentId}/memory`),
};

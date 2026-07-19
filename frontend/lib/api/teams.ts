/** Teams + their sessions (ARCH §14; backend `api/teams.py`). */
import { apiFetch } from "@/lib/api/client";
import type { TeamCreate, TeamRead, TeamUpdate, SessionRead } from "@/types/api";

export const teamsApi = {
  list: () => apiFetch<TeamRead[]>("/teams"),
  get: (teamId: string) => apiFetch<TeamRead>(`/teams/${teamId}`),
  create: (payload: TeamCreate) =>
    apiFetch<TeamRead>("/teams", { method: "POST", body: payload }),
  update: (teamId: string, payload: TeamUpdate) =>
    apiFetch<TeamRead>(`/teams/${teamId}`, { method: "PUT", body: payload }),
  remove: (teamId: string) =>
    apiFetch<void>(`/teams/${teamId}`, { method: "DELETE" }),
  listSessions: (teamId: string) =>
    apiFetch<SessionRead[]>(`/teams/${teamId}/sessions`),
};

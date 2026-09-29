/** Sessions, runs, artifacts (ARCH §14/§8/§21.4; backend `api/sessions.py`). */
import { apiFetch } from "@/lib/api/client";
import type {
  SessionCreate,
  SessionRead,
  RunLaunch,
  RunLaunchResponse,
  ResumeRequest,
  ArtifactRead,
  RunRead,
} from "@/types/api";

export const sessionsApi = {
  /** Org-scoped session list (Slice-0 read endpoint). */
  list: () => apiFetch<SessionRead[]>("/sessions"),
  get: (sessionId: string) => apiFetch<SessionRead>(`/sessions/${sessionId}`),
  /** A session's runs, newest first — History uses this to reach the artifact. */
  listRuns: (sessionId: string) => apiFetch<RunRead[]>(`/sessions/${sessionId}/runs`),
  create: (teamId: string, payload: SessionCreate = {}) =>
    apiFetch<SessionRead>(`/teams/${teamId}/sessions`, { method: "POST", body: payload }),
  /** Launch a run; the response carries the WS `stream_url` + interrupt flag. */
  run: (sessionId: string, payload: RunLaunch) =>
    apiFetch<RunLaunchResponse>(`/sessions/${sessionId}/run`, { method: "POST", body: payload }),
  /** Resolve the HITL gate (approve/edit/reject). */
  resume: (sessionId: string, payload: ResumeRequest) =>
    apiFetch<RunLaunchResponse>(`/sessions/${sessionId}/resume`, { method: "POST", body: payload }),
  artifact: (runId: string) => apiFetch<ArtifactRead>(`/runs/${runId}/artifact`),
  /**
   * Stop a running or HITL-paused run (ARCH §21.6). Keyed on the RUN, so one endpoint
   * serves both session runs and chat turns. Returns 409 if already terminal — a
   * double-click is a harmless no-op, not an error.
   */
  cancel: (runId: string) => apiFetch<RunRead>(`/runs/${runId}/cancel`, { method: "POST" }),
};

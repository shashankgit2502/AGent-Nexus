/** Dashboard headline counts (ARCH §14; backend `api/stats.py`). */
import { apiFetch } from "@/lib/api/client";
import type { StatsRead } from "@/types/api";

export const statsApi = {
  get: () => apiFetch<StatsRead>("/stats"),
};

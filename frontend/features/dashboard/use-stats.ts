"use client";

/** Dashboard headline counts (React Query — REST DTOs, ARCH §14 `GET /stats`). */
import { useQuery } from "@tanstack/react-query";
import { statsApi } from "@/lib/api/stats";

export function useStats() {
  return useQuery({ queryKey: ["stats"], queryFn: () => statsApi.get() });
}

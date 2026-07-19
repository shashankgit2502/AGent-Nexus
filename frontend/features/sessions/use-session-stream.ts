"use client";

/**
 * useSessionStream — bridge the AG-UI WebSocket into the Zustand store.
 *
 * Locked decision: streaming state flows WS → `ingest` (the pure reducer) →
 * store, NEVER React Query. This hook owns one `AGUIStream` per (streamUrl,
 * runId): it starts on mount, forwards every event to `ingest`, surfaces the
 * connection status (§9.8 Connecting/Live/Reconnecting/Disconnected), and tears
 * the socket down on unmount or when the target run changes.
 *
 * Reconnect + replay are the client's job (`AGUIStream` tracks the highest seq
 * and reconnects with `after_seq`); dedup is the reducer's job (keyed by seq) —
 * so a mid-run drop resumes with no duplicate events.
 */
import { useEffect, useRef, useState } from "react";
import { useSessionStore } from "@/store/session-store";
import { AGUIStream, type StreamStatus } from "@/lib/ws/agui-client";

export interface SessionStreamState {
  status: StreamStatus | "idle";
  error: string | null;
}

interface UseSessionStreamParams {
  /** Backend-provided WS path/url, or null when no run is active. */
  streamUrl: string | null;
  runId: string | null;
  /** Initial replay cursor (default 0 → full replay then live). */
  afterSeq?: number;
}

export function useSessionStream({
  streamUrl,
  runId,
  afterSeq = 0,
}: UseSessionStreamParams): SessionStreamState {
  const ingest = useSessionStore((s) => s.ingest);
  const [status, setStatus] = useState<StreamStatus | "idle">("idle");
  const [error, setError] = useState<string | null>(null);
  const streamRef = useRef<AGUIStream | null>(null);

  useEffect(() => {
    if (!streamUrl || !runId) {
      setStatus("idle");
      return;
    }
    setError(null);
    const stream = new AGUIStream({
      streamUrl,
      runId,
      afterSeq,
      onEvent: ingest,
      onStatusChange: setStatus,
      onError: (e) => setError(e.message),
    });
    streamRef.current = stream;
    stream.start();

    return () => {
      stream.close();
      streamRef.current = null;
    };
  }, [streamUrl, runId, afterSeq, ingest]);

  return { status, error };
}

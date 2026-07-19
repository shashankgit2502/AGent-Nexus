/**
 * AG-UI WebSocket client (ARCH §24.7/§24.8).
 *
 * A run streams its AG-UI envelope events over a single WebSocket
 * (`WS /sessions/{id}/stream?run_id=&after_seq=` or the `/conversations/...`
 * variant). The backend **replays** persisted events from `after_seq`, then
 * continues **live** on the same socket — so a reconnect after a drop resumes
 * exactly where we left off by sending `after_seq=<last seq seen>`.
 *
 * Responsibilities (R2 — use the browser `WebSocket`, don't hand-roll a
 * transport; R5 — validate untrusted frames at the boundary):
 *  - resolve the WS URL from `NEXT_PUBLIC_WS_URL` + the backend-provided path;
 *  - parse + validate each frame as an `AGUIEvent` (drop malformed frames via
 *    `onError`, never crash the stream);
 *  - track the highest `seq` and reconnect with backoff using it as `after_seq`;
 *  - dedup is the reducer's job (keyed by `seq`) — this client only forwards.
 *
 * Streaming feeds the Zustand store, never React Query (locked decision).
 */
import { isAGUIEventType, type AnyAGUIEvent } from "@/types/agui";

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

export type StreamStatus = "connecting" | "open" | "closed" | "reconnecting";

export interface AGUIStreamOptions {
  /** Backend-provided stream path/url, e.g. `/sessions/{id}/stream?run_id=...`. */
  streamUrl: string;
  runId: string;
  /** Initial replay cursor; 0 replays the whole run (default 0). */
  afterSeq?: number;
  onEvent: (event: AnyAGUIEvent) => void;
  onError?: (error: Error) => void;
  onStatusChange?: (status: StreamStatus) => void;
  /** Max reconnect attempts before giving up (default 6). */
  maxRetries?: number;
}

/** Build an absolute ws:// URL with `run_id` + `after_seq` query params. */
export function resolveWsUrl(streamUrl: string, runId: string, afterSeq: number): string {
  // Accept either an absolute ws(s):// URL or a backend-relative path.
  const isAbsolute = /^wss?:\/\//i.test(streamUrl);
  const base = isAbsolute ? streamUrl : `${WS_BASE_URL.replace(/\/$/, "")}/${streamUrl.replace(/^\//, "")}`;
  const url = new URL(base);
  url.searchParams.set("run_id", runId);
  url.searchParams.set("after_seq", String(afterSeq));
  return url.toString();
}

/** Minimal structural validation of an inbound frame (R5: trust nothing). */
function parseEvent(raw: unknown): AnyAGUIEvent | null {
  if (typeof raw !== "object" || raw === null) return null;
  const candidate = raw as Record<string, unknown>;
  if (!isAGUIEventType(candidate.type)) return null;
  if (typeof candidate.seq !== "number") return null;
  if (typeof candidate.run_id !== "string") return null;
  if (typeof candidate.data !== "object" || candidate.data === null) return null;
  return candidate as unknown as AnyAGUIEvent;
}

/**
 * A reconnecting AG-UI stream for one run. Call `start()` to connect and
 * `close()` to tear down. Idempotent: `close()` cancels pending reconnects.
 */
export class AGUIStream {
  private readonly options: Required<Omit<AGUIStreamOptions, "onError" | "onStatusChange">> &
    Pick<AGUIStreamOptions, "onError" | "onStatusChange">;
  private socket: WebSocket | null = null;
  private lastSeq: number;
  private retries = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;

  constructor(options: AGUIStreamOptions) {
    this.options = {
      afterSeq: 0,
      maxRetries: 6,
      ...options,
    };
    this.lastSeq = this.options.afterSeq;
  }

  /** The highest `seq` observed (the reconnect cursor). */
  get cursor(): number {
    return this.lastSeq;
  }

  start(): void {
    this.stopped = false;
    this.connect();
  }

  close(): void {
    this.stopped = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.onopen = null;
      this.socket.onmessage = null;
      this.socket.onerror = null;
      this.socket.onclose = null;
      this.socket.close();
      this.socket = null;
    }
    this.setStatus("closed");
  }

  private setStatus(status: StreamStatus): void {
    this.options.onStatusChange?.(status);
  }

  private connect(): void {
    if (this.stopped) return;
    const url = resolveWsUrl(this.options.streamUrl, this.options.runId, this.lastSeq);
    this.setStatus(this.retries === 0 ? "connecting" : "reconnecting");

    const socket = new WebSocket(url);
    this.socket = socket;

    socket.onopen = () => {
      this.retries = 0;
      this.setStatus("open");
    };

    socket.onmessage = (message: MessageEvent) => {
      let raw: unknown;
      try {
        raw = JSON.parse(typeof message.data === "string" ? message.data : "");
      } catch {
        this.options.onError?.(new Error("AG-UI frame was not valid JSON"));
        return;
      }
      const event = parseEvent(raw);
      if (!event) {
        this.options.onError?.(new Error("AG-UI frame failed contract validation"));
        return;
      }
      if (event.seq > this.lastSeq) this.lastSeq = event.seq;
      this.options.onEvent(event);
    };

    socket.onerror = () => {
      this.options.onError?.(new Error("AG-UI WebSocket error"));
    };

    socket.onclose = () => {
      this.socket = null;
      if (this.stopped) return;
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.retries >= this.options.maxRetries) {
      this.options.onError?.(
        new Error(`AG-UI stream gave up after ${this.options.maxRetries} reconnect attempts`),
      );
      this.setStatus("closed");
      return;
    }
    this.retries += 1;
    // Exponential backoff capped at 10s.
    const delay = Math.min(10_000, 500 * 2 ** (this.retries - 1));
    this.setStatus("reconnecting");
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }
}

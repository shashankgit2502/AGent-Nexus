"use client";

/**
 * Session header (§9.2) — always visible while a run is active. Carries the
 * goal, a status badge, a runtime clock, the current round, the at-a-glance
 * consensus ring, the live connection indicator (§9.8), token usage, and the run
 * controls: Stop (cancel the run server-side) and Reset (close the stream + clear the
 * board locally).
 *
 * Stop is real, not decorative: it POSTs `/runs/{id}/cancel`, which stops the graph at a
 * checkpointed boundary (ARCH §21.6). It is shown only while the run is actually
 * stoppable — live and not a replay — because a button that cannot act is worse than no
 * button. Mid-run *pause* still does not exist; the human control for that remains the
 * HITL gate.
 */
import { useEffect, useState } from "react";
import { RotateCcw, Square } from "lucide-react";
import { ConsensusRing } from "@/components/workspace/consensus-ring";
import type { RunStatus } from "@/store/session-reducer";
import type { StreamStatus } from "@/lib/ws/agui-client";

interface SessionHeaderProps {
  goal: string | null;
  status: RunStatus;
  round: number;
  meanConfidence: number | null;
  target: number;
  connection: StreamStatus | "idle";
  startedAt: number | null;
  onReset: () => void;
  /** Stop the run server-side. Omitted (with the button) when the run isn't stoppable. */
  onCancel?: () => void;
  cancelling?: boolean;
  /** Total tokens the run has consumed so far (ARCH §21.7); null when unreported. */
  totalTokens?: number | null;
  /** A historical run replayed from `run_events` — show "Replay", not a live clock. */
  replay?: boolean;
}

const STATUS_BADGE: Record<RunStatus, string> = {
  idle: "bg-zinc-700/40 text-zinc-300 border-zinc-600/40",
  running: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  awaiting_human: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  finished: "bg-green-500/15 text-green-300 border-green-500/30",
  error: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  cancelled: "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
};

const CONNECTION_LABEL: Record<StreamStatus | "idle", { label: string; color: string }> = {
  idle: { label: "Idle", color: "#52525b" },
  connecting: { label: "Connecting", color: "#f59e0b" },
  open: { label: "Live", color: "#22c55e" },
  reconnecting: { label: "Reconnecting", color: "#f59e0b" },
  closed: { label: "Disconnected", color: "#ef4444" },
};

export function SessionHeader({
  goal,
  status,
  round,
  meanConfidence,
  target,
  connection,
  startedAt,
  onReset,
  onCancel,
  cancelling = false,
  totalTokens = null,
  replay = false,
}: SessionHeaderProps) {
  const runtime = useRuntimeClock(startedAt, status);
  const conn = CONNECTION_LABEL[connection];
  // Stoppable only while the run is genuinely in flight on the server. A replay has no
  // live run behind it, and a finished/cancelled run would 409.
  const stoppable =
    !replay && onCancel !== undefined && (status === "running" || status === "awaiting_human");

  return (
    <div className="artistic-pane rounded-xl p-4 flex flex-col lg:flex-row lg:items-center gap-4 shadow-[0_4px_24px_rgba(0,0,0,0.15)]">
      <div className="flex items-center gap-4 flex-1 min-w-0">
        <ConsensusRing value={meanConfidence} target={target} />
        <div className="min-w-0">
          <p className="text-[9px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-1">
            Session Goal
          </p>
          <p className="text-sm font-semibold text-white truncate" title={goal ?? ""}>
            {goal ?? "—"}
          </p>
          <div className="flex flex-wrap items-center gap-2 mt-1.5 font-mono text-[10px]">
            <span
              className={`px-2 py-0.5 rounded-full border uppercase font-bold tracking-wider ${STATUS_BADGE[status]}`}
            >
              {status.replace("_", " ")}
            </span>
            <span className="text-zinc-500">
              Round <span className="text-zinc-300 font-bold">{round}</span>
            </span>
            <span className="text-zinc-600">·</span>
            {replay ? (
              <span className="px-2 py-0.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 uppercase font-bold tracking-wider">
                Replay
              </span>
            ) : (
              <span className="text-zinc-500">{runtime}</span>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3 self-start lg:self-auto">
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-white/10 bg-black/30">
          <span
            className="w-2 h-2 rounded-full"
            style={{
              backgroundColor: conn.color,
              boxShadow: connection === "open" ? `0 0 8px ${conn.color}` : "none",
            }}
          />
          <span className="text-[9.5px] font-mono uppercase tracking-wider text-zinc-400">
            {conn.label}
          </span>
        </div>
        {totalTokens !== null ? (
          <div
            className="px-2.5 py-1 rounded-lg border border-white/10 bg-black/30 text-[9.5px] font-mono uppercase tracking-wider text-zinc-400"
            title="total tokens consumed by this run"
          >
            {formatTokens(totalTokens)} tok
          </div>
        ) : null}
        {stoppable ? (
          <button
            type="button"
            onClick={onCancel}
            disabled={cancelling}
            className="flex items-center gap-1.5 px-3 py-2 bg-transparent hover:bg-rose-500/10 text-rose-300 hover:text-rose-200 rounded-lg border border-rose-500/30 text-[10px] font-mono uppercase tracking-wider transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Square className="w-3 h-3 fill-current" />
            {cancelling ? "Stopping…" : "Stop"}
          </button>
        ) : null}
        <button
          type="button"
          onClick={onReset}
          className="flex items-center gap-1.5 px-3 py-2 bg-transparent hover:bg-white/5 text-zinc-400 hover:text-white rounded-lg border border-white/10 text-[10px] font-mono uppercase tracking-wider transition-all"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Reset
        </button>
      </div>
    </div>
  );
}

/** Compact token count: 12345 → "12.3k". Long runs otherwise overflow the header. */
function formatTokens(total: number): string {
  if (total < 1000) return String(total);
  if (total < 1_000_000) return `${(total / 1000).toFixed(1)}k`;
  return `${(total / 1_000_000).toFixed(2)}M`;
}

/** A 1Hz elapsed-time clock that freezes once the run leaves a live state. */
function useRuntimeClock(startedAt: number | null, status: RunStatus): string {
  const [now, setNow] = useState(() => Date.now());
  const live = status === "running" || status === "awaiting_human";

  useEffect(() => {
    if (!startedAt || !live) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [startedAt, live]);

  if (!startedAt) return "00:00";
  const elapsed = Math.max(0, Math.floor(((live ? now : Date.now()) - startedAt) / 1000));
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

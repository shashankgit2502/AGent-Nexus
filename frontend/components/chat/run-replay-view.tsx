"use client";

/**
 * RunReplayView (§9A.2 "Expand to Session Workspace") — reuses the SLICE-2 panels
 * verbatim (R2, no fork): they are pure readers of the Zustand store, so a team
 * turn's completed run is replayed by subscribing to its conversation stream
 * (`WS /conversations/{id}/stream?run_id=&after_seq=0`) and folding events into
 * the same store. Reset on open and on close so the board is clean.
 *
 * Team chat turns run to completion server-side before the POST returns
 * (ARCH §8.5.2), so this is a full replay (after_seq=0), not a live tail — the
 * same `AGUIStream` replay-then-live path from Slice 1 handles it identically.
 */
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { X, Network, ClipboardList, TrendingUp, ArrowLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSessionStore } from "@/store/session-store";
import { useTeamAgents, toAgentLabels } from "@/features/sessions/use-run-controls";
import { useSessionStream } from "@/features/sessions/use-session-stream";
import { AgentGraph } from "@/components/agent-graph/agent-graph";
import { DebateThread } from "@/components/debate-thread/debate-thread";
import { OutputCanvas } from "@/components/blackboard/output-canvas";
import { ConsensusDetail } from "@/components/blackboard/consensus-detail";

interface RunReplayViewProps {
  teamId: string | null;
  runId: string;
  streamUrl: string;
  target: number;
  /** Label of the originating conversation, shown in the back-nav breadcrumb (Bug 3). */
  conversationLabel: string;
  onClose: () => void;
}

type DockTab = "output" | "consensus";

export function RunReplayView({
  teamId,
  runId,
  streamUrl,
  target,
  conversationLabel,
  onClose,
}: RunReplayViewProps) {
  const [dockTab, setDockTab] = useState<DockTab>("output");
  // Portal target is only available on the client; gate the portal on mount so SSR
  // never touches `document` (Bug 3 — the overlay must escape <main>'s z-10 stacking
  // context to sit above the sticky z-50 nav, so the back-nav header is visible).
  const [mounted, setMounted] = useState(false);
  const reset = useSessionStore((s) => s.reset);

  const teamAgents = useTeamAgents(teamId);
  const labels = useMemo(() => toAgentLabels(teamAgents.data), [teamAgents.data]);

  // Clean the board before replaying this run, and again on unmount.
  useEffect(() => {
    reset();
    return () => reset();
  }, [reset, runId]);

  const stream = useSessionStream({ streamUrl, runId, afterSeq: 0 });

  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-[60] flex flex-col bg-[#050506]/95 backdrop-blur-sm">
      <div className="flex items-center justify-between gap-4 px-6 py-3 border-b border-white/10">
        {/* Back-navigation (Bug 3): a drill-in from the chat, not a replacement — a
            clear "← Back to chat" plus a breadcrumb that names the originating
            conversation so the user is never stranded in the workspace. */}
        <div className="flex items-center gap-3 min-w-0">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-zinc-100 hover:text-emerald-300 transition-colors shrink-0"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to chat
          </button>
          <nav
            aria-label="Breadcrumb"
            className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.15em] text-zinc-500 min-w-0"
          >
            <span className="shrink-0">Chat</span>
            <ChevronRight className="w-3 h-3 shrink-0" />
            <span className="truncate max-w-[220px] text-zinc-300" title={conversationLabel}>
              {conversationLabel}
            </span>
            <ChevronRight className="w-3 h-3 shrink-0" />
            <span className="inline-flex items-center gap-1 text-emerald-400 shrink-0">
              <Network className="w-3 h-3" />
              Workspace
            </span>
          </nav>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-[10px] font-mono text-zinc-500">{stream.status}</span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close workspace"
            className="inline-flex items-center gap-1.5 text-[11px] text-zinc-400 hover:text-zinc-100"
          >
            <X className="w-4 h-4" />
            Close
          </button>
        </div>
      </div>

      {stream.error ? (
        <p className="px-6 py-1 text-[11px] text-rose-400 font-mono">Stream: {stream.error}</p>
      ) : null}

      <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 flex flex-col gap-4">
          <div className="h-[420px]">
            <AgentGraph labels={labels} />
          </div>
          <div className="flex border-b border-white/10 select-none font-mono">
            <DockTabButton active={dockTab === "output"} onClick={() => setDockTab("output")} icon={<ClipboardList className="w-3.5 h-3.5" />} label="Final Output" />
            <DockTabButton active={dockTab === "consensus"} onClick={() => setDockTab("consensus")} icon={<TrendingUp className="w-3.5 h-3.5" />} label="Consensus" />
          </div>
          <div className="h-[300px]">
            {dockTab === "output" ? <OutputCanvas /> : <ConsensusDetail target={target} labels={labels} />}
          </div>
        </div>

        <div className="lg:col-span-4 flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-emerald-400" />
            <span className="text-[11px] font-bold tracking-widest uppercase text-zinc-300">
              Debate
            </span>
          </div>
          <div className="h-[480px]">
            <DebateThread labels={labels} />
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function DockTabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "px-4 py-2.5 text-[10px] uppercase font-bold tracking-widest transition-all border-b-2 flex items-center gap-1.5",
        active
          ? "border-emerald-500 text-white bg-white/5"
          : "border-transparent text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.02]",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

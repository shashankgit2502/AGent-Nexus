"use client";

/**
 * Session Workspace (§9, flagship) — the real run → WS → reducer → panels flow,
 * replacing the reference's setTimeout simulation entirely.
 *
 * Locked separation: launch/resume go through React Query mutations (REST); the
 * live AG-UI stream flows ONLY into the Zustand store via `useSessionStream`.
 * The panels (AgentGraph, DebateThread, OutputCanvas, ConsensusDetail, HitlGate)
 * are pure readers of the store. The WS socket stays open across the HITL gate —
 * /resume continues the SAME run, so hitl_resolved → synthesis → run_finished
 * arrive live (no resubscribe). Reconnect/replay (after_seq) + seq-dedup are
 * handled by the Slice-1 seam.
 */
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Network, ClipboardList, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSessionStore } from "@/store/session-store";
import {
  useCancelRun,
  useLaunchRun,
  useResumeRun,
  useSession,
  useTeamAgents,
  toAgentLabels,
} from "@/features/sessions/use-run-controls";
import { useSessionStream } from "@/features/sessions/use-session-stream";
import { useAgentErrorToasts } from "@/features/notifications/use-agent-error-toasts";
import { AgentGraph, type AgentNode } from "@/components/agent-graph/agent-graph";
import { DebateThread } from "@/components/debate-thread/debate-thread";
import { OutputCanvas } from "@/components/blackboard/output-canvas";
import { ConsensusDetail } from "@/components/blackboard/consensus-detail";
import { HitlGate, type HitlDecisionPayload } from "@/components/hitl-gate/hitl-gate";
import { SessionHeader } from "@/components/workspace/session-header";
import { LaunchConfig } from "@/components/workspace/launch-config";
import { PlanPanel } from "@/components/workspace/plan-panel";
import type { RunLaunch } from "@/types/api";

interface ActiveRun {
  sessionId: string;
  runId: string;
  streamUrl: string;
  teamId: string;
  startedAt: number;
  /** Attached from History (replay of a past run) vs launched live here. */
  replay: boolean;
}

type DockTab = "output" | "consensus";

/**
 * `useSearchParams` (the deep-link reader) must sit under a Suspense boundary in
 * the App Router, so the page is a thin Suspense wrapper around the real view.
 */
export default function WorkspacePage() {
  return (
    <Suspense fallback={null}>
      <WorkspaceInner />
    </Suspense>
  );
}

function WorkspaceInner() {
  const [active, setActive] = useState<ActiveRun | null>(null);
  const [target, setTarget] = useState(0.85);
  const [inspected, setInspected] = useState<AgentNode | null>(null);
  const [dockTab, setDockTab] = useState<DockTab>("output");

  const resetStore = useSessionStore((s) => s.reset);

  // Store reads (selectors → only re-render what changed).
  const status = useSessionStore((s) => s.run.status);
  const goal = useSessionStore((s) => s.run.goal);
  const round = useSessionStore((s) => s.run.round);
  const meanConfidence = useSessionStore((s) => s.run.consensus?.meanConfidence ?? null);
  const hitlPending = useSessionStore((s) => s.run.hitl?.status === "pending");

  const usage = useSessionStore((s) => s.run.usage);
  const agents = useSessionStore((s) => s.run.agents);

  const launch = useLaunchRun();
  const resume = useResumeRun();
  const cancel = useCancelRun();

  // Before the terminal `usage` event lands, sum what the agents have reported so far, so
  // the header shows a live-growing figure instead of "—" for the whole run. After it, the
  // run-level total wins: it is authoritative and also covers the planner, synthesizer,
  // verifier and producer, which no agent's own turn accounts for.
  const liveTokens = useMemo(() => {
    const sum = Object.values(agents).reduce((acc, a) => acc + (a.tokens?.total ?? 0), 0);
    return sum > 0 ? sum : null;
  }, [agents]);
  const totalTokens = usage?.totalTokens ?? liveTokens;

  const teamAgents = useTeamAgents(active?.teamId ?? null);
  const labels = useMemo(() => toAgentLabels(teamAgents.data), [teamAgents.data]);

  const stream = useSessionStream({
    streamUrl: active?.streamUrl ?? null,
    runId: active?.runId ?? null,
  });

  // Raise a notification toast whenever an agent fails/abstains during a LIVE run
  // so the failure isn't only visible on the node. Suppressed for History replays
  // (their whole error history would otherwise burst in at once).
  useAgentErrorToasts(labels, !active?.replay);

  // Deep-link replay (from History): `?session=&run=` attaches to a past run and
  // replays it through the SAME WS path (after_seq=0 → full replay then live).
  // We need the run's team_id (for roster labels), so we read the session first.
  const params = useSearchParams();
  const deepSessionId = params.get("session");
  const deepRunId = params.get("run");
  const deepSession = useSession(deepSessionId);
  // Remember which deep-link we've consumed so Reset doesn't immediately re-attach.
  const consumedDeepLink = useRef<string | null>(null);

  useEffect(() => {
    if (!deepSessionId || !deepRunId) return;
    if (consumedDeepLink.current === deepRunId) return;
    const session = deepSession.data;
    if (!session) return; // wait until we know the team
    consumedDeepLink.current = deepRunId;
    resetStore();
    setInspected(null);
    setActive({
      sessionId: deepSessionId,
      runId: deepRunId,
      streamUrl: `/sessions/${deepSessionId}/stream?run_id=${deepRunId}`,
      teamId: session.team_id,
      startedAt: Date.now(),
      replay: true,
    });
  }, [deepSessionId, deepRunId, deepSession.data, resetStore]);

  const handleLaunch = (teamId: string, payload: RunLaunch) => {
    resetStore(); // clear the board before a new run
    setInspected(null);
    setTarget(payload.confidence_threshold ?? 0.85);
    launch.mutate(
      { teamId, payload },
      {
        onSuccess: ({ session, launch: res }) =>
          setActive({
            sessionId: session.id,
            runId: res.run.id,
            streamUrl: res.stream_url,
            teamId,
            startedAt: Date.now(),
            replay: false,
          }),
      },
    );
  };

  const handleResume = (payload: HitlDecisionPayload) => {
    if (!active) return;
    resume.mutate({
      sessionId: active.sessionId,
      payload: {
        run_id: active.runId,
        decision: payload.decision,
        content: payload.content ?? null,
        reason: payload.reason ?? null,
      },
    });
  };

  /**
   * Stop the run server-side (ARCH §21.6). We do NOT clear the board here: the terminal
   * `run_finished` arrives on the still-open WebSocket and settles the UI, so the user
   * keeps everything the team produced before the stop instead of losing it to a local
   * reset. Reset is a separate, explicit action.
   */
  const handleCancel = () => {
    if (!active) return;
    cancel.mutate(active.runId);
  };

  const handleReset = () => {
    setActive(null); // null streamUrl → useSessionStream closes the socket
    resetStore();
    setInspected(null);
  };

  return (
    <div className="w-full max-w-7xl xl:max-w-[1550px] mx-auto px-6 md:px-12 py-6 md:py-8 flex flex-col gap-6">
      {active ? (
        <SessionHeader
          goal={goal}
          status={status}
          round={round}
          meanConfidence={meanConfidence}
          target={target}
          connection={stream.status}
          startedAt={active.startedAt}
          onReset={handleReset}
          onCancel={handleCancel}
          cancelling={cancel.isPending}
          totalTokens={totalTokens}
          replay={active.replay}
        />
      ) : (
        <header>
          <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#10b981] mb-2">
            Slice 2 · Flagship
          </p>
          <h1 className="text-3xl font-bold artistic-text-gradient">Session Workspace</h1>
          <p className="text-sm text-zinc-400 mt-2 max-w-2xl">
            Launch a collaboration run and watch the live AG-UI stream — the agent mesh, the
            debate, consensus, and the human gate — all event-derived and round-cadenced over the
            real WebSocket.
          </p>
        </header>
      )}

      {stream.error ? (
        <p className="text-[11px] text-rose-400 font-mono">Stream: {stream.error}</p>
      ) : null}

      {active && hitlPending ? (
        <HitlGate labels={labels} onDecide={handleResume} submitting={resume.isPending} />
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {!active ? (
          <div className="lg:col-span-4">
            <LaunchConfig
              onLaunch={handleLaunch}
              launching={launch.isPending}
              error={launch.error?.message ?? null}
            />
          </div>
        ) : null}

        {/* Agent Network — center hero */}
        <div className={cn("flex flex-col gap-4", active ? "lg:col-span-8" : "lg:col-span-8")}>
          <div className="flex items-center gap-2">
            <Network className="w-4 h-4 text-emerald-400" />
            <span className="text-[11px] font-bold tracking-widest uppercase text-zinc-300">
              Agent Network
            </span>
          </div>
          <div className="h-[440px]">
            <AgentGraph
              labels={labels}
              onInspect={setInspected}
              selectedNodeId={inspected?.id ?? null}
            />
          </div>
          {inspected ? <NodeInspector node={inspected} /> : null}
        </div>

        {/* Plan + Debate — persistent right rail (only once a run exists). The plan
            sits above the debate: it arrives first (before round 1) and is the frame
            the contributions below should be read against. */}
        {active ? (
          <div className="lg:col-span-4 flex flex-col gap-4">
            <PlanPanel labels={labels} />
            <div className="flex items-center gap-2">
              <ClipboardList className="w-4 h-4 text-emerald-400" />
              <span className="text-[11px] font-bold tracking-widest uppercase text-zinc-300">
                Debate
              </span>
            </div>
            <div className="h-[440px]">
              <DebateThread labels={labels} />
            </div>
          </div>
        ) : null}
      </div>

      {/* Bottom dock — Output canvas / Consensus detail */}
      {active ? (
        <div className="flex flex-col gap-3">
          <div className="flex border-b border-white/10 select-none font-mono">
            <DockTabButton
              active={dockTab === "output"}
              onClick={() => setDockTab("output")}
              icon={<ClipboardList className="w-3.5 h-3.5" />}
              label="Final Output"
            />
            <DockTabButton
              active={dockTab === "consensus"}
              onClick={() => setDockTab("consensus")}
              icon={<TrendingUp className="w-3.5 h-3.5" />}
              label="Consensus"
            />
          </div>
          <div className="h-[320px]">
            {dockTab === "output" ? (
              <OutputCanvas />
            ) : (
              <ConsensusDetail target={target} labels={labels} />
            )}
          </div>
        </div>
      ) : null}
    </div>
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

function NodeInspector({ node }: { node: AgentNode }) {
  const d = node.data;
  return (
    <div className="artistic-pane p-4 rounded-xl text-xs flex flex-col gap-4 border border-white/10">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Info label="Agent" value={d.label} />
        <Info label="Model" value={d.model ?? "—"} />
        <Info label="Status" value={d.status} />
        <Info label="Confidence" value={d.confidence === null ? "—" : `${Math.round(d.confidence * 100)}%`} />
        {/* What the team thought, beside what the agent thought of itself (§8.1). */}
        <Info label="Peer votes" value={d.votes > 0 ? String(d.votes) : "—"} />
      </div>
      {d.subtask ? (
        <div>
          <p className="text-[9px] uppercase font-bold tracking-[0.15em] text-zinc-500 mb-1 font-mono">
            Assigned work
          </p>
          <p className="text-zinc-200 leading-snug">{d.subtask}</p>
        </div>
      ) : null}
      {d.status === "error" && d.errorMessage ? (
        <div>
          <p className="text-[9px] uppercase font-bold tracking-[0.15em] text-rose-400/80 mb-1 font-mono">
            Failure reason
          </p>
          <p className="text-rose-300 leading-snug break-words">{d.errorMessage}</p>
        </div>
      ) : null}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[9px] uppercase font-bold tracking-[0.15em] text-zinc-500 mb-1 font-mono">
        {label}
      </p>
      <p className="text-zinc-200 font-semibold truncate" title={value}>
        {value}
      </p>
    </div>
  );
}

"use client";

/**
 * History (Slice 4 + follow-up, ARCH §14).
 *
 * Master-detail browser of past sessions (`GET /sessions`). Selecting a session
 * lists its runs (`GET /sessions/{id}/runs`, newest first) and shows the terminal
 * run's synthesized artifact (`GET /runs/{id}/artifact`). A session carries no run
 * id of its own, so the runs endpoint is the bridge to the artifact — the gap
 * flagged in Slice 4, now closed with a thin org-scoped read (no contract drift).
 */
import { useState } from "react";
import Link from "next/link";
import { History as HistoryIcon, FileText, Play } from "lucide-react";
import {
  CrudPage,
  Pane,
  QueryBoundary,
  StatusPill,
  EmptyState,
  SectionTitle,
} from "@/components/crud/primitives";
import { cn } from "@/lib/utils";
import {
  useSessions,
  useSessionRuns,
  useArtifact,
  terminalRun,
  hasArtifact,
} from "@/features/history/use-history";
import { useTeams } from "@/features/teams/use-teams";
import type { SessionRead, RunRead, TeamRead } from "@/types/api";

export default function HistoryPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const sessions = useSessions();
  const teams = useTeams();

  const teamName = (teamId: string): string =>
    (teams.data ?? []).find((t: TeamRead) => t.id === teamId)?.name ?? teamId.slice(0, 8);

  return (
    <CrudPage
      eyebrow="Slice 4 · CRUD"
      title="History"
      description="Past collaboration sessions across the org — open one to read its synthesized output."
    >
      <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-5">
        <Pane className="p-3">
          <QueryBoundary
            isLoading={sessions.isLoading}
            error={sessions.error}
            data={sessions.data}
            isEmpty={(d) => d.length === 0}
            emptyMessage="No sessions yet — launch one from the Workspace."
          >
            {(list) => (
              <ul className="flex flex-col gap-1">
                {list.map((session) => (
                  <SessionRow
                    key={session.id}
                    session={session}
                    teamName={teamName(session.team_id)}
                    active={session.id === selectedId}
                    onSelect={() => setSelectedId(session.id)}
                  />
                ))}
              </ul>
            )}
          </QueryBoundary>
        </Pane>

        <Pane>
          {selectedId ? (
            <SessionDetail sessionId={selectedId} />
          ) : (
            <EmptyState
              message="Select a session to view its runs and output."
              icon={<HistoryIcon className="w-7 h-7" />}
            />
          )}
        </Pane>
      </div>
    </CrudPage>
  );
}

function SessionRow({
  session,
  teamName,
  active,
  onSelect,
}: {
  session: SessionRead;
  teamName: string;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "w-full text-left rounded-lg px-3 py-2.5 border transition-colors flex items-center justify-between gap-2",
          active
            ? "bg-emerald-500/10 border-emerald-500/30"
            : "bg-white/[0.02] border-white/10 hover:bg-white/5",
        )}
      >
        <div className="min-w-0">
          <p className="text-[12.5px] font-semibold text-zinc-100 truncate">{teamName}</p>
          <p className="text-[10px] text-zinc-500 font-mono truncate">
            {new Date(session.created_at).toLocaleString()}
          </p>
        </div>
        <StatusPill status={session.status} />
      </button>
    </li>
  );
}

function SessionDetail({ sessionId }: { sessionId: string }) {
  const runs = useSessionRuns(sessionId);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <SectionTitle label="Runs" hint="Newest first" />
        <QueryBoundary
          isLoading={runs.isLoading}
          error={runs.error}
          data={runs.data}
          isEmpty={(d) => d.length === 0}
          emptyMessage="This session has no runs."
        >
          {(list) => (
            <>
              <ul className="flex flex-col gap-2">
                {list.map((run) => (
                  <RunRow key={run.id} run={run} />
                ))}
              </ul>
              <ArtifactView run={terminalRun(list)} />
            </>
          )}
        </QueryBoundary>
      </div>
    </div>
  );
}

function RunRow({ run }: { run: RunRead }) {
  return (
    <li className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-2.5 flex items-center justify-between gap-3">
      <div className="min-w-0">
        <p className="text-[12px] text-zinc-200 truncate">{run.query}</p>
        <p className="text-[10px] text-zinc-500 font-mono">
          {run.rounds} round{run.rounds === 1 ? "" : "s"}
          {run.converged ? " · converged" : ""}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <StatusPill status={run.status} />
        {run.session_id ? (
          <Link
            href={`/workspace?session=${run.session_id}&run=${run.id}`}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-white/10 bg-white/[0.02] text-zinc-300 hover:text-white hover:bg-white/5 text-[10px] font-semibold transition-colors"
            title="Replay this run in the Session Workspace"
          >
            <Play className="w-3 h-3" />
            Replay
          </Link>
        ) : null}
      </div>
    </li>
  );
}

/** The terminal run's synthesized artifact, fetched only when one can exist. */
function ArtifactView({ run }: { run: RunRead | null }) {
  const artifact = useArtifact(hasArtifact(run) ? run!.id : null);

  if (!run) return null;
  if (!hasArtifact(run)) {
    return (
      <div className="mt-5 border border-white/10 rounded-xl p-4 text-[12px] text-zinc-500">
        The latest run is still in progress — no synthesized output yet.
      </div>
    );
  }

  return (
    <div className="mt-5">
      <div className="flex items-center gap-2 mb-2">
        <FileText className="w-4 h-4 text-[#10b981]" />
        <SectionTitle label="Synthesized output" />
      </div>
      <QueryBoundary
        isLoading={artifact.isLoading}
        error={artifact.error}
        data={artifact.data}
        emptyMessage="No artifact recorded for this run."
      >
        {(art) => (
          <div className="border border-[#10b981]/20 bg-[#10b981]/[0.05] rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[9px] font-mono uppercase tracking-widest text-[#10b981]">
                {art.kind}
              </span>
              <span className="text-[9px] font-mono text-zinc-500">{art.content_format}</span>
            </div>
            {art.content ? (
              <pre className="text-[12.5px] text-zinc-200 whitespace-pre-wrap font-sans leading-relaxed">
                {art.content}
              </pre>
            ) : (
              <p className="text-[12px] text-zinc-500 italic">
                Run rejected — no output was synthesized.
              </p>
            )}
          </div>
        )}
      </QueryBoundary>
    </div>
  );
}

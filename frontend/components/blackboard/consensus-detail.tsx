"use client";

/**
 * Consensus detail (§9.5) — the bottom-dock tab behind the header ring: mean
 * confidence vs target τ with a progress bar, convergence state, current round,
 * and the confidence-weighted ranking (`"agent_id:round"` keys, best first).
 * Pure read off the store via `buildConsensusModel`.
 */
import { useMemo } from "react";
import { useSessionStore } from "@/store/session-store";
import { buildConsensusModel, type AgentLabel } from "@/components/agent-graph/graph-model";
import { TrendingUp, CheckCircle2, Circle } from "lucide-react";

interface ConsensusDetailProps {
  target: number;
  labels: Record<string, AgentLabel>;
}

export function ConsensusDetail({ target, labels }: ConsensusDetailProps) {
  // Derive in useMemo off the stable run reference — computing inside the selector
  // returns a fresh object each call and trips the getSnapshot infinite-loop guard.
  const run = useSessionStore((s) => s.run);
  const model = useMemo(() => buildConsensusModel(run), [run]);
  const pct = model.meanConfidence ?? 0;

  const rankLabel = (key: string) => {
    const [agentId = key, round = "?"] = key.split(":");
    const name = labels[agentId]?.name ?? agentId;
    return { name, round };
  };

  return (
    <div className="w-full h-full bg-[#111113] border border-[#27272a] rounded-xl p-5 overflow-y-auto">
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp className="w-4 h-4 text-emerald-400" />
        <span className="text-[11px] font-bold tracking-wider text-zinc-400 uppercase">
          Consensus Detail
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-4 font-mono">
        <Stat label="Mean conf" value={model.meanConfidence === null ? "—" : `${Math.round(pct * 100)}%`} />
        <Stat label="Target τ" value={`${Math.round(target * 100)}%`} />
        <Stat label="Round" value={String(model.round)} />
      </div>

      <div className="mb-5">
        <div className="h-2 rounded-full bg-white/5 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              model.converged ? "bg-green-500" : "bg-emerald-500"
            }`}
            style={{ width: `${Math.min(100, Math.round(pct * 100))}%` }}
          />
        </div>
        <div className="flex items-center gap-1.5 mt-2 text-[10px] font-mono">
          {model.converged ? (
            <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
          ) : (
            <Circle className="w-3.5 h-3.5 text-zinc-500" />
          )}
          <span className={model.converged ? "text-green-400" : "text-zinc-500"}>
            {model.converged ? "Converged" : "Deliberating"}
          </span>
        </div>
      </div>

      <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-2">
        Ranking (weighted)
      </p>
      {model.ranking.length === 0 ? (
        <p className="text-[10.5px] text-zinc-600 font-mono">No ranking yet</p>
      ) : (
        <ol className="space-y-1.5">
          {model.ranking.map((key, i) => {
            const { name, round } = rankLabel(key);
            return (
              <li
                key={key}
                className="flex items-center gap-2 text-[11px] bg-white/[0.02] border border-white/5 rounded px-2.5 py-1.5"
              >
                <span className="text-[9px] font-mono text-zinc-500 w-4">{i + 1}.</span>
                <span className="text-zinc-200 font-semibold">{name}</span>
                <span className="text-[9px] font-mono text-zinc-600">round {round}</span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[8.5px] uppercase tracking-[0.15em] text-zinc-500 mb-1">{label}</p>
      <p className="text-lg font-extrabold text-white leading-none">{value}</p>
    </div>
  );
}

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
  // The bar tracks the PEER-ADJUSTED score, because that is the number compared against τ
  // (ARCH §8.1). With no peer signal it equals mean confidence, so this is safe either way
  // — but showing raw self-confidence against τ would draw a bar that disagrees with the
  // convergence verdict beside it.
  const pct = model.meanScore ?? 0;
  const hasPeerSignal = Object.keys(model.tally).length > 0;

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

      <div className="grid grid-cols-4 gap-4 mb-4 font-mono">
        <Stat
          label="Team score"
          value={model.meanScore === null ? "—" : `${Math.round(pct * 100)}%`}
        />
        <Stat label="Target τ" value={`${Math.round(target * 100)}%`} />
        <Stat
          label="Agreement"
          value={model.agreement === null ? "—" : `${Math.round(model.agreement * 100)}%`}
        />
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
        {hasPeerSignal ? "Ranking (peer-weighted)" : "Ranking (self-confidence)"}
      </p>
      {!hasPeerSignal && model.ranking.length > 0 ? (
        /* Honest labelling: with no ENDORSE/VOTE this round the ranking is exactly the old
           self-reported order. Calling it "peer-weighted" regardless would overstate what
           the number actually knows. */
        <p className="text-[10px] text-zinc-600 mb-2 leading-snug">
          No peer votes this round — agents are ranked on self-assessment alone.
        </p>
      ) : null}
      {model.ranking.length === 0 ? (
        <p className="text-[10.5px] text-zinc-600 font-mono">No ranking yet</p>
      ) : (
        <ol className="space-y-1.5">
          {model.ranking.map((key, i) => {
            const { name, round } = rankLabel(key);
            const agentId = key.split(":")[0] ?? key;
            const votes = model.tally[agentId] ?? 0;
            const delta = model.peerDeltas[key] ?? 0;
            return (
              <li
                key={key}
                className="flex items-center gap-2 text-[11px] bg-white/[0.02] border border-white/5 rounded px-2.5 py-1.5"
              >
                <span className="text-[9px] font-mono text-zinc-500 w-4">{i + 1}.</span>
                <span className="text-zinc-200 font-semibold">{name}</span>
                <span className="text-[9px] font-mono text-zinc-600">round {round}</span>
                <span className="flex-1" />
                {votes > 0 ? (
                  <span
                    className="text-[9px] font-mono px-1.5 py-0.5 rounded-full border bg-teal-500/10 text-teal-300 border-teal-500/25"
                    title="peer votes received"
                  >
                    {votes} {votes === 1 ? "vote" : "votes"}
                  </span>
                ) : null}
                {/* The signed peer adjustment: how far the team moved this agent's own
                    self-assessment. This is the whole point of §8.1 made visible — a
                    negative delta is the team saying "we don't back this". */}
                {delta !== 0 ? (
                  <span
                    className={`text-[9px] font-mono font-bold ${
                      delta > 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                    title="peer adjustment to self-confidence"
                  >
                    {delta > 0 ? "+" : ""}
                    {delta.toFixed(2)}
                  </span>
                ) : null}
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

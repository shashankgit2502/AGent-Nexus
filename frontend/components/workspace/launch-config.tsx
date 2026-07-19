"use client";

/**
 * Launch config (§9 controls) — create-session + launch-run parameters. Shown
 * before a run; collapses out once the mesh is live. The team list comes from
 * React Query (REST), the launch is a mutation in the page. τ is shown as a
 * percentage (60–95) and converted to the 0–1 `confidence_threshold` the
 * RunLaunch DTO expects; `deep_collaborate` toggles the full HITL-gated run vs
 * the lightweight pass.
 */
import { useEffect, useState } from "react";
import { ChevronRight, Cpu, Sliders, Loader2 } from "lucide-react";
import { useTeams } from "@/features/sessions/use-run-controls";
import { SelectInput } from "@/components/crud/primitives";
import type { RunLaunch } from "@/types/api";

interface LaunchConfigProps {
  onLaunch: (teamId: string, payload: RunLaunch) => void;
  launching: boolean;
  error: string | null;
}

export function LaunchConfig({ onLaunch, launching, error }: LaunchConfigProps) {
  const teamsQuery = useTeams();
  const [teamId, setTeamId] = useState<string>("");
  const [goal, setGoal] = useState(
    "Design a resilient, multi-tenant rate-limiter for a high-throughput API gateway",
  );
  const [tauPct, setTauPct] = useState(85);
  const [maxRounds, setMaxRounds] = useState(3);
  const [deep, setDeep] = useState(true);

  // Default to the first team once loaded (no fake data — real teams only).
  useEffect(() => {
    const first = teamsQuery.data?.[0];
    if (!teamId && first) {
      setTeamId(first.id);
    }
  }, [teamsQuery.data, teamId]);

  const canLaunch = teamId !== "" && goal.trim().length > 0 && !launching;

  const submit = () => {
    if (!canLaunch) return;
    onLaunch(teamId, {
      query: goal.trim(),
      confidence_threshold: tauPct / 100,
      max_rounds: maxRounds,
      deep_collaborate: deep,
    });
  };

  return (
    <div className="artistic-pane rounded-xl p-5 shadow-[0_4px_24px_rgba(0,0,0,0.15)] space-y-4">
      <div className="flex items-center gap-2">
        <Sliders className="w-4 h-4 text-white" />
        <span className="text-[11px] font-bold tracking-widest uppercase text-zinc-300">
          Deploy Parameters
        </span>
      </div>

      <Field label="Team">
        {teamsQuery.isLoading ? (
          <p className="text-[11px] text-zinc-500 font-mono py-2">Loading teams…</p>
        ) : teamsQuery.isError ? (
          <p className="text-[11px] text-rose-400 font-mono py-2">
            Failed to load teams. Is the backend running?
          </p>
        ) : teamsQuery.data && teamsQuery.data.length > 0 ? (
          <SelectInput
            value={teamId}
            onChange={(e) => setTeamId(e.target.value)}
            disabled={launching}
          >
            {teamsQuery.data.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </SelectInput>
        ) : (
          <p className="text-[11px] text-amber-400 font-mono py-2">
            No teams yet — create one in the Teams Builder (Slice 4) first.
          </p>
        )}
      </Field>

      <Field label="Goal">
        <textarea
          rows={3}
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          disabled={launching}
          placeholder="Describe the problem for the mesh to solve…"
          className="w-full bg-[#111113] border border-white/10 rounded p-3 text-xs text-[#ececec] outline-none focus:border-emerald-500/40 resize-none font-sans leading-relaxed"
        />
      </Field>

      <Field label={`Threshold (τ) · ${tauPct}%`}>
        <input
          type="range"
          min={60}
          max={95}
          step={5}
          value={tauPct}
          onChange={(e) => setTauPct(Number(e.target.value))}
          disabled={launching}
          className="w-full accent-emerald-500 cursor-pointer"
        />
      </Field>

      <div className="grid grid-cols-2 gap-4">
        <Field label={`Max rounds · ${maxRounds}`}>
          <input
            type="range"
            min={1}
            max={6}
            step={1}
            value={maxRounds}
            onChange={(e) => setMaxRounds(Number(e.target.value))}
            disabled={launching}
            className="w-full accent-emerald-500 cursor-pointer"
          />
        </Field>
        <Field label="Deep collaborate">
          <button
            type="button"
            onClick={() => setDeep((d) => !d)}
            disabled={launching}
            className={`w-full p-2.5 rounded border text-[11px] font-mono uppercase tracking-wider transition-all ${
              deep
                ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-300"
                : "bg-white/5 border-white/10 text-zinc-400"
            }`}
          >
            {deep ? "On · HITL gated" : "Off · fast pass"}
          </button>
        </Field>
      </div>

      {error ? <p className="text-[11px] text-rose-400 font-mono">{error}</p> : null}

      <button
        type="button"
        onClick={submit}
        disabled={!canLaunch}
        className="w-full px-6 py-3 bg-white hover:bg-zinc-200 text-black font-black text-xs uppercase rounded transition-all shadow-[0_4px_20px_rgba(255,255,255,0.12)] hover:scale-[1.005] active:scale-95 disabled:opacity-40 disabled:pointer-events-none flex items-center gap-2 justify-center"
      >
        {launching ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" /> Launching…
          </>
        ) : (
          <>
            <Cpu className="w-4 h-4" /> Deploy Agent Mesh <ChevronRight className="w-4 h-4" />
          </>
        )}
      </button>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10.5px] font-mono font-bold text-zinc-500 uppercase mb-2">
        {label}
      </label>
      {children}
    </div>
  );
}

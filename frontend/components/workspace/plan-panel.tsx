"use client";

/**
 * Plan panel — the orchestrator's assignment, shown before the work starts (§4.1).
 *
 * This is what turns the Session Workspace from "watch four agents talk" into
 * "watch a team execute a plan": who owns what, in which phase, what counts as done,
 * and what the team is building. It renders the `plan_ready` event the reducer folds
 * into `run.plan`, so it is entirely event-derived — no fabricated structure.
 *
 * A `debate` plan has no subtasks *by design* (the team deliberately tackles one
 * question in parallel), so the panel says so rather than rendering an empty list.
 */
import { ClipboardCheck, FileDown, GitBranch, TriangleAlert, Users } from "lucide-react";
import { useSessionStore } from "@/store/session-store";
import type { PlanState } from "@/store/session-reducer";
import type { AgentLabel } from "@/components/agent-graph/graph-model";
import { cn } from "@/lib/utils";

const STRATEGY_COPY: Record<PlanState["strategy"], { label: string; hint: string }> = {
  decompose: { label: "Divided", hint: "each agent owns a different piece" },
  debate: { label: "Debate", hint: "all agents answer the same question in parallel" },
  single_owner: { label: "Single owner", hint: "one agent delivers, the others review" },
};

export function PlanPanel({ labels }: { labels: Record<string, AgentLabel> }) {
  const plan = useSessionStore((s) => s.run.plan);
  const round = useSessionStore((s) => s.run.round);
  const amendments = useSessionStore((s) => s.run.planAmendments);
  if (!plan) return null;

  const strategy = STRATEGY_COPY[plan.strategy];
  const named = (id: string) => labels[id]?.name ?? (id.length > 8 ? `${id.slice(0, 8)}…` : id);

  return (
    <div className="artistic-pane rounded-xl border border-white/10 p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ClipboardCheck className="w-4 h-4 text-emerald-400" />
          <span className="text-[11px] font-bold tracking-widest uppercase text-zinc-300">
            Plan
          </span>
          <span className="text-[9px] uppercase font-bold tracking-[0.15em] px-1.5 py-0.5 rounded border border-emerald-500/30 text-emerald-300 font-mono">
            {strategy.label}
          </span>
        </div>
        <span className="text-[10px] text-zinc-500 font-mono">{strategy.hint}</span>
      </div>

      {plan.summary ? (
        <p className="text-[12.5px] text-zinc-300 leading-relaxed">{plan.summary}</p>
      ) : null}

      {plan.subtasks.length > 0 ? (
        <ul className="flex flex-col gap-1.5">
          {plan.subtasks.map((task) => {
            const active = task.round === round;
            return (
              <li
                key={task.id}
                className={cn(
                  "rounded-lg border px-3 py-2 transition-colors",
                  active
                    ? "border-emerald-500/40 bg-emerald-500/[0.06]"
                    : "border-white/10 bg-white/[0.02]",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[12px] font-semibold text-zinc-100 truncate">
                    {task.title}
                  </p>
                  <span className="shrink-0 flex items-center gap-1.5">
                    {/* Work a peer handed over mid-run (ARCH §23.3 DELEGATE). Marked so
                        the plan never silently changes shape under the reader — a task
                        that appeared after the run started is a different fact from one
                        the orchestrator planned. */}
                    {task.id.startsWith("d-") ? (
                      <span
                        className="text-[8px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded-full border border-violet-500/30 text-violet-300 bg-violet-500/10"
                        title="delegated by a peer during the run"
                      >
                        delegated
                      </span>
                    ) : null}
                    <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">
                      round {task.round}
                    </span>
                  </span>
                </div>
                <p className="mt-0.5 flex items-center gap-1 text-[10px] text-emerald-300/80 font-mono">
                  <Users className="w-3 h-3" />
                  {named(task.agent_id)}
                  {task.depends_on.length > 0 ? (
                    <span className="text-zinc-500"> · after {task.depends_on.join(", ")}</span>
                  ) : null}
                </p>
                <p className="mt-1 text-[11.5px] text-zinc-400 leading-snug">
                  {task.instruction}
                </p>
                {task.acceptance.length > 0 ? (
                  <ul className="mt-1.5 flex flex-col gap-0.5">
                    {task.acceptance.map((check) => (
                      <li key={check} className="text-[10.5px] text-zinc-500">
                        ✓ {check}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-[11.5px] text-zinc-500 italic">
          No work split — every agent addresses the goal directly and the
          confidence-weighted vote decides.
        </p>
      )}

      {plan.deliverable.kind !== "none" ? (
        <p className="flex items-center gap-1.5 text-[11px] text-zinc-400 font-mono border-t border-white/10 pt-2.5">
          <FileDown className="w-3.5 h-3.5 text-emerald-400" />
          Deliverable:{" "}
          <span className="text-zinc-200">
            {plan.deliverable.filename ?? plan.deliverable.kind.toUpperCase()}
          </span>
          {plan.deliverable.notes ? (
            <span className="text-zinc-500"> — {plan.deliverable.notes}</span>
          ) : null}
        </p>
      ) : null}

      {amendments.length > 0 ? (
        /* Peer-driven re-planning (ARCH §4.1 / Finding 8). The orchestrator plans once,
           before any work exists; these are the changes the team made once it learned
           something. Shown with provenance — a plan that mutates without saying who
           changed it is worse than no plan, because the reader's mental model goes stale
           with no signal. */
        <ul className="flex flex-col gap-1 border-t border-white/10 pt-2.5">
          {amendments.map((a, i) => (
            <li
              key={`${a.subtaskId ?? "amend"}-${i}`}
              className="flex items-start gap-1.5 text-[10.5px] text-violet-300/85 leading-snug"
            >
              <GitBranch className="w-3 h-3 mt-0.5 shrink-0" />
              <span>
                <span className="font-semibold">{named(a.byAgent)}</span> {a.change}
                <span className="text-zinc-600"> · round {a.round}</span>
                {a.reason ? <span className="text-zinc-500"> — {a.reason}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {plan.warnings.length > 0 ? (
        <ul className="flex flex-col gap-1 border-t border-white/10 pt-2.5">
          {plan.warnings.map((warning) => (
            <li
              key={warning}
              className="flex items-start gap-1.5 text-[10.5px] text-amber-300/80 leading-snug"
            >
              <TriangleAlert className="w-3 h-3 mt-0.5 shrink-0" />
              {warning}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

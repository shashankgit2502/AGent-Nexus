"use client";

/**
 * HITL gate (§9 / ARCH §4.5) — the human decision before synthesis. Shown only
 * while `run.hitl.status === "pending"` (an `interrupt()` paused the graph). The
 * candidate + ranking come from the `hitl_request` event; the allowed decisions
 * are server-driven (`allowed_decisions`). Resolving POSTs /resume, which
 * continues the SAME run on the already-open WS (hitl_resolved → synthesis →
 * run_finished arrive live — no resubscribe).
 */
import { useState } from "react";
import { motion } from "framer-motion";
import { Check, Pencil, X, UserCheck } from "lucide-react";
import { useSessionStore } from "@/store/session-store";
import { Markdown } from "@/components/ui/markdown";
import { cn } from "@/lib/utils";
import type { ResumeDecision } from "@/types/api";
import type { AgentLabel } from "@/components/agent-graph/graph-model";

export interface HitlDecisionPayload {
  decision: ResumeDecision;
  content?: string;
  reason?: string;
}

interface HitlGateProps {
  labels: Record<string, AgentLabel>;
  onDecide: (payload: HitlDecisionPayload) => void;
  submitting: boolean;
}

/**
 * The plan's acceptance criteria, checked against the agreed result (ARCH §4.1).
 *
 * This is what turns the gate from "does this read well?" into "did the team do what it
 * was asked?". The planner has always defined `acceptance` criteria per subtask; until now
 * nothing evaluated them, so a run could finish with half its work unaddressed and look
 * identical to one that finished properly.
 *
 * Renders nothing when `acceptance` is null — which means **unverified** (no criteria in
 * the plan, no verifier configured, or verification failed), NOT "passed". Drawing an
 * all-green checklist for an unverified run would be exactly the false assurance the human
 * gate exists to prevent.
 */
function AcceptanceChecklist() {
  const acceptance = useSessionStore((s) => s.run.acceptance);
  if (!acceptance || acceptance.total === 0) return null;

  const allMet = acceptance.metCount === acceptance.total;
  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-3 mb-4">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          Acceptance checks
        </span>
        <span
          className={cn(
            "text-[10px] font-mono font-bold",
            allMet ? "text-emerald-400" : "text-amber-300",
          )}
        >
          {acceptance.metCount}/{acceptance.total} met
        </span>
      </div>
      <ul className="flex flex-col gap-1.5">
        {acceptance.checks.map((check, i) => (
          <li key={`${check.subtask_id}-${i}`} className="flex items-start gap-2">
            {check.met ? (
              <Check className="w-3.5 h-3.5 mt-0.5 shrink-0 text-emerald-400" />
            ) : (
              <X className="w-3.5 h-3.5 mt-0.5 shrink-0 text-rose-400" />
            )}
            <div className="min-w-0">
              <p
                className={cn(
                  "text-[11.5px] leading-snug",
                  check.met ? "text-zinc-300" : "text-rose-200",
                )}
              >
                {check.criterion}
              </p>
              {check.evidence ? (
                <p className="text-[10.5px] text-zinc-500 leading-snug mt-0.5 italic">
                  “{check.evidence}”
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
      {!allMet ? (
        <p className="mt-2 text-[10.5px] text-amber-300/80 leading-snug">
          Some criteria are unmet — approving accepts the result as-is.
        </p>
      ) : null}
    </div>
  );
}

export function HitlGate({ labels, onDecide, submitting }: HitlGateProps) {
  const hitl = useSessionStore((s) => s.run.hitl);
  const [mode, setMode] = useState<"idle" | "edit" | "reject">("idle");
  const [editText, setEditText] = useState("");
  const [reason, setReason] = useState("");

  if (!hitl || hitl.status !== "pending") return null;

  const allowed = hitl.allowedDecisions;
  const can = (d: string) => allowed.length === 0 || allowed.includes(d);
  const candidateAuthorId = hitl.candidateKey?.split(":")[0];
  const candidateAuthor = candidateAuthorId ? labels[candidateAuthorId]?.name : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="artistic-pane rounded-xl border border-amber-500/30 p-5 shadow-[0_8px_40px_rgba(0,0,0,0.4)]"
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse" />
        <UserCheck className="w-4 h-4 text-amber-400" />
        <span className="text-[11px] font-bold tracking-widest uppercase text-amber-300">
          Human Gate · Awaiting Decision
        </span>
      </div>

      <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-1">
        Candidate {candidateAuthor ? `· ${candidateAuthor}` : ""}
      </p>
      <div className="rounded-lg bg-black/40 border border-white/5 p-3 mb-4 max-h-[50vh] overflow-y-auto">
        {hitl.candidate ? (
          <Markdown content={hitl.candidate} className="text-[12px]" />
        ) : (
          <p className="text-[12px] text-zinc-500">No candidate text provided.</p>
        )}
      </div>

      <AcceptanceChecklist />

      {mode === "edit" && (
        <textarea
          rows={4}
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          placeholder="Edit the candidate output to synthesize…"
          className="w-full bg-[#111113] border border-white/10 rounded p-3 text-xs text-zinc-200 outline-none focus:border-emerald-500/40 resize-none font-sans mb-3"
        />
      )}
      {mode === "reject" && (
        <textarea
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Reason for rejection (optional)…"
          className="w-full bg-[#111113] border border-white/10 rounded p-3 text-xs text-zinc-200 outline-none focus:border-rose-500/40 resize-none font-sans mb-3"
        />
      )}

      <div className="flex flex-wrap items-center gap-2 font-mono">
        {mode === "idle" ? (
          <>
            {can("approve") && (
              <button
                type="button"
                disabled={submitting}
                onClick={() => onDecide({ decision: "approve" })}
                className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-black font-black text-xs uppercase rounded transition-all disabled:opacity-50 flex items-center gap-1.5"
              >
                <Check className="w-3.5 h-3.5" /> Approve
              </button>
            )}
            {can("edit") && (
              <button
                type="button"
                disabled={submitting}
                onClick={() => {
                  setEditText(hitl.candidate ?? "");
                  setMode("edit");
                }}
                className="px-4 py-2 bg-white/5 hover:bg-white/10 text-white text-xs uppercase rounded border border-white/10 transition-all disabled:opacity-50 flex items-center gap-1.5"
              >
                <Pencil className="w-3.5 h-3.5" /> Edit
              </button>
            )}
            {can("reject") && (
              <button
                type="button"
                disabled={submitting}
                onClick={() => setMode("reject")}
                className="px-4 py-2 bg-transparent hover:bg-rose-500/10 text-rose-400 text-xs uppercase rounded border border-rose-500/20 transition-all disabled:opacity-50 flex items-center gap-1.5"
              >
                <X className="w-3.5 h-3.5" /> Reject
              </button>
            )}
          </>
        ) : mode === "edit" ? (
          <>
            <button
              type="button"
              disabled={submitting || editText.trim().length === 0}
              onClick={() => onDecide({ decision: "edit", content: editText })}
              className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-black font-black text-xs uppercase rounded transition-all disabled:opacity-50 flex items-center gap-1.5"
            >
              <Check className="w-3.5 h-3.5" /> Submit Edit
            </button>
            <CancelButton onClick={() => setMode("idle")} disabled={submitting} />
          </>
        ) : (
          <>
            <button
              type="button"
              disabled={submitting}
              onClick={() => onDecide({ decision: "reject", reason: reason || undefined })}
              className="px-4 py-2 bg-rose-500 hover:bg-rose-400 text-white font-black text-xs uppercase rounded transition-all disabled:opacity-50 flex items-center gap-1.5"
            >
              <X className="w-3.5 h-3.5" /> Confirm Reject
            </button>
            <CancelButton onClick={() => setMode("idle")} disabled={submitting} />
          </>
        )}
      </div>
    </motion.div>
  );
}

function CancelButton({ onClick, disabled }: { onClick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="px-3 py-2 bg-transparent hover:bg-white/5 text-zinc-400 hover:text-white text-xs uppercase rounded border border-white/5 transition-all disabled:opacity-50"
    >
      Cancel
    </button>
  );
}

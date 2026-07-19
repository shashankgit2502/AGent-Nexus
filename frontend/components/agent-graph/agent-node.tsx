"use client";

/**
 * Custom React Flow node for a mesh agent (§9.3). Visual encoding is
 * event-derived: border colour = live status, border width/glow = confidence,
 * a status dot mirrors the reference's AgentGraph legend. Handles are present
 * (so critique edges can anchor) but visually hidden — this is a read-only viz,
 * not an editable diagram.
 */
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Cpu, Wrench, CircleCheck, CircleDot, TriangleAlert, Unplug } from "lucide-react";
import type { AgentNode, AgentNodeStatus } from "@/components/agent-graph/graph-model";

const STATUS_COLOR: Record<AgentNodeStatus, string> = {
  idle: "#3f3f46",
  thinking: "#10b981",
  tool_call: "#f59e0b",
  contributed: "#22c55e",
  abstained: "#fb923c", // orange-400 — fixable config warning, not a hard failure
  error: "#ef4444",
};

const STATUS_LABEL: Record<AgentNodeStatus, string> = {
  idle: "Idle",
  thinking: "Thinking",
  tool_call: "Tool Call",
  contributed: "Contributed",
  abstained: "No Tools",
  error: "Error",
};

function StatusIcon({ status }: { status: AgentNodeStatus }) {
  const cls = "w-3.5 h-3.5";
  switch (status) {
    case "thinking":
      return <Cpu className={`${cls} text-emerald-400`} />;
    case "tool_call":
      return <Wrench className={`${cls} text-amber-400`} />;
    case "contributed":
      return <CircleCheck className={`${cls} text-green-400`} />;
    case "abstained":
      return <Unplug className={`${cls} text-orange-400`} />;
    case "error":
      return <TriangleAlert className={`${cls} text-rose-400`} />;
    default:
      return <CircleDot className={`${cls} text-zinc-500`} />;
  }
}

export function AgentNodeView({ data, selected }: NodeProps<AgentNode>) {
  const color = STATUS_COLOR[data.status];
  const active = data.status === "thinking" || data.status === "tool_call";
  // Confidence (0–1) → border intensity (§9.3 "border intensity = confidence").
  const conf = data.confidence ?? 0;
  const borderWidth = 1 + Math.round(conf * 2); // 1–3px

  return (
    <div
      className="relative rounded-xl px-3 py-2 w-[150px] bg-[#141416] transition-all"
      style={{
        border: `${selected ? 3 : borderWidth}px solid ${color}`,
        boxShadow: active ? `0 0 18px ${color}55` : selected ? `0 0 12px ${color}44` : "none",
      }}
    >
      {/* Hidden handles so directed critique edges have anchor points. */}
      <Handle type="target" position={Position.Top} className="!opacity-0 !w-1 !h-1" />
      <Handle type="source" position={Position.Bottom} className="!opacity-0 !w-1 !h-1" />

      <div className="flex items-center justify-between gap-2 mb-1">
        <StatusIcon status={data.status} />
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ backgroundColor: color }}
          aria-hidden
        />
      </div>
      <p className="text-[12px] font-bold text-white leading-tight truncate" title={data.label}>
        {data.label}
      </p>
      {data.model ? (
        <p className="text-[8.5px] font-mono text-zinc-500 truncate" title={data.model}>
          {data.model}
        </p>
      ) : null}
      <div className="mt-1.5 flex items-center justify-between text-[8.5px] font-mono">
        <span className="uppercase tracking-wider" style={{ color }}>
          {STATUS_LABEL[data.status]}
        </span>
        {data.confidence !== null ? (
          <span className="text-zinc-400">{Math.round(data.confidence * 100)}%</span>
        ) : null}
      </div>
      {/* Failure reason (§21.5 abstention): show *why* the agent dropped out so the
          viewer isn't left guessing. Coloured by status (orange = fixable config
          abstention, red = hard error). Full text on hover; clamped in the node. */}
      {(data.status === "error" || data.status === "abstained") && data.errorMessage ? (
        <p
          className="mt-1.5 text-[8.5px] leading-snug break-words line-clamp-3"
          style={{ color }}
          title={data.errorMessage}
        >
          {data.errorMessage}
        </p>
      ) : null}
    </div>
  );
}

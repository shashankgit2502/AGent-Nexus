"use client";

/**
 * AgentGraph (§9.3) — the mesh topology, driven entirely by the live RunState.
 *
 * R2: built on @xyflow/react (React Flow 12), not a hand-rolled SVG. The graph
 * is fully CONTROLLED from the Zustand store: every render derives nodes/edges
 * via the pure `buildGraphModel`, so the topology, node status, confidence
 * encoding, and round-cadenced critique edges all reflect real AG-UI events
 * (§9.10 — no decorative fiction). The viz is read-only (no dragging/connecting).
 */
import { useMemo } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  type NodeTypes,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useSessionStore } from "@/store/session-store";
import {
  buildGraphModel,
  type AgentEdge,
  type AgentLabel,
  type AgentNode,
} from "@/components/agent-graph/graph-model";
import { AgentNodeView } from "@/components/agent-graph/agent-node";

// Module-level (stable identity) — React Flow warns if nodeTypes is recreated.
const NODE_TYPES: NodeTypes = { agent: AgentNodeView };

interface AgentGraphProps {
  /** id → {name, model} joined from GET /teams/{id}/agents (labels the nodes). */
  labels: Record<string, AgentLabel>;
  onInspect?: (node: AgentNode | null) => void;
  selectedNodeId?: string | null;
}

export function AgentGraph({ labels, onInspect, selectedNodeId }: AgentGraphProps) {
  return (
    <ReactFlowProvider>
      <AgentGraphInner labels={labels} onInspect={onInspect} selectedNodeId={selectedNodeId} />
    </ReactFlowProvider>
  );
}

function AgentGraphInner({ labels, onInspect, selectedNodeId }: AgentGraphProps) {
  const run = useSessionStore((s) => s.run);

  const { nodes, edges } = useMemo(() => {
    const model = buildGraphModel(run, labels);
    // Reflect the inspector selection into RF's `selected` flag (border emphasis).
    const nodes = selectedNodeId
      ? model.nodes.map((n) => (n.id === selectedNodeId ? { ...n, selected: true } : n))
      : model.nodes;
    return { nodes, edges: model.edges };
  }, [run, labels, selectedNodeId]);

  const empty = nodes.length === 0;

  return (
    <div className="relative w-full h-full min-h-[320px] rounded-xl border border-[#27272a] bg-[#111113] overflow-hidden">
      {empty ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center text-zinc-500 p-6">
          <p className="text-[11px] font-mono">Mesh idle</p>
          <p className="text-[10px] text-zinc-600 mt-1">Launch a run to populate the agent network</p>
        </div>
      ) : (
        <ReactFlow<AgentNode>
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodeClick={(_, node) => onInspect?.(node as AgentNode)}
          onPaneClick={() => onInspect?.(null)}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesFocusable={false}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.3}
          maxZoom={1.5}
          proOptions={{ hideAttribution: false }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#ffffff10" />
        </ReactFlow>
      )}
      {!empty ? <EdgeLegend edges={edges} /> : null}
    </div>
  );
}

/** Edge colour → meaning. Only the kinds actually on screen are listed. */
const LEGEND: readonly { key: string; color: string; label: string }[] = [
  { key: "REQUEST", color: "#f59e0b", label: "asked" },
  { key: "DELEGATE", color: "#a78bfa", label: "handed over" },
  { key: "ENDORSE", color: "#34d399", label: "backed" },
  { key: "VOTE", color: "#2dd4bf", label: "voted" },
  { key: "critique", color: "#f43f5e", label: "challenged" },
  { key: "reply", color: "#60a5fa", label: "builds on" },
];

/**
 * Legend for the live edges (ARCH §23.3 / §9.10).
 *
 * Six colours on a dense mesh is unreadable without a key — but a *static* legend listing
 * relationships that aren't happening is just as bad, so this renders only the kinds
 * currently drawn. An empty round shows nothing at all.
 */
function EdgeLegend({ edges }: { edges: readonly AgentEdge[] }) {
  const present = new Set(
    edges
      .filter((e) => e.data?.active)
      .map((e) => (e.data?.kind === "a2a" ? String(e.data?.intent) : String(e.data?.kind))),
  );
  const shown = LEGEND.filter((entry) => present.has(entry.key));
  if (shown.length === 0) return null;

  return (
    <div className="absolute bottom-2 left-2 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-black/50 backdrop-blur-sm border border-white/10 px-2.5 py-1.5 pointer-events-none">
      {shown.map((entry) => (
        <span key={entry.key} className="flex items-center gap-1.5">
          <span
            className="h-0.5 w-3.5 rounded-full"
            style={{ backgroundColor: entry.color }}
            aria-hidden
          />
          <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-400">
            {entry.label}
          </span>
        </span>
      ))}
    </div>
  );
}

// Re-export the node type for callers that inspect a clicked node.
export type { AgentNode } from "@/components/agent-graph/graph-model";
export type RFNode = Node;

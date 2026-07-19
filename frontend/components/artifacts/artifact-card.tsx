"use client";

/**
 * ArtifactCard — the compact, clickable card shown wherever a run produced files
 * (ARTIFACTS.md §12). Shows kind icon, filename, kind/size/version, and the live
 * `generating → ready` status; clicking opens the ArtifactPanel.
 */
import { Ban, Loader2 } from "lucide-react";
import { artifactIcon } from "@/components/artifacts/artifact-icon";
import { formatBytes } from "@/lib/artifacts";
import type { ArtifactEntry } from "@/store/session-reducer";

interface ArtifactCardProps {
  artifact: ArtifactEntry;
  onOpen: (artifactId: string) => void;
}

export function ArtifactCard({ artifact, onOpen }: ArtifactCardProps) {
  const Icon = artifactIcon(artifact.kind);
  const generating = artifact.status === "generating";
  const failed = artifact.status === "failed";

  return (
    <button
      type="button"
      onClick={() => onOpen(artifact.artifactId)}
      className="group flex items-center gap-2.5 w-full max-w-[280px] text-left px-3 py-2 rounded-lg border border-[#27272a] bg-[#18181b] hover:border-emerald-500/40 hover:bg-[#1c1c20] transition-all"
    >
      <span className="shrink-0 grid place-items-center w-8 h-8 rounded-md bg-emerald-500/10 border border-emerald-500/20">
        <Icon className="w-4 h-4 text-emerald-400" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[11.5px] font-medium text-zinc-200 truncate">
          {artifact.filename ?? `artifact.${artifact.kind}`}
        </span>
        <span className="block text-[9.5px] font-mono text-zinc-500 uppercase tracking-wide">
          {artifact.kind} · {formatBytes(artifact.sizeBytes)}
          {artifact.version > 1 ? ` · v${artifact.version}` : ""}
        </span>
      </span>
      {generating ? (
        <Loader2 className="w-3.5 h-3.5 shrink-0 text-amber-400 animate-spin" />
      ) : failed ? (
        <Ban className="w-3.5 h-3.5 shrink-0 text-rose-400" />
      ) : null}
    </button>
  );
}

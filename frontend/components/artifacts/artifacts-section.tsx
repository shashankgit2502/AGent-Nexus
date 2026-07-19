"use client";

/**
 * ArtifactsSection — the run's downloadable file artifacts, shown in the Final
 * Output area (ARTIFACTS.md §12, FRONTEND_SPEC §9.7). Reads the producer artifacts
 * from the session store (folded from `tool_result` attachments, §11.1), renders a
 * strip of cards, and opens the ArtifactPanel for the selected one.
 *
 * Self-contained (reads its own store slice) so its only mount — `OutputCanvas`,
 * which is used in BOTH the Session Workspace and chat — stays a one-line include and
 * renders nothing until a file is produced.
 */
import { useState } from "react";
import { Paperclip } from "lucide-react";
import { useSessionStore } from "@/store/session-store";
import { ArtifactCard } from "@/components/artifacts/artifact-card";
import { ArtifactPanel } from "@/components/artifacts/artifact-panel";

export function ArtifactsSection() {
  const artifacts = useSessionStore((s) => s.run.artifacts);
  const [openId, setOpenId] = useState<string | null>(null);

  if (artifacts.length === 0) return null;

  const open = artifacts.find((a) => a.artifactId === openId) ?? null;

  return (
    <div className="mt-4 pt-4 border-t border-[#27272a]/60">
      <div className="flex items-center gap-1.5 mb-2.5">
        <Paperclip className="w-3 h-3 text-zinc-500" />
        <span className="text-[9.5px] font-mono uppercase tracking-[0.18em] text-zinc-500">
          Artifacts · {artifacts.length}
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {artifacts.map((artifact) => (
          <ArtifactCard key={artifact.artifactId} artifact={artifact} onOpen={setOpenId} />
        ))}
      </div>
      {open ? <ArtifactPanel artifact={open} onClose={() => setOpenId(null)} /> : null}
    </div>
  );
}

"use client";

/**
 * MessageArtifacts — inline artifact cards on a chat assistant message (ARTIFACTS §12).
 *
 * ChatGPT/Claude behaviour: when a team-chat turn produced downloadable file(s), the
 * assistant message shows artifact cards; clicking opens the shared ArtifactPanel
 * (preview / versions / iterate / download). The files come from the turn's run
 * (`GET /runs/{runId}/artifacts`); the run's terminal `synthesis`/`rejected` outcome —
 * which *is* the message text — is filtered out, leaving only deliverable files.
 */
import { useEffect, useState } from "react";
import { ArtifactCard } from "@/components/artifacts/artifact-card";
import { ArtifactPanel } from "@/components/artifacts/artifact-panel";
import {
  ARTIFACT_FILE_KINDS,
  listRunArtifacts,
  type ArtifactReadDto,
} from "@/lib/api/artifacts";
import type { ArtifactEntry } from "@/store/session-reducer";
import type { ArtifactFileKind } from "@/types/agui";

function readToEntry(row: ArtifactReadDto): ArtifactEntry {
  return {
    artifactId: row.id,
    kind: row.kind as ArtifactFileKind,
    filename: row.filename,
    mimeType: row.mime_type,
    version: row.current_version,
    status: row.status,
    preview: null, // the panel fetches full content by id on open
    downloadUrl: "",
    sizeBytes: row.size_bytes,
    producerAgentId: row.producer_agent_id,
  };
}

export function MessageArtifacts({ runId }: { runId: string }) {
  const [artifacts, setArtifacts] = useState<ArtifactEntry[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listRunArtifacts(runId)
      .then((rows) => {
        if (cancelled) return;
        setArtifacts(rows.filter((r) => ARTIFACT_FILE_KINDS.has(r.kind)).map(readToEntry));
      })
      .catch(() => {
        // No inline cards on failure — the message text still stands (non-fatal).
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (artifacts.length === 0) return null;
  const open = artifacts.find((a) => a.artifactId === openId) ?? null;

  return (
    <div className="flex flex-wrap gap-2 mt-0.5">
      {artifacts.map((artifact) => (
        <ArtifactCard key={artifact.artifactId} artifact={artifact} onOpen={setOpenId} />
      ))}
      {open ? <ArtifactPanel artifact={open} onClose={() => setOpenId(null)} /> : null}
    </div>
  );
}

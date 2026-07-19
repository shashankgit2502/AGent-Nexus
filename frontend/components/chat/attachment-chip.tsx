"use client";

/**
 * AttachmentChip (§9A.5) — a transient conversation upload (ARCH §8.5.3). Shows live
 * ingestion status (ingesting → ready/failed) so a failed upload is never silent
 * (Bug 2). For a TEAM chat it offers "Save to team knowledge" (promotes into
 * `knowledge_sources`, one-way). No-team chats have no team KB, so the action hides.
 */
import { Paperclip, BookUp, Check, Loader2, AlertCircle } from "lucide-react";
import { isAttachmentIngesting } from "@/features/chat/chat-model";
import type { AttachmentRead } from "@/types/api";

interface AttachmentChipProps {
  attachment: AttachmentRead;
  /** Team chats only — undefined hides the promote action (ARCH §8.5.3). */
  onSaveToKnowledge?: (attachmentId: string) => void;
  saving?: boolean;
}

function fileName(uri: string): string {
  const parts = uri.split(/[\\/]/);
  return parts[parts.length - 1] || uri;
}

/** The small status badge: ingesting spinner, ready check, or a failure marker. */
function StatusBadge({ attachment }: { attachment: AttachmentRead }) {
  if (isAttachmentIngesting(attachment)) {
    return (
      <span className="inline-flex items-center gap-1 text-zinc-400 font-mono" title="Ingesting…">
        <Loader2 className="w-3 h-3 animate-spin" /> ingesting
      </span>
    );
  }
  if (attachment.status === "failed") {
    return (
      <span
        className="inline-flex items-center gap-1 text-rose-400 font-mono"
        title={attachment.error ?? "Ingestion failed"}
      >
        <AlertCircle className="w-3 h-3" /> failed
      </span>
    );
  }
  if (attachment.status === "ready") {
    return (
      <span className="inline-flex items-center gap-1 text-emerald-400/80 font-mono" title="Ready">
        <Check className="w-3 h-3" /> ready
      </span>
    );
  }
  return null;
}

export function AttachmentChip({ attachment, onSaveToKnowledge, saving }: AttachmentChipProps) {
  const promoted = attachment.scope === "knowledge";
  // While the file is still ingesting (or failed), promoting to the team KB is not
  // meaningful yet, so the Save action only appears once it is retrievable.
  const canPromote = Boolean(onSaveToKnowledge) && attachment.status === "ready";
  return (
    <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-lg border border-white/10 bg-white/[0.03] text-[10.5px]">
      <Paperclip className="w-3 h-3 text-zinc-400 shrink-0" />
      <span className="text-zinc-300 max-w-[180px] truncate" title={fileName(attachment.uri)}>
        {fileName(attachment.uri)}
      </span>
      <StatusBadge attachment={attachment} />
      {promoted ? (
        <span className="inline-flex items-center gap-1 text-emerald-400 font-mono">
          <Check className="w-3 h-3" /> in KB
        </span>
      ) : canPromote ? (
        <button
          type="button"
          onClick={() => onSaveToKnowledge?.(attachment.id)}
          disabled={saving}
          className="inline-flex items-center gap-1 text-zinc-400 hover:text-emerald-400 transition-colors disabled:opacity-50"
          title="Save to team knowledge"
        >
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <BookUp className="w-3 h-3" />}
          Save
        </button>
      ) : null}
    </div>
  );
}

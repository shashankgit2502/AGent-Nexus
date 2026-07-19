"use client";

/**
 * ChatComposer (§9A.5) — input + file upload + Deep Collaborate toggle. Enter
 * sends, Shift+Enter inserts a newline. The Deep Collaborate toggle is shown for
 * team chats only (no-team has no mesh, ARCH §8.5.1). File uploads are transient
 * conversation context (ARCH §8.5.3) and surface as chips above the input.
 */
import { useState, type KeyboardEvent } from "react";
import { Send, Paperclip, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { AttachmentChip } from "@/components/chat/attachment-chip";
import type { AttachmentRead } from "@/types/api";

interface ChatComposerProps {
  onSend: (text: string, deepCollaborate: boolean) => void;
  onUpload: (file: File) => void;
  /** Team chats only — show the Deep Collaborate toggle + save-to-knowledge. */
  isTeam: boolean;
  attachments: readonly AttachmentRead[];
  onSaveToKnowledge: (attachmentId: string) => void;
  savingAttachmentId: string | null;
  sending: boolean;
  uploading: boolean;
}

export function ChatComposer({
  onSend,
  onUpload,
  isTeam,
  attachments,
  onSaveToKnowledge,
  savingAttachmentId,
  sending,
  uploading,
}: ChatComposerProps) {
  const [text, setText] = useState("");
  const [deep, setDeep] = useState(false);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    onSend(trimmed, isTeam && deep);
    setText("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-white/10 bg-[#0a0a0c]/60 p-3 flex flex-col gap-2">
      {attachments.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {attachments.map((a) => (
            <AttachmentChip
              key={a.id}
              attachment={a}
              onSaveToKnowledge={isTeam ? onSaveToKnowledge : undefined}
              saving={savingAttachmentId === a.id}
            />
          ))}
        </div>
      ) : null}

      <div className="flex items-end gap-2">
        <label
          className={cn(
            "shrink-0 w-9 h-9 rounded-lg border border-white/10 bg-white/[0.03] flex items-center justify-center cursor-pointer hover:bg-white/[0.06] transition-colors",
            uploading && "pointer-events-none opacity-60",
          )}
          title="Attach a file (transient context)"
        >
          {uploading ? (
            <Loader2 className="w-4 h-4 animate-spin text-zinc-400" />
          ) : (
            <Paperclip className="w-4 h-4 text-zinc-400" />
          )}
          <input
            type="file"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onUpload(file);
              e.target.value = ""; // allow re-selecting the same file
            }}
          />
        </label>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="Message the team…"
          className="flex-1 resize-none max-h-32 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[12.5px] text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/40"
        />

        <button
          type="button"
          onClick={submit}
          disabled={sending || !text.trim()}
          className="shrink-0 w-9 h-9 rounded-lg bg-emerald-500/90 hover:bg-emerald-500 text-black flex items-center justify-center transition-colors disabled:opacity-40 disabled:pointer-events-none"
          title="Send (Enter)"
        >
          {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </button>
      </div>

      {isTeam ? (
        <button
          type="button"
          onClick={() => setDeep((d) => !d)}
          className={cn(
            "self-start inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.15em] px-2 py-1 rounded-lg border transition-colors",
            deep
              ? "text-emerald-300 bg-emerald-500/10 border-emerald-500/30"
              : "text-zinc-400 bg-white/[0.02] border-white/10 hover:text-zinc-200",
          )}
          aria-pressed={deep}
        >
          <Sparkles className="w-3 h-3" />
          Deep Collaborate {deep ? "on" : "off"}
        </button>
      ) : null}
    </div>
  );
}

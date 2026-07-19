"use client";

/**
 * MessageBubble (§9A.5) — one transcript turn. User turns are plain text. An
 * assistant turn renders its content; a TEAM turn (has a run + stream_url) shows
 * the "Expand to Session Workspace" affordance (§9A.2) and a Deep/Fast badge.
 * Pending turns show a thinking state; failed turns surface the error (R3).
 */
import { Bot, User, Maximize2, Loader2, AlertTriangle, Layers } from "lucide-react";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/ui/markdown";
import { MessageArtifacts } from "@/components/chat/message-artifacts";
import { canExpand, type ChatMessage } from "@/features/chat/chat-model";

interface MessageBubbleProps {
  message: ChatMessage;
  onExpand?: (message: ChatMessage) => void;
}

export function MessageBubble({ message, onExpand }: MessageBubbleProps) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={cn(
          "w-7 h-7 rounded-lg flex items-center justify-center shrink-0 border",
          isUser
            ? "bg-white/5 border-white/10 text-zinc-300"
            : "bg-emerald-500/10 border-emerald-500/30 text-emerald-400",
        )}
      >
        {isUser ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
      </div>

      <div className={cn("flex flex-col gap-1.5 max-w-[78%]", isUser ? "items-end" : "items-start")}>
        <div
          className={cn(
            "rounded-xl px-3.5 py-2.5 text-[12.5px] leading-relaxed",
            isUser
              ? "bg-white/[0.06] border border-white/10 text-zinc-100 whitespace-pre-wrap"
              : "artistic-pane border border-white/10 text-zinc-200",
          )}
        >
          {message.state === "pending" ? (
            <span className="inline-flex items-center gap-2 text-zinc-400 font-mono text-[11px]">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-400" />
              {message.deepCollaborate ? "Agents collaborating…" : "Thinking…"}
            </span>
          ) : message.state === "error" ? (
            <span className="inline-flex items-center gap-2 text-rose-300 text-[11.5px]">
              <AlertTriangle className="w-3.5 h-3.5" />
              {message.error ?? "Turn failed."}
            </span>
          ) : isUser ? (
            message.content
          ) : (
            <Markdown content={message.content} className="text-[12.5px]" />
          )}
        </div>

        {/* Inline artifact cards (§12): a done team turn that produced downloadable
            file(s) shows them under the message; clicking opens the ArtifactPanel. */}
        {!isUser && message.runId && message.state === "done" ? (
          <MessageArtifacts runId={message.runId} />
        ) : null}

        {/* Affordances: a team turn can be expanded into the live Session Workspace
            even while it is still streaming (pending), and shows a Deep/Fast badge
            once done. */}
        {!isUser && message.state !== "error" ? (
          <div className="flex items-center gap-2">
            {message.runId && message.state === "done" ? (
              <span
                className={cn(
                  "inline-flex items-center gap-1 text-[9px] font-mono uppercase tracking-[0.15em] px-1.5 py-0.5 rounded",
                  message.deepCollaborate
                    ? "text-emerald-300 bg-emerald-500/10 border border-emerald-500/20"
                    : "text-zinc-400 bg-white/5 border border-white/10",
                )}
              >
                <Layers className="w-2.5 h-2.5" />
                {message.deepCollaborate ? "Deep" : "Fast"}
              </span>
            ) : null}
            {canExpand(message) && onExpand ? (
              <button
                type="button"
                onClick={() => onExpand(message)}
                className="inline-flex items-center gap-1 text-[9.5px] font-mono uppercase tracking-[0.15em] text-emerald-400 hover:text-emerald-300 transition-colors"
              >
                <Maximize2 className="w-3 h-3" />
                Expand to Workspace
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

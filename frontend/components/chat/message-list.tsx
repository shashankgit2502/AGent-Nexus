"use client";

/**
 * MessageList (§9A.5) — the transcript. In-session only: the backend exposes no
 * `GET /conversations/{id}/messages`, so this renders the turns accumulated this
 * session (flagged in FRONTEND_INTEGRATION_PLAN §11). Auto-scrolls to the latest.
 */
import { useEffect, useRef } from "react";
import { MessageSquare } from "lucide-react";
import { MessageBubble } from "@/components/chat/message-bubble";
import type { ChatMessage } from "@/features/chat/chat-model";

interface MessageListProps {
  messages: readonly ChatMessage[];
  onExpand?: (message: ChatMessage) => void;
}

export function MessageList({ messages, onExpand }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  if (messages.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center text-zinc-500 p-6">
        <MessageSquare className="w-8 h-8 opacity-20 mb-3" />
        <p className="text-xs text-zinc-400">Send a message to start the conversation.</p>
        <p className="text-[10px] text-zinc-600 mt-1 max-w-[320px]">
          Team chats run a fast 1-round pass (toggle Deep Collaborate for full consensus). The reply
          can expand into the live Session Workspace.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 p-4">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} onExpand={onExpand} />
      ))}
      <div ref={endRef} />
    </div>
  );
}

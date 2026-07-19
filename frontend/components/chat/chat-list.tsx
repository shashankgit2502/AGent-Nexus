"use client";

/**
 * ChatList (§9A.5) — the left rail. Lists saved conversations from
 * `GET /conversations` (playgrounds are excluded server-side, ARCH §8.5.1) plus
 * any playground opened this session (held in `extra`, since it never lands in
 * the list). "+ New chat" opens the dialog.
 */
import { Plus, Users, Bot, FlaskConical, Loader2, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useConversations } from "@/features/chat/use-chat";
import type { ConversationRead } from "@/types/api";

interface ChatListProps {
  activeId: string | null;
  /** Session-local conversations not in the server list (e.g. playgrounds). */
  extra?: readonly ConversationRead[];
  onSelect: (conversation: ConversationRead) => void;
  onNewChat: () => void;
  onDelete?: (conversation: ConversationRead) => void;
  /** Id of the conversation whose delete is in flight (disables its button). */
  deletingId?: string | null;
}

export function ChatList({
  activeId,
  extra = [],
  onSelect,
  onNewChat,
  onDelete,
  deletingId = null,
}: ChatListProps) {
  const conversations = useConversations();

  const serverIds = new Set((conversations.data ?? []).map((c) => c.id));
  const sessionOnly = extra.filter((c) => !serverIds.has(c.id));
  const all = [...sessionOnly, ...(conversations.data ?? [])];

  return (
    <div className="flex flex-col h-full">
      <button
        type="button"
        onClick={onNewChat}
        className="m-3 inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-emerald-500/90 hover:bg-emerald-500 text-black text-[11px] font-semibold transition-colors"
      >
        <Plus className="w-3.5 h-3.5" />
        New chat
      </button>

      <div className="flex-1 overflow-y-auto px-2 pb-2 flex flex-col gap-1">
        {conversations.isLoading ? (
          <div className="flex items-center gap-2 px-3 py-2 text-[11px] text-zinc-500">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
          </div>
        ) : null}

        {all.length === 0 && !conversations.isLoading ? (
          <p className="px-3 py-2 text-[11px] text-zinc-600">No conversations yet.</p>
        ) : null}

        {all.map((c) => (
          <ChatRow
            key={c.id}
            conversation={c}
            active={c.id === activeId}
            onSelect={() => onSelect(c)}
            onDelete={onDelete ? () => onDelete(c) : undefined}
            deleting={deletingId === c.id}
          />
        ))}
      </div>
    </div>
  );
}

function ChatRow({
  conversation,
  active,
  onSelect,
  onDelete,
  deleting,
}: {
  conversation: ConversationRead;
  active: boolean;
  onSelect: () => void;
  onDelete?: () => void;
  deleting: boolean;
}) {
  const isTeam = conversation.team_id !== null;
  const Icon = conversation.is_playground ? FlaskConical : isTeam ? Users : Bot;
  const label = conversation.title || (isTeam ? "Team chat" : "LLM chat");
  return (
    <div
      className={cn(
        "group relative rounded-lg border transition-colors",
        active
          ? "bg-white/[0.06] border-emerald-500/30"
          : "bg-transparent border-transparent hover:bg-white/[0.03]",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "w-full text-left px-3 py-2 text-[12px] flex items-center gap-2",
          onDelete ? "pr-9" : "",
          active ? "text-zinc-100" : "text-zinc-400",
        )}
      >
        <Icon
          className={cn(
            "w-3.5 h-3.5 shrink-0",
            conversation.is_playground
              ? "text-amber-400"
              : isTeam
                ? "text-emerald-400"
                : "text-zinc-400",
          )}
        />
        <span className="truncate">{label}</span>
      </button>
      {onDelete ? (
        <button
          type="button"
          onClick={onDelete}
          disabled={deleting}
          title="Delete chat"
          aria-label={`Delete ${label}`}
          className="absolute top-1/2 right-1.5 -translate-y-1/2 p-1.5 rounded-md text-zinc-500 hover:text-rose-300 hover:bg-rose-500/10 transition-all opacity-0 group-hover:opacity-100 focus-visible:opacity-100 disabled:opacity-50"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      ) : null}
    </div>
  );
}

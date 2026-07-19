"use client";

/**
 * Chat & Playground (§9A, ARCH §8.5) — the conversational entry surface.
 *
 * Composition (R2 — reuses the Slice-1 seam + Slice-2 renderer, no new engine):
 *  - REST via React Query (`features/chat/use-chat`): list/create conversations,
 *    send turns, upload/promote attachments.
 *  - A team turn's completed run is replayed through the EXACT Slice-2 panels via
 *    `RunReplayView` (Zustand store + `WS /conversations/{id}/stream`), never the
 *    query cache (locked decision).
 *
 * Three modes (ARCH §8.5.1): team chat (fast 1-round + Deep Collaborate toggle),
 * no-team single-LLM (a lightweight single-agent run that streams live, no mesh —
 * ARCH §8.5.4), and Playground (ephemeral team chat).
 */
import { useState } from "react";
import { MessageSquare } from "lucide-react";
import { ChatList } from "@/components/chat/chat-list";
import { NewChatDialog } from "@/components/chat/new-chat-dialog";
import { ChatThread } from "@/components/chat/chat-thread";
import { RunReplayView } from "@/components/chat/run-replay-view";
import { conversationMode, conversationLabel } from "@/features/chat/chat-model";
import { useDeleteConversation } from "@/features/chat/use-chat";
import type { ConversationRead } from "@/types/api";

interface ReplayTarget {
  teamId: string | null;
  runId: string;
  streamUrl: string;
}

export default function ChatPage() {
  const [active, setActive] = useState<ConversationRead | null>(null);
  /** Session-local conversations not in the server list (playgrounds). */
  const [sessionConversations, setSessionConversations] = useState<ConversationRead[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [replay, setReplay] = useState<ReplayTarget | null>(null);
  const removeConversation = useDeleteConversation();

  const handleCreated = (conversation: ConversationRead) => {
    if (conversation.is_playground) {
      setSessionConversations((prev) => [conversation, ...prev]);
    }
    setActive(conversation);
    setDialogOpen(false);
  };

  const handleDelete = (conversation: ConversationRead) => {
    const label = conversation.title || (conversation.team_id ? "this team chat" : "this chat");
    if (!window.confirm(`Delete ${label}? This removes its messages and cannot be undone.`)) return;
    removeConversation.mutate(conversation.id, {
      onSuccess: () => {
        setSessionConversations((prev) => prev.filter((c) => c.id !== conversation.id));
        setActive((current) => (current?.id === conversation.id ? null : current));
      },
    });
  };

  return (
    <div className="w-full max-w-7xl mx-auto h-[calc(100vh-3.5rem)] flex">
      {/* Left rail — chat list */}
      <aside className="w-64 shrink-0 border-r border-white/10 hidden md:flex flex-col">
        <ChatList
          activeId={active?.id ?? null}
          extra={sessionConversations}
          onSelect={setActive}
          onNewChat={() => setDialogOpen(true)}
          onDelete={handleDelete}
          deletingId={removeConversation.isPending ? removeConversation.variables ?? null : null}
        />
      </aside>

      {/* Thread pane */}
      <section className="flex-1 min-w-0 flex flex-col">
        {active ? (
          <>
            <ThreadHeader conversation={active} />
            <div className="flex-1 min-h-0">
              <ChatThread
                key={active.id}
                conversation={active}
                onExpand={({ teamId, runId, streamUrl }) => setReplay({ teamId, runId, streamUrl })}
              />
            </div>
          </>
        ) : (
          <EmptyState onNewChat={() => setDialogOpen(true)} />
        )}
      </section>

      {dialogOpen ? (
        <NewChatDialog onClose={() => setDialogOpen(false)} onCreated={handleCreated} />
      ) : null}

      {replay ? (
        <RunReplayView
          teamId={replay.teamId}
          runId={replay.runId}
          streamUrl={replay.streamUrl}
          target={0.85}
          conversationLabel={active ? conversationLabel(active) : "Chat"}
          onClose={() => setReplay(null)}
        />
      ) : null}
    </div>
  );
}

function ThreadHeader({ conversation }: { conversation: ConversationRead }) {
  const mode = conversationMode(conversation);
  return (
    <header className="px-5 py-3 border-b border-white/10 flex items-center justify-between">
      <div>
        <h1 className="text-sm font-bold text-zinc-100">{conversationLabel(conversation)}</h1>
        <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 mt-0.5">
          {mode === "team" ? "Multi-agent" : "Single LLM"}
          {conversation.is_playground ? " · Playground" : ""}
        </p>
      </div>
    </header>
  );
}

function EmptyState({ onNewChat }: { onNewChat: () => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center p-6">
      <MessageSquare className="w-10 h-10 text-zinc-700 mb-4" />
      <h1 className="text-xl font-bold artistic-text-gradient">Chat & Playground</h1>
      <p className="text-sm text-zinc-400 mt-2 max-w-md">
        Start a team chat (fast 1-round, with a Deep Collaborate toggle for full consensus), a
        single-LLM chat, or an ephemeral Playground. Team replies can expand into the live Session
        Workspace.
      </p>
      <button
        type="button"
        onClick={onNewChat}
        className="mt-5 px-4 py-2 rounded-lg bg-emerald-500/90 hover:bg-emerald-500 text-black text-[12px] font-semibold transition-colors"
      >
        New chat
      </button>
    </div>
  );
}

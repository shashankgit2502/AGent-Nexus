"use client";

/**
 * ChatThread (§9A.2/§9A.3) — one conversation's transcript + composer.
 *
 * Server-driven (ARCH §24.5): the backend persists every turn and runs team turns
 * in the **background**, filling the assistant message when the run finishes. So
 * the transcript is rendered from `GET /conversations/{id}/messages` (`useMessages`,
 * which polls while a turn is pending) rather than optimistically folded from the
 * send response. A short-lived local **echo** shows the user's own message
 * instantly, cleared once the refetch lands. Every assistant turn (team *and*
 * no-team) now streams live over a run and can be expanded into the Session
 * Workspace (ARCH §24.5/§8.5.4); no-team simply has no mesh/consensus.
 */
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  conversationMode,
  canSaveToKnowledge,
  fromServerMessage,
  sendableAttachmentIds,
  userMessage,
  type ChatMessage,
} from "@/features/chat/chat-model";
import {
  useAttachments,
  useMessages,
  useSendMessage,
  useUploadAttachment,
  useSaveAttachmentToKnowledge,
} from "@/features/chat/use-chat";
import { MessageList } from "@/components/chat/message-list";
import { ChatComposer } from "@/components/chat/chat-composer";
import { PlaygroundBanner } from "@/components/chat/playground-banner";
import type { ConversationRead } from "@/types/api";

interface ChatThreadProps {
  conversation: ConversationRead;
  onExpand: (args: { teamId: string | null; runId: string; streamUrl: string; deep: boolean }) => void;
}

function newId(): string {
  // Browser-only component; crypto.randomUUID is available (R5: no Math.random).
  return crypto.randomUUID();
}

export function ChatThread({ conversation, onExpand }: ChatThreadProps) {
  const [echoes, setEchoes] = useState<ChatMessage[]>([]);
  const [savingAttachmentId, setSavingAttachmentId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const isTeam = conversationMode(conversation) === "team";
  const messages = useMessages(conversation.id);
  // Server-driven attachments (live ingestion status, polled while ingesting) — the
  // single source of truth for the composer chips (ARCH §8.5.3 / Bug 2).
  const attachmentsQuery = useAttachments(conversation.id);
  const attachments = attachmentsQuery.data ?? [];
  const send = useSendMessage();
  const upload = useUploadAttachment();
  const saveToKnowledge = useSaveAttachmentToKnowledge();

  const refreshAttachments = () =>
    queryClient.invalidateQueries({
      queryKey: ["conversation-attachments", conversation.id],
    });

  const serverMessages = (messages.data ?? []).map((m) => fromServerMessage(conversation.id, m));
  const transcript = [...serverMessages, ...echoes];
  const pending = serverMessages.some((m) => m.state === "pending") || send.isPending;

  const handleSend = (text: string, deep: boolean) => {
    // Optimistic echo for instant feedback; the server creates the user + pending
    // assistant rows synchronously, so the refetch replaces the echo immediately.
    setEchoes((prev) => [...prev, userMessage(newId(), text, deep)]);
    send.mutate(
      {
        conversationId: conversation.id,
        // Link this turn's uploads so the agent retrieves them (ARCH §8.5.3 / Bug 2).
        payload: {
          content: text,
          deep_collaborate: deep,
          attachment_ids: sendableAttachmentIds(attachments),
        },
      },
      {
        onSuccess: async () => {
          await messages.refetch();
          setEchoes([]);
        },
        onError: () => setEchoes([]), // surfaced via `send.error` below
      },
    );
  };

  const handleUpload = (file: File) => {
    // On success the new attachment starts `pending` ingestion; refetch so the chip
    // appears and the poll begins (clears to ready/failed when the worker finishes).
    upload.mutate(
      { conversationId: conversation.id, file },
      { onSuccess: () => void refreshAttachments() },
    );
  };

  const handleSaveToKnowledge = (attachmentId: string) => {
    setSavingAttachmentId(attachmentId);
    saveToKnowledge.mutate(
      { conversationId: conversation.id, attachmentId },
      {
        onSuccess: () => void refreshAttachments(),
        onSettled: () => setSavingAttachmentId(null),
      },
    );
  };

  const handleExpand = (message: ChatMessage) => {
    if (!message.runId || !message.streamUrl) return;
    onExpand({
      teamId: conversation.team_id,
      runId: message.runId,
      streamUrl: message.streamUrl,
      deep: message.deepCollaborate,
    });
  };

  return (
    <div className="flex flex-col h-full">
      {conversation.is_playground ? (
        <div className="p-3">
          <PlaygroundBanner />
        </div>
      ) : null}

      <div className="flex-1 overflow-y-auto">
        <MessageList messages={transcript} onExpand={handleExpand} />
      </div>

      {send.error ? (
        <p className="px-4 py-1 text-[11px] text-rose-400 font-mono">Send failed: {send.error.message}</p>
      ) : null}

      {upload.error ? (
        <p className="px-4 py-1 text-[11px] text-rose-400 font-mono">
          Upload failed: {upload.error.message}
        </p>
      ) : null}

      <ChatComposer
        onSend={handleSend}
        onUpload={handleUpload}
        isTeam={isTeam}
        attachments={attachments}
        onSaveToKnowledge={canSaveToKnowledge(conversation) ? handleSaveToKnowledge : () => {}}
        savingAttachmentId={savingAttachmentId}
        sending={pending}
        uploading={upload.isPending}
      />
    </div>
  );
}

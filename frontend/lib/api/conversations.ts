/** Chat & Playground conversations (ARCH §8.5/§14; backend `api/conversations.py`). */
import { apiFetch, apiUpload } from "@/lib/api/client";
import type {
  ConversationCreate,
  ConversationRead,
  MessageCreate,
  MessageRead,
  SendMessageResponse,
  AttachmentRead,
} from "@/types/api";

export const conversationsApi = {
  /** Non-playground conversations (playgrounds are excluded from history). */
  list: () => apiFetch<ConversationRead[]>("/conversations"),
  get: (conversationId: string) =>
    apiFetch<ConversationRead>(`/conversations/${conversationId}`),
  /** A conversation's transcript in chronological order (rehydrates a thread). */
  listMessages: (conversationId: string) =>
    apiFetch<MessageRead[]>(`/conversations/${conversationId}/messages`),
  create: (payload: ConversationCreate) =>
    apiFetch<ConversationRead>("/conversations", { method: "POST", body: payload }),
  /** Soft-delete a conversation (its messages/attachments cascade server-side). */
  remove: (conversationId: string) =>
    apiFetch<void>(`/conversations/${conversationId}`, { method: "DELETE" }),
  /** Send a user turn; team turns return `run` + `stream_url` to expand into the Workspace renderer. */
  sendMessage: (conversationId: string, payload: MessageCreate) =>
    apiFetch<SendMessageResponse>(`/conversations/${conversationId}/messages`, {
      method: "POST",
      body: payload,
    }),
  /** A conversation's uploads with live ingestion status (poll until ready/failed). */
  listAttachments: (conversationId: string) =>
    apiFetch<AttachmentRead[]>(`/conversations/${conversationId}/attachments`),
  /** Upload a file as transient conversation context (ARCH §8.5.3). */
  uploadAttachment: (conversationId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiUpload<AttachmentRead>(`/conversations/${conversationId}/attachments`, form);
  },
  saveAttachmentToKnowledge: (conversationId: string, attachmentId: string) =>
    apiFetch<AttachmentRead>(
      `/conversations/${conversationId}/attachments/${attachmentId}/save-to-knowledge`,
      { method: "POST" },
    ),
};

"use client";

/**
 * REST hooks for Chat & Playground (React Query — the locked home for DTO calls).
 *
 *  - `useConversations`: the chat list (backend excludes playgrounds, ARCH §8.5.1).
 *  - `useCreateConversation`: open a team / no-team / playground chat.
 *  - `useSendMessage`: one user turn → `SendMessageResponse` (team turns carry run+url).
 *  - `useUploadAttachment` / `useSaveAttachmentToKnowledge`: transient files + promote.
 *  - `useProfiles` / `useChatCatalog`: feed the no-team model picker (profile + model).
 *
 * Streaming is deliberately absent — a team turn's run is replayed through the
 * Zustand store via `useSessionStream`, never React Query (locked decision).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { conversationsApi } from "@/lib/api/conversations";
import { providersApi } from "@/lib/api/providers";
import { hasIngestingAttachment, hasPendingTurn } from "@/features/chat/chat-model";
import type {
  AttachmentRead,
  ConversationCreate,
  ConversationRead,
  MessageCreate,
  SendMessageResponse,
} from "@/types/api";

const CONVERSATIONS_KEY = ["conversations"] as const;

export function useConversations() {
  return useQuery({ queryKey: CONVERSATIONS_KEY, queryFn: () => conversationsApi.list() });
}

/**
 * A conversation's persisted transcript — rehydrates the thread on (re)open and
 * **polls while a team turn is in flight** (its assistant message is filled
 * asynchronously when the background run finishes, ARCH §24.5). Polling stops
 * automatically once no message is pending.
 */
export function useMessages(conversationId: string | null) {
  return useQuery({
    queryKey: ["conversation-messages", conversationId],
    queryFn: () => conversationsApi.listMessages(conversationId as string),
    enabled: Boolean(conversationId),
    refetchInterval: (query) => (hasPendingTurn(query.state.data ?? []) ? 1500 : false),
  });
}

/**
 * A conversation's uploads with live ingestion status (ARCH §8.5.3 / Bug 2).
 * Polls while any attachment is still ingesting (pending/ingesting) and stops once
 * all are terminal (ready/failed), so an ingestion failure surfaces — not silence.
 */
export function useAttachments(conversationId: string | null) {
  return useQuery({
    queryKey: ["conversation-attachments", conversationId],
    queryFn: () => conversationsApi.listAttachments(conversationId as string),
    enabled: Boolean(conversationId),
    refetchInterval: (query) => (hasIngestingAttachment(query.state.data ?? []) ? 1500 : false),
  });
}

export function useCreateConversation() {
  const qc = useQueryClient();
  return useMutation<ConversationRead, Error, ConversationCreate>({
    mutationFn: (payload) => conversationsApi.create(payload),
    onSuccess: (created) => {
      // Playgrounds are ephemeral and excluded from the list — don't surface them.
      if (!created.is_playground) qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
  });
}

/** Delete a saved conversation and drop it from the cached chat list. */
export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (conversationId) => conversationsApi.remove(conversationId),
    onSuccess: () => qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY }),
  });
}

export interface SendMessageVars {
  conversationId: string;
  payload: MessageCreate;
}

export function useSendMessage() {
  return useMutation<SendMessageResponse, Error, SendMessageVars>({
    mutationFn: ({ conversationId, payload }) =>
      conversationsApi.sendMessage(conversationId, payload),
  });
}

export interface UploadVars {
  conversationId: string;
  file: File;
}

export function useUploadAttachment() {
  return useMutation<AttachmentRead, Error, UploadVars>({
    mutationFn: ({ conversationId, file }) =>
      conversationsApi.uploadAttachment(conversationId, file),
  });
}

export interface SaveToKnowledgeVars {
  conversationId: string;
  attachmentId: string;
}

export function useSaveAttachmentToKnowledge() {
  return useMutation<AttachmentRead, Error, SaveToKnowledgeVars>({
    mutationFn: ({ conversationId, attachmentId }) =>
      conversationsApi.saveAttachmentToKnowledge(conversationId, attachmentId),
  });
}

/** Inference profiles (the no-team picker's required selection, ARCH §8.5.5). */
export function useProfiles() {
  return useQuery({ queryKey: ["profiles"], queryFn: () => providersApi.listProfiles() });
}

/** Chat-type catalog models (optional override in the no-team picker). */
export function useChatCatalog() {
  return useQuery({
    queryKey: ["catalog", "chat"],
    queryFn: () => providersApi.listCatalog(),
  });
}

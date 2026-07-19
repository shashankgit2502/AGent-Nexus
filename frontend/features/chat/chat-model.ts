/**
 * Pure chat domain logic (no React, no I/O) — the high-risk mapping in Slice 3.
 *
 * Keeping mode detection, `model_ref` construction, transcript folding, and the
 * new-chat validation in one pure module means the whole flow is unit-testable
 * in a node env (R3/R5) without rendering a component. The page/components stay
 * thin wrappers that call these and push the results into React state.
 *
 * Locked decisions encoded here (ARCH §8.5, CLAUDE.md §3):
 *  - team chat = `team_id` set; no-team = `model_ref` set; playground = team + ephemeral.
 *  - a no-team conversation REQUIRES a `model_ref` ({profile_id, model_id?});
 *    a playground REQUIRES a team — mirrored from `ConversationCreate._check_target`.
 *  - transcripts are IMMUTABLE: every fold returns a new array (coding-style R5).
 */
import type {
  AttachmentRead,
  ConversationCreate,
  ConversationRead,
  MessageRead,
  ModelRef,
} from "@/types/api";

export type ChatMode = "team" | "no-team";
export type ChatTurnState = "pending" | "done" | "error";

/** One rendered transcript turn (UI state — NOT a server DTO; in-session only). */
export interface ChatMessage {
  /** Client-stable id (server message id once known, else a local uuid). */
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Team-turn run id + stream url → drives the "Expand to Workspace" affordance. */
  runId: string | null;
  streamUrl: string | null;
  deepCollaborate: boolean;
  state: ChatTurnState;
  /** Set when `state === "error"` so the bubble can surface the failure (R3). */
  error?: string;
}

/** team_id present ⇒ the team collaborates; absent ⇒ single-LLM (ARCH §8.5.1). */
export function conversationMode(conversation: ConversationRead): ChatMode {
  return conversation.team_id !== null ? "team" : "no-team";
}

/** Human label for a conversation (its title, else a mode default) — used in the
 *  thread header and the expanded-workspace breadcrumb (Bug 3 back-navigation). */
export function conversationLabel(conversation: ConversationRead): string {
  return conversation.title || (conversationMode(conversation) === "team" ? "Team chat" : "LLM chat");
}

/** Deep Collaborate is a team-only control (no-team has no mesh, ARCH §8.5.1). */
export function canDeepCollaborate(conversation: ConversationRead): boolean {
  return conversationMode(conversation) === "team";
}

/** Attachments promote into a *team* KB only (ARCH §8.5.3 — team chats only). */
export function canSaveToKnowledge(conversation: ConversationRead): boolean {
  return conversation.team_id !== null;
}

/** Build the no-team `model_ref` JSON the backend expects ({profile_id, model_id?}). */
export function buildModelRef(profileId: string, modelId?: string | null): ModelRef {
  const ref: Record<string, unknown> = { profile_id: profileId };
  if (modelId) ref.model_id = modelId;
  return ref;
}

/** Discriminated input for the New-chat dialog → a typed `ConversationCreate`. */
export type NewChatInput =
  | { kind: "team"; teamId: string; title?: string; isPlayground?: boolean }
  | { kind: "no-team"; profileId: string; modelId?: string | null; title?: string };

/**
 * Validate a new-chat request at the client boundary, mirroring the backend
 * `ConversationCreate` validator so we fail fast with a clear message (R5).
 * Returns an error string, or `null` when the input is valid.
 */
export function validateNewChat(input: NewChatInput): string | null {
  if (input.kind === "team") {
    if (!input.teamId) return "Select a team to start a team chat.";
    return null;
  }
  // no-team
  if (!input.profileId) return "Pick a model (inference profile) for a single-LLM chat.";
  return null;
}

/** Map a validated New-chat input to the `POST /conversations` payload. */
export function toConversationCreate(input: NewChatInput): ConversationCreate {
  if (input.kind === "team") {
    return {
      team_id: input.teamId,
      title: input.title?.trim() || null,
      is_playground: Boolean(input.isPlayground),
    };
  }
  return {
    model_ref: buildModelRef(input.profileId, input.modelId),
    title: input.title?.trim() || null,
  };
}

// ── Transcript mapping (server-driven) ────────────────────────────────────────
//
// The backend persists every turn and runs team turns in the background (ARCH
// §24.5): a team assistant message is created **pending** (content null) and filled
// when the run finishes. So the transcript is server-driven — rendered from
// `GET /conversations/{id}/messages`, polled while a turn is pending — rather than
// optimistically folded from the send response.

/** An optimistic local echo of the user's turn, shown until the refetch lands. */
export function userMessage(id: string, content: string, deepCollaborate: boolean): ChatMessage {
  return {
    id,
    role: "user",
    content,
    runId: null,
    streamUrl: null,
    deepCollaborate,
    state: "done",
  };
}

/** Can this assistant turn expand into the Session Workspace renderer? (team only) */
export function canExpand(message: ChatMessage): boolean {
  return message.role === "assistant" && Boolean(message.runId && message.streamUrl);
}

/** Derive the conversation WS stream url for a team turn's run (live + replay). */
export function conversationStreamUrl(conversationId: string, runId: string): string {
  return `/conversations/${conversationId}/stream?run_id=${runId}`;
}

/** True while a team assistant turn is still being produced (run in flight). */
export function isPendingAssistant(message: MessageRead): boolean {
  return message.role === "assistant" && message.content === null && message.run_id !== null;
}

/**
 * Map a persisted `MessageRead` into a rendered `ChatMessage`. A team assistant
 * turn carries a `run_id`, so we re-derive its stream url to keep "Expand to
 * Workspace" working (live while running, replay after — ARCH §24.5/§24.8). A
 * team turn whose content has not landed yet stays **pending** (still streaming).
 */
export function fromServerMessage(conversationId: string, message: MessageRead): ChatMessage {
  const role = message.role === "assistant" ? "assistant" : "user";
  return {
    id: message.id,
    role,
    content: message.content ?? "",
    runId: message.run_id,
    streamUrl: message.run_id ? conversationStreamUrl(conversationId, message.run_id) : null,
    deepCollaborate: message.deep_collaborate,
    state: isPendingAssistant(message) ? "pending" : "done",
  };
}

/** Does this transcript have a turn still in flight? (drives polling + composer lock) */
export function hasPendingTurn(messages: readonly MessageRead[]): boolean {
  return messages.some(isPendingAssistant);
}

// ── Attachments (transient chat uploads, ARCH §8.5.3) ─────────────────────────

/** An attachment is still ingesting (not yet retrievable) while pending/ingesting. */
export function isAttachmentIngesting(attachment: AttachmentRead): boolean {
  return attachment.status === "pending" || attachment.status === "ingesting";
}

/** Any upload still ingesting? Drives the attachments poll (mirror of `hasPendingTurn`). */
export function hasIngestingAttachment(attachments: readonly AttachmentRead[]): boolean {
  return attachments.some(isAttachmentIngesting);
}

/**
 * The attachment ids to send with a turn (ARCH §8.5.3 / Bug 2). Retrieval is
 * conversation-scoped, so we link every non-failed upload — the backend ignores
 * unknown ids, and a still-ingesting file becomes retrievable once it is ready.
 */
export function sendableAttachmentIds(attachments: readonly AttachmentRead[]): string[] {
  return attachments.filter((a) => a.status !== "failed").map((a) => a.id);
}

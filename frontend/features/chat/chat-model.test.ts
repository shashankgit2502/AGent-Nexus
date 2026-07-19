/**
 * Slice-3 acceptance test: the pure chat domain logic.
 *
 * Node env, no DOM/React — exercises mode detection, model_ref construction,
 * boundary validation (mirroring the backend `ConversationCreate` validator),
 * and the immutable transcript fold (pending → resolved/failed). This is the
 * highest-risk mapping in the slice, so it is verified directly.
 */
import { describe, it, expect } from "vitest";
import {
  conversationMode,
  conversationLabel,
  canDeepCollaborate,
  canSaveToKnowledge,
  buildModelRef,
  validateNewChat,
  toConversationCreate,
  userMessage,
  canExpand,
  fromServerMessage,
  conversationStreamUrl,
  isPendingAssistant,
  hasPendingTurn,
  isAttachmentIngesting,
  hasIngestingAttachment,
  sendableAttachmentIds,
  type NewChatInput,
} from "@/features/chat/chat-model";
import type { AttachmentRead, AttachmentStatus, ConversationRead, MessageRead } from "@/types/api";

function conv(overrides: Partial<ConversationRead>): ConversationRead {
  return {
    id: "c1",
    org_id: "o1",
    team_id: null,
    model_ref: null,
    thread_id: "conv-1",
    title: null,
    is_playground: false,
    created_at: "2026-06-19T00:00:00Z",
    ...overrides,
  };
}

describe("conversation mode + capability guards", () => {
  it("classifies team vs no-team by team_id", () => {
    expect(conversationMode(conv({ team_id: "t1" }))).toBe("team");
    expect(conversationMode(conv({ team_id: null, model_ref: { profile_id: "p1" } }))).toBe(
      "no-team",
    );
  });

  it("allows Deep Collaborate + save-to-knowledge only for team chats", () => {
    const team = conv({ team_id: "t1" });
    const noTeam = conv({ team_id: null, model_ref: { profile_id: "p1" } });
    expect(canDeepCollaborate(team)).toBe(true);
    expect(canDeepCollaborate(noTeam)).toBe(false);
    expect(canSaveToKnowledge(team)).toBe(true);
    expect(canSaveToKnowledge(noTeam)).toBe(false);
  });

  it("labels a conversation by title, else a mode default (Bug 3 breadcrumb)", () => {
    expect(conversationLabel(conv({ title: "Atlas due diligence" }))).toBe("Atlas due diligence");
    expect(conversationLabel(conv({ title: null, team_id: "t1" }))).toBe("Team chat");
    expect(
      conversationLabel(conv({ title: null, team_id: null, model_ref: { profile_id: "p1" } })),
    ).toBe("LLM chat");
  });
});

describe("model_ref construction (no-team, ARCH §8.5.5)", () => {
  it("includes profile_id always and model_id only when provided", () => {
    expect(buildModelRef("p1")).toEqual({ profile_id: "p1" });
    expect(buildModelRef("p1", "m1")).toEqual({ profile_id: "p1", model_id: "m1" });
    expect(buildModelRef("p1", null)).toEqual({ profile_id: "p1" });
  });
});

describe("validateNewChat mirrors the backend validator", () => {
  it("requires a team for team chats", () => {
    expect(validateNewChat({ kind: "team", teamId: "" })).toMatch(/team/i);
    expect(validateNewChat({ kind: "team", teamId: "t1" })).toBeNull();
  });

  it("requires a profile (model_ref) for no-team chats", () => {
    expect(validateNewChat({ kind: "no-team", profileId: "" })).toMatch(/model/i);
    expect(validateNewChat({ kind: "no-team", profileId: "p1" })).toBeNull();
  });
});

describe("toConversationCreate", () => {
  it("maps a team playground to team_id + is_playground", () => {
    const input: NewChatInput = { kind: "team", teamId: "t1", isPlayground: true, title: "  x " };
    expect(toConversationCreate(input)).toEqual({
      team_id: "t1",
      title: "x",
      is_playground: true,
    });
  });

  it("maps a no-team chat to a model_ref (no team_id)", () => {
    const input: NewChatInput = { kind: "no-team", profileId: "p1", modelId: "m1" };
    expect(toConversationCreate(input)).toEqual({
      model_ref: { profile_id: "p1", model_id: "m1" },
      title: null,
    });
  });
});

function msg(overrides: Partial<MessageRead>): MessageRead {
  return {
    id: "m1",
    conversation_id: "c1",
    role: "assistant",
    content: "answer",
    run_id: null,
    deep_collaborate: false,
    created_at: "2026-06-19T00:00:00Z",
    ...overrides,
  };
}

describe("optimistic user echo", () => {
  it("builds a done user turn for instant feedback", () => {
    const echo = userMessage("u1", "hello", true);
    expect(echo).toMatchObject({ role: "user", content: "hello", state: "done", runId: null });
  });
});

describe("server-driven transcript mapping (ARCH §24.5)", () => {
  it("maps a completed team assistant turn with a re-derived stream url (expandable)", () => {
    const m = fromServerMessage("c1", msg({ run_id: "r1", content: "synth", deep_collaborate: true }));
    expect(m).toMatchObject({
      content: "synth",
      runId: "r1",
      streamUrl: conversationStreamUrl("c1", "r1"),
      state: "done",
    });
    expect(canExpand(m)).toBe(true);
  });

  it("keeps a team turn PENDING while its content has not landed (still streaming)", () => {
    const server = msg({ run_id: "r1", content: null, deep_collaborate: true });
    expect(isPendingAssistant(server)).toBe(true);
    const m = fromServerMessage("c1", server);
    expect(m.state).toBe("pending");
    // Expandable even while pending — the run streams live (ARCH §24.5).
    expect(canExpand(m)).toBe(true);
  });

  it("maps a user turn with no run (not expandable, null content safe)", () => {
    const m = fromServerMessage("c2", msg({ role: "user", content: null, run_id: null }));
    expect(m.role).toBe("user");
    expect(m.content).toBe("");
    expect(m.streamUrl).toBeNull();
    expect(isPendingAssistant(msg({ role: "user", content: null, run_id: null }))).toBe(false);
    expect(canExpand(m)).toBe(false);
  });

  it("treats a no-team assistant turn as a live, expandable run (ARCH §8.5.4)", () => {
    // No-team now runs a single-agent streaming run, so its assistant turn carries
    // a run_id and is expandable — same shape as a team turn (no mesh, just one node).
    const streaming = fromServerMessage("c3", msg({ run_id: "r9", content: null }));
    expect(streaming.state).toBe("pending");
    expect(canExpand(streaming)).toBe(true);
    const done = fromServerMessage("c3", msg({ run_id: "r9", content: "hi there" }));
    expect(done.state).toBe("done");
    expect(canExpand(done)).toBe(true);
  });

  it("hasPendingTurn detects an in-flight team turn (drives polling + composer lock)", () => {
    expect(hasPendingTurn([msg({ content: "done", run_id: "r1" })])).toBe(false);
    expect(
      hasPendingTurn([
        msg({ id: "u", role: "user", content: "hi" }),
        msg({ id: "a", run_id: "r1", content: null }),
      ]),
    ).toBe(true);
  });
});

function att(id: string, status: AttachmentStatus | null): AttachmentRead {
  return {
    id,
    conversation_id: "c1",
    kind: "text/plain",
    uri: `/a/${id}.txt`,
    scope: "transient",
    source_id: "s1",
    status,
    error: status === "failed" ? "boom" : null,
    promoted_source_id: null,
    created_at: "2026-06-22T00:00:00Z",
  };
}

describe("chat attachments (Bug 2 / §8.5.3)", () => {
  it("treats pending/ingesting as still ingesting, ready/failed as terminal", () => {
    expect(isAttachmentIngesting(att("a", "pending"))).toBe(true);
    expect(isAttachmentIngesting(att("a", "ingesting"))).toBe(true);
    expect(isAttachmentIngesting(att("a", "ready"))).toBe(false);
    expect(isAttachmentIngesting(att("a", "failed"))).toBe(false);
  });

  it("hasIngestingAttachment drives the poll while any upload is mid-ingest", () => {
    expect(hasIngestingAttachment([att("a", "ready"), att("b", "failed")])).toBe(false);
    expect(hasIngestingAttachment([att("a", "ready"), att("b", "ingesting")])).toBe(true);
    expect(hasIngestingAttachment([])).toBe(false);
  });

  it("sends every non-failed attachment id (failed ones are unretrievable)", () => {
    const ids = sendableAttachmentIds([
      att("ready", "ready"),
      att("pending", "pending"),
      att("failed", "failed"),
    ]);
    expect(ids).toEqual(["ready", "pending"]);
  });
});

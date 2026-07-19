/**
 * Slice-4 unit test: the pure Agent Builder form logic.
 *
 * Node env, no DOM/React — exercises capability toggling (immutability + the
 * five-key filter that mirrors the backend `Capabilities` source of truth),
 * boundary validation, and the form→DTO mapping (nullable trimming) for both
 * create and update.
 */
import { describe, it, expect } from "vitest";
import {
  CAPABILITY_CATALOG,
  initialAgentForm,
  toggleCapability,
  isCapabilityOn,
  enabledCapabilities,
  validateAgentForm,
  toAgentCreate,
  toAgentUpdate,
  capabilitySummary,
  effectiveModelId,
  toolCapabilityWarning,
  type ModelCapabilityLookup,
  type AgentFormState,
} from "@/features/agents/agent-model";
import type { AgentRead } from "@/types/api";

// A lookup where profile "tool"→a tool-capable model, "notool"→a non-tool model.
const LOOKUP: ModelCapabilityLookup = {
  profileDefaultModelId: (id) => ({ tool: "m-tool", notool: "m-notool" })[id] ?? null,
  modelSupportsTools: (id) => ({ "m-tool": true, "m-notool": false })[id],
};

function formState(over: Partial<AgentFormState> = {}): AgentFormState {
  return { ...initialAgentForm(), ...over };
}

function agent(overrides: Partial<AgentRead> = {}): AgentRead {
  return {
    id: "a1",
    org_id: "o1",
    team_id: "t1",
    name: "Critic",
    description: "Pokes holes",
    instructions: "Be skeptical",
    capabilities: { rag: true, web_search: false },
    memory_enabled: true,
    profile_id: "p1",
    override_model_id: null,
    embedding_model_id: null,
    created_at: "2026-06-20T00:00:00Z",
    ...overrides,
  };
}

describe("capability catalog", () => {
  it("offers exactly the five backend Capabilities keys", () => {
    expect(CAPABILITY_CATALOG.map((c) => c.key)).toEqual([
      "rag",
      "web_search",
      "code_interpreter",
      "doc_chart",
      "image_gen",
    ]);
  });
});

describe("toggleCapability", () => {
  it("returns a new object (immutable) and sets the flag", () => {
    const before = { rag: true };
    const after = toggleCapability(before, "web_search", true);
    expect(after).not.toBe(before);
    expect(after).toEqual({ rag: true, web_search: true });
    expect(before).toEqual({ rag: true }); // unchanged
  });

  it("isCapabilityOn only treats strict true as on", () => {
    expect(isCapabilityOn({ rag: true }, "rag")).toBe(true);
    expect(isCapabilityOn({ rag: false }, "rag")).toBe(false);
    expect(isCapabilityOn({}, "rag")).toBe(false);
  });
});

describe("enabledCapabilities", () => {
  it("keeps only known, enabled keys and drops false/unknown ones", () => {
    const out = enabledCapabilities({
      rag: true,
      web_search: false,
      bogus: true, // unknown key must be dropped (mirrors snapshot.py filter)
    });
    expect(out).toEqual({ rag: true });
  });
});

describe("validateAgentForm", () => {
  it("requires a name", () => {
    expect(validateAgentForm({ ...initialAgentForm(), name: "  " })).toMatch(/name/i);
  });

  it("requires an inference profile (no team-default fallback exists)", () => {
    // Name present but no profile → invalid (would force the stub path server-side).
    expect(validateAgentForm({ ...initialAgentForm(), name: "Critic" })).toMatch(/profile/i);
    // Name + profile → valid.
    expect(
      validateAgentForm({ ...initialAgentForm(), name: "Critic", profileId: "p1" }),
    ).toBeNull();
  });
});

describe("toAgentCreate / toAgentUpdate", () => {
  it("seeds the form from an existing agent and round-trips capabilities", () => {
    const form = initialAgentForm(agent());
    expect(form.name).toBe("Critic");
    expect(form.memoryEnabled).toBe(true);
    expect(form.profileId).toBe("p1");
    const create = toAgentCreate(form);
    expect(create.capabilities).toEqual({ rag: true });
    expect(create.memory_enabled).toBe(true);
    expect(create.profile_id).toBe("p1");
    expect(create.override_model_id).toBeNull();
  });

  it("trims empty free-text fields to null", () => {
    const form = { ...initialAgentForm(), name: " Builder ", description: "  ", profileId: "" };
    const create = toAgentCreate(form);
    expect(create.name).toBe("Builder");
    expect(create.description).toBeNull();
    expect(create.profile_id).toBeNull();
  });

  it("update mirrors create's full editable set", () => {
    const form = initialAgentForm(agent({ name: "Edited" }));
    const update = toAgentUpdate(form);
    expect(update.name).toBe("Edited");
    expect(update.capabilities).toEqual({ rag: true });
  });
});

describe("capabilitySummary", () => {
  it("lists enabled capability labels in catalog order", () => {
    expect(capabilitySummary({ image_gen: true, rag: true })).toEqual([
      "Knowledge retrieval (RAG)",
      "Image generation",
    ]);
  });
});

describe("effectiveModelId — override wins over the profile default (ARCH Q1)", () => {
  it("uses the override model when set", () => {
    const state = formState({ profileId: "tool", overrideModelId: "m-override" });
    expect(effectiveModelId(state, LOOKUP)).toBe("m-override");
  });

  it("falls back to the profile's default model when no override", () => {
    expect(effectiveModelId(formState({ profileId: "notool" }), LOOKUP)).toBe("m-notool");
  });

  it("is null when neither profile nor override resolves a model", () => {
    expect(effectiveModelId(formState(), LOOKUP)).toBeNull();
  });
});

describe("toolCapabilityWarning — client mirror of the §9.3 config-time gate", () => {
  it("warns when the profile's default model can't call tools", () => {
    const warn = toolCapabilityWarning(formState({ profileId: "notool" }), LOOKUP);
    expect(warn).toContain("can't call tools");
  });

  it("does not warn for a tool-capable profile", () => {
    expect(toolCapabilityWarning(formState({ profileId: "tool" }), LOOKUP)).toBeNull();
  });

  it("warns when a non-tool override overrides a tool-capable profile", () => {
    const state = formState({ profileId: "tool", overrideModelId: "m-notool" });
    expect(toolCapabilityWarning(state, LOOKUP)).toContain("can't call tools");
  });

  it("does NOT warn on unknown capability (data not loaded) — backend stays the authority", () => {
    const empty: ModelCapabilityLookup = {
      profileDefaultModelId: () => undefined,
      modelSupportsTools: () => undefined,
    };
    expect(toolCapabilityWarning(formState({ profileId: "tool" }), empty)).toBeNull();
  });
});
